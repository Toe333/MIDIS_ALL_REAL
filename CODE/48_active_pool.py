#!/usr/bin/env python3
"""48_active_pool.py — ACTIVE-LEARNING pool for NinjaStar-8.

Picks the next ~200 songs to rate that most improve the taste model AND span the
empty corners we want to generate into. Acquisition = taste-model UNCERTAINTY
(47_propagator's unc_love) + EMPTY-CORNER PROXIMITY (cosine to the nearest of the
120 corner targets), balanced across predicted-groove deciles, with the top-8
targets force-included and a few already-rated songs re-queued for consistency.

Writes _work/pool_active.parquet in the live schema (pool_id, md5, source,
is_repeat, repeat_of_md5, cluster_id, title, artist). With --deploy it points
_work/pool_current.txt at it and restarts ninjastar8.service. Ratings live in a
SEPARATE append-only parquet (rating_id keyed) and are never touched by a swap —
the script verifies the count is unchanged across the restart.

Usage:
  python CODE/48_active_pool.py                 # build + verify only (no live change)
  python CODE/48_active_pool.py --deploy         # also swap pool_current.txt + restart
  python CODE/48_active_pool.py --n 200 --empty-frac 0.30 --repeats 20
"""
import os, sys, argparse, subprocess
from datetime import datetime
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG = os.path.join(ROOT, "SIGNATURES_DATA", "signatures_ext.npy")
IDX = os.path.join(ROOT, "SIGNATURES_DATA", "signatures_md5.txt")
PRED = os.path.join(ROOT, "_work", "taste_pred_v2.parquet")
RATINGS = os.path.join(ROOT, "_work", "ninjastar8_ratings.parquet")
EMPTY = os.path.join(ROOT, "_work", "emptyspace")
TARGETS = os.path.join(ROOT, "_work", "generation_seeds", "targets_taste_v2_20260622.csv")
POOL = os.path.join(ROOT, "_work", "pool_active.parquet")
POOL_PTR = os.path.join(ROOT, "_work", "pool_current.txt")


def log(m): print(f"[48] {m}", flush=True)


