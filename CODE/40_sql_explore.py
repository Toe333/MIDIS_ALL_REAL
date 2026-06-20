#!/usr/bin/env python3
"""
40_sql_explore.py  —  SQL-driven taste-targeted candidate finder (Windows / LocalDB)
====================================================================================
Joins SQL catalog queries with taste_pred.parquet to surface the highest-predicted-
taste songs matching various musicological filters, then optionally renders top
candidates to WAV using the local FluidSynth install.

Run:
    .venv\Scripts\python CODE\40_sql_explore.py
    .venv\Scripts\python CODE\40_sql_explore.py --render     # also render top-10
    .venv\Scripts\python CODE\40_sql_explore.py --top 20     # show 20 per query
"""
import argparse, os, pathlib, subprocess, sys
import pandas as pd
import pyodbc

# ── paths ─────────────────────────────────────────────────────────────────────
ROOT       = pathlib.Path(__file__).resolve().parents[1]
WORK       = ROOT / "_work"
MIDIS      = ROOT / "MIDIs"
SF2        = ROOT / "soundfonts" / "GeneralUserGS.sf2"
FLUIDSYNTH = pathlib.Path(r"C:\Program Files\fluidsynth-2.4.8-win10-x64\bin\fluidsynth.exe")
OUT_DIR    = WORK / "sql_explore"
OUT_DIR.mkdir(exist_ok=True)

# ── DB connection ─────────────────────────────────────────────────────────────
CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=(localdb)\MSSQLLocalDB;"
    "DATABASE=MIDIS_ALL_REAL;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

def get_db():
    return pyodbc.connect(CONN_STR, timeout=10)

# ── taste scores ──────────────────────────────────────────────────────────────
def load_taste():
    df = pd.read_parquet(WORK / "taste_pred.parquet")
    return dict(zip(df["md5"], df["pred_groove_taste"]))

# ── path converter (Linux → Windows) ─────────────────────────────────────────
def midi_path(md5: str) -> pathlib.Path:
    """Reconstruct local Windows MIDI path from md5."""
    return MIDIS / md5[:2] / f"{md5}.mid"

# ── MIDI copy helper ──────────────────────────────────────────────────────────
def copy_midi(row, label: str, out_dir: pathlib.Path, idx: int) -> bool:
    """Copy MIDI with a rich descriptive filename. No audio bounce needed."""
    src = midi_path(row.md5)
    if not src.exists():
        print(f"  ⚠ MIDI missing: {src}")
        return False
    # build name: 03_swung_melodic_Eb-major_185bpm_sw2.43_diat0.78_abc12345.mid
    key_safe = str(getattr(row, "key", "unk")).replace(" ", "-").replace("#", "s")
    bpm_val  = getattr(row, "bpm", None)
    bpm_str  = f"{int(bpm_val)}bpm" if bpm_val and bpm_val == bpm_val else "bpm-unk"
    sw       = getattr(row, "swing_bur", None)
    sw_str   = f"_sw{sw:.2f}" if sw and sw == sw else ""
    dr       = getattr(row, "diatonic_ratio", None)
    dr_str   = f"_diat{dr:.2f}" if dr and dr == dr else ""
    taste    = getattr(row, "pred_taste", None)
    t_str    = f"_taste{taste:.2f}" if taste and taste == taste else ""
    fname    = f"{idx:02d}_{label}_{key_safe}_{bpm_str}{sw_str}{dr_str}{t_str}_{row.md5[:8]}.mid"
    dest = out_dir / fname
    if dest.exists():
        print(f"  ↩ already exists: {dest.name}")
        return True
    import shutil
    shutil.copy2(src, dest)
    print(f"  ✅ {dest.name}")
    return True

# ── query runners ─────────────────────────────────────────────────────────────
def run_query(con, sql: str, taste: dict) -> pd.DataFrame:
    df = pd.read_sql(sql, con)
    df["pred_taste"] = df["md5"].map(taste).fillna(0.0)
    return df.sort_values("pred_taste", ascending=False)

# ── queries ───────────────────────────────────────────────────────────────────
Q_SWUNG_MELODIC = """
SELECT TOP 500
    md5, bpm, [key], swing_bur, diatonic_ratio,
    drum_swing, drum_pattern_entropy, drum_snare_backbeat,
    has_melody, has_drums, song_id
FROM dbo.metadata
WHERE quality_flag = 'ok'
  AND bpm_valid   = 1
  AND is_swung    = 1
  AND has_melody  = 1
  AND diatonic_ratio > 0.75
ORDER BY swing_bur DESC
"""

