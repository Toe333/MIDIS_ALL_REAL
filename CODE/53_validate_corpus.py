#!/usr/bin/env python3
"""53_validate_corpus.py — READ-ONLY Medallion-model quality gate for the corpus.

A Great-Expectations-style assertion pass (stdlib + pandas/numpy only, no heavy deps)
that proves the data the invention loop (CODE/52) seeds from is sound. It NEVER mutates
the catalog, signatures, or MIDIs/ — it only reads and reports.

Medallion mapping (the three tiers the loop depends on):
  * BRONZE = MIDIs/<md5[:2]>/<md5>.mid          (read-only warehouse)
  * SILVER = catalog/metadata.parquet (+ .sqlite) (~459,805 × ~201)
  * GOLD   = SIGNATURES_DATA/signatures_ext.npy (N×88) + md5 map + taste preds

Checks (each → PASS / WARN / FAIL):
  1. SILVER row count vs STATE.md LIVE VALUES (catalog == 459,805).
  2. GOLD internal consistency: signatures_ext rows == signatures_md5.txt lines (HARD).
  3. GOLD signature width == 88 (the locked layout) (HARD).
  4. GOLD↔SILVER alignment: ext rows == catalog rows, else report the known +N drift
     (the 2026-06-25 seed embed grew ext past the catalog) as a documented WARN.
  5. Corrected detection columns present (bpm_v2/felt_bpm, ts_final, key_v2, key_corr).
  6. Pristine subset (quality_flag='ok' AND bpm_valid=1 AND duration_suspect=0) is
     non-empty and has no NaNs in the columns the loop / signature pipeline rely on.
  7. Seed-pickability: every seed the loop could pick from the taste targets CSV
     (nearest_md5 + top-3) exists on disk, is in the signature space, and (when in the
     catalog) passes the pristine filter.
  8. Taste predictions exist and cover the catalog (md5-joinable).

Emits a PASS/FAIL report (stdout + _work/validation/report_<UTC>.txt + latest.json).
Exit code 0 = no FAILs (WARNs allowed), 1 = at least one FAIL.

Usage:
  .venv-linux/bin/python CODE/53_validate_corpus.py
  .venv-linux/bin/python CODE/53_validate_corpus.py --targets _work/generation_seeds/targets_taste_v2_20260622.csv
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)

SIG = os.path.join(ROOT, "SIGNATURES_DATA", "signatures_ext.npy")
IDX = os.path.join(ROOT, "SIGNATURES_DATA", "signatures_md5.txt")
META = os.path.join(ROOT, "catalog", "metadata.parquet")
PRED = os.path.join(ROOT, "_work", "taste_pred_v2.parquet")
SEEDS = os.path.join(ROOT, "_work", "generation_seeds")
OUTDIR = os.path.join(ROOT, "_work", "validation")

# --- STATE.md LIVE VALUES (the things that drift — keep in sync with STATE.md) ---
STATE_CATALOG_ROWS = 459_805
STATE_SIG_WIDTH = 88
CORRECTED_COLS = ["bpm_v2", "felt_bpm", "ts_final", "key_v2", "key_corr"]
# columns the signature pipeline / loop must have non-null in the pristine subset
PRISTINE_NONNULL = ["bpm_v2", "felt_bpm", "ts_final", "diatonic_ratio"]
PRISTINE_FILTER = "quality_flag == 'ok' and bpm_valid == 1 and duration_suspect == 0"


class Report:
    def __init__(self):
        self.rows = []   # (level, name, detail)
        self.n_fail = 0
        self.n_warn = 0

    def add(self, level, name, detail=""):
        level = level.upper()
        if level == "FAIL":
            self.n_fail += 1
        elif level == "WARN":
            self.n_warn += 1
        self.rows.append((level, name, detail))
        mark = {"PASS": "ok ", "WARN": "WARN", "FAIL": "FAIL"}.get(level, level)
        print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))

    def gate(self, cond, name, ok_detail="", fail_detail="", warn=False):
        if cond:
            self.add("PASS", name, ok_detail)
        else:
            self.add("WARN" if warn else "FAIL", name, fail_detail)
        return cond


def md5_path(md5: str) -> str:
    return os.path.join(ROOT, "MIDIs", md5[:2], md5 + ".mid")


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Medallion quality gate.")
    ap.add_argument("--targets", default=os.path.join(SEEDS, "targets_taste_v2_20260622.csv"),
                    help="taste targets CSV whose seeds the loop may pick")
    ap.add_argument("--max-seed-check", type=int, default=200,
                    help="cap on how many candidate seeds to disk-check")
    args = ap.parse_args()

    print("=" * 74)
    print("53_validate_corpus — READ-ONLY Medallion quality gate")
    print("=" * 74)
    R = Report()

    # ---------------- GOLD: signatures + md5 map ----------------
    print("\n[GOLD] signatures_ext.npy + signatures_md5.txt")
    if not os.path.exists(SIG) or not os.path.exists(IDX):
        R.add("FAIL", "gold artifacts exist", f"missing {SIG} or {IDX}")
        return _finish(R)
    ext = np.load(SIG, mmap_mode="r")
    md5s = [l.strip() for l in open(IDX) if l.strip()]
    n_ext, width = ext.shape
    R.gate(n_ext == len(md5s), "ext rows == md5 map lines",
           f"{n_ext} rows", f"ext {n_ext} != md5 map {len(md5s)}")
    R.gate(width == STATE_SIG_WIDTH, "signature width == 88",
           f"{width}-D", f"width {width} != {STATE_SIG_WIDTH}")
    R.gate(len(set(md5s)) == len(md5s), "md5 map has no duplicates",
           f"{len(md5s)} unique", f"{len(md5s) - len(set(md5s))} dupes")

    # ---------------- SILVER: catalog ----------------
    print("\n[SILVER] catalog/metadata.parquet")
    pf = pq.ParquetFile(META)
    n_cat = pf.metadata.num_rows
    cat_cols = set(pf.schema.names)
    R.gate(n_cat == STATE_CATALOG_ROWS, "catalog rows == STATE LIVE VALUE",
           f"{n_cat} rows", f"{n_cat} != STATE {STATE_CATALOG_ROWS}")
    drift = n_ext - n_cat
    if drift != 0:
        R.add("WARN", "ext vs catalog row drift",
              f"ext has {drift:+d} vs catalog (documented 2026-06-25 seed embed; "
              f"these rows are in ext+md5 map but not yet in catalog/taste)")
    missing_corr = [c for c in CORRECTED_COLS if c not in cat_cols]
    R.gate(not missing_corr, "corrected detection cols present",
           ", ".join(CORRECTED_COLS), f"missing: {missing_corr}")

    # ---------------- SILVER: pristine subset integrity ----------------
    print("\n[SILVER] pristine subset integrity")
    need = ["md5", "quality_flag", "bpm_valid", "duration_suspect"] + \
           [c for c in PRISTINE_NONNULL if c in cat_cols]
    cat = pd.read_parquet(META, columns=[c for c in need if c in cat_cols])
    try:
        pristine = cat.query(PRISTINE_FILTER)
    except Exception as ex:  # noqa: BLE001
        R.add("FAIL", "pristine filter evaluable", repr(ex)[:80])
        pristine = cat.iloc[0:0]
    R.gate(len(pristine) > 0, "pristine subset non-empty",
           f"{len(pristine):,} rows ({100*len(pristine)/max(1,len(cat)):.1f}% of catalog)",
           "pristine subset is empty")
    for c in PRISTINE_NONNULL:
        if c not in pristine.columns:
            R.add("WARN", f"pristine non-null: {c}", "column absent")
            continue
        n_nan = int(pristine[c].isna().sum())
        R.gate(n_nan == 0, f"pristine non-null: {c}",
               "0 NaNs", f"{n_nan:,} NaNs in pristine subset", warn=True)

    pristine_md5 = set(pristine["md5"]) if "md5" in pristine.columns else set()

    # ---------------- GOLD: taste predictions ----------------
    print("\n[GOLD] taste predictions")
    if os.path.exists(PRED):
        tp = pd.read_parquet(PRED, columns=["md5", "pred_love"])
        R.gate(len(tp) > 0, "taste_pred_v2 non-empty", f"{len(tp):,} rows", "empty")
        cov = len(set(tp["md5"]) & set(md5s)) / max(1, len(md5s))
        R.gate(cov > 0.98, "taste preds cover signature space",
               f"{100*cov:.1f}% of sig md5s have a taste pred",
               f"only {100*cov:.1f}% coverage", warn=(cov > 0.90))
    else:
        R.add("WARN", "taste_pred_v2 exists", "absent — loop taste rank will retrain only")

    # ---------------- seed-pickability (the gate that protects the loop) ----------------
    print("\n[SEEDS] loop seed-pickability from taste targets")
    if not os.path.exists(args.targets):
        R.add("WARN", "targets CSV exists", f"absent: {args.targets}")
    else:
        tg = pd.read_csv(args.targets)
        sig_set = set(md5s)
        seeds = []
        for col in ("nearest_md5", "nearest_md5_top3"):
            if col in tg.columns:
                for v in tg[col].dropna():
                    seeds.extend(str(v).split(";"))
        seeds = [s.strip() for s in seeds if s and len(s.strip()) == 32]
        uniq = list(dict.fromkeys(seeds))[: args.max_seed_check]
        n_disk = sum(os.path.exists(md5_path(m)) for m in uniq)
        n_insig = sum(m in sig_set for m in uniq)
        n_prist = sum(1 for m in uniq if m in pristine_md5)
        R.gate(n_disk == len(uniq), "candidate seeds exist on disk",
               f"{n_disk}/{len(uniq)} present", f"{len(uniq)-n_disk} missing .mid")
        R.gate(n_insig == len(uniq), "candidate seeds embeddable (in sig space)",
               f"{n_insig}/{len(uniq)} in signature map",
               f"{len(uniq)-n_insig} not in signature map", warn=True)
        # not every nearest_md5 must be pristine, but most should be — soft gate
        frac_prist = n_prist / max(1, len(uniq))
        R.gate(frac_prist >= 0.5, "majority of candidate seeds are pristine",
               f"{n_prist}/{len(uniq)} ({100*frac_prist:.0f}%) pass pristine filter",
               f"only {100*frac_prist:.0f}% pristine", warn=True)

    return _finish(R)


def _finish(R: "Report") -> int:
    verdict = "FAIL" if R.n_fail else ("PASS-with-WARN" if R.n_warn else "PASS")
    print("\n" + "=" * 74)
    print(f"VERDICT: {verdict}   ({R.n_fail} FAIL, {R.n_warn} WARN, "
          f"{len(R.rows) - R.n_fail - R.n_warn} PASS)")
    print("=" * 74)

    os.makedirs(OUTDIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    txt = os.path.join(OUTDIR, f"report_{ts}.txt")
    with open(txt, "w") as fh:
        fh.write(f"53_validate_corpus report {ts}\nVERDICT: {verdict}\n\n")
        for level, name, detail in R.rows:
            fh.write(f"[{level}] {name}" + (f" — {detail}" if detail else "") + "\n")
    payload = {"built_at": ts, "verdict": verdict, "n_fail": R.n_fail,
               "n_warn": R.n_warn,
               "checks": [{"level": l, "name": n, "detail": d} for l, n, d in R.rows]}
    with open(os.path.join(OUTDIR, "latest.json"), "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"report -> {txt}")
    return 1 if R.n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
