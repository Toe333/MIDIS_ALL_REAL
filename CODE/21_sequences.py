#!/usr/bin/env python3
"""21_sequences.py — Phase 9.2/9.3/9.4 + 9.R RHYTHM. The second (and final) TMIDIX pass.

Re-parses every MIDI ONCE to recover the per-note/per-tempo event sequences the
META_DATA pickles never stored (they hold only aggregates). From those sequences it
computes, per file:

  9.R  RHYTHM (PRIMARY — per user directive, rhythm is the top priority):
       IOI distribution in beat units, onset density, grid/quantization tightness,
       syncopation, swing, microtiming/groove, pulse clarity, polyrhythm hint,
       articulation/duration profile, + a fixed-length rhythm fingerprint vector.
  9.2  MELODY: has_melody, melody_channel, melody_n_notes, contour fingerprint.
  9.3  STRUCTURE: self-similarity -> n_sections, has_repetition, repetition_ratio.
  9.4  TEMPO-CURVE: constant | gradual | rubato | erratic.

And it CACHES the note sequence per file so nothing ever re-parses again:
  NOTESEQ_DATA/<2hex>.npz   (key=md5 -> int32 array (n_notes,5): start,dur,chan,pitch,vel)
  NOTESEQ_DATA/<2hex>.meta.json (ticks_per_beat per md5)

Parallelism is per-BUCKET (MIDIs/<2hex>/, 256 of them): each worker parses one whole
bucket, writes that bucket's npz + a feature parquet part, so the job is naturally
resumable (skip any bucket whose part already exists) and yields 256 cache files
instead of 460k.

Usage:
  python3 CODE/21_sequences.py                      # full, all 256 buckets
  python3 CODE/21_sequences.py --buckets 00,01      # just these buckets (test)
  python3 CODE/21_sequences.py --limit 50           # at most N files/bucket (test)
  python3 CODE/21_sequences.py --workers 12
  python3 CODE/21_sequences.py --merge-only         # just concat parts -> seq_features.parquet
"""
import os, sys, glob, json, argparse, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
PARTS = os.path.join(C.WORK, "seq_parts")
OUT = os.path.join(C.WORK, "seq_features.parquet")
os.makedirs(NOTESEQ, exist_ok=True)
os.makedirs(PARTS, exist_ok=True)

# musical note-value bins for IOI/duration histograms, in BEAT units (tempo-free).
# bin i covers [edges[i], edges[i+1]); labels are the nearest note value.
NV_EDGES = np.array([0.0, 0.1875, 0.375, 0.75, 1.5, 3.0, 6.0, np.inf])  # 16th..whole+
NV_LABELS = ["sub16", "n16", "n8", "n4", "n2", "n1", "long"]


# ----------------------------- parse -----------------------------
def parse_notes(path):
    """Return (tpb, notes_array int32 (n,5)[start,dur,chan,pitch,vel], tempos list,
    timesigs list). Raises on parse failure."""
    TMIDIX = C.tmidix()
    score = TMIDIX.midi2score(open(path, "rb").read())
    tpb = int(score[0]) if score and score[0] else 480
    notes, tempos, timesigs = [], [], []
    for ti, trk in enumerate(score):
        if ti == 0:
            continue
        for e in trk:
            if e[0] == "note" and len(e) >= 6:
                notes.append((e[1], e[2], e[3], e[4], e[5]))
            elif e[0] == "set_tempo" and len(e) >= 3 and e[2]:
                tempos.append((e[1], 60_000_000.0 / e[2]))  # (tick, bpm)
            elif e[0] == "time_signature" and len(e) >= 4:
                timesigs.append((e[1], e[2], e[3]))          # (tick, num, denom_pow)
    arr = np.array(notes, dtype=np.int32) if notes else np.zeros((0, 5), np.int32)
    return tpb, arr, tempos, timesigs


# ----------------------------- rhythm -----------------------------
def _hist_beats(vals_beats):
    h = np.zeros(len(NV_LABELS))
    if len(vals_beats):
        idx = np.searchsorted(NV_EDGES, vals_beats, side="right") - 1
        idx = np.clip(idx, 0, len(NV_LABELS) - 1)
        for i in idx:
            h[i] += 1
        h /= h.sum()
    return h


