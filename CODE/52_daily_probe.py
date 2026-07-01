#!/usr/bin/env python3
"""52_daily_probe.py — Daily Style Probe Generator.

One focused, low-cost run that samples a fresh empty corner, generates 1-3 short
coherent probe tracks by recombining the nearest real donor stems, renders them,
and logs everything. Designed as a daily cron-friendly "new music invention"
loop that closes hunt → generate → listen → evaluate without manual work.

Reuses 50_generate's stem/phrase machinery, 49_sig_one for embedding, and the
taste-ranked corner targets from 27_emptyspace / 47_propagator.

Output structure (resumable):
  _work/daily_probes/YYYY-MM-DD_cornerXXXX/
    meta.json          — corner info, donors, coords
    probe_001.mid       — generated MIDI
    probe_001.wav       — fluidsynth render (if --render)
    probe_001.json      — embedding & quality scores
    ...                 — probe_002, probe_003
    shortlist.tsv       — all probes with scores for this run

Usage:
  .venv-linux/bin/python CODE/52_daily_probe.py                         # default: top undonated blend corner
  .venv-linux/bin/python CODE/52_daily_probe.py --corner-id latest      # same
  .venv-linux/bin/python CODE/52_daily_probe.py --corner-id 5           # target CSV rank
  .venv-linux/bin/python CODE/52_daily_probe.py --num-probes 3 --render --add-to-webplayer
  .venv-linux/bin/python CODE/52_daily_probe.py --log-only              # describe what would be done
  .venv-linux/bin/python CODE/52_daily_probe.py --list-corners          # print all corners
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import util as _u
from pathlib import Path

import numpy as np
import pandas as pd

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)
import _common as C  # noqa

# -- paths --------------------------------------------------------------------
SIG_DIR = os.path.join(ROOT, "SIGNATURES_DATA")
EXT_NPY = os.path.join(SIG_DIR, "signatures_ext.npy")
IDX_TXT = os.path.join(SIG_DIR, "signatures_md5.txt")
KNN_PKL = os.path.join(SIG_DIR, "knn_cosine.pkl")
EMPTY = os.path.join(ROOT, "_work", "emptyspace")
CENTROIDS = os.path.join(EMPTY, "clusters_centroids.npy")
BLENDS = os.path.join(EMPTY, "corners_blends.parquet")
TARGETS_CSV = os.path.join(ROOT, "_work", "generation_seeds",
                           "targets_taste_v2_20260622.csv")
PRED = os.path.join(ROOT, "_work", "taste_pred_v2.parquet")
OUTBASE = os.path.join(ROOT, "_work", "daily_probes")
SF2 = os.path.join(ROOT, "soundfonts", "GeneralUserGS.sf2")
SCALER = os.path.join(ROOT, "_work", "sig_scaler.pkl")
COMMON_TPB = 480
BAR_TICKS = 4 * COMMON_TPB  # 1920 (4/4 grid, corpus-dominant)

# -- lazy module loaders (same pattern as 50_generate) ------------------------
def _load(modfile, name):
    spec = _u.spec_from_file_location(name, os.path.join(CODE, modfile))
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

_SIG = None  # 49_sig_one
_GEN = None  # 50_generate (for stem/phrase helpers)


def _sig():
    global _SIG
    if _SIG is None:
        _SIG = _load("49_sig_one.py", "sig_one")
    return _SIG


def _gen():
    global _GEN
    if _GEN is None:
        _GEN = _load("50_generate.py", "generate")
    return _GEN


# -- corner helpers -----------------------------------------------------------
def _l2(x):
    n = np.linalg.norm(x)
    return x / n if n > 1e-12 else x


def _cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


def _bpm_from_caption(cap):
    m = re.match(r"\s*(\d+)\s*bpm", cap or "")
    return float(m.group(1)) if m else 120.0


def load_corner_targets():
    """Return DataFrame of taste-ranked target corners."""
    return pd.read_csv(TARGETS_CSV)


def list_corners():
    """Print all corners to stdout."""
    tg = load_corner_targets()
    print(f"{'rank':>5} {'type':>10}  caption")
    print("-" * 80)
    for _, r in tg.iterrows():
        print(f"{int(r['rank']):>5} {str(r['corner_type']):>10}  {r['caption']}")


def corner_target_vec(ctype, caption):
    """Resolve a corner's 88-D target vector (midpoint of blend centroids, or
    isolated cluster centroid). Returns unit vector or None."""
    if not os.path.exists(CENTROIDS):
        return None
    cents = np.load(CENTROIDS).astype(np.float64)
    if ctype == "blend":
        bl = pd.read_parquet(BLENDS) if os.path.exists(BLENDS) else pd.DataFrame()
        if bl.empty:
            return None
        r = bl[bl.midpoint_caption == caption]
        if r.empty:
            return None
        r = r.iloc[0]
        mid = (cents[int(r["anchor_a"])] + cents[int(r["anchor_b"])]) / 2.0
        return _l2(mid)
    if ctype == "isolated":
        iso = pd.read_parquet(os.path.join(EMPTY, "corners_isolated.parquet")) \
            if os.path.exists(os.path.join(EMPTY, "corners_isolated.parquet")) else pd.DataFrame()
        if iso.empty:
            return None
        r = iso[iso.caption == caption]
        if r.empty:
            return None
        cid = int(r.iloc[0]["cluster_id"])
        if 0 <= cid < len(cents):
            return _l2(cents[cid].astype(np.float64))
    return None


def corner_donor_md5s(row):
    """Extract donor md5s from a targets CSV row (nearest_md5_top3)."""
    raw = str(row.get("nearest_md5_top3", ""))
    md5s = [m.strip() for m in raw.split(";") if len(m.strip()) == 32]
    # fallback to single nearest
    if not md5s:
        ns = str(row.get("nearest_md5", "")).strip()
        if len(ns) == 32:
            md5s = [ns]
    return md5s


# -- resumability -------------------------------------------------------------
def probes_already_exist(corner_id):
    """Check if any probe directory exists for this corner id (YYYY-MM-DD_cornerXXXX)."""
    if not os.path.exists(OUTBASE):
        return False
    for d in os.listdir(OUTBASE):
        if f"corner{corner_id}" in d:
            return True
    return False


def done_corner_ids():
    """Return set of corner IDs already probed."""
    if not os.path.exists(OUTBASE):
        return set()
    ids = set()
    for d in os.listdir(OUTBASE):
        m = re.search(r"corner(\d+)", d)
        if m:
            ids.add(int(m.group(1)))
    return ids


# -- generation ---------------------------------------------------------------
def load_donor_stems(donor_md5s, max_donors=5):
    """Load stem dicts for up to max_donors donors (skipping parse errors).
    Returns {md5: {drums, melody, harmony}}."""
    g = _gen()
    out = {}
    for md5 in donor_md5s[:max_donors]:
        try:
            stems = g.load_stems(md5)
            if stems.get("drums") or stems.get("melody") or stems.get("harmony"):
                out[md5] = stems
        except Exception as e:
            print(f"  [probe] skip donor {md5[:8]}: {repr(e)[:60]}")
    return out


def load_donor_phrases(donor_md5s, max_donors=5):
    """Load phrase-split donors. Returns list of phrase dicts with keys
    {melody, drums, harmony, bars, donor}."""
    g = _gen()
    all_phrases = []
    for md5 in donor_md5s[:max_donors]:
        try:
            phrases = g.load_phrases(md5, min_bars=2, max_bars=6, align_key=True)
            all_phrases.extend(phrases)
        except Exception as e:
            print(f"  [probe] skip phrases for {md5[:8]}: {repr(e)[:60]}")
    return all_phrases


def build_phrase_song(slots, force_tbb=False):
    """Concatenate phrase slots end-to-end into [drums, melody, harmony].
    Thin wrapper around 50_generate.build_phrase_song."""
    g = _gen()
    tbb = g.load_tbb_loop() if force_tbb else None
    return g.build_phrase_song(slots, force_drum=force_tbb, tbb_loop=tbb)


def probe_song(drums, melody, harmony, bpm, out_noext):
    """Write a 3-part MIDI at COMMON_TPB and return path (or None).
    Pulls together write_midi from 50_generate's module for consistency."""
    g = _gen()
    ok = g.write_midi([drums, melody, harmony], out_noext + ".mid", bpm)
    if not ok:
        return None
    return out_noext + ".mid"


