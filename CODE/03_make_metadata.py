#!/usr/bin/env python3
"""03_make_metadata.py — LAMD-style metadata over the deduped MIDIs store.

Walks <out_root>/MIDIs, parses each MIDI with TMIDIX, and produces:
  META_DATA/META_DATA_<n>.pickle   chunked [md5, data] LAMDa-compatible records
                                   (data carries ms_chords_counts = similarity
                                    signature + chords data, exactly as LAMD search uses)
  catalog/metadata.parquet         flat per-file features for SQL/pandas queries
  catalog/catalog.sqlite           metadata JOINed to master_manifest on md5
  catalog/meta_errors.log          skipped/unparseable files

Faithful re-implementation of los_angeles_midi_dataset_metadata_maker.py's
extraction, run multiprocess over the canonical store. md5 = filename stem.
"""
import os, sys, glob, pickle, argparse, time, statistics, sqlite3
from collections import Counter
from multiprocessing import Pool

# TMIDIX from the LAMD code dir
sys.path.insert(0, "/home/t/datasets/LAMD/CODE")
import TMIDIX  # noqa: E402


def extract(path):
    """Return (md5, lamd_data_list, flat_dict) or raises."""
    md5 = os.path.basename(path).split(".mid")[0]
    fdata = open(path, "rb").read()
    opus = TMIDIX.midi2opus(fdata)

    opus_events_matrix = []
    it = 1
    while it < len(opus):
        opus_events_matrix += list(opus[it]); it += 1

    ms_score = TMIDIX.opus2score(TMIDIX.to_millisecs(opus))
    ms_events_matrix = []
    it = 1
    while it < len(ms_score):
        for e in ms_score[it]:
            if e[0] == "note":
                ms_events_matrix.append(e)
        it += 1
    ms_events_matrix.sort(key=lambda x: x[1])

    score = TMIDIX.opus2score(opus)
    events_matrix, full_events_matrix = [], []
    itrack = 1
    patches = [0] * 16
    while itrack < len(score):
        for e in score[itrack]:
            if e[0] == "note" or e[0] == "patch_change":
                events_matrix.append(e)
            full_events_matrix.append(e)
        itrack += 1
    full_events_matrix.sort(key=lambda x: x[1])
    events_matrix.sort(key=lambda x: x[1])

    events_matrix1 = []
    for e in events_matrix:
        if e[0] == "patch_change":
            patches[e[2]] = e[3]
        if e[0] == "note":
            e.extend([patches[e[3]]])
            events_matrix1.append(e)

    if len(events_matrix1) <= 32 or len(ms_events_matrix) == 0:
        raise ValueError("too-few-notes")

    events_matrix1.sort(key=lambda x: x[1])
    for e in events_matrix1:
        if e[0] == "note":
            if e[3] == 9:
                e[4] = (abs(e[4]) % 128) + 128
            else:
                e[4] = abs(e[4]) % 128

    pitches_counts = [[y[0], y[1]] for y in Counter([y[4] for y in events_matrix1]).most_common()]
    pitches_counts.sort(key=lambda x: x[0], reverse=True)

    patches_s = sorted([y[6] for y in events_matrix1])
    patches_counts = [[y[0], y[1]] for y in Counter(patches_s).most_common()]
    patches_counts.sort(key=lambda x: x[0])

    midi_patches = sorted(set([y[3] for y in events_matrix if y[0] == "patch_change"])) or [0]

    times = []
    pt = ms_events_matrix[0][1]
    start = True
    for e in ms_events_matrix:
        if (e[1] - pt) != 0 or start:
            times.append(e[1] - pt); start = False
        pt = e[1]
    times_sum = min(10000000, sum(times))
    durs = [e[2] for e in ms_events_matrix]
    vels = [e[5] for e in ms_events_matrix]
    avg_time, avg_dur, avg_vel = int(sum(times)/len(times)), int(sum(durs)/len(durs)), int(sum(vels)/len(vels))
    mode_time, mode_dur, mode_vel = statistics.mode(times), statistics.mode(durs), statistics.mode(vels)
    median_time, median_dur, median_vel = int(statistics.median(times)), int(statistics.median(durs)), int(statistics.median(vels))

    text_events_list = ['text_event','text_event_08','text_event_09','text_event_0a','text_event_0b','text_event_0c','text_event_0d','text_event_0e','text_event_0f']
    text_events_count = len([e for e in full_events_matrix if e[0] in text_events_list])
    lyric_events_count = len([e for e in full_events_matrix if e[0] == "lyric"])

    chords = []
    pe = ms_events_matrix[0]; cho = []
    for e in ms_events_matrix:
        if (e[1] - pe[1]) == 0:
            if e[3] != 9 and (e[4] % 12) not in cho:
                cho.append(e[4] % 12)
        else:
            if len(cho) > 0:
                chords.append(sorted(cho))
            cho = []
            if e[3] != 9 and (e[4] % 12) not in cho:
                cho.append(e[4] % 12)
        pe = e
    if len(cho) > 0:
        chords.append(sorted(cho))
    ms_chords_counts = sorted([[list(k), v] for k, v in Counter([tuple(c) for c in chords if len(c) > 1]).most_common()], reverse=True, key=lambda x: x[1])
    if len(ms_chords_counts) == 0:
        ms_chords_counts = [[[0, 0], 0]]

    total_number_of_chords = len(set([y[1] for y in events_matrix1]))
    tempo_change_count = len([e for e in full_events_matrix if e[0] == "set_tempo"])
    thirty_second_note = [e for e in events_matrix1][32]
    tsn_idx = full_events_matrix.index(thirty_second_note)

    data = []
    data.append(['total_number_of_tracks', itrack])
    data.append(['total_number_of_opus_midi_events', len(opus_events_matrix)])
    data.append(['total_number_of_score_midi_events', len(full_events_matrix)])
    data.append(['average_median_mode_time_ms', [avg_time, median_time, mode_time]])
    data.append(['average_median_mode_dur_ms', [avg_dur, median_dur, mode_dur]])
    data.append(['average_median_mode_vel', [avg_vel, median_vel, mode_vel]])
    data.append(['total_number_of_chords', total_number_of_chords])
    data.append(['total_number_of_chords_ms', len(times)])
    data.append(['ms_chords_counts', ms_chords_counts])
    data.append(['pitches_times_sum_ms', times_sum])
    data.append(['total_pitches_counts', pitches_counts])
    data.append(['midi_patches', midi_patches])
    data.append(['total_patches_counts', patches_counts])
    data.append(['tempo_change_count', tempo_change_count])
    data.append(['text_events_count', text_events_count])
    data.append(['lyric_events_count', lyric_events_count])
    data.append(['midi_ticks', score[0]])
    data.extend(full_events_matrix[:tsn_idx])
    data.append(full_events_matrix[-1])

    # ---- flat features for SQL/pandas ----
    note_pitches = [e[4] for e in events_matrix1 if e[4] < 128]  # non-drum
    has_drums = any(e[3] == 9 for e in events_matrix1)
    # tempo (BPM): first set_tempo (microsec per quarter)
    bpm = None
    for e in full_events_matrix:
        if e[0] == "set_tempo" and len(e) >= 3 and e[2]:
            bpm = round(60_000_000 / e[2], 1); break
    # time signature: first time_signature event
    tsig = None
    for e in full_events_matrix:
        if e[0] == "time_signature" and len(e) >= 4:
            tsig = f"{e[2]}/{2**e[3]}"; break
    duration_ms = max((e[1] + e[2]) for e in ms_events_matrix)

    flat = dict(
        md5=md5,
        n_tracks=int(itrack),
        n_notes=len(events_matrix1),
        n_score_events=len(full_events_matrix),
        duration_sec=round(duration_ms / 1000.0, 2),
        bpm=bpm,
        time_signature=tsig,
        n_distinct_patches=len(midi_patches),
        midi_patches=",".join(map(str, midi_patches)),
        has_drums=int(has_drums),
        pitch_min=min(note_pitches) if note_pitches else None,
        pitch_max=max(note_pitches) if note_pitches else None,
        n_distinct_chords=len([c for c in ms_chords_counts if c[1] > 0]),
        avg_vel=avg_vel,
        tempo_change_count=tempo_change_count,
        text_events_count=text_events_count,
        lyric_events_count=lyric_events_count,
    )
    return md5, data, flat


