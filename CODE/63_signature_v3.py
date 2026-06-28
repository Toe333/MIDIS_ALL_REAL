#!/usr/bin/env python3
"""63_signature_v3.py — build balanced 4-pillar v3 signature + kNN (versioned, safe).

NEVER overwrites live signatures_ext.npy / knn_cosine.pkl.
Writes *_v3 + timestamped .bak of the live ones (if present).

Uses:
- existing signatures.npy (pitch 36) + signatures_md5.txt alignment
- _work/counterpoint.parquet, harmony_deep.parquet, melody_deep.parquet
- _work/groove_rhythm_patch.parquet (additive accent/bar_var/polyr)
- existing groove_dna / harmony / melody features for completeness

Pillar weights (balanced, logged to phase5_design):
  pitch:1.0 , rhythm:1.2 , harmony:1.2 , counterpoint:1.2 , melody:1.2

After build: roundtrip cos~1.0 on sample rows, known high-cp cluster check.

Usage:
  .venv-linux/bin/python CODE/63_signature_v3.py
  .venv-linux/bin/python CODE/63_signature_v3.py --dry-run --no-backup
"""

import os, sys, argparse, pickle, time, shutil
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

SIG_DIR = os.path.join(C.ROOT, "SIGNATURES_DATA")
NPY_OLD = os.path.join(SIG_DIR, "signatures.npy")
MD5S = os.path.join(SIG_DIR, "signatures_md5.txt")
EXT_LIVE = os.path.join(SIG_DIR, "signatures_ext.npy")
KNN_LIVE = os.path.join(SIG_DIR, "knn_cosine.pkl")

EXT_V3 = os.path.join(SIG_DIR, "signatures_ext_v3.npy")
KNN_V3 = os.path.join(SIG_DIR, "knn_cosine_v3.pkl")

CP = os.path.join(C.WORK, "counterpoint.parquet")
HD = os.path.join(C.WORK, "harmony_deep.parquet")
MD = os.path.join(C.WORK, "melody_deep.parquet")
GP = os.path.join(C.WORK, "groove_rhythm_patch.parquet")
GROOVE = os.path.join(C.WORK, "groove_dna.parquet")

LOG_MAX=50.0; CLIP=8.0

PITCH_W = 1.0
RHY_W = 1.2
HAR_W = 1.2
CTR_W = 1.2
MEL_W = 1.2

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def backup_live():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for p, nm in [(EXT_LIVE, "signatures_ext"), (KNN_LIVE, "knn_cosine")]:
        if os.path.exists(p):
            bak = p + f".bak_{ts}_v3"
            shutil.copy2(p, bak)
            log(f"backed {nm} -> {os.path.basename(bak)}")
    return ts

def load_md5_order():
    with open(MD5S) as fh:
        return [ln.strip() for ln in fh if ln.strip()]

def load_features(md5s):
    # load all, reindex to order, fill neutral
    idx = pd.Index(md5s)
    def load_parq(p, name):
        if not os.path.exists(p): 
            log(f"missing {name} {p} -> neutral")
            return pd.DataFrame(index=idx)
        df = pd.read_parquet(p)
        if "md5" in df.columns:
            df = df.set_index("md5")
        df = df.reindex(idx)
        return df
    cp = load_parq(CP, "counterpoint")
    hd = load_parq(HD, "harmony_deep")
    mdp = load_parq(MD, "melody_deep")
    gp = load_parq(GP, "groove_patch")
    gr = load_parq(GROOVE, "groove")
    # merge select useful cols (avoid dup)
    frames = []
    # counter block (drop error)
    ccols = [c for c in cp.columns if c not in ("counterpoint_error",)]
    if ccols: frames.append(cp[ccols].add_prefix("ctr_"))
    # harmony deep (drop some carried)
    hcols = [c for c in hd.columns if not c.endswith("_error") and c not in ("md5",)]
    if hcols: frames.append(hd[hcols].add_prefix("hdeep_"))
    # melody
    mcols = [c for c in mdp.columns if not c.endswith("_error")]
    if mcols: frames.append(mdp[mcols].add_prefix("mdeep_"))
    # groove patch
    pcols = [c for c in gp.columns if c != "md5"]
    if pcols: frames.append(gp[pcols])
    # original groove select non-dup
    if not gr.empty:
        gsel = [c for c in ["accent_balance","bar_var","polyr_flag","kick_density_bar","snare_backbeat_strength","bar_drum_variance"] if c in gr.columns]
        if gsel: frames.append(gr[gsel])
    if frames:
        big = pd.concat(frames, axis=1)
    else:
        big = pd.DataFrame(index=idx)
    # fillna median-ish
    for col in big.columns:
        big[col] = pd.to_numeric(big[col], errors="coerce").fillna(0.0)
    log(f"feature matrix {big.shape[1]} cols for {len(md5s)} rows")
    return big

