#!/usr/bin/env python3
"""34_drum_corner_audio.py — Render top drum-corner songs to WAV."""
import sqlite3, os, subprocess
import pandas as pd

ROOT = "/mnt/2FAST/MIDIS_ALL_REAL"
SF = "/home/t/datasets/LAMD/CODE/fluidsynth-master/sf2/VintageDreamsWaves-v2.sf2"
CORNERS = os.path.join(ROOT, "_work/drum_emptyspace/drum_corners.csv")
OUT_DIR = os.path.join(ROOT, "_work/drum_emptyspace/corner_audio")
os.makedirs(OUT_DIR, exist_ok=True)

def get_path(md5, con):
    res = con.execute("SELECT stored_path FROM manifest WHERE md5=?", (md5,)).fetchone()
    return res[0] if res else None

def main():
    if not os.path.exists(CORNERS):
        print(f"MISSING {CORNERS}")
        return
        
    df = pd.read_csv(CORNERS).head(15)
    con = sqlite3.connect(os.path.join(ROOT, "catalog/catalog.sqlite"))
    
    for i, row in df.iterrows():
        md5 = row['songs'].split(';')[0]
        mpath = get_path(md5, con)
        if not mpath:
            print(f"MISSING path for {md5}")
            continue
            
        out_wav = os.path.join(OUT_DIR, f"drum_corner_{i:02d}_{md5[:12]}.wav")
        if os.path.exists(out_wav):
            continue
            
        print(f"[{i:02d}] Rendering {md5[:12]} ({row['caption']})...")
        # Render first 30 seconds to be fast
        subprocess.run([
            "fluidsynth", "-ni", "-F", out_wav, "-T", "wav", "-r", "16000", SF, mpath
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    con.close()
    print(f"Done. WAVs in {OUT_DIR}")

if __name__ == "__main__":
    main()
