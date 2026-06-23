# TONY BOLLAS DRUM ATLAS — INVENTION MODE (corpus later)

> **PT** = the Tony Bollas Plain Text drum notation system (defined below).
> **TBB** = our new locked core groove signature for the new style we are inventing,
> written in PT. TBB is NOT yet chosen — Section 3 generates 8 "Left" candidates; the
> human reviews and picks one to lock as **TBB**.
>
> This file has two jobs:
> 1. Catalog **known style signature patterns** (ear-reference probes), and
> 2. Use deterministic rules to generate **novel candidates** for an inevitable-but-empty
>    new style (the STATE.md empty-space goal). Known styles describe the past; the
>    generated candidates aim at the gaps.
>
> Each corpus-verified pattern is checked against the actual MIDI grid.

## Notation Key (PT)

| Symbol | Instrument |
|--------|-----------|
| K | Kick drum (GM 36) |
| S | Snare (GM 38) |
| H | Closed hi-hat (GM 42) |
| O | Open hi-hat (GM 46) |
| R | Ride cymbal (GM 51) |
| C | Crash cymbal (GM 49) |
| T | Tom (generic, GM 45) |
| Tb | Tambourine (GM 54) |
| VS | Vibra-Slap (GM 58) |
| Cb | Cabasa (GM 69) |
| Clv | Claves (GM 75) |
| ( ) | Simultaneous hits within one slot |
| + | Separator between multi-character names within a slot |
| . | Rest (empty slot — silence) |
| - | Tie / sustain (previous slot's sound continues, no new attack) |
| [ ] | Metric grouping bracket (used for odd meters) |

> One `( )` group = one **16th note** by default. Grid resolution is **16th notes**
> unless stated otherwise (swing uses 8th-triplets; odd meters state their slot count).
>
> **Durations & ties.** Each slot is one 16th and holds exactly one of: an **attack** (an
> instrument letter or `( )` group), a **tie** `-` (the previous sound continues — no new
> attack), or a **rest** `.` (silence). A tie sets duration: `K` = 16th kick, `K-` = 8th,
> `K--` = dotted 8th, `K---` = quarter; `K.` = a 16th kick then a 16th of silence. For
> one-shots (K, S, closed H) the tie is a duration/feel marker; for ringing voices (O, R,
> C, T) `-` = let ring and `.` = choke/dampen. A trailing `-` after a `( )` group ties the
> whole slot — to tie only one stacked voice, use the per-instrument grid, where each row
> reads `X` = attack, `-` = sustain, `.` = rest.

---

## TBB_LOCKED — the style signature (v1, locked 2026-06-22 by orcamang)

> **TBB v1 = the "5-5-6 gallop clave"** — orcamang's locked L3+L6 hybrid. Every song in
> the new style uses this beat (see §4 Enforcement). Rendered: `DRUM_PATTERNS/TBB_locked.mid`
> (4-bar loop, 118 BPM, GM perc ch10). orcamang's spec was loose; the grid below is
> codemang's concrete, auditable reading of it (kick chain from L6, displaced-tresillo
> snare + open-hat surprise voice from L3) — adjust here if the ear disagrees.

**PT:** `(HK).(Hs)(KO)..(KSH)..(K.s)(KO)..(KS)..(Hs)`  *(see grid; ( ) groups are 16ths)*
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
K:     X  .  .  X  .  .  X  .  .  X  .  .  X  .  .  .   (1,4,7,10,13 — 3+3+3+3+4 gallop chain)
S:     .  .  g  .  .  .  X  .  .  g  .  .  X  .  g  .   (X=accent 7,13; g=ghost 3,10,15)
H:     .  .  X  .  .  .  X  .  .  .  .  .  .  .  X  .   (closed hat on upbeats 3,7,15)
O:     .  .  .  .  X  .  .  .  .  .  X  .  .  .  .  .   (open hat 5,11 — the R12 surprise voice)
```
**Why locked (orcamang):** inevitable body-move (lurch → hard bar-end snap); R1–R12 compliant
but outside all 12 known styles (empty corner); enforced verbatim at generation time as the
style's DNA. **BPM 118.**

---

## 1. Known Style Signature Patterns

Each entry: PT string · grid · why it defines that style. 16-slot = one 4/4 bar at
16th resolution. These are reference probes, not generation targets. **The 8 "Left"
candidates (L1–L8) that TBB was chosen from are archived at
`DRUM_PATTERNS/_archive/left_candidates.md`.**

### `rock_backbeat`
**PT:** `(HK).H.(HS).H.(HK).H.(HS).H.`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .
K:     X  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
S:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why:** snare on 2 & 4 (the backbeat) + steady 8th hats + kick on 1 & 3. The anchor of rock/pop.

### `funk_pocket`
**PT:** `(HK)HHH(HS)HH(HK)HH(HK)H(HS)HHH`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X
K:     X  .  .  .  .  .  .  X  .  .  X  .  .  .  .  .
S:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why:** continuous 16th hats + kick pushed off the downbeat (the "&a") + tight 2&4 snare = the funk pocket.

### `surf_rock`
**PT:** `(RK)RSR(RS)RSR(RK)RSR(RS)RSR`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
R:     X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X
K:     X  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
S:     .  .  X  .  X  .  X  .  .  .  X  .  X  .  X  .
```
**Why:** galloping ride + snare driving the offbeat 8ths over a backbeat = surf drive.

