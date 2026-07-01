---
name: corpus-data-quality
description: Validate the MIDIS_ALL_REAL corpus as a Medallion (Bronze/Silver/Gold) data product with read-only assertions before trusting it for search, taste, or generation. Use when the user asks to validate the corpus, check data integrity, verify row/column/signature counts against STATE.md, confirm the pristine subset is clean, or make sure the invention loop will only seed from sound data.
when-to-use: "validate corpus, data quality check, verify signatures match catalog, check pristine subset, confirm counts vs STATE.md, run 53_validate_corpus, debug a count/NaN mismatch"
allowed-tools: "run_terminal_command, read_file, grep, todo_write"
---

# Corpus Data-Quality Skill

A Medallion-model quality gate over the corpus, implemented as `CODE/53_validate_corpus.py`
(stdlib + pandas/numpy only — no heavy deps). **Read-only**: it never mutates the catalog,
signatures, or `MIDIs/`.

## Medallion tiers

- **Bronze** = `MIDIs/<md5[:2]>/<md5>.mid` — read-only warehouse (one file per md5).
- **Silver** = `catalog/metadata.parquet` (+ `catalog.sqlite`) — ~459,805 × ~201.
- **Gold**   = `SIGNATURES_DATA/signatures_ext.npy` (N×88) + `signatures_md5.txt` + `_work/taste_pred_v2.parquet`.

## What it asserts (PASS / WARN / FAIL)

1. Silver row count vs STATE.md LIVE VALUE (catalog == 459,805).
2. Gold internal consistency: `signatures_ext` rows == `signatures_md5.txt` lines (HARD).
3. Gold signature width == 88 (HARD).
4. Gold↔Silver alignment; the known +N seed-embed drift (2026-06-25) is a documented WARN.
5. Corrected detection columns present (`bpm_v2`/`felt_bpm`, `ts_final`, `key_v2`, `key_corr`).
6. Pristine subset (`quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0`) non-empty
   and NaN-free in the columns the pipeline relies on.
7. Seed-pickability: every seed the invention loop could pick (from the taste targets CSV)
   exists on disk, is in the signature space, and is mostly pristine.
8. Taste predictions exist and cover the signature space.

## How to run

```bash
.venv-linux/bin/python CODE/53_validate_corpus.py
# or point at a specific targets CSV the loop will use:
.venv-linux/bin/python CODE/53_validate_corpus.py --targets _work/generation_seeds/targets_taste_v2_20260622.csv
```

Reports to stdout and `_work/validation/report_<UTC>.txt` + `latest.json`. Exit code 0 = no
FAILs (WARNs allowed), 1 = at least one FAIL.

## Interpreting results

- **FAIL** blocks downstream work — fix before running the invention loop or trusting search.
- **WARN** is expected drift to be aware of (e.g. the +9 ext-vs-catalog rows, a few corrected
  columns that are NaN in the pristine subset and get median-imputed by `49_sig_one`).
- When STATE.md LIVE VALUES change (new ingest, rebuilt signatures), update the constants at
  the top of `53_validate_corpus.py` to match, then re-run.

## Guardrails

- `.venv-linux/bin/python` only. Read-only — never let this skill mutate data.
- This is corpus-lane work; do not touch NinjaStar-8 files.
