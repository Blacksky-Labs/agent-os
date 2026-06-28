# Skipper.app — macOS Packaging & Auto-Update Plan

*Blacksky Labs | 2026-06-20 | Companion to native-client-plan.md and skipper-audit.md*
*Distribution decision: direct download + Sparkle (no App Store, no platform cut).*

---

## 0. The one principle: separate code from data

An app update replaces the `.app` bundle. Memory must live **outside** the bundle so an update never touches it.

- **Code** (replaced on every update): the Swift UI + the compiled AgentOS kernel, inside `Skipper.app`.
- **Data** (never touched by updates): `~/Library/Application Support/Skipper/` — `memory.db`, the config overlay, corpus, model.

Then the loop is: **update → relaunch → `agentos resume skipper` → exact continuity.** Software updates become invisible to memory. This is the cornerstone everything else hangs on, and it's the one thing worth wiring into the kernel *now* (see §6).

---

## 1. Anatomy of Skipper.app

```
Skipper.app/                         ← the notarizable top-level bundle (Swift)
  Contents/
    MacOS/Skipper                    ← Swift launcher + SwiftUI chat (AgentOSKit)
    Resources/
      kernel/                        ← the compiled AgentOS kernel (standalone)
      manifests/ cells/ personas/    ← agent definition (ships read-only with the app)
    Info.plist                       ← Sparkle public EdDSA key, feed URL, ATS localhost
```

**Runtime:** on launch the Swift app spawns the bundled kernel — `agentos resume skipper` — bound to `127.0.0.1:1776`, waits for `/health`, then shows the chat. On quit it terminates the child. (We already built `start`/`resume`, `/health` with `running_agent`/`active_session`, and the macOS scaffold — this is the wiring that joins them.)

**Data home:** the kernel reads `AGENTOS_DATA_DIR`; the app sets it to `~/Library/Application Support/Skipper/`. That's where all mutable state lives.

---

## 2. Bundling the Python kernel (IP + no "install Python")

The kernel ships compiled so there's no Python install step and the IP is protected (per the seed).

**Verified current reality (2026):**
- **Nuitka** transpiles Python → C → native: best startup speed and strongest IP protection — but it produces **non-standard app bundles that fail Apple notarization repeatedly** (dylibs must sit in `Contents/Frameworks`, no data files in `MacOS`/`Frameworks` — poorly-documented notarization rules).
- **PyInstaller** bundles the interpreter + deps: more standard layout, but **slow startup** and still needs careful signing.
- Both hit the same wall: unsigned nested binaries → Gatekeeper blocks.

**Recommended architecture — kernel as a signed nested helper, not its own .app.** Don't let Nuitka/PyInstaller produce the top-level bundle. Instead:
- The **Swift app is the top-level `.app`** (standard, notarizes cleanly).
- The compiled kernel is a **standalone executable directory nested in `Contents/Resources/kernel/`**, signed as nested code.

This sidesteps Nuitka's top-level-bundle notarization problem (the failing part is the *outer* bundle structure, which Swift now owns). Use **Nuitka** for the kernel binary (speed + IP); fall back to PyInstaller only if signing the nested Nuitka output fights back.

**Embedded-Python signing caveats:** hardened runtime needs entitlements `com.apple.security.cs.disable-library-validation` and (likely) `allow-unsigned-executable-memory` for an embedded interpreter; sign nested binaries before the outer `.app`.

---

## 3. Auto-update with Sparkle (verified current)

**Sparkle 2** is the standard: **EdDSA (ed25519) signatures** on the update archive **plus** Apple code signing + notarization; an **RSS `appcast.xml`** feed; supports sandboxed apps.

**Release flow:**
1. Build `Skipper.app` → codesign (Developer ID, hardened runtime) → **notarize** (`notarytool`) → **staple**.
2. Package as a DMG (or zip).
3. **EdDSA-sign** the archive (`sign_update`) with your private key; the public key lives in `Info.plist`.
4. Update `appcast.xml` (version, URL, EdDSA signature, release notes) and upload the appcast + DMG to your host.
5. The app checks the feed, verifies EdDSA + code signature, swaps itself, relaunches.

**Automate it** (GitHub Actions, standard in 2026): build → notarize → staple → EdDSA-sign → regenerate `appcast.xml` → upload. One push ships an update.

**Business-model fit:** direct download + Sparkle = one-time purchase, free updates forever, **no App Store cut**. Payment/licensing is separate (no App Store receipt) — see §8.

---

## 4. The update → resume flow (no amnesia)

1. Sparkle replaces the `.app` bundle (code only).
2. `~/Library/Application Support/Skipper/` (memory, config, model) is untouched.
3. Relaunch → Swift spawns `agentos resume skipper` → prior conversation + everything learned are exactly where they were.

**Schema migrations:** if a kernel update changes the `memory.db` schema, run lightweight versioned migrations on launch. Today the cells create tables idempotently (`CREATE TABLE IF NOT EXISTS`), which covers additive changes; add a migration step when a breaking change lands.

---

## 5. The model is not in the bundle

Gemma is multiple GB. Shipping it inside the `.app` makes every update a multi-GB download. Instead:
- **First-launch download** of the model into `~/Library/Application Support/Skipper/models/` (the seed's plan), with progress UI.
- Model updates then happen **independently** of app updates — and a reinstall/app-update never re-downloads it.

---

## 6. The one code change to make now: a configurable data home

Independent of all the packaging work, this is the foundational change and it's small + verifiable in the kernel:

- Add `AGENTOS_DATA_DIR` (default: `./data` for dev; the app sets it to Application Support).
- Route the per-namespace `memory.db`, the `config.overrides.yaml`, and the corpus through it (`db_path_for`, the overlay path, retrieval store).

After this, "updates don't forget" is true regardless of how we package — the data simply isn't in the bundle.

---

## 7. Phased path

- **Phase A — Data home** *(kernel, do now)*: configurable `AGENTOS_DATA_DIR`; memory/overlay/corpus route through it.
- **Phase B — Bundle the kernel**: Nuitka standalone of `agentos`; the macOS app launches it from `Contents/Resources/kernel/` on `localhost`; prove `/health` + a chat turn from inside the `.app`.
- **Phase C — Sparkle**: EdDSA keypair, `Info.plist` feed + key, in-app updater UI, first signed + notarized DMG + `appcast.xml`.
- **Phase D — CI**: GitHub Actions build → notarize → staple → EdDSA-sign → appcast → upload.
- **Phase E — Licensing**: one-time-purchase key (no App Store receipt) + the paid-upgrade tiers from the seed.

---

## 8. Open decisions

1. **Nuitka vs PyInstaller** for the nested kernel — recommend prototyping **Nuitka-as-nested-helper** (speed + IP); fall back to PyInstaller if notarizing the nested Nuitka output resists.
2. **Hosting** for `appcast.xml` + DMGs — your server, S3 + CloudFront, or GitHub Releases.
3. **Licensing/payment** for one-time purchase — Paddle, Lemon Squeezy, Gumroad, or Stripe + a license-key gate (no App Store, so this is on us).
4. **Code-signing identity** — confirm the Blacksky Apple Developer ID for signing + notarization.

---

*Next build step: Phase A (the data home) — small, in-kernel, and the thing that makes every later phase safe. Everything else (bundling, Sparkle, CI, licensing) happens on the Mac in Xcode + your build pipeline.*
