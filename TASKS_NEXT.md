# NEXT TASKS — MIDI corpus (written 2026-06-20)

Four self-contained task briefs for the post-N×88 phase. Each `PROMPT` block below is
written to be **pasted whole into a fresh Claude Code session** rooted at
`/mnt/2FAST/MIDIS_ALL_REAL` — it re-derives its own context. Do them in any order;
**Task 1 is the recommended next** (it reconnects taste to today's fresh empty-space hunt).

## Shared context (true as of 2026-06-20, all tasks rely on this)
- **Read `STATE.md` first**, and **append a Session Log entry** to it when done.
- **ALWAYS use the `uv` venv `/.venv-linux`** (`.venv-linux/bin/python …`). The repo `.venv`
  is a Windows venv (unusable on Linux). A PreToolUse hook blocks bare `pip` — use
  `uv pip install --python .venv-linux/bin/python <pkg>`.
- **Signature space (current):** `SIGNATURES_DATA/signatures_ext.npy` = **N×88 float32**
  (459,805 rows), row order in `SIGNATURES_DATA/signatures_md5.txt`. Block layout in
  `knn_cosine.pkl["block_dims"]` = `pitch 36 / rhythm 20 / melody 13 / harmony 8 / groove 11`
  (rhythm & groove ×2-weighted; rows ~unit-norm √7). Built by `CODE/26_signature_extend.py`.
- **Catalog:** `catalog/metadata.parquet` (201 cols) + `catalog/catalog.sqlite`. Corrected
  detection cols: `bpm_v2`, `felt_bpm`, `ts_final`, `key_v2`, `key_corr`.
- **Empty-space hunt (fresh, N×88):** `CODE/27_emptyspace.py`; outputs in `_work/emptyspace/`:
  `corners_blends.parquet` (60), `corners_isolated.parquet` (60), `clusters.parquet`,
  `clusters_centroids.npy`, `density.parquet`, `cluster_summary.parquet`. Blend cols incl.
  `anchor_a/b`, `midpoint_caption`, `nearest_songs` (`;`-joined md5s), `nearest_song_sims`.
- **Audio:** MIDIs at `MIDIs/<first2hex>/<md5>.mid`; render with
  `fluidsynth -ni -F out.wav soundfonts/GeneralUserGS.sf2 in.mid`. Audition via `webplayer`
  (`webplayer add <wav> --group G --label L --desc D` → `webplayer open`).
  **RULE: when loading a ranked set, add in REVERSE rank so #1 is the newest-added file.**

---

## TASK 1 — Re-rank empty corners by predicted taste (on N×88)  ★ recommended next

```PROMPT
Root: /mnt/2FAST/MIDIS_ALL_REAL. Read STATE.md and TASKS_NEXT.md "Shared context" first.
Use the .venv-linux uv venv for all Python.

GOAL: Produce a fresh, taste-ranked shortlist of "beautiful empty corners" to target for
generation. The old taste predictions (_work/taste_pred.parquet) and locked targets
(_work/generation_seeds/top5_targets.csv) were computed on the OLD 85-D space and are stale —
today's hunt moved the corners ~100%. Rebuild on N×88.

STEPS:
1. Read the existing CODE/37_taste_stub.py (old Ridge propagator) to reuse its shape.
2. Train a taste propagator on the CURRENT signature:
   - X = SIGNATURES_DATA/signatures_ext.npy aligned by signatures_md5.txt.
   - y = _work/ninjastar8_ratings.parquet (283 rows; axes: musicality, novelty, groove,
     valence, energy, memorability, spark; md5-keyed — average duplicate md5s).
   - Define a "love" target (recommend: mean of musicality+memorability+spark, 0–8) AND keep
     per-axis models for groove especially. Up-weight the groove block (dims 77–87) like the
     stub did (×5) if it helps CV.
   - Use Ridge as baseline; try LightGBM only if it installs cleanly in the venv. Report
     5-fold CV pearson r + MAE per target. (Old stub: groove r≈0.32 — beat it or match.)
   - Predict over all 459,805 → _work/taste_pred_v2.parquet (md5 + predicted love + axes).
3. Score & rank the 60 corners_blends + 60 corners_isolated:
   - For each corner, map its `nearest_songs` md5s → predicted love (mean of top-3). Rank by
     predicted_love, but keep emptiness/coherence as tie-breakers (blends already have
     nearest_sim≈0.82 = coherent). Optionally also require proxy-beauty (catalog
     diatonic_ratio≥0.6, has_melody=1) to bias toward "beautiful".
   - Write _work/generation_seeds/targets_v2_20260620.csv: rank, corner_type, caption,
     nearest_md5, predicted_love, nearest_sim. Replace/supersede top5_targets.csv (keep old
     as .bak).
4. Render the top-8 corners' nearest real songs to WAV (fluidsynth + GeneralUserGS.sf2) and
   load into webplayer group "targets_v2" — REVERSE order so rank #1 is newest. Print the URL.

VALIDATE: print CV metrics; confirm targets_v2 top rows are diatonic/melodic (spot-check
catalog). DO NOT touch signatures_ext.npy / knn_cosine.pkl. Append a STATE.md session entry.
```

---

## TASK 2 — Build the generator (target an empty corner)  ★ the frontier / biggest lift

> **STATUS 2026-06-24 — DONE (route C + theory-gated 8-bit enhancement).**
> - `CODE/49_sig_one.py` (signature-of-one-MIDI) verified: rebuilds a known corpus
>   row at cosine **1.0000** from both catalog and raw `.mid`.
> - `CODE/50_generate.py` route-C recombination is live (stem split → recombine →
>   cosine-to-corner → proxy-beauty gate → webplayer).
> - **NEW: `CODE/50_theory_gate.py`** — theory-gated, 8-bit-aware enhancement
>   (`enhance_candidate`): music21 key detection, `music_rules.evaluate_passage`
>   voice-leading grade, **chiptune ≤4-voice + arp** arrange (square 80 / saw 81 /
>   bass 38 / noise ch9), re-scored cosine-to-corner, rejection-sampled variants.
> - **NEW: `50_generate.py --enhance {chiptune,arp,clean}`** runs `enhance_candidate`
>   on every kept candidate, keeps only those passing rules + quality + cosine, writes
>   `_work/generated/<corner>/enhanced_*.mid` and auditions the survivors.
>
> **Run full gated gen (one-liner):**
> ```bash
> .venv-linux/bin/python CODE/50_generate.py --rank 1 --keep 3 --enhance chiptune --gate-min-cos 0.7 --group gated_test
> ```
> Single-file gate: `.venv-linux/bin/python CODE/50_theory_gate.py --input <mid> --mode chiptune --target_corner "<caption>"`

```PROMPT
Root: /mnt/2FAST/MIDIS_ALL_REAL. Read STATE.md and TASKS_NEXT.md "Shared context" first.
Use the .venv-linux uv venv. This is the north-star step: GENERATE music that lands in a
chosen empty corner, then audition it.

PREREQUISITE SUB-TASK (build first — nothing else can score a new file without it):
  "signature-of-one-MIDI". The feature pipeline (CODE/21_sequences.py → 22_rhythm_refine,
  24_melody_refine, 25_harmony_refine, 29_groove_dna) is corpus-batch. Write
  CODE/49_sig_one.py: given a single .mid, run the SAME feature extraction + the SAME scaling
  used in CODE/26_signature_extend.py (reuse its functions / scaler stats) to emit one 88-D
  vector comparable to signatures_ext.npy rows. Verify: re-extract a known corpus md5 and
  confirm cosine≈1.0 vs its stored row.

GENERATOR (start with the simplest that can work — retrieve-and-recombine, route C):
1. Pick a target corner from _work/generation_seeds/targets_v2_*.csv (Task 1) — or a corner
   midpoint vector recomputed from anchors_a/b centroids in clusters_centroids.npy.
2. Gather its k nearest REAL songs (corner.nearest_songs). Generate candidate MIDIs by
   recombination + light variation (e.g. take rhythm/drums from song A, melody from B,
   harmony from C; transpose; tempo-nudge). Use pretty_midi/mido (uv pip install if missing).
3. Score each candidate with CODE/49_sig_one.py → cosine to the target. Keep the closest few
   that ALSO pass proxy-beauty (diatonic, consonant). Save to _work/generated/<corner>/.
4. Render to WAV + load into webplayer group "generated_<corner>" (REVERSE order). Print URL.

STRETCH (only if route C is weak): integrate the sibling theory engine at music_rules/
(SkyTNT midi-model + rejection sampling) to steer generation toward the target signature.
See memory music-rules-project-link. Keep this behind a flag; don't block the route-C baseline.

VALIDATE: report cosine-to-target of best candidates vs the nearest real song's cosine (we
want candidates AT LEAST as close to the corner, ideally inside it). Audition is the real
test — flag the best 3 for the user to listen. Append a STATE.md session entry.
```

---

## TASK 3 — Refresh the UMAP maps on N×88

```PROMPT
Root: /mnt/2FAST/MIDIS_ALL_REAL. Read STATE.md and TASKS_NEXT.md "Shared context" first.
Use the .venv-linux uv venv (needs umap-learn: uv pip install --python .venv-linux/bin/python umap-learn).

GOAL: The 2D/3D map embeddings (_work/emptyspace/umap2.{npy,parquet}, umap3.{npy,parquet})
are N×74-era and no longer match the N×88 space or today's corners. Re-embed them.

STEPS:
1. Embed SIGNATURES_DATA/signatures_ext.npy (N×88, unit-normalize rows first) with
   umap.UMAP(n_neighbors=30, min_dist=0.1, metric="cosine"): 2D -> umap2.{npy,parquet},
   and 3D (n_components=3) -> umap3.{npy,parquet}. (Reuse _work/emptyspace/_umap_embed.py if
   present; NOTE the known past bug — explicitly set n_components=3 for the galaxy or it
   silently stays 2D.) ~5 min each; drop random_state for multicore.
2. Back up the old umap*.{npy,parquet} first (timestamped). Keep the same parquet schema the
   mapserver expects (md5 + x/y[/z] + whatever color cols 28_mapserver reads).
3. Restart the mapserver: it runs as a manual process (and as user service
   midimap8767 if that exists). Re-run e.g.
   .venv-linux/bin/python CODE/28_mapserver.py --port 8766 --color syncopation
   and the drum map on 8767 (--umap umap2_drums.parquet --corners drum). Verify pages load
   (curl / -> 200, /points.json -> 200) and the empty-corner ✕ markers land in the gaps.

VALIDATE: headless check (playwright in venv) or at least curl 200s + non-empty points.json.
Append a STATE.md session entry. Don't touch the signature/kNN artifacts.
```

---

## TASK 4 — Grow + exploit taste data (active learning)

```PROMPT
Root: /mnt/2FAST/MIDIS_ALL_REAL. Read STATE.md and TASKS_NEXT.md "Shared context" first.
Use the .venv-linux uv venv.

CONTEXT: 283 NinjaStar-8 ratings exist (_work/ninjastar8_ratings.parquet); the propagator is
weak (groove r≈0.32). NinjaStar-8 is live (systemd ninjastar8.service, https://lab.tail0b3418.ts.net/).
More + smarter-chosen ratings = a trustworthy taste model for Tasks 1/2.

STEPS:
1. ACTIVE-LEARNING SAMPLER (code): train the Task-1 propagator with per-prediction
   uncertainty (e.g. variance across a small Ridge/tree ensemble, or LightGBM quantiles).
   Pick the next ~200 songs to rate that MOST reduce uncertainty AND span the empty corners
   (so new ratings inform the regions we want to generate into). Write the chosen md5s to
   pools/pool_active.txt and wire it as the live NinjaStar pool (see CODE/36_pool_preview.py /
   38_pool_sampler_v2.py for the pool format; restart ninjastar8.service after swapping —
   PRESERVE existing ratings, they're md5-keyed).
2. (Optional) Add a `rater` column path for a 2nd annotator if the user wants one.
3. After the user banks more ratings, RE-RUN Task 1 to refresh predictions/targets.

VALIDATE: confirm the new pool is balanced over groove deciles + includes empty-corner songs,
and that all prior ratings survive the pool swap. Append a STATE.md session entry.
Do NOT edit signatures/kNN; only the taste lane + pool.
```

---

### On "send to Claude to code"
Each `PROMPT` block is standalone — paste one into a new Claude Code session in this repo and
it'll run. Or run several in parallel as background agents (one per task; Tasks 1/3/4 are
independent, Task 2 depends on Task 1's targets). Recommended sequence: **1 → 2**, with **3**
and **4** anytime alongside.
