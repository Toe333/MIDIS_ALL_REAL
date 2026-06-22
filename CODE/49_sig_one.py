#!/usr/bin/env python3
"""49_sig_one.py — signature-of-ONE-MIDI: embed a single .mid into the SAME N×88
space as SIGNATURES_DATA/signatures_ext.npy, so a freshly generated file can be
scored by cosine against an empty-corner target.

THE PROBLEM this solves
-----------------------
26_signature_extend.py builds the 88-D matrix by z-scoring / L2-normalizing each
pillar over the WHOLE corpus, but it BAKES those per-column scaler stats into the
matrix and never saves them. To place a brand-new file in the same space we must
(a) re-derive that exact scaler from the catalog, and (b) re-extract every raw
feature with the SAME per-file functions the batch pipeline used.

WHAT IT REUSES (no logic forked — imported from the batch scripts)
  pitch 36  : 12_signatures.signature()  (total_pitches/ms_chords from the parsed notes)
  rhythm 20 : 21_sequences (syncopation/polyrhythm/voices, tempo_curve),
              22_rhythm_refine.rhythm_of (swing), 24 mel_rhythm_*, + felt_bpm/meter
  melody 13 : 24_melody_refine.melody_features
  harmony  8: 25_harmony_refine.harmony_features (+ legacy chord-count cols imputed)
  groove 11 : 29_groove_dna.groove_of

The scaler (log1p flags, per-column median/mean/std, block order, weights) is a
faithful re-implementation of 26_signature_extend.scale_block — verified by the
`verify` command: rebuilding a known corpus row FROM THE CATALOG reproduces its
stored ext vector at cosine 1.0 (proves scaler+assembly), and rebuilding the same
row FROM ITS .mid reports the feature-extraction fidelity.

A handful of columns are produced by upstream scripts NOT replayed here (the v2
detection felt_bpm/ts_final and the original-build chord-count columns
n_distinct_chords/n_unique_chords/chord_density/has_extended_harmony/
tempo_stability/tempo_change_count). From a raw .mid those are approximated where
cheap and otherwise left NaN → median-imputed by the scaler (exactly what 26 does
for missing cells). This affects ~6 of 88 dims; the `verify` cosine quantifies it.

Usage
  python CODE/49_sig_one.py build-scaler            # (re)build _work/sig_scaler.pkl
  python CODE/49_sig_one.py verify [md5 ...]        # cat-path & midi-path cosine vs stored
  python CODE/49_sig_one.py vec path/to/file.mid    # print the 88-D vector

Import
  from importlib ... ; sig = vector_from_midi("foo.mid")   # -> np.float32[88]
"""
import os, sys, pickle, argparse, json
from collections import Counter
import numpy as np
import pandas as pd
from importlib import util as _u

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)
import _common as C  # noqa

SIG_DIR = os.path.join(ROOT, "SIGNATURES_DATA")
NPY = os.path.join(SIG_DIR, "signatures.npy")          # N×36 pitch (by md5 row)
IDX = os.path.join(SIG_DIR, "signatures_md5.txt")
EXT = os.path.join(SIG_DIR, "signatures_ext.npy")      # N×88 (truth to verify against)
KNN = os.path.join(SIG_DIR, "knn_cosine.pkl")          # block_dims / weights / feature_names
META = os.path.join(ROOT, "catalog", "metadata.parquet")
SCALER = os.path.join(ROOT, "_work", "sig_scaler.pkl")

LOG_MAX = 50.0   # must match 26_signature_extend
CLIP = 8.0

# ---- import the batch per-file feature functions (single source of truth) ----
def _load(modfile, name):
    spec = _u.spec_from_file_location(name, os.path.join(CODE, modfile))
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

_m12 = _load("12_signatures.py", "sig12")
_m21 = _load("21_sequences.py", "seq21")
_m22 = _load("22_rhythm_refine.py", "rhy22")
_m24 = _load("24_melody_refine.py", "mel24")
_m25 = _load("25_harmony_refine.py", "har25")
_m29 = _load("29_groove_dna.py", "grv29")

