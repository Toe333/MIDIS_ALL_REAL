# HANDOFF — Windows SQL / next corpus work (2026-06-19)

> **Start here next session.** SQL Server is live. The corpus on Linux is unchanged.
> Two independent lanes — they don't conflict.

---

## ✅ What Was Done This Session (SQL lane)

| Item | Done |
|---|---|
| ODBC Driver 17 for SQL Server installed | ✅ |
| uv venv at `B:\MIDIS_ALL_REAL\.venv` (pyodbc/pandas/pyarrow/numpy) | ✅ |
| `CODE/migrate_to_sqlserver.py` written + run | ✅ |
| `dbo.metadata` — 459,805 rows × 182 cols in LocalDB | ✅ |
| `dbo.master_manifest` — 463,896 rows × 7 cols in LocalDB | ✅ |
| `CODE/_verify_migration.py` passes | ✅ |

**Full connection details + re-migration commands → `HANDOFF_SQL_MIGRATION.md`**

---

## ▶ Next Tasks — Pick One Lane

### Lane A — SQL exploration (Windows, new context)

The DB is live. Start querying it immediately via the MSSQL MCP:

1. Open a new Copilot chat and say:
   > "Connect to `(localdb)\MSSQLLocalDB`, database `MIDIS_ALL_REAL`, Windows auth"

2. Try these starter queries:

```sql
-- What's in the DB?
SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES;

-- Taste-predict candidates: clean + swung + melodic + diatonic
SELECT TOP 50 md5, bpm, [key], swing_bur, diatonic_ratio, drum_swing
FROM dbo.metadata
WHERE quality_flag = 'ok'
  AND bpm_valid = 1
  AND is_swung = 1
  AND has_melody = 1
  AND diatonic_ratio > 0.80
ORDER BY swing_bur DESC;

-- Empty-corner region candidates (near b56df652's feel coordinates)
SELECT TOP 30 md5, drum_kick_density, drum_swing, drum_snare_backbeat,
              drum_pattern_entropy, diatonic_ratio
FROM dbo.metadata
WHERE has_drums = 1
  AND drum_swing BETWEEN 0.40 AND 0.65
  AND drum_snare_backbeat < 0.3          -- no backbeat = unusual
  AND diatonic_ratio > 0.75
  AND quality_flag = 'ok'
ORDER BY drum_pattern_entropy DESC;
```

3. **Proposed next script:** `CODE/40_sql_explore.py` — joins SQL results with
   `_work/taste_pred.parquet` (the taste predictions) to find high-predicted-taste
   empty-corner songs and render them to audio.

---

### Lane B — Corpus / Linux (new context, attach to tmux `work`)

State from STATE.md CURRENT STATUS:

- **Empty-space hunt done** (`_work/emptyspace/`). Re-run bolder:
  ```bash
  python3 CODE/27_emptyspace.py corners --pair-lo .15 --pair-hi .85
  ```
- **Taste propagator** (`CODE/37_taste_stub.py`) has r=0.318 with 128 ratings.
  More NinjaStar ratings → better predictions.
- **Generation targets** already in `_work/generation_seeds/top5_targets.csv`.
  Next step: generate MIDI from them via SkyTNT, check against music_rules.
- **Signature is N×85** (`signatures_ext.npy`). Nothing needs rebuilding.

**NinjaStar annotator:** live at `https://lab.tail0b3418.ts.net/` — keep rating.

---

## Quick Reference

| Thing | Value |
|---|---|
| LocalDB server | `(localdb)\MSSQLLocalDB` |
| Database | `MIDIS_ALL_REAL` |
| venv activate | `b:\MIDIS_ALL_REAL\.venv\Scripts\activate` |
| Re-migrate | `python CODE\migrate_to_sqlserver.py --table all` |
| Verify | `python CODE\_verify_migration.py` |
| sqllocaldb | `C:\Program Files\Microsoft SQL Server\160\Tools\Binn\SqlLocalDB.exe` |
| Taste preds | `_work/taste_pred.parquet` |
| Generation seeds | `_work/generation_seeds/top5_targets.csv` |
| NinjaStar | `https://lab.tail0b3418.ts.net/` |
