#!/usr/bin/env python3
"""genre_engine.py — turn coherent musical material into a GENRE-IDIOMATIC song.

This is the "style skin" layer used by the unified generator (50_generate.py
--style ...). The recombination / remix machinery (50_generate.py, 51_remix.py)
produces a musically COHERENT skeleton (melody + harmony/keys + bass + drums,
key-aware, bar-aligned). This module RE-SKINS that skeleton into a requested
style — death metal, rap/trap, chiptune, lo-fi, house, etc. — by changing the
five things that actually carry genre in a General-MIDI render:

  1. TEMPO            — each genre has a felt-BPM home (death metal ~196, rap ~88…)
  2. MODE / SCALE     — snap tonal notes to the genre's scale (metal→phrygian/minor)
  3. INSTRUMENTS      — GM program per role (distortion gtr, 808, square lead, EP…)
  4. DRUMS            — a generated, idiomatic kit pattern (blast beat, trap hats,
                        boom-bap, four-on-floor) tiled with fills + dynamics
  5. ROLE RHYTHM      — per-role transforms: tremolo picking, palm-mute chug,
                        arpeggios, 808 glides, hi-hat rolls, chord stabs

Everything is 100% symbolic (events in -> events out at COMMON_TPB); audio is
only the final fluidsynth render done by the caller. The skeleton stays
musically intact (same key, same chord grid, same phrase structure) so the
genred result sounds like a real song in that style, not a random swap.

Genre is parsed from free text (`profile_for("death metal with blast beats")`)
so the user can describe a style in their own words; keyword modifiers
("blast beats", "half-time", "tremolo", "fast", "dark") tweak the base profile.
"""
from __future__ import annotations

import os
import re
import sys
from importlib import util as _u

import numpy as np

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)


def _load(modfile, name):
    spec = _u.spec_from_file_location(name, os.path.join(CODE, modfile))
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


G = _load("50_generate.py", "gen50")          # stems / write / fit / embed / TBB
TG = G._gate_mod()                              # 50_theory_gate (key / scale / snap)
_S = G._S                                       # 49_sig_one (parser + vector)
_m25 = _S._m25                                  # 25_harmony_refine (estimate_chord/TEMPLATES)

COMMON_TPB = G.COMMON_TPB                       # 480
BAR_TICKS = G.BAR_TICKS                         # 1920 (4/4)
STEP = COMMON_TPB // 4                          # 120 ticks = 1/16 note

# ----------------------------- scales --------------------------------------
MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)                 # natural minor / aeolian
PHRYGIAN = (0, 1, 3, 5, 7, 8, 10)              # metal's darkest mode (b2)
PHRYG_DOM = (0, 1, 4, 5, 7, 8, 10)             # phrygian dominant (flamenco/metal)
DORIAN = (0, 2, 3, 5, 7, 9, 10)
HARM_MINOR = (0, 2, 3, 5, 7, 8, 11)
PENT_MINOR = (0, 3, 5, 7, 10)

SCALES = {"major": MAJOR, "minor": MINOR, "phrygian": PHRYGIAN,
          "phrygian_dominant": PHRYG_DOM, "dorian": DORIAN,
          "harmonic_minor": HARM_MINOR, "pentatonic_minor": PENT_MINOR}

# ----------------------------- GM drum pitches -----------------------------
KICK, KICK2 = 36, 35
SNARE, RIM, CLAP = 38, 37, 39
CHH, PHH, OHH = 42, 44, 46            # closed / pedal / open hat
LTOM, MTOM, HTOM = 45, 47, 50
CRASH, RIDE, RIDEB, CHINA = 49, 51, 53, 52
TAMB, COWBELL = 54, 56

# ----------------------------- GM program numbers --------------------------
P = dict(
    square=80, pulse=80, saw=81, calliope=82, chiff=83, charang=84,
    epiano=4, epiano2=5, piano=0, clav=7, organ=18, harpsi=6,
    nylon=24, steel=25, jazzgtr=26, cleangtr=27, mutegtr=28,
    overdrive=29, distortion=30, harmonics=31,
    acbass=32, fingerbass=33, pickbass=34, fretless=35,
    synbass=38, synbass2=39, slapbass=36,
    strings=48, ensemble=49, synstrings=50, pad_warm=89, pad_poly=90,
    pad_sweep=95, pad_halo=94, pad_new=88, pad_bowed=92,
    lead_saw=81, lead_square=80, lead_voice=85, lead_5th=86, bass_lead=87,
    bell=14, glock=9, vibes=11, marimba=12, music_box=10, kalimba=108,
    sitar=104, brass=61, synbrass=62, sax=66, flute=73, choir=52, voice_oohs=53,
)


# =========================================================================
#                              GENRE PROFILES
# =========================================================================
# Each profile is a dict of knobs consumed by restyle(). Missing keys fall back
# to sensible defaults. `drums` names a generator in DRUM_PATTERNS below.
def _base():
    return dict(
        bpm=None,                 # None -> keep skeleton bpm
        bpm_mult=1.0,             # multiply skeleton bpm (used if bpm is None)
        mode=None,                # None -> keep detected mode; else force scale name
        prog_melody=P["square"], prog_keys=P["epiano"], prog_bass=P["fingerbass"],
        mel_transform="keep",     # keep|tremolo|arp|octave_up|octave_down|thin|stab
        keys_transform="sustain", # sustain|powerchord|arp|stab|pad|drop
        bass_transform="root",    # root|chug|808|octaves|walk|drop|keep
        drums="rock",             # key into DRUM_PATTERNS
        drum_intensity=1.0,       # scales velocities / density
        mel_octave=0, keys_octave=0, bass_octave=0,
        mel_vel=96, keys_vel=78, bass_vel=92,
        humanize=0.0,             # 0..1 timing/velocity jitter
        swing=0.0,                # 0..1 push of the off-8ths
        snap_strength=1.0,        # 1 = full mode snap of tonal notes
        keep_drums=False,         # True -> keep skeleton drums instead of generating
    )


