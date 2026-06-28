# Pushing software updates to the app (Sparkle)

How a running copy of the app upgrades itself. The update **mechanism** is secured by
Sparkle's EdDSA signatures and needs **no Apple notarization** — notarization only
affects clean Gatekeeper on the *first* install (§4). So you can wire and test the
whole update flow today.

**Memory is never lost on update.** The `.app` (SwiftUI + compiled kernel) is replaced;
everything the entity learned lives in `~/Library/Application Support/Skipper/` (via
`AGENTOS_DATA_DIR`). After an update the app relaunches → `agentos resume` → the
conversation and profile are exactly where they were.

Scripts (all in `clients/`):

- `build-dmg.sh` — quick ad-hoc DMG of the current build (drag-to-Applications)
- `release-update.sh` — package → EdDSA-sign → (re)generate `releases/appcast.xml`
- `serve-updates.sh` — serve `releases/` on `http://localhost:8000` for local testing

---

## 1. One-time setup (turn updates on)

Sparkle's CLI tools come with the SPM package after a build. Find them once:

```bash
cd ~/sites/agentOS/clients
./build-local.sh            # fetches Sparkle into build/dd/SourcePackages
SPARKLE_BIN=$(find build/dd/SourcePackages/artifacts -type d -path '*Sparkle*/bin' | head -1)
echo "$SPARKLE_BIN"
```

Generate your signing keys (private key → your Keychain; public key printed):

```bash
"$SPARKLE_BIN/generate_keys"
```

Copy the printed **public** key into `project.yml` → `SUPublicEDKey: "…"`. That single
edit also activates the in-app updater (it stays inert while the key is empty). The
private key never leaves your Keychain — `generate_appcast` uses it automatically.

Set `SUFeedURL` in `project.yml` to wherever the appcast will live (your host for prod,
or `http://localhost:8000/appcast.xml` for the local test in §2).

---

## 2. Test the whole flow locally (no host, no notarization)

Prove an update installs before involving a server:

```bash
# a) build + install v0.1.0
#    set project.yml: SUFeedURL = http://localhost:8000/appcast.xml , SUPublicEDKey = <yours>
./build-local.sh
./build-dmg.sh
# drag Skipper.app from the DMG into /Applications, open it

# b) bump the version in project.yml: MARKETING_VERSION 0.1.1 AND CURRENT_PROJECT_VERSION 2
#    (Sparkle compares CURRENT_PROJECT_VERSION — it must increase)

# c) build the new version + sign it into the appcast, pointed at localhost
DOWNLOAD_URL_PREFIX="http://localhost:8000/" ./release-update.sh

# d) serve it
./serve-updates.sh
```

Now in the **running v0.1.0** app: menu → **Check for Updates…**. Sparkle reads the
local appcast, sees 0.1.1, verifies the EdDSA signature, installs, and relaunches into
your existing memory. That's the entire production loop, just with `localhost` as the host.

---

## 3. Push a real update

1. Host a static folder reachable at your `SUFeedURL` (S3, GitHub Releases, your server).
2. Bump `MARKETING_VERSION` **and** `CURRENT_PROJECT_VERSION` in `project.yml`.
3. Build + sign + appcast, with the URL prefix set to your host:
   ```bash
   DOWNLOAD_URL_PREFIX="https://updates.blacksky.org/skipper/" ./release-update.sh
   ```
4. Upload everything in `clients/releases/` (the `.dmg` + `appcast.xml`) to that host.

Every running copy checks the appcast on its schedule (`SUScheduledCheckInterval`, once
`SUEnableAutomaticChecks: true`) or when the user picks **Check for Updates…**, then
verifies + installs. To ship another update, repeat 2–4.

---

## 4. Making it official (notarization) — deferred

The quick DMG and the EdDSA update path both work, but the app is **ad-hoc signed**, so a
brand-new install on someone else's Mac trips Gatekeeper (right-click → Open, or
`xattr -dr com.apple.quarantine`). To remove that — clean double-click install anywhere —
notarize with your Apple Developer ID (you have the account):

1. In `project.yml`, flip to release signing: `CODE_SIGN_IDENTITY` → your *Developer ID
   Application*, `ENABLE_HARDENED_RUNTIME` → `YES`. Re-run `xcodegen generate`.
2. Create a notarytool credential profile once:
   ```bash
   xcrun notarytool store-credentials skipper-notary \
     --apple-id you@blacksky.com --team-id TEAMID --password <app-specific-password>
   ```
3. Use `build-macos.sh` instead of `build-local.sh` — it does Developer ID sign →
   notarize → staple → DMG → EdDSA-sign → appcast in one pass. The EdDSA half is identical
   to what you already tested, so your update flow is unchanged; notarization just adds the
   clean-Gatekeeper layer on top.

Nothing about §1–§3 changes when you do this — a notarized build is a strict superset.
