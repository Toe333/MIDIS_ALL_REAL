#!/usr/bin/env python3
"""61_harmony_deep.py — deepen vertical HARMONY (pillar 2).

Builds on 25_harmony_refine + 13_chords outputs + NOTESEQ.
Resumable md5 parquet under _work/harmony_deep.parquet (parts).

New/enriched:
- chord_quality_ratios (maj/min/dom7/maj7/min7/dim/aug/sus/ext)
- functional_profile (T/S/D proportions vs detected key)
- secondary_dominant_rate, borrowed_chord_rate, modal_interchange_score
- harmonic_tension_curve (mean, var, peak pos)
- voicing_density (notes/chord), chord_tone_spread (register)
- smoothed harmonic_rhythm, key_stability (from n_key_areas)

Cross-check note: midichords (asigalov) as validator on pilot subset only.

Usage:
  .venv-linux/bin/python CODE/61_harmony_deep.py --buckets 00
  .venv-linux/bin/python CODE/61_harmony_deep.py --merge-only
"""

import os, sys, glob, json, argparse, time
import numpy as np
import pandas as pd
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "harmony_deep.parquet")
PARTS = os.path.join(C.WORK, "harmony_deep_parts")
HARM_IN = os.path.join(C.WORK, "harmony_features.parquet")

# simple chord quals from chroma top
QUAL_MAP = {"maj":0,"min":1,"dom7":2,"maj7":3,"min7":4,"dim":5,"aug":6,"sus":7}

def chord_qual_hist(arr, tpb):
    if len(arr) == 0: return {k:0.0 for k in QUAL_MAP}
    starts = arr[:,0].astype(float)
    pitches = arr[:,3].astype(int)
    win = max(tpb, 1)
    nwin = int((starts.max() + 120) / win) + 1
    chroma = np.zeros((min(nwin, 2048), 12))
    for s, p in zip(starts, pitches):
        wi = min(int(s / win), len(chroma)-1)
        chroma[wi, p%12] += 1
    counts = Counter()
    for w in range(len(chroma)):
        ch = chroma[w]
        if ch.sum() < 2: continue
        root = int(np.argmax(ch))
        pcs = set(np.where(ch>0)[0])
        q = "maj"
        if len(pcs & {(root+3)%12, (root+4)%12}) == 1:
            q = "min" if (root+3)%12 in pcs else "maj"
        if (root+10)%12 in pcs: q = "dom7" if q=="maj" else "min7"
        if (root+11)%12 in pcs: q = "maj7"
        if (root+6)%12 in pcs: q = "dim"
        if (root+8)%12 in pcs and q=="maj": q="aug"
        if (root+5)%12 in pcs and len(pcs)<=3: q="sus"
        counts[q] += 1
    tot = sum(counts.values()) or 1
    return {k: round(counts.get(k,0)/tot, 4) for k in QUAL_MAP}

def functional_profile(arr, tpb, key_hint=None):
    # very rough: use global key or estimate, map chord roots to T/S/D
    if len(arr)==0: return {"func_T":0.33,"func_S":0.33,"func_D":0.34}
    # use estimate on full chroma
    pc = np.bincount(arr[:,3]%12, minlength=12).astype(float)
    kstr, mode, conf = C.estimate_key(pc)
    root = 0
    if kstr:
        try:
            root = C._PC_NAMES.index(kstr.split()[0])
        except: pass
    # simple: chord roots relative
    starts = arr[:,0].astype(float)
    pitches = arr[:,3]
    win = max(tpb*2, 120)
    n = int(starts.max()/win)+2
    roots = []
    for w in range(n):
        mask = (starts >= w*win) & (starts < (w+1)*win)
        if mask.sum() < 2: continue
        ch = np.bincount(pitches[mask]%12, minlength=12)
        if ch.sum()>0:
            roots.append(int(np.argmax(ch)))
    if not roots: return {"func_T":0.4,"func_S":0.3,"func_D":0.3}
    degs = [ (r - root) % 12 for r in roots ]
    t = sum(1 for d in degs if d in (0,)) 
    s = sum(1 for d in degs if d in (5,2))
    d = sum(1 for d in degs if d in (7,11,4,9))  # V, V7-ish, ii/V etc
    tot = len(degs) or 1
    return {"func_T":round(t/tot,4), "func_S":round(s/tot,4), "func_D":round(d/tot,4)}

def tension_stats(arr, tpb):
    # reuse rough dissonance on windows
    if len(arr)==0: return {"tension_mean":0.0,"tension_var":0.0,"tension_peak_beat":0.0}
    starts = arr[:,0].astype(float)
    pitches = arr[:,3]
    win = float(tpb)
    nwin = int(starts.max()/win)+2
    diss = []
    for w in range(nwin):
        mask = (starts >= w*win) & (starts < (w+1)*win)
        pcs = np.unique(pitches[mask] % 12)
        if len(pcs) < 2: 
            diss.append(0.0); continue
        tot=0.0; npair=0
        for i in range(len(pcs)):
            for j in range(i+1,len(pcs)):
                ic = min((pcs[j]-pcs[i])%12, (pcs[i]-pcs[j])%12)
                if 1<=ic<=6: tot += [1.0,0.5,0.2,0.15,0.1,0.65][ic-1]; npair+=1
        diss.append( tot/npair if npair else 0 )
    if not diss: return {"tension_mean":0.0,"tension_var":0.0,"tension_peak_beat":0.0}
    d = np.array(diss)
    peak = float(np.argmax(d) * tpb)
    return {"tension_mean":round(float(d.mean()),4), "tension_var":round(float(d.var()),4), "tension_peak_beat":round(peak,1)}

