"""
migrate_to_sqlserver.py
=======================
Migrates the MIDIS_ALL_REAL catalog (metadata.parquet + master_manifest.parquet)
into SQL Server LocalDB (MIDIS_ALL_REAL database) using pyodbc + fast_executemany.

Usage:
    python CODE/migrate_to_sqlserver.py [--dry-run] [--batch-size 2000] [--table metadata|manifest|all]

Tables created:
    dbo.metadata        — 459,805 rows × 148 cols (all catalog features)
    dbo.master_manifest — 463,896 rows × key manifest cols
"""

import argparse, sys, time, textwrap
from pathlib import Path
import pandas as pd
import numpy as np

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT   = Path(__file__).resolve().parent.parent          # B:\MIDIS_ALL_REAL
META_P = ROOT / "catalog" / "metadata.parquet"
MAN_P  = ROOT / "catalog" / "master_manifest.parquet"

# ── SQL Server connection ─────────────────────────────────────────────────────
def _build_conn_str() -> str:
    """Return the first available ODBC driver connection string for LocalDB."""
    import pyodbc
    available = {d.lower() for d in pyodbc.drivers()}
    for drv in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server"):
        if drv.lower() in available:
            return (
                f"DRIVER={{{drv}}};"
                "SERVER=(localdb)\\MSSQLLocalDB;"
                "DATABASE=MIDIS_ALL_REAL;"
                "Trusted_Connection=yes;"
                "TrustServerCertificate=yes;"
            )
    installed = ", ".join(d for d in pyodbc.drivers() if "sql" in d.lower()) or "none"
    raise RuntimeError(
        "ODBC Driver 17 or 18 for SQL Server not found.\n"
        f"  Installed SQL drivers: {installed}\n"
        r"  Fix: right-click install_odbc17_RUNAS_ADMIN.bat → Run as administrator"
    )


CONN_STR: str = ""   # populated lazily in main()

# ── type mapping: pandas/numpy → SQL Server ───────────────────────────────────
def pd_dtype_to_sql(col: pd.Series) -> str:
    dt = col.dtype
    if pd.api.types.is_bool_dtype(dt):
        return "BIT"
    if pd.api.types.is_integer_dtype(dt):
        mx = col.abs().max() if len(col) else 0
        if pd.isna(mx): mx = 0
        return "BIGINT" if mx > 2_147_483_647 else "INT"
    if pd.api.types.is_float_dtype(dt):
        return "FLOAT"
    # string / object / categorical
    try:
        max_len = int(col.astype(str).str.len().max())
    except Exception:
        max_len = 255
    if max_len > 4000:
        return "NVARCHAR(MAX)"
    return f"NVARCHAR({max(max_len + 10, 50)})"


def safe_val(v):
    """Convert NaN / numpy scalars / arrays to Python-native for pyodbc."""
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, np.ndarray):
        return "|".join(str(x) for x in v.tolist())
    if isinstance(v, list):
        return "|".join(str(x) for x in v)
    return v


