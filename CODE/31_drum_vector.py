#!/usr/bin/env python3
"""31_drum_vector.py — "DrumDNA": a dedicated, research-grounded DRUM SIGNATURE.

GrooveDNA (29_groove_dna.py) is an 11-D drum summary folded INTO the 85-D combined
signature. DrumDNA is its bigger sibling: a 72-D *standalone* drum vector with its
own .npy matrix and cosine kNN, so you can search/cluster purely by DRUM FEEL and
even find "the same beat" — independent of pitch/harmony/melody.

It reads the NOTESEQ_DATA cache (no re-parse; same process_bucket/Pool pattern as 22
and 29) and isolates the kit with the SAME proven mask as GrooveDNA so the two agree
on what "drums" are:  drums = (chan 9 OR 10) AND pitch in the GM percussion map 35..81
(AND, not the spec's loose OR — GM pitch numbers only MEAN drums on the drum channel;
an OR would swallow melodic middle-C=60 and destroy isolation). Densities are per 4/4
BAR in BEATS (quarter = tick/tpb), which is tempo-independent (a bar is 4 beats at any
tempo). Sub-beat positions use the 16th-note grid (16 cells/bar, 0.25 beat each).

WHY 72-D (what the 11-D GrooveDNA omits, per the drum-similarity literature —
GrooveToolbox/Bruford, the HVO/MGT feature set, Tutzer's rhythm descriptors, and the
Columbia "eigenrhythm" basis): (1) a fixed-grid PER-VOICE onset fingerprint (the most
discriminative feature for "same beat" retrieval), (2) metric-salience-weighted
syncopation (Longuet-Higgins & Lee), (3) microtiming push/laid-back, and (4) an
accent / one-drop descriptor (STATE.md Open Concern #1: beat-3 accent vs beat-1).

The 72 LOCKED dims (index = position in the drum_dna array — DO NOT REORDER):
  SCALARS (0..19)
   0 kick_density        kicks per bar — the pulse foundation
   1 snare_density       snares per bar
   2 hat_density         hi-hats (closed/pedal/open) per bar
   3 cymbal_density      rides/crashes/splash per bar
   4 tom_density         toms per bar
   5 total_density       all drum onsets per bar — overall busyness
   6 perc_diversity      unique drum voices used (kit colour)
   7 kick_on_downbeat    fraction of kicks landing on beat 1
   8 snare_backbeat      fraction of snares on beats 2 & 4 (the pop signature)
   9 kick_snare_interlock kick/snare complementarity (how much they avoid each other)
  10 swing               0-1 continuous swing (BUR), straight<->shuffle
  11 laidback            signed microtiming: 0.5 on-grid, >0.5 laid-back, <0.5 pushed
  12 timing_tightness    1 = perfectly quantized, 0 = loose/humanized
  13 syncopation_poly    Longuet-Higgins & Lee metric-salience syncopation (0-1)
  14 ghost_dynamics      velocity std on weak 16ths — ghost-note humanization
  15 accent_strength     velocity contrast strong-beats vs weak positions
  16 pattern_entropy     entropy of onset positions in the bar — complexity
  17 bar_variance        mean cosine dist of consecutive bars — fills vs dead loop
  18 symmetry            first-half vs second-half similarity of the bar pattern
  19 pulse_clarity       onset-autocorrelation at the beat lag — metric steadiness
  PER-BEAT ACCENT (20..23)  velocity-energy share on each quarter beat (one-drop=beat3)
  20 beat1_accent  21 beat2_accent  22 beat3_accent  23 beat4_accent
  PER-VOICE 16-STEP ONSET GRID (24..71)  onset probability over the 16 sixteenths
  24..39 kick_g00..15    40..55 snare_g00..15    56..71 hat_g00..15

NaN-safe: a song with NO drum kit returns an ALL-ZERO vector and has_drums=0 (cleaner
than GrooveDNA's overloaded 0.5). For drum songs, an undefined sub-feature falls back
to its per-dim DEFAULT (neutral 0.5 for ratios, 0.0 for densities/grids).

Output: per-bucket _work/drum_dna_parts/<bucket>.parquet (md5 + has_drums + 72 cols),
        merged to _work/drum_dna.parquet.

Usage:
  python3 CODE/31_drum_vector.py                 # extract over all cached buckets
  python3 CODE/31_drum_vector.py --buckets 00,42 # subset
  python3 CODE/31_drum_vector.py --merge-only    # rebuild drum_dna.parquet from parts
  python3 CODE/31_drum_vector.py --validate      # self-test on one real bucket
  python3 CODE/31_drum_vector.py signature       # build signatures_drums.npy + knn_drums.pkl
"""
import os, sys, glob, json, argparse, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "drum_dna.parquet")
PARTS = os.path.join(C.WORK, "drum_dna_parts")
SIG_DIR = os.path.join(C.ROOT, "SIGNATURES_DATA")

