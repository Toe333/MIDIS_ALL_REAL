#!/usr/bin/env python3
"""Remap a generated MIDI onto a dark psychedelic / trip-hop palette
(Dr Octagon "Blue Flowers" / Portishead / Pink Floyd vibe):
   drums(ch9)         -> Room kit (prog 8)  [dusty/roomy, not clean]
   bass (lowest med)  -> Acoustic/upright bass (prog 32)  [warm, woozy]
   lead (highest med) -> Strings (prog 48)  [eerie cinematic]
   keys (next)        -> Rhodes EP (prog 4)
   extra melodic      -> Warm Pad (prog 89) [Floyd atmosphere]
All bank-0 GM programs, so no bank select needed; drum kit selected by
program change on ch9 (GS drum bank is automatic).
Usage: psych_remap.py in.mid out.mid
"""
import sys
from collections import defaultdict
import mido

DRUM_KIT = 8       # Room kit
BASS = 32          # Acoustic Bass
LEAD = 48          # Strings
KEYS = 4           # Rhodes EP
PAD = 89           # Warm Pad

def main(src, dst):
    m = mido.MidiFile(src)
    notes = defaultdict(list)
    for tr in m.tracks:
        for msg in tr:
            if msg.type == 'note_on' and msg.velocity > 0 and msg.channel != 9:
                notes[msg.channel].append(msg.note)
    if not notes:
        m.save(dst); print("no melodic channels"); return
    meds = {ch: sorted(ns)[len(ns)//2] for ch, ns in notes.items()}
    order = sorted(meds, key=meds.get)              # low -> high pitch
    role = {}
    role[order[0]] = ('bass', BASS)
    if len(order) >= 2:
        role[order[-1]] = ('lead/strings', LEAD)
    if len(order) >= 3:
        role[order[1]] = ('rhodes', KEYS)
    for ch in order:
        if ch not in role:
            role[ch] = ('pad', PAD)

    for tr in m.tracks:
        tr[:] = [msg for msg in tr if not (
            msg.type == 'program_change' or
            (msg.type == 'control_change' and msg.control in (0, 32)))]

    setup = []
    for ch in order:
        setup.append(mido.Message('program_change', channel=ch, program=role[ch][1], time=0))
    setup.append(mido.Message('program_change', channel=9, program=DRUM_KIT, time=0))
    m.tracks[0][0:0] = setup

    m.save(dst)
    print(f"psych remap {src} -> {dst}")
    for ch in order:
        print(f"  ch{ch}: {role[ch][0]} (prog {role[ch][1]})")
    print(f"  ch9: room kit (prog {DRUM_KIT})")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
