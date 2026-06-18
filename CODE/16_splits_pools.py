#!/usr/bin/env python3
"""16_splits_pools.py — Phase 7 song-level splits + curated pools.

Splits on song_id (so arrangements never leak across train/val/test), stratified
by source, 80/10/10. Pools are .tsv manifests pointing into the store (no copies).

Reads catalog/metadata.parquet + master_manifest.parquet.
Writes TOKENIZED/{train,val,test}_manifest.tsv, split_report.json, pools/*.tsv.
Usage:  python3 CODE/16_splits_pools.py [--seed 42]
"""
import os, sys, json, argparse
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

TOK = os.path.join(C.ROOT, "TOKENIZED")
POOLS = os.path.join(C.ROOT, "pools")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    os.makedirs(TOK, exist_ok=True)
    os.makedirs(POOLS, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    df = pd.read_parquet(os.path.join(C.CATALOG, "metadata.parquet"))
    man = pd.read_parquet(os.path.join(C.CATALOG, "master_manifest.parquet"),
                          columns=["md5", "stored_path", "sources"])
    df = df.merge(man, on="md5", how="left")
    def col(frame, name, default=0):
        """Return frame[name] as a Series, or a default-filled Series if absent."""
        if name in frame.columns:
            return frame[name].fillna(default)
        return pd.Series(default, index=frame.index)

    df = df[col(df, "is_quarantined", 0) == 0].copy()
    df["primary_source"] = df["sources"].apply(
        lambda s: (s[0] if hasattr(s, "__len__") and len(s) and not isinstance(s, str)
                   else (str(s).split(",")[0] if s is not None else "unknown")))

    # group key: song_id if clustered else the md5 itself (singleton song)
    df["grp"] = df["song_id"].where(df["song_id"].notna(), df["md5"])

    # assign each GROUP to a split, stratified by the group's primary source
    grp_src = df.groupby("grp")["primary_source"].first()
    split_of = {}
    for src, grps in grp_src.groupby(grp_src):
        g = grps.index.to_numpy()
        rng.shuffle(g)
        n = len(g); n_val = int(n * 0.1); n_test = int(n * 0.1)
        for x in g[:n_test]:        split_of[x] = "test"
        for x in g[n_test:n_test+n_val]: split_of[x] = "val"
        for x in g[n_test+n_val:]:  split_of[x] = "train"
    df["split"] = df["grp"].map(split_of)

    for sp in ("train", "val", "test"):
        sub = df[df.split == sp]
        sub[["stored_path"]].to_csv(os.path.join(TOK, f"{sp}_manifest.tsv"),
                                    sep="\t", index=False, header=False)
    # leakage check
    leak = df.groupby("grp")["split"].nunique()
    assert (leak <= 1).all(), "song_id leaks across splits!"
    report = dict(
        total=int(len(df)),
        by_split={sp: int((df.split == sp).sum()) for sp in ("train", "val", "test")},
        by_source_split={src: {sp: int(((df.primary_source == src) & (df.split == sp)).sum())
                               for sp in ("train", "val", "test")}
                         for src in df.primary_source.unique()},
        song_level=True, seed=args.seed,
    )
    json.dump(report, open(os.path.join(TOK, "split_report.json"), "w"), indent=2)
    C.log(f"splits: {report['by_split']} (song-level, no leakage)", "splits.log")

    # ---- pools (canonical-only where relevant) ----
    canon = df[col(df, "is_canonical", 1) == 1]
    def write_pool(name, mask, frame=None):
        f = frame if frame is not None else df
        sub = f[mask]
        sub[["stored_path"]].to_csv(os.path.join(POOLS, f"{name}.tsv"),
                                    sep="\t", index=False, header=False)
        return len(sub)

    sizes = {}
    g = canon
    is_clean = col(g, "quality_flag", "ok") == "ok"
    multi_inst = ((col(g, "n_piano_tracks") + col(g, "n_guitar_tracks") +
                   col(g, "n_strings_tracks") + col(g, "n_bass_tracks")) >= 2)
    gold = (is_clean & (col(g, "duration_sec", 0) >= 30) &
            (col(g, "velocity_dynamic_range", 99) > 15) & multi_inst)
    sizes["tier_gold"] = write_pool("tier_gold", gold, g)
    # bronze = flagged-garbage OR very short/empty; silver = the clean middle
    bronze = (~is_clean) | (col(g, "duration_sec", 999) < 10)
    sizes["tier_bronze"] = write_pool("tier_bronze", bronze, g)
    sizes["tier_silver"] = write_pool("tier_silver", ~(gold | bronze), g)
    sizes["with_lyrics"] = write_pool("with_lyrics", col(df, "has_lyrics", 0) == 1)
    sizes["no_drums"] = write_pool("no_drums", col(df, "has_drums", 0) == 0)
    sizes["solo_piano"] = write_pool("solo_piano", col(canon, "genre_hint", "") == "solo_piano", canon)
    for gen in ("classical", "jazz", "electronic"):
        sizes[gen] = write_pool(gen, col(canon, "genre_hint", "") == gen, canon)
    json.dump(sizes, open(os.path.join(POOLS, "pool_sizes.json"), "w"), indent=2)
    C.log(f"pools: {sizes}", "splits.log")
    C.progress("PHASE7", f"splits={report['by_split']} pools={sizes}")


if __name__ == "__main__":
    main()