# ---- voice families (GM percussion) --------------------------------------
GM_LO, GM_HI = 35, 81
KICK = frozenset({35, 36})
SNARE = frozenset({37, 38, 40})                 # snare + side-stick (clap 39 excluded, as in 29)
TOM = frozenset({41, 43, 45, 47, 48, 50})
HAT = frozenset({42, 44, 46})                   # closed / pedal / open hi-hat
CYM = frozenset({49, 51, 52, 53, 55, 57, 59})   # crashes / rides / splash / china

GRID16 = 16                                     # 16th cells per 4/4 bar (0.25 beat each)
STRONG16 = frozenset({0, 4, 8, 12})             # the four quarter-beats
WEAK16 = frozenset({1, 3, 5, 7, 9, 11, 13, 15}) # odd 16ths — where ghosts live
# Longuet-Higgins & Lee metric salience for the 16 cells (higher = stronger beat):
# beat1=5, beat3=4, beats2&4=3, 8th-offbeats=2, 16ths=1.
LHL = np.array([5, 1, 2, 1, 3, 1, 2, 1, 4, 1, 2, 1, 3, 1, 2, 1], dtype=np.float64)

# ---- locked dimension order ----------------------------------------------
SCALARS = [
    "kick_density", "snare_density", "hat_density", "cymbal_density", "tom_density",
    "total_density", "perc_diversity", "kick_on_downbeat", "snare_backbeat",
    "kick_snare_interlock", "swing", "laidback", "timing_tightness", "syncopation_poly",
    "ghost_dynamics", "accent_strength", "pattern_entropy", "bar_variance", "symmetry",
    "pulse_clarity",
]
ACCENT = [f"beat{i}_accent" for i in range(1, 5)]
GRID = ([f"kick_g{i:02d}" for i in range(16)]
        + [f"snare_g{i:02d}" for i in range(16)]
        + [f"hat_g{i:02d}" for i in range(16)])
DIMS = SCALARS + ACCENT + GRID                  # 20 + 4 + 48 = 72
assert len(DIMS) == 72, len(DIMS)

# per-dim default when a DRUM song leaves a sub-feature undefined (no-drum -> all 0.0).
# ratio/feel dims are neutral 0.5; densities, accent and grid default to 0.0.
RATIO_NEUTRAL = {"kick_on_downbeat", "snare_backbeat", "kick_snare_interlock", "swing",
                 "laidback", "timing_tightness", "syncopation_poly", "ghost_dynamics",
                 "accent_strength", "pattern_entropy", "bar_variance", "symmetry",
                 "pulse_clarity"}
DEFAULTS = {d: (0.5 if d in RATIO_NEUTRAL else 0.0) for d in DIMS}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _drum_mask(arr):
    """Boolean mask isolating the kit: (chan 9|10) AND GM pitch 35..81 (as in 29)."""
    chan, pitch = arr[:, 2], arr[:, 3]
    return ((chan == 9) | (chan == 10)) & (pitch >= GM_LO) & (pitch <= GM_HI)


def _grid_cell(t_beats):
    """0..15 sixteenth cell within the 4/4 bar for each onset (beats)."""
    return (np.round(np.mod(t_beats, 4.0) / 0.25).astype(np.int64) % GRID16)


