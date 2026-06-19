#!/usr/bin/env python3
"""33_drum_catalog.py — fold DrumDNA scalars into the catalog.
Non-destructive: only adds columns, backs up first.
"""
import os, sys, shutil, sqlite3, datetime
import pandas as pd
import numpy as np

ROOT = "/mnt/2FAST/MIDIS_ALL_REAL"
META_PARQUET = os.path.join(ROOT, "catalog/metadata.parquet")
SQLITE = os.path.join(ROOT, "catalog/catalog.sqlite")
CKPT_DIR = os.path.join(ROOT, "catalog/checkpoints")
DRUM_PARQUET = os.path.join(ROOT, "_work/drum_dna.parquet")
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def log(m): print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)

DRUM_COLS_MAP = {
    "kick_density": "drum_kick_density",
    "snare_density": "drum_snare_density",
    "hat_density": "drum_hat_density",
    "cymbal_density": "drum_cymbal_density",
    "tom_density": "drum_tom_density",
    "total_density": "drum_total_density",
    "perc_diversity": "drum_perc_diversity",
    "kick_on_downbeat": "drum_kick_on_downbeat",
    "snare_backbeat": "drum_snare_backbeat",
    "kick_snare_interlock": "drum_kick_snare_interlock",
    "swing": "drum_swing",
    "laidback": "drum_laidback",
    "timing_tightness": "drum_timing_tightness",
    "syncopation_poly": "drum_syncopation_poly",
    "ghost_dynamics": "drum_ghost_dynamics",
    "accent_strength": "drum_accent_strength",
    "pattern_entropy": "drum_pattern_entropy",
    "bar_variance": "drum_bar_variance",
    "symmetry": "drum_symmetry",
    "pulse_clarity": "drum_pulse_clarity",
    "beat1_accent": "drum_beat1_accent",
    "beat2_accent": "drum_beat2_accent",
    "beat3_accent": "drum_beat3_accent",
    "beat4_accent": "drum_beat4_accent"
}

def main():
    log("=== 33 drum catalog merge: folding DrumDNA into metadata ===")
    if not os.path.exists(DRUM_PARQUET):
        raise SystemExit(f"MISSING {DRUM_PARQUET} — run 31_drum_vector.py first")

    os.makedirs(CKPT_DIR, exist_ok=True)
    shutil.copy2(SQLITE, os.path.join(CKPT_DIR, f"catalog_{TS}_pre_drum.sqlite"))
    shutil.copy2(META_PARQUET, META_PARQUET + f".bak_{TS}")

    # 1. Load data
    full = pd.read_parquet(META_PARQUET)
    source_cols = ["md5"] + list(DRUM_COLS_MAP.keys())
    drum = pd.read_parquet(DRUM_PARQUET, columns=source_cols).drop_duplicates("md5")
    drum = drum.rename(columns=DRUM_COLS_MAP)

    new_cols = [c for c in DRUM_COLS_MAP.values() if c not in full.columns]
    if not new_cols:
        log("No new columns to add. Already merged?")
        return

    log(f"Adding {len(new_cols)} columns")

    # 2. Update Parquet
    sub = drum[["md5"] + new_cols]
    merged = full.merge(sub, on="md5", how="left")
    merged.to_parquet(META_PARQUET + ".tmp", index=False)
    os.replace(META_PARQUET + ".tmp", META_PARQUET)
    log(f"Updated {META_PARQUET}")

    # 3. Update SQLite
    con = sqlite3.connect(SQLITE)
    cur = con.cursor()
    for c in new_cols:
        dtype = sub[c].dtype
        sql_t = "INTEGER" if pd.api.types.is_integer_dtype(dtype) else "REAL"
        cur.execute(f'ALTER TABLE metadata ADD COLUMN "{c}" {sql_t}')

    # Batch update via temp table
    sub.to_sql("drum_patch", con, if_exists="replace", index=False)
    cur.execute("CREATE INDEX idx_drum_patch_md5 ON drum_patch(md5)")
    set_clause = ", ".join(f'"{c}" = (SELECT p."{c}" FROM drum_patch p WHERE p.md5 = metadata.md5)'
                           for c in new_cols)
    cur.execute(f"UPDATE metadata SET {set_clause}")
    cur.execute("DROP TABLE drum_patch")
    con.commit()
    con.close()
    log(f"Updated {SQLITE}")
    log("DONE")

if __name__ == "__main__":
    main()
