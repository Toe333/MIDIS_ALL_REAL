# SQL Server Migration — MIDIS_ALL_REAL
**Completed:** 2026-06-19  
**Status: ✅ FULLY DONE — DB live, all tables loaded, verified.**

---

## What Was Done This Session

| Step | Status | Detail |
|---|---|---|
| SQL Server 2022 LocalDB 16.0 | ✅ | `sqllocaldb.exe` at `C:\Program Files\Microsoft SQL Server\160\Tools\Binn\` |
| `MSSQLLocalDB` instance running | ✅ | Auto-starts on demand |
| ODBC Driver 17 for SQL Server | ✅ | Installed via `install_odbc17_RUNAS_ADMIN.bat` (elevated) |
| uv venv at `B:\MIDIS_ALL_REAL\.venv` | ✅ | pyodbc 5.3, pandas 3.0, pyarrow 24, numpy 2.4, pymssql 2.3 |
| `dbo.metadata` loaded | ✅ | **459,805 rows × 182 cols** (groove_dna array col dropped) |
| `dbo.master_manifest` loaded | ✅ | **463,896 rows × 7 cols** |
| Indexes created | ✅ | md5, song_id, split, key, mode, quality_flag, bpm_valid, duration_suspect on metadata; md5 on manifest |
| Post-migration verification | ✅ | `CODE/_verify_migration.py` — row counts + spot-checks pass |

---

## Connection Details

```
Server:   (localdb)\MSSQLLocalDB
Database: MIDIS_ALL_REAL
Auth:     Windows (Trusted_Connection=yes)
Driver:   ODBC Driver 17 for SQL Server
```

**Python connection string:**
```python
CONN = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=(localdb)\MSSQLLocalDB;"
    "DATABASE=MIDIS_ALL_REAL;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)
```

**Activate venv and run:**
```powershell
b:\MIDIS_ALL_REAL\.venv\Scripts\activate
python CODE\migrate_to_sqlserver.py --dry-run   # safe preview
python CODE\migrate_to_sqlserver.py --table all  # full reload (drops+recreates tables)
python CODE\_verify_migration.py                  # sanity check
```

---

## If LocalDB Stops Responding

```powershell
# Check status
& 'C:\Program Files\Microsoft SQL Server\160\Tools\Binn\SqlLocalDB.exe' info MSSQLLocalDB

# Start if stopped
& 'C:\Program Files\Microsoft SQL Server\160\Tools\Binn\SqlLocalDB.exe' start MSSQLLocalDB
```

---

## Useful SQL Queries

```sql
-- Row counts
SELECT TABLE_NAME, SUM(row_count) AS rows
FROM sys.dm_db_partition_stats p
JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_NAME = OBJECT_NAME(p.object_id)
WHERE index_id < 2
GROUP BY TABLE_NAME;

-- Key distribution
SELECT [key], COUNT(*) c FROM dbo.metadata GROUP BY [key] ORDER BY c DESC;

-- Clean swung songs
SELECT TOP 20 md5, bpm, [key], swing_bur
FROM dbo.metadata
WHERE quality_flag = 'ok' AND bpm_valid = 1 AND is_swung = 1
ORDER BY swing_bur DESC;

-- Strong kick drums
SELECT TOP 20 md5, drum_kick_density, drum_swing, drum_snare_backbeat
FROM dbo.metadata
WHERE drum_kick_density > 4.0
ORDER BY drum_kick_density DESC;

-- Songs near an empty corner (by md5 join → look up taste_pred)
SELECT m.md5, m.bpm, m.[key], m.drum_swing, m.diatonic_ratio
FROM dbo.metadata m
WHERE m.quality_flag = 'ok' AND m.split = 'train' AND m.has_drums = 1
  AND m.drum_swing BETWEEN 0.35 AND 0.65
  AND m.diatonic_ratio > 0.75
