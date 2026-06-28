# Skipper — Codebase Audit & Architecture Reconciliation

*Blacksky Labs / AgentOS | 2026-06-19*
*Companion to `native-client-plan.md` and the Skipper seed. Step 1 of the seed's "What CoWork Needs to Do."*
*Every claim below is verified against the actual code unless marked otherwise.*

---

## 0. TL;DR

- **AgentOS backend is real and runnable.** Clean cell-pipeline kernel, working `/chat` HTTP surface, SQLite memory, ChromaDB retrieval, LiteLLM inference.
- **Skipper's actual intelligence does not exist yet.** Capture / track / surface / seed, sentiment-weighted threads, and the sleep cycle are all aspirational. *That* is the real build — the platform under it is mostly done.
- **Gemma / MediaPipe / Whisper / Nuitka: zero in the stack.** All ahead.
- **There is no Node layer in AgentOS.** The only Node app is Axis's Next.js UI — a separate project. AgentOS's own UI is server-rendered Python HTML.
- **Mobile is greenfield.** No Swift, Xcode, or React Native anywhere.
- **Prism is a separate, Dockerized, server-side data platform** (Mongo→Postgres→Qdrant). It is not wired into AgentOS and should **not** be in the local-first Skipper MVP.
- **macOS-first (already chosen) is strongly validated** — it sidesteps the single biggest risk in the seed: running compiled Python inside the iOS sandbox.

---

## 1. Answers to the seed's five open questions

### Q1 — Current state of the AgentOS Python backend

| Component | State | Notes |
|---|---|---|
| Kernel (`context`, `pipeline`, `registry`, `config`, `hooks`, `observability`) | **Works** | Matches `SPEC.md`. Pipeline degrades gracefully on cell error. |
| HTTP surface (`agentos/main.py`) | **Works** | `POST /chat`, `GET /agents`, `GET /health`, corpus ingest/list/delete. |
| CLI (`agentos/cli.py`, Typer) | **Works** | `agentos new/start/…`; `start` → uvicorn on `127.0.0.1:7777`. |
| `mode-control` cell | **Works** | Simple: copies `persona.modes[mode]` → `mode_constraints`. |
| `memory` cell | **Works** | **SQLite**, one DB per namespace at `data/<ns>/memory.db` (`turns` table). Written post-turn by the `memory_persist` hook. |
| `retrieval` cell | **Works** | **ChromaDB** vectors; embeddings via Ollama `nomic-embed-text`. |
| `llm-interface` cell | **Works** | **LiteLLM** `acompletion`. Single inference point. |
| `ingestion` cell | **Stub** | No entity/sentiment extraction running today. |
| `context-builder` cell | Present | Assembles the prompt from persona + channels. |
| **Skipper entity logic** (threads, capture, surface, seed, sleep) | **Does not exist** | None of it is in the codebase. |

**Entry points:** `agentos start <agent>` → uvicorn serving `agentos.main:app` on port 7777; the core call is `POST /chat`.
**Databases in use today:** SQLite (memory) + ChromaDB (retrieval vectors). No Mongo/Postgres/Qdrant.

### Q2 — Is Gemma already in the stack?

**No.** Inference today is **LiteLLM** (cloud- or Ollama-routable); embeddings are Ollama `nomic-embed-text`. There are **zero** references to Gemma, MediaPipe, or Whisper anywhere in the code. On-device model work is greenfield. (`future-needs.md` notes `llama.cpp` as a deferred local-provider idea — the closest existing thought to on-device.)

### Q3 — What does the Node layer do?

**There is no Node layer in AgentOS.** The only `package.json` in scope is `axis-ui` (Next.js 15 / React 18), which belongs to **Axis** — a separate project per the seed itself. AgentOS's UI is a single HTML string served from `agentos/ui.py` (Python).
**Implication:** the seed's premise that React Native would "port AgentOS web logic naturally" doesn't hold — there is no JS web logic to port.

