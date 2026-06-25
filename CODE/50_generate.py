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
_GATE = None                                # 50_theory_gate (lazy; only if --enhance)


def _gate_mod():
    global _GATE
    if _GATE is None:
        _GATE = _load("50_theory_gate.py", "theory_gate")
    return _GATE


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


# ----------------------------- TBB enforcement -----------------------------
TBB_MID = os.path.join(ROOT, "DRUM_PATTERNS", "TBB_locked.mid")


def load_tbb_loop():
    """TBB_locked.mid -> (drum events at COMMON_TPB, loop_len_ticks). One bar = 4 beats."""
    mf = mido.MidiFile(TBB_MID)
    sc = COMMON_TPB / float(mf.ticks_per_beat)
    evs, maxend = [], 0
    for tr in mf.tracks:
        t = 0
        active = {}
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                k = (msg.channel, msg.note)
                if active.get(k):
                    st, v = active[k].pop(0)
                    s2, d2 = int(round(st * sc)), max(1, int(round((t - st) * sc)))
                    evs.append((s2, d2, 9, int(msg.note), int(v)))
                    maxend = max(maxend, s2 + d2)
    loop = int(round(maxend / (4 * COMMON_TPB))) * 4 * COMMON_TPB or maxend  # whole bars
    return evs, max(loop, 4 * COMMON_TPB)


def tile_tbb(loop_evs, loop_len, span):
    """Tile the TBB loop to cover [0, span] ticks; returns drum events."""
    out = []
    reps = max(1, int(np.ceil(span / loop_len)))
    for r in range(reps):
        off = r * loop_len
        out.extend((s + off, d, ch, p, v) for (s, d, ch, p, v) in loop_evs)
    return out


def _span_ticks(*stems):
    end = 0
    for st in stems:
        for s, d, *_ in st:
            end = max(end, s + d)
    return end


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
# ext pillar layout: pitch36 / rhythm20 / melody13 / harmony8 / groove11 = 88
P_RHYTHM = slice(36, 56)
P_GROOVE = slice(77, 88)
_TBB_EXT = None


def tbb_ext_vec():
    """TBB_locked.mid embedded in the 88-D ext space (we use its rhythm+groove pillars)."""
    global _TBB_EXT
    if _TBB_EXT is None:
        _TBB_EXT = _S.vector_from_midi(TBB_MID).astype(np.float64)
    return _TBB_EXT


def anchor_tbb(tgt):
    """Overwrite the rhythm + groove pillars of a corner target with TBB's, renormalize."""
    t = tgt.copy()
    tv = tbb_ext_vec()
    t[P_RHYTHM] = tv[P_RHYTHM]
    t[P_GROOVE] = tv[P_GROOVE]
    return t / (np.linalg.norm(t) + 1e-12)


def generate_corner(rank, caption, force_drum, diatonic, tbb_loop, target_mode="corner"):
    """Build recombination candidates for one corner; returns (list[cand], base, cap)."""
    cap, donors, tgt, felt_bpm, nsim = pick_corner(rank, caption)
    if target_mode == "tbb_anchored":
        tgt = anchor_tbb(tgt)
    slug = re.sub(r"[^a-z0-9]+", "_", cap.lower())[:40].strip("_")
    outdir = os.path.join(OUTBASE, "tbb_birth" if force_drum else slug, slug)
    print(f"[corner rank={rank}] {cap}  donors={donors} felt_bpm={felt_bpm}")
    base = max(_cos(_mean_song_vec([d]), tgt) for d in donors)

    stems = {d: load_stems(d) for d in donors}
    stems = {d: s for d, s in stems.items() if s.get("drums") or s.get("melody") or s.get("harmony")}
    donors = list(stems)
    os.makedirs(outdir, exist_ok=True)

    # When forcing TBB, drums no longer vary with donor A -> iterate only melody×harmony.
    drum_donors = [None] if force_drum else donors
    cands = []
    for da in drum_donors:
        for mb in donors:
            for hc in donors:
                if force_drum:
                    span = _span_ticks(stems[mb]["melody"], stems[hc]["harmony"]) or 4 * COMMON_TPB
                    drum_stem = tile_tbb(tbb_loop[0], tbb_loop[1], span)
                    dlabel = "TBB"
                else:
                    drum_stem = stems[da]["drums"]; dlabel = da[:4]
                recipe = [drum_stem, stems[mb]["melody"], stems[hc]["harmony"]]
                if not any(recipe):
                    continue
                name = f"cand_d{dlabel}_m{mb[:4]}_h{hc[:4]}.mid"
                path = os.path.join(outdir, name)
                if not write_midi(recipe, path, felt_bpm):
                    continue
                try:
                    vec = _S.vector_from_midi(path).astype(np.float64)
                    cos = _cos(vec, tgt)
                    dia, has_mel = beauty(path)
                    has_tbb = any(ch == 9 for _, _, ch, _, _ in drum_stem)
                except Exception as ex:  # noqa: BLE001
                    print(f"  skip {name}: {repr(ex)[:60]}"); os.remove(path); continue
                cands.append(dict(name=name, path=path, cos=cos, diatonic=dia, has_melody=has_mel,
                                  drums=dlabel, melody=mb[:4], harmony=hc[:4], tbb=has_tbb, cap=cap))
    return cands, base, cap, tgt


