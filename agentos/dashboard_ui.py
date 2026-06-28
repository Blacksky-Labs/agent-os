"""The backend dashboard — a single self-contained HTML page served at
``/dashboard``. Vanilla JS, no build step. Shows analytics for the **currently
running entity** (the one this process was started for, surfaced on /health):
activity, latency + token usage, top threads, and recent sessions.
"""

from __future__ import annotations

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentOS — Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#060608; --panel:#101014; --panel2:#0c0c10; --border:#1a1a22; --border2:#262630;
  --white:#f0eeea; --dim:#9a968f; --faint:#524e50; --green:#c8f060; --cloud:#a0c8ff;
}
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
.head{display:flex;align-items:center;gap:12px;margin-bottom:32px}
.head .name{font-family:'Syne',sans-serif;font-weight:800;font-size:30px;letter-spacing:-.02em}
.run{display:flex;align-items:center;gap:6px;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim);border:1px solid var(--border2);padding:4px 10px;border-radius:2px}
.run .dot{width:6px;height:6px;border-radius:50%;background:var(--green)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--border);border:1px solid var(--border);margin-bottom:40px}
.card{background:var(--panel2);padding:22px 20px}
.card .num{font-family:'Syne',sans-serif;font-weight:800;font-size:30px;letter-spacing:-.02em;color:var(--green)}
.card .lab{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin-top:6px}
.section-label{font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--faint);margin:0 0 16px;display:flex;align-items:center;gap:12px}
.section-label::after{content:'';flex:1;height:1px;background:var(--border)}
.grid2{display:grid;grid-template-columns:1.3fr 1fr;gap:24px;margin-bottom:40px}
.panel{border:1px solid var(--border);background:var(--panel2)}
.panel-h{padding:14px 18px;border-bottom:1px solid var(--border);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.panel-b{padding:18px}
.chart{display:flex;align-items:flex-end;gap:4px;height:120px}
.bar{flex:1;background:var(--green);opacity:.75;border-radius:2px 2px 0 0;min-height:2px;position:relative}
.bar:hover{opacity:1}
.chart-x{display:flex;justify-content:space-between;margin-top:8px;font-size:9px;color:var(--faint)}
.thread{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--border)}
.thread:last-child{border-bottom:none}
.thread .key{flex:1;font-size:13px}
.badge{font-size:8px;letter-spacing:.1em;text-transform:uppercase;padding:2px 6px;border-radius:2px;border:1px solid var(--border2);color:var(--faint)}
.badge.topic{color:var(--cloud);border-color:rgba(160,200,255,.3)}
.mentions{font-family:'Syne',sans-serif;font-weight:700;color:var(--green);font-size:14px;min-width:34px;text-align:right}
.sess{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);font-size:11px;color:var(--dim)}
.sess:last-child{border-bottom:none}
.sess .sid{color:var(--white)}
.empty{color:var(--faint);font-size:12px;padding:24px 0;text-align:center}
@media(max-width:820px){.grid2{grid-template-columns:1fr}}
</style>
</head>
<body>
<nav>
  <div class="brand">Agent<span>OS</span></div>
  <div class="tabs">
    <a href="/dashboard" class="active">Overview</a>
    <a href="/config">Config</a>
    <a href="/db">DB</a>
    <a href="/">Chat →</a>
  </div>
</nav>
<div class="wrap">
  <div class="head">
    <span class="name" id="agent-name">—</span>
    <span class="run"><span class="dot"></span>Running</span>
  </div>

  <div class="cards" id="cards"></div>

  <div class="grid2">
    <div class="panel">
      <div class="panel-h">Activity · messages per day</div>
      <div class="panel-b"><div class="chart" id="chart"></div><div class="chart-x" id="chart-x"></div></div>
    </div>
    <div class="panel">
      <div class="panel-h">Top threads · what they return to</div>
      <div class="panel-b" id="threads"></div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-h">Recent sessions</div>
    <div class="panel-b" id="sessions"></div>
  </div>
</div>

<script>
const $ = s => document.querySelector(s);
async function getJSON(u){ const r = await fetch(u); return r.json(); }
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

async function init(){
  let running = null;
  try { running = (await getJSON('/health')).running_agent; } catch(e){}
  if(!running){ try { running = ((await getJSON('/agents')).agents[0]||{}).name; } catch(e){} }
  if(!running){ $('#agent-name').textContent='No agent running'; return; }

  $('#agent-name').textContent = running;
  const s = await getJSON('/agents/' + encodeURIComponent(running) + '/stats');
  renderCards(s); renderChart(s.messages_by_day||[]); renderThreads(s.top_threads||[]); renderSessions(s.recent_sessions||[]);
}

function renderCards(s){
  const cards = [
    ['Messages', fmt(s.total_messages)],
    ['Sessions', fmt(s.sessions)],
    ['Avg / session', s.avg_messages_per_session],
    ['Avg latency · ms', fmt(s.avg_latency_ms)],
    ['Total tokens', fmt(s.total_tokens)],
    ['Threads tracked', fmt(s.threads)],
  ];
  $('#cards').innerHTML = cards.map(([l,v]) => `<div class="card"><div class="num">${v}</div><div class="lab">${l}</div></div>`).join('');
}

function renderChart(days){
  if(!days.length){ $('#chart').innerHTML='<div class="empty" style="width:100%">No activity yet.</div>'; $('#chart-x').innerHTML=''; return; }
  const max = Math.max(...days.map(d=>d.count), 1);
  $('#chart').innerHTML = days.map(d => `<div class="bar" style="height:${Math.round(d.count/max*100)}%" title="${d.date}: ${d.count}"></div>`).join('');
  $('#chart-x').innerHTML = `<span>${days[0].date.slice(5)}</span><span>${days[days.length-1].date.slice(5)}</span>`;
}

function renderThreads(threads){
  if(!threads.length){ $('#threads').innerHTML='<div class="empty">No threads yet — they build as the entity is used.</div>'; return; }
  $('#threads').innerHTML = threads.map(t => `<div class="thread"><span class="key">${t.key}</span><span class="badge ${t.kind}">${t.kind}</span><span class="mentions">${t.mentions}×</span></div>`).join('');
}

function renderSessions(sessions){
  if(!sessions.length){ $('#sessions').innerHTML='<div class="empty">No sessions yet.</div>'; return; }
  $('#sessions').innerHTML = sessions.map(s => `<div class="sess"><span class="sid">${s.session_id}</span><span>${s.messages} msgs</span><span>${(s.last||'').replace('T',' ').slice(0,16)}</span></div>`).join('');
}

init();
</script>
</body>
</html>
"""