def _profiles():
    prof = {}

    dm = _base(); dm.update(
        bpm=196, mode="phrygian", prog_melody=P["distortion"], prog_keys=P["overdrive"],
        prog_bass=P["pickbass"], mel_transform="tremolo", keys_transform="powerchord",
        bass_transform="chug", drums="blast", mel_octave=0, keys_octave=-12,
        bass_octave=-12, mel_vel=110, keys_vel=104, bass_vel=108, snap_strength=1.0)
    prof["death_metal"] = dm

    bm = dict(dm); bm.update(
        bpm=210, prog_keys=P["distortion"], mel_transform="tremolo",
        keys_transform="powerchord", drums="blast", keys_octave=0, mel_octave=12,
        mel_vel=104, keys_vel=96)
    prof["black_metal"] = bm

    th = _base(); th.update(
        bpm=150, mode="minor", prog_melody=P["overdrive"], prog_keys=P["distortion"],
        prog_bass=P["pickbass"], mel_transform="keep", keys_transform="powerchord",
        bass_transform="chug", drums="dbeat", keys_octave=-12, bass_octave=-12,
        mel_vel=104, keys_vel=102, bass_vel=104)
    prof["thrash_metal"] = th

    mt = _base(); mt.update(
        bpm=140, mode="minor", prog_melody=P["distortion"], prog_keys=P["overdrive"],
        prog_bass=P["pickbass"], keys_transform="powerchord", bass_transform="chug",
        drums="metal", keys_octave=-12, bass_octave=-12, mel_vel=104, keys_vel=100)
    prof["metal"] = mt

    rk = _base(); rk.update(
        bpm=130, prog_melody=P["overdrive"], prog_keys=P["cleangtr"],
        prog_bass=P["fingerbass"], keys_transform="powerchord", bass_transform="octaves",
        drums="rock", mel_vel=100, keys_vel=86)
    prof["rock"] = rk

    rap = _base(); rap.update(
        bpm=88, mode="minor", prog_melody=P["epiano2"], prog_keys=P["epiano"],
        prog_bass=P["synbass"], mel_transform="thin", keys_transform="sustain",
        bass_transform="808", drums="boombap", swing=0.18, mel_octave=0,
        bass_octave=0, mel_vel=82, keys_vel=70, bass_vel=104, humanize=0.18)
    prof["rap"] = rap

    bb = dict(rap); bb.update(bpm=92, drums="boombap", prog_keys=P["piano"], swing=0.22)
    prof["boom_bap"] = bb
    prof["hip_hop"] = dict(rap)

    trap = _base(); trap.update(
        bpm=140, mode="phrygian", prog_melody=P["bell"], prog_keys=P["pad_warm"],
        prog_bass=P["synbass"], mel_transform="thin", keys_transform="sustain",
        bass_transform="808", drums="trap", mel_octave=12, bass_octave=0,
        mel_vel=86, keys_vel=64, bass_vel=110)
    prof["trap"] = trap

    drill = dict(trap); drill.update(bpm=144, drums="trap", bass_transform="808",
                                     mode="harmonic_minor")
    prof["drill"] = drill

    chip = _base(); chip.update(
        bpm=150, prog_melody=P["square"], prog_keys=P["pulse"], prog_bass=P["synbass"],
        mel_transform="octave_up", keys_transform="arp", bass_transform="octaves",
        drums="chip", mel_vel=100, keys_vel=82, bass_vel=92)
    prof["chiptune"] = chip
    prof["8bit"] = dict(chip)

    lofi = _base(); lofi.update(
        bpm=78, prog_melody=P["epiano"], prog_keys=P["epiano2"], prog_bass=P["acbass"],
        mel_transform="keep", keys_transform="sustain", bass_transform="walk",
        drums="lofi", swing=0.28, mel_vel=74, keys_vel=62, bass_vel=80,
        humanize=0.3, mel_octave=0)
    prof["lofi"] = lofi
    prof["lo_fi"] = dict(lofi)

    house = _base(); house.update(
        bpm=124, prog_melody=P["saw"], prog_keys=P["pad_poly"], prog_bass=P["synbass"],
        mel_transform="keep", keys_transform="stab", bass_transform="octaves",
        drums="fourfloor", mel_vel=96, keys_vel=80, bass_vel=96)
    prof["house"] = house
    prof["edm"] = dict(house)

    elec = _base(); elec.update(
        bpm=120, prog_melody=P["saw"], prog_keys=P["pad_sweep"], prog_bass=P["synbass"],
        mel_transform="arp", keys_transform="pad", bass_transform="octaves",
        drums="fourfloor", mel_vel=92, keys_vel=72, bass_vel=92)
    prof["electronic"] = elec

    amb = _base(); amb.update(
        bpm=84, prog_melody=P["pad_halo"], prog_keys=P["pad_warm"], prog_bass=P["pad_bowed"],
        mel_transform="keep", keys_transform="pad", bass_transform="root",
        drums="none", mel_vel=70, keys_vel=58, bass_vel=64, mel_octave=0)
    prof["ambient"] = amb
    prof["gradual_electronic"] = dict(elec, drums="fourfloor", keys_transform="pad",
                                      mel_transform="arp", bpm=118)

    pop = _base(); pop.update(
        bpm=116, prog_melody=P["saw"], prog_keys=P["piano"], prog_bass=P["fingerbass"],
        keys_transform="stab", bass_transform="octaves", drums="pop",
        mel_vel=96, keys_vel=80)
    prof["pop"] = pop

    funk = _base(); funk.update(
        bpm=104, prog_melody=P["clav"], prog_keys=P["clav"], prog_bass=P["slapbass"],
        keys_transform="stab", bass_transform="octaves", drums="funk", swing=0.12,
        mel_vel=96, keys_vel=84, bass_vel=100, humanize=0.15)
    prof["funk"] = funk

    jazz = _base(); jazz.update(
        bpm=120, prog_melody=P["vibes"], prog_keys=P["piano"], prog_bass=P["acbass"],
        keys_transform="sustain", bass_transform="walk", drums="jazz", swing=0.3,
        mel_vel=82, keys_vel=70, bass_vel=82, humanize=0.2)
    prof["jazz"] = jazz

    return prof


