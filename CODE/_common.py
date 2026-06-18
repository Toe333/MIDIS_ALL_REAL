#!/usr/bin/env python3
"""_common.py — shared helpers for the MIDIS_ALL_REAL v2 pipeline.

Everything the 10_*..17_* scripts need lives here so each script stays short,
self-contained, and safe to run by any model or by hand. No script mutates the
MIDIs/ store; only 10_integrity.py --apply ever moves files (into _quarantine/).

Design rules (see AGENT_TODO.md):
  * md5 == filename stem; stored path == MIDIs/<md5[:2]>/<md5>.mid
  * Derive from the existing META_DATA pickles wherever possible (fast, no parse).
  * Every per-file output is a md5-keyed parquet under _work/ so steps are
    resumable: re-running skips md5s already present.
"""
import os, sys, glob, pickle, time, math
import numpy as np

ROOT = os.environ.get("MAR_ROOT", "/mnt/2FAST/MIDIS_ALL_REAL")
LAMD_CODE = "/home/t/datasets/LAMD/CODE"

WORK   = os.path.join(ROOT, "_work")
LOGS   = os.path.join(ROOT, "_logs")
STATS  = os.path.join(ROOT, "_stats")
CATALOG= os.path.join(ROOT, "catalog")
QUAR   = os.path.join(ROOT, "_quarantine")
META   = os.path.join(ROOT, "META_DATA")

for d in (WORK, LOGS, STATS, os.path.join(CATALOG, "checkpoints")):
    os.makedirs(d, exist_ok=True)

# ----- labeled fields stored at indices 0..16 of each META_DATA record -----
META_FIELDS = [
    "total_number_of_tracks", "total_number_of_opus_midi_events",
    "total_number_of_score_midi_events", "average_median_mode_time_ms",
    "average_median_mode_dur_ms", "average_median_mode_vel",
    "total_number_of_chords", "total_number_of_chords_ms", "ms_chords_counts",
    "pitches_times_sum_ms", "total_pitches_counts", "midi_patches",
    "total_patches_counts", "tempo_change_count", "text_events_count",
    "lyric_events_count", "midi_ticks",
]

# ----- General MIDI program -> family (8-program families) -----
GM_FAMILIES = {
    "piano": range(0, 8), "chromperc": range(8, 16), "organ": range(16, 24),
    "guitar": range(24, 32), "bass": range(32, 40), "strings": range(40, 48),
    "ensemble": range(48, 56), "brass": range(56, 64), "reed": range(64, 72),
    "pipe": range(72, 80), "synth_lead": range(80, 88), "synth_pad": range(88, 96),
    "synth_fx": range(96, 104), "ethnic": range(104, 112), "percussive": range(112, 120),
    "sfx": range(120, 128),
}
def gm_family(program):
    for fam, rng in GM_FAMILIES.items():
        if program in rng:
            return fam
    return "other"


def log(msg, logfile=None):
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if logfile:
        with open(os.path.join(LOGS, logfile), "a") as fh:
            fh.write(line + "\n")


def progress(phase, stats):
    with open(os.path.join(LOGS, "progress.log"), "a") as fh:
        fh.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {phase} DONE {stats}\n")


def tmidix():
    """Import TMIDIX lazily (only the parse pass needs it)."""
    if LAMD_CODE not in sys.path:
        sys.path.insert(0, LAMD_CODE)
    import TMIDIX  # noqa
    return TMIDIX


def stored_path(md5):
    return os.path.join(ROOT, "MIDIs", md5[:2], md5 + ".mid")


def iter_meta_pickles(chunk_glob="META_DATA_*.pickle"):
    """Yield (md5, fields_dict) for every record in the local META_DATA pickles.
    fields_dict holds the 17 labeled fields (see META_FIELDS) plus 'raw_tail'
    (the event list after index 16) for the rare consumer that needs it."""
    for fp in sorted(glob.glob(os.path.join(META, chunk_glob))):
        with open(fp, "rb") as fh:
            recs = pickle.load(fh)
        for md5, data in recs:
            d = {}
            for i, label in enumerate(META_FIELDS):
                try:
                    item = data[i]
                    d[label] = item[1] if (isinstance(item, list) and len(item) == 2
                                           and item[0] == label) else None
                except Exception:
                    d[label] = None
            d["raw_tail"] = data[17:]
            yield md5, d


# ----- feature derivation from the labeled fields (NO re-parse needed) -----
def pc_histogram(total_pitches_counts, drums=False):
    """12-bin pitch-class histogram (np.float64, L1-normalized).
    Non-drum pitches are <128; drum tokens are >=128 in this corpus."""
    h = np.zeros(12, dtype=np.float64)
    if not total_pitches_counts:
        return h
    for p, c in total_pitches_counts:
        is_drum = p >= 128
        if is_drum != drums:
            continue
        h[(p % 128) % 12] += c
    s = h.sum()
    return h / s if s > 0 else h


def shannon_entropy(hist):
    p = hist[hist > 0]
    return float(-(p * np.log2(p)).sum()) if p.size else 0.0


# Krumhansl-Schmuckler key profiles (major, minor), normalized at use time.
_KS_MAJOR = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
_KS_MINOR = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
_PC_NAMES = ["C","C#","D","Eb","E","F","F#","G","Ab","A","Bb","B"]

def estimate_key(pc_hist):
    """Return (key_str, mode, confidence). confidence = best_corr - 2nd_best_corr."""
    if pc_hist.sum() <= 0:
        return None, None, 0.0
    x = pc_hist - pc_hist.mean()
    def corr(profile):
        p = profile - profile.mean()
        denom = math.sqrt((x * x).sum() * (p * p).sum())
        return (x * p).sum() / denom if denom else 0.0
    scores = []  # (corr, name, mode)
    for tonic in range(12):
        scores.append((corr(np.roll(_KS_MAJOR, tonic)), _PC_NAMES[tonic], "major"))
        scores.append((corr(np.roll(_KS_MINOR, tonic)), _PC_NAMES[tonic], "minor"))
    scores.sort(reverse=True)
    best = scores[0]
    conf = round(best[0] - scores[1][0], 4)
    return f"{best[1]} {best[2]}", best[2], conf


# ----- resumable parquet helpers -----
def load_done_md5s(parquet_path):
    if not os.path.exists(parquet_path):
        return set()
    import pandas as pd
    try:
        return set(pd.read_parquet(parquet_path, columns=["md5"])["md5"])
    except Exception:
        return set()


def write_parquet_atomic(df, parquet_path):
    import pandas as pd  # noqa
    tmp = parquet_path + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, parquet_path)


if __name__ == "__main__":
    # self-test: parse a handful of records and derive features end-to-end
    log("self-test: reading first 5 META_DATA records")
    n = 0
    for md5, d in iter_meta_pickles():
        pc = pc_histogram(d["total_pitches_counts"])
        key, mode, conf = estimate_key(pc)
        ent = shannon_entropy(pc)
        log(f"  {md5} key={key} conf={conf} entropy={ent:.2f} patches={d['midi_patches']}")
        n += 1
        if n >= 5:
            break
    log("self-test OK")