### Q4 — Existing mobile experiments?

**None.** No `.swift` / `.xcodeproj` / `.xcworkspace` / `Podfile` / `.pbxproj`, and no React Native / Expo. iOS and macOS are greenfield. (The only SwiftUI/Xcode mentions in the repo are inside `native-client-plan.md` — the planning doc.)

### Q5 — Prism timeline / MVP impact?

Prism is real but **separate and server-side**: a FastAPI gateway over a three-tier pipeline — **Tier 1 Mongo** (raw truth) → **Tier 2 Postgres** (structured) → **Tier 3 Qdrant** (vectors), plus an optional local "Zero" tier. It ships as Docker containers (`docker-compose.yml` = Mongo + Postgres + Qdrant + API). It is **not imported by AgentOS** today.
Because Prism is multi-container and server-resident, it is structurally **opposed** to Skipper's "fully local, no central DB" model. **Recommendation:** Skipper's MVP ships on the local store AgentOS already has (SQLite, plus local vectors only if needed) and does **not** depend on Prism. Prism remains the backbone for the *server-side* fleet (Stan / Maurice / Judy). **It does not block the MVP.**

---

## 2. How the seed reconciles with reality (and with the earlier plan)

`native-client-plan.md` assumed a **networked** Python backend reached over HTTP, with auth/TLS/hosting deferred to a later phase. The seed replaces that with a **local-first, on-device** model. Net effect:

- **Transport flips** from "remote server" to "local API served by a binary bundled with the app." Most earlier Phase-3 gaps — auth, TLS, CORS, hosting — **evaporate**: there is no server to secure (except the paid phone-call surface on BlackOne).
- **New hard parts replace them:** (a) running compiled Python inside the app sandbox, (b) on-device model integration, (c) building Skipper's thread/sleep/seed intelligence, which doesn't exist yet.
- **What survives intact:** the entire cell-pipeline architecture, the `/chat` contract, the `macos` mode, SQLite memory, and the `AgentOSKit` + SwiftUI client design. All reusable as-is.

---

## 3. Four decisions to make before building

### D1 — Where does inference run? *(the pivotal one)*

On-device LLM runtimes are **native**, not Python. Two coherent architectures:

- **Option A — Native inference.** Gemma runs in the Swift layer; Python runs the rest of the pipeline (capture, threads, sleep, seeds) and `llm-interface` calls out to the native runtime. Best Apple-silicon performance; adds a Python↔native bridge and breaks "one inference point."
- **Option B — Python inference.** Gemma runs *inside* the (embedded) Python via a `llama.cpp`/GGUF binding; the existing `llm-interface` cell just swaps LiteLLM → llama.cpp. Keeps the whole AgentOS architecture intact and is the fastest path to "Skipper talks." Loses native ANE tuning.

> **Verified correction to the seed:** the **MediaPipe LLM Inference API is now maintenance-only, and its iOS implementation is deprecated** — Google points new iOS work to the **LiteRT-LM Swift API**. Gemma on-device on iOS is still fully supported; the *runtime named in the seed is the wrong one to start on*. If we go Option A on iOS, target **LiteRT-LM**, not MediaPipe.

**Recommendation:** **Option B for the macOS MVP** (least disruption, keeps the cell model whole, fastest to a talking Skipper). Re-evaluate native inference via **LiteRT-LM** for iOS when battery/latency demand it.

### D2 — Frontend: React Native or SwiftUI?

**Recommendation: SwiftUI.** The RN case ("stay in JS, port web logic") is undercut by Q3 — there's no JS web logic to port, and AgentOS's UI is Python. Meanwhile every hard piece is native-first: on-device inference (LiteRT-LM), Whisper, the Neural Engine, Background tasks (the sleep cycle), StoreKit (one-time purchase), and the privacy story. The SwiftUI + shared `AgentOSKit` design already drafted stands.

