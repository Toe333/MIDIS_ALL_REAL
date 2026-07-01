#!/usr/bin/env python3
"""_pipeline_graph.py — machine-checkable dependency map of the CODE/ pipeline.

Parses every CODE/*.py for *actual* references to other pipeline scripts (the
`_load("NN_*.py")` / importlib / subprocess / `import _common` patterns the steps use)
and emits PIPELINE_GRAPH.md: a Mermaid dependency graph + a table. Every edge is
confidence-tagged:

  * EXTRACTED — script B's source literally references script A by filename (high confidence).
  * INFERRED  — no extracted dep found, so we fall back to the numbering backbone (B depends
                on the nearest lower-numbered base step). Low confidence; verify before trusting.

Read-only. Run from anywhere:
  .venv-linux/bin/python CODE/_pipeline_graph.py            # writes PIPELINE_GRAPH.md
  .venv-linux/bin/python CODE/_pipeline_graph.py --print    # also dump to stdout
"""
from __future__ import annotations

import argparse
import os
import re
import sys

CODE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE)
OUT = os.path.join(ROOT, "PIPELINE_GRAPH.md")

# scripts to skip (one-offs, tests, migrations — not part of the dependency backbone)
SKIP = {"_pipeline_graph.py", "_detect_test.py", "_dump_pt.py", "migrate_to_sqlserver.py",
        "test_drum_vector.py", "_test_sql_conn.py", "_validate_key.py", "_verify_migration.py",
        "_common.py"}

REF_RE = re.compile(r"\b(\d{2}_[a-z0-9_]+)\.py")          # references to numbered scripts
NAMED_RE = re.compile(r"\b(genre_engine|_common)\b")       # key named modules
NUM_RE = re.compile(r"^(\d{2})_")


def scripts():
    out = []
    for f in sorted(os.listdir(CODE)):
        if f.endswith(".py") and f not in SKIP:
            out.append(f)
    return out


def docline(path):
    """First non-empty line of the module docstring (the purpose)."""
    try:
        src = open(path, encoding="utf-8").read()
    except Exception:  # noqa: BLE001
        return ""
    m = re.search(r'"""(.*?)"""', src, re.S)
    if not m:
        return ""
    for line in m.group(1).strip().splitlines():
        line = line.strip()
        if line:
            # strip a leading "NN_name.py — " prefix for brevity
            return re.sub(r"^\S+\.py\s*[—:-]\s*", "", line)[:110]
    return ""


def number(f):
    m = NUM_RE.match(f)
    return int(m.group(1)) if m else None


def build():
    files = scripts()
    fileset = set(files)
    stems = {f[:-3]: f for f in files}        # 'NN_name' -> 'NN_name.py'
    edges = {}      # (src, dst) -> 'EXTRACTED' | 'INFERRED'
    extracted_into = {f: set() for f in files}

    for f in files:
        src = open(os.path.join(CODE, f), encoding="utf-8").read()
        refs = set(m.group(1) + ".py" for m in REF_RE.finditer(src))
        refs |= set((m.group(1) + ".py") if m.group(1) != "_common" else "_common.py"
                    for m in NAMED_RE.finditer(src))
        for r in refs:
            if r == f or r not in fileset:
                continue
            edges[(r, f)] = "EXTRACTED"      # r is produced/used-before f
            extracted_into[f].add(r)

    # INFERRED backbone: base build steps (10..17) in numeric order, only where a step
    # has no extracted upstream among the numbered scripts.
    numbered = sorted([f for f in files if number(f) is not None], key=lambda x: (number(x), x))
    for i, f in enumerate(numbered):
        n = number(f)
        if extracted_into[f]:
            continue
        # nearest lower-numbered script becomes an inferred predecessor
        prev = None
        for g in reversed(numbered[:i]):
            if number(g) is not None and number(g) < n:
                prev = g
                break
        if prev and (prev, f) not in edges:
            edges[(prev, f)] = "INFERRED"
    return files, edges


def node_id(f):
    return "n_" + f[:-3].replace("-", "_")


def mermaid(files, edges):
    lines = ["```mermaid", "graph LR"]
    for f in files:
        label = f[:-3]
        lines.append(f'  {node_id(f)}["{label}"]')
    for (a, b), conf in sorted(edges.items()):
        arrow = "-->" if conf == "EXTRACTED" else "-.->"
        lines.append(f"  {node_id(a)} {arrow} {node_id(b)}")
    lines.append("```")
    lines.append("")
    lines.append("Solid `-->` = EXTRACTED (source-verified). Dotted `-.->` = INFERRED (numbering backbone).")
    return "\n".join(lines)


def table(files, edges):
    rows = ["| script | purpose | upstream (EXTRACTED) | upstream (INFERRED) |",
            "|---|---|---|---|"]
    for f in files:
        ext = sorted(a[:-3] for (a, b), c in edges.items() if b == f and c == "EXTRACTED")
        inf = sorted(a[:-3] for (a, b), c in edges.items() if b == f and c == "INFERRED")
        rows.append(f"| `{f[:-3]}` | {docline(os.path.join(CODE, f))} | "
                    f"{', '.join('`'+e+'`' for e in ext) or '—'} | "
                    f"{', '.join('`'+e+'`' for e in inf) or '—'} |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="dump")
    args = ap.parse_args()
    files, edges = build()
    n_ext = sum(1 for c in edges.values() if c == "EXTRACTED")
    n_inf = sum(1 for c in edges.values() if c == "INFERRED")
    doc = (
        "# PIPELINE_GRAPH — CODE/ dependency map\n\n"
        "> Generated by `CODE/_pipeline_graph.py` (read-only). The numbering in `CODE/NN_*.py`\n"
        "> encodes dependency order; this map makes the *actual* source-level references explicit\n"
        "> and tags each edge EXTRACTED (verified in source) vs INFERRED (numbering backbone).\n"
        "> STATE.md remains the source of truth for live values; regenerate after adding a step.\n\n"
        f"- scripts mapped: **{len(files)}**\n"
        f"- edges: **{n_ext} EXTRACTED**, **{n_inf} INFERRED**\n\n"
        "## Graph\n\n" + mermaid(files, edges) + "\n\n## Table\n\n" + table(files, edges) + "\n"
    )
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"[graph] wrote {OUT}  ({len(files)} scripts, {n_ext} extracted / {n_inf} inferred edges)")
    if args.dump:
        print("\n" + doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
