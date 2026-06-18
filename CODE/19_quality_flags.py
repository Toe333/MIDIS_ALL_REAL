#!/usr/bin/env python3
"""
KNOWN GAPS fix #3 + #4 + #5 (see STATE.md). No reparse; all derivable from
existing columns. Non-destructive: original values preserved in backups, and
corrections are recoverable via the added flag columns.

#3 time_signature (15% bad/missing):
    33,717 NULL + 32,639 bogus '1/4' + 2,008 '1/8' (parse artifacts -- 1/N
    meters aren't real here, they're TMIDIX defaults). Fill all to '4/4'
    (the MIDI spec default when no valid meter) and set time_signature_inferred=1
    so every touched row is flagged/recoverable. Genuine meters keep inferred=0.

#4 bpm outliers:
    Add bpm_valid (1 when 20<=bpm<=300, else 0). 7,297 invalid
    (5,393 NULL + 1,564 >300 + 340 <20). bpm itself is NOT overwritten --
    raw per-file tempo events aren't stored, so we flag rather than fabricate.
    Users who want a default can COALESCE(bpm,120) (MIDI default).

#5 duration outliers:
    Add duration_suspect (1 when duration_sec>3600). ~289 files up to 9.9h --
    almost all stuck-note / junk that parses fine. NULL duration -> not suspect.

Adds 3 columns (77 -> 80). Touches metadata.parquet + sqlite metadata table.
"""
import os, shutil, sqlite3, datetime
import pandas as pd

ROOT = "/mnt/2FAST/MIDIS_ALL_REAL"
META_PARQUET = os.path.join(ROOT, "catalog/metadata.parquet")
SQLITE = os.path.join(ROOT, "catalog/catalog.sqlite")
CKPT_DIR = os.path.join(ROOT, "catalog/checkpoints")
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

BAD_TS = {"1/4", "1/8"}          # parse artifacts, not real meters
BPM_LO, BPM_HI = 20.0, 300.0
DUR_SUSPECT_SEC = 3600.0         # > 1 hour

def log(m): print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)

def backup():
    os.makedirs(CKPT_DIR, exist_ok=True)
    sq_bak = os.path.join(CKPT_DIR, f"catalog_{TS}_pre_gaps345.sqlite")
    pq_bak = META_PARQUET + f".bak_{TS}"
    log(f"backup sqlite -> {sq_bak}");  shutil.copy2(SQLITE, sq_bak)
    log(f"backup parquet -> {pq_bak}"); shutil.copy2(META_PARQUET, pq_bak)

def fix_parquet():
    df = pd.read_parquet(META_PARQUET)
    n = len(df)
    # ---- #3 time_signature ----
    ts = df["time_signature"]
    bad = ts.isna() | (ts.astype(str).str.len() == 0) | ts.isin(BAD_TS)
    df["time_signature_inferred"] = bad.astype(int)
    df.loc[bad, "time_signature"] = "4/4"
    log(f"  #3 time_signature: {int(bad.sum())} rows -> '4/4' (inferred=1); "
        f"top values now {df['time_signature'].value_counts().head(4).to_dict()}")
    # ---- #4 bpm_valid ----
    bpm = df["bpm"]
    df["bpm_valid"] = ((bpm >= BPM_LO) & (bpm <= BPM_HI)).fillna(False).astype(int)
    log(f"  #4 bpm_valid: valid={int(df['bpm_valid'].sum())} "
        f"invalid={int((df['bpm_valid']==0).sum())}")
    # ---- #5 duration_suspect ----
    df["duration_suspect"] = (df["duration_sec"] > DUR_SUSPECT_SEC).fillna(False).astype(int)
    log(f"  #5 duration_suspect: {int(df['duration_suspect'].sum())} rows (>1h)")
    # atomic write
    tmp = META_PARQUET + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, META_PARQUET)
    log(f"  wrote {META_PARQUET} ({len(df.columns)} cols)")
    return df[["md5", "time_signature", "time_signature_inferred", "bpm_valid", "duration_suspect"]]

def fix_sqlite(patch):
    con = sqlite3.connect(SQLITE); cur = con.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(metadata)")]
    for c, t in (("time_signature_inferred", "INTEGER"),
                 ("bpm_valid", "INTEGER"),
                 ("duration_suspect", "INTEGER")):
        if c not in cols:
            cur.execute(f"ALTER TABLE metadata ADD COLUMN {c} {t}")
            log(f"  ALTER metadata ADD COLUMN {c}")
    cur.execute("CREATE TEMP TABLE q_patch(md5 TEXT PRIMARY KEY, time_signature TEXT, "
                "time_signature_inferred INT, bpm_valid INT, duration_suspect INT)")
    cur.executemany("INSERT INTO q_patch VALUES (?,?,?,?,?)",
                    patch.itertuples(index=False, name=None))
    cur.execute("""UPDATE metadata SET
        time_signature          = (SELECT p.time_signature          FROM q_patch p WHERE p.md5=metadata.md5),
        time_signature_inferred = (SELECT p.time_signature_inferred FROM q_patch p WHERE p.md5=metadata.md5),
        bpm_valid               = (SELECT p.bpm_valid               FROM q_patch p WHERE p.md5=metadata.md5),
        duration_suspect        = (SELECT p.duration_suspect        FROM q_patch p WHERE p.md5=metadata.md5)""")
    for c in ("bpm_valid", "duration_suspect", "time_signature_inferred"):
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_meta_{c} ON metadata({c})")
    con.commit()
    checks = {
        "ts NULL":              "SELECT count(*) FROM metadata WHERE time_signature IS NULL OR time_signature=''",
        "ts bad artifacts":     "SELECT count(*) FROM metadata WHERE time_signature IN ('1/4','1/8')",
        "ts inferred":          "SELECT count(*) FROM metadata WHERE time_signature_inferred=1",
        "ts top4":              "SELECT time_signature||':'||count(*) FROM metadata GROUP BY time_signature ORDER BY count(*) DESC LIMIT 4",
        "bpm_valid=1":          "SELECT count(*) FROM metadata WHERE bpm_valid=1",
        "bpm_valid=0":          "SELECT count(*) FROM metadata WHERE bpm_valid=0",
        "duration_suspect=1":   "SELECT count(*) FROM metadata WHERE duration_suspect=1",
        "col count":            "SELECT count(*) FROM pragma_table_info('metadata')",
    }
    for label, q in checks.items():
        log(f"  VERIFY {label}: {[r[0] for r in cur.execute(q).fetchall()]}")
    con.close()

def main():
    log("=== KNOWN GAPS #3+#4+#5 fix ===")
    backup()
    fix_sqlite(fix_parquet())
    log("DONE")

if __name__ == "__main__":
    main()
