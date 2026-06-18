#!/usr/bin/env python3
"""26_signature_extend.py — extend the 36-D pitch signature with rhythm /
melody / harmony / tempo / GrooveDNA pillars and rebuild the cosine kNN.

GrooveDNA (the 11 drum-only rhythm dims from 29_groove_dna.py, merged onto the
catalog by 23) is its own pillar, up-weighted x2 like rhythm (--w-groove), so
drum FEEL clusters independently of pitch/harmony. Pillars whose columns are not
yet in the catalog are auto-pruned with a warning instead of crashing.

The original `signatures.npy` (N x 36) is PURE PITCH (12 pc + 12 pc-dur + 6
interval + 6 chord-size) and carries ZERO rhythm information, so the kNN index
ranks neighbors on pitch content alone. This script pulls the engineered
feature columns merged onto `catalog/metadata.parquet` (steps 22/24/25 ->
23_catalog_merge), reindexes them to the signature row order BY md5, scales
each pillar independently, up-weights rhythm (the stated top priority), and
concatenates everything into a wider matrix. It then refits a cosine
NearestNeighbors index over all rows.

Pipeline per non-pitch pillar:
  1. reindex catalog feature cols to signatures_md5.txt order (by md5, not row order)
  2. one-hot the small categoricals (tempo_class); drop high-card strings (most_common_chord)
  3. log1p heavy-tailed non-negative columns (max > LOG_MAX) to tame outliers
  4. median-impute NaN per column (report counts)
  5. z-score per column, clip to +/- CLIP
  6. per-row L2-normalize the pillar block, then scale by sqrt(weight)

Because each pillar block is L2-normalized to unit length and scaled by
sqrt(w_b), the cosine similarity of the full concatenated vector reduces to a
fixed w-weighted average of the per-pillar cosine similarities
(total norm = sqrt(sum_b w_b), constant across rows). Up-weighting rhythm
(w=2) therefore makes rhythm count double toward neighbor ranking.

Outputs (originals are NEVER clobbered — back them up first, see --no-backup):
  SIGNATURES_DATA/signatures_ext.npy   (N x K float32, the extended matrix)
  SIGNATURES_DATA/knn_cosine.pkl       (dict: nn, fit_rows, + extend metadata)

Usage:
  python3 CODE/26_signature_extend.py
  python3 CODE/26_signature_extend.py --w-rhythm 2.0 --w-melody 1 --w-harmony 1 --w-pitch 1
  python3 CODE/26_signature_extend.py --dry-run        # build matrix, skip kNN/save
"""
import os, sys, argparse, pickle, time, shutil, json
from datetime import datetime
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG_DIR = os.path.join(ROOT, "SIGNATURES_DATA")
NPY = os.path.join(SIG_DIR, "signatures.npy")          # N x 36 pitch (input, untouched)
IDX = os.path.join(SIG_DIR, "signatures_md5.txt")      # row -> md5
EXT = os.path.join(SIG_DIR, "signatures_ext.npy")      # N x K (output)
KNN = os.path.join(SIG_DIR, "knn_cosine.pkl")          # refit (output)
META = os.path.join(ROOT, "catalog", "metadata.parquet")

LOG_MAX = 50.0   # log1p any non-negative column whose max exceeds this (heavy tail)
CLIP = 8.0       # clip z-scores to +/- this many SD

