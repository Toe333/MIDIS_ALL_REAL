#!/usr/bin/env bash
# make_track.sh — one-command song/loop generator for the oxygen workflow.
# Runs: 50_generate (style mode) -> palette remap -> loop cut -> fluidsynth render
#       -> webplayer add. Then prints the .mid/.wav paths.
#
# Usage:
#   tools/make_track.sh --seed <MD5> --style "<text>" [options]
#
# Options (all optional):
#   --style   TEXT   style/genre string (default "hip hop minor 82bpm")
#   --seed    MD5    corpus md5 seed (REQUIRED unless --pattern-from given)
#   --pattern-from MD5  keep this song's drums/backing, melody from --seed
#   --novelty low|med|high   (default med)
#   --catchy         richer arrangement (flag)
#   --iters   N      evolution passes (default 1)
#   --palette psych|chip|none   instrument remap (default psych)
#   --bars    N      loop length in bars (default 2; 0 = no loop, full track)
#   --repeat  N      tile the loop N times (default 4)
#   --start   N      start the loop N bars in (default 4)
#   --sf      PATH   soundfont (default soundfonts/GeneralUserGS.sf2)
#   --group   NAME   webplayer group (default "make_track")
#   --no-play        skip webplayer add
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root (MIDIS_ALL_REAL)
PY=.venv-linux/bin/python
TOOLS=tools

STYLE="hip hop minor 82bpm"; SEED=""; PATFROM=""; NOV=med; CATCHY=""; ITERS=1
PALETTE=psych; BARS=2; REPEAT=4; START=4; SF=soundfonts/GeneralUserGS.sf2
GROUP=make_track; PLAY=1
while [ $# -gt 0 ]; do case "$1" in
  --style) STYLE="$2"; shift 2;; --seed) SEED="$2"; shift 2;;
  --pattern-from) PATFROM="$2"; shift 2;; --novelty) NOV="$2"; shift 2;;
  --catchy) CATCHY="--catchy"; shift;; --iters) ITERS="$2"; shift 2;;
  --palette) PALETTE="$2"; shift 2;; --bars) BARS="$2"; shift 2;;
  --repeat) REPEAT="$2"; shift 2;; --start) START="$2"; shift 2;;
  --sf) SF="$2"; shift 2;; --group) GROUP="$2"; shift 2;;
  --no-play) PLAY=0; shift;; *) echo "unknown arg: $1" >&2; exit 1;;
esac; done

GENARGS=(--style "$STYLE" --novelty "$NOV" --iterations "$ITERS" --no-audio --group "$GROUP" $CATCHY)
[ -n "$SEED" ] && GENARGS+=(--seed-md5 "$SEED")
[ -n "$PATFROM" ] && GENARGS+=(--pattern-from "$PATFROM")

echo ">> generating..."
$PY CODE/50_generate.py "${GENARGS[@]}" 2>&1 | grep -E "\[style\]" || true

# newest style outdir + its final.mid
D=$(ls -dt _work/generated/style_* | head -1)
FIN=$(ls "$D"/*_final.mid | head -1)
echo ">> final: $FIN"

STEM="${FIN%_final.mid}"; OUT="${STEM}_${PALETTE}"
case "$PALETTE" in
  psych) $PY $TOOLS/psych_remap.py   "$FIN" "${OUT}.mid";;
  chip)  $PY $TOOLS/palette_remap.py "$FIN" "${OUT}.mid";;
  none)  cp "$FIN" "${OUT}.mid";;
  *) echo "bad --palette"; exit 1;;
esac

MID="${OUT}.mid"
if [ "$BARS" -gt 0 ]; then
  LOOP="${OUT}_${BARS}barx${REPEAT}.mid"
  $PY $TOOLS/make_loop.py "$MID" "$LOOP" "$BARS" "$START" "$REPEAT"
  MID="$LOOP"
fi

# soundfont shortcuts
case "$SF" in
  earthbound) SF="/usr/share/sounds/sf2/EarthBound.sf2";;
  megadrive)  SF="soundfonts/Megadrive.sf2";;
  general|gm) SF="soundfonts/GeneralUserGS.sf2";;
esac

WAV="${MID%.mid}.wav"
echo ">> rendering with $(basename "$SF") @48k..."
fluidsynth -ni -r 48000 -F "$WAV" "$SF" "$MID" >/dev/null 2>&1
# trim reverb tail to the exact musical length so loops loop clean
LEN=$($PY -c "import mido,sys; print(round(mido.MidiFile(sys.argv[1]).length,3))" "$MID" 2>/dev/null || echo "")
if [ -n "$LEN" ] && command -v sox >/dev/null 2>&1; then
  sox "$WAV" "${WAV}.tmp.wav" trim 0 "$LEN" 2>/dev/null && mv "${WAV}.tmp.wav" "$WAV" \
    && echo ">> trimmed to ${LEN}s"
fi
echo ">> MIDI: $MID"
echo ">> WAV : $WAV"

if [ "$PLAY" -eq 1 ]; then
  webplayer add "$WAV" --group "$GROUP" --label "$(basename "${OUT}") ${PALETTE}" \
     --desc "$STYLE · palette=$PALETTE · $(basename "$SF")" >/dev/null 2>&1 || true
  webplayer open >/dev/null 2>&1 || true
  echo ">> added to webplayer group '$GROUP' — http://127.0.0.1:8765/"
fi
