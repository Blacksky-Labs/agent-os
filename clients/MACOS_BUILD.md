# Skipper.app — assemble & ship (direct download + Sparkle)

Companion to `macos-packaging-plan.md`. The code is in `clients/`; the build runs
on your Mac. Direct download, **not** App Store — so no App Sandbox, no platform cut.

## Files in this drop

- `AgentOSKit/` — shared Swift core (models, HTTP client, transcript store)
- `AgentOSMac/`
  - `SkipperApp.swift` — `@main`; starts the kernel, shows chat, stops kernel on quit; "Check for Updates…"
  - `KernelController.swift` — launches the bundled kernel (`agentos resume skipper`) with `AGENTOS_DATA_DIR` → Application Support; waits for `/health`
  - `Updater.swift` — Sparkle wrapper
  - `ChatView/AgentPicker/Settings/ChatViewModel.swift` — UI
  - `Skipper.entitlements` — hardened-runtime entitlements for the embedded interpreter
- `project.yml` — XcodeGen spec: defines the app, the local AgentOSKit package, Sparkle, entitlements, Info.plist, and a build phase that embeds the kernel
- `build-kernel.sh` — Nuitka compile of the kernel (shared by local + release)
- `build-local.sh` — **the local path**: compile kernel → generate + build app → embed kernel → ad-hoc sign → launch
- `build-macos.sh` — **the release path**: kernel → assemble → codesign (Developer ID) → notarize → staple → EdDSA-sign → appcast
- `../agentos/__main__.py` — kernel entry (`python -m agentos`, and Nuitka's compile target)

## 1. Run it locally (one command)

No Developer ID, no notarization. Prereqs:

```bash
brew install xcodegen
pip install -e . && pip install nuitka
ollama pull gemma4:e4b        # the app talks to your local Ollama; keep Ollama running
```

Then:

```bash
./clients/build-local.sh
```

That compiles the kernel, generates `Skipper.xcodeproj` from `project.yml`, builds the app,
embeds the kernel at `Contents/Resources/kernel/agentos`, ad-hoc signs the bundle, and opens it.
You should see "Starting Skipper…" then the chat; quitting stops the kernel. Memory + config
live in `~/Library/Application Support/Skipper/` (via `AGENTOS_DATA_DIR`).

To iterate on the **UI** in Xcode, open `Skipper.xcodeproj` and Run (⌘R) — the embed-kernel
build phase reuses the last compiled kernel (re-run `build-kernel.sh` when the Python changes).
Reasoning is single-model by default; turn MoE on per-entity from the in-app dashboard.

## 3. One-time release setup

```bash
pip install -e . && pip install nuitka
# Sparkle tools come with the Sparkle release (Sparkle/bin/)
./clients/Sparkle/bin/generate_keys          # prints the public EdDSA key → Info.plist SUPublicEDKey
xcrun notarytool store-credentials skipper-notary \
  --apple-id you@blacksky.com --team-id TEAMID --password <app-specific-password>
```

## 4. Cut a release

First flip `project.yml` from local to release signing, then `xcodegen generate`:
`CODE_SIGN_IDENTITY` → your Developer ID, `ENABLE_HARDENED_RUNTIME` → `YES`, and add
`SUPublicEDKey` (from `generate_keys`) + `SUEnableAutomaticChecks: true` to the Info.plist
properties. Archive/export the `.app` in Xcode (Developer ID), then:

```bash
VERSION=0.1.0 DEV_ID="Developer ID Application: Blacksky LLC (TEAMID)" \
  ./clients/build-macos.sh /path/to/exported/Skipper.app
```

Upload `clients/releases/{Skipper-<v>.dmg, appcast.xml}` to the host behind `SUFeedURL`.
Bump `VERSION`, rebuild, re-run — Sparkle does the rest for users.

## 5. Why updates don't forget

The `.app` (Swift UI + compiled kernel) is replaced on update. Memory, config, and
model live in `~/Library/Application Support/Skipper/` (via `AGENTOS_DATA_DIR`) and are
never touched. After an update the app relaunches → `agentos resume skipper` → the
conversation and everything learned are exactly where they were.

## Known rough edges (expect iteration)

- **Nuitka + notarization** is fiddly (non-standard nested binaries); if signing the
  nested kernel resists, fall back to PyInstaller for the kernel, same assembly.
- **Port 1776** is hardcoded; add a free-port finder in `KernelController` before shipping.
- **The model** (Gemma) is not bundled — add a first-launch download into
  `Application Support/Skipper/models/` (per the plan) before release.
- **Licensing** (one-time purchase key) is a separate gate — not in this drop.