GENRE_PROFILES = _profiles()

# free-text keyword -> canonical genre key (first match wins, longer phrases first)
_ALIASES = [
    ("death metal", "death_metal"), ("black metal", "black_metal"),
    ("thrash", "thrash_metal"), ("djent", "metal"), ("metalcore", "metal"),
    ("doom", "metal"), ("metal", "metal"),
    ("boom bap", "boom_bap"), ("boombap", "boom_bap"), ("hip hop", "hip_hop"),
    ("hip-hop", "hip_hop"), ("rap", "rap"), ("drill", "drill"), ("trap", "trap"),
    ("chiptune", "chiptune"), ("chip tune", "chiptune"), ("8 bit", "8bit"),
    ("8-bit", "8bit"), ("8bit", "8bit"), ("nes", "chiptune"), ("gameboy", "chiptune"),
    ("lo-fi", "lo_fi"), ("lofi", "lofi"), ("lo fi", "lo_fi"),
    ("house", "house"), ("edm", "edm"), ("techno", "house"),
    ("gradual electronic", "gradual_electronic"), ("ambient", "ambient"),
    ("electronic", "electronic"), ("synthwave", "electronic"),
    ("funk", "funk"), ("jazz", "jazz"), ("rock", "rock"), ("punk", "rock"),
    ("pop", "pop"),
]


def profile_for(style_text: str):
    """Parse a free-text style string -> (genre_key, profile dict, label).

    Picks the base genre by keyword, then applies modifiers found in the text
    (blast beats, half-time, fast/slow, tremolo, dark, swing) so the user can
    describe a style in their own words."""
    t = (style_text or "").lower().strip()
    genre = "pop"
    for kw, key in _ALIASES:
        if kw in t:
            genre = key
            break
    prof = dict(GENRE_PROFILES.get(genre, GENRE_PROFILES["pop"]))

    # ---- text modifiers ----
    if "blast beat" in t or "blastbeat" in t or "blast" in t:
        prof["drums"] = "blast"
    if "double bass" in t or "double kick" in t:
        prof["drums"] = "blast" if prof["drums"] in ("blast",) else "metal"
    if "half-time" in t or "half time" in t or "halftime" in t:
        prof["drums"] = "trap" if "trap" not in prof["drums"] else prof["drums"]
    if "four on the floor" in t or "four-on-the-floor" in t or "4 on the floor" in t:
        prof["drums"] = "fourfloor"
    if ("open hat" in t or "openhat" in t or "seed groove" in t or "that beat" in t
            or "16th hat" in t):
        prof["drums"] = "openhat"
    if "tremolo" in t:
        prof["mel_transform"] = "tremolo"
    if "arp" in t or "arpegg" in t:
        prof["keys_transform"] = "arp"
    if "swing" in t or "shuffle" in t:
        prof["swing"] = max(prof.get("swing", 0.0), 0.25)
    if "dark" in t or "evil" in t or "brutal" in t:
        prof["mode"] = "phrygian"
    if "minor" in t:
        prof["mode"] = prof.get("mode") or "minor"
    if "major" in t or "happy" in t or "uplifting" in t:
        prof["mode"] = "major"
    # tempo words / explicit bpm
    m = re.search(r"(\d{2,3})\s*bpm", t)
    if m:
        prof["bpm"] = float(m.group(1))
    elif "fast" in t or "uptempo" in t:
        prof["bpm"] = (prof["bpm"] or 120) * 1.25
    elif "slow" in t or "downtempo" in t:
        prof["bpm"] = (prof["bpm"] or 120) * 0.8

    return genre, prof, genre.replace("_", " ")


# =========================================================================
#                          DRUM PATTERN GENERATORS
# =========================================================================
# Each returns a 1-bar list of (start, dur, 9, pitch, vel). Tiled by gen_drums.
def _hit(step, pitch, vel, dur=STEP):
    return (step * STEP, dur, 9, pitch, int(max(1, min(127, vel))))


def _blast(rng):
    """True blast beat: kick+snare alternating 16ths, ride/hat every 16th, crash 1."""
    evs = [_hit(0, CRASH, 118, STEP * 2)]
    for s in range(16):
        evs.append(_hit(s, KICK if s % 2 == 0 else SNARE, 112 if s % 2 == 0 else 104))
        evs.append(_hit(s, RIDE if s % 4 == 0 else CHH, 84))
    return evs


