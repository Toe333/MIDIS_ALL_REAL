"""Quick PT notation dumper for any MIDI file in the SHUTTLE folder."""
import mido, collections, sys

MIDI = sys.argv[1] if len(sys.argv) > 1 else r'b:\MIDIS_ALL_REAL\SHUTTLE\gypsy_drumpattern_11_16_96bpm_FINAL.mid'
GM = {35:'BD2',36:'BD ',38:'SD ',40:'SD2',42:'CHH',44:'PHH',46:'OHH',
      49:'CC ',51:'RC ',54:'Tb ',58:'VS ',69:'Cb ',75:'Clv',56:'CB ',
      39:'CP ',37:'RS ',41:'LT ',43:'HT ',45:'MT ',47:'MT2',48:'HT2',50:'HT3'}

mid = mido.MidiFile(MIDI)
tpb = mid.ticks_per_beat
tempos = [round(60000000/msg.tempo,1) for tr in mid.tracks for msg in tr if msg.type=='set_tempo']
tsigs  = [(msg.numerator, msg.denominator) for tr in mid.tracks for msg in tr if msg.type=='time_signature']
print(f"File : {MIDI.split(chr(92))[-1]}")
print(f"tpb  : {tpb}  tempos: {tempos}  time_sigs: {tsigs}")

# figure out bar length in 16ths
if tsigs:
    num, den = tsigs[0]
    # den=8 → beat=8th=tpb/2; den=16 → beat=16th=tpb/4
    beat_ticks = tpb * 4 // den
    bar_16ths  = num * beat_ticks // (tpb // 4)
else:
    bar_16ths = 16

print(f"Bar  : {bar_16ths} sixteenth-note slots\n")

step = tpb // 4   # one sixteenth note

for i, tr in enumerate(mid.tracks):
    notes = []
    tick  = 0
    for msg in tr:
        tick += msg.time
        if msg.type == 'note_on' and getattr(msg, 'channel', 0) == 9 and msg.velocity > 0:
            notes.append((tick, msg.note))
    if not notes:
        continue

    # how many complete bars?
    last_slot = int(notes[-1][0] / step)
    n_bars    = max(1, (last_slot // bar_16ths) + 1)
    n_bars    = min(n_bars, 4)   # cap at 4 for readability
    steps     = n_bars * bar_16ths

    grid = collections.defaultdict(lambda: ['.'] * steps)
    for (t, n) in notes:
        s = int(t / step)
        if s < steps:
            lbl = GM.get(n, f'p{n:02d}')
            grid[lbl][s] = 'X'

    print(f"Track {i}: {tr.name!r}  ({len(notes)} hits, {n_bars} bar(s))")

    # header row
    hdr = "      "
    for b in range(n_bars):
        hdr += "".join(str(s+1).rjust(2) for s in range(bar_16ths)) + "  |  "
    print(hdr)

    for name in sorted(grid):
        row  = grid[name]
        line = f"{name:>4}: "
        for b in range(n_bars):
            chunk = row[b*bar_16ths:(b+1)*bar_16ths]
            line += " ".join(f" {c}" for c in chunk) + "  |  "
        print(line)

    # PT compact notation (collapsed to first bar via OR)
    print("\nPT (1 bar, 8th-note slots):")
    bar_grid = collections.defaultdict(lambda: ['.'] * bar_16ths)
    for name, row in grid.items():
        for s in range(bar_16ths):
            for b in range(n_bars):
                if b*bar_16ths+s < steps and row[b*bar_16ths+s] == 'X':
                    bar_grid[name][s] = 'X'
    # group by slot
    slots = []
    for s in range(bar_16ths):
        hits = [name.strip() for name, row in bar_grid.items() if row[s] == 'X']
        slots.append('(' + '+'.join(sorted(hits)) + ')' if hits else '.')
    print(' '.join(slots))
    print()
