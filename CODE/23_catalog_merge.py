#!/usr/bin/env python3
"""23_catalog_merge.py — fold the Phase-9 sequence features into the catalog.

Adds the rhythm / melody / harmony / structure columns produced by the cache-based
passes (21 seq_features, 22 rhythm, 24 melody, 25 harmony) onto the 80-col catalog.

NON-DESTRUCTIVE, mirrors 19_quality_flags.py:
  * Backs up sqlite + metadata.parquet to catalog/checkpoints/ FIRST.
  * Only ADDS columns (no existing column is overwritten). New column names were
    checked to not collide with the existing 80.
  * Writes metadata.parquet atomically, then ALTER TABLE ADD COLUMN + UPDATE the
    sqlite `metadata` table (preserves all views), and VERIFIES parquet<->sqlite.

Authoritative source per pillar (avoid duplicate/over-lapping columns):
  * RHYTHM  swing/dotted/triplet/straight  <- 22 (validated BUR + log-snapped values)
  * MELODY  contour/phrases/motif          <- 24 (supersedes 21's first-pass melody)
  * HARMONY chords/modulation/tension      <- 25
  * STRUCTURE + rhythm CONTEXT + tempo     <- 21 (only the cols 22 doesn't cover)
"""
import os, sys, shutil, sqlite3, datetime
import pandas as pd
import numpy as np

ROOT = "/mnt/2FAST/MIDIS_ALL_REAL"
WORK = os.path.join(ROOT, "_work")
META_PARQUET = os.path.join(ROOT, "catalog/metadata.parquet")
SQLITE = os.path.join(ROOT, "catalog/catalog.sqlite")
CKPT_DIR = os.path.join(ROOT, "catalog/checkpoints")
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# curated column selection per source (md5 is the join key, added separately)
COLS_21 = [  # structure + rhythm-context + tempo (NOT swing/dotted -> that's 22)
    "n_sections", "has_repetition", "repetition_ratio",
    "onset_density_per_beat", "syncopation", "offbeat_ratio", "downbeat_ratio",
    "quant_tightness_16", "quant_tightness_triplet", "triplet_feel",
    "grid_dev_std", "microtiming_ms", "pulse_clarity", "polyrhythm_hint",
    "n_rhythm_voices", "articulation_mean", "total_beats", "n_onsets",
    "n_tempo_changes", "tempo_class", "tempo_cv", "seq_ok",
]
COLS_22 = [
    "swing_bur", "swing_confidence", "swing_n_beats", "eighth_subdiv_ratio",
    "is_swung", "is_triplet_feel", "is_dotted",
    "ioi_straight_ratio", "ioi_dotted_ratio", "ioi_triplet_ratio", "ioi_free_ratio",
    "dur_straight_ratio", "dur_dotted_ratio", "dur_triplet_ratio", "dotted_pair_ratio",
]
COLS_24 = [
    "has_melody", "melody_channel", "melody_n_notes", "mel_pitch_mean", "mel_range",
    "mel_pc_entropy", "mel_stepwise_ratio", "mel_leap_ratio", "mel_repeat_ratio",
    "mel_interval_mean_abs", "mel_up_ratio", "mel_direction_changes", "mel_chromaticism",
    "mel_rhythm_straight", "mel_rhythm_dotted", "mel_rhythm_triplet",
    "mel_n_phrases", "mel_mean_phrase_notes", "mel_motif_repeat",
]
COLS_25 = [
    "n_chord_segments", "harmonic_rhythm", "chord_change_rate", "n_distinct_chord_roots",
    "dominant_function_ratio", "dissonance_mean", "dissonance_std", "progression_entropy",
    "n_key_areas", "key_changes", "key_stability", "diatonic_ratio",
]
BOOL_COLS = {"has_repetition", "is_swung", "is_triplet_feel", "is_dotted",
             "has_melody", "seq_ok"}

SOURCES = [
    (os.path.join(WORK, "seq_features.parquet"), COLS_21),
    (os.path.join(WORK, "rhythm_features.parquet"), COLS_22),
    (os.path.join(WORK, "melody_features.parquet"), COLS_24),
    (os.path.join(WORK, "harmony_features.parquet"), COLS_25),
]


def log(m): print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


def sql_type(dtype):
    if pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_bool_dtype(dtype):
        return "INTEGER"
    if pd.api.types.is_float_dtype(dtype):
        return "REAL"
    return "TEXT"


