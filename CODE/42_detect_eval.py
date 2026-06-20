#!/usr/bin/env python3
"""
42_detect_eval.py — score detectors against human ear-labels.

This is the scorecard. You ear-check songs and record the truth in
_work/ground_truth.json; this compares the OLD catalog values and the NEW v2
detectors against that truth and prints accuracy. No more "vibes" — a number.

ground_truth.json format (one entry per md5):
  { "<md5>": { "bpm": 129, "key": "C major", "time_sig": "4/4",
               "feel": "free notes", "confirmed": true } }
Leave a field null/absent if you didn't judge it. Set confirmed=true once you've
actually listened. Only confirmed entries are scored.

BPM scoring is octave-aware: an exact match, or a clean 2x/3x/0.5x relationship,
is reported separately (half/double-time is a notation choice, not a wrong read).

Run:  python3 CODE/42_detect_eval.py
"""
import json, pathlib
import pandas as pd, numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
GT   = ROOT / "_work" / "ground_truth.json"

def bpm_match(pred, truth, tol=0.03):
    if pred is None or truth is None: return None
    pred, truth = float(pred), float(truth)
    if truth == 0: return None
    if abs(pred - truth) / truth <= tol: return "exact"
    for r in (2, 3, 0.5, 1/3, 4, 0.25):
        if abs(pred - truth * r) / truth <= tol: return f"x{r:g}"
    return "miss"

def key_norm(s):
    return s.strip().lower().replace("-", "b") if isinstance(s, str) else None

def main():
    if not GT.exists():
        print(f"no ground truth yet — create {GT}"); return
    gt = json.load(open(GT))
    cat = pd.read_parquet(ROOT/"catalog/metadata.parquet",
                          columns=["md5","bpm","key","mode","time_signature","key_confidence"]).set_index("md5")
    tm  = pd.read_parquet(ROOT/"_work/tempo_meter_v2.parquet").set_index("md5") if (ROOT/"_work/tempo_meter_v2.parquet").exists() else None
    kv  = pd.read_parquet(ROOT/"_work/key_v2.parquet").set_index("md5") if (ROOT/"_work/key_v2.parquet").exists() else None

    confirmed = {k: v for k, v in gt.items() if v.get("confirmed")}
    print(f"ground truth: {len(gt)} entries, {len(confirmed)} confirmed\n")
    if not confirmed:
        print("nothing confirmed yet — ear-check songs and set confirmed:true"); return

    tally = {"bpm_old":[], "bpm_v2":[], "key_old":[], "key_v2":[], "ts_old":[], "ts_v2":[]}
    for md5, lab in confirmed.items():
        c = cat.loc[md5] if md5 in cat.index else None
        print(f"=== {md5[:8]}  truth: bpm={lab.get('bpm')} key={lab.get('key')} ts={lab.get('time_sig')}")
        # BPM
        if lab.get("bpm") and c is not None:
            o = bpm_match(c["bpm"], lab["bpm"]); tally["bpm_old"].append(o=="exact")
            print(f"    BPM old={c['bpm']:<7} -> {o}")
            if tm is not None and md5 in tm.index:
                v = bpm_match(tm.loc[md5,"bpm_v2"], lab["bpm"]); tally["bpm_v2"].append(v=="exact")
                print(f"    BPM v2 ={tm.loc[md5,'bpm_v2']:<7} -> {v}")
        # KEY
        if lab.get("key") and c is not None:
            o = key_norm(c["key"])==key_norm(lab["key"]); tally["key_old"].append(o)
            print(f"    KEY old={c['key']} (conf {c['key_confidence']:.2f}) -> {'OK' if o else 'miss'}")
            if kv is not None and md5 in kv.index:
                v = key_norm(kv.loc[md5,"key_v2"])==key_norm(lab["key"]); tally["key_v2"].append(v)
                print(f"    KEY v2 ={kv.loc[md5,'key_v2']} (corr {kv.loc[md5,'key_corr']:.2f}) -> {'OK' if v else 'miss'}")
        # TIME SIG
        if lab.get("time_sig") and c is not None:
            o = str(c["time_signature"])==lab["time_sig"]; tally["ts_old"].append(o)
            print(f"    TS  old={c['time_signature']} -> {'OK' if o else 'miss'}")
            if tm is not None and md5 in tm.index:
                tsf = tm.loc[md5,"ts_final"] if "ts_final" in tm.columns else tm.loc[md5,"ts_v2"]
                v = str(tsf)==lab["time_sig"]; tally["ts_v2"].append(v)
                print(f"    TS  v2 ={tsf} (file={tm.loc[md5,'ts_v2']}) -> {'OK' if v else 'miss'}")
        print()

    def pct(x): return f"{np.mean(x)*100:.0f}% ({sum(x)}/{len(x)})" if x else "—"
    print("==== ACCURACY (confirmed songs) ====")
    print(f"  BPM : old {pct(tally['bpm_old'])}   ->   v2 {pct(tally['bpm_v2'])}")
    print(f"  KEY : old {pct(tally['key_old'])}   ->   v2 {pct(tally['key_v2'])}")
    print(f"  TS  : old {pct(tally['ts_old'])}   ->   v2 {pct(tally['ts_v2'])}")

if __name__ == "__main__":
    main()