# ---- pillar -> catalog columns -------------------------------------------
# tempo_class is one-hot expanded into RHYTHM. most_common_chord is dropped
# (high-cardinality string; pitch content already lives in the 36-D block).
PILLARS = {
    "rhythm": [
        "syncopation", "polyrhythm_hint", "n_rhythm_voices",
        "tempo_change_count", "n_tempo_changes", "tempo_stability", "tempo_cv",
        "swing_bur", "swing_confidence", "swing_n_beats",
        "mel_rhythm_straight", "mel_rhythm_dotted", "mel_rhythm_triplet",
        # tempo_class one-hot dummies appended at runtime
    ],
    "melody": [
        "mel_pitch_mean", "mel_range", "mel_pc_entropy",
        "mel_stepwise_ratio", "mel_leap_ratio", "mel_repeat_ratio",
        "mel_interval_mean_abs", "mel_up_ratio", "mel_direction_changes",
        "mel_chromaticism", "mel_n_phrases", "mel_mean_phrase_notes",
        "mel_motif_repeat",
    ],
    "harmony": [
        "n_distinct_chords", "n_unique_chords", "chord_density",
        "has_extended_harmony", "n_chord_segments", "harmonic_rhythm",
        "chord_change_rate", "n_distinct_chord_roots",
    ],
    # GrooveDNA (29_groove_dna.py via 23_catalog_merge) — the drum-only rhythm
    # vector. Its own pillar so feel clusters independently of pitch/harmony; the
    # 11 scalars are the same dims packed into the catalog's groove_dna array col.
    "groove": [
        "kick_density_bar", "snare_backbeat_strength", "hat_cym_density",
        "perc_diversity", "swing_cont", "syncopation_drum", "dotted_groove",
        "ghost_dynamics", "drum_pattern_entropy", "bar_drum_variance",
        "groove_composite",
    ],
}
ONEHOT = {"tempo_class": ["constant", "gradual", "erratic", "rubato"]}
DROP = ["most_common_chord"]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def scale_block(df_block, name):
    """log1p heavy tails -> median impute -> z-score -> clip. Returns (X, report)."""
    X = np.array(df_block.to_numpy(dtype=np.float64), copy=True)
    cols = list(df_block.columns)
    rep = {"n_cols": len(cols), "logged": [], "imputed": {}}
    for j, c in enumerate(cols):
        col = X[:, j]
        finite = col[np.isfinite(col)]
        # log1p for non-negative heavy-tailed columns
        if finite.size and finite.min() >= 0 and finite.max() > LOG_MAX:
            col = np.log1p(col)
            rep["logged"].append(c)
        # median impute (median over finite values)
        nan_mask = ~np.isfinite(col)
        n_nan = int(nan_mask.sum())
        if n_nan:
            med = np.nanmedian(np.where(np.isfinite(col), col, np.nan))
            if not np.isfinite(med):
                med = 0.0
            col[nan_mask] = med
            rep["imputed"][c] = n_nan
        # z-score
        mu, sd = col.mean(), col.std()
        col = (col - mu) / sd if sd > 1e-12 else col - mu
        np.clip(col, -CLIP, CLIP, out=col)
        X[:, j] = col
    return X, rep


