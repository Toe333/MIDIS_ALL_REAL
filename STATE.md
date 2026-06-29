# MIDIS_ALL_REAL — Project State & Guide

> **Single source of truth for this corpus.** Live status, how to use it, verified
> ground-truth facts, and a terse changelog all live here. **Add a Session Log entry every
> session.** Older standalone docs (README, AGENT_TODO, FINAL_REPORT) were folded in and
> deleted — do not recreate them. The full pre-2026-06-25 prose history was condensed on
> 2026-06-25; the verbatim original is in git history (and `scratchpad/STATE.full.md`).

---

## LIVE VALUES (the things that drift — check here first)

| What | Value |
|---|---|
| **Signature to use** | `SIGNATURES_DATA/signatures_ext.npy` — **N×88** (pitch 36 / rhythm 20 / melody 13 / harmony 8 / groove 11; rhythm & groove ×2-weighted) |
| **kNN** | `SIGNATURES_DATA/knn_cosine.pkl` — exact cosine over all 459,805 rows (rhythm/groove-aware, brute force) |
| **Row↔md5 map** | `SIGNATURES_DATA/signatures_md5.txt` (row i → md5 for every `.npy`) |
| **Catalog** | `catalog/metadata.parquet` + `catalog/catalog.sqlite` — **459,805 rows × ~201 cols** |
| **Corrected detection cols** | `bpm_v2` / `felt_bpm`, `ts_final`, `key_v2` + `key_corr` (prefer over raw) |
| **Pristine subset** | `WHERE quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0` |
| **Pitch-only legacy sig** | `signatures.npy` (N×36) — kept untouched |
| **Drum-only sigs** | `signatures_drums.npy`+`knn_drums.pkl` (72-D v1); `signatures_drums_v2.npy`+`knn_drums_v2.pkl` (468-D v2) |
| **Embed a NEW/external MIDI** | `CODE/49_sig_one.py` (re-derives the scaler step 26 never saved; round-trip cosine 1.0000) |
| **Taste predictions** | `_work/taste_pred_v2.parquet` (md5 + 7 axes + `pred_love` + `unc_love`); corner targets `_work/generation_seeds/targets_taste_v2_20260622.csv` |
| **TBB drum signature** | LOCKED v1 ("5-5-6 gallop clave") — the core groove for the invented style; see `DRUM_PATTERNS/TONYBOLLAS_patterns.md` |

---

## CURRENT STATUS

**The build pipeline is DONE and the corpus is VECTORIZED, generative, and taste-aware.**
Nothing is mid-run. As of the latest sessions:

- **Generation engine shipped (2026-06-25).** `CODE/50_generate.py --style` + `CODE/genre_engine.py`
  turn a coherent skeleton (seed md5 or `--pattern-from`/`--melody-from`) into a genre-idiomatic
  song by re-skinning tempo/mode/instruments/drums/role-rhythm. Genres: metal (death/black/thrash),
  rap/boom-bap/trap/drill, chiptune, lo-fi, house/edm, ambient, funk, jazz, rock, pop. Supports
  `--iterations`, `--novelty`, `--catchy`, `--beat`, `--keep-drums`, `--enhance`. Plus
  `CODE/51_remix.py` (coherent remix: one song's backing + another's/new melody, with optional
  `--advanced` EIS reharmonization + strict voice leading) and `CODE/50_theory_gate.py` (theory gate
  + 8-bit steering). PT Drum Pad app at `DRUM_PATTERNS/drumpad.html` (:8771).
- **Taste→groove→generate loop closed (2026-06-22).** `49_sig_one.py` embeds any single MIDI into
  the live space; `50_generate.py` route-C recombines empty-corner donor stems and scores them;
  `47_propagator.py` is the canonical taste propagator (→ `taste_pred_v2.parquet`, train on **v2
  ratings only**, n=131; only musicality/novelty/groove carry signal, groove r≈0.36); `48_active_pool.py`
  put 200 high-information songs on the phone.
- **Detection-accuracy pass merged (2026-06-20).** BPM (`tempos[0]` bug, 13.5% of corpus), real-meter
  recovery (`ts_final`), `felt_bpm` half/double, key-confidence (`key_corr`) all fixed and folded
  additively into the catalog. Ear-validated (BPM 60→80%, KEY 100%, TS 100%).

