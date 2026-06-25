#!/usr/bin/env python3
"""50_theory_gate.py — theory-gated, 8-bit-aware enhancement of a candidate MIDI.

This is the quality gate that sits AFTER the route-C recombination generator
(CODE/50_generate.py). A raw recombination lands in the right region of the
N×88 signature space but is musically rough: out-of-key passing tones, too many
overlapping voices, no idiomatic timbre. This script takes ONE candidate .mid and:

  1. DETECTS KEY     — music21 `analyze('key')` (Krumhansl), with a fast
                       pitch-class Krumhansl-Schmuckler fallback if music21 is
                       slow / fails on a malformed file.
  2. ARRANGES (8-bit)— reduces to a chiptune voice budget (<=4 voices: square
                       lead + saw/pulse harmony + synth bass + noise/drums),
                       assigns pulse/square GM program changes, and — in `arp`
                       mode — turns held chords into 1/16 arpeggios. Optionally
                       snaps out-of-key tonal notes to the nearest scale tone.
  3. GATES (theory)  — runs music_rules.evaluate_passage (Fux/EIS, 184 rules)
                       over the reduced melody+bass voices -> grade + soft cost.
                       Combined with diatonic ratio into a 0..1 quality score.
  4. SCORES (corner) — if a target corner caption / vector is given, embeds the
                       enhanced file with 49_sig_one.vector_from_midi and reports
                       cosine to the corner target.
  5. REJECTION SAMPLE— tries a few arrangement variants (snap / no-snap, block /
                       arp) and keeps the one that maximizes quality (and cosine
                       to target when supplied). This is the lightweight
                       rejection-sampling steer toward a theory-clean, on-target
                       8-bit rendering.

Returns: enhanced .mid path + quality score + detected key (the dict from
`enhance_candidate`). Designed to be imported by 50_generate.py (the
`--enhance` route) and runnable standalone.

CLI
  uv run --python .venv-linux/bin/python CODE/50_theory_gate.py \
      --input <mid> --mode chiptune --target_corner "<caption>"
  CODE/50_theory_gate.py --input cand.mid --mode arp --out enhanced.mid -v
  CODE/50_theory_gate.py --input cand.mid --dry-run        # analyse only, no write

Modes
  chiptune : <=4 voices, square/saw/bass program changes, block harmony.
  arp      : chiptune timbres + 1/16 arpeggiated harmony (classic 8-bit).
  clean    : keep original instruments; only key-snap + voice cap (theory only).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from importlib import util as _u

import numpy as np

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)
sys.path.insert(0, os.path.join(ROOT, "music_rules", "src"))

import mido  # noqa: E402

LOG = logging.getLogger("theory_gate")

EMPTY = os.path.join(ROOT, "_work", "emptyspace")
COMMON_TPB = 480

# ---- chiptune voice budget (GM program numbers) ----------------------------
PROG_SQUARE = 80   # Lead 1 (square)   -> melody
PROG_SAW = 81      # Lead 2 (sawtooth) -> harmony / arp
PROG_BASS = 38     # Synth Bass 1      -> bass
CH_MELODY, CH_HARMONY, CH_BASS, CH_DRUMS = 0, 1, 2, 9

MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)  # natural minor
# Krumhansl-Schmuckler key profiles (fallback key finder)
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_PCNAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# =========================== lazy heavy imports =============================
def _load(modfile: str, name: str):
    spec = _u.spec_from_file_location(name, os.path.join(CODE, modfile))
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_SIG = None       # 49_sig_one module (vector_from_midi, _m21 parser, etc.)
_EVAL = None       # music_rules.evaluate_passage


def sig_mod():
    global _SIG
    if _SIG is None:
        LOG.debug("loading 49_sig_one ...")
        _SIG = _load("49_sig_one.py", "sig_one")
    return _SIG


def eval_passage():
    global _EVAL
    if _EVAL is None:
        try:
            from music_rules import evaluate_passage  # noqa: E402
            _EVAL = evaluate_passage
        except Exception as ex:  # noqa: BLE001
            LOG.warning("music_rules unavailable (%s); theory grade disabled", repr(ex)[:80])
            _EVAL = False
    return _EVAL


# =============================== parsing ====================================
def parse_to_events(path: str):
    """Parse a .mid -> (events, tempos_bpm, end_tick) at COMMON_TPB.

    events: list[(start, dur, chan, pitch, vel)] ints, drums on chan 9 kept.
    Reuses the corpus parser (49_sig_one._m21.parse_notes) for fidelity.
    """
    tpb, arr, tempos, _ = sig_mod()._m21.parse_notes(path)
    if len(arr) == 0:
        raise ValueError("no notes in MIDI")
    sc = COMMON_TPB / float(tpb)
    events = []
    for s, d, ch, p, v in arr.tolist():
        events.append((int(round(s * sc)), max(1, int(round(d * sc))),
                       int(ch), int(p), int(v)))
    # parse_notes stores tempo events as (tick, bpm) — BPM directly, not usec.
    bpm = float(sorted(tempos)[0][1]) if tempos else 120.0
    if not (20.0 <= bpm <= 400.0):
        bpm = 120.0
    end_tick = max(s + d for s, d, *_ in events)
    return events, bpm, end_tick


# =============================== key ========================================
def _ks_key(pitch_classes: np.ndarray):
    """Krumhansl-Schmuckler best key from a 12-bin pitch-class histogram."""
    if pitch_classes.sum() <= 0:
        return "C", "major", 0.0
    x = pitch_classes / pitch_classes.sum()
    best = (-2.0, 0, "major")
    for mode, prof in (("major", _KS_MAJOR), ("minor", _KS_MINOR)):
        pn = (prof - prof.mean())
        for tonic in range(12):
            rot = np.roll(pn, tonic)
            r = float(np.corrcoef(x - x.mean(), rot)[0, 1])
            if np.isfinite(r) and r > best[0]:
                best = (r, tonic, mode)
    corr, tonic, mode = best
    return _PCNAMES[tonic], mode, round(corr, 3)


def detect_key(path: str, events=None):
    """(tonic_name, mode, correlation). music21 first; KS histogram fallback."""
    try:
        from music21 import converter  # noqa: E402
        sc = converter.parse(path)
        k = sc.analyze("key")
        return (k.tonic.name.replace("-", "b"), k.mode,
                round(float(getattr(k, "correlationCoefficient", 0.0) or 0.0), 3))
    except Exception as ex:  # noqa: BLE001
        LOG.debug("music21 key detect failed (%s); KS fallback", repr(ex)[:60])
        if events is None:
            events, _, _ = parse_to_events(path)
        hist = np.zeros(12)
        for s, d, ch, p, v in events:
            if ch != CH_DRUMS:
                hist[p % 12] += d
        return _ks_key(hist)


def scale_pcs(tonic_name: str, mode: str):
    tonic = _PCNAMES.index(tonic_name) if tonic_name in _PCNAMES else \
        {"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10}.get(tonic_name, 0)
    base = MINOR_SCALE if str(mode).startswith("min") else MAJOR_SCALE
    return tonic, set((tonic + s) % 12 for s in base)


def snap_pitch(pitch: int, allowed: set[int]):
    """Move a pitch to the nearest pitch whose pitch-class is in `allowed`."""
    if pitch % 12 in allowed:
        return pitch
    for off in (1, -1, 2, -2):
        if (pitch + off) % 12 in allowed:
            return max(0, min(127, pitch + off))
    return pitch


def diatonic_ratio(events, allowed: set[int]):
    tot = wt = 0
    for s, d, ch, p, v in events:
        if ch == CH_DRUMS:
            continue
        tot += d
        if p % 12 in allowed:
            wt += d
    return (wt / tot) if tot else 0.0


# =========================== voice reduction ================================
def split_roles(events):
    """Split tonal events into (melody, bass, harmony) + drums, by the corpus
    melody-channel picker and per-onset hi/lo split. Returns dict of lists."""
    S = sig_mod()
    arr = np.array([[s, d, ch, p, v] for (s, d, ch, p, v) in events], dtype=np.int64)
    mel_ch = S._m24.pick_melody(arr)
    drums = [e for e in events if e[2] == CH_DRUMS]
    tonal = [e for e in events if e[2] != CH_DRUMS]
    melody = [e for e in tonal if e[2] == mel_ch] if mel_ch >= 0 else []
    rest = [e for e in tonal if e not in melody]
    if not melody and tonal:
        # fall back: top note per onset is the melody
        by_onset = {}
        for e in tonal:
            by_onset.setdefault(e[0], []).append(e)
        melody = [max(g, key=lambda e: e[3]) for g in by_onset.values()]
        melset = set(melody)
        rest = [e for e in tonal if e not in melset]
    # bass = lowest note per onset across the remaining harmony
    by_onset = {}
    for e in rest:
        by_onset.setdefault(e[0], []).append(e)
    bass = [min(g, key=lambda e: e[3]) for g in by_onset.values()]
    bset = set(bass)
    harmony = [e for e in rest if e not in bset]
    return {"melody": sorted(melody), "bass": sorted(bass),
            "harmony": sorted(harmony), "drums": drums}


def beat_voices(events, max_beats=48):
    """Beat-aligned [bass, melody] MIDI columns for music_rules.evaluate_passage.

    One pitch per beat per voice (highest tonal = melody, lowest = bass); only
    beats where BOTH voices sound are kept. Capped for speed."""
    tonal = [e for e in events if e[2] != CH_DRUMS]
    if not tonal:
        return None
    beat = COMMON_TPB
    end = max(s + d for s, d, *_ in tonal)
    nbeats = min(max_beats, int(end // beat) + 1)
    mel, bass = [], []
    for b in range(nbeats):
        lo_t, hi_t = b * beat, (b + 1) * beat
        sounding = [p for (s, d, ch, p, v) in tonal if s < hi_t and s + d > lo_t]
        if not sounding:
            continue
        mel.append(max(sounding))
        bass.append(min(sounding))
    if len(mel) < 2:
        return None
    return [bass, mel]   # voice 0 = bass = cantus firmus


def theory_grade(events):
    """(grade, total_cost, n_hard, score0to1) from music_rules over the beat voices.

    NOTE the music_rules engine grades *species counterpoint*; arbitrary pop/8-bit
    recombinations almost always grade 'F' against strict Fux. We therefore use it
    as a RELATIVE voice-leading-cleanliness signal (cost + hard hits normalized by
    passage length), not an absolute pass/fail."""
    ev = eval_passage()
    voices = beat_voices(events)
    if not ev or voices is None:
        return "n/a", 0.0, 0, 0.5
    try:
        rep = ev({"voices": voices, "species": 1, "meter": "4/4",
                  "key": "C", "cantus_firmus_voice": 0})
    except Exception as ex:  # noqa: BLE001
        LOG.debug("evaluate_passage failed: %s", repr(ex)[:80])
        return "err", 0.0, 0, 0.5
    grade = rep["grade"]
    cost = float(rep["total_cost"])
    n_hard = len(rep["hard_violations"])
    n = max(1, len(voices[0]))
    # cleanliness: fewer soft cost + hard hits PER BEAT = cleaner voice leading
    penalty = min((cost + 1.5 * n_hard) / (3.0 * n), 1.0)
    return grade, cost, n_hard, max(0.0, 1.0 - penalty)


# =========================== arrangement ====================================
def arpeggiate(harmony, step=COMMON_TPB // 4):
    """Replace block harmony with 1/16 arpeggios cycling chord tones."""
    by_onset = {}
    for e in harmony:
        by_onset.setdefault(e[0], []).append(e)
    out = []
    onsets = sorted(by_onset)
    for i, on in enumerate(onsets):
        chord = sorted(set(e[3] for e in by_onset[on]))
        if not chord:
            continue
        nxt = onsets[i + 1] if i + 1 < len(onsets) else on + max(e[1] for e in by_onset[on])
        vel = int(np.median([e[4] for e in by_onset[on]]))
        t, j = on, 0
        while t < nxt:
            out.append((t, step, CH_HARMONY, chord[j % len(chord)], vel))
            t += step
            j += 1
    return out


def arrange(events, key, mode="chiptune", snap=True):
    """Produce reduced, 8-bit-timbred events + a {channel: program} map.

    Enforces the <=4-voice chiptune budget: melody/harmony/bass + drums."""
    tonic, allowed = scale_pcs(*key[:2])
    roles = split_roles(events)

    def _snap(lst):
        return [(s, d, ch, snap_pitch(p, allowed) if snap and ch != CH_DRUMS else p, v)
                for (s, d, ch, p, v) in lst]

    melody = [(s, d, CH_MELODY, p, v) for (s, d, _, p, v) in roles["melody"]]
    bass = [(s, d, CH_BASS, p, v) for (s, d, _, p, v) in roles["bass"]]
    harmony_src = [(s, d, CH_HARMONY, p, v) for (s, d, _, p, v) in roles["harmony"]]
    if mode == "arp":
        harmony = arpeggiate(harmony_src)
    else:
        harmony = harmony_src
    drums = roles["drums"]  # chan 9 noise/percussion preserved

    out = _snap(melody) + _snap(harmony) + _snap(bass) + drums
    if mode == "clean":
        progs = {}        # keep GM defaults; clean = theory-only pass
    else:
        progs = {CH_MELODY: PROG_SQUARE, CH_HARMONY: PROG_SAW, CH_BASS: PROG_BASS}
    n_voices = len({e[2] for e in out})
    return out, progs, n_voices


def write_midi(events, progs, out_path, bpm):
    """Write events (+ program changes) to a single-track MIDI at COMMON_TPB."""
    if not events:
        raise ValueError("nothing to write")
    mf = mido.MidiFile(ticks_per_beat=COMMON_TPB)
    meta = mido.MidiTrack(); mf.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(int(bpm)), time=0))
    trk = mido.MidiTrack(); mf.tracks.append(trk)
    for ch, prog in sorted(progs.items()):
        trk.append(mido.Message("program_change", channel=ch, program=int(prog), time=0))
    msgs = []
    for s, d, ch, p, v in events:
        p = max(0, min(127, p)); v = max(1, min(127, v))
        msgs.append((s, 1, ch, p, v))
        msgs.append((s + d, 0, ch, p, 0))
    msgs.sort(key=lambda e: (e[0], e[1]))
    last = 0
    for tick, kind, ch, p, v in msgs:
        dt = tick - last; last = tick
        trk.append(mido.Message("note_on" if kind else "note_off",
                                channel=ch, note=p, velocity=v, time=dt))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    mf.save(out_path)
    return out_path


# =========================== corner target ==================================
def corner_target_from_caption(caption: str):
    """Normalized anchor-centroid midpoint for a blend corner caption, or None."""
    import pandas as pd
    bp = os.path.join(EMPTY, "corners_blends.parquet")
    cp = os.path.join(EMPTY, "clusters_centroids.npy")
    if not (os.path.exists(bp) and os.path.exists(cp)):
        return None
    blends = pd.read_parquet(bp)
    br = blends[blends.midpoint_caption == caption]
    if br.empty:
        return None
    br = br.iloc[0]
    cents = np.load(cp)
    mid = (cents[int(br["anchor_a"])] + cents[int(br["anchor_b"])]) / 2.0
    return (mid / (np.linalg.norm(mid) + 1e-12)).astype(np.float64)


def _cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# =========================== the gate =======================================
def enhance_candidate(input_path, mode="chiptune", out_path=None,
                      target_vec=None, scaler=None, dry_run=False):
    """Theory-gate + 8-bit-arrange ONE candidate MIDI.

    Tries arrangement variants (snap/no-snap) and keeps the best by quality
    (and cosine-to-target when given). Returns a result dict with the enhanced
    path, quality score and detected key. Pure-analysis when dry_run=True.
    """
    events, bpm, _ = parse_to_events(input_path)
    key = detect_key(input_path, events)
    LOG.info("key=%s %s (corr=%.3f) bpm=%.0f", key[0], key[1], key[2], bpm)
    tonic, allowed = scale_pcs(*key[:2])
    # key-fit of the ORIGINAL notes — the meaningful signal (snapping makes the
    # enhanced file diatonic by construction, so it can't discriminate).
    orig_dia = round(diatonic_ratio(events, allowed), 4)

    variants = [True, False] if mode != "clean" else [True]
    best = None
    for snap in variants:
        ev, progs, nvoices = arrange(events, key, mode=mode, snap=snap)
        grade, cost, n_hard, tscore = theory_grade(ev)
        dia = diatonic_ratio(ev, allowed)
        # quality = voice-leading cleanliness + original key-fit (not post-snap)
        quality = round(0.4 * tscore + 0.6 * orig_dia, 4)
        cand = dict(snap=snap, events=ev, progs=progs, n_voices=nvoices,
                    grade=grade, total_cost=round(cost, 3), n_hard=n_hard,
                    theory_score=round(tscore, 4), diatonic=round(dia, 4),
                    quality_score=quality)
        LOG.debug("variant snap=%s grade=%s cost=%.2f hard=%d enh_dia=%.2f quality=%.3f",
                  snap, grade, cost, n_hard, dia, quality)
        cand["_obj"] = quality
        if best is None or cand["_obj"] > best["_obj"]:
            best = cand

    res = dict(input=input_path, mode=mode, detected_key=f"{key[0]} {key[1]}",
               key_corr=key[2], bpm=round(bpm, 1),
               grade=best["grade"], total_cost=best["total_cost"], n_hard=best["n_hard"],
               theory_score=best["theory_score"], orig_diatonic=orig_dia,
               enh_diatonic=best["diatonic"], n_voices=best["n_voices"],
               snapped=best["snap"], quality_score=best["quality_score"],
               cosine=None, enhanced_path=None)

    if dry_run:
        return res

    if out_path is None:
        d = os.path.dirname(os.path.abspath(input_path))
        stem = os.path.splitext(os.path.basename(input_path))[0]
        out_path = os.path.join(d, f"enhanced_{stem}.mid")
    write_midi(best["events"], best["progs"], out_path, bpm)
    res["enhanced_path"] = out_path

    if target_vec is not None:
        try:
            vec = sig_mod().vector_from_midi(out_path, scaler).astype(np.float64)
            res["cosine"] = round(_cos(vec, np.asarray(target_vec, dtype=np.float64)), 4)
        except Exception as ex:  # noqa: BLE001
            LOG.warning("cosine scoring failed: %s", repr(ex)[:80])
    LOG.info("enhanced -> %s  quality=%.3f cosine=%s",
             out_path, res["quality_score"], res["cosine"])
    return res


def passes_gate(res, min_score=0.6, min_cos=None):
    """Gate a result. We deliberately do NOT hard-reject on grade 'F' (strict
    species counterpoint fails almost all pop/8-bit material); instead we require
    a quality floor (voice-leading cleanliness + original key-fit) and, when a
    target corner was scored, a cosine floor."""
    if res["quality_score"] < min_score:
        return False
    if min_cos is not None and res.get("cosine") is not None and res["cosine"] < min_cos:
        return False
    return True


# =============================== CLI ========================================
def main():
    ap = argparse.ArgumentParser(description="Theory-gated 8-bit candidate enhancer")
    ap.add_argument("--input", required=True, help="candidate .mid to enhance")
    ap.add_argument("--mode", default="chiptune", choices=["chiptune", "arp", "clean"])
    ap.add_argument("--target_corner", default=None,
                    help="blend-corner caption to score cosine against")
    ap.add_argument("--out", default=None, help="output .mid path (default enhanced_<stem>.mid)")
    ap.add_argument("--min-score", type=float, default=0.55)
    ap.add_argument("--min-cos", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true", help="analyse only, write nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="[%(levelname)s] %(message)s")
    for noisy in ("matplotlib", "PIL", "music21", "fontTools"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if not os.path.exists(args.input):
        raise SystemExit(f"input not found: {args.input}")

    target_vec = None
    if args.target_corner:
        target_vec = corner_target_from_caption(args.target_corner)
        if target_vec is None:
            LOG.warning("corner caption not found among blends; cosine disabled")

    res = enhance_candidate(args.input, mode=args.mode, out_path=args.out,
                            target_vec=target_vec, dry_run=args.dry_run)
    res["passed"] = passes_gate(res, args.min_score, args.min_cos)
    print(json.dumps(res, indent=2))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