def rhythm_features(tpb, arr, tempos):
    """The primary block. arr columns: start,dur,chan,pitch,vel (ticks)."""
    f = {}
    starts = arr[:, 0].astype(np.float64)
    durs = arr[:, 1].astype(np.float64)
    chans = arr[:, 2]
    n = len(starts)
    if n == 0 or tpb <= 0:
        return f
    span_ticks = float((starts + durs).max())
    total_beats = span_ticks / tpb if tpb else 0.0
    f["total_beats"] = round(total_beats, 2)

    # collapse simultaneous onsets (within a 32nd) into one rhythmic pulse event
    onset_ticks = np.unique(np.round(starts / (tpb / 8.0)).astype(np.int64)) * (tpb / 8.0)
    f["n_onsets"] = int(len(onset_ticks))
    f["onset_density_per_beat"] = round(len(onset_ticks) / total_beats, 4) if total_beats else 0.0

    # --- IOI distribution (beat units) ---
    if len(onset_ticks) > 1:
        ioi_b = np.diff(np.sort(onset_ticks)) / tpb
        ioi_b = ioi_b[ioi_b > 0]
        if len(ioi_b):
            f["ioi_mean_beats"] = round(float(ioi_b.mean()), 4)
            f["ioi_median_beats"] = round(float(np.median(ioi_b)), 4)
            f["ioi_cv"] = round(float(ioi_b.std() / ioi_b.mean()), 4) if ioi_b.mean() else 0.0
            h = _hist_beats(ioi_b)
            for lab, v in zip(NV_LABELS, h):
                f[f"ioi_{lab}"] = round(float(v), 4)

    # --- grid alignment / quantization / microtiming ---
    # distance of each onset to nearest 16th-note grid point, in [0,0.5] of a 16th
    grid16 = tpb / 4.0
    if grid16 > 0:
        phase = (starts % grid16) / grid16
        dist = np.minimum(phase, 1.0 - phase)          # 0=on grid, .5=max off
        f["quant_tightness_16"] = round(float((dist < 0.1).mean()), 4)
        f["grid_dev_mean"] = round(float(dist.mean()), 4)
        f["grid_dev_std"] = round(float(dist.std()), 4)
        # triplet grid (8th-note triplet = tpb/3)
        grid3 = tpb / 3.0
        phase3 = (starts % grid3) / grid3
        dist3 = np.minimum(phase3, 1.0 - phase3)
        f["quant_tightness_triplet"] = round(float((dist3 < 0.1).mean()), 4)
        f["triplet_feel"] = round(float((dist3 < 0.1).mean() - (dist < 0.1).mean()), 4)
        # microtiming magnitude in ms (needs tempo)
        bpm = tempos[0][1] if tempos else 120.0
        ms_per_tick = (60_000.0 / bpm) / tpb if (bpm and tpb) else 0.0
        f["microtiming_ms"] = round(float((dist * grid16).mean() * ms_per_tick), 2)

    # --- syncopation / off-beat energy ---
    beat_phase = (starts / tpb) % 1.0                  # position within the beat
    on_beat = np.minimum(beat_phase, 1.0 - beat_phase) < 0.05
    f["offbeat_ratio"] = round(float(1.0 - on_beat.mean()), 4)
    # weak-position emphasis: onsets on the "and"/"e"/"a" weighted by how weak
    bar_beats = 4.0
    bar_phase = (starts / tpb) % bar_beats
    downbeat = np.minimum(bar_phase, bar_beats - bar_phase) < 0.05
    f["downbeat_ratio"] = round(float(downbeat.mean()), 4)
    f["syncopation"] = round(float(((~on_beat).mean()) * (1.0 - downbeat.mean())), 4)

    # --- swing: where does the 2nd eighth land within beats that have two onsets? ---
    eighth_phase = beat_phase[(beat_phase > 0.3) & (beat_phase < 0.7)]
    if len(eighth_phase) >= 8:
        # straight=0.5, swung~0.667; report mean landing & a 0..1 swing score
        f["swing_phase"] = round(float(np.median(eighth_phase)), 4)
        f["swing_score"] = round(float(np.clip((np.median(eighth_phase) - 0.5) / 0.167, 0, 1.5)), 4)

    # --- articulation (dur / IOI per voice-ish): staccato<1 legato>=1 ---
    if total_beats:
        f["articulation_mean"] = round(float(np.median(durs / max(grid16, 1.0))), 4)
    hd = _hist_beats(durs / tpb)
    for lab, v in zip(NV_LABELS, hd):
        f[f"dur_{lab}"] = round(float(v), 4)

    # --- pulse clarity: autocorr of onset envelope on a 16th grid (capped) ---
    if grid16 > 0 and total_beats > 1:
        ncells = int(min(span_ticks / grid16 + 1, 8192))
        if ncells > 8:
            env = np.zeros(ncells)
            cell = np.clip((starts / grid16).astype(np.int64), 0, ncells - 1)
            for c in cell:
                env[c] += 1
            env -= env.mean()
            ac = np.correlate(env, env, mode="full")[ncells - 1:]
            if ac[0] > 0:
                ac = ac / ac[0]
                lo = min(2, len(ac) - 1)
                f["pulse_clarity"] = round(float(ac[lo:min(len(ac), 65)].max()), 4) if len(ac) > lo else 0.0

    # --- polyrhythm hint: do duple- and triplet-aligned onsets BOTH dominate? ---
    if grid16 > 0:
        duple = (dist < 0.08).mean()
        trip = (dist3 < 0.08).mean()
        f["polyrhythm_hint"] = round(float(min(duple, trip)), 4)

    # number of distinct rhythmic voices (channels carrying onsets)
    f["n_rhythm_voices"] = int(len(np.unique(chans)))
    return f


