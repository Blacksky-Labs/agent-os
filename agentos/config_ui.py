"""The config page — served at ``/config``. Shows the **running entity's** real
configuration and lets you live-swap the model layer (any locally-available
model, temperature, max tokens) — written to a config overlay and applied on the
next message. The database layer shows SQLite (active) with Postgres/Prism
grayed out until they come online. Includes a Danger zone reset (wipe history).
Vanilla JS, no build step.
"""

from __future__ import annotations

CONFIG_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentOS — Config</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#060608;--panel:#101014;--panel2:#0c0c10;--border:#1a1a22;--border2:#262630;--white:#f0eeea;--dim:#9a968f;--faint:#524e50;--green:#c8f060;--cloud:#a0c8ff;--red:#f0607a}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--white);font-family:'DM Mono',monospace;font-size:13px;line-height:1.6}
a{color:inherit;text-decoration:none}
nav{display:flex;align-items:center;justify-content:space-between;padding:0 32px;height:56px;border-bottom:1px solid var(--border);position:sticky;top:0;background:rgba(6,6,8,.96);backdrop-filter:blur(12px);z-index:10}
.brand{font-family:'Syne',sans-serif;font-weight:800;letter-spacing:.1em;text-transform:uppercase;font-size:14px}
.brand span{color:var(--green)}
.tabs{display:flex;align-items:center;gap:20px;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.tabs a:hover{color:var(--white)}
.tabs a.active{color:var(--green)}
.wrap{padding:32px;max-width:980px;margin:0 auto}
.head{display:flex;align-items:center;gap:12px;margin-bottom:32px}
.head .name{font-family:'Syne',sans-serif;font-weight:800;font-size:30px;letter-spacing:-.02em}
.head .ns{font-size:11px;color:var(--faint);letter-spacing:.08em}
.note{font-size:12px;color:var(--dim);border:1px solid var(--border2);border-left:2px solid var(--cloud);padding:10px 14px;margin-bottom:28px}
.layer{border:1px solid var(--border);background:var(--panel2);margin-bottom:1px}
.layer-h{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--border)}
.layer-h .t{font-family:'Syne',sans-serif;font-weight:700;font-size:15px}
.layer-h .soon{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);border:1px solid var(--border2);padding:2px 8px;border-radius:2px}
.layer-h .soon.live{color:var(--green);border-color:rgba(200,240,96,.3)}
.layer-b{padding:18px}
.row{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--border);font-size:12px}
.row:last-child{border-bottom:none}
.row .k{color:var(--faint);letter-spacing:.06em}
.pill{display:inline-block;font-size:11px;color:var(--cloud);border:1px solid rgba(160,200,255,.3);padding:2px 8px;border-radius:2px;margin:0 4px 4px 0}
.chip{display:inline-block;font-size:11px;padding:4px 10px;border-radius:3px;border:1px solid;margin:0 6px 6px 0;cursor:pointer;user-select:none}
.chip.on{color:var(--green);border-color:rgba(200,240,96,.4);background:rgba(200,240,96,.06)}
.chip.off{color:var(--faint);border-color:var(--border2);text-decoration:line-through}
.chip.lock{cursor:default;color:var(--green);border-color:rgba(200,240,96,.25);opacity:.6}
.field{margin:12px 0}
.field label{display:block;font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:5px}
select,input{background:var(--panel);color:var(--white);border:1px solid var(--border2);border-radius:3px;padding:8px 10px;font-family:inherit;font-size:12px;width:100%;max-width:320px}
select:disabled,input:disabled{color:var(--faint)}
.model-bar{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;margin:14px 0}
.model-bar .ctl{display:flex;flex-direction:column}
.model-bar .ctl.grow{flex:1;min-width:220px}
.model-bar label{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin-bottom:5px}
.model-bar select{width:100%;max-width:none}
.model-bar input{width:108px}
select option:disabled{color:var(--faint)}
.actions{margin-top:14px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.btn{background:var(--green);color:#0a0a0c;border:none;border-radius:3px;padding:9px 18px;font-family:inherit;font-size:12px;font-weight:500;letter-spacing:.04em;cursor:pointer}
.btn:hover{opacity:.9}
.link{cursor:pointer;color:var(--faint);font-size:11px;letter-spacing:.04em}
.link:hover{color:var(--white)}
.status{font-size:11px;color:var(--green);min-height:15px}
.muted{color:var(--faint);font-size:11px;margin-top:8px}
.danger{border:1px solid rgba(240,96,122,.4);background:rgba(240,96,122,.04);margin-top:32px}
.danger .layer-h{border-color:rgba(240,96,122,.3)}
.danger .t{color:var(--red)}
.btn-danger{background:transparent;color:var(--red);border:1px solid rgba(240,96,122,.5);border-radius:3px;padding:9px 16px;font-family:inherit;font-size:12px;letter-spacing:.06em;cursor:pointer}
.btn-danger:hover{background:rgba(240,96,122,.12)}
.reset-status{font-size:12px;color:var(--green);margin-top:10px;min-height:16px}
#mode-chips .chip{cursor:pointer}
.erow{display:flex;align-items:center;gap:12px;padding:6px 2px;border-bottom:1px solid var(--border);font-size:12px}
.erow:last-child{border-bottom:none}
.erow .ename{color:var(--green);min-width:110px}
.erow .emodel{color:var(--cloud);min-width:150px;font-size:11px}
.erow .edesc{color:var(--dim);flex:1;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.erow .ex{color:var(--red);cursor:pointer;padding:0 6px;user-select:none;font-size:14px}
.erow .ex:hover{color:#ff8098}
</style>
</head>
<body>
<nav>
  <div class="brand">Agent<span>OS</span></div>
  <div class="tabs">
    <a href="/dashboard">Overview</a>
    <a href="/config" class="active">Config</a>
    <a href="/db">DB</a>
    <a href="/">Chat →</a>
  </div>
</nav>
<div class="wrap">
  <div class="head"><span class="name" id="name">—</span><span class="ns" id="ns"></span></div>
  <div class="note">The model, dashboard, and reasoning layers are live — swap the model, swap the dashboard pack, switch between a single model and a mixture of experts, and add/remove expert mini-models; changes take effect on the next message (or, for the dashboard, the next time the Overview tab loads). Database swapping (Postgres, Prism) is planned. Changes are stored in a config overlay; the manifest stays untouched.</div>
  <div id="layers"></div>

  <div class="layer">
    <div class="layer-h"><span class="t">First-launch screen</span><span class="soon live">preview</span></div>
    <div class="layer-b">
      <div class="muted" style="margin:0 0 12px">See the slideshow that plays while the on-device model downloads — without waiting for a download.</div>
      <a class="btn" href="/loadscreen" style="display:inline-block;text-decoration:none">Preview load screen</a>
    </div>
  </div>

  <div class="layer danger">
    <div class="layer-h" id="danger-toggle" style="cursor:pointer">
      <span class="t"><span id="danger-caret">▸</span>&nbsp; Danger zone · reset</span>
      <span class="soon live">live</span>
    </div>
    <div class="layer-b" id="danger-body" style="display:none">
      <div>Delete the downloaded on-device model (~5 GB). Skipper re-downloads it on the next launch — which is when the load screen plays. Does not touch memory.</div>
      <div style="margin-top:14px"><button class="btn-danger" id="wipe-model-btn">Wipe on-device model</button></div>
      <div class="reset-status" id="wipe-model-status"></div>
      <hr style="border:none;border-top:1px solid var(--border);margin:20px 0">
      <div>Wipe all accumulated memory — conversation turns, Context Engine threads, and metrics. The entity starts newborn. This cannot be undone.</div>
      <div style="margin-top:14px"><button class="btn-danger" id="reset-btn">Delete history · reset entity</button></div>
      <div class="reset-status" id="reset-status"></div>
      <div class="muted">Does not touch the corpus / vector store or the manifest.</div>
    </div>
  </div>
</div>

<script>
const $ = s => document.querySelector(s);
async function getJSON(u){ const r = await fetch(u); return r.json(); }
let AGENT = null, MODELS = [], CFG = null, DASHBOARDS = [];

async function init(){
  let running = null;
  try { running = (await getJSON('/health')).running_agent; } catch(e){}
  if(!running){ try { running = ((await getJSON('/agents')).agents[0]||{}).name; } catch(e){} }
  if(!running){ $('#name').textContent='No agent running'; return; }
  AGENT = running;
  const [cfg, models, dashboards] = await Promise.all([
    getJSON('/agents/' + encodeURIComponent(running) + '/config'),
    getJSON('/models').catch(()=>({models:[]})),
    getJSON('/api/dashboards').catch(()=>[]),
  ]);
  CFG = cfg; MODELS = (models.models)||[]; DASHBOARDS = Array.isArray(dashboards)?dashboards:[];
  $('#name').textContent = cfg.display_name || cfg.name;
  $('#ns').textContent = 'namespace: ' + cfg.namespace + ' · v' + cfg.version;
  renderLayers(cfg);
}

function layer(title, bodyHTML, soon, live){
  const tag = soon ? `<span class="soon ${live?'live':''}">${soon}</span>` : '';
  return `<div class="layer"><div class="layer-h"><span class="t">${title}</span>${tag}</div><div class="layer-b">${bodyHTML}</div></div>`;
}

function modelControls(m){
  const cur = m.name || '';
  const known = MODELS.some(x => x.name === cur);
  let opts = '';
  if(cur && !known) opts += `<option value="${cur}" selected>${cur} · current</option>`;
  opts += MODELS.map(x => `<option value="${x.name}" ${x.name===cur?'selected':''}>${x.label||x.name}</option>`).join('');
  opts += `<option value="__custom__">Custom…</option>`;
  const avail = MODELS.length ? `${MODELS.length} model(s) available locally` : 'Ollama not reachable — current model + custom only';
  return `
    <div class="model-bar">
      <div class="ctl grow"><label>Model</label><select id="model-select">${opts}</select></div>
      <div class="ctl"><label>Temp</label><input id="model-temp" type="number" step="0.1" min="0" max="2" value="${m.temperature!=null?m.temperature:0.6}"></div>
      <div class="ctl"><label>Max tokens</label><input id="model-maxtok" type="number" step="64" min="64" value="${m.max_tokens!=null?m.max_tokens:1024}"></div>
      <button class="btn" id="model-apply">Apply</button>
    </div>
    <div id="custom-wrap" style="display:none;margin:0 0 10px"><input id="model-custom" placeholder="e.g. ollama/qwen2.5:7b  or  together_ai/..." style="max-width:420px"></div>
    <div class="actions" style="margin-top:0"><span class="muted" style="margin:0">${m.provider||'—'} · ${avail}</span><span class="link" id="model-reset">reset to manifest default</span><span class="status" id="model-status"></span></div>`;
}

function dbControls(c){
  const dbCells = (c.cells||[]).filter(x=>['memory','retrieval'].includes(x.name));
  const cells = dbCells.length
    ? dbCells.map(x=>`<div class="row"><span class="k">${x.name} <span style="color:var(--faint)">v${x.version||''}</span></span><span>${Object.keys(x.config||{}).length?JSON.stringify(x.config):'default'}</span></div>`).join('')
    : '';
  return `
    <div class="field"><label>Backend</label>
      <select id="db-select">
        <option value="sqlite" selected>SQLite · Lightweight — active</option>
        <option value="postgres" disabled>PostgreSQL — coming online soon</option>
        <option value="prism" disabled>Prism · AI-native — coming online soon</option>
      </select>
      <div class="muted">Postgres and Prism are grayed out until those backends come online.</div>
    </div>
    ${cells}`;
}

function dashboardControls(packs){
  if(!packs.length) return `<div class="muted">No dashboard packs found in /dashboards. Drop a pack folder there and reload.</div>`;
  const active = packs.find(p=>p._active) || packs[0];
  const opts = packs.map(p=>`<option value="${p.id}" ${p._active?'selected':''}>${p.name} · v${p.version}</option>`).join('');
  return `
    <div class="field"><label>Active dashboard</label>
      <select id="dash-select">${opts}</select>
      <div class="muted" id="dash-desc">${active.description||''}</div>
    </div>
    <div class="actions" style="margin-top:6px">
      <button class="btn" id="dash-apply">Apply</button>
      <span class="muted" style="margin:0">${packs.length} pack(s) for this agent · the Overview tab loads the active pack</span>
      <span class="status" id="dash-status"></span>
    </div>`;
}

const ESSENTIAL_CELLS = ['context-builder', 'llm-interface', 'moe'];

function reasoningControls(c){
  const cells = (c.cells||[]).filter(x=>!['memory','retrieval'].includes(x.name));
  const offCells = new Set(c.disabled_cells||[]);
  const offHooks = new Set(c.disabled_hooks||[]);
  const cellChips = cells.map(x=>{
    const locked = ESSENTIAL_CELLS.includes(x.name);
    const on = !offCells.has(x.name);
    const cls = locked ? 'chip lock' : ('chip ' + (on?'on':'off'));
    const tag = locked ? ' · core' : '';
    return `<span class="${cls}" data-type="cell" data-name="${x.name}" data-locked="${locked}" title="${locked?'core pipeline — always on':'click to toggle'}">${x.name}${tag}</span>`;
  }).join('') || '<span class="muted">none</span>';
  const handlers = [];
  Object.values(c.hooks||{}).forEach(arr => arr.forEach(h => { if(!handlers.includes(h)) handlers.push(h); }));
  const hookChips = handlers.length ? handlers.map(h=>{
    const on = !offHooks.has(h);
    return `<span class="chip ${on?'on':'off'}" data-type="hook" data-name="${h}" title="click to toggle">${h}</span>`;
  }).join('') : '<span class="muted">none</span>';

  const cb = (c.cells||[]).find(x=>x.name==='context-builder') || {};
  const mem = (c.cells||[]).find(x=>x.name==='memory') || {};
  const surface = (cb.config||{}).surface_threads !== false;          // default on
  const hist = ((mem.config||{}).max_history != null) ? (mem.config||{}).max_history : 20;

  const mode = c.reasoning_mode || 'single';
  window.MOE = JSON.parse(JSON.stringify(c.moe || {router_model:'', default:'', experts:[]}));
  const modeBlock = `
    <div class="field"><label>Reasoning mode</label>
      <div id="mode-chips">
        <span class="chip ${mode==='single'?'on':'off'}" data-mode="single" title="one model answers every turn">single model</span>
        <span class="chip ${mode==='moe'?'on':'off'}" data-mode="moe" title="a router picks one specialist expert per turn">mixture of experts</span>
      </div>
      <div class="muted">Single = the llm-interface cell. MoE = a small router picks one expert (each with its own model) per turn. Switching here swaps the generation slot live.</div>
    </div>
    <div id="moe-panel" style="${mode==='moe'?'':'display:none'}"></div>`;

  return `
    ${modeBlock}
    <div class="field"><label>Engines · cells</label><div id="cell-chips">${cellChips}</div></div>
    <div class="field"><label>Hooks</label><div id="hook-chips">${hookChips}</div></div>
    <div class="actions" style="margin-top:6px"><button class="btn" id="reason-apply">Apply toggles</button><span class="muted" style="margin:0">click a chip to toggle</span><span class="status" id="reason-status"></span></div>
    <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px;font-size:11px;color:var(--dim);line-height:1.7"><span style="color:var(--green)">core · always on:</span> context-builder assembles the prompt; the reasoning cell (llm-interface or moe) calls the model — disabling either means no reply. The entity model lives in the <span style="color:var(--white)">Model layer</span> above; per-expert models are set in the roster.</div>
    <div class="field" style="margin-top:14px"><label>Prompt assembly · context-builder</label>
      <div class="model-bar">
        <div class="ctl"><label>Surface ongoing threads</label><span class="chip ${surface?'on':'off'}" data-type="cb" id="cb-threads" title="inject the Context Engine's ongoing threads into the prompt">ongoing threads</span></div>
        <div class="ctl"><label>History window · turns</label><input id="cb-history" type="number" min="0" step="2" value="${hist}"></div>
        <button class="btn" id="cb-apply">Apply</button>
      </div>
      <span class="status" id="cb-status"></span>
    </div>`;
}

function renderMoe(){
  const p = $('#moe-panel'); if(!p) return;
  const m = window.MOE || {experts:[]};
  const rows = (m.experts||[]).map((e,i)=>`
    <div class="erow">
      <span class="ename">${e.name}${e.name===m.default?' · default':''}</span>
      <span class="emodel">${e.model||'(entity model)'}</span>
      <span class="edesc" title="${(e.description||'').replace(/"/g,'&quot;')}">${e.description||''}</span>
      <span class="ex" data-rm="${i}" title="remove expert">×</span>
    </div>`).join('') || '<div class="muted">no experts yet — add one below</div>';
  p.innerHTML = `
    <div class="field" style="margin-top:10px"><label>Router model · keep it small/fast</label>
      <input id="moe-router" value="${m.router_model||''}" placeholder="ollama/gemma4:e2b" style="max-width:320px"></div>
    <div class="field"><label>Experts · mini models</label><div id="erows">${rows}</div></div>
    <div class="model-bar">
      <div class="ctl"><label>name</label><input id="ex-name" placeholder="concise" style="width:120px"></div>
      <div class="ctl grow"><label>when to use</label><input id="ex-desc" placeholder="short factual answers"></div>
      <div class="ctl"><label>model</label><input id="ex-model" placeholder="ollama/gemma3:1b" style="width:180px"></div>
      <button class="btn" id="ex-add">Add</button>
    </div>
    <div class="actions" style="margin-top:6px"><button class="btn" id="moe-apply">Apply roster</button><span class="muted" style="margin:0">router + experts take effect on the next message</span><span class="status" id="moe-status"></span></div>`;
}

function renderLayers(c){
  const modePills = (c.modes||[]).length ? (c.modes||[]).map(x=>`<span class="pill" style="margin:0">${x}</span>`).join('') : '<span class="muted">none</span>';
  const modesLine = `<div class="layer"><div class="layer-h"><span class="t">Surfaces · modes</span><span style="display:flex;gap:6px">${modePills}</span></div></div>`;

  $('#layers').innerHTML =
    layer('Model layer', modelControls(c.model||{}), 'live', true) +
    layer('Database layer', dbControls(c), 'swap planned') +
    layer('Dashboard layer', dashboardControls(DASHBOARDS), 'live', true) +
    layer('Reasoning layer · pipeline', reasoningControls(c), 'live', true) +
    modesLine;
  renderMoe();
}

function selectedModel(){
  const v = $('#model-select').value;
  if(v === '__custom__') return { name: ($('#model-custom').value||'').trim() };
  const opt = MODELS.find(x => x.name === v);
  return opt ? { name: opt.name, provider: opt.provider, api_base: opt.api_base } : { name: v };
}

document.addEventListener('change', e => {
  if(e.target && e.target.id === 'model-select'){
    $('#custom-wrap').style.display = e.target.value === '__custom__' ? 'block' : 'none';
  }
  if(e.target && e.target.id === 'dash-select'){
    const p = DASHBOARDS.find(x => x.id === e.target.value);
    if(p && $('#dash-desc')) $('#dash-desc').textContent = p.description || '';
  }
});

document.addEventListener('click', async (e) => {
  const dz = e.target.closest && e.target.closest('#danger-toggle');
  if(dz){
    const b = $('#danger-body'); const open = b.style.display !== 'none';
    b.style.display = open ? 'none' : 'block';
    $('#danger-caret').textContent = open ? '▸' : '▾';
    return;
  }
  const modeChip = e.target.closest && e.target.closest('#mode-chips .chip');
  if(modeChip){
    try{ await fetch('/agents/'+encodeURIComponent(AGENT)+'/reasoning-mode',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:modeChip.dataset.mode})}); }catch(err){}
    location.reload(); return;
  }
  if(e.target.classList && e.target.classList.contains('ex') && e.target.dataset.rm!=null){
    window.MOE.experts.splice(parseInt(e.target.dataset.rm),1); renderMoe(); return;
  }
  if(e.target.classList && e.target.classList.contains('chip') && e.target.dataset.type && e.target.dataset.locked !== 'true'){
    e.target.classList.toggle('on'); e.target.classList.toggle('off');
    return;
  }
  const id = e.target && e.target.id;
  if(id === 'model-apply'){
    const m = selectedModel();
    if(!m.name){ $('#model-status').textContent = 'Enter a model name.'; return; }
    if(m.provider === undefined){
      if(m.name.startsWith('ollama/')){ m.provider = 'ollama'; m.api_base = 'http://localhost:11434'; }
      else { m.provider = m.name.split('/')[0]; }
    }
    m.temperature = parseFloat($('#model-temp').value);
    m.max_tokens = parseInt($('#model-maxtok').value);
    $('#model-status').textContent = 'Applying…';
    try{
      const d = await (await fetch('/agents/'+encodeURIComponent(AGENT)+'/model', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(m)})).json();
      $('#model-status').textContent = 'Applied: ' + ((d.model&&d.model.name)||m.name) + ' — effective on the next message.';
    }catch(err){ $('#model-status').textContent = 'Failed: ' + err.message; }
  }
  else if(id === 'model-reset'){
    $('#model-status').textContent = 'Resetting to manifest default…';
    try{ await fetch('/agents/'+encodeURIComponent(AGENT)+'/overrides', {method:'DELETE'}); }catch(err){}
    setTimeout(()=>location.reload(), 500);
  }
  else if(id === 'dash-apply'){
    const pack = $('#dash-select').value;
    $('#dash-status').textContent = 'Applying…';
    try{
      const r = await fetch('/api/dashboard', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({pack})});
      const d = await r.json();
      if(r.ok && d.active_dashboard_pack){
        DASHBOARDS.forEach(p => p._active = (p.id === d.active_dashboard_pack));
        $('#dash-status').textContent = 'Active: ' + (d.name||pack) + ' — open the Overview tab to see it.';
      } else {
        $('#dash-status').textContent = 'Failed: ' + (d.detail || ('HTTP ' + r.status));
      }
    }catch(err){ $('#dash-status').textContent = 'Failed: ' + err.message; }
  }
  else if(id === 'reason-apply'){
    const dc = [...document.querySelectorAll('#cell-chips .chip.off')].map(x=>x.dataset.name);
    const dh = [...document.querySelectorAll('#hook-chips .chip.off')].map(x=>x.dataset.name);
    $('#reason-status').textContent = 'Applying…';
    try{
      await fetch('/agents/'+encodeURIComponent(AGENT)+'/reasoning', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({disabled_cells:dc, disabled_hooks:dh})});
      $('#reason-status').textContent = 'Applied — effective on the next message.';
    }catch(err){ $('#reason-status').textContent = 'Failed: '+err.message; }
  }
  else if(id === 'cb-apply'){
    const surface = $('#cb-threads').classList.contains('on');
    const hist = parseInt($('#cb-history').value);
    $('#cb-status').textContent = 'Applying…';
    try{
      await fetch('/agents/'+encodeURIComponent(AGENT)+'/cell-config', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({cell:'context-builder', config:{surface_threads:surface}})});
      if(!isNaN(hist)) await fetch('/agents/'+encodeURIComponent(AGENT)+'/cell-config', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({cell:'memory', config:{max_history:hist}})});
      $('#cb-status').textContent = 'Applied — effective on the next message.';
    }catch(err){ $('#cb-status').textContent = 'Failed: '+err.message; }
  }
  else if(id === 'ex-add'){
    const name = ($('#ex-name').value||'').trim(); if(!name) return;
    window.MOE.experts = window.MOE.experts||[];
    window.MOE.router_model = ($('#moe-router').value||'').trim() || window.MOE.router_model;
    const exp = {name, description:($('#ex-desc').value||'').trim()};
    const mdl = ($('#ex-model').value||'').trim(); if(mdl) exp.model = mdl;
    window.MOE.experts.push(exp);
    if(!window.MOE.default) window.MOE.default = name;
    renderMoe();
  }
  else if(id === 'moe-apply'){
    window.MOE.router_model = ($('#moe-router').value||'').trim() || window.MOE.router_model;
    $('#moe-status').textContent = 'Applying…';
    try{
      await fetch('/agents/'+encodeURIComponent(AGENT)+'/reasoning-mode',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'moe', moe:window.MOE})});
      $('#moe-status').textContent = 'Applied — effective on the next message.';
    }catch(err){ $('#moe-status').textContent = 'Failed: '+err.message; }
  }
  else if(id === 'wipe-model-btn'){
    if(!confirm('Delete the downloaded on-device model (~5 GB)?\n\nSkipper re-downloads it on the next launch — that is when the load screen plays. Memory is untouched.')) return;
    e.target.disabled = true;
    $('#wipe-model-status').textContent = 'Wiping…';
    try{
      const r = await fetch('/system/model', {method:'DELETE'});
      const d = await r.json();
      if(r.ok){
        const gb = d.freed_bytes ? ' (' + (d.freed_bytes/1e9).toFixed(2) + ' GB freed)' : '';
        $('#wipe-model-status').textContent = d.wiped
          ? ('Model wiped' + gb + ' — quit and reopen Skipper to re-download.')
          : 'No model found on disk — already clear.';
      } else {
        $('#wipe-model-status').textContent = 'Failed: ' + (d.detail || ('HTTP ' + r.status));
      }
    }catch(err){ $('#wipe-model-status').textContent = 'Failed: ' + err.message; }
    e.target.disabled = false;
  }
  else if(id === 'reset-btn'){
    if(!AGENT) return;
    if(!confirm('Wipe ALL history for "'+AGENT+'"?\n\nDeletes conversation turns, Context Engine threads, and metrics. The entity starts newborn. This cannot be undone.')) return;
    e.target.disabled = true;
    try{
      const d = await (await fetch('/agents/'+encodeURIComponent(AGENT)+'/history', {method:'DELETE'})).json();
      $('#reset-status').textContent = d.wiped ? AGENT+' is newborn — all memory wiped.' : 'Nothing to wipe (no data yet).';
    }catch(err){ $('#reset-status').textContent = 'Reset failed: '+err.message; }
    e.target.disabled = false;
  }
});

init();
</script>
</body>
</html>
"""
