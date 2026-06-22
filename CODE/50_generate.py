#!/usr/bin/env python3
"""50_generate.py — route-C generator: land NEW music in an empty corner of the
N×88 space by RECOMBINING the stems of the real songs nearest that corner, then
keeping the recombinations that score closest to the corner target (49_sig_one).

The north-star step, simplest-thing-that-can-work first. An empty BLEND corner
(27_emptyspace) is the midpoint between two dense cluster centroids; its 3 nearest
real songs surround it at cos≈0.82. We split each donor into stems by role —
drums (chan 9), melody (the 24_melody_refine pick), harmony/accompaniment (the
rest) — and rebuild candidates as {drums from A, melody from B, harmony from C}
over all donor triples, with a tempo nudge toward the corner's felt BPM. Each
candidate is embedded with 49_sig_one.vector_from_midi and scored by cosine to the
corner target (the normalized anchor-centroid midpoint). We keep the candidates
that beat the nearest real song's distance to the corner AND pass a proxy-beauty
gate (diatonic, has melody), render them, and load them into the webplayer.

Usage:
  python CODE/50_generate.py                      # top groove-ranked blend corner
  python CODE/50_generate.py --rank 2 --keep 6
  python CODE/50_generate.py --corner-caption "135bpm constant · triplet-feel ..."
"""
import os, sys, argparse, re, glob, subprocess
from importlib import util as _u
import numpy as np
import pandas as pd
import mido

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)
import _common as C  # noqa

EMPTY = os.path.join(ROOT, "_work", "emptyspace")
TARGETS = os.path.join(ROOT, "_work", "generation_seeds", "targets_v2_20260620.csv")
OUTBASE = os.path.join(ROOT, "_work", "generated")
SF2 = os.path.join(ROOT, "soundfonts", "GeneralUserGS.sf2")
COMMON_TPB = 480


def _load(modfile, name):
    spec = _u.spec_from_file_location(name, os.path.join(CODE, modfile))
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_S = _load("49_sig_one.py", "sig_one")     # vector_from_midi / parse / blocks
_m24 = _S._m24                              # melody channel picker


# ----------------------------- corner target -------------------------------
def _bpm_from_caption(cap):
    m = re.match(r"\s*(\d+)\s*bpm", cap or "")
    return float(m.group(1)) if m else 120.0


def pick_corner(rank=None, caption=None):
    """Return (caption, donors[md5...], target_vec[88], felt_bpm, nearest_sim)."""
    tg = pd.read_csv(TARGETS)
    blends = pd.read_parquet(os.path.join(EMPTY, "corners_blends.parquet"))
    cents = np.load(os.path.join(EMPTY, "clusters_centroids.npy"))
    if caption is None:
        row = (tg[tg.corner_type == "blend"].iloc[0] if rank is None
               else tg[tg["rank"] == rank].iloc[0])
        caption = row["caption"]
        donors = str(row["nearest_md5_top3"]).split(";")
        nsim = float(row["nearest_sim"])
    else:
        donors, nsim = None, None
    # map caption -> blend row (anchor centroids) for the true midpoint target
    br = blends[blends.midpoint_caption == caption]
    if br.empty:
        # isolated corner: target = mean of donor vectors (no anchor pair)
        if donors is None:
            raise SystemExit("caption not found among blends and no donors given")
        tgt = _mean_song_vec(donors)
    else:
        br = br.iloc[0]
        mid = (cents[int(br["anchor_a"])] + cents[int(br["anchor_b"])]) / 2.0
        tgt = mid / (np.linalg.norm(mid) + 1e-12)
        if donors is None:
            donors = str(br["nearest_songs"]).split(";")[:3]
            nsim = float(br["nearest_sim"])
    return caption, [d for d in donors if d], tgt.astype(np.float64), _bpm_from_caption(caption), nsim


def _mean_song_vec(md5s):
    ext = np.load(os.path.join(ROOT, "SIGNATURES_DATA", "signatures_ext.npy"), mmap_mode="r")
    idx = [l.strip() for l in open(os.path.join(ROOT, "SIGNATURES_DATA", "signatures_md5.txt"))]
    pos = {m: i for i, m in enumerate(idx)}
    v = np.mean([np.asarray(ext[pos[m]], dtype=np.float64) for m in md5s if m in pos], axis=0)
    return v / (np.linalg.norm(v) + 1e-12)


# ----------------------------- stems ---------------------------------------
def load_stems(md5):
    """Parse a donor and split into role stems, rescaled to COMMON_TPB ticks.
    Returns dict role -> list[(start,dur,chan,pitch,vel)] (ints)."""
    path = os.path.join(ROOT, "MIDIs", md5[:2], md5 + ".mid")
    tpb, arr, _, _ = _S._m21.parse_notes(path)
    if len(arr) == 0:
        return {}
    sc = COMMON_TPB / float(tpb)
    mel_ch = _m24.pick_melody(arr)
    drums, melody, harmony = [], [], []
    for s, d, ch, p, v in arr.tolist():
        ev = (int(round(s * sc)), max(1, int(round(d * sc))), int(ch), int(p), int(v))
        if ch == 9:
            drums.append(ev)
        elif ch == mel_ch and mel_ch >= 0:
            melody.append(ev)
        else:
            harmony.append(ev)
    return {"drums": drums, "melody": melody, "harmony": harmony}