# ---- the 88-column contract (from the built kNN payload) ---------------------
_meta = pickle.load(open(KNN, "rb"))
BLOCK_DIMS = _meta["block_dims"]        # {'pitch':36,'rhythm':20,'melody':13,'harmony':8,'groove':11}
WEIGHTS = _meta["weights"]              # {'pitch':1,'rhythm':2,'melody':1,'harmony':1,'groove':2}
FEAT = _meta["feature_names"]           # 88 names, pitch_0..35 then the rest
PITCH_DIM = BLOCK_DIMS["pitch"]
PILLAR_ORDER = ["pitch", "rhythm", "melody", "harmony", "groove"]
# slice the non-pitch feature names per pillar, in order
_off = PITCH_DIM
PILLAR_COLS = {}
for p in PILLAR_ORDER[1:]:
    n = BLOCK_DIMS[p]
    PILLAR_COLS[p] = FEAT[_off:_off + n]
    _off += n
NONPITCH = FEAT[PITCH_DIM:]
TEMPO_CATS = ["constant", "gradual", "erratic", "rubato"]


# ============================ scaler =========================================
def derive_meter(val):
    """ts_final 'n/d' -> (ts_num, ts_compound). compound=1 for 6/8,9/8,12/8."""
    if not isinstance(val, str) or "/" not in val:
        return np.nan, np.nan
    a, _, b = val.partition("/")
    try:
        n, d = int(a), int(b)
    except ValueError:
        return np.nan, np.nan
    return float(n), (1.0 if (d == 8 and n in (6, 9, 12)) else 0.0)


def _catalog_nonpitch_frame(cat):
    """Build the exact 52-column non-pitch frame 26 feeds to scale_block, in FEAT order.
    cat is the catalog reindexed to signatures_md5 order (md5 index)."""
    out = pd.DataFrame(index=cat.index)
    base = [c for c in NONPITCH
            if not c.startswith("tempo_class__") and c not in ("ts_num", "ts_compound")]
    for c in base:
        out[c] = cat[c] if c in cat.columns else np.nan
    # tempo_class one-hot (missing -> all zero, matches 26's 'missing' sentinel)
    tc = cat["tempo_class"].astype("object") if "tempo_class" in cat.columns else pd.Series(index=cat.index, dtype=object)
    tc = tc.where(tc.notna(), "missing")
    for cat_name in TEMPO_CATS:
        out[f"tempo_class__{cat_name}"] = (tc == cat_name).astype(float)
    # corrected meter -> ts_num / ts_compound
    src = cat["ts_final"] if "ts_final" in cat.columns else pd.Series(index=cat.index, dtype=object)
    nums, comps = zip(*[derive_meter(v) for v in src.to_numpy()]) if len(src) else ([], [])
    out["ts_num"] = np.array(nums, dtype=float) if len(nums) else np.nan
    out["ts_compound"] = np.array(comps, dtype=float) if len(comps) else np.nan
    return out[NONPITCH]   # enforce exact column order


def build_scaler(save=True):
    """Re-derive 26's per-column scaler (mirrors scale_block) and cache it."""
    md5s = [l.strip() for l in open(IDX) if l.strip()]
    need = (["md5", "tempo_class", "ts_final"] +
            [c for c in NONPITCH if not c.startswith("tempo_class__")
             and c not in ("ts_num", "ts_compound")])
    import pyarrow.parquet as pq
    avail = set(pq.ParquetFile(META).schema.names)
    cat = pd.read_parquet(META, columns=[c for c in need if c in avail])
    cat = cat.drop_duplicates("md5").set_index("md5").reindex(md5s)
    frame = _catalog_nonpitch_frame(cat)

    params = {}   # col -> (logged, median, mu, sd)
    for c in NONPITCH:
        x = np.array(frame[c].to_numpy(dtype=np.float64), copy=True)
        finite = x[np.isfinite(x)]
        logged = bool(finite.size and finite.min() >= 0 and finite.max() > LOG_MAX)
        if logged:
            x = np.log1p(x)
        nan = ~np.isfinite(x)
        med = np.nanmedian(np.where(np.isfinite(x), x, np.nan))
        if not np.isfinite(med):
            med = 0.0
        x[nan] = med
        mu, sd = float(x.mean()), float(x.std())
        params[c] = (logged, float(med), mu, sd)

    payload = {"params": params, "block_dims": BLOCK_DIMS, "weights": WEIGHTS,
               "feature_names": FEAT, "pillar_cols": PILLAR_COLS,
               "log_max": LOG_MAX, "clip": CLIP, "n_rows": len(md5s)}
    if save:
        os.makedirs(os.path.dirname(SCALER), exist_ok=True)
        with open(SCALER, "wb") as fh:
            pickle.dump(payload, fh, protocol=4)
        print(f"[49] scaler -> {SCALER}  ({len(params)} non-pitch cols, {len(md5s)} rows)")
    return payload


