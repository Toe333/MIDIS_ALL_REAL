#!/usr/bin/env python3
"""50_generate.py — route-C generator: land NEW music in an empty corner of the
N×88 space by RECOMBINING the stems of the real songs nearest that corner, then
keeping the recombinations that score closest to the corner target (49_sig_one).

The north-star step, simplest-thing-that-can-work first. An empty BLEND corner
(27_emptyspace) is the midpoint between two dense cluster centroids; its 3 nearest
real songs surround it at cos≈0.82. We split each donor into stems by role —
drums (chan 9), melody (the 24_melody_refine pick), harmony/accompaniment (the
rest) — and rebuild candidates as {drums from A, melody from B, harmony from C}
over all donor triples, with a tempo nudge toward the corner's felt BPM. Each
candidate is embedded with 49_sig_one.vector_from_midi and scored by cosine to the
corner target (the normalized anchor-centroid midpoint). We keep the candidates
that beat the nearest real song's distance to the corner AND pass a proxy-beauty
gate (diatonic, has melody), render them, and load them into the webplayer.

Usage:
  python CODE/50_generate.py                      # top groove-ranked blend corner
  python CODE/50_generate.py --rank 2 --keep 6
  python CODE/50_generate.py --corner-caption "135bpm constant · triplet-feel ..."
"""
import os, sys, argparse, re, glob, subprocess
from importlib import util as _u
import numpy as np
import pandas as pd
import mido

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)
import _common as C  # noqa

EMPTY = os.path.join(ROOT, "_work", "emptyspace")
TARGETS = os.path.join(ROOT, "_work", "generation_seeds", "targets_v2_20260620.csv")
OUTBASE = os.path.join(ROOT, "_work", "generated")
SF2 = os.path.join(ROOT, "soundfonts", "GeneralUserGS.sf2")
COMMON_TPB = 480


def _load(modfile, name):
    spec = _u.spec_from_file_location(name, os.path.join(CODE, modfile))
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_S = _load("49_sig_one.py", "sig_one")     # vector_from_midi / parse / blocks
_m24 = _S._m24                              # melody channel picker
_GATE = None                                # 50_theory_gate (lazy; only if --enhance)


def _gate_mod():
    global _GATE
    if _GATE is None:
        _GATE = _load("50_theory_gate.py", "theory_gate")
    return _GATE


# ----------------------------- corner target -------------------------------
def _bpm_from_caption(cap):
    m = re.match(r"\s*(\d+)\s*bpm", cap or "")
    return float(m.group(1)) if m else 120.0


def pick_corner(rank=None, caption=None):
    """Return (caption, donors[md5...], target_vec[88], felt_bpm, nearest_sim)."""
    tg = pd.read_csv(TARGETS)
    blends = pd.read_parquet(os.path.join(EMPTY, "corners_blends.parquet"))
    cents = np.load(os.path.join(EMPTY, "clusters_centroids.npy"))
    if caption is None:
        row = (tg[tg.corner_type == "blend"].iloc[0] if rank is None
               else tg[tg["rank"] == rank].iloc[0])
        caption = row["caption"]
        donors = str(row["nearest_md5_top3"]).split(";")
        nsim = float(row["nearest_sim"])
    else:
        donors, nsim = None, None
    # map caption -> blend row (anchor centroids) for the true midpoint target
    br = blends[blends.midpoint_caption == caption]
    if br.empty:
        # isolated corner: target = mean of donor vectors (no anchor pair)
        if donors is None:
            raise SystemExit("caption not found among blends and no donors given")
        tgt = _mean_song_vec(donors)
    else:
        br = br.iloc[0]
        mid = (cents[int(br["anchor_a"])] + cents[int(br["anchor_b"])]) / 2.0
        tgt = mid / (np.linalg.norm(mid) + 1e-12)
        if donors is None:
            donors = str(br["nearest_songs"]).split(";")[:3]
            nsim = float(br["nearest_sim"])
    return caption, [d for d in donors if d], tgt.astype(np.float64), _bpm_from_caption(caption), nsim


def _mean_song_vec(md5s):
    ext = np.load(os.path.join(ROOT, "SIGNATURES_DATA", "signatures_ext.npy"), mmap_mode="r")
    idx = [l.strip() for l in open(os.path.join(ROOT, "SIGNATURES_DATA", "signatures_md5.txt"))]
    pos = {m: i for i, m in enumerate(idx)}
    v = np.mean([np.asarray(ext[pos[m]], dtype=np.float64) for m in md5s if m in pos], axis=0)
    return v / (np.linalg.norm(v) + 1e-12)


# ----------------------- "in the style of a liked song" --------------------
_EXT_CACHE = None


def _load_ext():
    """Load the N×88 matrix + md5 row index once (cached)."""
    global _EXT_CACHE
    if _EXT_CACHE is None:
        ext = np.load(os.path.join(ROOT, "SIGNATURES_DATA", "signatures_ext.npy"))
        idx = [l.strip() for l in open(os.path.join(ROOT, "SIGNATURES_DATA", "signatures_md5.txt"))
               if l.strip()]
        pos = {m: i for i, m in enumerate(idx)}
        norms = np.linalg.norm(ext, axis=1).astype(np.float64) + 1e-12
        _EXT_CACHE = (ext, idx, pos, norms)
    return _EXT_CACHE


