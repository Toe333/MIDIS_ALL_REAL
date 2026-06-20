# PT — THE TONY BOLLAS PLAIN TEXT DRUM NOTATION SYSTEM (TM)

> **PT** is a plain-text drum notation format for capturing, comparing, and communicating
> drum patterns from the MIDIS_ALL_REAL corpus and beyond.
> Shorthand: **PT** throughout this document and all project notes.
>
> Each pattern is verified against the actual MIDI grid.
> Use these as named archetypes for labeling, searching, and generation.

## Notation Key

| Symbol | Instrument |
|--------|-----------|
| K | Kick drum |
| S | Snare |
| H | Closed hi-hat |
| O | Open hi-hat |
| R | Ride cymbal |
| C | Crash cymbal |
| T | Tom (generic) |
| Tb | Tambourine (GM 54) |
| VS | Vibra-Slap (GM 58) |
| Cb | Cabasa (GM 69) |
| Clv | Claves (GM 75) |
| ( ) | Simultaneous hits within one slot |
| + | Separator between multi-character names within a slot |
| . | Rest (empty slot) |
| [ ] | Metric grouping bracket (used for odd meters) |

> One `( )` group = one **16th note** by default.
> When resolution differs (e.g. 8th notes for odd-meter patterns), it is stated explicitly.
> Grid resolution is **16th notes** unless noted otherwise.

---

## Patterns

---

### `blast_beat_non_drummer_variant_01`

**Source song:** `5672a90158cffc067ebc828e6ac79cfe`
**Key:** F major · **BPM:** 150 · **Feel:** 150 notated, sounds like 75 (double-time feel)
**Genre context:** Death metal / speed metal adjacent. Programmed, not performed.

**Pattern (1 bar, repeats for entire song):**
```
(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)(KS)(HK)
```

**MIDI grid confirmed:**
```
16ths:  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16
K:      X  X  X  X  X  X  X  X  X  X  X  X  X  X  X  X   (every 16th)
S:      X  .  X  .  X  .  X  .  X  .  X  .  X  .  X  .   (every odd 16th)
H:      .  X  .  X  .  X  .  X  .  X  .  X  .  X  .  X   (every even 16th)
```

**Notes:**
- Real blast beat = `(RK)(S)(RK)(S)...` (ride+kick alternating with snare on 8ths)
- Most common single-kick version = `(HK)(S)(HK)(S)...`
- Double-kick version adds K on every 16th on top of either of the above
- This MIDI variant is a programmed approximation: kick fills every slot, hat fills the gaps
- Pattern is 100% locked — zero bar-to-bar variation — despite `drum_pattern_entropy ≈ 1.0` in the DB (entropy metric bug: all slots filled = max entropy even for a totally rigid pattern)

**Bassline (same song, 1-bar loop):**
```
F F F F F F F F B B B B C C C C   (16th notes, F4 / B3 / C4)
```
= Root (F) × 8 → Tritone down (B3) × 4 → 5th (C4) × 4. Repeats every bar.

---

<!-- ADD NEW PATTERNS BELOW THIS LINE -->

---

### `gypsy_folk_11_8_main_loop`

**Source song:** `ab83f1ddeb3969f0f54634ef74e7880a`
**Key:** E major · **BPM:** 120 · **Genre:** Gypsy / Greek folk
**Time signature:** Intro bar: 7/8 (anomaly, not notated here) → then 11/8 for the rest of the song
**Grid resolution:** 8th notes (11 slots per bar)
**Grouping:** 2 + 2 + 2 + 2 + 3

**Slot grid:**

```
Slots:   1    2    3    4    5    6    7    8    9    10   11
Tamb:    X    X    X    X    X    X    X    X    X    X    X   (also plays 16th subdivisions)
VS+OHH:  X    .    .    .    X    .    .    .    X    .    .
K+Clv:   X    .    X    .    X    .    X    .    X    .    .
Cab:     X    .    .    .    .    .    .    .    .    .    .
```

**TONYBOLLAS notation (8th-note slots, grouping shown with [ ]):**

```
[(Tb+VS+K+Cb)(Tb)] [(Tb+K)(Tb)] [(Tb+VS+K)(Tb)] [(Tb+K)(Tb)] [(Tb+VS+K)(Tb)(Tb)]
```

**Notes:**
- The Cabasa hits only on slot 1 — the strongest downbeat marker, effectively announces the bar
- VS (Vibra-Slap) and OHH (Open Hi-Hat) play the same rhythm — accent on slots 1, 5, 9 (every 4 slots except the final group which is 3)
- Kick and Claves play the same rhythm — hits on every odd slot (1,3,5,7,9), then two rests to close the 11
- Tambourine locks all 16th subdivisions (continuous 16th pulse underneath)
- The 2+2+2+2+3 grouping is the defining feel: the final group of 3 creates the "limp" that makes 11/8 sound like it does
- GM percussion pitches: Tb=54, VS=58, Cb=69, Clv=75, OHH=46
- **DB failure:** stored as 4/4 with `drum_pattern_entropy ≈ 1.0` — both completely wrong
