# AgentOS iOS Port — Nuitka Pipeline Seed
**Blacksky Labs / AgentOS**
**Seed type:** CoWork implementation handoff
**Date:** June 2026
**Status:** Ready for implementation

---

## Mission

Port AgentOS to iOS as a personal development build (ADC sideload, no App Store).
Software updates are delivered via Xcode re-deploy over USB or wireless debugging.
No OTA update infrastructure. No network state. No Prism. No Postgres.

This is the simplest possible working loop:

```
Edit Python → Nuitka compile → Xcode deploy → test on device
```

---

## What Is Confirmed True

| Item | Status |
|---|---|
| macOS AgentOS app | ✅ Live, native Swift |
| Python backend | ✅ Running, source of truth permanently |
| SQLite | ✅ Already the active DB layer |
| Postgres | 🔘 Placeholder, greyed out in UI |
| Prism | 🔘 Placeholder, greyed out in UI |
| iOS app | ❌ This is the work |
| OTA updates | ❌ Out of scope — Xcode redeploy only |
| App Store submission | ❌ Out of scope |

**Do not build anything beyond this table. Scope is intentionally minimal.**

---

## Architecture

```
┌─────────────────────────────────────────┐
│            Swift Layer (iOS)            │
│  • SwiftUI UI                           │
│  • MediaPipe / Gemma 4 bridge           │
│  • Calls into compiled Python binary    │
└───────────────┬─────────────────────────┘
                │  C ABI function calls
┌───────────────▼─────────────────────────┐
│     Compiled Python Binary (Nuitka)     │
│  • All agent orchestration logic        │
│  • All business logic                   │
│  • SQLite via Python sqlite3 module     │
│  • _sqlite3 C extension bundled         │
└───────────────┬─────────────────────────┘
                │
┌───────────────▼─────────────────────────┐
│          SQLite (on-device)             │
│  • Stored in iOS app sandbox            │
│  • FileManager path — no hardcoded dirs │
└─────────────────────────────────────────┘
```

**Python is the permanent source of truth. Swift never reimplements logic.**
**Swift's only jobs: UI, Gemma bridge, calling into the compiled binary.**

---

## Phase 1 — Codebase Audit (Do This First)

Before writing a line of build script, answer these questions by reading the existing codebase:

### 1.1 Python backend structure
- What is the entry point? (e.g. `main.py`, `app.py`)
- What modules are imported? List all third-party packages from `requirements.txt` or `pyproject.toml`
- How does the Swift macOS app currently call into Python? (subprocess? embedded interpreter? something else?)
- Are there any `subprocess`, `multiprocessing`, or `os.fork()` calls? These will not work on iOS and must be identified now.

### 1.2 SQLite usage
- What file path does the Python backend use to open the SQLite DB?
- Is the path hardcoded or configurable? It must become configurable — iOS requires all file writes inside the app sandbox.
- Are any SQLite extensions loaded beyond the stdlib `sqlite3` module? (e.g. `pysqlite2`, `SQLAlchemy`, custom `.so` extensions)

### 1.3 macOS Swift ↔ Python interface
- Exactly how does Swift currently call Python on macOS? Document the mechanism.
- What data crosses the boundary? (strings, JSON, binary blobs?)
- What does the return path look like — how does Python return results to Swift?

### 1.4 Gemma / MediaPipe
- Is MediaPipe already imported as an iOS-compatible framework or macOS-only?
- What model variant is in use? (Gemma 4 — 2B, 7B, or other?)
- Where is the model file stored on macOS? This path must change for iOS.

**The audit output is a short written summary of findings. Do not begin Phase 2 until the audit is complete and reviewed.**

---

## Phase 2 — Nuitka Pipeline

### 2.1 Environment setup

Nuitka cross-compiles Python to C and then to a native binary. For iOS (arm64) this requires:

```bash
# Install Nuitka
pip install nuitka

# Required system dependencies
# - Xcode with iOS SDK installed
# - Apple Silicon Mac strongly recommended (native arm64)
# - Python 3.11 or 3.12 (confirm version matches what backend uses)
```

Confirm the Python version in use on the macOS backend before proceeding. The compiled binary must use the same version.

### 2.2 Nuitka compile flags for iOS

The compile command will look like this — adapt to the actual entry point found in the audit:

