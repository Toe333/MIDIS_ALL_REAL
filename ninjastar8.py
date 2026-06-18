#!/usr/bin/env python3
"""NinjaStar-8 — by-ear MIDI taste annotator (NinjaStarRecords).

Grok-refined axes (v1). Listen to a track, rate it on 0-8 bipolar sliders
(4 = neutral, bipolar diverging meter), save -> auto-advance. Engineered to feel
like we're building the next inevitable sound: fast, fun, zero drudgery.

  7 axes: CORE  musicality(❤️ love-it) · novelty(✨) · groove(🥁)
          BONUS valence(🎭) · energy(⚡) · memorability(🎣)
          LIGHTNING spark(🔥 = makes me want to generate 10 variations now)
  each tagged felt vs perceived. Core always shown; bonus+lightning behind "+ more".

  ratings file : _work/ninjastar8_ratings.parquet  (APPEND model, keyed by rating_id)
  columns      : rating_id, pool_id, md5, repeat_of_md5, session_id,
                 musicality, novelty, groove, valence, energy, memorability, spark,
                 confidence, glitch_flag, free_tag, rated_at
  song pool    : _work/pool_<ver>.parquet (built by CODE/28_build_pool.py); the file
                 named in _work/pool_current.txt is served.

Read-only on catalog/midi/soundfonts; only writes its own ratings parquet (atomically).
Append model so silent REPEATS (same md5, new pool_id) co-exist for self-consistency.

Usage: ./ninjastar8.py {serve|open|stop|status|export} [--port 8780]
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

BASE = Path(__file__).resolve().parent
AUDIO_DIR = BASE / "_stats" / "audio_sanity_wav"   # source of the 109-clip pool set
MIDI_DIR = BASE / "MIDIs"                           # served to the phone (tiny .mid)
WEB_DIR = BASE / "web"                              # vendored spessasynth synth engine
SF_DIR = BASE / "soundfonts"                        # .sf2/.sf3 soundbanks (swappable)
META = BASE / "catalog" / "metadata.parquet"
OUT = BASE / "_work" / "ninjastar8_ratings.parquet"
POOL_PTR = BASE / "_work" / "pool_current.txt"     # names the active pool_<ver>.parquet
PID_FILE = BASE / "_work" / ".ninjastar8.pid"
PORT_FILE = BASE / "_work" / ".ninjastar8.port"
LOG_FILE = BASE / "_work" / ".ninjastar8.log"
DEFAULT_PORT = 8780
# Bind all interfaces so an iPhone on the tailnet (via Tailscale) can reach it.
# Reachability is still limited to the tailnet + LAN; advertise the Tailscale IP.
HOST = "0.0.0.0"


def _advertise_host() -> str:
    """Best URL host to hand the phone: Tailscale IP if available, else LAN IP."""
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True,
                             text=True, timeout=3)
        ip = out.stdout.strip().splitlines()[0].strip()
        if ip:
            return ip
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# --- the 7 axes (bipolar, 0 = low pole, 4 = neutral, 8 = high pole) ---
# tier: core (always) | bonus (when obvious) | lightning (special). badge: felt | perceived.
DIMS = [
    {"key": "musicality",   "lo": "meh",        "hi": "I love this",       "tier": "core",      "badge": "felt",      "emoji": "❤️", "hint": "love-it / quality"},
    {"key": "novelty",      "lo": "predictable","hi": "strange-but-works", "tier": "core",      "badge": "felt",      "emoji": "✨", "hint": "novelty"},
    {"key": "groove",       "lo": "no pocket",  "hi": "deep pocket",       "tier": "core",      "badge": "perceived", "emoji": "🥁", "hint": "groove (top priority)"},
    {"key": "valence",      "lo": "dark",       "hi": "bright",            "tier": "bonus",     "badge": "perceived", "emoji": "🎭", "hint": "valence"},
    {"key": "energy",       "lo": "calm",       "hi": "intense",           "tier": "bonus",     "badge": "perceived", "emoji": "⚡", "hint": "energy"},
    {"key": "memorability", "lo": "forgettable","hi": "earworm",           "tier": "bonus",     "badge": "felt",      "emoji": "🎣", "hint": "catchiness"},
    {"key": "spark",        "lo": "meh",        "hi": "gen 10 NOW",        "tier": "lightning", "badge": "felt",      "emoji": "🔥", "hint": "generation spark"},
]
DIM_KEYS = [d["key"] for d in DIMS]
EXTRA_COLS = ["confidence", "glitch_flag", "free_tag"]          # extra per-rating metadata
META_COLS = ["rating_id", "pool_id", "md5", "repeat_of_md5", "session_id"]
RATING_COLS = [*META_COLS, *DIM_KEYS, *EXTRA_COLS, "rated_at"]  # rated_at == spec's rating_ts
INT_DIMS = [*DIM_KEYS, "confidence"]                            # 0..8 nullable ints
SCALE_MAX = 8   # 0..8, 9 cells; half (4) = neutral


# --------------------------------------------------------------------------- data

def _pool_path() -> Path | None:
    """The active pool parquet named in _work/pool_current.txt (built by 28_build_pool.py)."""
    if POOL_PTR.exists():
        p = (BASE / "_work" / POOL_PTR.read_text().strip())
        if p.is_file():
            return p
    # fall back to any pool_*.parquet, newest first
    cands = sorted((BASE / "_work").glob("pool_*.parquet"))
    return cands[-1] if cands else None


def _build_pool() -> list[dict]:
    """Serve the hybrid pool (CODE/28_build_pool.py) as ordered entries.

    Each entry is keyed by a unique pool_id so silent REPEATS (same md5, different
    pool_id) are distinct rating slots. Falls back to the old 109 WAV-derived set if
    no pool file exists yet.
    """
    import pandas as pd
    pp = _pool_path()
    if pp is None:
        return _legacy_wav_pool()
    df = pd.read_parquet(pp)
    pool = []
    for r in df.itertuples(index=False):
        md5 = str(r.md5)
        pool.append({
            "pool_id": str(r.pool_id),
            "md5": md5,
            "matched": True,
            "source": getattr(r, "source", ""),
            "is_repeat": bool(getattr(r, "is_repeat", False)),
            "repeat_of": (str(r.repeat_of_md5) if pd.notna(getattr(r, "repeat_of_md5", None)) else None),
            "title": (r.title if isinstance(r.title, str) else "") or "",
            "artist": (r.artist if isinstance(r.artist, str) else "") or "",
        })
    return pool


def _legacy_wav_pool() -> list[dict]:
    """Old 109-clip pool from the audio-sanity WAVs (fallback only)."""
    wavs = sorted(AUDIO_DIR.glob("*.wav"))
    prefixes = {w.stem.split("__")[-1]: w.stem.split("__")[0] for w in wavs}
    if not prefixes:
        return []
    import pandas as pd
    df = pd.read_parquet(META, columns=["md5", "title", "artist"]).dropna(subset=["md5"])
    df["pre"] = df["md5"].astype(str).str[:12]
    df = df[df["pre"].isin(prefixes)].drop_duplicates("pre")
    lut = {r.pre: (r.md5, r.title, r.artist) for r in df.itertuples(index=False)}
    pool = []
    for i, pre in enumerate(sorted(prefixes)):
        md5, title, artist = lut.get(pre, (None, None, None))
        if not md5:
            continue
        pool.append({"pool_id": f"legacy_{i:04d}", "md5": str(md5), "matched": True,
                     "source": "legacy", "is_repeat": False, "repeat_of": None,
                     "title": (title if isinstance(title, str) else "") or "",
                     "artist": (artist if isinstance(artist, str) else "") or ""})
    return pool


def _list_soundfonts() -> list[dict]:
    """Available soundbanks in soundfonts/ — drop any .sf2/.sf3 in there to add one.

    Returned as [{id, name}]; id is the filename, served at /soundfont/<id>.
    VintageDreams (the one the WAV renders used) is forced first when present.
    """
    sfs = []
    for p in sorted(SF_DIR.glob("*")):
        if p.suffix.lower() in (".sf2", ".sf3", ".sfogg", ".dls") and p.is_file():
            sfs.append({"id": p.name, "name": p.stem,
                        "size": p.stat().st_size})
    def rank(d):
        n = d["id"].lower()
        if "vintage" in n:     return 0   # tiny 314KB -> DEFAULT (instant on bad signal)
        if "generaluser" in n: return 1   # good full GM 30MB -> opt-in upgrade
        return 2
    sfs.sort(key=lambda d: (rank(d), d["name"].lower()))
    return sfs


def _load_ratings_rows() -> list[dict]:
    """All rating rows as JSON-safe dicts (NaN -> None). APPEND model, keyed by rating_id."""
    if not OUT.exists():
        return []
    import pandas as pd
    try:
        df = pd.read_parquet(OUT)
    except Exception:
        return []
    return df.astype(object).where(pd.notna(df), None).to_dict("records")


def _rated_pool_ids() -> list[str]:
    """pool_ids that already have a rating -> the frontend skips them in the queue."""
    return [str(r["pool_id"]) for r in _load_ratings_rows() if r.get("pool_id")]


def _clamp(v):
    """0..SCALE_MAX int, else None (so un-touched/neutral-skip stays NA, not a fake 0)."""
    if v is None or v == "" or v == -1:
        return None
    try:
        iv = int(v)
        return iv if 0 <= iv <= SCALE_MAX else None
    except (TypeError, ValueError):
        return None


def _save_rating(payload: dict) -> int:
    """Upsert ONE rating row by rating_id (append model). Returns total row count.

    Keyed by rating_id (not md5) so silent repeats co-exist and offline retries are
    idempotent (same rating_id -> replace, not duplicate).
    """
    import pandas as pd
    rid = str(payload.get("rating_id") or uuid4().hex)
    values = payload.get("values", {}) or {}
    row = {
        "rating_id": rid,
        "pool_id": (str(payload["pool_id"]) if payload.get("pool_id") else None),
        "md5": str(payload.get("md5") or ""),
        "repeat_of_md5": (str(payload["repeat_of_md5"]) if payload.get("repeat_of_md5") else None),
        "session_id": (str(payload["session_id"]) if payload.get("session_id") else None),
        "confidence": _clamp(payload.get("confidence")),
        "glitch_flag": 1 if payload.get("glitch_flag") in (1, True, "1") else 0,
        "free_tag": (str(payload["free_tag"])[:200] if payload.get("free_tag") else None),
        "rated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for k in DIM_KEYS:
        row[k] = _clamp(values.get(k))

    rows = [r for r in _load_ratings_rows() if str(r.get("rating_id")) != rid]
    rows.append(row)
    df = pd.DataFrame(rows)
    for c in RATING_COLS:
        if c not in df.columns:
            df[c] = None
    df = df[RATING_COLS]
    for k in INT_DIMS:
        df[k] = df[k].astype("Int64")
    df["glitch_flag"] = df["glitch_flag"].fillna(0).astype("Int8")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".parquet.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, OUT)
    return len(df)


# --------------------------------------------------------------------------- page

PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="NinjaStar-8">
<title>NinjaStar-8</title>
<script type="importmap">
{ "imports": { "spessasynth_core": "/web/vendor/spessasynth_core.js" } }
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap" rel="stylesheet">
<style>
  :root{ color-scheme: dark; --ink:#e8f9e8; --bg:#0b0f0b; --acc:#39ff14; --acc2:#ff3864;
         --dim:#1a241a; --cell:#13301a; --line:#214a2a; }
  *{ box-sizing:border-box; margin:0; padding:0;
     -webkit-tap-highlight-color:transparent; }
  body{ font-family:"Press Start 2P", ui-monospace, Menlo, Consolas, monospace;
        background: radial-gradient(circle at 50% -10%, #11201a, var(--bg) 60%);
        color:var(--ink); min-height:100dvh; padding:1rem; line-height:1.7;
        image-rendering:pixelated;
        padding-left:max(1rem,env(safe-area-inset-left));
        padding-right:max(1rem,env(safe-area-inset-right)); }
  .cell, .play, button.act, .dim{ touch-action:manipulation; user-select:none;
        -webkit-user-select:none; }
  .wrap{ max-width:760px; margin:0 auto; }

  header{ display:flex; align-items:center; gap:0.8rem; margin-bottom:0.8rem; }
  .star{ width:46px; height:46px; flex-shrink:0; animation:spin 6s linear infinite;
         filter: drop-shadow(0 0 6px var(--acc)); }
  @keyframes spin{ to{ transform:rotate(360deg);} }
  h1{ font-size:0.95rem; color:var(--acc); letter-spacing:0.04em; }
  h1 small{ display:block; font-size:0.5rem; color:#6fae7f; margin-top:0.4rem; }
  .progress{ margin-left:auto; text-align:right; font-size:0.5rem; color:#7fbf8f; }
  .pbar{ width:140px; height:10px; border:2px solid var(--line); margin-top:0.4rem;
         background:var(--dim); }
  .pbar > i{ display:block; height:100%; background:var(--acc); width:0%; }

  .card{ border:3px solid var(--line); background:rgba(10,20,12,0.7);
         padding:1rem; box-shadow:0 0 0 3px #0b0f0b, 0 0 24px rgba(57,255,20,0.08); }
  .track{ display:flex; align-items:center; gap:0.8rem; margin-bottom:0.9rem;
          border-bottom:2px dashed var(--line); padding-bottom:0.8rem; }
  .play{ width:64px; height:64px; flex-shrink:0; border:3px solid var(--acc);
         background:var(--cell); color:var(--acc); font-family:inherit; cursor:pointer;
         font-size:1.4rem; }
  .play:active{ transform:scale(0.95); }
  .play.playing{ color:var(--acc2); border-color:var(--acc2); }
  .tmeta{ min-width:0; }
  .ttitle{ font-size:0.7rem; color:var(--ink); overflow:hidden; text-overflow:ellipsis;
           white-space:nowrap; }
  .tsub{ font-size:0.5rem; color:#6fae7f; margin-top:0.45rem; word-break:break-all; }

  .dims{ display:flex; flex-direction:column; gap:0.55rem; }
  .dim{ padding:0.45rem 0.5rem; border:2px solid transparent; }
  .dim.focus{ border-color:var(--acc); background:rgba(57,255,20,0.05); }
  .dim-head{ display:flex; align-items:baseline; gap:0.5rem; font-size:0.5rem;
             color:#9fd8af; margin-bottom:0.35rem; }
  .dim-key{ color:var(--acc); }
  .dim-val{ color:var(--acc2); font-size:0.5rem; margin-left:auto; }
  .dim-hint{ margin-left:auto; color:#5f8f6f; font-size:0.45rem; }
  .meter{ display:flex; align-items:center; gap:0.5rem; }
  .pole{ font-size:0.46rem; color:#7fae8f; width:5.5rem; flex-shrink:0; }
  .pole.hi{ text-align:right; color:#d8a; }
  .cells{ display:flex; gap:4px; flex:1; }
  .cell{ flex:1; height:22px; border:2px solid var(--line); background:var(--dim);
         cursor:pointer; }
  .cell.mid{ border-color:#86b39a; border-top-width:3px; border-bottom-width:3px; }
  .cell.fill{ background:var(--acc); box-shadow:0 0 8px rgba(57,255,20,0.5); }   /* all green */
  .badge{ font-size:0.4rem; padding:1px 4px; border:1px solid; border-radius:2px; }
  .badge.felt{ color:#ffd36e; border-color:#7a5533; }
  .badge.perceived{ color:#7fd8ff; border-color:#447788; }
  .dim.tier-lightning{ box-shadow: inset 0 0 0 1px #5a8a33; }
  .ftag{ margin-top:0.4rem; }
  .ftag input{ width:100%; font-family:inherit; font-size:0.5rem; color:var(--ink);
        background:var(--cell); border:2px solid var(--line); padding:0.5rem; }
  .act.glitch{ border-color:var(--acc2); flex:0 0 auto; }
  .act.more{ border-color:#55aa88; color:#9fe8c8; }
  .rep{ color:var(--acc2); font-size:0.5rem; }

  .bar{ display:flex; gap:0.6rem; margin-top:1rem; flex-wrap:wrap; }
  button.act{ font-family:inherit; font-size:0.55rem; padding:0.7rem 0.9rem; cursor:pointer;
              border:3px solid var(--line); background:var(--cell); color:var(--ink); }
  button.act.go{ border-color:var(--acc); color:var(--acc); }
  button.act:active{ transform:translateY(2px); }
  .hint{ margin-top:0.9rem; font-size:0.45rem; color:#5f8f6f; line-height:2; }
  kbd{ color:var(--acc); }
  .sfbar{ display:flex; align-items:center; gap:0.6rem; margin-top:0.8rem;
          font-size:0.5rem; color:#7fbf8f; }
  .sfbar select{ font-family:inherit; font-size:0.5rem; color:var(--ink);
          background:var(--cell); border:2px solid var(--line); padding:0.5rem 0.4rem;
          flex:1; min-width:0; }
  .sflabel{ color:var(--acc); flex-shrink:0; }
  .done{ text-align:center; padding:3rem 1rem; }
  .done h2{ color:var(--acc); font-size:0.9rem; margin-bottom:1rem; }
  audio{ display:none; }

  /* ---- phone (iPhone Safari over Tailscale): everything on ONE screen, no scroll ---- */
  @media (max-width:640px){
    body{ padding:0.35rem; line-height:1.25; }
    .wrap{ max-width:100%; }
    header{ margin-bottom:0.35rem; gap:0.45rem; }
    h1{ font-size:0.6rem; }
    h1 small{ font-size:0.34rem; margin-top:0.18rem; }
    .star{ width:28px; height:28px; }
    .progress{ font-size:0.36rem; }
    .pbar{ width:70px; height:7px; margin-top:0.18rem; }
    .card{ padding:0.45rem; border-width:2px; }
    .track{ margin-bottom:0.35rem; padding-bottom:0.35rem; gap:0.45rem; }
    .play{ width:44px; height:44px; font-size:1.1rem; border-width:2px; }
    .ttitle{ font-size:0.54rem; white-space:normal; }
    .tsub{ font-size:0.4rem; margin-top:0.2rem; }
    .md5{ display:none; }                          /* md5 irrelevant while rating */
    .dims{ gap:0.25rem; }
    .dim{ padding:0.16rem 0.2rem; }
    .dim-head{ font-size:0.4rem; margin-bottom:0.14rem; gap:0.3rem; }
    .dim-hint{ display:none; }                      /* save vertical space on phone */
    .dim-val{ font-size:0.4rem; }
    .meter{ gap:0.3rem; }
    .pole{ width:2.3rem; font-size:0.33rem; }
    .cell{ height:26px; border-width:1px; }
    .cell.mid{ border-top-width:2px; border-bottom-width:2px; }
    .cells{ gap:3px; }
    .sfbar{ margin-top:0.35rem; font-size:0.38rem; gap:0.4rem; }
    .sfbar select{ padding:0.3rem 0.3rem; font-size:0.38rem; }
    .bar{ margin-top:0.45rem; gap:0.4rem; }
    button.act{ font-size:0.52rem; padding:0.55rem 0.5rem; flex:1; text-align:center; }
    .hint{ display:none; }
  }
</style></head><body>
<div class="wrap">
<header>
  <svg class="star" viewBox="-50 -50 100 100" aria-hidden="true">
    <polygon fill="#39ff14" points="0,-46 9,-9 46,0 9,9 0,46 -9,9 -46,0 -9,-9"/>
    <circle r="6" fill="#0b0f0b" stroke="#39ff14" stroke-width="3"/>
  </svg>
  <h1>NinjaStar-8<small>NinjaStarRecords · rate by ear</small></h1>
  <div class="progress">
    <span id="prog">0 / 0</span><span id="pending"></span>
    <div class="pbar"><i id="pfill"></i></div>
  </div>
</header>
<div id="app" class="card"></div>
<div class="sfbar"><span class="sflabel">♪ soundfont</span><select id="sf"></select></div>
<div class="hint" id="hint"></div>
</div>
<script>
let STATE=null, queue=[], cur=null, vals={}, conf=null, freeTag='', focus=0, started=false,
    showMore=false, curRatingId=null, sessionId=null, ratedPool=new Set();

function api(p, opts){ return fetch(p, opts).then(r => r.json()); }
function rid(p){ return p+'_'+Math.random().toString(36).slice(2,10)+'_'+Date.now().toString(36); }

function init(){
  sessionId = rid('s');
  api('/state').then(s => {
    STATE = s;
    ratedPool = new Set(s.rated_pool_ids || []);
    // queued-but-not-yet-synced saves also count as done so we don't re-show them
    loadQueue().forEach(it => { if(it.pool_id) ratedPool.add(it.pool_id); });
    const un = s.pool.filter(t => !ratedPool.has(t.pool_id));
    const re = s.pool.filter(t =>  ratedPool.has(t.pool_id));
    queue = un.concat(re);                          // unrated first, rated to the back
    const sel = document.getElementById('sf');
    if(sel && s.soundfonts && s.soundfonts.length){
      sel.innerHTML = s.soundfonts.map(sf => '<option value="'+sf.id+'">'+sf.name+'</option>').join('');
      curSF = s.soundfonts[0].id; sel.value = curSF; sel.onchange = () => changeSoundfont(sel.value);
    }
    document.getElementById('hint').innerHTML =
      '<kbd>↑↓</kbd> slider · <kbd>←→/0-8</kbd> set · <kbd>Enter</kbd> save+next · '+
      '<kbd>Space</kbd> play · <kbd>m</kbd> more · <kbd>s</kbd> skip';
    updatePending(); flushQueue();
    next(true);
  });
}

function setProgress(){
  const n = ratedPool.size, total = STATE.pool.length;
  document.getElementById('prog').textContent = n + ' / ' + total;
  document.getElementById('pfill').style.width = (total ? (100*n/total) : 0) + '%';
}

// which dim indices are visible: core (tier core) always; bonus+lightning only with "+ more"
function visibleDims(){
  return STATE.dims.map((d,i)=>i).filter(i => showMore || STATE.dims[i].tier==='core');
}
function toggleMore(){ showMore = !showMore; render(); }

function next(first){
  cur = queue.shift();
  if(!cur){ return done(); }
  curRatingId = rid('r');                           // one rating_id per slot (idempotent retries)
  const MID = Math.floor(STATE.scale_max/2);
  vals = {}; STATE.dims.forEach(d => vals[d.key] = MID);  // default neutral; repeats stay blind
  conf = null; freeTag = ''; focus = 0;
  render();
  play(true);
}

function dimHtml(d, di){
  const v = vals[d.key], SMAX = STATE.scale_max, MID = SMAX/2;
  const lo = Math.min(v,MID), hi = Math.max(v,MID);
  let row = '';
  for(let i=0;i<=SMAX;i++){
    let cls = 'cell';
    if(i===MID) cls += ' mid';
    if(v>=0 && i>=lo && i<=hi) cls += ' fill';        // bipolar: grows out from neutral, all green
    row += '<div class="'+cls+'" data-d="'+di+'" data-v="'+i+'"></div>';
  }
  const vlabel = (v>=0) ? (v===MID ? v+' ·neu' : v) : '–';
  const badge = '<span class="badge '+d.badge+'">'+(d.badge==='felt'?'felt':'perc')+'</span>';
  return '<div class="dim tier-'+d.tier+(di===focus?' focus':'')+'" data-di="'+di+'">'+
    '<div class="dim-head"><span class="dim-key">'+d.emoji+' '+d.key+'</span>'+badge+
    '<span class="dim-val">'+vlabel+'</span></div>'+
    '<div class="meter"><span class="pole">'+d.lo+'</span>'+
    '<div class="cells">'+row+'</div><span class="pole hi">'+d.hi+'</span></div></div>';
}

function confHtml(){
  let row = '';
  for(let i=0;i<=STATE.scale_max;i++)
    row += '<div class="cell'+((conf!==null && i<=conf)?' fill':'')+'" data-conf="'+i+'"></div>';
  return '<div class="dim conf"><div class="dim-head"><span class="dim-key">🎚️ confidence</span>'+
    '<span class="dim-val">'+(conf!==null?conf:'–')+'</span></div>'+
    '<div class="meter"><span class="pole">unsure</span><div class="cells">'+row+'</div>'+
    '<span class="pole hi">certain</span></div></div>';
}
function freeTagHtml(){
  return '<div class="ftag"><input id="ftag" placeholder="free tag (optional)" maxlength="200" value="'+
    (freeTag||'').replace(/"/g,'&quot;')+'"></div>';
}

function render(){
  setProgress();
  const t = cur;
  const vis = visibleDims();
  if(!vis.includes(focus)) focus = vis[0];
  const dimsHtml = vis.map(di => dimHtml(STATE.dims[di], di)).join('');
  const extra = showMore ? (confHtml() + freeTagHtml()) : '';
  const title = t.title || ((t.source||'pool')+' · '+t.md5.slice(0,8));
  const sub = (t.artist ? t.artist+' — ' : '') + (t.title||'');
  document.getElementById('app').innerHTML =
    '<div class="track"><button class="play" id="play">▶</button>'+
    '<div class="tmeta"><div class="ttitle">'+title+(t.is_repeat?' <span class="rep">↻repeat</span>':'')+'</div>'+
    '<div class="tsub">'+(sub||'')+'<span class="md5"><br>'+(t.source||'')+' · md5 '+t.md5+'</span></div></div></div>'+
    '<div class="dims">'+dimsHtml+'</div>'+ extra +
    '<div class="bar">'+
      '<button class="act go" onclick="saveNext()">✓ SAVE+NEXT</button>'+
      '<button class="act more" onclick="toggleMore()">'+(showMore?'− less':'+ more')+'</button>'+
      '<button class="act" onclick="next()">» SKIP</button>'+
      '<button class="act glitch" onclick="glitch()" title="glitch / unlistenable">🚩</button>'+
    '</div>';
  bindControls();
}

function bindControls(){
  document.getElementById('play').onclick = () => toggle();
  document.querySelectorAll('.dim .cell[data-v]').forEach(c => {
    c.onclick = () => { focus = +c.dataset.d; setVal(focus, +c.dataset.v); };
  });
  document.querySelectorAll('.dim[data-di]').forEach(d => {
    d.onclick = (e) => { if(e.target.dataset.v !== undefined) return; focus = +d.dataset.di; render(); };
  });
  document.querySelectorAll('.cell[data-conf]').forEach(c => {
    c.onclick = () => { conf = +c.dataset.conf; render(); };
  });
  const ft = document.getElementById('ftag');
  if(ft) ft.oninput = () => { freeTag = ft.value; };
}

function setVal(di, v){
  const key = STATE.dims[di].key;
  vals[key] = Math.max(0, Math.min(STATE.scale_max, v));
  render();
}

function done(){
  document.getElementById('app').innerHTML =
    '<div class="done"><h2>★ pool complete ★</h2>'+
    '<div style="font-size:0.5rem;color:#7fbf8f">'+ratedPool.size+' / '+STATE.pool.length+
    ' rated.<br>ready for Bradley-Terry + taste model.</div></div>';
  setProgress();
  cur = null;
}

// ---- audio (self-hosted spessasynth + our soundfont; only tiny .mid leaves the box) ----
let _mod=null, ctx=null, synth=null, seq=null, audioReady=false, loadedMd5=null,
    curSF=null, audioErr=null, isPlaying=false;

const VER = '2';  // bump to bust phone cache of the vendored synth engine
async function ensureAudio(){
  if(audioReady) return;
  if(!_mod) _mod = await import('/web/vendor/spessasynth_lib.js?v='+VER);
  const AC = window.AudioContext || window.webkitAudioContext;
  ctx = new AC();
  await ctx.audioWorklet.addModule('/web/vendor/spessasynth_processor.min.js?v='+VER);
  synth = new _mod.WorkletSynthesizer(ctx);
  synth.connect(ctx.destination);   // route synth output to the speakers (not automatic!)
  const sf = curSF || (STATE.soundfonts[0] && STATE.soundfonts[0].id);
  const buf = await (await fetch('/soundfont/'+encodeURIComponent(sf))).arrayBuffer();
  await synth.soundBankManager.addSoundBank(buf, 'main');
  await synth.isReady;
  seq = new _mod.Sequencer(synth);
  curSF = sf; audioReady = true;
}

async function ensureLoaded(){
  await ensureAudio();
  if(loadedMd5 !== cur.md5){
    const midi = await (await fetch('/midi/'+cur.md5)).arrayBuffer();
    seq.loadNewSongList([{ binary: midi, fileName: cur.md5+'.mid' }]);
    seq.currentTime = 0;
    loadedMd5 = cur.md5;
  }
}

// auto-called when advancing: load the track, play only if audio is already unlocked
function play(reset){
  if(!cur) return;
  isPlaying = false;
  ensureLoaded().then(() => {
    if(ctx && ctx.state === 'running'){ seq.play(); isPlaying = true; started = true; }
    setPlayUI();
  }).catch(e => { audioErr = e; console.error('audio', e); setPlayUI(); });
}

// the ▶ tap is a user gesture — this is what unlocks audio on iOS Safari
function toggle(){
  if(!cur) return;
  ensureLoaded().then(() => ctx.resume()).then(() => {
    audioErr = null;
    if(isPlaying){ seq.pause(); isPlaying = false; }
    else { seq.currentTime = 0; seq.play(); isPlaying = true; started = true; }
    setPlayUI();
  }).catch(e => { audioErr = e; console.error('audio', e); setPlayUI(); });
}

function setPlayUI(){
  const b = document.getElementById('play'); if(!b) return;
  // natural end -> reset to ▶
  if(isPlaying && seq && seq.duration && seq.currentTime >= seq.duration - 0.05){
    isPlaying = false;
  }
  b.classList.toggle('playing', isPlaying);
  b.textContent = audioErr ? '!' : (isPlaying ? 'Ⅱ' : '▶');
}

async function changeSoundfont(id){
  curSF = id;
  if(!audioReady) return;
  try{
    const buf = await (await fetch('/soundfont/'+encodeURIComponent(id))).arrayBuffer();
    await synth.soundBankManager.addSoundBank(buf, 'main');
  }catch(e){ console.error('soundfont swap', e); }
}

setInterval(() => { if(audioReady && seq) setPlayUI(); }, 600);

// ---- save (offline-resilient: never blocks, never loses a rating on bad cell) ----
const QKEY = 'ns8_queue';
function loadQueue(){ try{ return JSON.parse(localStorage.getItem(QKEY)||'[]'); }catch(e){ return []; } }
function saveQueue(q){ try{ localStorage.setItem(QKEY, JSON.stringify(q)); }catch(e){} }
let _flushing = false;

function updatePending(){
  const el = document.getElementById('pending');
  const n = loadQueue().length;
  if(el) el.textContent = n ? ('  ⟳'+n) : '';
}

function flushQueue(){
  if(_flushing) return;
  const q = loadQueue();
  if(!q.length){ updatePending(); return; }
  _flushing = true;
  const item = q[0];                                            // full rating payload
  api('/rate', { method:'POST', headers:{'Content-Type':'application/json'},
                 body: JSON.stringify(item) })
    .then(() => {
      const q2 = loadQueue().filter(x => x.rating_id !== item.rating_id);  // drop synced
      saveQueue(q2);
      _flushing = false; updatePending();
      if(q2.length) flushQueue();
    })
    .catch(() => { _flushing = false; updatePending(); });      // stay queued, retry later
}

// build the full rating payload, write it locally + queue, advance instantly, sync in bg
function doSave(opts){
  if(!cur) return;
  opts = opts || {};
  const values = {};
  STATE.dims.forEach(d => { values[d.key] = (vals[d.key]<0 ? null : vals[d.key]); });
  const ft = document.getElementById('ftag'); if(ft) freeTag = ft.value;
  const payload = {
    rating_id: curRatingId, pool_id: cur.pool_id, md5: cur.md5,
    repeat_of_md5: (cur.is_repeat ? (cur.repeat_of || cur.md5) : null),
    session_id: sessionId, values: values,
    confidence: conf, glitch_flag: opts.glitch ? 1 : 0,
    free_tag: (freeTag && freeTag.trim()) ? freeTag.trim() : null,
    ts: Date.now(),
  };
  ratedPool.add(cur.pool_id);
  const q = loadQueue().filter(x => x.rating_id !== payload.rating_id);
  q.push(payload); saveQueue(q); updatePending();
  next();
  flushQueue();
}
function saveNext(){ doSave({}); }
function glitch(){ doSave({ glitch: 1 }); }   // 🚩 mark unlistenable + advance

setInterval(flushQueue, 5000);                  // retry stuck saves every 5s
window.addEventListener('online', flushQueue);  // and the moment signal returns

// ---- keyboard ----
document.addEventListener('keydown', e => {
  if(!cur) return;
  if(e.target && e.target.id === 'ftag') return;   // don't hijack typing in the tag box
  const vis = visibleDims(); const pos = Math.max(0, vis.indexOf(focus));
  if(e.key==='ArrowDown'){ focus=vis[(pos+1)%vis.length]; render(); e.preventDefault(); }
  else if(e.key==='ArrowUp'){ focus=vis[(pos-1+vis.length)%vis.length]; render(); e.preventDefault(); }
  else if(e.key==='ArrowRight'){ const k=STATE.dims[focus].key; setVal(focus,(vals[k]<0?0:vals[k]+1)); e.preventDefault(); }
  else if(e.key==='ArrowLeft'){ const k=STATE.dims[focus].key; setVal(focus,(vals[k]<0?0:vals[k]-1)); e.preventDefault(); }
  else if(e.key>='0' && e.key<='8'){ setVal(focus, +e.key); e.preventDefault(); }
  else if(e.key==='Enter'){ saveNext(); e.preventDefault(); }
  else if(e.key===' '){ toggle(); e.preventDefault(); }
  else if(e.key==='m' || e.key==='M'){ toggleMore(); e.preventDefault(); }
  else if(e.key==='s' || e.key==='S'){ next(); e.preventDefault(); }
});

init();
</script>
</body></html>
"""