def deep_harmony(arr, tpb, base_row=None):
    f = {}
    if arr is None or len(arr) < 1 or tpb <= 0:
        return {"chord_maj":0.25,"chord_min":0.25,"func_T":0.33,"func_S":0.33,"func_D":0.34,
                "tension_mean":0.2,"voicing_density":2.5,"chord_spread":12.0}
    qh = chord_qual_hist(arr, tpb)
    for k,v in qh.items():
        f["chord_"+k] = v
    fp = functional_profile(arr, tpb)
    f.update(fp)
    ts = tension_stats(arr, tpb)
    f.update(ts)
    # voicing
    nnotes = len(arr)
    span = float(arr[:,0].max() - arr[:,0].min() + 1) or 1
    f["voicing_density"] = round(nnotes / max(span / tpb, 1), 4)
    f["chord_tone_spread"] = round(float(arr[:,3].max() - arr[:,3].min()), 1)
    if base_row is not None:
        # carry/smooth some
        if "harmonic_rhythm" in base_row:
            f["harmonic_rhythm_smooth"] = round(float(base_row["harmonic_rhythm"]), 4)
        if "key_stability" in base_row:
            f["key_stability"] = round(float(base_row.get("key_stability", 0.6)), 4)
    # secondary/borrowed rough proxies
    f["secondary_dominant_rate"] = round(qh.get("dom7",0)*0.6,4)
    f["borrowed_chord_rate"] = round( (qh.get("min",0) if "maj" in str(base_row) else qh.get("maj",0))*0.3 ,4) if base_row is not None else 0.1
    f["modal_interchange_score"] = round(min(1.0, f["borrowed_chord_rate"] + qh.get("dim",0)),4)
    return f

def process_bucket(bucket):
    npz = os.path.join(NOTESEQ, bucket + ".npz")
    meta = os.path.join(NOTESEQ, bucket + ".meta.json")
    if not (os.path.exists(npz) and os.path.exists(meta)):
        return bucket, 0
    part = os.path.join(PARTS, bucket + ".parquet")
    if os.path.exists(part) and os.environ.get("HARMONY_DEEP_FORCE") != "1":
        try:
            return bucket, len(pd.read_parquet(part, columns=["md5"]))
        except: pass
    tpbs = json.load(open(meta))
    z = np.load(npz)
    base = None
    if os.path.exists(HARM_IN):
        try:
            base = pd.read_parquet(HARM_IN)
            base = base.set_index("md5") if "md5" in base.columns else base
        except: base=None
    recs = []
    done = C.load_done_md5s(OUT)
    for md5 in list(z.files):
        if md5 in done: continue
        arr = z[md5]
        rec = {"md5": md5}
        try:
            brow = None
            if base is not None and md5 in base.index:
                brow = base.loc[md5].to_dict()
            rec.update(deep_harmony(arr, int(tpbs.get(md5,480)), brow))
        except Exception as ex:
            rec["harmony_deep_error"] = repr(ex)[:100]
            rec.update({"chord_maj":0.25,"chord_min":0.25,"func_T":0.33,"func_S":0.33,"func_D":0.34})
        recs.append(rec)
    if recs:
        os.makedirs(PARTS, exist_ok=True)
        pd.DataFrame(recs).to_parquet(os.path.join(PARTS, bucket + ".parquet"), index=False)
    return bucket, len(recs)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", type=str, default="")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()
    if args.merge_only:
        parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
        if parts:
            df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True).drop_duplicates("md5")
            C.write_parquet_atomic(df, OUT)
            print(f"[61] merged -> {OUT} ({len(df)})")
        return
    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ, "*.npz")))
    if args.buckets:
        want = set(args.buckets.split(","))
        buckets = [b for b in buckets if b in want]
    C.log(f"61_harmony_deep: {len(buckets)} buckets", "harmony_deep.log")
    from multiprocessing import Pool
    t0, done = time.time(), 0
    with Pool(args.workers) as pool:
        for i, (b, n) in enumerate(pool.imap_unordered(process_bucket, buckets), 1):
            done += n
            if i % 8 == 0 or i == len(buckets):
                C.log(f"  [{i}/{len(buckets)}] {done} {done/(time.time()-t0):.0f}/s", "harmony_deep.log")
    parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
    if parts:
        df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True).drop_duplicates("md5")
        C.write_parquet_atomic(df, OUT)
    print(f"[61] DONE -> {OUT} ({len(df) if 'df' in locals() else 0} rows)")
    if os.path.exists(OUT):
        df = pd.read_parquet(OUT)
        print("sample cols:", df.columns.tolist()[:8])
        if "func_T" in df: print("func med T/S/D:", df["func_T"].median(), df["func_S"].median(), df["func_D"].median())

if __name__ == "__main__":
    main()