def l2_weight(X, w):
    """Per-row L2-normalize, then scale by sqrt(w). Zero-norm rows stay zero."""
    norm = np.linalg.norm(X, axis=1, keepdims=True)
    out = np.divide(X, norm, out=np.zeros_like(X), where=norm > 1e-12)
    return out * np.sqrt(w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--w-pitch", type=float, default=1.0)
    ap.add_argument("--w-rhythm", type=float, default=2.0)
    ap.add_argument("--w-melody", type=float, default=1.0)
    ap.add_argument("--w-harmony", type=float, default=1.0)
    ap.add_argument("--w-groove", type=float, default=2.0,
                    help="GrooveDNA (drum-only rhythm) weight; up-weighted x2 like rhythm")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip the in-script .bak copy (use if you already backed up)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build + report the matrix but do not fit kNN or write files")
    args = ap.parse_args()
    weights = {"pitch": args.w_pitch, "rhythm": args.w_rhythm,
               "melody": args.w_melody, "harmony": args.w_harmony,
               "groove": args.w_groove}
    t0 = time.time()

    # ---- load pitch signature + row order --------------------------------
    pitch = np.load(NPY).astype(np.float64)
    with open(IDX) as fh:
        md5s = [l.strip() for l in fh if l.strip()]
    assert pitch.shape[0] == len(md5s), f"pitch {pitch.shape} vs md5 {len(md5s)}"
    log(f"pitch signature {pitch.shape}, {len(md5s)} md5 rows")

    # ---- load catalog, reindex features to signature order BY md5 --------
    # prune any pillar columns absent from the catalog so a not-yet-merged pillar
    # (e.g. groove before 23 runs) degrades to "skipped" instead of crashing.
    import pyarrow.parquet as pq
    avail = set(pq.ParquetFile(META).schema.names)
    for pillar, cols in PILLARS.items():
        miss = [c for c in cols if c not in avail]
        if miss:
            log(f"WARN pillar '{pillar}': {len(miss)} cols not in catalog, dropping: {miss}")
            PILLARS[pillar] = [c for c in cols if c in avail]
    PILLARS_ACTIVE = [p for p in ("rhythm", "melody", "harmony", "groove") if PILLARS.get(p)]
    use_cols = ["md5"] + sum(PILLARS.values(), []) + list(ONEHOT) + DROP
    m = pd.read_parquet(META, columns=[c for c in use_cols if c in avail or c == "md5"])
    if m["md5"].duplicated().any():
        sys.exit("FATAL: duplicate md5 in catalog — cannot align")
    m = m.set_index("md5").reindex(md5s)        # align BY md5 to signature order
    missing = m[PILLARS["rhythm"][0]].isna().sum()  # rough: rows absent from catalog
    n_absent = int(m.index.isin(set(md5s)).sum() == 0)  # sanity
    log(f"reindexed catalog to signature order; rows not found in catalog "
        f"-> all-NaN (will impute). example col NaN={int(missing)}")

    # one-hot tempo_class, drop high-card strings
    blocks = {k: list(v) for k, v in PILLARS.items()}
    for col, cats in ONEHOT.items():
        s = m[col].astype("object").where(m[col].notna(), "missing")
        for cat in cats:
            name = f"{col}__{cat}"
            m[name] = (s == cat).astype(float)
            blocks["rhythm"].append(name)

    # ---- scale each non-pitch pillar, then L2 + weight -------------------
    report = {"weights": weights, "log_max": LOG_MAX, "clip": CLIP,
              "n_rows": len(md5s), "pillars": {}}
    parts, block_dims, names = [], {}, []

    # pitch block: already non-negative histograms; L2 + weight as one block
    pitch_lw = l2_weight(pitch, weights["pitch"])
    parts.append(pitch_lw)
    block_dims["pitch"] = pitch.shape[1]
    names += [f"pitch_{i}" for i in range(pitch.shape[1])]
    report["pillars"]["pitch"] = {"n_cols": pitch.shape[1], "logged": [], "imputed": {}}

    for pillar in PILLARS_ACTIVE:
        cols = blocks[pillar]
        X, rep = scale_block(m[cols], pillar)
        Xlw = l2_weight(X, weights[pillar])
        parts.append(Xlw)
        block_dims[pillar] = len(cols)
        names += cols
        rep["weight"] = weights[pillar]
        report["pillars"][pillar] = rep
        n_imp = sum(rep["imputed"].values())
        log(f"{pillar:8} dims={len(cols):3} weight={weights[pillar]} "
            f"logged={len(rep['logged'])} imputed_cells={n_imp} "
            f"(cols imputed: {list(rep['imputed'])[:6]}{'...' if len(rep['imputed'])>6 else ''})")

    ext = np.concatenate(parts, axis=1).astype(np.float32)
    report["block_dims"] = block_dims
    report["total_dims"] = int(ext.shape[1])
    report["feature_names"] = names
    log(f"extended matrix {ext.shape}  block_dims={block_dims}")
    # full-vector norm is constant (= sqrt(sum w)) for rows with all blocks present
    rn = np.linalg.norm(ext, axis=1)
    log(f"row-norm: min={rn.min():.3f} median={np.median(rn):.3f} max={rn.max():.3f} "
        f"(expected ~{np.sqrt(sum(weights.values())):.3f})")

    if args.dry_run:
        log("dry-run: skipping save + kNN refit")
        print(json.dumps({k: report[k] for k in ("weights", "block_dims", "total_dims")}, indent=2))
        return

    # ---- save extended matrix (keep originals) ---------------------------
    np.save(EXT, ext)
    log(f"saved {EXT}  ({os.path.getsize(EXT)/1e6:.1f} MB)")

    # ---- refit cosine kNN over ALL rows ----------------------------------
    from sklearn.neighbors import NearestNeighbors
    log("fitting NearestNeighbors(metric='cosine', algorithm='brute') over all rows...")
    nn = NearestNeighbors(n_neighbors=12, metric="cosine", algorithm="brute")
    nn.fit(ext)
    log(f"fit done ({time.time()-t0:.0f}s elapsed)")

    if not args.no_backup and os.path.exists(KNN):
        bak = KNN + f".prerefit_{datetime.now():%Y%m%d_%H%M%S}.bak"
        shutil.copy2(KNN, bak)
        log(f"in-script backup of prior kNN -> {bak}")

    payload = {
        "nn": nn,
        "fit_rows": np.arange(len(md5s)),   # all rows (back-compat with old dict shape)
        "matrix": "signatures_ext.npy",
        "metric": "cosine",
        "block_dims": block_dims,
        "weights": weights,
        "feature_names": names,
        "built": datetime.now().isoformat(timespec="seconds"),
        "report": {k: v for k, v in report.items() if k != "feature_names"},
    }
    with open(KNN, "wb") as fh:
        pickle.dump(payload, fh, protocol=4)
    log(f"saved {KNN}  ({os.path.getsize(KNN)/1e6:.1f} MB)")
    log(f"DONE in {time.time()-t0:.0f}s  -> N x {ext.shape[1]} extended signature, cosine kNN rebuilt")


if __name__ == "__main__":
    main()
