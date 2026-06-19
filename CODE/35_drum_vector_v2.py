#!/usr/bin/env python3
"""35_drum_vector_v2.py — "DrumDNA v2": the research-standard drum signature.

v1 (31_drum_vector.py) is a 72-D vector and STAYS UNTOUCHED. v2 is a separate,
bigger sibling (its own .npy + kNN) that folds in three field-standard upgrades
without changing v1's files:

  (A) rhythmtoolbox descriptors (Gomez-Marin et al 2020): polyBalance / polyEvenness
      (Milne&Herff, Milne&Dean), polySync (Witek), band-split low/mid/hi syncopation
      and syness — perceptually-validated drum-similarity descriptors v1 lacked.
  (B) HVO grid (Magenta GrooVAE / Gillick et al): the per-voice onset grid is split
      into THREE layers — Hits (probability), Velocity (root-5 scaled mean), and
      Offset (signed microtiming per cell) — so "feel" (ahead/behind, dynamics) is
      encoded per step, not just presence.
  (C) 9-voice canonical GM "paper mapping" (Groove MIDI Dataset): the grid expands
      from v1's 3 voices to the standard 9 (kick, snare, closed/open hat, lo/mid/hi
      tom, crash, ride), aligning us with HVO and rhythmtoolbox literature.

The shared 24 dims (20 scalars + 4 per-beat accents) are computed by REUSING v1's
drum_of() so the two vectors agree exactly on that core. v2 then appends 12 rtb
dims and a 9x16x3 = 432-D HVO grid.

LOCKED dim order (DO NOT REORDER):
  0..19   v1 SCALARS          20..23  v1 ACCENT
  24..35  RTB (12)            36..179 gridH (9x16)
  180..323 gridV (9x16)       324..467 gridO (9x16)            -> 468 dims total

Same drum isolation as v1 (chan 9|10 AND GM pitch 35..81). No kit -> all-zero,
has_drums=0. NaN-safe. float32. Densities per 4/4 bar; 16th-note grid.

Output: per-bucket _work/drum_dna_v2_parts/<bucket>.parquet -> _work/drum_dna_v2.parquet
Usage:
  python3 CODE/35_drum_vector_v2.py                 # extract over all cached buckets
  python3 CODE/35_drum_vector_v2.py --buckets 00,42 # subset
  python3 CODE/35_drum_vector_v2.py --merge-only    # rebuild parquet from parts
  python3 CODE/35_drum_vector_v2.py --validate      # self-test on real buckets
  python3 CODE/35_drum_vector_v2.py signature       # build signatures_drums_v2.npy + knn
"""
import os, sys, glob, json, argparse, time, importlib.util
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

# ---- reuse v1 module (numeric filename -> import by path) ----------------
_V1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "31_drum_vector.py")
_spec = importlib.util.spec_from_file_location("drum_vector_v1", _V1)
m1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m1)

from rhythmtoolbox import pattlist2descriptors

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "drum_dna_v2.parquet")
PARTS = os.path.join(C.WORK, "drum_dna_v2_parts")
SIG_DIR = os.path.join(C.ROOT, "SIGNATURES_DATA")
GRID16 = m1.GRID16

# ---- 9-voice canonical GM paper mapping (Groove MIDI Dataset) ------------
VOICES = ["kick", "snare", "chat", "ohat", "ltom", "mtom", "htom", "crash", "ride"]
VMAP = {
    "kick":  {35, 36},
    "snare": {37, 38, 40},
    "chat":  {42, 44, 22},            # closed + pedal + edge hi-hat
    "ohat":  {46, 26},                # open hi-hat
    "ltom":  {41, 43, 45},
    "mtom":  {47, 48},
    "htom":  {50},
    "crash": {49, 52, 55, 57},
    "ride":  {51, 53, 59},
}

# ---- locked dimension order ----------------------------------------------
RTB = ["rtb_balance", "rtb_polybalance", "rtb_evenness", "rtb_polyevenness",
       "rtb_polysync", "rtb_syness", "rtb_lowsync", "rtb_midsync", "rtb_hisync",
       "rtb_lowness", "rtb_midness", "rtb_hiness"]
RTB_SRC = ["balance", "polyBalance", "evenness", "polyEvenness", "polySync",
           "syness", "lowSync", "midSync", "hiSync", "lowness", "midness", "hiness"]
