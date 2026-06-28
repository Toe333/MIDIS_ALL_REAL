#!/usr/bin/env python3
"""62_melody_deep.py — deepen MELODY pillar (contour, motif, expectancy).

From NOTESEQ + _work/melody_features.parquet.
Resumable _work/melody_deep.parquet + parts.

Metrics:
- contour (arch/ramp/wave/static) class + interval ngram vocab size
- motif_repetition, self_similarity, phrase_count/len
- call_response_score, sequence_rate
- melodic_complexity (interval entropy), predictability (simple markov surprise IDyOM-lite)
- range_semitones, chromaticism, leap_vs_step_ratio

Pilot/full via --buckets.
"""

import os, sys, glob, json, argparse, time, math
import numpy as np
import pandas as pd
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "melody_deep.parquet")
PARTS = os.path.join(C.WORK, "melody_deep_parts")
MEL_IN = os.path.join(C.WORK, "melody_features.parquet")

def extract_melody(arr):
    # heuristic: highest chan non-drum or top line
    if len(arr)==0: return []
    arr = arr[arr[:,2] != 9]
    if len(arr)==0: return []
    # take channel with most notes or highest avg pitch
    by_ch = {}
    for r in arr:
        ch = int(r[2])
        by_ch.setdefault(ch, []).append(r)
    best_ch = max(by_ch, key=lambda c: (len(by_ch[c]), np.mean([x[3] for x in by_ch[c]])) )
    mel = sorted(by_ch[best_ch], key=lambda r: r[0])
    return [(float(r[0]), int(r[3]), float(r[1])) for r in mel]  # start, pitch, dur

def contour_class(notes):
    if len(notes) < 3: return "static"
    ps = [p for _,p,_ in notes]
    deltas = np.diff(ps)
    up = (deltas > 0).sum()
    dn = (deltas < 0).sum()
    if up > 1.5*dn: return "ramp"
    if dn > 1.5*up: return "ramp_down"
    if up > 0 and dn > 0: return "wave"
    return "arch" if abs(ps[-1]-ps[0]) < 3 else "static"

def interval_vocab(notes):
    if len(notes)<2: return 0
    ivs = [abs(p2-p1) for (_,p1,_),(_,p2,_) in zip(notes, notes[1:])]
    return len(set(ivs))

def phrase_stats(notes, gap_beat=1.5):
    if not notes: return 1, 4.0
    phrases = 1
    lens = []
    cur = 1
    for i in range(1, len(notes)):
        gap = (notes[i][0] - (notes[i-1][0] + notes[i-1][2])) / 480.0  # rough ticks->beat
        if gap > gap_beat:
            phrases += 1
            lens.append(cur)
            cur=1
        else:
            cur +=1
    lens.append(cur)
    return phrases, float(np.mean(lens)) if lens else 4.0

def call_response(notes):
    if len(notes) < 8: return 0.0
    # simple: second half mirrors first half contour sign
    ps = [p for _,p,_ in notes]
    mid = len(ps)//2
    d1 = np.sign(np.diff(ps[:mid+1]))
    d2 = np.sign(np.diff(ps[mid:]))
    if len(d2)==0: return 0.0
    match = np.mean(d1[:len(d2)] == d2[:len(d1)])
    return round(float(match),4)

