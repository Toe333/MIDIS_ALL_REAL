#!/usr/bin/env python3
"""gen_tbb.py — render the LOCKED TBB (Tony Bollas Beat) v1 to MIDI.

TBB v1 = the L3+L6 hybrid orcamang locked ("5-5-6 gallop clave signature").
orcamang's spec was loose; this is codemang's concrete, auditable reading of it
(documented in TONYBOLLAS_patterns.md). 16th grid, one bar, looped 4 bars, 118 BPM,
GM percussion on channel 10 (mido channel index 9).

Spec (1 bar, 16 sixteenths):
  K  (kick, vel 105) : 1, 4, 7, 10, 13      (every 3rd 16th = 3+3+3+3+4 gallop chain)
  S  (snare accent)  : 7, 13                 (backbeat pulled to the tresillo)
  s  (ghost snare 45): 3, 10, 15
  H  (closed hat)    : 3, 7, 15              (upbeats)
  O  (open hat)      : 5, 11                 (the R12 "surprise voice", off the 4-grid)
"""
import os
import mido

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "TBB_locked.mid")

GM = {"K": 36, "S": 38, "H": 42, "O": 46}
BPM = 118
BARS = 4
TPB = 480
STEP = TPB // 4

# voice -> list of (1-based 16th slot, velocity)
TBB = {
    "K": [(s, 105) for s in (1, 4, 7, 10, 13)],
    "S": [(7, 110), (13, 110), (3, 45), (10, 45), (15, 45)],   # accents + ghosts
    "H": [(s, 80) for s in (3, 7, 15)],
    "O": [(5, 92), (11, 92)],
}


def build():
    mid = mido.MidiFile(ticks_per_beat=TPB)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("track_name", name="TBB_v1_5-5-6_gallop_clave", time=0))
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM), time=0))
    tr.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

    events = []
    for bar in range(BARS):
        for v, hits in TBB.items():
            note = GM[v]
            for slot, vel in hits:
                t = (bar * 16 + (slot - 1)) * STEP
                events.append((t, "on", note, vel))
                events.append((t + STEP, "off", note, 0))
    events.sort(key=lambda e: (e[0], 0 if e[1] == "off" else 1))

    prev = 0
    for t, typ, note, vel in events:
        dt = t - prev
        prev = t
        msg = "note_on" if typ == "on" else "note_off"
        tr.append(mido.Message(msg, note=note, velocity=vel, channel=9, time=dt))
    mid.save(OUT)
    return OUT


if __name__ == "__main__":
    print("wrote", os.path.relpath(build(), ROOT))
