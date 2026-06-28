# AgentOS — iOS Build Plan (corrected)

*Blacksky Labs / AgentOS | 2026-06-21 | Supersedes `AGENTOS_IOS_NUITKA_SEED.md`*

Same mission and scope as the Nuitka seed — **a personal on-device iOS build, sideloaded
via Xcode, no App Store, no OTA** — but with the one load-bearing mechanism corrected.
Everything the seed got right (Python is the source of truth, Swift does UI + Gemma, a
JSON in/out seam, configurable SQLite path, no subprocess/fork) carries over.

---

## 0. The correction: embed CPython, don't "Nuitka to iOS"

**Nuitka cannot target iOS.** Its `--target-arch=arm64` / `--macos-target-sdk-version`
flags build a *macOS* arm64 binary; iOS is not a Nuitka target. And `--standalone` emits an
*app with a `main()`* that `dlopen`s bundled `.so` modules at runtime — neither a
Swift-callable library nor something iOS permits loading. So the seed's
"Edit Python → Nuitka compile → Xcode deploy" cannot produce an iOS artifact.

**Use embedded CPython instead — the supported path:**

- **PEP 730** made iOS an official CPython platform (3.13; backported to 3.10–3.12).
- **BeeWare's Python-Apple-support** ships CPython as an `.xcframework` (incl. the stdlib,
  so `_sqlite3` is already there — the seed's biggest Nuitka failure mode disappears).
- You bundle the **AgentOS Python source** (or `.pyc`) as an app resource; a small C/Swift
  shim initializes the interpreter and calls one function — exactly the `ao_call(json) → json`
  the seed designed.

Net: only **Phase 2 changes** (embed CPython, not Nuitka). The seam, the SQLite-path work,
Gemma-in-Swift, the iOS target, validation, and the failure table all stand.

---

## 1. Architecture

```
┌──────────────────────────────────────────────┐
│                Swift Layer (iOS)               │
│  • SwiftUI UI (shares AgentOSKit with macOS)   │
│  • Gemma 4 inference (MediaPipe / MLX, ANE)    │
│  • Embeds CPython; calls ao_call(json)→json    │
└───────────────┬────────────────────────────────┘
                │  C ABI (one function, JSON in/out)
┌───────────────▼────────────────────────────────┐
│        Embedded CPython + AgentOS source        │
│  • cells / pipeline / MoE protocol (unchanged)  │
│  • NO FastAPI/uvicorn — called in-process       │
│  • inference → callback into Swift (see §3)      │
└───────────────┬────────────────────────────────┘
                │  sqlite3 (stdlib)
┌───────────────▼────────────────────────────────┐
│   SQLite in the app's sandbox DATA CONTAINER    │
│   (Library/Application Support) via AGENTOS_DATA_DIR │
└──────────────────────────────────────────────────┘
```

Python stays the orchestrator. Swift's jobs: UI, Gemma inference, and hosting the interpreter.

---

## 2. Memory & updates — the part that matters most

**The app keeps its memory and context across every Xcode redeploy** — by the same design
as the macOS Sparkle updates.

An iOS app is two separate things: the **`.app` bundle** (Swift + bundled Python) and the
**sandbox data container** (`Documents/`, `Library/Application Support/`). A redeploy with
the **same bundle ID replaces the bundle but preserves the container.** So:

- **All mutable state lives in the container, never in the bundle.** SQLite (turns, threads,
  metrics), config overlays, vectors → `Library/Application Support/`.
- Swift sets **`AGENTOS_DATA_DIR`** to that container path at launch; the kernel writes there.
  We already have this env var (`agentos/paths.py`) — it's the macOS mechanism, reused verbatim.
- Update loop: **edit Python on the Mac → Run in Xcode → new pipeline live on the phone, memory
  intact.** The bundle is disposable; the data is not.

**One caveat:** this holds while you *update* the app. **Deleting** the app (clean uninstall)
wipes its container — so redeploy over the existing install, don't delete-and-reinstall.

---

## 3. Two decisions the seed left open

### 3a. Integration style — start lean (`ao_call`), keep the server as an option

