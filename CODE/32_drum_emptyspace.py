#!/usr/bin/env python3
"""
32_drum_emptyspace.py — Empty-space hunt in the 72-D DrumDNA space.
Finds novel drum feels by clustering the 311k songs with kits and finding
gaps in the rhythmic manifold.
"""
import argparse, os, sys, time, json
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG  = os.path.join(ROOT, "SIGNATURES_DATA")
OUT  = os.path.join(ROOT, "_work", "drum_emptyspace")
os.makedirs(OUT, exist_ok=True)

# DrumDNA columns for description
DESC_NUM = [
    "kick_density", "snare_backbeat", "swing", "syncopation_poly", 
    "pattern_entropy", "beat3_accent", "total_density", "perc_diversity",
    "kick_on_downbeat", "kick_snare_interlock", "timing_tightness",
    "ghost_dynamics", "pulse_clarity"
]

def load_data():
    print("[load] loading signatures and dna...")
    sig = np.load(os.path.join(SIG, "signatures_drums.npy")).astype(np.float32)
    md5s = open(os.path.join(SIG, "signatures_md5.txt")).read().split()
    dna = pd.read_parquet(os.path.join(ROOT, "_work", "drum_dna.parquet"))
    dna = dna.drop_duplicates("md5").set_index("md5").reindex(md5s)
    
    # Filter to songs with drums
    mask = (dna.has_drums == 1).values
    sig_drum = sig[mask]
    md5_drum = [m for i, m in enumerate(md5s) if mask[i]]
    dna_drum = dna.iloc[mask]
    
    # Unit normalize for cosine distance
    norms = np.linalg.norm(sig_drum, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    U = sig_drum / norms
    
    return U, md5_drum, dna_drum

def stage_cluster(args):
    from sklearn.cluster import MiniBatchKMeans
    U, md5s, dna = load_data()
    k = args.k
    print(f"[cluster] MiniBatchKMeans k={k} over {U.shape[0]:,}x{U.shape[1]}")
    km = MiniBatchKMeans(n_clusters=k, batch_size=20000, n_init=3, max_iter=200, random_state=0)
    labels = km.fit_predict(U)
    cent = km.cluster_centers_.astype(np.float32)
    cn = np.linalg.norm(cent, axis=1, keepdims=True); cn[cn == 0] = 1.0
    cent = cent / cn
    
    np.save(os.path.join(OUT, "clusters_centroids.npy"), cent)
    pd.DataFrame({"md5": md5s, "cluster_id": labels.astype(np.int32)}).to_parquet(
        os.path.join(OUT, "clusters.parquet"))
    print(f"[cluster] done. centroid shape {cent.shape}")

def _phrase(d):
    bits = []
    if d.get("kick_density", 0) > 4: bits.append("busy-kick")
    if d.get("snare_backbeat", 0) > 0.9: bits.append("strong-backbeat")
    if d.get("snare_backbeat", 0) < 0.1: bits.append("no-backbeat")
    if d.get("beat3_accent", 0) > 0.4: bits.append("one-drop")
    if d.get("swing", 0) > 0.2: bits.append(f"swung({d['swing']:.2f})")
    if d.get("syncopation_poly", 0) > 0.3: bits.append(f"sync({d['syncopation_poly']:.2f})")
    if d.get("timing_tightness", 0) < 0.8: bits.append("loose-timing")
    if d.get("pattern_entropy", 0) < 0.5: bits.append("repetitive")
    return " · ".join(bits) if bits else "generic-beat"

def stage_summary(args):
    cl = pd.read_parquet(os.path.join(OUT, "clusters.parquet"))
    cent = np.load(os.path.join(OUT, "clusters_centroids.npy"))
    U, md5s, dna = load_data()
    labels = cl["cluster_id"].values
    
    recs = []
    for c in range(cent.shape[0]):
        members = np.where(labels == c)[0]
        if len(members) == 0: continue
        sims = U[members] @ cent[c]
        mem_md5 = [md5s[i] for i in members]
        sub = dna.loc[mem_md5]
        d = {col: float(sub[col].median()) for col in DESC_NUM if col in sub}
        recs.append({
            "cluster_id": c, "size": len(members), "tightness": float(1.0 - sims.mean()),
            "caption": _phrase(d), "reps": ";".join([mem_md5[i] for i in np.argsort(-sims)[:5]]),
            **d
        })
    pd.DataFrame(recs).to_parquet(os.path.join(OUT, "cluster_summary.parquet"))
    print(f"[summary] wrote {len(recs)} clusters")

def stage_corners(args):
    sm = pd.read_parquet(os.path.join(OUT, "cluster_summary.parquet")).set_index("cluster_id")
    cent = np.load(os.path.join(OUT, "clusters_centroids.npy"))
    U, md5s, dna = load_data()
    
    # Simple blend hunt
    anchors = sm[sm["size"] >= sm["size"].median()].index.values
    A = cent[anchors]
    iu = np.triu_indices(len(anchors), k=1)
    pair_sim = (A @ A.T)[iu]
    band = (pair_sim >= 0.3) & (pair_sim <= 0.7)
    pi, pj = iu[0][band], iu[1][band]
    mids = A[pi] + A[pj]
    mids /= np.linalg.norm(mids, axis=1, keepdims=True)
    
    pop = np.zeros(len(mids), dtype=np.int32)
    nn1 = np.zeros(len(mids), dtype=np.float32)
    for bi in range(0, len(mids), 512):
        ch = mids[bi:bi+512]
        sims = U @ ch.T
        pop[bi:bi+len(ch)] = (sims >= 0.85).sum(0)
        nn1[bi:bi+len(ch)] = sims.max(0)
    
    cand = np.where(nn1 >= 0.75)[0]
    cand = cand[np.lexsort((-nn1[cand], pop[cand]))]
    
    recs = []
    for r in cand[:30]:
        sims = U @ mids[r]
        nb = np.argsort(-sims)[:10]
        sub = dna.loc[[md5s[i] for i in nb]]
        d = {col: float(sub[col].median()) for col in DESC_NUM}
        recs.append({
            "pop": int(pop[r]), "near": float(nn1[r]), "caption": _phrase(d),
            "songs": ";".join(md5s[i] for i in nb[:3])
        })
    pd.DataFrame(recs).to_csv(os.path.join(OUT, "drum_corners.csv"), index=False)
    print(f"[corners] found {len(recs)} empty drum corners")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=["cluster", "summary", "corners", "all"])
    parser.add_argument("--k", type=int, default=800)
    args = parser.parse_args()
    if args.cmd == "cluster": stage_cluster(args)
    elif args.cmd == "summary": stage_summary(args)
    elif args.cmd == "corners": stage_corners(args)
    elif args.cmd == "all":
        stage_cluster(args)
        stage_summary(args)
        stage_corners(args)
