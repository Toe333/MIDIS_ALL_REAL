#!/usr/bin/env python3
"""
43_redetect_key.py — fix key detection + its confidence, recomputed from NOTESEQ cache.

Two bugs in the old detector (_common.estimate_key):
  1. confidence = best_corr - 2nd_best_corr  → always tiny because every key's
     relative major/minor scores almost identically. 100% of the corpus read <0.5
     "confidence" even when the key is obvious. The strength of the tonal fit is
     best_corr itself, NOT the gap to the runner-up.
  2. histogram was note-COUNT based; key detection works better DURATION-weighted
     (a pitch held for a whole bar matters more than a passing 16th).

This re-derives, per song, a duration-weighted pitch-class histogram (drums excluded)
and runs Krumhansl-Schmuckler over all 24 keys. Writes _work/key_v2.parquet:
  md5, key_v2, mode_v2, key_corr (0-1 = real confidence), key_margin (old metric),
  key_alt (2nd best, usually the relative), tonal_strength

Modes:
  python3 CODE/43_redetect_key.py                  # full re-derive over the cache
  python3 CODE/43_redetect_key.py --benchmark 300  # compare vs music21 on N samples
"""
import argparse, glob, json, os, pathlib
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT    = pathlib.Path(__file__).resolve().parents[1]
NOTESEQ = ROOT / "NOTESEQ_DATA"
OUT     = ROOT / "_work" / "key_v2.parquet"

# Krumhansl-Kessler profiles (the standard K-S profiles; music21's default too)
KS_MAJOR = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
KS_MINOR = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
PC_NAMES = ["C","C#","D","Eb","E","F","F#","G","Ab","A","Bb","B"]
_MAJ = np.array([np.roll(KS_MAJOR, t) for t in range(12)])  # 12x12
_MIN = np.array([np.roll(KS_MINOR, t) for t in range(12)])

def detect_key(pc_hist):
    """pc_hist: length-12 weighted pitch-class vector. Returns dict."""
    s = pc_hist.sum()
    if s <= 0:
        return dict(key_v2=None, mode_v2=None, key_corr=0.0, key_margin=0.0,
                    key_alt=None, tonal_strength=0.0)
    x = pc_hist - pc_hist.mean()
    def corrs(profiles):
        p = profiles - profiles.mean(axis=1, keepdims=True)
        num = (p * x).sum(axis=1)
        den = np.sqrt((p * p).sum(axis=1) * (x * x).sum()) + 1e-12
        return num / den
    cmaj, cmin = corrs(_MAJ), corrs(_MIN)
    allc = np.concatenate([cmaj, cmin])                # 0-11 major, 12-23 minor
    order = np.argsort(allc)[::-1]
    best, second = order[0], order[1]
    def name(i): return (PC_NAMES[i % 12], "major" if i < 12 else "minor")
    bn, bm = name(best); an, am = name(second)
    # tonal_strength: how peaked the histogram is on the chosen scale's 7 notes
    tonic = best % 12
    scale = (np.array([0,2,4,5,7,9,11]) if best < 12 else np.array([0,2,3,5,7,8,10])) + tonic
    inscale = pc_hist[scale % 12].sum() / s
    return dict(key_v2=f"{bn} {bm}", mode_v2=bm, key_corr=round(float(allc[best]),4),
                key_margin=round(float(allc[best]-allc[second]),4),
                key_alt=f"{an} {am}", tonal_strength=round(float(inscale),4))

def pc_hist_from_arr(arr):
    """duration-weighted PC histogram, drums (chan 9) excluded."""
    if arr.shape[0] == 0:
        return np.zeros(12)
    chan = arr[:, 2]; nd = arr[chan != 9]
    if nd.shape[0] == 0:
        nd = arr
    pcs = (nd[:, 3] % 12).astype(np.int64)
    durs = np.maximum(nd[:, 1].astype(np.float64), 1.0)
    h = np.zeros(12)
    np.add.at(h, pcs, durs)
    return h

