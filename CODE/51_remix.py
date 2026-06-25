#!/usr/bin/env python3
"""51_remix.py — COHERENT REMIX: keep one song's full backing (drums + bass +
keys/harmony groove) and lay a DIFFERENT song's melody (or a freshly generated /
user-supplied one) on top, so the result sounds like a real song instead of a
disjointed stem swap.

Why this is coherent (not Frankenstein):
  * The BACKING is kept INTACT — it's already a real, internally-consistent
    arrangement (drums + bass + comping). We never chop it into mismatched layers.
  * The MELODY is made to FIT the backing: transposed into the backing's key,
    then snapped per-bar to the active chord (chord tones on strong beats, scale
    tones elsewhere) for consonance / voice-leading, and bar-aligned/tiled so its
    phrases line up with the backing's bars.
  * Everything then runs through CODE/50_theory_gate.py (music21 key detect →
    voice-leading grade → chiptune/clean arrange → cosine re-score) so the output
    is polished and intentional.

100% symbolic (MIDI in, MIDI out); audio is only the final fluidsynth render.

Melody sources (mix & match in one run):
  --melody-from A,B,...   use the melody line from these corpus md5s
  --new-melody --variants N   generate N chord-aware diatonic melodies that fit
  --user-melody f1.mid,f2.mid  overlay your own melody file(s)

Examples:
  # pattern from a liked song + a new generated melody (6 variants):
  python CODE/51_remix.py --pattern-from <MD5> --new-melody --variants 6 \
      --enhance chiptune --group coherent_remix
  # drums/bass/keys from A, melody from B:
  python CODE/51_remix.py --pattern-from <A> --melody-from <B> --enhance clean
  # your own topline over a corpus groove:
  python CODE/51_remix.py --pattern-from <A> --user-melody mytune.mid
"""
import os, sys, argparse, re, subprocess, bisect
from importlib import util as _u
import numpy as np
import pandas as pd

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)


def _load(modfile, name):
    spec = _u.spec_from_file_location(name, os.path.join(CODE, modfile))
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


G = _load("50_generate.py", "gen50")          # reuse stems/write/fit/embed helpers
TG = G._gate_mod()                              # 50_theory_gate (enhance/grade)
_S = G._S                                       # 49_sig_one (parser + vector_from_midi)
_m25 = _S._m25                                  # 25_harmony_refine (estimate_chord/TEMPLATES)

COMMON_TPB = G.COMMON_TPB
BAR_TICKS = G.BAR_TICKS
OUTBASE = G.OUTBASE
SF2 = G.SF2
MAJOR = set(_m25.MAJOR_SCALE)
MINOR = set(_m25.MINOR_SCALE)

# ---- optional EIS engine (advanced pass: chord extensions + strict voice leading) ----
sys.path.insert(0, os.path.join(ROOT, "music_rules", "src"))
try:
    from music_rules.core.eis import chords as _ech          # noqa: E402
    from music_rules.core.eis import voice_leading as _evl    # noqa: E402
    from music_rules.core.eis import nct as _nct             # noqa: E402
    _EIS = True
except Exception as _ex:  # noqa: BLE001
    print(f"[remix] music_rules EIS unavailable ({repr(_ex)[:60]}); --advanced disabled")
    _EIS = False

# detected triad quality (25_harmony_refine) -> EIS chord class
_EXT_CLASS = {"maj": "9", "maj7": "9", "min": "min9", "min7": "min9",       # rich (9ths)
              "dom7": "dom9", "sus": "dom9", "dim": "min7b5", "aug": "triad-7"}
_BASIC_CLASS = {"maj": "triad", "maj7": "triad-7", "min": "triad-min",      # plain triads/7ths
                "min7": "triad-min-7", "dom7": "dom7", "sus": "dom7",
                "dim": "min7b5", "aug": "triad-7"}
# diatonic functional substitution by scale degree (relative to key tonic): deg -> (deg, quality)
_DEG_SUB = {0: (9, "min"), 5: (2, "min"), 9: (0, "maj"), 2: (5, "maj"), 4: (9, "min")}
_TECHNIQUES = ("ext", "sub", "dsub", "iiv", "nct")

