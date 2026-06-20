# MANUAL — How This Whole Thing Works

*A plain-language guide to the MIDIS_ALL_REAL corpus. Read it as many times as you
want; it's built to make more sense each pass. STATE.md is the "what's the current
status" file — THIS file is the "how do I think about it" file. Where a number here
could drift (signature size, column count), STATE.md is the source of truth.*

---

## 0. The one sentence

> **You have ~460,000 songs turned into numbers, laid out in a giant space, so a
> computer can measure how music is similar or different — and so we can go hunting
> for the empty spots where no music exists yet.**

That last part is the whole point: **the goal is to invent a new form of music.**
Everything below is machinery in service of that.

If you only remember one image, remember this:

> Every song is a **dot floating in a room**. Similar songs sit near each other.
> Most of the room is crowded. We're looking for the **empty corners**.

Read on when you want to know *why* that image is true.

---

## 1. What we actually have (the raw material)

We gathered every MIDI file off your machines + the big public datasets (LAMD, Lakh,
BitMidi) — **935,168 files**. About half were exact duplicates (the same file copied
around), so we kept **one real copy of each unique song: 463,896 files.**

- Stored in `MIDIs/`, split into 256 folders by the first 2 letters of each file's
  fingerprint. Read-only. We never delete or rename the originals' info.
- Every file has an **md5** — a 32-character fingerprint of its exact contents.
  Two files with the same md5 ARE the same file, byte for byte. This md5 is the
  "name" we use for everything. (For most files the *filename* is just this hash —
  the original human names were lost long ago, except for ~38k named ones.)

**Mental model:** `MIDIs/` is the warehouse. One shelf per song. The md5 is the
barcode. Nothing creative happens here — it's just clean, deduplicated storage.

---

## 2. The catalog (the spreadsheet about every song)

We can't *listen* to 460k files to know what they are. So we measured each one and
wrote the measurements into a giant spreadsheet.

