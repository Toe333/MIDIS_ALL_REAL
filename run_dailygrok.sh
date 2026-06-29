#!/usr/bin/env bash
# run_dailygrok.sh — Daily Grok task runner
#
# 1. git pull from origin
# 2. Look for dailygrok.md in the repo root
# 3. If found, feed content to opencode CLI for execution
# 4. Commit & push any changes
# 5. Archive the processed dailygrok.md
#
# Install as a cron job (run `crontab -e` and add):
#   0 9 * * * /mnt/2FAST/MIDIS_ALL_REAL/run_dailygrok.sh >> /home/t/.cache/dailygrok_cron.log 2>&1

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

echo "=== DailyGrok run ${TIMESTAMP} ===" >> "${LOG}"

# 1. Git pull
cd "${REPO_DIR}"
git pull --rebase origin main 2>>"${LOG}" || git pull --rebase origin master 2>>"${LOG}" || true

# 2. Check for dailygrok.md
if [ ! -f "${DAILY_FILE}" ]; then
    echo "$(date '+%H:%M:%S') — No dailygrok.md found, nothing to do." >> "${LOG}"
    exit 0
fi

INSTRUCTIONS=$(cat "${DAILY_FILE}")
if [ -z "${INSTRUCTIONS}" ]; then
    echo "$(date '+%H:%M:%S') — dailygrok.md is empty, skipping." >> "${LOG}"
    mv "${DAILY_FILE}" "${ARCHIVE_DIR}/${TIMESTAMP}_empty.md"
    exit 0
fi

echo "$(date '+%H:%M:%S') — Found dailygrok.md ($(wc -c < "${DAILY_FILE}") bytes)" >> "${LOG}"
echo "$(date '+%H:%M:%S') — Content preview: $(head -3 "${DAILY_FILE}" | tr '\n' ' ')" >> "${LOG}"

# 3. Execute the instructions via opencode
# --dangerously-skip-permissions: headless, no UI for approvals
# --model: use same free model the user is talking to
# --cwd: work in this repo
echo "$(date '+%H:%M:%S') — Running opencode..." >> "${LOG}"

cd "${REPO_DIR}"
if "${OPENCODE}" run \
    --dangerously-skip-permissions \
    --model "${MODEL}" \
    --cwd "${REPO_DIR}" \
    --title "dailygrok-${TIMESTAMP}" \
    "${INSTRUCTIONS}" 2>>"${LOG}"; then
    echo "$(date '+%H:%M:%S') — opencode execution succeeded" >> "${LOG}"
else
    EXIT_CODE=$?
    echo "$(date '+%H:%M:%S') — opencode execution finished with exit code ${EXIT_CODE}" >> "${LOG}"
fi

# 4. Commit and push any changes
cd "${REPO_DIR}"
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add -A
    git commit -m "dailygrok auto-commit ${TIMESTAMP}" 2>>"${LOG}" || true
    git push origin main 2>>"${LOG}" || git push origin master 2>>"${LOG}" || \
        echo "$(date '+%H:%M:%S') — WARNING: git push failed" >> "${LOG}"
    echo "$(date '+%H:%M:%S') — Changes committed and pushed" >> "${LOG}"
else
    echo "$(date '+%H:%M:%S') — No changes to commit" >> "${LOG}"
fi

# 5. Archive the processed dailygrok.md
mkdir -p "${ARCHIVE_DIR}"
mv "${DAILY_FILE}" "${ARCHIVE_DIR}/${TIMESTAMP}.md"
echo "$(date '+%H:%M:%S') — dailygrok.md archived to ${ARCHIVE_DIR}/${TIMESTAMP}.md" >> "${LOG}"

echo "=== DailyGrok done ${TIMESTAMP} ===" >> "${LOG}"