```bash
python -m nuitka \
  --standalone \
  --no-prefer-source-code \
  --target-arch=arm64 \
  --macos-target-sdk-version=latest \
  --enable-plugin=pylint-warnings \
  --include-package=sqlite3 \
  --include-module=_sqlite3 \
  --include-package-data=YOUR_PACKAGE \
  --output-dir=./build/ios \
  main.py
```

**Critical flags to get right:**
- `--include-module=_sqlite3` — SQLite's C extension. If this is omitted, SQLite will fail silently at runtime on the compiled binary. This is the single most common Nuitka/SQLite failure mode.
- `--standalone` — bundles everything needed into the output directory, no external Python install required on device
- `--target-arch=arm64` — iPhone target architecture

### 2.3 iOS framework packaging

Nuitka produces a standalone directory, not an `.xcframework` natively. To embed it in Xcode:

1. Nuitka output goes to `./build/ios/main.dist/`
2. Wrap the output as a static library or embed the directory as a bundle resource
3. The Swift layer calls into it via the C ABI (see Phase 3)

**Validation checkpoint before Phase 3:**
Run the compiled binary on a Mac first. If it boots, connects to SQLite, and returns correct results from a test query, the Nuitka step is working. Only then move to iOS embedding.

```bash
# Quick smoke test on Mac before iOS
./build/ios/main.dist/main --test
```

Define a `--test` flag in the Python entry point that runs a minimal SQLite read/write and returns success or failure.

### 2.4 SQLite path fix

The Python backend must not use hardcoded macOS file paths for the SQLite DB. Before compiling, update the DB path to be configurable via an environment variable or startup argument:

```python
import os

DB_PATH = os.environ.get("AO_DB_PATH", "./agentOS.db")
```

The Swift layer will set `AO_DB_PATH` to the correct iOS sandbox path at launch:

```swift
// Swift sets the DB path before calling into the binary
let dbPath = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
    .first!.appendingPathComponent("agentOS.db").path
setenv("AO_DB_PATH", dbPath, 1)
```

---

## Phase 3 — Swift ↔ Compiled Binary Interface

This is the seam between Swift and Python. Keep it as thin as possible.

### 3.1 Interface design

The compiled Nuitka binary exposes a C ABI. Swift calls functions by name. The simplest interface is JSON in, JSON out:

```c
// C header (agentOS_bridge.h)
// Swift imports this header via the bridging header

const char* ao_call(const char* json_input);
void ao_free(const char* ptr);
```

```python
# Python side — the function Nuitka exposes
import json

def ao_call(json_input: str) -> str:
    payload = json.loads(json_input)
    # route to appropriate agent function
    result = dispatch(payload)
    return json.dumps(result)
```

```swift
// Swift side
func callAgent(payload: [String: Any]) -> [String: Any]? {
    guard let jsonData = try? JSONSerialization.data(withJSONObject: payload),
          let jsonString = String(data: jsonData, encoding: .utf8) else { return nil }
    
    guard let resultPtr = ao_call(jsonString) else { return nil }
    let resultString = String(cString: resultPtr)
    ao_free(resultPtr)
    
    guard let resultData = resultString.data(using: .utf8),
          let result = try? JSONSerialization.jsonObject(with: resultData) as? [String: Any]
    else { return nil }
    
    return result
}
```

**JSON is the boundary protocol. No shared memory, no complex types across the boundary. Everything serializes to JSON.**

### 3.2 Xcode bridging header

Create `AgentOS-Bridging-Header.h` in the Xcode project:

```c
#ifndef AgentOS_Bridging_Header_h
#define AgentOS_Bridging_Header_h

#include "agentOS_bridge.h"

#endif
```

Set this as the Objective-C Bridging Header in Xcode build settings.

### 3.3 Gemma stays in Swift

MediaPipe and Gemma inference remain entirely in the Swift layer. The compiled Python binary does not touch Gemma. This is intentional — MediaPipe's iOS framework handles Neural Engine acceleration natively in Swift.

```
Swift → MediaPipe → Gemma 4 (Neural Engine)
Swift → ao_call() → compiled Python binary → SQLite
```

These are two separate call paths. They do not intersect.

---

## Phase 4 — iOS Target in Xcode

### 4.1 Add iOS target

In the existing Xcode project (which currently has only a macOS target):

1. File → New → Target → iOS App
2. Name it `AgentOS-iOS`
3. Set minimum iOS version: iOS 17.0 (required for latest MediaPipe)
4. Link the Nuitka compiled binary output to this target
5. Add the MediaPipe framework to the iOS target

### 4.2 Platform-specific Swift code