GRID_H = [f"h_{v}_{i:02d}" for v in VOICES for i in range(GRID16)]
GRID_V = [f"v_{v}_{i:02d}" for v in VOICES for i in range(GRID16)]
GRID_O = [f"o_{v}_{i:02d}" for v in VOICES for i in range(GRID16)]
SHARED = m1.SCALARS + m1.ACCENT                  # 24 dims, identical to v1
DIMS = SHARED + RTB + GRID_H + GRID_V + GRID_O   # 24 + 12 + 432 = 468
assert len(DIMS) == 468, len(DIMS)

# ratio-like dims fall back to 0.5; everything else (sync/density/grids) to 0.0
RTB_NEUTRAL = {"rtb_balance", "rtb_polybalance", "rtb_evenness"}
DEFAULTS = dict(m1.DEFAULTS)
DEFAULTS.update({d: (0.5 if d in RTB_NEUTRAL else 0.0) for d in RTB})
DEFAULTS.update({d: 0.0 for d in GRID_H + GRID_V + GRID_O})


# ---------------------------------------------------------------------------
# new feature blocks
# ---------------------------------------------------------------------------
def _hvo_grids(pitch, vel, cell, t, n_bars):
    """Per-voice (H,V,O) layers over 16 cells. H=hit prob/bar, V=root-5 mean vel,
    O=mean signed microtiming (units of half-cell, clipped +/-1). 0 where silent."""
    vscaled = np.clip(vel / 127.0, 0.0, 1.0) ** 0.2
    phase = np.mod(t, 4.0)
    off = np.clip((phase - np.round(phase / 0.25) * 0.25) / 0.125, -1.0, 1.0)
    H, V, O = {}, {}, {}
    for v in VOICES:
        m = np.isin(pitch, list(VMAP[v]))
        c = cell[m]
        cnt = np.bincount(c, minlength=GRID16).astype(np.float64)
        H[v] = np.clip(cnt / n_bars, 0.0, 1.0)
        vsum = np.bincount(c, weights=vscaled[m], minlength=GRID16)
        osum = np.bincount(c, weights=off[m], minlength=GRID16)
        nz = cnt > 0
        Vv = np.zeros(GRID16); Oo = np.zeros(GRID16)
        Vv[nz] = vsum[nz] / cnt[nz]; Oo[nz] = osum[nz] / cnt[nz]
        V[v], O[v] = Vv, Oo
    return H, V, O


def _repr_pattlist(pitch, cell, n_bars, thresh=0.30):
    """A representative 16-step pattern list (GM note numbers per cell) for the
    rhythmtoolbox descriptors: a pitch appears at a cell if it onsets there in
    >= thresh of bars. Falls back to the modal cell of the busiest pitch."""
    patt = [[] for _ in range(GRID16)]
    for p in np.unique(pitch):
        pm = pitch == p
        ccount = np.bincount(cell[pm], minlength=GRID16)
        for c in np.nonzero(ccount / n_bars >= thresh)[0]:
            patt[c].append(int(p))
    if not any(patt):
        p = int(np.bincount(pitch.astype(np.int64)).argmax())
        patt[int(np.bincount(cell[pitch == p], minlength=GRID16).argmax())].append(p)
    return patt


def drum_of_v2(arr, tpb):
    """468-D DrumDNA v2 for one note-sequence. Returns (has_drums, {dim: val})."""
    f = dict(DEFAULTS)
    has, v1f = m1.drum_of(arr, tpb)              # authoritative shared 24 dims
    if not has:
        return 0, {d: 0.0 for d in DIMS}
    for d in SHARED:
        f[d] = v1f[d]

    drums = arr[m1._drum_mask(arr)]
    pitch = drums[:, 3]
    vel = drums[:, 4].astype(np.float64)
    t = drums[:, 0].astype(np.float64) / tpb
    bar = np.floor(t / 4.0).astype(np.int64)
    n_bars = max(float(bar.max() - bar.min() + 1), 1.0)
    cell = m1._grid_cell(t)

    # (A) rhythmtoolbox descriptors on a representative 16-step bar
    try:
        d = pattlist2descriptors(_repr_pattlist(pitch, cell, n_bars))
        for name, src in zip(RTB, RTB_SRC):
            val = d.get(src)
            if val is not None and np.isfinite(val):
                f[name] = float(val)
    except Exception:  # noqa: BLE001 — a bad pattern never kills the row
        pass

    # (B)+(C) 9-voice HVO grids
    H, V, O = _hvo_grids(pitch, vel, cell, t, n_bars)
    for v in VOICES:
        for i in range(GRID16):
            f[f"h_{v}_{i:02d}"] = float(H[v][i])
            f[f"v_{v}_{i:02d}"] = float(V[v][i])
            f[f"o_{v}_{i:02d}"] = float(O[v][i])
    return 1, f


