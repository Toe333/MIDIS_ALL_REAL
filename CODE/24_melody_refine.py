#!/usr/bin/env python3
"""24_melody_refine.py — deep MELODY features, recomputed from the NOTESEQ_DATA cache.

Melody is one of the three first-class pillars (rhythm #1, then melody + harmony).
This reads the note-sequence cache (no re-parse) and, for the extracted melody line,
computes contour, register, articulation of intervals, phrase structure, the melody's
OWN rhythm (note-values), and motif repetition.

Melody extraction (same lead-score as 21): among non-drum channels with >=8 notes,
pick the one maximizing  (mean_pitch/127) * monophonicity * log(1+n_notes)  — high,
mostly-monophonic, well-populated voice.

Outputs: _work/melody_features.parquet

Usage:
  python3 CODE/24_melody_refine.py                 # all cached buckets
  python3 CODE/24_melody_refine.py --buckets 00,01
  python3 CODE/24_melody_refine.py --merge-only
"""
import os, sys, glob, json, argparse, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C
from importlib import util as _u
# reuse 22's value classifier for the melody's own rhythm
_spec = _u.spec_from_file_location("r22", os.path.join(os.path.dirname(__file__), "22_rhythm_refine.py"))
_r22 = _u.module_from_spec(_spec); _spec.loader.exec_module(_r22)

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "melody_features.parquet")
PARTS = os.path.join(C.WORK, "melody_parts")

MAJOR_SCALE = {0, 2, 4, 5, 7, 9, 11}


def pick_melody(arr):
    chans, pitches, starts = arr[:, 2], arr[:, 3], arr[:, 0]
    best, best_score = -1, -1.0
    for ch in np.unique(chans):
        if ch == 9:
            continue
        m = chans == ch
        p = pitches[m]
        if len(p) < 8:
            continue
        mono = len(np.unique(starts[m])) / len(p)
        score = (p.mean() / 127.0) * mono * np.log1p(len(p))
        if score > best_score:
            best, best_score = int(ch), float(score)
    return best


def melody_features(arr, tpb):
    f = {"has_melody": False, "melody_channel": -1, "melody_n_notes": 0}
    if arr is None or len(arr) == 0 or tpb <= 0:
        return f
    ch = pick_melody(arr)
    if ch < 0:
        return f
    m = arr[:, 2] == ch
    sub = arr[m]
    order = np.argsort(sub[:, 0])
    sub = sub[order]
    p = sub[:, 3].astype(np.int64)
    onset_b = sub[:, 0].astype(np.float64) / tpb
    f["has_melody"] = True
    f["melody_channel"] = ch
    f["melody_n_notes"] = int(len(p))
    f["mel_pitch_mean"] = round(float(p.mean()), 2)
    f["mel_range"] = int(p.max() - p.min())
    # pitch-class entropy of the melody
    pc = np.bincount(p % 12, minlength=12).astype(float)
    pc /= pc.sum()
    f["mel_pc_entropy"] = round(float(-(pc[pc > 0] * np.log2(pc[pc > 0])).sum()), 4)

    iv = np.diff(p)
    if len(iv):
        a = np.abs(iv)
        f["mel_stepwise_ratio"] = round(float((a <= 2).mean()), 4)
        f["mel_leap_ratio"] = round(float((a >= 5).mean()), 4)
        f["mel_repeat_ratio"] = round(float((iv == 0).mean()), 4)
        f["mel_interval_mean_abs"] = round(float(a.mean()), 3)
        f["mel_up_ratio"] = round(float((iv > 0).mean()), 4)
        # contour reversals (zigzag vs smooth arch): sign changes per interval
        sgn = np.sign(iv[iv != 0])
        f["mel_direction_changes"] = round(float((np.diff(sgn) != 0).mean()), 4) if len(sgn) > 1 else 0.0
        # chromaticism: fraction of melody PCs outside the major scale of the modal root
        root = int(np.argmax(np.bincount(p % 12, minlength=12)))
        outside = [(int(x) - root) % 12 not in MAJOR_SCALE for x in p]
        f["mel_chromaticism"] = round(float(np.mean(outside)), 4)

    # melody's OWN rhythm (note-values of the melodic line) -> ties melody<->rhythm
    if len(onset_b) > 1:
        ob = np.sort(np.unique(np.round(onset_b * 48).astype(np.int64))) / 48.0
        ioi = np.diff(ob)
        sd = _r22.classify_values(ioi)
        f["mel_rhythm_straight"] = round(float(sd[0]), 4)
        f["mel_rhythm_dotted"] = round(float(sd[1]), 4)
        f["mel_rhythm_triplet"] = round(float(sd[2]), 4)

        # phrase segmentation: a gap (IOI) >= 2 beats starts a new phrase
        gaps = np.where(ioi >= 2.0)[0]
        n_phrases = len(gaps) + 1
        f["mel_n_phrases"] = int(n_phrases)
        f["mel_mean_phrase_notes"] = round(len(p) / n_phrases, 2)

    # motif repetition: fraction of length-4 interval n-grams that recur
    if len(iv) >= 8:
        grams = [tuple(iv[i:i + 4].tolist()) for i in range(len(iv) - 3)]
        from collections import Counter
        cnt = Counter(grams)
        repeated = sum(c for c in cnt.values() if c > 1)
        f["mel_motif_repeat"] = round(repeated / len(grams), 4)
    return f


def process_bucket(bucket):
    npz = os.path.join(NOTESEQ, bucket + ".npz")
    meta = os.path.join(NOTESEQ, bucket + ".meta.json")
    if not (os.path.exists(npz) and os.path.exists(meta)):
        return bucket, 0
    tpbs = json.load(open(meta))
    z = np.load(npz)
    recs = []
    for md5 in z.files:
        rec = {"md5": md5}
        try:
            rec.update(melody_features(z[md5], int(tpbs.get(md5, 480))))
        except Exception as ex:  # noqa: BLE001
            rec["melody_error"] = repr(ex)[:120]
        recs.append(rec)
    os.makedirs(PARTS, exist_ok=True)
    pd.DataFrame(recs).to_parquet(os.path.join(PARTS, bucket + ".parquet"), index=False)
    return bucket, len(recs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", type=str, default="")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()
    if args.merge_only:
        parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
        df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        C.write_parquet_atomic(df, OUT)
        print(f"[24] merged {len(parts)} -> {OUT} ({len(df)} rows)"); return

    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ, "*.npz")))
    if args.buckets:
        want = set(args.buckets.split(","))
        buckets = [b for b in buckets if b in want]
    C.log(f"24_melody_refine: {len(buckets)} buckets (workers={args.workers})", "melody.log")
    from multiprocessing import Pool
    t0, done = time.time(), 0
    with Pool(args.workers) as pool:
        for i, (b, n) in enumerate(pool.imap_unordered(process_bucket, buckets), 1):
            done += n
            if i % 16 == 0 or i == len(buckets):
                C.log(f"  [{i}/{len(buckets)}] {done} files {done/(time.time()-t0):.0f}/s", "melody.log")
    parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    C.write_parquet_atomic(df, OUT)
    print(f"[24] DONE -> {OUT} ({len(df)} rows, {df.shape[1]} cols)")
    if "has_melody" in df:
        print(f"[24] has_melody={int(df['has_melody'].sum())}  "
              f"mean stepwise_ratio={df['mel_stepwise_ratio'].mean():.3f}  "
              f"mean motif_repeat={df['mel_motif_repeat'].mean():.3f}")


if __name__ == "__main__":
    main()
