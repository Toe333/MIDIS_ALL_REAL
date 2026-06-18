# MANUAL — How This Whole Thing Works

*A plain-language guide to the MIDIS_ALL_REAL corpus. Read it as many times as you
want; it's built to make more sense each pass. STATE.md is the "what's the current
status" file — THIS file is the "how do I think about it" file.*

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
- **148 columns** — the measurements (grew from 80 when the 2026-06-17 rhythm/melody/
  harmony re-parse merged in; see STATE.md). Things like:
  - `key`, `mode` (is it in C major? A minor?)
  - `duration_sec`, `bpm` (how long, how fast)
  - `note_density`, `polyphony_density` (busy or sparse?)
  - `pitch_class_entropy` (how chromatic/unpredictable are the notes?)
  - `has_bass`, `has_pad`, `is_solo` (what instruments)
  - `n_unique_chords`, `chord_density` (harmonic richness)
  - `syncopation`, `swing_bur`, `tempo_class`, `mel_stepwise_ratio` (rhythm & melody — the new pillars)
  - `quality_flag`, `bpm_valid`, `duration_suspect` (is this measurement trustworthy?)
  - `split` (train/val/test — for machine learning)
  - `song_id` (see section 5)

**Mental model:** a spreadsheet with 459,805 rows and 148 columns. You can sort,
filter, and ask questions like "show me all the minor-key songs with lyrics, longest
first." That's what SQL does (`catalog.sqlite`). See section 7 for how to ask.

> A "pristine, trust-it-fully" subset is:
> `WHERE quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0`.

---

## 3. The signature: turning a song into 36 numbers

The catalog describes songs in *words/categories*. But to do **math** on music — to
measure "how close are these two songs" — we need each song to be a **list of pure
numbers of the same length.** That fixed-length list of numbers is the **signature**.

We chose **36 numbers per song.** They live in one big file,
`SIGNATURES_DATA/signatures.npy`, shaped **459,805 × 36** — one row per song.

The 36 numbers are four little "profiles" stuck together:

| numbers | profile | plain meaning |
|---|---|---|
| 1–12  | **which notes** | of the 12 notes (C, C#, D … B), how much is each used? |
| 13–24 | (same again — a placeholder for a future "weighted by note length" version) |
| 25–30 | **intervals** | what *gaps* between notes show up — smooth steps? big leaps? spicy tritones? |
| 31–36 | **chord sizes** | are chords mostly single notes, or fat 5–6 note stacks? |

Each little profile is scaled so it adds up to 1 — i.e. it's **proportions, not
counts.** That's important: it means a 30-second sketch and a 10-minute epic in the
same style get *almost the same signature*. The signature captures **the flavor of
the music, not how long or loud it is.**

**Mental model:** the signature is a song's **nutrition label.** Two different brands
of the "same" cereal have nearly identical nutrition labels. Two wildly different
foods have very different ones. We turned every song into its nutrition label so we
can compare 460,000 of them at once.

> Important: building these 36 numbers did **NOT** require re-analyzing the MIDI from
> scratch. The note-counts and chord-counts were already saved in `META_DATA/`. The
> signature is just a *reshaping* of numbers we already had. (That's a core rule of
> this project: don't redo expensive work.)

> **✅ UPDATE (2026-06-17): the signature is now 74 numbers, not 36.** Those original
> 36 were almost pure **pitch/harmony** — they said nothing about **rhythm**, which is
> the single most important dimension for the model. So we did a full re-parse and
> bolted on three more "profiles": **rhythm/time-feel** (syncopation, swing, triplet
> feel, tempo shape…), **melody contour** (steps vs leaps, range, phrasing…), and
> **refined harmony** (chord change rate, harmonic rhythm…). The extended label lives
> in `SIGNATURES_DATA/signatures_ext.npy`, shaped **459,805 × 74**. The original 36-D
> `signatures.npy` is kept untouched. Rhythm is deliberately **weighted ×2** so two
> songs that share a groove land near each other even if their notes differ. So: the
> "nutrition label" below is the *pitch* part; the real label now also has a rhythm,
> melody, and harmony panel stapled on.

---

## 4. The space, and "nearest neighbors" (the heart of it)

Here's the leap that makes everything click.

A list of 2 numbers is a point on a piece of paper (x, y). A list of 3 numbers is a
point in a room (x, y, z). A list of **36** numbers is a point in a **36-dimensional
room** — you can't picture it, but the *math works exactly the same.*

So our 459,805 signatures are **459,805 dots floating in a 36-dimensional room.**
(Since the 2026-06-17 extension the room is **74-dimensional** — same idea, more axes:
the extra dimensions are rhythm, melody, and harmony. Everything below works identically.)

- Songs that sound alike → their nutrition labels are alike → their dots are **close
  together.**
- Songs that are very different → their dots are **far apart.**

"Close" is measured with **cosine similarity** — basically: do the two nutrition
labels *point the same direction?* (We care about the shape of the proportions, not
the size.) Cosine = 1.0 means "essentially the same flavor"; lower means "more
different."

**k-Nearest Neighbors (kNN)** is just: *"given one dot, find the k dots sitting
closest to it."* You hand it a song, it finds the most musically-similar songs in the
whole corpus in a fraction of a second. The file `SIGNATURES_DATA/knn_cosine.pkl` is
the pre-built "find-nearby-dots machine" — **as of 2026-06-17 it's built on the full
74-D space**, so neighbors now share rhythm/groove, not just notes. (The old
`CODE/04_search.py` is a separate, slower **pitch-only** matcher kept for reference;
for rhythm-aware neighbors use `knn_cosine.pkl` + `signatures_ext.npy` — see §7.)

**Mental model:** imagine all 460k songs as **stars in a galaxy.** Similar songs
form **constellations.** kNN is pointing at one star and asking "what are its
neighbors?" That's similarity search, recommendation, and de-duplication all at once.

> One honest caveat: to keep it fast at this scale, the saved search machine was
> trained on a 100k sample of the stars, so it's *approximate* — great for "find me
> similar," not a courtroom guarantee of THE single closest star.

---

## 5. song_id: same tune, different arrangements

Some "different" files are really the *same song* — a piano version and a full-band
version of the same tune. Byte-for-byte they differ (so md5 dedup keeps them both),
but musically they're siblings.

We used the signatures to find these sibling groups (dots that are *almost on top of
each other*) and gave each group a shared **`song_id`.** ~23,316 real
multi-arrangement clusters were found; every other file is its own one-member group.
**378,923 distinct song_ids total.**

Why it matters: when training a model you must not let a song's piano version sit in
"train" while its band version sits in "test" — that's cheating (the model has
secretly seen the answer). Grouping by `song_id` keeps all arrangements of one tune
on the *same side* of the train/test split. This was done **carefully to avoid
over-merging** (a dumb version would collapse thousands of simple C-major songs into
one blob — we have guards against that).

**Mental model:** md5 = "is this the exact same recording?" song_id = "is this the
same *song*, even in a different outfit?"

---

## 6. WHY all this — the new-music idea

Now the payoff. You have a galaxy of 460k musical dots. Here's the creative move:

**Most of the galaxy is crowded.** Huge dense blobs of "4/4 diatonic triadic pop/rock
music" — because that's what most MIDI is. But a 74-dimensional room is *enormous*,
and most of it is **empty.** Those empty regions are combinations of notes /
intervals / chord-shapes that are perfectly coherent but that **almost no human music
has ever occupied.**

> **A new form of music = a populated region of this space that is currently empty.**

So the plan isn't "imitate the crowd" (that's what normal AI music does — it samples
the dense blobs and gives you more of the same). The plan is:

1. **Map** where the dots are dense and where they're empty.
2. **Pick an empty-but-coherent corner** — a target coordinate.
3. **Generate music aimed at that coordinate** instead of at the crowd.

That turns the vague wish "make something new" into a **concrete address in a
space** you can point a generator at. That's the whole reason the corpus, the
signatures, and the space exist.