def worker(path):
    try:
        return ("OK",) + extract(path)
    except Exception as ex:
        return ("ERR", path, repr(ex)[:160])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--chunk", type=int, default=50000, help="records per META_DATA pickle")
    args = ap.parse_args()

    R = args.out_root
    meta_dir = os.path.join(R, "META_DATA")
    catalog = os.path.join(R, "catalog")
    os.makedirs(meta_dir, exist_ok=True)
    err_log = open(os.path.join(catalog, "meta_errors.log"), "w")

    files = glob.glob(os.path.join(R, "MIDIs", "*", "*.mid"))
    print(f"[{time.strftime('%H:%M:%S')}] metadata over {len(files)} files, workers={args.workers}", flush=True)

    buf = []           # LAMDa [md5, data] records for current chunk
    flats = []         # flat dicts
    chunk_idx = 0
    ok = errs = 0
    t0 = time.time()

    def flush_chunk():
        nonlocal chunk_idx
        if not buf:
            return
        with open(os.path.join(meta_dir, f"META_DATA_{chunk_idx:04d}.pickle"), "wb") as fh:
            pickle.dump(buf, fh, protocol=pickle.HIGHEST_PROTOCOL)
        chunk_idx += 1
        buf.clear()

    with Pool(args.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(worker, files, chunksize=32), 1):
            if res[0] == "OK":
                _, md5, data, flat = res
                buf.append([md5, data])
                flats.append(flat)
                ok += 1
                if len(buf) >= args.chunk:
                    flush_chunk()
            else:
                err_log.write(f"{res[1]}\t{res[2]}\n"); errs += 1
            if i % 20000 == 0:
                err_log.flush()
                print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(files)} ok={ok} err={errs} {i/(time.time()-t0):.0f}/s", flush=True)
    flush_chunk()
    err_log.close()
    print(f"[{time.strftime('%H:%M:%S')}] DONE meta ok={ok} err={errs} chunks={chunk_idx}", flush=True)

    # ---- flat parquet ----
    import pandas as pd
    mdf = pd.DataFrame(flats)
    pq = os.path.join(catalog, "metadata.parquet")
    mdf.to_parquet(pq, index=False)
    print(f"metadata.parquet rows={len(mdf)} -> {pq}", flush=True)

    # ---- sqlite: metadata JOIN manifest ----
    man = pd.read_parquet(os.path.join(catalog, "master_manifest.parquet"))
    man2 = man.copy()
    man2["sources"] = man2["sources"].apply(lambda x: ",".join(x))
    man2["hosts"] = man2["hosts"].apply(lambda x: ",".join(x))
    man2["original_paths"] = man2["original_paths"].apply(lambda x: "\n".join(x))
    dbp = os.path.join(catalog, "catalog.sqlite")
    if os.path.exists(dbp):
        os.remove(dbp)
    con = sqlite3.connect(dbp)
    mdf.to_sql("metadata", con, index=False)
    man2.to_sql("manifest", con, index=False)
    con.execute("CREATE INDEX idx_meta_md5 ON metadata(md5)")
    con.execute("CREATE INDEX idx_man_md5 ON manifest(md5)")
    con.execute("""CREATE VIEW catalog AS
        SELECT m.*, n.sources, n.hosts, n.n_copies, n.stored_path
        FROM metadata m JOIN manifest n ON m.md5 = n.md5""")
    con.commit()
    con.close()
    print(f"catalog.sqlite written (tables: metadata, manifest; view: catalog) -> {dbp}", flush=True)


if __name__ == "__main__":
    main()
