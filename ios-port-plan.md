# AgentOS — iOS Port Plan

*Blacksky Labs | 2026-06-21 | Companion to `native-client-plan.md`, `macos-packaging-plan.md`, `agentos-v1-spec.md`*

How AgentOS reaches iPhone/iPad. AgentOS is the OS; iOS is another **surface** for the
same entities (Skipper first, then Maurice, Judy, …). This is not a recompile — one
architectural constraint reshapes how the kernel and inference run. Everything else is
designed to carry over.

---

## 0. The one constraint that shapes everything

**iOS forbids subprocesses.** A macOS app launches the Nuitka-compiled Python kernel as a
child process and talks to it over `127.0.0.1` (`KernelController`). iOS sandboxing does
not allow an app to `fork`/`exec` a separate binary or run a sibling process. So two things
that work on macOS cannot port as-is:

1. **The kernel-as-subprocess model** — the kernel must run *inside* the app process.
2. **Ollama** — it's a separate process/server; on iOS there is no Ollama. Inference must
   be an embedded library.

Note: iOS apps *can* still open a listening socket on `127.0.0.1` (in-process), so a
localhost HTTP server is allowed — just not a separate process hosting it. That keeps one
nice option open (see §4).

Also: **updates on iOS go through the App Store / TestFlight**, not Sparkle. The Sparkle
pipeline (`UPDATES.md`) stays macOS-only.

---

## 1. What carries over unchanged

- **`AgentOSKit`** — the shared Swift core (models, HTTP client, transcript store). Its
  `Package.swift` already declares `.iOS(.v16)`; the iOS app imports it as-is.
- **Manifests & personas** — pure YAML data. An entity is defined the same way on every
  surface.
- **The cell-pipeline architecture** — cells are pure functions of `AgentContext`, hooks
  are side effects, the registry resolves versions. The *design* is platform-independent.
- **The LLM seam** — `agentos/llm.py` already speaks one OpenAI-compatible contract. Whatever
  runs inference on iOS just has to satisfy that same contract.
- **The dashboards** — the kernel's HTML pages can still render in a `WKWebView` *if* an
  in-process localhost server is kept (§4).

This is why the recent macOS work was deliberately structured this way — it minimizes what
iOS has to redo.

---

## 2. The kernel: two paths

### Path A — Embed CPython in-process (keep the Python)

