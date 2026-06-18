#!/usr/bin/env python3
"""05_tokenize.py — SkyTNT-aligned tokenized training corpus.

SkyTNT's train.py tokenizes MIDIs *on the fly* from a file list (MIDI.midi2score
-> tokenizer.tokenize), so the primary trainable artifact is a manifest of the
deduped store keyed by md5 (joins back to metadata for filtered LoRA pools).
This script:

  1. Writes TOKENIZED/train_manifest.tsv : md5 \\t stored_path   (the training set)
  2. Pre-tokenizes a SAMPLE into TOKENIZED/sample_shards/*.npy   (cache + sanity)
  3. Round-trips one file (tokenize -> detokenize -> .mid) to prove reconstruction
  4. With --full, pre-tokenizes the whole corpus into shards (optional, heavy)

Uses the SkyTNT tokenizer so the corpus trains directly with train.py.
"""
import os, sys, glob, argparse, time
import numpy as np

sys.path.insert(0, "/home/t/projects/midi-model")
import MIDI  # noqa: E402
from midi_tokenizer import MIDITokenizer  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--version", default="v2", choices=["v1", "v2"])
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--full", action="store_true", help="pre-tokenize ALL files (heavy)")
    ap.add_argument("--shard-size", type=int, default=20000)
    args = ap.parse_args()

    R = args.out_root
    tdir = os.path.join(R, "TOKENIZED")
    os.makedirs(tdir, exist_ok=True)
    tok = MIDITokenizer(args.version)

    files = sorted(glob.glob(os.path.join(R, "MIDIs", "*", "*.mid")))
    print(f"corpus: {len(files)} files; tokenizer {args.version}", flush=True)

    # 1. training manifest (md5 \t path)
    man = os.path.join(tdir, "train_manifest.tsv")
    with open(man, "w") as fh:
        for f in files:
            md5 = os.path.basename(f).split(".mid")[0]
            fh.write(f"{md5}\t{f}\n")
    print(f"wrote {man} ({len(files)} entries)", flush=True)

    # 2 + 3. sample pre-tokenize + round-trip
    sdir = os.path.join(tdir, "sample_shards")
    os.makedirs(sdir, exist_ok=True)
    targets = files if args.full else files[: args.sample]
    shard, shard_idx, ok, err = [], 0, 0, 0
    roundtripped = False
    t0 = time.time()
    for i, f in enumerate(targets, 1):
        md5 = os.path.basename(f).split(".mid")[0]
        try:
            score = MIDI.midi2score(open(f, "rb").read())
            tokens = tok.tokenize(score)
            arr = np.asarray(tokens, dtype=np.int16)
            shard.append((md5, arr))
            ok += 1
            if not roundtripped:
                back = tok.detokenize(tokens)
                rt = MIDI.score2midi(back)
                with open(os.path.join(tdir, "roundtrip_sample.mid"), "wb") as g:
                    g.write(rt)
                print(f"round-trip OK: {md5} -> {len(tokens)} tokens -> reconstructed "
                      f"{os.path.join(tdir,'roundtrip_sample.mid')}", flush=True)
                roundtripped = True
        except Exception as ex:
            err += 1
            continue
        if len(shard) >= args.shard_size:
            np.savez_compressed(os.path.join(sdir, f"shard_{shard_idx:04d}.npz"),
                                md5=[m for m, _ in shard],
                                tokens=np.array([a for _, a in shard], dtype=object))
            shard_idx += 1; shard = []
        if i % 5000 == 0:
            print(f"[{time.strftime('%H:%M:%S')}] {i}/{len(targets)} ok={ok} err={err} {i/(time.time()-t0):.0f}/s", flush=True)
    if shard:
        np.savez_compressed(os.path.join(sdir, f"shard_{shard_idx:04d}.npz"),
                            md5=[m for m, _ in shard],
                            tokens=np.array([a for _, a in shard], dtype=object))
        shard_idx += 1
    print(f"DONE tokenize ok={ok} err={err} shards={shard_idx} "
          f"({'FULL corpus' if args.full else f'sample of {len(targets)}'})", flush=True)


if __name__ == "__main__":
    main()
