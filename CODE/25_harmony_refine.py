#!/usr/bin/env python3
"""25_harmony_refine.py — deep HARMONY features, recomputed from the NOTESEQ_DATA cache.

Harmony is one of the three first-class pillars (rhythm #1, then melody + harmony).
The existing catalog already has aggregate harmony (key/mode/n_unique_chords/
chord_density/progression_complexity). This adds TIME-ORDERED harmony from the actual
note sequences (impossible from the pickle histograms):

  * per-beat chord estimate via template matching (maj/min/dim/aug/7ths/sus)
  * harmonic_rhythm        — chord changes per bar
  * chord_change_rate      — chord changes per beat
  * n_chord_segments, progression_entropy (entropy of chord-to-chord bigrams)
  * modulation: windowed key (Krumhansl) -> n_key_areas, key_changes, key_stability
  * tension: mean/std interval-class dissonance over time
  * diatonic_ratio         — fraction of notes inside the global key's scale
  * dominant_function_ratio, n_distinct_chord_roots

Outputs: _work/harmony_features.parquet

Usage:
  python3 CODE/25_harmony_refine.py                 # all cached buckets
  python3 CODE/25_harmony_refine.py --buckets 00,01
  python3 CODE/25_harmony_refine.py --merge-only
"""
import os, sys, glob, json, argparse, time
import numpy as np
import pandas as pd
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C

NOTESEQ = os.path.join(C.ROOT, "NOTESEQ_DATA")
OUT = os.path.join(C.WORK, "harmony_features.parquet")
PARTS = os.path.join(C.WORK, "harmony_parts")

# chord templates (relative pitch classes from root) -> quality label
TEMPLATES = {
    "maj": (0, 4, 7), "min": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8),
    "dom7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10),
    "sus": (0, 5, 7),
}
MAJOR_SCALE = {0, 2, 4, 5, 7, 9, 11}
MINOR_SCALE = {0, 2, 3, 5, 7, 8, 10}
# interval-class roughness weights (ic1=m2 ... ic6=tritone)
IC_DISS = np.array([1.0, 0.5, 0.2, 0.15, 0.1, 0.65])


def estimate_chord(chroma):
    """Return (root, quality) best fitting the 12-d chroma, or (-1,'N')."""
    if chroma.sum() <= 0 or (chroma > 0).sum() < 2:
        return -1, "N"
    cn = chroma / chroma.sum()
    best, best_score = (-1, "N"), -1e9
    for root in range(12):
        for q, tmpl in TEMPLATES.items():
            tset = [(root + i) % 12 for i in tmpl]
            inn = sum(cn[t] for t in tset)
            out = cn.sum() - inn
            score = inn - 0.55 * out - 0.05 * (len(tmpl))  # slight bias to simpler chords
            if score > best_score:
                best, best_score = (root, q), score
    return best


def dissonance(chroma):
    pcs = np.where(chroma > 0)[0]
    if len(pcs) < 2:
        return 0.0
    tot, npair = 0.0, 0
    for i in range(len(pcs)):
        for j in range(i + 1, len(pcs)):
            ic = min((pcs[j] - pcs[i]) % 12, (pcs[i] - pcs[j]) % 12)
            if 1 <= ic <= 6:
                tot += IC_DISS[ic - 1]; npair += 1
    return tot / npair if npair else 0.0