# --------------------------------------------------------------------------- server

class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):  # noqa: N802
        path = (self.path or "/").split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._bytes(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if path == "/state":
            payload = {
                "pool": self.server.pool,
                "dims": DIMS,                        # key/lo/hi/tier/badge/emoji/hint
                "scale_max": SCALE_MAX,
                "rated_pool_ids": _rated_pool_ids(), # frontend skips these in the queue
                "n_ratings": len(_load_ratings_rows()),
                "soundfonts": _list_soundfonts(),
            }
            return self._json(200, payload)
        if path == "/export":
            return self._json(200, {"ratings": _load_ratings_rows()})
        if path.startswith("/midi/"):
            return self._serve_midi(path[len("/midi/"):])
        if path.startswith("/soundfont/"):
            return self._serve_soundfont(path[len("/soundfont/"):])
        if path.startswith("/web/"):
            return self._serve_web(path[len("/web/"):])
        if path.startswith("/audio/"):
            return self._serve_audio(path[len("/audio/"):])
        self.send_error(404)

    def do_POST(self):  # noqa: N802
        path = (self.path or "/").split("?", 1)[0]
        if path == "/rate":
            length = int(self.headers.get("Content-Length", 0) or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad json"})
            if not body.get("md5"):
                return self._json(400, {"error": "need md5"})
            n = _save_rating(body)
            return self._json(200, {"ok": True, "n_ratings": n,
                                    "rating_id": body.get("rating_id")})
        self.send_error(404)

    # -- static files (midi / soundfont / vendored synth / wav) with Range support --
    def _serve_midi(self, name: str):
        import urllib.parse, re
        md5 = urllib.parse.unquote(name).strip()
        if not re.fullmatch(r"[0-9a-fA-F]{32}", md5):
            return self.send_error(404)
        fp = (MIDI_DIR / md5[:2] / f"{md5}.mid").resolve()
        if MIDI_DIR.resolve() not in fp.parents or not fp.is_file():
            return self.send_error(404)
        return self._serve_ranged(fp, "audio/midi")

    def _serve_soundfont(self, name: str):
        import urllib.parse
        fp = (SF_DIR / urllib.parse.unquote(name)).resolve()
        if SF_DIR.resolve() not in fp.parents or not fp.is_file():
            return self.send_error(404)
        return self._serve_ranged(fp, "application/octet-stream", cache=True)

    def _serve_web(self, name: str):
        import urllib.parse
        fp = (WEB_DIR / urllib.parse.unquote(name).lstrip("/")).resolve()
        if WEB_DIR.resolve() not in fp.parents or not fp.is_file():
            return self.send_error(404)
        ctype = {".js": "text/javascript; charset=utf-8",
                 ".mjs": "text/javascript; charset=utf-8",
                 ".wasm": "application/wasm",
                 ".json": "application/json",
                 ".css": "text/css; charset=utf-8"}.get(fp.suffix.lower(),
                                                        "application/octet-stream")
        return self._serve_ranged(fp, ctype, cache=True)

    def _serve_audio(self, name: str):
        import urllib.parse
        fp = (AUDIO_DIR / urllib.parse.unquote(name)).resolve()
        if AUDIO_DIR.resolve() not in fp.parents or not fp.is_file():
            return self.send_error(404)
        return self._serve_ranged(fp, "audio/wav")

    def _serve_ranged(self, fp, ctype: str, cache: bool = False):
        size = fp.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        status = 200
        if rng and rng.startswith("bytes="):
            spec = rng[6:].split(",")[0].strip()
            try:
                a, b = spec.split("-", 1)
                if a == "":
                    start = max(0, size - int(b)); end = size - 1
                else:
                    start = int(a); end = int(b) if b else size - 1
                status = 206
            except ValueError:
                status = 200
        end = min(end, size - 1)
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control",
                         "public, max-age=86400" if cache else "no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Connection", "close")
        self.end_headers()
        with open(fp, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    def _bytes(self, payload: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, data: dict):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)


def _pick_port(start: int) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"no free port near {start}")


