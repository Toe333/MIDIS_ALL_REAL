#!/usr/bin/env python3
"""51_tbb_feature.py — TBB v1 corpus feature (SAFE / additive / versioned).

Computes `tbb_cos` = cosine similarity of every song's DrumDNA (31's 72-D drum
signature space) to the LOCKED TBB beat (DRUM_PATTERNS/TBB_locked.mid), then:
  (1) adds `tbb_cos` as a NON-destructive column to metadata.parquet + catalog.sqlite,
  (2) writes a VERSIONED SIGNATURES_DATA/signatures_ext_tbb_v1.npy = current N×88 ext
      with tbb_cos appended as dim 89 at ×3 weight (that dim only) + its own kNN.

The canonical signatures_ext.npy / knn_cosine.pkl are NEVER touched (orcamang's safe
plan; codemang's reversible design). Re-run anytime; it overwrites only the *_tbb_v1
artifacts and the additive column.
"""
import os, sys, pickle, importlib.util
import numpy as np, pandas as pd, mido

ROOT = os.environ.get("MAR_ROOT", "/mnt/2FAST/MIDIS_ALL_REAL")
CODE = os.path.join(ROOT, "CODE")
SIG = os.path.join(ROOT, "SIGNATURES_DATA")
WORK = os.path.join(ROOT, "_work")
CAT = os.path.join(ROOT, "catalog")
TBB_MID = os.path.join(ROOT, "DRUM_PATTERNS", "TBB_locked.mid")
TBB_W = 3.0   # ×3 weight on the new dim, that dim only


def _load(modfile, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(CODE, modfile))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def parse_mid_to_arr(path):
    """MIDI -> np.int64[N,5] = (start_tick, dur_tick, chan, pitch, vel), + tpb."""
    mid = mido.MidiFile(path)
    tpb = mid.ticks_per_beat
    ev = []
    for tr in mid.tracks:
        t = 0
        active = {}
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                k = (msg.channel, msg.note)
                if active.get(k):
                    st, v = active[k].pop(0)
                    ev.append((st, max(1, t - st), msg.channel, msg.note, v))
    return np.array(ev, dtype=np.int64), tpb


def main():
    d31 = _load("31_drum_vector.py", "d31")
    drum_of, _scale_block, _l2 = d31.drum_of, d31._scale_block, d31._l2
    BLOCKS, DIMS = d31.BLOCKS, d31.DIMS

    # --- 1. TBB raw 72-D ---
    arr, tpb = parse_mid_to_arr(TBB_MID)
    has, feats = drum_of(arr, tpb)
    assert has, "TBB MIDI has no drum kit?!"
    tbb_raw = np.array([feats[d] for d in DIMS], dtype=np.float64)
    print(f"[51] TBB parsed: {len(arr)} notes, has_drums={has}")

    # --- 2. embed TBB into the signatures_drums space (replicate 31 per-block scale+L2) ---
    dna = pd.read_parquet(os.path.join(WORK, "drum_dna.parquet"))
    sig_drums = np.load(os.path.join(SIG, "signatures_drums.npy"))   # N×72, md5-aligned
    md5s = open(os.path.join(SIG, "signatures_md5.txt")).read().split()
    assert sig_drums.shape[0] == len(md5s)

    tbb_blocks = []
    for name, cols in BLOCKS.items():
        Xc = dna[cols].to_numpy(dtype=np.float64)
        Xt = tbb_raw[[DIMS.index(c) for c in cols]][None, :]
        scaled = _l2(_scale_block(np.vstack([Xc, Xt])))   # corpus stats dominate; TBB = last row
        tbb_blocks.append(scaled[-1])
    tbb_vec = np.concatenate(tbb_blocks).astype(np.float64)            # 72-D, comparable to sig_drums

    # cosine of every corpus drum row to TBB (zero rows -> 0)
    sd_norm = np.linalg.norm(sig_drums, axis=1)
    tv_norm = np.linalg.norm(tbb_vec)
    tbb_cos = np.zeros(sig_drums.shape[0], dtype=np.float64)
    nz = sd_norm > 1e-9
    tbb_cos[nz] = (sig_drums[nz] @ tbb_vec) / (sd_norm[nz] * tv_norm)
    print(f"[51] tbb_cos: median={np.median(tbb_cos[nz]):.3f} max={tbb_cos.max():.3f} "
          f">0.78: {(tbb_cos > 0.78).sum()}  (over {int(nz.sum())} drum-bearing rows)")
    top = np.argsort(-tbb_cos)[:5]
    print("[51] top-5 tbb_cos md5:", [(md5s[i][:8], round(float(tbb_cos[i]), 3)) for i in top])

    cos_by_md5 = dict(zip(md5s, tbb_cos))

    # --- 3. write tbb_cos to a SEPARATE, left-mergeable parquet (NON-destructive;
    #        canonical metadata.parquet / catalog.sqlite are NOT touched — fold later
    #        with explicit user OK, same staging pattern as GrooveDNA/DrumDNA) ---
    feat = pd.DataFrame({"md5": md5s, "tbb_cos": tbb_cos.astype("float32")})
    out_feat = os.path.join(WORK, "tbb_cos.parquet")
    feat.to_parquet(out_feat, index=False)
    print(f"[51] saved {out_feat}  ({len(feat)} rows; left-merge on md5 to fold into catalog)")

    # --- 4. versioned signatures_ext_tbb_v1.npy (canonical untouched) ---
    ext = np.load(os.path.join(SIG, "signatures_ext.npy"))            # N×88
    assert ext.shape[0] == len(md5s)
    dim89 = (tbb_cos.astype(np.float32) * TBB_W)[:, None]
    ext_v1 = np.concatenate([ext, dim89], axis=1).astype(np.float32)  # N×89
    out_npy = os.path.join(SIG, "signatures_ext_tbb_v1.npy")
    np.save(out_npy, ext_v1)
    print(f"[51] saved {out_npy}  shape={ext_v1.shape}")

    # its own cosine kNN (brute = exact), canonical knn_cosine.pkl untouched
    from sklearn.neighbors import NearestNeighbors
    nn = NearestNeighbors(n_neighbors=11, metric="cosine", algorithm="brute")
    nn.fit(ext_v1)
    out_knn = os.path.join(SIG, "knn_cosine_tbb_v1.pkl")
    with open(out_knn, "wb") as f:
        pickle.dump({"nn": nn, "matrix": "signatures_ext_tbb_v1.npy", "metric": "cosine",
                     "dims": ext_v1.shape[1], "tbb_dim": ext_v1.shape[1] - 1,
                     "tbb_weight": TBB_W, "note": "ext N×88 + tbb_cos dim89 ×3; canonical untouched"}, f)
    print(f"[51] saved {out_knn}")
    print("[51] DONE — canonical signatures_ext.npy / knn_cosine.pkl NOT modified.")


if __name__ == "__main__":
    main()