def _load_scaler():
    if not os.path.exists(SCALER):
        return build_scaler()
    return pickle.load(open(SCALER, "rb"))


# ============================ assembly =======================================
def _l2(x):
    n = np.linalg.norm(x)
    return x / n if n > 1e-12 else x


def assemble(pitch36, raw, scaler=None):
    """pitch36: np.float32[36] raw pitch signature. raw: dict of non-pitch col -> value
    (NaN/absent allowed). Returns the 88-D float32 vector in the corpus space."""
    sc = scaler or _load_scaler()
    P = sc["params"]
    parts = [_l2(np.asarray(pitch36, dtype=np.float64)) * np.sqrt(WEIGHTS["pitch"])]
    for pillar in PILLAR_ORDER[1:]:
        cols = sc["pillar_cols"][pillar]
        z = np.empty(len(cols), dtype=np.float64)
        for i, c in enumerate(cols):
            logged, med, mu, sd = P[c]
            v = raw.get(c, np.nan)
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = np.nan
            if logged and np.isfinite(v) and v >= -1.0:
                v = np.log1p(v)
            if not np.isfinite(v):
                v = med
            v = (v - mu) / sd if sd > 1e-12 else (v - mu)
            z[i] = np.clip(v, -CLIP, CLIP)
        parts.append(_l2(z) * np.sqrt(WEIGHTS[pillar]))
    return np.concatenate(parts).astype(np.float32)


# ============================ raw feature extraction =========================
def raw_from_catalog(md5):
    """Pull the raw non-pitch cols + stored pitch sig for a corpus md5 (EXACT path)."""
    md5s = [l.strip() for l in open(IDX) if l.strip()]
    row = md5s.index(md5)
    pitch36 = np.load(NPY, mmap_mode="r")[row].astype(np.float64)
    cat = pd.read_parquet(META)
    cat = cat[cat.md5 == md5]
    if cat.empty:
        raise SystemExit(f"{md5} not in catalog")
    cat = cat.drop_duplicates("md5").set_index("md5").reindex([md5])
    frame = _catalog_nonpitch_frame(cat)
    raw = {c: frame[c].iloc[0] for c in NONPITCH}
    return np.asarray(pitch36), raw


def _ms_chords(path):
    """Reconstruct ms_chords_counts EXACTLY as 03_make_metadata.py did, on TMIDIX's
    millisecond score (opus2score(to_millisecs(opus))): walk notes in ms-time order,
    group those sharing an onset ms into a chord of DISTINCT non-drum pitch-classes,
    keep len>1, count identical pitch-class sets. Also returns dur_sec from
    pitches_times_sum_ms (sum of inter-onset gaps, capped 1e7) so chord_density matches.
    Returns ([[pcs, count], ...], dur_sec)."""
    T = C.tmidix()
    opus = T.midi2opus(open(path, "rb").read())
    ms_score = T.opus2score(T.to_millisecs(opus))
    msm = [e for trk in ms_score[1:] for e in trk if e and e[0] == "note"]
    if not msm:
        return [], 0.0
    msm.sort(key=lambda x: x[1])
    chords, cho, pe = [], [], msm[0]
    for e in msm:
        if (e[1] - pe[1]) == 0:
            if e[3] != 9 and (e[4] % 12) not in cho:
                cho.append(e[4] % 12)
        else:
            if cho:
                chords.append(sorted(cho))
            cho = []
            if e[3] != 9 and (e[4] % 12) not in cho:
                cho.append(e[4] % 12)
        pe = e
    if cho:
        chords.append(sorted(cho))
    cnt = Counter(tuple(c) for c in chords if len(c) > 1)
    mcc = [[list(pcs), c] for pcs, c in cnt.most_common()]
    # pitches_times_sum_ms -> dur_sec (03 lines 86-93)
    times, pt, start = [], msm[0][1], True
    for e in msm:
        if (e[1] - pt) != 0 or start:
            times.append(e[1] - pt); start = False
        pt = e[1]
    dur_sec = min(10_000_000, sum(times)) / 1000.0
    return mcc, dur_sec


