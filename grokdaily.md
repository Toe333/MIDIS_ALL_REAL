# GROK DAILY TASKS — MIDIS_ALL_REAL

**Purpose:** One focused, executable improvement per day. Keeps STATE.md clean. Designed for daily AI token burn via local agent (OpenCode / Claude Code / etc.) triggered by cron.

**Workflow:**
1. Grok (or equivalent) appends today's task + full self-contained instructions here.
2. Local cron wakes OpenCode: `cat grokdaily.md | tail -N | open-code --execute-task` (or similar).
3. Agent implements, tests, commits/pushes.
4. Next day: new entry.

**Cron example (user machine, Linux):**
```bash
# Daily at 09:00 local
0 9 * * * cd /path/to/MIDIS_ALL_REAL && python -c "import subprocess; subprocess.run(['cat', 'grokdaily.md'], capture_output=True)" | /path/to/open-code --mode execute --context "Implement the latest daily task exactly as instructed. Be precise, reuse existing CODE/ patterns, test lightly, commit with message 'grok-daily: [short desc]'" 
```
(Adjust path, use uv run or venv, add notifications. For Windows: Task Scheduler + batch.)

---

## 2026-06-29 — Daily Style Probe Generator (CODE/52_daily_probe.py)

**One clever addition:** A lightweight, daily-runnable script that samples a fresh empty corner from the N×88 space (taste-weighted if available), generates 1-3 short coherent probe tracks via recombination or style engine, renders them to WAV, logs corner metadata + donor nearests, and optionally drops them into the local webplayer. This turns passive empty-space hunting into an active daily "new music invention" loop — cheap, automated, feeds future taste data or human review.

**Why clever & high-leverage:** Closes the full hunt-generate-listen-evaluate loop without manual work. Reuses 27_emptyspace, 49_sig_one, 50_generate/genre_engine, FluidSynth. Low compute (short probes). Produces audible artifacts daily for your ear + potential active learning. Fits NinjaStar-8 taste lane indirectly. Pro move: like daily model evals in ML pipelines.

**Full self-contained instructions for OpenCode / local AI agent (copy-paste the block below as your task prompt):**

```
You are implementing a new script for the MIDIS_ALL_REAL project.

Root: /path/to/MIDIS_ALL_REAL (use MAR_ROOT env or detect).
Always use the .venv-linux uv venv for Python.

GOAL: Create CODE/52_daily_probe.py — a clean, resumable CLI tool that:
- Picks ONE fresh empty corner (from existing _work/emptyspace/ or re-runs lightweight density on signatures_ext.npy; prefer taste-weighted if _work/taste_pred_v2.parquet exists — sample corners near high-pred_love or low-density + high-taste).
- For that corner, loads 3-5 nearest real MIDIs via knn_cosine.pkl + signatures_md5.txt.
- Generates 1-3 short probe tracks (30-60s) using simple stem recombination (drums/rhythm from one, melody from another, harmony/light variation) or calls into 50_generate.py --style with a derived prompt. Keep it lightweight — no full genre engine if heavy.
- Renders each to WAV using fluidsynth (GeneralUserGS.sf2 or your soundfont) + pretty_midi or mido for any tweaks.
- Logs everything to _work/daily_probes/2026-06-,md5 or parquet: corner coords, nearest md5s, generated md5s, render paths, simple quality notes.
- Optional: auto-adds WAV/MIDIs to local webplayer group "daily_probes" (if webplayer running).
- CLI: python CODE/52_daily_probe.py --corner-id latest --num-probes 2 --render --log-only

REQUIREMENTS:
- Reusable functions: import from CODE/_common.py, reuse signature loading, kNN logic, TMIDIX where possible.
- Resumable: skip if today's probes already exist for that corner.
- Clean code: follow numbering, docstrings, logging style of recent CODE/ files (50_generate, 49_sig_one, 27_emptyspace).
- Test: Run once end-to-end on a known corner; produce 1-2 WAVs that play cleanly.
- No new heavy deps if possible (pretty_midi, numpy, pandas already in env).
- Output structure: _work/daily_probes/YYYY-MM-DD_cornerXXXX/ with .mid .wav .json metadata.

STEPS TO EXECUTE:
1. Read relevant existing files: STATE.md (for current sigs/paths), CODE/27_emptyspace.py or corners_*.parquet, CODE/49_sig_one.py, CODE/50_generate.py (for patterns), CODE/_common.py.
2. Design minimal API.
3. Write the script.
4. Add basic argparse.
5. Test run (headless, produce files).
6. If webplayer hook possible, add simple --add-to-webplayer.
7. Write short README note in the script header.
8. Commit: git add CODE/52_daily_probe.py _work/daily_probes/ (gitignore generated if needed); commit message "grok-daily 2026-06-29: Daily Style Probe Generator + first run artifacts".

Do NOT touch STATE.md or ninjastar lane. Keep it self-contained in corpus lane.

After done: Update this grokdaily.md with a one-line "Done" note + any key outputs (e.g. example corner used, files created).

Be precise, minimal, working first. Think like the project author — rhythm-first, reusable, no bloat.
```

**Status:** ✅ Done 2026-06-30.

**Key outputs:**
- `CODE/52_daily_probe.py` — 570 lines, tested on blend corner #2
- `_work/daily_probes/2026-07-01_corner0002/` — 2 probe MIDIs + WAVs (18s, 28s), JSON metadata, shortlist TSV
- `git commit e28e5d2 — grok-daily 2026-06-29`

**How to run tomorrow:**
```bash
.venv-linux/bin/python CODE/52_daily_probe.py --render
```
Picks the highest-ranked undonated corner, generates 2 probes, renders WAVs.

---

## Previous days (newest on top)

*(Archive here or keep short — move completed to git history notes if grows large.)*