- `catalog/metadata.parquet` and `catalog/catalog.sqlite` — same data, two formats.
- **459,805 rows** (one per song; the ~4,000 missing ones were too short/broken to
  measure — they're logged, not lost).
- **~200 columns** (201 as of 2026-06-20 — it keeps growing as we add measurements;
  check STATE.md for the live count). It started at 80, grew to 148 with the
  rhythm/melody/harmony re-parse, then to ~160 with GrooveDNA drum metrics, then to
  201 when the corrected tempo/meter/key columns were merged. Things like:
  - `key`, `mode`, plus corrected `key_v2` / `key_corr` (is it C major? A minor? how sure?)
  - `duration_sec`, `bpm`, plus corrected `bpm_v2` / `felt_bpm` (how long, how fast)
  - `time_signature` + corrected `ts_final` (the meter, ear-validated)
  - `note_density`, `polyphony_density` (busy or sparse?)
  - `pitch_class_entropy` (how chromatic/unpredictable are the notes?)
  - `n_unique_chords`, `chord_density` (harmonic richness)
  - `syncopation`, `swing_bur`, `tempo_class`, `mel_stepwise_ratio` (rhythm & melody)
  - `drum_kick_density`, `drum_snare_backbeat`, `drum_swing`, … (GrooveDNA drum feel)
  - `quality_flag`, `bpm_valid`, `duration_suspect` (is this measurement trustworthy?)
  - `split` (train/val/test), `song_id` (see section 5)

**Mental model:** a spreadsheet with 459,805 rows and ~200 columns. You can sort,
filter, and ask questions like "show me all the minor-key songs with lyrics, longest
first." That's what SQL does (`catalog.sqlite`). See section 7 for how to ask.

> A "pristine, trust-it-fully" subset is:
> `WHERE quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0`.
> For tempo/meter/key prefer the corrected columns: `bpm_v2`/`felt_bpm`, `ts_final`,
> `key_v2`+`key_corr`.

---

## 3. The signature: turning a song into a list of numbers

The catalog describes songs in *words/categories*. But to do **math** on music — to
measure "how close are these two songs" — we need each song to be a **list of pure
numbers of the same length.** That fixed-length list of numbers is the **signature**.

There are two signature files:

- `SIGNATURES_DATA/signatures.npy` — **459,805 × 36**, the ORIGINAL pitch-only label
  (kept untouched). Four little "profiles" stuck together:

  | numbers | profile | plain meaning |
  |---|---|---|
  | 1–12  | **which notes** | of the 12 notes (C, C#, D … B), how much is each used? |
  | 13–24 | (same again — weighted-by-note-length placeholder) |
  | 25–30 | **intervals** | what *gaps* between notes — smooth steps? big leaps? tritones? |
  | 31–36 | **chord sizes** | single notes, or fat 5–6 note stacks? |

- `SIGNATURES_DATA/signatures_ext.npy` — **the one we actually use, 459,805 × 88**
  (as of 2026-06-20; see STATE.md for the live width). It's the pitch label above
  **plus four more panels** stapled on, because the original 36 said nothing about
  **rhythm** — the single most important dimension here. The 88 numbers are five
  "pillars":

  | dims | pillar | what it captures |
  |---|---|---|
  | 36 | **pitch** | the original notes/intervals/chords label |
  | 20 | **rhythm** ×2 | syncopation, swing, triplet/dotted feel, tempo shape, **corrected perceptual tempo (`felt_bpm`) and meter (`ts_num`/`ts_compound`)** |
  | 13 | **melody** | contour: steps vs leaps, range, phrasing, chromaticism |
  | 8  | **harmony** | chord change rate, harmonic rhythm, extended harmony |
  | 11 | **groove (GrooveDNA)** ×2 | drum-only feel: kick/snare/hat density, backbeat, swing, ghosting |

Each profile is scaled to proportions (not raw counts) and per-pillar normalized, so a
30-second sketch and a 10-minute epic in the same style get almost the same signature.
**Rhythm and groove are deliberately weighted ×2** so two songs that share a groove
land near each other even if their notes differ.

**Mental model:** the signature is a song's **nutrition label.** Two brands of the
"same" cereal have nearly identical labels; two wildly different foods have very
different ones. We turned every song into its label so we can compare 460,000 at once.

> Built by `CODE/26_signature_extend.py` (re-runnable in seconds; weights are CLI
> knobs). The 36-D pitch file is a *reshaping* of counts already in `META_DATA/`; the
> rhythm/melody/harmony/groove pillars come from the one-time full re-parse
> (`NOTESEQ_DATA/` cache) — never re-parsed again.

---

## 4. The space, and "nearest neighbors" (the heart of it)

Here's the leap that makes everything click.

A list of 2 numbers is a point on paper (x, y). A list of 3 is a point in a room
(x, y, z). A list of **88** numbers is a point in an **88-dimensional room** — you
can't picture it, but the *math works exactly the same.*

So our 459,805 signatures are **459,805 dots floating in an 88-dimensional room.** The
extra dimensions beyond pitch are rhythm, melody, harmony, and groove — everything
below works identically regardless of how many axes there are.

- Songs that sound alike → their labels are alike → their dots are **close together.**
- Songs that are very different → their dots are **far apart.**

"Close" is measured with **cosine similarity** — do the two labels *point the same
direction?* Cosine = 1.0 means "essentially the same flavor"; lower means "more
different."

**k-Nearest Neighbors (kNN)** is just: *"given one dot, find the k dots sitting
closest to it."* You hand it a song, it finds the most musically-similar songs in the
corpus in a fraction of a second. `SIGNATURES_DATA/knn_cosine.pkl` is the pre-built
"find-nearby-dots machine" — an **exact** cosine index fit over **all 459,805 rows**
of the 88-D space, so neighbors share rhythm/groove, not just notes. (The old
`CODE/04_search.py` is a separate, slower **pitch-only** matcher kept for reference;
for rhythm-aware neighbors use `knn_cosine.pkl` + `signatures_ext.npy` — see §7.)

**Mental model:** imagine all 460k songs as **stars in a galaxy.** Similar songs form
**constellations.** kNN is pointing at one star and asking "what are its neighbors?"
That's similarity search, recommendation, and de-duplication all at once.

---

## 5. song_id: same tune, different arrangements

Some "different" files are really the *same song* — a piano version and a full-band
version of the same tune. Byte-for-byte they differ (so md5 dedup keeps them both),
but musically they're siblings.

We used the signatures to find these sibling groups (dots almost on top of each other)
and gave each group a shared **`song_id`.** ~23,316 real multi-arrangement clusters
were found; every other file is its own one-member group. **378,923 distinct
song_ids total.**

Why it matters: when training a model you must not let a song's piano version sit in
"train" while its band version sits in "test" — that's cheating. Grouping by `song_id`
keeps all arrangements of one tune on the *same side* of the split. Done **carefully
to avoid over-merging** (a dumb version would collapse thousands of simple C-major
songs into one blob — we have guards against that).

**Mental model:** md5 = "is this the exact same recording?" song_id = "is this the
same *song*, even in a different outfit?"

---

## 6. WHY all this — the new-music idea

Now the payoff. You have a galaxy of 460k musical dots. Here's the creative move:

**Most of the galaxy is crowded.** Huge dense blobs of "4/4 diatonic triadic pop/rock
music" — because that's what most MIDI is. But an 88-dimensional room is *enormous*,
and most of it is **empty.** Those empty regions are combinations of notes / rhythms /
chord-shapes / grooves that are perfectly coherent but that **almost no human music
has ever occupied.**

> **A new form of music = a populated region of this space that is currently empty.**

So the plan isn't "imitate the crowd" (that's what normal AI music does — it samples
the dense blobs and gives you more of the same). The plan is:

1. **Map** where the dots are dense and where they're empty.
2. **Pick an empty-but-coherent corner** — a target coordinate.
3. **Generate music aimed at that coordinate** instead of at the crowd.

That turns the vague wish "make something new" into a **concrete address in a space**
you can point a generator at.

> **The empty-corner hunt exists and has been run on the full 88-D space**
> (`CODE/27_emptyspace.py all` → `_work/emptyspace/`): 1200 clusters, plus 60 empty
> "blend" corners and 60 isolated rare pockets, each captioned in plain language
> (incl. meter + felt-tempo). Because the signature now includes rhythm, melody, and
> groove, the corners span **time-feel, not just notes.** The remaining frontier is
> step 3 — actually generating into a chosen corner (see STATE.md + TASKS_NEXT.md).

---

## 7. How to actually use it (cheat sheet)

**Ask the spreadsheet a question (SQL):**
```bash
sqlite3 catalog/catalog.sqlite
SELECT count(*) FROM catalog;                       -- how many songs
SELECT key, count(*) c FROM catalog GROUP BY key ORDER BY c DESC;   -- key distribution
-- minor-key, clean, with lyrics, longest first:
SELECT md5, key, duration_sec FROM v_canonical
  WHERE mode='minor' AND quality_flag='ok' AND has_lyrics=1
  ORDER BY duration_sec DESC LIMIT 20;
```
Handy pre-built views: `catalog` (clean default), `v_canonical` (one file per song),
`v_clean`, `v_with_lyrics`, `v_classical`, `v_solo_piano`, `v_no_drums`.

**Find songs similar to one you have (pitch-only, legacy):**
```bash
python3 CODE/04_search.py --out-root . --query /path/to/song.mid --top 10
python3 CODE/04_search.py --out-root . --md5 <md5-already-in-store> --top 10
```

**Load it in Python** (use the `.venv-linux` uv venv — never bare pip):
```python
import pandas as pd, numpy as np, pickle
meta = pd.read_parquet("catalog/metadata.parquet")        # the ~200-col spreadsheet
sigs = np.load("SIGNATURES_DATA/signatures.npy")          # 459805 x 36 (pitch-only, original)
ext  = np.load("SIGNATURES_DATA/signatures_ext.npy")      # 459805 x 88 (pitch+rhythm+melody+harmony+groove)
md5s = open("SIGNATURES_DATA/signatures_md5.txt").read().split()  # row i -> which song

# rhythm-aware nearest neighbors of one song:
P   = pickle.load(open("SIGNATURES_DATA/knn_cosine.pkl", "rb"))   # {nn, fit_rows, block_dims, weights, ...}
row = md5s.index("<some_md5>")
d, i = P["nn"].kneighbors(ext[row:row+1], n_neighbors=11)
neighbors = [md5s[j] for j in i[0] if j != row]           # 10 most similar (rhythm & groove count ×2)
```

**Hear something:** any rendered audio →
`webplayer add <file-or-dir> && webplayer open`. (When loading a *ranked* set, add in
reverse so rank #1 is the newest-added file.)

---

## 8. The glossary (when a word trips you up)

- **MIDI** — a file that stores the *notes/instructions* of music (which note, when,
  how hard), not the actual sound. Like sheet music for a computer.
- **md5** — a 32-char fingerprint of a file's exact bytes. Same md5 = identical file.
- **corpus** — the whole organized collection of songs.
- **catalog / metadata** — the spreadsheet of measurements about every song.
- **parquet / sqlite** — two file formats holding that spreadsheet (one for Python,
  one for SQL queries). Same data.
- **signature** — the "nutrition label" of one song. Pitch-only original = 36 numbers;
  the one we use = **88** (pitch + rhythm + melody + harmony + groove) in
  `signatures_ext.npy`.
- **pillar** — one panel of the signature (pitch / rhythm / melody / harmony / groove);
  rhythm and groove are weighted ×2.
- **dimension** — one number in the list. 88 numbers = 88 dimensions = a point in
  "88-D space." Can't be pictured, behaves like a point.
- **vector / matrix** — a vector is one row of numbers (a dot); a matrix is many rows
  stacked. `signatures_ext.npy` is a 459805×88 matrix (the pitch-only
  `signatures.npy` is 459805×36).
- **cosine similarity** — a way to measure if two number-lists "point the same way";
  1.0 = same direction/flavor.
- **kNN (k-nearest neighbors)** — "find the k closest dots to this one."
- **GrooveDNA** — the drum-only feel pillar (11 numbers); also its own standalone
  drum-similarity index (`signatures_drums*.npy`).
- **song_id** — groups different arrangements of the same underlying tune.
- **split (train/val/test)** — partitioning songs for machine learning so the model
  is tested on songs it never trained on.
- **embedding / latent space** — fancier future version of "the space of dots," where
  the numbers are *learned* by a neural net instead of hand-defined. Same mental
  model: songs as dots, near = similar, empty = unexplored.

---

## 9. The five things to actually internalize

1. **Every song is a dot in a space** (a list of 88 numbers / its "nutrition label").
2. **Near = similar, far = different**, and we measure it with cosine + kNN.
3. **The space is mostly empty.** The crowd is normal music.
4. **A new form of music = filling an empty corner** of that space on purpose.
5. **Everything else (warehouse, spreadsheet, song_id, splits) is plumbing** that
   keeps the data clean and honest so step 4 is possible.

If those five land, you've got it. Re-read 1–6 whenever a detail slips; re-read 9
when you just need the gist.