def harmony_features(arr, tpb):
    f = {}
    if arr is None or len(arr) == 0 or tpb <= 0:
        return f
    starts = arr[:, 0].astype(np.float64)
    pitches = arr[:, 3].astype(np.int64)
    span = float((starts + arr[:, 1]).max())
    win = float(tpb)                                   # 1-beat harmonic window
    nwin = int(min(span / win + 1, 4096))
    if nwin < 2:
        return f
    widx = np.clip((starts / win).astype(np.int64), 0, nwin - 1)
    chroma = np.zeros((nwin, 12))
    for wi, p in zip(widx, pitches):
        chroma[wi, p % 12] += 1

    # per-window chord + dissonance
    chords, diss = [], []
    for w in range(nwin):
        if chroma[w].sum() == 0:
            continue
        chords.append(estimate_chord(chroma[w]))
        diss.append(dissonance(chroma[w]))
    chords = [c for c in chords if c[0] >= 0]
    if not chords:
        return f
    # collapse consecutive identical chords -> chord segments (the progression)
    prog = [chords[0]]
    for c in chords[1:]:
        if c != prog[-1]:
            prog.append(c)
    n_bars = max(span / (tpb * 4.0), 1.0)
    f["n_chord_segments"] = len(prog)
    f["harmonic_rhythm"] = round((len(prog) - 1) / n_bars, 4)          # changes per bar
    f["chord_change_rate"] = round((len(prog) - 1) / max(nwin, 1), 4)  # changes per beat
    f["n_distinct_chord_roots"] = len(set(r for r, _ in prog))
    f["dominant_function_ratio"] = round(np.mean([q in ("dom7",) for _, q in prog]), 4)
    f["dissonance_mean"] = round(float(np.mean(diss)), 4)
    f["dissonance_std"] = round(float(np.std(diss)), 4)

    # progression entropy: entropy of chord-bigram distribution
    if len(prog) > 2:
        bigrams = Counter(zip(prog[:-1], prog[1:]))
        tot = sum(bigrams.values())
        p = np.array(list(bigrams.values())) / tot
        f["progression_entropy"] = round(float(-(p * np.log2(p)).sum()), 4)

    # modulation via windowed Krumhansl over 8-beat windows
    big = max(nwin // 8, 1)
    keys = []
    for s in range(0, nwin, 8):
        ch = chroma[s:s + 8].sum(axis=0)
        if ch.sum() > 0:
            k, _, _ = C.estimate_key(ch)
            if k:
                keys.append(k)
    if keys:
        kc = Counter(keys)
        glob_key = kc.most_common(1)[0][0]
        f["n_key_areas"] = len(kc)
        f["key_changes"] = int(sum(1 for a, b in zip(keys[:-1], keys[1:]) if a != b))
        f["key_stability"] = round(kc[glob_key] / len(keys), 4)
        # diatonic ratio against the global key
        root_name, mode = glob_key.split()
        root = C._PC_NAMES.index(root_name) if hasattr(C, "_PC_NAMES") else 0
        scale = MAJOR_SCALE if mode == "major" else MINOR_SCALE
        inb = [((int(p) - root) % 12) in scale for p in pitches]
        f["diatonic_ratio"] = round(float(np.mean(inb)), 4)
    return f


def process_bucket(bucket):
    npz = os.path.join(NOTESEQ, bucket + ".npz")
    meta = os.path.join(NOTESEQ, bucket + ".meta.json")
    if not (os.path.exists(npz) and os.path.exists(meta)):
        return bucket, 0
    # Resume support: skip buckets whose part already exists (set HARMONY_FORCE=1 to redo).
    part = os.path.join(PARTS, bucket + ".parquet")
    if os.path.exists(part) and os.environ.get("HARMONY_FORCE") != "1":
        try:
            return bucket, len(pd.read_parquet(part, columns=["md5"]))
        except Exception:  # noqa: BLE001 — corrupt/partial part, reprocess
            pass
    tpbs = json.load(open(meta))
    z = np.load(npz)
    recs = []
    for md5 in z.files:
        rec = {"md5": md5}
        try:
            rec.update(harmony_features(z[md5], int(tpbs.get(md5, 480))))
        except Exception as ex:  # noqa: BLE001
            rec["harmony_error"] = repr(ex)[:120]
        recs.append(rec)
    os.makedirs(PARTS, exist_ok=True)
    pd.DataFrame(recs).to_parquet(os.path.join(PARTS, bucket + ".parquet"), index=False)
    return bucket, len(recs)


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
        print(f"[25] merged {len(parts)} -> {OUT} ({len(df)} rows)"); return

    buckets = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(NOTESEQ, "*.npz")))
    if args.buckets:
        want = set(args.buckets.split(","))
        buckets = [b for b in buckets if b in want]
    C.log(f"25_harmony_refine: {len(buckets)} buckets (workers={args.workers})", "harmony.log")
    from multiprocessing import Pool
    t0, done = time.time(), 0
    with Pool(args.workers) as pool:
        for i, (b, n) in enumerate(pool.imap_unordered(process_bucket, buckets), 1):
            done += n
            if i % 16 == 0 or i == len(buckets):
                C.log(f"  [{i}/{len(buckets)}] {done} files {done/(time.time()-t0):.0f}/s", "harmony.log")
    parts = sorted(glob.glob(os.path.join(PARTS, "*.parquet")))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    C.write_parquet_atomic(df, OUT)
    print(f"[25] DONE -> {OUT} ({len(df)} rows, {df.shape[1]} cols)")
    if "harmonic_rhythm" in df:
        print(f"[25] harmonic_rhythm med={df['harmonic_rhythm'].median():.3f}  "
              f"diatonic_ratio med={df['diatonic_ratio'].median():.3f}  "
              f"n_key_areas med={df['n_key_areas'].median():.1f}")


if __name__ == "__main__":
    main()
