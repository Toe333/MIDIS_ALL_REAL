#!/usr/bin/env python3
"""02_make_dataset.py — build the deduplicated canonical MIDI store.

Pure full-content MD5 dedup (NO LAMD content filters: keeps all sizes,
keeps short files, keeps distinct arrangements). One REAL copy per unique
MD5 into MIDIs/<2hex>/<md5>.mid. Every original path is recorded so nothing
becomes unfindable.

Outputs:
  <out_root>/MIDIs/<2hex>/<md5>.mid     deduped real copies
  <out_root>/catalog/raw_rows.csv       one row per INPUT file (streamed, resumable)
  <out_root>/catalog/master_manifest.parquet   grouped by md5 (built at end)
  <out_root>/catalog/errors.log         skipped/unreadable files

Resumable: rerun skips input paths already present in raw_rows.csv.
"""
import os, sys, csv, hashlib, shutil, argparse, time
from multiprocessing import Pool

CSV_FIELDS = ["md5", "host", "source", "size", "original_path", "stored_path", "copied"]


def classify_source(path: str, host: str) -> str:
    p = path.lower()
    if host == "imac":
        return "imac_personal"
    if "lakh" in p or "/lmd" in p or "lmd_full" in p:
        return "lakh"
    if "/datasets/lamd/midis" in p or "/lamd/midis" in p:
        return "lamd"
    if "bitmidi" in p:
        return "bitmidi"
    if "maestro" in p:
        return "maestro"
    if "ragtime" in p:
        return "ragtime"
    if "/2fast/" in p:
        return "2fast_existing"
    return "lab_personal"


def md5_of(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# globals set per worker
G = {}


def init_worker(out_root, staging_prefix):
    G["midis"] = os.path.join(out_root, "MIDIs")
    G["staging_prefix"] = staging_prefix


def process(task):
    host, path = task
    try:
        size = os.path.getsize(path)
        if size == 0:
            return ("ERR", path, "zero-length")
        md5 = md5_of(path)
        bucket = md5[:2]
        dest_dir = os.path.join(G["midis"], bucket)
        dest = os.path.join(dest_dir, md5 + ".mid")
        copied = 0
        if not os.path.exists(dest):
            os.makedirs(dest_dir, exist_ok=True)
            tmp = dest + f".tmp.{os.getpid()}"
            shutil.copy2(path, tmp)
            os.replace(tmp, dest)  # atomic; last writer wins, identical bytes
            copied = 1
        # original path: strip staging prefix for imac provenance
        orig = path
        if host == "imac" and G["staging_prefix"] and path.startswith(G["staging_prefix"]):
            orig = path[len(G["staging_prefix"]):]
            if not orig.startswith("/"):
                orig = "/" + orig
        source = classify_source(orig, host)
        return ("OK", [md5, host, source, size, orig, dest, copied])
    except Exception as ex:
        return ("ERR", path, repr(ex)[:200])


def build_tasks(lists, host_for):
    tasks = []
    for lst in lists:
        host = host_for[lst]
        with open(lst) as f:
            for line in f:
                p = line.rstrip("\n")
                if p:
                    tasks.append((host, p))
    return tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--lab-list", required=True)
    ap.add_argument("--imac-list", required=True)
    ap.add_argument("--staging-prefix", required=True)
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    catalog = os.path.join(args.out_root, "catalog")
    os.makedirs(catalog, exist_ok=True)
    raw_csv = os.path.join(catalog, "raw_rows.csv")
    err_log = os.path.join(catalog, "errors.log")

    host_for = {args.lab_list: "lab", args.imac_list: "imac"}
    tasks = build_tasks([args.lab_list, args.imac_list], host_for)
    total = len(tasks)

    # Resume by INPUT path via a sidecar set file (one line per processed input).
    seen_input = os.path.join(catalog, "_seen_input.txt")
    seen = set()
    if os.path.exists(seen_input):
        with open(seen_input) as f:
            seen = set(l.rstrip("\n") for l in f)
    if seen:
        tasks = [t for t in tasks if t[1] not in seen]

    print(f"[{time.strftime('%H:%M:%S')}] total={total} remaining={len(tasks)} workers={args.workers}", flush=True)

    write_header = not os.path.exists(raw_csv)
    f_csv = open(raw_csv, "a", newline="")
    w = csv.writer(f_csv)
    if write_header:
        w.writerow(CSV_FIELDS)
    f_err = open(err_log, "a")
    f_seen = open(seen_input, "a")

    ok = errs = 0
    t0 = time.time()
    with Pool(args.workers, initializer=init_worker,
              initargs=(args.out_root, args.staging_prefix)) as pool:
        for i, res in enumerate(pool.imap_unordered(process, tasks, chunksize=64), 1):
            status = res[0]
            if status == "OK":
                w.writerow(res[1])
                f_seen.write((res[1][4] if res[1][1] != "imac" else args.staging_prefix + res[1][4]) + "\n")
                ok += 1
            else:
                f_err.write(f"{res[1]}\t{res[2]}\n")
                f_seen.write(res[1] + "\n")
                errs += 1
            if i % 20000 == 0:
                rate = i / (time.time() - t0)
                f_csv.flush(); f_err.flush(); f_seen.flush()
                print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(tasks)} ok={ok} err={errs} {rate:.0f}/s", flush=True)
    f_csv.close(); f_err.close(); f_seen.close()
    print(f"[{time.strftime('%H:%M:%S')}] DONE process ok={ok} err={errs}", flush=True)

    # Build grouped manifest
    print("Building master_manifest.parquet ...", flush=True)
    import pandas as pd
    df = pd.read_csv(raw_csv)
    g = df.groupby("md5")
    man = g.agg(
        stored_path=("stored_path", "first"),
        size=("size", "first"),
        n_copies=("original_path", "size"),
        sources=("source", lambda s: sorted(set(s))),
        hosts=("host", lambda s: sorted(set(s))),
        original_paths=("original_path", list),
    ).reset_index()
    out = os.path.join(catalog, "master_manifest.parquet")
    man.to_parquet(out, index=False)
    print(f"unique_md5={len(man)} input_rows={len(df)} -> {out}", flush=True)
    # per-source breakdown
    print("Per-source input breakdown:", flush=True)
    print(df["source"].value_counts().to_string(), flush=True)


if __name__ == "__main__":
    main()
