#!/usr/bin/env python3
"""gen_candidates_midi.py — render the 8 "Left" candidate drum patterns from
TONYBOLLAS_patterns.md (Section 3) to MIDI for ear-checking.

Each candidate is a 1-bar 4/4 loop at 16th resolution, GM percussion on channel 10
(mido channel index 9). Patterns are defined here as per-voice 16-step on/off rows so
this stays a self-contained, dependency-light (mido only) generator. Loops 4 bars.
Output: DRUM_PATTERNS/candidates_midi/Lx_<name>.mid  (git-ignored; regenerable).
"""
import os
import mido

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "candidates_midi")
os.makedirs(OUT, exist_ok=True)

GM = {"K": 36, "S": 38, "H": 42, "O": 46, "R": 51, "C": 49, "T": 45}
BPM = 120
BARS = 4
TPB = 480                       # ticks per beat
STEP = TPB // 4                 # one 16th note

# Each candidate: name -> {voice: 16-char on/off string ("X"/".")}
CANDIDATES = {
    "L1_tresillo_backbeat": {
        "H": "X.X.X.X.X.X.X.X.",
        "K": "X.........X.....",
        "S": "...X..X.....X...",
    },
    "L2_offbeat_kick_suspension": {
        "O": "X.......X.......",
        "H": "..X.X.X...X.X.X.",
        "K": "..X...X...X...X.",
        "S": "....X.......X...",
    },
    "L3_additive_5_5_6": {
        "H": "XXXXXXXXXXXXXXXX",
        "K": "X....X....X.....",
        "S": "............X...",
    },
    "L4_one_drop_double_time": {
        "H": "XXXXXXXXXXXXXXXX",
        "K": "........X.......",
        "S": "......X.X.X.....",
    },
    "L5_lurch_7_9": {
        "H": "X.X.X.X.X.X.X.X.",
        "K": "X......X........",
        "S": "....X......X....",
    },
    "L6_gallop_clave_chain": {
        "H": "XXXXXXXXXXXXXXXX",
        "K": "X..X..X..X..X...",
        "S": "....X.......X...",
    },
    "L7_inverted_backbeat": {
        "H": "X.X.X.X.X.X.X.X.",
        "S": "X.......X.......",
        "K": "....X.......X...",
    },
    "L8_polymeter_5_hat": {
        "O": "X....X....X....X",
        "H": ".XXXX.XXXX.XXXX.",
        "K": "X.......X.......",
        "S": "....X.......X...",
    },
}


def build(name, voices):
    mid = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("track_name", name=name, time=0))
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM), time=0))
    tr.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

    # collect (abs_tick, type, note) events, channel 9 = GM drums
    events = []
    for bar in range(BARS):
        for v, row in voices.items():
            note = GM[v]
            for step, ch in enumerate(row):
                if ch == "X":
                    t = (bar * 16 + step) * STEP
                    events.append((t, "on", note))
                    events.append((t + STEP, "off", note))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "off" else 1))

    prev = 0
    for t, typ, note in events:
        dt = t - prev
        prev = t
        if typ == "on":
            tr.append(mido.Message("note_on", note=note, velocity=100, channel=9, time=dt))
        else:
            tr.append(mido.Message("note_off", note=note, velocity=0, channel=9, time=dt))
    out = os.path.join(OUT, name + ".mid")
    mid.save(out)
    return out


if __name__ == "__main__":
    for name, voices in CANDIDATES.items():
        p = build(name, voices)
        print("wrote", os.path.relpath(p, ROOT))
    print(f"done: {len(CANDIDATES)} candidate MIDIs in {os.path.relpath(OUT, ROOT)}/")
