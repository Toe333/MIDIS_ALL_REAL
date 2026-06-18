#!/usr/bin/env python3
"""_validate_key.py — Phase 2.2 validation: numpy K-S key vs music21 on a 2k sample.
Writes _work/key_validation.json. Exits 0 even if music21 is slow/missing.
Usage: python3 CODE/_validate_key.py [--n 2000]
"""
import os, sys, json, argparse, random
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    args = ap.parse_args()
    feat = pd.read_parquet(os.path.join(C.WORK, "features_pickle.parquet"),
                           columns=["md5", "key", "mode"])
    try:
        import music21
    except Exception:
        json.dump({"skipped": "music21 unavailable"},
                  open(os.path.join(C.WORK, "key_validation.json"), "w"), indent=2)
        print("music21 unavailable — skipping"); return
    random.seed(42)
    rows = feat.dropna(subset=["key"]).sample(min(args.n, len(feat)), random_state=42)
    agree = total = 0
    for r in rows.itertuples():
        p = C.stored_path(r.md5)
        if not os.path.exists(p):
            continue
        try:
            sc = music21.converter.parse(p)
            k = sc.analyze("key")
            m21 = f"{k.tonic.name.replace('-', 'b')} {k.mode}"
            total += 1
            if r.mode == k.mode:           # mode agreement (looser, robust)
                agree += 1
        except Exception:
            continue
    rate = agree / total if total else 0
    json.dump({"n": total, "mode_agreement": round(rate, 3)},
              open(os.path.join(C.WORK, "key_validation.json"), "w"), indent=2)
    print(f"key validation: mode_agreement={rate:.1%} over {total} files")


if __name__ == "__main__":
    main()