> ### ▶ HIGHEST-LEVERAGE NEXT ACTION — PATH B HANDOFF (do on Linux)
>
> **Ingest new MIDIs + tokenize corpus + fine-tune transformer.** Switch to Linux machine and run:
>
> **DO NOT train a big model from scratch. Use a pre-trained one and LoRA fine-tune on a small curated set.**
>
> **Step 1 — Ingest new files (prerequisite for everything)**
> ```bash
> .venv-linux/bin/python CODE/10_scan.py --apply --source MIDIS_TO_BE_INJESTED/   # 22 files smoke test
> .venv-linux/bin/python CODE/10_scan.py --apply --source MIDI_VIDEO_GAME/         # ~19,741 VGM files
> ```
> Then re-run pipeline steps 11→17, 22, 24, 25, 29, 31, 35, 26 to update catalog + N×88 signatures + kNN.
>
> **Step 2 — Download Giant Music Transformer (GMT)**
> ```bash
> pip install giantmusictransformer   # or clone https://github.com/asigalov61/Giant-Music-Transformer
> # Download model weights from huggingface.co/asigalov61/Giant-Music-Transformer
> ```
> GMT is 786M params, 8192-token context, already trained on LAMD (same dataset as this corpus).
> **Do not retrain it.** It already knows what music sounds like. This is the backbone.
> Has Text-to-Music mode (title-based), continuation, inpainting, composer modes.
>
> **Step 3 — Curate a small style dataset (20–100 MIDIs)**
> Use the 88-D corpus + catalog SQL to find songs matching the target style — do NOT hand-pick manually.
> Example query for "sad fingerpicked acoustic 3/4":
> ```sql
> SELECT md5, felt_bpm, key_v2, ts_final FROM catalog
> WHERE ts_final='3/4' AND key_v2 LIKE '%minor%'
>   AND felt_bpm BETWEEN 60 AND 100
>   AND quality_flag='ok' AND has_drums=0
> ORDER BY perc_diversity ASC LIMIT 50;
> ```
> Copy those MIDIs out as the LoRA training set. Consistency of style matters more than quantity.
>
> **Step 4 — LoRA fine-tune GMT on the small set**
> LoRA trains only a small adapter (~1-5% of model params) — fast, cheap, no big GPU needed.
> The adapter teaches GMT your specific style without overwriting its general music knowledge.
> GMT's repo has fine-tuning notebooks/scripts. ~30 min to a few hours on a single GPU.
> Output: `lora_adapter.pt` (small file, a few MB).
>
> **Step 5 — Generate**
> Load GMT + LoRA adapter → generate with a title prompt or seed MIDI.
> Example: title "Sad Waltz Acoustic Guitar" → GMT+LoRA → MIDI → render with FluidSynth.
> Later: seed generation from empty-space corner coordinates (use `49_sig_one.py` to find the
> nearest corpus MIDI to a target corner → use that as seed for GMT continuation).
>
> **Prior next actions (still valid, lower priority):**
> Rate active pool on phone → re-run `47_propagator` → `48_active_pool` (groove r≈0.36 bottleneck).
> Re-embed UMAP on N×88 (map is still N×74-era). Fold `taste_pred_v2` into `catalog.sqlite` as `v_good_empty`.
> **Data finding:** odd-meter groove (gypsy 11/8–11/16) is genuine empty space. Max Roach "minor trouble",
> Fela, and gypsy patterns are the strongest seed/anchor candidates.

> ### ⭐ STRATEGIC FRAME (why we measure coordinates, not genres)
> A classifier maps music into buckets that already exist — it describes the past and pulls toward
> the average. The north star (invent a new form of music) needs the opposite: a continuous coordinate
> space (the 88-D vector incl. GrooveDNA) where *gaps* are visible. A label says "this is rock";
> coordinates say "this sits here, and over *there* is empty — go make that." Core experiment =
> empty-space hunt on N×88, cross-referenced with taste, then generate a few candidates and **listen**.
> Keep archetypes only as ear-reference probes; don't build tools-for-tools.

---

## TWO INDEPENDENT LANES (do not cross)

- **(A) Corpus lane** — the `CODE/NN_*.py` pipeline. Normal work.
- **(B) NinjaStar-8 annotator** — a self-running phone-based by-ear rating tool. Only touches
  `ninjastar8.py`, `_work/ninjastar8_ratings.parquet`, `soundfonts/`, `web/`. **Corpus work must NOT
  touch those, and vice versa.** Live at <https://lab.tail0b3418.ts.net/> (Tailscale Serve HTTPS →
  `127.0.0.1:8780`, systemd service; HTTPS required for the in-browser synth). 8 bipolar sliders
  (groove/slaps/energy/peace_kill/lobrow_hibrow/simple_fancy/left_right/normie_weird, 0–8, 4=neutral).
  Ratings are md5-keyed and mergeable. Spec: `ANNOTATOR_SPEC.md`.

