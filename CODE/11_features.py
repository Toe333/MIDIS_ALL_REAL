#!/usr/bin/env python3
"""11_features.py — Phase 2 features derived from the META_DATA pickles (NO parse).

Everything here comes from the labeled fields already stored per file, so it is
fast (minutes) and needs no MIDI parsing. The parse-only features live in
scan.parquet (10_scan.py); 15_catalog.py merges the two.

Output: _work/features_pickle.parquet (md5-keyed).
Usage:  python3 CODE/11_features.py [--limit N]
"""
import os, sys, json, argparse, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

OUT = os.path.join(C.WORK, "features_pickle.parquet")


def derive(md5, d):
    tpc = d.get("total_pitches_counts") or []
    pc = C.pc_histogram(tpc, drums=False)
    key, mode, conf = C.estimate_key(pc)
    nondrum_pitches = [p for p, _ in tpc if p < 128]
    drum_count = sum(c for p, c in tpc if p >= 128)
    nondrum_count = sum(c for p, c in tpc if p < 128)
    total = drum_count + nondrum_count

    patches = d.get("midi_patches") or []
    fam_counts = {}
    for p in patches:
        fam_counts[C.gm_family(p)] = fam_counts.get(C.gm_family(p), 0) + 1
    def fam(name): return int(fam_counts.get(name, 0))

    amd = d.get("average_median_mode_dur_ms") or [None, None, None]
    median_dur_ms = amd[1] if len(amd) > 1 else None

    nondrum_families = [f for f in fam_counts if f != "percussive"]
    return dict(
        md5=md5,
        key=key, mode=mode, key_confidence=conf,
        pitch_class_entropy=round(C.shannon_entropy(pc), 4),
        register_span_semitones=(max(nondrum_pitches) - min(nondrum_pitches))
            if nondrum_pitches else None,
        percussion_ratio=round(drum_count / total, 4) if total else 0.0,
        avg_note_length_sec=round(median_dur_ms / 1000.0, 4) if median_dur_ms else None,
        n_distinct_patches=len(set(patches)),
        instrument_family_counts=json.dumps(fam_counts),
        n_piano_tracks=fam("piano"), n_guitar_tracks=fam("guitar"),
        n_bass_tracks=fam("bass"), n_strings_tracks=fam("strings") + fam("ensemble"),
        n_brass_tracks=fam("brass"), n_reed_tracks=fam("reed"),
        n_synth_tracks=fam("synth_lead") + fam("synth_pad") + fam("synth_fx"),
        n_drum_tracks=fam("percussive"),
        has_bass=int(fam("bass") > 0), has_pad=int(fam("synth_pad") > 0),
        is_solo=int(len(set(p for p in patches)) <= 1 and len(nondrum_families) <= 1),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    rows, t0 = [], time.time()
    for md5, d in C.iter_meta_pickles():
        rows.append(derive(md5, d))
        if args.limit and len(rows) >= args.limit:
            break
        if len(rows) % 50000 == 0:
            C.log(f"  features {len(rows)} {len(rows)/(time.time()-t0):.0f}/s", "features.log")
    df = pd.DataFrame(rows)
    C.write_parquet_atomic(df, OUT)
    C.log(f"features_pickle DONE: {len(df)} rows -> {OUT}", "features.log")
    # quick sanity
    C.log(f"  key coverage: {df['key'].notna().mean():.1%}, "
          f"mode counts: {df['mode'].value_counts().to_dict()}", "features.log")
    C.progress("PHASE2pickle", f"rows={len(df)}")


if __name__ == "__main__":
    main()