def build_patch():
    """Load all sources, select curated cols, left-merge onto metadata's md5 list."""
    base = pd.read_parquet(META_PARQUET, columns=["md5"])
    n_existing = pd.read_parquet(META_PARQUET).shape[1]
    log(f"catalog has {len(base)} rows, {n_existing} existing columns")
    patch = base.copy()
    for path, cols in SOURCES:
        if not os.path.exists(path):
            raise SystemExit(f"MISSING source {path} — run the refine passes first")
        df = pd.read_parquet(path)
        have = [c for c in cols if c in df.columns]
        missing = set(cols) - set(have)
        if missing:
            log(f"  WARN {os.path.basename(path)} missing cols: {sorted(missing)}")
        sub = df[["md5"] + have].drop_duplicates("md5")
        patch = patch.merge(sub, on="md5", how="left")
        log(f"  + {os.path.basename(path)}: {len(have)} cols (matched "
            f"{int(sub['md5'].isin(base['md5']).sum())} md5s)")
    # bool -> nullable int (NaN stays NaN -> SQL NULL)
    for c in BOOL_COLS:
        if c in patch.columns:
            patch[c] = patch[c].map({True: 1, False: 0, 1: 1, 0: 0})
    return patch, n_existing


def write_parquet(patch):
    full = pd.read_parquet(META_PARQUET)
    newcols = [c for c in patch.columns if c != "md5"]
    add = patch.set_index("md5")[newcols]
    merged = full.merge(add, on="md5", how="left")
    assert len(merged) == len(full), "row count changed!"
    tmp = META_PARQUET + ".tmp"
    merged.to_parquet(tmp, index=False)
    os.replace(tmp, META_PARQUET)
    log(f"  wrote {META_PARQUET}: {full.shape[1]} -> {merged.shape[1]} cols, {len(merged)} rows")
    return merged, newcols


def write_sqlite(patch, newcols):
    con = sqlite3.connect(SQLITE); cur = con.cursor()
    existing = {r[1] for r in cur.execute("PRAGMA table_info(metadata)")}
    # add columns
    for c in newcols:
        if c not in existing:
            cur.execute(f'ALTER TABLE metadata ADD COLUMN "{c}" {sql_type(patch[c].dtype)}')
    log(f"  added {len([c for c in newcols if c not in existing])} columns to sqlite metadata")
    # stage patch in a temp table, then UPDATE ... FROM
    patch.to_sql("seq_patch", con, if_exists="replace", index=False)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_seq_patch_md5 ON seq_patch(md5)")
    set_clause = ", ".join(f'"{c}" = (SELECT p."{c}" FROM seq_patch p WHERE p.md5 = metadata.md5)'
                           for c in newcols)
    cur.execute(f"UPDATE metadata SET {set_clause}")
    cur.execute("DROP TABLE seq_patch")
    # helpful indexes for the most-queried new flags
    for c in ("is_swung", "is_dotted", "has_melody", "tempo_class"):
        if c in newcols:
            cur.execute(f'CREATE INDEX IF NOT EXISTS idx_meta_{c} ON metadata("{c}")')
    con.commit()
    # verify
    ncols = cur.execute("SELECT count(*) FROM pragma_table_info('metadata')").fetchone()[0]
    log(f"  sqlite metadata now {ncols} columns")
    for q, lbl in [
        ("SELECT count(*) FROM metadata WHERE is_swung=1", "is_swung=1"),
        ("SELECT count(*) FROM metadata WHERE is_dotted=1", "is_dotted=1"),
        ("SELECT count(*) FROM metadata WHERE has_melody=1", "has_melody=1"),
        ("SELECT count(*) FROM metadata WHERE swing_bur IS NOT NULL", "swing_bur not null"),
        ("SELECT count(*) FROM catalog", "catalog view still works"),
    ]:
        log(f"  VERIFY {lbl}: {cur.execute(q).fetchone()[0]}")
    con.close()
    return ncols


def main():
    log("=== 23 catalog merge: rhythm+melody+harmony+structure ===")
    os.makedirs(CKPT_DIR, exist_ok=True)
    sq_bak = os.path.join(CKPT_DIR, f"catalog_{TS}_pre_seqmerge.sqlite")
    pq_bak = META_PARQUET + f".bak_{TS}"
    log(f"backup sqlite  -> {sq_bak}");  shutil.copy2(SQLITE, sq_bak)
    log(f"backup parquet -> {pq_bak}"); shutil.copy2(META_PARQUET, pq_bak)

    patch, n_existing = build_patch()
    merged, newcols = write_parquet(patch)
    sql_cols = write_sqlite(patch, newcols)

    # final cross-check
    pq_cols = merged.shape[1]
    log(f"CROSS-CHECK parquet cols={pq_cols}  sqlite cols={sql_cols}  "
        f"({'AGREE' if pq_cols == sql_cols else 'MISMATCH!'})")
    log(f"added {len(newcols)} new columns ({n_existing} -> {pq_cols})")
    log("DONE")


if __name__ == "__main__":
    main()