Where macOS and iOS diverge, use conditional compilation:

```swift
#if os(iOS)
    // iOS navigation, window scene, etc.
#elseif os(macOS)
    // macOS window controller, etc.
#endif
```

Audit the existing Swift codebase for:
- `NSWindowController` — macOS only, needs iOS equivalent
- Hardcoded file paths — replace with `FileManager`
- Any AppKit imports — iOS uses UIKit

### 4.3 Sideload deployment

With ADC subscription:
1. In Xcode, select the iOS scheme
2. Connect iPhone via USB (or enable wireless debugging on same network)
3. Select device as target
4. Product → Run
5. On first run: Settings → VPN & Device Management → trust the developer certificate

For wireless debugging (no cable after first connection):
- Window → Devices and Simulators → enable "Connect via network"

This is the full update loop. New build = new Python compile + Xcode deploy.

---

## Phase 5 — Validation

### 5.1 Minimal test sequence

Before calling this done, verify this sequence works end to end on device:

1. App launches on iPhone ✓
2. Compiled Python binary initializes without crash ✓
3. SQLite DB is created in iOS sandbox at correct path ✓
4. A write to SQLite from Python succeeds ✓
5. A read from SQLite returns correct data to Swift via `ao_call()` ✓
6. Gemma 4 loads and returns an inference result ✓
7. Full agent interaction (user input → Python processing → Gemma inference → response displayed) ✓

### 5.2 Known failure modes to check

| Failure | Cause | Fix |
|---|---|---|
| `No module named '_sqlite3'` | _sqlite3 not included in Nuitka build | Add `--include-module=_sqlite3` |
| App crashes on launch silently | subprocess/fork call in Python | Audit and remove all subprocess calls |
| DB write fails | Hardcoded macOS path | Use `AO_DB_PATH` env var |
| Gemma fails to load | macOS model path hardcoded | Set model path from Swift at runtime |
| Binary not found at runtime | Nuitka output not linked in Xcode | Verify build phases include the binary |

---

## Out of Scope (Do Not Build)

- OTA software updates — Xcode redeploy only
- Postgres integration — placeholder stays greyed out
- Prism integration — placeholder stays greyed out
- App Store submission or TestFlight
- Nuitka IP obfuscation flags — that's the App Store prep milestone
- Any network state or cross-platform sync
- Web client

---

## Open Questions CoWork Must Answer Before Building

1. **What is the Python entry point?** (`main.py`? `app.py`? something else?) The Nuitka compile command depends on this.

2. **How does the macOS Swift app currently call Python?** If it uses `subprocess`, that mechanism is completely replaced by the C ABI bridge in this seed. If it already uses an embedded approach, we may be closer than expected.

3. **Are there any `subprocess`, `fork`, or `multiprocessing` calls in the Python backend?** These must be removed or replaced before compiling for iOS.

4. **What third-party Python packages are in use?** Some packages have C extensions that Nuitka handles automatically; some require explicit `--include-package` flags. A full list is required before the compile command is finalized.

5. **What Python version is the backend running on?** Must match the version used for Nuitka compilation.

---

## Build Script (to be finalized after audit)

```bash
#!/bin/bash
# build_ios.sh — AgentOS iOS Nuitka build
# Run from project root after audit confirms entry point and packages

set -e

ENTRY_POINT="main.py"           # UPDATE after audit
OUTPUT_DIR="./build/ios"
PYTHON_VERSION="3.12"           # UPDATE to match backend

echo "🔨 Compiling Python → native binary via Nuitka..."

python -m nuitka \
  --standalone \
  --target-arch=arm64 \
  --include-module=_sqlite3 \
  --include-package=sqlite3 \
  --output-dir=$OUTPUT_DIR \
  $ENTRY_POINT

echo "✅ Build complete: $OUTPUT_DIR"
echo "📱 Open Xcode, select iOS scheme, connect device, and deploy."
```

---

## Summary

| Phase | What happens | Gating condition |
|---|---|---|
| 1 — Audit | Map Python backend, Swift interface, SQLite paths | Must complete before any build work |
| 2 — Nuitka pipeline | Compile Python → arm64 binary, validate on Mac | Audit findings confirmed |
| 3 — Swift interface | C ABI bridge, JSON protocol, bridging header | Nuitka binary validates on Mac |
| 4 — iOS target | Add Xcode target, link binary, MediaPipe, sideload | Swift interface working |
| 5 — Validation | End-to-end test on device | iOS target builds and deploys |