> **✅ This limitation is now fixed (2026-06-17).** The original 36 numbers were mostly
> **pitch and harmony** and barely captured **rhythm / time-feel / melody shape** — so
> if your "new" was a new *rhythm* or *form*, the space couldn't see it. We did exactly
> the widening this paragraph predicted: a full re-parse added rhythm, melody-contour,
> and tempo-shape features, growing the signature from **36 → 74 numbers**
> (`signatures_ext.npy`), with rhythm weighted ×2. The empty-corner hunt can now span
> **time-feel and melody, not just notes.** (Building that hunt is the next job — see
> STATE.md "Phase 11".)

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

**Find songs similar to one you have:**
```bash
python3 CODE/04_search.py --out-root . --query /path/to/song.mid --top 10
python3 CODE/04_search.py --out-root . --md5 <md5-already-in-store> --top 10
```

**Load it in Python:**
```python
import pandas as pd, numpy as np, pickle
meta = pd.read_parquet("catalog/metadata.parquet")        # the 148-col spreadsheet
sigs = np.load("SIGNATURES_DATA/signatures.npy")          # 459805 x 36 (pitch-only, original)
ext  = np.load("SIGNATURES_DATA/signatures_ext.npy")      # 459805 x 74 (pitch+rhythm+melody+harmony)
md5s = open("SIGNATURES_DATA/signatures_md5.txt").read().split()  # row i -> which song

# rhythm-aware nearest neighbors of one song:
P   = pickle.load(open("SIGNATURES_DATA/knn_cosine.pkl", "rb"))   # {nn, fit_rows, weights, ...}
row = md5s.index("<some_md5>")
d, i = P["nn"].kneighbors(ext[row:row+1], n_neighbors=11)
neighbors = [md5s[j] for j in i[0] if j != row]           # 10 most similar (rhythm counts ×2)
```

**Hear something:** any rendered audio →
`webplayer add <file-or-dir> && webplayer open`.

---

## 8. The glossary (when a word trips you up)

- **MIDI** — a file that stores the *notes/instructions* of music (which note, when,
  how hard), not the actual sound. Like sheet music for a computer.
- **md5** — a 32-char fingerprint of a file's exact bytes. Same md5 = identical file.
- **corpus** — the whole organized collection of songs.
- **catalog / metadata** — the spreadsheet of measurements about every song.
- **parquet / sqlite** — two file formats holding that spreadsheet (one for Python,
  one for SQL queries). Same data.
- **signature** — the "nutrition label" of one song. Originally 36 numbers (pitch);
  **now 74** (pitch + rhythm + melody + harmony) in `signatures_ext.npy`.
- **dimension** — one number in the list. 74 numbers = 74 dimensions = a point in
  "74-D space." Can't be pictured, behaves like a point.
- **vector / matrix** — a vector is one row of numbers (a dot); a matrix is many rows
  stacked (all the dots). `signatures_ext.npy` is a 459805×74 matrix (the original
  pitch-only `signatures.npy` is 459805×36).
- **cosine similarity** — a way to measure if two number-lists "point the same way";
  1.0 = same direction/flavor.
- **kNN (k-nearest neighbors)** — "find the k closest dots to this one."
- **song_id** — groups different arrangements of the same underlying tune.
- **split (train/val/test)** — partitioning songs for machine learning so the model
  is tested on songs it never trained on.
- **embedding / latent space** — fancier future version of "the space of dots,"
  where the numbers are *learned* by a neural net instead of hand-defined. Same
  mental model: songs as dots, near = similar, empty = unexplored.

---

## 9. The five things to actually internalize

1. **Every song is a dot in a space** (a list of 74 numbers / its "nutrition label").
2. **Near = similar, far = different**, and we measure it with cosine + kNN.
3. **The space is mostly empty.** The crowd is normal music.
4. **A new form of music = filling an empty corner** of that space on purpose.
5. **Everything else (warehouse, spreadsheet, song_id, splits) is plumbing** that
   keeps the data clean and honest so step 4 is possible.

If those five land, you've got it. Re-read 1–6 whenever a detail slips; re-read 9
when you just need the gist.