# -- scoring ------------------------------------------------------------------
def score_probe(midi_path, target_vec, donor_vecs):
    """Embed candidate and return {cos, donor_sim, n_notes, distinct_pc, diatonic, has_melody}."""
    sig = _sig()
    info = {"n_notes": 0, "distinct_pc": 0, "cos": None, "donor_sim": None,
            "diatonic": 0.0, "has_melody": False}
    try:
        vec = sig.vector_from_midi(midi_path).astype(np.float64)
        info["cos"] = round(_cos(vec, target_vec), 5)
        if donor_vecs:
            info["donor_sim"] = round(max(_cos(vec, dv) for dv in donor_vecs.values()), 5)
        # parse for note count + distinct pitch classes
        tpb, arr, _, _ = sig._m21.parse_notes(midi_path)
        info["n_notes"] = len(arr)
        nondrum = arr[arr[:, 2] != 9]
        info["distinct_pc"] = len(set(int(p) % 12 for p in nondrum[:, 3])) if len(nondrum) else 0
        # proxy beauty
        hf = sig._m25.harmony_features(arr, tpb)
        mf = sig._m24.melody_features(arr, tpb)
        info["diatonic"] = hf.get("diatonic_ratio", 0.0) or 0.0
        info["has_melody"] = bool(mf.get("has_melody"))
    except Exception as e:
        print(f"  [probe] scoring error: {repr(e)[:60]}")
    return info


