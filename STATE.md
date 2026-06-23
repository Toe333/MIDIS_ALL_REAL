# MIDIS_ALL_REAL — Project State & Guide

> **This is the single source of truth for this corpus.** Current status, how to use
> it, verified ground-truth facts, and an append-only session log all live here.
> **Every time we work on this, add an entry to the Session Log at the bottom.**
> Older standalone docs (README.md, AGENT_TODO.md, FINAL_REPORT.txt) were folded
> into this file on 2026-06-16 and deleted — do not recreate them.

> **GrooveDNA (2026-06-18, `CODE/29_groove_dna.py`):** the canonical **11-D drum-only
> Rhythm Vector** per song, built to push the project's #1 priority (rhythm) into a
> dedicated, clusterable space. It reads the `NOTESEQ_DATA` cache (no re-parse, same
> `process_bucket`/parallel pattern as 22), **isolates the drum kit** (`chan 9|10` AND
> GM-percussion pitch `35–81` — AND, not the loose OR, so melodic notes can't leak in),
> and normalizes every density to **per-4/4-bar in beats** (tempo-independent, so the
> "120 BPM reference grid" needs no rescale). The 11 LOCKED dims (array index order):
> `kick_density_bar, snare_backbeat_strength, hat_cym_density, perc_diversity,
> swing_cont, syncopation_drum, dotted_groove, ghost_dynamics, drum_pattern_entropy,
> bar_drum_variance, groove_composite` — all float32, NaN-safe, **neutral 0.5 when a
> song has no drums**. **Purpose:** drum-pattern clustering for new-music invention —
> it gives the corpus a real *feel* axis independent of pitch/harmony. **Integration:**
> outputs `_work/groove_dna.parquet` → `23_catalog_merge.py` folds the 11 scalars onto
> the catalog (inspectable) **plus** a packed `groove_dna float32[11]` array column for
> kNN/clustering. **DONE & integrated 2026-06-18:** computed over all 462,621 cached
> files (311,585 have a real drum kit), merged onto the catalog (now 160 parquet / 159
> sqlite cols), and added to the signature as its own **×2-weighted pillar** via
> `26_signature_extend.py` → **`signatures_ext.npy` is now N×88** (was 85→74; the +3
> over 85 are the 2026-06-20 corrected tempo/meter dims `felt_bpm`/`ts_num`/`ts_compound`
> added to the rhythm pillar — see top Session Log) with kNN
> refit; neighbor groove-block spread is 6× tighter than global (0.071 vs 0.426), i.e.
> feel now clusters. It is the quantitative backbone of the **NinjaStar "Groove" axis**
> (by-ear ratings ↔ measured GrooveDNA) and a new lens for the **empty-space hunt**
> (`27_emptyspace.py`): find under-populated regions of *groove* space, not just
> pitch/harmony space, to target genuinely novel rhythmic feels.

> **DrumDNA (2026-06-18, `CODE/31_drum_vector.py`):** GrooveDNA's bigger sibling — a
> **72-D *standalone* drum signature** with its **own `.npy` matrix + cosine kNN**, so you
> can search/cluster purely by DRUM FEEL and even find "the same beat", independent of
> pitch/harmony/melody. Same proven isolation as 29 (`chan 9|10` AND GM pitch `35–81`),
> same per-4/4-bar-in-beats normalization. **72 LOCKED dims (array index order):**
> 20 scalars (`kick/snare/hat/cymbal/tom/total_density, perc_diversity, kick_on_downbeat,
> snare_backbeat, kick_snare_interlock, swing, laidback, timing_tightness,
> syncopation_poly, ghost_dynamics, accent_strength, pattern_entropy, bar_variance,
> symmetry, pulse_clarity`) + 4 per-beat accent shares (`beat1..4_accent`; one-drop = beat-3
> heavy — closes STATE Open Concern #1) + a 48-D **per-voice 16-step onset grid**
> (kick/snare/hat probability over the bar's 16 sixteenths — the "eigenrhythm" fingerprint,
> the single most discriminative feature for same-beat retrieval). Research-grounded
> (GrooveToolbox/Bruford, HVO/MGT, Longuet-Higgins & Lee metric salience, Columbia
> eigenrhythm). All float32; **a song with no kit → all-zero with `has_drums=0`** (cleaner
> than 29's overloaded 0.5). **Why separate from GrooveDNA:** 29's 11-D is folded into the
> 88-D combined signature and up-weighted for *clustering the whole corpus*; DrumDNA is a
> first-class, higher-resolution *drum-only* space for "find this exact feel". **DONE &
> verified 2026-06-18:** extracted over all 462,621 cached files (311,585 have a kit) →
> `_work/drum_dna.parquet` (74 cols: md5 + has_drums + 72); built
> `SIGNATURES_DATA/signatures_drums.npy` (459,805×72, aligned to `signatures_md5.txt`,
> three equal-weight L2 blocks scalar20/accent4/grid48 → row-norm √3) +
> `SIGNATURES_DATA/knn_drums.pkl` (cosine kNN over the 311,412 drum-bearing rows). Existing
> `signatures*.npy` / `knn_cosine.pkl` and the NinjaStar lane were NOT touched.
> **Empty-Space Hunt (DrumDNA):** `CODE/32_drum_emptyspace.py` run on the 311k drum-active
> subset found 30 coherent-but-empty drum corners (pop=0 within cos≈0.85); top corner
> feels: `no-backbeat · swung(0.50) · sync(0.36) · loose-timing`. **Audio rendered:**
> `_work/drum_emptyspace/corner_audio/*.wav`. **Catalog enriched:** `CODE/33_drum_catalog.py`
> folded 23 drum scalars (e.g., `drum_kick_density`, `drum_snare_backbeat`, `drum_swing`)
> onto `metadata.parquet` and `catalog.sqlite` for SQL-based "feel filtering".


> **DrumDNA v2 (2026-06-18, `CODE/35_drum_vector_v2.py`):** The research-standard upgrade to
> DrumDNA. It expands the **468-D standalone signature** with scientifically-validated
> descriptors and a high-fidelity HVO grid, without touching v1. **Features added:** (A)
> **RhythmToolbox descriptors** (`polyBalance`, `polyEvenness`, `polySync`, band-split
> syncopation/syness) — perceptually-grounded metrics for drum similarity. (B) **HVO grid**
> (Hits, Velocity, Offset) — the 16-step grid now encodes hit probability, root-5 scaled mean
> velocity, and signed microtiming (ahead/behind) per cell. (C) **9-voice GM mapping** —
> expanded from v1's 3 voices to the Groove MIDI Dataset standard 9 (kick, snare, chat, ohat,
> ltom, mtom, htom, crash, ride). **468 LOCKED dims (array index order):** 24 shared with v1
> (20 scalars + 4 accents) + 12 RTB + 144 Hits + 144 Velocity + 144 Offset. **Normalization:**
> 6 equal-weight L2 blocks (scalar/accent/rtb/gridH/gridV/gridO → row-norm √6). **DONE &
> validated 2026-06-18:** extracted over all 462,621 files (311,585 with kit) →
> `_work/drum_dna_v2.parquet` (470 cols: md5+has_drums+468); built
> `SIGNATURES_DATA/signatures_drums_v2.npy` (459,805×468) + `SIGNATURES_DATA/knn_drums_v2.pkl`
> (cosine kNN over 311,412 drum rows). Medians: `polybalance=0.91`, `polyevenness=5.32`,
> `h_kick_00=0.84`. v1 files remain untouched.

---

## MODEL IMPROVEMENT NOTES (append-only — findings from listening sessions)

### 2026-06-19 — Ear-vs-DB calibration, song `5672a901` (high_entropy_drums batch)

**Song:** `5672a90158cffc067ebc828e6ac79cfe` · F major · 150 BPM · 2 min · 5 tracks · 5,778 notes

**Drum pattern (confirmed by ear + MIDI grid dump):**
- Archetype name: `blast_beat_non_drummer_variant_01`
- 16th-note grid (1 bar, repeats locked for entire song):
  `(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)`
- K=kick (BD, pitch 36) on every 16th. S=snare (SD, pitch 38) on odd 16ths. H=closed hat (CHH, pitch 42) on even 16ths.
- Real drummer blast beat is usually `(RK)(S)(RK)(S)...` (ride+kick / snare alternating 8ths) or `(HK)(S)(HK)(S)...` with single kick. This MIDI variant puts kick on EVERY 16th with hat filling the gaps — a programmed approximation, not idiomatic drumming.

**Bassline (confirmed by ear):**
- 1-bar repeating: `F F F F F F F F B B B B C C C C` (16th-note resolution)
- Pitches: F4 (8×) → B3 (4×) → C4 (4×) = root → tritone-down → 5th. Repeats every bar.
- Harmonic motion: I → ♭V (tritone sub) → V — dark/heavy progression typical of metal contexts.

**What this reveals about model accuracy:**
1. **`drum_pattern_entropy` = 0.9999 is WRONG as a complexity measure for blast beats.**
   All 16 kick slots filled → every slot occupied → Shannon entropy = max. But this is the *most regular* pattern possible. Entropy measures slot occupancy, not pattern complexity. Fix needed: add `bar_to_bar_variance` (how much does the pattern change bar-to-bar?). Blast beat = 0.0 variance. Random/complex = high variance. Use variance, not entropy, to find genuinely complex patterns.
2. **`drum_snare_backbeat = 0.25` correctly flags non-standard snare placement** — the snare is on every odd 16th, not on beats 2 & 4. This field is working.
3. **`drum_kick_density = 15.6 kicks/bar` is a real signal** — when this is >12, flag as `blast_beat_candidate`. At normal tempos (120–160 BPM) this physically means a kick on every 16th note. Combine with `drum_pattern_entropy > 0.95` AND `bar_to_bar_variance ≈ 0` to detect this archetype cleanly.
4. **Key detection: DB said F major, ear confirmed F major ✓.** No error here.
5. **BPM: DB says 150, felt as 75 (double-time feel).** Not a data error — the MIDI is notated at 150. The double-time feel is a perceptual consequence of the kick-on-every-16th pattern. Do NOT store a corrected BPM; use as-is. A future `double_time_feel` flag (when `kick_density > 12/bar`) is optional but not urgent.

### 2026-06-19 — `ab83f1dd` is 7/8 + 11/8 mixed meter (Gypsy/Greek folk)

**Song:** `ab83f1ddeb3969f0f54634ef74e7880a` · E major · 120 BPM
**What the DB says:** `time_signature = 4/4` (inferred/filled), `drum_pattern_entropy ≈ 1.0`
**What it actually is:** Bar 1 in **7/8**, then the rest of the song in **11/8**. Accordion + Ocarina + Piano + Bass + Tambourine (p54 every 16th) + irregular hand percussion. Gypsy or Greek folk music. Completely undetected by the current pipeline.

**⭐ #1 PRIORITY: Better rhythm/meter detection before more vectorization.**

> "What's the point of vectors if all the data is wrong?"

The current pipeline has these known rhythm detection failures, confirmed by ear:

| Failure | Example | Impact |
|---|---|---|
| BPM detector latches on subdivisions | songs detected at 37/47 BPM, actually 120–150 | BPM col unreliable for ~10–20% of corpus |
| `time_signature` filled as 4/4 for everything odd | `ab83f1dd` is 7/8+11/8 | All odd-meter songs miscategorized |
| `drum_pattern_entropy` measures slot occupancy, not complexity | blast beat scores max entropy; locked tambourine pulse scores max entropy | Entropy useless as a complexity discriminator |
| Key detector confused by dense percussion | blast beat song detected as F major (actually correct here, but fails on others) | Key accuracy unknown at scale |
| No odd-meter detection at all | 7/8, 11/8, 5/4, 6/8 all stored as 4/4 | Entire folk/world/prog subset is mislabeled |

> **✅ LARGELY ADDRESSED 2026-06-20** — see the top Session Log entry ("DETECTION-ACCURACY PASS"). BPM (the `tempos[0]` bug, 13.5% of corpus), real-meter recovery (hybrid `ts_final`), `felt_tempo` half/double, and key-confidence (`key_corr`) are all fixed in `_work/tempo_meter_v2.parquet` + `_work/key_v2.parquet`, ear-validated (BPM 60→80%, KEY 100%, TS 100%). Remaining: merge into catalog + re-derive per-bar drum metrics on clean bars + (optional) onset-based meter *inference* for the ~33k junk-`1/4`/missing-meter files. The list below is kept as the planning record.

**What needs to be built (Linux, future session, HIGH PRIORITY):**
1. **Real time-signature detector** — onset-based meter detection (e.g. autocorrelation of onset strength at 6/8/7/8/11/8 periods). At minimum: flag songs where 4/4 assumption produces poor grid fit as `meter_uncertain=1`.
2. **BPM confidence + multi-hypothesis** — store top-2 BPM candidates + ratio; flag when detected BPM < 60 (almost always a subdivision error).
3. **`bar_to_bar_drum_variance`** — replaces entropy as complexity measure. Blast beat = 0. Genuinely varying = high.
4. **`blast_beat_candidate`** flag: `kick_density > 12 AND snare_backbeat < 0.35 AND drum_entropy > 0.90`.
5. **Percussion-vs-drum-kit classifier** — tambourine/conga/cabasa patterns (GM pitches 54–81) should be treated differently from kick/snare/hat patterns. Currently all mixed together.

**Until these are fixed, rhythm-based SQL queries and DrumDNA clustering have limited reliability. Fix data before extending vectors.**

**Action items for pipeline (Linux, future session):**
- Add `bar_to_bar_drum_variance` to DrumDNA / catalog — replaces entropy as the "complexity" discriminator.
- Add `blast_beat_candidate` binary flag: `kick_density > 12 AND snare_backbeat < 0.35 AND drum_pattern_entropy > 0.90`.
- When delivering MIDI examples, include key + BPM + md5 prefix in filename (already done in `40_sql_explore.py`).
- Use MIDI delivery (not WAV bounce) for ear-check sessions — faster, smaller, playable at any tempo in a DAW.

---

## CURRENT STATUS (always reflects the latest session)

**As of 2026-06-22 (latest) — the taste→groove→generate loop is now CLOSED end-to-end.** Four
things shipped today (all committed; see the four 2026-06-22 Session Log entries for detail):
1. **Embed any single MIDI into the live N×88 space** — `CODE/49_sig_one.py` re-derives the
   scaler 26 never saved and reuses the per-file feature functions; verified round-trip
   **cosine 1.0000** (median over 120 songs) vs the stored rows. This is the missing primitive
   that lets us score *new* / *external* files against the corpus and the empty corners.
2. **Route-C generator** — `CODE/50_generate.py` recombines an empty corner's nearest-donor
   stems (drums/melody/harmony) at the corner BPM, scores each candidate with 49, gates on
   beauty, renders to webplayer. Works but only reaches the *rim* of empty space (the corner is
   empty by construction); the stretch is theory-steered generation.
3. **Canonical taste propagator** — `CODE/47_propagator.py` → **`_work/taste_pred_v2.parquet`**
   (md5 + 7 pred axes + `pred_love` + `unc_love` + provenance cols). Train on **v2 ratings only**
   (n=131; mixing v1 legacy hurts CV). Only **musicality/novelty/groove** carry signal; groove
   tuned to up=3/alpha=300 (r≈0.36). `pred_love` is groove-dominant. 120 corners ranked →
   `_work/generation_seeds/targets_taste_v2_20260622.csv`.
4. **Active learning is LIVE** — `CODE/48_active_pool.py` put 200 high-information songs
   (uncertainty + empty-corner proximity, groove-balanced) on the phone
   (`pool_current.txt`→`pool_active.parquet`, `ninjastar8.service` restarted, **286 ratings
   preserved**).

> **WHERE WE STAND / WHAT'S NEXT.** The pipeline is VECTORIZED (N×88) and now also *generative*
> + *taste-aware*. **The single highest-leverage action is human: rate the 200-song active pool
> on the phone, then re-run `47_propagator.py` → `48_active_pool.py`** to tighten the groove
> model (it's the bottleneck — r≈0.36). Open engineering, in priority order:
> (a) **Task 3** — re-embed UMAP on N×88 + mapserver with taste tint + corner overlay (the visual
> map is still N×74-era); (b) **Task 5** — fold `taste_pred_v2` into `catalog.sqlite` as view
> `v_good_empty` (canonical parquet + provenance done; the SQL view is the open piece);
> (c) **Stretch** — theory-steered generation (music_rules/SkyTNT + rejection sampling) to push
> *into* empty space instead of hovering at its rim; de-dup donor selection in 50.
> **Data note from today:** embedding the user's new MIDI drop confirmed **odd-meter groove is
> genuine empty space** (every gypsy 11/8–11/16 pattern maps nearest to a 4/4 corpus song); Max
> Roach "minor trouble", Fela, and the gypsy patterns are the strongest seed/anchor candidates.
> **Use going forward:** `signatures_ext.npy` (N×88) + `knn_cosine.pkl`; `49_sig_one.py` to embed
> new files; `taste_pred_v2.parquet` (canonical taste) + `targets_taste_v2_20260622.csv`.

**As of 2026-06-20 — signature refreshed to N×88, empty-space hunt re-run, docs brought current.** The rhythm pillar now folds in the corrected tempo/meter (`felt_bpm`, `ts_num`, `ts_compound`) → **`SIGNATURES_DATA/signatures_ext.npy` is N×88** (pitch 36 / rhythm 20 / melody 13 / harmony 8 / groove 11; rhythm & groove ×2-weighted), cosine `knn_cosine.pkl` refit, validated no-regression (meter & felt-tempo now cluster; swing/sync unchanged). The empty-space hunt was **re-run on N×88** (`_work/emptyspace/`: 1200 clusters, 60 blends + 60 isolated, captioned with meter+felt-tempo; ~0% corner overlap with the old N×74 run; top-10 in webplayer group `emptyspace_n88`). MANUAL.md + this file's evergreen reference sections updated to 88-D / ~201 cols; obsolete handoffs removed. **Use `signatures_ext.npy` (N×88) + `knn_cosine.pkl` going forward.** Next steps catalogued in `TASKS_NEXT.md`. See top Session Log entries.

**As of 2026-06-20 — DETECTION-ACCURACY PASS done & merged into the catalog.** The #1-priority "fix the data" work: BPM (`tempos[0]` bug, 13.5% of corpus wrong), real-meter recovery (hybrid `ts_final`), `felt_bpm` (half/double), and key-confidence (`key_corr`, was a broken metric) are all fixed and **folded additively into `metadata.parquet`/`catalog.sqlite`** (18 new `*_v2` cols; originals kept). Ear-validated on 5 songs (BPM 60→80%, KEY 100%, TS 100%). Drum density investigated → fine at scale (no re-derive needed). See top Session Log entry. **Use `bpm_v2`/`ts_final`/`key_v2`+`key_corr` going forward.** (Prior status below still holds for the taste/empty-space lane.)

**As of 2026-06-18 (evening) — FIRST taste→pool→propagate loop closed (under Grok supervision via the Playwright bridge).** Live NinjaStar pool swapped to a 500-song **rhythm-heavy stratified set** (`_work/pool_v2.parquet`, now `pool_current.txt`; 73% drum-bearing, all 88 eligible empty-corner songs force-included, balanced over groove deciles) and the systemd service restarted on its pinned port 8780 — phone queue is now the new set, all 283 ratings preserved (md5-keyed). A **taste-propagator STUB** (`CODE/37_taste_stub.py`, Ridge on the 85-D signature → user groove rating, GrooveDNA block ×5) was trained on the 128 v2 groove ratings and predicted over all 459,805 → `_work/taste_pred.parquet`; 5-fold CV **pearson r=+0.318, MAE=2.00** (weak but real — needs more groove truth). Pool builders: `CODE/36_pool_preview.py` (the live v2) and `CODE/38_pool_sampler_v2.py` (Grok-spec 512-row rhythm-weighted, staged not deployed). **Generation seeds RESOLVED = option B (top-5 empty-corner targets):** `b56df652, 622f340d, f96decc4, 41277f13, cf698cb6` (pred groove-taste 6.73–7.08) → `_work/generation_seeds/top5_targets.csv`, and rendered to audio (`_work/seed_audio/*.wav`, in webplayer group `empty-corner-targets`) so they can be auditioned. Signature was N×85 at this point (now N×88 — see the latest block above). (Prior: 2026-06-18 ~15:30 GrooveDNA+MCP+NinjaStar-v2; 2026-06-17 finish line N×74.) **Strategic frame below still holds: coordinates over labels; hunt empty space and LISTEN.**

> ### ⭐ STRATEGIC FRAME (why we measure coordinates, not genres)
> A machine *can* tag rock/rap/jazz and detect beats (audio: librosa/madmom/Essentia/Spotify-features; symbolic: research-grade MIDI genre classifiers). **But a classifier maps music into buckets that already exist — it describes the past and pulls toward the average. The north star (invent a new form of music) needs the opposite:** a continuous coordinate space (our 88-D vector incl. GrooveDNA) where *gaps* are visible. A label says "this is rock"; coordinates say "this sits here, and over *there* is empty — go make that." So: GrooveDNA (the 11 numbers) = the right primitive and it's DONE. A pretrained genre tag would be a nice optional metadata column, not the quest. The MCP notation/archetypes + NinjaStar anchor UI were partly **tools-for-tools / scope creep** — keep the archetypes only as ear-reference probes; don't build them out further until the core experiment proves it needs them. **Core experiment = empty-space hunt (`27_emptyspace.py all`) on N×88, cross-referenced with [[taste-anchor-songs]], then generate a few candidates and listen.**

> ### ▶ NEXT SESSION — START HERE (corpus lane)
> **Two parallel lanes now:** (A) **corpus / Phase 11** — this pointer; (B) **NinjaStar-8 annotator**
> — a self-running phone lane (live at https://lab.tail0b3418.ts.net/, systemd service), only touches
> `ninjastar8.py` / `_work/ninjastar8_ratings.parquet` / `soundfonts/` / `web/`. **Corpus work must NOT
> touch those.** They're conflict-free. (See the top Session Log entry + the NinjaStar-8 block in ROADMAP.)
>
> The build pipeline is **DONE**. Vectorized: `SIGNATURES_DATA/signatures_ext.npy` (N×88) +
> rebuilt cosine `knn_cosine.pkl`; catalog 459,805×~201. Nothing mid-run.
> **Phase 11 #1 (empty-space hunt) is now DONE** — `CODE/27_emptyspace.py` + `_work/emptyspace/`
> (clusters, full density/frontier, cluster_summary, corners_blends, corners_isolated, REPORT.md,
> corner_audio in webplayer group `emptyspace_corners`). See the top Session Log entry.
> **Recommended next task: pick the *beautiful* corners — cross `corners_blends`/`corners_isolated`
> with taste.** Either (a) proxy "beauty" filters now (high diatonic_ratio + has_melody + low
> dissonance + moderate sync) to shortlist corners worth generating, or (b) Phase 11 #2 (re-cluster
> `song_id` with the 88-D sig). Re-run bolder: `python3 CODE/27_emptyspace.py corners --pair-lo .15 --pair-hi .85`.
> Load vectors per HOW TO USE IT → "Find similar songs". ⚠️ kNN is brute cosine over 460k rows.

> **The goal is to get the corpus EXPERIMENT-READY, which means VECTORIZED:** every song a
> point in one extended feature space (signature) so we can do kNN, clustering, and the
> "empty-space" hunt. Pitch/harmony were already in the 36-D signature; the 2026-06-17
> rhythm-first re-parse added the missing TIME-FEEL + melody-contour + refined-harmony
> dimensions. **That path is now complete** (harmony 25 → catalog merge 23 → signature
> extend + kNN rebuild 26, all done 2026-06-17). Forward work lives in ROADMAP → Phase 11.

**Rhythm-first re-parse pipeline (2026-06-17):**
- **Re-parse → `NOTESEQ_DATA/` cache — ✅ DONE** (256/256 buckets, ~463k files). Permanent note-sequence store `(start,dur,chan,pitch,vel)`; nothing ever re-parses again. All refine passes read from here.
- **22 rhythm refine — ✅ DONE** → `_work/rhythm_features.parquet` (462,621 rows, 16 cols). is_swung=20,098 / is_dotted=84,971 / is_triplet_feel=38,386.
- **24 melody refine — ✅ DONE** → `_work/melody_features.parquet` (462,621 rows, 20 cols). has_melody=460,948.
- **25 harmony refine — ✅ DONE (2026-06-17 13:44, resumed run `--workers 10`).** → `_work/harmony_features.parquet` (**462,621 rows, 13 cols**). 256/256 buckets, ~44 files/s, clean exit. Sanity: `harmonic_rhythm` med 2.82, `diatonic_ratio` med 0.832, `n_key_areas` med 6.0 (the med 2.8 / med 6 are the known "tune later" reads — smoothing/key_stability, re-derivable from cache, no re-parse). Writes `_work/harmony_parts/<2hex>.parquet` → merged to `_work/harmony_features.parquet` (`HARMONY_FORCE=1` to redo a bucket).
- **23 catalog merge — ✅ DONE (2026-06-17 14:16).** `catalog/metadata.parquet` + `catalog.sqlite` now **148 cols** (80→148, +68: seq/rhythm/melody/harmony), **459,805 rows unchanged**, parquet⇄sqlite agree. Verify counts: is_swung=20,069 / is_dotted=84,068 / has_melody=458,607 / swing_bur not-null=409,926. Pre-merge checkpoint: `catalog/checkpoints/catalog_20260617_141430_pre23.sqlite` (+ script's own `.bak_20260617_141441`).
- **Signature → vectors rebuild — ✅ DONE (2026-06-17 15:02, `CODE/26_signature_extend.py`).** Extended `signatures.npy` (N×36 pitch, UNTOUCHED) → **`signatures_ext.npy` (459,805 × 74)** = pitch 36 + rhythm 17 + melody 13 + harmony 8. Catalog feature cols reindexed to `signatures_md5.txt` order **by md5** (not row order); `tempo_class` one-hot into rhythm, `most_common_chord` dropped (high-card; pitch already covers it). Per-pillar scaling: log1p heavy tails (max>50) → median-impute NaN (rhythm 58,189 / melody 15,678 / harmony 1,312 cells; ~52 md5s absent from catalog all-imputed) → z-score → clip ±8 → per-row L2 → ×√weight. **Rhythm up-weighted ×2** (pitch/melody/harmony ×1); full-vector norm const ≈√5 so cosine = w-weighted avg of per-pillar cosines. Refit `NearestNeighbors(metric='cosine', algorithm='brute')` over all rows → **`knn_cosine.pkl`** (dict keeps `nn`+`fit_rows`=all rows for back-compat, plus `block_dims`/`weights`/`feature_names`/`report`). **Sanity ✅:** mean neighbor rhythm z-spread dropped **1.004 (pitch-only) → 0.375 (extended)**; e.g. a triplet-feel seed's pitch-only neighbors were triplet≈0 but extended neighbors triplet≈0.55. Backups: `signatures_20260617_150005.npy.bak`, `knn_cosine_20260617_150005.pkl.bak`, `knn_cosine.pkl.prerefit_20260617_150210.bak`. Re-run/tune weights: `python3 CODE/26_signature_extend.py --w-rhythm N` (`--dry-run` to preview, `--no-backup` to skip in-script copy).

**Core pipeline P0–P8 (2026-06-16): COMPLETE — corpus is clean & catalogued.**

- **Catalog:** `catalog/catalog.sqlite` + `catalog/metadata.parquet` — **~201 columns** (current; 80 after the 2026-06-16 audit-gap fixes → 148 with the 2026-06-17 rhythm/melody/harmony merge → ~160 with GrooveDNA → 201 with the 2026-06-20 tempo/meter/key merge), **459,805 rows**. Every row has a `song_id` (378,923 distinct) and a `split`. Quality filter cols: `quality_flag`, `bpm_valid`, `duration_suspect`, `time_signature_inferred`; corrected detection: `bpm_v2`/`felt_bpm`/`ts_final`/`key_v2`/`key_corr`.
- **Manifest:** `catalog/master_manifest.parquet` — **463,896 rows** (one per unique md5).
- **Gap of 4,091** (463,896 − 459,805) = files that failed parse / too-few-notes; by design, in `meta_errors.log`, NOT in metadata. Reconciles exactly.
- **Quarantined:** 90 genuinely-broken files in `_quarantine/` (recorded in manifest, never deleted).
- **Splits:** train 367,139 / val 46,106 / test 46,560 — song-level (no arrangement leakage).
- **Pools:** gold 239,126 / silver 133,173 / bronze 6,624 + genre/feature pools.

**What's left (the build pipeline is DONE; what remains is USING the space + upkeep):**
- **Data-quality gaps: ALL 5 DONE 2026-06-16 (see KNOWN GAPS below).** Catalog now ~201 columns.
- **Phase 9 (rhythm-first re-parse): DONE 2026-06-17** — 9.1 audio sanity, 9.R rhythm, 9.2 melody, 9.3/9.4 structure/tempo all folded into the 21→26 pipeline and merged. Signature is vectorized (now **N×88**; N×74 at first build). Nothing mid-run.
- **NEXT (forward roadmap — no scripts yet; see ROADMAP "Phase 11" below):**
  1. **Empty-space hunt / clustering** (`CODE/27_*`) — the payoff: map dense vs sparse regions of the 88-D space, cluster, drive sampling. THIS is what vectorizing was for.
  2. **Re-cluster `song_id` with the richer signature** — `12_signatures.py` dedup used pitch-only (36-D) and over-merges; rhythm+melody now available to tighten it. Deliberate backed-up rebuild.
  3. **Phase 10 maintenance scripts** — `validate_new.sh`, `rebuild_catalog.sh`, `rebuild_pools.sh`, `stats_report.sh`; fold `26_signature_extend.py` into a reproducible rebuild.
  4. **Polish** — validate the rhythm up-weight (currently ×2, a guess) empirically; tune the two "tune-later" harmony reads (smoothing / `key_stability`), re-derivable from `NOTESEQ_DATA` cache.

---

## KNOWN GAPS / QUALITY TODO (found 2026-06-16 audit — verified by SQL)

**All 5 gaps fixed 2026-06-16.** Kept here as a record of what was done. None required another full parse pass.

1. **✅ DONE (2026-06-16).** ~~`song_id` only on 104,198 / 459,805 files.~~ All 355,607 singletons now have their own `song_id = "song_"+uuid5(NAMESPACE_DNS, md5).hex[:12]` (identical algorithm to the cluster roots in `12_signatures.py`). Every metadata row + every manifest row now has a `song_id`; **378,923 distinct song_ids, zero truncation collisions** (23,316 clusters + 355,607 singletons). Fixed by `CODE/18_fill_song_id_and_split.py`.
2. **✅ DONE (2026-06-16).** ~~No `split` column.~~ `metadata` now has a `split TEXT` column (+ `idx_meta_split`), joined from `TOKENIZED/{train,val,test}_manifest.tsv` by md5. No NULLs; counts match `split_report.json` exactly (train 367,139 / val 46,106 / test 46,560). `WHERE split='train'` works in SQL and through all views. Same script as #1.
3. **✅ DONE (2026-06-16).** ~~`time_signature` 15% wrong/missing.~~ Filled 68,364 bad values (33,717 NULL + 32,639 `1/4` + 2,008 `1/8` artifacts) → `4/4` and added `time_signature_inferred` flag (1 = filled/corrected, recoverable). `4/4` now 393,614; 0 NULL, 0 `1/4`/`1/8` left. Fixed by `CODE/19_quality_flags.py`.
4. **✅ DONE (2026-06-16).** ~~BPM outliers.~~ Added `bpm_valid` flag (1 when 20≤bpm≤300): **452,508 valid / 7,297 invalid** (NULL/`>300`/`<20`). `bpm` itself not overwritten (raw tempo events aren't stored — flag, don't fabricate; `COALESCE(bpm,120)` for a default). Same script as #3.
5. **✅ DONE (2026-06-16).** ~~Duration outliers.~~ Added `duration_suspect` flag (1 when `duration_sec>3600`): **289 files** (up to 9.9h, stuck-note junk). Same script as #3.

> Negative durations from the OLD build report are **already fixed** (0 now). `quality_flag` and quarantine handling are working. **Catalog was 80 columns here (all 5 audit gaps closed); now 148 after the 2026-06-17 pillar merge.** New filter cols: `split`, `time_signature_inferred`, `bpm_valid`, `duration_suspect`; every row has a `song_id`. A pristine clean subset = `WHERE quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0`.

---

## GROUND TRUTH (verified 2026-06-16 — do not re-assume; this was checked on disk)

| Fact | Value | Implication |
|---|---|---|
| Parser in use | **TMIDIX** (`/home/t/datasets/LAMD/CODE/TMIDIX.py`), not pretty_midi/music21 | House parser, ~33 ms/file. Reuse it. |
| `metadata.parquet` | 459,805 rows × ~201 cols | 4,091 files failed parse (in `catalog/meta_errors.log`); NOT in metadata. |
| Local `META_DATA/*.pickle` | 10 chunks, md5-keyed | Already contain `total_pitches_counts` (pitch sig), `ms_chords_counts` (chord sig), patch/timing/velocity stats for all 459,805. Signatures + chords are a *transform*, not a new parse. |
| LAMD `SIGNATURES_DATA/LAMDa_SIGNATURES_DATA.pickle` | 404,714 `[md5, signature]` | Joinable to 87% of corpus by md5. Don't recompute. |
| `master_manifest.parquet` | 463,896 rows: md5, stored_path, size, n_copies, sources, hosts, original_paths | The full file list of record. |
| Errors | meta_errors.log = 4,001 too-few-notes (≤32 notes, **policy reject, not corrupt**) + 89 IndexError + 1 other; errors.log = 1 zero-length (`bitmidi/368.mid`) | Only ~90 genuinely suspect. |
| Symlinks in `MIDIs/` | **0** | Store is clean real copies. |
| Provenance names | LAMD/Lakh/bitmidi basenames are **MD5 hashes** (no human names). Real names only for ragtime/maestro/personal (~38k). | Filename genre/composer mining is a small targeted job, not corpus-wide. |
| Source tags | **NOISY** (a bitmidi-tagged row pointed at a lakh path) | Treat `sources` as a hint to verify, not ground truth. |
| Installed libs | mido, pretty_midi 0.2.11, music21 9.9.1, pandas 3.0.3, numpy 2.4.6, pyarrow, sklearn 1.8.0, scipy, tqdm | No venv/install phase needed. |
| Audio tooling | `fluidsynth` + `midi_to_colab_audio.py` in LAMD CODE | Phase 9 audio render feasible. (Preview with `webplayer`.) |

**Three rules the pipeline is built on:** (1) Don't re-parse for data already in the pickles. (2) ONE unified TMIDIX pass for genuinely-new features. (3) music21 is opt-in, subset-only (50–150× slower than TMIDIX); key detection is numpy Krumhansl-Schmuckler.

---

## WHAT THE CORPUS IS

One unified, deduplicated, machine-readable MIDI corpus, organized like the **Los Angeles MIDI Dataset (LAMD)** so LAMD/SkyTNT tooling works over it. Built 2026-06-14 from every MIDI on `imac` + `lab` (personal + full LAMD + Lakh + BitMidi). One **real** copy per unique song (full-content MD5 dedup); every original path preserved in the manifest.

- **Input files inventoried:** 935,168 (lab 919,782 + imac 15,387)
- **Unique songs stored:** 463,896 (≈50% were byte-identical duplicates)
- **Dedup:** full MD5 of file contents. Different *arrangements* of a tune stay separate (collapsed later via signature-based `song_id`, never deleted).

### Source breakdown (input files, before dedup)
| source | files | | source | files |
|---|---|---|---|---|
| lamd | 404,714 | | 2fast_existing | 20,346 |
| lakh | 354,962 | | imac_personal | 15,387 |
| bitmidi | 113,237 | | ragtime | 3,574 |
| lab_personal | 21,672 | | maestro | 1,276 |

### v2 enrichment (what the 76 columns add over the original 17)
- **Key/mode** — numpy Krumhansl-Schmuckler (`key`, `mode`, `key_confidence`); 99.8% coverage.
- **Complexity/quality** — `polyphony_density`, `note_density`, `pitch_class_entropy`, `velocity_dynamic_range`, `tempo_stability`, `register_span_semitones`, etc.
- **Instrumentation** — per-GM-family track counts, `has_bass`, `has_pad`, `is_solo`.
- **Harmony** — `n_unique_chords`, `chord_density`, `has_extended_harmony`, `progression_complexity`, `most_common_chord`.
- **Near-dup `song_id`** — 23,316 multi-arrangement clusters (cosine-NN on pitch sigs); `is_canonical`, `n_arrangements`.
- **Provenance/tags** — `composer`/`title` for ~4.8k named files; coarse `genre_hint` (75% honest `unknown`).
- **Integrity** — `quality_flag` (`ok` | `absurd_density`; 4,352 corrupt-tempo files have density cols nulled); 90 quarantined.
- **Splits** — song-level 80/10/10. **Pools** — quality/genre/feature tiers.

---

## LAYOUT

```
MIDIs/<2-hex>/<md5>.mid     deduped REAL copies, 256 buckets (md5[:2]) — READ-ONLY
_quarantine/<2-hex>/        90 genuinely-broken files (moved, never deleted)
META_DATA/                  LAMDa-compatible [md5, data] pickles (data[8]=ms_chords_counts,
                            data[10]=total_pitches_counts -> similarity sig + chords)
SIGNATURES_DATA/            signatures.npy (N x 36, pitch-only) + signatures_ext.npy (N x 88,
                            pitch+rhythm+melody+harmony+groove) + signatures_md5.txt + knn_cosine.pkl
                            (cosine kNN on the 88-D matrix) + timestamped *.bak
CHORDS_DATA/                chords_summary.parquet (md5-keyed harmony features)
TOKENIZED/                  {train,val,test}_manifest.tsv (song-level 80/10/10) + split_report.json
pools/                      *.tsv quality/genre/feature pools (pointers, not copies) + pool_sizes.json
catalog/
  master_manifest.parquet   md5 -> stored_path, size, sources, original_paths[], is_quarantined, song_id
  metadata.parquet          148 per-file features (was 76→80→148; +seq/rhythm/melody/harmony pillars)
  catalog.sqlite            metadata + manifest; views: catalog, catalog_all, v_clean, v_canonical,
                            v_with_lyrics, v_classical, v_solo_piano, v_no_drums
  checkpoints/              timestamped sqlite snapshots before each rebuild
_work/  _logs/  _stats/     pipeline outputs, logs, dataset card + corpus stats
CODE/                       build scripts (02-06) + v2 pipeline (_common, 10-17, run_all.sh)
                            + v3 rhythm-first re-parse & vectorize (18-26)
```

> Buckets are 2-hex (`md5[:2]`, 256 dirs). Stock `midi-model/build_training_manifest.py` uses single-hex `h[0]` — change to `h[:2]` and point `MIDI_ROOT` at `MIDIs/` to reuse it.

---

## HOW TO USE IT

### Query (SQL)
```bash
sqlite3 catalog/catalog.sqlite
SELECT count(*) FROM catalog;                                   -- 459,805 (non-quarantined)
SELECT key, count(*) c FROM catalog GROUP BY key ORDER BY c DESC LIMIT 10;
-- canonical only, minor key, clean timing, with lyrics:
SELECT md5, key, duration_sec FROM v_canonical
  WHERE mode='minor' AND quality_flag='ok' AND has_lyrics=1
  ORDER BY duration_sec DESC LIMIT 20;
```
Views: `catalog` (clean default), `catalog_all` (incl. quarantined), `v_clean`, `v_canonical` (one file per song), `v_with_lyrics`, `v_classical`, `v_solo_piano`, `v_no_drums`.

### Pandas
```python
import pandas as pd
m   = pd.read_parquet("catalog/metadata.parquet")
man = pd.read_parquet("catalog/master_manifest.parquet")
```

### Find similar songs
`04_search.py` is the old **pitch-only** brute-force ratio search (LAMD-style, no index):
```bash
python3 CODE/04_search.py --out-root . --query /path/to/song.mid --top 10
python3 CODE/04_search.py --out-root . --md5 <md5-in-store> --top 10
```
The **vectorized** path (pitch+rhythm+melody+harmony, rhythm-aware) uses the rebuilt kNN:
```python
import numpy as np, pickle
ext  = np.load("SIGNATURES_DATA/signatures_ext.npy")            # N x 88
md5s = open("SIGNATURES_DATA/signatures_md5.txt").read().split()
P = pickle.load(open("SIGNATURES_DATA/knn_cosine.pkl","rb"))    # {nn, fit_rows, block_dims, weights, ...}
row = md5s.index("<some_md5>")
d,i = P["nn"].kneighbors(ext[row:row+1], n_neighbors=11)
print([md5s[j] for j in i[0] if j != row])                      # 10 nearest (rhythm counts ×2)
```
Re-tune pillar weights anytime: `python3 CODE/26_signature_extend.py --w-rhythm N` (`--dry-run` to preview).

### Train / LoRA pool
`TOKENIZED/train_manifest.tsv` is the training set (SkyTNT `train.py` tokenizes live). Filter metadata → md5 list → join to the manifest for paths. Pools are **manifests of stored paths, not copies**: `pools/tier_gold.tsv` (239k curated), silver, bronze + genre/feature pools (sizes in `pools/pool_sizes.json`).

---

## PIPELINE / CODE PROVENANCE (in CODE/)

**v1 build:** `02_make_dataset.py` (dedup+store+manifest) · `03_make_metadata.py` (metadata/sig/chord pickles+parquet+sqlite) · `04_search.py` (similarity CLI) · `05_tokenize.py` (train manifest+sample shards) · `06_enrich_pop60s.py` (one-off "pop60s like incense" query, Jun 14 — see `catalog/enrichment*`, `pop60s_like_incense.csv`).

**v2 enrichment (resumable; `bash CODE/run_all.sh`):** `_common.py` (helpers, pickle parser, K-S key) · `10_scan.py` (the one TMIDIX parse: integrity + velocity/tempo/drum) · `11_features.py` (key/entropy/instrumentation, pickle-derived) · `12_signatures.py` (N×36 PITCH matrix + initial kNN + near-dup clusters) · `13_chords.py` (harmony) · `14_provenance.py` (composer/genre/era) · `15_catalog.py` (merge → 76-col catalog) · `16_splits_pools.py` (splits+pools) · `17_stats.py` (stats + HF dataset card).

**v3 rhythm-first re-parse & vectorize (2026-06-17):** `18_fill_song_id_and_split.py` + `19_quality_flags.py` (the 5 audit-gap fixes) · `20_audio_sanity.py` (Phase 9.1 render check) · `21_sequences.py` (the unified TMIDIX re-parse → `NOTESEQ_DATA/` note-sequence cache) · `22_rhythm_refine.py` · `24_melody_refine.py` · `25_harmony_refine.py` (the 3 pillar feature tables, read from cache) · `23_catalog_merge.py` (merge pillars → catalog) · **`26_signature_extend.py` (extend N×36 pitch sig → `signatures_ext.npy`, now **N×88** incl. groove + corrected tempo/meter, rhythm & groove ×2, refit cosine `knn_cosine.pkl`)** · `27_emptyspace.py` (the empty-space hunt) · `29_groove_dna.py` (GrooveDNA) · `41/43/44_*` (corrected tempo/meter/key + merge).

Logs in `_logs/` (per-phase + `progress.log`). Stats in `_stats/`.

---

## ROADMAP — Phase 9 ✅ DONE 2026-06-17 (was "all of Phase 9, in order"; folded into the 21→26 rhythm-first pipeline). Forward work = Phase 11 below.

Do these in order: 9.1 → 9.2 → 9.3 → 9.4 → 10.x. Continue the established pattern
(backup sqlite+parquet first; new flag/feature COLUMNS, non-destructive; verify
parquet ⇄ sqlite agree; one script per phase in `CODE/`, numbered 20+).

- **9.1 Audio sanity render — ✅ DONE 2026-06-16** (`CODE/20_audio_sanity.py` → `_stats/audio_sanity.parquet`, 500 rows + WAVs in `_stats/audio_sanity_wav/`). 500-file deterministic sample (linspace over sorted md5, non-quarantined, ≤3600s). **Result: 0 silent, 0 render errors → corpus renders to real audio.** 17 clipping (`frac_fs>0.10`), 19 length_mismatch (stuck/hanging notes). NOTE: renderer max-normalizes so `peak`≈1.0 is useless — used `rms` (silence) + `frac_fs`=frac samples near full-scale (saturation). Raw metrics saved → re-thresholdable without re-render. WAVs in webplayer group `audio_sanity`.
- **⚠️ PIVOT 2026-06-17: RHYTHM IS THE TOP PRIORITY** — **✅ FULLY DELIVERED 2026-06-17 15:02 (see CURRENT STATUS + top session-log entry).** The rhythm block now lives in `signatures_ext.npy` (now N×88, rhythm & groove up-weighted ×2); this section is kept as the planning record. (User directive — rhythm is THE most important dimension for the model; the old 36-D signature had ZERO rhythm.) 9.2–9.4 folded into ONE unified TMIDIX re-parse of all ~460k files (user chose full re-parse 2026-06-17 — pickles only have aggregates, NOT note sequences, so contour/structure/rhythm-curve need real parsing). Script: `CODE/21_sequences.py`.
  - **9.R Rhythm block (NEW, primary deliverable):** IOI distribution (beat units), onset density, grid/quantization tightness, syncopation score, swing ratio, microtiming/groove, pulse clarity (onset-envelope autocorr), polyrhythm hint, duration profile. These become NEW signature dimensions so the empty-space hunt covers TIME-FEEL.
  - **9.2 Melody (secondary, same pass):** `has_melody`, `melody_track_index`, `melody_n_notes`, contour fingerprint.
  - **9.3 Structure (secondary, same pass):** self-similarity → `n_sections`, `has_repetition`.
  - **9.4 Tempo-curve:** `constant|gradual|rubato|erratic` (part of the rhythm block).
  - **Note-sequence CACHE:** per-bucket compressed store of `(start_tick,dur_tick,chan,pitch,vel)` per file → never parse again.
- **10.x Maintenance scripts** — `validate_new.sh`, `rebuild_catalog.sh`, `rebuild_pools.sh`, `stats_report.sh`. **(still pending — see Phase 11 #3.)**

### Phase 11 — USE the vectorized space (NEW, the work after the finish line; chosen 2026-06-17)
The corpus is vectorized (`signatures_ext.npy`, now **N×88** + cosine kNN). The build pipeline is complete; everything below is about *using* the space and keeping it maintainable. Priority order (recommended start = #1):
1. **Empty-space hunt / clustering — `CODE/27_emptyspace.py` (the payoff) — ✅ BUILT & re-run on N×88.** Maps where the 88-D dots are dense vs sparse, clusters the 460k points, surfaces "empty-but-coherent corners" (under-represented but musically-plausible regions) to aim generation/sampling at — spanning TIME-FEEL + groove, not just pitch. Outputs in `_work/emptyspace/`. The ×2 rhythm/groove weight is confirmed to cluster feel. Remaining: cross corners with taste + generate (see `TASKS_NEXT.md`).
2. **Re-cluster `song_id` with the richer signature.** `12_signatures.py`'s near-dup clustering runs on 36-D pitch only and is documented to over-merge (e.g. simple C-major files collapse). Rhythm+melody now let it distinguish arrangements that pitch alone can't. A deliberate, backed-up rebuild (changes `song_id` groupings → re-verify splits don't leak).
3. **Phase 10 maintenance** (above) — make catalog→signature→kNN rebuild reproducibly; fold `26_signature_extend.py` into the rebuild flow (it's currently a one-off).
4. **Polish.** Validate the rhythm up-weight (×2 is a guess — e.g. check against known arrangement clusters); tune the two "tune-later" harmony reads (smoothing / `key_stability`; `harmonic_rhythm` med 2.82, `n_key_areas` med 6.0), re-derivable from `NOTESEQ_DATA` — no re-parse.

**Separate parallel workstream (not blocking the above) — human-annotation tool ("NinjaStar-8"): ✅ BUILT & LIVE (2026-06-17).** `ninjastar8.py` (project root) — phone-first web app to add subjective by-ear ratings (groove/slaps/energy/peace_kill/lobrow_hibrow/simple_fancy/left_right/normie_weird — **8 sliders, 0–8 scale, 4 = neutral**) → `_work/ninjastar8_ratings.parquet`, left-merges onto the catalog by `md5` like any other feature table (un-rated stay NaN; never touches catalog directly). Adds taste/feel axes the computed features can't. Full build spec in **`ANNOTATOR_SPEC.md`**; see `[[human-annotation-plan]]`. **This is a self-running, separate lane — a corpus/Phase-11 agent should NOT touch `ninjastar8.py` / `_work/ninjastar8_ratings.parquet` / `soundfonts/` / `web/`.**
- **Access (persistent, works on the road over cell): https://lab.tail0b3418.ts.net/** (Tailscale Serve HTTPS → `127.0.0.1:8780`). HTTPS is **required** — the in-browser synth (AudioWorklet) only runs in a secure context; plain `http://<tailscale-ip>:8780` will NOT play audio. (Set up via tailnet HTTPS Certificates + `tailscale set --operator=t` + `tailscale serve --bg --https=443 http://127.0.0.1:8780`.)
- **MIDI-first playback:** serves the source `.mid` (~36 KB med) and synthesizes in-browser via **self-hosted spessasynth_lib v4** (`web/vendor/`: lib 76 KB + worklet 388 KB + core 720 KB, ~1.2 MB cached once; lib's bare `spessasynth_core` import was patched to relative `./spessasynth_core.js`; URLs carry `?v=N` cache-bust). **`synth.connect(ctx.destination)` is required** (no auto-connect — omitting it = silent playback that looks like it's working). Swappable soundfont via ♪ dropdown (`soundfonts/`): **default VintageDreams 314 KB** (instant on bad cell); **GeneralUserGS 30 MB** opt-in (much better GM, load once on wifi). Drop any `.sf2/.sf3` in `soundfonts/` → auto-appears.
- **Bipolar diverging sliders:** each slider lights green OUT FROM the neutral center (4); push left → lo pole, right → hi pole. Sliders **default to 4** (untouched save = neutral 4, NOT NaN). Stored value is still a single 0–8 int per axis (0=lo pole, 4=neutral, 8=hi pole) — the diverging visual is cosmetic only. Whole UI fits one phone screen (≤540 px).
- **Offline-resilient save (survives cellular dead zones):** on save it writes to `localStorage` + advances INSTANTLY (never blocks), then POSTs in the background; failed POSTs stay queued (⟳N badge) and auto-retry every 5 s / on `online` / on reload. A save can't be lost to a dropped connection. Server `/rate` upsert is idempotent.
- **Verified on WebKit (Safari engine) + iPhone emulation:** real audio output, default-4, all-green diverging meter, one-screen fit, offline-queue→sync, all pass.
- Ratings so far: **45** (md5-keyed). Pool = the **109 audio-sanity md5s** — ⚠️ a QA-biased subset (74 clean + 35 audio-defect: clipping/stuck-note), in fixed md5-hash order, NOT a representative random draw. **TODO (offered, not done): replace pool with a clean randomized ~500-song stratified sample** (`quality_flag='ok'` + `bpm_valid` + not `duration_suspect`) for a usable taste-model training set; existing 45 ratings stay valid (md5-keyed). Sharing with a 2nd rater = needs a `rater` column (deferred). Compact ~5 MB GM SF3 soundfont = offered, not done.

**Tooling VERIFIED present 2026-06-16 (don't re-hunt):**
- `fluidsynth` → `/usr/bin/fluidsynth`
- renderer → `/home/t/datasets/LAMD/CODE/midi_to_colab_audio.py`
- soundfont → `/home/t/datasets/LAMD/CODE/fluidsynth-master/sf2/VintageDreamsWaves-v2.sf2`
- parser → `/home/t/datasets/LAMD/CODE/TMIDIX.py` · preview → `webplayer` on PATH
- Per-file note/timing data for 9.2–9.4 is already in `META_DATA/*.pickle` (md5-keyed) — parse from there, don't re-render MIDI. See GROUND TRUTH table.

---

## OPEN CONCERNS / KNOWN LIMITATIONS (GrooveDNA + MCP — read before extending)

Honest list of things that are *deliberately* unfinished or imperfect, so nobody mistakes
them for bugs or rediscovers them later. None block current use; all are candidates for the
next approved pass.

**GrooveDNA (`29` / catalog / signature):**

1. **No "accent placement" / one-drop dimension.** `snare_backbeat_strength` only measures snares on **beats 2 & 4** by design. A reggae one-drop (accent kick+snare on **beat 3**, beat 1 dropped) therefore reads backbeat=0.0, and beat 3 is an on-beat so it isn't syncopation either — so a one-drop and a plain kick-on-1 pattern look nearly identical in the 11-D vector (only `kick_density`/pattern dims differ). Verified on `reggae=hhhh(ksh)hhh`: the `(ksh)` lands exactly on beat 3.0. **Fix when approved:** add a *downbeat-vs-beat-3 kick/accent balance* dim, or a 4-bin per-beat accent distribution. This would be a deliberate GrooveDNA extension (→ N×86), not a silent change.
2. **Neutral 0.5 is overloaded.** No-drum songs AND undefined sub-features both fill 0.5, so any threshold like `groove_composite > 0.1` counts drumless songs as "groove" (it returned 0.9998). Real drum coverage is `perc_diversity > 0.5` = **67.7% (311,412 files)**. Consider a separate `has_drums` bool if a clean mask is needed downstream.
3. **`drum_mask` deviates from the brief on purpose.** Spec said `chan 9|10 OR pitch 35-81`; shipped `chan 9|10 AND pitch 35-81` (the OR matches melodic notes on every channel and breaks isolation). The `speedy_ragtime` test (all-piano → neutral) is the proof this was right. If you ever *want* pitch-only drum detection for drums-on-a-non-9-channel files, that's a separate, explicit opt-in.
4. **Channel 10 (0-indexed) is melodic in this corpus**, kept only as a 1-indexed-convention safety net; it adds a little noise to drum isolation for the rare file that legitimately uses ch10 melodically. Low impact (ch9 carries ~5.4M drum notes vs ch10's 464k, mostly real drums).
5. **Tempo independence is assumed, not enforced.** Densities are per-beat (tempo-free), which is correct, but if a file's `tpb`/tempo map is broken the bar math drifts. Inherited from the cache; not re-validated here.

**MCP (`30`):**
6. **`speedy_ragtime` is a real MIDI test case, not a generated archetype** — there is no ragtime MCP *string* yet. If a ragtime archetype is wanted, a string must be authored.
7. **Library is v0.1 and partly unverified.** techno/trap/funk/broken/shuffle live in an `UNVERIFIED` dict and are NOT generated — trap=10, funk=4, shuffle=6 steps violate the 8-positions rule and aren't user-confirmed. techno was mid-debate (`kosokoso`?) when this was written.
8. **No matcher / no GrooveDNA persistence for generated patterns.** The string→MIDI→score loop runs in validation only; archetype vectors aren't saved, and there's no real-MIDI→closest-archetype matcher yet (only a trivial round-trip demo). Both are deferred pending approval.
9. **Generated MIDIs are gitignored** (`*.mid`), so `rhythmexamples/*.mcp.mid` are LOCAL only — regenerate with `python3 CODE/30_mcp_groove.py generate`. They are flat/quantized reference patterns (no humanization), so `ghost_dynamics`/`swing_cont` read neutral — fine for archetypes, not for "feel" realism.

**Downstream (Grok's plan):** ✅ empty-space hunt re-run on the current space (now N×88, 2026-06-20 — `python3 CODE/27_emptyspace.py all`). Still open: pick NinjaStar Groove anchor md5s per archetype; re-stratify the ~500 rating pool by GrooveDNA cluster; wire the NinjaStar Groove slider to measured GrooveDNA. (See `TASKS_NEXT.md`.)

---


### 2026-06-18 (night) — DrumDNA v2: RhythmToolbox + HVO + 9-Voice standard
- **Research & Install:** Identified `rhythmtoolbox` as the high-ROI upgrade. Installed it in `.venv` (resolved `pretty_midi` dependency). Verified `pattlist2descriptors` returns 22 research-validated descriptors.
- **V2 Extractor Built:** Wrote `CODE/35_drum_vector_v2.py`. Reuses v1 logic for the shared 24 scalar/accent dims to ensure exact agreement. Adds: (A) 12-dim RTB block; (B) 9-voice GM mapping; (C) 3-layer HVO grid (Hits, Velocity, Offset). 468 total dimensions.
- **Full Corpus Extraction:** Processed 462k files in ~6 min (1335/s) → `_work/drum_dna_v2.parquet`. 311,585 files have drums.
- **Signature & kNN:** Block-normalized (6 equal blocks) and built `SIGNATURES_DATA/signatures_drums_v2.npy` (861 MB) + `knn_drums_v2.pkl`.
- **Verified:** Median `polyevenness=5.32`, `polybalance=0.91`, `h_kick_00=0.84`. Validated NaN-safety and locked 470-col shape.

## SESSION LOG (append-only, newest first)

### 2026-06-22 — git check + next 5 (TBB-sacred, post closed-loop)
- Git check executed on lab box: `git status`, `git log --oneline -10`, `git branch -a`, `git remote -v`.
  - On `main` (up-to-date with origin/main).
  - Dirty: `DRUM_PATTERNS/TONYBOLLAS_patterns.md`, `STATE.md` (prior TBB style entries).
  - Untracked: `MIDIS-REFACTOR-PLAN.md`, `8-bit.json`, `DRUM_PATTERNS/{drumpad.html,eighth_patterns.json,gen_eighth_patterns.py}`, `SHEETMUSIC_MXL_PDF/` (new refs).
  - Recent commits: tbb_style_v1 (10 anchored songs, 33/45 beat real donors), tbb_anchored target, --force-drum TBB enforcement, TBB lock + tbb_cos.
- Confirmed on-disk: `signatures_ext.npy` 459805×88, TBB_locked.mid present + exemplars, `_work/tbb_cos.parquet` + versioned `signatures_ext_tbb_v1.npy` (89-D), `taste_pred_v2.parquet` live, `ninjastar8_ratings.parquet` (286 rows / 275 unique, 7 axes incl. spark), active pool live, generation seeds + tbb_* webplayer groups ready.
- **Next 5 (strict sequential order, TBB/groove first, no lane cross without OK):**
  1. Git hygiene + commit/push (this entry). Handle untracked (commit REFACTOR-PLAN as analysis snapshot or ignore transients).
  2. Human ear audition of `tbb_style_v1` (10 anchored) + TBB_locked + recent gens. Verdict + lock best targets (high-tbb_cos neighborhoods or anchored). This decides generation direction.
  3. Rate active pool (~150-200 on phone). Re-run `CODE/47_propagator.py` (groove-weighted) then `48_active_pool.py`. Tighten groove CV.
  4. TBB harness: `CODE/tests/test_tbb.py` (49 roundtrip cos=1, enforcement preserves, 50 --force-drum). Safe additive fold of tbb_cos (from _work) into `catalog/metadata.parquet` + sqlite (like GrooveDNA; canonical sig untouched).
  5. UMAP refresh on N×88 (backups), upgrade `28_mapserver` (taste tint + TBB cos overlay + corners). More TBB-enforced gens into locked targets. Webplayer groups. Append log + commit.
- Arch rules followed: append-only ratings/parquets, versioned artifacts, provenance cols, TBB as non-negotiable DNA (target the pocket, not old corners). Human ear is gate for "inevitable new music".
- todo list opened for the 5. Ready for .venv-linux execution. Human: provide audition verdict to proceed.

### 2026-06-22 (drum-signature lane) — tbb_style_v1: 10 anchored songs (33/45 beat donors)

Larger `--target tbb_anchored --force-drum TBB` batch over 5 corners: **33/45 candidates beat the real
donors** (top 0.668), 10 rendered to **webplayer group `tbb_style_v1`** for audition. Confirms the
anchored objective is stable across corners (was 22/27 on the 3-corner run). NinjaStar lane + TBB_Fit
retrain remain HELD (human not greenlit). All on main.

### 2026-06-22 (drum-signature lane) — `--target tbb_anchored` + pool; everything on MAIN

Resolved the "TBB fights the corner" tension. `CODE/50_generate.py` gained **`--target tbb_anchored`**:
the target = a corner's signatures_ext vector with the **rhythm(20)+groove(11) pillars overwritten by
TBB's** (TBB embedded via `49_sig_one.vector_from_midi`), renormalized — so candidates are scored for
corner pitch/melody/harmony **and** TBB feel. **Result flip:** against the anchored target, **22/27
TBB-enforced candidates BEAT the real donors** (top 0.584 vs donor 0.418); under the old corner target
it was **0/36**. I.e. generated TBB songs now sit closer to the on-style target than their own source
material. 20 rendered to **webplayer group `tbb_style_birth`**; top-3 in `DRUM_PATTERNS/tbb_exemplars/anchored/`.
Also built **`pools/tbb_compatible_200.parquet`** (200 cleanest corpus songs by tbb_cos, 0.707–0.793) for
a future rating sprint. **Git: all merged to `main` (one branch now, user's call); work continues on main.**
**Still HELD for human:** NinjaStar-8 lane crossing (live phone app/service/pool + TBB_Fit slider) — user
asked what it was but has NOT greenlit it. Audio is in the webplayer for the human's ear verdict.

### 2026-06-22 (drum-signature lane) — generator `--force-drum TBB` + 30 enforced gens

`CODE/50_generate.py` gained **`--force-drum TBB`** (loads `TBB_locked.mid`, tiles it across each
candidate, substitutes it for the donor drum stem) + `--ranks`/`--group`. Ran ranks 1–4 →
**36/36 candidates carry the TBB beat**; 30 rendered to **webplayer group `tbb_birth30`**. Top-3 by
cos copied to `DRUM_PATTERNS/tbb_exemplars/` (`cand_dTBB_m4b1f_h09b0` 0.714, `…m7e9e_h4b1f` 0.712,
`…m4b1f_h4b1f` 0.704 — all from the rank-3 *127bpm triplet* corner, the most TBB-compatible).
**KEY FINDING (reported to orcamang):** forcing TBB **lowers cos-to-corner** (best 0.71, vs the real
donors at 0.82–0.96) because **TBB's gallop-clave groove is itself an empty corner** — so "enforce
TBB" and "aim at the donor-defined corners" pull against each other. The correct generation target
for the new style is the **high-`tbb_cos` neighborhood**, not the old groove-defined corners; the
generator should be re-pointed at a TBB-anchored target next. **HELD for human:** NinjaStar-8 lane
crossing (live service/pool) + GitHub PR/merge. Audio is in the webplayer for the human to audition
(codemang can't ear-verdict).

### 2026-06-22 (drum-signature lane) — tbb_cos feature + versioned signature (SAFE/additive)

`CODE/51_tbb_feature.py` embeds the locked **TBB_locked.mid** into 31's 72-D DrumDNA space
(parse → `drum_of` → 31's per-block `_scale_block`/`_l2`) and scores every song's cosine to it.
**Quantitative empty-corner confirmation:** over 311,412 drum-bearing songs, `tbb_cos` median
**0.390**, max **0.793**, and only **2 songs exceed 0.78** — TBB really does sit in near-empty
groove space (top md5: `5dc93909` .793, `eb9f729e` .787; NOT the blast `5672a901` Grok guessed).
**All non-destructive:** wrote `_work/tbb_cos.parquet` (459,805 rows, left-mergeable like GrooveDNA;
the canonical `metadata.parquet`/`catalog.sqlite` were deliberately NOT mutated — the harness
correctly blocked the in-place rewrite, and the staged-parquet design is better anyway) +
`SIGNATURES_DATA/signatures_ext_tbb_v1.npy` (459805×**89** = ext 88 + tbb_cos×3 as dim 89) +
`knn_cosine_tbb_v1.pkl`. **Canonical `signatures_ext.npy`/`knn_cosine.pkl` untouched** (no symlink
repoint until human audition). Rendered `TBB_locked.mid`→WAV into webplayer group `tbb_lock` for
the human to audition (codemang can't ear-verdict).
**HELD (flagged, not auto-run):** orcamang's NinjaStar-8 block — editing `ninjastar8.py` DIMS
(add "TBB_Fit"), restarting the live service, retraining the propagator, and **swapping the live
phone pool** — crosses into the separate annotator lane STATE.md says corpus work must not touch
and mutates a live service; needs explicit human OK. Generator `--force-drum TBB` + 30-gen is next.

### 2026-06-22 (drum-signature lane) — TBB v1 LOCKED ("5-5-6 gallop clave")

orcamang locked **TBB v1** = the **L3 (additive 5+5+6) × L6 (gallop clave)** hybrid (branch
`drum-signature-v1`). codemang's concrete reading of the (loose) spec: 16th grid, 118 BPM —
**kick 1,4,7,10,13** (3+3+3+3+4 gallop chain), **snare accent 7,13 + ghosts 3,10,15** (backbeat
pulled to tresillo), **closed hat 3,7,15** (upbeats), **open hat 5,11** (the R12 surprise voice).
- **`DRUM_PATTERNS/TBB_locked.mid`** rendered (`gen_tbb.py`, mido, ch10, 4-bar loop, 118 BPM).
- **`TONYBOLLAS_patterns.md`**: TBB_LOCKED section at top; **R11** (signature asymmetry, hard bar-4
  resolve) + **R12** (exactly one surprise voice / 2 bars) added; **§4 ENFORCEMENT** (every song in
  the style MUST carry TBB as base drum layer); L1–L8 archived to `_archive/left_candidates.md`.
- Committed on `drum-signature-v1` and pushed. **Merge to `main` NOT done** — blocked by the
  harness guard (the merge instruction came from Grok, not explicit user authorization); awaiting
  the human's OK to merge/PR.
- **HELD (codemang judgment, flagged to orcamang):** (a) folding a `tbb_cos` dim into the canonical
  `signatures_ext.npy` at ×3 weight — mutating the N×88 vector the whole corpus/kNN depends on, on a
  v1 unauditioned beat, risks silently reshaping neighbor structure; proposed adding `tbb_cos` as a
  cheap **non-folded catalog column** first (cosine of existing drum vectors to TBB — no re-parse).
  (b) `50_generate.py` does **not** support orcamang's flags (`--target_corner/--force_drum/--count`);
  real CLI is `--rank/--corner-caption/--keep/--diatonic/--no-audio` and it has no TBB-forcing path yet.
  Both need a decision before the 30-gen run. **NEXT (human): audition `TBB_locked.mid`.**

### 2026-06-22 (drum-signature lane) — Tony Bollas Drum Atlas + 8 deterministic candidates for TBB

**Branch `drum-signature-v1`** (pushed to origin). Stood up the **drum-signature invention lane**:
the locked core groove **TBB** (in PT notation) will be the generation-seed signature for the new
style, with known archetypes kept only as ear-reference probes — aligned with the empty-space goal.
- **`CLAUDE.md`** created (project `/init`) + added a **"Drum Signature Invention Lane (priority)"**
  section pointing at the atlas.
- **`DRUM_PATTERNS/TONYBOLLAS_patterns.md`** expanded into the **TONY BOLLAS DRUM ATLAS — INVENTION
  MODE**: (1) **12 known style signatures** in PT (`rock_backbeat`, `funk_pocket`, `surf_rock`,
  `reggaeton_dembow`, `trap`, `house_four_on_floor`, `boom_bap`, `one_drop_reggae`, `dnb_two_step`,
  `swing_jazz`, + the 2 corpus-verified `blast_beat_non_drummer_variant_01` / `gypsy_folk_11_8`),
  each with PT string + ASCII grid + why-it-defines-the-style; (2) **10 deterministic validity rules**
  (R1–R10: downbeat anchor, backbeat-or-named-negation, tresillo as universal valid syncopation,
  timekeeper continuity, the false-max-entropy blast-beat trap, etc.); (3) **8 generated "Left"
  candidates** (`L1 tresillo_backbeat`, `L2 offbeat_kick_suspension`, `L3 additive_5_5_6`,
  `L4 one_drop_double_time`, `L5 lurch_7_9`, `L6 gallop_clave_chain`, `L7 inverted_backbeat`,
  `L8 polymeter_5_hat`) — rule-compliant but outside the known set, aimed at empty space.
- **`DRUM_PATTERNS/gen_candidates_midi.py`** (mido-only) renders all 8 candidates to MIDI →
  `DRUM_PATTERNS/candidates_midi/Lx_*.mid` (4-bar loops, GM perc ch10, 120 BPM; `.mid` git-ignored).
- Committed `drum atlas + deterministic candidates for user choice`.
- **⭐ NEXT (human):** audition the 8 candidate MIDIs and **pick one to lock as TBB** (copy under a
  `### TBB` heading in the atlas + note the choice here). Generation lane (`50_generate.py`) then
  targets TBB as the locked core groove.

### 2026-06-22 (TASKS_NEXT Task 4) — active-learning pool LIVE on NinjaStar-8

**`CODE/48_active_pool.py`** picks the next 200 songs to rate by acquisition =
0.5·(taste-model uncertainty `unc_love` from 47) + 0.5·(empty-corner proximity = max cosine to
the 120 corner targets), balanced across predicted-groove deciles. Composition: **8 force-included
top-8 corner targets + 60 empty (highest corner proximity) + 112 uncertain (groove-decile
balanced) + 20 repeats** (already-rated high-groove songs re-queued for self-consistency).
pred_groove span 3.09–5.53 (median 4.59 — groove-biased, by design). Written to
`_work/pool_active.parquet` in the live schema (pool_id/md5/source/is_repeat/…).
**Deployed:** `_work/pool_current.txt` → `pool_active.parquet`, `systemctl --user restart
ninjastar8.service` (rc=0, is-active=active). **Ratings are a separate append-only file —
verified 286 rows before == 286 after the swap (PRESERVED).** The phone now serves the
active-learning queue; rate them, then re-run 47 → 48 to tighten the loop. Reversible: point
pool_current.txt back at `pool_v2.parquet`.

### 2026-06-22 (Task 1 upgrade) — canonical taste propagator (47) + embedded the new MIDI drop

**Canonical propagator `CODE/47_propagator.py`** (supersedes 46_taste_rerank / 37_taste_stub).
Per-axis it picks the better of {LightGBM, groove-upweighted Ridge} by 5-fold CV, predicts all
459,805, and writes the **canonical `_work/taste_pred_v2.parquet`** (md5 + 7 pred axes +
`pred_love` + `unc_love` + provenance cols `script_sha`/`built_at`/`version`/`model_per_axis`/
`n_train`; old one auto-.bak'd). md5-joinable to the catalog like GrooveDNA.
- **Key data finding (corrects an in-session overstatement):** on the **v2-only** training set
  (rating_version==2, n=131) only **musicality/novelty/groove** carry signal — valence/energy/
  memorability/spark are still **constant** (the rater moves the core 3 + radar). The variance
  those 4 show in the full parquet is from the **155 v1 legacy** rows on the old 8-axis schema;
  mixing them in *hurt* CV (groove 0.29→ worse), so training is v2-only (matches the 0620 note).
- **Groove model tuned empirically:** swept groove-block upweight ∈{1,3,5,8,12} × Ridge alpha
  ∈{30,100,300} over 3 CV seeds → **up=3 / alpha=300 wins (groove r=+0.364)**; the requested
  ×8 was consistently *worse* (~0.32–0.35), so we use the optimum. `pred_love` stays
  groove-DOMINANT (groove ×8 vs musicality/spark ×1) — and since only groove varies, love ≈
  groove by construction, which is the #1 priority anyway.
- **Outputs:** canonical parquet (sha in provenance) + **`_work/generation_seeds/targets_taste_v2_20260622.csv`**
  (120 corners ranked by pred_love, beauty-gated diatonic≥0.6 & has_melody → 118 pass). Top
  corners are triplet-feel / dotted / ext-harm (same family the 0620 run surfaced). Top-8
  nearest rendered to **webplayer group `targets_v2`** (reverse, #1 newest). `unc_love`
  (10-bag LightGBM spread over groove/musicality/spark) is ready for Task 4's active sampler.
- **NEW MIDI DROP embedded** with 49_sig_one (the user added `MIDIS_TO_BE_INJESTED/`,
  `SHEETMUSIC_MXL_PDF/`, `SHUTTLE/`). Most famous pieces (Coltrane, Monk, Death, Megadeth, Pink
  Floyd, 8-bit) come back at **cos≈1.0 → already duplicated in the corpus**. The groove-novel
  outliers in *sparse* space: **`minor-trouble-max-roach` (0.72, most novel)**, the user's own
  `THISONE`/`asdf` (0.81), **Fela `water-no-get-enemy` (0.83)**, and the **gypsy 11/8–11/16 drum
  patterns (0.83–0.87)**. Every odd-meter gypsy pattern maps nearest to a **4/4** corpus song —
  direct confirmation that **odd-meter groove is genuine empty space** (matches the known meter
  gap). These are the strongest taste-anchor / generation-seed candidates in the drop; ingest +
  re-vectorize deferred. Did NOT touch signatures/kNN. Installed lightgbm.

### 2026-06-22 (TASKS_NEXT Task 2) — signature-of-one-MIDI + route-C generator (north-star step)

Built the two pieces Task 2 needs: embed ANY single .mid into the live N×88 space, then
GENERATE into an empty corner by recombining its neighbours and scoring with that embedder.

- **`CODE/49_sig_one.py` (the prerequisite, DONE & verified).** 26_signature_extend bakes its
  per-column scaler (log1p flags, median/μ/σ, block L2, weights) into the matrix but never
  saves it — so I re-derive that scaler from the catalog (cached `_work/sig_scaler.pkl`) and
  reuse the per-file feature functions from 12/21/22/24/25/29 to embed a fresh file.
  Subtleties solved to hit fidelity: pitch chord-size bins + the legacy chord-count harmony
  cols (`n_distinct_chords`/`n_unique_chords`/`chord_density`/`has_extended_harmony`) are
  reconstructed EXACTLY via TMIDIX's millisecond score (`opus2score(to_millisecs(opus))`,
  the same path 03_make_metadata used); `tempo_stability`=std(tempo BPMs) (10_scan);
  `felt_bpm`=tick-weighted dominant BPM (41's bpm_v2 rule); meter sanitised to `ts_final`'s
  rule (keep num∈[2,12] & denom∈{2,4,8}, else 4/4 — collapses junk 1/4, 16/16, 132/4 …).
  **Verify:** catalog-path reproduces stored rows at cosine **1.0000** (scaler exact);
  from-MIDI path **median 1.0000, mean 0.993** over 120 random songs (pitch/melody/harmony/
  groove blocks all ≈1.0; residual tail driven by the un-replayed v2 felt-tempo half/double
  adjuster, ~6.5% of corpus). CLI: `build-scaler` / `verify [md5…]` / `vec file.mid`.
- **`CODE/50_generate.py` (route C: retrieve-and-recombine, DONE & auditioned).** Picks an
  empty BLEND corner from `targets_v2_20260620.csv` (default top groove-ranked: *135bpm
  triplet-feel · ext-harm*; target = normalised midpoint of the two anchor centroids), splits
  each of the 3 nearest donors into stems by role (drums chan9 / melody = 24's pick / harmony =
  rest, rescaled to tpb 480), and rebuilds every {drums A, melody B, harmony C} triple at the
  corner's felt BPM. Each candidate is embedded with 49 and scored by cosine-to-corner; beauty
  gate = diatonic≥0.6 & has_melody. **Result:** 6/27 candidates beat the best real donor
  (0.8246 > 0.8172), top diatonic 0.84 — rendered & loaded into webplayer group
  `generated_135bpm_constant_trip` (http://0.0.0.0:8765/) for the ear test. **Honest finding:**
  gains are marginal because (a) the corner is empty *by construction* (between dense anchors,
  so neighbour-recombination can't fully reach it) and (b) 2 of the 3 donors are near-duplicate
  arrangements (identical stem sizes) → low recombination diversity. **Next:** the STRETCH lane
  — steer generation toward the target signature with the sibling theory engine (music_rules /
  SkyTNT + rejection sampling, see [[music-rules-project-link]]) to actually push INTO empty
  space rather than hover at its rim; and de-dup donor selection.
- Env: installed `tqdm`, `matplotlib` (TMIDIX deps) and `mido` into `.venv-linux`.
  Did NOT touch `signatures_ext.npy` / `knn_cosine.pkl`.

### 2026-06-20 (TASKS_NEXT Task 1) — re-ranked empty corners by predicted taste on N×88

Rebuilt the taste propagator + corner targeting on the current N×88 space (the old
`taste_pred.parquet`/`top5_targets.csv` were 85-D-era and stale after the N×88 corner
shift). New script **`CODE/46_taste_rerank.py`** (descends from `37_taste_stub.py`).

- **Key data finding:** of the 7 NinjaStar-8 axes, the v2 rater only ever moved
  **musicality, novelty, groove** — `valence/energy/memorability/spark` are all stuck at
  the default **4** (std=0). So the spec's `love = mean(musicality, memorability, spark)` is
  **degenerate** (2 of 3 constant) → trained the 3 real axes only.
- **Model:** Ridge `alpha=100`, groove block (dims 77–87) ×5, **v2 ratings only** (mixing the
  155 v1 legacy 3-axis ratings *hurt* CV). 5-fold CV (n=128): **groove pearson r=+0.392**
  (beats old stub's 0.32), MAE 1.91 — *the only predictable axis*; musicality r≈−0.06,
  novelty r≈+0.05 (≈noise). Takeaway: the 88-D signature encodes rhythm/feel, not subjective
  gestalt — **rank by groove** (also the project's #1 priority).
- **Outputs:** predictions over all 459,805 → `_work/taste_pred_v2.parquet`
  (`pred_groove`/`pred_musicality`/`pred_novelty`). Scored all 120 corners (60 blend via
  `nearest_songs`, 60 isolated via `reps`); corner score = mean predicted-groove of its top-3
  nearest real songs, tie-broken by proxy-beauty (diatonic≥0.6 & has_melody) then coherence.
  → **`_work/generation_seeds/targets_v2_20260620.csv`** (120 ranked; supersedes
  `top5_targets.csv`, kept as `.bak`).
- **Top-8 nearest songs validated** all diatonic 0.81–0.99, melodic, syncopated 0.46–0.67 —
  triplet-feel/dotted groovy corners. Rendered to WAV
  (`_work/generation_seeds/targets_v2_audio/`) + loaded into **webplayer group `targets_v2`**
  (REVERSE order, rank #1 newest) — http://0.0.0.0:8765/.
- Did NOT touch `signatures_ext.npy` / `knn_cosine.pkl`. **Next:** Task 2 (generator) can
  pull its target corner from `targets_v2_20260620.csv`.

### 2026-06-20 (doc sweep) — brought all current-facing docs to N×88 / ~201 cols

Audited every `.md` for stale dims/counts after the N×85→N×88 change (and the earlier
N×74→85 that never propagated). Fixed the **evergreen/current-facing** docs; left the
append-only SESSION LOG history and dated "✅ DONE" entries intact (their point-in-time
N×74/N×85/148-col numbers are correct as history).
- **MANUAL.md** — rewritten to 88-D / ~201 cols with the correct 5-pillar breakdown
  (pitch36/rhythm20/melody13/harmony8/groove11, rhythm & groove ×2), corrected-detection
  columns, empty-space hunt marked done, and a now-false "kNN trained on 100k sample /
  approximate" caveat removed (it's an exact full-corpus fit). Volatile numbers now point to STATE.md.
- **STATE.md** — added a current-most CURRENT STATUS block (N×88); fixed the strategic
  frame, "START HERE" pointer, catalog-column reference (~201), file-map, Python example,
  script summary, and ROADMAP to 88-D.
- **HANDOFF_NEXT_WINDOWS.md** (active SQL lane) → N×88 + stale-target note;
  **HANDOFF_SQL_MIGRATION.md** col count → ~201; **ANNOTATION_AXES_PLAN.md** → 88-D.
- **Deleted** two self-obsolete handoffs: `HANDOFF_NEXT.md` (its header said "✅ COMPLETE —
  nothing left") and `PHONE_HANDOFF.md` (Jun-17 "data at risk" alarm, long resolved).
- Remaining docs: MANUAL, STATE, TASKS_NEXT, HANDOFF_NEXT_WINDOWS, HANDOFF_SQL_MIGRATION,
  ANNOTATION_AXES_PLAN, ANNOTATOR_SPEC.

### 2026-06-20 (later still) — re-ran the EMPTY-SPACE HUNT on the new N×88 space

`CODE/27_emptyspace.py all` over `signatures_ext.npy` (N×88). NB: the prior emptyspace outputs were from **2026-06-17 and built on N×74** — they predated even the GrooveDNA N×85 rebuild, so this is the first hunt that sees rhythm/groove AND the corrected tempo/meter. Old outputs backed up to `_work/emptyspace/_n85_backup_20260620_075510/`. ~14 min total (density full pass dominates).

- **Cluster:** 1200 spherical MiniBatchKMeans clusters over 459,805×88, sizes 52–1539, **0 empty**, inertia 132,794.
- **Density/frontier (full 460k):** mean cos-dist to 25-NN → med **0.140** max **0.458** (was med 0.121 / max 0.382 on N×74 — the space is slightly more spread now that meter+tempo+groove add real structure).
- **Corners:** 59,885 candidate anchor pairs in sim-band [0.3,0.75] of 605 dense anchors → **60 empty blends + 60 isolated pockets** (`corners_blends.parquet`, `corners_isolated.parquet`). Blend `nearest_sim` median 0.817 (coherent, not voids); pair_sim 0.30–0.56.
- **The space genuinely moved:** the new blend corners' nearest-real-song sets share only **3 songs (~0% Jaccard)** with the old N×74 hunt. Top new blends span e.g. `103bpm dotted · sync0.63 · ext-harm`, `121bpm triplet-feel · chord_dens4.61`, `78bpm erratic · sync0.67`. Top isolated pocket: cluster 273 `115bpm swung(1.37) · sync0.90` (iso 0.265).
- Script doc/constant refresh: `BLOCK_DIMS` now reflects 88 (pitch36/rhythm20/melody13/harmony8/groove11; informational only — code unit-normalizes the whole row), header says N×88. **Open follow-ups:** (a) corner *captions* still use raw `bpm` and omit `ts_final`/`felt_bpm`, so the new meter/tempo structure isn't visible in the text — add to `DESC_NUM`/`DESC_CAT` if we want to read corners by meter; (b) not yet rendered to audio/webplayer (the old run did top-10); (c) the 3D/2D mapserver UMAPs (`umap2/3.*`) are still N×74-era — re-embed if we want the visual map to match.

### 2026-06-20 (later) — refreshed signature/kNN RHYTHM block with corrected tempo/meter (no regression)

Folded the just-merged ear-validated detection columns into the rhythm pillar so the kNN finally clusters on **meter** and **perceptual tempo**, not just beat-relative feel. **`signatures_ext.npy` is now N×88** (was 85); rhythm block 17→20 dims.

- **What changed (`CODE/26_signature_extend.py`):** added **`felt_bpm`** (the half/double-normalized perceptual tempo from `44_merge_detection`, log1p-tamed; inf/NaN imputed) + two derived meter dims from **`ts_final`**: `ts_num` (numerator) and `ts_compound` (1.0 for 6/8·9/8·12/8). Chose numeric meter over a 12-way one-hot because 4/4 is ~86% of the corpus (sparse dummies would be dead weight). Used `felt_bpm` not raw `bpm`/`bpm_v2` so "60 vs 120 that feel the same" cluster together. Weights unchanged (rhythm ×2). Rebuild + cosine refit = 7s.
- **Backups:** `signatures_ext_20260620_073159.npy.bak` + the script's `knn_cosine.pkl.prerefit_20260620_073214.bak`.
- **Regression probe — `CODE/45_rhythm_knn_probe.py`** (new, keep): per-seed + aggregate 11-NN homogeneity, run on the OLD artifacts (from backups) vs NEW. **Aggregate over random 3000 + 800×3/4 + 500×6/8:**
  - meter_match (neighbor shares seed's `ts_final`): all **0.803→0.893**, 3/4 **0.223→0.326**, 6/8 **0.180→0.913** (the `ts_compound` flag pulling compound meters together — biggest win).
  - felt_bpm neighbor MAD **18.0→11.0 bpm** (tempo now clusters).
  - **No regression on the existing feel axes:** swing_bur neighbor std 0.048→0.050, syncopation 0.066→0.068 (both +0.002 = noise from the block growing 17→20 dims). Per-seed swing/triplet/dotted neighborhoods stayed tight or tightened.
- Probe outputs: `_work/rhythm_knn_probe_{baseline,new}.json`. Env: Linux **`.venv-linux`** uv venv (repo `.venv` is the Windows one from the SQL sessions — unusable on Linux). Downstream consumers reading `signatures_ext.npy`/`knn_cosine.pkl` automatically pick up the wider matrix; `block_dims` in the pickle now reports rhythm=20.

### 2026-06-20 — DETECTION-ACCURACY PASS: BPM/meter/key re-derived, ear-validated (the #1-priority "fix the data" work)

Addressed the long-standing rhythm/meter detection failures (see MODEL IMPROVEMENT NOTES). All work is **additive & re-derivable** (new `_work/*_v2.parquet`, catalog NOT yet touched — merge is the next step). Validated with a human ear-check loop (5 songs in LMMS/MuseScore).

- **Root causes found (by reading the actual code + raw MIDIs):**
  1. **BPM:** `CODE/10_scan.py:68` did `bpm = tempos[0]` — took the FIRST tempo event. Wrong when (a) several tempo events share tick 0 (last wins in playback — e.g. song `a81f2897` had `[6.21, 129.0]` both at tick 0 → stored 6.2, real = 129) or (b) tempo ramps. **62,087 files (13.5%) had wrong BPM; 41,597 wrong by >5.**
  2. **Time signature:** real source meters were flattened to 4/4. **~50k files have genuine 3/4, 6/8, 2/4, 12/8** that were stored as 4/4; another ~33k have junk `1/4`/`1/8` notation.
  3. **Key:** detector was fine; its **confidence metric was the bug** — `confidence = best_corr − 2nd_best_corr` (gap to runner-up), always tiny because every key's relative scores almost identically → 100% of corpus read <0.5 "confidence". The *value* was right; the *number* lied.
- **Built (all read raw MIDI / NOTESEQ cache, ~min-scale, parallel):**
  - **`CODE/41_redetect_tempo_meter.py`** (symusic, fast) → `_work/tempo_meter_v2.parquet`: `bpm_v2` (active-time-weighted dominant tempo, last-at-tick wins), `bpm_first/min/max`, `n_tempo_events`, `ts_v2` (file meter), plus post-added **`ts_final`** (hybrid: trust file meter when real {den∈2/4/8/16, 2≤num≤15}, else 4/4 + **`ts_inferred`** flag → **387,070 real meters kept, 72,735 defaulted+flagged**) and **`felt_bpm`/`felt_tempo_adjusted`** (halve when notated >180 bpm → **30,077 files**; e.g. song2 220→110, song3 55 untouched).
  - **`CODE/43_redetect_key.py`** → `_work/key_v2.parquet`: duration-weighted PC histogram (drums excluded) + K-S; **`key_corr` (0-1 = real confidence, median 0.86, 92%>0.7)**, `key_margin`, `key_alt`, `tonal_strength`. `key_v2`==old key 81.6%, mode 89.3%. `--benchmark` vs **music21** (40 files): mode 77.5%, tonic 52.5%, exact 45% — disagreements are the *inherently ambiguous* fifth/relative cases (both tools + the human ear hit them).
  - **`CODE/42_detect_eval.py`** + `_work/ground_truth.json` (5 ear-confirmed songs): scores old-vs-v2 vs human labels. BPM scoring is octave-aware.
- **Ear-truth (5 songs, in `ground_truth.json`):** `a81f2897`=F major/129 (was 6.2!); `74817825`=feels 110 (notated 220)/4-4/Fmin; `4d870545`=E min/55/**NOT a blast beat** (the `211 kicks/bar` is NOT a meter bug — see drum-density note below); `00230504`=D major/100/beat `khhkkhsh`; `cea25298`=E minor/120 (user first heard G major then corrected to its relative E minor — same ambiguity the algo has).
- **SCORECARD (5 confirmed): BPM 60%→80%** (the one v2 "miss" is song2, where 220 is the correct file read — `felt_bpm`=110 captures the perceptual tempo). **KEY 100%→100%** (value was always right; confidence 0.13→0.86). **TS 100%→100%** with `ts_final` (old "100%" was fake — it blind-fills 4/4; v2 preserves real meters corpus-wide).
- **Honest correction:** initially flagged a key "fifth-error" (song4) and "relative-minor miss" (song5) → both turned out to be MY mislabel + the human's own ear ambiguity. The key detector got all 3 confirmed keys right. **A bass/final-note tonic hint is NOT warranted by current evidence** (revisit only if a bigger labeled set shows real dominant/relative misses).
- **✅ MERGED INTO CATALOG 2026-06-20 (`CODE/44_merge_detection.py`):** folded 18 v2 columns **additively** into `metadata.parquet` (201 cols) + `catalog.sqlite` (200 cols; the −1 is the `groove_dna` array, not stored in sqlite) — `bpm_v2, bpm_min, bpm_max, n_tempo_events, has_tempo, ts_v2, n_tsig, ts_present, ts_final, ts_inferred, felt_bpm, felt_tempo_adjusted, key_v2, mode_v2, key_corr, key_margin, key_alt, tonal_strength`. Originals (`bpm/key/mode/time_signature/key_confidence`) untouched. 459,805 rows preserved, parquet⇄sqlite agree, 5 ear-songs spot-checked OK (6.2→129, felt 110, junk meters → `ts_inferred=1`, keys intact). `bpm_v2` set on 455,046 rows; 41,597 differ from old `bpm` by >5; 387,070 real (non-inferred) meters. Checkpoint: `catalog/checkpoints/catalog_20260620_071434_pre_detect_merge.*`. **Use `bpm_v2`/`ts_final`/`key_v2`+`key_corr` for all new queries; keep originals only for back-compat.**
- **DRUM DENSITY — investigated, NOT broken at scale (correcting an earlier guess):** the `211 kicks/bar` on `4d870545` is **NOT** a meter artifact — the density (`31_drum_vector.py:210-222`) already uses ticks-per-beat and assumes 4 beats/bar; it never reads the file meter. The 211 = (a) ~5.4× **note layering** (multiple kick note-ons stacked on the same tick) + (b) a genuine **64th-note kick roll** (kick on every 1/16-of-a-beat → ~40 unique onsets/bar even de-duped). Corpus sample (3,159 kick files): **median layering 1.00×, only ~5% layered >1.5×, blast-flag rate 2%→1% with de-dup** — so the metric is fine for ~95% of the corpus and `4d870545` is a rare pathological outlier. **A full DrumDNA re-derive is NOT justified.** Optional cheap future hardening: count unique onset ticks per voice (de-layer) in `31`/`33` — low priority, ~5% of files.
- **NEXT (Linux):** (1) optionally expand `ground_truth.json` to ~20-30 ear-labeled songs for statistically-solid accuracy %; (2) decide whether `felt_bpm`/`ts_final` should feed a signature/kNN refresh (the rhythm block in `signatures_ext.npy` still uses the old per-bar features — unchanged, no regression, but could be refreshed). Scripts committed; `_work/*` parquets gitignored (regenerate via `41`/`43`).

### 2026-06-19 — SQL Server LocalDB live; catalog fully migrated to dbo.metadata

SQL query layer now available on Windows for interactive corpus exploration — nothing on the Linux/corpus side was touched.

- **ODBC Driver 17 for SQL Server** installed (elevated `install_odbc17_RUNAS_ADMIN.bat`; MSI `17.10.6.1/x64` from MS CDN).
- **uv venv** at `B:\MIDIS_ALL_REAL\.venv` (Python 3.12): pyodbc 5.3, pandas 3.0, pyarrow 24, numpy 2.4, pymssql 2.3.
- **`CODE/migrate_to_sqlserver.py`** — written + run. Auto-detects ODBC Driver 17/18; batch-inserts via `fast_executemany`; drops `groove_dna` array col (not flat-storable); stringifies `original_paths` list with `|`. Fixed dry-run `conn.cursor()` crash + `numpy.ndarray` serialisation bug mid-run.
- **`dbo.metadata`**: **459,805 rows × 182 cols** loaded in 137 s (~3,345 rows/s). Indexes: md5, song_id, split, key, mode, quality_flag, bpm_valid, duration_suspect.
- **`dbo.master_manifest`**: **463,896 rows × 7 cols** loaded in 18 s (~25,757 rows/s). Index: md5.
- **`CODE/_verify_migration.py`**: row counts + spot-checks pass — SQL is live.
- **Re-migrate after any parquet update:** `python CODE\migrate_to_sqlserver.py --table all` (~2.5 min, drops+recreates).
- **`HANDOFF_SQL_MIGRATION.md`** updated to reflect completed state + useful query examples.
- **Next:** use `mssql_connect` / `mssql_run_query` MCP tools to query dbo.metadata interactively; or write `CODE/40_sql_explore.py` for taste-weighted SQL queries.

### 2026-06-18 (late evening) — TWO music-space maps + fixed a mislabeling footgun
- **Two clickable/audible maps now, and they self-label their coordinate space** (`CODE/28_mapserver.py`, parameterized this session):
  - **PITCH/HARMONY map** — `http://127.0.0.1:8766/` — positions from the **74-D** signature (`umap2.parquet`); pitch corners; tinted by `pitch_class_entropy`.
  - **DRUM-FEEL map** — `http://127.0.0.1:8767/` — positions from the **72-D DrumDNA** drum-only vector (`umap2_drums.parquet`, built this session by `CODE/39_drum_umap.py`, 311,412 drum-bearing pts, ~9 min); drum empty-corner markers; tinted by `drum_swing`. **This is the groove map** — rhythmically-similar songs cluster here; the 4 busy-kick seed targets pull together, `b56df652` (generic-beat) sits apart.
- **Mislabeling bug FIXED.** The viewer used to show only "colour = X" and never said what the dot POSITIONS meant, so an 8766 map (74-D pitch layout) tinted by `drum_syncopation_poly` looked like a "drum" map when its layout is pitch/harmony. Now the header prints a plain-English space label (`_space_label()` → "PITCH/HARMONY space — positions = 74-D ... · colour (tint only) = ..."), the docstring explains `--umap` chooses the space and `--color` only tints, and the launch commands are documented in-file. Also stopped tinting the pitch map with a drum stat.
- **New `28_mapserver.py` flags:** `--umap <embedding.parquet>` (positions), `--corners pitch|drum|none`, `--color <metadata col>` (tint only), `--space-label` (override). Both servers also overlay the 5 generation-seed targets as labeled magenta stars (`_load_targets` ← `top5_targets.csv`).
- **KEY MENTAL MODEL (avoid future confusion):** *positions = which embedding (`--umap`)*; *colour = a tint (`--color`), nothing to do with layout*. A drum-named colour on a pitch-positioned map is just a tint, not a drum map.

### 2026-06-18 (evening) — Grok-supervised loop: live pool swap (v2) + taste-propagator stub
- **Setup:** drove the user's logged-in Grok (Heavy) via the **Playwright/CDP bridge** ([[grok-playwright-bridge]]) — read its messages, executed its concrete specs, reported results, repeated. User chose "full Grok mode," but execution stayed honest (surfaced a non-bug and a seed mismatch rather than blindly complying).
- **(a) Ratings parquet verified:** `_work/ninjastar8_ratings.parquet` = **283 rows** (rating_version v1=155, v2=128), correcting Grok's stale "155/2-of-10". All 128 v2 rows have `groove` set across 128 unique md5s, full 0–8 spread. **Anchor-tag persistence is NOT a bug** — `ninjastar8.py:745` already folds the pattern chips into `free_tag`; the chips are just optional/hidden behind "+ more" and weren't tapped (the one tagged row is `groove=0`, a test row). Did NOT "fix" it (auto-tagging on anchor-*play* would corrupt compare-vs-label semantics).
- **(b) Pool preview → live swap:** wrote **`CODE/36_pool_preview.py`** (clean = `parses & !zero_byte & !absurd_density & !over_1h & in_piano_range` → 455,385/459,805; weight `exp(0.6·z(bar_variance+pattern_entropy+syncopation+0.5·swing)) ×3 drums ×4 empty-corner`, stratified over groove_composite deciles, all 88 eligible empty-corner md5s force-included). Result `_work/pool_v2.parquet` (500, 73% drum-bearing). **Swapped live with user's OK:** backed up `pool_current.txt` → `.bak_pre_v2`, pointed it at `pool_v2.parquet`, restarted the **systemd --user `ninjastar8.service`** on its pinned port **8780** (Tailscale `lab.tail0b3418.ts.net` → 8780). Cleaned up a duplicate-process / wrong-port (8781) tangle from the restart; verified single process serving v2 (`first_pool_id v2_0001`), 283 ratings intact.
- **(c) Taste-propagator STUB:** **`CODE/37_taste_stub.py`** — Ridge(α=10) on the 85-D `signatures_ext.npy` (GrooveDNA block `[74:85]` ×5) → user groove rating; trained on 128 v2 ratings, predicted all 459,805 → `_work/taste_pred.parquet`. **5-fold CV pearson r=+0.318, MAE=2.00 (0–8)** — weak but real; ceiling-saturated (13 songs pegged at 8.0).
- **Generation seeds (RESOLVED → B):** Grok's `nlargest(5)` snippet picked **global** top-taste (0/5 in empty corners); flagged it and offered A(global)/B(empty-corner). User chose **B**. `_work/generation_seeds/top5_targets.csv` locked to the 5 empty-corner targets `b56df652(7.08) 622f340d(6.91) f96decc4(6.85) 41277f13(6.83) cf698cb6(6.73)`. (Grok briefly degenerated into a repetitive paste-loop, self-corrected after the user called it out; the original chat later hit "conversation too long" and rolled into a fresh project chat `14da722f`.)
- **Pool sampler v2 (Grok task 1):** built `CODE/38_pool_sampler_v2.py` — 512-row pool, force-include the 5 targets, rhythm subspace = cols matching swing/syncop/onset/density/entropy/rhythm/groove (34 matched), weight `0.45·(1−density)+0.3·rhythm_var+0.2·top5_bonus+0.05·rand`, clean-only, `--force/--dry-run`. Ran → `_work/new_annotation_pool_512.parquet` + `pool_md5_list.txt` (5/5 targets, 41% groove-empty). **Built in pandas (polars not installed) and pointed at `catalog/metadata.parquet`** (Grok's `catalog.parquet` path doesn't exist). **Staged, NOT deployed** — live NinjaStar is still pool_v2.
- **Audio audition:** rendered the 5 empty-corner targets to `_work/seed_audio/*.wav` (fluidsynth + FluidR3_GM) and added to the webplayer (group `empty-corner-targets`) so they can be heard before generating into those corners.
- **Repo hygiene:** added `.playwright-mcp/` (bridge scratch) and nested separate repo `music_rules/` to `.gitignore`. All data artifacts under `_work/` remain gitignored. (User env preference recorded: `uv` + `venv`.)

### 2026-06-18 (~17:50) — DrumDNA: Empty-Space Hunt + Catalog Integration + Unit Tests
- **Empty-Space Hunt in DrumDNA:** Wrote `CODE/32_drum_emptyspace.py` to map the 311k drum-active manifold. Clustered to k=800; identified 30 coherent-but-empty corners (pop=0 within cos≈0.85). These are "unwritten" rhythmic directions (e.g. no-backbeat swung-sync, busy-kick loose-timing).
- **Drum Corner Audio:** Rendered the nearest real songs for the top 15 drum corners to `_work/drum_emptyspace/corner_audio/*.wav` using `fluidsynth` (VintageDreams SF2).
- **SQL Catalog Integration:** Wrote `CODE/33_drum_catalog.py` to fold 23 drum scalars (renamed with `drum_` prefix, e.g. `drum_kick_density`, `drum_swing`, `drum_beat3_accent`) into `catalog.sqlite` and `metadata.parquet`. Verified 459k rows, 183 cols (sqlite) / 184 cols (parquet).
- **Unit Tests:** Created `CODE/test_drum_vector.py` (unittest) to verify `drum_of` musical truths. Passes for: empty inputs, melodic isolation, rock backbeat (1.0), one-drop (beat-3 heavy), swing detection (straight vs shuffle), and microtiming (laidback vs pushed).
- **Strategic Payoff:** The corpus is now searchable and clusterable purely by "feel". You can query `SELECT * FROM catalog WHERE drum_beat3_accent > 0.8` to find all one-drops instantly.

### 2026-06-18 (~16:40) — DrumDNA: 72-D standalone drum signature + cosine kNN (separate drum vector)
- **User ask:** "make a separate vector for the drums (channel 10)" → "research best features and execute". Built **`CODE/31_drum_vector.py`** — a dedicated **72-D drum signature** (GrooveDNA's bigger sibling), with its OWN matrix + kNN so you can search/cluster purely by drum feel, independent of pitch/harmony.
- **Feature set (research-grounded:** GrooveToolbox/Bruford, HVO/MGT, Longuet-Higgins & Lee metric salience, Columbia eigenrhythm**)** — 72 LOCKED dims: **20 scalars** (per-voice + total density, perc_diversity, kick_on_downbeat, snare_backbeat, kick_snare_interlock, swing, laidback microtiming, timing_tightness, LHL syncopation_poly, ghost_dynamics, accent_strength, pattern_entropy, bar_variance, symmetry, pulse_clarity) + **4 per-beat accent shares** (beat1..4 — one-drop = beat-3 heavy, closes Open Concern #1) + a **48-D per-voice 16-step onset grid** (kick/snare/hat probability over the bar — the eigenrhythm fingerprint, best same-beat discriminator).
- **Isolation identical to 29** (`chan 9|10` AND GM pitch `35–81`) so both vectors agree on "drums"; densities per 4/4 bar in beats (tempo-independent). **No-kit song → all-zero vector + `has_drums=0`** (cleaner than 29's overloaded 0.5; drum songs fall back to per-dim neutral).
- **Extracted full corpus** (~2,000 files/s, 12 workers, ~4 min) → **`_work/drum_dna.parquet` (462,621 rows, 74 cols)**; **311,585 have a real kit**. Medians (drum files): kick/bar 2.91, backbeat 0.50, swing 0.00, sync 0.00, grid-entropy 0.83, beat3_accent 0.24.
- **`signature` mode** aligned DrumDNA to `signatures_md5.txt` order, scaled 3 equal-weight L2 blocks (scalar20/accent4/grid48 → constant row-norm √3) and zeroed drumless rows → **`SIGNATURES_DATA/signatures_drums.npy` (459,805×72, 132 MB)** + **`knn_drums.pkl`** (cosine kNN over the 311,412 drum rows only). **Existing `signatures*.npy` / `knn_cosine.pkl` and the whole NinjaStar lane were NOT touched.**
- **Validated** (`--validate` on buckets 00,42): locked 74-col shape, float32, NaN-safe, drumless→all-zero, sane reads. **kNN sanity:** a clear backbeat rock query returns a coherent same-feel cluster (neighbors backbeat 0.98–1.00, straight, kick 3–7/bar; cos 0.13–0.15).
- **Next (awaiting go-ahead):** optionally surface DrumDNA in an empty-space "find the unwritten *beat*" hunt (run `27`-style frontier on `signatures_drums.npy`); or fold a down-projected DrumDNA into the catalog for SQL filtering. Not done — kept scope to the separate vector + its kNN.

### 2026-06-18 (~13:50) — MCP groove notation: parser + dependency-free MIDI generator + 5 archetypes
- **New `CODE/30_mcp_groove.py`** — MCP ("Mini-Compact-Pattern") is a human grammar for typing a drum groove as a string, the authoring layer on top of GrooveDNA: type a string → get a MIDI + an 11-D GrooveDNA score. **Grammar:** tokens `k`=kick `s`=snare `h`=closed-hat `o`=open-hat (+`c`/`r`/`t`); `(...)` = simultaneous group; `.`/`-`/`_` = rest; **8 positions per 4/4 bar** by default; optional leading `N/M ` time-sig (so `3/4 kss` = a 3-step waltz bar).
- **Parser** (`parse_mcp`) → step list; **generator** (`mcp_to_array` → `write_smf`) renders 4 bars to a NOTESEQ-style array and a **dependency-free Standard MIDI File** (mido/pretty_midi aren't installed) with drums on channel 9. GM map k=36 s=38 h=42 o=46 (all in GrooveDNA's 35-81 range, so generated MIDIs round-trip through 29). Flat reference velocities (kick/snare 110, hat 80, open 95).
- **5 archetype MIDIs generated** → `rhythmexamples/<name>.mcp.mid`: `rock=(hk)h(hs)(h)(hk)(hk)(hs)(h)`, `surf=khsshhsh`, `reggae=hhhh(ksh)hhh`, `waltz=3/4 kss`, `raggaetone=khshkshh` (strings from the user/Grok MCP Library v0.1). Validation closes the loop string→MIDI→GrooveDNA and asserts musical truths: rock backbeat=1.0 (snare on 2&4), reggae one-drop backbeat=0.0, rock = strongest composite (0.44). Generated files round-trip cleanly back through TMIDIX (rock=52 ch9 notes @ pitches 36/38/42).
- **`speedy_ragtime.mid` test case** — the pre-existing real MIDI in `rhythmexamples/` is **all piano (3112 notes, channel 0, zero drums)**; GrooveDNA scores it **NEUTRAL 0.5** across the board. That's the point: it proves drum isolation ignores melodic notes (the AND-not-OR mask), so a busy syncopated piano part can't fake a groove.
- **Scope held:** parser + 5 archetypes + ragtime test + STATE only. Grok's other v0.1 guesses (techno/trap/funk/broken/shuffle) are kept in an `UNVERIFIED` dict but NOT generated — several violate the 8-positions rule (trap=10, funk=4, shuffle=6 steps) and aren't user-confirmed. No new features beyond the task. **Next (awaiting approval):** lock the rest of the MCP library; add a real-MIDI→closest-archetype matcher; NinjaStar Groove anchors + GrooveDNA-stratified rating pool.

### 2026-06-18 (~13:06) — GrooveDNA: 11-D drum-only Rhythm Vector built, merged, folded into the signature
- **New `CODE/29_groove_dna.py`** — canonical 11-D GrooveDNA per song from the `NOTESEQ_DATA` cache (no re-parse; same `process_bucket`/parallel `Pool` pattern as 22). Ran full corpus in ~165s @ ~2,800 files/s → **`_work/groove_dna.parquet` (462,621 rows, 12 cols)**; **311,585 files have a real drum kit** (rest = neutral 0.5). Medians (drum files): kick/bar 2.91, backbeat 0.50, swing 0.00, sync 0.50, composite 0.41.
- **Drum isolation** = `(chan 9|10) AND pitch∈[35,81]` (GM percussion). NOTE: the brief's literal `OR pitch∈35–81` would match melodic notes on every channel (middle-C piano = 60) and break "drum isolation"; GM pitch numbers only MEAN drums on the drum channel, so it's an AND. Verified ch9 = GM drum channel (top pitches 42 hat / 36-35 kick / 38-40 snare / 51 ride). One documented deviation; everything else per spec.
- The 11 LOCKED dims (= `groove_dna` array index order): `kick_density_bar, snare_backbeat_strength, hat_cym_density, perc_diversity, swing_cont, syncopation_drum, dotted_groove, ghost_dynamics, drum_pattern_entropy, bar_drum_variance, groove_composite`. All float32, NaN-safe, neutral 0.5; densities per 4/4 bar in beats (tempo-independent).
- **`CODE/23_catalog_merge.py` patched** (non-breaking): added the 11 scalars as a source + a packed `groove_dna float32[11]` array col (parquet only — no SQL array type; sqlite keeps the 11 scalars). Catalog **148 → 160 parquet cols / 159 sqlite**, 459,805 rows unchanged, cross-check AGREE. **Also made the parquet merge idempotent** — re-running with extra sources was creating `_x/_y` duplicate cols for already-merged pillars; now it skips columns already present (mirrors the sqlite ADD-COLUMN guard). Backups: `catalog/metadata.parquet.bak_20260618_125944`, `catalog/checkpoints/catalog_20260618_125944_pre_seqmerge.sqlite`.
- **`CODE/26_signature_extend.py` patched** — GrooveDNA is now its own pillar (`--w-groove`, default **×2** like rhythm) + a schema guard that auto-prunes any pillar whose cols aren't in the catalog yet (so it never crashes mid-build). Rebuilt **`signatures_ext.npy` N×74 → N×85** (block_dims pitch36/rhythm17/melody13/harmony8/groove11), row-norm √7=2.646, kNN refit (6s). **Sanity:** neighbor groove-block std 0.071 vs global 0.426 → feel clusters ~6× tighter. Backup: `knn_cosine.pkl.prerefit_20260618_130607.bak`.
- **Next:** re-cluster / re-run the empty-space hunt on the N×85 space to find under-populated *groove* regions (`python3 CODE/27_emptyspace.py all` reads `signatures_ext.npy`); and wire the NinjaStar by-ear "Groove" ratings against measured GrooveDNA. NB: 27 re-normalizes each row by its actual norm at load (`U = ext/norms`), so cosine=dot still holds on N×85 — only its √5 doc-comments are stale (real norm is now √7).

### 2026-06-17 (~19:40) — Phase 11 #1 DONE: EMPTY-SPACE HUNT built + run (the payoff of vectorizing)
- Wrote **`CODE/27_emptyspace.py`** (subcommands `cluster|density|summary|corners|show|all`, resumable; outputs under `_work/emptyspace/`). Reads `signatures_ext.npy` (N×74) read-only; unit-normalizes (norm≈√5 confirmed) so cosine = dot. Touched nothing in the NinjaStar-8 lane.
- **Clustered** all 459,805 → **1200 spherical MiniBatchKMeans clusters** (17s; sizes 76–1338, 0 empty). `clusters.parquet` + `clusters_centroids.npy`.
- **Density / FRONTIER (full 460k pass, ~15 min):** per-song `frontier` = mean cosine dist to 25 NN → `density.parquet`. p50=0.121 p90=0.179 p99=0.231 max=0.382 (thin outlier tail). Sparsest *clean* real songs = the literal edge of known music (extreme feels: sync 0.83–0.99, chroma 0.50).
- **Cluster summary** (`cluster_summary.parquet`): each cluster human-captioned from catalog medians (genre/bpm/swing/sync/chroma/diat/chord_dens/ext-harm) + isolation + tightness + frontier_med + 5 nearest-centroid reps. Rhythm-feel clearly separates clusters (swung/triplet/sync) → the ×2 rhythm weight is doing its job.
- **Corners = candidate "new forms"** (`corners_blends.parquet`, `corners_isolated.parquet`): (A) **empty blends** — midpoints between dense, distinct cluster pairs with **0 corpus songs in-neighbourhood** yet nearest real song at cos≈0.84 (coherent, not a void); ranked emptiest-then-most-coherent; each captioned by the median features of the real songs nearest the midpoint + the closest real song to listen to. (B) **isolated pockets** — rare-but-real song types far from everything (iso up to 0.25). Radius auto-calibrated from median 50th-NN sim.
- **Made it HEARABLE:** rendered the nearest real song of the **top 10 most-distinct empty corners** → `_work/emptyspace/corner_audio/*.wav`, loaded into **webplayer** group `emptyspace_corners` (http://127.0.0.1:8765/). Plain-language **`_work/emptyspace/REPORT.md`** (top 20 blends + 20 pockets).
- **NEXT:** (a) cross the corners with TASTE — once NinjaStar-8 has enough ratings (45 now), rank corners by predicted "love", or now use proxy beauty filters (diatonic/melodic/consonant) to pick the *beautiful* corners to actually generate; (b) Phase 11 #2 re-cluster `song_id` with the 74-D sig; (c) re-run `27 corners` with wider `--pair-lo/--pair-hi` or higher `--k` to surface bolder fusions.

### 2026-06-18 (~02:00) — ALL THREE: 3D galaxy + empty-corner overlay + ♥ Like (one pass)
- User: "LETS DO EM ALL." Built into `CODE/28_mapserver.py` (now 4 pages on port 8766: `/` 2D map, `/galaxy` 3D, `/duel`, + endpoints). Refactored `build_points`→**`build_space`**: shared 60k sample, builds 2D (umap2) AND 3D (umap3) payloads + corner markers, normalization fixed from the FULL embedding so points & corners align. `/points.json` (2D), `/points3.json` (3D), each `{pts,corners}`.
- **3D galaxy (`/galaxy`)** — three.js vendored locally (`_work/emptyspace/vendor3d/three.module.min.js` 670 KB + `OrbitControls.js`, fetched once from unpkg; import-map `"three"`→local). 60k-star `THREE.Points` cloud colored by syncopation (viridis), orbit/zoom/pan + gentle auto-rotate, **raycast click-to-play** (verified: click hit a star→loaded+captioned), empty corners as additive-glow yellow markers, ♥ like, ■ stop, soundfont dropdown. **3D UMAP** = `umap3.{npy,parquet}` (n_components=3, cosine, 4.9 min) — NOTE first attempt silently stayed 2D (sed had no `n_components=` to replace; script never set it) → fixed script explicitly sets `n_components=3`.
- **Empty-corner overlay** — the 60 `corners_blends` plotted as ✕ markers on BOTH map & galaxy, positioned at the mean embedding coord of their nearest real songs (lands them squarely in the dark gaps between islands ✓ screenshot). Hover = "✕ EMPTY CORNER" + caption; click = plays the closest real song to that gap. Bridges the empty-space hunt to "hear the unwritten."
- **♥ Like** — `/like` POST appends md5 to `_work/taste_likes.jsonl` (corpus lane, NOT ninjastar); `/likes` returns the set; liked stars get a pink ring (2D). Complements Taste Duel as a second taste signal → both feed the "love direction" for targeting generation. (Wiped a test-like so user data starts clean; the anchor `f5ca…` lives in memory [[taste-anchor-songs]].)
- **Verified headless (playwright+swiftshader WebGL):** 2D 0 errors + ✕ corners render; galaxy 0 errors, canvas 1200×780, 60k stars, click-to-play works. Fixed a stray-CSS typo + KeyError('z') from the bad first umap3.
- **NEXT:** the taste→empty-space→generate loop (route C retrieve-and-recombine first, proxy-beauty filter per user); optionally color-switch UI in-page; liked-ring in 3D; mark which corners sit nearest liked songs.

### 2026-06-17 (~23:10) — Taste Duel game + soundfont switcher (clean default)
- **Taste Duel** added to `CODE/28_mapserver.py` (`/duel`, `/duel/pair`, POST `/duel/pick`): A/B "which do you love more" over a clean proxy-beauty pool (quality ok, bpm valid, has_melody, diatonic≥0.5, 20–600s, one per song_id). Picks log winner/loser to **`_work/taste_duels.jsonl`** (append-only, md5-keyed, corpus-lane — NOT the NinjaStar-8 phone lane). Keys: ← A-wins / → B-wins / ↓ skip, A/L to audition. Reuses the vendored synth. Verified headless: 0 errors, audio peak 0.82, pick logs + advances. **This is the corpus-lane taste signal** → fit a "love direction" in 74-D → score empty gaps by predicted love (the missing piece for "generate music in a black gap you'll love").
- **Confirmed to user:** duel/map songs ARE real corpus `.mid`s (served from `MIDIs/<md5>.mid`); synth is just playback.
- **Soundfont switcher:** old default VintageDreams (314 KB) is a lo-fi *synth* bank (the "effects" sound). Copied clean GM banks into `_work/emptyspace/assets/` (**TimGM6mb 6 MB = new default**, GMbank 4 MB) + kept VintageDreams. `/soundfont?sf=<file>` (allow-listed), `/soundfonts` lists them, 🔊 dropdown on both `/` and `/duel` swaps live via `soundBankManager.addSoundBank(buf,'main')`. Bigger clean fonts available if wanted: `/usr/share/sounds/sf2/FluidR3_GM.sf2` (148 MB), ninjastar `soundfonts/GeneralUserGS.sf2` (30 MB).
- **First taste anchor saved** (memory [[taste-anchor-songs]]): user loves `f5ca332850121fd3bf4fcd25d777da1a` — C minor 108bpm, busy+singable, chromatic, extended harmony (cinematic/game/anime). Plan: target empty space NEAR loved songs = novel + beautiful-by-association.
- **Game/3D ideas discussed; user picked Taste-duel first.** Pending offers: 3D UMAP galaxy (three.js, embed to 3 comps), ❤ Like button on the map, Frontier game, overlay empty corners on the map.

### 2026-06-17 (~21:00) — VISUALIZED the space: UMAP map + clickable play-the-MIDI graph
- **Is the corpus vectorized? Yes** — confirmed `signatures_ext.npy` = 459,805×74; made it visible.
- **uv venv** at `.venv` (PEP-668 blocks system pip): `uv venv .venv --python 3.12` + `uv pip install umap-learn playwright`. Reusable.
- **UMAP embedding of all 460k** → `_work/emptyspace/umap2.{npy,parquet}` (`umap.UMAP(n_neighbors=30,min_dist=0.1,metric=cosine)`, multi-core ~5 min; dropped random_state for parallelism). Far better than PCA (which only held 24% var). Static 4-panel PNGs: `space_umap.png` (+ `space_pca.npy`/`space_pca.png` fallback). The map is an **archipelago** — big mainstream continents + many small rare-type islands, **gaps between = empty space**; swing forms its OWN island; syncopation is a continent-scale gradient (rhythm ×2 is real structure). Embed script: `_work/emptyspace/_umap_embed.py`.
- **Clickable, AUDIBLE map — `CODE/28_mapserver.py`** (stdlib http, port **8766**, separate from webplayer:8765 / ninjastar:8780). Canvas scatter (no CDN), pan/zoom/hover-caption; **click a star → streams that song's `.mid` → synthesizes in-browser** reusing the vendored spessasynth (served from `web/vendor/` read-only + a copied soundfont `_work/emptyspace/assets/VintageDreams.sf2`). `python3 CODE/28_mapserver.py --port 8766 --sample 60000 --color syncopation` → http://127.0.0.1:8766/. Does NOT modify the NinjaStar-8 lane (reads its vendor/soundfont, writes nothing there).
- **Verified with headless Chromium (playwright in venv), not just curl** — caught a real page bug: `playIdx` referenced in `draw()` before its `let` (temporal-dead-zone) crashed the module → click handlers never bound. Hoisted `let hi=-1, playIdx=-1` above `draw()`. Post-fix: 0 page errors, 60k points, AnalyserNode RMS confirms real audio (peak 1.34/1.18 on dense songs; quiet songs genuinely quiet). Synth pattern copied verbatim from the debugged ninjastar path (import-map → `WorkletSynthesizer` → `synth.connect(ctx.destination)` → `Sequencer.loadNewSongList`).
- **NEXT:** overlay the empty corners (`corners_blends`) as marked targets on the map; color-switch UI (`--color` is currently a server flag — could expose in-page); optionally plot cluster-centroid labels. Then the taste cross (beautiful corners).

### 2026-06-17 (~17:00–02:30) — NinjaStar-8 annotator: rebuilt MIDI-first, HTTPS, persistent, offline-resilient (phone lane)
- **Phone-synced `work` tmux session.** Picked up the NinjaStar-8 annotator (was already built + serving). Resolved the PHONE_HANDOFF "data at risk" alarm: the tool + `_work/ninjastar8_ratings.parquet` existed and were fine. Drove the whole session from the user's iPhone over Tailscale.
- **Rebuilt playback MIDI-first.** Was streaming the 109 pre-rendered WAVs (multi-MB each); switched to serving the source `.mid` (~36 KB med) + **in-browser synthesis** via self-hosted **spessasynth_lib v4** (vendored to `web/vendor/`, ~1.2 MB cached once) with a swappable soundfont. ~100× less cell data; nothing leaves the tailnet. New endpoints: `/midi/<md5>`, `/soundfont/<id>`, `/web/<asset>` (range + path-guarded); `/state` lists soundfonts.
- **Three real bugs caught by headless Playwright (Chromium + WebKit/Safari engine), not curl:** (1) lib's bare `import "spessasynth_core"` → patched to relative + `?v=` cache-bust (kills the iOS<16.4 import-map dependency); (2) **silence bug** — `WorkletSynthesizer` does NOT auto-connect; added `synth.connect(ctx.destination)` (clock ran/red-but-silent without it); (3) **AudioWorklet needs a secure context** → required HTTPS. Verified real audio OUTPUT via an AnalyserNode (peak ~0.9–1.3), not just the transport.
- **HTTPS via Tailscale Serve:** enabled tailnet HTTPS Certificates (user, admin console) + `sudo tailscale set --operator=t` + `tailscale serve --bg --https=443 http://127.0.0.1:8780` → **https://lab.tail0b3418.ts.net/** (valid LE cert, tailnet-only). Plain http-over-IP can't play audio (no secure context).
- **Persistence:** systemd `--user` `ninjastar8.service` (Restart=always, enabled, linger on) + tailscale serve config persists. Survives reboot / tmux-close / logout.
- **UX per user:** scale 0–5 → **0–8, 4=neutral**; **bipolar diverging sliders** (green out from center, both sides green); sliders **default to 4**; whole thing **fits one phone screen**; soundfont default = light **VintageDreams 314 KB** (GeneralUserGS 30 MB was too heavy a default on cell → demoted to opt-in). Migrated existing ratings carefully (restored originals after a scrapped 0–10 ×2 rescale).
- **Offline-resilient save (the on-the-go fix):** save → `localStorage` queue + instant advance; background POST with auto-retry (5 s / `online` / reload); ⟳N "pending" badge. A dropped cell connection can no longer lose or block a rating — tested with a simulated dead `/rate`.
- **State:** **45 ratings** banked (md5-keyed). Pool is still the QA-biased 109; offered (not yet done) to swap in a clean randomized ~500 stratified sample, a `rater` column for a 2nd annotator, and a compact ~5 MB GM SF3. **Corpus/Phase-11 work is untouched and conflict-free** (annotator only edits `ninjastar8.py`/`_work/ninjastar8_ratings.parquet`/`soundfonts/`/`web/`).

### 2026-06-17 (~15:02) — signature EXTENDED + kNN rebuilt → corpus VECTORIZED (finish line)
- Picked up STEP 4 from HANDOFF_NEXT.md (context was cleared; reconstructed from HANDOFF + STATE + reading 12_signatures.py). Confirmed STEP 3 already done (catalog 459,805×148, all 36 feature cols present) and that **nothing but `12_signatures.py` + docs reference `knn_cosine.pkl`** (04_search.py is a separate brute-force pitch search) → free to change the pickle, but kept it back-compatible.
- **Must #1 backups:** `SIGNATURES_DATA/signatures_20260617_150005.npy.bak` + `knn_cosine_20260617_150005.pkl.bak` (the old pickle was a 100k-sample dict, NOT a full fit). Script also auto-backed-up the kNN again pre-refit (`.prerefit_20260617_150210.bak`).
- **Wrote `CODE/26_signature_extend.py`** and validated with `--dry-run` before the real run. Aligned features to `signatures_md5.txt` **by md5** (reindex, not row order); one-hot `tempo_class`→rhythm; dropped `most_common_chord`. Per pillar: log1p heavy tails → median-impute → z-score → clip ±8 → row L2 → ×√weight. **Rhythm ×2**, others ×1. → **`signatures_ext.npy` (459,805×74)** (36-D pitch file kept untouched). Refit `NearestNeighbors(cosine, brute)` over all 460k rows → **`knn_cosine.pkl`** (139.8 MB; `nn`+`fit_rows`=all rows + `block_dims`/`weights`/`feature_names`/`report`). Whole run **5s** (handoff over-estimated; brute-cosine fit just stores the matrix). Phone watcher (`notify-when-done`) launched per must #3; log `_logs/26_signature_extend_*.log`.
- **Sanity ✅ (rhythm now drives neighbors, not just pitch):** mean neighbor rhythm z-spread **1.004 pitch-only → 0.375 extended**. Triplet-feel seed: pitch-only neighbors triplet≈0–0.08, extended triplet≈0.54–0.59. Swing seed (swing_bur=2.43): extended neighbors all 2.43 (z-spread 0.044 vs 0.803). High-sync seed: extended pulls sync≈0.87 vs pitch-only 0.24–0.4.
- **Tune later:** weights are a CLI knob — `python3 CODE/26_signature_extend.py --w-rhythm N --w-melody N ...` re-derives `signatures_ext.npy` + refits in seconds (`--dry-run` previews dims/norms). If a downstream consumer wants the old behavior, the 36-D `signatures.npy` and the timestamped `.bak` pickle are intact.

### 2026-06-17 (~14:16) — catalog merge (23) DONE → catalog at 148 cols; only signature/kNN left
- Worked the HANDOFF_NEXT.md plan from the phone. **STEP 1 (DQ checks) PASSED:** all 4 feature tables (rhythm/melody/harmony/seq) ~462k rows, **0 dup md5, 100% catalog coverage, 0 infs, ratios in [0,1], near-zero errors** (seq has 1,185 parse-reject errors = 0.26%, ok_rows 462,621 — expected, fine for a left-merge). 52 catalog md5s absent from rhythm/melody/harmony → NaN after merge, by design.
- **STEP 2 checkpoint:** manual pre-merge backup `catalog/checkpoints/catalog_20260617_141430_pre23.sqlite` + `metadata_20260617_141430_pre23.parquet`.
- **STEP 3 merge — `CODE/23_catalog_merge.py` ran clean (exit 0).** Joined seq(22)+rhythm(15)+melody(19)+harmony(12) → **80→148 cols, 459,805 rows unchanged**; script took its own backups (`.bak_20260617_141441` + pre_seqmerge sqlite). **parquet⇄sqlite cross-check: both 148, AGREE.** Verify: is_swung=20,069 / is_dotted=84,068 / has_melody=458,607 / swing_bur not-null=409,926 / catalog view=459,805. Spot-check confirms `swing_bur`, `syncopation`, `mel_*`, `n_distinct_chords`, `chord_density` etc. present. Log: `_logs/23_catalog_merge_*.log`.
- **STOPPED here (good stopping point).** Remaining = STEP 4 = the "vectorized" finish line: write `CODE/26_signature_extend.py` (extend N×36 signature with the new pillars, up-weight rhythm, refit cosine kNN). New script + slow ~460k-row refit → deferred to a deliberate run; will `notify` the phone on completion.

### 2026-06-17 (~13:45) — harmony (25) DONE → all 3 pillars built; ready for the 23 merge
- **Harmony refine (25) finished cleanly at 13:44** (exit 0). The resumed `--workers 10` run completed all **256/256 buckets** (~462,621 files at ~44 files/s) → **`_work/harmony_features.parquet` (462,621 rows, 13 cols)**. Watched it to completion via a background wait on the PID.
- Final sanity from the log: `harmonic_rhythm` med **2.82**, `diatonic_ratio` med **0.832**, `n_key_areas` med **6.0**. The 2.8 / 6.0 reads are the previously-noted "tune later" items (per-beat windowing over-counts chord changes; windowed Krumhansl over-counts modulation → prefer `key_stability` / add min-chord-duration smoothing). **Re-derivable from the `NOTESEQ_DATA` cache — no re-parse ever.**
- **All three first-class pillars now exist as parquet feature tables** (462,621 rows each): `_work/rhythm_features.parquet`, `_work/melody_features.parquet`, `_work/harmony_features.parquet`.
- Clarified for the user: finishing 25 means **features computed**, NOT a vector-indexed/embedded corpus. No vector DB (Qdrant/Chroma/FAISS index) is running or built; the only live services are Ollama (`:11434`) + Redis (`:6379`). "Vectorized / experiment-ready" is still the next phase (23 merge → extend signature → rebuild kNN).
- **RESUME POINT:** run **`CODE/23_catalog_merge.py`** to join rhythm+melody+harmony into `catalog.sqlite` + `metadata.parquet` (**BACK UP sqlite+parquet FIRST**; non-destructive new columns; verify parquet⇄sqlite agree) → takes catalog past 80 cols. Then extend the N×36 signature + rebuild `knn_cosine.pkl`.

### 2026-06-17 (~10:55) — re-parse + rhythm + melody DONE; resumed harmony; clarified goal = vectorized
- Confirmed on disk: the overnight **re-parse → `NOTESEQ_DATA/` cache is COMPLETE** (256/256 buckets, ~463k files — the permanent note-sequence store). **Rhythm (22) and melody (24) refine passes both DONE** (`_work/{rhythm,melody}_features.parquet`, 462,621 rows each).
- **Harmony (25) had died ~10/256 buckets** (terminal closed again; process gone, only 10 parts written). Added **skip-existing resume** to `25_harmony_refine.py` (`process_bucket` skips buckets whose part already exists unless `HARMONY_FORCE=1`), then **relaunched `--workers 10` in background** (`_logs/refine_all.log`). Verified all 10 workers at ~100% CPU. Slow per-beat pass; ETA a few hours.
- **23 catalog merge NOT yet run** (metadata still 80 cols); **signature/vector rebuild NOT started.** Recorded the explicit "path to vectorized" in NEXT STEPS / CURRENT STATUS.
- Clarified with user: **"ready for experiments" = VECTORIZED** — every song a point in the extended signature space. That's the finish line: harmony → `23` merge → extend signature + rebuild kNN.

### 2026-06-16 (latest) — Phase 9.1 audio sanity render DONE + wrote MANUAL.md
- Wrote `CODE/20_audio_sanity.py`: renders a **deterministic 500-file sample** (np.linspace over sorted md5, non-quarantined, duration ≤3600s) via fluidsynth/LAMD `midi_to_colab_audio` + VintageDreamsWaves sf2, measures audio, flags anomalies. Per roadmap: results → standalone `_stats/audio_sanity.parquet` (NOT added to the 459,805-row catalog); WAVs for flagged + 12 clean controls → `_stats/audio_sanity_wav/`.
- **Key finding: 0 silent, 0 render errors across 500 files → the corpus renders to real audio (the main sanity goal).** 6.8s/file avg (~57 min total); ran in background.
- Metric note: the renderer **max-normalizes** every clip, so `peak`≈1.0 is useless for clipping. Used `rms` (silence detector; min rms 0.0386 → nothing remotely silent) and `frac_fs` = fraction of samples within 1% of full-scale (saturation/distortion proxy).
- Initial `frac_fs>0.02` clipping threshold over-fired (82/500=16%). Recalibrated to **`>0.10`** (clear tail) → **17 clipping**; **19 length_mismatch** (rendered length differs >25% from `duration_sec` — mostly stuck/hanging notes, e.g. 221s→1131s). Re-labeled the parquet + renamed WAVs in place (no re-render — raw rms/peak/frac_fs/rendered_sec are saved, so re-thresholding is free). Synced `CLIP_FRAC=0.10` in the script.
- Loaded all 109 WAVs into **webplayer** (group `audio_sanity`, http://127.0.0.1:8765/) for ear spot-check.
- Wrote **`MANUAL.md`** (project root) — a plain-language, re-readable guide to how the corpus/signatures/kNN/space work and how it serves the goal of inventing a new form of music. Saved Claude memory `north-star-new-music` (the standing goal).

**PIVOT mid-session (2026-06-17): RHYTHM = top priority + full re-parse decided.**
- User directive: **rhythm is THE most important dimension for the model.** Saved memory `rhythm-is-priority`. The current 36-D signature has ZERO rhythm — biggest gap.
- Verified the `META_DATA` pickles hold ONLY aggregates (pitch/chord histograms, timing stats); `raw_tail` is just the last ~32 events, NOT full note sequences. So melody-contour / structure / rhythm-curve CANNOT come from pickles — they need a real parse. **User chose: full re-parse of all ~460k (one unified pass).**
- **Wrote `CODE/21_sequences.py`** — the rhythm-first unified TMIDIX re-parse (the 2nd and FINAL parse). Per-BUCKET parallelism (256 buckets → resumable, 256 cache files not 460k). Outputs:
  - `_work/seq_parts/<2hex>.parquet` (per-bucket feature parts) → merged to **`_work/seq_features.parquet`**.
  - **`NOTESEQ_DATA/<2hex>.npz`** (key=md5 → int32 (n,5) [start,dur,chan,pitch,vel]) + `<2hex>.meta.json` (ticks_per_beat). The permanent note-sequence CACHE — nothing re-parses after this.
  - Features: **9.R rhythm** (IOI hist in beat units, onset density, quant tightness, syncopation, swing, microtiming, pulse_clarity, polyrhythm_hint, articulation, tempo_class) + **9.2 melody** (has_melody, melody_channel, contour) + **9.3 structure** (n_sections, has_repetition, repetition_ratio).
- **`CODE/22_rhythm_refine.py` — authoritative SWING + DOTTED detection, recomputed FROM the cache (no re-parse).** Per user (2026-06-17): the model must above all nail **swing** and **dotted rhythms**. Detectors:
  - **SWING via Beat-Upbeat Ratio (BUR)** = on-beat-eighth len / off-beat-eighth len (straight≈1, swing≈1.5–2.0+). Onsets snapped to a **1/48-beat grid** (represents 16ths+triplets+swing exactly; 1/16 corrupted triplet/swing). Swing upbeat window (0.40,0.72) excludes dotted's 0.75; a beat is rejected if it has an onset at ~1/3/16th (so triplets/16ths don't false-positive). `is_swung` = BUR∈[1.3,2.6] & confidence>0.3 & ≥8 beats.
  - **DOTTED/TRIPLET/STRAIGHT** = every IOI & duration snapped to nearest canonical value in LOG space → straight/dotted/triplet/free ratios; plus `dotted_pair_ratio` (adjacent IOIs ~3:1).
  - **VALIDATED against synthetic ground truth (all pass):** straight, 16ths, swing-2:1, light-swing-1.5, dotted-8+16, triplets all classify correctly; swing cleanly separated from dotted & triplets.
- **THREE first-class pillars (user 2026-06-17): rhythm #1, + MELODY + HARMONY.** Three cache-based refine passes, all validated:
  - `CODE/22_rhythm_refine.py` — swing(BUR)/dotted/triplet/straight. Validated synthetic + real (bucket00: is_swung~5%, is_dotted~18%, swing_bur med 1.0 — correct shape).
  - `CODE/24_melody_refine.py` — contour, range, stepwise/leap/repeat, chromaticism, **phrases**, **melody's own note-values (mel_rhythm_*)**, **motif repetition**. Validated synthetic (scale→stepwise, arp→leaps) + real (has_melody 1789/1797).
  - `CODE/25_harmony_refine.py` — per-beat chord (template match maj/min/dim/aug/7ths/sus), **harmonic_rhythm**, **modulation (windowed Krumhansl → n_key_areas/key_changes/key_stability)**, **tension/dissonance**, diatonic_ratio, progression_entropy. Validated synthetic (Cmaj→maj, Amin→min, dim, G7→dom7, dissonance discriminates). SLOWEST pass (per-window template match) — run with full cores after parse frees CPU. Real-data check (bucket00): diatonic_ratio med 0.84 ✓, dissonance 0.34 ✓. TUNE LATER (re-derivable from cache, no re-parse): `harmonic_rhythm` med 2.8 chords/bar reads high (per-beat windowing counts passing chords as changes → add min-chord-duration smoothing); `n_key_areas` med 6 overestimates modulation (windowed Krumhansl jumpy → prefer `key_stability`, or smooth window keys).
- **CROSS-PROJECT (2026-06-17): see memory `music-rules-project-link`.** `~/projects/music_rules` = theory-constraint engine (EIS/Fux/Orch, 184 rules, SkyTNT rejection-sampling bridge) with only 1 RHYTHM rule. It's the pitch/harmony half; this corpus is the empirical/rhythm half. Both target SkyTNT midi-model. Synthesis: author a new Rhythm rule-system grounded in corpus distributions; run music-rules checkers over the corpus to mine/weight rules; "new form" = a new coherent rule system.
- **NEXT STEPS (2026-06-17 ~10:55) — the path to VECTORIZED / experiment-ready:**
  1. **Let harmony (25) finish** → `_work/harmony_features.parquet` (running now, PID-tracked in `_logs/refine_all.log`/`harmony.log`). Verify row count ≈ 462,621 and `harmonic_rhythm`/`diatonic_ratio` medians look sane.
  2. **Run `CODE/23_catalog_merge.py`** — joins rhythm+melody+harmony parquets into `catalog.sqlite` + `metadata.parquet` (BACK UP sqlite+parquet FIRST; non-destructive new columns; verify parquet⇄sqlite agree). This takes the catalog past 80 cols.
  3. **Extend the signature → rebuild vectors** — add rhythm/melody/harmony dims to the N×36 matrix in `SIGNATURES_DATA/`, rebuild `knn_cosine.pkl`. THIS is "vectorized / experiment-ready." Then the empty-space hunt covers time-feel + melody + harmony, not just pitch.
  - Re-tune (re-derivable from cache, no re-parse): harmony `harmonic_rhythm` reads high (add min-chord-duration smoothing), `n_key_areas` overestimates modulation (prefer `key_stability`).
- **STATUS / RESUME POINT (2026-06-17 ~01:15):** Full parse `21_sequences.py --workers 10` RUNNING (`_logs/21_sequences_full.log`, ~85/256 buckets, ~50 files/s, ETA ~1.5h). Builds `NOTESEQ_DATA/*.npz` cache + `_work/seq_parts/*.parquet`. **When done, the overnight chain:** (1) `python3 CODE/21_sequences.py --merge-only`; (2) run `22`, `24`, `25` `--workers 10` (from cache) → `_work/{rhythm,melody,harmony}_features.parquet`; (3) write `CODE/23_catalog_merge.py` to add ALL seq/rhythm/melody/harmony columns to catalog.sqlite + metadata.parquet (**BACK UP sqlite+parquet FIRST** per convention; non-destructive new columns; verify parquet⇄sqlite agree); (4) extend the N×36 signature with rhythm+melody+harmony dims → rebuild kNN → empty-space hunt covers time-feel + melody + harmony. NOTE: all features re-derivable from cache forever; never parse again.

### 2026-06-16 — fixed KNOWN GAPS #3 + #4 + #5 (all data-quality gaps now closed)
- Wrote `CODE/19_quality_flags.py` (non-destructive flags + one safe fill; backs up sqlite + parquet first). No reparse — all derivable from existing columns.
- **#3 time_signature:** filled 68,364 bad values (33,717 NULL + 32,639 `1/4` + 2,008 `1/8` artifacts) → `4/4`, added `time_signature_inferred` flag so every touched row is recoverable. `4/4` now 393,614; 0 NULL / 0 artifacts remain.
- **#4 bpm:** added `bpm_valid` (20≤bpm≤300) → 452,508 valid / 7,297 invalid. Did NOT overwrite `bpm` (raw tempo events aren't stored; flag don't fabricate).
- **#5 duration:** added `duration_suspect` (`duration_sec>3600`) → 289 files (up to 9.9h).
- Catalog now **80 columns**; verified parquet ⇄ sqlite agree from fresh reads. Backups: `catalog/checkpoints/catalog_20260616_215532_pre_gaps345.sqlite` + `catalog/metadata.parquet.bak_20260616_215532`.
- **All 5 audit gaps are now closed.** Pristine subset = `WHERE quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0`. **Next: Phase 9 stretch** (audio sanity render, melody/structure/tempo-curve analysis, maintenance scripts) OR move to experiments.

### 2026-06-16 (later) — fixed KNOWN GAPS #1 (song_id on singletons) + #2 (split column)
- Wrote `CODE/18_fill_song_id_and_split.py` (idempotent-ish; backs up sqlite + parquet first).
- **#1 song_id:** filled all 355,607 singleton NULLs with `"song_"+uuid5(NAMESPACE_DNS, md5).hex[:12]` — the *same* algorithm `12_signatures.py:182` used for cluster roots, applied to each file's own md5. `n_arrangements`(=1)/`arrangement_rank`(=0) were already correct, so only `song_id` changed. Also filled the sqlite `manifest` table's 359,698 NULLs (singletons + 4,001 parse-rejects + 90 quarantined). Result: **378,923 distinct song_ids, zero collisions** (= 23,316 + 355,607 exactly). `master_manifest.parquet` left untouched — it has no song_id column (song_id lives in the sqlite manifest table), out of scope.
- **#2 split:** added `split TEXT` + `idx_meta_split` to `metadata`; populated from the 3 TOKENIZED manifests (md5 = basename). 0 NULLs; per-split counts match `split_report.json` to the row. `WHERE split='train'` now works in SQL and through `catalog`/`v_canonical`/etc.
- Verified both `metadata.parquet` (now **77 cols**) and `catalog.sqlite` independently from fresh reads; they agree. Backups: `catalog/checkpoints/catalog_20260616_214130_pre_gaps12.sqlite` + `catalog/metadata.parquet.bak_20260616_214130`.
- **Next:** KNOWN GAPS #3 (time_signature ~15% bad/missing), #4 (BPM outliers), #5 (duration outliers) remain. Then Phase 9 vs. experiments.

### 2026-06-16 — recovery + doc consolidation
- Came back to a closed terminal; confirmed **nothing was lost** — the 17:49 run was the *successful completion* of P0–P8, not a crash. No processes were mid-run.
- Verified catalog integrity: metadata 459,805 rows, manifest 463,896, counts reconcile.
- Flagged that `catalog/FINAL_REPORT.txt` (Jun 14) had garbage duration percentiles — it was from the OLD build, superseded by the v2 catalog.
- **Consolidated all docs into this `STATE.md`.** Folded in README.md (usage guide) + AGENT_TODO.md (ground-truth table + roadmap), then deleted README.md, AGENT_TODO.md, FINAL_REPORT.txt, and the empty `_make_done`/`_meta_done`/`_all_done` markers.
- Ran a data-quality audit (SQL over catalog.sqlite). Found 5 fixable gaps — recorded in KNOWN GAPS above. Headline: 77% of files have NULL `song_id`; no `split` column in catalog; `time_signature` ~15% bad/missing.
- Saved Claude memory pointing at this STATE.md so future sessions auto-orient.
- **Next session:** fix the 5 KNOWN GAPS (a short cleanup pass, no full re-parse), THEN decide Phase 9 vs. move to experiments.
