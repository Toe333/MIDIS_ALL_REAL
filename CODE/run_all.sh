#!/usr/bin/env bash
# run_all.sh — execute the MIDIS_ALL_REAL v2 pipeline, pilot-first, verify-after-each.
# Safe to re-run: every step is resumable. Only Phase 1 --apply moves files
# (into _quarantine/, never deletes). Run from the dataset root:
#     bash CODE/run_all.sh            # full pipeline (pilots first, then full)
#     bash CODE/run_all.sh pilot      # just the pilots, stop before any full pass
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY=python3
MODE="${1:-full}"
log(){ echo "[$(date -Iseconds)] $*"; }

log "ROOT=$ROOT  mode=$MODE"
mkdir -p _work _logs _stats _quarantine pools catalog/checkpoints SIGNATURES_DATA CHORDS_DATA

# --- P0 smoke test ---
log "P0 smoke test"
$PY CODE/_common.py >/dev/null
log "P0 OK"

# --- P1 scan: PILOT 10k, verify, then FULL ---
log "P1 pilot scan (10k)"
$PY CODE/10_scan.py --limit 10000
$PY - <<'PY'
import pandas as pd
d=pd.read_parquet("_work/scan.parquet")
broken=int((~d.parses).sum()); neg=int(d.neg_ticks.sum()); absurd=int(d.note_density_absurd.sum())
print(f"PILOT: rows={len(d)} broken={broken} neg_ticks={neg} absurd={absurd}")
assert broken < len(d)*0.05, "too many broken in pilot — stop and inspect"
print("PILOT OK")
PY
if [ "$MODE" = "pilot" ]; then log "pilot mode: stopping before full passes"; exit 0; fi

log "P1 FULL scan (this is the ~26-min pass)"
rm -f _work/scan.parquet           # full run from scratch after pilot
$PY CODE/10_scan.py                 # dry-run report; review _work/quarantine_candidates.json
log "P1 review broken set, then apply quarantine"
$PY CODE/10_scan.py --apply

# --- P2 pickle-derived features (fast) ---
log "P2 features"; $PY CODE/11_features.py
# optional music21 key validation on a 2k sample (skips cleanly if music21 missing)
$PY CODE/_validate_key.py || log "key validation skipped"

# --- P3 / P4 / P5 (all read pickles; run sequentially here for simplicity) ---
log "P3 signatures + clusters"; $PY CODE/12_signatures.py
log "P4 chords";               $PY CODE/13_chords.py
log "P5 provenance";           $PY CODE/14_provenance.py

# --- P6 catalog, P7 splits/pools, P8 stats ---
log "P6 catalog";       $PY CODE/15_catalog.py
log "P7 splits/pools";  $PY CODE/16_splits_pools.py
log "P8 stats";         $PY CODE/17_stats.py

log "DONE. See _logs/progress.log, catalog/catalog.sqlite, _stats/."
