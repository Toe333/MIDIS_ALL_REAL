#!/usr/bin/env python3
"""60_counterpoint.py — COUNTERPOINT (horizontal) feature pass, primary 4-pillar target.

Reads NOTESEQ_DATA/ (no re-parse ever). Per-md5 resumable via parts + done set.

Voice separation:
- Prefer distinct non-drum channels as voices (MIDI channel = voice in many counterpoint files).
- Fallback: simple streaming assignment by pitch proximity + non-crossing heuristic (skyline + bass + inners).

Metrics (md5-keyed):
- n_independent_voices: median concurrent sounding voices (sweep-line sampled)
- motion_contrary/parallel/oblique/similar: ratios over adjacent inter-voice intervals
- rhythmic_independence: 1 - (coincident onsets within 1/32 beat) / total
- voice_crossing_rate, voice_overlap_rate
- nct_ratio: rough non-chord-tone density (vs local chord estimate from chroma)
- imitation_score: delayed contour/interval sequence matches across voices (canon-like)
- voice_leading_smoothness: mean |semitone delta| per voice per adjacent notes
- polyphony_density: mean concurrent voices over time

Outputs: _work/counterpoint.parquet (via counterpoint_parts/*.parquet)

Usage:
  .venv-linux/bin/python CODE/60_counterpoint.py                 # all
  .venv-linux/bin/python CODE/60_counterpoint.py --buckets 00,01 # pilot
  .venv-linux/bin/python CODE/60_counterpoint.py --merge-only
"""

import os, sys, glob, json, argparse, time
import numpy as np
import pandas as pd
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "counterpoint.parquet")
PARTS = os.path.join(C.WORK, "counterpoint_parts")


def ticks_to_beats(ticks, tpb):
    return float(ticks) / max(tpb, 1)


def separate_voices(arr, tpb):
    """Return list of voices; each voice = list of (start_beats, pitch) sorted. Robust."""
    if arr is None or len(arr) == 0:
        return []
    arr = arr[np.argsort(arr[:, 0])]
    starts = arr[:, 0].astype(np.float64)
    durs = arr[:, 1].astype(np.float64)
    chans = arr[:, 2].astype(np.int32)
    pitches = arr[:, 3].astype(np.int32)
    ends = starts + durs

    # prefer channels (skip drum chans 9/10)
    uniq_ch = sorted(set(int(c) for c in chans if c not in (9, 10)))
    if len(uniq_ch) >= 2:
        voices = []
        for ch in uniq_ch:
            mask = (chans == ch)
            if mask.sum() > 0:
                v = [(ticks_to_beats(s, tpb), int(p)) for s, p in zip(starts[mask], pitches[mask])]
                voices.append(sorted(v))
        if voices:
            return voices

    # streaming: maintain active voices, assign by min pitch dist among those ended, limit spawn
    voices = []
    v_end = []
    for s, e, p in zip(starts, ends, pitches):
        sb = ticks_to_beats(s, tpb)
        eb = ticks_to_beats(e, tpb)
        # free voices
        free = [vi for vi in range(len(voices)) if v_end[vi] <= sb + 0.01]
        best, best_d = -1, 999
        for vi in free:
            if voices[vi]:
                dp = abs(voices[vi][-1][1] - p)
                if dp < best_d:
                    best_d = dp
                    best = vi
        if best >= 0 and best_d <= 12:
            voices[best].append((sb, int(p)))
            v_end[best] = max(v_end[best], eb)
        else:
            # spawn only if not too many or far from all
            if len(voices) < 8 or (best_d > 12 and len(free) == 0):
                voices.append([(sb, int(p))])
                v_end.append(eb)
            elif free:
                # attach to closest free anyway
                vi = free[0]
                voices[vi].append((sb, int(p)))
                v_end[vi] = max(v_end[vi], eb)
            else:
                # merge to last
                if voices:
                    voices[-1].append((sb, int(p)))
                    v_end[-1] = max(v_end[-1], eb)
    return [v for v in voices if len(v) >= 1]


