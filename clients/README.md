# Skipper — Native Clients

Phase 0 scaffold for the native AgentOS surfaces. macOS first; iOS later reuses
`AgentOSKit` untouched. See `../skipper-audit.md` and `../native-client-plan.md`.

```
clients/
├── AgentOSKit/          # shared Swift package — models, HTTP client, transcript store (iOS-reusable)
│   ├── Package.swift
│   ├── Sources/AgentOSKit/{Models,AgentOSClient,TranscriptStore}.swift
│   └── Tests/AgentOSKitTests/ContractTests.swift
└── AgentOSMac/          # macOS SwiftUI app sources (drop into an Xcode app target)
    ├── SkipperApp.swift  ChatView.swift  ChatViewModel.swift
    └── AgentPickerView.swift  SettingsView.swift
```

---

## 1. Start the local kernel with Skipper

From the repo root (`agentOS/`):

```bash
# one-time: install the kernel + pull a local Gemma
pip install -e .
ollama pull gemma4:e4b         # edge-first, runs on Mac + iPhone; gemma4:e2b for low-RAM devices

# make sure Ollama is running (the menubar app, or `ollama serve`)
agentos start skipper          # serves http://127.0.0.1:1776
```

Sanity check in another terminal:

```bash
curl -s http://127.0.0.1:1776/health
curl -s -X POST http://127.0.0.1:1776/chat \
  -H 'Content-Type: application/json' \
  -d '{"agent_name":"skipper","user_message":"hey","session_id":"smoke-1","mode":"macos","user_id":"mario"}'
```

If `model.name` in `manifests/skipper.yaml` doesn't match a model you've pulled,
edit it (e.g. `ollama/gemma2:2b`). First reply is slow while Gemma loads into memory.

> Skipper's manifest runs `mode-control → memory → ingestion → context-builder → llm-interface`.
> `retrieval` is intentionally left out until Skipper reads your files.

---

## 2. Verify the shared core (no server needed)

```bash
cd clients/AgentOSKit
swift test          # runs ContractTests — pins the wire format to the backend
```

---

## 3. Assemble the macOS app in Xcode

The `.swift` files are ready; they just need an app target around them (the
`.xcodeproj` isn't checked in — Xcode should generate it).

1. **New project** → macOS → **App**. Product Name `Skipper`, Interface **SwiftUI**,
   Language **Swift**. Save it inside `clients/` (e.g. `clients/Skipper/`).
2. **Delete** the two files Xcode generated: `SkipperApp.swift` *(the generated one)*
   and `ContentView.swift`.
3. **Add the app sources**: drag the five files from `clients/AgentOSMac/` into the
   target ("Copy items if needed" off; add to the Skipper target).
4. **Add the package**: File → Add Package Dependencies → **Add Local…** → select
   `clients/AgentOSKit`. Add the `AgentOSKit` library to the Skipper target.
5. **Two macOS gotchas** (both silently block networking if skipped):
   - **Sandbox network access** — target → Signing & Capabilities → App Sandbox →
     check **Outgoing Connections (Client)** (`com.apple.security.network.client`).
   - **Allow local HTTP** — in Info, add `App Transport Security Settings` →
     `Allow Local Networking = YES` (`NSAllowsLocalNetworking`). The kernel is
     plain HTTP on loopback.
6. **Run** (⌘R). The sidebar shows Skipper from `/agents`; the dot turns green when
   `/health` answers. Type in the composer and Skipper replies through the local pipeline.

---

## 4. What's wired (Phase 0) and what's next

**Working now:** native chat with Skipper over the local kernel, agent picker,
connection status, on-device transcript persistence, `mode=macos`, contract tests.

**Phase 1 →:** polish the chat loop. **Phase 2 →:** Skipper's brain — real
`ingestion` (entities + sentiment), thread store + recurrence/sentiment weighting,
proactive surfacing, the nightly sleep compaction, the seed builder, local Whisper
voice. **Phase 3 →:** iOS target (reuses `AgentOSKit`), CPython-embedding spike,
LiteRT-LM evaluation for on-device Gemma, `BGTaskScheduler` sleep cycle, StoreKit.

> All local. Per the privacy model in `skipper-audit.md`, nothing leaves the device.
