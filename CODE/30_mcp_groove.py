#!/usr/bin/env python3
"""30_mcp_groove.py — MCP (Mini-Compact-Pattern) drum notation: parse + generate.

MCP is a tiny human grammar for typing a drum groove as a string, so we can hand-author
archetypes, generate labelled test MIDIs, and (later) match a real MIDI to its closest
archetype. It is the human interface layer that sits on top of GrooveDNA (29): you type a
string, you get a MIDI + an 11-D GrooveDNA score.

GRAMMAR (as taught by the user)
  tokens     k=kick  s=snare  h=closed-hat  o=open-hat   (extra: c=crash r=ride t=tom)
  simultan.  (...)   a parenthesised group fires together, e.g. (hk) = kick+hat together
  rest       . - _   an empty step (silence); none of the v0.1 archetypes use one
  positions  one step per token/group; DEFAULT 8 positions per 4/4 bar (8th-note grid)
  time-sig   an optional leading "N/M " overrides the bar, e.g. "3/4 kss" = a 3-step
             waltz bar in 3/4 (quarter-note pulse). Without it the bar is 4/4 and the
             grid subdivision = bar_beats / n_steps.

  e.g.  rock = (hk)h(hs)(h)(hk)(hk)(hs)(h)   -> 8 steps, backbeat snare on 3 & 7
        waltz = 3/4 kss                      -> 3 steps in 3/4 (kick then two snares)

DESIGN DECISIONS (flagged — correct me and I'll relock):
  * GM pitch map below (k=36 s=38 h=42 o=46) — standard GM, and inside GrooveDNA's
    drum range 35-81, so generated MIDIs round-trip through 29 cleanly.
  * Velocities: kick/snare=110 (accent), hat=80, open-hat=95 — flat, no humanization,
    so ghost_dynamics stays ~neutral (these are clean reference patterns, not performances).
  * Render = 4 bars @ each archetype's bpm, ticks-per-beat 480, drums on channel 9.
  * Output: rhythmexamples/<name>.mcp.mid (never touches the user's speedy_ragtime.mid).
  * No external MIDI lib (mido/pretty_midi absent) — a tiny dependency-free Standard
    MIDI File (format 0) writer is included.

Usage:
  python3 CODE/30_mcp_groove.py            # generate the 5 archetype MIDIs + run validation
  python3 CODE/30_mcp_groove.py generate   # just write the MIDIs
  python3 CODE/30_mcp_groove.py validate   # just run the test (string->MIDI->GrooveDNA)
"""
import os, sys, re, importlib.util
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = os.path.join(ROOT, "rhythmexamples")
RAGTIME = os.path.join(OUTDIR, "speedy_ragtime.mid")   # real-MIDI test case (pre-existing)
TPB = 480                                              # ticks per quarter for generation

# token -> GM percussion pitch (all inside GrooveDNA's 35-81 range so 29 reads them).
TOKENS = {"k": 36, "s": 38, "h": 42, "o": 46, "c": 49, "r": 51, "t": 45}
VEL = {36: 110, 38: 110, 42: 80, 46: 95, 49: 100, 51: 90, 45: 100}   # flat reference dynamics

# ---- the MCP Groove Library v0.1 -----------------------------------------------------
# The 5 archetypes the task locks (rock, surf, reggae, waltz, raggaetone) + a bpm each.
# (bpm only affects listenability; GrooveDNA is beat-based and tempo-independent.)
ARCHETYPES = {
    "rock":       ("(hk)h(hs)(h)(hk)(hk)(hs)(h)", 120),   # backbeat snare on steps 3 & 7
    "surf":       ("khsshhsh",                    160),   # busy 60s surf 8ths
    "reggae":     ("hhhh(ksh)hhh",                 78),   # one-drop: kit hit on the '3'
    "waltz":      ("3/4 kss",                     150),   # 3/4 bar, kick + two snares
    "raggaetone": ("khshkshh",                    95),    # dembow-ish kick/snare interplay
}
# Grok's other v0.1 guesses are kept for reference but NOT generated — several violate the
# 8-positions rule (trap=10, funk=4, shuffle=6 steps) and are unconfirmed by the user.
UNVERIFIED = {
    "techno": "kosokoso", "trap": "kss(hh)ss(k)ss(hh)", "funk": "(hk)(hs)(hk)(hs)",
    "broken": "k(hs)h(sh)k(hs)h(sh)", "shuffle": "(hk)hh(hs)hh",
}


