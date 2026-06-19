#!/usr/bin/env python3
"""
28_mapserver.py — clickable, audible map of a chosen MUSIC-EMBEDDING space.

Serves an interactive 2-D scatter of the corpus. The DOT POSITIONS come from whichever
embedding you pass via --umap (so the map can show DIFFERENT spaces):
  * umap2.parquet        -> PITCH/HARMONY space (74-D signature; pitch+melody+harmony)
  * umap2_drums.parquet  -> DRUM-FEEL space (72-D DrumDNA; groove/rhythm) [CODE/39_drum_umap.py]
The --color flag only TINTS the dots by a metadata column; it is NOT what positions them.
The header shows a plain-English label of the active space so the two never get confused.

Every dot is a real song; CLICK a dot and it streams that song's tiny .mid and synthesizes
it in-browser (self-hosted spessasynth, reusing the vendored engine in web/vendor/).

Self-contained: canvas rendering (no CDN), in-browser synth (no server-side audio).
Local-only: AudioWorklet gets a secure context on http://127.0.0.1 automatically.

  # pitch/harmony map (default)
  python3 CODE/28_mapserver.py --port 8766 --color pitch_class_entropy
  # drum-feel map (positions from the drum vectors)
  python3 CODE/28_mapserver.py --port 8767 --umap umap2_drums.parquet --corners drum --color drum_swing

Reads (read-only): _work/emptyspace/umap2.parquet|pca2.parquet, clusters.parquet,
cluster_summary.parquet, density.parquet, catalog/metadata.parquet, MIDIs/<2hex>/<md5>.mid,
web/vendor/* (vendored synth), _work/emptyspace/assets/VintageDreams.sf2.
Does NOT touch the NinjaStar-8 lane (different port; serves, never writes those files).
"""
import argparse, json, os, io, random, time, threading
import numpy as np, pandas as pd
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "_work", "emptyspace")
VENDOR = os.path.join(ROOT, "web", "vendor")
ASSETS = os.path.join(OUT, "assets")
# clean → effecty; first is the default. label : filename in assets/
SOUNDFONTS = [("TimGM6mb (clean GM)", "TimGM6mb.sf2"),
              ("GM bank (clean)", "GMbank.sf2"),
              ("VintageDreams (synthy)", "VintageDreams.sf2")]
DUELS = os.path.join(ROOT, "_work", "taste_duels.jsonl")   # corpus-lane taste signal
LIKES = os.path.join(ROOT, "_work", "taste_likes.jsonl")   # ♥ point-likes
_dlock = threading.Lock()

STATE = {}   # filled by build_space() + build_duel_pool()
# generation seed targets (highlighted as big magenta stars): _work/generation_seeds/top5_targets.csv
TARGETS_CSV = os.path.join(ROOT, "_work", "generation_seeds", "top5_targets.csv")


def _load_targets():
    """List of (md5, label) for the locked generation-seed targets, or [] if none."""
    if not os.path.exists(TARGETS_CSV):
        return []
    df = pd.read_csv(TARGETS_CSV)
    out = []
    for i, r in df.reset_index(drop=True).iterrows():
        taste = r.get("pred_groove_taste")
        lab = f"#{i+1}" + (f" · {float(taste):.2f}" if taste == taste else "")
        out.append((str(r["md5"]), lab))
    return out


def _load_likes():
    s = set()
    if os.path.exists(LIKES):
        for ln in open(LIKES):
            try:
                s.add(json.loads(ln)["md5"])
            except Exception:
                pass
    return s


def _norm01(v, lohi):
    lo, hi = lohi
    return np.clip((v - lo) / (hi - lo + 1e-9), -0.05, 1.05)


def _build_dim(full, axes, sample_md5, color_md5, cap_map, corners, targets=()):
    """Build one embedding payload (2D or 3D) for the shared sample + corner markers,
    using a normalization fixed from the FULL embedding so points & corners align."""
    idx = {h: i for i, h in enumerate(full["md5"].values)}
    coords = {a: full[a].values for a in axes}
    norm = {a: (np.percentile(coords[a], 0.2), np.percentile(coords[a], 99.8)) for a in axes}
    rows = [idx[h] for h in sample_md5 if h in idx]
    pts = {a: np.round(_norm01(coords[a][rows], norm[a]), 4).tolist() for a in axes}
    pts["md5"] = [sample_md5[i] for i in range(len(sample_md5)) if sample_md5[i] in idx]
    pts["c"] = [color_md5.get(h, 0.5) for h in pts["md5"]]
    pts["cap"] = [cap_map.get(h, "") for h in pts["md5"]]
    # corner markers: position = mean of nearest songs' coords (normalized)
    cmark = {a: [] for a in axes}
    cmark["cap"], cmark["md5"] = [], []
    for cap, songs in corners:
        present = [s for s in songs if s in idx]
        if not present:
            continue
        for a in axes:
            cmark[a].append(round(float(_norm01(
                np.mean([coords[a][idx[s]] for s in present]), norm[a])), 4))
        cmark["cap"].append(cap)
        cmark["md5"].append(present[0])      # closest real song = what plays
    # generation-seed targets: big magenta stars at their own coords
    tmark = {a: [] for a in axes}
    tmark["label"], tmark["md5"] = [], []
    for md5, label in targets:
        if md5 not in idx:
            continue
        for a in axes:
            tmark[a].append(round(float(_norm01(coords[a][idx[md5]], norm[a])), 4))
        tmark["label"].append(label)
        tmark["md5"].append(md5)
    return {"pts": pts, "corners": cmark, "targets": tmark}


