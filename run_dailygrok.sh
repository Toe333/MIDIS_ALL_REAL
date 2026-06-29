#!/usr/bin/env bash
# run_dailygrok.sh — Daily Grok task runner
#
# 1. git pull from origin
# 2. Look for dailygrok.md in the repo root
# 3. If found, feed content to opencode CLI for execution
# 4. Commit & push any changes
# 5. Archive the processed dailygrok.md
#
# Install as a cron job (add this to `crontab -e`):
#   0 9 * * * /mnt/2FAST/MIDIS_ALL_REAL/run_dailygrok.sh

set -euo pipefail

REPO_DIR="/mnt/2FAST/MIDIS_ALL_REAL"
ARCHIVE_DIR="${REPO_DIR}/_dailygrok_archive"
DAILY_FILE="${REPO_DIR}/dailygrok.md"
LOG="/home/t/.cache/dailygrok_cron.log"
MODEL="opencode/deepseek-v4-flash-free"
OPENCODE="/home/t/.opencode/bin/opencode"
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')

# Ensure minimal env for cron
export PATH="/home/t/.opencode/bin:/home/t/.local/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/t"
export XDG_RUNTIME_DIR="/run/user/1000"
export TERM="xterm-256color"

echo "=== DailyGrok run ${TIMESTAMP} ===" >> "${LOG}"

# ── 1. Git pull ──────────────────────────────────────────────────────────
cd "${REPO_DIR}"
git pull --rebase origin main 2>&1 | sed 's/^/  [git pull] /' >> "${LOG}" || \
    git pull --rebase origin master 2>&1 | sed 's/^/  [git pull] /' >> "${LOG}" || true

# ── 2. Check for dailygrok.md ────────────────────────────────────────────
if [ ! -f "${DAILY_FILE}" ]; then
    echo "$(date '+%H:%M:%S') — No dailygrok.md found, nothing to do." >> "${LOG}"
    echo "=== DailyGrok done ${TIMESTAMP} (noop) ===" >> "${LOG}"
    exit 0
fi

FILESIZE=$(wc -c < "${DAILY_FILE}")
echo "$(date '+%H:%M:%S') — Found dailygrok.md (${FILESIZE} bytes)" >> "${LOG}"
echo "$(date '+%H:%M:%S') — First line: $(head -1 "${DAILY_FILE}")" >> "${LOG}"

# ── 3. Execute via opencode (pass dailygrok.md as an attached file) ─────
echo "$(date '+%H:%M:%S') — Running opencode run --file dailygrok.md ..." >> "${LOG}"

cd "${REPO_DIR}"
"${OPENCODE}" run \
    --dangerously-skip-permissions \
    --model "${MODEL}" \
    --cwd "${REPO_DIR}" \
    --title "dailygrok-${TIMESTAMP}" \
    --file "${DAILY_FILE}" \
    "DailyGrok: execute these instructions from dailygrok.md" 2>&1 | sed 's/^/  [opencode] /' >> "${LOG}"

OC_EXIT="${PIPESTATUS[0]}"
echo "$(date '+%H:%M:%S') — opencode exit code: ${OC_EXIT}" >> "${LOG}"

# ── 4. Pull latest (remote may have moved), then commit & push ─────────
cd "${REPO_DIR}"
git pull --rebase origin main 2>&1 | sed 's/^/  [git rebase] /' >> "${LOG}" || \
    git pull --rebase origin master 2>&1 | sed 's/^/  [git rebase] /' >> "${LOG}" || true

if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add -A
    git commit -m "dailygrok auto-commit ${TIMESTAMP}" 2>&1 | sed 's/^/  [git commit] /' >> "${LOG}" || true
    git push origin main 2>&1 | sed 's/^/  [git push] /' >> "${LOG}" || git push origin master 2>&1 | sed 's/^/  [git push] /' >> "${LOG}" || \
        echo "$(date '+%H:%M:%S') — WARNING: git push failed (remote may have diverged)" >> "${LOG}"
    echo "$(date '+%H:%M:%S') — Changes committed and push attempted" >> "${LOG}"
else
    echo "$(date '+%H:%M:%S') — No changes to commit" >> "${LOG}"
fi

# ── 5. Archive dailygrok.md ─────────────────────────────────────────────
mkdir -p "${ARCHIVE_DIR}"
mv "${DAILY_FILE}" "${ARCHIVE_DIR}/${TIMESTAMP}.md"
echo "$(date '+%H:%M:%S') — Archived to ${ARCHIVE_DIR}/${TIMESTAMP}.md" >> "${LOG}"

echo "=== DailyGrok done ${TIMESTAMP} ===" >> "${LOG}"