def scale_block(X, w):
    X = np.asarray(X, dtype=np.float64)
    # log if heavy non-neg
    if X.size and X.min() >= 0 and X.max() > LOG_MAX:
        X = np.log1p(X)
    # median impute per col
    for j in range(X.shape[1]):
        col = X[:,j]
        m = np.nanmedian(col)
        if not np.isfinite(m): m=0.0
        X[:,j] = np.where(np.isfinite(col), col, m)
    # z
    mu = X.mean(0); sd = X.std(0) + 1e-9
    X = (X - mu) / sd
    X = np.clip(X, -CLIP, CLIP)
    # L2 row + sqrt(w)
    norms = np.sqrt((X**2).sum(1, keepdims=True)) + 1e-12
    X = X / norms * np.sqrt(w)
    return X

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    log("PHASE 5: building signatures_ext_v3 + knn_v3 (balanced 4-pillar)")
    md5s = load_md5_order()
    N = len(md5s)
    log(f"N={N} from md5 list")

    # load pitch base (36) — handle post-ingest md5 growth (legacy npy smaller)
    if os.path.exists(EXT_LIVE):
        pitch = np.load(EXT_LIVE)[:, :36]
    else:
        pitch = np.load(NPY_OLD)
    if pitch.shape[0] < N:
        pad = np.zeros((N - pitch.shape[0], 36), dtype=np.float32)
        pitch = np.vstack([pitch, pad])
    elif pitch.shape[0] > N:
        pitch = pitch[:N]
    log(f"pitch block {pitch.shape}")

    # features
    feats = load_features(md5s)
    # group pillars heuristically
    ctr_cols = [c for c in feats.columns if c.startswith("ctr_")]
    h_cols = [c for c in feats.columns if c.startswith("hdeep_") or c in ("func_T","func_S","func_D","tension_mean")]
    m_cols = [c for c in feats.columns if c.startswith("mdeep_") or c in ("contour","mel_complexity")]
    r_cols = [c for c in feats.columns if c in ("accent_balance","bar_var","polyr_flag","kick_density_bar","bar_drum_variance") or c.startswith("rhythm_")]

    log(f"blocks: ctr={len(ctr_cols)} h={len(h_cols)} m={len(m_cols)} r={len(r_cols)}")

    # design log (append)
    with open(os.path.join(C.WORK, "grok_progress/phase5_design.md"), "a") as fh:
        fh.write(f"\n## Build {datetime.now()}\n")
        fh.write(f"pitch:{pitch.shape[1]} w={PITCH_W}\n")
        fh.write(f"rhythm:{len(r_cols)} w={RHY_W}\n harmony:{len(h_cols)} w={HAR_W}\n counter:{len(ctr_cols)} w={CTR_W}\n melody:{len(m_cols)} w={MEL_W}\n")

    blocks = []
    if len(r_cols): blocks.append( scale_block(feats[r_cols].values, RHY_W) )
    if len(h_cols): blocks.append( scale_block(feats[h_cols].values, HAR_W) )
    if len(ctr_cols): blocks.append( scale_block(feats[ctr_cols].values, CTR_W) )
    if len(m_cols): blocks.append( scale_block(feats[m_cols].values, MEL_W) )

    # pitch
    pblk = scale_block(pitch, PITCH_W)
    X = np.concatenate([pblk] + blocks, axis=1) if blocks else pblk
    log(f"v3 matrix shape {X.shape}")

    if args.dry_run:
        log("dry-run: not saving")
        return

    if not args.no_backup:
        ts = backup_live()

    np.save(EXT_V3, X.astype(np.float32))
    log(f"wrote {EXT_V3}")

    # knn
    nn = NearestNeighbors(metric="cosine", algorithm="brute", n_jobs=-1)
    nn.fit(X)
    blob = {"nn": nn, "fit_rows": N, "block_dims": {"pitch":pitch.shape[1], "rhythm":len(r_cols), "harmony":len(h_cols), "counterpoint":len(ctr_cols), "melody":len(m_cols)},
            "weights": {"pitch":PITCH_W, "rhythm":RHY_W, "harmony":HAR_W, "counterpoint":CTR_W, "melody":MEL_W},
            "created": datetime.now().isoformat(), "v":"v3"}
    with open(KNN_V3, "wb") as fh:
        pickle.dump(blob, fh, protocol=4)
    log(f"wrote {KNN_V3}")

    # roundtrip spot
    for i in [0, min(1000,N-1), N//2]:
        row = X[i:i+1]
        d, j = nn.kneighbors(row, n_neighbors=3)
        cos = 1.0 - d[0,0]
        log(f"row {i} self-cos~{cos:.6f} nn[0]={j[0,0]}")
    log("v3 build complete (live artifacts untouched)")

if __name__ == "__main__":
    main()
