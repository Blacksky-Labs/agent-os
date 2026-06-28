"""Minimal local chat UI for agentOS.

A single self-contained HTML page served by ``GET /``. Lets a tester:
    - pick any scaffolded agent
    - chat with it via ``POST /chat``
    - view the agent's corpus (sources + chunk counts)
    - ingest a file/folder by path
    - delete a source from the corpus

No framework, no build step — vanilla HTML/CSS/JS. Replace freely.
"""

from __future__ import annotations


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>agentOS</title>
  <style>
    :root {
      --bg:        #0e0e10;
      --panel:     #15151a;
      --panel-2:   #1f1f26;
      --border:    #2a2a33;
      --text:      #e6e6ea;
      --text-dim:  #888892;
      --accent:    #6ee7b7;
      --user-bg:   #1d2731;
      --agent-bg:  #1a1a22;
      --error:     #ff7a7a;
      --warn:      #f4c466;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text",
                   "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      flex-direction: column;
      height: 100vh;
    }
    button { font: inherit; cursor: pointer; }

    /* --- Topbar --- */
    .topbar {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 20px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }
    .topbar .brand {
      font-weight: 600;
      letter-spacing: 0.02em;
      color: var(--accent);
    }
    .topbar select {
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 14px;
      min-width: 240px;
    }
    .topbar .meta {
      color: var(--text-dim);
      font-size: 12px;
      margin-left: auto;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
    }
    .topbar .manage-btn {
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 13px;
    }
    .topbar .manage-btn.open { background: var(--accent); color: #0a0a0c; border-color: var(--accent); }

    /* --- Manage panel --- */
    .manage-panel {
      border-bottom: 1px solid var(--border);
      background: var(--panel);
      padding: 14px 20px 18px;
      display: none;
    }
    .manage-panel.open { display: block; }
    .manage-panel h3 {
      margin: 0 0 8px 0;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-dim);
    }
    .manage-panel .corpus-summary {
      font-size: 12px;
      color: var(--text-dim);
      margin-bottom: 8px;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
    }
    .corpus-list {
      list-style: none;
      margin: 0 0 12px 0;
      padding: 0;
      max-height: 220px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 6px;
    }
    .corpus-list li {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
    }
    .corpus-list li:last-child { border-bottom: 0; }
    .corpus-list li:hover { background: var(--panel-2); }
    .corpus-list .source {
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      font-size: 13px;
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .corpus-list .chunks {
      color: var(--text-dim);
      font-size: 12px;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      flex-shrink: 0;
    }
    .corpus-list .delete-btn {
      background: transparent;
      color: var(--error);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 3px 8px;
      font-size: 12px;
    }
    .corpus-list .delete-btn:hover { background: rgba(255, 122, 122, 0.1); }
    .corpus-empty {
      color: var(--text-dim);
      font-style: italic;
      font-size: 13px;
      padding: 12px;
      border: 1px dashed var(--border);
      border-radius: 6px;
      margin-bottom: 12px;
      text-align: center;
    }

    .ingest-row {
      display: flex;
      gap: 8px;
    }
    .ingest-row input {
      flex: 1;
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      font-size: 13px;
    }
    .ingest-row input:focus {
      outline: none;
      border-color: var(--accent);
    }
    .ingest-row button {
      background: var(--accent);
      color: #0a0a0c;
      border: 0;
      border-radius: 6px;
      padding: 0 16px;
      font-weight: 600;
      font-size: 13px;
    }
    .ingest-row button:disabled { opacity: 0.4; cursor: not-allowed; }
    .ingest-row .hint {
      color: var(--text-dim);
      font-size: 12px;
      align-self: center;
    }
    .pill {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 10px;
      border: 1px solid var(--border);
      font-size: 11px;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      color: var(--text-dim);
      flex-shrink: 0;
    }
    .pill.ok      { color: var(--accent); border-color: rgba(110, 231, 183, 0.4); }
    .pill.pending { color: var(--warn);   border-color: rgba(244, 196, 102, 0.4); }
    .status-line {
      margin-top: 8px;
      font-size: 12px;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      color: var(--text-dim);
      min-height: 16px;
    }
    .status-line.ok   { color: var(--accent); }
    .status-line.err  { color: var(--error); }
    .status-line.warn { color: var(--warn); }

    /* --- Chat --- */
    .chat {
      flex: 1;
      overflow-y: auto;
      padding: 24px 20px 12px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .chat:empty::before {
      content: "Pick an agent above, then send a message.";
      color: var(--text-dim);
      font-style: italic;
      align-self: center;
      margin-top: 40px;
    }
    .msg {
      display: flex;
      flex-direction: column;
      max-width: 760px;
      align-self: flex-start;
    }
    .msg.user { align-self: flex-end; align-items: flex-end; }
    .bubble {
      padding: 10px 14px;
      border-radius: 14px;
      border: 1px solid var(--border);
      white-space: pre-wrap;
      word-wrap: break-word;
      line-height: 1.45;
      font-size: 14px;
    }
    .msg.user .bubble  { background: var(--user-bg); }
    .msg.agent .bubble { background: var(--agent-bg); }
    .msg.agent.error .bubble { border-color: var(--error); color: var(--error); }
    .bubble.thinking { color: var(--text-dim); font-style: italic; }
    .footer-meta {
      font-size: 11px;
      color: var(--text-dim);
      margin-top: 4px;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
    }

    .input {
      display: flex;
      gap: 8px;
      padding: 12px 20px 16px;
      border-top: 1px solid var(--border);
      background: var(--panel);
    }
    .input textarea {
      flex: 1;
      resize: none;
      min-height: 38px;
      max-height: 140px;
      padding: 9px 12px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--panel-2);
      color: var(--text);
      font: inherit;
      font-size: 14px;
      line-height: 1.4;
    }
    .input textarea:focus { outline: none; border-color: var(--accent); }
    .input button {
      padding: 0 18px;
      background: var(--accent);
      color: #0a0a0c;
      border: 0;
      border-radius: 8px;
      font-weight: 600;
    }
    .input button:disabled { opacity: 0.4; cursor: not-allowed; }
  </style>
</head>
<body>
  <div class="topbar">
    <span class="brand">agentOS</span>
    <select id="agent-select" disabled>
      <option>Loading agents…</option>
    </select>
    <span class="meta" id="agent-meta"></span>
    <a class="manage-btn" href="/dashboard" style="text-decoration:none;display:inline-block;">Dashboard →</a>
    <button class="manage-btn" id="manage-toggle">📁 Manage</button>
  </div>

  <div class="manage-panel" id="manage-panel">
    <h3>Drop folder</h3>
    <div class="corpus-summary" id="drop-folder-summary">Loading…</div>
    <div id="drop-folder-container"></div>
    <div class="ingest-row" style="margin-top:8px;">
      <button id="ingest-folder-btn" class="primary">Ingest folder</button>
      <span class="hint" id="ingest-folder-hint"></span>
    </div>

    <h3 style="margin-top:18px;">Corpus for <span id="manage-agent-name">—</span></h3>
    <div class="corpus-summary" id="corpus-summary"></div>
    <div id="corpus-container"></div>

    <h3 style="margin-top:18px;">Advanced: ingest from any path</h3>
    <div class="ingest-row">
      <input id="ingest-path" placeholder="Absolute path on this machine, e.g. /Users/you/Documents/notes.md">
      <button id="ingest-btn">Ingest</button>
    </div>
    <div class="status-line" id="ingest-status"></div>
  </div>

  <div class="chat" id="chat"></div>

  <div class="input">
    <textarea id="input" placeholder="Message your agent — Enter to send, Shift+Enter for newline" rows="1"></textarea>
    <button id="send" disabled>Send</button>
  </div>

  <script>
    const $   = (id) => document.getElementById(id);
    const sel = $("agent-select");
    const inp = $("input");
    const btn = $("send");
    const chat = $("chat");
    const metaEl = $("agent-meta");
    const manageBtn = $("manage-toggle");
    const managePanel = $("manage-panel");
    const corpusContainer = $("corpus-container");
    const corpusSummary = $("corpus-summary");
    const manageAgentName = $("manage-agent-name");
    const ingestInput = $("ingest-path");
    const ingestBtn = $("ingest-btn");
    const ingestStatus = $("ingest-status");
    const dropFolderSummary = $("drop-folder-summary");
    const dropFolderContainer = $("drop-folder-container");
    const ingestFolderBtn = $("ingest-folder-btn");
    const ingestFolderHint = $("ingest-folder-hint");

    let currentDropFolder = null;     // relative path, e.g. "corpus/stan"

    let sessionId = `s_${Math.random().toString(36).slice(2, 14)}`;  // overridden by the kernel's active session on load
    let agents = {};

    function escapeHtml(s) {
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function basename(path) {
      if (!path) return "";
      const parts = path.split("/");
      return parts[parts.length - 1] || path;
    }

    function setStatus(el, text, kind) {
      el.textContent = text;
      el.classList.remove("ok", "err", "warn");
      if (kind) el.classList.add(kind);
    }

    // -------------------- Chat --------------------

    function appendMsg(who, text, opts = {}) {
      const wrap = document.createElement("div");
      wrap.className = `msg ${who}` + (opts.error ? " error" : "");
      const bubble = document.createElement("div");
      bubble.className = "bubble" + (opts.thinking ? " thinking" : "");
      bubble.textContent = text;
      wrap.appendChild(bubble);
      const meta = document.createElement("div");
      meta.className = "footer-meta";
      wrap.appendChild(meta);
      chat.appendChild(wrap);
      chat.scrollTop = chat.scrollHeight;
      return { wrap, bubble, meta };
    }

    function renderMeta(data) {
      const timings = data.cell_timings || {};
      const total = Object.values(timings).reduce((a, b) => a + (b || 0), 0);
      const usage = data.usage || {};
      const errs = Object.keys(data.cell_errors || {}).length;
      const parts = [];
      parts.push(`turn ${data.turn_id}`);
      parts.push(`${total}ms total`);
      if (usage.total_tokens) parts.push(`${usage.total_tokens} tokens`);
      if (errs > 0) parts.push(`${errs} cell error(s)`);
      return parts.join("  ·  ");
    }

    function setAgentMeta() {
      const a = agents[sel.value];
      if (!a) { metaEl.textContent = ""; return; }
      const bits = [];
      if (a.provider) bits.push(a.provider);
      if (a.model)    bits.push(a.model);
      metaEl.textContent = bits.join(" · ");
    }

    async function loadAgents() {
      try {
        const r = await fetch("/agents");
        const data = await r.json();
        sel.innerHTML = "";
        if (!data.agents || data.agents.length === 0) {
          const opt = document.createElement("option");
          opt.textContent = "(no agents — run `agentos new agent` first)";
          opt.disabled = true;
          sel.appendChild(opt);
          btn.disabled = true;
          return;
        }
        data.agents.forEach(a => {
          agents[a.name] = a;
          const opt = document.createElement("option");
          opt.value = a.name;
          opt.textContent = a.display_name
            ? `${a.name}  —  ${a.display_name}`
            : a.name;
          sel.appendChild(opt);
        });
        sel.disabled = false;
        btn.disabled = false;
        setAgentMeta();
      } catch (e) {
        const opt = document.createElement("option");
        opt.textContent = `(error loading agents: ${e.message})`;
        opt.disabled = true;
        sel.innerHTML = "";
        sel.appendChild(opt);
      }
    }

    async function send() {
      const text = inp.value.trim();
      if (!text || sel.disabled || btn.disabled) return;
      inp.value = "";
      inp.style.height = "auto";

      appendMsg("user", text);
      const thinking = appendMsg("agent", "…", { thinking: true });
      thinking.meta.textContent = `→ ${sel.value}`;
      btn.disabled = true;
      sel.disabled = true;

      const t0 = performance.now();
      try {
        const r = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            agent_name: sel.value,
            user_message: text,
            session_id: sessionId,
            mode: "web",
          }),
        });
        const data = await r.json();
        const wall = Math.round(performance.now() - t0);

        const errs = data.cell_errors || {};
        const hasError = Object.keys(errs).length > 0 || !data.response;

        if (hasError) {
          const errSummary = Object.entries(errs)
            .map(([cell, msg]) => `${cell}: ${msg}`)
            .join("\\n") || "(empty response, no cell errors)";
          thinking.wrap.classList.add("error");
          thinking.bubble.classList.remove("thinking");
          thinking.bubble.textContent = errSummary;
        } else {
          thinking.bubble.classList.remove("thinking");
          thinking.bubble.textContent = data.response;
        }
        thinking.meta.textContent = renderMeta(data) + `  ·  ${wall}ms wall`;
      } catch (e) {
        thinking.wrap.classList.add("error");
        thinking.bubble.classList.remove("thinking");
        thinking.bubble.textContent = `Request failed: ${e.message}`;
      } finally {
        btn.disabled = false;
        sel.disabled = false;
        inp.focus();
      }
    }

    // -------------------- Manage panel --------------------

    function renderCorpus(data) {
      manageAgentName.textContent = data.agent_name || sel.value || "—";
      currentDropFolder = data.drop_folder || null;

      // ---- Drop folder section ----
      const folderFiles = data.drop_folder_files || [];
      if (!data.drop_folder_exists) {
        dropFolderSummary.textContent =
          `${data.drop_folder} (not created yet — drop files in to populate)`;
      } else {
        const ingestedCount = folderFiles.filter(f => f.in_corpus).length;
        dropFolderSummary.textContent =
          `${data.drop_folder}  ·  ${folderFiles.length} file(s) in folder  ·  ${ingestedCount} ingested`;
      }
      ingestFolderHint.textContent = `(runs ingest on ${data.drop_folder}/)`;
      ingestFolderBtn.disabled = !data.drop_folder_exists || folderFiles.length === 0;

      if (folderFiles.length === 0) {
        dropFolderContainer.innerHTML =
          `<div class="corpus-empty">Drop .md, .txt, or .markdown files into ${escapeHtml(data.drop_folder_abs || data.drop_folder)}/, then click Ingest folder.</div>`;
      } else {
        const ulf = document.createElement("ul");
        ulf.className = "corpus-list";
        folderFiles.forEach(f => {
          const li = document.createElement("li");
          const label = document.createElement("span");
          label.className = "source";
          label.title = f.path;
          label.textContent = f.name;
          const pill = document.createElement("span");
          if (f.in_corpus) {
            pill.className = "pill ok";
            pill.textContent = `ingested · ${f.chunks} chunk${f.chunks === 1 ? "" : "s"}`;
          } else {
            pill.className = "pill pending";
            pill.textContent = "not ingested";
          }
          li.appendChild(label);
          li.appendChild(pill);
          ulf.appendChild(li);
        });
        dropFolderContainer.innerHTML = "";
        dropFolderContainer.appendChild(ulf);
      }

      // ---- Full corpus list (includes external sources too) ----
      const sources = data.sources || [];
      corpusSummary.textContent =
        `namespace ${data.namespace}  ·  ${data.total_chunks} chunk(s)  ·  ${sources.length} source(s)`;

      if (sources.length === 0) {
        corpusContainer.innerHTML =
          '<div class="corpus-empty">No documents ingested yet.</div>';
        return;
      }

      const ul = document.createElement("ul");
      ul.className = "corpus-list";
      sources.forEach(s => {
        const li = document.createElement("li");
        const label = document.createElement("span");
        label.className = "source";
        label.title = s.source;
        label.textContent = basename(s.source);

        const count = document.createElement("span");
        count.className = "chunks";
        count.textContent = `${s.chunks} chunk${s.chunks === 1 ? "" : "s"}`;

        const del = document.createElement("button");
        del.className = "delete-btn";
        del.textContent = "Delete";
        del.addEventListener("click", () => deleteSource(s.source));

        li.appendChild(label);
        li.appendChild(count);
        li.appendChild(del);
        ul.appendChild(li);
      });
      corpusContainer.innerHTML = "";
      corpusContainer.appendChild(ul);
    }

    async function ingestFolder() {
      if (!currentDropFolder) return;
      const agent = sel.value;
      ingestFolderBtn.disabled = true;
      setStatus(ingestStatus, `Ingesting ${currentDropFolder}/…`, "warn");
      try {
        const r = await fetch(`/agents/${encodeURIComponent(agent)}/ingest`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: currentDropFolder }),
        });
        const data = await r.json();
        if (!r.ok) {
          setStatus(ingestStatus, `Ingest failed: ${data.detail || r.statusText}`, "err");
          return;
        }
        const errs = (data.errors || []).length;
        const note = errs > 0 ? `  (${errs} warning(s))` : "";
        setStatus(
          ingestStatus,
          `✓ ${data.files || 0} file(s), ${data.chunks || 0} chunk(s) added, ${data.total_in_collection || 0} total${note}`,
          "ok"
        );
        await loadCorpus();
      } catch (e) {
        setStatus(ingestStatus, `Ingest failed: ${e.message}`, "err");
      } finally {
        ingestFolderBtn.disabled = false;
      }
    }

    async function loadCorpus() {
      const agent = sel.value;
      if (!agent) return;
      corpusContainer.innerHTML = '<div class="corpus-empty">Loading…</div>';
      try {
        const r = await fetch(`/agents/${encodeURIComponent(agent)}/corpus`);
        if (!r.ok) {
          const err = await r.json().catch(() => ({}));
          corpusContainer.innerHTML =
            `<div class="corpus-empty">Could not load corpus: ${escapeHtml(err.detail || r.statusText)}</div>`;
          corpusSummary.textContent = "";
          return;
        }
        renderCorpus(await r.json());
      } catch (e) {
        corpusContainer.innerHTML =
          `<div class="corpus-empty">Could not load corpus: ${escapeHtml(e.message)}</div>`;
      }
    }

    async function deleteSource(source) {
      if (!confirm(`Delete all chunks for "${basename(source)}"?\\n\\nFull path:\\n${source}`)) {
        return;
      }
      const agent = sel.value;
      const url = `/agents/${encodeURIComponent(agent)}/corpus?source=${encodeURIComponent(source)}`;
      try {
        const r = await fetch(url, { method: "DELETE" });
        const data = await r.json();
        if (!r.ok) {
          setStatus(ingestStatus, `Delete failed: ${data.detail || r.statusText}`, "err");
          return;
        }
        setStatus(ingestStatus, `Removed ${data.deleted_chunks} chunk(s) for ${basename(source)}`, "ok");
        await loadCorpus();
      } catch (e) {
        setStatus(ingestStatus, `Delete failed: ${e.message}`, "err");
      }
    }

    async function ingestPath() {
      const path = ingestInput.value.trim();
      if (!path) {
        setStatus(ingestStatus, "Enter a path first.", "warn");
        return;
      }
      const agent = sel.value;
      ingestBtn.disabled = true;
      setStatus(ingestStatus, `Ingesting ${path}… (this may take a few seconds for big files)`, "warn");
      try {
        const r = await fetch(`/agents/${encodeURIComponent(agent)}/ingest`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path }),
        });
        const data = await r.json();
        if (!r.ok) {
          setStatus(ingestStatus, `Ingest failed: ${data.detail || r.statusText}`, "err");
          return;
        }
        const errs = (data.errors || []).length;
        const note = errs > 0 ? `  (${errs} warning(s))` : "";
        setStatus(
          ingestStatus,
          `✓ ${data.files || 0} file(s), ${data.chunks || 0} chunk(s) added, ${data.total_in_collection || 0} total${note}`,
          "ok"
        );
        ingestInput.value = "";
        await loadCorpus();
      } catch (e) {
        setStatus(ingestStatus, `Ingest failed: ${e.message}`, "err");
      } finally {
        ingestBtn.disabled = false;
      }
    }

    function toggleManagePanel() {
      const isOpen = managePanel.classList.toggle("open");
      manageBtn.classList.toggle("open", isOpen);
      if (isOpen) {
        loadCorpus();
        setStatus(ingestStatus, "", null);
      }
    }

    // -------------------- Wire --------------------
    sel.addEventListener("change", () => {
      setAgentMeta();
      chat.innerHTML = "";
      if (managePanel.classList.contains("open")) loadCorpus();
    });
    btn.addEventListener("click", send);
    inp.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    inp.addEventListener("input", () => {
      inp.style.height = "auto";
      inp.style.height = Math.min(inp.scrollHeight, 140) + "px";
    });
    manageBtn.addEventListener("click", toggleManagePanel);
    ingestBtn.addEventListener("click", ingestPath);
    ingestFolderBtn.addEventListener("click", ingestFolder);
    ingestInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        ingestPath();
      }
    });

    loadAgents();
    // Adopt the kernel's active session: `agentos start` → fresh, `agentos resume` → last conversation.
    fetch("/health").then(r => r.json()).then(d => { if (d && d.active_session) sessionId = d.active_session; }).catch(() => {});
  </script>
</body>
</html>
"""
