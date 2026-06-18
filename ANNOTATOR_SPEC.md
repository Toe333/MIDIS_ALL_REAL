# BUILD SPEC — human-annotation web player ("the slider tool")

Written 2026-06-17 so a fresh context can build this with no backstory. Goal: let the
user **listen to tracks and add subjective ratings by ear**, producing a new feature
table that merges onto the catalog like any other (see [[human-annotation-plan]] memory).

## What it is
A small **localhost web app**: shows one track → plays its audio → user drags sliders →
saves a row → auto-advances to the next track. Fast, keyboard-driven.

## Theme / branding — "NinjaStar-8" (the 8-Point Shuriken)
8 sliders = the **8 points of a ninja star** (shuriken). 8 features · 8 points · **8-bit**.
Brand: **NinjaStarRecords**. The web player should look **8-bit / chiptune** — pixel font
(e.g. "Press Start 2P"), retro/limited palette, chunky pixel sliders, blippy click sounds
optional. Title screen: a spinning 8-point shuriken whose 8 spokes are the 8 sliders.
NOTE: user also mentioned "there-mang" / theremin as a motif — confirm intent (a mascot? a
sound?) and work it in; left as a TODO, don't fabricate.

## The 8 sliders (each = one feature column, scale 0–5)
Bipolar = rate from the LOW pole (0) to the HIGH pole (5).

| pt | slider | 0 (low pole) → 5 (high pole) |
|----|--------|------------------------------|
| 1  | **groove**       | no pocket → deep groove *(top priority dimension)* |
| 2  | **slaps**        | meh → banger (overall quality) |
| 3  | **energy**       | calm → intense |
| 4  | **peace→kill**   | hippy → death metal (aggression) |
| 5  | **lobrow→hibrow**| trashy → refined — *cultural class / who listens; NOT note complexity* (Mozart = hi) |
| 6  | **simple→fancy** | punk → prog — *musical complexity / musicianship; NOT class* (Mozart = simple, Dream Theater = fancy) |
| 7  | **left→right**   | cerebral (Bach) → creative (Velvet Underground) — leftbrain vs rightbrain |
| 8  | **normie→weird** | Britney pop → 9/8 gypsy rag (mainstream vs strange) |

KEY DESIGN NOTE: sliders 5 (class) and 6 (complexity) are **independent axes** — keep them
distinct (Mozart is hi-brow + simple; fusion can be lo-brow + fancy). Do NOT let them bleed.
Dropped: `sparse→dense` (the script already measures density via `n_tracks`/note-density —
not worth a human slider). Adding/cutting a slider later = adding/cutting a column; no lock-in.

## Track pool
- **v1 (build/test on this):** the 109 pre-rendered clips in `_stats/audio_sanity_wav/`,
  named `clean__<md5[:12]>.wav`. Map filename prefix → full `md5` via `catalog/metadata.parquet`.
- **v2 (later):** render on demand from the full corpus with fluidsynth
  (`/etc/alternatives/default-GM.sf2` or a nicer sf2). md5→MIDI path lives in the
  **sqlite `manifest` table** in `catalog/catalog.sqlite` (NOT in metadata.parquet — it has
  no path column). Wire that in phase 2.

## Output (the important part)
- Append each rating to an **`md5`-keyed parquet**, e.g. `_work/ninjastar8_ratings.parquet`,
  columns: `md5, groove, slaps, energy, peace_kill, lobrow_hibrow, simple_fancy,
  left_right, normie_weird, rated_at` (the 8 points + key + timestamp).
- Must be **resumable** (skip already-rated md5s; never lose prior rows on restart).
- This file later **left-merges onto the catalog by `md5`** exactly like the other feature
  tables — un-rated tracks stay NaN. Do NOT touch the catalog directly.

## UX musts
- One track per screen; big play button + sliders; keyboard `1–4` focus a slider,
  arrows/number to set, **Enter/Space = save + next**, maybe `s` = skip.
- Show progress (n rated / pool size). Single-play audio (pause others).
- Localhost only (bind 127.0.0.1). The existing `webplayer` only PLAYS — it can't capture
  ratings — so build a dedicated tiny Flask/stdlib app; don't try to bolt onto webplayer.

## Notes
- Read-only on catalog + audio; only writes its own ratings parquet → safe to run alongside
  the pipeline.
- For the goal context (each song → vector → similar songs cluster → empty gaps = new music),
  these human sliders add taste/feel axes the computed features can't. Rhythm is the top
  priority dimension ([[rhythm-is-priority]]).
