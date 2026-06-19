#!/usr/bin/env python3
"""
36_pool_preview.py  —  DRY-RUN preview of the 500 "clean stratified, rhythm-heavy" pool.

Grok spec (supervised): sample 500 clean files, heavy weight on rhythm / GrooveDNA
variance + empty corners + clean flag. Output preview stats + candidate list to
_work/pool_preview.parquet.  NO live write to pool_v1, NO git. Preview only.
"""
import numpy as np, pandas as pd, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
W = ROOT / "_work"
N = 500
SEED = 1729
rng = np.random.default_rng(SEED)

# ---- load -------------------------------------------------------------
meta = pd.read_parquet(ROOT / "catalog/metadata.parquet", columns=[
    "md5", "parses", "is_zero_byte", "note_density_absurd", "dur_over_1h",
    "all_notes_out_of_piano_range", "has_drums", "bpm", "duration_sec"])
gd = pd.read_parquet(W / "groove_dna.parquet")  # md5 + 11 groove dims

# ---- clean flag -------------------------------------------------------
clean = (
    meta.parses.fillna(False)
    & ~meta.is_zero_byte.fillna(True)
    & ~meta.note_density_absurd.fillna(True)
    & ~meta.dur_over_1h.fillna(True)
    & (meta.all_notes_out_of_piano_range != True)
)
df = meta[clean].merge(gd, on="md5", how="inner")

# ---- empty-corner boost (md5s sitting in under-populated drum corners) -
corner_md5 = set()
csv = W / "drum_emptyspace/drum_corners.csv"
if csv.exists():
    for s in pd.read_csv(csv)["songs"].dropna():
        corner_md5.update(str(s).split(";"))
df["in_empty_corner"] = df.md5.isin(corner_md5)

# ---- weighting --------------------------------------------------------
def z(s):  # robust z-score, NaN->0
    s = s.astype("float64")
    sd = s.std(ddof=0)
    return ((s - s.mean()) / sd).fillna(0.0) if sd > 0 else s * 0.0

# groove-variance / "interesting feel" axis (rhythm priority #1)
variety = (z(df.bar_drum_variance) + z(df.drum_pattern_entropy)
           + z(df.syncopation_drum) + 0.5 * z(df.swing_cont))
w = np.exp(0.6 * variety.to_numpy())          # soft preference, not hard cutoff
w *= np.where(df.has_drums.to_numpy() == 1, 3.0, 1.0)   # rhythm-heavy
w *= np.where(df.in_empty_corner.to_numpy(), 4.0, 1.0)  # empty-corner boost
w = np.clip(w, 0, np.quantile(w, 0.999))      # tame outliers
df["weight"] = w

# ---- force-include every eligible empty-corner song (explicit target) -
df["g_decile"] = pd.qcut(df.groove_composite.rank(method="first"), 10, labels=False)
forced = df[df.in_empty_corner].copy()

# ---- stratified weighted sample over groove_composite deciles ---------
remain = N - len(forced)
per = remain // 10
pool_rest = df.drop(forced.index)
picks = []
for d, g in pool_rest.groupby("g_decile"):
    k = min(per, len(g))
    p = g.weight / g.weight.sum()
    picks.append(g.sample(n=k, weights=p, random_state=int(rng.integers(1e9))))
pool = pd.concat([forced] + picks)
if len(pool) < N:  # top up from the weighted remainder
    rest = df.drop(pool.index)
    pool = pd.concat([pool, rest.sample(n=N - len(pool),
                     weights=rest.weight / rest.weight.sum(), random_state=SEED)])
pool = pool.head(N).reset_index(drop=True)

# ---- write preview (NO live pool write) -------------------------------
out_cols = ["md5", "has_drums", "in_empty_corner", "bpm", "duration_sec",
            "groove_composite", "bar_drum_variance", "drum_pattern_entropy",
            "syncopation_drum", "swing_cont", "weight", "g_decile"]
out = pool[out_cols].copy()
out.insert(0, "preview_pool_id", range(1, len(out) + 1))
dst = W / "pool_preview.parquet"
out.to_parquet(dst, index=False)

# ---- stats ------------------------------------------------------------
print(f"clean universe: {len(df):,} / {len(meta):,} files")
print(f"empty-corner md5s available: {len(corner_md5)}")
print(f"PREVIEW POOL: {len(out)} rows -> {dst}")
print(f"  has_drums=1 : {int(out.has_drums.sum())} ({out.has_drums.mean()*100:.0f}%)")
print(f"  in_empty_corner: {int(out.in_empty_corner.sum())}")
print(f"  bpm    median {out.bpm.median():.0f}  range {out.bpm.min():.0f}-{out.bpm.max():.0f}")
print(f"  groove_composite  min {out.groove_composite.min():.3f}  "
      f"med {out.groove_composite.median():.3f}  max {out.groove_composite.max():.3f}")
print("  per groove-decile count:", list(out.g_decile.value_counts().sort_index().values))
