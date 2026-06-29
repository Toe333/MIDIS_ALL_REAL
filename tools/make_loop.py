#!/usr/bin/env python3
"""Cut a clean N-bar loop out of a MIDI (assumes 4/4) and optionally repeat it.
Keeps tempo/program/CC setup, keeps note_ons that start before the loop end,
and clips/adds note_offs at the loop boundary so nothing hangs over.
Usage: make_loop.py in.mid out.mid [bars] [start_bar] [repeat]
"""
import sys
import mido

def main(src, dst, bars=4, start_bar=0, repeat=1):
    m = mido.MidiFile(src)
    tpb = m.ticks_per_beat
    bar = tpb * 4
    t0 = start_bar * bar
    t1 = t0 + bars * bar

    # flatten to absolute-time events across all tracks
    meta = []        # (abstime, msg) tempo/timesig/key
    setup = []       # program_change / control_change (channel setup) at/<=t0
    notes = []       # (abstime, msg) note on/off within window
    for tr in m.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.is_meta:
                if msg.type in ('set_tempo', 'time_signature', 'key_signature') and t <= t1:
                    meta.append((min(t, t0), msg.copy(time=0)))
                continue
            if msg.type in ('program_change', 'control_change'):
                if t <= t0 + 1:            # channel setup placed before the loop
                    setup.append(msg.copy(time=0))
                continue
            if msg.type in ('note_on', 'note_off'):
                notes.append((t, msg))

    # resolve notes: keep ons in [t0,t1); clip matching offs to <= t1
    active = {}      # (chan,note) -> ontick
    kept = []        # (tick, msg)
    for t, msg in sorted(notes, key=lambda e: e[0]):
        on = msg.type == 'note_on' and msg.velocity > 0
        key = (msg.channel, msg.note)
        if on:
            if t0 <= t < t1:
                active[key] = t
                kept.append((t - t0, msg.copy(time=0)))
        else:  # note off (or note_on vel 0)
            if key in active:
                off_t = min(t, t1)
                kept.append((off_t - t0, mido.Message('note_off', channel=msg.channel,
                                                      note=msg.note, velocity=0, time=0)))
                del active[key]
    # close anything still ringing at the boundary
    for key, on_t in active.items():
        ch, note = key
        kept.append((t1 - t0, mido.Message('note_off', channel=ch, note=note, velocity=0, time=0)))

    out = mido.MidiFile(ticks_per_beat=tpb)
    mtrk = mido.MidiTrack(); out.tracks.append(mtrk)
    for _, msg in sorted(meta, key=lambda e: e[0]):
        mtrk.append(msg)
    trk = mido.MidiTrack(); out.tracks.append(trk)
    for msg in setup:
        trk.append(msg)
    kept.sort(key=lambda e: (e[0], 0 if e[1].type == 'note_off' else 1))
    loop_ticks = bars * bar
    tiled = [(tick + r * loop_ticks, msg) for r in range(repeat) for tick, msg in kept]
    tiled.sort(key=lambda e: (e[0], 0 if e[1].type == 'note_off' else 1))
    last = 0
    for tick, msg in tiled:
        trk.append(msg.copy(time=tick - last)); last = tick
    out.save(dst)
    print(f"loop: {bars} bars x{repeat} = {bars*repeat} bars @tpb {tpb} -> {dst} "
          f"({len(tiled)} note events)")

if __name__ == '__main__':
    a = sys.argv
    main(a[1], a[2], int(a[3]) if len(a) > 3 else 4,
         int(a[4]) if len(a) > 4 else 0, int(a[5]) if len(a) > 5 else 1)