Q_EMPTY_CORNER = """
SELECT TOP 500
    md5, bpm, [key], swing_bur, diatonic_ratio,
    drum_swing, drum_kick_density,
    drum_snare_backbeat, drum_pattern_entropy, has_drums
FROM dbo.metadata
WHERE quality_flag = 'ok'
  AND has_drums   = 1
  AND drum_swing  BETWEEN 0.38 AND 0.68
  AND drum_snare_backbeat < 0.30          -- no backbeat (unusual)
  AND diatonic_ratio > 0.72
ORDER BY drum_pattern_entropy DESC
"""

Q_HIGH_ENTROPY_DRUMS = """
SELECT TOP 500
    md5, bpm, [key], drum_pattern_entropy, drum_swing,
    drum_kick_density, drum_snare_backbeat,
    diatonic_ratio, swing_bur, has_melody
FROM dbo.metadata
WHERE quality_flag = 'ok'
  AND has_drums   = 1
  AND drum_pattern_entropy > 0.60
  AND bpm_valid   = 1
  AND bpm BETWEEN 80 AND 200          -- exclude BPM-halving/quartering errors
ORDER BY drum_pattern_entropy DESC
"""

Q_CLEAN_DIATONIC = """
SELECT TOP 500
    md5, bpm, [key], diatonic_ratio, swing_bur,
    drum_swing, has_melody, has_drums
FROM dbo.metadata
WHERE quality_flag    = 'ok'
  AND bpm_valid       = 1
  AND diatonic_ratio  > 0.90
  AND has_melody      = 1
ORDER BY diatonic_ratio DESC
"""

QUERIES = [
    ("swung_melodic",      Q_SWUNG_MELODIC,      "Swung + melodic + diatonic"),
    ("empty_corner",       Q_EMPTY_CORNER,        "Empty-corner drum region (no-backbeat, swung)"),
    ("high_entropy_drums", Q_HIGH_ENTROPY_DRUMS,  "High drum entropy (complex patterns)"),
    ("clean_diatonic",     Q_CLEAN_DIATONIC,      "Cleanly diatonic + melodic"),
]

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render",  action="store_true", help="Render top-10 of best query to WAV")
    ap.add_argument("--top",     type=int, default=15, help="Rows to print per query (default 15)")
    ap.add_argument("--render-n", type=int, default=10, help="How many to render (default 10)")
    args = ap.parse_args()

    print("Loading taste predictions ...")
    taste = load_taste()
    print(f"  {len(taste):,} md5 scores loaded  (mean={sum(taste.values())/len(taste):.2f})")

    print("\nConnecting to LocalDB ...")
    con = get_db()
    print("  ✅ connected\n")

    best_query_name = None
    best_df = None

    for name, sql, label in QUERIES:
        print(f"{'─'*70}")
        print(f"▶ {label}")
        df = run_query(con, sql, taste)
        n_pool = len(df)
        print(f"  {n_pool} candidates  │  top-{args.top} by predicted taste:")
        top = df.head(args.top)
        # nice display columns
        show_cols = ["md5", "pred_taste"] + [c for c in
            ["bpm","key","swing_bur","diatonic_ratio","drum_swing",
             "drum_snare_backbeat","drum_pattern_entropy","has_melody","has_drums"]
            if c in df.columns]
        print(top[show_cols].to_string(index=False))

        csv_path = OUT_DIR / f"{name}_top{args.top}.csv"
        top.to_csv(csv_path, index=False)
        print(f"  → {csv_path}")

        if best_df is None or df.iloc[0]["pred_taste"] > best_df.iloc[0]["pred_taste"]:
            best_df = df
            best_query_name = name

    con.close()

    # ── copy MIDIs ────────────────────────────────────────────────────────────
    if args.render:
        print(f"\n{'═'*70}")
        print(f"🎵 Copying top-{args.render_n} MIDIs from '{best_query_name}' ...")
        render_dir = OUT_DIR / f"midi_{best_query_name}"
        render_dir.mkdir(exist_ok=True)
        copied = 0
        for i, row in enumerate(best_df.head(args.render_n).itertuples(index=False)):
            ok = copy_midi(row, best_query_name, render_dir, i)
            copied += ok
        print(f"\n  {copied}/{args.render_n} MIDIs → {render_dir}")
    else:
        print("\n  Tip: re-run with --render to copy top candidate MIDIs.")

    # ── also surface the 5 known generation seeds ──────────────────────────────
    seeds_csv = WORK / "generation_seeds" / "top5_targets.csv"
    if seeds_csv.exists():
        seeds = pd.read_csv(seeds_csv)
        seeds["pred_taste"] = seeds["md5"].map(taste)
        print(f"\n{'═'*70}")
        print("📌 Known generation seeds (top5_targets.csv) with taste scores:")
        print(seeds.to_string(index=False))

    print("\nDone.")

if __name__ == "__main__":
    main()