You don't have to delete the Python. As of **Python 3.13 (PEP 730)**, iOS is an officially
supported platform, and CPython can be linked into the app as a static library
(e.g. BeeWare's *Python-Apple-support* XCFramework). Swift then calls the pipeline directly,
in-process, instead of over HTTP.

- **Work:** refactor the kernel to separate its **core** (the cell pipeline,
  `Pipeline.process(context)`) from its **transport** (FastAPI/uvicorn). On iOS, call the
  core; skip the web server (or run it in-process — §4). Swap Ollama for an embedded runtime
  (§3).
- **Pros:** fastest route to a *working* iOS proof; reuses the kernel logic verbatim.
- **Cons:** larger binary; trimming heavy deps (uvicorn, pydantic, etc.) for size; App Store
  review is fussier about embedded interpreters (allowed, but no remote code execution).

### Path B — Native Swift kernel (the destination)

Reimplement the kernel in Swift, growing `AgentOSKit` from "client core" into "runtime core."

- **Work:** port the pipeline, the cells, memory (SQLite via GRDB), and the `llm.py` client
  (URLSession) to Swift. Manifests/personas stay as YAML (parsed in Swift).
- **Pros:** native, small, fast, best App Store fit; one core shared by macOS + iOS; and it
  eventually lets macOS drop the Python subprocess too.
- **Cons:** a real reimplementation of the kernel — the largest single piece of work here.

**Recommendation:** Path A to *prove* AgentOS on iOS quickly; Path B as the shipped product.
Treat A's "separate core from transport" refactor as a prerequisite that also benefits macOS.

---

## 3. On-device inference (required on either path)

No Ollama on iOS, so inference becomes an embedded library. Candidates to evaluate:

- **MLX / MLX-Swift** — Apple's array framework; native Swift API; runs Gemma on Apple
  silicon (A-series/M-series). Most Apple-native fit.
- **llama.cpp (Metal backend)** — the same C library Ollama wraps; GGUF Gemma; bind to its
  C API from Swift. Also the natural embedded runtime for *self-contained macOS* (so it's
  shared work).
- **MediaPipe LLM Inference / LiteRT-LM** — Google's own on-device path for Gemma; first-class
  iOS support.

Because `agentos/llm.py` (or its Swift equivalent) is the single inference seam, swapping the
backend is a localized change — point it at the embedded runtime instead of `localhost:11434`.

**Model management:** the weights aren't bundled — download on first launch into the app's
container, with progress (the macOS `OllamaController` is the conceptual ancestor). On iPhone,
prefer the lighter **`gemma4:e2b`** over `e4b` for RAM headroom; let the manifest's model
field drive it per device.

---

## 4. Transport: HTTP vs. direct calls

- **macOS today:** kernel is a subprocess; UI talks to it over loopback HTTP; dashboards are
  `WKWebView`s onto that server.
- **iOS option 1 — keep HTTP in-process:** run the (embedded-Python or Swift) server on
  `127.0.0.1` inside the app. Maximizes reuse — `AgentOSClient` and the WebView dashboards
  work unchanged. iOS permits in-process loopback sockets.
- **iOS option 2 — direct calls:** Swift calls the pipeline directly; the UI is fully native
  SwiftUI; dashboards become native screens (or are dropped on phone). Leaner, but the
  dashboards need a native rebuild.

Option 1 is the higher-reuse bridge; Option 2 is the cleaner native end state.

---

## 5. Phased roadmap

1. **Phase 0 — Embed inference on macOS (shared stepping stone).** Replace Ollama with an
   embedded llama.cpp/MLX runtime behind the existing LLM seam. Proves the runtime and drops
   the external dependency — and it's exactly what iOS needs next.
2. **Phase 1 — Decouple core from transport.** Split the cell pipeline from FastAPI/uvicorn so
   the core is callable directly. Benefits macOS too.
3. **Phase 2 — iOS proof (Path A).** Embed CPython + the inference runtime; native SwiftUI
   chat over `AgentOSKit`; one entity (Skipper) end to end on device.
4. **Phase 3 — Native Swift kernel (Path B).** Migrate the pipeline/cells/memory/LLM into
   `AgentOSKit`; share one core across macOS + iOS; retire embedded Python.
5. **Phase 4 — Ship.** On-device model download/management, background/suspension handling,
   storage limits, TestFlight → App Store.

---

## 6. Risks & open questions

- **App Store review** of embedded interpreters (Path A) and multi-GB model downloads —
  allowed, but design for "no remote code execution" and clear download UX.
- **Memory & size** — phone RAM caps inference; bias to `e2b`-class models; watch binary size
  on Path A.
- **Background limits** — iOS suspends apps; the "always-on kernel" mental model becomes
  "kernel runs while foregrounded." Background hooks (signal extraction, cron/sleep-cycle)
  need rethinking around iOS background execution.
- **Inference runtime choice** — MLX vs llama.cpp vs LiteRT is a real evaluation (speed,
  Gemma support, Swift ergonomics, size). Decide in Phase 0.
- **Data parity** — `AGENTOS_DATA_DIR` maps to the app's container; SQLite via GRDB; the
  "updates don't forget" property is automatic since App Store updates preserve the container.

---

## 7. Implications for how we build *now*

None of this requires iOS work today, but three habits keep the door open and are good macOS
hygiene regardless:

1. **Keep the kernel core decoupled from FastAPI/uvicorn** — the pipeline should be callable
   without the web layer.
2. **Keep `agentos/llm.py` as the single inference seam** — every model call goes through it,
   so the runtime is swappable in one place.
3. **Keep `AgentOSKit` the shared client core** — UI talks to the kernel only through it, so a
   transport change (HTTP → direct) is contained.
