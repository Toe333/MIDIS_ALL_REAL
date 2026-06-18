#!/usr/bin/env python3
"""29_groove_dna.py — the canonical 11-D RHYTHM VECTOR ("GrooveDNA") for the corpus.

Rhythm is the project's #1 priority, and pitch/melody/harmony already dominate the
74-D signature. GrooveDNA is the missing piece: a drum-ONLY fingerprint of how a song
GROOVES, so we can cluster by feel and hunt the empty space for music that doesn't
exist yet. It reads the NOTESEQ_DATA cache (no re-parse, fast + iterable, same as
22_rhythm_refine.py) and isolates the drum kit, then distils it to 11 locked dims.

------------------------------------------------------------------------------------
DRUM ISOLATION (non-negotiable architecture rule #1)
  drums = channel 9 OR 10  AND  pitch in the General-MIDI percussion map 35..81.
  In this 0-indexed corpus channel 9 is the GM drum channel (verified: its top
  pitches are 42 hat / 36-35 kick / 38-40 snare / 51 ride). Channel 10 is kept to
  cover files saved with a 1-indexed convention. The 35..81 GM range is applied as
  an AND (not the spec's literal OR) because pitch 35..81 across *all* channels would
  swallow melodic notes (middle-C piano = 60) and destroy drum isolation — GM
  percussion numbers only MEAN drums on the drum channel. This is the one, documented
  deviation; it is the only way to honor "Drum isolation ONLY".

GM percussion key map (the common hits we name; everything 35..81 counts for kit size):
  35 Acoustic Bass Drum   36 Bass Drum 1        37 Side Stick    38 Acoustic Snare
  39 Hand Clap            40 Electric Snare      41/43/45/47/48/50 Toms
  42 Closed Hi-Hat        44 Pedal Hi-Hat        46 Open Hi-Hat
  49 Crash 1  51 Ride 1  52 China  53 Ride Bell  55 Splash  57 Crash 2  59 Ride 2

NORMALIZATION
  All densities are per 4/4 BAR. We work in BEATS (quarter = 1 beat = tick/tpb), which
  is already tempo-independent, so a "120 BPM reference grid" needs no rescale — a bar
  is 4 beats regardless of tempo. Sub-beat positions use the 1/48-beat pulse grid
  (exact for 16ths=3/48, triplets=16/48, swung 8ths=32/48) exactly like 22.
------------------------------------------------------------------------------------

The 11 LOCKED dimensions (order is canonical — index = position in the groove_dna array):
   0 kick_density_bar        kicks per bar — the pulse foundation every groove is built on
   1 snare_backbeat_strength snare hits on beats 2 & 4 / all snare — the popular-music signature
   2 hat_cym_density         hats+cymbals per bar — subdivision "busyness" / energy
   3 perc_diversity          unique drum pitches used — how big/colourful the kit is
   4 swing_cont              0-1 continuous swing from BUR+subdiv — the straight<->shuffle axis
   5 syncopation_drum        off-the-quarter-beat onset % on drums only — groove tension
   6 dotted_groove           dotted/long-short (3:1) adjacent-IOI ratio on drums — shuffle/dotted feel
   7 ghost_dynamics          velocity std on weak 16ths — ghost-note humanization
   8 drum_pattern_entropy    entropy of onset positions in the bar — pattern complexity
   9 bar_drum_variance       mean cosine dist of consecutive bars — fills/variation vs dead loop
  10 groove_composite        weighted blend of 0..9 — a single "how strong is the groove" scalar

All features are float32, NaN-safe, and default to the NEUTRAL value 0.5 when a song has
no drums (or a sub-feature is undefined), so the vector is never NaN downstream.

Output: per-bucket _work/groove_dna_parts/<bucket>.parquet  (md5 + 11 scalars = 12 cols),
        merged to _work/groove_dna.parquet. 23_catalog_merge.py folds these onto the
        catalog and adds the packed `groove_dna` float32[11] array column for clustering.

Usage:
  python3 CODE/29_groove_dna.py                 # all cached buckets
  python3 CODE/29_groove_dna.py --buckets 00,01 # subset
  python3 CODE/29_groove_dna.py --workers 10
  python3 CODE/29_groove_dna.py --merge-only    # just rebuild groove_dna.parquet from parts
"""
import os, sys, glob, json, argparse, time
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "groove_dna.parquet")
PARTS = os.path.join(C.WORK, "groove_dna_parts")

# canonical dim order — index in this list == index in the groove_dna array (LOCKED).
DIMS = [
    "kick_density_bar", "snare_backbeat_strength", "hat_cym_density", "perc_diversity",
    "swing_cont", "syncopation_drum", "dotted_groove", "ghost_dynamics",
    "drum_pattern_entropy", "bar_drum_variance", "groove_composite",
]
NEUTRAL = 0.5                                   # default for a missing/undefined dim