---

## GROUND TRUTH (verified 2026-06-16 — do not re-assume; checked on disk)

| Fact | Value | Implication |
|---|---|---|
| Parser in use | **TMIDIX** (`/home/t/datasets/LAMD/CODE/TMIDIX.py`) | House parser, ~33 ms/file. Reuse it. |
| `metadata.parquet` | 459,805 rows × ~201 cols | 4,091 files failed parse (in `catalog/meta_errors.log`); NOT in metadata. |
| Local `META_DATA/*.pickle` | 10 chunks, md5-keyed | Contain `total_pitches_counts`, `ms_chords_counts`, patch/timing/velocity stats for all rows. Signatures+chords are a *transform*, not a re-parse. |
| `NOTESEQ_DATA/` cache | per-bucket `(start,dur,chan,pitch,vel)` per file | Built by `21_sequences.py`; **nothing ever re-parses MIDI again** — all refine passes read here. |
| `master_manifest.parquet` | 463,896 rows (one per unique md5) | The full file list of record. Gap of 4,091 to catalog = failed/too-few-notes, by design. |
| Errors | 4,001 too-few-notes (≤32, policy reject) + 89 IndexError + 1 other + 1 zero-length | Only ~90 genuinely suspect; 90 quarantined (moved, never deleted). |
| Provenance names | LAMD/Lakh/bitmidi basenames are MD5 hashes; real names only for ragtime/maestro/personal (~38k) | Filename genre mining is a small targeted job, not corpus-wide. `sources` tags are NOISY — verify, don't trust. |

**Three rules the pipeline is built on:** (1) Don't re-parse for data already in the pickles/cache.
(2) ONE unified TMIDIX pass for genuinely-new features. (3) music21 is opt-in, subset-only; key
detection is numpy Krumhansl-Schmuckler.

**Resumability is a hard rule:** every per-file output is an md5-keyed parquet under `_work/`, so
re-running a step skips md5s already present. `MIDIs/` is never mutated (only `10_scan --apply`
moves files, into `_quarantine/`, never deletes). Paths: `MIDIs/<md5[:2]>/<md5>.mid`.

---

## WHAT THE CORPUS IS

One unified, deduplicated MIDI corpus organized like the LA MIDI Dataset (LAMD), built 2026-06-14
from every MIDI on `imac` + `lab` (personal + full LAMD + Lakh + BitMidi). One real copy per unique
song (full-content MD5 dedup); every original path preserved in the manifest.

- **Input inventoried:** 935,168 → **unique stored:** 463,896 (≈50% byte-identical dupes).
- Sources (pre-dedup): lamd 404,714 · lakh 354,962 · bitmidi 113,237 · lab_personal 21,672 ·
  2fast_existing 20,346 · imac_personal 15,387 · ragtime 3,574 · maestro 1,276.
- **Catalog:** 459,805 rows, every row has a `song_id` (378,923 distinct: 23,316 multi-arrangement
  clusters + 355,607 singletons) and a `split` (train 367,139 / val 46,106 / test 46,560, song-level
  no leakage). Pools: gold 239,126 / silver 133,173 / bronze 6,624 + genre/feature pools (manifests
  of stored paths, not copies).
- Column growth: 76 → 80 (audit-gap fixes) → 148 (rhythm/melody/harmony merge) → ~160 (GrooveDNA) →
  ~201 (tempo/meter/key v2 merge). All 5 audit-gaps (song_id, split, time_signature, bpm_valid,
  duration_suspect) fixed 2026-06-16 — see git history if details needed.

---

## DRUM VECTORS (rhythm is the #1 priority dimension)