def _load_corners(spec):
    """corners as [(caption, [md5,...])]. spec: 'pitch' (corners_blends.parquet),
    'drum' (drum_emptyspace/drum_corners.csv), or 'none'."""
    if spec == "none":
        return []
    if spec == "drum":
        p = os.path.join(ROOT, "_work", "drum_emptyspace", "drum_corners.csv")
        if not os.path.exists(p):
            return []
        df = pd.read_csv(p)
        return [(r["caption"], str(r["songs"]).split(";")) for _, r in df.iterrows()]
    cdf = pd.read_parquet(os.path.join(OUT, "corners_blends.parquet"))
    return [(r["midpoint_caption"], r["nearest_songs"].split(";")) for _, r in cdf.iterrows()]


def _space_label(umap_file, color_col):
    """Human-readable description of what the DOT POSITIONS mean (not the colour)."""
    if "drum" in umap_file:
        layout = "DRUM-FEEL space — positions = 72-D DrumDNA (groove/rhythm)"
    else:
        layout = "PITCH/HARMONY space — positions = 74-D signature (pitch+melody+harmony)"
    return f"{layout}  ·  colour (tint only) = {color_col}"


def build_space(sample, color_col, umap_file="umap2.parquet", corners_spec="pitch",
                space_label=""):
    cl = pd.read_parquet(os.path.join(OUT, "clusters.parquet"))
    sm = pd.read_parquet(os.path.join(OUT, "cluster_summary.parquet"))[["cluster_id", "caption"]]
    cap_map = cl.merge(sm, on="cluster_id", how="left").set_index("md5")["caption"].fillna("").to_dict()
    m = pd.read_parquet(os.path.join(ROOT, "catalog", "metadata.parquet"),
                        columns=["md5", color_col]).drop_duplicates("md5")
    c = pd.to_numeric(m[color_col], errors="coerce")
    clo, chi = np.nanpercentile(c, 2), np.nanpercentile(c, 98)
    cn = np.clip((c - clo) / (chi - clo + 1e-9), 0, 1).fillna(0.5)
    color_md5 = dict(zip(m["md5"].values, np.round(cn.values, 3)))

    corners = _load_corners(corners_spec)

    targets = _load_targets()
    target_md5 = {m for m, _ in targets}

    u2 = pd.read_parquet(os.path.join(OUT, umap_file))
    which = "UMAP-drum" if "drum" in umap_file else "UMAP"
    rng = np.random.default_rng(0)
    allmd5 = u2["md5"].values
    take = rng.choice(len(allmd5), size=min(sample, len(allmd5)), replace=False)
    sample_md5 = [allmd5[i] for i in sorted(take)]
    # force-include the seed targets so they always render
    have = set(sample_md5)
    sample_md5 += [m for m in allmd5 if m in target_md5 and m not in have]

    STATE["which"] = which
    STATE["color_col"] = color_col
    STATE["space_label"] = space_label or _space_label(umap_file, color_col)
    STATE["2d"] = _build_dim(u2, ["x", "y"], sample_md5, color_md5, cap_map, corners, targets)
    n3 = os.path.join(OUT, umap_file.replace("umap2", "umap3"))
    if os.path.exists(n3):
        u3 = pd.read_parquet(n3)
        STATE["3d"] = _build_dim(u3, ["x", "y", "z"], sample_md5, color_md5, cap_map, corners, targets)
        has3 = len(STATE["3d"]["pts"]["md5"])
    else:
        STATE["3d"] = None; has3 = 0
    print(f"[map] {which} · {len(STATE['2d']['pts']['md5']):,} pts 2D / {has3:,} 3D · "
          f"{len(STATE['2d']['corners']['cap'])} corner markers · "
          f"{len(STATE['2d']['targets']['md5'])} targets · colour={color_col}")


def build_duel_pool():
    """A clean, listenable, pretty-ish pool of distinct songs (one per song_id) for
    Taste Duel. Proxy-beauty filter (quality ok, valid bpm, has melody, decently
    diatonic, reasonable length) so neither side of a duel is junk."""
    cl = pd.read_parquet(os.path.join(OUT, "clusters.parquet"))
    sm = pd.read_parquet(os.path.join(OUT, "cluster_summary.parquet"))[["cluster_id", "caption"]]
    cap = cl.merge(sm, on="cluster_id", how="left").set_index("md5")["caption"].to_dict()
    cols = ["md5", "song_id", "quality_flag", "bpm_valid", "duration_suspect",
            "has_melody", "diatonic_ratio", "duration_sec", "is_canonical"]
    m = pd.read_parquet(os.path.join(ROOT, "catalog", "metadata.parquet"),
                        columns=[c for c in cols if c is not None])
    q = m[(m.get("quality_flag") == "ok") & (m.get("bpm_valid") == 1) &
          (m.get("duration_suspect") == 0) & (m.get("has_melody") == 1) &
          (m.get("diatonic_ratio") >= 0.5) & m.duration_sec.between(20, 600)]
    if "is_canonical" in q.columns:               # one file per song where we can
        q = q.sort_values("is_canonical", ascending=False)
    q = q.drop_duplicates("song_id")
    pool = q["md5"].tolist()
    STATE["pool"] = pool
    STATE["dcap"] = cap
    STATE["duel_count"] = sum(1 for _ in open(DUELS)) if os.path.exists(DUELS) else 0
    print(f"[duel] pool {len(pool):,} clean distinct songs · "
          f"{STATE['duel_count']} duels logged so far")


def pick_pair():
    pool = STATE["pool"]
    a = random.choice(pool); b = random.choice(pool)
    while b == a:
        b = random.choice(pool)
    cap = STATE["dcap"]
    return {"a": {"md5": a, "cap": cap.get(a, "") or ""},
            "b": {"md5": b, "cap": cap.get(b, "") or ""}}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Music-space map — click a star to hear it</title>
