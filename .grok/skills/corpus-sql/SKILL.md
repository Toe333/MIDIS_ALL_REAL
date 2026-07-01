---
name: corpus-sql
description: Query catalog/catalog.sqlite for MIDIS_ALL_REAL with discipline — prefer corrected columns and the pre-built views, write CTE-first readable SQL, and EXPLAIN before scanning ~460k rows. Use when the user asks to query the catalog, count/filter songs by tempo/meter/key/groove, find seed candidates for generation, or build a feel/genre filter.
when-to-use: "query catalog.sqlite, count songs by key/meter/tempo, filter by groove/feel, find generation seeds via SQL, build a pool, sanity-check a corner's nearest songs"
allowed-tools: "run_terminal_command, read_file, grep"
---

# Corpus SQL Skill

Disciplined querying of `catalog/catalog.sqlite` (~459,805 rows × ~201 cols). Same data as
`catalog/metadata.parquet`, two formats.

## Rules

1. **Prefer corrected columns** over raw: `bpm_v2` / `felt_bpm` (not `bpm`), `ts_final`
   (not `time_signature`), `key_v2` + `key_corr` (not raw key). Raw `sources` tags are NOISY —
   verify, don't trust.
2. **Use the pre-built views** instead of re-deriving filters:
   `catalog` (clean default), `catalog_all` (incl. quarantined), `v_clean`, `v_canonical`
   (one file per song), `v_with_lyrics`, `v_classical`, `v_solo_piano`, `v_no_drums`.
3. **Pristine subset** for anything feeding search/taste/generation:
   `WHERE quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0`.
4. **CTE-first**: build readable queries with `WITH`, name subresults, filter early.
5. **EXPLAIN before big scans**: `EXPLAIN QUERY PLAN <sql>;` — the table is large; make sure
   an index or a view is used before a full table scan.
6. Read-only. Never `UPDATE`/`DELETE`/`DROP` the catalog; rebuilds go through the pipeline,
   which checkpoints to `catalog/checkpoints/` first.

## Patterns

```bash
# Distribution of a column
sqlite3 catalog/catalog.sqlite \
  "SELECT key, COUNT(*) c FROM catalog GROUP BY key ORDER BY c DESC LIMIT 10;"

# Pristine generation-seed candidates (CTE-first, corrected cols)
sqlite3 catalog/catalog.sqlite "
WITH cand AS (
  SELECT md5, felt_bpm, key_v2, ts_final, has_drums
  FROM catalog
  WHERE quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0
    AND ts_final IN ('5/4','7/4') AND felt_bpm BETWEEN 80 AND 140
)
SELECT * FROM cand ORDER BY felt_bpm LIMIT 50;"

# Always sanity-check a heavy query's plan first
sqlite3 catalog/catalog.sqlite "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM catalog WHERE ts_final='7/4';"
```

## Hand-off to other lanes

- Seeds found here feed the invention loop (use the `invention-loop` skill) or `50_generate.py`.
- For vector/rhythm-aware similarity (not SQL), use `signatures_ext.npy` + `knn_cosine.pkl`.
- Corpus lane only — never query or touch NinjaStar-8 artifacts.
