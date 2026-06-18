# HANDOFF — catalog merge → vectorize  (for the phone/`work` Claude)

> ## ✅ COMPLETE — ALL 4 STEPS DONE (2026-06-17 ~15:02). Nothing left to do here.
> STEP 1 DQ checks passed, STEP 2 checkpoint taken, STEP 3 merge → catalog 148 cols,
> STEP 4 → `CODE/26_signature_extend.py` built `signatures_ext.npy` (N×74) + refit
> `knn_cosine.pkl`. The corpus is **vectorized / experiment-ready**. This file is kept
> as a record of the plan; **the live source of truth is STATE.md** (CURRENT STATUS +
> top session-log entry). Don't re-run these steps blind.

Written by the desktop Claude on 2026-06-17. Do these **in order**. Don't skip the
checks or the checkpoint. Convention (per STATE.md): **back up before any rebuild,
non-destructive column adds only, verify parquet ⇄ sqlite.**

## Context (where we are)
- All 4 feature tables are DONE, ~462k rows each, in `_work/`:
  `rhythm_features.parquet` (22), `melody_features.parquet` (24),
  `harmony_features.parquet` (25), `seq_features.parquet` (21).
- Catalog = `catalog/metadata.parquet` + `catalog/catalog.sqlite` — **80 cols, 459,805 rows**, keyed on `md5`.
- Goal of this run: merge features onto the catalog, then **extend the 36-D signature
  + rebuild kNN** → every song becomes a point in rhythm+melody+harmony+pitch space
  ("vectorized / experiment-ready"). The current `SIGNATURES_DATA/signatures.npy` is
  **N×36 with ZERO rhythm** — that's the gap we're closing.

---

## STANDING RULE — ping the phone on anything long-running
The desktop set up phone notifications on 2026-06-17 (ntfy → iPhone). **Use them for
any step that takes more than a couple of minutes** (e.g. the STEP 4 kNN refit over
~460k rows can be slow). The user wants to walk away and get buzzed when things finish.

- **Ping anytime:**  `notify "message" "title"`  (e.g. end a long script with it)
- **Fire-and-forget watcher** (pings when matching processes exit):
  ```bash
  setsid nohup notify-when-done 'python3 .*26_signature.*\.py' 'Signature rebuild' \
      >/tmp/notify-sig.log 2>&1 </dev/null &
  ```
- Both are on PATH (`~/bin/notify`, `~/bin/notify-when-done`). Topic is baked in
  (`ntfy.sh/lab-ae3or56xum`); the user's phone is subscribed in the **ntfy** app.
- So: **before kicking off STEP 3 or STEP 4, launch a `notify-when-done` watcher on it**
  (or append `notify "... done" "..."` to the command), then the phone gets pinged.

Also relevant to remote work: there is a shared tmux session **`work`** (green
`📱 PHONE-SYNCED` bar) that the desktop and the iPhone (Termius/Mosh over Tailscale)
both attach to — that's how the user follows along from the phone. Don't kill it.

---

## STEP 1 — Data-quality checks (must pass BEFORE merging)
Run and eyeball. We're checking the 4 feature tables are complete, sane, and joinable.