<script type="importmap">{ "imports": { "spessasynth_core": "/web/vendor/spessasynth_core.js" } }</script>
<style>
 html,body{margin:0;background:#07080d;color:#cfd6e6;font:13px/1.4 system-ui,sans-serif;overflow:hidden}
 #c{display:block;cursor:crosshair}
 #hud{position:fixed;top:10px;left:12px;max-width:46ch;z-index:5;pointer-events:none}
 #hud b{color:#fff} .pill{background:#11151f;border:1px solid #232a3a;border-radius:6px;padding:6px 9px;display:inline-block;margin-top:6px}
 #now{position:fixed;bottom:12px;left:12px;right:12px;z-index:5;background:#11151fcc;border:1px solid #2a3346;border-radius:8px;padding:8px 11px}
 #now .cap{color:#9fe7c4} #now .md5{color:#6b7587;font-size:11px}
 #tip{position:fixed;z-index:9;background:#0c1018ee;border:1px solid #2a3346;border-radius:6px;padding:5px 8px;pointer-events:none;display:none;max-width:40ch}
 .k{color:#7f8aa3} #stop{pointer-events:auto;cursor:pointer;color:#ff8a8a;border:1px solid #5a2a2a;border-radius:5px;padding:2px 8px;background:#1a0f12;float:right}
 #like{pointer-events:auto;cursor:pointer;color:#ff7eb6;border:1px solid #5a2a44;border-radius:5px;padding:2px 8px;background:#1a0f16;float:right;margin-right:8px}
 #like.on{background:#7a1f4f;color:#fff}
</style></head><body>
<canvas id=c></canvas>
<div id=hud><div><b id=spacelabel>—</b> · <span id=n></span> songs</div>
 <div class=pill>🔊 <select id=sf style="background:#11151f;color:#cfd6e6;border:1px solid #232a3a;border-radius:5px;pointer-events:auto"></select> · <span class=k>positions = the space above · colour is only a tint · drag to pan · wheel · click a star</span></div></div>
<div id=tip></div>
<div id=now><span id=stop>■ stop</span><span id=like>♡ like</span><div class=cap id=ncap>— click a star —</div><div class=md5 id=nmd5></div></div>
<script type="module">
const D = await (await fetch('/points.json')).json();
document.getElementById('spacelabel').textContent = D.space_label || D.which;
document.getElementById('n').textContent = D.pts.md5.length.toLocaleString();
const P = D.pts, N = P.md5.length;
const C = D.corners||{x:[],y:[],cap:[],md5:[]}, NC = (C.cap||[]).length;
const T = D.targets||{x:[],y:[],label:[],md5:[]}, NT = (T.label||[]).length;
let likes = new Set(); fetch('/likes').then(r=>r.json()).then(a=>{likes=new Set(a); draw();});
let nowMd5 = null;
const cv = document.getElementById('c'), g = cv.getContext('2d');
let W,H; function resize(){ W=cv.width=innerWidth; H=cv.height=innerHeight; draw(); }
addEventListener('resize', resize);
// view transform: world(0..1) -> screen
let view = {s: Math.min(innerWidth,innerHeight)*0.86, ox: 0, oy: 0};
function recenter(){ view.ox = (innerWidth - view.s)/2; view.oy = (innerHeight - view.s)/2; }
function sx(x){ return x*view.s + view.ox; } function sy(y){ return (1-y)*view.s + view.oy; }
let hi = -1, hiC = -1, playIdx = -1;   // hoisted: draw() reads these at first paint (avoid TDZ)
// viridis-ish ramp
function col(t){ const r=Math.round(255*Math.min(1,Math.max(0, -0.2+2.6*t-1.3*t*t)));
  const gg=Math.round(255*Math.min(1,Math.max(0,0.1+0.95*t)));
  const b=Math.round(255*Math.min(1,Math.max(0,0.6-0.7*t+0.5*(1-t)*(1-t)))); return `rgb(${r},${gg},${b})`; }
function draw(){
  g.fillStyle='#07080d'; g.fillRect(0,0,W,H);
  for(let i=0;i<N;i++){ const X=sx(P.x[i]), Y=sy(P.y[i]);
    if(X<-5||X>W+5||Y<-5||Y>H+5) continue;
    g.fillStyle = col(P.c[i]); g.globalAlpha=0.62;
    g.fillRect(X,Y,2,2);
  }
  g.globalAlpha=1;
  // liked stars: pink ring
  g.strokeStyle='#ff7eb6'; g.lineWidth=1.4;
  for(let i=0;i<N;i++){ if(likes.has(P.md5[i])){ const X=sx(P.x[i]),Y=sy(P.y[i]);
    if(X>-5&&X<W+5&&Y>-5&&Y<H+5){ g.beginPath(); g.arc(X,Y,4,0,7); g.stroke(); } } }
  // EMPTY CORNERS: white ✕ targets (the unwritten music)
  for(let k=0;k<NC;k++){ const X=sx(C.x[k]), Y=sy(C.y[k]);
    if(X<-8||X>W+8||Y<-8||Y>H+8) continue;
    g.strokeStyle = (hiC===k)?'#fff':'#ffd34d'; g.lineWidth=(hiC===k)?2.4:1.6;
    g.beginPath(); g.moveTo(X-5,Y-5); g.lineTo(X+5,Y+5); g.moveTo(X+5,Y-5); g.lineTo(X-5,Y+5); g.stroke();
    g.globalAlpha=0.5; g.beginPath(); g.arc(X,Y,9,0,7); g.stroke(); g.globalAlpha=1; }
  // GENERATION-SEED TARGETS: big magenta stars + labels (the songs we'll seed into)
  for(let k=0;k<NT;k++){ const X=sx(T.x[k]), Y=sy(T.y[k]);
    if(X<-20||X>W+20||Y<-20||Y>H+20) continue;
    g.fillStyle='#ff37d2'; g.globalAlpha=0.95;
    g.beginPath();
    for(let s=0;s<10;s++){ const ang=-Math.PI/2+s*Math.PI/5, rad=(s%2?3.2:8);
      const px=X+Math.cos(ang)*rad, py=Y+Math.sin(ang)*rad; s?g.lineTo(px,py):g.moveTo(px,py); }
    g.closePath(); g.fill();
    g.strokeStyle='#fff'; g.lineWidth=1.2; g.stroke();
    g.globalAlpha=1; g.fillStyle='#ffd1f4'; g.font='11px ui-monospace,monospace';
    g.fillText(T.label[k]||'', X+11, Y+4); }
  if(hi>=0){ const X=sx(P.x[hi]), Y=sy(P.y[hi]);
    g.strokeStyle='#fff'; g.lineWidth=1.5; g.beginPath(); g.arc(X,Y,6,0,7); g.stroke(); }
  if(playIdx>=0){ const X=sx(P.x[playIdx]), Y=sy(P.y[playIdx]);
    g.strokeStyle='#9fe7c4'; g.lineWidth=2; g.beginPath(); g.arc(X,Y,8,0,7); g.stroke(); }
}
recenter(); resize();
// hit test (screen-space nearest within radius)
function pick(mx,my){ let best=-1, bd=49; for(let i=0;i<N;i++){ const dx=sx(P.x[i])-mx, dy=sy(P.y[i])-my; const d=dx*dx+dy*dy; if(d<bd){bd=d;best=i;} } return best; }
function pickCorner(mx,my){ let best=-1, bd=121; for(let k=0;k<NC;k++){ const dx=sx(C.x[k])-mx, dy=sy(C.y[k])-my; const d=dx*dx+dy*dy; if(d<bd){bd=d;best=k;} } return best; }
// pan + zoom
let drag=null;
cv.addEventListener('mousedown',e=>{ drag={x:e.clientX,y:e.clientY,ox:view.ox,oy:view.oy,moved:false}; });
addEventListener('mouseup',e=>{ if(drag && !drag.moved){
    const k=pickCorner(e.clientX,e.clientY);
    if(k>=0) playCorner(k); else { const i=pick(e.clientX,e.clientY); if(i>=0) playSong(i); }
  } drag=null; });
addEventListener('mousemove',e=>{
  if(drag){ view.ox=drag.ox+(e.clientX-drag.x); view.oy=drag.oy+(e.clientY-drag.y);
    if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>3) drag.moved=true; draw(); return; }
  const tip=document.getElementById('tip');
  const k=pickCorner(e.clientX,e.clientY);
  const i = k<0 ? pick(e.clientX,e.clientY) : -1;
  if(k!==hiC||i!==hi){ hiC=k; hi=i; draw(); }
  if(k>=0){ tip.style.display='block'; tip.style.left=(e.clientX+12)+'px'; tip.style.top=(e.clientY+12)+'px';
    tip.innerHTML='<b style="color:#ffd34d">✕ EMPTY CORNER</b><br><b>'+(C.cap[k]||'')+'</b><br><span class=k>unwritten — click to hear the closest real song</span>'; }
  else if(i>=0){ tip.style.display='block'; tip.style.left=(e.clientX+12)+'px'; tip.style.top=(e.clientY+12)+'px';
    tip.innerHTML='<b>'+(P.cap[i]||'(no caption)')+'</b><br><span class=k>'+P.md5[i].slice(0,12)+'… — click to play</span>'; }
  else tip.style.display='none';
});
cv.addEventListener('wheel',e=>{ e.preventDefault(); const f=e.deltaY<0?1.12:1/1.12;
  const wx=(e.clientX-view.ox)/view.s, wy=(e.clientY-view.oy)/view.s;
  view.s*=f; view.ox=e.clientX-wx*view.s; view.oy=e.clientY-wy*view.s; draw(); },{passive:false});

// ---- audio: reuse the vendored spessasynth engine ----
const VER='1'; let _mod=null, ctx=null, synth=null, seq=null, ready=false, loaded=null, curSF='TimGM6mb.sf2';
async function ensureAudio(){
  if(ready) return;
  _mod = await import('/web/vendor/spessasynth_lib.js?v='+VER);
  const AC = window.AudioContext||window.webkitAudioContext; ctx=new AC();
  await ctx.audioWorklet.addModule('/web/vendor/spessasynth_processor.min.js?v='+VER);
  synth = new _mod.WorkletSynthesizer(ctx);
  synth.connect(ctx.destination);
  const buf = await (await fetch('/soundfont?sf='+encodeURIComponent(curSF))).arrayBuffer();
  await synth.soundBankManager.addSoundBank(buf,'main');
  await synth.isReady;
  seq = new _mod.Sequencer(synth); ready=true;
}
(async()=>{ const list=await (await fetch('/soundfonts')).json(); curSF=list[0].file;
  const sel=document.getElementById('sf'); if(!sel) return;
  sel.innerHTML=list.map(s=>'<option value="'+s.file+'">'+s.label+'</option>').join('');
  sel.onchange=async()=>{ curSF=sel.value; if(ready){ const b=await (await fetch('/soundfont?sf='+encodeURIComponent(curSF))).arrayBuffer(); await synth.soundBankManager.addSoundBank(b,'main'); } };
})();
async function playMd5(md5, cap){
  nowMd5=md5;
  document.getElementById('ncap').textContent = cap||'(no caption)';
  document.getElementById('nmd5').textContent = md5;
  setLike();
  try{
    await ensureAudio(); await ctx.resume();
    if(loaded!==md5){ const midi=await (await fetch('/midi/'+md5)).arrayBuffer();
      seq.loadNewSongList([{binary:midi, fileName:md5+'.mid'}]); loaded=md5; }
    seq.currentTime=0; seq.play();
  }catch(e){ document.getElementById('nmd5').textContent='audio error: '+e; console.error(e); }
}
function playSong(i){ playIdx=i; hiC=-1; draw(); return playMd5(P.md5[i], P.cap[i]); }
function playCorner(k){ playIdx=-1; draw();
  return playMd5(C.md5[k], '✕ near empty corner — '+(C.cap[k]||'')); }
function setLike(){ const b=document.getElementById('like');
  const on = nowMd5 && likes.has(nowMd5); b.classList.toggle('on',on); b.textContent = on?'♥ liked':'♡ like'; }
document.getElementById('like').onclick=()=>{
  if(!nowMd5) return;
  likes.add(nowMd5); setLike(); draw();
  fetch('/like',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({md5:nowMd5,src:'map'})}).catch(()=>{});
};
document.getElementById('stop').onclick=()=>{ if(seq){ seq.pause(); } playIdx=-1; draw(); };
</script></body></html>"""


DUEL_PAGE = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Taste Duel — which do you love more?</title>
<script type="importmap">{ "imports": { "spessasynth_core": "/web/vendor/spessasynth_core.js" } }</script>
<style>
 :root{color-scheme:dark}
 html,body{margin:0;height:100%;background:#07080d;color:#e7ecf6;font:15px/1.45 system-ui,sans-serif}
 .wrap{max-width:880px;margin:0 auto;padding:14px 14px 30px;text-align:center}
 h1{font-size:19px;margin:10px 0 2px} .sub{color:#7f8aa3;font-size:13px;margin-bottom:14px}
 .count{color:#9fe7c4;font-weight:600}
 .cards{display:flex;gap:14px;justify-content:center;align-items:stretch}
 .card{flex:1;background:#0e1320;border:1px solid #232c40;border-radius:14px;padding:16px 14px;display:flex;flex-direction:column;gap:12px;min-height:180px}
 .tag{font-weight:700;font-size:13px;letter-spacing:.1em;color:#6b7587}
 .play{font-size:34px;width:74px;height:74px;border-radius:50%;border:2px solid #2f7a55;background:#0f2419;color:#9fe7c4;cursor:pointer;align-self:center;transition:.1s}
 .play:hover{background:#14361f} .play.on{background:#1b6b3f;color:#fff;border-color:#39d27e}
 .cap{font-size:13px;color:#c7d0e2;min-height:34px} .md5{font-size:10px;color:#5a6378}
 .pickrow{display:flex;gap:12px;margin-top:18px;justify-content:center}
 .pick{flex:1;max-width:230px;padding:15px;border-radius:12px;border:1px solid #2a3346;background:#141a28;color:#e7ecf6;font-size:16px;font-weight:600;cursor:pointer}
 .pick:hover{background:#1c2436;border-color:#3a78ff}
 .pick.A:hover{border-color:#ff7eb6} .pick.B:hover{border-color:#7ee0ff}
 .skip{margin-top:12px;background:none;border:none;color:#6b7587;cursor:pointer;font-size:13px;text-decoration:underline}
 .hint{margin-top:16px;color:#5a6378;font-size:12px}
 .vs{align-self:center;color:#46506a;font-weight:700;padding:0 4px}
 .flash{animation:fl .4s} @keyframes fl{0%{background:#1b6b3f}100%{}}
</style></head><body><div class=wrap>
 <h1>🎧 Taste Duel</h1>
 <div class=sub>Play both. Pick the one <b>you</b> love more. <span class=count id=count>0</span> duels &middot; building your taste.</div>
 <div class=sub>🔊 sound: <select id=sf style="background:#0e1320;color:#cfd6e6;border:1px solid #2a3346;border-radius:5px;padding:2px 4px"></select></div>
 <div class=cards>
   <div class=card id=cardA><div class=tag>A</div>
     <button class=play id=playA>▶</button>
     <div class=cap id=capA>—</div><div class=md5 id=md5A></div></div>
   <div class=vs>vs</div>
   <div class=card id=cardB><div class=tag>B</div>
     <button class=play id=playB>▶</button>
     <div class=cap id=capB>—</div><div class=md5 id=md5B></div></div>
 </div>
 <div class=pickrow>
   <button class="pick A" id=pickA>❤ A wins</button>
   <button class="pick B" id=pickB>B wins ❤</button>
 </div>
 <button class=skip id=skip>skip / can't decide →</button>
 <div class=hint>keys: <b>←</b> A wins &middot; <b>→</b> B wins &middot; <b>↓</b> skip &middot; <b>A</b>/<b>L</b> play A/B</div>
</div>
<script type="module">
let cur=null, count=0;
const $=id=>document.getElementById(id);
// ---- synth (reuse vendored spessasynth) ----
const VER='1'; let _mod=null, ctx=null, synth=null, seq=null, ready=false, loaded=null, playing=null, curSF=null;
async function ensureAudio(){
  if(ready) return;
  _mod=await import('/web/vendor/spessasynth_lib.js?v='+VER);
  ctx=new (window.AudioContext||window.webkitAudioContext)();
  await ctx.audioWorklet.addModule('/web/vendor/spessasynth_processor.min.js?v='+VER);
  synth=new _mod.WorkletSynthesizer(ctx); synth.connect(ctx.destination);
  const sf=await (await fetch('/soundfont?sf='+encodeURIComponent(curSF))).arrayBuffer();
  await synth.soundBankManager.addSoundBank(sf,'main'); await synth.isReady;
  seq=new _mod.Sequencer(synth); ready=true;
}
async function swapSF(file){
  curSF=file;
  if(!ready) return;
  const sf=await (await fetch('/soundfont?sf='+encodeURIComponent(file))).arrayBuffer();
  await synth.soundBankManager.addSoundBank(sf,'main');
}
(async()=>{ const list=await (await fetch('/soundfonts')).json(); curSF=list[0].file;
  const sel=document.getElementById('sf');
  sel.innerHTML=list.map(s=>'<option value="'+s.file+'">'+s.label+'</option>').join('');
  sel.onchange=()=>swapSF(sel.value);
})();
async function playSide(side){
  const md5 = side==='a'?cur.a.md5:cur.b.md5;
  await ensureAudio(); await ctx.resume();
  if(loaded!==md5){ const mid=await (await fetch('/midi/'+md5)).arrayBuffer();
    seq.loadNewSongList([{binary:mid,fileName:md5+'.mid'}]); loaded=md5; }
  seq.currentTime=0; seq.play(); playing=side; paint();
}
function stop(){ if(seq) seq.pause(); playing=null; paint(); }
function paint(){
  $('playA').classList.toggle('on', playing==='a');
  $('playB').classList.toggle('on', playing==='b');
  $('playA').textContent = playing==='a'?'❚❚':'▶';
  $('playB').textContent = playing==='b'?'❚❚':'▶';
}
async function loadPair(){
  stop(); loaded=null;
  cur=await (await fetch('/duel/pair')).json();
  $('capA').textContent=cur.a.cap||'(no description)';
  $('capB').textContent=cur.b.cap||'(no description)';
  $('md5A').textContent=cur.a.md5.slice(0,12)+'…';
  $('md5B').textContent=cur.b.md5.slice(0,12)+'…';
}
async function pick(which){
  if(!cur) return;
  const body={a:cur.a.md5,b:cur.b.md5,pick:which};
  fetch('/duel/pick',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{ count=d.count; $('count').textContent=count; });
  if(which!=='skip'){ count++; $('count').textContent=count;
    const c=$(which==='a'?'cardA':'cardB'); c.classList.remove('flash'); void c.offsetWidth; c.classList.add('flash'); }
  loadPair();
}
$('playA').onclick=()=>playing==='a'?stop():playSide('a');
$('playB').onclick=()=>playing==='b'?stop():playSide('b');
$('pickA').onclick=()=>pick('a'); $('pickB').onclick=()=>pick('b'); $('skip').onclick=()=>pick('skip');
addEventListener('keydown',e=>{
  if(e.key==='ArrowLeft')pick('a'); else if(e.key==='ArrowRight')pick('b');
  else if(e.key==='ArrowDown')pick('skip');
  else if(e.key==='a'||e.key==='A')(playing==='a'?stop():playSide('a'));
  else if(e.key==='l'||e.key==='L')(playing==='b'?stop():playSide('b'));
});
loadPair();
</script></body></html>"""