# GM percussion families. We separate the kit so each dim can target the right voice:
# kick carries the pulse, snare carries the backbeat, hats/cymbals carry subdivision.
GM_LO, GM_HI = 35, 81                           # standard GM percussion pitch range
KICK = frozenset({35, 36})                      # bass drums — dim 0 (pulse foundation)
SNARE = frozenset({37, 38, 40})                 # snare + side-stick — dim 1 (backbeat)
HAT = frozenset({42, 44, 46})                   # closed/pedal/open hi-hat — dim 2 (subdiv)
CYM = frozenset({49, 51, 52, 53, 55, 57, 59})   # crashes/rides/splash — dim 2 (subdiv)
HATCYM = HAT | CYM                              # everything that marks the fast grid

GRID16 = 16                                     # 16th-note cells per 4/4 bar (0.25 beat each)
STRONG16 = frozenset({0, 4, 8, 12})             # the four quarter-beats inside a bar
WEAK16 = frozenset({1, 3, 5, 7, 9, 11, 13, 15}) # the "e"/"a" 16ths — where ghost notes live


def _drum_mask(arr):
    """Boolean mask isolating the drum kit (see DRUM ISOLATION block at top)."""
    chan = arr[:, 2]
    pitch = arr[:, 3]
    on_drum_chan = (chan == 9) | (chan == 10)   # 0-indexed GM drum chan (+1-indexed safety)
    in_gm_range = (pitch >= GM_LO) & (pitch <= GM_HI)
    return on_drum_chan & in_gm_range           # AND, not OR — keeps melodic notes out


def _onsets_beats(starts_beats):
    """Collapse near-simultaneous drum hits onto the 1/48-beat pulse grid (as in 22).

    1/48 represents 16ths (3/48), triplets (16/48) and swung 8ths (32/48) EXACTLY,
    so chord-stacked drum hits merge without corrupting triplet/swing timing."""
    q = np.round(starts_beats / (1.0 / 48.0)).astype(np.int64)
    return np.sort(np.unique(q) * (1.0 / 48.0))


def _swing_cont(ob):
    """0-1 continuous swing from the Beat-Upbeat Ratio over drum pulse-onsets.

    Same BUR logic as 22 (on-beat 8th length / off-beat 8th length) but squashed to a
    continuous 0..1: straight (BUR~1)->0, hard swing (BUR>=2)->1, damped by how many
    beats are actually 8th-divided so a couple of accidental hits can't fake a shuffle."""
    if len(ob) < 4:
        return NEUTRAL
    beat_idx = np.floor(ob + 1e-6).astype(np.int64)
    phase = ob - beat_idx
    from collections import defaultdict
    by_beat = defaultdict(list)
    for b, p in zip(beat_idx, phase):
        by_beat[b].append(p)
    burs, n_onbeat = [], 0
    for ps in by_beat.values():
        ps = sorted(ps)
        if not any(p < 0.15 for p in ps):       # need a downbeat to anchor the pair
            continue
        n_onbeat += 1
        if any(0.15 < p <= 0.40 for p in ps):    # a 16th/triplet onset -> not a swing 8th beat
            continue
        mids = [p for p in ps if 0.40 < p < 0.72]  # the swung upbeat (excludes 0.75 dotted)
        if len(mids) == 1:
            pm = mids[0]
            burs.append(pm / (1.0 - pm))
    if not burs or n_onbeat == 0:
        return NEUTRAL
    med = float(np.median(burs))
    conf = len(burs) / n_onbeat                  # fraction of beats that are 8th-divided
    base = np.clip((med - 1.0) / 1.0, 0.0, 1.0)  # BUR 1->0, 2->1
    return float(np.clip(base * (0.5 + 0.5 * conf), 0.0, 1.0))


def _dotted_groove(ob):
    """Fraction of adjacent drum IOIs forming a ~3:1 long-short (dotted/shuffle) figure."""
    if len(ob) < 3:
        return NEUTRAL
    ioi = np.diff(ob)
    ioi = ioi[ioi > 0]
    if len(ioi) < 2:
        return NEUTRAL
    a, b = ioi[:-1], ioi[1:]
    dotted = np.abs(np.log2(a / b) - np.log2(3.0)) <= 0.16   # long:short ~ 3:1
    return float(dotted.mean())


def _grid16(t_beats):
    """Map beat positions to their 0..15 sixteenth cell within the 4/4 bar."""
    in_bar = np.mod(t_beats, 4.0)                # position within the bar, in beats
    return (np.round(in_bar / 0.25).astype(np.int64) % GRID16)