def _alive():
    if not PID_FILE.exists() or not PORT_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
        port = int(PORT_FILE.read_text().strip())
        os.kill(pid, 0)
    except (ValueError, ProcessLookupError, PermissionError):
        return None
    return pid, port


# --------------------------------------------------------------------------- commands

def cmd_serve(args):
    pool = _build_pool()
    pp = _pool_path()
    print(f"pool: {len(pool)} songs ({pp.name if pp else 'legacy WAV set'}) · "
          f"{len(_load_ratings_rows())} ratings", file=sys.stderr)
    port = _pick_port(args.port)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    PORT_FILE.write_text(str(port))
    httpd = ThreadingHTTPServer((HOST, port), Handler)
    httpd.pool = pool
    adv = _advertise_host()
    print(f"NinjaStar-8 serving on all interfaces :{port}", file=sys.stderr)
    print(f"  on this machine : http://127.0.0.1:{port}/", file=sys.stderr)
    print(f"  from iPhone     : http://{adv}:{port}/   (open in Safari over Tailscale)",
          file=sys.stderr)
    try:
        httpd.serve_forever()
    finally:
        PID_FILE.unlink(missing_ok=True)
        PORT_FILE.unlink(missing_ok=True)


def cmd_open(args):
    alive = _alive()
    if alive is None:
        log = open(LOG_FILE, "ab", buffering=0)
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "serve", "--port", str(args.port)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
        )
        for _ in range(80):
            time.sleep(0.05)
            alive = _alive()
            if alive:
                break
        else:
            raise SystemExit(f"server failed to start; check {LOG_FILE}")
    pid, port = alive
    adv = _advertise_host()
    print(f"running · pid {pid}")
    print(f"  on this machine : http://127.0.0.1:{port}/")
    print(f"  from iPhone     : http://{adv}:{port}/   (Safari over Tailscale)")
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")


