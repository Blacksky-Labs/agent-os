# AgentOS iOS — build & sideload

Personal on-device build, sideloaded via Xcode (no App Store, no OTA — Xcode redeploy is
the update loop). Corrects/realizes `AGENTOS_IOS_NUITKA_SEED.md`; see `agentos-ios-build-plan.md`.

**What's proven (Python side, done):** the in-process kernel (`agentos/runtime.py` → `ao_call`)
and the Swift inference seam (`agentos/llm.py` `set_inference_backend`). The staged bundle is
536 KB, FastAPI-free, and runs a full turn in-process. **What's left is this doc: embed CPython
and wire Swift.** Expect iteration on §3 — embedding is the fiddly part.

Files in `clients/AgentOSiOS/`:
- `AgentOSApp.swift` / `ContentView.swift` — minimal SwiftUI chat
- `PythonKernel.swift` — Swift ↔ embedded Python bridge (PythonKit)
- `GemmaBackend.swift` — on-device inference seam (stub → MediaPipe/MLX)
- `stage-python.sh` (in `clients/`) — copies the runtime Python into the bundle

---

## Stage 1 — demo shell on your phone (today, no embedding)

Prove your iOS signing + device deploy before tackling the embedding. With PythonKit
commented out in `project.yml`, the app builds as a pure SwiftUI shell (stub replies):

```bash
cd clients
xcodegen generate        # demo shell — no Python staging or framework needed yet
open Skipper.xcodeproj
```

In Xcode: pick the **AgentOSiOS** scheme → Signing & Capabilities → select your Team →
plug in your iPhone → **Run (⌘R)**. First launch on device: Settings → General →
VPN & Device Management → trust your developer cert. You should see Skipper with a working
chat that echoes a stub reply. That confirms the whole iOS pipeline is yours to drive.

Then do Stage 2 below to swap the stub shell for the real on-device kernel.

---

## 1. Prereqs (Stage 2 — embedding)
- Xcode + iOS SDK, an iPhone, and your Apple Developer account (for device deploy)
- `brew install xcodegen`
- Python **3.12 or 3.13** locally (match the embedded build)

## 2. Get the embedded Python + dependencies

Download a **Python-Apple-support** release (BeeWare) for iOS — it provides
`Python.xcframework` + the `python-stdlib` (includes `_sqlite3`, so no Nuitka SQLite pain):

```bash
# from https://github.com/beeware/Python-Apple-support/releases  (match your Python minor)
#   Python-3.13-iOS-support.bX.tar.gz
mkdir -p clients/Frameworks && tar -xzf Python-3.13-iOS-support.b*.tar.gz -C clients/Frameworks
# → clients/Frameworks/Python.xcframework  and  clients/Frameworks/python-stdlib/
```

Stage our Python into the app resources. PyYAML (our only third-party dep) is vendored as
pure Python by the script — **no iOS wheel needed**:

```bash
cd clients
./stage-python.sh           # → AgentOSiOS/Resources/app    (agentos + cells + vendored yaml)
./assemble-python-ios.sh    # → AgentOSiOS/Resources/python (CPython home: stdlib + arm64 _sqlite3 etc.)
```

## 3. Build (the iteration point)

`project.yml` already wires PythonKit, `Python.xcframework`, the folder references, the
`STAGE2_EMBED` flag, and the prebuild stage step — so once §2 is done:

```bash
cd clients
xcodegen generate
open Skipper.xcodeproj
```

Run the **AgentOSiOS** scheme on your iPhone and watch the Xcode console for the `AGENTOS:`
logs — they show how far init got:

- crash **at launch, in `dyld\`start`, before any `AGENTOS:` log** → iOS (`amfid`) is rejecting
  the embedded `Python.framework`/`.so` modules because they're signed by BeeWare, not your
  team. The `postBuildScripts` re-sign step in `project.yml` force-signs them with your build
  identity; make sure you `xcodegen generate`d after it was added.
- crash **before** `AGENTOS: Python <version>` → PythonKit can't load the embedded `libpython`
  (tune `PYTHON_LIBRARY` in `PythonKernel.swift`, or init via the C API first)
- crash **before** `AGENTOS: kernel runtime ready` → the staged app isn't on `sys.path`
  (check the `Resources/app` folder reference + `PYTHONPATH`)
- `AGENTOS: ready ✓` → the real on-device kernel is running; chat now hits the actual pipeline

The model reply is still the Gemma stub until §4 — but the pipeline, memory, and SQLite are
all real and on-device at this point.

## 4. Wire Gemma (after the bridge works)

Replace `GemmaBackend.complete(request:)`'s stub with real inference — **MediaPipe LLM
Inference** or **MLX-Swift** loading **Gemma 4 E4B** (download to the sandbox on first launch;
don't bundle the multi-GB model). Move the call off the main actor (`ContentView.send`).

## 5. Build & sideload

```bash
cd clients && xcodegen generate        # regenerates the project with the iOS target
# Open Skipper.xcodeproj → select the AgentOSiOS scheme → your iPhone → Run (⌘R)
# First run on device: Settings → General → VPN & Device Management → trust your cert
```

## 6. The update loop (memory preserved)

```
edit Python  →  ./clients/stage-python.sh  →  Xcode Run  →  new pipeline live on iPhone
```

Memory & context survive because the kernel writes to `AGENTOS_DATA_DIR` = the app's
**sandbox container** (`Library/Application Support`), which a redeploy preserves. Only
**deleting** the app wipes it — redeploy, don't delete-and-reinstall.

## 7. Failure modes

| Failure | Cause | Fix |
|---|---|---|
| PythonKit can't find libpython | embedded lib not discovered | set `PYTHON_LIBRARY` to the xcframework binary; init interpreter before first `Python.import` |
| `ModuleNotFoundError: agentos` | `Resources/app` not on `sys.path` | confirm `PYTHONPATH` = `…/app` and it's a folder reference |
| `No module named 'yaml'` | pyyaml wheel not staged | re-run the `pip install --target …` step with the iOS platform tag |
| `No module named '_sqlite3'` | stdlib not bundled | add `python-stdlib` as a resource (Python-Apple-support includes `_sqlite3`) |
| memory lost after redeploy | data written in the bundle | only ever write to `AGENTOS_DATA_DIR` (sandbox container) |
| UI freezes during a reply | Gemma on the main actor | run `kernel.send` off the main actor |
