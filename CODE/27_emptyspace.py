#!/usr/bin/env python3
"""
27_emptyspace.py — Phase 11 #1: the EMPTY-SPACE HUNT over the N×88 signature.

The payoff of vectorizing. Maps where the 459,805 songs sit dense vs sparse in the
extended signature space (pitch+rhythm+melody+harmony, rhythm ×2), then surfaces
"coherent-but-underpopulated corners" — regions that are musically plausible but that
almost nobody has written in. Those corners are the candidate "new forms of music".

Reads (never writes) the build artifacts:
  SIGNATURES_DATA/signatures_ext.npy   (N x 88, L2-per-pillar, rhythm & groove ×2; norm≈√7)
  SIGNATURES_DATA/signatures_md5.txt   (row -> md5)
  catalog/metadata.parquet             (200 cols, for human-readable descriptions)

Writes everything under _work/emptyspace/ (resumable; each stage cached):
  clusters.parquet        md5 -> cluster_id              (stage: cluster)
  clusters_centroids.npy  k x 74 unit centroids          (stage: cluster)
  density.parquet         md5 -> frontier (mean cos-dist to k NN)  (stage: density)
  cluster_summary.parquet one row per cluster, human-described      (stage: summary)
  corners_isolated.parquet  rare-but-coherent real pockets          (stage: corners)
  corners_blends.parquet    empty interpolations between dense types(stage: corners)

Cosine geometry: signatures_ext rows have ~constant norm √5, so we unit-normalize once
(U) and cosine similarity = dot product. Clustering is spherical k-means via
MiniBatchKMeans on U (centroids re-normalized). "Empty" = few/no corpus points within a
cosine radius; "coherent" = the region is adjacent to / between real dense clusters, or
is itself a tight isolated pocket of real songs.

Usage:
  python3 CODE/27_emptyspace.py all                 # cluster -> density -> summary -> corners
  python3 CODE/27_emptyspace.py cluster --k 1200
  python3 CODE/27_emptyspace.py density             # full 460k pass (~30 min); --sample N for a fast map
  python3 CODE/27_emptyspace.py summary
  python3 CODE/27_emptyspace.py corners --top 60
  python3 CODE/27_emptyspace.py show --corner-blends 20   # print top corners in plain language
"""
import argparse, os, sys, time, json
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG  = os.path.join(ROOT, "SIGNATURES_DATA")
OUT  = os.path.join(ROOT, "_work", "emptyspace")
os.makedirs(OUT, exist_ok=True)

# informational only (the code unit-normalizes the whole row; it never slices by block)
BLOCK_DIMS = {"pitch": 36, "rhythm": 20, "melody": 13, "harmony": 8, "groove": 11}  # = 88

# catalog columns used to describe a region in human/musical terms
DESC_NUM = ["bpm", "felt_bpm", "swing_bur", "syncopation", "note_density", "polyphony_density",
            "mel_stepwise_ratio", "mel_leap_ratio", "mel_chromaticism",
            "diatonic_ratio", "chord_density", "harmonic_rhythm", "n_key_areas",
            "duration_sec"]
DESC_FRAC = ["is_swung", "is_dotted", "is_triplet_feel", "has_melody",
             "has_extended_harmony"]
# ts_final = the corrected ear-validated meter (now drives clustering, so caption it)
DESC_CAT = ["genre_hint", "key", "mode", "tempo_class", "ts_final"]