def _swing_cont(t):
    """0-1 continuous swing from the Beat-Upbeat Ratio over drum onsets (as in 29)."""
    ob = np.sort(np.unique(np.round(t / (1.0 / 48.0)).astype(np.int64))) * (1.0 / 48.0)
    if len(ob) < 4:
        return DEFAULTS["swing"]
    beat_idx = np.floor(ob + 1e-6).astype(np.int64)
    phase = ob - beat_idx
    from collections import defaultdict
    by_beat = defaultdict(list)
    for b, p in zip(beat_idx, phase):
        by_beat[b].append(p)
    burs, n_onbeat = [], 0
    for ps in by_beat.values():
        ps = sorted(ps)
        if not any(p < 0.15 for p in ps):
            continue
        n_onbeat += 1
        if any(0.15 < p <= 0.40 for p in ps):
            continue
        mids = [p for p in ps if 0.40 < p < 0.72]
        if len(mids) == 1:
            burs.append(mids[0] / (1.0 - mids[0]))
    if not burs or n_onbeat == 0:
        return DEFAULTS["swing"]
    base = np.clip((float(np.median(burs)) - 1.0), 0.0, 1.0)
    return float(np.clip(base * (0.5 + 0.5 * len(burs) / n_onbeat), 0.0, 1.0))


def _microtiming(t):
    """(laidback, tightness): signed mean offset from the nearest 16th + its magnitude.

    offset in beats; a 16th cell is 0.25 beat, so max meaningful deviation = ±0.125.
    laidback: 0.5 = on-grid, >0.5 = late/laid-back, <0.5 = early/pushed.
    tightness: 1 = perfectly quantized, 0 = half-cell loose."""
    if len(t) < 4:
        return DEFAULTS["laidback"], DEFAULTS["timing_tightness"]
    phase = np.mod(t, 4.0)
    off = phase - np.round(phase / 0.25) * 0.25       # signed beats from nearest 16th
    laid = 0.5 + np.clip(float(np.mean(off)) / 0.125, -1.0, 1.0) * 0.5
    tight = 1.0 - np.clip(float(np.mean(np.abs(off))) / 0.125, 0.0, 1.0)
    return float(laid), float(tight)


def _lhl_syncopation(bar_grids):
    """Mean Longuet-Higgins & Lee syncopation over per-bar binary 16-onset vectors.

    A syncopation event = an onset at a weak cell followed by NO onset at the next
    (cyclic) stronger cell; its weight = salience(stronger) - salience(weaker).
    Summed per bar, normalized by the max possible, averaged across bars."""
    if not bar_grids:
        return DEFAULTS["syncopation_poly"]
    maxw = float(LHL.max() - LHL.min()) * 4.0          # ~ a few strong rests; normalizer
    scores = []
    for g in bar_grids:
        s = 0.0
        for i in range(GRID16):
            j = (i + 1) % GRID16
            if g[i] and not g[j] and LHL[j] > LHL[i]:
                s += LHL[j] - LHL[i]
        scores.append(min(s / maxw, 1.0) if maxw > 0 else 0.0)
    return float(np.mean(scores))


def _voice_grid(cells, n_bars):
    """Onset-probability over the 16 cells for one voice (sums to 1, or all-zero)."""
    h = np.bincount(cells, minlength=GRID16).astype(np.float64)
    s = h.sum()
    return (h / s) if s > 0 else h