def _dbeat(rng):
    """D-beat / punk-metal: driving kick, snare 2&4, 8th hats."""
    evs = [_hit(0, CRASH, 110, STEP * 2)]
    for s in (0, 3, 6, 8, 11, 14):
        evs.append(_hit(s, KICK, 110))
    for s in (4, 12):
        evs.append(_hit(s, SNARE, 112))
    for s in range(0, 16, 2):
        evs.append(_hit(s, CHH, 80))
    return evs


def _metal(rng):
    """Mid-tempo metal: double-kick gallops, snare 2&4, ride 8ths."""
    evs = [_hit(0, CRASH, 108, STEP * 2)]
    for s in (0, 1, 3, 4, 6, 8, 9, 11, 12, 14):
        evs.append(_hit(s, KICK, 104))
    for s in (4, 12):
        evs.append(_hit(s, SNARE, 114))
    for s in range(0, 16, 2):
        evs.append(_hit(s, RIDE, 82))
    return evs


def _rock(rng):
    evs = [_hit(0, KICK, 108), _hit(4, SNARE, 110), _hit(8, KICK, 104),
           _hit(10, KICK, 96), _hit(12, SNARE, 110)]
    for s in range(0, 16, 2):
        evs.append(_hit(s, CHH, 76 + (8 if s % 4 == 0 else 0)))
    return evs


def _pop(rng):
    evs = [_hit(0, KICK, 104), _hit(4, SNARE, 108), _hit(10, KICK, 98),
           _hit(12, SNARE, 108)]
    for s in range(0, 16, 2):
        evs.append(_hit(s, CHH, 72))
    return evs


def _boombap(rng):
    """Boom-bap: punchy kick on 1 + syncopated, fat snare on 2&4, swung hats, ghosts."""
    evs = [_hit(0, KICK, 112), _hit(3, KICK, 88), _hit(8, KICK, 106), _hit(11, KICK, 84)]
    evs += [_hit(4, SNARE, 116), _hit(12, SNARE, 116)]
    for s in range(0, 16, 2):
        v = 64 + (10 if s % 4 == 0 else 0)
        evs.append(_hit(s, CHH, v))
    evs.append(_hit(7, CHH, 52))    # ghost
    return evs


def _openhat(rng):
    """The seed-song groove (track 'enhanced_phr_35_n5_m1a45', user ear-confirmed,
    verified against its MIDI). Straight 16ths, per beat = `K+hat · hat · Ohat · Ohat`:

        Kh  h  O O   KSh  h  O O   Kh  h  O O   KSh  h  O O

    kick on beats 1&3, kick+snare backbeat on 2&4, closed hat on the first two
    16ths of each beat and an OPEN hat on the last two — the 'tss-tss' lift that
    gives this groove its bounce."""
    out = []
    for beat in range(4):
        b0 = beat * 4
        backbeat = beat in (1, 3)
        out.append((b0 * STEP, STEP, 9, KICK, 110))
        out.append((b0 * STEP, STEP, 9, CHH, 80))
        if backbeat:
            out.append((b0 * STEP, STEP, 9, SNARE, 116))
        out.append(((b0 + 1) * STEP, STEP, 9, CHH, 66))
        out.append(((b0 + 2) * STEP, STEP, 9, OHH, 74))
        out.append(((b0 + 3) * STEP, STEP, 9, OHH, 70))
    return out


