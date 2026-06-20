# Annotation Axes Plan — request for a second opinion

> **What I want reviewed:** the design of the *subjective rating axes* for a by-ear music
> annotation tool. Is this the right set of things to rate, rated the right way? Self-contained
> below — you don't need any prior context. Open questions for you are in §7.

---

## 1. Context (what the ratings are for)

- **The corpus:** ~460,000 unique MIDI files, deduped and catalogued. Every song already has
  **88 computed feature dimensions** (pitch, rhythm/swing/syncopation + corrected tempo/meter,
  melody contour, harmony/key/dissonance, drum groove) and is a point in that 88-D space.
  Structure is well covered by machines.
- **The goal:** north-star is "invent a new form of music." Near-term concrete task: an
  "empty-space hunt" has mapped dense vs. sparse regions of the 88-D space; the next step is to
  **find the *good* empty corners** — musically appealing but under-represented regions — to aim
  generation at. That requires a **taste/quality signal the computed features don't have.**
- **The tool ("NinjaStar-8"):** a phone web app. One person (the corpus owner) listens to a song
  and moves sliders. Ratings are stored **md5-keyed**, left-merged onto the catalog like any other
  feature table (un-rated songs = NaN). Intent: rate a subset (target ~500), then **train a small
  model to predict the ratings from the 88-D features and propagate taste across all 460k.**
- **Current state:** 8 ad-hoc axes (groove, slaps, energy, peace→kill, lobrow→hibrow, simple→fancy,
  left→right, normie→weird), **0–8 sliders, 4 = neutral**, ~45 songs rated so far, **single rater**.
- **Problem prompting this review:** some axes are hard to rate consistently (left/right, fancy vs
  hibrow overlap), some duplicate what's already computed, and the set was picked by intuition, not
  evidence. Before investing time rating ~500, get the axes right.

---

## 2. What the literature says (evidence base)