def enhance_kept(ranked, cap, mode, min_score, min_cos, tgt=None):
    """Run the theory gate (50_theory_gate.enhance_candidate) on each kept
    candidate; write enhanced_<stem>.mid beside it; return per-candidate result
    dicts with a `passed` flag. `tgt` is the exact corner target vector the
    recombiner aimed at (so cosine is scored against the same point)."""
    G = _gate_mod()
    if tgt is None:
        tgt = G.corner_target_from_caption(cap)
    if tgt is None:
        print("[gate] no corner target vector; cosine gate disabled")
    rows = []
    for r in ranked.itertuples():
        src = r.path
        outp = os.path.join(os.path.dirname(src),
                            "enhanced_" + os.path.basename(src))
        try:
            res = G.enhance_candidate(src, mode=mode, out_path=outp, target_vec=tgt)
            res["passed"] = bool(G.passes_gate(res, min_score, min_cos))
        except Exception as ex:  # noqa: BLE001
            print(f"[gate] enhance failed for {os.path.basename(src)}: {repr(ex)[:80]}")
            res = dict(input=src, enhanced_path=None, quality_score=0.0, cosine=None,
                       detected_key="?", grade="err", passed=False)
        res["src_cos"] = float(getattr(r, "cos", 0.0))
        rows.append(res)
        print(f"  [gate] {os.path.basename(src)} -> key={res['detected_key']} "
              f"grade={res['grade']} q={res['quality_score']:.3f} "
              f"cos={res['cosine']} {'PASS' if res['passed'] else 'fail'}")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rank", type=int, default=None, help="row in targets_v2 (default top blend)")
    ap.add_argument("--ranks", default=None, help="comma list of ranks to span (e.g. 1,2,3,4)")
    ap.add_argument("--corner-caption", default=None)
    ap.add_argument("--keep", type=int, default=6)
    ap.add_argument("--diatonic", type=float, default=0.6)
    ap.add_argument("--force-drum", default=None, help="TBB = force the locked TBB beat as base drum layer")
    ap.add_argument("--target", default="corner", choices=["corner", "tbb_anchored"],
                    help="tbb_anchored = score vs corner pitch/melody/harmony + TBB rhythm/groove")
    ap.add_argument("--group", default=None)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--enhance", default="off", choices=["off", "chiptune", "arp", "clean"],
                    help="post-process kept candidates through CODE/50_theory_gate.py "
                         "(theory gate + 8-bit arrange); keep only those that pass")
    ap.add_argument("--gate-min-score", type=float, default=0.6)
    ap.add_argument("--gate-min-cos", type=float, default=None,
                    help="min cosine-to-corner for an enhanced candidate to pass")
    args = ap.parse_args()

    force = (args.force_drum or "").upper() == "TBB"
    tbb_loop = load_tbb_loop() if force else None
    if force:
        print(f"[force-drum] TBB enforced: {len(tbb_loop[0])} drum events, loop={tbb_loop[1]} ticks")

    ranks = ([int(x) for x in args.ranks.split(",")] if args.ranks
             else [args.rank])
    all_cands = []
    base = 0.0
    tgt = None
    for rk in ranks:
        cs, b, cap, tgt = generate_corner(rk, args.corner_caption, force, args.diatonic, tbb_loop, args.target)
        all_cands += cs
        base = max(base, b)
    if not all_cands:
        raise SystemExit("no candidates produced")
    cap = all_cands[0]["cap"]
    slug = re.sub(r"[^a-z0-9]+", "_", cap.lower())[:40].strip("_")
    outdir = os.path.join(OUTBASE, "tbb_birth" if force else slug)
    df = pd.DataFrame(all_cands).sort_values("cos", ascending=False).reset_index(drop=True)
    if force:
        print(f"[force-drum] {int(df.tbb.sum())}/{len(df)} candidates carry the TBB drum layer")
    # proxy-beauty gate, but never return empty
    good = df[(df.diatonic >= args.diatonic) & (df.has_melody)]
    ranked = (good if len(good) else df).head(args.keep)
    n = len(df)
    os.makedirs(outdir, exist_ok=True)
    csv = os.path.join(outdir, "candidates.csv")
    df.to_csv(csv, index=False)
    print(f"\n[generated] {n} candidates -> {outdir}")
    print(f"[best] cos-to-corner top5:\n{df.head(5)[['name','cos','diatonic','has_melody']].to_string(index=False)}")
    beat = (df.cos > base).sum()
    print(f"[result] {beat}/{n} candidates beat the best real donor ({base:.4f}); "
          f"top {df.cos.iloc[0]:.4f}")

    # prune non-kept candidate MIDIs by absolute path (corners live in sub-slugs)
    keep_paths = set(ranked.path)
    for p in df.path:
        if p not in keep_paths and os.path.exists(p):
            os.remove(p)

    # ---- theory gate + 8-bit enhancement (Task-2 route, behind --enhance) ----
    enhanced_rows = None
    if args.enhance != "off":
        enhanced_rows = enhance_kept(ranked, cap, args.enhance,
                                     args.gate_min_score, args.gate_min_cos, tgt)
        gcsv = os.path.join(outdir, "candidates_gated.csv")
        pd.DataFrame(enhanced_rows).to_csv(gcsv, index=False)
        n_pass = sum(r["passed"] for r in enhanced_rows)
        print(f"\n[gate] mode={args.enhance}: {n_pass}/{len(enhanced_rows)} enhanced "
              f"candidates passed (min_score={args.gate_min_score}, "
              f"min_cos={args.gate_min_cos}) -> {gcsv}")

    if args.no_audio:
        return
    group = args.group or ("tbb_birth30" if force else f"generated_{slug[:20]}")

    if enhanced_rows is not None:
        # render ENHANCED passing files (fallback to best-quality if none passed)
        passing = [r for r in enhanced_rows if r["passed"] and r.get("enhanced_path")]
        if not passing:
            passing = sorted([r for r in enhanced_rows if r.get("enhanced_path")],
                             key=lambda r: r["quality_score"], reverse=True)[:1]
            if passing:
                print("[gate] none passed; auditioning best-quality enhanced candidate")
        passing = sorted(passing, key=lambda r: (r.get("cosine") or 0, r["quality_score"]),
                         reverse=True)
        for i, r in enumerate(reversed(passing), 1):
            wav = r["enhanced_path"].replace(".mid", ".wav")
            subprocess.run(["fluidsynth", "-ni", "-F", wav, SF2, r["enhanced_path"]],
                           check=False, capture_output=True)
            if os.path.exists(wav):
                rank_i = len(passing) - i + 1
                cs = f"{r['cosine']:.3f}" if r.get("cosine") is not None else "n/a"
                subprocess.run(["webplayer", "add", wav, "--group", group,
                                "--label", f"#{rank_i} {args.enhance} cos{cs} q{r['quality_score']:.2f}",
                                "--desc", f"{cap} | key={r['detected_key']} grade={r['grade']}"],
                               check=False, capture_output=True)
        subprocess.run(["webplayer", "open"], check=False, capture_output=True)
        st = subprocess.run(["webplayer", "status"], capture_output=True, text=True)
        print(f"[webplayer] group '{group}': {len(passing)} enhanced tracks\n{st.stdout.strip()}")
        return

    # render kept candidates + load into webplayer (REVERSE so rank #1 is newest)
    rows = list(ranked.itertuples())
    for i, r in enumerate(reversed(rows), 1):
        wav = r.path.replace(".mid", ".wav")
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