def sequence_rate(notes):
    if len(notes)<6: return 0.0
    ps = [p for _,p,_ in notes]
    reps = 0
    for w in [3,4]:
        for i in range(len(ps)-2*w):
            if ps[i:i+w] == [x+ps[i+w]-ps[i] for x in ps[i+w:i+2*w]]:
                reps +=1
    return round(min(1.0, reps / max(1,len(ps)//3)),4)

def complexity_predict(notes):
    if len(notes)<4: return 0.5, 0.5
    iv = [p2-p1 for (_,p1,_),(_,p2,_) in zip(notes,notes[1:])]
    # entropy
    c = Counter(iv)
    tot = sum(c.values())
    ent = -sum( (v/tot) * math.log2(v/tot) for v in c.values() if v) / max(1,len(c)) if tot else 0
    # markov surprise (order1)
    trans = defaultdict(Counter)
    for a,b in zip(iv, iv[1:]):
        trans[a][b] +=1
    surp = []
    for a,b in zip(iv, iv[1:]):
        row = trans[a]
        s = sum(row.values())
        p = row[b]/s if s else 1e-6
        surp.append( -math.log2(p) )
    pred = 1.0 / (1 + np.mean(surp)) if surp else 0.5
    return round(ent,4), round(pred,4)

def range_chrom_leap(notes):
    if len(notes)<2: return 0,0,0.5
    ps = [p for _,p,_ in notes]
    rng = max(ps)-min(ps)
    chrom = sum(1 for a,b in zip(ps,ps[1:]) if abs(b-a)==1 ) / max(1,len(ps)-1)
    leaps = sum(1 for a,b in zip(ps,ps[1:]) if abs(b-a) >= 5 ) / max(1,len(ps)-1)
    return int(rng), round(chrom,4), round(leaps,4)

def melody_deep(arr, tpb, base=None):
    f = {"contour":"static", "interval_vocab":0, "phrase_count":1, "phrase_len_avg":4.0,
         "call_response":0.0, "sequence_rate":0.0, "mel_complexity":0.5, "mel_predict":0.5,
         "range_semitones":12, "chromaticism":0.1, "leap_step":0.5}
    notes = extract_melody(arr)
    if len(notes) < 2:
        return f
    f["contour"] = contour_class(notes)
    f["interval_vocab"] = interval_vocab(notes)
    pc, pl = phrase_stats(notes)
    f["phrase_count"] = pc
    f["phrase_len_avg"] = round(pl,2)
    f["call_response"] = call_response(notes)
    f["sequence_rate"] = sequence_rate(notes)
    ent, pred = complexity_predict(notes)
    f["mel_complexity"] = ent
    f["mel_predict"] = pred
    rng, chr, lvs = range_chrom_leap(notes)
    f["range_semitones"] = rng
    f["chromaticism"] = chr
    f["leap_step"] = lvs
    return f

def process_bucket(bucket):
    npz = os.path.join(NOTESEQ, bucket + ".npz")
    meta = os.path.join(NOTESEQ, bucket + ".meta.json")
    if not (os.path.exists(npz) and os.path.exists(meta)): return bucket,0
    partp = os.path.join(PARTS, bucket+".parquet")
    if os.path.exists(partp) and os.environ.get("MELODY_DEEP_FORCE") != "1":
        try: return bucket, len(pd.read_parquet(partp, columns=["md5"]))
        except: pass
    tpbs = json.load(open(meta))
    z = np.load(npz)
    base = None
    if os.path.exists(MEL_IN):
        try:
            bdf = pd.read_parquet(MEL_IN)
            if "md5" in bdf: base = bdf.set_index("md5")
        except: pass
    recs = []
    done = C.load_done_md5s(OUT)
    for md5 in list(z.files):
        if md5 in done: continue
        rec={"md5":md5}
        try:
            rec.update(melody_deep(z[md5], int(tpbs.get(md5,480)), base.loc[md5] if base is not None and md5 in base.index else None))
        except Exception as ex:
            rec["melody_deep_error"] = repr(ex)[:80]
        recs.append(rec)
    if recs:
        os.makedirs(PARTS, exist_ok=True)
        pd.DataFrame(recs).to_parquet(os.path.join(PARTS, bucket+".parquet"), index=False)
    return bucket, len(recs)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--buckets", type=str, default="")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--merge-only", action="store_true")
    args=ap.parse_args()
    if args.merge_only:
        ps = sorted(glob.glob(os.path.join(PARTS,"*.parquet")))
        if ps:
            df=pd.concat([pd.read_parquet(p) for p in ps], ignore_index=True).drop_duplicates("md5")
            C.write_parquet_atomic(df, OUT)
            print(f"[62] merged {len(ps)}")
        return
    bks = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ,"*.npz")))
    if args.buckets:
        w = set(args.buckets.split(","))
        bks = [b for b in bks if b in w]
    C.log(f"62_melody_deep {len(bks)}", "melody_deep.log")
    from multiprocessing import Pool
    t0,done=time.time(),0
    with Pool(args.workers) as pool:
        for i,(b,n) in enumerate(pool.imap_unordered(process_bucket, bks),1):
            done +=n
            if i%8==0 or i==len(bks): C.log(f"  {i}/{len(bks)} +{done}", "melody_deep.log")
    ps = sorted(glob.glob(os.path.join(PARTS,"*.parquet")))
    if ps:
        df = pd.concat([pd.read_parquet(p) for p in ps], ignore_index=True).drop_duplicates("md5")
        C.write_parquet_atomic(df, OUT)
    print(f"[62] DONE {OUT} rows={len(df) if 'df' in locals() else 0}")

if __name__=="__main__": main()
