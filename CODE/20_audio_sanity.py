#!/usr/bin/env python3
"""Phase 9.1 — Audio sanity render.

Render a DETERMINISTIC sample of N (default 500) non-quarantined files to audio
with fluidsynth (via LAMD's midi_to_colab_audio), measure energy/length, and flag
silent / clipping / wrong-length renders.

Design (per STATE.md Roadmap 9.1):
  * Does NOT add per-file audio columns to the 459,805-row catalog (only N rendered).
  * Writes a standalone _stats/audio_sanity.parquet (md5, rms, peak, rendered_sec, flags).
  * Writes WAVs only for the flagged files (+ a few clean controls) into
    _stats/audio_sanity_wav/ so they can be previewed with `webplayer`.
  * Deterministic sample: eligible md5s sorted ascending, N evenly-spaced via linspace.

Notes on metrics:
  The renderer max-normalizes each clip, so PEAK is ~1.0 for anything non-silent and
  is useless for clipping detection. We therefore use:
    rms          -> RMS of the normalized int16 signal (silence detector)
    peak         -> max |sample| (recorded for completeness; ~1.0 when not silent)
    frac_fs      -> fraction of samples within 1% of full-scale (distortion/clip proxy)
    rendered_sec -> len/sample_rate with trim_silence=False (true synth length)

Flags:
    silent          rms < 1e-3                       (essentially no audio)
    near_silent     1e-3 <= rms < 1e-2               (suspiciously quiet)
    clipping        frac_fs > 0.02                   (>2% samples piled at full scale)
    length_mismatch |rendered_sec - duration_sec| > max(2.0, 0.25*duration_sec)
    render_error    fluidsynth/parse raised          (rms/peak/etc NaN)
"""
import os, sys, time, sqlite3, argparse
import numpy as np
import pandas as pd

LAMD_CODE = "/home/t/datasets/LAMD/CODE"
sys.path.insert(0, LAMD_CODE)
import midi_to_colab_audio as M  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "catalog", "catalog.sqlite")
SF = os.path.join(LAMD_CODE, "fluidsynth-master/sf2/VintageDreamsWaves-v2.sf2")
OUT_PARQUET = os.path.join(ROOT, "_stats", "audio_sanity.parquet")
WAV_DIR = os.path.join(ROOT, "_stats", "audio_sanity_wav")
SAMPLE_RATE = 16000

# thresholds
SILENT_RMS = 1e-3
NEAR_SILENT_RMS = 1e-2
CLIP_FRAC = 0.10  # frac of samples near full-scale; 0.10 = genuine saturation tail
                  # (0.02 over-fired at 16% of renders; raw frac_fs is kept so this
                  #  is re-thresholdable without re-rendering)
LEN_ABS = 2.0
LEN_REL = 0.25
# exclude absurdly long junk (duration_suspect, >3600s) from the render pool so
# one stuck-note 9.9h file can't dominate runtime.
MAX_DURATION_SEC = 3600


def pick_sample(con, n):
    """Deterministic: all eligible md5 sorted asc, N evenly-spaced indices."""
    rows = con.execute(
        """SELECT m.md5, m.stored_path, md.duration_sec
             FROM manifest m JOIN metadata md ON m.md5 = md.md5
            WHERE m.is_quarantined = 0
              AND md.duration_sec IS NOT NULL
              AND md.duration_sec > 0
              AND md.duration_sec <= ?
            ORDER BY m.md5 ASC""",
        (MAX_DURATION_SEC,),
    ).fetchall()
    if len(rows) <= n:
        return rows
    idx = np.linspace(0, len(rows) - 1, n).round().astype(int)
    idx = sorted(set(idx.tolist()))
    return [rows[i] for i in idx]


def render_stats(path):
    """Return (rendered_sec, rms, peak, frac_fs, audio_int16) or raise."""
    raw = open(path, "rb").read()
    opus = M.midi2opus(raw)
    audio = M.midi_opus_to_colab_audio(
        opus, soundfont_path=SF, sample_rate=SAMPLE_RATE,
        trim_silence=False, output_for_gradio=True,
    )
    if audio is None or audio.shape[0] == 0:
        return 0.0, 0.0, 0.0, 0.0, np.zeros((0, 2), dtype=np.int16)
    a = audio.astype(np.float64) / 32767.0
    rendered_sec = audio.shape[0] / SAMPLE_RATE
    rms = float(np.sqrt((a ** 2).mean()))
    peak = float(np.abs(a).max())
    frac_fs = float((np.abs(a) > 0.99).mean())
    return rendered_sec, rms, peak, frac_fs, audio


