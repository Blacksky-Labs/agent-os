import SwiftUI
import Sparkle

/// Thin wrapper over Sparkle's standard updater (direct-download auto-update).
///
/// Setup (see MACOS_BUILD.md):
///   1. Add the Sparkle Swift Package: https://github.com/sparkle-project/Sparkle
///   2. In Info.plist set `SUFeedURL` (your appcast.xml URL) and `SUPublicEDKey`
///      (the public half of your EdDSA key).
///   3. Releases are EdDSA-signed by build-macos.sh; Sparkle verifies signature
///      + Apple code signature before installing.
final class Updater: ObservableObject {
    private let controller: SPUStandardUpdaterController

    init() {
        // Only auto-start the scheduled updater when an EdDSA public key is configured
        // (release builds). Local/dev builds have no SUPublicEDKey, so they launch clean
        // and "Check for Updates…" simply reports it can't check — no startup error.
        let key = Bundle.main.object(forInfoDictionaryKey: "SUPublicEDKey") as? String
        let configured = !(key ?? "").isEmpty
        controller = SPUStandardUpdaterController(
            startingUpdater: configured, updaterDelegate: nil, userDriverDelegate: nil)
    }

    func checkForUpdates() { controller.checkForUpdates(nil) }
}

/// Adds "Check for Updates…" under the app menu. Use via `.commands { UpdaterCommands(updater:) }`.
struct UpdaterCommands: Commands {
    let updater: Updater

    var body: some Commands {
        CommandGroup(after: .appInfo) {
            Button("Check for Updates…") { updater.checkForUpdates() }
        }
    }
}
