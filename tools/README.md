# tools/ — oxygen-workflow song/loop generation

One-command wrapper around `CODE/50_generate.py` for making hip-hop / psychedelic
loops "in the oxygen vibe". Run everything from the repo root (`MIDIS_ALL_REAL/`)
using the `.venv-linux` python.

## make_track.sh (the front door)

```bash
tools/make_track.sh --seed <MD5> --style "<description>" [options]
```

Chains: `50_generate.py` (style mode) -> palette remap -> loop cut -> fluidsynth
render -> webplayer add. Prints the `.mid` / `.wav` paths.

Options: `--style` `--seed` `--pattern-from` `--novelty low|med|high` `--catchy`
`--iters N` `--palette psych|chip|none` `--bars N` (0 = full track, no loop)
`--repeat N` `--start N` `--sf PATH` `--group NAME` `--no-play`.

### Examples
```bash
# psychedelic (Dr Octagon / Portishead / Floyd) — strings/Rhodes/upright/room kit
tools/make_track.sh --seed 2de68dfdfebfdf2a20eb2f7ba375026a \
  --style "lo-fi trip hop, dark psychedelic, eerie, minor, 82bpm, swing" \
  --catchy --palette psych --bars 2 --repeat 4 --group psych

# clean hip hop — 808 drums + NES square lead + sine bass
tools/make_track.sh --seed 0a9ae8025581ccac42dbbaa18be08957 \
  --style "hip hop minor 82bpm" --palette chip --bars 0 --group hiphop

# oxygen drum groove + Monk "Off Minor" melody
tools/make_track.sh --pattern-from 0da9e669c61feec3803c7fc8277afad2 \
  --seed 5854fb943c83d10f0073d2f3f586be3b \
  --style "lo-fi dark psychedelic minor 82bpm" --palette psych
```

## The pieces

- **psych_remap.py** `in.mid out.mid` — dark/psychedelic palette: drums->Room kit,
  bass->upright, lead->Strings, keys->Rhodes EP, extras->Warm Pad.
- **palette_remap.py** `in.mid out.mid` — chiptune palette: drums->808/909,
  lowest melodic->Sine, others->Square (NES). (GeneralUser GS bank selects.)
- **make_loop.py** `in.mid out.mid [bars] [start_bar] [repeat]` — cut a clean
  N-bar loop (clips notes at the barline) and optionally tile it `repeat` times.

## Notes
- Style keywords map to genres in `CODE/genre_engine.py`. "hip hop"->boombap/808,
  "lo-fi"/"trip hop"->Rhodes/upright/dusty; "dark"/"eerie"->phrygian; an explicit
  `NNbpm` token pins tempo; "swing"/"slow"/"fast" also recognized.
- Seed from a non-corpus file: `cp file.mid MIDIs/<md5[:2]>/<md5>.mid` first
  (md5 = `md5sum file.mid`).
- Soundfonts in `soundfonts/`: GeneralUserGS (default, full GM), Megadrive (FM).
  Auditioning: the **:8765 webplayer** is the reliable path on this machine.
