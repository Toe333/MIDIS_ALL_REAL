#!/usr/bin/env python3
"""28_build_pool.py — Grok hybrid "elite" sampling for the NinjaStar-8 rating pool.

Turns the 460k-MIDI corpus into a ~500-song rating queue that COVERS the 74-D taste
space while OVER-WEIGHTING the regions we most want taste signal in. Reproducible &
versioned: same --seed -> same pool. Output left-merges nowhere; it's just a queue.

Mix (per the spec):
  60% uniform-stratified across 74-D   (even coverage -> trains a model that generalizes)
  20% empty-corner oversample          (Phase-11 isolated clusters + blend midpoints)
  10% known bangers                    (loved anchors + high-groove ratings + their kNN nbrs)
  10% repeats / edge cases             (self-consistency re-shows + 74-D outliers)

Every candidate must be: quality_flag='ok' & bpm_valid & not duration_suspect, present in
the signature matrix, and have a real .mid on disk. Repeats are exempt from "must be new".

Output -> _work/pool_v1.parquet  (and a sibling pool_v1.meta.json with provenance counts)
  columns: pool_id, md5, source, is_repeat, repeat_of_md5, cluster_id, title, artist

Usage:
  python3 CODE/28_build_pool.py [--n 500] [--seed 8] [--version v1]
  python3 CODE/28_build_pool.py --dry-run        # print the mix, write nothing
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
META = BASE / "catalog" / "metadata.parquet"
SIG = BASE / "SIGNATURES_DATA" / "signatures_ext.npy"
SIG_MD5 = BASE / "SIGNATURES_DATA" / "signatures_md5.txt"
KNN = BASE / "SIGNATURES_DATA" / "knn_cosine.pkl"
ES = BASE / "_work" / "emptyspace"                      # Phase-11 outputs
RATINGS = BASE / "_work" / "ninjastar8_ratings.parquet"
MIDI_DIR = BASE / "MIDIs"

# Loved-song anchors (taste-anchor-songs memory). Add md5s here as the user flags more.
LOVED_MD5 = ["f5ca332850121fd3bf4fcd25d777da1a"]


def _midi_exists(md5: str) -> bool:
    return (MIDI_DIR / md5[:2] / f"{md5}.mid").is_file()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=8)
    ap.add_argument("--version", default="v1")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)

    N = a.n
    n_strat = int(round(N * 0.60))   # 300
    n_corner = int(round(N * 0.20))  # 100
    n_banger = int(round(N * 0.10))  # 50
    n_repeat = int(round(N * 0.05))  # 25 (half of the final 10%)
    n_edge = N - n_strat - n_corner - n_banger - n_repeat  # ~25

    # ---- load the universe ---------------------------------------------------
    md5_order = [m.strip() for m in SIG_MD5.read_text().split()]
    row_of = {m: i for i, m in enumerate(md5_order)}        # md5 -> signature row
    X = np.load(SIG, mmap_mode="r")                          # (N,74)

    cat = pd.read_parquet(META, columns=["md5", "title", "artist", "quality_flag",
                                          "bpm_valid", "duration_suspect"])
    cat["md5"] = cat["md5"].astype(str)
    clean_mask = ((cat.quality_flag == "ok") & (cat.bpm_valid == 1)
                  & (cat.duration_suspect == 0))
    clean = set(cat.loc[clean_mask, "md5"])
    meta = cat.set_index("md5")[["title", "artist"]].to_dict("index")

    clusters = pd.read_parquet(ES / "clusters.parquet")     # md5 -> cluster_id
    clusters["md5"] = clusters["md5"].astype(str)
    cl_of = dict(zip(clusters.md5, clusters.cluster_id))
    members = clusters.groupby("cluster_id")["md5"].apply(list).to_dict()

    def eligible(md5, *, allow_rated=True, used=None):
        return (md5 in clean and md5 in row_of and _midi_exists(md5)
                and (used is None or md5 not in used))

    used: set[str] = set()
    picks: list[dict] = []

    def add(md5, source, is_repeat=False, repeat_of=None):
        picks.append({"md5": md5, "source": source, "is_repeat": is_repeat,
                      "repeat_of_md5": repeat_of, "cluster_id": int(cl_of.get(md5, -1))})
        if not is_repeat:
            used.add(md5)

    # ---- 60% uniform-stratified across the 74-D space ------------------------
    # one clean song from each of n_strat distinct clusters -> even coverage,
    # NOT proportional to density (which would just mirror the crowded regions).
    cl_ids = [c for c, ms in members.items() if any(eligible(m, used=used) for m in ms)]
    rng.shuffle(cl_ids)
    for c in cl_ids:
        if sum(1 for p in picks if p["source"] == "stratified") >= n_strat:
            break
        cands = [m for m in members[c] if eligible(m, used=used)]
        if cands:
            add(str(rng.choice(cands)), "stratified")

    # ---- 20% empty-corner oversample -----------------------------------------
    corner_pool: list[str] = []
    iso = pd.read_parquet(ES / "corners_isolated.parquet")  # isolated clusters
    for cid in iso["cluster_id"].tolist():
        corner_pool += [m for m in members.get(cid, []) if eligible(m, used=used)]
    bl = pd.read_parquet(ES / "corners_blends.parquet")     # blend midpoints
    for lst in bl.get("nearest_songs", pd.Series([], dtype=object)):
        if isinstance(lst, (list, np.ndarray)):
            corner_pool += [str(m) for m in lst if eligible(str(m), used=used)]
    corner_pool = list(dict.fromkeys(corner_pool))          # dedupe, keep order
    rng.shuffle(corner_pool)
    for m in corner_pool[:n_corner]:
        add(m, "corner")

    # ---- 10% known bangers: loved anchors + high-groove ratings + kNN nbrs ----
    seeds = [m for m in LOVED_MD5 if m in row_of]
    if RATINGS.exists():
        r = pd.read_parquet(RATINGS)
        if "groove" in r.columns:
            seeds += r.loc[r["groove"].fillna(-1) >= 6, "md5"].astype(str).tolist()
    seeds = list(dict.fromkeys(seeds))
    banger_pool: list[str] = []
    if seeds:
        P = pickle.load(open(KNN, "rb"))
        nn = P["nn"]
        seed_rows = [row_of[m] for m in seeds if m in row_of]
        if seed_rows:
            _, idx = nn.kneighbors(np.asarray(X[seed_rows]), n_neighbors=25)
            for r_ in idx.ravel():
                m = md5_order[int(r_)]
                if eligible(m, used=used):
                    banger_pool.append(m)
    banger_pool = list(dict.fromkeys(banger_pool))
    rng.shuffle(banger_pool)
    for m in banger_pool[:n_banger]:
        add(m, "banger")

    # ---- 5% edge cases: 74-D outliers (loneliest / most isolated regions) -----
    csum = pd.read_parquet(ES / "cluster_summary.parquet")
    iso_col = "isolation" if "isolation" in csum.columns else "frontier_med"
    lonely = csum.sort_values(iso_col, ascending=False)["cluster_id"].tolist()
    edge_pool: list[str] = []
    for cid in lonely:
        edge_pool += [m for m in members.get(cid, []) if eligible(m, used=used)]
        if len(edge_pool) > n_edge * 6:
            break
    edge_pool = list(dict.fromkeys(edge_pool))
    rng.shuffle(edge_pool)
    for m in edge_pool[:n_edge]:
        add(m, "edge")

    # ---- 5% repeats: silent re-shows of already-rated songs (self-consistency)
    if RATINGS.exists():
        rated = pd.read_parquet(RATINGS)["md5"].astype(str)
        rated = [m for m in rated.unique() if m in row_of and _midi_exists(m)]
        rng.shuffle(rated)
        for m in rated[:n_repeat]:
            add(m, "repeat", is_repeat=True, repeat_of=m)

    # ---- backfill from stratified if any bucket fell short -------------------
    short = N - len(picks)
    if short > 0:
        extra = [m for c in cl_ids for m in members[c] if eligible(m, used=used)]
        extra = list(dict.fromkeys(extra))
        rng.shuffle(extra)
        for m in extra[:short]:
            add(m, "stratified_fill")

    # ---- assemble, shuffle order (don't group by bucket), assign pool_id -----
    df = pd.DataFrame(picks)
    df = df.sample(frac=1.0, random_state=a.seed).reset_index(drop=True)
    df.insert(0, "pool_id", [f"{a.version}_{i:04d}" for i in range(len(df))])
    df["title"] = df["md5"].map(lambda m: (meta.get(m, {}).get("title") or ""))
    df["artist"] = df["md5"].map(lambda m: (meta.get(m, {}).get("artist") or ""))
    df["title"] = df["title"].where(df["title"].apply(lambda s: isinstance(s, str)), "")
    df["artist"] = df["artist"].where(df["artist"].apply(lambda s: isinstance(s, str)), "")

    mix = df["source"].value_counts().to_dict()
    print(f"pool {a.version}: {len(df)} songs  | mix = {mix}", flush=True)
    print(f"  distinct md5: {df['md5'].nunique()}  | repeats: {int(df['is_repeat'].sum())}")

    if a.dry_run:
        print("(dry run — nothing written)")
        return

    out = BASE / "_work" / f"pool_{a.version}.parquet"
    df.to_parquet(out, index=False)
    meta_out = out.with_suffix(".meta.json")
    meta_out.write_text(json.dumps({
        "version": a.version, "n": len(df), "seed": a.seed, "mix": mix,
        "distinct_md5": int(df["md5"].nunique()), "repeats": int(df["is_repeat"].sum()),
        "loved_anchors": LOVED_MD5,
    }, indent=2))
    # stable "current pool" pointer the server reads
    (BASE / "_work" / "pool_current.txt").write_text(out.name)
    print(f"wrote {out}  (+ {meta_out.name}, pool_current.txt -> {out.name})")


if __name__ == "__main__":
    main()
