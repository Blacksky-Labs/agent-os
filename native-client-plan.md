# AgentOS — Native Client Plan (macOS first, iOS next)

*Blacksky LLC | Foundation Infrastructure | Companion to SPEC.md*
*Status: Draft v0.1 — 2026-06-19*

> **Update (2026-06-19) — read `skipper-audit.md` first.** The Skipper seed makes the agent **local-first / on-device**. The transport stays a *local* API (FastAPI on `localhost`, bundled with the app rather than reached remotely), so the client architecture below holds — but the Phase-3 auth/TLS/hosting items are **superseded** by on-device bundling, and the model is **Gemma on-device** (not Ollama/LiteLLM over the network). See the audit's §2–§4 for the reconciled path.

---

## 0. Goal

Stand up a **native macOS app** as the first real human surface for the Blacksky agent fleet: a desktop client that talks to the existing agentOS Python kernel over HTTP. Prove the native-client architecture as a **local-first MVP** running on the same Mac the kernel already lives on, and structure the SwiftUI codebase so the **iOS app later reuses almost all of it**.

One sentence: the kernel stays exactly as specified in `SPEC.md`; the macOS app is just another HTTP client speaking the `/chat` contract, declaring itself through a new `macos` mode.

---

## 1. Decisions locked in

- **Architecture:** native client + Python backend. The kernel is *not* ported; it stays Python/FastAPI. (Confirmed.)
- **Platform order:** **macOS first**, iOS as a follow-on phase that imports the same shared Swift core. (Confirmed — macOS is the more open, lower-friction POC.)
- **POC agent: Skipper, the personal agent.** A single-agent POC, but driven by the live `GET /agents` list so multi-agent falls out for free — the picker shows whatever manifests exist. Prove the surface on Skipper, and it already works for Stan, Maurice, and Judy.

> **Reality check (from the repo today):** **no real agent exists yet** — the only manifests/personas present are smoke tests (`ui_smoke`, `__smoke`, `_inproc_smoke`), and **no persona defines a `modes:` block**. Skipper is **net-new** and must be defined from scratch: unlike Stan (whose `stan.yaml` is pre-written in `agentOS-build-handoff.md`), there is no ready-made manifest to borrow. The upside — a *personal* agent needs a far lighter cell set than Stan's market/BTC-clock ingestion. Phase 0 can start Skipper on just `mode-control → memory → context-builder → llm-interface` and add `retrieval`/`ingestion` only when he needs to read your files. `agentos new agent skipper` scaffolds the skeleton; his persona + manifest are the first thing I'll draft.

---

## 2. Why macOS first is the right call

The instinct is correct, and it specifically removes the parts of an iOS-first plan that would have slowed the MVP:

- **It can talk to `localhost` directly.** The kernel binds `127.0.0.1:7777` by default (`AGENTOS_PORT`, see `cli.py`). A macOS app hits it with zero hosting, zero TLS, zero tunnel. An iOS device cannot reach `localhost` and would have forced a hosting + HTTPS decision on day one.
- **No App Store friction to iterate.** No provisioning profiles, no TestFlight, no App Review. Build and run locally as fast as you can recompile.
- **The app can supervise the kernel itself.** A macOS app can launch `agentos start <agent>` as a child process and surface its logs — a one-click "run my agent" experience that is simply impossible on iOS.
- **It runs where the work already is.** Mario is the only operator and works on the Mac; the POC lives next to the kernel, the corpus, and the manifests.
- **The hard problems get deferred honestly, not skipped.** Auth, TLS, remote hosting, and streaming-over-network are exactly the gaps `SPEC.md §14` and `future-needs.md` already park for later. macOS-local lets us ship without them and pick them up when iOS forces the issue.
- **The UI is shared, not thrown away.** SwiftUI is the same framework on both platforms. If networking and models live in a shared Swift package, the iOS app imports that core untouched and only re-does layout.

---

## 3. How a native surface fits the agentOS model

Nothing in the kernel needs to learn what "macOS" is. That is a direct consequence of the SPEC's second invariant — *the kernel knows nothing about any specific agent* — extended to surfaces.

A surface is a **mode**, and modes are **data**. `mode-control/cell.py` resolves `context.mode` against the persona's `modes` block and copies the matching constraints onto `context.mode_constraints`. So adding a native surface is a **persona edit, not a code change**:

```yaml
# in each persona.yaml (e.g. personas/skipper.yaml)
modes:
  web:    { max_words: 250, markdown: true }
  phone:  { max_words: 60,  markdown: false, no_lists: true }
  macos:  { max_words: 400, markdown: true }    # desktop has the screen
  # ios:  { max_words: 200, markdown: true }    # sibling, added in Phase 3
```

The `/chat` request already carries `mode` (`ChatRequest.mode`, `main.py`), so the app sends `mode: "macos"` and everything downstream — context-builder, llm-interface — already honors it. Keeping `macos` and `ios` as **separate blocks** mirrors the existing `web` vs `phone` split and lets each surface tune its own response shape.

Note: **no persona in the repo defines a `modes:` block today**, so this `macos` block is the first one. That degrades gracefully — `mode-control` returns empty `mode_constraints` for an unknown mode rather than failing (see `cell.py`) — but until the block exists, the desktop surface gets no tuning. Adding it is part of Phase 0.

**Net kernel/cell code changes required for the macOS MVP: none.** Only declarative persona additions.

---

## 4. The API contract the app speaks

Taken from the live models in `agentos/main.py` — not invented. The macOS client needs exactly three endpoints for the MVP, plus three more for the Phase 2 power features.

**MVP endpoints**

`POST /chat` — the one that matters.

```
Request  (ChatRequest)            Response (ChatResponse)
{                                 {
  "agent_name": "skipper",          "response": "…",
  "user_message": "…",              "turn_id": "t_abc123",
  "session_id": "<client uuid>",    "namespace": "skipper",
  "mode": "macos",                  "cell_timings": { … },
  "user_id": "mario"                "cell_errors": { … },
}                                   "usage": { … } | null
                                  }
```

`GET /agents` — powers the agent picker: `{ "agents": [ { name, display_name, provider, model } ] }`.

`GET /health` — connection light: `{ status, version, agents_loaded, cells_available }`.

**Phase 2 endpoints (desktop power features)**

`GET /agents/{name}/corpus`, `POST /agents/{name}/ingest` (`{ "path": "…" }`), `DELETE /agents/{name}/corpus?source=…`. These manage an agent's RAG corpus. Note the ingest path is interpreted **on the server host** — which on macOS-local is the *same machine* — so the desktop app can let Mario pick a local file or folder in a native open-panel and hand the real path straight to the kernel. That is a genuine macOS-only superpower the web UI can't match.

---

## 5. Backend gaps — and why macOS-local shrinks them

| Gap | Status today | Does the macOS MVP need it? | Plan |
|---|---|---|---|
| **Streaming** | Request/response only (`SPEC §14`) | No | Ship with a "thinking" indicator; add SSE in Phase 2 when the wait annoys (the exact trigger in `future-needs.md`). |
| **Session / history** | `memory` cell is a stub; `/chat` returns no history | No | App owns `session_id` and keeps the local transcript (SwiftData or JSON). When `memory` becomes real, server-side history can backfill. |
| **Auth** | None (`SPEC §14` defers to the HTTP layer) | No | Fine over `localhost`. Becomes mandatory in Phase 3 when iOS/remote appears — add a bearer token read from kernel env. |
| **CORS** | Not configured | No | Irrelevant to a native app; only browsers enforce it. Native sidesteps it entirely. |
| **TLS / hosting** | Plain HTTP on `127.0.0.1` | No | Add an ATS exception for localhost in the app's `Info.plist` (`NSAllowsLocalNetworking`). Real TLS + hosting is a Phase 3 / iOS concern. |

The takeaway: **none of the deferred backend work blocks the macOS MVP.** macOS-local is the configuration in which all five gaps are safe to leave open.

---

## 6. macOS app architecture

SwiftUI app, MVVM, with the reuse seam deliberately drawn so iOS is cheap later.

**`AgentOSKit` — a shared Swift package (the reuse seam).** Everything platform-independent lives here so both the macOS and the future iOS target import it unchanged:
- **Models:** `Codable` structs mirroring the contract — `ChatRequest`, `ChatResponse`, `AgentSummary`, `HealthStatus`.
- **`AgentOSClient`:** an `actor` wrapping `URLSession` async/await — `chat(_:)`, `agents()`, `health()`. Base URL injected (defaults to `http://127.0.0.1:7777`).
- **Session:** client-side `session_id` generation and a `TranscriptStore` for local history.