def _trap(rng):
    """Trap: half-time snare/clap on 3, syncopated 808 kick, hat rolls + triplets."""
    evs = [_hit(0, KICK, 112), _hit(6, KICK, 96), _hit(10, KICK, 100)]
    evs.append(_hit(8, CLAP, 116)); evs.append(_hit(8, SNARE, 96))   # backbeat on '3'
    # hats: steady 8ths with a couple of fast rolls
    for s in range(0, 16):
        if s % 2 == 0:
            evs.append(_hit(s, CHH, 70 + (8 if s % 4 == 0 else 0)))
    # 1/32 roll on the last beat
    for k in range(4):
        evs.append((14 * STEP + k * (STEP // 2), STEP // 2, 9, CHH, 60 + k * 6))
    # triplet roll mid-bar sometimes
    if rng.random() < 0.5:
        for k in range(3):
            evs.append((6 * STEP + k * (STEP * 2 // 3), STEP * 2 // 3, 9, CHH, 66))
    evs.append(_hit(0, OHH, 70))
    return evs


def _fourfloor(rng):
    """House/EDM four-on-the-floor: kick every beat, clap 2&4, offbeat open hats."""
    evs = []
    for b in range(4):
        evs.append(_hit(b * 4, KICK, 112))
    evs += [_hit(4, CLAP, 100), _hit(12, CLAP, 100)]
    for s in range(2, 16, 4):           # the 'and' of each beat
        evs.append(_hit(s, OHH, 82))
    for s in range(0, 16, 2):
        evs.append(_hit(s, CHH, 64))
    return evs


def _lofi(rng):
    """Lo-fi: soft swung boom-bap, laid-back, ghosted, low velocity."""
    evs = [_hit(0, KICK, 90), _hit(8, KICK, 80)]
    evs += [_hit(4, SNARE, 92), _hit(12, SNARE, 90)]
    for s in range(0, 16, 2):
        evs.append(_hit(s, CHH, 50 + (6 if s % 4 == 0 else 0)))
    evs.append(_hit(7, SNARE, 40))      # ghost snare
    return evs


def _funk(rng):
    evs = [_hit(0, KICK, 108), _hit(6, KICK, 92), _hit(10, KICK, 96)]
    evs += [_hit(4, SNARE, 112), _hit(12, SNARE, 112)]
    evs.append(_hit(2, SNARE, 44)); evs.append(_hit(14, SNARE, 48))   # ghosts
    for s in range(0, 16):
        if s % 2 == 0 or rng.random() < 0.3:
            evs.append(_hit(s, CHH, 60 + (s % 3) * 6))
    return evs


def _jazz(rng):
    """Jazz swing ride pattern + hat on 2&4."""
    evs = []
    for b in range(4):
        evs.append(_hit(b * 4, RIDE, 78))
        if b % 2 == 1:
            evs.append((b * 4 * STEP + STEP * 8 // 3, STEP, 9, RIDE, 66))
    evs += [_hit(4, PHH, 70), _hit(12, PHH, 70)]
    return evs


def _none(rng):
    return [_hit(0, CHH, 40)]


DRUM_PATTERNS = {
    "blast": _blast, "dbeat": _dbeat, "metal": _metal, "rock": _rock, "pop": _pop,
    "boombap": _boombap, "openhat": _openhat, "trap": _trap, "fourfloor": _fourfloor,
    "lofi": _lofi, "funk": _funk, "jazz": _jazz, "none": _none,
}


# ---- custom beat strings -------------------------------------------------
# one token per step (single char OR a (group) of simultaneous hits); the bar is
# divided into len(tokens) equal steps. Rests: . - _ space.
_BEATCHARS = {"b": KICK, "k": KICK, "d": KICK, "s": SNARE, "n": SNARE,
              "h": CHH, "c": CRASH, "o": OHH, "p": CLAP, "r": RIDE, "t": MTOM,
              "m": TAMB, "w": COWBELL}
_BEATVEL = {KICK: 110, SNARE: 116, CHH: 78, OHH: 76, CLAP: 112, CRASH: 116,
            RIDE: 80, MTOM: 96, TAMB: 70, COWBELL: 90}


_NICE_STEPS = (8, 12, 16, 24, 32)


def parse_beat(spec, snap=True):
    """Parse a beat string -> (one-bar events, n_steps). Tokens are single chars
    (b=kick s=snare h=hat o=open-hat p=clap c=crash r=ride t=tom, .=rest) or a
    parenthesized group of simultaneous hits e.g. '(hk)'. The bar is split into
    len(tokens) equal steps. If `snap` and the token count isn't a clean grid
    (8/12/16/24/32), it's trimmed/padded (with rests) to the nearest so the
    pattern locks to 4/4. Returns ([] , 0) if nothing parseable."""
    toks, i = [], 0
    s = spec.strip()
    while i < len(s):
        ch = s[i]
        if ch == "(":
            j = s.find(")", i)
            if j < 0:
                j = len(s)
            toks.append(s[i + 1:j])
            i = j + 1
        elif ch in " ":
            i += 1
        else:
            toks.append(ch)
            i += 1
    n = len(toks)
    if n == 0:
        return [], 0
    if snap and n not in _NICE_STEPS:
        tgt = min(_NICE_STEPS, key=lambda g: abs(g - n))
        if n > tgt:
            toks = toks[:tgt]
        else:
            toks = toks + ["."] * (tgt - n)
        n = tgt
    step = BAR_TICKS / n
    out = []
    for k, tok in enumerate(toks):
        t0 = int(round(k * step))
        dur = max(1, int(round(step)))
        for c in tok.lower():
            if c in ".-_":
                continue
            pit = _BEATCHARS.get(c)
            if pit is not None:
                out.append((t0, dur, 9, pit, _BEATVEL.get(pit, 90)))
    return out, n


# named PT beats (mirror the drum-pad presets) usable as --beat <name>
NAMED_BEATS = {
    "compton": "KHKHSHHSHS(KO)KSHOS",
    "tbb": "(HK).(Hs)(KO)..(KSH)..(K.s)(KO)..(KS)..(Hs)",
    "getobeatrap1": "KHKHSHHHKHKKHSHH",
    "seedgroove": "(HK)HOO(HKS)HOO(HK)HOO(HKS)HOO",
}


def resolve_beat(spec):
    """Resolve a --beat value -> ('pattern', name) | ('custom', bar, n) | ('none',).
    Order: registered generator name, then named PT beat, then raw beat string."""
    s = (spec or "").strip()
    if s in DRUM_PATTERNS:
        return ("pattern", s)
    if s.lower() in NAMED_BEATS:
        bar, n = parse_beat(NAMED_BEATS[s.lower()])
        return ("custom", bar, n, s.lower())
    bar, n = parse_beat(s)
    if bar:
        return ("custom", bar, n, "custom")
    return ("none",)


def tile_bar(bar_events, total_bars, rng, intensity=1.0, energy=None, crash=True):
    """Tile a fixed one-bar pattern across total_bars (energy scales velocity,
    crash accent on section/song start)."""
    out = []
    for b in range(total_bars):
        off = b * BAR_TICKS
        e = 1.0 if energy is None else float(0.65 + 0.45 * energy[min(b, len(energy) - 1)])
        sc = intensity * e
        for s, d, ch, p, v in bar_events:
            out.append((s + off, d, ch, p, int(max(1, min(127, round(v * sc))))))
        if crash and b % 8 == 0:
            out.append((off, STEP, 9, CRASH, 112))
    return out


def _fill(style, rng):
    """A 1-bar drum fill (snare/tom roll) to cap a section."""
    evs = []
    seq = [SNARE, SNARE, MTOM, MTOM, LTOM, LTOM, HTOM, SNARE]
    for i, s in enumerate(range(8, 16)):
        evs.append(_hit(s, seq[i % len(seq)], 96 + i * 2))
    evs += [_hit(0, KICK, 104), _hit(4, SNARE, 100)]
    evs.append(_hit(0, CHH, 70))
    return evs


def gen_drums(style, total_bars, rng, intensity=1.0, fills=True, energy=None):
    """Tile a genre drum loop across total_bars, crash on section starts, fill the
    last bar of every 4-bar group. `energy` (per-bar 0..1) scales velocity so the
    kit follows the song's dynamics. Returns events at COMMON_TPB."""
    gen = DRUM_PATTERNS.get(style, _rock)
    out = []
    for b in range(total_bars):
        off = b * BAR_TICKS
        last_of_group = fills and (b % 4 == 3) and (b != total_bars - 1) and style not in ("none",)
        bar = _fill(style, rng) if last_of_group else gen(rng)
        e = 1.0 if energy is None else float(0.6 + 0.5 * energy[min(b, len(energy) - 1)])
        scale = intensity * e
        for s, d, ch, p, v in bar:
            out.append((s + off, d, ch, p, int(max(1, min(127, round(v * scale))))))
    return out


# =========================================================================
#                          TONAL RESTYLE HELPERS
# =========================================================================
def _scale_set(tonic_pc, mode):
    return set((tonic_pc + s) % 12 for s in SCALES.get(mode, MINOR))


def _snap(events, allowed, strength=1.0, rng=None):
    """Snap tonal notes into the genre scale (drums untouched)."""
    out = []
    for s, d, ch, p, v in events:
        if ch == 9:
            out.append((s, d, ch, p, v)); continue
        if p % 12 not in allowed and strength > 0:
            np_ = TG.snap_pitch(p, allowed)
            p = np_
        out.append((s, d, ch, p, v))
    return out


def _oct(events, semis):
    if not semis:
        return events
    return [(s, d, ch, max(0, min(127, p + semis)) if ch != 9 else p, v)
            for (s, d, ch, p, v) in events]


def _mono(events):
    """One note (top) per onset, sorted — collapse a melody to a clean line."""
    by = {}
    for s, d, ch, p, v in events:
        if s not in by or p > by[s][3]:
            by[s] = (s, d, ch, p, v)
    return [by[k] for k in sorted(by)]


# ---- melody transforms ----
def mel_keep(mel, **k):
    return mel


def mel_tremolo(mel, rng=None, **k):
    """Tremolo picking: subdivide each note into fast 16th repeats (metal lead)."""
    out = []
    for s, d, ch, p, v in _mono(mel):
        n = max(1, d // STEP)
        for i in range(n):
            out.append((s + i * STEP, STEP, ch, p, int(v * (0.85 if i % 2 else 1.0))))
    return out


def mel_thin(mel, rng=None, **k):
    """Keep the structurally strong notes (downbeats / longer) — sparse topline."""
    mono = _mono(mel)
    out = []
    for s, d, ch, p, v in mono:
        beat = (s % BAR_TICKS) / COMMON_TPB
        on_strong = abs(beat - round(beat)) < 0.06
        if on_strong or d >= COMMON_TPB:
            out.append((s, max(d, COMMON_TPB // 2), ch, p, v))
    return out or mono


def mel_octup(mel, **k):
    return _oct(_mono(mel), 12)


def mel_octdown(mel, **k):
    return _oct(_mono(mel), -12)


def mel_stab(mel, rng=None, **k):
    out = []
    for s, d, ch, p, v in _mono(mel):
        out.append((s, min(d, STEP * 2), ch, p, v))
    return out


MEL_TF = {"keep": mel_keep, "tremolo": mel_tremolo, "thin": mel_thin,
          "octave_up": mel_octup, "octave_down": mel_octdown, "stab": mel_stab}


# ---- keys / harmony transforms (chord-grid driven) ----
def _powerchord(cgrid, total_bars, octave=-12, vel=100, rhythm="chug", rng=None):
    """Root+5(+8) power chords following the chord grid; metal palm-mute chug."""
    out = []
    base = 48 + octave
    for b in range(total_bars):
        ch = cgrid[b] if b < len(cgrid) and cgrid[b] else None
        if not ch:
            continue
        root = base + (ch[0] - base) % 12
        notes = [root, root + 7, root + 12]
        off = b * BAR_TICKS
        if rhythm == "chug":
            pattern = [0, 1, 2, 3, 4, 6, 8, 9, 10, 11, 12, 14]   # gallop-ish 16ths
        elif rhythm == "eighths":
            pattern = list(range(0, 16, 2))
        else:
            pattern = [0]
        for s in pattern:
            for n in notes:
                out.append((off + s * STEP, STEP, 1, n, int(vel * (0.9 if s % 2 else 1.0))))
    return out


def _arp_keys(cgrid, total_bars, octave=0, vel=82, rng=None):
    out = []
    base = 60 + octave
    for b in range(total_bars):
        ch = cgrid[b] if b < len(cgrid) and cgrid[b] else None
        if not ch:
            continue
        pcs = sorted(ch[2]) if ch[2] else [0, 4, 7]
        notes = [base + ((pc - base) % 12) for pc in pcs]
        notes = notes + [n + 12 for n in notes]
        off = b * BAR_TICKS
        for i, s in enumerate(range(0, 16)):
            out.append((off + s * STEP, STEP, 1, notes[i % len(notes)], vel))
    return out


def _sustain_keys(cgrid, total_bars, octave=0, vel=78, stab=False, pad=False, rng=None):
    out = []
    base = 60 + octave
    for b in range(total_bars):
        ch = cgrid[b] if b < len(cgrid) and cgrid[b] else None
        if not ch:
            continue
        pcs = sorted(ch[2]) if ch[2] else [0, 4, 7]
        notes = [base + ((pc - base) % 12) for pc in pcs]
        off = b * BAR_TICKS
        if stab:                       # off-beat chord stabs (house/funk/pop)
            for s in (2, 6, 10, 14):
                for n in notes:
                    out.append((off + s * STEP, STEP * 2, 1, n, vel))
        elif pad:                      # one long swell per bar
            for n in notes:
                out.append((off, BAR_TICKS, 1, n, int(vel * 0.85)))
        else:                          # held block chord per bar
            for n in notes:
                out.append((off, BAR_TICKS, 1, n, vel))
    return out


def keys_restyle(cgrid, total_bars, transform, octave, vel, rng):
    if transform == "powerchord":
        return _powerchord(cgrid, total_bars, octave, vel, "chug", rng)
    if transform == "drop":
        return _powerchord(cgrid, total_bars, octave, vel, "whole", rng)
    if transform == "arp":
        return _arp_keys(cgrid, total_bars, octave, vel, rng)
    if transform == "stab":
        return _sustain_keys(cgrid, total_bars, octave, vel, stab=True, rng=rng)
    if transform == "pad":
        return _sustain_keys(cgrid, total_bars, octave, vel, pad=True, rng=rng)
    return _sustain_keys(cgrid, total_bars, octave, vel, rng=rng)


# ---- bass transforms (chord-grid driven) ----
def bass_restyle(cgrid, total_bars, transform, octave, vel, scale, rng):
    out = []
    base = 40 + octave
    for b in range(total_bars):
        ch = cgrid[b] if b < len(cgrid) and cgrid[b] else None
        if not ch:
            continue
        root = base + (ch[0] - base) % 12
        fifth = root + 7
        off = b * BAR_TICKS
        if transform == "chug":                      # metal 16th palm-mute root
            for s in [0, 1, 2, 3, 4, 6, 8, 9, 10, 11, 12, 14]:
                out.append((off + s * STEP, STEP, 2, root, int(vel * (0.9 if s % 2 else 1.0))))
        elif transform == "808":                     # long sub root with octave drop tail
            out.append((off, BAR_TICKS - STEP, 2, root - 12, vel))
            out.append((off + 12 * STEP, STEP * 2, 2, root, int(vel * 0.85)))
        elif transform == "octaves":                 # root-octave pumping 8ths
            for i, s in enumerate(range(0, 16, 2)):
                out.append((off + s * STEP, STEP * 2, 2, root if i % 2 == 0 else root + 12, vel))
        elif transform == "walk":                    # quarter-note walking (jazz/lofi)
            tones = [root, root + 3 if (root + 3) % 12 in scale else root + 4,
                     fifth, fifth + 2 if (fifth + 2) % 12 in scale else fifth + 1]
            for i, s in enumerate((0, 4, 8, 12)):
                out.append((off + s * STEP, STEP * 4, 2, tones[i % len(tones)], vel))
        else:                                        # root: one note per bar
            out.append((off, BAR_TICKS, 2, root, vel))
    return out


def _swing(events, amount):
    """Push off-8th onsets later by `amount`*half-an-8th for a shuffle feel."""
    if amount <= 0:
        return events
    push = int(amount * (STEP))      # up to one 16th late
    out = []
    for s, d, ch, p, v in events:
        pos = s % (STEP * 2)
        if pos == STEP:              # the off-8th
            s = s + push
        out.append((s, d, ch, p, v))
    return out


def _humanize(events, amount, rng):
    if amount <= 0:
        return events
    out = []
    tj = int(amount * 18)
    for s, d, ch, p, v in events:
        s2 = max(0, s + int(rng.integers(-tj, tj + 1)))
        v2 = int(max(1, min(127, v + rng.integers(-int(amount * 16), int(amount * 16) + 1))))
        out.append((s2, d, ch, p, v2))
    return out


# =========================================================================
#                              RESTYLE
# =========================================================================
def restyle(skel, prof, rng=None):
    """Re-skin a coherent skeleton into the genre profile. Returns (recipe, progs,
    bpm) where recipe = [drums, keys, bass, melody] event lists for G.write_midi."""
    rng = rng or np.random.default_rng(0)
    total_bars = skel["total_bars"]
    tonic = skel["tonic_pc"]
    mode = prof.get("mode") or skel["mode"]
    allowed = _scale_set(tonic, mode)
    cgrid = skel["cgrid"]

    # melody -> snap to scale, octave, transform
    mel = _mono(skel["melody"])
    mel = _snap(mel, allowed, prof.get("snap_strength", 1.0), rng)
    mel = _oct(mel, prof.get("mel_octave", 0))
    mel = MEL_TF.get(prof["mel_transform"], mel_keep)(mel, rng=rng)
    mel = [(s, d, 0, p, prof["mel_vel"] if v == 0 else int(0.5 * v + 0.5 * prof["mel_vel"]))
           for (s, d, ch, p, v) in mel]

    # keys / bass driven by the chord grid (always in the genre scale)
    keys = keys_restyle(cgrid, total_bars, prof["keys_transform"],
                        prof.get("keys_octave", 0), prof["keys_vel"], rng)
    # power chords (root+5) are consonant by construction — snapping breaks the
    # perfect fifth; only snap voiced/scalar comping (sustain/arp/stab/pad).
    if prof["keys_transform"] not in ("powerchord", "drop"):
        keys = _snap(keys, allowed, 1.0)
    bass = bass_restyle(cgrid, total_bars, prof["bass_transform"],
                        prof.get("bass_octave", 0), prof["bass_vel"], allowed, rng)

    # drums
    if prof.get("custom_bar"):
        drums = tile_bar(prof["custom_bar"], total_bars, rng,
                         intensity=prof.get("drum_intensity", 1.0),
                         energy=skel.get("energy"))
    elif prof.get("keep_drums") and skel.get("drums"):
        drums = skel["drums"]
    else:
        drums = gen_drums(prof["drums"], total_bars, rng,
                          intensity=prof.get("drum_intensity", 1.0),
                          energy=skel.get("energy"))

    # feel: swing + humanize on tonal+drums
    sw = prof.get("swing", 0.0)
    hu = prof.get("humanize", 0.0)
    mel, keys, bass = _swing(mel, sw), _swing(keys, sw), _swing(bass, sw)
    drums = _swing(drums, sw)
    if hu:
        mel = _humanize(mel, hu, rng); keys = _humanize(keys, hu, rng)
        drums = _humanize(drums, hu * 0.6, rng)

    progs = {0: prof["prog_melody"], 1: prof["prog_keys"], 2: prof["prog_bass"]}
    return [drums, keys, bass, mel], progs


# =========================================================================
#                        SKELETON + STRUCTURE
# =========================================================================
def _split_bass_keys(harmony):
    by = {}
    for e in harmony:
        by.setdefault(e[0], []).append(e)
    bass, keys = [], []
    for on, g in by.items():
        lo = min(g, key=lambda e: e[3])
        bass.append(lo)
        keys.extend(e for e in g if e is not lo)
    return bass, keys


def _bar_energy(drums, melody, total_bars):
    """Per-bar activity (note count) normalized 0..1 — drives drum dynamics."""
    e = np.zeros(total_bars)
    for s, d, ch, p, v in (drums + melody):
        b = int(s // BAR_TICKS)
        if 0 <= b < total_bars:
            e[b] += 1
    if e.max() > 0:
        e = e / e.max()
    return e


def skeleton_from_stems(melody, harmony, drums, want_bars=None):
    """Build a key-aware skeleton from raw role stems (events at COMMON_TPB)."""
    import importlib
    R = _remix()
    span = G._span_ticks(melody, harmony, drums)
    total_bars = max(1, int(np.ceil(span / BAR_TICKS)))
    tonic_pc, mode, scale = R.key_of(harmony + melody)
    cgrid = R.chord_grid(harmony + melody, total_bars)
    bass, keys = _split_bass_keys(harmony)
    skel = dict(melody=melody, harmony=harmony, bass=bass, keys=keys, drums=drums,
                tonic_pc=tonic_pc, mode=mode, scale=scale, cgrid=cgrid,
                total_bars=total_bars,
                energy=_bar_energy(drums, melody, total_bars))
    return skel


_REMIX = None


def _remix():
    global _REMIX
    if _REMIX is None:
        _REMIX = _load("51_remix.py", "remix51")
    return _REMIX


def arrange_catchy(skel, section_bars=4, rng=None, form=("A", "A", "B", "A")):
    """Make it catchy by REPETITION: pull the strongest `section_bars` window as a
    HOOK, build a contrasting B (the next window, or the hook up a 5th), and lay
    out a short verse/chorus FORM so the ear hears a returning hook. Everything is
    re-derived on the new bar grid (chord grid + per-section energy)."""
    rng = rng or np.random.default_rng(0)
    R = _remix()
    tb = skel["total_bars"]
    if tb <= section_bars:
        return skel
    # score each candidate window by melodic note density (busier = hookier)
    mel = skel["melody"]
    best_b, best_score = 0, -1
    for start in range(0, max(1, tb - section_bars + 1)):
        t0, t1 = start * BAR_TICKS, (start + section_bars) * BAR_TICKS
        score = sum(1 for s, d, ch, p, v in mel if t0 <= s < t1)
        if score > best_score:
            best_score, best_b = score, start

    def _win(events, start, n):
        t0, t1 = start * BAR_TICKS, (start + n) * BAR_TICKS
        return [(s - t0, d, ch, p, v) for (s, d, ch, p, v) in events if t0 <= s < t1]

    A = {r: _win(skel[r], best_b, section_bars) for r in ("melody", "harmony", "drums")}
    # B section: a different window if available, else hook transposed up a 4th
    altstart = (best_b + section_bars) % max(1, tb - section_bars + 1)
    if altstart != best_b and (altstart + section_bars) <= tb:
        Bm = _win(skel["melody"], altstart, section_bars)
        Bh = _win(skel["harmony"], altstart, section_bars)
        Bd = _win(skel["drums"], altstart, section_bars)
    else:
        Bm = [(s, d, ch, min(127, p + 5), v) for (s, d, ch, p, v) in A["melody"]]
        Bh = [(s, d, ch, min(127, p + 5), v) for (s, d, ch, p, v) in A["harmony"]]
        Bd = A["drums"]
    blocks = {"A": (A["melody"], A["harmony"], A["drums"]), "B": (Bm, Bh, Bd)}

    mel2, harm2, drum2 = [], [], []
    for i, sec in enumerate(form):
        off = i * section_bars * BAR_TICKS
        bm, bh, bd = blocks[sec]
        mel2 += [(s + off, d, ch, p, v) for (s, d, ch, p, v) in bm]
        harm2 += [(s + off, d, ch, p, v) for (s, d, ch, p, v) in bh]
        drum2 += [(s + off, d, ch, p, v) for (s, d, ch, p, v) in G.fit_to_bars(
            bd, section_bars, section_bars)]
    return skeleton_from_stems(mel2, harm2, drum2)