GALAXY_PAGE = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Galaxy — fly through your music</title>
<script type="importmap">{ "imports": {
  "three": "/vendor3d/three.module.min.js",
  "spessasynth_core": "/web/vendor/spessasynth_core.js" } }</script>
<style>
 html,body{margin:0;height:100%;background:#03040a;color:#dfe6f2;font:13px/1.4 system-ui,sans-serif;overflow:hidden}
 #hud{position:fixed;top:10px;left:12px;z-index:5;max-width:48ch}
 #hud b{color:#fff} .pill{background:#0c1220cc;border:1px solid #243049;border-radius:7px;padding:7px 10px;display:inline-block;margin-top:6px}
 select{background:#0c1220;color:#cfd6e6;border:1px solid #243049;border-radius:5px}
 .k{color:#7f8aa3}
 #now{position:fixed;bottom:12px;left:12px;right:12px;z-index:5;background:#0c1220cc;border:1px solid #243049;border-radius:8px;padding:8px 11px}
 #now .cap{color:#9fe7c4} #now .md5{color:#6b7587;font-size:11px}
 #stop,#like{cursor:pointer;border-radius:5px;padding:2px 9px;float:right;margin-left:8px}
 #stop{color:#ff8a8a;border:1px solid #5a2a2a;background:#1a0f12}
 #like{color:#ff7eb6;border:1px solid #5a2a44;background:#1a0f16} #like.on{background:#7a1f4f;color:#fff}
 #tip{position:fixed;z-index:9;background:#060912ee;border:1px solid #2a3346;border-radius:6px;padding:5px 8px;pointer-events:none;display:none;max-width:42ch}
 a{color:#7fb0ff}
</style></head><body>
<div id=hud><div><b>🌌 Galaxy</b> · <span id=n></span> stars · <span id=which></span></div>
 <div class=pill>colour=<b id=cc></b> · 🔊 <select id=sf></select><br>
   <span class=k>drag=orbit · scroll=zoom · right-drag=pan · click a star to play · ✕=empty corner</span> · <a href="/">2D map</a></div></div>
<div id=tip></div>
<div id=now><span id=stop>■ stop</span><span id=like>♡ like</span>
  <div class=cap id=ncap>— click a star to hear it —</div><div class=md5 id=nmd5></div></div>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from '/vendor3d/OrbitControls.js';
const D = await (await fetch('/points3.json')).json();
const P=D.pts, N=P.md5.length, C=D.corners||{x:[],y:[],z:[],cap:[],md5:[]}, NC=(C.cap||[]).length;
document.getElementById('n').textContent=N.toLocaleString();
document.getElementById('which').textContent=D.which+' 3D';
document.getElementById('cc').textContent=D.color_col;
let likes=new Set(); fetch('/likes').then(r=>r.json()).then(a=>likes=new Set(a));
const SPAN=120;
function vir(t){ return [Math.min(1,Math.max(0,-0.2+2.6*t-1.3*t*t)),
  Math.min(1,Math.max(0,0.1+0.95*t)), Math.min(1,Math.max(0,0.6-0.7*t+0.5*(1-t)*(1-t)))]; }
const scene=new THREE.Scene(); scene.background=new THREE.Color(0x03040a);
const cam=new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 0.1, 4000);
cam.position.set(0,0,SPAN*1.7);
const rend=new THREE.WebGLRenderer({antialias:true}); rend.setPixelRatio(devicePixelRatio);
rend.setSize(innerWidth,innerHeight); document.body.appendChild(rend.domElement);
const ctrl=new OrbitControls(cam, rend.domElement); ctrl.enableDamping=true; ctrl.dampingFactor=0.08;
ctrl.autoRotate=true; ctrl.autoRotateSpeed=0.35;
// star cloud
const pos=new Float32Array(N*3), col=new Float32Array(N*3);
for(let i=0;i<N;i++){ pos[i*3]=(P.x[i]-0.5)*SPAN; pos[i*3+1]=(P.y[i]-0.5)*SPAN; pos[i*3+2]=(P.z[i]-0.5)*SPAN;
  const c=vir(P.c[i]); col[i*3]=c[0]; col[i*3+1]=c[1]; col[i*3+2]=c[2]; }
const geo=new THREE.BufferGeometry();
geo.setAttribute('position',new THREE.BufferAttribute(pos,3));
geo.setAttribute('color',new THREE.BufferAttribute(col,3));
const mat=new THREE.PointsMaterial({size:0.8,vertexColors:true,sizeAttenuation:true,transparent:true,opacity:0.85});
const cloud=new THREE.Points(geo,mat); scene.add(cloud);
// empty-corner markers (bright yellow, additive glow)
let cornObj=null;
if(NC){ const cp=new Float32Array(NC*3);
  for(let k=0;k<NC;k++){ cp[k*3]=(C.x[k]-0.5)*SPAN; cp[k*3+1]=(C.y[k]-0.5)*SPAN; cp[k*3+2]=(C.z[k]-0.5)*SPAN; }
  const cg=new THREE.BufferGeometry(); cg.setAttribute('position',new THREE.BufferAttribute(cp,3));
  cornObj=new THREE.Points(cg,new THREE.PointsMaterial({size:3.6,color:0xffd34d,sizeAttenuation:true,
    transparent:true,opacity:0.95,blending:THREE.AdditiveBlending,depthWrite:false}));
  scene.add(cornObj); }
addEventListener('resize',()=>{ cam.aspect=innerWidth/innerHeight; cam.updateProjectionMatrix(); rend.setSize(innerWidth,innerHeight); });
// raycast pick
const ray=new THREE.Raycaster(); ray.params.Points.threshold=1.2;
const mouse=new THREE.Vector2();
function intersect(ev){ mouse.x=(ev.clientX/innerWidth)*2-1; mouse.y=-(ev.clientY/innerHeight)*2+1;
  ray.setFromCamera(mouse,cam);
  let hitC=cornObj?ray.intersectObject(cornObj):[]; if(hitC.length) return {type:'corner',idx:hitC[0].index};
  let hit=ray.intersectObject(cloud); if(hit.length) return {type:'star',idx:hit[0].index}; return null; }
// click vs orbit-drag
let down=null;
rend.domElement.addEventListener('pointerdown',e=>down={x:e.clientX,y:e.clientY});
rend.domElement.addEventListener('pointerup',e=>{
  if(down && Math.abs(e.clientX-down.x)+Math.abs(e.clientY-down.y)<5){
    const h=intersect(e); if(h){ ctrl.autoRotate=false; h.type==='corner'?playCorner(h.idx):playStar(h.idx); } }
  down=null; });
rend.domElement.addEventListener('mousemove',e=>{ const h=intersect(e); const tip=document.getElementById('tip');
  if(h){ tip.style.display='block'; tip.style.left=(e.clientX+12)+'px'; tip.style.top=(e.clientY+12)+'px';
    tip.innerHTML = h.type==='corner'
      ? '<b style="color:#ffd34d">✕ EMPTY CORNER</b><br><b>'+(C.cap[h.idx]||'')+'</b><br><span class=k>unwritten — click for closest real song</span>'
      : '<b>'+(P.cap[h.idx]||'(no caption)')+'</b><br><span class=k>'+P.md5[h.idx].slice(0,12)+'… — click to play</span>';
    rend.domElement.style.cursor='pointer'; }
  else { tip.style.display='none'; rend.domElement.style.cursor='grab'; } });
(function loop(){ requestAnimationFrame(loop); ctrl.update(); rend.render(scene,cam); })();

// ---- audio (reuse vendored spessasynth) ----
const VER='1'; let _mod=null,actx=null,synth=null,seq=null,ready=false,loaded=null,curSF='TimGM6mb.sf2',nowMd5=null;
async function ensureAudio(){ if(ready)return;
  _mod=await import('/web/vendor/spessasynth_lib.js?v='+VER);
  actx=new (window.AudioContext||window.webkitAudioContext)();
  await actx.audioWorklet.addModule('/web/vendor/spessasynth_processor.min.js?v='+VER);
  synth=new _mod.WorkletSynthesizer(actx); synth.connect(actx.destination);
  const sf=await (await fetch('/soundfont?sf='+encodeURIComponent(curSF))).arrayBuffer();
  await synth.soundBankManager.addSoundBank(sf,'main'); await synth.isReady; seq=new _mod.Sequencer(synth); ready=true; }
async function playMd5(md5,cap){ nowMd5=md5;
  document.getElementById('ncap').textContent=cap||'(no caption)';
  document.getElementById('nmd5').textContent=md5; setLike();
  try{ await ensureAudio(); await actx.resume();
    if(loaded!==md5){ const m=await (await fetch('/midi/'+md5)).arrayBuffer(); seq.loadNewSongList([{binary:m,fileName:md5+'.mid'}]); loaded=md5; }
    seq.currentTime=0; seq.play();
  }catch(e){ document.getElementById('nmd5').textContent='audio error: '+e; console.error(e); } }
function playStar(i){ return playMd5(P.md5[i],P.cap[i]); }
function playCorner(k){ return playMd5(C.md5[k],'✕ near empty corner — '+(C.cap[k]||'')); }
function setLike(){ const b=document.getElementById('like'); const on=nowMd5&&likes.has(nowMd5);
  b.classList.toggle('on',on); b.textContent=on?'♥ liked':'♡ like'; }
document.getElementById('like').onclick=()=>{ if(!nowMd5)return; likes.add(nowMd5); setLike();
  fetch('/like',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({md5:nowMd5,src:'galaxy'})}).catch(()=>{}); };
document.getElementById('stop').onclick=()=>{ if(seq)seq.pause(); };
(async()=>{ const list=await (await fetch('/soundfonts')).json(); curSF=list[0].file;
  const sel=document.getElementById('sf'); sel.innerHTML=list.map(s=>'<option value="'+s.file+'">'+s.label+'</option>').join('');
  sel.onchange=async()=>{ curSF=sel.value; if(ready){ const b=await (await fetch('/soundfont?sf='+encodeURIComponent(curSF))).arrayBuffer(); await synth.soundBankManager.addSoundBank(b,'main'); } }; })();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, ctype, body, extra=None):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def _file(self, path, ctype):
        if not os.path.isfile(path): return self._send(404, "text/plain", b"404")
        with open(path, "rb") as f: self._send(200, ctype, f.read())

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/" or p == "/index.html":
            return self._send(200, "text/html; charset=utf-8", PAGE.encode())
        if p == "/duel":
            return self._send(200, "text/html; charset=utf-8", DUEL_PAGE.encode())
        if p == "/duel/pair":
            return self._send(200, "application/json", json.dumps(pick_pair()).encode())
        if p == "/points.json":
            d = STATE["2d"]
            body = json.dumps({"which": STATE["which"], "color_col": STATE["color_col"],
                               "space_label": STATE.get("space_label",""),
                               "pts": d["pts"], "corners": d["corners"],
                               "targets": d.get("targets", {})}, default=float).encode()
            return self._send(200, "application/json", body)
        if p == "/points3.json":
            if not STATE.get("3d"):
                return self._send(404, "application/json", b'{"error":"3d not ready"}')
            d = STATE["3d"]
            body = json.dumps({"which": STATE["which"], "color_col": STATE["color_col"],
                               "space_label": STATE.get("space_label",""),
                               "pts": d["pts"], "corners": d["corners"],
                               "targets": d.get("targets", {})}, default=float).encode()
            return self._send(200, "application/json", body)
        if p == "/likes":
            return self._send(200, "application/json", json.dumps(sorted(_load_likes())).encode())
        if p == "/galaxy":
            return self._send(200, "text/html; charset=utf-8", GALAXY_PAGE.encode())
        if p.startswith("/vendor3d/"):
            return self._file(os.path.join(OUT, "vendor3d", os.path.basename(p)),
                              "application/javascript")
        if p == "/soundfonts":
            return self._send(200, "application/json",
                              json.dumps([{"label": l, "file": f} for l, f in SOUNDFONTS]).encode())
        if p == "/soundfont":
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query)
            name = (q.get("sf") or [SOUNDFONTS[0][1]])[0]
            if name not in {f for _, f in SOUNDFONTS}:   # only known files
                name = SOUNDFONTS[0][1]
            return self._file(os.path.join(ASSETS, name), "application/octet-stream")
        if p.startswith("/web/vendor/"):
            name = os.path.basename(p)
            return self._file(os.path.join(VENDOR, name), "application/javascript")
        if p.startswith("/midi/"):
            md5 = os.path.basename(p)
            if len(md5) < 32 or not all(ch in "0123456789abcdef" for ch in md5[:32]):
                return self._send(400, "text/plain", b"bad")
            return self._file(os.path.join(ROOT, "MIDIs", md5[:2], md5 + ".mid"),
                              "audio/midi")
        return self._send(404, "text/plain", b"404")

    def do_POST(self):
        p = self.path.split("?", 1)[0]
        if p == "/like":
            n = int(self.headers.get("Content-Length", 0))
            try:
                d = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, "text/plain", b"bad json")
            md5 = (d.get("md5") or "")[:32]
            if len(md5) != 32:
                return self._send(400, "text/plain", b"bad md5")
            with _dlock:
                with open(LIKES, "a") as f:
                    f.write(json.dumps({"ts": round(time.time(), 1), "md5": md5,
                                        "src": d.get("src", "map")}) + "\n")
            likes = _load_likes()
            return self._send(200, "application/json",
                              json.dumps({"ok": True, "count": len(likes)}).encode())
        if p == "/duel/pick":
            n = int(self.headers.get("Content-Length", 0))
            try:
                d = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, "text/plain", b"bad json")
            a, b, pk = d.get("a"), d.get("b"), d.get("pick")
            if not (a and b and pk in ("a", "b", "skip")):
                return self._send(400, "text/plain", b"bad pick")
            rec = {"ts": round(time.time(), 1), "a": a, "b": b, "pick": pk,
                   "winner": (a if pk == "a" else b if pk == "b" else None),
                   "loser":  (b if pk == "a" else a if pk == "b" else None)}
            with _dlock:
                with open(DUELS, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                if pk != "skip":
                    STATE["duel_count"] = STATE.get("duel_count", 0) + 1
            return self._send(200, "application/json",
                              json.dumps({"ok": True, "count": STATE.get("duel_count", 0)}).encode())
        return self._send(404, "text/plain", b"404")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--sample", type=int, default=40000)
    ap.add_argument("--color", default="syncopation")
    ap.add_argument("--umap", default="umap2.parquet",
                    help="embedding parquet in _work/emptyspace (e.g. umap2_drums.parquet)")
    ap.add_argument("--corners", default="pitch", choices=["pitch", "drum", "none"])
    ap.add_argument("--space-label", default="",
                    help="override the header's plain-English space description")
    a = ap.parse_args()
    build_space(a.sample, a.color, a.umap, a.corners, a.space_label)
    build_duel_pool()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"[map]    2D    : http://127.0.0.1:{a.port}/")
    print(f"[galaxy] 3D    : http://127.0.0.1:{a.port}/galaxy")
    print(f"[duel]   game  : http://127.0.0.1:{a.port}/duel   (Ctrl-C to stop)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
