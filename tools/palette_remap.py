#!/usr/bin/env python3
"""Remap a generated MIDI onto the oxygen palette:
   drums(ch9) -> 808/909 kit (prog 25)
   bass (lowest-median non-drum channel) -> Sine Wave (GS bank 8, prog 80)
   all other melodic channels -> Square Wave / NES (GS bank 1, prog 80)
GeneralUser GS uses CC0 (bank MSB) for variation banks, so we set CC0 then program.
Usage: palette_remap.py in.mid out.mid
"""
import sys
from collections import defaultdict
import mido

SINE = (8, 80)    # bank, program
SQUARE = (1, 80)
DRUM_PROG = 25    # 808/909 kit on the drum channel (bank 128 auto in GS)

def main(src, dst):
    m = mido.MidiFile(src)
    # find median pitch per non-drum channel -> lowest is the bass
    notes = defaultdict(list)
    for tr in m.tracks:
        for msg in tr:
            if msg.type == 'note_on' and msg.velocity > 0 and msg.channel != 9:
                notes[msg.channel].append(msg.note)
    bass_ch = None
    if notes:
        meds = {ch: sorted(ns)[len(ns)//2] for ch, ns in notes.items()}
        bass_ch = min(meds, key=meds.get)

    melodic = sorted(notes)            # all non-drum channels that play
    # strip existing program_change + bank-select CCs (0/32)
    for tr in m.tracks:
        tr[:] = [msg for msg in tr if not (
            msg.type == 'program_change' or
            (msg.type == 'control_change' and msg.control in (0, 32)))]

    setup = []
    for ch in melodic:
        bank, prog = SINE if ch == bass_ch else SQUARE
        setup.append(mido.Message('control_change', channel=ch, control=0, value=bank, time=0))
        setup.append(mido.Message('control_change', channel=ch, control=32, value=0, time=0))
        setup.append(mido.Message('program_change', channel=ch, program=prog, time=0))
    setup.append(mido.Message('program_change', channel=9, program=DRUM_PROG, time=0))

    m.tracks[0][0:0] = setup
    m.save(dst)
    role = {ch: ('sine bass' if ch == bass_ch else 'square/NES') for ch in melodic}
    role[9] = '808 drums'
    print(f"remapped {src} -> {dst}")
    for ch in sorted(role):
        print(f"  ch{ch}: {role[ch]}")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