def classify(rms, frac_fs, rendered_sec, duration_sec, errored):
    flags = []
    if errored:
        flags.append("render_error")
        return flags
    if rms < SILENT_RMS:
        flags.append("silent")
    elif rms < NEAR_SILENT_RMS:
        flags.append("near_silent")
    if frac_fs > CLIP_FRAC:
        flags.append("clipping")
    if duration_sec and duration_sec > 0:
        tol = max(LEN_ABS, LEN_REL * duration_sec)
        if abs(rendered_sec - duration_sec) > tol:
            flags.append("length_mismatch")
    return flags


def write_wav(audio, path):
    from scipy.io import wavfile
    wavfile.write(path, SAMPLE_RATE, audio)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--wav-controls", type=int, default=12,
                    help="how many non-flagged clean files to also dump as WAV")
    ap.add_argument("--max-wav", type=int, default=120,
                    help="cap total WAVs written (flagged + controls)")
    args = ap.parse_args()

    os.makedirs(WAV_DIR, exist_ok=True)
    con = sqlite3.connect(DB)
    sample = pick_sample(con, args.n)
    print(f"[20] eligible-sampled {len(sample)} files (deterministic linspace over sorted md5)")

    recs = []
    written = []           # WAV filenames written (flagged + clean controls)
    n_controls = 0         # clean WAVs written so far
    t0 = time.time()
    n_err = 0
    # Audio arrays are NOT retained across iterations (500 long renders would be
    # multiple GB). We write any WAV we want for a file in-loop, then drop it.
    for i, (md5, path, dur) in enumerate(sample):
        errored = False
        rendered_sec = rms = peak = frac_fs = np.nan
        audio = None
        try:
            rendered_sec, rms, peak, frac_fs, audio = render_stats(path)
        except Exception as e:  # noqa: BLE001
            errored = True
            n_err += 1
            if n_err <= 10:
                print(f"  ! render_error {md5}: {type(e).__name__}: {e}")
        flags = classify(rms, frac_fs, rendered_sec, dur, errored)
        recs.append({
            "md5": md5, "stored_path": path,
            "duration_sec": dur, "rendered_sec": rendered_sec,
            "rms": rms, "peak": peak, "frac_fs": frac_fs,
            "flags": ";".join(flags), "n_flags": len(flags),
        })

        # write WAV for every flagged file, plus up to --wav-controls clean ones,
        # capped at --max-wav total.
        want_wav = bool(flags) or (n_controls < args.wav_controls)
        if (want_wav and len(written) < args.max_wav
                and audio is not None and getattr(audio, "shape", (0,))[0] > 0):
            tag = ";".join(flags) if flags else "clean"
            fn = f"{tag.replace(';','_')}__{md5[:12]}.wav"
            try:
                write_wav(audio, os.path.join(WAV_DIR, fn))
                written.append(fn)
                if not flags:
                    n_controls += 1
            except Exception as e:  # noqa: BLE001
                print(f"  ! wav write failed {md5}: {e}")
        audio = None  # free immediately

        if (i + 1) % 50 == 0:
            el = time.time() - t0
            print(f"  {i+1}/{len(sample)}  {el:.1f}s  ({el/(i+1)*1000:.0f} ms/file)")

    out = pd.DataFrame(recs)
    df = out  # alias for the report section below
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)

    # --- report ---
    el = time.time() - t0
    print(f"\n[20] rendered {len(df)} files in {el:.1f}s ({el/max(len(df),1)*1000:.0f} ms/file)")
    print(f"[20] render errors: {n_err}")
    print("[20] flag counts:")
    fc = {}
    for s in df["flags"]:
        for f in (s.split(";") if s else ["(ok)"]):
            fc[f] = fc.get(f, 0) + 1
    for k in sorted(fc, key=lambda x: -fc[x]):
        print(f"       {k:16s} {fc[k]}")
    print(f"[20] clean (no flags): {(df['n_flags']==0).sum()}")
    print(f"[20] wrote {OUT_PARQUET}  ({len(out)} rows)")
    print(f"[20] wrote {len(written)} WAVs -> {WAV_DIR}")
    print(f"[20] preview:  webplayer add {WAV_DIR} --group audio_sanity && webplayer open")


if __name__ == "__main__":
    main()