def drum_of(arr, tpb):
    """Compute the 72-D DrumDNA for one note-sequence. Returns (has_drums, {dim: val})."""
    f = dict(DEFAULTS)
    if arr is None or len(arr) == 0 or tpb <= 0:
        return 0, {d: 0.0 for d in DIMS}          # no notes -> all-zero, has_drums=0
    drums = arr[_drum_mask(arr)]
    if len(drums) == 0:
        return 0, {d: 0.0 for d in DIMS}          # no kit -> all-zero, has_drums=0

    pitch = drums[:, 3]
    vel = drums[:, 4].astype(np.float64)
    t = drums[:, 0].astype(np.float64) / tpb      # onset times in beats (tempo-independent)
    bar = np.floor(t / 4.0).astype(np.int64)
    n_bars = max(float(bar.max() - bar.min() + 1), 1.0)
    cell = _grid_cell(t)                          # 0..15 cell per onset

    kick_m = np.isin(pitch, list(KICK))
    snare_m = np.isin(pitch, list(SNARE))
    hat_m = np.isin(pitch, list(HAT))
    cym_m = np.isin(pitch, list(CYM))
    tom_m = np.isin(pitch, list(TOM))

    # --- densities (per bar) + diversity ---
    f["kick_density"] = float(kick_m.sum()) / n_bars
    f["snare_density"] = float(snare_m.sum()) / n_bars
    f["hat_density"] = float(hat_m.sum()) / n_bars
    f["cymbal_density"] = float(cym_m.sum()) / n_bars
    f["tom_density"] = float(tom_m.sum()) / n_bars
    f["total_density"] = float(len(drums)) / n_bars
    f["perc_diversity"] = float(len(np.unique(pitch)))

    # --- kick on the downbeat (beat 1) ---
    if kick_m.any():
        kph = np.mod(t[kick_m], 4.0)
        f["kick_on_downbeat"] = float(((kph <= 0.15) | (kph >= 3.85)).mean())
    # --- snare backbeat (beats 2 & 4) ---
    if snare_m.any():
        sph = np.mod(t[snare_m], 4.0)
        f["snare_backbeat"] = float(((np.abs(sph - 1.0) <= 0.15)
                                     | (np.abs(sph - 3.0) <= 0.15)).mean())

    # --- per-voice aggregate grids (also feed interlock/symmetry/entropy) ---
    kg_cnt = np.bincount(cell[kick_m], minlength=GRID16).astype(np.float64)
    sg_cnt = np.bincount(cell[snare_m], minlength=GRID16).astype(np.float64)
    all_cnt = np.bincount(cell, minlength=GRID16).astype(np.float64)
    kb, sb = kg_cnt > 0, sg_cnt > 0
    either = kb | sb
    if either.any():
        f["kick_snare_interlock"] = float((kb ^ sb).sum()) / float(either.sum())

    # --- swing + microtiming ---
    f["swing"] = _swing_cont(t)
    f["laidback"], f["timing_tightness"] = _microtiming(t)

    # --- syncopation (LHL) over per-bar binary onset grids ---
    bars_present = np.unique(bar)
    bpos = {b: i for i, b in enumerate(bars_present)}
    mat = np.zeros((len(bars_present), GRID16), dtype=np.float64)
    for bi, ci in zip(bar, cell):
        mat[bpos[bi], ci] += 1.0
    f["syncopation_poly"] = _lhl_syncopation([(row > 0).astype(np.int64) for row in mat])

    # --- ghost dynamics + accent contrast ---
    weak = np.isin(cell, list(WEAK16))
    strong = np.isin(cell, list(STRONG16))
    if weak.sum() >= 2:
        f["ghost_dynamics"] = float(np.clip(np.std(vel[weak]) / 127.0, 0.0, 1.0))
    if strong.any() and weak.any():
        f["accent_strength"] = float(np.clip(
            (vel[strong].mean() - vel[weak].mean()) / 127.0, 0.0, 1.0))

    # --- pattern entropy over the 16 cells ---
    if all_cnt.sum() > 0:
        p = all_cnt[all_cnt > 0] / all_cnt.sum()
        f["pattern_entropy"] = float(-(p * np.log2(p)).sum() / np.log2(GRID16))

    # --- bar-to-bar variance (fills) ---
    if len(bars_present) >= 2:
        dists = []
        for i in range(len(bars_present) - 1):
            u, v = mat[i], mat[i + 1]
            nu, nv = np.linalg.norm(u), np.linalg.norm(v)
            if nu > 0 and nv > 0:
                dists.append(1.0 - float(u @ v) / (nu * nv))
        if dists:
            f["bar_variance"] = float(np.clip(np.mean(dists), 0.0, 1.0))

    # --- symmetry: first half vs second half of the mean bar pattern ---
    h1, h2 = all_cnt[:8], all_cnt[8:]
    n1, n2 = np.linalg.norm(h1), np.linalg.norm(h2)
    if n1 > 0 and n2 > 0:
        f["symmetry"] = float(h1 @ h2 / (n1 * n2))

    # --- pulse clarity: onset autocorrelation at the 1-beat (4-cell) lag ---
    env = all_cnt - all_cnt.mean()
    ac0 = float(env @ env)
    if ac0 > 0:
        ac4 = float(np.sum(env * np.roll(env, 4)))
        f["pulse_clarity"] = float(np.clip(ac4 / ac0, 0.0, 1.0))

    # --- per-beat accent: velocity-energy share on each quarter beat ---
    beat_of = np.clip(np.floor(np.mod(t, 4.0)).astype(np.int64), 0, 3)
    be = np.array([vel[beat_of == b].sum() for b in range(4)], dtype=np.float64)
    if be.sum() > 0:
        be = be / be.sum()
        for i in range(4):
            f[f"beat{i+1}_accent"] = float(be[i])

    # --- per-voice 16-step onset-probability grids ---
    for name, m in (("kick", kick_m), ("snare", snare_m), ("hat", hat_m)):
        g = _voice_grid(cell[m], n_bars)
        for i in range(16):
            f[f"{name}_g{i:02d}"] = float(g[i])

    return 1, f


