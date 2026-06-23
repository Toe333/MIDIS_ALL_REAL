#!/usr/bin/env python3
"""gen_ks8_perms.py

Brute-force all 256 kick+snare 8-position patterns (each slot K or S, no rests).
Hi-hat on every slot ("on each beat").
Pure drums only (no piano or other instruments that made previous gens corny boogie-woogie).

Each pattern rendered as a short loop (configurable bars, default 8 bars)
so the pocket/groove can be felt.

Output:
- DRUM_PATTERNS/ks8_loops/ks####_pattern.mid   (one per permutation)
- DRUM_PATTERNS/ks8_index.txt                  (index + pattern string)
- Optionally a combined file with markers.

Usage:
  python3 gen_ks8_perms.py                 # generate all individuals + index
  python3 gen_ks8_perms.py --combined      # also make one big file

Then audition:
  webplayer add DRUM_PATTERNS/ks8_loops/*.mid --group ks8_audit
  webplayer open

Grid: 8 positions = one bar of 8th notes.
Hats (42) on all 8 positions every bar.
"""

import os
import itertools
import mido
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "ks8_loops")
INDEX_FILE = os.path.join(ROOT, "ks8_index.txt")
COMBINED = os.path.join(ROOT, f"ks8_all_{BARS}bar.mid")

GM = {"K": 36, "S": 38, "H": 42}
BPM = 120
BARS = 16         # short loop per pattern (user requested ~16 bars)
TPB = 480
SLOT_TICKS = TPB // 2   # 8th note grid

def pat_to_events(pat, bars):
    """Return list of (tick, 'on'/'off', note, vel) for one pattern repeated 'bars' times."""
    events = []
    for bar in range(bars):
        base = bar * 8 * SLOT_TICKS
        for slot, c in enumerate(pat):
            t = base + slot * SLOT_TICKS
            if c == "k":
                note = GM["K"]
                vel = 105
            else:
                note = GM["S"]
                vel = 100
            events.append((t, "on", note, vel))
            events.append((t + SLOT_TICKS - 1, "off", note, 0))

            # hi-hat on every slot
            h_t = t
            events.append((h_t, "on", GM["H"], 75))
            events.append((h_t + SLOT_TICKS // 2, "off", GM["H"], 0))  # shorter hat for clarity
    return events

def make_one(pat, idx, bars=BARS):
    mid = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)

    name = f"ks{idx:04d}_{pat}"
    tr.append(mido.MetaMessage("track_name", name=name, time=0))
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM), time=0))
    tr.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

    evs = pat_to_events(pat, bars)
    evs.sort(key=lambda e: (e[0], 0 if e[1] == "off" else 1))

    prev = 0
    for t, typ, note, vel in evs:
        dt = t - prev
        prev = t
        msg = "note_on" if typ == "on" else "note_off"
        tr.append(mido.Message(msg, note=note, velocity=vel, channel=9, time=dt))

    out = os.path.join(OUT_DIR, f"{name}.mid")
    mid.save(out)
    return out

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--combined", action="store_true", help="also build one big file with markers")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    pats = ["".join(p) for p in itertools.product("ks", repeat=8)]
    assert len(pats) == 256

    with open(INDEX_FILE, "w") as idx:
        idx.write("idx\tpattern\n")
        for i, p in enumerate(pats):
            idx.write(f"{i:04d}\t{p}\n")

    print(f"Generating {len(pats)} individual {BARS}-bar KS+hat loops...")

    for i, pat in enumerate(pats):
        f = make_one(pat, i)
        if i % 32 == 0:
            print(f"  {i:04d} {pat} -> {os.path.basename(f)}")

    print("Wrote index to", INDEX_FILE)
    print("Loops in", OUT_DIR)

    if args.combined:
        print("Building combined file (this will take a moment)...")
        big = mido.MidiFile(ticks_per_beat=TPB)
        tr = mido.MidiTrack()
        big.tracks.append(tr)
        tr.append(mido.MetaMessage("track_name", name="KS8_256_patterns_8bar_each", time=0))
        tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM), time=0))

        cur_tick = 0
        for i, pat in enumerate(pats):
            # text marker
            tr.append(mido.MetaMessage("text", text=f"[{i:04d}] {pat}", time=0))
            evs = pat_to_events(pat, BARS)
            evs.sort(key=lambda e: (e[0], 0 if e[1]=="off" else 1))
            prev_local = 0
            for t, typ, note, vel in evs:
                dt = (t - prev_local)
                prev_local = t
                msgt = "note_on" if typ == "on" else "note_off"
                tr.append(mido.Message(msgt, note=note, velocity=vel, channel=9, time=dt))
            # advance global
            cur_tick += BARS * 8 * SLOT_TICKS

        big.save(COMBINED)
        print("Wrote combined:", COMBINED)

    print("\nTo audition: the .mid files are ready for any MIDI player / DAW.")
    print(f"  Individuals: {OUT_DIR}/")
    print(f"  Combined (all in one file with labels): {COMBINED}")
    print("  Copy the folder to your machine and load in your MIDI player.")
    print("  (webplayer add is optional if you want them as audio groups too, but raw .mid is better for pattern hunting.)")

if __name__ == "__main__":
    main()
