#!/usr/bin/env python3
"""52_invention_loop.py — autonomous, coordinate-driven INVENTION loop.

The flagship of INVENTION_LOOP_PLAN.md. An unattended search loop that pushes the
corpus toward its north star — *invent a new form of music by generating into
empty-but-coherent regions of the 88-D space* — using BASE Giant Music Transformer
as a fixed engine and SEEDING (never free-improv) to hit a target coordinate.

Shape adapted 1:1 from the "Autonomous ML Research Agent" prompt: a closed loop with
ONE metric, a fixed per-corner budget, resumable telemetry, and keep/discard/crash
semantics — but the "experiment" is a *generation toward an empty corner* and the
metric is `invention_score` (higher better), not val_bpb.

Per iteration:
  1. ORIENT     — load target corners (taste-ranked CSV) + resolve each corner's 88-D
                  coordinate (blend = midpoint of two cluster centroids; isolated =
                  the cluster centroid). Read results.tsv tail for resumability.
  2. HYPOTHESIZE— pick the next (corner, seed_md5, params). Seed = a real corpus MIDI
                  near the corner (the CSV's nearest_md5 / top-3). Vary one param.
  3. GENERATE   — base GMT `continue`: prime from the seed, generate N tokens. No LoRA.
  4. EMBED+SCORE— embed the full output AND the seed's own GMT round-trip with
                  49_sig_one; corner_gain = cos(cand,corner) − cos(seed_rt,corner)
                  (relative to the seed round-trip to neutralize GMT decode drift);
                  taste model -> pred_love; coherence gate -> invention_score.
  5. DECIDE     — keep (beats seed baseline AND best-for-corner) / discard / crash.
  6. LOG        — one (corner,seed,params)-keyed row to results.tsv; render kept WAVs.
  7. LOOP       — until per-corner budget exhausted, or interrupted (Ctrl-C → summary).

THE METRIC (one number, higher better, hard coherence gate):
  invention_score = w_place * corner_gain + w_taste * pred_love_norm
                    subject to coherence_gate(candidate) == PASS  (else -inf, discard)
  - corner_gain   = cos(cand, corner) − cos(seed_roundtrip, corner)   (cosine delta)
  - pred_love_norm= corpus-percentile-normalized 47_propagator love (tie-breaker)
  - coherence_gate= 50_theory_gate quality floor + cheap degeneracy checks
  Default weights: w_place=0.6 (north star), w_taste=0.4 (tie-breaker). The human ear
  is the FINAL keep/discard on the shortlist; the score only decides what gets rendered.

GUARDRAILS (see INVENTION_LOOP_PLAN.md): base GMT only (no fine-tune); seed-and-continue
only; score full seeded songs relative to the seed round-trip; resumable; MIDIs/ read-only;
corpus lane only (never touches NinjaStar-8 write paths). GPU must be reachable.

Usage:
  .venv-linux/bin/python CODE/52_invention_loop.py --once --tag inv-smoke
  .venv-linux/bin/python CODE/52_invention_loop.py --tag inv-20260630 \
      --corners _work/generation_seeds/targets_taste_v2_20260622.csv \
      --n-corners 3 --budget 4 --tokens 512 --prime 512 --render
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
import json
import signal
import subprocess
from datetime import datetime, timezone
from importlib import util as _u

import numpy as np
import pandas as pd

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
sys.path.insert(0, CODE)

SIGP = os.path.join(ROOT, "SIGNATURES_DATA", "signatures_ext.npy")
IDXP = os.path.join(ROOT, "SIGNATURES_DATA", "signatures_md5.txt")
EMPTY = os.path.join(ROOT, "_work", "emptyspace")
CENTROIDS = os.path.join(EMPTY, "clusters_centroids.npy")
BLENDS = os.path.join(EMPTY, "corners_blends.parquet")
ISO = os.path.join(EMPTY, "corners_isolated.parquet")
PRED = os.path.join(ROOT, "_work", "taste_pred_v2.parquet")
RATINGS = os.path.join(ROOT, "_work", "ninjastar8_ratings.parquet")
DEFAULT_TARGETS = os.path.join(ROOT, "_work", "generation_seeds", "targets_taste_v2_20260622.csv")
SF2 = os.path.join(ROOT, "soundfonts", "GeneralUserGS.sf2")
RUNS = os.path.join(ROOT, "_work", "invention_runs")

RESULTS_COLS = [
    "ts", "corner_id", "corner_type", "caption", "seed_md5", "param_hash",
    "prime", "tokens", "temperature", "topp",
    "corner_gain", "seed_cos", "cand_cos", "pred_love", "pred_love_norm",
    "coherent", "quality", "n_notes", "invention_score", "status", "midi", "wav", "note",
]


def log(m):
    print(f"[52] {m}", flush=True)


def inv(line):
    """Telemetry-only [INV] line."""
    print(f"[INV] {line}", flush=True)


# ----------------------------- module loading -------------------------------
def _load(path, name):
    spec = _u.spec_from_file_location(name, path)
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_modules():
    sig = _load(os.path.join(CODE, "49_sig_one.py"), "sig_one")
    tg = _load(os.path.join(CODE, "50_theory_gate.py"), "theory_gate")
    gg = _load(os.path.join(ROOT, "GMT", "gmt_generate.py"), "gmt_generate")
    prop = _load(os.path.join(CODE, "47_propagator.py"), "propagator")
    return sig, tg, gg, prop


# ----------------------------- taste model ----------------------------------
class TasteModel:
    """In-process 47_propagator love predictor for NEW candidate vectors.

    Reuses 47's model factories + LOVE weights (read-only over the ratings parquet).
    Predicts the groove-dominant love composite for a single 88-D vector. Falls back
    to nearest-corpus-neighbor love (from taste_pred_v2) if ratings are unavailable.
    """

    def __init__(self, prop, ext, md5s):
        self.ok = False
        self.models = {}
        self.weights = prop.LOVE_W
        self._neighbor = None
        try:
            r = pd.read_parquet(RATINGS)
            r = r[r.rating_version == 2]
            agg = r.groupby("md5")[prop.AXES].mean()
            pos = {m: i for i, m in enumerate(md5s)}
            agg = agg[agg.index.isin(pos)]
            rows = np.array([pos[m] for m in agg.index])
            Xtr = ext[rows].astype(np.float32)
            for ax in self.weights:           # only the axes the love composite needs
                y = agg[ax].to_numpy(float)
                ok = np.isfinite(y)
                name, _, _ = prop.cv_select(Xtr[ok], y[ok], ax)
                mk = prop._ridge_groove if name == "ridge_g8" else prop._lgbm
                mdl = mk(); mdl.fit(Xtr[ok], y[ok])
                self.models[ax] = mdl
            self.ok = True
            log(f"taste model trained on {len(agg)} v2-rated songs "
                f"(axes={list(self.weights)})")
        except Exception as ex:  # noqa: BLE001
            log(f"taste model train failed ({repr(ex)[:70]}); will use neighbor fallback")
            self._build_neighbor(ext, md5s)

    def _build_neighbor(self, ext, md5s):
        try:
            tp = pd.read_parquet(PRED, columns=["md5", "pred_love"])
            lv = dict(zip(tp["md5"], tp["pred_love"]))
            self._neighbor = (ext, md5s, lv)
        except Exception:  # noqa: BLE001
            self._neighbor = None

    def love(self, vec):
        v = np.asarray(vec, dtype=np.float32)[None, :]
        if self.ok:
            wsum = sum(self.weights.values())
            return float(sum(self.weights[a] * float(self.models[a].predict(v)[0])
                             for a in self.weights) / wsum)
        if self._neighbor is not None:
            ext, md5s, lv = self._neighbor
            sims = (ext @ vec) / (np.linalg.norm(ext, axis=1) * np.linalg.norm(vec) + 1e-12)
            j = int(np.argmax(sims))
            return float(lv.get(md5s[j], np.nan))
        return float("nan")


# ----------------------------- corner geometry ------------------------------
def _l2(x):
    n = np.linalg.norm(x)
    return x / n if n > 1e-12 else x


def _cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


class CornerBook:
    """Resolves a taste-targets CSV row -> the 88-D empty-corner coordinate."""

    def __init__(self):
        self.centroids = np.load(CENTROIDS).astype(np.float64)
        self.blends = pd.read_parquet(BLENDS) if os.path.exists(BLENDS) else pd.DataFrame()
        self.iso = pd.read_parquet(ISO) if os.path.exists(ISO) else pd.DataFrame()

    def resolve(self, corner_type, caption):
        if corner_type == "blend" and not self.blends.empty:
            r = self.blends[self.blends.midpoint_caption == caption]
            if r.empty:
                return None
            r = r.iloc[0]
            mid = (self.centroids[int(r["anchor_a"])] + self.centroids[int(r["anchor_b"])]) / 2.0
            return _l2(mid)
        if corner_type == "isolated" and not self.iso.empty:
            r = self.iso[self.iso.caption == caption]
            if r.empty:
                return None
            cid = int(r.iloc[0]["cluster_id"])
            if 0 <= cid < len(self.centroids):
                return _l2(self.centroids[cid].astype(np.float64))
        return None


# ----------------------------- GMT engine -----------------------------------
class Engine:
    """Holds the loaded base GMT model; generates a seeded continuation and decodes
    BOTH the full candidate and the seed's own GMT round-trip (the placement baseline)."""

    def __init__(self, gg, model_path=None):
        self.gg = gg
        import torch  # noqa: F401
        self.torch = torch
        from x_transformer_1_23_2 import top_p  # noqa: E402
        self.top_p = top_p
        self.model = gg.build_model(model_path or gg.LARGE)
        self.ctx, self.dtype = gg.autocast_ctx()
        log(f"GMT base model loaded (precision={self.dtype})")

    def seed_tokens(self, seed_midi):
        return self.gg.seed_midi_to_tokens(seed_midi)

    @staticmethod
    def snap_prime(toks, prime):
        """Header is 3 tokens then note triples; keep prime on a triple boundary."""
        prime = max(3, min(prime, len(toks)))
        if prime > 3:
            prime = 3 + 3 * ((prime - 3) // 3)
        return prime

    def generate(self, toks, prime, tokens, temperature, topp):
        prime = self.snap_prime(toks, prime)
        outy = toks[:prime]
        inp = self.torch.LongTensor([outy]).cuda()
        self.torch.cuda.empty_cache()
        with self.ctx, self.torch.inference_mode():
            out = self.model.generate(
                inp, tokens, filter_logits_fn=self.top_p,
                filter_kwargs={"thres": topp}, temperature=temperature,
                return_prime=True, verbose=False)
        full = out.tolist()[0]
        return outy, full, prime

    def write(self, tokens, out_noext):
        return self.gg.write_midi(tokens, out_noext)   # -> (path+'.mid', n_notes) | (None,0)


# ----------------------------- coherence gate -------------------------------
def coherence_gate(sig, tg, midi_path, min_notes, min_quality):
    """(passed, info). Cheap degeneracy checks + 50_theory_gate quality floor."""
    info = {"n_notes": 0, "distinct_pc": 0, "quality": float("nan"),
            "reason": ""}
    try:
        _tpb, arr, _tempos, _ts = sig._m21.parse_notes(midi_path)
    except Exception as ex:  # noqa: BLE001
        info["reason"] = f"parse:{repr(ex)[:40]}"
        return False, info
    n = len(arr)
    info["n_notes"] = int(n)
    if n < min_notes:
        info["reason"] = f"too few notes ({n}<{min_notes})"
        return False, info
    nondrum = arr[arr[:, 2] != 9]
    distinct_pc = len(set(int(p) % 12 for p in nondrum[:, 3])) if len(nondrum) else 0
    info["distinct_pc"] = distinct_pc
    if distinct_pc < 3:
        info["reason"] = f"drone (distinct pcs={distinct_pc})"
        return False, info
    span = float((arr[:, 0] + arr[:, 1]).max() - arr[:, 0].min())
    if span <= 0:
        info["reason"] = "zero span"
        return False, info
    try:
        res = tg.enhance_candidate(midi_path, mode="clean", dry_run=True)
        info["quality"] = float(res.get("quality_score", float("nan")))
    except Exception as ex:  # noqa: BLE001
        info["reason"] = f"theory:{repr(ex)[:40]}"
        info["quality"] = float("nan")
    q = info["quality"]
    if np.isfinite(q) and q < min_quality:
        info["reason"] = f"low quality ({q:.2f}<{min_quality})"
        return False, info
    info["reason"] = "ok"
    return True, info


# ----------------------------- results IO -----------------------------------
def param_hash(prime, tokens, temperature, topp):
    s = f"{prime}|{tokens}|{temperature}|{topp}"
    return hashlib.sha1(s.encode()).hexdigest()[:8]


def load_done(results_path):
    if not os.path.exists(results_path):
        return set(), []
    df = pd.read_csv(results_path, sep="\t")
    done = set(zip(df["corner_id"].astype(str), df["seed_md5"].astype(str),
                   df["param_hash"].astype(str)))
    return done, df.to_dict("records")


def append_row(results_path, row):
    new = not os.path.exists(results_path)
    with open(results_path, "a") as fh:
        if new:
            fh.write("\t".join(RESULTS_COLS) + "\n")
        fh.write("\t".join(str(row.get(c, "")) for c in RESULTS_COLS) + "\n")


def render_wav(midi_path, wav_path):
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    subprocess.run(["fluidsynth", "-ni", "-F", wav_path, SF2, midi_path],
                   check=False, capture_output=True)
    return os.path.exists(wav_path)


# ----------------------------- love normalization ---------------------------
def love_normalizer():
    """Map raw 47 love -> ~[-0.5,0.5] using corpus percentiles, so the taste term is
    on the same scale as corner_gain (a cosine delta) and stays a tie-breaker."""
    try:
        tp = pd.read_parquet(PRED, columns=["pred_love"])
        p05, p50, p95 = np.percentile(tp["pred_love"].to_numpy(float), [5, 50, 95])
        span = max(1e-6, float(p95 - p05))
        return lambda lv: float((lv - p50) / span) if np.isfinite(lv) else 0.0
    except Exception:  # noqa: BLE001
        return lambda lv: 0.0


# ----------------------------- the loop -------------------------------------
def build_plan(targets_csv, book, n_corners, budget, seeds_per_corner,
               prime, tokens, temps):
    """Build the ordered (corner, seed, params) work list from the targets CSV."""
    tg_df = pd.read_csv(targets_csv)
    plan = []
    used_corners = 0
    for _, row in tg_df.iterrows():
        if used_corners >= n_corners:
            break
        ctype = str(row.get("corner_type", ""))
        caption = str(row.get("caption", ""))
        corner_vec = book.resolve(ctype, caption)
        if corner_vec is None:
            continue
        seeds = []
        top3 = str(row.get("nearest_md5_top3", "")).split(";")
        for m in top3:
            m = m.strip()
            if len(m) == 32 and m not in seeds:
                seeds.append(m)
        if not seeds:
            ns = str(row.get("nearest_md5", "")).strip()
            if len(ns) == 32:
                seeds = [ns]
        if not seeds:
            continue
        corner_id = f"r{int(row['rank'])}" if "rank" in row and pd.notna(row["rank"]) else \
            hashlib.sha1(caption.encode()).hexdigest()[:6]
        # candidates: cycle seeds × temperatures until budget reached, one param varied
        cands = []
        for t in temps:
            for sd in seeds[:seeds_per_corner]:
                cands.append((sd, t))
        for sd, t in cands[:budget]:
            plan.append(dict(corner_id=corner_id, corner_type=ctype, caption=caption,
                             corner_vec=corner_vec, seed_md5=sd,
                             prime=prime, tokens=tokens, temperature=t, topp=0.96))
        used_corners += 1
    return plan


def run(args):
    os.makedirs(RUNS, exist_ok=True)
    run_dir = os.path.join(RUNS, args.tag)
    listen_dir = os.path.join(run_dir, "listen")
    os.makedirs(listen_dir, exist_ok=True)
    results_path = os.path.join(run_dir, "results.tsv")

    sig, tg, gg, prop = load_modules()
    scaler = sig._load_scaler()
    ext = np.load(SIGP).astype(np.float32)
    md5s = [l.strip() for l in open(IDXP) if l.strip()]

    book = CornerBook()
    taste = TasteModel(prop, ext, md5s)
    love_norm = love_normalizer()
    engine = Engine(gg, args.model)

    temps = [float(t) for t in args.temps.split(",")] if args.sweep else [args.temperature]
    plan = build_plan(args.corners, book, args.n_corners, args.budget,
                      args.seeds_per_corner, args.prime, args.tokens, temps)
    if args.once:
        plan = plan[:1]
    if not plan:
        log("empty plan (no resolvable corners/seeds) — nothing to do.")
        return 1

    done, prior = load_done(results_path)
    best_for_corner = {}
    for rec in prior:
        try:
            s = float(rec.get("invention_score"))
        except (TypeError, ValueError):
            continue
        cid = str(rec.get("corner_id"))
        if cid not in best_for_corner or s > best_for_corner[cid]:
            best_for_corner[cid] = s

    log(f"run '{args.tag}': {len(plan)} planned iterations, {len(done)} already done "
        f"(resumable). weights place={args.w_place} taste={args.w_taste}")

    interrupted = {"flag": False}

    def _sigint(_a, _b):
        interrupted["flag"] = True
        log("interrupt received — finishing current iteration then summarizing.")
    signal.signal(signal.SIGINT, _sigint)

    kept = []
    n_iter = n_keep = n_disc = n_crash = 0
    t0 = time.time()

    for it, p in enumerate(plan, 1):
        key = (str(p["corner_id"]), p["seed_md5"], param_hash(p["prime"], p["tokens"],
                                                              p["temperature"], p["topp"]))
        if key in done:
            continue
        n_iter += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        ph = key[2]
        stem = f"{p['corner_id']}_{p['seed_md5'][:8]}_{ph}"
        seed_midi = os.path.join(ROOT, "MIDIs", p["seed_md5"][:2], p["seed_md5"] + ".mid")
        row = dict(ts=ts, corner_id=p["corner_id"], corner_type=p["corner_type"],
                   caption=p["caption"], seed_md5=p["seed_md5"], param_hash=ph,
                   prime=p["prime"], tokens=p["tokens"], temperature=p["temperature"],
                   topp=p["topp"])
        try:
            toks = engine.seed_tokens(seed_midi)
            seed_toks, full_toks, used_prime = engine.generate(
                toks, p["prime"], p["tokens"], p["temperature"], p["topp"])
            cand_noext = os.path.join(run_dir, "cand", stem)
            seed_noext = os.path.join(run_dir, "seed_rt", stem)
            os.makedirs(os.path.dirname(cand_noext), exist_ok=True)
            os.makedirs(os.path.dirname(seed_noext), exist_ok=True)
            cand_mid, n_cand = engine.write(full_toks, cand_noext)
            seed_mid, _n_seed = engine.write(seed_toks, seed_noext)
            if not cand_mid or not seed_mid:
                raise RuntimeError("decode produced no notes")

            cand_vec = sig.vector_from_midi(cand_mid, scaler).astype(np.float64)
            seed_vec = sig.vector_from_midi(seed_mid, scaler).astype(np.float64)
            cv = p["corner_vec"]
            cand_cos = _cos(cand_vec, cv)
            seed_cos = _cos(seed_vec, cv)
            corner_gain = cand_cos - seed_cos

            ok, cinfo = coherence_gate(sig, tg, cand_mid, args.min_notes, args.min_quality)
            pred_love = taste.love(cand_vec)
            pln = love_norm(pred_love)

            row.update(corner_gain=round(corner_gain, 4), seed_cos=round(seed_cos, 4),
                       cand_cos=round(cand_cos, 4), pred_love=round(pred_love, 4),
                       pred_love_norm=round(pln, 4), coherent=int(ok),
                       quality=round(cinfo["quality"], 4) if np.isfinite(cinfo["quality"]) else "",
                       n_notes=n_cand, midi=os.path.relpath(cand_mid, ROOT))

            if not ok:
                score = float("-inf")
                status = "discard"
                row.update(invention_score="-inf", status=status, note=cinfo["reason"])
                n_disc += 1
            else:
                score = args.w_place * corner_gain + args.w_taste * pln
                prev_best = best_for_corner.get(str(p["corner_id"]), float("-inf"))
                # keep if it moved toward the corner AND is the best yet for this corner
                keep = (corner_gain > 0) and (score > prev_best)
                status = "keep" if keep else "discard"
                row.update(invention_score=round(score, 4), status=status,
                           note=cinfo["reason"])
                if keep:
                    best_for_corner[str(p["corner_id"])] = score
                    n_keep += 1
                    if args.render:
                        wav = os.path.join(listen_dir, f"{stem}_score{score:+.3f}.wav")
                        if render_wav(cand_mid, wav):
                            row["wav"] = os.path.relpath(wav, ROOT)
                    kept.append((p["corner_id"], p["seed_md5"], score, corner_gain,
                                 pred_love, row.get("wav", ""), p["caption"]))
                else:
                    n_disc += 1

            inv(f"{args.tag} {it} | corner:{p['corner_id']} | seed:{p['seed_md5'][:8]} "
                f"| place:{corner_gain:+.4f} | love:{pred_love:.2f} "
                f"| score:{row['invention_score']} | status:{status} | "
                f"{cinfo['reason']} (prime {used_prime}, {n_cand} notes)")
        except Exception as ex:  # noqa: BLE001
            n_crash += 1
            row.update(corner_gain="", seed_cos="", cand_cos="", pred_love="",
                       pred_love_norm="", coherent=0, quality="", n_notes=0,
                       invention_score="-inf", status="crash", note=repr(ex)[:80])
            inv(f"{args.tag} {it} | corner:{p['corner_id']} | seed:{p['seed_md5'][:8]} "
                f"| status:crash | {repr(ex)[:60]}")

        append_row(results_path, row)
        done.add(key)
        if interrupted["flag"]:
            break

    summary = write_summary(run_dir, args, kept, best_for_corner, n_iter, n_keep,
                            n_disc, n_crash, time.time() - t0, interrupted["flag"])
    log(f"DONE: {n_iter} iters | keep {n_keep} / discard {n_disc} / crash {n_crash} "
        f"| {time.time()-t0:.0f}s")
    log(f"results -> {results_path}")
    log(f"summary -> {summary}")
    if kept and args.render:
        log(f"shortlist WAVs -> {listen_dir} ({len([k for k in kept if k[5]])} rendered)")
    return 0


def write_summary(run_dir, args, kept, best_for_corner, n_iter, n_keep, n_disc,
                  n_crash, elapsed, interrupted):
    path = os.path.join(run_dir, "summary.md")
    kept_sorted = sorted(kept, key=lambda k: k[2], reverse=True)
    with open(path, "w") as fh:
        fh.write(f"# Invention loop run `{args.tag}`\n\n")
        fh.write(f"- ended: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
                 f"{' (INTERRUPTED)' if interrupted else ''}\n")
        fh.write(f"- iterations: {n_iter}  |  keep {n_keep} / discard {n_disc} / "
                 f"crash {n_crash}  |  {elapsed:.0f}s\n")
        fh.write(f"- weights: place={args.w_place}, taste={args.w_taste}; "
                 f"tokens={args.tokens}, prime={args.prime}\n\n")
        fh.write("## Best invention_score per corner\n\n")
        if best_for_corner:
            for cid, s in sorted(best_for_corner.items(), key=lambda kv: kv[1], reverse=True):
                fh.write(f"- `{cid}`: {s:+.4f}\n")
        else:
            fh.write("- (none scored)\n")
        fh.write("\n## Shortlist (kept, by score — AUDITION THESE)\n\n")
        if kept_sorted:
            for cid, seed, s, cg, lv, wav, cap in kept_sorted:
                fh.write(f"- **{s:+.4f}** corner `{cid}` seed `{seed[:8]}` "
                         f"(place {cg:+.4f}, love {lv:.2f})\n  - {cap}\n")
                if wav:
                    fh.write(f"  - WAV: `{wav}`\n")
        else:
            fh.write("- (nothing kept — no candidate beat its seed baseline + coherence)\n")
        fh.write("\n## Next ideas\n\n")
        fh.write("- Widen budget on the highest-gain corner; vary prime length next.\n")
        fh.write("- Try the #2/#3 nearest seeds for corners that produced only discards.\n")
        fh.write("- Hand-audition the shortlist; the ear is the final keep/discard.\n")
    return path


def main():
    ap = argparse.ArgumentParser(description="Autonomous coordinate-driven invention loop")
    ap.add_argument("--tag", default="inv-" + datetime.now().strftime("%Y%m%d"))
    ap.add_argument("--corners", default=DEFAULT_TARGETS, help="taste-ranked targets CSV")
    ap.add_argument("--model", default=None, help="GMT ckpt (default: base Large)")
    ap.add_argument("--once", action="store_true", help="single iteration (smoke test)")
    ap.add_argument("--n-corners", type=int, default=3)
    ap.add_argument("--budget", type=int, default=4, help="candidates per corner")
    ap.add_argument("--seeds-per-corner", type=int, default=3)
    ap.add_argument("--prime", type=int, default=512)
    ap.add_argument("--tokens", type=int, default=512)
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--sweep", action="store_true", help="vary temperature per --temps")
    ap.add_argument("--temps", default="0.8,0.95")
    ap.add_argument("--w-place", type=float, default=0.6)
    ap.add_argument("--w-taste", type=float, default=0.4)
    ap.add_argument("--min-notes", type=int, default=40)
    ap.add_argument("--min-quality", type=float, default=0.45)
    ap.add_argument("--render", action="store_true", help="render kept candidates to WAV")
    args = ap.parse_args()

    if not os.path.exists(args.corners):
        raise SystemExit(f"targets CSV not found: {args.corners}")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
