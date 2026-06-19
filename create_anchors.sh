#!/usr/bin/env bash
# Generate the 4 NinjaStar groove-anchor MIDIs from MCP strings (idempotent; skips if present).
cd "$(dirname "$0")"
python3 - <<'PY'
import importlib.util, os
m=importlib.util.spec_from_file_location("mcp","CODE/30_mcp_groove.py"); mcp=importlib.util.module_from_spec(m); m.loader.exec_module(mcp)
A={"blast":("(hk)(s)(hk)(s)(hk)(s)(hk)(s)(hk)(s)(hk)(s)(hk)(s)(hk)(s)",140),"rap":("khkhshhshskhshhhkhkhshhshskhshhh",92),"death":("kkkkskkkkkkkskkkkkkkskkkkkkkskkk h h h h",240),"neutral":("k...s...k...s...k...s...k...s...",120)}
os.makedirs("rhythmexamples",exist_ok=True)
for n,(s,bpm) in A.items():
    p=f"rhythmexamples/{n}.mcp.mid"
    if not os.path.exists(p): st,bpb=mcp.parse_mcp(s); mcp.write_smf(mcp.mcp_to_array(st,bpb),p,bpm=bpm); print("wrote",p)
PY