### `reggaeton_dembow`
**PT:** `(HK).HS(HK).(HS).(HK).HS(HK).(HS).`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .
K:     X  .  .  .  X  .  .  .  X  .  .  .  X  .  .  .
S:     .  .  .  X  .  .  X  .  .  .  .  X  .  .  X  .
```
**Why:** four-on-the-floor kick under a tresillo (3+3+2) snare = the dembow, the DNA of reggaeton.

### `trap`
**PT:** `(HK)HHHHH(HK)H(HS)H(HK)HHHHH`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X
K:     X  .  .  .  .  .  X  .  .  .  X  .  .  .  .  .
S:     .  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
```
**Why:** half-time snare on beat 3 + rolling 16th hats + syncopated 808 kick = trap.

### `house_four_on_floor`
**PT:** `K.O.(KS).O.K.O.(KS).O.`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
K:     X  .  .  .  X  .  .  .  X  .  .  .  X  .  .  .
O:     .  .  X  .  .  .  X  .  .  .  X  .  .  .  X  .
S:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why:** kick on every quarter (four-on-the-floor) + open hat on the upbeat "ts" + clap on 2&4 = house.

### `boom_bap`
**PT:** `(HK).H.(HS).H.H.(HK).(HS).H.`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .
K:     X  .  .  .  .  .  .  .  .  .  X  .  .  .  .  .
S:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why:** backbeat snare + kick on 1 and the "&" of 3 (slot 11), dusty/laid-back = classic boom-bap hip-hop.