def nearest_neighbors(md5, k=2, lo=0.50, hi=0.9990):
    """Top-k cosine neighbors of md5 in the 88-D space, skipping the song itself
    and near-duplicate arrangements (cos > hi). Returns [(md5, cos), ...]."""
    ext, idx, pos, norms = _load_ext()
    if md5 not in pos:
        raise SystemExit(f"{md5} not in signatures_md5.txt")
    v = ext[pos[md5]].astype(np.float64)
    sims = (ext @ v) / (norms * (np.linalg.norm(v) + 1e-12))
    out = []
    for j in np.argsort(-sims):
        m = idx[j]
        if m == md5:
            continue
        s = float(sims[j])
        if s > hi:                 # near-identical arrangement of the same song
            continue
        if s < lo:
            break
        out.append((m, round(s, 4)))
        if len(out) >= k:
            break
    return out


def _felt_bpm_for(md5, caption=None):
    if caption:
        b = _bpm_from_caption(caption)
        if b and b != 120.0:
            return b
    try:
        cat = pd.read_parquet(os.path.join(ROOT, "catalog", "metadata.parquet"),
                              columns=["md5", "felt_bpm"])
        r = cat[cat.md5 == md5]
        if len(r) and np.isfinite(r.felt_bpm.iloc[0]):
            return float(r.felt_bpm.iloc[0])
    except Exception:  # noqa: BLE001
        pass
    return _bpm_from_caption(caption or "")


def pick_like(md5, n_neighbors=2, empty_bias=0.25, caption=None):
    """Build a generation spec from a LIKED song: donor pool = {liked + its nearest
    neighbors}; target = the liked song's own 88-D vector nudged a little toward the
    nearest EMPTY direction (away from the neighbor crowd, into sparser space) so we
    don't just remix it. Returns the same tuple shape as pick_corner()."""
    ext, idx, pos, _ = _load_ext()
    seed = ext[pos[md5]].astype(np.float64)
    seed = seed / (np.linalg.norm(seed) + 1e-12)
    nbrs = nearest_neighbors(md5, n_neighbors)
    donors = [md5] + [m for m, _ in nbrs]
    tgt = seed.copy()
    if nbrs and empty_bias > 0:
        nbr_mean = np.mean([ext[pos[m]].astype(np.float64) for m, _ in nbrs], axis=0)
        nbr_mean = nbr_mean / (np.linalg.norm(nbr_mean) + 1e-12)
        direction = seed - nbr_mean        # points away from the crowd = toward emptier space
        nd = np.linalg.norm(direction)
        if nd > 1e-9:
            tgt = seed + empty_bias * (direction / nd)
    tgt = tgt / (np.linalg.norm(tgt) + 1e-12)
    cap = caption or f"style of {md5[:8]}"
    nsim = nbrs[0][1] if nbrs else 1.0
    print(f"[like] seed={md5[:8]} neighbors={[(m[:8], s) for m, s in nbrs]} "
          f"empty_bias={empty_bias} -> target cos-to-seed={_cos(tgt, seed):.4f}")
    return cap, donors, tgt.astype(np.float64), _felt_bpm_for(md5, caption), nsim


# ----------------------------- stems ---------------------------------------
def load_stems(md5):
    """Parse a donor and split into role stems, rescaled to COMMON_TPB ticks.
    Returns dict role -> list[(start,dur,chan,pitch,vel)] (ints)."""
    path = os.path.join(ROOT, "MIDIs", md5[:2], md5 + ".mid")
    tpb, arr, _, _ = _S._m21.parse_notes(path)
    if len(arr) == 0:
        return {}
    sc = COMMON_TPB / float(tpb)
    mel_ch = _m24.pick_melody(arr)
    drums, melody, harmony = [], [], []
    for s, d, ch, p, v in arr.tolist():
        ev = (int(round(s * sc)), max(1, int(round(d * sc))), int(ch), int(p), int(v))
        if ch == 9:
            drums.append(ev)
        elif ch == mel_ch and mel_ch >= 0:
            melody.append(ev)
        else:
            harmony.append(ev)
    return {"drums": drums, "melody": melody, "harmony": harmony}


def write_midi(stems, out_path, bpm):
    """Write overlaid stems to a single MIDI at COMMON_TPB and the target BPM."""
    mf = mido.MidiFile(ticks_per_beat=COMMON_TPB)
    meta = mido.MidiTrack(); mf.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    notes = [ev for st in stems for ev in st]
    if not notes:
        return False
    events = []                                  # (tick, kind, chan, pitch, vel)
    for s, d, ch, p, v in notes:
        p = max(0, min(127, p)); v = max(1, min(127, v))
        events.append((s, 1, ch, p, v))
        events.append((s + d, 0, ch, p, 0))
    events.sort(key=lambda e: (e[0], e[1]))      # note-offs before note-ons at a tick
    trk = mido.MidiTrack(); mf.tracks.append(trk)
    last = 0
    for tick, kind, ch, p, v in events:
        dt = tick - last; last = tick
        msg = "note_on" if kind else "note_off"
        trk.append(mido.Message(msg, channel=ch, note=p, velocity=v, time=dt))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mf.save(out_path)
    return True


# ----------------------------- TBB enforcement -----------------------------
TBB_MID = os.path.join(ROOT, "DRUM_PATTERNS", "TBB_locked.mid")


