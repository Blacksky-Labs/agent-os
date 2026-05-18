"""Minimal local chat UI for agentOS.

A single self-contained HTML page served by ``GET /``. Lets a tester pick
any scaffolded agent and chat with it via the existing ``POST /chat``
endpoint. No framework, no build step — vanilla HTML/CSS/JS.

This is testing scaffolding, not a product. Replace freely.
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
    .input textarea:focus {
      outline: none;
      border-color: var(--accent);
    }
    .input button {
      padding: 0 18px;
      background: var(--accent);
      color: #0a0a0c;
      border: 0;
      border-radius: 8px;
      font-weight: 600;
      cursor: pointer;
    }
    .input button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }
  </style>
</head>
<body>
  <div class="topbar">
    <span class="brand">agentOS</span>
    <select id="agent-select" disabled>
      <option>Loading agents…</option>
    </select>
    <span class="meta" id="agent-meta"></span>
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

    const sessionId = `s_${Math.random().toString(36).slice(2, 14)}`;
    let agents = {};   // {name: {display_name, provider, model}}

    function escapeHtml(s) {
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

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
        thinking.meta.textContent =
          renderMeta(data) + `  ·  ${wall}ms wall`;
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

    // --- wire ---
    sel.addEventListener("change", () => {
      setAgentMeta();
      // New session per agent so memory cells (when real) don't bleed.
      chat.innerHTML = "";
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

    loadAgents();
  </script>
</body>
</html>
"""
