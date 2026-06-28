"""The DB explorer — served at ``/db``. A read-only window into the running
entity's per-namespace SQLite (``memory.db``): every table with its row count,
columns, and most-recent rows (turns, threads, turn_metrics, and anything else
that appears). Vanilla JS, no build step.
"""

from __future__ import annotations

DB_EXPLORER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentOS — DB Explorer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{--bg:#060608;--panel:#101014;--panel2:#0c0c10;--border:#1a1a22;--border2:#262630;--white:#f0eeea;--dim:#9a968f;--faint:#524e50;--green:#c8f060;--cloud:#a0c8ff}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--white);font-family:'DM Mono',monospace;font-size:13px;line-height:1.6}
a{color:inherit;text-decoration:none}
nav{display:flex;align-items:center;justify-content:space-between;padding:0 32px;height:56px;border-bottom:1px solid var(--border);position:sticky;top:0;background:rgba(6,6,8,.96);backdrop-filter:blur(12px);z-index:10}
.brand{font-family:'Syne',sans-serif;font-weight:800;letter-spacing:.1em;text-transform:uppercase;font-size:14px}
.brand span{color:var(--green)}
.tabs{display:flex;align-items:center;gap:20px;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.tabs a:hover{color:var(--white)}
.tabs a.active{color:var(--green)}
.wrap{padding:32px;max-width:1140px;margin:0 auto}
.head{display:flex;align-items:baseline;gap:12px;margin-bottom:8px}
.head .name{font-family:'Syne',sans-serif;font-weight:800;font-size:30px;letter-spacing:-.02em}
.path{font-size:11px;color:var(--faint);margin-bottom:28px;word-break:break-all}
.table-card{border:1px solid var(--border);background:var(--panel2);margin-bottom:24px}
.table-h{display:flex;align-items:center;gap:12px;padding:12px 16px;border-bottom:1px solid var(--border)}
.table-h .tn{font-family:'Syne',sans-serif;font-weight:700;font-size:15px}
.table-h .cnt{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--green);border:1px solid rgba(200,240,96,.3);padding:2px 8px;border-radius:2px}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:11px}
th{text-align:left;padding:8px 12px;color:var(--faint);letter-spacing:.06em;text-transform:uppercase;font-size:9px;border-bottom:1px solid var(--border);white-space:nowrap;position:sticky;top:0;background:var(--panel)}
td{padding:7px 12px;border-bottom:1px solid var(--border);color:var(--dim);white-space:nowrap;max-width:380px;overflow:hidden;text-overflow:ellipsis}
tr:hover td{color:var(--white);background:rgba(255,255,255,.015)}
.empty{color:var(--faint);font-size:12px;padding:24px 16px;text-align:center}
.refresh{cursor:pointer;color:var(--dim)}
.refresh:hover{color:var(--white)}
</style>
</head>
<body>
<nav>
  <div class="brand">Agent<span>OS</span></div>
  <div class="tabs">
    <a href="/dashboard">Overview</a>
    <a href="/config">Config</a>
    <a href="/db" class="active">DB</a>
    <a href="/">Chat →</a>
  </div>
</nav>
<div class="wrap">
  <div class="head"><span class="name" id="name">—</span><span class="refresh" id="refresh">↻ refresh</span></div>
  <div class="path" id="path"></div>
  <div id="tables"></div>
</div>

<script>
const $ = s => document.querySelector(s);
async function getJSON(u){ const r = await fetch(u); return r.json(); }
const trunc = v => { const s = v==null ? '∅' : String(v); return s.length>160 ? s.slice(0,160)+'…' : s; };
// Compact large numbers to 3 significant digits: 16234 -> 16.2k, 1.62M, 999 stays.
const fmt = n => {
  n = (n==null?0:Number(n));
  if(Math.abs(n) < 1000) return String(parseFloat(n.toFixed(1)));
  const units = ['k','M','B','T'];
  let u = -1, x = n;
  while(Math.abs(x) >= 1000 && u < units.length-1){ x/=1000; u++; }
  const a = Math.abs(x);
  let r = parseFloat(x.toFixed(a>=100?0:a>=10?1:2));
  if(Math.abs(r) >= 1000 && u < units.length-1){ r = parseFloat((r/1000).toFixed(2)); u++; }
  return r + units[u];
};
let AGENT = null;

async function init(){
  let running = null;
  try { running = (await getJSON('/health')).running_agent; } catch(e){}
  if(!running){ try { running = ((await getJSON('/agents')).agents[0]||{}).name; } catch(e){} }
  if(!running){ $('#name').textContent='No agent running'; return; }
  AGENT = running;
  load();
}

async function load(){
  $('#name').textContent = AGENT + ' · memory';
  const d = await getJSON('/agents/' + encodeURIComponent(AGENT) + '/db');
  $('#path').textContent = d.db_path || '';
  if(!d.exists){ $('#tables').innerHTML = '<div class="empty">No database yet — it appears after the first turn.</div>'; return; }
  if(!d.tables.length){ $('#tables').innerHTML = '<div class="empty">Database exists but has no tables yet.</div>'; return; }
  $('#tables').innerHTML = d.tables.map(t => {
    const head = '<tr>' + t.columns.map(c=>`<th>${c}</th>`).join('') + '</tr>';
    const body = t.rows.length
      ? t.rows.map(r=>'<tr>'+r.map(v=>`<td title="${(v==null?'':String(v)).replace(/"/g,'&quot;')}">${trunc(v)}</td>`).join('')+'</tr>').join('')
      : `<tr><td colspan="${t.columns.length}" class="empty">empty</td></tr>`;
    return `<div class="table-card">
      <div class="table-h"><span class="tn">${t.name}</span><span class="cnt">${fmt(t.count)} rows</span><span style="font-size:10px;color:var(--faint)">showing latest ${t.rows.length}</span></div>
      <div class="scroll"><table><thead>${head}</thead><tbody>${body}</tbody></table></div>
    </div>`;
  }).join('');
}

$('#refresh').addEventListener('click', load);
init();
</script>
</body>
</html>
"""
