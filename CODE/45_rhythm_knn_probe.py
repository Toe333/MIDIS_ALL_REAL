#!/usr/bin/env python3
"""45_rhythm_knn_probe.py — regression probe for the rhythm/kNN block.

Measures whether neighbors are homogeneous along rhythm axes (the existing
"rhythm clusters" guarantee) AND along the newly-added corrected tempo/meter.
Run BEFORE and AFTER a 26_signature_extend rebuild to confirm no regression.

For a fixed, deterministic set of seed songs (one per rhythm characteristic) it
pulls the 12 cosine neighbors from the given kNN pickle and reports, per seed,
the spread (std) of key rhythm features over the neighborhood vs the global std.
Tighter-than-global = that axis clusters. Lower is better for the seeded axis.

Usage:
  python3 CODE/45_rhythm_knn_probe.py                       # current knn_cosine.pkl
  python3 CODE/45_rhythm_knn_probe.py --knn <path> --ext <path>
"""
import os, sys, argparse, pickle, json
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIG = os.path.join(ROOT, "SIGNATURES_DATA")
META = os.path.join(ROOT, "catalog", "metadata.parquet")

# rhythm/tempo/meter columns we report neighborhood spread on
NUM_COLS = ["swing_bur", "syncopation", "mel_rhythm_triplet", "mel_rhythm_dotted",
            "polyrhythm_hint", "felt_bpm", "bpm_v2"]
CAT_COLS = ["ts_final", "tempo_class"]


def pick_seeds(df):
    """Deterministic seed md5 per rhythm characteristic (idxmax over a filter)."""
    seeds = {}
    f = df
    def top(mask, col):
        sub = f[mask]
        return None if sub.empty else sub[col].idxmax()
    seeds["swing"]   = top((f["swing_confidence"] > 0.5) & (f["swing_bur"].between(1.5, 2.4)), "swing_confidence")
    seeds["triplet"] = top(f["mel_rhythm_triplet"].notna(), "mel_rhythm_triplet")
    seeds["dotted"]  = top(f["mel_rhythm_dotted"].notna(), "mel_rhythm_dotted")
    seeds["highsync"]= top(f["syncopation"].notna(), "syncopation")
    # odd meter + fast tempo: the axes we are ADDING — want neighbors to share them
    seeds["meter34"] = top((f["ts_final"] == "3/4") & f["felt_bpm"].notna(), "felt_bpm")
    seeds["fast"]    = top(f["felt_bpm"].between(20, 400), "felt_bpm")
    return {k: v for k, v in seeds.items() if v is not None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--knn", default=os.path.join(SIG, "knn_cosine.pkl"))
    ap.add_argument("--ext", default=os.path.join(SIG, "signatures_ext.npy"))
    ap.add_argument("--tag", default="baseline")
    args = ap.parse_args()

    with open(os.path.join(SIG, "signatures_md5.txt")) as fh:
        md5s = [l.strip() for l in fh if l.strip()]
    pos = {m: i for i, m in enumerate(md5s)}
    ext = np.load(args.ext)
    with open(args.knn, "rb") as fh:
        payload = pickle.load(fh)
    nn = payload["nn"]
    print(f"[{args.tag}] ext={ext.shape} knn dims={nn.n_features_in_} "
          f"block_dims={payload.get('block_dims')}")

    sel_cols = sorted(set(["md5", "swing_confidence"] + NUM_COLS + CAT_COLS))
    df = pd.read_parquet(META, columns=sel_cols).set_index("md5")
    df = df.reindex(md5s)
    # global std for context (inf -> nan so it doesn't poison the std)
    def fin(a):
        a = a.astype(float).copy(); a[~np.isfinite(a)] = np.nan; return a
    gstd = {c: float(np.nanstd(fin(df[c].to_numpy()))) for c in NUM_COLS}

    seeds = pick_seeds(df)
    out = {"tag": args.tag, "knn": args.knn, "global_std": gstd, "seeds": {}}
    for name, md5 in seeds.items():
        i = pos[md5]
        dist, idx = nn.kneighbors(ext[i:i+1], n_neighbors=12)
        nbr = [j for j in idx[0] if j != i][:11]
        nb_md5 = [md5s[j] for j in nbr]
        sub = df.loc[nb_md5]
        rep = {"seed_md5": md5, "n_nbr": len(nb_md5)}
        for c in NUM_COLS:
            v = sub[c].to_numpy(dtype=float)
            rep[f"{c}_mean"] = round(float(np.nanmean(v)), 4)
            rep[f"{c}_std"]  = round(float(np.nanstd(v)), 4)
        for c in CAT_COLS:
            vc = sub[c].value_counts(dropna=False)
            top = vc.index[0]
            rep[f"{c}_top"] = str(top)
            rep[f"{c}_agree"] = round(float(vc.iloc[0] / len(sub)), 3)
        out["seeds"][name] = rep
        seedrow = df.loc[md5]
        print(f"\n[{name}] seed={md5[:8]} "
              f"swing_bur={seedrow['swing_bur']} sync={seedrow['syncopation']} "
              f"trip={seedrow['mel_rhythm_triplet']} ts={seedrow['ts_final']} "
              f"felt_bpm={seedrow['felt_bpm']}")
        print(f"  nbr swing_bur {rep['swing_bur_mean']}±{rep['swing_bur_std']} "
              f"| sync {rep['syncopation_mean']}±{rep['syncopation_std']} "
              f"| trip {rep['mel_rhythm_triplet_mean']}±{rep['mel_rhythm_triplet_std']}")
        print(f"  nbr felt_bpm {rep['felt_bpm_mean']}±{rep['felt_bpm_std']} (global±{gstd['felt_bpm']:.1f}) "
              f"| ts_final top={rep['ts_final_top']} agree={rep['ts_final_agree']} "
              f"| tempo_class top={rep['tempo_class_top']} agree={rep['tempo_class_agree']}")

    dst = os.path.join(ROOT, "_work", f"rhythm_knn_probe_{args.tag}.json")
    with open(dst, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nwrote {dst}")


if __name__ == "__main__":
    main()
