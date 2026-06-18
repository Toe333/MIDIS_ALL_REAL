#!/bin/bash
# Waits for metadata to finish, then runs search self-test + final verification.
set -u
R=/mnt/2FAST/MIDIS_ALL_REAL
REP=$R/catalog/FINAL_REPORT.txt

echo "[finalize] waiting for metadata..."
while [ ! -f $R/catalog/_meta_done ]; do sleep 20; done

{
echo "================ MIDIS_ALL_REAL — FINAL REPORT ================"
date
echo
echo "## Metadata run tail"
grep -E "DONE meta|metadata.parquet|catalog.sqlite" $R/catalog/make_metadata.log

echo
echo "## VERIFY: counts line up"
echo -n "stored MIDIs:        "; find $R/MIDIs -type f -name '*.mid' | wc -l
echo -n "manifest unique md5: "; python3 -c "import pandas as pd;print(len(pd.read_parquet('$R/catalog/master_manifest.parquet')))"
echo -n "metadata.parquet rows:"; python3 -c "import pandas as pd;print(len(pd.read_parquet('$R/catalog/metadata.parquet')))"
echo -n "symlinks (want 0):   "; find $R/MIDIs -type l | wc -l
echo -n "META_DATA chunks:    "; ls $R/META_DATA/ | wc -l
echo -n "meta errors logged:  "; wc -l < $R/catalog/meta_errors.log

echo
echo "## VERIFY: sqlite catalog view"
sqlite3 $R/catalog/catalog.sqlite "SELECT count(*) AS files_in_catalog FROM catalog;"
echo "-- tempo/meter/drums sample query (120-130 BPM, 4/4, drums):"
sqlite3 $R/catalog/catalog.sqlite "SELECT count(*) FROM catalog WHERE bpm BETWEEN 120 AND 130 AND time_signature='4/4' AND has_drums=1;"
echo "-- duration percentiles (sec):"
sqlite3 $R/catalog/catalog.sqlite "SELECT round(min(duration_sec),1), round(avg(duration_sec),1), round(max(duration_sec),1) FROM catalog;"
echo "-- has_drums split:"
sqlite3 $R/catalog/catalog.sqlite "SELECT has_drums, count(*) FROM catalog GROUP BY has_drums;"

echo
echo "## VERIFY: similarity search self-test"
QMD5=$(python3 -c "import pandas as pd;m=pd.read_parquet('$R/catalog/master_manifest.parquet');print(m[m.n_copies>=2].iloc[0].md5)")
echo "query md5: $QMD5"
python3 $R/CODE/04_search.py --out-root $R --md5 $QMD5 --top 5 2>/dev/null

echo
echo "================ DONE ================"
} > $REP 2>&1

touch $R/catalog/_all_done
echo "[finalize] wrote $REP"