# ----------------------------- tempo curve (9.4) -----------------------------
def tempo_curve(tempos):
    f = {"n_tempo_changes": len(tempos)}
    if len(tempos) <= 1:
        f["tempo_class"] = "constant"
        f["tempo_cv"] = 0.0
        return f
    bpms = np.array([b for _, b in tempos], dtype=np.float64)
    cv = float(bpms.std() / bpms.mean()) if bpms.mean() else 0.0
    f["tempo_cv"] = round(cv, 4)
    if cv < 0.01:
        f["tempo_class"] = "constant"
    else:
        d1 = np.diff(bpms)
        # smoothness: how monotone / low-jerk the changes are
        mono = abs(d1.sum()) / (np.abs(d1).sum() + 1e-9)   # 1=monotone, 0=oscillating
        jerk = float(np.abs(np.diff(d1)).mean()) / (bpms.mean() + 1e-9)
        if mono > 0.7 and cv < 0.25:
            f["tempo_class"] = "gradual"
        elif cv >= 0.25 or jerk > 0.05:
            f["tempo_class"] = "erratic"
        else:
            f["tempo_class"] = "rubato"
    return f


# ----------------------------- melody (9.2) -----------------------------
def melody_features(tpb, arr):
    f = {"has_melody": False, "melody_channel": -1, "melody_n_notes": 0}
    if len(arr) == 0:
        return f
    chans, pitches, starts = arr[:, 2], arr[:, 3], arr[:, 0]
    best, best_score = -1, -1.0
    for ch in np.unique(chans):
        if ch == 9:
            continue                                   # skip drums
        m = chans == ch
        p = pitches[m]
        if len(p) < 8:
            continue
        s = starts[m]
        # polyphony: fraction of onsets that are simultaneous with another
        uniq = len(np.unique(s))
        mono = uniq / len(s)                            # 1=monophonic
        score = (p.mean() / 127.0) * mono * np.log1p(len(p))
        if score > best_score:
            best, best_score = int(ch), float(score)
    if best < 0:
        return f
    m = chans == best
    mp = pitches[m]
    ms = starts[m]
    order = np.argsort(ms)
    mp = mp[order]
    f["has_melody"] = True
    f["melody_channel"] = best
    f["melody_n_notes"] = int(len(mp))
    f["melody_pitch_mean"] = round(float(mp.mean()), 2)
    f["melody_pitch_range"] = int(mp.max() - mp.min())
    # contour fingerprint: directed-interval histogram (5 bins) + interval stats
    iv = np.diff(mp.astype(np.int64))
    if len(iv):
        bins = np.array([
            (iv <= -3).mean(),               # down leap
            ((iv < 0) & (iv >= -2)).mean(),  # down step
            (iv == 0).mean(),                # repeat
            ((iv > 0) & (iv <= 2)).mean(),   # up step
            (iv >= 3).mean(),                # up leap
        ])
        for lab, v in zip(["dleap", "dstep", "rep", "ustep", "uleap"], bins):
            f[f"mel_{lab}"] = round(float(v), 4)
        f["mel_interval_mean_abs"] = round(float(np.abs(iv).mean()), 3)
        f["mel_stepwise_ratio"] = round(float((np.abs(iv) <= 2).mean()), 4)
    return f


