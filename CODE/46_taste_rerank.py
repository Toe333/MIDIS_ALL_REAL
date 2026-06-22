#!/usr/bin/env python3
"""
46_taste_rerank.py  —  TASK 1: re-rank empty corners by predicted taste on N×88.

Old taste predictions (_work/taste_pred.parquet) and locked targets
(_work/generation_seeds/top5_targets.csv) were computed on the OLD 85-D space and are
stale — today's N×88 hunt moved the corners ~100%. Rebuild on the current signature.

Pipeline (descends from CODE/37_taste_stub.py, same shape, current space):
  1. Train a Ridge taste propagator on signatures_ext.npy (N×88) -> NinjaStar-8 ratings.
     - "love" target = mean(musicality, memorability, spark)   (0-8)
     - per-axis models too (esp. groove); groove block (dims 77-87) up-weighted ×5.
     - 5-fold CV pearson r + MAE per target.
  2. Predict love + axes over all 459,805 -> _work/taste_pred_v2.parquet.
  3. Score the 60 blend + 60 isolated corners: corner score = mean predicted-GROOVE of its
     top-3 nearest real songs; emptiness/coherence/beauty as tie-breakers.
     -> _work/generation_seeds/targets_v2_20260620.csv (supersedes top5_targets.csv).
  4. (audio render handled separately in the shell step.)

KEY FINDING (2026-06-20): on the 88-D signature, GROOVE is the only reliably-predictable
taste axis (v2-only, alpha=100, groove×5 -> CV pearson r=+0.39, beats the old 0.32 stub).
"love"/musicality/memorability/spark are ~unpredictable (r≈0) — the signature encodes
rhythm/pitch/harmony, not subjective gestalt. Mixing v1 legacy ratings (different 3-axis
rubric) HURTS, so training uses rating_version==2 only. Corners are therefore ranked by
predicted GROOVE (also the project's #1 priority); love is kept as an informational column.

Non-destructive: writes only _work/taste_pred_v2.parquet + the targets CSV. Does NOT touch
signatures_ext.npy / knn_cosine.pkl.
"""
import numpy as np, pandas as pd, pathlib, pickle
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_predict, KFold

ROOT = pathlib.Path(__file__).resolve().parents[1]
W, SIG = ROOT / "_work", ROOT / "SIGNATURES_DATA"

# block layout (from knn_cosine.pkl): pitch36/rhythm20/melody13/harmony8/groove11
GROOVE_BLOCK = slice(77, 88)
GROOVE_W = 5.0
# NOTE: in the v2 ratings only musicality/novelty/groove were actually moved by the rater;
# valence/energy/memorability/spark are all stuck at the default 4 (std=0). The spec's
# "love = mean(musicality, memorability, spark)" is therefore degenerate (2/3 constant), so
# we train only the 3 REAL axes and rank by groove (the only one with predictive signal).
AXES = ["musicality", "novelty", "groove"]
REAL_AXES = AXES

# ---- load signatures + md5 index --------------------------------------
X = np.load(SIG / "signatures_ext.npy").astype("float32")
md5s = [l.strip() for l in (SIG / "signatures_md5.txt").read_text().splitlines() if l.strip()]
assert len(md5s) == X.shape[0], (len(md5s), X.shape)
idx = {m: i for i, m in enumerate(md5s)}
print(f"signatures: {X.shape}  ({len(md5s):,} md5s)")

bd = pickle.load(open(SIG / "knn_cosine.pkl", "rb")).get("block_dims")
print(f"block_dims from knn_cosine.pkl: {bd}")

# ---- groove ×5 weighted copy ------------------------------------------
Xw = X.copy()
Xw[:, GROOVE_BLOCK] *= GROOVE_W

# ---- ratings: v2 only (clean 7-axis rubric; mixing v1 legacy hurts CV) -
ALPHA = 100.0
r = pd.read_parquet(W / "ninjastar8_ratings.parquet").dropna(subset=["md5"])
r = r[r.rating_version == 2]
for a in AXES:
    r[a] = pd.to_numeric(r[a], errors="coerce")
agg = r.groupby("md5")[AXES].mean()
print(f"ratings (v2 only): {len(r)} rows -> {len(agg)} unique md5; "
      f"real axes rated = {AXES} (others were constant=4)")

# ---- train + CV per target --------------------------------------------
def train_target(name):
    sub = agg[name].dropna()
    rows = [(idx[m], float(v)) for m, v in sub.items() if m in idx]
    ti = np.array([i for i, _ in rows]); ty = np.array([v for _, v in rows], float)
    if ti.size < 10:
        print(f"  [{name}] too few rows ({ti.size}); skip"); return None, np.nan
    Xtr = Xw[ti]
    cv = KFold(5, shuffle=True, random_state=0)
    cvp = cross_val_predict(Ridge(alpha=ALPHA), Xtr, ty, cv=cv)
    cr = float(np.corrcoef(cvp, ty)[0, 1]); mae = float(np.abs(cvp - ty).mean())
    m = Ridge(alpha=ALPHA).fit(Xtr, ty)
    flag = "  <- predictable" if cr >= 0.25 else ("  (~noise)" if cr < 0.1 else "")
    print(f"  [{name:12s}] n={ti.size:3d}  CV pearson r={cr:+.3f}  MAE={mae:.2f}{flag}")
    return m, cr