1. **The validated emotion frame is valence–arousal** (Russell's circumplex): two orthogonal axes,
   **arousal** (calm↔intense) and **valence** (negative↔positive). Dominant model in music-emotion
   research. The closest precedent to *this* project — **EMOPIA**, a symbolic/**MIDI** emotion
   dataset — labels songs by the 4 quadrants of valence-arousal. [survey; EMOPIA]
2. **Arousal is reliably rated; valence is the noisy one** — across datasets, raters agree on
   arousal far more than valence. **BUT for MIDI specifically, valence is *more* predictable from
   symbolic features (.88) than from audio (.70)**, because valence tracks major/minor tonality,
   which is explicit in MIDI. So valence — normally avoided as unreliable — is a *good fit for a
   MIDI corpus.* [EMOPIA, DEAM]
3. **Perceived vs. felt/induced emotion** is a real fork. Perceived = what the music *expresses*
   (more consistent, what most datasets use). Felt = what *you actually feel* (personal, noisier
   across people, but it *is* the taste signal). With a **single rater**, cross-person noise is
   irrelevant — **self-consistency** is the thing to protect. [survey, EMOPIA]
4. **Song aesthetics** can be rated as distinct dimensions: SongEval uses **memorability** and
   **overall musicality** (holistic enjoyment) among others — but warns its dimensions *overlap*
   (musicality≈memorability) and that it measures *expert consensus, not personal taste.* [SongEval]
5. **Rank, don't rate** — the strongest methodological finding. Human affect judgments are
   **ordinal/relative, not absolute**: "is A more X than B?" is much more reliable than "rate A's X
   on a scale." Absolute sliders drift; pairwise comparisons don't. Cost: ranking is slower / a
   bigger build. [PREFAB / Yannakakis; survey]
6. **Annotation fatigue is real** — long mandatory annotation degrades quality. Keep per-song load
   low; selective/optional rating preserves quality. [PREFAB]

---

## 3. Proposed design — 6 axes in 3 layers

Rather than 8 flat sliders, **6 axes split by how much they matter and how reliable they are.**
Default = neutral (4) and any axis is skippable, so extra axes cost ~nothing per song.

### Layer 1 — Core (always rate; the signals machines CAN'T compute + project priorities)
| Axis | Low ↔ High | Type | Why |
|---|---|---|---|
| **Musicality / love-it** | meh ↔ I love this | felt | the holistic quality target; not computable |
| **Novelty** | predictable ↔ strange-but-works | felt | the north-star "new music" axis |
| **Groove** | no pocket ↔ deep pocket | perceived | rhythm is the project's #1 priority; *perceived* groove ≠ computed swing |

### Layer 2 — Bonus (rate when obvious, skip when not; cheaper / partly computable)
| Axis | Low ↔ High | Type | Why |
|---|---|---|---|
| **Valence** | dark ↔ bright | perceived | other half of the emotion frame; MIDI-friendly |
| **Energy** | calm ↔ intense | perceived | the reliably-rated arousal axis |
| **Memorability** | forgettable ↔ unforgettable hook | felt | distinct aesthetic signal (SongEval) |

### Layer 3 — Calibration: occasional A-vs-B **duels**
Not a full ranking grind. Every so often the tool shows **two songs** and asks *"which is more
[love-it / novel]?"* — one tap. These give rock-solid ordinal ground truth (the rank-don't-rate
finding) and **calibrate the absolute sliders** so they stop drifting. Sliders = coverage (every
song scored); duels = accuracy (trustworthy ordering on the axes that matter most).

### Dropped from the current 8 (with reasons)
- **peace→kill** — folds into valence + energy.
- **lobrow→hibrow** (cultural class) — hard to rate, unclear payoff for the goal.
- **simple→fancy** (complexity) — already computed (note density, entropy, chord complexity).
- **left→right** (cerebral/creative) — vague, low self-consistency.

---

## 4. Methodology (how to rate, not just what)

- **Tag each axis felt vs. perceived and never mix** — emotion axes (valence/energy) = what the
  music *expresses*; taste axes (love-it/novelty/memorability) = your gut reaction. Mixing the two
  framings on one axis is how ratings get noisy.
- **Anchor every axis** with 2–3 reference songs from the corpus (a clear 0 and a clear 8) so the
  scale doesn't drift over hundreds of ratings.
- **~10% repeats** — silently re-show some songs to measure self-consistency; the single-rater
  stand-in for inter-rater reliability. Tells us which axes to trust.
- **Treat the data as ordinal downstream** (rank correlations), since absolute affect numbers are
  noisy even from a consistent rater.
- **Pool (related, separate issue):** the current 109-song pool is a QA-defect-biased sample (74
  "clean" + 35 flagged for audio glitches), in fixed md5-hash order. Swap it for a **randomized
  ~500-song stratified sample** of clean songs spread across the 88-D space, so the trained model
  generalizes instead of overfitting weird files.

---

## 5. Migration cost (why now is the right time)

- Only **~45 songs rated so far**, so changing axes is cheap. Surviving axes (groove, energy,
  novelty≈"normie_weird") **carry forward by md5**; new axes (valence, musicality, memorability)
  just start un-rated. After 500 ratings this would be painful — now it's nearly free.
- Ratings live in a separate parquet (`_work/ninjastar8_ratings.parquet`), never touch the catalog
  directly, so nothing else in the project is affected.

---

## 6. Build order (proposed)

1. **Now (quick):** swap the 8 axes → these 6, marked core/bonus + felt/perceived. Sliders stay.
2. **Soon:** pick 2–3 anchor songs per axis; show the anchors in the UI.
3. **Later:** build the A-vs-B duel mode for love-it + novelty.
4. **Parallel:** replace the QA-biased 109 pool with a randomized ~500 stratified sample.

---

## 7. Open questions for the second opinion

1. **Is 6 the right number?** Too many (fatigue) or too few (missing something important — e.g. a
   separate "emotional intensity/movingness," tension, or a danceability axis)?
2. **Is the felt-vs-perceived split sensible**, or should everything be one framing for simplicity?
3. **Sliders-first then duels, or commit to pairwise ranking now?** The evidence favors ranking; is
   the extra build worth it up front, or is slider-coverage + periodic duels the right compromise?
4. **Keep absolute 0–8, or go pure ordinal?** (0–8 with 4=neutral, bipolar diverging meter.)
5. **Anything from GEMS / music-preference models we're leaving on the table** that would matter for
   a *generation-steering* taste model (vs. a recommendation/therapy model)?
6. **Pool design:** is ~500 stratified across the 88-D space the right sampling, or should it be
   stratified by genre, by cluster, or weighted toward the "empty corners" we ultimately care about?

---

## Sources
- MER survey (datasets/annotation/reliability): https://arxiv.org/abs/2406.08809
- EMOPIA (symbolic/MIDI valence-arousal, the closest precedent): https://arxiv.org/abs/2108.01374
- SongEval (song aesthetics dimensions): https://arxiv.org/abs/2505.10793
- PREFAB / "rank don't rate" ordinal affect: https://arxiv.org/abs/2601.13904
- DEAM (valence-arousal, reliability): https://cvml.unige.ch/databases/DEAM/manual.pdf
- GEMS (Geneva Emotional Music Scale): https://en.wikipedia.org/wiki/Geneva_Emotional_Music_Scale
- Rentfrow MUSIC model (music-preference factors): https://pubmed.ncbi.nlm.nih.gov/21299309/

*Drafted for review. Current tool: NinjaStar-8 (`ninjastar8.py`), 8 axes / 0–8 sliders / ~45
ratings. This plan proposes replacing the 8 with the 6 above + a duel mode.*