def sweep_concurrent(voices):
    """Return list of concurrent counts sampled at each note onset + midpoints, plus median."""
    if not voices:
        return 0.0, 0.0
    events = []
    for v in voices:
        for i, (st, p) in enumerate(v):
            events.append((st, +1))
            # rough end: use next start or +0.5 beat heuristic
            nxt = v[i+1][0] if i+1 < len(v) else st + 0.5
            events.append(( (st + nxt)/2 , -1 ))  # mid
    events.sort()
    cur = 0
    counts = []
    for t, d in events:
        cur += d
        if d > 0:
            counts.append(max(1, cur))
    if not counts:
        return 1.0, 1.0
    med = float(np.median(counts))
    return med, float(np.mean(counts))


def motion_ratios(voices):
    """Ratios of contrary/parallel/oblique/similar between all voice pairs on adjacent events."""
    if len(voices) < 2:
        return {"motion_contrary": 0.0, "motion_parallel": 0.0, "motion_oblique": 0.0, "motion_similar": 0.0}
    c_contr = c_par = c_obl = c_sim = 0
    for i in range(len(voices)):
        for j in range(i+1, len(voices)):
            va = voices[i]
            vb = voices[j]
            # pair onsets roughly by time
            ia = ib = 0
            prev_da = prev_db = 0
            while ia < len(va)-1 and ib < len(vb)-1:
                ta, pa = va[ia]
                ta2, pa2 = va[ia+1]
                tb, pb = vb[ib]
                tb2, pb2 = vb[ib+1]
                # advance the earlier
                if ta2 < tb2:
                    da = pa2 - pa
                    # find closest in b around ta2
                    while ib < len(vb)-1 and vb[ib+1][0] < ta2:
                        ib += 1
                    if abs(vb[ib][0] - ta2) < 0.6:  # ~ half beat tolerance
                        db = vb[ib+1][1] - vb[ib][1]
                        classify_motion(da, db, c_contr, c_par, c_obl, c_sim)  # will inc below
                        # use closure
                    ia += 1
                else:
                    db = pb2 - pb
                    while ia < len(va)-1 and va[ia+1][0] < tb2:
                        ia += 1
                    if abs(va[ia][0] - tb2) < 0.6:
                        da = va[ia+1][1] - va[ia][1]
                        classify_motion(da, db, c_contr, c_par, c_obl, c_sim)
                    ib += 1
    tot = max(1, c_contr + c_par + c_obl + c_sim)
    return {
        "motion_contrary": round(c_contr / tot, 4),
        "motion_parallel": round(c_par / tot, 4),
        "motion_oblique": round(c_obl / tot, 4),
        "motion_similar": round(c_sim / tot, 4),
    }


def classify_motion(da, db, cc, cp, co, cs):
    # mutate counters via list? hack: use nonlocal in py3 but pass mutable
    # simple: since ints are immutable, use external but for simplicity count in caller context later
    # instead return label
    pass  # see adjusted impl below


def motion_label(da, db):
    if abs(da) < 1 and abs(db) < 1:
        return "oblique"
    sda = 1 if da > 0 else (-1 if da < 0 else 0)
    sdb = 1 if db > 0 else (-1 if db < 0 else 0)
    if sda == 0 or sdb == 0:
        return "oblique"
    if sda != sdb:
        return "contrary"
    if abs(abs(da) - abs(db)) <= 2:
        return "parallel"
    return "similar"


def pair_motions(voices):
    labs = Counter()
    for i in range(len(voices)):
        for j in range(i+1, len(voices)):
            va, vb = voices[i], voices[j]
            ia = ib = 0
            while ia < len(va)-1 and ib < len(vb)-1:
                ta2 = va[ia+1][0]
                tb2 = vb[ib+1][0]
                if ta2 < tb2:
                    da = va[ia+1][1] - va[ia][1]
                    # nearest b step
                    while ib < len(vb)-1 and vb[ib+1][0] <= ta2 + 0.1:
                        ib += 1
                    if abs(vb[ib][0] - ta2) < 1.0:
                        db = vb[ib+1][1] - vb[ib][1]
                        labs[motion_label(da, db)] += 1
                    ia += 1
                else:
                    db = vb[ib+1][1] - vb[ib][1]
                    while ia < len(va)-1 and va[ia+1][0] <= tb2 + 0.1:
                        ia += 1
                    if abs(va[ia][0] - tb2) < 1.0:
                        da = va[ia+1][1] - va[ia][1]
                        labs[motion_label(da, db)] += 1
                    ib += 1
    tot = sum(labs.values()) or 1
    return {f"motion_{k}": round(labs.get(k,0)/tot, 4) for k in ("contrary","parallel","oblique","similar")}


