#!/usr/bin/env python3
"""10_scan.py — Phase 1 + parse-only features. The ONE TMIDIX parse pass.

Walks every file in MIDIs/, parses once with TMIDIX, and emits both integrity
flags AND the handful of features that need per-event data (everything else is
derived from the pickles in 11_features.py — no second parse).

Resumable: results stream to _work/scan.parquet keyed by md5; re-running skips
md5s already present. Safe: NEVER moves files unless you pass --apply, and even
then only genuinely-broken files (won't parse + zero-byte/negative-tick).

Usage:
  python3 CODE/10_scan.py                 # scan all, write _work/scan.parquet
  python3 CODE/10_scan.py --limit 2000    # quick sample run
  python3 CODE/10_scan.py --apply         # additionally move broken files to _quarantine/
"""
import os, sys, glob, argparse, time, statistics, shutil
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

SCAN_PARQUET = os.path.join(C.WORK, "scan.parquet")


def scan_one(path):
    md5 = os.path.basename(path).split(".mid")[0]
    rec = dict(md5=md5, parses=False, parse_error=None, is_zero_byte=False,
               neg_ticks=False, n_notes=0, dur_sec=None, bpm=None,
               note_density=None, note_density_absurd=False, dur_over_1h=False,
               all_notes_out_of_piano_range=None, vel_min=None, vel_max=None,
               velocity_dynamic_range=None, tempo_stability=None,
               polyphony_density=None, n_voices=None, drums_on_channel_9=False,
               drum_notes_valid=None, nonstandard_drum_channel=False)
    try:
        if os.path.getsize(path) == 0:
            rec["is_zero_byte"] = True
            rec["parse_error"] = "zero-byte"
            return rec
        TMIDIX = C.tmidix()
        score = TMIDIX.midi2score(open(path, "rb").read())
        ticks = score[0] if score else 480
        notes, tempos = [], []
        for ti, trk in enumerate(score):
            if ti == 0:
                continue
            for e in trk:
                if e[0] == "note":
                    notes.append(e)  # ['note', start, dur, chan, pitch, vel]
                elif e[0] == "set_tempo" and len(e) >= 3 and e[2]:
                    tempos.append(60_000_000 / e[2])
        rec["parses"] = True
        rec["n_notes"] = len(notes)
        if not notes:
            rec["parse_error"] = "no-notes"
            return rec
        if any((e[1] < 0 or e[2] < 0) for e in notes):
            rec["neg_ticks"] = True

        starts = np.array([e[1] for e in notes], dtype=np.float64)
        durs   = np.array([e[2] for e in notes], dtype=np.float64)
        chans  = np.array([e[3] for e in notes], dtype=np.int64)
        pitches= np.array([e[4] for e in notes], dtype=np.int64)
        vels   = np.array([e[5] for e in notes], dtype=np.int64)

        # duration in seconds: ticks are absolute ms after midi2score? No -- midi2score
        # uses ticks; convert via first tempo. Use simple tempo-based estimate.
        bpm = tempos[0] if tempos else 120.0
        span_ticks = float((starts + durs).max())
        sec_per_tick = (60.0 / bpm) / ticks if ticks else 0.0
        dur_sec = span_ticks * sec_per_tick
        rec["bpm"] = round(bpm, 1)
        rec["dur_sec"] = round(dur_sec, 2)
        rec["dur_over_1h"] = dur_sec > 3600
        if dur_sec > 0:
            nd = len(notes) / dur_sec
            rec["note_density"] = round(nd, 3)
            rec["note_density_absurd"] = nd > 80
            rec["polyphony_density"] = round(float(durs.sum()) * sec_per_tick / dur_sec, 3)

        nondrum = pitches[chans != 9]
        if nondrum.size:
            rec["all_notes_out_of_piano_range"] = bool(
                ((nondrum < 21) | (nondrum > 108)).all())
        rec["vel_min"] = int(vels.min())
        rec["vel_max"] = int(vels.max())
        rec["velocity_dynamic_range"] = int(vels.max() - vels.min())
        rec["tempo_stability"] = round(float(np.std(tempos)), 3) if len(tempos) > 1 else 0.0
        rec["n_voices"] = int(len(set(zip(chans.tolist(), (pitches // 12).tolist())))) \
            if False else int(len(np.unique(chans)))

        drum_chans = chans == 9
        rec["drums_on_channel_9"] = bool(drum_chans.any())
        other_drumlike = False  # heuristic: a channel that is *only* used like drums
        rec["nonstandard_drum_channel"] = other_drumlike
        if drum_chans.any():
            dp = pitches[drum_chans]
            rec["drum_notes_valid"] = bool(((dp >= 35) & (dp <= 81)).mean() > 0.8)
        return rec
    except Exception as ex:
        rec["parse_error"] = repr(ex)[:160]
        return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--apply", action="store_true",
                    help="move genuinely-broken files to _quarantine/ (otherwise dry-run report only)")
    args = ap.parse_args()
    from multiprocessing import Pool

    files = sorted(glob.glob(os.path.join(C.ROOT, "MIDIs", "*", "*.mid")))
    if args.limit:
        files = files[:args.limit]
    done = C.load_done_md5s(SCAN_PARQUET)
    todo = [f for f in files if os.path.basename(f).split(".mid")[0] not in done]
    C.log(f"scan: {len(files)} files, {len(done)} already done, {len(todo)} to scan", "scan.log")

    rows, t0, flushed = [], time.time(), 0
    existing = pd.read_parquet(SCAN_PARQUET) if done else None
    if todo:
        with Pool(args.workers) as pool:
            for i, rec in enumerate(pool.imap_unordered(scan_one, todo, chunksize=32), 1):
                rows.append(rec)
                if i % 20000 == 0:
                    df = pd.DataFrame(rows)
                    if existing is not None:
                        df = pd.concat([existing, df], ignore_index=True)
                    C.write_parquet_atomic(df, SCAN_PARQUET)
                    existing, rows, flushed = df, [], i
                    C.log(f"  {i}/{len(todo)} {i/(time.time()-t0):.0f}/s", "scan.log")
        df = pd.DataFrame(rows)
        if existing is not None:
            df = pd.concat([existing, df], ignore_index=True)
        C.write_parquet_atomic(df, SCAN_PARQUET)
    else:
        df = existing

    # ---- report ----
    broken = df[(~df["parses"]) | (df["is_zero_byte"]) | (df["neg_ticks"])]
    C.log(f"scan DONE: {len(df)} scanned, parses={int(df['parses'].sum())}, "
          f"broken={len(broken)}, neg_ticks={int(df['neg_ticks'].sum())}, "
          f"zero_byte={int(df['is_zero_byte'].sum())}", "scan.log")
    broken[["md5", "parse_error", "is_zero_byte", "neg_ticks"]].to_json(
        os.path.join(C.WORK, "quarantine_candidates.json"), orient="records", indent=2)

    if args.apply:
        moved = 0
        for md5 in broken["md5"]:
            src = C.stored_path(md5)
            if not os.path.exists(src):
                continue
            dst_dir = os.path.join(C.QUAR, md5[:2])
            os.makedirs(dst_dir, exist_ok=True)
            shutil.move(src, os.path.join(dst_dir, md5 + ".mid"))
            moved += 1
        C.log(f"--apply: moved {moved} broken files to _quarantine/", "scan.log")
    else:
        C.log(f"dry-run: {len(broken)} broken files listed in "
              f"_work/quarantine_candidates.json (pass --apply to move them)", "scan.log")
    C.progress("PHASE1+2parse", f"scanned={len(df)} broken={len(broken)}")


if __name__ == "__main__":
    main()