def migrate_table(conn, df: pd.DataFrame, table_name: str, batch_size: int, dry_run: bool):
    # ── sanitise column names (no spaces, no reserved words clash) ──
    df = df.copy()
    df.columns = [c.replace(" ", "_").replace("-", "_") for c in df.columns]

    # ── build CREATE TABLE ──
    col_defs = []
    for c in df.columns:
        sql_type = pd_dtype_to_sql(df[c])
        col_defs.append(f"    [{c}] {sql_type}")
    create_sql = (
        f"IF OBJECT_ID('dbo.{table_name}', 'U') IS NOT NULL "
        f"DROP TABLE dbo.{table_name};\n"
        f"CREATE TABLE dbo.{table_name} (\n"
        + ",\n".join(col_defs)
        + "\n);"
    )

    if dry_run:
        print(f"\n[DRY RUN] Would create dbo.{table_name} ({len(df.columns)} cols, {len(df):,} rows)")
        print(textwrap.indent(create_sql[:800] + "...", "  "))
        return

    cur = conn.cursor()
    print(f"\nCreating dbo.{table_name} ({len(df.columns)} cols)...")
    cur.execute(create_sql)
    conn.commit()

    # ── INSERT in batches ──
    placeholders = ", ".join(["?" ] * len(df.columns))
    insert_sql   = f"INSERT INTO dbo.{table_name} VALUES ({placeholders})"
    cur.fast_executemany = True

    total  = len(df)
    loaded = 0
    t0     = time.time()

    for start in range(0, total, batch_size):
        chunk = df.iloc[start : start + batch_size]
        rows  = [tuple(safe_val(v) for v in row) for row in chunk.itertuples(index=False)]
        cur.executemany(insert_sql, rows)
        conn.commit()
        loaded += len(rows)
        elapsed = time.time() - t0
        rate    = loaded / elapsed if elapsed > 0 else 0
        pct     = 100 * loaded / total
        print(f"  {loaded:>9,}/{total:,}  {pct:5.1f}%  {rate:,.0f} rows/s", end="\r", flush=True)

    print(f"\n  ✅ {loaded:,} rows loaded in {time.time()-t0:.1f}s")
    cur.close()


def add_indexes(conn, table_name: str, index_cols: list[str]):
    cur = conn.cursor()
    for col in index_cols:
        try:
            idx = f"idx_{table_name}_{col}"
            cur.execute(f"CREATE INDEX [{idx}] ON dbo.{table_name} ([{col}])")
            conn.commit()
            print(f"  ↳ index on [{col}]")
        except Exception as e:
            print(f"  ⚠  index on [{col}] skipped: {e}")
    cur.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run",    action="store_true")
    ap.add_argument("--batch-size", type=int, default=2000)
    ap.add_argument("--table",      choices=["metadata", "manifest", "all"], default="all")
    args = ap.parse_args()

    # ── check pyodbc ──
    try:
        import pyodbc
    except ImportError:
        print("pyodbc not found — installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyodbc"])
        import pyodbc

    if not args.dry_run:
        print("Connecting to SQL Server LocalDB...")
        conn_str = _build_conn_str()
        conn = pyodbc.connect(conn_str, autocommit=False)
        print("Connected ✅")
    else:
        conn = None

    # ── METADATA ──
    if args.table in ("metadata", "all"):
        print(f"\nReading {META_P} ...")
        df = pd.read_parquet(META_P)
        # drop heavy array cols (groove_dna float32[11] → not storable as a plain column)
        array_cols = [c for c in df.columns if df[c].dtype == object
                      and df[c].dropna().apply(lambda x: hasattr(x, '__len__') and not isinstance(x, str)).any()]
        if array_cols:
            print(f"  Dropping array cols: {array_cols}")
            df = df.drop(columns=array_cols)
        print(f"  Shape: {df.shape}")
        migrate_table(conn, df, "metadata", args.batch_size, args.dry_run)
        if not args.dry_run:
            add_indexes(conn, "metadata", ["md5", "song_id", "split", "key", "mode",
                                           "quality_flag", "bpm_valid", "duration_suspect"])

    # ── MANIFEST ──
    if args.table in ("manifest", "all"):
        print(f"\nReading {MAN_P} ...")
        df = pd.read_parquet(MAN_P)
        # original_paths is a list column — stringify it
        if "original_paths" in df.columns:
            df["original_paths"] = df["original_paths"].apply(
                lambda x: "|".join(x) if isinstance(x, list) else str(x) if x is not None else None
            )
        print(f"  Shape: {df.shape}")
        migrate_table(conn, df, "master_manifest", args.batch_size, args.dry_run)
        if not args.dry_run:
            add_indexes(conn, "master_manifest", ["md5", "song_id", "is_quarantined"])

    if not args.dry_run and conn:
        conn.close()
        print("\nAll done. Connection closed.")
    else:
        print("\n[DRY RUN complete — no data written]")


if __name__ == "__main__":
    main()
