#!/usr/bin/env python3
"""17_stats.py — Phase 8 corpus statistics + dataset card (text, no heavy deps).

Reads catalog/metadata.parquet, writes _stats/corpus_statistics.md and
_stats/dataset_card.md. Charts optional (skipped if matplotlib absent).
Usage:  python3 CODE/17_stats.py
"""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C


def vc(df, col, n=12):
    if col not in df.columns:
        return "(missing)"
    return df[col].value_counts(dropna=False).head(n).to_string()


def main():
    df = pd.read_parquet(os.path.join(C.CATALOG, "metadata.parquet"))
    man = pd.read_parquet(os.path.join(C.CATALOG, "master_manifest.parquet"),
                          columns=["md5", "sources"])
    src = man["sources"].explode().value_counts()
    total_hours = (df["duration_sec"].dropna().sum() / 3600.0) if "duration_sec" in df else 0

    lines = ["# MIDIS_ALL_REAL — Corpus Statistics\n",
             f"- Files (metadata rows): **{len(df):,}**",
             f"- Total duration: **{total_hours:,.0f} hours**",
             f"- Quarantined: {int(df.get('is_quarantined', pd.Series([0])).fillna(0).sum())}",
             "\n## Files by source\n```", src.to_string(), "```",
             "\n## Key distribution\n```", vc(df, "key", 24), "```",
             "\n## Mode\n```", vc(df, "mode"), "```",
             "\n## Genre hint\n```", vc(df, "genre_hint"), "```",
             "\n## Time signature\n```", vc(df, "time_signature"), "```",
             "\n## Progression complexity\n```", vc(df, "progression_complexity"), "```",
             f"\n## Numeric summary\n```",
             df[[c for c in ("duration_sec", "bpm", "note_density", "polyphony_density",
                 "pitch_class_entropy", "velocity_dynamic_range", "n_unique_chords")
                 if c in df.columns]].describe().to_string(), "```\n"]
    open(os.path.join(C.STATS, "corpus_statistics.md"), "w").write("\n".join(lines))

    card = f"""# Dataset Card — MIDIS_ALL_REAL

## Summary
{len(df):,} unique MIDI files (MD5-deduped from ~935k inputs), ~{total_hours:,.0f} hours,
richly annotated (key, harmony, instrumentation, complexity, near-dup song_id, splits).

## Sources
{src.to_string()}

## Intended uses
Symbolic-music ML (generation, MIR, similarity search), curated training pools,
song-level train/val/test splits (no arrangement leakage).

## How it was built
TMIDIX parsing; features derived from the LAMD-style META_DATA records plus one
unified parse pass; numpy Krumhansl-Schmuckler key detection; cosine-NN near-dup
clustering with mutual-kNN + oversized-cluster guards.

## Known limitations
- **Source tags are noisy** (provenance was reconstructed; verify before trusting).
- **Genre is heuristic and mostly `unknown`** — LAMD/Lakh/bitmidi filenames are MD5
  hashes with no usable metadata. Real names exist only for ~38k files.
- **Key detection is statistical** (validated against music21 on a 2k sample, not perfect).
- **Near-dup recall is conservative** — precision favored so splits don't leak; some
  true arrangements remain unlinked (Level-2 melody-contour matching is a stretch goal).
"""
    open(os.path.join(C.STATS, "dataset_card.md"), "w").write(card)
    C.log(f"stats written -> {C.STATS}/corpus_statistics.md + dataset_card.md", "stats.log")
    C.progress("PHASE8", f"hours={total_hours:.0f}")


if __name__ == "__main__":
    main()
