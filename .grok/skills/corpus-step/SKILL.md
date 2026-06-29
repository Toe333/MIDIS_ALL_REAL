---
name: corpus-step
description: Safely run or diagnose one step of the MIDIS_ALL_REAL numbered pipeline (CODE/NN_*.py). Use when the user asks to run a pipeline script, continue a step, check resumability, or analyze progress on catalog/signatures/empty-space/taste/generation. Always enforce venv, STATE.md, and resumability rules.
when-to-use: "run pipeline step, execute 10_scan, 26_signature, 47_propagator, 50_generate, check _work parquet progress, diagnose why a step is slow"
allowed-tools: "run_terminal_command, read_file, grep, todo_write"
---

# MIDI Corpus Pipeline Step Skill

This skill ensures every pipeline interaction on MIDIS_ALL_REAL follows the project's hard rules.

## Mandatory pre-flight (do every time)

1. Read the latest `STATE.md` (top section for live values + highest-leverage next action).
2. Confirm the exact script and purpose.
3. Identify what md5s or data it will touch.

## Execution rules

- **Python**: ALWAYS use `.venv-linux/bin/python` for any `CODE/*.py`.
- **Resumability**: Never force re-processing. Let the per-md5 parquet checks skip work. If user wants a clean re-run they must say so explicitly and understand the cost.
- **Lanes**: Confirm this is corpus-lane work (not NinjaStar-8 files).
- **Environment**: If a script needs `MAR_ROOT`, it defaults correctly here.
- **Long jobs**: For anything that will take > few minutes, suggest headless `grok -p "..."` or background.

## Common patterns

```bash
# Standard one-step
.venv-linux/bin/python CODE/26_signature_extend.py

# Pilot / small test
.venv-linux/bin/python CODE/50_generate.py --help

# Check progress of a step (example)
ls -1 _work/some_step_*.parquet | wc -l
```

## After the run

- Summarize: files processed, new artifacts, any warnings.
- If taste/generation related, cross-check against current targets in STATE.md.
- Suggest next logical step from STATE.md "HIGHEST-LEVERAGE" note.

## Safety notes

- Huge disk (MIDIs is terabytes). Avoid commands that walk the whole tree unnecessarily.
- Only `10_scan.py --apply` mutates MIDIs (into quarantine).
- Report exact command you will run and wait for confirmation on risky steps.

Use `todo_write` if the user request spans multiple steps.