def _pitch_sig_from_notes(arr, mcc):
    """36-D pitch signature for a parsed note array, reusing 12.signature.
    total_pitches_counts maps drum pitches to token+128 (chan 9), matching 03."""
    pitches = arr[:, 3].astype(np.int64)
    chans = arr[:, 2].astype(np.int64)
    tok = np.where(chans == 9, pitches + 128, pitches)
    tpc = [[t, c] for t, c in Counter(tok.tolist()).most_common()]
    return _m12.signature({"total_pitches_counts": tpc, "ms_chords_counts": mcc})


def _felt_bpm(tempos, end_tick):
    """Tick-weighted DOMINANT BPM (the bpm_v2 rule from 41_redetect_tempo_meter):
    collapse same-tick events last-writer-wins, weight each by ticks active.
    felt_bpm == bpm_v2 for ~93% of the corpus; the v2 half/double 'felt' adjuster
    (6.5% of files) is not replayed here, so this is bpm_v2 as the felt stand-in."""
    if not tempos:
        return 120.0
    timeline = []
    for tk, q in sorted(tempos):
        if timeline and timeline[-1][0] == tk:
            timeline[-1] = (tk, q)
        else:
            timeline.append((tk, q))
    span = max(end_tick, timeline[-1][0] + 1)
    w = {}
    for j, (tk, q) in enumerate(timeline):
        nxt = timeline[j + 1][0] if j + 1 < len(timeline) else span
        w[q] = w.get(q, 0) + max(1, nxt - tk)
    return float(max(w, key=w.get))