# ----------------------------------------------------------------------------- io
def load_vectors():
    ext = np.load(os.path.join(SIG, "signatures_ext.npy")).astype(np.float32)
    md5s = open(os.path.join(SIG, "signatures_md5.txt")).read().split()
    assert len(md5s) == ext.shape[0], (len(md5s), ext.shape)
    norms = np.linalg.norm(ext, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    U = ext / norms                       # unit rows -> cosine = dot
    return ext, U, md5s


def load_catalog(md5s):
    import pandas as pd
    cols = ["md5"] + DESC_NUM + DESC_FRAC + DESC_CAT + ["composer", "title"]
    m = pd.read_parquet(os.path.join(ROOT, "catalog", "metadata.parquet"),
                        columns=[c for c in cols if c is not None])
    m = m.drop_duplicates("md5").set_index("md5")
    m = m.reindex(md5s)                   # align to signature row order; absent -> NaN
    return m


def _notify(msg):
    """best-effort phone ping; never fails the run"""
    try:
        import subprocess
        subprocess.run(["notify", msg], timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# ------------------------------------------------------------------- stage: cluster
def stage_cluster(args):
    from sklearn.cluster import MiniBatchKMeans
    import pandas as pd
    ext, U, md5s = load_vectors()
    k = args.k
    print(f"[cluster] MiniBatchKMeans k={k} over {U.shape[0]:,}x{U.shape[1]} (spherical)")
    t = time.time()
    km = MiniBatchKMeans(n_clusters=k, batch_size=10000, n_init=3,
                         max_iter=200, random_state=0, verbose=0)
    labels = km.fit_predict(U)
    cent = km.cluster_centers_.astype(np.float32)
    cn = np.linalg.norm(cent, axis=1, keepdims=True); cn[cn == 0] = 1.0
    cent = cent / cn                      # re-normalize centroids to the sphere
    print(f"[cluster] done in {time.time()-t:.1f}s; inertia={km.inertia_:.1f}")
    np.save(os.path.join(OUT, "clusters_centroids.npy"), cent)
    pd.DataFrame({"md5": md5s, "cluster_id": labels.astype(np.int32)}).to_parquet(
        os.path.join(OUT, "clusters.parquet"))
    sizes = np.bincount(labels, minlength=k)
    print(f"[cluster] sizes: min {sizes.min()} med {int(np.median(sizes))} "
          f"max {sizes.max()} ; empty clusters {int((sizes==0).sum())}")
    return labels, cent, md5s


# ------------------------------------------------------------------- stage: density
def stage_density(args):
    """Per-point FRONTIER score = mean cosine DISTANCE to its k nearest neighbours
    (excluding self). High => the song sits in a sparse region (the frontier).
    Batched full-corpus pass; --sample to map a subset fast."""
    import pandas as pd
    ext, U, md5s = load_vectors()
    N = U.shape[0]
    k = args.knn
    rows = np.arange(N)
    if args.sample and args.sample < N:
        rng = np.random.default_rng(0)
        rows = np.sort(rng.choice(N, size=args.sample, replace=False))
        print(f"[density] SAMPLE map: {len(rows):,} query points, k={k}")
    else:
        print(f"[density] FULL pass: {N:,} query points, k={k} (~30 min)")
    Ut = np.ascontiguousarray(U.T)        # 74 x N for fast matmul
    out = np.empty(len(rows), dtype=np.float32)
    B = 512
    t0 = time.time()
    for bi in range(0, len(rows), B):
        qi = rows[bi:bi+B]
        sims = U[qi] @ Ut                 # b x N cosine sims
        # self-sim is 1.0; knock it out then take k largest sims
        sims[np.arange(len(qi)), qi] = -2.0
        part = np.partition(sims, N-k, axis=1)[:, N-k:]   # k largest sims
        out[bi:bi+len(qi)] = 1.0 - part.mean(axis=1)      # mean cosine distance
        if bi % (B*40) == 0:
            el = time.time()-t0
            done = bi+len(qi)
            eta = el/done*(len(rows)-done)
            print(f"[density] {done:,}/{len(rows):,}  {el:.0f}s elapsed  ETA {eta/60:.1f}m",
                  flush=True)
    df = pd.DataFrame({"md5": [md5s[i] for i in rows], "frontier": out})
    tag = f"_sample{args.sample}" if (args.sample and args.sample < N) else ""
    path = os.path.join(OUT, f"density{tag}.parquet")
    df.to_parquet(path)
    print(f"[density] wrote {path}: frontier min {out.min():.3f} med "
          f"{np.median(out):.3f} max {out.max():.3f}")
    _notify(f"emptyspace density done: {len(rows):,} pts")
    return df


# ------------------------------------------------------------------- stage: summary
def _describe(sub, m):
    """plain-language description of a set of songs (a cluster) from catalog medians"""
    d = {}
    idx = sub  # md5 list
    mm = m.reindex(idx)
    for c in DESC_NUM:
        if c in mm: d[c] = float(np.nanmedian(mm[c].values.astype("float64")))
    for c in DESC_FRAC:
        if c in mm: d[c] = float(np.nanmean(mm[c].values.astype("float64")))
    for c in DESC_CAT:
        if c in mm:
            vc = mm[c].value_counts()
            d[c] = (str(vc.index[0]), int(vc.iloc[0])) if len(vc) else ("?", 0)
    return d


def _phrase(d):
    """one-line musical caption from a description dict"""
    bits = []
    g = d.get("genre_hint", ("?", 0))[0]
    if g and g != "unknown": bits.append(g)
    tc = d.get("tempo_class", ("?", 0))[0]
    bpm = d.get("bpm")
    if bpm == bpm: bits.append(f"{bpm:.0f}bpm {tc}")
    fb = d.get("felt_bpm")
    if fb == fb and bpm == bpm and abs(fb - bpm) >= 5: bits.append(f"felt{fb:.0f}")
    ts = d.get("ts_final", ("?", 0))[0]
    if ts and ts not in ("?", "4/4"): bits.append(ts)   # surface non-4/4 meters
    if d.get("is_swung", 0) > 0.25: bits.append(f"swung({d.get('swing_bur',0):.2f})")
    if d.get("is_triplet_feel", 0) > 0.25: bits.append("triplet-feel")
    if d.get("is_dotted", 0) > 0.30: bits.append("dotted")
    sy = d.get("syncopation")
    if sy == sy and sy > 0: bits.append(f"sync{sy:.2f}")
    ch = d.get("mel_chromaticism")
    if ch == ch: bits.append(f"chroma{ch:.2f}")
    di = d.get("diatonic_ratio")
    if di == di: bits.append(f"diat{di:.2f}")
    cd = d.get("chord_density")
    if cd == cd: bits.append(f"chord_dens{cd:.2f}")
    if d.get("has_extended_harmony", 0) > 0.3: bits.append("ext-harm")
    return " · ".join(bits)


def stage_summary(args):
    import pandas as pd
    cl = pd.read_parquet(os.path.join(OUT, "clusters.parquet"))
    cent = np.load(os.path.join(OUT, "clusters_centroids.npy"))
    ext, U, md5s = load_vectors()
    m = load_catalog(md5s)
    row_of = {h: i for i, h in enumerate(md5s)}
    labels = cl["cluster_id"].values
    k = cent.shape[0]

    # centroid-centroid cosine -> isolation = 1 - max sim to any OTHER centroid
    CC = cent @ cent.T
    np.fill_diagonal(CC, -2.0)
    nearest_other = CC.argmax(1)
    isolation = 1.0 - CC.max(1)

    # optional frontier (density) join
    fr = None
    dp = os.path.join(OUT, "density.parquet")
    if os.path.exists(dp):
        fr = pd.read_parquet(dp).set_index("md5")["frontier"]

    recs = []
    Uall = U
    for c in range(k):
        members = np.where(labels == c)[0]
        size = len(members)
        if size == 0:
            continue
        sims = Uall[members] @ cent[c]
        tight = float(1.0 - sims.mean())           # mean cos-dist member->centroid (small=tight)
        # representatives = closest real songs to the centroid (to LISTEN to)
        order = members[np.argsort(-sims)]
        reps = [md5s[i] for i in order[:5]]
        mem_md5 = [md5s[i] for i in members]
        d = _describe(mem_md5, m)
        rec = {"cluster_id": c, "size": size, "tightness": tight,
               "isolation": float(isolation[c]), "nearest_other": int(nearest_other[c]),
               "caption": _phrase(d), "reps": ";".join(reps)}
        if fr is not None:
            rec["frontier_med"] = float(np.nanmedian(fr.reindex(mem_md5).values))
        for c2 in DESC_NUM:    rec[c2] = d.get(c2, np.nan)
        for c2 in DESC_FRAC:   rec[c2] = d.get(c2, np.nan)
        for c2 in DESC_CAT:    rec[c2] = d.get(c2, ("?", 0))[0]
        recs.append(rec)
    sm = pd.DataFrame(recs).sort_values("size")
    sm.to_parquet(os.path.join(OUT, "cluster_summary.parquet"))
    print(f"[summary] {len(sm)} non-empty clusters -> cluster_summary.parquet")
    print(f"[summary] size: min {sm['size'].min()} med {int(sm['size'].median())} "
          f"max {sm['size'].max()}")
    print(f"[summary] most ISOLATED coherent clusters (rare-but-real pockets):")
    iso = sm[sm["size"] >= args.min_pocket].sort_values("isolation", ascending=False)
    for _, r in iso.head(12).iterrows():
        print(f"   #{r['cluster_id']:5d} n={r['size']:5d} iso={r['isolation']:.3f} "
              f"tight={r['tightness']:.3f} | {r['caption']}")
    return sm


# ------------------------------------------------------------------- stage: corners
def stage_corners(args):
    """
    Two complementary maps of 'coherent but empty':
      A) ISOLATED POCKETS — real clusters that are small/tight yet far from everything
         else: rare genuine musical types that exist but are under-written.
      B) EMPTY BLENDS — midpoints between pairs of DENSE, DISTINCT clusters that
         themselves have almost no corpus points nearby: plausible fusions nobody has
         made. Ranked by emptiness (corpus neighbours within a cosine radius).
    """
    import pandas as pd
    sm = pd.read_parquet(os.path.join(OUT, "cluster_summary.parquet")).set_index("cluster_id")
    cent = np.load(os.path.join(OUT, "clusters_centroids.npy"))
    ext, U, md5s = load_vectors()
    m = load_catalog(md5s)
    N = U.shape[0]
    Ut = np.ascontiguousarray(U.T)

    # --- radius calibration: typical NN distance scale -> pick a "within neighbourhood"
    # sim threshold. Use the 50th-NN sim of a random sample as the radius.
    rng = np.random.default_rng(1)
    samp = rng.choice(N, size=3000, replace=False)
    s = U[samp] @ Ut
    s[np.arange(len(samp)), samp] = -2.0
    kth = np.partition(s, N-args.radius_k, axis=1)[:, N-args.radius_k]   # k-th largest sim
    sim_thresh = float(np.median(kth))
    print(f"[corners] neighbourhood radius: sim>={sim_thresh:.4f} "
          f"(median {args.radius_k}th-NN sim); points within = local population")

    # ---------------- A) isolated coherent pockets
    pockets = sm[sm["size"] >= args.min_pocket].sort_values(
        "isolation", ascending=False).head(args.top).reset_index()
    pockets.to_parquet(os.path.join(OUT, "corners_isolated.parquet"))

    # ---------------- B) empty blends between dense anchors
    anchors = sm[sm["size"] >= sm["size"].median()].index.values
    A = cent[anchors]                                  # a x 74
    AC = A @ A.T
    # candidate pairs: distinct (sim in a band) so the blend is a real fusion, not noise
    iu = np.triu_indices(len(anchors), k=1)
    pair_sim = AC[iu]
    band = (pair_sim >= args.pair_lo) & (pair_sim <= args.pair_hi)
    pi, pj = iu[0][band], iu[1][band]
    print(f"[corners] {len(pi):,} candidate anchor pairs in sim-band "
          f"[{args.pair_lo},{args.pair_hi}] of {len(anchors)} dense anchors")
    if len(pi) == 0:
        print("[corners] no pairs in band; widen --pair-lo/--pair-hi"); return
    mids = A[pi] + A[pj]
    mn = np.linalg.norm(mids, axis=1, keepdims=True); mn[mn == 0] = 1.0
    mids = (mids / mn).astype(np.float32)              # p x 74 unit midpoints

    # population within radius of each midpoint, batched over midpoints
    pop = np.zeros(len(mids), dtype=np.int32)
    nn1 = np.zeros(len(mids), dtype=np.float32)        # nearest corpus sim (coherence guard)
    CB = 1024
    t0 = time.time()
    for bi in range(0, len(mids), CB):
        ch = mids[bi:bi+CB]
        sims = U @ ch.T                                # N x cb
        pop[bi:bi+ch.shape[0]] = (sims >= sim_thresh).sum(0)
        nn1[bi:bi+ch.shape[0]] = sims.max(0)
        if bi % (CB*10) == 0:
            print(f"[corners]   blends {bi:,}/{len(mids):,}  {time.time()-t0:.0f}s", flush=True)
    # coherence guard: nearest real song must be within a looser radius (not a void/outlier)
    coh = nn1 >= args.coh_min
    cand = np.where(coh)[0]
    # rank: emptiest first (pop asc); among equally-empty, the most COHERENT (closest to
    # the manifold = most plausibly fillable) first (nearest_sim desc).
    cand = cand[np.lexsort((-nn1[cand], pop[cand]))]
    recs = []
    for r in cand[:args.top]:
        ca, cb = int(anchors[pi[r]]), int(anchors[pj[r]])
        # nearest real songs to the midpoint -> closest existing music to listen to,
        # and the basis for describing what the corner itself sounds like
        sims = U @ mids[r]
        nb = np.argsort(-sims)[:args.neigh]
        mid_caption = _phrase(_describe([md5s[i] for i in nb], m))
        recs.append({
            "anchor_a": ca, "anchor_b": cb, "pair_sim": float(AC[pi[r], pj[r]]),
            "midpoint_population": int(pop[r]), "nearest_sim": float(nn1[r]),
            "midpoint_caption": mid_caption,
            "cap_a": sm.loc[ca, "caption"], "cap_b": sm.loc[cb, "caption"],
            "size_a": int(sm.loc[ca, "size"]), "size_b": int(sm.loc[cb, "size"]),
            "nearest_songs": ";".join(md5s[i] for i in nb[:6]),
            "nearest_song_sims": ";".join(f"{sims[i]:.3f}" for i in nb[:6]),
        })
    bl = pd.DataFrame(recs)
    bl.to_parquet(os.path.join(OUT, "corners_blends.parquet"))
    print(f"\n[corners] wrote corners_isolated.parquet ({len(pockets)}) + "
          f"corners_blends.parquet ({len(bl)})")
    print("\n=== TOP EMPTY-BUT-COHERENT BLENDS (fusions nobody has written) ===")
    for _, r in bl.head(args.show).iterrows():
        print(f"\n  pop={r['midpoint_population']:3d} near={r['nearest_sim']:.3f} "
              f"(parent sim {r['pair_sim']:.2f})  #{r['anchor_a']}×#{r['anchor_b']}")
        print(f"    THE CORNER: {r['midpoint_caption']}")
        print(f"    = blend of A ({r['size_a']:>5}): {r['cap_a']}")
        print(f"             & B ({r['size_b']:>5}): {r['cap_b']}")
        print(f"    closest real song: {r['nearest_songs'].split(';')[0]} "
              f"({r['nearest_song_sims'].split(';')[0]})")
    _notify(f"emptyspace corners done: {len(bl)} blends, {len(pockets)} pockets")
    return bl


# ----------------------------------------------------------------------- stage: show
def stage_show(args):
    import pandas as pd
    if args.corner_blends:
        bl = pd.read_parquet(os.path.join(OUT, "corners_blends.parquet"))
        print("=== EMPTY-BUT-COHERENT BLENDS ===")
        for _, r in bl.head(args.corner_blends).iterrows():
            print(f"\n  pop={r['midpoint_population']:3d} near={r['nearest_sim']:.3f}  "
                  f"#{r['anchor_a']}×#{r['anchor_b']}")
            print(f"    A: {r['cap_a']}")
            print(f"    B: {r['cap_b']}")
            print(f"    listen: {r['nearest_songs'].split(';')[0]}")
    if args.pockets:
        pk = pd.read_parquet(os.path.join(OUT, "corners_isolated.parquet"))
        print("\n=== ISOLATED COHERENT POCKETS (rare real types) ===")
        for _, r in pk.head(args.pockets).iterrows():
            print(f"  #{int(r['cluster_id']):5d} n={int(r['size']):5d} "
                  f"iso={r['isolation']:.3f} | {r['caption']}")
            print(f"      listen: {r['reps'].split(';')[0]}")


# ------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("cluster"); p.add_argument("--k", type=int, default=1200)
    p = sub.add_parser("density")
    p.add_argument("--knn", type=int, default=25)
    p.add_argument("--sample", type=int, default=0, help="0 = full corpus")
    p = sub.add_parser("summary")
    p.add_argument("--min-pocket", type=int, default=30)
    p = sub.add_parser("corners")
    p.add_argument("--top", type=int, default=60)
    p.add_argument("--show", type=int, default=15)
    p.add_argument("--min-pocket", type=int, default=30)
    p.add_argument("--radius-k", type=int, default=50)
    p.add_argument("--pair-lo", type=float, default=0.30)
    p.add_argument("--pair-hi", type=float, default=0.75)
    p.add_argument("--coh-min", type=float, default=0.55)
    p.add_argument("--neigh", type=int, default=40, help="NN used to caption a corner")
    p = sub.add_parser("show")
    p.add_argument("--corner-blends", type=int, default=0)
    p.add_argument("--pockets", type=int, default=0)
    p = sub.add_parser("all")
    p.add_argument("--k", type=int, default=1200)
    p.add_argument("--density-sample", type=int, default=0)

    a = ap.parse_args()
    if a.cmd == "cluster":
        stage_cluster(a)
    elif a.cmd == "density":
        stage_density(a)
    elif a.cmd == "summary":
        stage_summary(a)
    elif a.cmd == "corners":
        stage_corners(a)
    elif a.cmd == "show":
        stage_show(a)
    elif a.cmd == "all":
        stage_cluster(argparse.Namespace(k=a.k))
        stage_density(argparse.Namespace(knn=25, sample=a.density_sample))
        stage_summary(argparse.Namespace(min_pocket=30))
        stage_corners(argparse.Namespace(top=60, show=15, min_pocket=30, radius_k=50,
                                         pair_lo=0.30, pair_hi=0.75, coh_min=0.55, neigh=40))


if __name__ == "__main__":
    main()