### `one_drop_reggae`
**PT:** `H.H.H.H.(HKS).H.H.H.`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .
K:     .  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
S:     .  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
```
**Why:** the deliberate void on beat 1 + kick & snare unified on beat 3 (the "drop") = reggae one-drop's laid-back lift.

### `dnb_two_step`
**PT:** `(HK)HHH(HS)HHHHH(HK)H(HS)HHH`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X
K:     X  .  .  .  .  .  .  .  .  .  X  .  .  .  .  .
S:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why:** snare on 2 & 4 with a syncopated second kick (the "two-step") at breakbeat tempo (~170 BPM) = drum & bass.

### `swing_jazz` — 8th-triplet resolution (12 slots / bar)
**PT:** `R..（R+HH).R R..(R+HH).R`  → 12 triplet slots
```
trips: 1  2  3  4  5  6  7  8  9 10 11 12
R:     X  .  .  X  .  X  X  .  .  X  .  X
HH:    .  .  .  X  .  .  .  .  .  X  .  .   (hi-hat foot on beats 2 & 4)
```
**Why:** the "spang-spang-a-lang" triplet ride + hi-hat foot on 2 & 4. The skipped middle triplet is the swing.

### `blast_beat_non_drummer_variant_01` — corpus-verified
**Source:** `5672a90158cffc067ebc828e6ac79cfe` · F major · 150 BPM (feels like 75)
**PT:** `(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
K:     X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X   (every 16th)
S:     X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .   (every odd 16th)
H:     .  X  .  X  .  X  .  X  .  X  .  X  .  X  .  X   (every even 16th)
```
**Why:** kick on every 16th, snare on odds, hat fills the gaps — a programmed death/speed-metal blast. 100% locked (0 bar-to-bar variation) despite the DB's bogus `drum_pattern_entropy ≈ 1.0`.

### `gypsy_folk_11_8_main_loop` — corpus-verified · 11/8, 8th-note slots
**Source:** `ab83f1ddeb3969f0f54634ef74e7880a` · E major · 120 BPM · grouping 2+2+2+2+3
**PT:** `[(Tb+VS+K+Cb)(Tb)] [(Tb+K)(Tb)] [(Tb+VS+K)(Tb)] [(Tb+K)(Tb)] [(Tb+VS+K)(Tb)(Tb)]`
```
8ths:    1    2    3    4    5    6    7    8    9   10   11
Tamb:    X    X    X    X    X    X    X    X    X    X    X
VS+OHH:  X    .    .    .    X    .    .    .    X    .    .
K+Clv:   X    .    X    .    X    .    X    .    X    .    .
Cab:     X    .    .    .    .    .    .    .    .    .    .
```
**Why:** the 2+2+2+2+3 grouping — the closing group of 3 is the "limp" that makes 11/8 sound like it does. GM perc: Tb=54, VS=58, Cb=69, Clv=75, OHH=46.

---

## 2. Deterministic Rules for Valid Patterns

Rules a 16th-grid must satisfy to read as "musical" (used to gate Section 3). A pattern
may break a rule **only** if it does so by name/design (e.g. one-drop breaks R1).

- **R1 — Downbeat anchor.** Slot 1 carries a strong-beat marker (K or S), OR the omission is named (one-drop drops beat 1 deliberately). No accidental empty downbeat.
- **R2 — Backbeat or its named negation.** Snare/clap on beats 2 & 4 (slots 5, 13) for pocket feels. If absent, justify it: half-time → beat 3 only; one-drop → beat 3; blast → every odd; displaced → tresillo.
- **R3 — Backbeat exclusivity.** Don't stack K and S on the same backbeat slot unless intentionally unifying (one-drop / reggae drop).
- **R4 — Timekeeper continuity.** A subdivision voice (H or R) runs at least on the 8th grid. Gaps must be musical (open-hat upbeats), never random single drops.
- **R5 — Density ceiling.** ≤ 2 simultaneous kit voices per slot, except accents (a crash may stack on a downbeat). Keeps it playable and legible.
- **R6 — Syncopation resolves.** Off-beat kicks must resolve to a downbeat within the bar; unresolved syncopation reads as an error.
- **R7 — No orphan voices.** Any voice present hits ≥ 2 times, unless it is a deliberate single marker (e.g. the gypsy cabasa downbeat).
- **R8 — Tresillo is the universal valid syncopation.** Hits on 1,4,7 (and 11,14) — the 3+3+2 clave — are inherently musical across every style; prefer it when displacing.
- **R9 — Open-hat placement.** Open hats belong on upbeats (offbeat 8ths: slots 3,7,11,15) and close on the downbeat.
- **R10 — Invalid cases to avoid.** (a) a single voice filling all slots with zero bar-to-bar variation read as "complex" (the false-max-entropy blast-beat bug); (b) two colliding backbeats; (c) a hat voice that drops random single 16ths; (d) an unanchored downbeat with no named reason; (e) orphan single hits.
- **R11 — Signature asymmetry (added 2026-06-22, orcamang).** A style signature must use an **asymmetric grouping** (5/7/11/etc.) that **resolves hard on the bar-4 end** — no floating, unresolved bars. The lurch must always snap back.
- **R12 — Exactly one surprise voice (added 2026-06-22, orcamang).** A signature must contain **exactly one "surprise voice"** (e.g. an open hat on a non-multiple-of-4 slot) per 2 bars — forces an ear-hook without complexity bloat.

---

## 3. Generated "Left" Candidates — ARCHIVED

The 8 rule-compliant novel candidates (L1–L8) that TBB was selected from have been
**archived to `_archive/left_candidates.md`** now that TBB v1 is locked (see the
TBB_LOCKED section at the top of this file). They remain auditable for provenance;
their MIDIs regenerate via `gen_candidates_midi.py`. TBB = the **L3 (additive 5+5+6)
× L6 (gallop clave)** hybrid.

---

## 4. ENFORCEMENT (style DNA)

**Every generated song in the new style MUST carry TBB as its base drum layer** — either
as the sole kit pattern or overlaid on / replacing any other drum pattern. TBB is the
non-negotiable signature: the beat is what makes the style the style. Micro-humanized
timing/velocity variants of TBB are allowed; structural departures from the TBB grid are
not (that would be a different style). The generator lane (`CODE/50_generate.py`) must
force the TBB drum layer on every candidate it emits for this style.

---

## How to relock / revise TBB

TBB v1 is locked (see top). To revise: edit the `TBB_LOCKED` grid + re-run
`gen_tbb.py`, bump the version, and log the change in STATE.md's Session Log.
