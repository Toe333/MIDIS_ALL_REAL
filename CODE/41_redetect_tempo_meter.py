#!/usr/bin/env python3
"""
41_redetect_tempo_meter.py — correct BPM + time-signature READ from the MIDI itself.

The v2 pipeline (10_scan.py:68) used `bpm = tempos[0]` — the FIRST tempo event.
That is wrong when (a) several tempo events share tick 0 (the LAST one wins in
playback) or (b) the song has a tempo ramp. This re-reads every file with symusic
(fast C++ parser) and computes the DOMINANT tempo = the BPM in effect for the most
ticks, collapsing same-tick events to last-writer-wins.

Additive & re-derivable: writes _work/tempo_meter_v2.parquet, never touches the catalog.
Columns: md5, bpm_v2, bpm_first (old behaviour, for impact diff), bpm_min, bpm_max,
         n_tempo_events, has_tempo, ts_v2, n_tsig, ts_present, end_ticks, tpq
Run:  python3 CODE/41_redetect_tempo_meter.py [--workers N] [--limit N]
"""
import argparse, pathlib, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd

ROOT  = pathlib.Path(__file__).resolve().parents[1]
MIDIS = ROOT / "MIDIs"
OUT   = ROOT / "_work" / "tempo_meter_v2.parquet"

def analyze(md5):
    import symusic
    rec = {"md5": md5, "bpm_v2": None, "bpm_first": None, "bpm_min": None,
           "bpm_max": None, "n_tempo_events": 0, "has_tempo": False,
           "ts_v2": None, "n_tsig": 0, "ts_present": False,
           "end_ticks": 0, "tpq": None, "err": None}
    try:
        s = symusic.Score(str(MIDIS / md5[:2] / f"{md5}.mid"))
    except Exception as e:
        rec["err"] = f"{type(e).__name__}"
        return rec
    rec["tpq"] = int(s.tpq)
    try:    end = int(s.end())
    except Exception: end = 0
    rec["end_ticks"] = end

    tempos = sorted(s.tempos, key=lambda t: t.time)   # time order; same-tick keeps list order
    if tempos:
        rec["has_tempo"] = True
        rec["n_tempo_events"] = len(tempos)
        rec["bpm_first"] = round(float(tempos[0].qpm), 2)
        qpms = [float(t.qpm) for t in tempos]
        rec["bpm_min"] = round(min(qpms), 2)
        rec["bpm_max"] = round(max(qpms), 2)
        # collapse same-tick -> last writer wins, then weight by ticks active
        timeline = []
        for t in tempos:
            tk = int(t.time)
            if timeline and timeline[-1][0] == tk:
                timeline[-1] = (tk, float(t.qpm))
            else:
                timeline.append((tk, float(t.qpm)))
        weights = {}
        span_end = max(end, timeline[-1][0] + 1)
        for j, (tk, qpm) in enumerate(timeline):
            nxt = timeline[j + 1][0] if j + 1 < len(timeline) else span_end
            weights[qpm] = weights.get(qpm, 0) + max(1, nxt - tk)
        rec["bpm_v2"] = round(max(weights, key=weights.get), 2)
    else:
        rec["bpm_v2"] = 120.0           # MIDI default when no tempo event present

    tsigs = sorted(s.time_signatures, key=lambda t: t.time)
    if tsigs:
        rec["ts_present"] = True
        rec["n_tsig"] = len(tsigs)
        rec["ts_v2"] = f"{tsigs[0].numerator}/{tsigs[0].denominator}"
    return rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    md5s = pd.read_parquet(ROOT / "catalog/metadata.parquet", columns=["md5"])["md5"].tolist()
    if args.limit:
        md5s = md5s[:args.limit]
    n = len(md5s)
    print(f"re-reading tempo/meter for {n:,} files with {args.workers} workers …", flush=True)

    rows = []
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for rec in ex.map(analyze, md5s, chunksize=256):
            rows.append(rec); done += 1
            if done % 20000 == 0:
                print(f"  {done:,}/{n:,}", flush=True)

    df = pd.DataFrame(rows)
    OUT.parent.mkdir(exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"\nwrote {OUT}  ({len(df):,} rows)")

    # impact report vs current catalog bpm
    cat = pd.read_parquet(ROOT / "catalog/metadata.parquet", columns=["md5", "bpm"])
    j = df.merge(cat, on="md5", how="left")
    changed = (j.bpm_v2.round(0) != j.bpm.round(0))
    big = (abs(j.bpm_v2 - j.bpm) > 5) & j.bpm.notna()
    print("\n==== IMPACT ====")
    print(f"parse errors:                 {df.err.notna().sum():,}")
    print(f"no tempo event (defaulted):   {(~df.has_tempo).sum():,}")
    print(f"bpm changed (rounded):        {changed.sum():,}  ({changed.mean()*100:.1f}%)")
    print(f"bpm changed by >5:            {big.sum():,}  ({big.mean()*100:.1f}%)")
    print(f"old bpm<40 fixed:             {((j.bpm<40)&(j.bpm_v2>=40)).sum():,}")
    print(f"multi-tempo files:            {(df.n_tempo_events>1).sum():,}")
    print(f"time-sig present in file:     {df.ts_present.sum():,}  ({df.ts_present.mean()*100:.1f}%)")
    print(f"time-sig ABSENT (no meta):    {(~df.ts_present).sum():,}")
    print("\ntop ts_v2 values in files:")
    print(df[df.ts_present].ts_v2.value_counts().head(10).to_string())

if __name__ == "__main__":
    main()
