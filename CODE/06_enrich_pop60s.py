#!/usr/bin/env python3
"""06_enrich_pop60s.py — first-pass genre/era enrichment for MIDIS_ALL_REAL.

Builds a "1960s catchy pop, like Incense and Peppermints" relevance layer over ALL
deduped songs, blending three signals:

  A. pop_sound_score  -- pitch-histogram similarity (LAMD same_pitches_ratio, the exact
                         metric CODE/04_search.py uses) to a curated seed set of known
                         60s catchy-pop songs. Covers every file. Numpy-vectorized.
  B. feature_gate     -- from metadata.parquet: real song length, not pure-drum, sane note
                         count, soft pop tempo band.
  C. era_prior        -- soft boost when provenance/filename says 1960s, or artist is a
                         known 60s-pop act.

  pop60s_score = pop_sound_score * feature_gate * era_prior

Additive only: writes new files under catalog/ and leaves everything else untouched.
Outputs: catalog/enrichment_pop60s.parquet, catalog/enrichment.sqlite (view `pop60s`),
         catalog/pop60s_like_incense.csv
"""
import os, sys, glob, pickle, re, sqlite3
from collections import Counter
import numpy as np
import pandas as pd

ROOT = "/mnt/2FAST/MIDIS_ALL_REAL"
SEED_INCENSE = ["09c286990f7146f3bee597f02838b24d",
                "76b00b0eaaefb7beabf21f50ad09c9bb",
                "f44fc5ce67b42098c6fa0bfb277529c6"]

# Artists in the named 1960s pool that are NOT "catchy pop like Incense" -> excluded from seeds.
# (jazz/lounge instrumentals, pure-instrumental surf, blues/hard-rock, country, crooners, chanson)
DENY = [
 "vince guaraldi","herb alpert","tijuana brass","glenn miller","leroy anderson","gabor szabo",
 "king curtis","james last","henry mancini","paul mauriat","floyd cramer","chet atkins",
 "bert kaempfert","neal hefti","oliver nelson","herbie hancock","hugh masekela","louis armstrong",
 "elmer bernstein","los indios","percusin","astrud gilberto","os cariocas","mar-keys","bar-kays",
 "booker t","spotnicks","the ventures","surfaris","chantay","jorgen ingmann",
 "led zeppelin","b.b. king","musselwhite","blue cheer","iron butterfly","grand funk","steppenwolf",
 "john mayall","jimi hendrix","pink floyd","blind faith","joe cocker","rare earth","lee michaels",
 "beautiful day","ultimate spinach",
 "johnny cash","faron young","connie smith","jack greene","bobby bare","willie nelson","ned miller",
 "george hamilton","jimmy dean","jerry jeff walker","jack nitzsche",
 "tony bennett","frank sinatra","perry como","engelbert","lettermen","trini lopez","etta james",
 "doris duke","tyrone davis",
 "gainsbourg","dutronc","hallyday","joe dassin","fugain","aufray","hardy","de andr","serrat",
 "bobby solo","equipe 84","joan manuel",
]

def denied(artist):
    a = artist.lower()
    return any(d in a for d in DENY)

# ---- artist -> known-60s-pop boost (for era_prior on UNnamed files we can't use this; it only
#      helps named ones, which is fine -- era_prior is a soft multiplier) ----
def is_60s_pop_artist(artist):
    return artist and not denied(artist)

# ---------------- load signatures (md5 -> distinct pitch set) ----------------
def load_signatures():
    sig = {}
    for fp in sorted(glob.glob(os.path.join(ROOT, "META_DATA", "META_DATA_*.pickle"))):
        with open(fp, "rb") as fh:
            for entry in pickle.load(fh):
                try:
                    counts = entry[1][10][1]           # [[pitch,count],...]
                    pitches = [int(p) for p, _ in counts]
                    if pitches:
                        sig[entry[0]] = pitches
                except Exception:
                    continue
    return sig

# pitch value range: non-drum 0..127, drums 128..255; seed transposition shifts non-drum by -6..5
DIM = 300
OFF = 16   # so transposed values (min -6) stay >= 0
def vec_of(pitches):
    v = np.zeros(DIM, dtype=np.float32)
    for p in pitches:
        idx = p + OFF
        if 0 <= idx < DIM:
            v[idx] = 1.0
    return v

def seed_transpositions(pitches):
    """Replicate query_pitches transposition: shift non-drum (<128) by i in -6..5, keep drums."""
    out = []
    for i in range(-6, 6):
        shifted = [(p + i if p < 128 else p) for p in pitches]
        out.append(frozenset(shifted))
    return out

