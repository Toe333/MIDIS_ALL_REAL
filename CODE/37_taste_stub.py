#!/usr/bin/env python3
"""
37_taste_stub.py  —  taste-propagator STUB (Grok instruction 2, item 3).

Train a quick regressor from the 85-D combined signature -> user's GROOVE rating
(v2 ratings), with the GroveDNA block weighted x5 (groove is king), then predict a
groove-taste score for all ~460k songs and surface the best empty-corner targets.

Non-destructive: writes only _work/taste_pred.parquet + prints a summary. STUB only
(Ridge, no tuning) — a baseline to confirm signal before the real propagator.
"""
import numpy as np, pandas as pd, pathlib
from sklearn.linear_model import Ridge
from sklearn.model_selection import cross_val_predict

ROOT = pathlib.Path(__file__).resolve().parents[1]
W, SIG = ROOT / "_work", ROOT / "SIGNATURES_DATA"
GROOVE_BLOCK = slice(74, 85)   # last 11 dims = GrooveDNA pillar in the 85-D sig
GROOVE_W = 5.0

# ---- load signatures + md5 index --------------------------------------
X = np.load(SIG / "signatures_ext.npy").astype("float32")
md5s = [l.strip() for l in (SIG / "signatures_md5.txt").read_text().splitlines() if l.strip()]
assert len(md5s) == X.shape[0], (len(md5s), X.shape)
idx = {m: i for i, m in enumerate(md5s)}

# ---- groove x5 weighting ----------------------------------------------
Xw = X.copy()
Xw[:, GROOVE_BLOCK] *= GROOVE_W

# ---- training set: v2 groove ratings ----------------------------------
r = pd.read_parquet(W / "ninjastar8_ratings.parquet")
r = r[(r.rating_version == 2) & r.groove.notna()].dropna(subset=["md5"])
r = r.drop_duplicates("md5", keep="last")
rows = [(idx[m], float(g)) for m, g in zip(r.md5, r.groove) if m in idx]
ti = np.array([i for i, _ in rows]); ty = np.array([g for _, g in rows])
Xtr, ytr = Xw[ti], ti.size and ty

# ---- fit + honest CV sanity check -------------------------------------
model = Ridge(alpha=10.0)
cvp = cross_val_predict(model, Xtr, ty, cv=5)
cv_r = float(np.corrcoef(cvp, ty)[0, 1])
mae = float(np.abs(cvp - ty).mean())
model.fit(Xtr, ty)

# ---- predict over all 460k --------------------------------------------
pred = model.predict(Xw).astype("float32")
pred = np.clip(pred, 0, 8)
out = pd.DataFrame({"md5": md5s, "pred_groove_taste": pred})
out.to_parquet(W / "taste_pred.parquet", index=False)

# ---- empty-corner targeting -------------------------------------------
corner = set()
for s in pd.read_csv(W / "drum_emptyspace/drum_corners.csv")["songs"].dropna():
    corner.update(str(s).split(";"))
cdf = out[out.md5.isin(corner)].sort_values("pred_groove_taste", ascending=False)

# ---- summary ----------------------------------------------------------
print(f"train rows: {ti.size} (v2 groove ratings in sig index)")
print(f"5-fold CV: pearson r={cv_r:+.3f}  MAE={mae:.2f} (groove 0-8)")
print(f"predicted over {len(out):,} songs -> _work/taste_pred.parquet")
print(f"  pred dist: min {pred.min():.2f}  med {np.median(pred):.2f}  "
      f"mean {pred.mean():.2f}  max {pred.max():.2f}")
print(f"empty-corner songs scored: {len(cdf)}")
print("  top 8 empty-corner targets (high predicted groove-taste):")
for _, row in cdf.head(8).iterrows():
    print(f"    {row.md5}  {row.pred_groove_taste:.2f}")