### D3 — iOS Python strategy (and why macOS goes first)

On **macOS**, bundling a local Python binary + local FastAPI is clean and low-risk. On **iOS** it is the biggest unknown in the whole plan.

> **Verified:** Python-in-an-iOS-app is officially feasible — CPython 3.13+ ships an official *"Using Python on iOS"* path — but via **libPython embedding** (the Python-Apple-support / BeeWare route), **not Nuitka**. The stdlib must be trimmed to pass App Store automated review, C extensions must be cross-compiled for iOS, and there's no dynamic loading of arbitrary shared libraries.

So the seed's "Nuitka → native binary → App Store" is **not the documented iOS path**; the supported path is official CPython embedding. **De-risk by proving the entire stack on macOS first**, then run iOS Python embedding as its own scoped spike before committing.

### D4 — Skipper's intelligence is the actual product, and it's unbuilt

Map the seed's four jobs onto AgentOS cleanly — none of it needs kernel changes:

- **Capture / extract** → make the `ingestion` cell real (entities + sentiment on *user* input).
- **Track / weight threads** (recurrence + emotional charge) → a Skipper-specific store, extending the SQLite memory schema.
- **Surface** (proactive, not noisy) → a hook + a scheduled pass.
- **Sleep cycle** (nightly compaction + re-weight) → a scheduled job: macOS `launchd`/cron now; iOS `BGTaskScheduler` later.
- **Seed builder** → a tool/hook that packages a compressed context handoff.

This is exactly what cells, hooks, a store, and a scheduled job are for — the architecture already supports it.

---

## 4. Recommended MVP path (reconciled)

**Phase 0 — Define Skipper + prove the local stack on macOS.** Write Skipper's persona + manifest (`mode-control → memory → ingestion → context-builder → llm-interface`, plus the `macos` mode). Swap `llm-interface` to local Gemma via `llama.cpp` (Option B); pull a Gemma GGUF. Run the kernel locally and confirm `/chat` answers. Scaffold the SwiftUI macOS app + `AgentOSKit` against the local server.

**Phase 1 — Skipper POC.** Native chat with Skipper end-to-end on macOS; local SQLite transcript. *Done = a real conversation in a native window.*

**Phase 2 — Skipper's brain.** Real `ingestion` (entities + sentiment), the thread store with recurrence/sentiment weighting, proactive surfacing, the nightly sleep compaction, and the seed builder. Add local **Whisper** for voice.

**Phase 3 — iOS.** The CPython-embedding spike (D3), a **LiteRT-LM** evaluation for ANE inference (D1), `BGTaskScheduler` sleep cycle, StoreKit one-time purchase, and the privacy manifest.

*(Prism stays out of the Skipper MVP. The paid phone-call surface stays out until BlackOne telephony is in scope.)*

---

## 5. What I'd correct in the seed (verified)

1. **"Node/npm layer on top [of AgentOS]"** — not present. The Node app is Axis's; AgentOS's UI is Python.
2. **"RN ports AgentOS web logic naturally"** — there is no JS web logic to port.
3. **MediaPipe LLM Inference (iOS)** — maintenance-only / deprecated; the current Google path is **LiteRT-LM Swift API**.
4. **Nuitka → iOS App Store** — not the documented path; official CPython **libPython embedding** is.
5. **Inference via a native runtime implies inference leaves Python** — a real architectural fork (D1) the seed doesn't call out.
6. **Prism** — "coming soon" is true for the *server-side* fleet, but it's Dockerized/server-resident and shouldn't be inside local-first Skipper.

---

*Verification basis: `agentos/main.py`, `cli.py`, `cells/*/​{cell,store}.py`, `hooks/memory_persist.py`, `pyproject.toml`, `prism-platform/`, and `axis/ui/package.json`, read 2026-06-19. External claims (D1, D3) verified via Google AI Edge and python.org iOS docs — see chat for source links.*