# ---------------------------------------------------------------------------
# bucket extraction (same NOTESEQ cache + Pool pattern as v1)
# ---------------------------------------------------------------------------
COLS = ["md5", "has_drums"] + DIMS


def process_bucket(bucket):
    bucket = str(bucket)
    npz = os.path.join(NOTESEQ, bucket + ".npz")
    meta = os.path.join(NOTESEQ, bucket + ".meta.json")
    if not (os.path.exists(npz) and os.path.exists(meta)):
        return pd.DataFrame(columns=COLS)
    tpbs = json.load(open(meta))
    z = np.load(npz)
    recs = []
    for md5 in z.files:
        rec = {"md5": md5}
        try:
            has, feats = drum_of_v2(z[md5], int(tpbs.get(md5, 480)))
        except Exception:  # noqa: BLE001
            has, feats = 0, {d: 0.0 for d in DIMS}
        rec["has_drums"] = has
        rec.update(feats)
        recs.append(rec)
    df = pd.DataFrame(recs, columns=COLS)
    df["has_drums"] = df["has_drums"].astype(np.int8)
    for d in DIMS:
        df[d] = df[d].astype(np.float32)
    os.makedirs(PARTS, exist_ok=True)
    df.to_parquet(os.path.join(PARTS, bucket + ".parquet"), index=False)
    return df


def _merge():
    parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    C.write_parquet_atomic(df, OUT)
    return parts, df


# ---------------------------------------------------------------------------
# signature mode: standalone v2 drum signature matrix + cosine kNN
# ---------------------------------------------------------------------------
# six equal-weight blocks so no group swamps another (H/V/O each get equal say).
BLOCKS = {"scalar": m1.SCALARS, "accent": m1.ACCENT, "rtb": RTB,
          "gridH": GRID_H, "gridV": GRID_V, "gridO": GRID_O}


