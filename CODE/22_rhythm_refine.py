#!/usr/bin/env python3
"""22_rhythm_refine.py — authoritative RHYTHM detection, recomputed from the cache.

Rhythm is the project's #1 priority, and the two hardest things to get right are
SWING and DOTTED rhythms. This reads the NOTESEQ_DATA cache built by 21_sequences.py
(no re-parse — fast + iterable) and computes a focused, high-quality rhythm block:

  SWING  — Beat-Upbeat Ratio (BUR): for each beat divided into two eighths, the ratio
           of the on-beat eighth's length to the off-beat eighth's length.
           straight ~1.0, swung ~1.5-2.0+. We report median BUR + confidence so
           "is this swung?" is a real, gradable answer.
  DOTTED — every IOI (and duration) is snapped to the nearest canonical note value in
           LOG space and sorted into three families: straight (1,1/2,1/4,1/8...),
           dotted (1.5,0.75,0.375...), triplet (1/3,2/3,4/3...). Outputs explicit
           straight/dotted/triplet ratios, plus a dotted-pair detector (adjacent IOIs
           at ~3:1, i.e. dotted-eighth+sixteenth figures).

MIDI note: ticks_per_beat (tpb) is ticks per QUARTER note, so IOI_beats = IOI_ticks/tpb
maps to note values regardless of time signature (quarter = 1.0 beat).

Outputs:  _work/rhythm_features.parquet  (md5 + the rhythm columns below)

Usage:
  python3 CODE/22_rhythm_refine.py                 # all cached buckets
  python3 CODE/22_rhythm_refine.py --buckets 00,01 # subset
  python3 CODE/22_rhythm_refine.py --workers 10
"""
import os, sys, glob, json, argparse, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "rhythm_features.parquet")

# canonical note values in beats (quarter=1), each tagged with its family.
_STRAIGHT = [4.0, 2.0, 1.0, 0.5, 0.25, 0.125, 0.0625]
_DOTTED = [3.0, 1.5, 0.75, 0.375, 0.1875]
_TRIPLET = [8/3, 4/3, 2/3, 1/3, 1/6]
_VALUES = np.array(_STRAIGHT + _DOTTED + _TRIPLET)
_FAMILY = np.array(["straight"] * len(_STRAIGHT) + ["dotted"] * len(_DOTTED) + ["triplet"] * len(_TRIPLET))
_LOGV = np.log2(_VALUES)
_FAM_IDX = {"straight": 0, "dotted": 1, "triplet": 2, "free": 3}
# a value is "recognized" if within this log2 distance of a canonical value
# (~0.18 ≈ ±13% ratio — wider than triplet/straight spacing would falsely merge).
_TOL = 0.16


def classify_values(vals_beats):
    """Return fractions [straight, dotted, triplet, free] over the given IOIs/durs."""
    counts = np.zeros(4)
    v = vals_beats[(vals_beats > 0) & np.isfinite(vals_beats)]
    if len(v) == 0:
        return counts
    lv = np.log2(v)
    # nearest canonical value in log space
    d = np.abs(lv[:, None] - _LOGV[None, :])
    j = d.argmin(axis=1)
    near = d[np.arange(len(v)), j]
    for k in range(len(v)):
        if near[k] <= _TOL:
            counts[_FAM_IDX[_FAMILY[j[k]]]] += 1
        else:
            counts[3] += 1                       # free / un-snappable
    return counts / counts.sum()


def onsets_beats(arr, tpb):
    """Collapse near-simultaneous note onsets into pulse onsets on a 1/48-beat grid.

    1/48 beat is the key resolution: it represents 16th-notes (3/48), triplets
    (16/48 = 1/3), and swung eighths (32/48 = 2/3) EXACTLY, so it merges chord
    notes without corrupting triplet/swing timing the way a 1/16 grid does."""
    starts = arr[:, 0].astype(np.float64)
    q = np.round(starts / (tpb / 48.0)).astype(np.int64)
    ob = np.unique(q) * (1.0 / 48.0)             # onset positions in beats
    return np.sort(ob)


def swing_bur(ob):
    """Beat-Upbeat Ratio swing detector from pulse-onset beat positions.

    For each integer beat that has an on-beat onset (phase<0.15) and exactly one
    'mid' onset in the SWING window (0.40<phase<0.72), the on-beat eighth length
    ~= phase_mid and the off-beat eighth length ~= (1 - phase_mid), so
    BUR = phase_mid/(1-phase_mid). The window excludes phase~0.75 so a literal
    dotted-eighth+sixteenth figure (BUR 3.0) is NOT mistaken for swing.
    """
    if len(ob) < 4:
        return np.nan, 0.0, 0, 0.0
    beat_idx = np.floor(ob + 1e-6).astype(np.int64)
    phase = ob - beat_idx
    burs = []
    n_onbeat = 0
    from collections import defaultdict
    by_beat = defaultdict(list)
    for b, p in zip(beat_idx, phase):
        by_beat[b].append(p)
    for b, ps in by_beat.items():
        ps = sorted(ps)
        has_onbeat = any(p < 0.15 for p in ps)
        if not has_onbeat:
            continue
        n_onbeat += 1
        # reject beats that are actually triplet/16th-subdivided: a true swing beat
        # has NOTHING between the downbeat and the upbeat (no onset at ~1/3 or 1/4).
        if any(0.15 < p <= 0.40 for p in ps):
            continue
        mids = [p for p in ps if 0.40 < p < 0.72]
        if len(mids) == 1:
            pm = mids[0]
            burs.append(pm / (1.0 - pm))
    if not burs or n_onbeat == 0:
        return np.nan, 0.0, n_onbeat, 0.0
    burs = np.array(burs)
    med = float(np.median(burs))
    conf = len(burs) / n_onbeat                  # fraction of beats that are eighth-divided
    eighth_subdiv = len(burs) / max(len(set(beat_idx)), 1)
    return med, round(conf, 4), len(burs), round(eighth_subdiv, 4)