def load_tbb_loop():
    """TBB_locked.mid -> (drum events at COMMON_TPB, loop_len_ticks). One bar = 4 beats."""
    mf = mido.MidiFile(TBB_MID)
    sc = COMMON_TPB / float(mf.ticks_per_beat)
    evs, maxend = [], 0
    for tr in mf.tracks:
        t = 0
        active = {}
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                k = (msg.channel, msg.note)
                if active.get(k):
                    st, v = active[k].pop(0)
                    s2, d2 = int(round(st * sc)), max(1, int(round((t - st) * sc)))
                    evs.append((s2, d2, 9, int(msg.note), int(v)))
                    maxend = max(maxend, s2 + d2)
    loop = int(round(maxend / (4 * COMMON_TPB))) * 4 * COMMON_TPB or maxend  # whole bars
    return evs, max(loop, 4 * COMMON_TPB)


def tile_tbb(loop_evs, loop_len, span):
    """Tile the TBB loop to cover [0, span] ticks; returns drum events."""
    out = []
    reps = max(1, int(np.ceil(span / loop_len)))
    for r in range(reps):
        off = r * loop_len
        out.extend((s + off, d, ch, p, v) for (s, d, ch, p, v) in loop_evs)
    return out


def _span_ticks(*stems):
    end = 0
    for st in stems:
        for s, d, *_ in st:
            end = max(end, s + d)
    return end


# ====================== phrase-level recombination =========================
# Multi-feature Novelty boundary detector (LBDM-inspired) + cross-donor phrase
# shuffling. The whole-song recombiner keeps each candidate hugging one donor
# per role; splitting every donor into bar-aligned PHRASES (boundaries found on
# the melody, propagated to drums+harmony) and re-sequencing phrases from
# DIFFERENT donors per slot pushes candidates off any single donor while staying
# inside the corner. Everything below is 100% symbolic — no audio is rendered.
BAR_BEATS = 4                              # assume 4/4 phrase grid (corpus-dominant)
BAR_TICKS = BAR_BEATS * COMMON_TPB         # 1920 ticks/bar at COMMON_TPB

# novelty weights: rest + harmonic changes are the strongest phrase cues, then
# rhythm (IOI + its change) and melodic leap/contour (rhythm is project priority #1).
NOV_W = {"rest": 1.0, "ioi": 0.7, "ioi_chg": 0.6, "leap": 0.5, "contour": 0.4, "harm": 1.0}


def _mono_melody(mel):
    """Collapse a melody stem to one (onset, pitch, dur) per onset (top note)."""
    by = {}
    for s, d, ch, p, v in mel:
        if s not in by or p > by[s][1]:
            by[s] = (s, p, d)
    return [by[k] for k in sorted(by)]


