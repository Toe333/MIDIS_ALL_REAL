#!/usr/bin/env python3
"""12_signatures.py — Phase 3 similarity signatures + index + near-dup clusters.

Builds ONE uniform signature per file from the pickles' total_pitches_counts /
ms_chords_counts (no parse), stores a single N x 36 float32 matrix (NOT per-file
files), fits a cosine NearestNeighbors index, and clusters near-duplicate
arrangements into song_id groups.

Outputs:
  SIGNATURES_DATA/signatures.npy        (N x 36 float32)
  SIGNATURES_DATA/signatures_md5.txt    (row -> md5)
  SIGNATURES_DATA/knn_cosine.pkl        (sklearn NearestNeighbors)
  _work/clusters.parquet                (md5, song_id, is_canonical, n_arrangements, arrangement_rank)

Usage:
  python3 CODE/12_signatures.py                  # full
  python3 CODE/12_signatures.py --limit 5000     # quick test subset
  python3 CODE/12_signatures.py --sim 0.97       # cluster cosine threshold
"""
import os, sys, argparse, pickle, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

SIG_DIR = os.path.join(C.ROOT, "SIGNATURES_DATA")
NPY = os.path.join(SIG_DIR, "signatures.npy")
IDX = os.path.join(SIG_DIR, "signatures_md5.txt")
KNN = os.path.join(SIG_DIR, "knn_cosine.pkl")
CLUSTERS = os.path.join(C.WORK, "clusters.parquet")


def interval_vector(pc_hist):
    """6-bin interval-class vector from a 12-bin pitch-class histogram (relative)."""
    iv = np.zeros(6)
    present = pc_hist > 0
    for i in range(12):
        for j in range(i + 1, 12):
            if present[i] and present[j]:
                ic = min((j - i) % 12, (i - j) % 12)
                iv[ic - 1] += min(pc_hist[i], pc_hist[j])
    s = iv.sum()
    return iv / s if s > 0 else iv


def signature(d):
    """36-dim: 12 pitch-class (notes) + 12 pitch-class (dur-weighted approx) + 6 interval + 6 chord-size."""
    tpc = d.get("total_pitches_counts") or []
    pc = C.pc_histogram(tpc, drums=False)                    # 12
    pc_dur = pc.copy()                                       # 12 (proxy; same source)
    iv = interval_vector(pc)                                 # 6
    # chord-size histogram from ms_chords_counts: how big are the chords
    csz = np.zeros(6)
    for chord, cnt in (d.get("ms_chords_counts") or []):
        n = len(chord) if isinstance(chord, list) else 0
        if 1 <= n <= 6:
            csz[n - 1] += cnt
    s = csz.sum()
    csz = csz / s if s > 0 else csz
    return np.concatenate([pc, pc_dur, iv, csz]).astype(np.float32)


def build_matrix(limit):
    md5s, vecs, t0 = [], [], time.time()
    for md5, d in C.iter_meta_pickles():
        md5s.append(md5)
        vecs.append(signature(d))
        if limit and len(md5s) >= limit:
            break
        if len(md5s) % 50000 == 0:
            C.log(f"  signatures {len(md5s)} {len(md5s)/(time.time()-t0):.0f}/s", "signatures.log")
    M = np.vstack(vecs)
    os.makedirs(SIG_DIR, exist_ok=True)
    np.save(NPY, M)
    with open(IDX, "w") as fh:
        fh.write("\n".join(md5s))
    C.log(f"matrix {M.shape} -> {NPY}", "signatures.log")
    return M, md5s