ORDER BY m.drum_swing DESC;
```

---

## Re-migration Note

The migration reads **live parquet files** (`catalog/metadata.parquet`,
`catalog/master_manifest.parquet`). If the parquet is updated (e.g. after a new
feature pass on Linux), re-run:
```powershell
python CODE\migrate_to_sqlserver.py --table all
```
This drops and recreates both tables — takes ~2.5 min total.


---

## What Was Completed This Session

### 1. SQL Server 2022 LocalDB — Installed ✅
- Downloaded `SqlLocalDB.msi` (SQL Server 2022, v16.0.1000.6) from Microsoft CDN.
- First silent install failed (error 1603 — needed elevation).
- Re-ran as Administrator → succeeded.
- Instance `MSSQLLocalDB` created and started.
- **Named pipe / server name for LocalDB:**
  ```
  (localdb)\MSSQLLocalDB
  ```

### 2. MIDIS_ALL_REAL Database — Created ✅
- Database created on the B drive:
  ```sql
  CREATE DATABASE MIDIS_ALL_REAL
  ON PRIMARY (
      NAME = MIDIS_ALL_REAL,
      FILENAME = 'B:\MIDIS_ALL_REAL\sqldata\MIDIS_ALL_REAL.mdf'
  )
  LOG ON (
      NAME = MIDIS_ALL_REAL_log,
      FILENAME = 'B:\MIDIS_ALL_REAL\sqldata\MIDIS_ALL_REAL_log.ldf'
  );
  ```
- Verified `state_desc = ONLINE`.

### 3. VS Code MSSQL Connection Profile — Added ✅
- Added to `C:\Users\sdz\AppData\Roaming\Code\User\settings.json` under `mssql.connections`:
  ```json
  {
    "server": "(localdb)\\MSSQLLocalDB",
    "database": "MIDIS_ALL_REAL",
    "authenticationType": "Integrated",
    "profileName": "MIDIS_ALL_REAL_LocalDB",
    "savePassword": true
  }
  ```
- The MSSQL MCP tools (`mssql_connect`, `mssql_run_query`, etc.) will see this profile.

### 4. uv venv — Created ✅
- Location: `C:\Users\sdz\.venv_midis`
- Created with: `uv venv C:\Users\sdz\.venv_midis --python 3.11 --clear`
- Python executable: `C:\Users\sdz\.venv_midis\Scripts\python.exe`
- Installed packages (via `uv pip install`):
  - `pyodbc==5.3.0`
  - `pandas==3.0.3`
  - `pyarrow==24.0.0`
  - `sqlalchemy==2.0.51`
  - `numpy==2.4.6`
  - (+ greenlet, python-dateutil, six, typing-extensions, tzdata)

> **Note:** The existing `B:\MIDIS_ALL_REAL\.venv` is a Linux-native venv (created on the lab server — has `bin/` not `Scripts/`). Do NOT use it for Windows migration scripts. Use `C:\Users\sdz\.venv_midis` on Windows.

---

## What Is Blocked / Still To Do

### BLOCKER: ODBC Driver 17/18 Not Installed ⚠️
- LocalDB requires **ODBC Driver 17** or **18** for SQL Server.
- Only the old legacy `SQL Server` driver is currently installed (confirmed via `pyodbc.drivers()`).
- Chocolatey install failed (`vcredist2017` dependency issue + directory permissions).
- Manual download was queued but cancelled.

**Fix (do this first):**
1. Download ODBC Driver 18 MSI directly from Microsoft:
   - URL: https://go.microsoft.com/fwlink/?linkid=2282986
   - Or search: "Download Microsoft ODBC Driver 18 for SQL Server"
2. Run the installer as Administrator (standard GUI install, accept defaults).
3. Verify in Python:
   ```powershell
   C:\Users\sdz\.venv_midis\Scripts\python.exe -c "import pyodbc; print([d for d in pyodbc.drivers() if 'ODBC Driver' in d])"
   # Should print: ['ODBC Driver 18 for SQL Server']
   ```

---

### Step 2: Run the Migration Script

Once the ODBC driver is installed, run this script to migrate the catalog:

```powershell
C:\Users\sdz\.venv_midis\Scripts\python.exe B:\MIDIS_ALL_REAL\CODE\migrate_to_sqlserver.py
```

The migration script (`CODE/migrate_to_sqlserver.py`) needs to be written. It should:
- Read `B:\MIDIS_ALL_REAL\catalog\metadata.parquet` (459,805 rows × 148 cols) via `pandas.read_parquet`
- Read `B:\MIDIS_ALL_REAL\catalog\master_manifest.parquet` (463,896 rows) via `pandas.read_parquet`
- Connect to LocalDB via:
  ```python
  import pyodbc, sqlalchemy
  conn_str = (
      "DRIVER={ODBC Driver 18 for SQL Server};"
      "SERVER=(localdb)\\MSSQLLocalDB;"
      "DATABASE=MIDIS_ALL_REAL;"
      "Trusted_Connection=yes;"
      "TrustServerCertificate=yes;"
  )
  engine = sqlalchemy.create_engine(f"mssql+pyodbc:///?odbc_connect={conn_str}")
  ```
- Write tables using `df.to_sql("metadata", engine, if_exists="replace", index=False, chunksize=1000, method="multi")`
- Tables to create: `metadata`, `master_manifest`
- Estimated time: ~5–15 min for 460k rows (chunk inserts)

**Optional speedup:** Use `fast_executemany=True` in the SQLAlchemy engine:
```python
engine = sqlalchemy.create_engine(
    f"mssql+pyodbc:///?odbc_connect={conn_str}",
    fast_executemany=True
)
```

---

### Step 3: Connect via MSSQL MCP and Verify

Once migrated, in a Copilot chat say:
> "Connect to MIDIS_ALL_REAL_LocalDB and run SELECT count(*) FROM metadata"

The MCP tools will:
1. `mssql_connect` → server `(localdb)\MSSQLLocalDB`, database `MIDIS_ALL_REAL`
2. `mssql_list_tables` → confirm `metadata`, `master_manifest` exist
3. `mssql_run_query` → run any SQL interactively

Example queries once live:
```sql
-- How many songs?
SELECT COUNT(*) FROM metadata;

