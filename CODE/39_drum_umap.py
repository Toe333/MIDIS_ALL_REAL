#!/usr/bin/env python3
"""
39_drum_umap.py — build a DRUM-FEEL 2-D UMAP from the 72-D drum-only signature.

Companion to the 74-D pitch/harmony map: this one positions songs by GROOVE/drum
pattern, so rhythmically-similar songs sit together. Embeds only drum-bearing rows
(311k; drumless are all-zero and excluded). Output aligns to md5 for 28_mapserver.

  .venv/bin/python CODE/39_drum_umap.py
Writes _work/emptyspace/umap2_drums.parquet (md5, x, y).
"""
import time, numpy as np, pandas as pd, umap

t0 = time.time()
X = np.load("SIGNATURES_DATA/signatures_drums.npy").astype(np.float32)
md5 = np.array(open("SIGNATURES_DATA/signatures_md5.txt").read().split())
assert len(md5) == X.shape[0], (len(md5), X.shape)

nz = np.abs(X).sum(1) > 0          # drum-bearing only
Xd, md5d = X[nz], md5[nz]
print(f"[drum-umap] fitting {Xd.shape} (drum-bearing of {X.shape[0]:,}) ...", flush=True)

xy = umap.UMAP(n_neighbors=25, min_dist=0.15, metric="cosine",
               random_state=42, verbose=True).fit_transform(Xd)

out = pd.DataFrame({"md5": md5d, "x": xy[:, 0].astype("float32"),
                    "y": xy[:, 1].astype("float32")})
out.to_parquet("_work/emptyspace/umap2_drums.parquet", index=False)
print(f"[drum-umap] wrote _work/emptyspace/umap2_drums.parquet "
      f"({len(out):,} pts) in {time.time()-t0:.0f}s")