# ---------------------------------------------------------------------------
# bucket extraction (same NOTESEQ cache + Pool pattern as 29)
# ---------------------------------------------------------------------------
COLS = ["md5", "has_drums"] + DIMS                # locked parquet column order


def process_bucket(bucket):
    """Compute DrumDNA for one cache bucket. Writes the part parquet AND returns the
    DataFrame (md5 + has_drums + 72 dims = 74 cols), so it doubles as validation."""
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
            has, feats = drum_of(z[md5], int(tpbs.get(md5, 480)))
        except Exception:  # noqa: BLE001 — one bad file never kills a bucket
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
# signature mode: build standalone drum signature matrix + cosine kNN
# ---------------------------------------------------------------------------
LOG_MAX = 50.0                                   # log1p non-negative cols whose max exceeds this
CLIP = 8.0                                        # clip z-scores to +/- this many SD
# three equal-weight blocks so the 48-D grid can't swamp the 20 scalars / 4 accents.
BLOCKS = {"scalar": SCALARS, "accent": ACCENT, "grid": GRID}


def _scale_block(X):
    """Per-column: log1p heavy non-neg tails -> median impute -> z-score -> clip."""
    X = np.array(X, dtype=np.float64, copy=True)
    for j in range(X.shape[1]):
        col = X[:, j]
        finite = col[np.isfinite(col)]
        if finite.size and finite.min() >= 0 and finite.max() > LOG_MAX:
            col = np.log1p(col)
        nan = ~np.isfinite(col)
        if nan.any():
            med = np.nanmedian(np.where(np.isfinite(col), col, np.nan))
            col[nan] = med if np.isfinite(med) else 0.0
        mu, sd = col.mean(), col.std()
        col = (col - mu) / sd if sd > 1e-12 else col - mu
        X[:, j] = np.clip(col, -CLIP, CLIP)
    return X


def _l2(X):
    """Per-row L2-normalize; zero-norm rows stay zero."""
    n = np.linalg.norm(X, axis=1, keepdims=True)
    return np.divide(X, n, out=np.zeros_like(X), where=n > 1e-12)