# ----------------------------- structure (9.3) -----------------------------
def structure_features(tpb, arr, max_windows=256):
    f = {"n_sections": 0, "has_repetition": False, "repetition_ratio": 0.0}
    if len(arr) == 0 or tpb <= 0:
        return f
    starts, pitches = arr[:, 0].astype(np.float64), arr[:, 3]
    span = float(starts.max()) + 1
    win = tpb * 2.0                                     # 2-beat windows
    nwin = int(min(span / win + 1, max_windows))
    if nwin < 4:
        return f
    if span / win > max_windows:                       # downsample long pieces
        win = span / max_windows
        nwin = max_windows
    # per-window chroma (12-d pitch-class presence)
    chroma = np.zeros((nwin, 12))
    widx = np.clip((starts / win).astype(np.int64), 0, nwin - 1)
    for wi, p in zip(widx, pitches):
        chroma[wi, p % 12] += 1
    norm = np.linalg.norm(chroma, axis=1, keepdims=True)
    norm[norm == 0] = 1
    chroma = chroma / norm
    sim = chroma @ chroma.T                             # cosine self-similarity
    # repetition: windows whose best FAR (non-local) match is near-identical.
    # threshold 0.95 (not 0.8) because same-key windows share chroma and over-match;
    # this is a secondary feature and is cheaply re-derivable from the NOTESEQ cache.
    rep_hits = 0
    gap = max(2, nwin // 16)                            # ignore matches within ~local context
    for i in range(nwin):
        row = sim[i].copy()
        for j in range(max(0, i - gap), min(nwin, i + gap + 1)):
            row[j] = -1
        if row.max() > 0.95:
            rep_hits += 1
    f["repetition_ratio"] = round(rep_hits / nwin, 4)
    f["has_repetition"] = bool(rep_hits / nwin > 0.3)
    # n_sections via novelty: count boundaries where adjacent windows differ a lot
    if nwin > 2:
        adj = np.array([sim[i, i + 1] for i in range(nwin - 1)])
        nov = adj < 0.5
        f["n_sections"] = int(1 + np.sum((np.diff(nov.astype(int)) == 1)))
    return f


# ----------------------------- per-bucket worker -----------------------------
def process_bucket(args):
    bucket, limit = args
    bdir = os.path.join(C.ROOT, "MIDIs", bucket)
    files = sorted(glob.glob(os.path.join(bdir, "*.mid")))
    if limit:
        files = files[:limit]
    recs, cache, tmeta = [], {}, {}
    for path in files:
        md5 = os.path.basename(path)[:-4]
        rec = {"md5": md5, "seq_ok": False, "seq_error": None}
        try:
            tpb, arr, tempos, timesigs = parse_notes(path)
            if len(arr) == 0:
                rec["seq_error"] = "no-notes"
            else:
                cache[md5] = arr
                tmeta[md5] = tpb
                rec.update(rhythm_features(tpb, arr, tempos))
                rec.update(tempo_curve(tempos))
                rec.update(melody_features(tpb, arr))
                rec.update(structure_features(tpb, arr))
                rec["seq_ok"] = True
        except Exception as ex:  # noqa: BLE001
            rec["seq_error"] = repr(ex)[:140]
        recs.append(rec)
    # write cache + features part for this bucket
    if cache:
        np.savez_compressed(os.path.join(NOTESEQ, bucket + ".npz"), **cache)
        with open(os.path.join(NOTESEQ, bucket + ".meta.json"), "w") as fh:
            json.dump(tmeta, fh)
    df = pd.DataFrame(recs)
    df.to_parquet(os.path.join(PARTS, bucket + ".parquet"), index=False)
    return bucket, len(recs), int(df["seq_ok"].sum()) if len(df) else 0


def merge_parts():
    parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
    if not parts:
        print("[21] no parts to merge"); return
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    C.write_parquet_atomic(df, OUT)
    print(f"[21] merged {len(parts)} buckets -> {OUT}  ({len(df)} rows, {df.shape[1]} cols)")
    print(f"[21] seq_ok={int(df['seq_ok'].sum())}  errors={int((~df['seq_ok']).sum())}")
    if "tempo_class" in df:
        print("[21] tempo_class:", df["tempo_class"].value_counts().to_dict())
    if "has_melody" in df:
        print(f"[21] has_melody={int(df['has_melody'].sum())}  has_repetition={int(df.get('has_repetition', pd.Series([])).sum())}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", type=str, default="", help="comma list e.g. 00,01 (default all)")
    ap.add_argument("--limit", type=int, default=0, help="max files per bucket (test)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()

    if args.merge_only:
        merge_parts(); return

    all_buckets = sorted(os.path.basename(d) for d in glob.glob(os.path.join(C.ROOT, "MIDIs", "*")))
    if args.buckets:
        want = set(args.buckets.split(","))
        all_buckets = [b for b in all_buckets if b in want]
    # resumable: skip buckets whose part already exists (unless --limit test mode)
    todo = [b for b in all_buckets
            if args.limit or not os.path.exists(os.path.join(PARTS, b + ".parquet"))]
    C.log(f"21_sequences: {len(all_buckets)} buckets, {len(todo)} to do "
          f"(workers={args.workers}, limit/bucket={args.limit or 'all'})", "sequences.log")

    from multiprocessing import Pool
    t0 = time.time()
    done_files = 0
    with Pool(args.workers) as pool:
        for i, (b, n, ok) in enumerate(
                pool.imap_unordered(process_bucket, [(b, args.limit) for b in todo]), 1):
            done_files += n
            el = time.time() - t0
            C.log(f"  [{i}/{len(todo)}] bucket {b}: {n} files ({ok} ok)  "
                  f"cum {done_files} files {done_files/el:.0f}/s", "sequences.log")

    if not args.limit:
        merge_parts()
    C.progress("PHASE9_seq", f"buckets={len(todo)} files={done_files}")


if __name__ == "__main__":
    main()