-- Key distribution
SELECT key, COUNT(*) c FROM metadata GROUP BY key ORDER BY c DESC;

-- Clean, drum-bearing, swung songs
SELECT TOP 20 md5, bpm, key, swing_bur
FROM metadata
WHERE quality_flag = 'ok'
  AND bpm_valid = 1
  AND is_swung = 1
ORDER BY swing_bur DESC;

-- GrooveDNA block — songs with strong kick density
SELECT TOP 20 md5, drum_kick_density, drum_swing, drum_snare_backbeat
FROM metadata
WHERE drum_kick_density > 4.0
ORDER BY drum_kick_density DESC;
```

---

## Quick Reference

| Thing | Value |
|---|---|
| LocalDB server name | `(localdb)\MSSQLLocalDB` |
| Database | `MIDIS_ALL_REAL` |
| venv (Windows) | `C:\Users\sdz\.venv_midis\Scripts\python.exe` |
| venv (Linux/lab) | `B:\MIDIS_ALL_REAL\.venv\bin\python` (Linux only) |
| Catalog parquet | `B:\MIDIS_ALL_REAL\catalog\metadata.parquet` |
| Manifest parquet | `B:\MIDIS_ALL_REAL\catalog\master_manifest.parquet` |
| ODBC driver needed | ODBC Driver 17 or 18 for SQL Server |
| ODBC driver download | https://go.microsoft.com/fwlink/?linkid=2282986 |
| VS Code profile name | `MIDIS_ALL_REAL_LocalDB` |

---

## Session Log Entry (append to STATE.md)

```
### 2026-06-19 — SQL Server LocalDB setup + venv (migration in progress)
- Installed SQL Server 2022 LocalDB (elevated MSI, v16.0.1000.6); instance MSSQLLocalDB running.
- Created MIDIS_ALL_REAL database on B drive (`sqldata/MIDIS_ALL_REAL.mdf`).
- Added MSSQL connection profile to VS Code settings.json (server: (localdb)\MSSQLLocalDB).
- Created uv venv at C:\Users\sdz\.venv_midis (Python 3.11) with pyodbc/pandas/pyarrow/sqlalchemy.
- BLOCKED: ODBC Driver 17/18 not installed — only legacy 'SQL Server' driver present.
  Chocolatey install failed (vcredist2017 dep issue). Manual MSI download queued.
- Next: install ODBC Driver 18, write + run CODE/migrate_to_sqlserver.py, verify via MSSQL MCP.
- See HANDOFF_SQL_MIGRATION.md for full details and migration script spec.
```