def render_wav(midi_path, wav_path):
    """fluidsynth render to WAV."""
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    ret = subprocess.run(["fluidsynth", "-ni", "-F", wav_path, SF2, midi_path],
                         capture_output=True, timeout=120)
    return os.path.exists(wav_path)


# -- webplayer ----------------------------------------------------------------
def add_to_webplayer(wav_dir, label, desc):
    """Probe WAVs -> webplayer group 'daily_probes'."""
    try:
        subprocess.run(["webplayer", "add", wav_dir, "--group", "daily_probes",
                        "--label", label, "--desc", desc],
                       capture_output=True, timeout=30)
        subprocess.run(["webplayer", "open"], capture_output=True, timeout=15)
        return True
    except Exception as e:
        print(f"  [probe] webplayer add failed: {repr(e)[:60]}")
        return False


# -- log runner ---------------------------------------------------------------
def log_only(corner_row):
    """Print what would be done without generating."""
    print("=== LOG-ONLY: would probe this corner ===")
    print(f"  rank:     {int(corner_row['rank'])}")
    print(f"  type:     {corner_row['corner_type']}")
    print(f"  caption:  {corner_row['caption']}")
    print(f"  pred_love: {corner_row.get('pred_love', '?')}")
    md5s = corner_donor_md5s(corner_row)
    print(f"  donors:   {[m[:8] for m in md5s]}")
    vec = corner_target_vec(corner_row["corner_type"], corner_row["caption"])
    if vec is not None:
        print(f"  target norm: {np.linalg.norm(vec):.4f}")
    print(f"  out:      {os.path.join(OUTBASE, 'YYYY-MM-DD_corner' + str(int(corner_row['rank'])).zfill(4))}")
    print(f"  probes:   {corner_row.get('num_probes', 2)}")
    print()