def build_signature():
    """Align DrumDNA to signatures_md5.txt order, block-scale + L2, write the
    standalone drum signature matrix and a cosine kNN fit over the drum-bearing rows.
    Existing signatures_*.npy / knn_cosine.pkl are NEVER touched."""
    import pickle, shutil
    from datetime import datetime
    from sklearn.neighbors import NearestNeighbors

    idx_path = os.path.join(SIG_DIR, "signatures_md5.txt")
    with open(idx_path) as fh:
        md5s = [l.strip() for l in fh if l.strip()]
    if not os.path.exists(OUT):
        sys.exit(f"[31] {OUT} missing — run extraction first")
    dna = pd.read_parquet(OUT).drop_duplicates("md5").set_index("md5").reindex(md5s)
    C.log(f"31_signature: {len(md5s)} signature rows; "
          f"{int(dna['has_drums'].fillna(0).sum())} have drums", "drum.log")

    has = dna["has_drums"].fillna(0).to_numpy().astype(bool)
    parts, block_dims = [], {}
    for name, cols in BLOCKS.items():
        Xlw = _l2(_scale_block(dna[cols].to_numpy()))   # equal weight (sqrt(1)=1)
        parts.append(Xlw)
        block_dims[name] = len(cols)
    sig = np.concatenate(parts, axis=1).astype(np.float32)
    sig[~has] = 0.0                                  # drumless rows -> zero vector
    assert sig.shape == (len(md5s), 72), sig.shape

    out_npy = os.path.join(SIG_DIR, "signatures_drums.npy")
    np.save(out_npy, sig)
    C.log(f"31_signature: saved {out_npy} {sig.shape} ({os.path.getsize(out_npy)/1e6:.1f} MB)", "drum.log")

    fit_rows = np.where(has)[0]                      # cosine kNN over drum songs only
    nn = NearestNeighbors(n_neighbors=12, metric="cosine", algorithm="brute")
    nn.fit(sig[fit_rows])
    knn_path = os.path.join(SIG_DIR, "knn_drums.pkl")
    if os.path.exists(knn_path):
        shutil.copy2(knn_path, knn_path + f".bak_{datetime.now():%Y%m%d_%H%M%S}")
    with open(knn_path, "wb") as fh:
        pickle.dump({"nn": nn, "fit_rows": fit_rows, "matrix": "signatures_drums.npy",
                     "metric": "cosine", "block_dims": block_dims, "dims": DIMS,
                     "built": datetime.now().isoformat(timespec="seconds")}, fh, protocol=4)
    C.log(f"31_signature: saved {knn_path} (kNN over {len(fit_rows)} drum rows)", "drum.log")


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
        print(f"[31] merged {len(parts)} buckets -> {OUT} ({len(df)} rows)")
        return

    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ, "*.npz")))
    if args.buckets:
        want = set(args.buckets.split(","))
        buckets = [b for b in buckets if b in want]
    C.log(f"31_drum_vector: {len(buckets)} cached buckets (workers={args.workers})", "drum.log")

    from multiprocessing import Pool
    t0, done = time.time(), 0
    with Pool(args.workers) as pool:
        for i, df in enumerate(pool.imap_unordered(process_bucket, buckets), 1):
            done += len(df)
            if i % 16 == 0 or i == len(buckets):
                C.log(f"  [{i}/{len(buckets)}] {done} files {done/(time.time()-t0):.0f}/s", "drum.log")

    parts, df = _merge()
    print(f"[31] DONE -> {OUT} ({len(df)} rows, {df.shape[1]} cols)")
    hd = df["has_drums"].astype(bool)
    print(f"[31] files with a drum kit: {int(hd.sum())} / {len(df)}")
    if hd.any():
        d = df.loc[hd]
        print(f"[31] medians (drum files): kick/bar={d['kick_density'].median():.2f}  "
              f"backbeat={d['snare_backbeat'].median():.2f}  swing={d['swing'].median():.2f}  "
              f"sync={d['syncopation_poly'].median():.2f}  "
              f"entropy={d['pattern_entropy'].median():.2f}  "
              f"beat3acc={d['beat3_accent'].median():.2f}")


def _validate():
    """Self-test on a couple of real buckets: locked shape, dtype, NaN-safety, sane reads."""
    for b in ("00", "42"):
        df = process_bucket(b)
        if len(df) == 0:
            print(f"[validate] bucket {b}: empty/missing, skipping")
            continue
        assert list(df.columns) == COLS, f"bucket {b}: column order is not locked"
        assert len(df.columns) == 74, f"bucket {b}: expected 74 cols, got {len(df.columns)}"
        assert all(str(df[d].dtype) == "float32" for d in DIMS), "all 72 dims must be float32"
        assert not df[DIMS].isna().any().any(), "DrumDNA must be NaN-safe"
        # drumless rows must be all-zero with has_drums=0
        drumless = df[df["has_drums"] == 0]
        if len(drumless):
            assert (drumless[DIMS].to_numpy() == 0).all(), "drumless rows must be all-zero"
        hd = df[df["has_drums"] == 1]
        print(f"[validate] bucket {b}: {len(df)} files, {len(hd)} with drums  ✓")
        if len(hd):
            print(f"    kick/bar median={hd['kick_density'].median():.2f}  "
                  f"backbeat={hd['snare_backbeat'].median():.2f}  "
                  f"beat3_accent={hd['beat3_accent'].median():.2f}")
    print("DrumDNA validated ✓ (locked 74-col shape, float32, NaN-safe, drumless->zero)")


if __name__ == "__main__":
    if "--validate" in sys.argv:
        _validate()
    elif "signature" in sys.argv:
        build_signature()
    else:
        main()
