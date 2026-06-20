#!/usr/bin/env python3
"""Pull 5 MIDIs spanning detection failure-modes, dump catalog read + independent re-parse."""
import pandas as pd, numpy as np, pathlib, json, collections
import pretty_midi
pretty_midi.pretty_midi.MAX_TICK = 1e10

ROOT = pathlib.Path(__file__).resolve().parents[1]
m = pd.read_parquet(ROOT / "catalog/metadata.parquet")

# common listenable/renderable filter
base = m[(m.quality_flag == "ok") & (m.duration_suspect == 0) &
         (m.duration_sec.between(30, 240)) & (m.parses == True)]

def pick(df, label, sort_col=None, asc=True):
    d = df.sort_values(sort_col if sort_col else "md5", ascending=asc)
    return (d.iloc[0]["md5"], label) if len(d) else None

picks = []
# A: low-BPM subdivision-latch suspect
picks.append(pick(base[base.bpm < 55], "low-BPM suspect (subdivision latch?)", "bpm", True))
# B: odd-meter suspect: inferred 4/4 + drums + high syncopation
picks.append(pick(base[(base.time_signature_inferred == 1) & (base.has_drums == True) &
                       (base.syncopation > base.syncopation.quantile(.9))],
                  "odd-meter suspect (4/4 inferred, synced, drummed)", "syncopation", False))
# C: blast-beat candidate
picks.append(pick(base[base.drum_kick_density > 12], "blast-beat candidate (kick>12/bar)", "drum_kick_density", False))
# D: clean solo piano, no drums, confident key
picks.append(pick(base[(base.is_solo == True) & (base.has_drums == False) &
                       (base.key_confidence > 0.8) & (base.n_piano_tracks >= 1)],
                  "solo piano, no drums (key/melody test)", "key_confidence", False))
# E: normal drummed baseline (mid tempo, backbeat present)
picks.append(pick(base[(base.has_drums == True) & (base.bpm.between(90, 140)) &
                       (base.drum_snare_backbeat > 0.7) & (base.bpm_valid == 1)],
                  "normal drummed baseline (backbeat)", "drum_snare_backbeat", False))

picks = [p for p in picks if p]
seen = set(); uniq = []
for md5, lab in picks:
    if md5 not in seen:
        seen.add(md5); uniq.append((md5, lab))
picks = uniq

FIELDS = ["bpm","bpm_valid","time_signature","time_signature_inferred","duration_sec",
          "key","mode","key_confidence","n_tracks","n_notes","n_voices","has_drums",
          "has_melody","melody_n_notes","is_solo","midi_patches","instrument_family_counts",
          "n_piano_tracks","n_guitar_tracks","n_bass_tracks","n_strings_tracks","n_brass_tracks",
          "n_drum_tracks","genre_hint","genre_confidence","composer","title","artist",
          "tempo_class","tempo_change_count","total_beats","onset_density_per_beat",
          "syncopation","swing_bur","is_swung","is_triplet_feel","is_dotted","triplet_feel",
          "pulse_clarity","most_common_chord","n_unique_chords","diatonic_ratio","n_key_areas",
          "key_changes","drum_kick_density","drum_snare_backbeat","drum_swing","drum_hat_density",
          "drum_pattern_entropy","bar_drum_variance","groove_composite","percussion_ratio"]

GM = ["Piano","ChromPerc","Organ","Guitar","Bass","Strings","Ensemble","Brass","Reed",
      "Pipe","SynthLead","SynthPad","SynthFX","Ethnic","Percussive","SoundFX"]
def gm_family(p):
    return GM[p//8] if 0 <= p < 128 else "?"

def reparse(md5):
    """Independent read straight from the MIDI bytes."""
    path = ROOT / "MIDIs" / md5[:2] / f"{md5}.mid"
    out = {"path": str(path)}
    try:
        pm = pretty_midi.PrettyMIDI(str(path))
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"; return out
    out["length_sec"] = round(pm.get_end_time(), 1)
    # tempos
    tt, tempi = pm.get_tempo_changes()
    out["tempo_changes"] = len(tempi)
    out["tempo_range_bpm"] = [round(float(tempi.min()),1), round(float(tempi.max()),1)] if len(tempi) else None
    try: out["estimated_tempo_bpm"] = round(float(pm.estimate_tempo()),1)
    except Exception: out["estimated_tempo_bpm"] = None
    # time signatures actually in the file
    out["time_sigs_in_file"] = [f"{ts.numerator}/{ts.denominator}@{round(ts.time,1)}s" for ts in pm.time_signature_changes] or ["(none)"]
    # key sigs
    out["key_sigs_in_file"] = len(pm.key_signature_changes)
    # instruments / channels
    insts = []
    drum_notes = 0; total = 0
    for inst in pm.instruments:
        n = len(inst.notes); total += n
        if inst.is_drum: drum_notes += n
        insts.append(f"{'DRUM' if inst.is_drum else gm_family(inst.program)}({inst.program}):{n}")
    out["total_notes"] = total
    out["drum_notes"] = drum_notes
    out["instruments"] = insts
    # drum grid (16th-note onset histogram over the bar, beats from estimated tempo)
    if drum_notes:
        bpm = out["estimated_tempo_bpm"] or 120
        beat = 60.0/bpm
        sixteenth = beat/4
        grid = collections.Counter()
        pitch_hist = collections.Counter()
        for inst in pm.instruments:
            if not inst.is_drum: continue
            for nt in inst.notes:
                slot = int(round(nt.start/sixteenth)) % 16
                grid[slot]+=1
                pitch_hist[nt.pitch]+=1
        out["drum_16th_grid"] = [grid.get(i,0) for i in range(16)]
        # top drum pitches (GM perc names)
        DRUM = {35:"AcBD",36:"BD",38:"SD",40:"SD2",42:"CHH",44:"PHH",46:"OHH",
                49:"Crash",51:"Ride",47:"MTom",45:"LTom",43:"FTom",
                54:"Tamb",56:"Cowb",39:"Clap",37:"Stick",53:"RideBell"}
        top = pitch_hist.most_common(6)
        out["top_drum_pitches"] = [f"{DRUM.get(p,p)}:{c}" for p,c in top]
    return out

print(f"# Detection test — {len(picks)} songs\n")
report = {}
for i,(md5,lab) in enumerate(picks,1):
    row = m[m.md5==md5].iloc[0]
    cat = {k: (row[k].item() if hasattr(row[k],"item") else row[k]) for k in FIELDS if k in row}
    rp = reparse(md5)
    report[md5] = {"label":lab, "catalog":cat, "reparse":rp}
    print(f"===== SONG {i}: {md5[:8]}  [{lab}] =====")
    print(json.dumps({"catalog":cat,"reparse":rp}, indent=1, default=str))
    print()

(ROOT/"_work").mkdir(exist_ok=True)
json.dump(report, open(ROOT/"_work/detect_test.json","w"), indent=1, default=str)
with open(ROOT/"_work/detect_test_md5s.txt","w") as f:
    for md5,lab in picks: f.write(f"{md5}\t{lab}\n")
print("md5s:", " ".join(md5[:8] for md5,_ in picks))