def corner_targets(md5_pos):
    """120 corner target vectors: blend = normalized anchor-centroid midpoint;
    isolated = the rep song's signature row."""
    ext = np.load(SIG, mmap_mode="r")
    cents = np.load(os.path.join(EMPTY, "clusters_centroids.npy"))
    vecs = []
    bl = pd.read_parquet(os.path.join(EMPTY, "corners_blends.parquet"))
    for _, b in bl.iterrows():
        mid = (cents[int(b["anchor_a"])] + cents[int(b["anchor_b"])]) / 2.0
        vecs.append(mid / (np.linalg.norm(mid) + 1e-12))
    iso = pd.read_parquet(os.path.join(EMPTY, "corners_isolated.parquet"))
    rep_col = "reps" if "reps" in iso.columns else "nearest_songs" if "nearest_songs" in iso.columns else None
    if rep_col:
        for _, b in iso.iterrows():
            m = str(b[rep_col]).split(";")[0]
            if m in md5_pos:
                v = np.asarray(ext[md5_pos[m]], dtype=np.float64)
                vecs.append(v / (np.linalg.norm(v) + 1e-12))
    return np.array(vecs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--empty-frac", type=float, default=0.30)
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--deploy", action="store_true", help="swap pool_current.txt + restart service")
    args = ap.parse_args()

    md5s = [l.strip() for l in open(IDX) if l.strip()]
    pos = {m: i for i, m in enumerate(md5s)}
    pred = pd.read_parquet(PRED, columns=["md5", "pred_groove", "pred_love", "unc_love"]).set_index("md5")
    pred = pred.reindex(md5s)
    log(f"loaded predictions for {pred.pred_love.notna().sum():,} songs")

    rated = set(pd.read_parquet(RATINGS, columns=["md5"])["md5"])
    n_rated_before = len(pd.read_parquet(RATINGS))
    log(f"already rated: {len(rated):,} distinct md5 ({n_rated_before} rating rows)")

    # empty-corner proximity: max cosine to the 120 corner targets (chunked matmul)
    tg = corner_targets(pos)
    ext = np.load(SIG).astype(np.float32)
    extn = ext / (np.linalg.norm(ext, axis=1, keepdims=True) + 1e-9)
    prox = np.zeros(len(md5s), np.float32)
    for s in range(0, len(md5s), 50000):
        prox[s:s+50000] = (extn[s:s+50000] @ tg.T.astype(np.float32)).max(1)
    df = pd.DataFrame({"md5": md5s, "groove": pred.pred_groove.to_numpy(),
                       "love": pred.pred_love.to_numpy(), "unc": pred.unc_love.to_numpy(),
                       "prox": prox})
    df = df[df.love.notna()].copy()

    # acquisition = 0.5*normalized-uncertainty + 0.5*normalized-corner-proximity
    def nz(x): return (x - np.nanmin(x)) / (np.nanmax(x) - np.nanmin(x) + 1e-9)
    df["acq"] = 0.5 * nz(df.unc.to_numpy()) + 0.5 * nz(df.prox.to_numpy())
    unrated = df[~df.md5.isin(rated)].copy()

    picks, why = [], {}
    def take(md5, src):
        if md5 not in why:
            why[md5] = src; picks.append(md5)

    # 1) force-include the top-8 corner targets
    tgt = pd.read_csv(TARGETS).head(8)
    for m in tgt.nearest_md5.tolist():
        take(m, "force_top8")

    # 2) empty bucket — highest corner proximity among unrated
    n_empty = int(args.n * args.empty_frac)
    for m in unrated.sort_values("prox", ascending=False).md5.head(n_empty * 2):
        if len(picks) >= 8 + n_empty:
            break
        take(m, "empty")

    # 3) uncertainty bucket — high acquisition, balanced across pred-groove deciles
    remaining = args.n - args.repeats - len(picks)
    pool = unrated[~unrated.md5.isin(why)].copy()
    pool["dec"] = pd.qcut(pool.groove.rank(method="first"), 10, labels=False)
    per = max(1, remaining // 10)
    for d in range(10):
        chunk = pool[pool.dec == d].sort_values("acq", ascending=False).md5.head(per)
        for m in chunk:
            take(m, "uncertain")
    # top up to target from global acquisition order
    for m in pool.sort_values("acq", ascending=False).md5:
        if len(picks) >= args.n - args.repeats:
            break
        take(m, "uncertain")

    # 4) repeats — re-queue already-rated, high-groove songs for self-consistency
    rep_src = df[df.md5.isin(rated)].sort_values("groove", ascending=False).md5.head(args.repeats).tolist()

    # ---- assemble pool in live schema ----
    rows = []
    for i, m in enumerate(picks, 1):
        rows.append(dict(pool_id=f"v3_{i:04d}", md5=m, source=why[m],
                         is_repeat=False, repeat_of_md5=None, cluster_id=None, title=np.nan, artist=np.nan))
    for j, m in enumerate(rep_src, len(picks) + 1):
        rows.append(dict(pool_id=f"v3_{j:04d}", md5=m, source="repeat",
                         is_repeat=True, repeat_of_md5=m, cluster_id=None, title=np.nan, artist=np.nan))
    pool_df = pd.DataFrame(rows)
    # shuffle so sources interleave on the phone (stable seed)
    pool_df = pool_df.sample(frac=1.0, random_state=42).reset_index(drop=True)
    pool_df.to_parquet(POOL, index=False)
    log(f"pool_active.parquet: {len(pool_df)} entries -> {POOL}")
    log("  sources: " + str(pool_df.source.value_counts().to_dict()))
    gq = df.set_index("md5").reindex(pool_df.md5).groove
    log(f"  pred_groove span: min={gq.min():.2f} median={gq.median():.2f} max={gq.max():.2f}")
    log(f"  groove-decile coverage of picks: {pool_df.md5.isin(unrated.md5).sum()} new + {args.repeats} repeats")

    if not args.deploy:
        log("built (no deploy). Re-run with --deploy to go live.")
        return

    # ---- LIVE SWAP (ratings are a separate append-only file; verify unchanged) ----
    prev = open(POOL_PTR).read().strip() if os.path.exists(POOL_PTR) else "(none)"
    with open(POOL_PTR, "w") as fh:
        fh.write("pool_active.parquet\n")
    log(f"pool_current.txt: {prev} -> pool_active.parquet")
    rc = subprocess.run(["systemctl", "--user", "restart", "ninjastar8.service"],
                        capture_output=True, text=True)
    log(f"restart ninjastar8.service rc={rc.returncode} {rc.stderr.strip()}")
    subprocess.run(["sleep", "1"])
    active = subprocess.run(["systemctl", "--user", "is-active", "ninjastar8.service"],
                           capture_output=True, text=True).stdout.strip()
    n_rated_after = len(pd.read_parquet(RATINGS))
    log(f"service is-active={active}  ratings rows before={n_rated_before} after={n_rated_after} "
        f"({'PRESERVED' if n_rated_after == n_rated_before else 'CHANGED!'})")


if __name__ == "__main__":
    main()
