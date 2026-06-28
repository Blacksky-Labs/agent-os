"""The first-launch load screen — served at ``/loadscreen``.

A web mirror of the native SwiftUI slideshow (clients/AgentOSMac/SlideshowView.swift)
so the operator can preview it from the config page without wiping the model and
waiting for a re-download. Same images (served by the kernel from the bundled
``Slides/`` folder) and the same five quotes.

Self-contained: embedded CSS + JS, no build step. Quotes mirror ``Quote.all`` in
SlideshowView.swift — keep the two in sync.
"""

from __future__ import annotations

LOADSCREEN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skipper — load screen preview</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--void:#0A0F1E;--cyan:#00D4FF;--ink:#E8EEF6;--dim:#8A97AB;--faint:#4A5568}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--void);color:var(--ink);font-family:'Space Grotesk',system-ui,sans-serif;overflow:hidden}
#stage{position:fixed;inset:0}
.frame{position:absolute;inset:0;opacity:0;transition:opacity 1.1s ease;background-size:cover;background-position:center;transform:scale(1.0);}
.frame.on{opacity:1;transform:scale(1.08);transition:opacity 1.1s ease, transform 7s ease-out}
.scrim{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,.55),rgba(0,0,0,.05) 30%,rgba(0,0,0,.3) 62%,rgba(0,0,0,.88))}
.bar{position:absolute;top:0;left:0;right:0;display:flex;align-items:center;justify-content:space-between;padding:22px 30px}
.brand{display:flex;align-items:center;gap:9px;font-weight:700;letter-spacing:.14em;font-size:13px}
.brand .dot{width:8px;height:8px;border-radius:50%;background:var(--cyan);box-shadow:0 0 12px var(--cyan)}
.brand .sub{color:var(--dim);font-weight:400}
.back{color:rgba(255,255,255,.62);font-size:12.5px;text-decoration:none;border:1px solid rgba(255,255,255,.18);padding:7px 13px;border-radius:8px}
.back:hover{color:#fff;border-color:rgba(255,255,255,.4)}
.quote{position:absolute;left:44px;right:44px;bottom:118px;max-width:820px}
.quote .l1{font-size:42px;font-weight:600;line-height:1.12;text-shadow:0 4px 16px rgba(0,0,0,.5)}
.quote .l2{font-size:21px;color:rgba(255,255,255,.74);margin-top:10px;text-shadow:0 3px 12px rgba(0,0,0,.5)}
.foot{position:absolute;left:44px;right:44px;bottom:34px}
.shimmer{height:3px;border-radius:3px;background:rgba(255,255,255,.10);overflow:hidden;position:relative}
.shimmer::after{content:"";position:absolute;top:0;left:-38%;height:100%;width:38%;background:linear-gradient(90deg,transparent,var(--cyan),transparent);animation:slide 1.7s ease-in-out infinite}
@keyframes slide{0%{left:-38%}100%{left:100%}}
.status{margin-top:13px;font-size:12.5px;color:rgba(255,255,255,.62)}
.tag{display:inline-block;margin-top:10px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--faint);letter-spacing:.06em}
</style>
</head>
<body>
<div id="stage"></div>
<div class="scrim"></div>
<div class="bar">
  <div class="brand"><span class="dot"></span>SKIPPER&nbsp;<span class="sub">· AgentOS</span></div>
  <a class="back" href="/config">← Back to config</a>
</div>
<div class="quote"><div class="l1" id="l1">—</div><div class="l2" id="l2"></div></div>
<div class="foot">
  <div class="shimmer"></div>
  <div class="status" id="status">Preview — this is the screen that plays while your on-device model downloads.</div>
  <div class="tag" id="tag"></div>
</div>

<script>
"use strict";
const QUOTES = [
  ["The instruments are tuning.",     "Your symphony is moments away."],
  ["Intelligence, composed for one.", "Private, on-device, almost ready."],
  ["No cloud. No eavesdroppers.",     "Just you and a mind of your own."],
  ["One download, then never again.", "Brilliance, cached forever."],
  ["The conductor raises the baton…",  "AgentOS is ready to play."],
];
const GRADS = [
  "linear-gradient(140deg,#0A1020,#06303C)","linear-gradient(140deg,#120A1E,#3A1646)",
  "linear-gradient(140deg,#08161A,#0D4238)","linear-gradient(140deg,#1A0A0C,#4C1C12)",
  "linear-gradient(140deg,#0A0E20,#1A2A6E)","linear-gradient(140deg,#160A18,#5A2230)",
  "linear-gradient(140deg,#08161A,#0F3A52)","linear-gradient(140deg,#140E08,#4C3810)",
  "linear-gradient(140deg,#0A0A1E,#2E1656)","linear-gradient(140deg,#08151C,#003C42)",
];
const stage = document.getElementById("stage");
let images = [], frames = [], idx = 0, cur = null;

async function boot(){
  try{ const r = await fetch("/loadscreen/images"); images = (await r.json()).images || []; }catch(e){ images = []; }
  const n = images.length || QUOTES.length;
  document.getElementById("tag").textContent =
    images.length ? (images.length + " slides · " + QUOTES.length + " quotes") : "no images found — showing gradients";
  // build frame layers (cap DOM nodes; reuse two layers via background swap)
  for(let i=0;i<2;i++){ const d=document.createElement("div"); d.className="frame"; stage.appendChild(d); frames.push(d); }
  show(0, true);
  setInterval(()=>{ idx=(idx+1)% n; show(idx,false); }, 4500);
}
function bgFor(i){
  if(images.length){ return "url('/loadscreen/img/"+encodeURIComponent(images[i % images.length])+"')"; }
  return GRADS[i % GRADS.length];
}
function show(i, first){
  const incoming = frames[ (cur===frames[0])?1:0 ] || frames[0];
  const outgoing = cur;
  incoming.style.backgroundImage = bgFor(i);
  // restart Ken Burns
  incoming.classList.remove("on"); void incoming.offsetWidth; incoming.classList.add("on");
  if(outgoing && outgoing!==incoming) outgoing.classList.remove("on");
  cur = incoming;
  const q = QUOTES[i % QUOTES.length];
  const l1=document.getElementById("l1"), l2=document.getElementById("l2");
  l1.style.opacity=0; l2.style.opacity=0;
  setTimeout(()=>{ l1.textContent=q[0]; l2.textContent=q[1]; l1.style.transition=l2.style.transition="opacity .8s ease"; l1.style.opacity=1; l2.style.opacity=1; }, first?0:260);
}
boot();
</script>
</body>
</html>
"""