# -- main run -----------------------------------------------------------------
def run(args):
    os.makedirs(OUTBASE, exist_ok=True)

    # 1. Pick corner
    tg = load_corner_targets()
    done_ids = done_corner_ids()

    if args.list_corners:
        list_corners()
        return 0

    if args.corner_id and args.corner_id != "latest":
        # specific rank
        row = tg[tg["rank"] == int(args.corner_id)]
        if row.empty:
            print(f"Corner rank {args.corner_id} not found in targets CSV.")
            return 1
        row = row.iloc[0]
    else:
        # latest = first undonated corner (skip already-probed)
        for _, r in tg.iterrows():
            if int(r["rank"]) not in done_ids:
                row = r
                break
        else:
            print("All corners already probed. Nothing to do.")
            return 0

    if args.log_only:
        row["num_probes"] = args.num_probes
        log_only(row)
        return 0

    corner_id = int(row["rank"])
    ctype = str(row["corner_type"])
    caption = str(row["caption"])

    # Resumability: skip if this corner already probed today
    if not args.force and corner_id in done_ids:
        print(f"Corner #{corner_id} already probed. Use --force to redo.")
        return 0

    # 2. Resolve corner target vector
    print(f"\n=== Probing corner #{corner_id} ({ctype}) ===")
    print(f"  caption: {caption}")
    target_vec = corner_target_vec(ctype, caption)
    if target_vec is None:
        print("  ERROR: cannot resolve corner target vector. Aborting.")
        return 1

    # 3. Load donors
    donor_md5s_in = corner_donor_md5s(row)
    if not donor_md5s_in:
        print("  ERROR: no donor md5s in CSV row.")
        return 1
    print(f"  donors: {[m[:8] for m in donor_md5s_in]}")

    donors = load_donor_stems(donor_md5s_in, max_donors=5)
    if len(donors) < 2:
        print("  WARNING: fewer than 2 donors parsed; recombination will be limited.")

    # Donor vecs for scoring
    ext = np.load(EXT_NPY, mmap_mode="r")
    idx = [l.strip() for l in open(IDX_TXT) if l.strip()]
    pos = {m: i for i, m in enumerate(idx)}
    donor_vecs = {}
    for m in donors:
        if m in pos:
            donor_vecs[m] = ext[pos[m]].astype(np.float64)

    phrases = load_donor_phrases(donor_md5s_in, max_donors=5)
    if not phrases:
        print("  ERROR: no phrases could be loaded from any donor.")
        return 1

    bpm = _bpm_from_caption(caption) or 120.0

    # 4. Output directory
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = f"{date_str}_corner{corner_id:04d}"
    out_dir = os.path.join(OUTBASE, slug)
    os.makedirs(out_dir, exist_ok=True)
    print(f"  output: {out_dir}")

    # 5. Generate probes
    n_probes = max(1, min(args.num_probes, 5))
    g = _gen()
    tbb_loop = g.load_tbb_loop() if args.tbb else None

    # If we have at least 3 distinct phrase donors, do proper recombination;
    # otherwise fall back to simple stem overlay.
    donor_set = set(p["donor"] for p in phrases)
    have_multi = len(donor_set) >= 2

    shortlist = []
    rng = np.random.default_rng(args.seed or int(time.time()))

    for pi in range(n_probes):
        print(f"\n  --- probe {pi + 1}/{n_probes} ---")

        if have_multi and len(phrases) >= 2:
            # Pick 2-4 phrases from different donors
            n_slots = int(rng.integers(2, min(5, len(phrases) + 1)))
            # Ensure at least 2 different donors among slots
            pool = list(phrases)
            rng.shuffle(pool)
            # Greedy pick ensuring donor diversity
            sel = [pool[0]]
            used_donors = {pool[0]["donor"]}
            for ph in pool[1:]:
                if len(sel) >= n_slots:
                    break
                if ph["donor"] not in used_donors or len(used_donors) >= len(donor_set):
                    sel.append(ph)
                    used_donors.add(ph["donor"])
            # If all same donor, try harder for diversity
            if len(used_donors) < 2 and len(pool) > 1:
                for ph in pool:
                    if ph["donor"] != sel[0]["donor"]:
                        sel.append(ph)
                        break
            # Build slots: each slot is (mel_ph, harm_ph, drum_ph) from the same phrase dict
            # For diversity, use the selected phrases for melody, and randomly assign
            # harmony/drums from the pool
            slot_strs = [f"{s['donor']}({s['bars']}bars)" for s in sel]
            print(f"    slots: {slot_strs}")
            slots = []
            for i, mp in enumerate(sel):
                # Harmony from this donor's phrase, drums from this donor's phrase
                hp = sel[(i + 1) % len(sel)] if len(sel) > 1 else mp
                dp = sel[(i + 2) % len(sel)] if len(sel) > 2 else mp
                slots.append((mp, hp, dp))
            stems = g.build_phrase_song(slots, force_drum=bool(args.tbb), tbb_loop=tbb_loop)
        else:
            # Simple overlay: take drums from one donor, melody from another, harmony from another
            donor_list = list(donors.keys())
            if len(donor_list) >= 3:
                rng.shuffle(donor_list)
            a, b, c = donor_list[0], donor_list[min(1, len(donor_list) - 1)], \
                donor_list[min(2, len(donor_list) - 1)]
            print(f"    stem-overlay: drums={a[:8]} melody={b[:8]} harm={c[:8]}")
            dr = donors[a].get("drums", [])[:] if a in donors else []
            me = donors[b].get("melody", [])[:] if b in donors else []
            ha = donors[c].get("harmony", [])[:] if c in donors else []
            # tempo nudge: rescale durations proportionally
            stems = [dr, me, ha]

        probe_stem = f"probe_{pi + 1:03d}"
        midi_path = os.path.join(out_dir, probe_stem + ".mid")

        ok = g.write_midi(stems, midi_path, bpm)
        if not ok:
            print(f"    SKIP: write_midi returned False (no notes)")
            continue

        # Score
        scores = score_probe(midi_path, target_vec, donor_vecs)
        print(f"    cos={scores['cos']} n_notes={scores['n_notes']} "
              f"pc={scores['distinct_pc']} dia={scores['diatonic']:.3f} "
              f"mel={scores['has_melody']}")

        # Save per-probe JSON
        meta = {
            "corner_id": corner_id,
            "corner_type": ctype,
            "caption": caption,
            "probe": pi + 1,
            "bpm": bpm,
            "midi": probe_stem + ".mid",
            "target_norm": round(float(np.linalg.norm(target_vec)), 5),
            "scores": scores,
            "donors": [m[:8] for m in donor_md5s_in],
            "ts": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        }
        with open(os.path.join(out_dir, probe_stem + ".json"), "w") as fh:
            json.dump(meta, fh, indent=2)

        # Render WAV
        wav_path = None
        if args.render:
            wav_path = os.path.join(out_dir, probe_stem + ".wav")
            ok_wav = render_wav(midi_path, wav_path)
            print(f"    wav: {'ok' if ok_wav else 'FAILED'} -> {wav_path}")
            if ok_wav:
                meta["wav"] = probe_stem + ".wav"
            else:
                wav_path = None

        shortlist.append({
            "probe": pi + 1,
            "midi": os.path.relpath(midi_path, ROOT),
            "wav": os.path.relpath(wav_path, ROOT) if wav_path and os.path.exists(wav_path) else "",
            "cos": scores.get("cos"),
            "donor_sim": scores.get("donor_sim"),
            "n_notes": scores.get("n_notes"),
            "distinct_pc": scores.get("distinct_pc"),
            "diatonic": scores.get("diatonic"),
            "has_melody": int(scores.get("has_melody", False)),
        })

    # 6. Write shortlist TSV
    tsv_path = os.path.join(out_dir, "shortlist.tsv")
    cols = ["probe", "midi", "wav", "cos", "donor_sim", "n_notes",
            "distinct_pc", "diatonic", "has_melody"]
    sl_df = pd.DataFrame(shortlist, columns=cols)
    sl_df.to_csv(tsv_path, sep="\t", index=False)
    print(f"\n  shortlist -> {tsv_path}")

    # 7. Write overall meta.json
    full_meta = {
        "corner_id": corner_id,
        "corner_type": ctype,
        "caption": caption,
        "bpm": bpm,
        "n_probes": n_probes,
        "donors": donor_md5s_in,
        "target_vec_norm": round(float(np.linalg.norm(target_vec)), 5),
        "out_dir": out_dir,
        "ts": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "probes": shortlist,
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as fh:
        json.dump(full_meta, fh, indent=2)
    print(f"  meta -> {os.path.join(out_dir, 'meta.json')}")

    # 8. Webplayer
    if args.add_to_webplayer and args.render and any(p["wav"] for p in shortlist):
        wav_dir = os.path.join(out_dir)
        add_to_webplayer(wav_dir,
                         f"daily_probe_corner{corner_id}",
                         f"Corner #{corner_id}: {caption[:60]}")

    print("\n=== Done ===")
    return 0


# -- CLI ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Daily Style Probe Generator — sample an empty corner, "
                    "recombine donor stems, render probes, log results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)

    ap.add_argument("--corner-id", default="latest",
                    help="Corner rank from targets CSV, or 'latest' (default) for "
                         "first unprobed corner.")
    ap.add_argument("--num-probes", type=int, default=2,
                    help="Number of probe tracks to generate (1-5, default 2).")
    ap.add_argument("--render", action="store_true",
                    help="Render each probe MIDI to WAV via fluidsynth.")
    ap.add_argument("--add-to-webplayer", action="store_true",
                    help="Add rendered WAVs to webplayer group 'daily_probes'.")
    ap.add_argument("--log-only", action="store_true",
                    help="Print what would be done without generating anything.")
    ap.add_argument("--list-corners", action="store_true",
                    help="List all target corners and exit.")
    ap.add_argument("--force", action="store_true",
                    help="Re-probe a corner even if already probed.")
    ap.add_argument("--tbb", action="store_true",
                    help="Force TBB locked drums on all probes.")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed for deterministic probes.")

    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