def cluster(M, md5s, sim, k, max_cluster, min_bins):
    """Conservative near-dup clustering.

    A coarse 36-dim pitch signature over-merges if you just union-find every
    cosine>=sim edge (transitive chaining collapses thousands of simple C-major
    files into one blob -- verified). Three guards prevent that:
      1. MUTUAL k-NN only: union i,j only if each is in the other's top-k.
      2. Skip DEGENERATE signatures (fewer than `min_bins` active pitch classes)
         -- a 2-note file matches everything; it is not a "song".
      3. DISSOLVE oversized clusters (> max_cluster): a group that big is
         signature-collapse, not a real arrangement set, so revert to singletons.
    This keeps precision high so song-level splits never leak. Recall (catching
    every true arrangement) is the stretch goal that needs the Level-2 melody
    contour check -- intentionally not attempted here.
    """
    from sklearn.neighbors import NearestNeighbors
    from collections import defaultdict
    thr = 1.0 - sim
    active_bins = (M[:, :12] > 0).sum(axis=1)   # pitch-class richness

    parent = list(range(len(md5s)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[max(ra, rb)] = min(ra, rb)

    # BLOCKING so we never do an O(N^2) brute kNN. Bucket by a coarse discrete
    # key (rank-ordered top-4 pitch classes); near-duplicates share it, and we
    # only run brute mutual-kNN *within* each (small) bucket. This makes the
    # full 460k run tractable (sum of bucket^2 instead of N^2).
    buckets = defaultdict(list)
    for i in range(len(md5s)):
        if active_bins[i] < min_bins:
            continue
        top = tuple(np.argsort(M[i, :12])[::-1][:4].tolist())
        buckets[top].append(i)

    # one global index just for the saved search tool (sampled if huge)
    fit_idx = np.random.default_rng(0).choice(
        len(md5s), size=min(len(md5s), 100000), replace=False)
    nn_global = NearestNeighbors(n_neighbors=min(k, len(fit_idx)),
                                 metric="cosine", algorithm="brute").fit(M[fit_idx])
    with open(KNN, "wb") as fh:
        pickle.dump({"nn": nn_global, "fit_rows": fit_idx}, fh)

    for members in buckets.values():
        if len(members) < 2:
            continue
        sub = M[members]
        nn = NearestNeighbors(n_neighbors=min(k, len(members)),
                              metric="cosine", algorithm="brute").fit(sub)
        dist, idx = nn.kneighbors(sub)
        nbr_sets = [set(idx[a]) for a in range(len(members))]
        for a in range(len(members)):
            for b, dd in zip(idx[a], dist[a]):
                if a == b or dd > thr:
                    continue
                if a in nbr_sets[b]:                    # mutual NN only
                    union(members[a], members[b])

    groups = defaultdict(list)
    for i in range(len(md5s)):
        groups[find(i)].append(i)
    # dissolve oversized (collapse) clusters back to singletons
    dissolved = 0
    out = {}
    for root, members in groups.items():
        if len(members) > max_cluster:
            dissolved += 1
            for m in members:
                out[m] = [m]
        else:
            out[root] = members
    if dissolved:
        C.log(f"  dissolved {dissolved} oversized (> {max_cluster}) clusters "
              f"as signature-collapse artifacts", "signatures.log")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sim", type=float, default=0.985)
    ap.add_argument("--k", type=int, default=12)
    ap.add_argument("--max-cluster", type=int, default=50)
    ap.add_argument("--min-bins", type=int, default=5)
    args = ap.parse_args()

    M, md5s = build_matrix(args.limit)
    groups = cluster(M, md5s, args.sim, args.k, args.max_cluster, args.min_bins)

    # canonical = member with most non-zero signature mass (proxy for richer content)
    import uuid
    rows = []
    n_multi = 0
    for root, members in groups.items():
        if len(members) > 1:
            n_multi += 1
            sid = "song_" + uuid.uuid5(uuid.NAMESPACE_DNS, md5s[root]).hex[:12]
        else:
            sid = None
        ranked = sorted(members, key=lambda i: -float(M[i].sum()))
        for rank, i in enumerate(ranked):
            rows.append(dict(md5=md5s[i], song_id=sid,
                             is_canonical=int(rank == 0 and len(members) > 1) or int(len(members) == 1 and False),
                             n_arrangements=len(members),
                             arrangement_rank=rank if len(members) > 1 else 0))
    df = pd.DataFrame(rows)
    # singletons: canonical=1 of themselves only if you want; keep is_canonical=1 for cluster reps
    df.loc[df["n_arrangements"] == 1, "is_canonical"] = 1
    C.write_parquet_atomic(df, CLUSTERS)
    C.log(f"clusters DONE: {len(md5s)} files, {n_multi} multi-arrangement clusters "
          f"(sim>={args.sim}) -> {CLUSTERS}", "signatures.log")
    # report biggest clusters for spot-check
    big = df[df.n_arrangements > 1].groupby("song_id").size().sort_values(ascending=False).head(20)
    C.log(f"  biggest cluster sizes: {big.tolist()[:20]}", "signatures.log")
    C.progress("PHASE3", f"files={len(md5s)} clusters={n_multi}")


if __name__ == "__main__":
    main()