def _bar_chroma(events, total_bars):
    ch = np.zeros((total_bars, 12))
    for s, d, c, p, v in events:
        if c == 9:
            continue
        b = int(s // BAR_TICKS)
        if 0 <= b < total_bars:
            ch[b, p % 12] += d
    return ch


def _harm_bar_novelty(events, total_bars):
    """Cosine distance between successive bars' chroma -> harmonic-change saliency
    indexed by bar boundary (sal[b] = change crossing into bar b)."""
    sal = np.zeros(total_bars + 1)
    if not events or total_bars < 2:
        return sal
    chroma = _bar_chroma(events, total_bars)
    for b in range(1, total_bars):
        a, c = chroma[b - 1], chroma[b]
        na, nc = np.linalg.norm(a), np.linalg.norm(c)
        if na > 0 and nc > 0:
            sal[b] = 1.0 - float(a @ c / (na * nc))
    return sal


def detect_boundaries(stems, min_bars=2, max_bars=8, weights=None):
    """Multi-feature Novelty (LBDM-inspired) phrase boundaries on the MELODY stem,
    snapped to bar lines and propagated to all roles. Returns bar cut indices
    [0, ..., total_bars] with every phrase length in [min_bars, max_bars]."""
    w = weights or NOV_W
    mel = stems.get("melody") or []
    harm = stems.get("harmony") or []
    span = _span_ticks(stems.get("melody", []), stems.get("harmony", []),
                       stems.get("drums", []))
    total_bars = max(1, int(np.ceil(span / BAR_TICKS)))
    if total_bars <= min_bars:
        return [0, total_bars]

    bar_sal = np.zeros(total_bars + 1)
    seq = _mono_melody(mel)
    if len(seq) >= 3:
        onsets = np.array([s for s, _, _ in seq], dtype=np.float64)
        pitches = np.array([p for _, p, _ in seq], dtype=np.float64)
        durs = np.array([d for _, _, d in seq], dtype=np.float64)
        ends = onsets + durs
        ioi = np.diff(onsets)                       # len n-1, transition t = t->t+1
        rest = np.maximum(0.0, onsets[1:] - ends[:-1])
        interval = np.diff(pitches)

        def _doc(a, b):                              # LBDM degree-of-change in [0,1]
            s = a + b
            return np.where(s > 0, np.abs(a - b) / (s + 1e-9), 0.0)

        nT = len(ioi)
        rest_s = rest / (rest.max() + 1e-9)
        ioi_s = ioi / (ioi.max() + 1e-9)
        ioi_chg = np.zeros(nT)
        if nT > 1:
            ioi_chg[1:] = _doc(ioi[:-1], ioi[1:])
        leap_s = np.abs(interval) / (np.abs(interval).max() + 1e-9)
        contour = np.zeros(nT)
        sgn = np.sign(interval)
        if nT > 1:
            contour[1:] = (sgn[1:] * sgn[:-1] < 0).astype(float)
        nov = (w["rest"] * rest_s + w["ioi"] * ioi_s + w["ioi_chg"] * ioi_chg +
               w["leap"] * leap_s + w["contour"] * contour)
        # a cut sits BEFORE note t+1, i.e. at its onset -> nearest bar line
        for nv, ct in zip(nov, onsets[1:]):
            b = int(round(ct / BAR_TICKS))
            if 0 < b <= total_bars:
                bar_sal[b] += nv

    bar_sal += w["harm"] * _harm_bar_novelty(harm + mel, total_bars)

    # greedy: walk forward, cut at the most-salient bar in [min,max] ahead,
    # always leaving >= min_bars for the tail; yields variable phrase lengths.
    cuts = [0]
    last = 0
    while total_bars - last > max_bars:
        lo = last + min_bars
        hi = min(last + max_bars, total_bars - min_bars)
        if hi < lo:
            nxt = last + max_bars
        else:
            seg = bar_sal[lo:hi + 1]
            nxt = lo + int(np.argmax(seg)) if seg.max() > 0 else last + max_bars
        cuts.append(nxt)
        last = nxt
    cuts.append(total_bars)
    return cuts


def _est_shift(stems):
    """Minimal semitone shift so the most-common tonal pitch-class lands on C."""
    hist = np.zeros(12)
    for role in ("melody", "harmony"):
        for s, d, ch, p, v in stems.get(role, []):
            hist[p % 12] += d
    if hist.sum() <= 0:
        return 0
    root = int(np.argmax(hist))
    shift = (-root) % 12
    return shift - 12 if shift > 6 else shift


def _transpose_tonal(stems, shift):
    if not shift:
        return stems
    out = {}
    for role, evs in stems.items():
        if role == "drums":
            out[role] = evs
        else:
            out[role] = [(s, d, ch, max(0, min(127, p + shift)), v)
                         for (s, d, ch, p, v) in evs]
    return out


def slice_phrase(events, bar_a, bar_b):
    """Events whose ONSET is in [bar_a, bar_b), shifted to 0 and clipped so no
    note bleeds past the phrase end (clean joins)."""
    t0, t1 = bar_a * BAR_TICKS, bar_b * BAR_TICKS
    out = []
    for s, d, ch, p, v in events:
        if t0 <= s < t1:
            nd = min(d, t1 - s)
            if nd > 0:
                out.append((s - t0, nd, ch, p, v))
    return out


def load_phrases(md5, min_bars=2, max_bars=8, align_key=True):
    """Split a donor into bar-aligned phrases. Boundaries are detected on the
    donor's own melody and propagated to drums+harmony. Returns list of dicts
    {melody, drums, harmony, bars, donor} with events shifted to phrase-start."""
    stems = load_stems(md5)
    if not stems:
        return []
    if align_key:
        stems = _transpose_tonal(stems, _est_shift(stems))
    cuts = detect_boundaries(stems, min_bars, max_bars)
    phrases = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        ph = {role: slice_phrase(stems.get(role, []), a, b)
              for role in ("melody", "drums", "harmony")}
        if ph["melody"] or ph["harmony"] or ph["drums"]:
            ph["bars"] = int(b - a)
            ph["donor"] = md5[:4]
            phrases.append(ph)
    return phrases


def fit_to_bars(events, src_bars, dst_bars):
    """Tile/truncate phrase events (start at 0) to exactly dst_bars of length."""
    if not events:
        return []
    dst_ticks = dst_bars * BAR_TICKS
    src_ticks = max(src_bars, 1) * BAR_TICKS
    out = []
    reps = int(np.ceil(dst_ticks / src_ticks))
    for r in range(reps):
        off = r * src_ticks
        for s, d, ch, p, v in events:
            ns = s + off
            if ns >= dst_ticks:
                continue
            nd = min(d, dst_ticks - ns)
            if nd > 0:
                out.append((ns, nd, ch, p, v))
    return out


def build_phrase_song(slots, force_drum=False, tbb_loop=None):
    """Concatenate phrase slots end-to-end on a shared bar grid. Each slot's
    length is driven by its MELODY phrase; harmony/drums are length-matched to it.
    slots: list of (mel_ph, harm_ph, drum_ph). Returns [drums, melody, harmony]."""
    drums, melody, harmony = [], [], []
    bar_off = 0
    for mp, hp, dp in slots:
        L = mp["bars"]
        off = bar_off * BAR_TICKS
        for s, d, ch, p, v in mp["melody"]:
            melody.append((s + off, d, ch, p, v))
        if hp is not None:
            for s, d, ch, p, v in fit_to_bars(hp["harmony"], hp["bars"], L):
                harmony.append((s + off, d, ch, p, v))
        if force_drum and tbb_loop is not None:
            seg = tile_tbb(tbb_loop[0], tbb_loop[1], L * BAR_TICKS)
            for s, d, ch, p, v in seg:
                if s < L * BAR_TICKS:
                    drums.append((s + off, d, ch, p, v))
        elif dp is not None:
            for s, d, ch, p, v in fit_to_bars(dp["drums"], dp["bars"], L):
                drums.append((s + off, d, ch, p, v))
        bar_off += L
    return [drums, melody, harmony]


# ----------------------------- proxy beauty --------------------------------
def beauty(path):
    """(diatonic_ratio, has_melody) from the same refine functions the corpus uses."""
    tpb, arr, _, _ = _S._m21.parse_notes(path)
    hf = _S._m25.harmony_features(arr, tpb)
    mf = _S._m24.melody_features(arr, tpb)
    return hf.get("diatonic_ratio", 0.0) or 0.0, bool(mf.get("has_melody"))


def _cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# ----------------------------- main ----------------------------------------
# ext pillar layout: pitch36 / rhythm20 / melody13 / harmony8 / groove11 = 88
P_RHYTHM = slice(36, 56)
P_GROOVE = slice(77, 88)
_TBB_EXT = None


def tbb_ext_vec():
    """TBB_locked.mid embedded in the 88-D ext space (we use its rhythm+groove pillars)."""
    global _TBB_EXT
    if _TBB_EXT is None:
        _TBB_EXT = _S.vector_from_midi(TBB_MID).astype(np.float64)
    return _TBB_EXT


def anchor_tbb(tgt):
    """Overwrite the rhythm + groove pillars of a corner target with TBB's, renormalize."""
    t = tgt.copy()
    tv = tbb_ext_vec()
    t[P_RHYTHM] = tv[P_RHYTHM]
    t[P_GROOVE] = tv[P_GROOVE]
    return t / (np.linalg.norm(t) + 1e-12)


def _score_candidate(path, drum_stem, tgt, donor_vecs, extra):
    """Embed a written candidate and score it: cosine-to-corner, proxy beauty, and
    donor_sim = max cosine to any single donor (lower = more genuinely new)."""
    vec = _S.vector_from_midi(path).astype(np.float64)
    cos = _cos(vec, tgt)
    dia, has_mel = beauty(path)
    has_tbb = any(ch == 9 for _, _, ch, _, _ in drum_stem)
    dsim = max((_cos(vec, dv) for dv in donor_vecs.values()), default=0.0)
    row = dict(path=path, name=os.path.basename(path), cos=round(cos, 4),
               diatonic=dia, has_melody=has_mel, tbb=has_tbb,
               donor_sim=round(float(dsim), 4))
    row.update(extra)
    return row


def _whole_song_cands(donors, stems, tgt, donor_vecs, felt_bpm, outdir, force_drum,
                      tbb_loop, cap):
    """Original whole-song stem recombination: {drums A, melody B, harmony C}."""
    drum_donors = [None] if force_drum else donors
    cands = []
    for da in drum_donors:
        for mb in donors:
            for hc in donors:
                if force_drum:
                    span = _span_ticks(stems[mb]["melody"], stems[hc]["harmony"]) or 4 * COMMON_TPB
                    drum_stem = tile_tbb(tbb_loop[0], tbb_loop[1], span)
                    dlabel = "TBB"
                else:
                    drum_stem = stems[da]["drums"]; dlabel = da[:4]
                recipe = [drum_stem, stems[mb]["melody"], stems[hc]["harmony"]]
                if not any(recipe):
                    continue
                name = f"cand_d{dlabel}_m{mb[:4]}_h{hc[:4]}.mid"
                path = os.path.join(outdir, name)
                if not write_midi(recipe, path, felt_bpm):
                    continue
                try:
                    row = _score_candidate(path, drum_stem, tgt, donor_vecs,
                                           dict(drums=dlabel, melody=mb[:4], harmony=hc[:4],
                                                mode="whole", cap=cap))
                except Exception as ex:  # noqa: BLE001
                    print(f"  skip {name}: {repr(ex)[:60]}"); os.remove(path); continue
                cands.append(row)
    return cands


def _phrase_cands(donors, tgt, donor_vecs, felt_bpm, outdir, force_drum, tbb_loop,
                  cap, n_candidates, min_bars, max_bars, min_slots, max_slots, seed,
                  coherent=True):
    """Phrase-level recombination: split donors into bar-aligned phrases (boundaries
    found on melody, propagated to drums+harmony), then re-sequence whole phrases.

    coherent=True  : each slot is one REAL excerpt — melody+harmony(+drums) from the
                     SAME donor phrase — so chords sit under the melody (no vertical
                     clash). Novelty comes from re-ordering phrases across donors.
    coherent=False : melody / harmony / drums are sampled INDEPENDENTLY per slot
                     (maximal novelty, but can sound jumbled — used for corner hunts)."""
    donor_phrases = {d: load_phrases(d, min_bars, max_bars) for d in donors}
    donor_phrases = {d: ph for d, ph in donor_phrases.items() if ph}
    if not donor_phrases:
        print("  [phrase] no phrases extracted; falling back to whole-song")
        return []
    mel_bank = [ph for d in donor_phrases for ph in donor_phrases[d] if ph["melody"]]
    harm_bank = [ph for d in donor_phrases for ph in donor_phrases[d] if ph["harmony"]]
    drum_bank = [ph for d in donor_phrases for ph in donor_phrases[d] if ph["drums"]]
    if not mel_bank:
        print("  [phrase] no melodic phrases; falling back to whole-song")
        return []
    nph = {d: len(ph) for d, ph in donor_phrases.items()}
    print(f"  [phrase] donors->phrases {nph}  banks: mel={len(mel_bank)} "
          f"harm={len(harm_bank)} drum={len(drum_bank)}  coherent={coherent}")

    rng = np.random.default_rng(seed)
    cands = []
    for ci in range(n_candidates):
        n_slots = int(rng.integers(min_slots, max_slots + 1))
        slots, mel_ds = [], []
        for _ in range(n_slots):
            if coherent:
                # one real excerpt: melody + its own harmony + its own drums
                mp = mel_bank[int(rng.integers(len(mel_bank)))]
                hp = mp if mp["harmony"] else (
                    harm_bank[int(rng.integers(len(harm_bank)))] if harm_bank else None)
                dp = mp if mp["drums"] else (
                    drum_bank[int(rng.integers(len(drum_bank)))] if drum_bank else None)
            else:
                mp = mel_bank[int(rng.integers(len(mel_bank)))]
                hp = harm_bank[int(rng.integers(len(harm_bank)))] if harm_bank else None
                dp = drum_bank[int(rng.integers(len(drum_bank)))] if drum_bank else None
            slots.append((mp, hp, dp))
            mel_ds.append(mp["donor"])
        recipe = build_phrase_song(slots, force_drum=force_drum, tbb_loop=tbb_loop)
        if not any(recipe):
            continue
        donor_tag = "".join(sorted(set(mel_ds)))[:12]
        name = f"phr_{ci:02d}_n{n_slots}_m{donor_tag}.mid"
        path = os.path.join(outdir, name)
        if not write_midi(recipe, path, felt_bpm):
            continue
        try:
            row = _score_candidate(path, recipe[0], tgt, donor_vecs,
                                   dict(drums="TBB" if force_drum else "mix",
                                        melody=donor_tag, harmony="mix", mode="phrase",
                                        n_slots=n_slots, n_mel_donors=len(set(mel_ds)),
                                        cap=cap))
        except Exception as ex:  # noqa: BLE001
            print(f"  skip {name}: {repr(ex)[:60]}"); os.remove(path); continue
        cands.append(row)
    return cands


def generate_corner(rank, caption, force_drum, diatonic, tbb_loop, target_mode="corner",
                    phrase_level=True, n_candidates=48, min_bars=2, max_bars=8,
                    min_slots=4, max_slots=8, seed=0, spec=None, coherent=True):
    """Build recombination candidates for one corner (or a `spec` from pick_like);
    returns (cands, base, cap, tgt)."""
    cap, donors, tgt, felt_bpm, nsim = spec if spec is not None else pick_corner(rank, caption)
    if target_mode == "tbb_anchored":
        tgt = anchor_tbb(tgt)
    slug = re.sub(r"[^a-z0-9]+", "_", cap.lower())[:40].strip("_")
    outdir = os.path.join(OUTBASE, "tbb_birth" if force_drum else slug, slug)
    print(f"[corner rank={rank}] {cap}  donors={donors} felt_bpm={felt_bpm} "
          f"mode={'phrase' if phrase_level else 'whole'}")
    donor_vecs = {d: _mean_song_vec([d]) for d in donors}
    base = max(_cos(donor_vecs[d], tgt) for d in donors)

    stems = {d: load_stems(d) for d in donors}
    stems = {d: s for d, s in stems.items() if s.get("drums") or s.get("melody") or s.get("harmony")}
    donors = list(stems)
    donor_vecs = {d: donor_vecs[d] for d in donors}
    os.makedirs(outdir, exist_ok=True)

    cands = []
    if phrase_level:
        cands = _phrase_cands(donors, tgt, donor_vecs, felt_bpm, outdir, force_drum,
                              tbb_loop, cap, n_candidates, min_bars, max_bars,
                              min_slots, max_slots, seed, coherent=coherent)
    if not cands:   # whole-song mode, or phrase mode produced nothing
        cands = _whole_song_cands(donors, stems, tgt, donor_vecs, felt_bpm, outdir,
                                  force_drum, tbb_loop, cap)
    return cands, base, cap, tgt


def enhance_kept(ranked, cap, mode, min_score, min_cos, tgt=None):
    """Run the theory gate (50_theory_gate.enhance_candidate) on each kept
    candidate; write enhanced_<stem>.mid beside it; return per-candidate result
    dicts with a `passed` flag. `tgt` is the exact corner target vector the
    recombiner aimed at (so cosine is scored against the same point)."""
    G = _gate_mod()
    if tgt is None:
        tgt = G.corner_target_from_caption(cap)
    if tgt is None:
        print("[gate] no corner target vector; cosine gate disabled")
    rows = []
    for r in ranked.itertuples():
        src = r.path
        outp = os.path.join(os.path.dirname(src),
                            "enhanced_" + os.path.basename(src))
        try:
            res = G.enhance_candidate(src, mode=mode, out_path=outp, target_vec=tgt)
            res["passed"] = bool(G.passes_gate(res, min_score, min_cos))
        except Exception as ex:  # noqa: BLE001
            print(f"[gate] enhance failed for {os.path.basename(src)}: {repr(ex)[:80]}")
            res = dict(input=src, enhanced_path=None, quality_score=0.0, cosine=None,
                       detected_key="?", grade="err", passed=False)
        res["src_cos"] = float(getattr(r, "cos", 0.0))
        rows.append(res)
        print(f"  [gate] {os.path.basename(src)} -> key={res['detected_key']} "
              f"grade={res['grade']} q={res['quality_score']:.3f} "
              f"cos={res['cosine']} {'PASS' if res['passed'] else 'fail'}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", type=int, default=None, help="row in targets_v2 (default top blend)")
    ap.add_argument("--ranks", default=None, help="comma list of ranks to span (e.g. 1,2,3,4)")
    ap.add_argument("--corner-caption", default=None)
    ap.add_argument("--like-md5", default=None,
                    help="generate NEW music in the STYLE of this liked corpus md5: donor "
                         "pool = liked song + its nearest 88-D neighbors; target = the liked "
                         "vector nudged toward the nearest empty direction (so it's not a remix)")
    ap.add_argument("--like-neighbors", type=int, default=2,
                    help="how many nearest neighbors to add to the donor pool (default 2)")
    ap.add_argument("--empty-bias", type=float, default=0.25,
                    help="0..1 how far to push the target away from the donor crowd into "
                         "sparser space (0 = exact style of the liked song)")
    ap.add_argument("--like-caption", default=None, help="optional caption for the liked seed")
    ap.add_argument("--keep", type=int, default=6)
    ap.add_argument("--diatonic", type=float, default=0.6)
    ap.add_argument("--force-drum", default=None, help="TBB = force the locked TBB beat as base drum layer")
    ap.add_argument("--target", default="corner", choices=["corner", "tbb_anchored"],
                    help="tbb_anchored = score vs corner pitch/melody/harmony + TBB rhythm/groove")
    ap.add_argument("--group", default=None)
    ap.add_argument("--phrase-level", action=argparse.BooleanOptionalAction, default=True,
                    help="phrase-level cross-donor recombination (default on); "
                         "--no-phrase-level reverts to whole-song stem swap")
    ap.add_argument("--n-candidates", type=int, default=48,
                    help="phrase-mode: number of phrase-shuffled candidates to build")
    ap.add_argument("--min-bars", type=int, default=2, help="phrase-mode: min phrase length (bars)")
    ap.add_argument("--max-bars", type=int, default=8, help="phrase-mode: max phrase length (bars)")
    ap.add_argument("--min-slots", type=int, default=4, help="phrase-mode: min phrases per candidate")
    ap.add_argument("--max-slots", type=int, default=8, help="phrase-mode: max phrases per candidate")
    ap.add_argument("--seed", type=int, default=0, help="phrase-mode: RNG seed for sampling")
    ap.add_argument("--coherent-slots", action=argparse.BooleanOptionalAction, default=True,
                    help="each slot = one real excerpt (melody+harmony+drums from the SAME "
                         "donor phrase) so chords sit under the melody (default on; avoids "
                         "the 'jumbled' vertical clash). --no-coherent-slots = independent "
                         "layer sampling (max novelty, for empty-corner hunts)")
    ap.add_argument("--novelty-weight", type=float, default=0.5,
                    help="kept set is ranked by cos_to_corner - w*donor_sim, so we keep "
                         "candidates that sit IN the corner but AWAY from any single donor "
                         "(0 = pure corner-cosine, the old behavior)")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--enhance", default="off", choices=["off", "chiptune", "arp", "clean"],
                    help="post-process kept candidates through CODE/50_theory_gate.py "
                         "(theory gate + 8-bit arrange); keep only those that pass")
    ap.add_argument("--gate-min-score", type=float, default=0.6)
    ap.add_argument("--gate-min-cos", type=float, default=None,
                    help="min cosine-to-corner for an enhanced candidate to pass")
    args = ap.parse_args()

    force = (args.force_drum or "").upper() == "TBB"
    tbb_loop = load_tbb_loop() if force else None
    if force:
        print(f"[force-drum] TBB enforced: {len(tbb_loop[0])} drum events, loop={tbb_loop[1]} ticks")

    all_cands = []
    base = 0.0
    tgt = None
    if args.like_md5:
        spec = pick_like(args.like_md5, args.like_neighbors, args.empty_bias, args.like_caption)
        cs, b, cap, tgt = generate_corner(
            None, None, force, args.diatonic, tbb_loop, args.target,
            phrase_level=args.phrase_level, n_candidates=args.n_candidates,
            min_bars=args.min_bars, max_bars=args.max_bars,
            min_slots=args.min_slots, max_slots=args.max_slots, seed=args.seed, spec=spec,
            coherent=args.coherent_slots)
        all_cands += cs
        base = max(base, b)
    else:
        ranks = ([int(x) for x in args.ranks.split(",")] if args.ranks else [args.rank])
        for rk in ranks:
            cs, b, cap, tgt = generate_corner(
                rk, args.corner_caption, force, args.diatonic, tbb_loop, args.target,
                phrase_level=args.phrase_level, n_candidates=args.n_candidates,
                min_bars=args.min_bars, max_bars=args.max_bars,
                min_slots=args.min_slots, max_slots=args.max_slots, seed=args.seed,
                coherent=args.coherent_slots)
            all_cands += cs
            base = max(base, b)
    if not all_cands:
        raise SystemExit("no candidates produced")
    cap = all_cands[0]["cap"]
    slug = re.sub(r"[^a-z0-9]+", "_", cap.lower())[:40].strip("_")
    outdir = os.path.join(OUTBASE, "tbb_birth" if force else slug)
    df = pd.DataFrame(all_cands).sort_values("cos", ascending=False).reset_index(drop=True)
    # corner-novelty objective: close to the corner, far from any single donor
    if "donor_sim" in df.columns:
        df["novelty_score"] = (df.cos - args.novelty_weight * df.donor_sim).round(4)
    else:
        df["novelty_score"] = df.cos
    if force:
        print(f"[force-drum] {int(df.tbb.sum())}/{len(df)} candidates carry the TBB drum layer")
    # proxy-beauty gate, but never return empty; KEEP by the novelty objective
    good = df[(df.diatonic >= args.diatonic) & (df.has_melody)]
    ranked = (good if len(good) else df).sort_values(
        "novelty_score", ascending=False).head(args.keep)
    n = len(df)
    os.makedirs(outdir, exist_ok=True)
    csv = os.path.join(outdir, "candidates.csv")
    df.to_csv(csv, index=False)
    print(f"\n[generated] {n} candidates -> {outdir}")
    cols = [c for c in ["name", "cos", "donor_sim", "novelty_score", "diatonic", "has_melody"]
            if c in df.columns]
    print(f"[best] cos-to-corner top5:\n{df.head(5)[cols].to_string(index=False)}")
    print(f"[kept] top {len(ranked)} by corner-novelty (cos - {args.novelty_weight}*donor_sim):\n"
          f"{ranked[cols].to_string(index=False)}")
    beat = (df.cos > base).sum()
    print(f"[result] {beat}/{n} candidates beat the best real donor ({base:.4f}); "
          f"top {df.cos.iloc[0]:.4f}")
    if "donor_sim" in df.columns:
        kept_ds = ranked["donor_sim"]
        print(f"[novelty] donor_sim (max cosine to ANY single donor; lower=newer): "
              f"all mean={df.donor_sim.mean():.4f} min={df.donor_sim.min():.4f} | "
              f"kept mean={kept_ds.mean():.4f} min={kept_ds.min():.4f}  "
              f"(nearest real donor↔corner baseline cos={base:.4f})")

    # prune non-kept candidate MIDIs by absolute path (corners live in sub-slugs)
    keep_paths = set(ranked.path)
    for p in df.path:
        if p not in keep_paths and os.path.exists(p):
            os.remove(p)

    # ---- theory gate + 8-bit enhancement (Task-2 route, behind --enhance) ----
    enhanced_rows = None
    if args.enhance != "off":
        enhanced_rows = enhance_kept(ranked, cap, args.enhance,
                                     args.gate_min_score, args.gate_min_cos, tgt)
        gcsv = os.path.join(outdir, "candidates_gated.csv")
        pd.DataFrame(enhanced_rows).to_csv(gcsv, index=False)
        n_pass = sum(r["passed"] for r in enhanced_rows)
        print(f"\n[gate] mode={args.enhance}: {n_pass}/{len(enhanced_rows)} enhanced "
              f"candidates passed (min_score={args.gate_min_score}, "
              f"min_cos={args.gate_min_cos}) -> {gcsv}")

    if args.no_audio:
        return
    group = args.group or (f"style_{args.like_md5[:8]}" if args.like_md5
                           else "tbb_birth30" if force else f"generated_{slug[:20]}")

    if enhanced_rows is not None:
        # render ENHANCED passing files (fallback to best-quality if none passed)
        passing = [r for r in enhanced_rows if r["passed"] and r.get("enhanced_path")]
        if not passing:
            passing = sorted([r for r in enhanced_rows if r.get("enhanced_path")],
                             key=lambda r: r["quality_score"], reverse=True)[:1]
            if passing:
                print("[gate] none passed; auditioning best-quality enhanced candidate")
        passing = sorted(passing, key=lambda r: (r.get("cosine") or 0, r["quality_score"]),
                         reverse=True)
        for i, r in enumerate(reversed(passing), 1):
            wav = r["enhanced_path"].replace(".mid", ".wav")
            subprocess.run(["fluidsynth", "-ni", "-F", wav, SF2, r["enhanced_path"]],
                           check=False, capture_output=True)
            if os.path.exists(wav):
                rank_i = len(passing) - i + 1
                cs = f"{r['cosine']:.3f}" if r.get("cosine") is not None else "n/a"
                subprocess.run(["webplayer", "add", wav, "--group", group,
                                "--label", f"#{rank_i} {args.enhance} cos{cs} q{r['quality_score']:.2f}",
                                "--desc", f"{cap} | key={r['detected_key']} grade={r['grade']}"],
                               check=False, capture_output=True)
        subprocess.run(["webplayer", "open"], check=False, capture_output=True)
        st = subprocess.run(["webplayer", "status"], capture_output=True, text=True)
        print(f"[webplayer] group '{group}': {len(passing)} enhanced tracks\n{st.stdout.strip()}")
        return

    # render kept candidates + load into webplayer (REVERSE so rank #1 is newest)
    rows = list(ranked.itertuples())
    for i, r in enumerate(reversed(rows), 1):
        wav = r.path.replace(".mid", ".wav")
        subprocess.run(["fluidsynth", "-ni", "-F", wav, SF2, r.path],
                       check=False, capture_output=True)
        if os.path.exists(wav):
            rank_i = len(rows) - i + 1
            subprocess.run(["webplayer", "add", wav, "--group", group,
                            "--label", f"#{rank_i} cos{r.cos:.3f} d{r.drums}/m{r.melody}/h{r.harmony}",
                            "--desc", f"{cap} | diatonic={r.diatonic:.2f}"],
                           check=False, capture_output=True)
    subprocess.run(["webplayer", "open"], check=False, capture_output=True)
    st = subprocess.run(["webplayer", "status"], capture_output=True, text=True)
    print(f"[webplayer] group '{group}': {len(rows)} tracks\n{st.stdout.strip()}")


if __name__ == "__main__":
    main()
