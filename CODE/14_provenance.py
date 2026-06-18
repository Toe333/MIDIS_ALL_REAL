#!/usr/bin/env python3
"""14_provenance.py — Phase 5 targeted tagging (composer/title/genre/era).

Reality: LAMD/Lakh/bitmidi basenames are MD5 hashes (no usable names), so this
is a TARGETED job: mine real names where they exist (~38k ragtime/maestro/personal),
mine embedded MIDI text events, and apply LOW-confidence genre rules from features
already computed. `unknown` is the honest default.

Reads: master_manifest.parquet, _work/features_pickle.parquet, metadata.parquet
Output: _work/provenance.parquet (md5-keyed)
Usage:  python3 CODE/14_provenance.py
"""
import os, sys, re, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

OUT = os.path.join(C.WORK, "provenance.parquet")

COMPOSER_RE = re.compile(r"[Cc]omposer[_\- ]?([A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)?)")
DECADE_RE   = re.compile(r"(19[2-9]0|20[0-2]0|[2-9]0s)")
SEP_RE      = re.compile(r"^([\w .'&]+?)\s*-\s*([\w .'&]+?)$")


def mine_name(paths):
    """Return (composer, title, method) from the most human-readable basename."""
    for p in paths:
        base = os.path.basename(p)
        stem = re.sub(r"\.midi?$", "", base, flags=re.I)
        # skip pure-hash names
        if re.fullmatch(r"[0-9a-f]{32}(_\d+)?", stem):
            continue
        m = COMPOSER_RE.search(stem)
        if m:
            return m.group(1), None, "filename"
        m = SEP_RE.match(stem.replace("_", " "))
        if m and not re.fullmatch(r"[0-9a-f ]+", m.group(1)):
            return m.group(1).strip(), m.group(2).strip(), "filename"
    return None, None, None


def mine_era(paths):
    for p in paths:
        m = DECADE_RE.search(os.path.basename(p))
        if m:
            return m.group(1), 0.5
    return None, 0.0


def genre_rule(row):
    """Coarse, LOW-confidence. Returns (genre, confidence, method)."""
    has_drums = bool(row.get("has_drums"))
    piano_only = (row.get("n_piano_tracks", 0) > 0 and not has_drums
                  and row.get("n_guitar_tracks", 0) == 0 and row.get("n_synth_tracks", 0) == 0)
    bpm = row.get("bpm") or 0
    ext = bool(row.get("has_extended_harmony"))
    span = row.get("register_span_semitones") or 0
    # Deliberately CONSERVATIVE: only the high-precision, specific cases get a
    # tag; everything else stays `unknown`. (An earlier broad jazz rule labeled
    # 34% of the corpus jazz — meaningless. Rules ordered most-specific first.)
    nuc = row.get("n_unique_chords", 0) or 0
    if row.get("is_solo") and row.get("n_piano_tracks", 0) > 0 and not has_drums:
        return "solo_piano", 0.5, "rule"
    if piano_only and span and span > 45 and not has_drums and nuc > 8:
        return "classical", 0.35, "rule"
    if has_drums and 118 <= bpm <= 140 and row.get("n_synth_tracks", 0) > 0 \
            and row.get("n_piano_tracks", 0) == 0:
        return "electronic", 0.3, "rule"
    if ext and nuc > 80 and has_drums and row.get("has_bass"):  # full-band rich harmony
        return "jazz", 0.25, "rule"
    return "unknown", 0.0, "unknown"


def main():
    man = pd.read_parquet(os.path.join(C.CATALOG, "master_manifest.parquet"),
                          columns=["md5", "original_paths", "sources"])
    feat = pd.read_parquet(os.path.join(C.WORK, "features_pickle.parquet"))
    meta = pd.read_parquet(os.path.join(C.CATALOG, "metadata.parquet"),
                           columns=["md5", "has_drums", "bpm", "lyric_events_count"])
    chords_p = os.path.join(C.ROOT, "CHORDS_DATA", "chords_summary.parquet")
    chords = pd.read_parquet(chords_p, columns=["md5", "n_unique_chords", "has_extended_harmony"]) \
        if os.path.exists(chords_p) else pd.DataFrame(columns=["md5"])

    df = feat.merge(meta, on="md5", how="left").merge(chords, on="md5", how="left")
    df = df.merge(man, on="md5", how="left")

    out = []
    for r in df.itertuples(index=False):
        d = r._asdict()
        paths = d.get("original_paths")
        paths = list(paths) if paths is not None else []
        comp, title, nm_method = mine_name(paths)
        era, era_conf = mine_era(paths)
        genre, gconf, gmethod = genre_rule(d)
        out.append(dict(
            md5=d["md5"], composer=comp, title=title, artist=None,
            extraction_method=nm_method or "none",
            has_lyrics=int((d.get("lyric_events_count") or 0) > 0),
            genre_hint=genre, genre_confidence=gconf, genre_method=gmethod,
            era_hint=era, era_confidence=era_conf,
        ))
    odf = pd.DataFrame(out)
    C.write_parquet_atomic(odf, OUT)
    C.log(f"provenance DONE: {len(odf)} rows -> {OUT}", "provenance.log")
    C.log(f"  named files: {int(odf['composer'].notna().sum())}, "
          f"genre dist: {odf['genre_hint'].value_counts().to_dict()}", "provenance.log")
    C.progress("PHASE5", f"rows={len(odf)} named={int(odf['composer'].notna().sum())}")


if __name__ == "__main__":
    main()
