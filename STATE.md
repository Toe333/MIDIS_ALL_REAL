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

> ### ▶ HIGHEST-LEVERAGE NEXT ACTION (it's human)
>
> **Rate the 200-song active pool on the phone, then re-run `47_propagator.py` → `48_active_pool.py`**
> to tighten the groove taste model — it's the bottleneck (groove r≈0.36). Open engineering, in
> priority order: (a) re-embed UMAP on N×88 + mapserver with taste tint + corner overlay (the visual
> map is still N×74-era); (b) fold `taste_pred_v2` into `catalog.sqlite` as view `v_good_empty`;
> (c) **stretch** — theory-steered generation to push *into* empty space instead of hovering at its
> rim (currently route-C only reaches the empty corner's rim, which is empty by construction).
> **Data finding:** odd-meter groove (gypsy 11/8–11/16) is genuine empty space — every such pattern
> maps nearest to a 4/4 corpus song. Max Roach "minor trouble", Fela, and gypsy patterns are the
> strongest seed/anchor candidates.

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

- **2026-06-27** — Phase 0 complete (GROK_BUILD_PLAN): reverted parser hygiene, shelved off-target asigalov61 artifacts to _work/grok_progress/shelved/, noted midichords for P2 validator, cleaned multi-line block from CURRENT STATUS into single log line + phase0.md. On grok/4-pillars; starting 4-pillar deepen (counterpoint #1).
- **2026-06-27** — Phase 1 (counterpoint): CODE/60_counterpoint.py written + pilot on bucket 00 (1797 rows, 0 errors final, med n_indep=2, high imitation/contrary tails exist). Resumable parts+done md5. phase1.md + STATE log.
- **2026-06-27** — Phase 2 (harmony deepen): CODE/61_harmony_deep.py + pilot bucket00 → _work/harmony_deep.parquet (1797 rows, chord qual ratios + func T/S/D + tension curve + voicing/spread). No errors. phase2.md. midichords crosscheck note preserved.
- **2026-06-27** — Phase 3 (melody): 62_melody_deep.py pilot 00 done (contour/phrase/call/seq/complex/predict/range). phase3.md.
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