def main():
    print("[1/6] loading signatures ...", flush=True)
    sig = load_signatures()
    md5s = list(sig.keys())
    print(f"      signatures: {len(md5s)}", flush=True)

    print("[2/6] manifest + named-artist map ...", flush=True)
    man = pd.read_parquet(f"{ROOT}/catalog/master_manifest.parquet")
    paths_map = dict(zip(man.md5, man.original_paths))
    def best_named(md5):
        for p in paths_map.get(md5, []):
            b = os.path.basename(str(p))
            if "__" in b:
                parts = b.replace(".mid", "").split("__")
                return parts[0].replace("_", " ").strip(), (parts[1].replace("_", " ").strip() if len(parts) > 1 else "")
        return "", ""
    def pool_1960s(md5):
        return any("/MIDI_LIBRARY/1960smidi/" in str(p) for p in paths_map.get(md5, []))
    def year_token(md5):
        return any(re.search(r"196\d", os.path.basename(str(p))) for p in paths_map.get(md5, []))

    # ---------------- seed set ----------------
    print("[3/6] building seed set ...", flush=True)
    seeds = set(SEED_INCENSE)
    for md5 in md5s:
        if pool_1960s(md5):
            a, _ = best_named(md5)
            if a and not denied(a):
                seeds.add(md5)
    seeds = [s for s in seeds if s in sig]
    print(f"      seeds: {len(seeds)}", flush=True)

    # unique transposed seed vectors
    seed_sets = set()
    for s in seeds:
        for fs in seed_transpositions(sig[s]):
            seed_sets.add(fs)
    seed_list = [np.array(sorted(fs), dtype=np.int32) for fs in seed_sets]
    S = len(seed_sets)
    seedM = np.zeros((S, DIM), dtype=np.float32)
    seed_len = np.zeros(S, dtype=np.float32)
    for j, arr in enumerate(seed_list):
        idx = arr + OFF
        idx = idx[(idx >= 0) & (idx < DIM)]
        seedM[j, idx] = 1.0
        seed_len[j] = len(arr)
    print(f"      unique seed vectors: {S}", flush=True)

    # ---------------- score all files (vectorized, chunked) ----------------
    print("[4/6] scoring all files vs seeds ...", flush=True)
    fileM = np.zeros((len(md5s), DIM), dtype=np.float32)
    file_len = np.zeros(len(md5s), dtype=np.float32)
    for i, md5 in enumerate(md5s):
        ps = sig[md5]
        idx = np.array(ps, dtype=np.int32) + OFF
        idx = idx[(idx >= 0) & (idx < DIM)]
        fileM[i, idx] = 1.0
        file_len[i] = len(set(ps))
    seedM_T = seedM.T  # (DIM, S)
    pop_sound = np.zeros(len(md5s), dtype=np.float32)
    CH = 8000
    for a in range(0, len(md5s), CH):
        b = min(a + CH, len(md5s))
        inter = fileM[a:b] @ seedM_T                       # (chunk, S) intersection counts
        fl = file_len[a:b][:, None]                        # (chunk,1)
        denom = np.maximum(fl, seed_len[None, :])          # (chunk,S)
        full = inter == seed_len[None, :]                  # seed fully contained
        ratio = np.where(full, inter / np.maximum(fl, 1), inter / np.maximum(denom, 1))
        pop_sound[a:b] = ratio.max(axis=1)
        if (a // CH) % 5 == 0:
            print(f"      {b}/{len(md5s)}", flush=True)

    # ---------------- feature gate + era prior ----------------
    print("[5/6] feature gate + era prior ...", flush=True)
    md = pd.read_parquet(f"{ROOT}/catalog/metadata.parquet").set_index("md5")
    df = pd.DataFrame({"md5": md5s, "pop_sound_score": pop_sound, "file_len": file_len})
    df = df.merge(md, left_on="md5", right_index=True, how="left")

    dur = df["duration_sec"].fillna(0)
    notes = df["n_notes"].fillna(0)
    drums = df["has_drums"].fillna(0)
    bpm = df["bpm"].fillna(0)
    npatch = df["n_distinct_patches"].fillna(0)
    # hard-ish gate -> 0/1 with soft tempo
    gate = ((dur.between(60, 360)) & (notes.between(60, 8000)) & (npatch >= 1)).astype(float)
    pure_drum = ((df["midi_patches"].fillna("") == "") & (drums == 1))
    gate = gate * (~pure_drum).astype(float)
    tempo_soft = np.where(bpm.between(70, 160), 1.0, np.where(bpm.between(50, 185), 0.6, 0.3))
    feature_gate = gate * tempo_soft
    df["feature_gate"] = feature_gate

    artist_title = [best_named(m) for m in df["md5"]]
    df["artist"] = [a for a, _ in artist_title]
    df["title"] = [t for _, t in artist_title]
    in_pool = df["md5"].map(pool_1960s)
    has_year = df["md5"].map(year_token)
    known_artist = df["artist"].map(lambda a: bool(a) and not denied(a))
    era_prior = np.where(in_pool | known_artist, 1.5, np.where(has_year, 1.2, 1.0))
    df["era_hint"] = np.where(in_pool, "1960s_pool", np.where(has_year, "year_token", np.where(known_artist, "named_artist", "")))
    df["era_prior"] = era_prior

    df["pop60s_score"] = df["pop_sound_score"] * df["feature_gate"] * df["era_prior"]

    # ---------------- write outputs ----------------
    print("[6/6] writing outputs ...", flush=True)
    out = df[["md5", "artist", "title", "pop_sound_score", "feature_gate", "era_hint",
              "era_prior", "pop60s_score", "bpm", "duration_sec", "has_drums", "midi_patches"]].copy()
    out = out.sort_values("pop60s_score", ascending=False)
    out.to_parquet(f"{ROOT}/catalog/enrichment_pop60s.parquet", index=False)

    con = sqlite3.connect(f"{ROOT}/catalog/enrichment.sqlite")
    out.to_sql("pop60s_scores", con, if_exists="replace", index=False)
    con.execute("DROP VIEW IF EXISTS pop60s")
    con.execute("""CREATE VIEW pop60s AS SELECT md5,artist,title,pop60s_score,pop_sound_score,
                   feature_gate,era_hint,bpm,duration_sec,has_drums,midi_patches
                   FROM pop60s_scores ORDER BY pop60s_score DESC""")
    con.commit(); con.close()

    top = out.head(500).copy()
    top.to_csv(f"{ROOT}/catalog/pop60s_like_incense.csv", index=False)
    print("DONE. seeds=%d  unique_seed_vecs=%d  scored=%d" % (len(seeds), S, len(out)))
    print("wrote: enrichment_pop60s.parquet, enrichment.sqlite (view pop60s), pop60s_like_incense.csv")

if __name__ == "__main__":
    main()
