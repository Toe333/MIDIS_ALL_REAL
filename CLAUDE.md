# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A research pipeline that turns **~460,000 deduplicated MIDI files into numeric vectors**, lays them out in a high-dimensional space, and hunts for **empty-but-coherent regions** — the north star is to *invent a new form of music* by generating into those gaps rather than imitating the crowded center. Rhythm/groove is the #1 priority dimension.

The data flow: `MIDIs/` (read-only warehouse, one file per md5) → measured into `catalog/metadata.parquet` + `catalog/catalog.sqlite` (~459,805 rows, ~200 cols) → distilled into fixed-length **signatures** → searched with **kNN** → mined for empty corners → fed to taste models and generators.

## Drum Signature Invention Lane (priority)

TBB (using PT notation) is the locked core groove signature for the new style we are inventing. We use archetypes as ear-reference probes but build TBB for generation seeds. This aligns with STATE.md empty-space goal.

See `DRUM_PATTERNS/TONYBOLLAS_patterns.md` for the PT notation system, the known-styles atlas, and the candidate pool from which TBB is locked.

## Read these first

- **`STATE.md` is the single source of truth.** Read it before doing anything — it holds current status, verified ground-truth facts, an append-only Session Log, and the live values for anything that drifts (signature width, column count). **Append a Session Log entry at the end of every working session.**
- **`MANUAL.md`** is the "how to think about it" conceptual guide (the warehouse/catalog/signature/galaxy mental models).
- Where STATE.md and any older doc disagree, STATE.md wins. Don't recreate deleted docs (README.md, AGENT_TODO.md, etc. were folded into STATE.md).

## Environment

- **Always use the `.venv-linux` uv venv on Linux** (Python 3.12). The repo-root `.venv/` is a Windows env — do not use it here. Never bare `pip`; install missing deps into `.venv-linux`, don't degrade specs.
- Scripts resolve the dataset root from `MAR_ROOT` env (defaults to `/mnt/2FAST/MIDIS_ALL_REAL`).

## Pipeline architecture

- **`CODE/NN_*.py`** — a numbered, ordered pipeline. Lower numbers (`10_scan` … `17_stats`) build the base catalog; higher numbers add refinement passes (rhythm `22`, melody `24`, harmony `25`), the extended signature (`26`), empty-space hunts (`27`, `32`), GrooveDNA/DrumDNA drum vectors (`29`, `31`, `35`), taste propagation (`37`, `47`), pools (`28`, `36`, `48`), and generation (`50`). The numbering encodes dependency order.
- **`CODE/_common.py`** — shared helpers every script imports (paths, GM program→family maps, `META_FIELDS` layout, logging). Read it before writing a new pipeline step; match its conventions.
- **Resumability is a hard design rule:** every per-file output is an **md5-keyed parquet under `_work/`**, so re-running a step skips md5s already present. Steps derive from existing caches (`META_DATA/` pickles, `NOTESEQ_DATA/`) rather than re-parsing MIDI wherever possible.
- **`MIDIs/` is never mutated.** Only `10_scan.py --apply` moves files, and only into `_quarantine/` (never deletes). Paths are `MIDIs/<md5[:2]>/<md5>.mid`; the md5 is the canonical key for everything.

## Common commands

```bash
# Run the base pipeline (resumable; pilots-first):
bash CODE/run_all.sh            # full
bash CODE/run_all.sh pilot      # pilots only, stop before full passes

# Run one pipeline step (from repo root):
.venv-linux/bin/python CODE/26_signature_extend.py

# Query the catalog (pre-built views: catalog, v_canonical, v_clean,
# v_with_lyrics, v_classical, v_solo_piano, v_no_drums):
sqlite3 catalog/catalog.sqlite "SELECT key, count(*) c FROM catalog GROUP BY key ORDER BY c DESC;"

# Pitch-only similarity search (legacy; for rhythm-aware use knn_cosine.pkl):
.venv-linux/bin/python CODE/04_search.py --out-root . --query /path/to.mid --top 10
```

## Key data artifacts (regenerable; all git-ignored)

- `SIGNATURES_DATA/signatures_ext.npy` — **the signature to use, N×88** (pitch 36 / rhythm 20×2 / melody 13 / harmony 8 / groove 11×2). `signatures.npy` is the original pitch-only N×36 (kept untouched).
- `SIGNATURES_DATA/signatures_md5.txt` — row i → md5 alignment for every `.npy`.
- `SIGNATURES_DATA/knn_cosine.pkl` — exact cosine kNN over all rows of the 88-D space (rhythm/groove-aware). Drum-only variants: `signatures_drums*.npy` + `knn_drums*.pkl`.
- `catalog/metadata.parquet` / `catalog/catalog.sqlite` — same data, two formats. For tempo/meter/key prefer corrected cols (`bpm_v2`/`felt_bpm`, `ts_final`, `key_v2`+`key_corr`). Pristine subset: `quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0`.
- `CODE/49_sig_one.py` — embed a *new/external* single MIDI into the live N×88 space (re-derives the scaler that step 26 never saved). Use this to score new files against the corpus/empty corners.

## Two independent lanes (do not cross)

- **(A) Corpus lane** — the pipeline above. This is normal work.
- **(B) NinjaStar-8 annotator** — a self-running phone-based by-ear rating tool (`ninjastar8.py`, served via systemd on port 8780, Tailscale HTTPS). It only touches `ninjastar8.py`, `_work/ninjastar8_ratings.parquet`, `soundfonts/`, `web/`. **Corpus work must NOT touch those files**, and vice versa — they are deliberately conflict-free. Ratings are md5-keyed and mergeable.

## Git hygiene

`.gitignore` is configured to **track `CODE/` + docs ONLY**. All corpus data, caches, vectors, catalogs, audio, envs, and `music_rules/` (a separate nested repo) are git-ignored as regenerable/huge. Don't try to commit data artifacts.