```bash
cd /mnt/2FAST/MIDIS_ALL_REAL
python3 - <<'PY'
import pandas as pd, numpy as np, pyarrow.parquet as pq
cat = pd.read_parquet('catalog/metadata.parquet', columns=['md5'])
cat_md5 = set(cat.md5)
print(f"catalog: {len(cat):,} rows, {cat.md5.nunique():,} unique md5")
srcs = {
 'rhythm':'_work/rhythm_features.parquet',
 'melody':'_work/melody_features.parquet',
 'harmony':'_work/harmony_features.parquet',
 'seq':'_work/seq_features.parquet',
}
for name,p in srcs.items():
    d = pd.read_parquet(p)
    dup = d.md5.duplicated().sum()
    cover = len(set(d.md5) & cat_md5)
    nan_frac = d.drop(columns=[c for c in ('md5','song_id') if c in d]).isna().mean().mean()
    errcol = [c for c in d.columns if 'error' in c.lower()]
    nerr = int(d[errcol[0]].notna().sum()) if errcol else 0
    okcol = [c for c in d.columns if c.endswith('_ok')]
    nok  = int(d[okcol[0]].sum()) if okcol else len(d)
    print(f"\n{name:8} rows={len(d):,} uniq_md5={d.md5.nunique():,} dup_md5={dup} "
          f"covers_catalog={cover:,}/{len(cat_md5):,} ({100*cover/len(cat_md5):.1f}%)")
    print(f"         mean NaN frac={nan_frac:.3f}  errors={nerr}  ok_rows={nok:,}")
    # value sanity: any inf? any ratio col outside [0,1.01]?
    num = d.select_dtypes('number')
    infs = int(np.isinf(num.to_numpy()).sum())
    ratios = [c for c in num.columns if 'ratio' in c]
    bad_ratio = {c:(float(num[c].min()),float(num[c].max())) for c in ratios
                 if num[c].min()<-0.01 or num[c].max()>1.01}
    print(f"         infs={infs}  out-of-range ratio cols={bad_ratio if bad_ratio else 'none'}")
PY
```
**PASS criteria:** no duplicate md5; coverage ~99%+ of the catalog (a few % missing is
fine — they'll be NaN after the left-merge); error counts near zero; NaN fraction low;
zero infs; ratio columns within [0,1]. If a table looks wrong, STOP and investigate —
do not merge bad data into the catalog.

## STEP 2 — Checkpoint (explicit, before touching the catalog)
`23` makes its own backup, but take a clean manual snapshot first.

```bash
cd /mnt/2FAST/MIDIS_ALL_REAL
TS=$(date +%Y%m%d_%H%M%S)
mkdir -p catalog/checkpoints
cp -v catalog/catalog.sqlite   catalog/checkpoints/catalog_${TS}_pre23.sqlite
cp -v catalog/metadata.parquet catalog/checkpoints/metadata_${TS}_pre23.parquet
ls -la catalog/checkpoints/ | tail -4
# optional: also git-snapshot the code/state
# save "pre-23 catalog merge checkpoint"
```

## STEP 3 — Run the merge
```bash
cd /mnt/2FAST/MIDIS_ALL_REAL
python3 CODE/23_catalog_merge.py 2>&1 | tee _logs/23_catalog_merge_$(date +%Y%m%d_%H%M%S).log
```
**Verify after:** log shows columns went **80 → ~148**, **rows still 459,805**, and the
script's own `parquet ⇄ sqlite` assertions passed (no "row count changed!" / no failed
verify queries). Spot-check:
```bash
python3 -c "import pandas as pd; m=pd.read_parquet('catalog/metadata.parquet'); print(m.shape); print([c for c in m.columns if any(k in c for k in ('swing','mel_','chord','syncop'))][:12])"
```

## STEP 4 — Extend signature + rebuild kNN  (the "vectorized" finish line)
No script exists for this yet — **you will write it** (suggest `CODE/26_signature_extend.py`).
It must:
1. **Back up first:** copy `SIGNATURES_DATA/signatures.npy` and
   `SIGNATURES_DATA/knn_cosine.pkl` to timestamped `.bak` (never overwrite blind).
2. Load `SIGNATURES_DATA/signatures.npy` (N×36) + `signatures_md5.txt` (row→md5 order).
3. Pull the new **rhythm + melody + harmony (+ structure/tempo)** feature columns from
   the merged `catalog/metadata.parquet`, **reindexed to the signatures_md5 row order** by md5.
4. **Handle NaN** (tracks missing a feature): median-impute per column (and/or keep a mask);
   note how many were imputed.
5. **Scale per block** (z-score or L2 each pillar) so cosine distance isn't dominated by
   raw magnitudes. Consider **up-weighting rhythm** — it's the stated top priority.
6. **Concatenate** → new wider matrix `signatures_ext.npy` (KEEP the original 36-D file too).
7. **Refit** `sklearn.neighbors.NearestNeighbors(metric='cosine')` on the extended matrix →
   write `SIGNATURES_DATA/knn_cosine.pkl` (old one already backed up in step 1).
8. **Sanity check:** pick a few known tracks, print nearest neighbors, confirm they're
   musically sensible (and that rhythm now influences neighbors, not just pitch).

**Result:** every song is a point in the extended (pitch+harmony+melody+**rhythm**) space
→ kNN + the "empty-space hunt" now cover time-feel. That is "vectorized / experiment-ready"
— the finish line in STATE.md.

---
When done, update STATE.md's Session Log (catalog now ~148 cols; signature extended to
N×K; kNN rebuilt) per the standing convention.
