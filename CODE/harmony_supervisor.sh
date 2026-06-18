#!/usr/bin/env bash
# Keeps 25_harmony_refine running until all 256 buckets are done, then merges.
# Resilient to crash/OOM/terminal-close: relaunches (script skips finished buckets).
# Launch detached:  setsid nohup bash CODE/harmony_supervisor.sh >> _logs/harmony_supervisor.log 2>&1 &
set -u
cd /mnt/2FAST/MIDIS_ALL_REAL || exit 1
PARTS=_work/harmony_parts
LOG=_logs/refine_all.log
say() { echo "[$(date -Is)] supervisor: $*"; }

while true; do
  n=$(ls "$PARTS"/*.parquet 2>/dev/null | wc -l)
  if [ "$n" -ge 256 ]; then
    say "all $n/256 buckets present -> final merge"
    python3 CODE/25_harmony_refine.py --merge-only >> "$LOG" 2>&1
    say "done. harmony_features.parquet written."
    break
  fi
  if ! pgrep -f "25_harmony_refine.py" >/dev/null; then
    say "harmony not running ($n/256 parts) -> relaunching --workers 10"
    nohup python3 CODE/25_harmony_refine.py --workers 10 >> "$LOG" 2>&1 &
  else
    say "harmony alive ($n/256 parts), watching"
  fi
  sleep 120
done
