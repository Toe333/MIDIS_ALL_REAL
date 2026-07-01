---
name: invention-loop
description: Run or extend the autonomous coordinate-driven INVENTION loop (CODE/52_invention_loop.py) that seeds BASE Giant Music Transformer from real corpus MIDIs near empty 88-D corners, scores placement + taste under a coherence gate, and shortlists candidates to audition. Use when the user asks to generate into empty space, hunt a new style, run the invention loop, score generations toward a corner, or expand a prior loop run.
when-to-use: "run invention loop, generate into an empty corner, seed GMT toward a target coordinate, expand inv-* run, audition the shortlist, push toward inventing a new style"
allowed-tools: "run_terminal_command, read_file, grep, todo_write"
---

# Invention Loop Skill

Drives the flagship loop from `INVENTION_LOOP_PLAN.md`: empty-corner → nearest real
corpus seed → **base GMT continuation** → embed in the live N×88 space → taste-rank →
coherence gate → `invention_score` → resumable log → shortlist WAVs. The north star is
to *invent a new form of music by generating into empty-but-coherent regions* — not to
imitate the crowded center.

## Mandatory pre-flight (every time)

1. Read `STATE.md` (LIVE VALUES + newest Session Log). Confirm signature is N×88 and the
   GMT verdict still holds.
2. Confirm GPU is reachable: `.venv-linux/bin/python -c "import torch;print(torch.cuda.is_available())"`
   must print `True`. If `False`, you are in a sandbox that hides `/dev/nvidia*` — run the
   loop **outside** the sandbox; do not proceed.
3. Run the quality gate first: `.venv-linux/bin/python CODE/53_validate_corpus.py`
   (must be FAIL-free; WARNs are documented drift).

## Hard guardrails (do not relearn the hard way)

- **Base GMT only — never fine-tune.** (2026-06-29: held-out loss flat/worse; fine-tuning is a dead end here.)
- **Seed-and-continue only — never free-improv for coordinate-seeking.** (Free-gen lands below random.)
- **Score the FULL seeded song relative to the seed's own GMT round-trip** (`corner_gain`),
  never an absolute cosine of a short fragment (round-trip drops self-cos to ~0.51).
- **Resumability is mandatory.** `results.tsv` is keyed by `(corner_id, seed_md5, param_hash)`;
  re-runs skip done rows. Never delete it to "start fresh" unless the user insists.
- **Corpus lane only.** Never touch NinjaStar-8 write paths (`ninjastar8.py`,
  `_work/ninjastar8_ratings.parquet`, the annotator's `soundfonts/`, `web/`). Reading the
  ratings parquet to train the taste model and reading a soundfont to render is fine.
- **`.venv-linux/bin/python` for everything.**
- **Telemetry-only during the loop** — the `[INV]` lines + `results.tsv` + `summary.md` are
  the truth; no essays between iterations.

## The one metric

```
invention_score = w_place * corner_gain + w_taste * pred_love_norm
                  subject to coherence_gate == PASS   (else -inf, discard)
```
- `corner_gain = cos(cand, corner) − cos(seed_roundtrip, corner)` (positive ⇒ moved toward the empty corner).
- `pred_love_norm` = corpus-percentile-normalized 47_propagator love (weak; tie-breaker only).
- Defaults `w_place=0.6`, `w_taste=0.4`. **The ear is the final keep/discard** on the shortlist.

## Common commands

```bash
# Smoke test (single iteration end-to-end)
.venv-linux/bin/python CODE/52_invention_loop.py --once --render --tag inv-smoke

# Small real run (resumable; writes results.tsv + summary.md + listen/*.wav)
.venv-linux/bin/python CODE/52_invention_loop.py --tag inv-$(date +%Y%m%d) \
  --n-corners 3 --budget 4 --seeds-per-corner 3 --tokens 512 --prime 512 --render

# Sweep temperature (vary ONE param at a time, like the source prompt)
.venv-linux/bin/python CODE/52_invention_loop.py --tag inv-temps --sweep --temps 0.8,0.95 --render
```

## After the run

- Read `_work/invention_runs/<tag>/summary.md`: best `invention_score` per corner + the
  shortlist of WAVs.
- Report the kept candidates (corner, seed, place, love) and point the user at the WAVs to
  audition. The score only decides what gets rendered; the human ear decides what survives.
- Suggest the next move: widen budget on the highest-gain corner, try the #2/#3 seeds for
  corners that only produced discards, or vary prime length.
- Append a terse Session Log entry to `STATE.md`. Never commit data artifacts.