def groove_of(arr, tpb):
    """Compute the 11 GrooveDNA dims for one note-sequence. Always returns all 11 keys."""
    f = {d: NEUTRAL for d in DIMS}               # NaN-safe: start everyone at neutral 0.5
    if arr is None or len(arr) == 0 or tpb <= 0:
        return f
    drums = arr[_drum_mask(arr)]
    if len(drums) == 0:                          # no kit -> leave all dims neutral
        return f

    pitch = drums[:, 3]
    vel = drums[:, 4].astype(np.float64)
    t = drums[:, 0].astype(np.float64) / tpb     # onset times in beats (tempo-independent)

    # --- bar accounting: a bar is 4 beats; density is per bar (normalization rule) ---
    bar = np.floor(t / 4.0).astype(np.int64)
    n_bars = float(bar.max() - bar.min() + 1)    # bars actually spanned by the drums
    n_bars = max(n_bars, 1.0)

    # --- dim 0: kick density — the pulse foundation under everything ---
    f["kick_density_bar"] = float(np.isin(pitch, list(KICK)).sum()) / n_bars

    # --- dim 1: snare backbeat — fraction of snare on beats 2 & 4 (the popular signature) ---
    snare_t = t[np.isin(pitch, list(SNARE))]
    if len(snare_t):
        ph = np.mod(snare_t, 4.0)                # bar-phase in beats; backbeat = ~1.0 or ~3.0
        on_back = (np.abs(ph - 1.0) <= 0.15) | (np.abs(ph - 3.0) <= 0.15)
        f["snare_backbeat_strength"] = float(on_back.mean())

    # --- dim 2: hat/cymbal density — subdivision busyness / energy of the groove ---
    f["hat_cym_density"] = float(np.isin(pitch, list(HATCYM)).sum()) / n_bars

    # --- dim 3: kit diversity — how many distinct drum voices colour the pattern ---
    f["perc_diversity"] = float(len(np.unique(pitch)))

    # --- pulse-onset positions (all drums) feed the swing/dotted/grid dims ---
    ob = _onsets_beats(t)
    f["swing_cont"] = _swing_cont(ob)            # dim 4: straight <-> shuffle axis
    f["dotted_groove"] = _dotted_groove(ob)      # dim 6: dotted/long-short feel

    # --- 16th-grid occupancy: the backbone for syncopation/entropy/variance/ghosts ---
    g = _grid16(t)                               # each drum hit's 0..15 cell in the bar
    # --- dim 5: syncopation — share of hits OFF the four quarter-beats (groove tension) ---
    on_strong = np.isin(g, list(STRONG16))
    f["syncopation_drum"] = float(1.0 - on_strong.mean())

    # --- dim 7: ghost dynamics — velocity spread on weak 16ths (human ghost notes) ---
    weak = np.isin(g, list(WEAK16))
    if weak.sum() >= 2:
        f["ghost_dynamics"] = float(np.clip(np.std(vel[weak]) / 127.0, 0.0, 1.0))

    # --- dim 8: pattern entropy — how evenly hits spread over the 16 cells (complexity) ---
    hist = np.bincount(g, minlength=GRID16).astype(np.float64)
    s = hist.sum()
    if s > 0:
        p = hist[hist > 0] / s
        f["drum_pattern_entropy"] = float(-(p * np.log2(p)).sum() / np.log2(GRID16))

    # --- dim 9: bar-to-bar variance — fills/variation vs a dead-looped pattern ---
    bars_present = np.unique(bar)
    if len(bars_present) >= 2:
        mat = np.zeros((len(bars_present), GRID16), dtype=np.float64)
        bpos = {b: i for i, b in enumerate(bars_present)}
        for bi, gi in zip(bar, g):
            mat[bpos[bi], gi] += 1.0             # per-bar 16-cell onset-count vector
        dists = []
        for i in range(len(bars_present) - 1):
            u, v = mat[i], mat[i + 1]
            nu, nv = np.linalg.norm(u), np.linalg.norm(v)
            if nu > 0 and nv > 0:
                dists.append(1.0 - float(u @ v) / (nu * nv))   # cosine distance
        if dists:
            f["bar_drum_variance"] = float(np.clip(np.mean(dists), 0.0, 1.0))

    # --- dim 10: composite — one weighted scalar "how strong/interesting is the groove" ---
    # densities are squashed to 0-1 first so the blend is scale-balanced; weights sum to 1.
    nk = np.clip(f["kick_density_bar"] / 8.0, 0.0, 1.0)
    nh = np.clip(f["hat_cym_density"] / 16.0, 0.0, 1.0)
    nd = np.clip(f["perc_diversity"] / 12.0, 0.0, 1.0)
    f["groove_composite"] = float(
        0.16 * nk + 0.18 * f["snare_backbeat_strength"] + 0.10 * nh + 0.06 * nd
        + 0.10 * f["swing_cont"] + 0.12 * f["syncopation_drum"] + 0.06 * f["dotted_groove"]
        + 0.06 * f["ghost_dynamics"] + 0.08 * f["drum_pattern_entropy"]
        + 0.08 * f["bar_drum_variance"])
    return f