**`AgentOSMac` — the macOS app target** (depends on `AgentOSKit`):
- `AgentPickerView` — sidebar from `GET /agents`.
- `ChatView` — transcript + composer; sends `mode: "macos"`.
- `ConnectionStatusView` — a light driven by `GET /health`.
- `SettingsView` — base URL / port, `user_id`.
- *(Phase 2)* `CorpusView` — native open-panel → `POST /ingest`; `ServerController` — launch/stop `agentos` via `Process`.

**`AgentOSiOS` — added in Phase 3.** Same `AgentOSKit`, new views/layout only.

---

## 7. Proposed project structure

A Swift workspace living alongside the kernel so the whole platform is one repo:

```
agentOS/
├── agentos/                 # existing Python kernel — untouched
├── cells/  manifests/  …    # existing
└── clients/                 # NEW — native surfaces
    └── AgentOS.xcworkspace
        ├── AgentOSKit/          # shared Swift package (models, client, session)
        │   └── Sources/AgentOSKit/
        │       ├── Models.swift
        │       ├── AgentOSClient.swift
        │       └── TranscriptStore.swift
        ├── AgentOSMac/          # macOS app target
        │   ├── App.swift
        │   ├── ChatView.swift
        │   ├── AgentPickerView.swift
        │   └── SettingsView.swift
        └── AgentOSiOS/          # added Phase 3 — imports AgentOSKit
```

*(Open question in §9: in-repo `clients/` vs a sibling `agentos-clients` repo.)*

---

## 8. Phased roadmap

**Phase 0 — Define Skipper + plumbing.** **Define and scaffold Skipper first** — he doesn't exist yet (`agentos new agent skipper`, then write his persona + manifest). Start him on the minimal personal-agent cell set (`mode-control → memory → context-builder → llm-interface`) and add the `macos` mode block to his persona. Confirm the kernel runs locally (`agentos start skipper`, hit `/health`). Create the Xcode workspace, the `AgentOSKit` package, the Codable models, and the `AgentOSClient`. Smoke-test `health()` and `agents()` from a unit test.

**Phase 1 — Skipper POC (the MVP).** `ChatView` wired to `POST /chat` with `mode: "macos"`. Local transcript persistence. Agent picker shows Skipper from `GET /agents`. **Definition of done: a real back-and-forth conversation with Skipper in a native window.**

**Phase 2 — Multi-agent + desktop power.** Picker spans all manifests (free, already from `/agents`). Corpus management screen with a native file picker → `/ingest`. SSE streaming. Optional `ServerController` to launch/stop agents from the app.

**Phase 3 — Harden + iOS.** Add bearer-token auth and a TLS/hosting story to the kernel. Add the `AgentOSiOS` target reusing `AgentOSKit`. Handle ATS / remote base URL / TestFlight. This is where the deferred gaps from §5 come due — by design, only when the device forces them.

---

## 9. Open decisions — what I need from you next

1. **Where should the Xcode project live?** In-repo under `clients/` (one repo for the whole platform — my recommendation) or a sibling `agentos-clients` repo?
2. **Mode naming:** separate `macos` / `ios` persona blocks (matches your `web`/`phone` split — my recommendation) or one shared `native` block?
3. **Should the macOS app launch the kernel**, or assume `agentos start` is already running? (Affects whether Phase 2's `ServerController` moves to Phase 1.)
4. **Minimum macOS version** to target (drives which SwiftUI APIs and whether SwiftData is available for the transcript store).

**One thing I found worth fixing:** `agentOS-build-handoff.md` tells testers to hit `http://localhost:8000`, but the real default is **`7777`** (`AGENTOS_PORT` in `cli.py`; the README is correct). The client should default to `7777`; the handoff doc should be corrected.

---

*Next step after you weigh in on §9: I define Skipper (persona + manifest) and scaffold Phase 0 — the `macos` persona mode, the Xcode workspace, `AgentOSKit`, and the client — and we get Skipper talking in a native window.*
