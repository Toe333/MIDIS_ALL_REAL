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
| . | Rest (empty slot) |
| [ ] | Metric grouping bracket (used for odd meters) |

> One `( )` group = one **16th note** by default. Grid resolution is **16th notes**
> unless stated otherwise (swing uses 8th-triplets; odd meters state their slot count).

---

## 1. Known Style Signature Patterns

Each entry: PT string · grid · why it defines that style. 16-slot = one 4/4 bar at
16th resolution. These are reference probes, not generation targets.

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

---

## 3. Generated "Left" Candidates (8)

Novel patterns that satisfy Section 2 but sit **outside** the known set — coherent,
yet aimed at empty space (displaced backbeats, additive groupings inside 4/4, hybrid
grooves, cymbal polymeter). **Human reviews and picks ONE to lock as TBB.** All are
one 4/4 bar at 16th resolution, ~120 BPM reference.

### L1 — `tresillo_backbeat`
**PT:** `(HK).HSH.(HS).H.(HK).(HS).H.`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .
K:     X  .  .  .  .  .  .  .  .  .  X  .  .  .  .  .
S:     .  .  .  X  .  .  X  .  .  .  .  .  X  .  .  .
```
**Why-new:** backbeat pulled toward the tresillo (slot 4 & 7 by R8) while keeping a 2&4 anchor at 13 — a "limping pocket" no straight 4/4 style uses.

### L2 — `offbeat_kick_suspension`
**PT:** `O.(HK).(HS).(HK).O.(HK).(HS).(HK).`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
O:     X  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
H:     .  .  X  .  X  .  X  .  .  .  X  .  X  .  X  .
K:     .  .  X  .  .  .  X  .  .  .  X  .  .  .  X  .
S:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why-new:** the four-on-the-floor kick pushed entirely onto the upbeat 8ths — kick never lands on a downbeat (open hat marks it instead) → perpetual suspension over a held 2&4.

### L3 — `additive_5_5_6`
**PT:** `(HK)HHHH(HK)HHHH(HK)HH(HS)HH`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X
K:     X  .  .  .  .  X  .  .  .  .  X  .  .  .  .  .
S:     .  .  .  .  .  .  .  .  .  .  .  .  X  .  .  .
```
**Why-new:** kick accents on a 5+5+6 sixteenth grouping inside straight 4/4 — implies a 5-pulse over the 16-grid (odd-meter feel without leaving 4/4), snare resolves the bar at 13.

### L4 — `one_drop_double_time`
**PT:** `HHHHHH(HS)H(HKS)H(HS)HHHHH`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X
K:     .  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
S:     .  .  .  .  .  .  X  .  X  .  X  .  .  .  .  .
```
**Why-new:** reggae's beat-1 void + beat-3 drop fused with trap's continuous 16th hats and ghost snares flanking the drop — a half-time skank at double-time density.

### L5 — `lurch_7_9`
**PT:** `(HK).H.(HS).HKH.HSH.H.`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .
K:     X  .  .  .  .  .  .  X  .  .  .  .  .  .  .  .
S:     .  .  .  .  X  .  .  .  .  .  .  X  .  .  .  .
```
**Why-new:** the bar splits 7+9 — a second kick on slot 8 ("and-a") shoves the second backbeat late to slot 12, a lurching break that still resolves.

### L6 — `gallop_clave_chain`
**PT:** `(HK)HH(HK)(HS)H(HK)HH(HK)HH(HKS)HHH`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X
K:     X  .  .  X  .  .  X  .  .  X  .  .  X  .  .  .
S:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why-new:** kick on a strict every-3-sixteenths chain (3+3+3+3+4) — the tresillo extended across the whole bar — a metal gallop that's also a clave, snare keeping 2&4.

### L7 — `inverted_backbeat`
**PT:** `(HS).H.(HK).H.(HS).H.(HK).H.`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
H:     X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .
S:     X  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
K:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why-new:** full inversion of rock — snare on 1 & 3, kick on 2 & 4. The backbeat instruments swap roles; the ear hears a "wrong-way" pocket that still locks to the grid.

### L8 — `polymeter_5_hat`
**PT:** `(OK)HHH(HS)OHH(HK)HOH(HS)HHO`
```
16ths: 1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
O:     X  .  .  .  .  X  .  .  .  .  X  .  .  .  .  X
H:     .  X  X  X  X  .  X  X  X  X  .  X  X  X  X  .
K:     X  .  .  .  .  .  .  .  X  .  .  .  .  .  .  .
S:     .  .  .  .  X  .  .  .  .  .  .  .  X  .  .  .
```
**Why-new:** a square backbeat pocket (K 1&9, S 2&4) with an open-hat accent cycling every 5 sixteenths (1,6,11,16) — a 5-against-16 polymeter in the cymbal layer over a straight 4/4 body.

---

## How to lock TBB

Pick one Lx above (or a hand-edit of one), copy it under a new `### TBB` heading with its
final PT string + grid, and note the choice in STATE.md's Session Log. Generation seeds
(`CODE/50_generate.py` lane) will then target TBB as the locked core groove.