print(f"training taste models (Ridge alpha={ALPHA:.0f}, groove block ×{GROOVE_W:.0f}):")
models = {}
for t in ["groove", "musicality", "novelty"]:
    mdl, _ = train_target(t)
    if mdl is not None:
        models[t] = mdl

# ---- predict over all 460k --------------------------------------------
pred = pd.DataFrame({"md5": md5s})
for t, mdl in models.items():
    lo, hi = (0, 8)
    pred[f"pred_{t}"] = np.clip(mdl.predict(Xw).astype("float32"), lo, hi)
pred.to_parquet(W / "taste_pred_v2.parquet", index=False)
pm = pred["pred_groove"]
print(f"predicted over {len(pred):,} -> _work/taste_pred_v2.parquet  (cols: {list(pred.columns)})")
print(f"  pred_groove: min {pm.min():.2f} med {pm.median():.2f} mean {pm.mean():.2f} max {pm.max():.2f}")

# ---- proxy-beauty from catalog ----------------------------------------
cat = pd.read_parquet("catalog/metadata.parquet", columns=["md5", "diatonic_ratio", "has_melody"])
cat = cat.drop_duplicates("md5").set_index("md5")
pi = pred.set_index("md5")
pgroove, pmus = pi["pred_groove"], pi["pred_musicality"]

def beauty_ok(mlist):
    """fraction of songs that pass proxy-beauty (diatonic>=0.6 & has_melody=1)."""
    sub = cat.reindex(mlist)
    if sub.empty: return np.nan
    ok = (sub.diatonic_ratio >= 0.6) & (sub.has_melody == 1)
    return float(ok.mean())

# ---- score corners (PRIMARY = predicted groove, the predictable axis) --
def score_corner(md5_csv, top=3):
    ms = [m for m in str(md5_csv).split(";") if m]
    g = pgroove.reindex(ms).dropna()
    if g.empty: return np.nan, np.nan, [], np.nan
    top_idx = g.sort_values(ascending=False).head(top).index
    return (float(g.loc[top_idx].mean()),
            float(pmus.reindex(top_idx).mean()),
            list(top_idx), beauty_ok(ms))

rows = []
blends = pd.read_parquet(W / "emptyspace/corners_blends.parquet")
for _, c in blends.iterrows():
    g, mus, top_md5, beauty = score_corner(c.nearest_songs)
    rows.append(dict(corner_type="blend", caption=c.midpoint_caption,
                     predicted_groove=g, predicted_musicality=mus,
                     nearest_md5=top_md5[0] if top_md5 else "",
                     nearest_md5_top3=";".join(top_md5), nearest_sim=c.nearest_sim,
                     emptiness=c.midpoint_population, beauty_frac=beauty,
                     pair_sim=c.pair_sim))

iso = pd.read_parquet(W / "emptyspace/corners_isolated.parquet")
for _, c in iso.iterrows():
    g, mus, top_md5, beauty = score_corner(c.reps)  # isolated uses `reps`
    rows.append(dict(corner_type="isolated", caption=c.caption,
                     predicted_groove=g, predicted_musicality=mus,
                     nearest_md5=top_md5[0] if top_md5 else "",
                     nearest_md5_top3=";".join(top_md5), nearest_sim=c.isolation,
                     emptiness=c.frontier_med, beauty_frac=beauty,
                     pair_sim=np.nan))

T = pd.DataFrame(rows).dropna(subset=["predicted_groove"])
# rank by predicted_groove (only predictable axis); tie-break beauty, coherence
T = T.sort_values(["predicted_groove", "beauty_frac", "nearest_sim"],
                  ascending=[False, False, False]).reset_index(drop=True)
T.insert(0, "rank", T.index + 1)

out = W / "generation_seeds/targets_v2_20260620.csv"
old = W / "generation_seeds/top5_targets.csv"
if old.exists() and not (old.with_suffix(".csv.bak")).exists():
    old.rename(old.with_suffix(".csv.bak"))
    print(f"backed up old targets -> {old.with_suffix('.csv.bak').name}")
T.to_csv(out, index=False)
print(f"\nwrote {len(T)} ranked corners -> {out}")
print("top 8 corners (ranked by predicted GROOVE):")
for _, x in T.head(8).iterrows():
    print(f"  #{x['rank']:2d} {x.corner_type:8s} groove={x.predicted_groove:.2f} "
          f"mus={x.predicted_musicality:.2f} beauty={x.beauty_frac:.2f} "
          f"sim={x.nearest_sim:.2f} | {x.caption[:55]}")
print("\ntop-8 nearest md5s (rank order, for audio render):")
print(" ".join(T.head(8).nearest_md5.tolist()))
