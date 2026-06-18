#!/usr/bin/env python3
"""04_search.py — similarity search over the merged corpus.

Reproduces the Los Angeles MIDI Dataset 'same_pitches_ratio' signature match
(master_midi_dataset_search_and_filter.py) over our META_DATA chunks. Give it
a query MIDI (or an md5 already in the store) and it ranks nearest neighbors
across the whole deduped corpus, printing md5, score, and original provenance.

Usage:
  python3 04_search.py --out-root <R> --query /path/to/song.mid --top 10
  python3 04_search.py --out-root <R> --md5 <md5> --top 10
"""
import os, sys, glob, pickle, argparse, copy
from collections import Counter

sys.path.insert(0, "/home/t/datasets/LAMD/CODE")
import TMIDIX  # noqa: E402


def query_pitches(midi_path, transpose=True):
    score = TMIDIX.midi2score(open(midi_path, "rb").read())
    events = []
    for ti, s in enumerate(score):
        if ti > 0:
            s.sort(key=lambda x: x[1]); events.extend(s)
    events.sort(key=lambda x: x[1])
    mult = []
    rng = range(-6, 6) if transpose else range(0, 1)
    for i in rng:
        em = []
        for e in events:
            if e[0] == "note":
                ev = copy.deepcopy(e)
                ev[4] = (e[4] % 128) + 128 if e[3] == 9 else (e[4] % 128) + i
                em.append(ev)
        pc = [[y[0], y[1]] for y in Counter([y[4] for y in em]).most_common()]
        pc.sort(key=lambda x: x[0], reverse=True)
        mult.append(pc)
    return mult


def trimmed(pc, cutoff):
    pc = sorted(pc, reverse=True, key=lambda x: x[1])
    if not pc:
        return []
    mx = pc[0][1]
    return [y for y in pc if y[1] >= mx * cutoff]


def load_meta(out_root):
    for fp in sorted(glob.glob(os.path.join(out_root, "META_DATA", "META_DATA_*.pickle"))):
        with open(fp, "rb") as fh:
            for entry in pickle.load(fh):
                # entry = [md5, data]; data[10] == ['total_pitches_counts', counts]
                try:
                    yield entry[0], entry[1][10][1]
                except Exception:
                    continue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--query", help="path to a query MIDI")
    ap.add_argument("--md5", help="md5 already in the store to use as query")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--cutoff", type=float, default=0.0,
                    help="pitch-count cutoff ratio (LAMD pitches_counts_cutoff_threshold_ratio)")
    ap.add_argument("--no-transpose", action="store_true")
    args = ap.parse_args()

    qpath = args.query
    if not qpath and args.md5:
        qpath = os.path.join(args.out_root, "MIDIs", args.md5[:2], args.md5 + ".mid")
    if not qpath or not os.path.exists(qpath):
        sys.exit("Provide --query <path> or --md5 <md5 in store>")

    mult = query_pitches(qpath, transpose=not args.no_transpose)
    trimmed_q = [trimmed(m, args.cutoff) for m in mult]

    results = []
    for md5, counts in load_meta(args.out_root):
        tp = trimmed(counts, args.cutoff)
        if not tp:
            continue
        tp_set = set(t[0] for t in tp)
        best = 0.0
        for tq in trimmed_q:
            if not tq:
                continue
            tq_set = set(t[0] for t in tq)
            same = tp_set & tq_set
            ns = len(same)
            if ns == len(tq):
                ratio = ns / len(tp) if tp else 0
            else:
                ratio = ns / max(len(tp), len(tq))
            best = max(best, ratio)
        results.append((best, md5))

    results.sort(reverse=True)
    # load manifest for provenance
    import pandas as pd
    man = pd.read_parquet(os.path.join(args.out_root, "catalog", "master_manifest.parquet")).set_index("md5")
    print(f"\nTop {args.top} matches for {os.path.basename(qpath)}:\n" + "-" * 70)
    shown = 0
    for score, md5 in results:
        if args.md5 and md5 == args.md5:
            continue  # skip self
        orig = man.loc[md5, "original_paths"][0] if md5 in man.index else "?"
        print(f"{score:.3f}  {md5}  <- {orig}")
        shown += 1
        if shown >= args.top:
            break


if __name__ == "__main__":
    main()
