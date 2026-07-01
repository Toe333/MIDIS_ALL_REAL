# INVENTION LOOP PLAN — incorporating awesome-prompts into the MIDI corpus

> **Purpose.** Turn the best off-the-shelf agent prompts (from
> [ai-boost/awesome-prompts](https://github.com/ai-boost/awesome-prompts)) into repo-native,
> corpus-tuned tooling that pushes MIDIS_ALL_REAL toward its north star: **invent a new form of
> music by generating into empty-but-coherent regions of the 88-D space.** This doc is the
> single source of execution truth for that work. Read it top-to-bottom, then work the
> **EXECUTION TODO** at the bottom in order. Append a Session Log entry to `STATE.md` when done.
>
> **Author/context note (read first):** Written 2026-06-29 from a fresh survey of `STATE.md`,
> `CODE/`, and `GMT/`. It is deliberately aligned with the **most recent strategic verdict** in the
> `STATE.md` Session Log (see "STRATEGIC ALIGNMENT" below). If `STATE.md` and this doc ever disagree,
> `STATE.md` wins — re-read it before executing.

---

## STRATEGIC ALIGNMENT (why this plan, and what it deliberately avoids)

The 2026-06-29 GMT session reached a hard, evidence-backed conclusion:

- **Fine-tuning GMT on this corpus is a dead end.** GMT was trained on LAMD, which *contains* these
  songs, so the target style is already in-distribution. Held-out token loss barely moved
  (base 0.5198 → v1 0.5174 → v2 0.5223, i.e. negligible / mildly worse). **Do not fine-tune again.**
- **Free improvisation does NOT hit a coordinate.** Free-gen (base or fine-tuned) lands ~0.04 cosine
  to a target 88-D cluster — *below* random (0.105). A style stamp does not steer placement.
- **Only SEEDING hits coordinates.** Priming GMT from a real corpus MIDI near a target corner is the
  one thing that reliably lands generations in the intended region.
- **88-D scoring of short fragments is unreliable.** GMT tokenize→decode round-trips drop a real
  song's self-cosine from 1.00 → ~0.51 (timing ×16 + velocity quantization). Score **full ~80s
  seeded songs**, and measure placement **relative to the seed's own round-tripped vector**, never
  against the raw corpus vector in absolute terms.

**Therefore the flagship deliverable is an autonomous, coordinate-driven SEEDING + TASTE-RANK loop**
that uses **base GMT** as a fixed engine. This is exactly the shape of the **Autonomous ML Research
Agent** prompt (karpathy/autoresearch) — a closed, unattended search loop with one metric, a fixed
budget per iteration, branch isolation, and telemetry-only output — but the "experiment" is a
*generation toward an empty corner* instead of a training run, and the "metric" is *invention score*
instead of `val_bpb`. The other awesome-prompts become supporting repo skills.

---

## PART A — WHAT WE INCORPORATE (external prompt → repo artifact → why)

| awesome-prompts source | Repo artifact we create | Corpus job it serves |
|---|---|---|
| 🧪 **Autonomous ML Research Agent** (`autonomous_ml_research_agent.txt`) | `.grok/skills/invention-loop/SKILL.md` + `CODE/52_invention_loop.py` | The flagship: unattended empty-space→seed→base-GMT→score→taste-rank→shortlist loop |
| 🔧 **Data Engineer** (`data_engineer.md`, Medallion + Great Expectations) | `.grok/skills/corpus-data-quality/SKILL.md` + `CODE/53_validate_corpus.py` | Bronze/Silver/Gold quality gates over `MIDIs/`→catalog→signatures |
| 🤖 **ML Systems Architect** (`ml_systems_architect.txt`) | folded into the invention-loop skill (eval/monitoring section) | Eval harness + run monitoring for the loop |
| 🗄 **SQL Assistant** (`sql_assistant.txt`) | `.grok/skills/corpus-sql/SKILL.md` | Disciplined `catalog.sqlite` querying (corrected cols, views) |
| 🕸 **Codebase Knowledge Graph Architect** (`codebase_knowledge_graph_architect.txt`) | `CODE/_pipeline_graph.py` → `PIPELINE_GRAPH.md` | Machine-checkable dependency map of `CODE/NN_*.py` |
| 📓 **AGENTS.md Author** (`agents_md_author.txt`) | targeted edits to existing `AGENTS.md` | Add an "invention loop" operational section |

We **do not** incorporate: web/mobile/blockchain/design/PPT prompts, Suno-style text-to-audio, or
anything that implies fine-tuning a big model. They don't fit a symbolic-MIDI, coordinate-seeking
corpus.

---

## PART B — THE AUTONOMOUS INVENTION LOOP (architecture)

Adapted 1:1 from the Autonomous ML Research Agent's structure. Mapping:

| Autonomous ML Research Agent | Invention Loop equivalent |
|---|---|
| Run tag + dedicated git branch | Run tag `inv-<date>` + branch `invention/<tag>` |
| Read-only `prepare.py` | Read-only: `27_emptyspace` corners, `signatures_ext.npy`, `knn_cosine.pkl`, `47` taste model, base GMT ckpt |
| Editable `train.py` (single file of truth) | Editable **generation plan** only: `{target_corner, seed_md5, prime_len, temperature, n_tokens}` — never corpus data |
| `results.tsv` (untracked, TSV) | `_work/invention_runs/<tag>/results.tsv` (untracked, md5/cand-keyed → **resumable**) |
| Baseline = train as-is | Baseline = seed-only round-tripped placement (the floor a candidate must beat) |
| One metric `val_bpb` (lower better) | One metric **`invention_score`** (higher better), defined below |
| Fixed 5-min wall-clock budget | Fixed **N candidates per corner** budget (e.g. 8), wall-clock cap per candidate |
| keep / discard / crash | keep / discard / crash — same semantics |
| Telemetry-only `[EXP]` lines | Telemetry-only `[INV]` lines |
| Human interrupt → final summary | Human interrupt → shortlist + rendered WAVs to listen to |

### The single metric — `invention_score`

One number, higher is better, with a hard coherence gate (mirrors "one metric to rule them all" +
"VRAM is a soft constraint" → here coherence is the hard constraint):

```
invention_score =  w_place * corner_gain   +   w_taste * pred_love
                   subject to:  coherence_gate(candidate) == PASS
                   else invention_score = -inf  (status = discard)
```

- **`corner_gain`** = `cos(cand_vec, target_corner) − cos(seed_roundtrip_vec, target_corner)`.
  Measured **relative to the seed's own round-tripped vector** to neutralize the documented
  tokenize→decode drift. Positive ⇒ the generation moved *toward* the empty corner vs. just echoing
  the seed. `cand_vec` is produced by `CODE/49_sig_one.vector_from_midi` (same path `score_outputs.py`
  uses).
- **`pred_love`** = the `47_propagator` taste model's predicted `pred_love` for `cand_vec` (the model
  is trained on v2 ratings; only musicality/novelty/groove carry signal, groove r≈0.36 — treat as a
  soft preference, not ground truth).
- **`coherence_gate`** = reuse `CODE/50_theory_gate.py` + cheap degeneracy checks (note count in range,
  not single-pitch drone, has rhythmic variance). Fail ⇒ discard.
- **Default weights:** `w_place = 0.6`, `w_taste = 0.4` (placement is the north star; taste is the
  tie-breaker). Expose as CLI flags. **The human ear is the final keep/discard** on the shortlist —
  the score only decides what gets rendered for listening.

### Loop (per iteration)

1. **Orient** — load target corners (`27_emptyspace` output / `_work/generation_seeds/` targets),
   read the tail of `results.tsv`, see which `(corner, seed)` pairs are already done (resumability).
2. **Hypothesize** — pick the next `(target_corner, seed_md5, params)`. Seed = nearest real corpus
   MIDI to the corner via `knn_cosine.pkl` / `49_sig_one`. Prefer corners with no/low prior coverage
   and seeds not yet tried. Vary one param at a time (prime length, temperature) like the source
   prompt varies one hyperparameter.
3. **Generate** — `GMT/gmt_generate.py continue --seed-midi <seed> --prime <P> --tokens <T>` (base
   ckpt, **no LoRA**). Redirect output to a log; do not stream into context.
4. **Embed + score** — embed the full output with `49_sig_one`, compute `corner_gain`, run the taste
   model for `pred_love`, run the coherence gate → `invention_score`.
5. **Decide** — keep (beats seed baseline AND best-for-corner) / discard / crash (same rules as
   source; fix trivial crashes once, else move on).
6. **Log** — append one md5/cand-keyed row to `results.tsv`. Render kept candidates to WAV under
   `_work/invention_runs/<tag>/listen/` with the project soundfont.
7. **Loop** — continue until the per-corner budget is exhausted for all targets, or interrupted.

### Output (telemetry only)

```
[INV] <tag> <iter> | corner:<id> | seed:<md5[:8]> | place:<corner_gain> | love:<pred_love> | score:<invention_score> | status:<keep|discard|crash> | <one-line>
```

On interrupt: total iterations, best `(corner, seed, score)` per corner, a 3–5 bullet trajectory
narrative, the shortlist of WAVs to listen to, and the next 3 ideas.

---

## PART C — `CODE/52_invention_loop.py` (the runner)

- **Number:** `52` is free and sits after `50_generate`/`51_remix` in the generation lane; it depends
  on `27`, `47`, `49`, `50`, and `GMT/`. Read `CODE/_common.py` first and match its conventions
  (paths, logging, `MAR_ROOT`).
- **Reuses, never reinvents:** `GMT/gmt_generate.py` (continue mode), `GMT/score_outputs.py` /
  `CODE/49_sig_one.py` (embedding), `CODE/47_propagator.py` model (`_work/taste_pred_v2.parquet`
  pipeline), `CODE/50_theory_gate.py` (coherence), the project soundfont render path used in
  `_work/gmt_listen/`.
- **Resumability (hard rule):** `_work/invention_runs/<tag>/results.tsv` keyed by
  `(corner_id, seed_md5, param_hash)`; re-runs skip completed rows. `MIDIs/` is read-only.
- **CLI sketch:**
  ```bash
  .venv-linux/bin/python CODE/52_invention_loop.py \
    --tag inv-20260630 --corners _work/generation_seeds/targets_taste_v2_20260622.csv \
    --budget 8 --w-place 0.6 --w-taste 0.4 --tokens 600 --prime 600 --render
  ```
- **Modes:** `--once` (single iteration, for smoke testing) and the full loop (default).
- **Output:** `results.tsv`, kept `.mid` + `.wav` in `listen/`, and a `summary.md` on exit.

---

## PART D — QUALITY-GATE LAYER (Data Engineer prompt)

Map the corpus to a Medallion model and add assertions so the loop never seeds from junk:

- **Bronze** = `MIDIs/<md5[:2]>/<md5>.mid` (read-only warehouse).
- **Silver** = `catalog/metadata.parquet` + `catalog.sqlite` (~459,805 × ~201).
- **Gold** = `SIGNATURES_DATA/signatures_ext.npy` (N×88) + kNN + taste preds.

`CODE/53_validate_corpus.py` (Great-Expectations-style, but stdlib/pandas — do not add heavy deps):
assert row counts match `STATE.md` LIVE VALUES, signature rows == `signatures_md5.txt` lines, no NaNs
in the pristine subset (`quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0`), corrected cols
present (`bpm_v2`/`felt_bpm`, `ts_final`, `key_v2`+`key_corr`), and that every seed the loop can pick
passes the pristine filter. Emits a PASS/FAIL report to `_work/validation/`. **Read-only** — never
mutates catalog or signatures.

---

## PART E — SUPPORTING SKILLS (low effort, high leverage)

- `.grok/skills/corpus-sql/SKILL.md` — CTE-first, EXPLAIN-aware querying of `catalog.sqlite`; always
  prefer corrected columns and the pre-built views (`v_clean`, `v_canonical`, …). Mirrors the format
  of the existing `corpus-step` and `drum-tbb` skills.
- `CODE/_pipeline_graph.py` → `PIPELINE_GRAPH.md` — parse `CODE/NN_*.py` imports + `STATE.md`
  provenance into a dependency graph (Mermaid + table). Confidence-tag edges (EXTRACTED vs INFERRED).
- `AGENTS.md` — add a short **"Invention loop"** section pointing at this plan + the new skill, in
  the existing style (≤200-line discipline). Do not rewrite the file.

---

## GUARDRAILS / LESSONS (do not relearn the hard way)

1. **No fine-tuning.** Base GMT only. (Evidence: 2026-06-29 held-out loss flat/worse.)
2. **No free-improv for coordinate-seeking.** Seed-and-continue only. (Free-gen lands below random.)
3. **Score full seeded songs, relative to the seed's round-tripped vector.** Never absolute cosine of
   short fragments (round-trip drops self-cos to ~0.51).
4. **Resumability is mandatory** — md5/cand-keyed `results.tsv`; re-runs skip done work.
5. **`MIDIs/` read-only; corpus lane only** — never touch NinjaStar-8 files (`ninjastar8.py`,
   `_work/ninjastar8_ratings.parquet`, `soundfonts/` for the annotator, `web/`).
6. **`.venv-linux/bin/python` for everything.** GPU commands must run **outside** the agent sandbox
   (the sandbox hides `/dev/nvidia*`).
7. **Taste model is weak** (groove r≈0.36, n=131) — use as tie-breaker, the ear decides.
8. **Telemetry-only output during the loop.** TSV + git are the truth; no essays between iterations.

---

## ACCEPTANCE CRITERIA (definition of done for the execution session)

- [ ] `CODE/52_invention_loop.py --once` produces ≥1 scored candidate end-to-end (corner→seed→GMT→
      embed→taste→gate→score→render) with no errors.
- [ ] A real loop run (`--budget` small, e.g. 3 corners × 4 cands) writes a resumable `results.tsv`
      and a `summary.md`, and re-running skips completed rows.
- [ ] At least one kept candidate has `corner_gain > 0` (moved toward the empty corner vs. seed).
- [ ] `CODE/53_validate_corpus.py` runs and reports PASS against current `STATE.md` LIVE VALUES.
- [ ] New skills load (`.grok/skills/invention-loop`, `corpus-data-quality`, `corpus-sql`).
- [ ] `PIPELINE_GRAPH.md` generated; `AGENTS.md` gains an "Invention loop" section.
- [ ] Shortlist WAVs rendered under `_work/invention_runs/<tag>/listen/` for the user to audition.
- [ ] `STATE.md` Session Log appended with a terse entry; nothing in NinjaStar-8 lane touched.

---

## EXECUTION TODO (work in order; each step lists done-when)

**Phase 0 — Orient & verify (no writes)**
1. Read `STATE.md` top section + newest Session Log entry; confirm LIVE VALUES still hold.
   *Done-when:* you can state current signature shape, row count, and the GMT verdict.
2. Confirm GPU is reachable **outside** the sandbox and base GMT ckpt loads
   (`GMT/repo/Models/Large/...0.3067_loss...pth`).
   *Done-when:* a 1-line GMT smoke gen works.
3. Read `CODE/_common.py`, `CODE/49_sig_one.py`, `CODE/47_propagator.py`, `CODE/27_emptyspace.py`,
   `GMT/gmt_generate.py`, `GMT/score_outputs.py`, `CODE/50_theory_gate.py`.
   *Done-when:* you know each one's CLI/function entry points.

**Phase 1 — Quality gate (safety net first)**
4. Write `CODE/53_validate_corpus.py` (Part D). Run it.
   *Done-when:* PASS report in `_work/validation/`, no catalog/signature mutation.

**Phase 2 — Flagship loop (smallest working slice first)**
5. Write `CODE/52_invention_loop.py` with `--once` mode only. Wire corner→seed→GMT continue→embed→
   taste→coherence gate→`invention_score`→log one row→render one WAV.
   *Done-when:* `--once` produces a scored, rendered candidate end-to-end.
6. Add the full loop (budget over corners×seeds), resumable `results.tsv`, `[INV]` telemetry,
   interrupt summary + shortlist.
   *Done-when:* small run writes resumable TSV + `summary.md`; re-run skips done rows; ≥1 kept
   candidate with `corner_gain > 0`.

**Phase 3 — Skills & docs (lock it in)**
7. Write `.grok/skills/invention-loop/SKILL.md` (adapt the Autonomous ML Research Agent prompt to the
   loop above; enforce venv/resumability/lanes/no-fine-tune guardrails).
8. Write `.grok/skills/corpus-data-quality/SKILL.md` and `.grok/skills/corpus-sql/SKILL.md`.
9. Write `CODE/_pipeline_graph.py`; generate `PIPELINE_GRAPH.md`.
10. Add the "Invention loop" section to `AGENTS.md` (style-matched, terse).
    *Done-when:* all skills load; graph + AGENTS section exist.

**Phase 4 — Close out**
11. Run a slightly larger loop; render the shortlist; the user auditions WAVs.
12. Append a Session Log entry to `STATE.md` (what ran, artifacts, next 3 ideas). Commit only
    `CODE/`, docs, skills, `AGENTS.md`, `STATE.md` per git hygiene — never data artifacts.
    *Done-when:* acceptance criteria all checked.

---

## NOTES FOR THE EXECUTOR
- Start small and prove each slice before widening (Karpathy guideline: think first, surgical changes,
  goal-driven verification). The `--once` path must work before the loop.
- If a step in this plan conflicts with a fresh read of `STATE.md`, **STATE.md wins** — note the
  conflict and adjust.
- Keep the loop's output as telemetry; put narrative only in `summary.md` and the Session Log.
