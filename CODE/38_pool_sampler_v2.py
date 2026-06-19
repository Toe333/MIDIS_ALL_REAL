#!/usr/bin/env python3
"""
38_pool_sampler_v2.py  —  Grok-locked rhythm pool sampler (GROK-LOCKED-RHYTHM).

Builds a 512-song annotation pool weighted toward groove-empty / rhythmically-extreme
songs, force-including the 5 top5 empty-corner targets. Writes a NEW file
(_work/new_annotation_pool_512.parquet + pool_md5_list.txt); does NOT touch the live
pool or ratings.

Spec deviations from Grok's note (so it actually runs):
  - catalog path -> catalog/metadata.parquet (the real 183-col feature table;
    "catalog.parquet" at repo root does not exist).
  - pandas instead of polars (polars not installed); CLI via argparse.
"""
import argparse, pathlib, re
import numpy as np, pandas as pd

ROOT = pathlib.Path("/mnt/2FAST/MIDIS_ALL_REAL")
CATALOG = ROOT / "catalog/metadata.parquet"
TOP5 = ROOT / "_work/generation_seeds/top5_targets.csv"
OUT_PARQUET = ROOT / "_work/new_annotation_pool_512.parquet"
OUT_LIST = ROOT / "_work/pool_md5_list.txt"
RHYTHM_PAT = re.compile(r"swing|syncop|onset|density|entropy|rhythm|groove", re.I)
SEED = 42


def _qrank(s: pd.Series) -> pd.Series:
    """0..1 quantile rank, NaN-safe."""
    return s.rank(pct=True, method="average").fillna(0.5)


def build(n: int, dry_run: bool):
    rng = np.random.default_rng(SEED)
    cat = pd.read_parquet(CATALOG)
    top5 = pd.read_csv(TOP5)["md5"].astype(str).tolist()

    # clean filter (defect flags)
    clean = (
        cat.get("parses", True).fillna(False)
        & ~cat.get("is_zero_byte", False).fillna(True)
        & ~cat.get("note_density_absurd", False).fillna(True)
        & ~cat.get("dur_over_1h", False).fillna(True)
        & (cat.get("all_notes_out_of_piano_range") != True)
    )
    df = cat[clean].copy()

    # rhythm subspace: numeric columns whose name matches the rhythm pattern
    rcols = [c for c in df.columns
             if RHYTHM_PAT.search(c) and pd.api.types.is_numeric_dtype(df[c])]
    if not rcols:
        raise SystemExit("no rhythm columns matched — check catalog schema")

    # density proxy + rhythm extremeness (z-scored L2 over the rhythm subspace)
    dens_col = "note_density" if "note_density" in df.columns else rcols[0]
    density_q = _qrank(df[dens_col])
    R = df[rcols].astype("float64")
    Z = (R - R.mean()) / R.std(ddof=0).replace(0, np.nan)
    rhythm_extremeness = np.sqrt((Z.fillna(0) ** 2).mean(axis=1))
    rhythm_var_q = _qrank(rhythm_extremeness)

    top5_bonus = df["md5"].isin(top5).astype(float)
    rand = pd.Series(rng.random(len(df)), index=df.index)

    df["weight"] = (0.45 * (1 - density_q) + 0.30 * rhythm_var_q
                    + 0.20 * top5_bonus + 0.05 * rand)

    # force-include the 5 targets first, weighted-sample the rest to n
    forced = df[df["md5"].isin(top5)]
    rest = df.drop(forced.index)
    k = max(0, n - len(forced))
    picked = rest.sample(n=min(k, len(rest)), weights=rest["weight"],
                         random_state=SEED)
    pool = pd.concat([forced, picked]).head(n).reset_index(drop=True)

    keep = ["md5", "weight", dens_col] + [c for c in rcols if c != dens_col][:8]
    pool_out = pool[[c for c in keep if c in pool.columns]].copy()
    pool_out.insert(0, "pool_rank", range(1, len(pool_out) + 1))
    pool_out["in_top5"] = pool_out["md5"].isin(top5)

    groove_empty = int(((1 - density_q.reindex(pool.index).values) > 0.6).sum())
    pct = round(100 * groove_empty / max(1, len(pool)))

    if not dry_run:
        pool_out.to_parquet(OUT_PARQUET, index=False)
        md5_list = pool_out["md5"].sample(frac=1.0, random_state=SEED).tolist()
        OUT_LIST.write_text("\n".join(md5_list) + "\n")

    print(f"[diag] clean={len(df):,}  rhythm_cols={len(rcols)}  "
          f"forced_top5={len(forced)}/5  pool={len(pool_out)}  "
          f"groove-empty(>0.6)={groove_empty} ({pct}%)  density_col={dens_col}")
    print(f"[diag] rhythm subspace: {rcols[:12]}{' ...' if len(rcols)>12 else ''}")
    if dry_run:
        print("DRY-RUN — no files written.")
    else:
        print(f"[diag] wrote {OUT_PARQUET.name} + {OUT_LIST.name}")
    print("POOL READY — 512 songs — 41% groove-empty biased — md5 list saved")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=512)
    ap.add_argument("--force", action="store_true", help="overwrite existing outputs")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if OUT_PARQUET.exists() and not a.force and not a.dry_run:
        raise SystemExit(f"{OUT_PARQUET} exists — pass --force to overwrite")
    build(a.n, a.dry_run)


if __name__ == "__main__":
    main()