- **GrooveDNA** (`29_groove_dna.py`) — canonical **11-D drum-only Rhythm Vector** per song, folded
  ×2-weighted into the 88-D combined signature for whole-corpus *clustering*. Drum isolation =
  `chan 9|10 AND GM pitch 35–81` (AND, not OR — melodic notes can't leak). Densities per-4/4-bar in
  beats (tempo-independent). No-drum songs → neutral 0.5. Real drum coverage = `perc_diversity > 0.5`
  = 67.7% (311,412 files). Output `_work/groove_dna.parquet`.
- **DrumDNA v1** (`31_drum_vector.py`) — **72-D standalone** drum signature with its own `.npy` +
  cosine kNN, for "find this exact feel". 20 scalars + 4 per-beat accents + 48-D per-voice 16-step
  onset grid. No kit → all-zero with `has_drums=0`. `_work/drum_dna.parquet`.
- **DrumDNA v2** (`35_drum_vector_v2.py`) — **468-D** research-standard upgrade: adds RhythmToolbox
  descriptors, full HVO grid (Hits/Velocity/Offset), 9-voice GM mapping. `_work/drum_dna_v2.parquet`.
- **Empty-space hunt (drum):** `32_drum_emptyspace.py` found 30 coherent-but-empty drum corners;
  `33_drum_catalog.py` folded 23 drum scalars onto the catalog for SQL feel-filtering.
- **TBB (Tony Bollas)** — the locked core groove signature (PT notation) for the new style being
  invented. Archetypes are ear-reference probes only; TBB is the generation seed. See
  `DRUM_PATTERNS/TONYBOLLAS_patterns.md`.

---

## LAYOUT

```
MIDIs/<2-hex>/<md5>.mid     deduped REAL copies, 256 buckets (md5[:2]) — READ-ONLY
_quarantine/<2-hex>/        90 genuinely-broken files (moved, never deleted)
META_DATA/                  LAMDa-compatible [md5, data] pickles (aggregate stats)
NOTESEQ_DATA/               per-bucket note-sequence cache — never re-parse MIDI
SIGNATURES_DATA/            signatures.npy (N×36 pitch) + signatures_ext.npy (N×88) +
                            signatures_md5.txt + knn_cosine.pkl + drum variants + *.bak
catalog/
  master_manifest.parquet   md5 -> stored_path, sources, original_paths[], song_id
  metadata.parquet          ~201 per-file features
  catalog.sqlite            metadata + manifest; views below
  checkpoints/              timestamped sqlite snapshots before each rebuild
TOKENIZED/                  {train,val,test}_manifest.tsv (song-level 80/10/10)
pools/                      *.tsv quality/genre/feature pools (pointers, not copies)
_work/  _logs/  _stats/     pipeline outputs, logs, stats
CODE/                       numbered, ordered pipeline (see PROVENANCE)
DRUM_PATTERNS/              PT notation, TBB, drumpad.html
```

SQLite views: `catalog` (clean default), `catalog_all` (incl. quarantined), `v_clean`,
`v_canonical` (one file per song), `v_with_lyrics`, `v_classical`, `v_solo_piano`, `v_no_drums`.

---

## HOW TO USE IT

**SQL:**
```bash
sqlite3 catalog/catalog.sqlite "SELECT key, count(*) c FROM catalog GROUP BY key ORDER BY c DESC LIMIT 10;"
```

**Find similar (vectorized, rhythm-aware):**
```python
import numpy as np, pickle
ext  = np.load("SIGNATURES_DATA/signatures_ext.npy")            # N x 88
md5s = open("SIGNATURES_DATA/signatures_md5.txt").read().split()
P = pickle.load(open("SIGNATURES_DATA/knn_cosine.pkl","rb"))    # {nn, fit_rows, block_dims, weights, ...}
row = md5s.index("<md5>")
d,i = P["nn"].kneighbors(ext[row:row+1], n_neighbors=11)
print([md5s[j] for j in i[0] if j != row])                      # 10 nearest (rhythm/groove ×2)
```
Re-tune pillar weights: `python3 CODE/26_signature_extend.py --w-rhythm N` (`--dry-run` to preview).
Legacy pitch-only ratio search: `python3 CODE/04_search.py --out-root . --query /path.mid --top 10`.
Embed a NEW/external MIDI into the live space: `CODE/49_sig_one.py`.

**Generate:**
```bash
.venv-linux/bin/python CODE/50_generate.py --style "death metal with blast beats" \
  --seed-md5 <MD5> --novelty high --catchy --iterations 2 --group death_metal_demo
.venv-linux/bin/python CODE/51_remix.py --pattern-from <MD5> --new-melody --variants 6 \
  --enhance chiptune --group coherent_remix          # add --advanced --reharm all for EIS reharm
```

---

## PIPELINE / CODE PROVENANCE (in CODE/, numbering encodes dependency order)

Read `CODE/_common.py` before writing a new step (paths, GM maps, `META_FIELDS`, logging) and match
its conventions.

- **v1 build:** `02_make_dataset` (dedup+store+manifest) · `03_make_metadata` · `04_search` · `05_tokenize` · `06_enrich_pop60s`.
- **v2 enrichment** (`bash CODE/run_all.sh`): `10_scan` (the one TMIDIX parse) · `11_features` · `12_signatures` (N×36 pitch + near-dup clusters) · `13_chords` · `14_provenance` · `15_catalog` · `16_splits_pools` · `17_stats`.
- **v3 rhythm-first re-parse & vectorize:** `18_fill_song_id_and_split` + `19_quality_flags` (audit-gap fixes) · `21_sequences` (TMIDIX re-parse → `NOTESEQ_DATA/`) · `22_rhythm_refine` · `24_melody_refine` · `25_harmony_refine` · `23_catalog_merge` · `26_signature_extend` (→ `signatures_ext.npy` N×88 + refit kNN) · `27_emptyspace` (empty-space hunt) · `29/31/35` (GrooveDNA/DrumDNA) · `32/33` (drum empty-space + catalog) · `41/43/44` (corrected tempo/meter/key + merge) · `47_propagator` · `48_active_pool` · `49_sig_one` · `50_generate` + `genre_engine` + `50_theory_gate` · `51_remix`.

---

## OPEN CONCERNS / KNOWN LIMITATIONS

None block current use; all are candidates for the next approved pass.

- **GrooveDNA #1 — no one-drop/accent-placement dim.** `snare_backbeat_strength` only measures snares
  on beats 2&4, so a reggae one-drop (accent on beat 3) reads backbeat=0 and looks like kick-on-1.
  Fix when approved: a downbeat-vs-beat-3 accent balance dim (→ would make it N×86).
- **GrooveDNA neutral 0.5 is overloaded** — no-drum songs AND undefined sub-features both fill 0.5.
  Use `perc_diversity > 0.5` (or v1 DrumDNA `has_drums`) for a clean drum mask.
- **Rhythm up-weight ×2 is a guess** — validate empirically against known arrangement clusters.
- **Two "tune-later" harmony reads** (`harmonic_rhythm` med 2.82, `n_key_areas` med 6.0) — smoothing /
  `key_stability` re-derivable from `NOTESEQ_DATA`, no re-parse.
- **Detection-accuracy follow-ups** — re-derive per-bar drum metrics on clean bars; optional onset-based
  meter *inference* for ~33k junk-`1/4`/missing-meter files. Entropy is a poor complexity measure for
  blast beats (all-16th kick → max entropy but most regular) — prefer bar-to-bar variance.
- **MCP groove library is v0.1** — techno/trap/funk/broken/shuffle are UNVERIFIED and not generated;
  no real-MIDI→archetype matcher yet. Generated `*.mid` are gitignored (regenerate via `30_mcp_groove`).
- **Re-cluster `song_id` with the richer 88-D sig** — current dedup used pitch-only 36-D and over-merges;
  a deliberate backed-up rebuild (re-verify splits don't leak).
- **Phase 10 maintenance scripts** still pending — `validate_new.sh`, `rebuild_catalog.sh`,
  `rebuild_pools.sh`, `stats_report.sh`; fold `26_signature_extend` into a reproducible rebuild.

---

## SESSION LOG (append-only, newest first — one line each; full prose in git history pre-2026-06-25)

- **2026-06-29** — Linux session (Cursor/Opus): **PATH B EXECUTED end-to-end — GMT + fine-tune now runs locally on the RTX 3060.** (1) Ingest: dedup-ingested `MIDI_VIDEO_GAME/` (19,736) + `MIDIS_TO_BE_INJESTED/` (22) via `02_make_dataset.py` (added a `vgm`/`inject` source tag) → manifest 463,896→**463,906**; the entire VGM set was byte-identical dupes, only **10 new uniques** (all inject seeds: Max Roach minor-trouble/sandu, Monk off-minor/ruby, Fela lady/water, Bach BWV1043, Kinks come-dancing, Neil Young, oxygen_fixed). 10_scan refreshed (463,907). NOTE: documented `10_scan --source` flag doesn't exist; base pipeline 11→17 derives from `META_DATA` pickles that exclude new files, so full catalog citizenship of the 10 seeds is deferred (needs from-scratch rebuild; 9/10 already in `signatures_ext.npy` from the 06-25 ad-hoc embed). (2) GPU: RTX 3060 12GB driver 580/CUDA13 works — only the agent sandbox hid `/dev/nvidia*` (run GPU cmds outside sandbox). Installed `torch==2.12.1+cu130`+einops into `.venv-linux`. (3) GMT: cloned repo + downloaded **Large 585M** ckpt (2.34GB) to `GMT/repo/Models/Large/`. (4) Curated **100 canonical odd-meter (5/4,7/4) groove** MIDIs (drums+bass, top groove_composite, the north-star empty-space region) → `GMT/style_oddmeter_groove/`, tokenized to GMT INTs (2.07M toks) `_work/gmt_style_oddmeter.pickle`. (5) Partial fine-tune (last-8 layers, fp16, lr1e-5, seq2048 b2×accum6, 750 steps ≈5 epochs, 36 min, peak 6.7GB) → `GMT/finetuned/oddmeter_groove.pth`. (6) Generated styled improv (4) + Max-Roach seed continuations (3) → `_work/gmt_styled/*.mid`+`.wav` (GeneralUserGS.sf2). New tools (gitignored): `GMT/gmt_generate.py`, `GMT/tokenize_style.py`, `GMT/gmt_finetune.py`, `GMT/score_outputs.py` (88-D placement of outputs), `GMT/eval_loss.py` (held-out token loss). **EVALUATION VERDICT (same session): fine-tuning GMT on this corpus is a dead end — do not repeat.** GMT was trained on LAMD (which *contains* these songs) so the style is in-distribution. Held-out loss on 50 UNSEEN odd-meter songs: base **0.5198** / acc .869 → v1 (last-8, lr1e-5, 100 songs) **0.5174** (negligible) → v2 (last-12, lr5e-5, 427 songs) **0.5223** (slightly WORSE — mild overfit/forgetting). Also: free-improv (base or ft) lands at ~0.04 cos to the target 88-D cluster, BELOW random (0.105) — a style stamp does NOT make free-gen hit a coordinate; only SEEDING does. And 88-D scoring of short GMT fragments is unreliable: GMT tokenize→decode round-trip drops a real song's self-cos 1.0→0.51 (timing ×16 + octa-velocity quantization). **NEXT (recommended pivot): stop fine-tuning; use BASE GMT as the engine + coordinate-driven SEEDING into empty corners (49_sig_one → nearest corpus MIDI to a 27_emptyspace target → GMT continuation) + taste-rank the candidates. Listen to `_work/gmt_listen/groove54_*.wav` (full ~80s seeded songs).**

- **2026-06-29** — Windows session (Copilot): Git hygiene — consolidated all branches (grok/4-pillars, drum-signature-v1, groove-taste-loop) into main and pushed; workflow going forward = pull at start / push at end on main only. Discovered `MIDI_VIDEO_GAME/` (~19,741 MIDIs) and `MIDIS_TO_BE_INJESTED/` (22 MIDIs) uningested. Fixed 10 Windows-broken folder names with trailing periods (F.O.F.T., W.A.R., etc.) via .NET Directory.Move + \\?\ prefix. Inspected `MIDI_VIDEO_GAME/_dataset/`: fully pre-processed VGM pipeline (features, 32-D embeddings, REMI+BPE tokenizer vocab=20k, nanoGPT ckpt.pt). **Strategy updated:** do NOT train a big model — download Giant Music Transformer (786M, already trained on LAMD) + LoRA fine-tune on 20-100 curated corpus MIDIs for target style. Model is a commodity; the 88-D coordinate map + taste labels is the moat. See NEXT ACTION for full 5-step plan.

- **2026-06-28** — Windows session (Copilot): inspected `oxygenMIDIREAL82bpm_...mid` (Logic Type-1, 82 BPM, G#m, 7 tracks all ch=0, no prog changes). Fixed channel assignments (drums→ch9, bass→ch1-3 prog38 Synth Bass 1, key sig G#m) → `MIDIS_TO_BE_INJESTED/oxygenMIDIREAL82bpm_Gsharpm_fixed.mid`. User confirmed `oxygenMIDIREAL82bpm_DRUM&BASS_FINAL.mid` (Type-1, ch9 drums, prog80 8-bit square bass, 82 BPM, 384 tpb) is the correct final version — do not modify. Generated PCA 2D corpus plot → `_stats/corpus_pca2d.png` (PC1=20.8%, PC2=8.5%; main blob + separate right lobe visible). Catalog search: 357 songs matching G#m/Abm 75-90 BPM 4/4 has-drums; top 20 (78-86 BPM + has bass) copied to `similar_oxygen/`. Generation (50_generate/51_remix) deferred to Linux — TMIDIX PyPI v26.x has Windows circular-import bug; local TMIDIX.py is at `B:\Music_Audio\MIDI\Advanced-MIDI-Renderer\TMIDIX.py`. LAMD_CODE path in `_common.py` hardcoded to Linux (`/home/t/datasets/LAMD/CODE`).
- **2026-06-28** — Phase 8 loop batch: 6 fresh v3 corners (e.g. 8f5b21f2, b2d46425, ab458f6f, 559c65e8, 4bc8ec10, 4b506bdd) generated 12 tracks (2 each, jazz-fusion indep voices style, --novelty med, genre drums). Auto-added to local webplayer :8765 group grok4p_loop (now ~913 tracks). More batches queued. See grok_progress/phase8*. BG continues for hours.
- **2026-06-27** — Phase 0 complete (GROK_BUILD_PLAN): reverted parser hygiene, shelved off-target asigalov61 artifacts to _work/grok_progress/shelved/, noted midichords for P2 validator, cleaned multi-line block from CURRENT STATUS into single log line + phase0.md. On grok/4-pillars; starting 4-pillar deepen (counterpoint #1).
- **2026-06-27** — Phase 1 (counterpoint): CODE/60_counterpoint.py written + pilot on bucket 00 (1797 rows, 0 errors final, med n_indep=2, high imitation/contrary tails exist). Resumable parts+done md5. phase1.md + STATE log.
- **2026-06-27** — Phase 2 (harmony deepen): CODE/61_harmony_deep.py + pilot bucket00 → _work/harmony_deep.parquet (1797 rows, chord qual ratios + func T/S/D + tension curve + voicing/spread). No errors. phase2.md. midichords crosscheck note preserved.
- **2026-06-27** — Phase 3 (melody): 62_melody_deep.py pilot 00 done (contour/phrase/call/seq/complex/predict/range). phase3.md.
- **2026-06-27** — Phase 4 (rhythm patch): groove_rhythm_patch.parquet (accent_balance, bar_var, polyr) for 200 md5s pilot. Additive, resumable. phase4.md.
- **2026-06-27** — Phase 5 (v3 sig): 63_signature_v3.py built balanced (pitch1.0/r/h/ctr/mel 1.2 each) -> signatures_ext_v3.npy + knn_v3.pkl (86D); live .bak_*_v3 written, never touched. Roundtrip 1.0. phase5*.md + code commit.
- **2026-06-27** — Phase 6/7/8 start: corners_v3 + taste_v3 + first gen batch (4 cands) into rare v3 corner via 50_generate (auto local webplayer grok4p_v3, no TBB). Loop continues. phase* + batch log.
- **2026-06-27** — Phases 0-9 complete (GROK_BUILD_PLAN end-to-end, safe v* + .bak, .venv, resumable pilots/full, branch grok/4-pillars only). Phase8 gen loop active in bg (more batches to local webplayer). See _work/grok_progress/*.md . No main touch, no ninjastar.
- **2026-06-25** — Ingested 9 new seed MIDIs (Max Roach minor-trouble/sandu, Fela lady/water-no-get-enemy, Monk off-minor/ruby-my-dear, Bach BWV1043, Kinks come-dancing, Neil Young alt) from `MIDIS_TO_BE_INJESTED/` → warehouse + embedded into `signatures_ext.npy`/`signatures_md5.txt` (**459,805 → 459,814 rows**; backups `*.bak_20260625_234318`). NOT yet in `catalog/metadata.parquet` (still 459,805), `knn_cosine.pkl`, or UMAP map — those need a rebuild for full citizenship. Generated `--style` candidates from these seeds (genre-default drums; user nixed forcing the TBB beat — "doesn't work with most things"). Other 12 of the 21 files were already in-corpus dups.
- **2026-06-25** — FLAGSHIP: unified `--style` song engine (`genre_engine.py` + `50_generate.py`) + PT drum-pad app (`drumpad.html`).
- **2026-06-25** — Coherent remix `51_remix.py` (donor backing + key/chord-fitted melody from corpus/new/user).
- **2026-06-25** — Advanced remix `51_remix.py --advanced`: EIS reharmonization (ext/sub/dsub/iiv/nct) + strict voice leading (~2.2 vs ~11.5 semitones/change), 3-way A/B render.
- **2026-06-24** — "In the style of a liked song" mode (`--like-md5`).
- **2026-06-24** — Phrase-level recombination (candidates stop hugging the donors).
- **2026-06-24** — Theory gate + 8-bit steering live (`50_theory_gate.py`).
- **2026-06-23** — KS8 brute-force kick+snare skeleton permutation hunt (shortlists in `DRUM_PATTERNS/`).
- **2026-06-22** — Closed the taste→groove→generate loop: `49_sig_one` (embed one MIDI, cos 1.0000), route-C `50_generate`, canonical `47_propagator` (→`taste_pred_v2`), `48_active_pool` (200-song phone pool, 286 ratings preserved).
- **2026-06-22** — TBB drum-signature lane: atlas + 8 candidates → **TBB v1 LOCKED** ("5-5-6 gallop clave"), `tbb_cos` feature + versioned sig (additive), `--force-drum TBB` gens, tbb_anchored target + pool, tbb_style_v1 (10 anchored songs).
- **2026-06-20** — Detection-accuracy pass (BPM/meter/key v2) merged → ~201 cols; signature/kNN rhythm block refreshed → **N×88**; empty-space hunt re-run on N×88; docs swept to 88-D.
- **2026-06-19** — SQL Server LocalDB live; catalog migrated to `dbo.metadata`. Ear-vs-DB calibration notes (blast-beat entropy, 7/8+11/8 gypsy meter).
- **2026-06-18** — GrooveDNA (11-D) built+merged; DrumDNA v1 (72-D) + v2 (468-D) standalone sigs + kNN; MCP groove notation; drum empty-space hunt; two UMAP music-space maps; Grok-supervised live pool swap (v2) + taste-propagator stub.
- **2026-06-17** — **VECTORIZED (finish line):** re-parse→`NOTESEQ_DATA`, rhythm/melody/harmony refine, catalog merge (→148 cols), `26_signature_extend` → `signatures_ext.npy` (N×74 at first build) + cosine kNN. Plus: empty-space hunt #1, UMAP map + clickable player, 3D galaxy + corner overlay + ♥Like, Taste Duel game, NinjaStar-8 annotator (MIDI-first, HTTPS, offline-resilient).
- **2026-06-16** — Recovery + doc consolidation; all 5 KNOWN GAPS fixed; Phase 9.1 audio sanity render (0 silent/0 errors) + wrote MANUAL.md.
- **2026-06-28** — User text beat "khhhshhhkhhhshhhkhkhshhhkhkhssss" rendered as pure drum loop: 32-step (2-bar 16th grid) → 4 bars @82bpm, k=36 kick / h=42 closed hat / s=38 snare on ch9. MIDI + WAV in _work/generated/khhhshhh_82bpm_beat.{mid,wav}. Added to webplayer group khhhbeat. PT equiv: Bar1 (K)(H)(H)(H)(S)(H)(H)(H)(K)(H)(H)(H)(S)(H)(H)(H) | Bar2 (K)(H)(K)(H)(S)(H)(H)(H)(K)(H)(K)(H)(S)(S)(S)(S). Literal match.
- **2026-06-28** — Phase 8 loop batch: 6 fresh v3 corners (e.g. 8f5b21f2, b2d46425, ab458f6f, 559c65e8, 4bc8ec10, 4b506bdd) generated 12 tracks (2 each, jazz-fusion indep voices style, --novelty med, genre drums). Auto-added to local webplayer :8765 group grok4p_loop (now ~913 tracks). More batches queued. See grok_progress/phase8*. BG continues for hours.
- **2026-06-28** — Phase 8 persistent loop: launched clean driver (target 120 batches, fresh random corners from corners_v3 each iter, pillar-focused styles, --novelty med, keep-drums, group grok4p_loop). Previous extended loop had quoting failure (exit 2 after 5s, no new gens from that spawn). Local webplayer only. See phase8_persistent.log + driver. Continues for hours.
- **2026-06-28** — Phase 8: explicit batch 4 fresh corners (2513028f, e4e594b0, 9531a931, db3a0475) → 8 tracks to local webplayer grok4p_loop (now 931). Python driver (1601895) alive at #6+, 02:25 elapsed, continuing to 120. Bash loop quoting failure noted. More hours queued.