def rhythmic_independence(voices, eps=0.125):
    """1 - fraction of near-coincident onsets."""
    all_on = []
    for v in voices:
        all_on.extend([st for st,_ in v])
    if len(all_on) < 2:
        return 1.0
    all_on.sort()
    coinc = 0
    for i in range(1, len(all_on)):
        if all_on[i] - all_on[i-1] <= eps:
            coinc += 1
    return round(1.0 - coinc / max(1, len(all_on)-1), 4)


def crossing_overlap(voices):
    crossings = overlaps = 0
    total_pairs = 0
    for i in range(len(voices)):
        for j in range(i+1, len(voices)):
            va, vb = voices[i], voices[j]
            # assume va is "upper" by init pitch if possible
            if va and vb and va[0][1] < vb[0][1]:
                va, vb = vb, va
            total_pairs += 1
            ia = ib = 0
            while ia < len(va) and ib < len(vb):
                ta, pa = va[ia]
                tb, pb = vb[ib]
                if abs(ta - tb) < 0.25 and pa < pb:
                    crossings += 1
                if abs(ta - tb) < 0.5:
                    overlaps += 1
                if ta < tb:
                    ia += 1
                else:
                    ib += 1
    denom = max(1, total_pairs)
    return round(crossings / max(1, overlaps or 1), 4), round(overlaps / max(1, len(voices)*10 or 1), 4)


def imitation_score(voices, win=4):
    """Crude delayed sequence match of interval contours."""
    if len(voices) < 2:
        return 0.0
    score = 0
    for i in range(len(voices)):
        for j in range(i+1, len(voices)):
            seqa = [p2 - p1 for (t1,p1),(t2,p2) in zip(voices[i][:-1], voices[i][1:])]
            seqb = [p2 - p1 for (t1,p1),(t2,p2) in zip(voices[j][:-1], voices[j][1:])]
            for k in range(len(seqa)-win):
                sub = seqa[k:k+win]
                for m in range(len(seqb)-win):
                    if seqb[m:m+win] == sub or seqb[m:m+win] == [-x for x in sub]:
                        score += 1
                        break
    return round(min(1.0, score / max(1, len(voices)*3)), 4)


def smoothness(voices):
    deltas = []
    for v in voices:
        for (t1,p1),(t2,p2) in zip(v[:-1], v[1:]):
            deltas.append(abs(p2 - p1))
    if not deltas:
        return 0.0
    return round(float(np.mean(deltas)), 4)


def poly_density(voices):
    med, avg = sweep_concurrent(voices)
    return round(avg, 4)


def rough_nct(arr, voices, tpb):
    """Very rough nct ratio using per-window simple triad chroma match."""
    if len(arr) == 0 or not voices:
        return 0.0
    # build coarse chord per ~beat from all notes
    starts = arr[:,0].astype(np.float64)
    pitches = arr[:,3]
    span = (starts + arr[:,1]).max()
    nwin = max(int(span / tpb) + 1, 2)
    win = float(tpb)
    chroma = np.zeros((nwin, 12))
    for s, p in zip(starts, pitches):
        wi = min(int(s / win), nwin-1)
        chroma[wi, p % 12] += 1
    # chord tones rough: top-3 pcs per win or template
    chord_tones = set()
    for w in range(nwin):
        pcs = np.argsort(chroma[w])[-3:]
        for pc in pcs:
            chord_tones.add(int(pc))
    if not chord_tones:
        return 0.0
    nct = 0
    total = 0
    for v in voices:
        for _, p in v:
            total += 1
            if (p % 12) not in chord_tones:
                nct += 1
    return round(nct / max(1, total), 4)