def parse_mcp(pattern):
    """MCP string -> (steps, beats_per_bar). steps is a list (one per grid position) of
    lists of GM pitches fired at that step ([] == rest)."""
    beats_per_bar = 4.0                                  # default 4/4
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)\s+(.*)", pattern)  # optional "N/M " time-sig prefix
    if m:
        beats_per_bar = float(m.group(1)) * (4.0 / float(m.group(2)))  # in quarter-beats
        pattern = m.group(3)
    body = pattern.replace(" ", "")
    steps, i = [], 0
    while i < len(body):
        ch = body[i]
        if ch == "(":                                    # simultaneous group: read to ')'
            j = body.index(")", i)
            group = body[i + 1:j]
            steps.append([TOKENS[c] for c in group if c in TOKENS])
            i = j + 1
        elif ch in ".-_":                                # explicit rest
            steps.append([]); i += 1
        elif ch in TOKENS:                               # single hit
            steps.append([TOKENS[ch]]); i += 1
        else:
            raise ValueError(f"bad MCP token {ch!r} in {pattern!r}")
    if not steps:
        raise ValueError(f"empty MCP pattern {pattern!r}")
    return steps, beats_per_bar


def mcp_to_array(steps, beats_per_bar, n_bars=4, tpb=TPB):
    """Render parsed steps to a NOTESEQ-style (N,5) int array (start,dur,chan,pitch,vel),
    drums on channel 9, repeated for n_bars. Matches what 29.groove_of expects."""
    step_beats = beats_per_bar / len(steps)              # subdivision length in beats
    step_ticks = int(round(step_beats * tpb))
    rows = []
    for bar in range(n_bars):
        bar_tick = int(round(bar * beats_per_bar * tpb))
        for si, pitches in enumerate(steps):
            start = bar_tick + si * step_ticks
            for p in pitches:
                rows.append((start, max(step_ticks - 1, 1), 9, p, VEL.get(p, 100)))
    return np.array(rows, dtype=np.int32) if rows else np.zeros((0, 5), np.int32)


def _vlq(n):
    """Variable-length quantity (MIDI delta-time) encoder."""
    out = [n & 0x7F]; n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80); n >>= 7
    return bytes(reversed(out))


def write_smf(array, path, bpm=120, tpb=TPB):
    """Minimal Standard MIDI File (format 0) writer — no external deps."""
    evs = []                                             # (tick, order, raw-bytes)
    for st, du, ch, pit, vel in array.tolist():
        evs.append((st, 1, bytes([0x90 | ch, pit, vel])))      # note-on
        evs.append((st + du, 0, bytes([0x80 | ch, pit, 0])))   # note-off (off sorts first)
    evs.sort(key=lambda e: (e[0], e[1]))
    mpq = int(round(60_000_000 / bpm))                   # microseconds per quarter
    trk = _vlq(0) + bytes([0xFF, 0x51, 0x03]) + mpq.to_bytes(3, "big")  # set-tempo
    prev = 0
    for tick, _, data in evs:
        trk += _vlq(tick - prev) + data; prev = tick
    trk += _vlq(0) + bytes([0xFF, 0x2F, 0x00])           # end-of-track
    hdr = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + \
        (1).to_bytes(2, "big") + tpb.to_bytes(2, "big")
    with open(path, "wb") as fh:
        fh.write(hdr + b"MTrk" + len(trk).to_bytes(4, "big") + trk)
    return path