def dotted_pair_ratio(ob):
    """Fraction of adjacent IOI pairs forming a ~3:1 (dotted) long-short figure."""
    if len(ob) < 3:
        return 0.0
    ioi = np.diff(ob)
    ioi = ioi[ioi > 0]
    if len(ioi) < 2:
        return 0.0
    a, b = ioi[:-1], ioi[1:]
    r = a / b
    dotted = (np.abs(np.log2(r) - np.log2(3.0)) <= 0.16)   # long:short ~ 3:1
    return round(float(dotted.mean()), 4)


def rhythm_of(arr, tpb):
    f = {}
    if arr is None or len(arr) == 0 or tpb <= 0:
        return f
    ob = onsets_beats(arr, tpb)
    if len(ob) > 1:
        ioi = np.diff(ob)
        sd = classify_values(ioi)
        f["ioi_straight_ratio"] = round(float(sd[0]), 4)
        f["ioi_dotted_ratio"] = round(float(sd[1]), 4)
        f["ioi_triplet_ratio"] = round(float(sd[2]), 4)
        f["ioi_free_ratio"] = round(float(sd[3]), 4)
    # durations -> dotted/triplet on note LENGTHS (articulated dotted figures)
    durs = arr[:, 1].astype(np.float64) / tpb
    dd = classify_values(durs)
    f["dur_straight_ratio"] = round(float(dd[0]), 4)
    f["dur_dotted_ratio"] = round(float(dd[1]), 4)
    f["dur_triplet_ratio"] = round(float(dd[2]), 4)
    f["dotted_pair_ratio"] = dotted_pair_ratio(ob)
    bur, conf, nq, eighth = swing_bur(ob)
    f["swing_bur"] = round(bur, 4) if np.isfinite(bur) else np.nan
    f["swing_confidence"] = conf
    f["swing_n_beats"] = nq
    f["eighth_subdiv_ratio"] = eighth
    f["is_swung"] = bool(np.isfinite(bur) and 1.3 < bur < 2.6 and conf > 0.3 and nq >= 8)
    f["is_triplet_feel"] = bool(f.get("ioi_triplet_ratio", 0) > 0.25)
    f["is_dotted"] = bool(f.get("ioi_dotted_ratio", 0) > 0.12 or f["dotted_pair_ratio"] > 0.1)
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
        arr = z[md5]
        rec = {"md5": md5}
        try:
            rec.update(rhythm_of(arr, int(tpbs.get(md5, 480))))
        except Exception as ex:  # noqa: BLE001
            rec["rhythm_error"] = repr(ex)[:120]
        recs.append(rec)
    df = pd.DataFrame(recs)
    os.makedirs(os.path.join(C.WORK, "rhythm_parts"), exist_ok=True)
    df.to_parquet(os.path.join(C.WORK, "rhythm_parts", bucket + ".parquet"), index=False)
    return bucket, len(recs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", type=str, default="")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()

    parts_dir = os.path.join(C.WORK, "rhythm_parts")
    if args.merge_only:
        parts = sorted(glob.glob(os.path.join(parts_dir, "*.parquet")))
        df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        C.write_parquet_atomic(df, OUT)
        print(f"[22] merged {len(parts)} buckets -> {OUT} ({len(df)} rows)")
        return

    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ, "*.npz")))
    if args.buckets:
        want = set(args.buckets.split(","))
        buckets = [b for b in buckets if b in want]
    C.log(f"22_rhythm_refine: {len(buckets)} cached buckets to process (workers={args.workers})", "rhythm.log")

    from multiprocessing import Pool
    t0, done = time.time(), 0
    with Pool(args.workers) as pool:
        for i, (b, n) in enumerate(pool.imap_unordered(process_bucket, buckets), 1):
            done += n
            if i % 16 == 0 or i == len(buckets):
                C.log(f"  [{i}/{len(buckets)}] {done} files {done/(time.time()-t0):.0f}/s", "rhythm.log")

    parts = sorted(glob.glob(os.path.join(parts_dir, "*.parquet")))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    C.write_parquet_atomic(df, OUT)
    print(f"[22] DONE -> {OUT} ({len(df)} rows, {df.shape[1]} cols)")
    if "is_swung" in df:
        print(f"[22] is_swung={int(df['is_swung'].sum())}  is_dotted={int(df['is_dotted'].sum())}  "
              f"is_triplet_feel={int(df['is_triplet_feel'].sum())}")
        print(f"[22] swing_bur median (where defined): {df['swing_bur'].median():.3f}")


if __name__ == "__main__":
    main()