# per-bar melodic rhythm templates, in beats: (onset_beat, dur_beats)
RHYTHMS = [
    [(0, 1), (1, 1), (2, 1), (3, 1)],
    [(0, 1), (1, 0.5), (1.5, 0.5), (2, 1), (3, 1)],
    [(0, 0.5), (0.5, 0.5), (1, 1), (2, 1), (3, 0.5), (3.5, 0.5)],
    [(0, 1.5), (1.5, 0.5), (2, 1), (3, 1)],
    [(0, 2), (2, 1), (3, 1)],
    [(0, 1), (1, 1), (2, 2)],
]


# ----------------------------- key / chords --------------------------------
def _pitch_hist(events):
    h = np.zeros(12)
    for s, d, ch, p, v in events:
        if ch != 9:
            h[p % 12] += d
    return h


def key_of(events):
    """(tonic_pc, mode, allowed_pcs) for a set of events via Krumhansl-Schmuckler."""
    name, mode, _ = TG._ks_key(_pitch_hist(events))
    tonic_pc, allowed = TG.scale_pcs(name, mode)
    return tonic_pc, mode, allowed


def chord_grid(events, total_bars):
    """Per-bar chord as (root, quality, pcs); carries the previous chord over
    empty bars so the melody always has something consonant to lean on."""
    chroma = np.zeros((total_bars, 12))
    for s, d, ch, p, v in events:
        if ch == 9:
            continue
        b = int(s // BAR_TICKS)
        if 0 <= b < total_bars:
            chroma[b, p % 12] += d
    grid, last = [], None
    for b in range(total_bars):
        if chroma[b].sum() > 0:
            root, q = _m25.estimate_chord(chroma[b])
            if root >= 0:
                pcs = set((root + i) % 12 for i in _m25.TEMPLATES.get(q, (0, 4, 7)))
                last = (root, q, pcs)
        grid.append(last)
    # backfill any leading None with the first real chord
    first = next((c for c in grid if c), None)
    return [c if c else first for c in grid]


# ----------------------------- melody helpers ------------------------------
def _norm_to_zero(events):
    """Shift events so the earliest onset is at tick 0; return (events0, n_bars)."""
    if not events:
        return [], 0
    t0 = min(s for s, *_ in events)
    ev0 = [(s - t0, d, ch, p, v) for (s, d, ch, p, v) in events]
    span = max(s + d for s, d, *_ in ev0)
    return ev0, max(1, int(np.ceil(span / BAR_TICKS)))


def _transpose(events, semis):
    if not semis:
        return events
    return [(s, d, ch, max(0, min(127, p + semis)), v) for (s, d, ch, p, v) in events]


def _min_shift(src_tonic, dst_tonic):
    sh = (dst_tonic - src_tonic) % 12
    return sh - 12 if sh > 6 else sh


def _nearest_pc(target, pool, lo=48, hi=88):
    best, bd = None, 99
    for cand in range(target - 7, target + 8):
        if lo <= cand <= hi and cand % 12 in pool:
            d = abs(cand - target)
            if d < bd:
                bd, best = d, cand
    return best if best is not None else target


def snap_melody(melody, cgrid, scale):
    """Snap each melody note to the active chord (strong beats) or scale (weak)."""
    out = []
    for s, d, ch, p, v in melody:
        b = int(s // BAR_TICKS)
        chord = cgrid[b][2] if (0 <= b < len(cgrid) and cgrid[b]) else scale
        beat = (s % BAR_TICKS) / COMMON_TPB
        strong = abs(beat - round(beat)) < 0.05 and int(round(beat)) % 2 == 0
        pool = chord if strong else scale
        np_ = p if p % 12 in pool else _nearest_pc(p, pool)
        out.append((s, d, ch, np_, v))
    return out


def fit_melody(melody0, mel_bars, total_bars):
    """Tile/truncate a zero-based melody to exactly total_bars (bar-aligned)."""
    return G.fit_to_bars(melody0, mel_bars, total_bars)


def melody_from_md5(md5):
    st = G.load_stems(md5)
    return st.get("melody", []) if st else []


def melody_from_file(path):
    tpb, arr, _, _ = _S._m21.parse_notes(path)
    if len(arr) == 0:
        return []
    sc = COMMON_TPB / float(tpb)
    ev = [(int(round(s * sc)), max(1, int(round(d * sc))), int(ch), int(p), int(v))
          for s, d, ch, p, v in arr.tolist()]
    mel_ch = _S._m24.pick_melody(np.array([[s, d, ch, p, v] for s, d, ch, p, v in ev],
                                          dtype=np.int64))
    if mel_ch >= 0:
        m = [e for e in ev if e[2] == mel_ch]
        if m:
            return m
    # fallback: top note per onset
    by = {}
    for e in ev:
        if e[2] == 9:
            continue
        if e[0] not in by or e[3] > by[e[0]][3]:
            by[e[0]] = e
    return [by[k] for k in sorted(by)]


def _snap_pool(pitch, t, cgrid, scale):
    bar = int(t // BAR_TICKS)
    chord = cgrid[bar][2] if (0 <= bar < len(cgrid) and cgrid[bar]) else scale
    beat = (t % BAR_TICKS) / COMMON_TPB
    strong = abs(beat - round(beat)) < 0.05 and int(round(beat)) % 2 == 0
    pool = chord if strong else scale
    return pitch if pitch % 12 in pool else _nearest_pc(pitch, pool)


def gen_melody(cgrid, scale, total_bars, rng, phrase_bars=4):
    """Song-like melody: build ONE chord-aware motif of `phrase_bars`, then REPEAT it
    across the song, re-snapping each repeat to the local chords (so it follows the
    changing harmony while keeping its rhythm + contour). Motif repetition is what
    makes it sound intentional instead of a 90-bar random walk."""
    motif = []
    prev = 67
    for b in range(phrase_bars):
        chord = cgrid[b % len(cgrid)][2] if cgrid[b % len(cgrid)] else scale
        t0 = b * BAR_TICKS
        for ob, db in RHYTHMS[int(rng.integers(len(RHYTHMS)))]:
            t = t0 + int(ob * COMMON_TPB)
            dur = max(1, int(db * COMMON_TPB))
            strong = abs(ob - round(ob)) < 1e-6 and int(round(ob)) % 2 == 0
            pool = chord if strong else scale
            prev = _nearest_pc(prev + int(rng.choice([-2, -1, 1, 2, 0, -1, 1, 3, -3])), pool)
            motif.append((t, dur, prev, 84))
    out, block = [], 0
    while block * phrase_bars < total_bars:
        base = block * phrase_bars * BAR_TICKS
        for t, dur, p, v in motif:
            tt = base + t
            if tt >= total_bars * BAR_TICKS:
                continue
            out.append((tt, dur, 0, _snap_pool(p, tt, cgrid, scale), v))
        block += 1
    return out


# ----------------------------- assembly ------------------------------------
def _mean_pitch(events):
    ps = [p for s, d, ch, p, v in events if ch != 9]
    return float(np.mean(ps)) if ps else 0.0


def build_remix(drums, backing, melody, pat_tonic, pat_scale, cgrid, total_bars,
                mel_key=None):
    """Key-match + chord-snap + bar-fit a melody onto an intact backing.
    Returns the 3-stem recipe [drums, backing, melody] for G.write_midi."""
    mel0, mel_bars = _norm_to_zero(melody)
    if mel0:
        if mel_key is None:
            mtonic, _, _ = key_of(mel0)
        else:
            mtonic = mel_key
        mel0 = _transpose(mel0, _min_shift(mtonic, pat_tonic))
        mel0 = fit_melody(mel0, mel_bars, total_bars)
        mel0 = snap_melody(mel0, cgrid, pat_scale)
        # lift the topline above the backing if it sits too low
        bmean = _mean_pitch(backing)
        mmean = _mean_pitch(mel0)
        if bmean and mmean and mmean < bmean + 4:
            oct_up = 12 * int(np.ceil((bmean + 4 - mmean) / 12.0))
            mel0 = _transpose(mel0, min(24, oct_up))
    # melody on a dedicated channel 0; move any backing on ch0 to ch2 to avoid timbre stomp
    backing2 = [(s, d, (2 if ch == 0 else ch), p, v) for (s, d, ch, p, v) in backing]
    melody2 = [(s, d, 0, p, v) for (s, d, ch, p, v) in mel0]
    return [drums, backing2, melody2]


# ===================== advanced pass: EIS reharmonization ==================
def split_bass_keys(backing):
    """Lowest note per onset = bass; the rest = keys/comping."""
    by_onset = {}
    for e in backing:
        by_onset.setdefault(e[0], []).append(e)
    bass, keys = [], []
    for on, g in by_onset.items():
        lo = min(g, key=lambda e: e[3])
        bass.append(lo)
        keys.extend(e for e in g if e is not lo)
    return bass, keys


def chord_segments(cgrid, total_bars):
    """One harmony segment per bar (carry last chord over empty bars)."""
    segs, last = [], None
    for b in range(total_bars):
        if cgrid[b]:
            last = cgrid[b]
        if last is None:
            continue
        root, q, _ = last
        segs.append(dict(start=b * BAR_TICKS, end=(b + 1) * BAR_TICKS, root=root, q=q))
    return segs


def reharm_segments(segs, tonic, tech, rng):
    """Apply chord substitutions / ii-V insertion at the segment level.
    Segments can split (ii-V) so this returns a NEW, possibly longer, list."""
    out = []
    for seg in segs:
        root, q = seg["root"], seg["q"]
        deg = (root - tonic) % 12
        # (dsub) diatonic functional substitution — shares 2 common tones, stays in key
        if "dsub" in tech and deg in _DEG_SUB and rng.random() < 0.4:
            nd, nq = _DEG_SUB[deg]
            root, q, deg = (tonic + nd) % 12, nq, nd
        # (sub) tritone substitution on dominants — chromatic cadential color
        if "sub" in tech and q == "dom7":
            root = (root + 6) % 12
        # (iiv) insert a ii in the first half of a V bar -> classic ii-V
        if "iiv" in tech and deg == 7 and q in ("dom7", "maj"):
            mid = (seg["start"] + seg["end"]) // 2
            out.append(dict(start=seg["start"], end=mid, root=(tonic + 2) % 12, q="min7"))
            out.append(dict(start=mid, end=seg["end"], root=root, q="dom7"))
            continue
        out.append(dict(start=seg["start"], end=seg["end"], root=root, q=q))
    return out


def voice_segments(segs, tech):
    """Voice each segment (extended or plain), connected by strict EIS voice_lead."""
    cmap = _EXT_CLASS if "ext" in tech else _BASIC_CLASS
    fallback = "triad-7" if "ext" in tech else "triad"
    prev = None
    for seg in segs:
        cls = cmap.get(seg["q"], fallback)
        pcs = _ech.pitch_classes(seg["root"], cls)
        seg["cls"], seg["pcs"] = cls, set(pcs)
        seg["voiced"] = (_ech.build_chord(seg["root"], cls, parts=4, base_octave=4)
                         if prev is None else _evl.voice_lead(prev, pcs, max_voice_jump=7))
        prev = seg["voiced"]
    return segs


def _seg_at(segs, starts, t):
    i = bisect.bisect_right(starts, t) - 1
    return segs[max(0, i)]


def advanced_keys_events(keys, segs):
    """Re-pitch the comping notes to the nearest voice-led chord tone of their
    segment — keeps original density/rhythm, applies the smooth EIS voicing."""
    starts = [s["start"] for s in segs]
    out = []
    for s, d, ch, p, v in keys:
        vch = _seg_at(segs, starts, s)["voiced"]
        out.append((s, d, 2, int(min(vch, key=lambda m: abs(m - p))), v))
    return out


def _resnap_melody(melody, segs, pat_scale):
    starts = [s["start"] for s in segs]
    mel = []
    for s, d, ch, p, v in melody:
        seg = _seg_at(segs, starts, s)
        beat = (s % BAR_TICKS) / COMMON_TPB
        strong = abs(beat - round(beat)) < 0.05 and int(round(beat)) % 2 == 0
        pool = seg["pcs"] if strong else pat_scale
        mel.append((s, d, 0, p if p % 12 in pool else _nearest_pc(p, pool), v))
    return mel


def embellish_melody(melody, tonic, mode):
    """(nct) Insert EIS non-chord tones between melody notes: a passing tone when
    two notes are a 3rd/4th apart, an upper-neighbour when a note repeats."""
    scale_id = "EIS-18-01" if mode == "major" else "EIS-18-07"
    mel = sorted(melody)
    out, n = [], len(mel)
    for i in range(n):
        s, d, ch, p, v = mel[i]
        done = False
        if i + 1 < n and d >= COMMON_TPB // 2:
            p2 = mel[i + 1][3]
            iv = p2 - p
            try:
                if 2 <= abs(iv) <= 4:
                    ev = _nct.insert_nct([p], [p2], voice=0, nct_type="PT",
                                         scale_id=scale_id, scale_root=tonic)
                elif iv == 0 and d >= COMMON_TPB:
                    ev = _nct.insert_nct([p], [p2], voice=0, nct_type="RT",
                                         scale_id=scale_id, scale_root=tonic, direction="up")
                else:
                    ev = None
                if ev is not None:
                    half = d // 2
                    out.append((s, half, ch, p, v))
                    out.append((s + half, d - half, ch, int(ev["midi"]), max(1, v - 8)))
                    done = True
            except Exception:  # noqa: BLE001
                pass
        if not done:
            out.append((s, d, ch, p, v))
    return out


def _vl_motion(voiced):
    """Mean per-voice semitone motion across chord changes (lower = smoother VL)."""
    tot, n, prev = 0, 0, None
    for v in voiced:
        if not v:
            continue
        if prev is not None and len(prev) == len(v):
            tot += sum(abs(a - b) for a, b in zip(sorted(prev), sorted(v)))
            n += 1
        prev = v
    return tot / max(1, n)


def _blocky_motion(segs):
    """Same chords voiced INDEPENDENTLY per segment (no VL) — the baseline."""
    return _vl_motion([_ech.build_chord(s["root"], s["cls"], parts=4, base_octave=4) for s in segs])


def advanced_recipe(recipe1, cgrid, total_bars, tonic, mode, pat_scale, tech, rng):
    """Turn a 1st-pass remix into the advanced version: keep drums + bass + melody,
    REPLACE the keys comping with EIS-reharmonized, voice-led chords, re-snap the
    melody and optionally embellish it. Returns (recipe, metrics)."""
    drums, backing, melody = recipe1
    bass, keys = split_bass_keys(backing)
    segs = voice_segments(reharm_segments(chord_segments(cgrid, total_bars), tonic, tech, rng), tech)
    adv_keys = advanced_keys_events(keys, segs)
    mel = _resnap_melody(melody, segs, pat_scale)
    if "nct" in tech:
        mel = embellish_melody(mel, tonic, mode)
    voiced = [s["voiced"] for s in segs]
    metrics = dict(vl_motion=round(_vl_motion(voiced), 2),
                   blocky_motion=round(_blocky_motion(segs), 2),
                   n_seg=len(segs), n_notes_mel=len(mel),
                   tech="+".join(t for t in _TECHNIQUES if t in tech))
    return [drums, bass, adv_keys, mel], metrics


# ----------------------------- main ----------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Coherent remix: backing from one song, melody from another/new")
    ap.add_argument("--pattern-from", required=True,
                    help="md5 (or .mid path) whose drums+bass+keys/harmony backing is kept")
    ap.add_argument("--melody-from", default=None, help="comma md5 list to take the melody from")
    ap.add_argument("--new-melody", action="store_true", help="generate chord-aware melodies")
    ap.add_argument("--variants", type=int, default=4, help="how many --new-melody variants")
    ap.add_argument("--user-melody", default=None, help="comma list of .mid files to overlay")
    ap.add_argument("--keep", type=int, default=8)
    ap.add_argument("--enhance", default="chiptune", choices=["chiptune", "arp", "clean", "off"])
    ap.add_argument("--gate-min-score", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--group", default="coherent_remix")
    ap.add_argument("--advanced", action="store_true",
                    help="also produce an ADVANCED version of the best results (EIS chord "
                         "extensions/substitutions + strict voice leading) and render a "
                         "3-way comparison: original base / 1st-pass mix / advanced")
    ap.add_argument("--compare-top", type=int, default=3,
                    help="how many best candidates to build advanced versions for (--advanced)")
    ap.add_argument("--reharm", default="ext,sub",
                    help="advanced techniques (comma): ext=9th/extended chords, sub=tritone "
                         "sub on dominants, dsub=diatonic functional sub (I<->vi/iii, IV<->ii), "
                         "iiv=ii-V insertion before V, nct=melodic passing/neighbour tones. "
                         "'all'=ext,sub,dsub,iiv,nct. (strict EIS voice leading is always applied)")
    ap.add_argument("--reharm-compare", action="store_true",
                    help="with --advanced: render ONE advanced version per technique on the "
                         "single best melody (base/1st/voicelead/ext/tritone/diatonic-sub/ii-V/"
                         "nct/ALL) so you can A/B each reharmonization in one group")
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()

    # ---- pattern (backing) ----
    pm = args.pattern_from
    if pm.endswith(".mid") or os.path.sep in pm:
        tpb, arr, _, _ = _S._m21.parse_notes(pm)
        sc = COMMON_TPB / float(tpb)
        ev = [(int(round(s * sc)), max(1, int(round(d * sc))), int(ch), int(p), int(v))
              for s, d, ch, p, v in arr.tolist()]
        mch = _S._m24.pick_melody(np.array([[s, d, ch, p, v] for s, d, ch, p, v in ev], dtype=np.int64))
        drums = [e for e in ev if e[2] == 9]
        backing = [e for e in ev if e[2] != 9 and e[2] != mch]
        pat_tag = os.path.splitext(os.path.basename(pm))[0][:8]
        pat_vec = None
    else:
        st = G.load_stems(pm)
        if not st:
            raise SystemExit(f"no notes in pattern source {pm}")
        drums = st["drums"]
        backing = st["harmony"]            # bass + keys + chords (everything non-melody, non-drums)
        pat_tag = pm[:8]
        try:
            pat_vec = G._mean_song_vec([pm])
        except Exception:  # noqa: BLE001
            pat_vec = None
    if not backing:
        raise SystemExit("pattern source has no backing (bass/keys/harmony) to keep")

    total_bars = max(1, int(np.ceil(G._span_ticks(drums, backing) / BAR_TICKS)))
    pat_tonic, pat_mode, pat_scale = key_of(backing)
    cgrid = chord_grid(backing, total_bars)
    print(f"[remix] pattern={pat_tag} bars={total_bars} key={'maj' if pat_mode=='major' else 'min'} "
          f"tonic_pc={pat_tonic} backing_notes={len(backing)} drums={len(drums)}")

    outdir = os.path.join(OUTBASE, f"remix_{pat_tag}")
    os.makedirs(outdir, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    # ---- collect melody sources -> raw remix candidates ----
    jobs = []   # (label, melody_events, mel_tonic_or_None)
    for md5 in (args.melody_from.split(",") if args.melody_from else []):
        md5 = md5.strip()
        if md5:
            jobs.append((f"mel{md5[:4]}", melody_from_md5(md5), None))
    for f in (args.user_melody.split(",") if args.user_melody else []):
        f = f.strip()
        if f:
            jobs.append((f"usr_{os.path.basename(f)[:6]}", melody_from_file(f), None))
    if args.new_melody:
        for i in range(args.variants):
            pbars = int(rng.choice([4, 4, 8]))      # mostly 4-bar motifs, some 8-bar
            mel = gen_melody(cgrid, pat_scale, total_bars, rng, phrase_bars=pbars)
            jobs.append((f"new{i:02d}b{pbars}", mel, pat_tonic))   # already in pattern key

    if not jobs:
        raise SystemExit("no melody source: pass --melody-from / --new-melody / --user-melody")

    cands = []
    for label, mel, mtonic in jobs:
        if not mel:
            print(f"  skip {label}: empty melody"); continue
        recipe = build_remix(drums, backing, mel, pat_tonic, pat_scale, cgrid, total_bars, mtonic)
        if not any(recipe):
            continue
        name = f"remix_{pat_tag}_{label}.mid"
        path = os.path.join(outdir, name)
        if not G.write_midi(recipe, path, _felt_bpm(pm)):
            continue
        try:
            dia, has_mel = G.beauty(path)
            cos = (G._cos(_S.vector_from_midi(path).astype(np.float64), pat_vec)
                   if pat_vec is not None else float("nan"))
        except Exception as ex:  # noqa: BLE001
            print(f"  skip {name}: {repr(ex)[:60]}"); continue
        cands.append(dict(name=name, path=path, label=label, cos_pattern=round(cos, 4),
                          diatonic=dia, has_melody=has_mel, recipe=recipe))
        print(f"  built {label}: diatonic={dia:.2f} has_melody={has_mel} cos_pattern={cos:.3f}")

    if not cands:
        raise SystemExit("no remixes built")
    cand_by_label = {c["label"]: c for c in cands}
    df = pd.DataFrame([{k: v for k, v in c.items() if k != "recipe"} for c in cands]) \
        .sort_values(["has_melody", "diatonic"], ascending=False).reset_index(drop=True)
    ranked = df.head(args.keep)
    df.to_csv(os.path.join(outdir, "remix_candidates.csv"), index=False)
    print(f"\n[remix] {len(df)} candidates -> {outdir}")

    def _enhance(path):
        outp = os.path.join(outdir, "enhanced_" + os.path.basename(path))
        try:
            res = TG.enhance_candidate(path, mode=args.enhance, out_path=outp, target_vec=pat_vec)
            res["passed"] = bool(TG.passes_gate(res, args.gate_min_score, None))
        except Exception as ex:  # noqa: BLE001
            print(f"  [gate] fail {os.path.basename(path)}: {repr(ex)[:70]}")
            res = dict(enhanced_path=None, quality_score=0.0, cosine=None,
                       detected_key="?", grade="err", passed=False)
        return res

    # ---- theory gate + chiptune enhancement (1st pass) ----
    rows = []
    if args.enhance != "off":
        for r in ranked.itertuples():
            res = _enhance(r.path)
            res["label"] = r.label
            rows.append(res)
            print(f"  [gate] {r.label} -> key={res['detected_key']} q={res['quality_score']:.3f} "
                  f"cos={res['cosine']} {'PASS' if res['passed'] else 'fail'}")
        pd.DataFrame(rows).to_csv(os.path.join(outdir, "remix_gated.csv"), index=False)
        print(f"[remix] gate: {sum(r['passed'] for r in rows)}/{len(rows)} passed")

    def _render(items):
        if args.no_audio:
            print(f"[remix] --no-audio: skipping render of {len(items)} tracks")
            return
        for label, mid, desc in items:
            wav = mid.replace(".mid", ".wav")
            subprocess.run(["fluidsynth", "-ni", "-F", wav, SF2, mid], check=False, capture_output=True)
            if os.path.exists(wav):
                subprocess.run(["webplayer", "add", wav, "--group", args.group,
                                "--label", label, "--desc", desc], check=False, capture_output=True)
        subprocess.run(["webplayer", "open"], check=False, capture_output=True)
        st = subprocess.run(["webplayer", "status"], capture_output=True, text=True)
        print(f"[webplayer] group '{args.group}': {len(items)} tracks\n{st.stdout.strip()}")

    # ===================== ADVANCED 3-way comparison =======================
    if args.advanced and _EIS:
        tech = set(_TECHNIQUES) if args.reharm.strip() == "all" \
            else {t.strip() for t in args.reharm.split(",") if t.strip() in _TECHNIQUES}
        print(f"[adv] techniques: {'+'.join(t for t in _TECHNIQUES if t in tech)} + voice-leading")
        # choose the best 1st-pass results (passed first, then by quality)
        order = sorted(rows, key=lambda r: (r["passed"], r["quality_score"]), reverse=True)
        chosen = [r for r in order if r["label"] in cand_by_label][:max(1, args.compare_top)]

        items = []
        # (1) original base pattern, untouched (drums + backing, no melody) — raw render
        base_path = os.path.join(outdir, f"base_{pat_tag}.mid")
        G.write_midi([drums, backing], base_path, _felt_bpm(pm))
        items.append((f"#0 ORIGINAL base · {pat_tag}", base_path,
                      f"untouched pattern (drums+bass+keys) key={'maj' if pat_mode=='major' else 'min'}"))

        adv_rows = []
        if args.reharm_compare:
            # isolate each technique on the SINGLE best melody so you can A/B them
            r = chosen[0]
            cand = cand_by_label[r["label"]]
            items.append((f"#1 1ST-PASS · {r['label']}", r["enhanced_path"] or cand["path"],
                          f"pattern+melody (no reharm) key={r['detected_key']} q={r['quality_score']:.2f}"))
            recipes = [("voicelead", {"ext"}),          # ext is needed for chord classes; VL is the star
                       ("ext", {"ext"}),
                       ("tritone-sub", {"ext", "sub"}),
                       ("diatonic-sub", {"ext", "dsub"}),
                       ("ii-V", {"ext", "iiv"}),
                       ("nct-melody", {"ext", "nct"}),
                       ("ALL", set(_TECHNIQUES))]
            for n, (tname, tset) in enumerate(recipes, 2):
                adv_recipe, m = advanced_recipe(cand["recipe"], cgrid, total_bars,
                                                pat_tonic, pat_mode, pat_scale, tset,
                                                np.random.default_rng(args.seed))
                adv_path = os.path.join(outdir, f"adv_{pat_tag}_{tname}.mid")
                G.write_midi(adv_recipe, adv_path, _felt_bpm(pm))
                ares = _enhance(adv_path)
                items.append((f"#{n} {tname}", ares["enhanced_path"] or adv_path,
                              f"EIS {m['tech']}+VL | VL {m['vl_motion']} vs blocky {m['blocky_motion']} | "
                              f"segs {m['n_seg']} mel_notes {m['n_notes_mel']} | q={ares['quality_score']:.2f}"))
                m.update(label=tname, q_adv=ares["quality_score"])
                adv_rows.append(m)
                print(f"  [adv:{tname}] VL {m['vl_motion']} (blocky {m['blocky_motion']}) "
                      f"segs {m['n_seg']} mel {m['n_notes_mel']} q->{ares['quality_score']:.2f}")
        else:
            for n, r in enumerate(chosen, 1):
                cand = cand_by_label[r["label"]]
                # (2) 1st-pass coherent mix (already enhanced)
                mix_mid = r["enhanced_path"] or cand["path"]
                items.append((f"#{n} 1ST-PASS · {r['label']}", mix_mid,
                              f"pattern+melody key={r['detected_key']} q={r['quality_score']:.2f}"))
                # (3) advanced: EIS reharmonization (per --reharm) + strict voice leading
                adv_recipe, m = advanced_recipe(cand["recipe"], cgrid, total_bars,
                                                pat_tonic, pat_mode, pat_scale, tech, rng)
                adv_path = os.path.join(outdir, f"adv_{pat_tag}_{r['label']}.mid")
                G.write_midi(adv_recipe, adv_path, _felt_bpm(pm))
                ares = _enhance(adv_path)
                adv_mid = ares["enhanced_path"] or adv_path
                items.append((f"#{n} ADVANCED · {r['label']}", adv_mid,
                              f"EIS {m['tech']}+VL | VL motion {m['vl_motion']} vs "
                              f"blocky {m['blocky_motion']} | q={ares['quality_score']:.2f}"))
                m.update(label=r["label"], q_1st=r["quality_score"], q_adv=ares["quality_score"])
                adv_rows.append(m)
                print(f"  [adv] {r['label']}: VL motion {m['vl_motion']} (vs blocky {m['blocky_motion']}), "
                      f"{m['n_seg']} segs | q {r['quality_score']:.2f} -> {ares['quality_score']:.2f}")
        pd.DataFrame(adv_rows).to_csv(os.path.join(outdir, "remix_advanced.csv"), index=False)
        _render(items)
        better = sum(1 for a in adv_rows if a["vl_motion"] < a["blocky_motion"])
        print(f"[remix] ADVANCED voice-leading smoother than blocky voicing in {better}/{len(adv_rows)} results")
        return

    # ---- normal render (1st-pass only) ----
    if rows:
        play = [r for r in rows if r["passed"] and r.get("enhanced_path")]
        if not play:
            play = sorted([r for r in rows if r.get("enhanced_path")],
                          key=lambda r: r["quality_score"], reverse=True)[:args.keep]
        triples = [(f"#{i} remix {pat_tag} {r['label']} [{args.enhance}]", r["enhanced_path"],
                    f"pattern={pat_tag} melody={r['label']} enhance={args.enhance} | "
                    f"key={r['detected_key']} q={r['quality_score']:.2f}") for i, r in enumerate(play, 1)]
    else:
        triples = [(f"#{i} remix {pat_tag} {r.label}", r.path, f"diatonic={r.diatonic:.2f}")
                   for i, r in enumerate(ranked.itertuples(), 1)]
    _render(triples)


def _felt_bpm(pattern_src):
    if pattern_src.endswith(".mid") or os.path.sep in pattern_src:
        try:
            _, _, tempos, _ = _S._m21.parse_notes(pattern_src)
            return float(sorted(tempos)[0][1]) if tempos else 120.0
        except Exception:  # noqa: BLE001
            return 120.0
    return G._felt_bpm_for(pattern_src)


if __name__ == "__main__":
    main()
