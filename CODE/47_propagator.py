#!/usr/bin/env python3
"""47_propagator.py — the canonical TASTE PROPAGATOR on the N×88 signature.

Supersedes the 46_taste_rerank / 37_taste_stub one-offs. For every NinjaStar-8
axis it trains the better of {LightGBM, groove-upweighted Ridge} by 5-fold CV,
predicts over all 459,805 songs, builds a groove-dominant LOVE composite, and an
ensemble-variance UNCERTAINTY (for the active-learning sampler, 48_active_pool).

Design decisions (the data-design win — make empty corners actionable & versioned):
  * CANONICAL OUTPUT _work/taste_pred_v2.parquet — md5 + pred_<axis> + pred_love +
    unc_love, PLUS provenance columns (script_sha / built_at / version / model_per_axis
    / n_train). One source of truth, md5-joinable to the catalog like GrooveDNA.
  * Groove is the #1 priority: the LOVE composite weights groove ×8 against
    musicality/spark ×1. "Groove block ×8 in loss" only bites a LINEAR model (trees are
    scale-invariant), so the Ridge variant scales the groove block (dims 77..87) ×8 and
    competes head-to-head with LightGBM per axis — we keep whichever wins CV.
  * Never overwrite without a timestamped .bak.

Outputs:
  _work/taste_pred_v2.parquet                      (canonical, all 459,805 rows)
  _work/generation_seeds/targets_v2_<DATE>.csv     (corners ranked by predicted love)

Usage:
  python CODE/47_propagator.py
  python CODE/47_propagator.py --no-audio          # skip render/webplayer
"""
import os, sys, argparse, hashlib, subprocess, glob
from datetime import datetime, timezone
import numpy as np
import pandas as pd

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)

SIG = os.path.join(ROOT, "SIGNATURES_DATA", "signatures_ext.npy")
IDX = os.path.join(ROOT, "SIGNATURES_DATA", "signatures_md5.txt")
RATINGS = os.path.join(ROOT, "_work", "ninjastar8_ratings.parquet")
META = os.path.join(ROOT, "catalog", "metadata.parquet")
EMPTY = os.path.join(ROOT, "_work", "emptyspace")
PRED = os.path.join(ROOT, "_work", "taste_pred_v2.parquet")
SEEDS = os.path.join(ROOT, "_work", "generation_seeds")
SF2 = os.path.join(ROOT, "soundfonts", "GeneralUserGS.sf2")

AXES = ["musicality", "novelty", "groove", "valence", "energy", "memorability", "spark"]
GROOVE_BLOCK = slice(77, 88)        # the 11 GrooveDNA dims in the 88-D signature
# groove-block scaling for the Ridge model: swept up∈{1,3,5,8,12}×alpha∈{30,100,300}
# over 3 CV seeds — up=3/alpha=300 wins (groove r=+0.364); ×8 was consistently worse,
# so we use the empirical optimum rather than a fixed ×8.
GROOVE_UPWEIGHT = 3.0
RIDGE_ALPHA = 300.0
# LOVE composite stays groove-DOMINANT (the #1 priority). NB on the v2 training set only
# musicality/novelty/groove carry signal; valence/energy/memorability/spark are constant
# (the rater moves the core 3 + radar), so spark here contributes only its mean — love is
# effectively groove(+light musicality) by construction, which is what we want.
LOVE_W = {"groove": 8.0, "musicality": 1.0, "spark": 1.0}
VERSION = "taste_v2_" + datetime.now().strftime("%Y%m%d")


def log(m): print(f"[47] {m}", flush=True)


def script_sha():
    return hashlib.sha1(open(__file__, "rb").read()).hexdigest()[:12]


