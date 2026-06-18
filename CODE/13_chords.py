#!/usr/bin/env python3
"""13_chords.py — Phase 4 chord/harmony summary from pickles (NO parse).

Derives harmony features from ms_chords_counts already stored per file.
Output: CHORDS_DATA/chords_summary.parquet (md5-keyed, columnar — NOT per-file).
Usage:  python3 CODE/13_chords.py [--limit N]
"""
import os, sys, argparse, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

OUT_DIR = os.path.join(C.ROOT, "CHORDS_DATA")
OUT = os.path.join(OUT_DIR, "chords_summary.parquet")
PC = ["C","C#","D","Eb","E","F","F#","G","Ab","A","Bb","B"]


def summarize(md5, d):
    mcc = d.get("ms_chords_counts") or []
    # mcc = [[[pitch-classes], count], ...]; ignore the [[0,0],0] sentinel
    real = [(pcs, cnt) for pcs, cnt in mcc if isinstance(pcs, list) and len(pcs) > 1]
    n_unique = len(real)
    total_chord_events = sum(c for _, c in real)
    dur_sec = (d.get("pitches_times_sum_ms") or 0) / 1000.0
    sizes = [len(pcs) for pcs, _ in real]
    has_ext = any(s >= 4 for s in sizes)
    if n_unique == 0:
        complexity = "none"
    elif n_unique < 8:
        complexity = "low"
    elif n_unique < 25:
        complexity = "medium"
    else:
        complexity = "high"
    most_common = None
    if real:
        top = max(real, key=lambda x: x[1])[0]
        most_common = "-".join(PC[p % 12] for p in top[:4])
    return dict(
        md5=md5,
        n_unique_chords=n_unique,
        chord_density=round(total_chord_events / dur_sec, 3) if dur_sec > 0 else None,
        most_common_chord=most_common,
        has_extended_harmony=int(has_ext),
        progression_complexity=complexity,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    rows, t0 = [], time.time()
    for md5, d in C.iter_meta_pickles():
        rows.append(summarize(md5, d))
        if args.limit and len(rows) >= args.limit:
            break
        if len(rows) % 50000 == 0:
            C.log(f"  chords {len(rows)} {len(rows)/(time.time()-t0):.0f}/s", "chords.log")
    df = pd.DataFrame(rows)
    C.write_parquet_atomic(df, OUT)
    C.log(f"chords_summary DONE: {len(df)} rows -> {OUT}", "chords.log")
    C.log(f"  complexity: {df['progression_complexity'].value_counts().to_dict()}", "chords.log")
    C.progress("PHASE4", f"rows={len(df)}")


if __name__ == "__main__":
    main()