def cmd_status(args):
    alive = _alive()
    n = len(_load_ratings_rows())
    if alive:
        pid, port = alive
        print(f"running · pid {pid} · {n} rated")
        print(f"  on this machine : http://127.0.0.1:{port}/")
        print(f"  from iPhone     : http://{_advertise_host()}:{port}/")
    else:
        print(f"stopped · {n} rated")


def cmd_stop(args):
    alive = _alive()
    if not alive:
        print("not running")
        return
    pid, _ = alive
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    PID_FILE.unlink(missing_ok=True)
    PORT_FILE.unlink(missing_ok=True)
    print(f"stopped pid {pid}")


def cmd_export(args):
    if args.csv:
        import pandas as pd
        if OUT.exists():
            print(pd.read_parquet(OUT).to_csv(index=False))
    else:
        print(json.dumps(_load_ratings_rows(), indent=2, default=str))


def main(argv=None):
    p = argparse.ArgumentParser(prog="ninjastar8", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("serve", cmd_serve), ("open", cmd_open)):
        sp = sub.add_parser(name)
        sp.add_argument("--port", type=int, default=DEFAULT_PORT)
        if name == "open":
            sp.add_argument("--no-browser", action="store_true")
        sp.set_defaults(func=fn)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    ex = sub.add_parser("export")
    ex.add_argument("--csv", action="store_true")
    ex.set_defaults(func=cmd_export)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