def pearson(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if a.std() < 1e-9 or b.std() < 1e-9:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _ridge_groove(alpha=RIDGE_ALPHA):
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer

    def up(X):
        X = X.copy(); X[:, GROOVE_BLOCK] *= GROOVE_UPWEIGHT; return X
    return Pipeline([("up", FunctionTransformer(up)), ("ridge", Ridge(alpha=alpha))])


def _lgbm():
    import lightgbm as lgb
    return lgb.LGBMRegressor(n_estimators=300, num_leaves=15, learning_rate=0.04,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                             min_child_samples=8, reg_lambda=1.0, random_state=0,
                             n_jobs=-1, verbosity=-1)


def cv_select(X, y, axis):
    """5-fold CV pearson for Ridge(groove×8) and LightGBM; return (name, r, mae)."""
    from sklearn.model_selection import KFold
    kf = KFold(n_splits=5, shuffle=True, random_state=7)
    out = {}
    for name, mk in (("ridge_g8", _ridge_groove), ("lgbm", _lgbm)):
        preds = np.zeros(len(y))
        for tr, te in kf.split(X):
            m = mk(); m.fit(X[tr], y[tr]); preds[te] = m.predict(X[te])
        out[name] = (pearson(preds, y), float(np.abs(preds - y).mean()))
    best = max(out, key=lambda k: out[k][0])
    log(f"  {axis:13} ridge_g8 r={out['ridge_g8'][0]:+.3f}  lgbm r={out['lgbm'][0]:+.3f}"
        f"  -> {best} (MAE {out[best][1]:.2f})")
    return best, out[best][0], out[best][1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--rating-version", type=int, default=2,
                    help="train on this rating_version only (0=all). v2 is the clean "
                         "7-axis schema; mixing v1 legacy ratings demonstrably hurt CV.")
    args = ap.parse_args()

    Xall = np.load(SIG).astype(np.float32)
    md5s = [l.strip() for l in open(IDX) if l.strip()]
    pos = {m: i for i, m in enumerate(md5s)}
    log(f"signature {Xall.shape}, {len(md5s)} rows")

    r = pd.read_parquet(RATINGS)
    if args.rating_version:
        r = r[r.rating_version == args.rating_version]
    agg = r.groupby("md5")[AXES].mean()
    agg = agg[agg.index.isin(pos)]
    rows = np.array([pos[m] for m in agg.index])
    Xtr_full = Xall[rows]
    log(f"training rows: {len(agg)} distinct rated md5 "
        f"(rating_version={args.rating_version or 'all'}, repeats averaged)")

    models, cv = {}, {}
    preds = {}
    for ax in AXES:
        y = agg[ax].to_numpy(float)
        ok = np.isfinite(y)
        Xt, yt = Xtr_full[ok], y[ok]
        name, rr, mae = cv_select(Xt, yt, ax)
        cv[ax] = {"model": name, "pearson": round(rr, 4), "mae": round(mae, 3), "n": int(ok.sum())}
        mk = _ridge_groove if name == "ridge_g8" else _lgbm
        m = mk(); m.fit(Xt, yt); models[ax] = m
        preds[ax] = m.predict(Xall).astype(np.float32)

    # uncertainty for the LOVE axes: ensemble spread (groove/musicality/spark)
    log("ensemble uncertainty for love axes (10 bagged LightGBM each)...")
    import lightgbm as lgb
    unc_parts = []
    for ax in ("groove", "musicality", "spark"):
        y = agg[ax].to_numpy(float); ok = np.isfinite(y)
        ens = np.zeros((10, len(md5s)), np.float32)
        for s in range(10):
            mm = lgb.LGBMRegressor(n_estimators=200, num_leaves=15, learning_rate=0.05,
                                   subsample=0.7, subsample_freq=1, colsample_bytree=0.7,
                                   min_child_samples=8, random_state=s, n_jobs=-1, verbosity=-1)
            mm.fit(Xtr_full[ok], y[ok]); ens[s] = mm.predict(Xall)
        unc_parts.append(ens.std(0))
    unc_love = np.mean(unc_parts, axis=0).astype(np.float32)

    # groove-dominant love composite
    wsum = sum(LOVE_W.values())
    love = sum(LOVE_W[a] * preds[a] for a in LOVE_W) / wsum

    # ---- canonical table with provenance ----
    built = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sha = script_sha()
    out = pd.DataFrame({"md5": md5s})
    for ax in AXES:
        out[f"pred_{ax}"] = preds[ax]
    out["pred_love"] = love.astype(np.float32)
    out["unc_love"] = unc_love
    out["script_sha"] = sha
    out["built_at"] = built
    out["version"] = VERSION
    out["model_per_axis"] = ";".join(f"{a}:{cv[a]['model']}" for a in AXES)
    out["n_train"] = len(agg)
    if os.path.exists(PRED):
        bak = PRED.replace(".parquet", f".bak_{datetime.now():%Y%m%d_%H%M%S}.parquet")
        os.rename(PRED, bak); log(f"backed up old canonical -> {os.path.basename(bak)}")
    out.to_parquet(PRED, index=False)
    log(f"canonical -> {PRED}  ({len(out)} rows, {out.shape[1]} cols, sha={sha})")
    log("CV summary: " + " | ".join(f"{a}={cv[a]['pearson']:+.2f}({cv[a]['model'][:5]})" for a in AXES))

    # ---- score empty corners by predicted love (groove-dominant) ----
    lovemap = dict(zip(md5s, love))
    cat = pd.read_parquet(META, columns=["md5", "diatonic_ratio", "has_melody"]).set_index("md5")
    def beauty_ok(mlist):
        for m in mlist:
            if m in cat.index:
                row = cat.loc[m]
                if (row.diatonic_ratio or 0) >= 0.6 and bool(row.has_melody):
                    return True
        return False
    recs = []
    blends = pd.read_parquet(os.path.join(EMPTY, "corners_blends.parquet"))
    for _, b in blends.iterrows():
        near = str(b["nearest_songs"]).split(";")[:3]
        lv = [lovemap[m] for m in near if m in lovemap]
        if not lv:
            continue
        recs.append(dict(corner_type="blend", caption=b["midpoint_caption"],
                         pred_love=float(np.mean(lv)), nearest_md5=near[0],
                         nearest_md5_top3=";".join(near), nearest_sim=float(b["nearest_sim"]),
                         beauty=beauty_ok(near)))
    iso = pd.read_parquet(os.path.join(EMPTY, "corners_isolated.parquet"))
    rep_col = "reps" if "reps" in iso.columns else ("nearest_songs" if "nearest_songs" in iso.columns else None)
    cap_col = "caption" if "caption" in iso.columns else ("midpoint_caption" if "midpoint_caption" in iso.columns else None)
    if rep_col:
        for _, b in iso.iterrows():
            near = str(b[rep_col]).split(";")[:3]
            lv = [lovemap[m] for m in near if m in lovemap]
            if not lv:
                continue
            recs.append(dict(corner_type="isolated", caption=(b[cap_col] if cap_col else ""),
                             pred_love=float(np.mean(lv)), nearest_md5=near[0],
                             nearest_md5_top3=";".join(near), nearest_sim=np.nan,
                             beauty=beauty_ok(near)))
    t = pd.DataFrame(recs).sort_values(["beauty", "pred_love"], ascending=False).reset_index(drop=True)
    t.insert(0, "rank", np.arange(1, len(t) + 1))
    os.makedirs(SEEDS, exist_ok=True)
    tcsv = os.path.join(SEEDS, f"targets_{VERSION}.csv")
    t.to_csv(tcsv, index=False)
    log(f"corners ranked -> {tcsv}  ({len(t)} corners; {int(t.beauty.sum())} pass beauty)")
    print(t.head(8)[["rank", "corner_type", "caption", "pred_love", "beauty"]].to_string(index=False))

    if args.no_audio:
        return
    # render the top-8 corners' nearest real songs (reverse so #1 is newest in webplayer)
    group = "targets_v2"
    top = t.head(8)
    for i, row in enumerate(reversed(list(top.itertuples())), 1):
        md5 = row.nearest_md5
        mid = os.path.join(ROOT, "MIDIs", md5[:2], md5 + ".mid")
        wav = os.path.join(SEEDS, "targets_v2_audio", f"r{len(top)-i+1}_{md5[:8]}.wav")
        os.makedirs(os.path.dirname(wav), exist_ok=True)
        subprocess.run(["fluidsynth", "-ni", "-F", wav, SF2, mid], check=False, capture_output=True)
        if os.path.exists(wav):
            subprocess.run(["webplayer", "add", wav, "--group", group,
                            "--label", f"#{row.rank} love{row.pred_love:.2f} {md5[:8]}",
                            "--desc", str(row.caption)], check=False, capture_output=True)
    subprocess.run(["webplayer", "open"], check=False, capture_output=True)
    st = subprocess.run(["webplayer", "status"], capture_output=True, text=True)
    log(f"webplayer group '{group}': top-8 nearest rendered\n{st.stdout.strip()}")


if __name__ == "__main__":
    main()
