# AGENTS.md — MIDIS_ALL_REAL (Grok Build rules)

This is the primary project instruction file for Grok. It loads alongside (and takes precedence over) older CLAUDE.md instructions in conflicts.

**Always read `STATE.md` first** before any substantive work. It is the single source of truth for live values (signature shape, catalog row count, taste model status, TBB lock, etc.) and the append-only Session Log.

## Core invariants (never violate)

- **Two independent lanes** (do not cross):
  - (A) Corpus lane: `CODE/NN_*.py`, catalog, signatures, generation (`50_*.py`, `51_*.py`, `genre_engine.py`), pools, empty-space, taste.
  - (B) NinjaStar-8 annotator lane: `ninjastar8.py`, `_work/ninjastar8_ratings.parquet`, `soundfonts/`, `web/`, phone rating UI. Ratings are md5-keyed and safe to merge later.
- `MIDIs/` is **read-only**. Only `10_scan.py --apply` ever moves files (into `_quarantine/` only). Never delete.
- **Resumability**: every heavy step writes md5-keyed parquet under `_work/`. Re-runs must skip existing work.
- **Python**: Always run pipeline scripts with `.venv-linux/bin/python` (Python 3.12). Never bare `python` or the root `.venv/`.
- `MAR_ROOT` (if needed by scripts) defaults to this directory.

## Pipeline & data model

- Numbered pipeline order in `CODE/` encodes dependencies.
- Primary signature today: `SIGNATURES_DATA/signatures_ext.npy` (N×88).
- Use `CODE/49_sig_one.py` to embed any external/new MIDI into the live space.
- Prefer corrected columns in catalog: `bpm_v2`/`felt_bpm`, `ts_final`, `key_v2`+`key_corr`.
- TBB (PT notation "5-5-6 gallop clave") is the **locked core groove** for the invented style. See `DRUM_PATTERNS/TONYBOLLAS_patterns.md`.

## Workflow rules

- For any task with ambiguity, architecture change, new generator step, or large refactor: **enter plan mode first** (`/plan` or Shift+Tab). Do not edit until plan approved.
- Use the built-in `todo_write` tool for any work with 3+ steps. Keep it live.
- After every working session, append a terse entry to the Session Log section at the bottom of `STATE.md`.
- Prefer project skills and MCPs when they exist (see below).
- When doing web research, prefer the `firecrawl_search` MCP tool over built-in web_search.

## Environment & commands

```bash
# Preferred Python
.venv-linux/bin/python CODE/26_signature_extend.py

# Full resumable pipeline (pilots first)
bash CODE/run_all.sh pilot

# Headless Grok (automation / long jobs)
grok -p "Run 47_propagator.py then 48_active_pool.py, respecting resumability. Report only the md5s processed."

# Single MIDI embed + score against corpus
.venv-linux/bin/python CODE/49_sig_one.py --midi /path/to.mid --compare
```

## Quality gates (use these skills)

- `/check-work` after edits or new pipeline steps.
- `/review` or implement+review flow for code changes.
- Music output: mcp-score + `/musescore-*` skills.
- Data work: `/xlsx` for catalog/metadata analysis.
- Large exploration: spawn `explore` subagent (read-only).

## Git & hygiene

- Only commit `CODE/`, docs, `AGENTS.md`, `CLAUDE.md`, `STATE.md`, `MANUAL.md`, scripts, and small tools.
- Everything under `MIDIs/`, `_work/`, `catalog/`, `SIGNATURES_DATA/`, audio, envs is git-ignored (regenerable or huge).

## Do not

- Touch NinjaStar-8 files while on corpus tasks.
- Re-parse MIDI when `META_DATA/`, `NOTESEQ_DATA/`, or parquet caches exist.
- Assume old signature widths or column counts — read `STATE.md`.

Follow `STATE.md` + `MANUAL.md` + `CLAUDE.md` for conceptual and current-status details. This file just makes the operational constraints explicit for Grok.

(Generated 2026-06-27 to strengthen Grok-native project rules for this corpus.)
