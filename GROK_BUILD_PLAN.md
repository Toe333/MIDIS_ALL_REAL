# GROK_BUILD_PLAN.md — Active Work Plan (the 4 pillars)

> **Read order:** `STATE.md` → `AGENTS.md` → **this file**. STATE.md is still the single
> source of truth for live values. This file is the *current standing work order* and
> supersedes the 2026-06-28 asigalov61 plan (`PLAN_ASIGALOV61_INTEGRATION.md`), which was
> off-target (see Phase 0).

## THE FOCUS (everything in this plan serves these — nothing else)

We are deepening the corpus along **four musical pillars only**, in this order of care:

1. **RHYTHM** — time-feel, syncopation, swing, metric strength. (Heavily built already — *maintain & fix*, don't re-invest.)
2. **HARMONY — vertical** — chords, chord quality/color, voicings, functional harmony (T/S/D), tension.
3. **COUNTERPOINT — horizontal** — independence of simultaneous voices, motion types, imitation. **This is the biggest gap — nothing measures it yet. It is the #1 build target.**
4. **MELODY** — contour, motif/phrase structure, melodic complexity & expectancy.

**EXPLICIT NON-GOALS (do NOT spend time on):**
- ❌ **Timbre / orchestration** — out of scope for now.
- ❌ **Dynamics / velocity expression** — out of scope for now.
- ❌ **Ingesting new external datasets** (Discover MIDI, etc.). The corpus is large enough; the north star is *empty space*, not *more data*. More MIDI crowds the center — anti-goal.
- ❌ **Swapping the MIDI parser.** Keep the existing TMIDIX. Never silently prefer a different version (see Phase 0).
- ❌ Building tools-for-tools. Every phase must end in a feature folded into the catalog/signature/taste, or audio a human can listen to.

## HARD RULES (never violate — from AGENTS.md/STATE.md)

- **Two lanes, do not cross.** Corpus lane only. Never touch the NinjaStar-8 lane (`ninjastar8.py`, `_work/ninjastar8_ratings.parquet`, `soundfonts/`, `web/`).
- `MIDIs/` is **read-only**. Never re-parse — derive everything from `NOTESEQ_DATA/` and `META_DATA/`.
- **Resumability is mandatory.** Every per-file output is an **md5-keyed parquet under `_work/`**. Re-runs must skip md5s already present. Pilots first, then full.
- **Python:** always `.venv-linux/bin/python`. Install missing deps with `uv pip install --python .venv-linux/bin/python <pkg>` — never bare pip, never degrade specs.
- **RUN THE WHOLE PLAN UNATTENDED — make destructive steps safe instead of stopping.** Do NOT pause for approval. Stay safe by construction:
  - **Never overwrite canonical artifacts in place.** Write **versioned new files** (`*_v3.*`) and a timestamped `.bak` of anything you would replace. The live `signatures_ext.npy` / `knn_cosine.pkl` / `catalog/catalog.sqlite` / `metadata.parquet` stay **untouched** — the human promotes `v3` later.
  - **Git:** commit work freely to a branch named **`grok/4-pillars`**. **Never push, never merge to main, never touch GitHub main** (that is the human's call — the only hard remote gate).
  - **Audio:** Phase-8 candidates go to the **local webplayer only**. Never touch the **NinjaStar-8 lane** or its live service.
  - With those three rules, every phase is reversible — so run end to end without stopping.
- **Report cadence:** after every phase, append ONE terse line to STATE.md Session Log, and write a longer note to `_work/grok_progress/<phase>.md`. Keep the TODO list live.

---

## PHASE 0 — Correct the last session (do this first, ~20 min)

0.1 **Revert the parser swap.** `git diff CODE/_common.py` shows `tmidix()` now prefers a tegridy
TMIDIX via `asigalov61_helpers`. This threatens the "never re-parse / reproducible" invariant for
zero benefit. Restore it: `git checkout CODE/_common.py`. The current TMIDIX stays the only parser.

0.2 **Shelve the off-target artifacts** (do not delete — move): keep `PLAN_ASIGALOV61_INTEGRATION.md`,
`CODE/55_midisim_probe.py`, `CODE/56_discover_dataset_probe.py`, `CODE/asigalov61_helpers.py` as
*reference experiments only*. They are NOT part of the pipeline. Do not run the Discover-ingest path.

0.3 **Salvage the one good idea:** `midichords` (asigalov61) is a useful *cross-check* for vertical-harmony
chord detection — note it for Phase 2, as a validator, not a replacement.

0.4 **Fix STATE.md hygiene:** the last session dropped a multi-line block into the CURRENT STATUS area and
re-added a condensed-out log line. Move its content to a single Session-Log line + `_work/grok_progress/`.

**Verify:** `git diff CODE/_common.py` is empty; `bash CODE/run_all.sh pilot` still runs clean.

---

## PHASE 1 — COUNTERPOINT feature pass  ★ primary target (hours)

**Why:** This is the one pillar with *no* measurement today (only voice-*leading* exists inside
`51_remix`). Build a first-class horizontal-harmony feature block from the note cache.

1.1 **New script `CODE/60_counterpoint.py`.** Read `NOTESEQ_DATA/` (per-bucket `(start,dur,chan,pitch,vel)`).
Never re-parse. Resumable md5-keyed parquet → `_work/counterpoint.parquet`.

1.2 **Voice separation first.** Within each file, segment concurrent notes into *voices* (by channel where
available, else a skyline/streaming voice-assignment: top line, bass line, inner voices). Document the method.

1.3 **Per-song counterpoint metrics** (md5-keyed):
- `n_independent_voices` (median simultaneous independent lines)
- motion mix between adjacent voice pairs: `motion_contrary` / `parallel` / `oblique` / `similar` ratios
- `rhythmic_independence` — how often voices move on different onsets (1 − onset-coincidence rate)
- `voice_crossing_rate`, `voice_overlap_rate`
- `nct_ratio` — non-chord-tone / passing-tone / suspension density vs the vertical chord
- `imitation_score` — detect delayed repetition of a voice's interval/contour in another voice (canon/fugue signal)
- `voice_leading_smoothness` — mean semitone motion per voice (small = smooth)
- `polyphony_density` — mean concurrent sounding voices over time

1.4 **Validate** on known cases (verify the *direction* of the metric is right):
Bach (BWV1043 is already a seed) and other counterpoint-heavy pieces should score HIGH on
`n_independent_voices` + `imitation_score` + `motion_contrary`; solo melody + block-chord pop should score LOW.
Pull 10 high / 10 low and sanity-check md5s against the catalog `key`/instrument tags.

**Verify:** parquet covers all pilot md5s, re-run skips them, hi/lo extremes make musical sense.

---

## PHASE 2 — HARMONY (vertical) deepening (hours)

**Why:** `25_harmony_refine` exists but is shallow. Deepen chord-color & function.

2.1 **New script `CODE/61_harmony_deep.py`** from `NOTESEQ_DATA/` + existing `_work/harmony_features.parquet`
+ `13_chords` outputs. Resumable → `_work/harmony_deep.parquet`.

2.2 **Metrics:**
- richer chord-quality histogram (maj/min/dom7/maj7/min7/dim/aug/sus/ext9-11-13) as ratios
- `functional_profile` — tonic/subdominant/dominant proportions (relative to detected key)
- `secondary_dominant_rate`, `borrowed_chord_rate`, `modal_interchange_score`
- `harmonic_tension_curve` summary (dissonance over time: mean, variance, peak placement)
- `voicing_density` (avg notes per chord), `chord_tone_spread` (register span)
- resolve the two STATE.md "tune-later" reads: smooth `harmonic_rhythm`; derive `key_stability` from `n_key_areas`.

2.3 **Cross-check with `midichords`** (Phase 0.3) on a small subset — agreement % only; do not replace the
existing detector unless agreement is poor AND the human approves a swap.

**Verify:** functional_profile sums ~1.0; jazz subset shows high ext/secondary-dominant; folk shows low.

---

## PHASE 3 — MELODY deepening (hours)

3.1 **New script `CODE/62_melody_deep.py`** from `NOTESEQ_DATA/` + `_work/melody_features.parquet`.
Resumable → `_work/melody_deep.parquet`.

3.2 **Metrics:**
- contour-class catalog (arch / ramp / wave / static) + interval n-gram vocabulary size
- `motif_repetition` / `self_similarity` (already partial — deepen) + `phrase_count`, `phrase_len` stats
- `call_response_score`, `sequence_rate` (melodic sequences)
- `melodic_complexity` (interval entropy) AND `melodic_predictability` (expectancy: simple Markov surprise —
  an IDyOM-lite, NOT a heavy model)
- `range_semitones`, `chromaticism`, `leap_vs_step_ratio`

**Verify:** nursery-rhyme/folk = high predictability + small range; bebop = high complexity + leaps.

---

## PHASE 4 — RHYTHM targeted fixes (short — do NOT over-invest)

Rhythm is already rich. Only close the two known gaps in STATE.md:
4.1 GrooveDNA accent-placement: add a downbeat-vs-beat-3 balance dim so reggae one-drop ≠ kick-on-1.
4.2 Replace entropy with **bar-to-bar variance** for complexity on drum lines (blast beats read wrong).
4.3 Optional: simple polyrhythm/cross-rhythm flag (3:2, 2:3 onset grids).
Write additively to `_work/` (e.g. `groove_dna_v2_patch.parquet`); do not rebuild the whole groove vector.

---

## PHASE 5 — Rebalanced 4-pillar signature + kNN (autonomous, versioned)

5.1 **Fold** Phases 1–4 outputs into an extended signature via a new `CODE/63_signature_v3.py` that EXTENDS
`26_signature_extend.py`'s logic. New layout adds a **counterpoint block** and rebalances weights so the four
pillars are **balanced** (no more groove ×8 / rhythm ×2 dominance). Suggested target: rhythm / harmony /
counterpoint / melody roughly equal; pitch retained as context. Log the proposed block widths + weights to
`_work/grok_progress/phase5_design.md`, then **proceed**.

5.2 Write **new files** `signatures_ext_v3.npy` + `knn_cosine_v3.pkl` — leave the live `signatures_ext.npy` /
`knn_cosine.pkl` untouched. Keep `signatures_md5.txt` alignment. Round-trip a few md5s to confirm cosine≈1.0.

**Verify:** known arrangement clusters still land as nearest neighbors; counterpoint-heavy pieces now cluster.

---

## PHASE 6 — Empty-space hunt on the balanced space (hours)

6.1 Re-run the empty-space hunt (`27_emptyspace.py` logic) on `signatures_ext_v3.npy`. Caption corners with
the new pillar reads (which of rhythm/harmony/counterpoint/melody is unusual). Output
`_work/emptyspace/corners_v3.parquet`.
6.2 Flag the corners that are empty because they're **coherent-but-rare** vs **incoherent** as best the
features allow (e.g., high counterpoint + valid functional harmony + low corpus density = gold).

**Verify:** list top 20 corners with human-readable captions; spot-check 3 nearest real songs each.

---

## PHASE 7 — Close the taste loop on the right axis (autonomous, additive)

7.1 **Wire the map ♥ likes into the model.** Today `_work/taste_likes.jsonl` (from `28_mapserver.py`) is never
read by `47_propagator.py`. Add it as strong positive labels. Resumable, additive.
7.2 **Rebalance the LOVE composite.** `47_propagator.py` currently uses `LOVE_W = {groove:8, musicality:1, spark:1}`
— groove-dominant, which mis-encodes the human's taste. Re-weight toward **harmony + melody + counterpoint**;
log before/after weights to `_work/grok_progress/phase7_weights.md`, then proceed.
7.3 Retrain → **new file** `_work/taste_pred_v3.parquet` (leave `taste_pred_v2.parquet` as the canonical one until
the human promotes v3); report CV r per axis. Note which pillars now carry signal.

---

## PHASE 8 — Generation experiments into the corners (hours, ends in AUDIO)

**The payoff. Every prior phase exists to make this good.**
8.1 Pick the top coherent-but-rare corners from Phase 6 that are *harmony/counterpoint/melody*-forward.
8.2 Generate **short candidates** with `CODE/50_generate.py` / `51_remix.py` aimed at those corners. Bias toward
the 4 pillars: real chord progressions, independent voices, strong melody. **Genre-default drums only — do NOT
force the TBB beat** (per standing user preference).
8.3 Render audio. Stage them with **`webplayer add` ONLY**, in REVERSE order so #1 is newest. Produce 8–16
candidates per batch. **NEVER call `webplayer open` (or xdg-open / a browser) — it spawns a new browser tab every
time and floods the screen. The human opens the player once themselves.** Adding tracks is enough; a page reload
shows them.
8.4 **Do not self-score as "done"** — the human's ears are the fitness function. `webplayer add` the batch (NO
`open`), log candidate md5s + corner provenance to `_work/grok_progress/phase8_batch_<date>.md`, then **keep going**:
generate the next corner's batch. Don't wait — accumulate batches for the human to rate whenever they return.

> **DO PHASES IN ORDER.** Do NOT jump straight to Phase 8. Phase 8 depends on Phases 1–6 (it needs
> `corners_v3.parquet`). If you reach a looping/generation phase, **rate-limit and never open UI windows** — a
> persistent loop must not spawn browser tabs, dialogs, or any GUI. Generate, add to webplayer, log, repeat.

---

## PHASE 9 — Stretch (only if hours remain)

- Counterpoint-aware generation: a constraint that *maximizes voice independence* during `51_remix` reharmonization
  (ties to the sibling `music_rules` engine — strong on harmony/melody).
- Per-pillar search endpoints: "find by counterpoint only" / "by harmony only" using the v3 block dims.
- Fold `taste_pred_v3` + corner flags into SQLite as a `v_good_empty` view (read-only view, not a rebuild).

---

## DEFINITION OF DONE (per phase) & WHAT NOT TO DO

**Done = ** md5-keyed parquet under `_work/` + resumable re-run skips + a verification spot-check that the
extreme-scoring songs make musical sense + a Session-Log line. Phases 5/7 write **versioned `*_v3` files** and
leave the live canonical artifacts untouched for the human to promote later; Phase 8 stages audio to the local
webplayer, never auto-scored as success.

**Do NOT:** re-parse MIDI; swap the parser; ingest external datasets; touch the NinjaStar-8 lane; push or merge to
GitHub main; overwrite the live `signatures_ext.npy` / `knn_cosine.pkl` / `catalog` in place (write `*_v3` + `.bak`
instead); work on timbre or dynamics; force the TBB beat in gens; mark research stubs "completed" without a real
`_work/` output.

**Loop forever rule:** when a phase finishes, advance to the next; if all are done, return to Phase 8 with a
fresh corner + new candidate batch for the human to rate. There is always more music to generate and audition.