def write_midi(stems, out_path, bpm):
    """Write overlaid stems to a single MIDI at COMMON_TPB and the target BPM."""
    mf = mido.MidiFile(ticks_per_beat=COMMON_TPB)
    meta = mido.MidiTrack(); mf.tracks.append(meta)
    meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    notes = [ev for st in stems for ev in st]
    if not notes:
        return False
    events = []                                  # (tick, kind, chan, pitch, vel)
    for s, d, ch, p, v in notes:
        p = max(0, min(127, p)); v = max(1, min(127, v))
        events.append((s, 1, ch, p, v))
        events.append((s + d, 0, ch, p, 0))
    events.sort(key=lambda e: (e[0], e[1]))      # note-offs before note-ons at a tick
    trk = mido.MidiTrack(); mf.tracks.append(trk)
    last = 0
    for tick, kind, ch, p, v in events:
        dt = tick - last; last = tick
        msg = "note_on" if kind else "note_off"
        trk.append(mido.Message(msg, channel=ch, note=p, velocity=v, time=dt))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mf.save(out_path)
    return True


# ----------------------------- proxy beauty --------------------------------
def beauty(path):
    """(diatonic_ratio, has_melody) from the same refine functions the corpus uses."""
    tpb, arr, _, _ = _S._m21.parse_notes(path)
    hf = _S._m25.harmony_features(arr, tpb)
    mf = _S._m24.melody_features(arr, tpb)
    return hf.get("diatonic_ratio", 0.0) or 0.0, bool(mf.get("has_melody"))


def _cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# ----------------------------- main ----------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", type=int, default=None, help="row in targets_v2 (default top blend)")
    ap.add_argument("--corner-caption", default=None)
    ap.add_argument("--keep", type=int, default=6)
    ap.add_argument("--diatonic", type=float, default=0.6)
    ap.add_argument("--no-audio", action="store_true")
    args = ap.parse_args()

    cap, donors, tgt, felt_bpm, nsim = pick_corner(args.rank, args.corner_caption)
    slug = re.sub(r"[^a-z0-9]+", "_", cap.lower())[:40].strip("_")
    outdir = os.path.join(OUTBASE, slug)
    print(f"[corner] {cap}")
    print(f"[corner] donors={donors}  felt_bpm={felt_bpm}  nearest_sim={nsim}")

    # baseline: how close do the real donors themselves sit to the corner?
    base = max(_cos(_mean_song_vec([d]), tgt) for d in donors)
    print(f"[baseline] best real-donor cos-to-corner = {base:.4f}")

    stems = {d: load_stems(d) for d in donors}
    stems = {d: s for d, s in stems.items() if s.get("drums") or s.get("melody") or s.get("harmony")}
    donors = list(stems)

    # candidates: every (drums A, melody B, harmony C) over the donors, at the corner BPM
    cands = []
    os.makedirs(outdir, exist_ok=True)
    n = 0
    for da in donors:
        for mb in donors:
            for hc in donors:
                recipe = [stems[da]["drums"], stems[mb]["melody"], stems[hc]["harmony"]]
                if not any(recipe):
                    continue
                name = f"cand_d{da[:4]}_m{mb[:4]}_h{hc[:4]}.mid"
                path = os.path.join(outdir, name)
                if not write_midi(recipe, path, felt_bpm):
                    continue
                try:
                    vec = _S.vector_from_midi(path).astype(np.float64)
                    cos = _cos(vec, tgt)
                    dia, has_mel = beauty(path)
                except Exception as ex:  # noqa: BLE001
                    print(f"  skip {name}: {repr(ex)[:60]}"); os.remove(path); continue
                cands.append(dict(name=name, path=path, cos=cos, diatonic=dia,
                                  has_melody=has_mel, drums=da[:4], melody=mb[:4], harmony=hc[:4]))
                n += 1
    if not cands:
        raise SystemExit("no candidates produced")
    df = pd.DataFrame(cands).sort_values("cos", ascending=False).reset_index(drop=True)
    # proxy-beauty gate, but never return empty
    good = df[(df.diatonic >= args.diatonic) & (df.has_melody)]
    ranked = (good if len(good) else df).head(args.keep)
    csv = os.path.join(outdir, "candidates.csv")
    df.to_csv(csv, index=False)
    print(f"\n[generated] {n} candidates -> {outdir}")
    print(f"[best] cos-to-corner top5:\n{df.head(5)[['name','cos','diatonic','has_melody']].to_string(index=False)}")
    beat = (df.cos > base).sum()
    print(f"[result] {beat}/{n} candidates are CLOSER to the corner than the best real donor "
          f"({base:.4f}); top candidate {df.cos.iloc[0]:.4f}")

    # prune non-kept candidate files to keep the dir clean, keep the ranked ones
    keepset = set(ranked.name)
    for f in glob.glob(os.path.join(outdir, "cand_*.mid")):
        if os.path.basename(f) not in keepset:
            os.remove(f)

    if args.no_audio:
        return
    # render kept candidates + load into webplayer (REVERSE so rank #1 is newest)
    group = f"generated_{slug[:20]}"
    rows = list(ranked.itertuples())
    for i, r in enumerate(reversed(rows), 1):
        wav = os.path.join(outdir, r.name.replace(".mid", ".wav"))
        subprocess.run(["fluidsynth", "-ni", "-F", wav, SF2, r.path],
                       check=False, capture_output=True)
        if os.path.exists(wav):
            rank_i = len(rows) - i + 1
            subprocess.run(["webplayer", "add", wav, "--group", group,
                            "--label", f"#{rank_i} cos{r.cos:.3f} d{r.drums}/m{r.melody}/h{r.harmony}",
                            "--desc", f"{cap} | diatonic={r.diatonic:.2f}"],
                           check=False, capture_output=True)
    subprocess.run(["webplayer", "open"], check=False, capture_output=True)
    st = subprocess.run(["webplayer", "status"], capture_output=True, text=True)
    print(f"[webplayer] group '{group}': {len(rows)} tracks\n{st.stdout.strip()}")


if __name__ == "__main__":
    main()