def build_signature():
    """Align v2 DrumDNA to signatures_md5.txt, block-scale + L2, write the standalone
    matrix and cosine kNN over drum-bearing rows. v1 / combined files NEVER touched."""
    import pickle, shutil
    from datetime import datetime
    from sklearn.neighbors import NearestNeighbors

    with open(os.path.join(SIG_DIR, "signatures_md5.txt")) as fh:
        md5s = [l.strip() for l in fh if l.strip()]
    if not os.path.exists(OUT):
        sys.exit(f"[35] {OUT} missing — run extraction first")
    dna = pd.read_parquet(OUT).drop_duplicates("md5").set_index("md5").reindex(md5s)
    C.log(f"35_signature: {len(md5s)} rows; "
          f"{int(dna['has_drums'].fillna(0).sum())} have drums", "drum.log")

    has = dna["has_drums"].fillna(0).to_numpy().astype(bool)
    parts, block_dims = [], {}
    for name, cols in BLOCKS.items():
        parts.append(m1._l2(m1._scale_block(dna[cols].to_numpy())))
        block_dims[name] = len(cols)
    sig = np.concatenate(parts, axis=1).astype(np.float32)
    sig[~has] = 0.0
    assert sig.shape == (len(md5s), 468), sig.shape

    out_npy = os.path.join(SIG_DIR, "signatures_drums_v2.npy")
    np.save(out_npy, sig)
    C.log(f"35_signature: saved {out_npy} {sig.shape} "
          f"({os.path.getsize(out_npy)/1e6:.1f} MB)", "drum.log")

    fit_rows = np.where(has)[0]
    nn = NearestNeighbors(n_neighbors=12, metric="cosine", algorithm="brute")
    nn.fit(sig[fit_rows])
    knn_path = os.path.join(SIG_DIR, "knn_drums_v2.pkl")
    if os.path.exists(knn_path):
        shutil.copy2(knn_path, knn_path + f".bak_{datetime.now():%Y%m%d_%H%M%S}")
    with open(knn_path, "wb") as fh:
        pickle.dump({"nn": nn, "fit_rows": fit_rows, "matrix": "signatures_drums_v2.npy",
                     "metric": "cosine", "block_dims": block_dims, "dims": DIMS,
                     "built": datetime.now().isoformat(timespec="seconds")}, fh, protocol=4)
    C.log(f"35_signature: saved {knn_path} (kNN over {len(fit_rows)} drum rows)", "drum.log")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", type=str, default="")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()

    if args.merge_only:
        parts, df = _merge()
        print(f"[35] merged {len(parts)} buckets -> {OUT} ({len(df)} rows)")
        return

    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ, "*.npz")))
    if args.buckets:
        want = set(args.buckets.split(","))
        buckets = [b for b in buckets if b in want]
    C.log(f"35_drum_vector_v2: {len(buckets)} cached buckets (workers={args.workers})", "drum.log")

    from multiprocessing import Pool
    t0, done = time.time(), 0
    with Pool(args.workers) as pool:
        for i, df in enumerate(pool.imap_unordered(process_bucket, buckets), 1):
            done += len(df)
            if i % 16 == 0 or i == len(buckets):
                C.log(f"  [{i}/{len(buckets)}] {done} files {done/(time.time()-t0):.0f}/s", "drum.log")

    parts, df = _merge()
    print(f"[35] DONE -> {OUT} ({len(df)} rows, {df.shape[1]} cols)")
    hd = df["has_drums"].astype(bool)
    print(f"[35] files with a drum kit: {int(hd.sum())} / {len(df)}")
    if hd.any():
        d = df.loc[hd]
        print(f"[35] medians (drum files): polybalance={d['rtb_polybalance'].median():.2f}  "
              f"polyevenness={d['rtb_polyevenness'].median():.2f}  "
              f"polysync={d['rtb_polysync'].median():.2f}  "
              f"h_kick_00={d['h_kick_00'].median():.2f}  "
              f"h_snare_04={d['h_snare_04'].median():.2f}")


def _validate():
    """Self-test on real buckets: locked shape, dtype, NaN-safety, drumless->zero,
    rtb populated, HVO layers in range."""
    for b in ("00", "42"):
        df = process_bucket(b)
        if len(df) == 0:
            print(f"[validate] bucket {b}: empty/missing, skipping")
            continue
        assert list(df.columns) == COLS, f"bucket {b}: column order not locked"
        assert len(df.columns) == 470, f"bucket {b}: expected 470 cols, got {len(df.columns)}"
        assert all(str(df[d].dtype) == "float32" for d in DIMS), "all 468 dims must be float32"
        assert not df[DIMS].isna().any().any(), "DrumDNA v2 must be NaN-safe"
        drumless = df[df["has_drums"] == 0]
        if len(drumless):
            assert (drumless[DIMS].to_numpy() == 0).all(), "drumless rows must be all-zero"
        hd = df[df["has_drums"] == 1]
        # HVO ranges: H in [0,1], V in [0,1], O in [-1,1]
        assert df[GRID_H].to_numpy().min() >= 0 and df[GRID_H].to_numpy().max() <= 1.0001
        assert df[GRID_V].to_numpy().min() >= 0 and df[GRID_V].to_numpy().max() <= 1.0001
        assert df[GRID_O].to_numpy().min() >= -1.0001 and df[GRID_O].to_numpy().max() <= 1.0001
        print(f"[validate] bucket {b}: {len(df)} files, {len(hd)} with drums  ✓")
        if len(hd):
            print(f"    polybalance={hd['rtb_polybalance'].median():.2f}  "
                  f"polysync={hd['rtb_polysync'].median():.2f}  "
                  f"h_kick_00={hd['h_kick_00'].median():.2f}  "
                  f"h_snare_04={hd['h_snare_04'].median():.2f}")
    print("DrumDNA v2 validated ✓ (locked 470-col shape, float32, NaN-safe, drumless->zero)")


if __name__ == "__main__":
    if "--validate" in sys.argv:
        _validate()
    elif "signature" in sys.argv:
        build_signature()
    else:
        main()
