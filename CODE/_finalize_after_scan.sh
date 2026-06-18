#!/usr/bin/env bash
# Waits for the full scan to finish, applies quarantine, folds scan features into
# the catalog, and re-runs splits+stats. Launched in background by execution.
set -euo pipefail
cd "$(dirname "$0")/.."
log(){ echo "[$(date -Iseconds)] FINALIZE $*" | tee -a _logs/finalize.log; }
# wait until scan.parquet stops growing (scan complete + final flush)
prev=-1
while true; do
  cur=$(python3 -c "import os,pandas as pd;print(len(pd.read_parquet('_work/scan.parquet')) if os.path.exists('_work/scan.parquet') else 0)" 2>/dev/null || echo 0)
  log "scan rows=$cur"
  if [ "$cur" -ge 463000 ] && [ "$cur" = "$prev" ]; then break; fi
  prev=$cur
  sleep 30
done
log "scan complete (rows=$cur). reviewing broken set."
python3 -c "import pandas as pd;d=pd.read_parquet('_work/scan.parquet');b=d[(~d.parses)|(d.is_zero_byte)|(d.neg_ticks)];print('broken:',len(b));b[['md5','parse_error']].head(20).to_string() and None"
log "applying quarantine (moves only genuinely-broken files)"
python3 CODE/10_scan.py --apply
log "re-running catalog + splits + stats to fold in integrity/velocity/drum features"
python3 CODE/15_catalog.py
python3 CODE/16_splits_pools.py
python3 CODE/17_stats.py
log "PIPELINE FULLY COMPLETE"
