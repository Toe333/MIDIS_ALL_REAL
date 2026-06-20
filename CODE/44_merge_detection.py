#!/usr/bin/env python3
"""
44_merge_detection.py — fold the validated v2 detection columns into the catalog.

ADDITIVE: originals (bpm, key, mode, time_signature, key_confidence) are kept
untouched; v2 lives alongside them. Re-runnable (skips already-present columns).
Checkpoint catalog/ before running (the session that calls this already did).

Adds, keyed by md5:
  from tempo_meter_v2.parquet: bpm_v2, bpm_min, bpm_max, n_tempo_events, has_tempo,
       ts_v2, n_tsig, ts_present, ts_final, ts_inferred, felt_bpm, felt_tempo_adjusted
  from key_v2.parquet:        key_v2, mode_v2, key_corr, key_margin, key_alt, tonal_strength
"""
import os, sqlite3, pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
META = ROOT / "catalog" / "metadata.parquet"
SQL  = ROOT / "catalog" / "catalog.sqlite"

TM_COLS = ["bpm_v2","bpm_min","bpm_max","n_tempo_events","has_tempo","ts_v2",
           "n_tsig","ts_present","ts_final","ts_inferred","felt_bpm","felt_tempo_adjusted"]
KV_COLS = ["key_v2","mode_v2","key_corr","key_margin","key_alt","tonal_strength"]

def sql_type(s):
    if pd.api.types.is_bool_dtype(s) or pd.api.types.is_integer_dtype(s): return "INTEGER"
    if pd.api.types.is_float_dtype(s): return "REAL"
    return "TEXT"

def main():
    full = pd.read_parquet(META)
    tm   = pd.read_parquet(ROOT/"_work/tempo_meter_v2.parquet")[["md5"]+TM_COLS]
    kv   = pd.read_parquet(ROOT/"_work/key_v2.parquet")[["md5"]+KV_COLS]
    # bools -> int8 for clean storage
    for c in ["has_tempo","ts_present"]:
        if c in tm: tm[c] = tm[c].astype("int8")
    patch = tm.merge(kv, on="md5", how="outer")
    new_cols = [c for c in TM_COLS+KV_COLS if c not in full.columns]
    print(f"adding {len(new_cols)} columns: {new_cols}")
    if not new_cols:
        print("nothing new — already merged."); return

    # 1. parquet
    merged = full.merge(patch[["md5"]+new_cols], on="md5", how="left")
    assert len(merged) == len(full), "row count changed!"
    merged.to_parquet(str(META)+".tmp", index=False)
    os.replace(str(META)+".tmp", META)
    print(f"parquet updated: {len(merged):,} rows x {len(merged.columns)} cols")

    # 2. sqlite (ALTER + temp-table UPDATE, same pattern as 33_drum_catalog)
    con = sqlite3.connect(SQL); cur = con.cursor()
    for c in new_cols:
        cur.execute(f'ALTER TABLE metadata ADD COLUMN "{c}" {sql_type(patch[c])}')
    sub = patch[["md5"]+new_cols]
    sub.to_sql("detect_patch", con, if_exists="replace", index=False)
    cur.execute("CREATE INDEX idx_detect_patch_md5 ON detect_patch(md5)")
    set_clause = ", ".join(f'"{c}" = (SELECT p."{c}" FROM detect_patch p WHERE p.md5 = metadata.md5)'
                           for c in new_cols)
    cur.execute(f"UPDATE metadata SET {set_clause}")
    cur.execute("DROP TABLE detect_patch")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_meta_ts_final ON metadata(ts_final)")
    con.commit()
    # verify
    n = cur.execute("SELECT count(*) FROM metadata WHERE bpm_v2 IS NOT NULL").fetchone()[0]
    fixed = cur.execute("SELECT count(*) FROM metadata WHERE abs(bpm-bpm_v2)>5").fetchone()[0]
    realmeter = cur.execute("SELECT count(*) FROM metadata WHERE ts_inferred=0").fetchone()[0]
    con.close()
    print(f"sqlite updated: bpm_v2 set on {n:,} rows; {fixed:,} differ from old bpm by >5; "
          f"{realmeter:,} real (non-inferred) meters")

if __name__ == "__main__":
    main()