def _load_groove_dna():
    """Reuse the VALIDATED GrooveDNA scorer from 29 (numeric filename -> load by path)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "29_groove_dna.py")
    spec = importlib.util.spec_from_file_location("groove_dna", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_real_midi(path):
    """Parse a real MIDI to a NOTESEQ-style (N,5) array via TMIDIX (the corpus parser)."""
    sys.path.insert(0, "/home/t/datasets/LAMD/CODE")
    import TMIDIX
    score = TMIDIX.midi2single_track_ms_score(open(path, "rb").read())
    notes = TMIDIX.advanced_score_processor(score, return_enhanced_score_notes=True)[0]
    # enhanced note = ['note', start, dur, chan, pitch, vel, ...]; ms timing -> beats@tpb.
    # speedy_ragtime is all-piano (chan 0) so this exercises the drum-isolation path.
    rows = [(int(n[1]), int(n[2]), int(n[3]), int(n[4]), int(n[5])) for n in notes]
    return np.array(rows, dtype=np.int32), int(score[0])


def generate():
    os.makedirs(OUTDIR, exist_ok=True)
    made = []
    for name, (pat, bpm) in ARCHETYPES.items():
        steps, bpb = parse_mcp(pat)
        arr = mcp_to_array(steps, bpb)
        path = os.path.join(OUTDIR, f"{name}.mcp.mid")
        write_smf(arr, path, bpm=bpm)
        made.append((name, pat, len(steps), bpb, len(arr), path))
    return made


def validate():
    gd = _load_groove_dna()
    DIMS = gd.DIMS
    show = ["kick_density_bar", "snare_backbeat_strength", "hat_cym_density",
            "perc_diversity", "swing_cont", "syncopation_drum", "groove_composite"]
    print(f"\n{'archetype':12} " + " ".join(f"{s.split('_')[0][:5]:>6}" for s in show))
    vecs = {}
    for name, (pat, bpm) in ARCHETYPES.items():
        steps, bpb = parse_mcp(pat)
        arr = mcp_to_array(steps, bpb)
        f = gd.groove_of(arr, TPB)
        vecs[name] = np.array([f[d] for d in DIMS], dtype=np.float32)
        print(f"{name:12} " + " ".join(f"{f[s]:6.2f}" for s in show))
        # parse round-trips to the same step count
        assert len(steps) == (3 if name == "waltz" else 8), f"{name}: unexpected step count"
    # sanity (all true of the v0.1 strings): rock has a strong 2&4 backbeat; reggae is a
    # one-drop so its snare is NOT on the backbeat; rock is the strongest overall groove.
    assert vecs["rock"][1] > 0.5, "rock should have strong backbeat (snare on 2&4)"
    assert vecs["reggae"][1] < 0.5, "reggae one-drop: snare on the 3, not the 2&4 backbeat"
    assert vecs["rock"][10] == max(v[10] for v in vecs.values()), "rock = strongest groove"

    # --- real-MIDI test case: speedy_ragtime.mid (all piano, no drums) -> NEUTRAL ---
    print("\nspeedy_ragtime.mid (real MIDI, all-piano test case):")
    arr, tpb = _parse_real_midi(RAGTIME)
    f = gd.groove_of(arr, tpb)
    drum = ((arr[:, 2] == 9) | (arr[:, 2] == 10)) & (arr[:, 3] >= 35) & (arr[:, 3] <= 81)
    print(f"  notes={len(arr)}  drum-channel notes={int(drum.sum())}  "
          f"perc_diversity={f['perc_diversity']:.2f}  groove_composite={f['groove_composite']:.2f}")
    assert f["perc_diversity"] == 0.5 and f["groove_composite"] == 0.5, \
        "drumless piano must score NEUTRAL 0.5 — proves melodic notes don't leak in"
    print("  -> NEUTRAL as expected: drum isolation correctly ignores the piano. ✓")

    # --- matcher demo: nearest archetype to rock's own vector (round-trip sanity) ---
    rv = vecs["rock"]
    nearest = min(vecs, key=lambda n: float(np.linalg.norm(vecs[n] - rv)) if n != "rock" else 1e9)
    print(f"\nmatcher: nearest archetype to 'rock' = {nearest}")
    print("\nMCP validated ✓  (5 archetypes parsed -> MIDI -> GrooveDNA; ragtime neutral)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("generate", "all"):
        made = generate()
        print("generated archetype MIDIs:")
        for name, pat, nst, bpb, nnotes, path in made:
            print(f"  {name:12} {nst} steps @ {bpb:g}/4-beats  {nnotes:3d} notes  {pat}")
    if cmd in ("validate", "all"):
        validate()


if __name__ == "__main__":
    main()
