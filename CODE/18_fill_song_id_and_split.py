#!/usr/bin/env python3
"""
KNOWN GAPS fix #1 + #2 (see STATE.md).

#1 song_id on singletons:
    Every singleton (n_arrangements==1) had NULL song_id but is_canonical=1.
    Assign each its own song_id = "song_" + uuid5(NAMESPACE_DNS, md5).hex[:12]
    -- the IDENTICAL algorithm 12_signatures.py used for cluster roots, just
    applied to the file's own md5. n_arrangements(=1)/arrangement_rank(=0) are
    already correct, so only song_id is filled.

#2 split column:
    Splits live only as TOKENIZED/{train,val,test}_manifest.tsv (one stored
    path per line). Derive md5 = basename(path)[:-4], join into metadata as a
    new `split` column (+ sqlite index).

Touches: metadata.parquet, catalog.sqlite (metadata + manifest tables).
master_manifest.parquet has no song_id column (song_id lives in the sqlite
manifest table) -> intentionally out of scope.

Idempotent-ish: backs up both artifacts first; ADD COLUMN guarded by introspection.
"""
import os, sys, uuid, shutil, sqlite3, datetime
import pandas as pd

ROOT = "/mnt/2FAST/MIDIS_ALL_REAL"
META_PARQUET = os.path.join(ROOT, "catalog/metadata.parquet")
SQLITE = os.path.join(ROOT, "catalog/catalog.sqlite")
CKPT_DIR = os.path.join(ROOT, "catalog/checkpoints")
TOK = os.path.join(ROOT, "TOKENIZED")
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def sid(md5: str) -> str:
    return "song_" + uuid.uuid5(uuid.NAMESPACE_DNS, md5).hex[:12]

def log(m): print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)

# ---------------------------------------------------------------- split map
def load_split_map():
    mp = {}
    for split in ("train", "val", "test"):
        p = os.path.join(TOK, f"{split}_manifest.tsv")
        n = 0
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                md5 = os.path.basename(line)
                if md5.endswith(".mid"):
                    md5 = md5[:-4]
                mp[md5] = split
                n += 1
        log(f"  {split}: {n} paths")
    log(f"split map: {len(mp)} unique md5")
    return mp

# ---------------------------------------------------------------- backups
def backup():
    os.makedirs(CKPT_DIR, exist_ok=True)
    sq_bak = os.path.join(CKPT_DIR, f"catalog_{TS}_pre_gaps12.sqlite")
    pq_bak = META_PARQUET + f".bak_{TS}"
    log(f"backup sqlite -> {sq_bak}")
    shutil.copy2(SQLITE, sq_bak)
    log(f"backup parquet -> {pq_bak}")
    shutil.copy2(META_PARQUET, pq_bak)
    return sq_bak, pq_bak

# ---------------------------------------------------------------- parquet
def fix_parquet(split_map):
    df = pd.read_parquet(META_PARQUET)
    n = len(df)
    # #1 song_id
    mask = df["song_id"].isna() | (df["song_id"].astype(str).str.len() == 0)
    n_fill = int(mask.sum())
    df.loc[mask, "song_id"] = df.loc[mask, "md5"].map(sid)
    assert df["song_id"].isna().sum() == 0, "song_id still has NULLs"
    # collision sanity: distinct song_id == distinct (cluster ids + singletons)
    n_distinct = df["song_id"].nunique()
    log(f"  parquet song_id filled={n_fill}; distinct song_id now={n_distinct}")
    # #2 split
    df["split"] = df["md5"].map(split_map)
    n_nosplit = int(df["split"].isna().sum())
    if n_nosplit:
        raise SystemExit(f"ABORT: {n_nosplit} metadata rows have no split assignment")
    log(f"  parquet split assigned for all {n} rows: "
        f"{df['split'].value_counts().to_dict()}")
    # atomic write
    tmp = META_PARQUET + ".tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, META_PARQUET)
    log(f"  wrote {META_PARQUET} ({len(df.columns)} cols)")
    return df[["md5", "song_id", "split"]]

# ---------------------------------------------------------------- sqlite
def fix_sqlite(meta_patch):
    con = sqlite3.connect(SQLITE)
    cur = con.cursor()
    # --- metadata table ---
    cols = [r[1] for r in cur.execute("PRAGMA table_info(metadata)")]
    if "split" not in cols:
        cur.execute("ALTER TABLE metadata ADD COLUMN split TEXT")
        log("  ALTER metadata ADD COLUMN split")
    cur.execute("CREATE TEMP TABLE meta_patch(md5 TEXT PRIMARY KEY, song_id TEXT, split TEXT)")
    cur.executemany("INSERT INTO meta_patch VALUES (?,?,?)",
                    meta_patch.itertuples(index=False, name=None))
    cur.execute("UPDATE metadata SET song_id=(SELECT p.song_id FROM meta_patch p WHERE p.md5=metadata.md5), "
                "split=(SELECT p.split FROM meta_patch p WHERE p.md5=metadata.md5)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_meta_split ON metadata(split)")
    log(f"  metadata: updated song_id+split ({cur.rowcount} rows), idx_meta_split ensured")
    # --- manifest table: fill every NULL song_id with sid(md5) ---
    null_md5 = [r[0] for r in cur.execute(
        "SELECT md5 FROM manifest WHERE song_id IS NULL OR song_id=''")]
    man_patch = [(m, sid(m)) for m in null_md5]
    cur.execute("CREATE TEMP TABLE man_patch(md5 TEXT PRIMARY KEY, song_id TEXT)")
    cur.executemany("INSERT INTO man_patch VALUES (?,?)", man_patch)
    cur.execute("UPDATE manifest SET song_id=(SELECT p.song_id FROM man_patch p WHERE p.md5=manifest.md5) "
                "WHERE song_id IS NULL OR song_id=''")
    log(f"  manifest: filled {len(man_patch)} NULL song_id")
    con.commit()
    # --- verify ---
    checks = {
        "meta total": "SELECT count(*) FROM metadata",
        "meta song_id NULL": "SELECT count(*) FROM metadata WHERE song_id IS NULL OR song_id=''",
        "meta split NULL": "SELECT count(*) FROM metadata WHERE split IS NULL",
        "meta split breakdown": "SELECT split||':'||count(*) FROM metadata GROUP BY split",
        "manifest song_id NULL": "SELECT count(*) FROM manifest WHERE song_id IS NULL OR song_id=''",
        "meta distinct song_id": "SELECT count(DISTINCT song_id) FROM metadata",
    }
    for label, q in checks.items():
        rows = cur.execute(q).fetchall()
        log(f"  VERIFY {label}: {[r[0] for r in rows]}")
    con.close()

def main():
    log("=== KNOWN GAPS #1+#2 fix ===")
    split_map = load_split_map()
    backup()
    meta_patch = fix_parquet(split_map)
    fix_sqlite(meta_patch)
    log("DONE")

if __name__ == "__main__":
    main()