def process_bucket(bucket):
    """Compute GrooveDNA for one cache bucket. Writes the part parquet AND returns the
    DataFrame (md5 + 11 scalar cols = 12 cols), so it doubles as the validation harness."""
    bucket = str(bucket)                         # accept "00".."ff" or a bare int label
    npz = os.path.join(NOTESEQ, bucket + ".npz")
    meta = os.path.join(NOTESEQ, bucket + ".meta.json")
    if not (os.path.exists(npz) and os.path.exists(meta)):
        return pd.DataFrame(columns=["md5"] + DIMS)
    tpbs = json.load(open(meta))
    z = np.load(npz)
    recs = []
    for md5 in z.files:
        arr = z[md5]
        rec = {"md5": md5}
        try:
            rec.update(groove_of(arr, int(tpbs.get(md5, 480))))
        except Exception as ex:  # noqa: BLE001 — never let one bad file kill a bucket
            rec.update({d: NEUTRAL for d in DIMS})   # neutral, stay NaN-safe
        recs.append(rec)
    df = pd.DataFrame(recs, columns=["md5"] + DIMS)
    for d in DIMS:                               # lock the dtype: every dim is float32
        df[d] = df[d].astype(np.float32)
    os.makedirs(PARTS, exist_ok=True)
    df.to_parquet(os.path.join(PARTS, bucket + ".parquet"), index=False)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buckets", type=str, default="")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args()

    if args.merge_only:
        parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
        df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
        C.write_parquet_atomic(df, OUT)
        print(f"[29] merged {len(parts)} buckets -> {OUT} ({len(df)} rows)")
        return

    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ, "*.npz")))
    if args.buckets:
        want = set(args.buckets.split(","))
        buckets = [b for b in buckets if b in want]
    C.log(f"29_groove_dna: {len(buckets)} cached buckets to process (workers={args.workers})", "groove.log")

    from multiprocessing import Pool
    t0, done = time.time(), 0
    with Pool(args.workers) as pool:
        for i, df in enumerate(pool.imap_unordered(process_bucket, buckets), 1):
            done += len(df)
            if i % 16 == 0 or i == len(buckets):
                C.log(f"  [{i}/{len(buckets)}] {done} files {done/(time.time()-t0):.0f}/s", "groove.log")

    parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    C.write_parquet_atomic(df, OUT)
    print(f"[29] DONE -> {OUT} ({len(df)} rows, {df.shape[1]} cols)")
    has_drums = df["perc_diversity"] > NEUTRAL   # neutral 0.5 == no kit; real kits have >=1 voice
    print(f"[29] files with a drum kit: {int(has_drums.sum())} / {len(df)}")
    print(f"[29] medians (drum files only): kick/bar={df.loc[has_drums,'kick_density_bar'].median():.2f}  "
          f"backbeat={df.loc[has_drums,'snare_backbeat_strength'].median():.2f}  "
          f"swing={df.loc[has_drums,'swing_cont'].median():.2f}  "
          f"sync={df.loc[has_drums,'syncopation_drum'].median():.2f}  "
          f"composite={df.loc[has_drums,'groove_composite'].median():.2f}")


def _validate():
    # validation: run one real bucket end-to-end and assert the locked 12-col shape.
    test = process_bucket("42")                  # bucket "42" exists in the cache
    assert len(test.columns) == 12, f"expected 12 cols (md5+11), got {len(test.columns)}"
    assert list(test.columns) == ["md5"] + DIMS, "column order is not the locked GrooveDNA order"
    assert all(str(test[d].dtype) == "float32" for d in DIMS), "all 11 dims must be float32"
    assert not test[DIMS].isna().any().any(), "GrooveDNA must be NaN-safe (neutral 0.5 fill)"
    print(test.head())
    print(f"GrooveDNA validated ✓  ({len(test)} rows, {len(DIMS)} dims, bucket 42)")


if __name__ == "__main__":
    # default: process the whole corpus (main). `--validate` runs the self-test instead,
    # so the locked validation block stays runnable without hijacking the real CLI run.
    if "--validate" in sys.argv:
        _validate()
    else:
        main()