def process_bucket(bucket):
    npz = NOTESEQ / f"{bucket}.npz"
    if not npz.exists():
        return []
    z = np.load(npz)
    out = []
    for md5 in z.files:
        rec = {"md5": md5}
        try:
            rec.update(detect_key(pc_hist_from_arr(z[md5])))
        except Exception as e:
            rec.update(dict(key_v2=None, mode_v2=None, key_corr=0.0,
                            key_margin=0.0, key_alt=None, tonal_strength=0.0))
        out.append(rec)
    return out

def run_full(workers):
    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(str(NOTESEQ / "*.npz")))
    print(f"re-deriving key for {len(buckets)} buckets, {workers} workers …", flush=True)
    rows, done = [], 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for recs in ex.map(process_bucket, buckets):
            rows.extend(recs); done += 1
            if done % 64 == 0: print(f"  {done}/{len(buckets)} buckets", flush=True)
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT}  ({len(df):,} rows)")
    cat = pd.read_parquet(ROOT / "catalog/metadata.parquet", columns=["md5","key","mode","key_confidence"])
    j = df.merge(cat, on="md5", how="left")
    agree = (j.key_v2 == (j.key)).mean()
    print("\n==== KEY REPORT ====")
    print(f"new key_corr  : mean {j.key_corr.mean():.3f}  median {j.key_corr.median():.3f}  >0.7: {(j.key_corr>0.7).mean()*100:.0f}%")
    print(f"old confidence: mean {j.key_confidence.mean():.3f}  >0.7: {(j.key_confidence>0.7).mean()*100:.0f}%")
    print(f"key_v2 == old key (exact str): {agree*100:.1f}%")
    print(f"mode agreement:                {(j.mode_v2==j['mode']).mean()*100:.1f}%")

def run_benchmark(n):
    """Compare key_v2 vs music21's analysis on n random MIDI files."""
    import music21, random
    md5s = pd.read_parquet(ROOT/"catalog/metadata.parquet", columns=["md5"])["md5"].tolist()
    random.seed(0); samp = random.sample(md5s, n)
    # build md5 -> bucket cache lookup
    agree_key = agree_tonic = agree_mode = ok = 0
    rows = []
    for md5 in samp:
        bucket = md5[:2]
        try:
            z = np.load(NOTESEQ / f"{bucket}.npz")
            if md5 not in z.files: continue
            mine = detect_key(pc_hist_from_arr(z[md5]))
        except Exception:
            continue
        try:
            sc = music21.converter.parse(str(ROOT/"MIDIs"/md5[:2]/f"{md5}.mid"))
            k = sc.analyze("key")
            m21 = f"{k.tonic.name.replace('-','b')} {k.mode}"
            m21_tonic = k.tonic.pitchClass
        except Exception:
            continue
        ok += 1
        my_tonic = PC_NAMES.index(mine["key_v2"].split()[0]) if mine["key_v2"] else -1
        ak = (mine["key_v2"] == m21); at = (my_tonic == m21_tonic); am = (mine["mode_v2"] == k.mode)
        agree_key += ak; agree_tonic += at; agree_mode += am
        rows.append((md5[:8], mine["key_v2"], round(mine["key_corr"],2), m21, ak))
    print(f"\n==== music21 BENCHMARK (n={ok}) ====")
    print(f"exact key agreement : {agree_key/ok*100:.1f}%")
    print(f"tonic agreement     : {agree_tonic/ok*100:.1f}%")
    print(f"mode agreement      : {agree_mode/ok*100:.1f}%")
    print("\nsample disagreements:")
    for r in [r for r in rows if not r[4]][:15]:
        print(f"  {r[0]}  mine={r[1]:<10}(corr {r[2]})  music21={r[3]}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--benchmark", type=int, default=0)
    args = ap.parse_args()
    if args.benchmark:
        run_benchmark(args.benchmark)
    else:
        run_full(args.workers)
