#!/usr/bin/env python3
"""15_catalog.py — Phase 6 merge everything into the catalog.

Left-joins (on md5): metadata.parquet (orig 17) + scan.parquet (parse features +
integrity) + features_pickle.parquet + chords_summary.parquet + clusters.parquet
+ provenance.parquet  ->  catalog/metadata.parquet (rebuilt) + catalog/catalog.sqlite.

Checkpoints the old sqlite first. Safe to re-run.
Usage:  python3 CODE/15_catalog.py
"""
import os, sys, sqlite3, shutil, time
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C


def load(path, cols=None):
    return pd.read_parquet(path, columns=cols) if os.path.exists(path) else None


# the 17 original build-03 columns; everything else is enrichment we re-derive
BASE17 = ["md5", "n_tracks", "n_notes", "n_score_events", "duration_sec", "bpm",
          "time_signature", "n_distinct_patches", "midi_patches", "has_drums",
          "pitch_min", "pitch_max", "n_distinct_chords", "avg_vel",
          "tempo_change_count", "text_events_count", "lyric_events_count"]


def main():
    # Idempotency: build from an immutable snapshot of the ORIGINAL 17 columns, not
    # from our own enriched output. Otherwise re-running compounds (nulled columns
    # get re-read as base, flag counts drift). Snapshot once, always start clean.
    base_path = os.path.join(C.CATALOG, "metadata_base.parquet")
    if not os.path.exists(base_path):
        cur = load(os.path.join(C.CATALOG, "metadata.parquet"))
        if cur is None:
            sys.exit("metadata.parquet missing and no base snapshot")
        have = [c for c in BASE17 if c in cur.columns]
        C.write_parquet_atomic(cur[have], base_path)
        C.log(f"  wrote immutable base snapshot ({len(have)} cols) -> {base_path}", "catalog.log")
    base = load(base_path)
    C.log(f"base metadata: {len(base)} rows x {base.shape[1]} cols (pristine)", "catalog.log")

    parts = {
        "scan":     os.path.join(C.WORK, "scan.parquet"),
        "features": os.path.join(C.WORK, "features_pickle.parquet"),
        "chords":   os.path.join(C.ROOT, "CHORDS_DATA", "chords_summary.parquet"),
        "clusters": os.path.join(C.WORK, "clusters.parquet"),
        "prov":     os.path.join(C.WORK, "provenance.parquet"),
    }
    df = base
    for name, p in parts.items():
        sub = load(p)
        if sub is None:
            C.log(f"  WARN: {name} ({p}) missing — skipping", "catalog.log")
            continue
        # avoid duplicate-column collisions (keep base's originals)
        dup = [c for c in sub.columns if c in df.columns and c != "md5"]
        sub = sub.drop(columns=dup)
        df = df.merge(sub, on="md5", how="left")
        C.log(f"  merged {name}: +{len(sub.columns)-1} cols -> {df.shape[1]} total", "catalog.log")

    # derive parse_status if not present
    if "parse_status" not in df.columns:
        df["parse_status"] = "ok"
    df["is_quarantined"] = df.get("is_quarantined", 0)
    df["is_quarantined"] = df["is_quarantined"].fillna(0).astype(int)

    # ---- CAVEAT FIX 2: quality flag + null garbage tempo/density outliers ----
    # A handful of files have corrupt tempo events -> near-zero duration ->
    # impossible note_density (millions/sec). Keep the file, but flag it and null
    # the unreliable numeric columns so stats/training are not poisoned.
    import numpy as np
    def s(col):
        return df[col] if col in df.columns else pd.Series(np.nan, index=df.index)
    absurd = ((s("note_density") > 1000) | (s("polyphony_density") > 200) |
              (s("tempo_stability") > 100000) | (s("note_density_absurd") == True))
    absurd = absurd.fillna(False)
    df["quality_flag"] = np.where(absurd, "absurd_density", "ok")
    for c in ("note_density", "polyphony_density", "tempo_stability"):
        if c in df.columns:
            df.loc[absurd, c] = np.nan
    C.log(f"  quality_flag: {int(absurd.sum())} files flagged absurd_density "
          f"(garbage tempo/duration); their density columns nulled", "catalog.log")

    # rebuild parquet
    out_pq = os.path.join(C.CATALOG, "metadata.parquet")
    C.write_parquet_atomic(df, out_pq)
    C.log(f"metadata.parquet rebuilt: {df.shape} -> {out_pq}", "catalog.log")

    # checkpoint + rebuild sqlite
    dbp = os.path.join(C.CATALOG, "catalog.sqlite")
    if os.path.exists(dbp):
        ck = os.path.join(C.CATALOG, "checkpoints", f"catalog_{time.strftime('%Y%m%d_%H%M%S')}.sqlite")
        shutil.copy2(dbp, ck)
        C.log(f"  checkpointed old sqlite -> {ck}", "catalog.log")
        os.remove(dbp)

    man = pd.read_parquet(os.path.join(C.CATALOG, "master_manifest.parquet"))
    for col in ("sources", "hosts", "original_paths"):
        if col in man.columns:
            man[col] = man[col].apply(lambda x: "\n".join(map(str, x)) if hasattr(x, "__iter__")
                                      and not isinstance(x, str) else x)
    # carry song_id/is_canonical onto manifest
    carry = df[["md5"] + [c for c in ("song_id", "is_canonical") if c in df.columns]]
    man = man.merge(carry, on="md5", how="left")

    # ---- CAVEAT FIX 1: wire quarantine into the manifest (full file-of-record).
    # Broken files have no metadata row, so flag them HERE where every file exists.
    scan = load(parts["scan"])
    man["is_quarantined"] = 0
    man["quarantine_reason"] = None
    if scan is not None:
        bad = scan[(~scan["parses"]) | (scan["is_zero_byte"]) | (scan["neg_ticks"])].copy()
        def reason(r):
            if r["is_zero_byte"]: return "zero_byte"
            if r["neg_ticks"]:    return "negative_ticks"
            return "parse_failed"
        bad["quarantine_reason"] = bad.apply(reason, axis=1)
        rmap = dict(zip(bad["md5"], bad["quarantine_reason"]))
        mask = man["md5"].isin(rmap)
        man.loc[mask, "is_quarantined"] = 1
        man.loc[mask, "quarantine_reason"] = man.loc[mask, "md5"].map(rmap)
        C.log(f"  manifest: marked {int(mask.sum())} files is_quarantined=1 "
              f"(reasons: {bad['quarantine_reason'].value_counts().to_dict()})", "catalog.log")

    # ---- self-documenting status for EVERY file (so no file is silently absent) ----
    # priority: quarantined > too_few_notes (policy reject, valid but <33 notes) > in_catalog
    in_catalog = set(df["md5"])
    too_few = set()
    mlog = os.path.join(C.CATALOG, "meta_errors.log")
    if os.path.exists(mlog):
        for line in open(mlog):
            if "too-few-notes" in line:
                p = line.split("\t", 1)[0]
                too_few.add(os.path.basename(p).split(".mid")[0])
    def file_status(md5, isq):
        if isq:            return "quarantined"
        if md5 in in_catalog: return "in_catalog"
        if md5 in too_few:    return "too_few_notes"
        return "no_metadata"
    man["file_status"] = [file_status(m, q) for m, q in zip(man["md5"], man["is_quarantined"])]
    C.log(f"  manifest file_status: {man['file_status'].value_counts().to_dict()}", "catalog.log")

    con = sqlite3.connect(dbp)
    df.to_sql("metadata", con, index=False)
    man.to_sql("manifest", con, index=False)
    con.execute("CREATE INDEX idx_meta_md5 ON metadata(md5)")
    con.execute("CREATE INDEX idx_man_md5 ON manifest(md5)")
    for col in ("bpm", "key", "mode", "genre_hint", "has_drums", "duration_sec",
                "song_id", "is_canonical"):
        if col in df.columns:
            con.execute(f"CREATE INDEX IF NOT EXISTS idx_meta_{col} ON metadata({col})")
    con.execute("""CREATE VIEW catalog AS SELECT m.*, n.sources, n.n_copies, n.stored_path
                   FROM metadata m JOIN manifest n ON m.md5=n.md5
                   WHERE COALESCE(m.is_quarantined,0)=0""")
    con.execute("""CREATE VIEW catalog_all AS SELECT m.*, n.sources, n.n_copies, n.stored_path
                   FROM metadata m JOIN manifest n ON m.md5=n.md5""")
    # convenience views (guarded by column existence)
    cols = set(df.columns)
    if "is_canonical" in cols:
        con.execute("CREATE VIEW v_canonical AS SELECT * FROM catalog WHERE is_canonical=1")
    if "has_lyrics" in cols:
        con.execute("CREATE VIEW v_with_lyrics AS SELECT * FROM catalog WHERE has_lyrics=1")
    if "genre_hint" in cols:
        con.execute("CREATE VIEW v_classical AS SELECT * FROM catalog WHERE genre_hint='classical'")
        con.execute("CREATE VIEW v_solo_piano AS SELECT * FROM catalog WHERE genre_hint='solo_piano'")
    if "has_drums" in cols:
        con.execute("CREATE VIEW v_no_drums AS SELECT * FROM catalog WHERE COALESCE(has_drums,0)=0")
    if "quality_flag" in cols:
        con.execute("CREATE INDEX idx_meta_quality ON metadata(quality_flag)")
        con.execute("CREATE VIEW v_clean AS SELECT * FROM catalog WHERE quality_flag='ok'")
    con.commit()
    con.close()
    C.log(f"catalog.sqlite rebuilt (tables metadata, manifest; views catalog, catalog_all, v_*) -> {dbp}",
          "catalog.log")
    C.progress("PHASE6", f"cols={df.shape[1]} rows={len(df)}")


if __name__ == "__main__":
    main()