- **Lean (chosen for v0):** one C ABI function, `ao_call(json) → json`, runs a turn through
  the pipeline directly. No web stack on device — drop FastAPI/uvicorn/pydantic from the iOS
  bundle (they're only the macOS HTTP transport). Smallest, fastest, but **no in-app
  dashboards** on iOS v0.
- **Max-reuse (later, optional):** run uvicorn *in-process* on loopback (iOS allows in-process
  sockets); the SwiftUI + the Overview/Config/DB dashboards work unchanged. Heavier bundle.

v0 takes the lean path; the dashboards stay a macOS feature for now.

### 3b. Where inference runs — Swift owns Gemma, Python calls a callback

Our pipeline calls the model *inline* (`llm-interface`/`moe` → `agentos/llm.py`). On iOS there's
no `llama-server` to hit, and Gemma should run in Swift on the Neural Engine (MediaPipe/MLX).
So give **`llm.py` an in-process backend**: instead of HTTP, it invokes a **Swift-registered
callback** for inference. This keeps Python the orchestrator and Swift the inference provider —
the same seam as the macOS `AGENTOS_LLM_API_BASE` swap, one tier deeper.

```
Swift → ao_call(json) ─► Python pipeline ─► llm.py ─► (callback) ─► Swift → Gemma (ANE) ─► back
                                          └─► SQLite (sandbox container)
```

---

## 4. Audit — where we already stand (the seed's Phase 1)

| Seed question | AgentOS today |
|---|---|
| Python entry point | `agentos/__main__.py` (CLI/server) on macOS. iOS needs a new in-process `ao_call` / `run_turn` entry that runs the pipeline without HTTP — **the first thing to build.** |
| How Swift calls Python (macOS) | Subprocess (`KernelController` spawns the kernel) + loopback HTTP. **This is exactly what iOS replaces** with in-process embedding. |
| subprocess / fork / multiprocessing | None in the kernel core (cells/pipeline). The macOS app spawns the kernel; `after_turn` uses asyncio `BackgroundTasks`; `llm.py` uses `asyncio.to_thread` (threads, fine). iOS-safe. |
| Third-party packages | FastAPI / uvicorn / pydantic (HTTP only — **dropped for iOS**) + `pyyaml` (pure Python, embeds easily). `llm.py` is stdlib. Lean bundle. |
| SQLite path | **Already configurable** via `AGENTOS_DATA_DIR` (`paths.py`). Seed Phase 2.4 effectively done. |
| Python version | 3.12 (Anaconda, per the macOS build). Match it, or move to 3.13 for best iOS support. |
| Gemma | macOS uses Ollama/llama.cpp; iOS uses MediaPipe/MLX in Swift (no Ollama/subprocess on iOS). |

---

## 5. Phased plan (corrected)

1. **Decouple the core from transport (Python, do now).** Add `agentos/runtime.py` with an
   in-process `run_turn(...)` + `ao_call(json) → json` that builds an `AgentContext`, runs the
   pipeline + after-turn hooks, persists, and returns the response — no FastAPI. Test on the Mac.
   *(Benefits macOS too; the HTTP `/chat` can later delegate to it.)*
2. **`llm.py` in-process inference backend.** A registerable callback path so a host (Swift) can
   provide inference; HTTP remains the default off-device.
3. **Embed CPython (Python-Apple-support).** Add the CPython xcframework + bundle `agentos/` as a
   resource; a C shim inits the interpreter and exposes `ao_call`. Smoke-test on the Mac first.
4. **iOS target in Xcode.** New iOS App target (shares `AgentOSKit`); bridging header for
   `ao_call`; Swift sets `AGENTOS_DATA_DIR` to the sandbox container; wire Gemma (MediaPipe/MLX).
5. **Sideload + validate on device.** Deploy to your iPhone; run the end-to-end sequence (launch
   → interpreter init → SQLite in container → write/read via `ao_call` → Gemma inference →
   response). Then prove persistence: redeploy and confirm memory survived.

Gating is the seed's: each phase validates before the next.

---

## 6. Update loop & persistence (the goal, restated)

```
Edit Python on Mac  →  Xcode Run (USB/wireless)  →  new pipeline live on iPhone
                                                     memory & context preserved
```

Works because the kernel writes to the sandbox **data container** (`AGENTOS_DATA_DIR`), which
survives bundle replacement. Your Apple Developer account covers deploying to your own device.

---

## 7. Failure modes to watch

| Failure | Cause | Fix |
|---|---|---|
| Interpreter won't init | CPython xcframework not linked / wrong arch | Use Python-Apple-support's signed xcframework; iOS-arm64 (+ simulator slice) |
| `ModuleNotFoundError` for our code | `agentos/` source not bundled as a resource | Add `agentos/` (and `cells/`, `hooks/`, manifests, personas) to the iOS target's resources |
| Memory lost after redeploy | data written inside the `.app` bundle | Write only to `AGENTOS_DATA_DIR` → sandbox container |
| Memory lost entirely | app was **deleted**, not updated | Redeploy over the existing install |
| No model response | inference callback not registered | Register the Swift Gemma callback before the first `ao_call` |
| Heavy bundle / slow init | FastAPI/uvicorn pulled into iOS | Keep the iOS path on `run_turn`/`ao_call`, not the HTTP app |

---

## 8. Out of scope (unchanged from the seed)

OTA updates (Xcode redeploy only), App Store / TestFlight, Postgres, Prism, web client,
cross-platform sync, IP-obfuscation flags. Scope stays intentionally minimal.