def raw_from_midi(path):
    """Re-extract every reproducible feature from a .mid -> (pitch36, raw-dict).
    Legacy/detection columns this script does not replay are left NaN (median-imputed)."""
    tpb, arr, tempos, timesigs = _m21.parse_notes(path)
    if len(arr) == 0:
        raise ValueError("no notes")
    mcc, dur_sec = _ms_chords(path)
    raw = {}
    # --- rhythm ---
    rf = _m21.rhythm_features(tpb, arr, tempos)
    for k in ("syncopation", "polyrhythm_hint", "n_rhythm_voices"):
        if k in rf:
            raw[k] = rf[k]
    tc = _m21.tempo_curve(tempos)
    raw["n_tempo_changes"] = tc.get("n_tempo_changes")
    raw["tempo_cv"] = tc.get("tempo_cv")
    tclass = tc.get("tempo_class", "constant")
    for cat_name in TEMPO_CATS:
        raw[f"tempo_class__{cat_name}"] = 1.0 if tclass == cat_name else 0.0
    ro = _m22.rhythm_of(arr, tpb)
    for k in ("swing_bur", "swing_confidence", "swing_n_beats"):
        if k in ro:
            raw[k] = ro[k]
    raw["tempo_change_count"] = float(len(tempos))     # 03: count of set_tempo events
    bpms = [b for _, b in tempos]
    raw["tempo_stability"] = round(float(np.std(bpms)), 3) if len(bpms) > 1 else 0.0  # 10_scan
    # felt_bpm + meter
    end_tick = int((arr[:, 0] + arr[:, 1]).max())
    raw["felt_bpm"] = _felt_bpm(tempos, end_tick)
    # ts_final sanitization (the v2 meter rule): keep a real musical meter, else default
    # 4/4 — junk like 1/4, 16/16, 2/1, 132/4 (33k files) all collapse to 4/4 in the corpus.
    num, denom = 4, 4
    if timesigs:
        _, n, dpow = timesigs[0]
        d = 2 ** int(dpow)
        if 2 <= n <= 12 and d in (2, 4, 8):
            num, denom = int(n), d
    raw["ts_num"] = float(num)
    raw["ts_compound"] = 1.0 if (denom == 8 and num in (6, 9, 12)) else 0.0
    # --- melody (also supplies mel_rhythm_*) ---
    mf = _m24.melody_features(arr, tpb)
    for c in PILLAR_COLS["melody"] + ["mel_rhythm_straight", "mel_rhythm_dotted", "mel_rhythm_triplet"]:
        if c in mf:
            raw[c] = mf[c]
    # --- harmony: 4 from 25 + 4 legacy chord-count cols from the reconstructed chords ---
    hf = _m25.harmony_features(arr, tpb)
    for c in ("n_chord_segments", "harmonic_rhythm", "chord_change_rate", "n_distinct_chord_roots"):
        if c in hf:
            raw[c] = hf[c]
    real = [(pcs, c) for pcs, c in mcc if len(pcs) > 1]
    n_unique = len(real)
    raw["n_distinct_chords"] = float(n_unique)          # 03: len(mcc with count>0)
    raw["n_unique_chords"] = float(n_unique)            # 13: len(real)
    raw["has_extended_harmony"] = 1.0 if any(len(p) >= 4 for p, _ in real) else 0.0
    total_chord_events = sum(c for _, c in real)        # 13: chord_density
    raw["chord_density"] = round(total_chord_events / dur_sec, 3) if dur_sec > 0 else np.nan
    # --- groove ---
    raw.update(_m29.groove_of(arr, tpb))
    return _pitch_sig_from_notes(arr, mcc), raw


def vector_from_midi(path, scaler=None):
    p, raw = raw_from_midi(path)
    return assemble(p, raw, scaler)


def vector_from_catalog(md5, scaler=None):
    p, raw = raw_from_catalog(md5)
    return assemble(p, raw, scaler)


# ============================ CLI ============================================
def _cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def cmd_verify(md5s):
    sc = _load_scaler()
    ext = np.load(EXT, mmap_mode="r")
    idx = [l.strip() for l in open(IDX) if l.strip()]
    pos = {m: i for i, m in enumerate(idx)}
    if not md5s:
        md5s = ["e801809a9e51919993df2c5fe4453037",   # rank-1 target (drums)
                "cf541385bbb97b56bf4887e73bd5420c"]
    print(f"{'md5':34} {'cat-cos':>8} {'midi-cos':>9}")
    for md5 in md5s:
        if md5 not in pos:
            print(f"{md5:34} (not in corpus)"); continue
        stored = np.asarray(ext[pos[md5]], dtype=np.float64)
        vc = vector_from_catalog(md5, sc).astype(np.float64)
        try:
            mid = os.path.join(ROOT, "MIDIs", md5[:2], md5 + ".mid")
            vm = vector_from_midi(mid, sc).astype(np.float64)
            mcos = f"{_cos(vm, stored):9.4f}"
        except Exception as ex:  # noqa: BLE001
            mcos = f"ERR:{repr(ex)[:18]}"
        print(f"{md5:34} {_cos(vc, stored):8.4f} {mcos:>9}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("build-scaler")
    v = sub.add_parser("verify"); v.add_argument("md5", nargs="*")
    g = sub.add_parser("vec"); g.add_argument("path")
    args = ap.parse_args()
    if args.cmd == "build-scaler":
        build_scaler()
    elif args.cmd == "verify":
        cmd_verify(args.md5)
    elif args.cmd == "vec":
        vec = vector_from_midi(args.path)
        print(json.dumps({"dims": len(vec), "norm": float(np.linalg.norm(vec)),
                          "vec": [round(float(x), 5) for x in vec]}))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
