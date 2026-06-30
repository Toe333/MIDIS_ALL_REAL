#!/usr/bin/env bash
# run_dailygrok.sh — Daily Grok task runner
#
# Reads grokdaily.md (Grok's append-only task ledger; newest dated task on top),
# runs the LATEST dated task through opencode, commits CODE/ + docs only, pushes
# to main. The ledger is NEVER deleted — re-runs are prevented by a marker file
# that records the last processed task header.
#
# Cron (runs 5pm daily):
#   0 17 * * * /mnt/2FAST/MIDIS_ALL_REAL/run_dailygrok.sh >> /home/t/.cache/dailygrok_cron.log 2>&1

set -uo pipefail   # no -e: failures are handled and reported explicitly

REPO_DIR="/mnt/2FAST/MIDIS_ALL_REAL"
TASK_FILE="${REPO_DIR}/grokdaily.md"
LOG="/home/t/.cache/dailygrok_cron.log"
LOCK="/home/t/.cache/dailygrok.lock"
MARKER="/home/t/.cache/dailygrok_last_task"   # last processed task header
MODEL="opencode/deepseek-v4-flash-free"
OPENCODE="/home/t/.opencode/bin/opencode"
BRANCH="main"
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')

# Minimal env for cron (no shell profile is sourced under cron)
export PATH="/home/t/.opencode/bin:/home/t/.local/bin:/usr/local/bin:/usr/bin:/bin"
export HOME="/home/t"
export XDG_RUNTIME_DIR="/run/user/1000"
export TERM="xterm-256color"

log() { echo "$(date '+%H:%M:%S') — $*" >> "${LOG}"; }

# ── Prevent overlapping runs ──────────────────────────────────────────────
mkdir -p "$(dirname "${LOCK}")"
exec 200>"${LOCK}"
if ! flock -n 200; then
    echo "=== DailyGrok ${TIMESTAMP}: another run holds the lock, skipping ===" >> "${LOG}"
    exit 0
fi

echo "=== DailyGrok run ${TIMESTAMP} ===" >> "${LOG}"
cd "${REPO_DIR}" || { log "FATAL: cannot cd to ${REPO_DIR}"; exit 1; }

# ── 1. Pull latest ledger ─────────────────────────────────────────────────
git pull --rebase origin "${BRANCH}" 2>&1 | sed 's/^/  [git pull] /' >> "${LOG}"

# ── 2. Find the latest dated task in the ledger ───────────────────────────
if [ ! -f "${TASK_FILE}" ]; then
    log "No grokdaily.md found, nothing to do."
    echo "=== DailyGrok done ${TIMESTAMP} (noop) ===" >> "${LOG}"
    exit 0
fi

# Topmost "## YYYY-MM-DD — ..." header is the current task; use it as the id.
TASK_ID=$(grep -m1 -E '^## [0-9]{4}-[0-9]{2}-[0-9]{2}' "${TASK_FILE}" | sed 's/^##[[:space:]]*//')
if [ -z "${TASK_ID}" ]; then
    log "No dated task header found in grokdaily.md, nothing to do."
    echo "=== DailyGrok done ${TIMESTAMP} (noop) ===" >> "${LOG}"
    exit 0
fi

LAST_DONE=$(cat "${MARKER}" 2>/dev/null || true)
if [ "${TASK_ID}" = "${LAST_DONE}" ]; then
    log "Latest task already processed: ${TASK_ID} — skipping."
    echo "=== DailyGrok done ${TIMESTAMP} (already-done) ===" >> "${LOG}"
    exit 0
fi
log "New task: ${TASK_ID}"

# ── 3. Execute via opencode ───────────────────────────────────────────────
log "Running opencode ..."
# NOTE: --file is a greedy array flag. The positional message MUST come first and
# --file MUST be last, or the parser slurps the prompt string in as a filename.
PROMPT="Implement ONLY the most recent dated task in grokdaily.md (the topmost '## YYYY-MM-DD' section). Follow its embedded instructions exactly. Reuse existing CODE/ patterns. Do NOT touch STATE.md or the ninjastar lane. When finished, append a one-line 'Done' note under that task section."
"${OPENCODE}" run \
    "${PROMPT}" \
    --dangerously-skip-permissions \
    --model "${MODEL}" \
    --dir "${REPO_DIR}" \
    --title "dailygrok-${TIMESTAMP}" \
    --file "${TASK_FILE}" \
    2>&1 | sed 's/^/  [opencode] /' >> "${LOG}"
OC_EXIT="${PIPESTATUS[0]}"
log "opencode exit code: ${OC_EXIT}"

if [ "${OC_EXIT}" -ne 0 ]; then
    log "ERROR: opencode failed — not marking done, not committing. Task will retry next run."
    echo "=== DailyGrok FAILED ${TIMESTAMP} ===" >> "${LOG}"
    exit 1
fi

# Mark this task processed so it won't re-run until Grok adds a newer dated task.
echo "${TASK_ID}" > "${MARKER}"

# ── 4. Commit ONLY code + docs (never the data corpus), then rebase + push ─
# Scoped on purpose: blanket `git add -A` would sweep GMT/, 8-bit_ALBUMS/, etc.
git add -u                       # tracked-file modifications & deletions only
git add -- CODE                  # new pipeline scripts
git add -- '*.md'                # new/changed docs (incl. grokdaily.md Done note)

if git diff --cached --quiet; then
    log "No code/doc changes to commit."
else
    git commit -m "dailygrok ${TIMESTAMP}: ${TASK_ID}" 2>&1 | sed 's/^/  [git commit] /' >> "${LOG}"
    git pull --rebase origin "${BRANCH}" 2>&1 | sed 's/^/  [git rebase] /' >> "${LOG}"
    if git push origin "${BRANCH}" 2>&1 | sed 's/^/  [git push] /' >> "${LOG}"; then
        log "Pushed to origin/${BRANCH}."
    else
        log "WARNING: git push FAILED — commit is local only, fix manually."
    fi
fi

echo "=== DailyGrok done ${TIMESTAMP} ===" >> "${LOG}"