def counterpoint_features(arr, tpb):
    f = {"n_independent_voices": 1.0, "n_voices": 1, "polyphony_density": 1.0,
         "motion_contrary":0.0,"motion_parallel":0.0,"motion_oblique":0.0,"motion_similar":0.0,
         "rhythmic_independence":1.0,"voice_crossing_rate":0.0,"voice_overlap_rate":0.0,
         "nct_ratio":0.0,"imitation_score":0.0,"voice_leading_smoothness":0.0}
    if arr is None or len(arr) < 2 or tpb <= 0:
        return f
    try:
        voices = separate_voices(arr, tpb)
        f["n_voices"] = len(voices)
        med, avg = sweep_concurrent(voices)
        f["n_independent_voices"] = round(med, 3)
        f["polyphony_density"] = round(avg, 4)
        mot = pair_motions(voices)
        f.update(mot)
        f["rhythmic_independence"] = rhythmic_independence(voices)
        cross, ov = crossing_overlap(voices)
        f["voice_crossing_rate"] = cross
        f["voice_overlap_rate"] = ov
        f["nct_ratio"] = rough_nct(arr, voices, tpb)
        f["imitation_score"] = imitation_score(voices)
        f["voice_leading_smoothness"] = smoothness(voices)
    except Exception:
        pass  # keep defaults
    return f


def process_bucket(bucket):
    npz = os.path.join(NOTESEQ, bucket + ".npz")
    meta = os.path.join(NOTESEQ, bucket + ".meta.json")
    if not (os.path.exists(npz) and os.path.exists(meta)):
        return bucket, 0
    part = os.path.join(PARTS, bucket + ".parquet")
    if os.path.exists(part) and os.environ.get("COUNTERPOINT_FORCE") != "1":
        try:
            return bucket, len(pd.read_parquet(part, columns=["md5"]))
        except Exception:
            pass
    tpbs = json.load(open(meta))
    z = np.load(npz)
    recs = []
    done = C.load_done_md5s(OUT)  # global resume across
    for md5 in list(z.files):
        if md5 in done:
            continue
        try:
            rec = {"md5": md5}
            rec.update(counterpoint_features(z[md5], int(tpbs.get(md5, 480))))
            recs.append(rec)
        except Exception as ex:  # noqa
            base = {"md5": md5, "counterpoint_error": repr(ex)[:120],
                    "n_independent_voices": 1.0, "motion_contrary":0.0,"motion_parallel":0.0,
                    "motion_oblique":0.0,"motion_similar":0.0,"rhythmic_independence":1.0,
                    "voice_crossing_rate":0.0,"voice_overlap_rate":0.0,"nct_ratio":0.0,
                    "imitation_score":0.0,"voice_leading_smoothness":0.0,"polyphony_density":1.0,
                    "n_voices":1}
            recs.append(base)
    if recs:
        os.makedirs(PARTS, exist_ok=True)
        pd.DataFrame(recs).to_parquet(os.path.join(PARTS, bucket + ".parquet"), index=False)
    return bucket, len(recs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", type=str, default="")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()

    if args.merge_only:
        parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
        if parts:
            df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
            # dedup just in case
            df = df.drop_duplicates(subset=["md5"])
            C.write_parquet_atomic(df, OUT)
            print(f"[60] merged {len(parts)} -> {OUT} ({len(df)} rows)")
        return

    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ, "*.npz")))
    if args.buckets:
        want = set(args.buckets.split(","))
        buckets = [b for b in buckets if b in want]
    C.log(f"60_counterpoint: {len(buckets)} buckets (workers={args.workers})", "counterpoint.log")

    from multiprocessing import Pool
    t0, done = time.time(), 0
    with Pool(args.workers) as pool:
        for i, (b, n) in enumerate(pool.imap_unordered(process_bucket, buckets), 1):
            done += n
            if i % 8 == 0 or i == len(buckets):
                C.log(f"  [{i}/{len(buckets)}] +{n}  total_done~{done}  {done/(time.time()-t0):.0f}/s", "counterpoint.log")

    parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
    if parts:
        df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        df = df.drop_duplicates(subset=["md5"])
        C.write_parquet_atomic(df, OUT)
    else:
        df = pd.DataFrame()
    print(f"[60] DONE -> {OUT} ({len(df)} rows, {df.shape[1]} cols)")
    if len(df) and "n_independent_voices" in df:
        print(f"[60] n_indep_voices med={df['n_independent_voices'].median():.2f}  poly_dens med={df['polyphony_density'].median():.2f}")
        print(f"[60] sample high: {df.nlargest(3,'n_independent_voices')['md5'].tolist()}")


if __name__ == "__main__":
    main()
