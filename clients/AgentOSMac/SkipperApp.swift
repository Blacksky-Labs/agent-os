import SwiftUI

// Entry point for the Skipper macOS app.
//
// On launch it starts the bundled kernel (KernelController), waits for it to be
// healthy, then shows the chat. On quit it stops the kernel. Sparkle provides
// "Check for Updates…". See clients/MACOS_BUILD.md to assemble in Xcode.

@main
struct SkipperApp: App {
    @StateObject private var kernel = KernelController(agent: "skipper")   // OS-assigned free port
    @StateObject private var vm = ChatViewModel()
    @StateObject private var updater = Updater()
    @StateObject private var llama = LlamaServerController()
    @State private var showSettings = false
    @State private var section: AppSection = .chat
    @State private var bypassLlama = false

    var body: some Scene {
        WindowGroup {
            ZStack {
                NavigationSplitView {
                    AgentPickerView(vm: vm).frame(minWidth: 220)
                } detail: {
                    Group {
                        if section == .chat {
                            ChatView(vm: vm)
                        } else {
                            DashboardPane(baseURL: kernel.baseURL, path: section.path,
                                          ready: kernel.status == .ready)
                        }
                    }
                    .frame(minWidth: 520, minHeight: 480)
                }
                .toolbar {
                    ToolbarItem(placement: .principal) {
                        Picker("View", selection: $section) {
                            ForEach(AppSection.allCases) { Text($0.title).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        .help("Switch between chat and the dashboards")
                    }
                    ToolbarItem(placement: .primaryAction) {
                        Button { showSettings = true } label: { Image(systemName: "gearshape") }
                            .help("Settings")
                    }
                }
                .sheet(isPresented: $showSettings) { SettingsView(vm: vm) }

                if case .preparing = llama.status {
                    // First launch downloads the model (minutes) — run the cinematic
                    // slideshow instead of a bare spinner.
                    SlideshowView(status: llama.status, onContinue: { bypassLlama = true })
                } else if case .failed = llama.status, !bypassLlama {
                    LlamaOverlay(status: llama.status, onContinue: { bypassLlama = true })
                } else if kernel.status != .ready {
                    KernelOverlay(status: kernel.status)
                }
            }
            .task {
                // Bring up the on-device runtime first, then point the kernel at it.
                if await llama.startAndWait() {
                    kernel.llmApiBase = llama.baseURL
                }
                // Kernel starts regardless — if llama isn't available it uses the manifest default.
                _ = await kernel.startAndWait()
                await vm.bootstrap()
            }
            // Child processes don't die with the parent — stop both on quit.
            .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
                kernel.stop()
                llama.stop()
            }
        }
        .windowResizability(.contentSize)
        .commands { UpdaterCommands(updater: updater) }
    }
}

/// Covers the window until the kernel is healthy, or explains a startup failure.
struct KernelOverlay: View {
    let status: KernelController.Status

    var body: some View {
        VStack(spacing: 12) {
            switch status {
            case .ready:
                EmptyView()
            case .failed(let message):
                Image(systemName: "exclamationmark.triangle")
                    .font(.largeTitle).foregroundStyle(.orange)
                Text("Skipper's kernel didn't start").font(.headline)
                ScrollView {
                    Text(message)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 20)
                }
                .frame(maxWidth: 560, maxHeight: 220)
                Text("Log: ~/Library/Application Support/Skipper/kernel.log")
                    .font(.caption2).foregroundStyle(.tertiary).textSelection(.enabled)
            default:
                ProgressView()
                Text("Starting Skipper…").foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.regularMaterial)
    }
}

/// Shown while the on-device llama.cpp runtime comes up (and downloads the model on
/// first launch). A failure here is non-fatal — the kernel falls back to the manifest's
/// runtime — so it offers "Continue anyway".
struct LlamaOverlay: View {
    let status: LlamaServerController.Status
    let onContinue: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            switch status {
            case .failed(let message):
                Image(systemName: "exclamationmark.triangle")
                    .font(.largeTitle).foregroundStyle(.orange)
                Text("On-device model unavailable").font(.headline)
                ScrollView {
                    Text(message)
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 20)
                }
                .frame(maxWidth: 560, maxHeight: 180)
                HStack(spacing: 16) {
                    Link("Install llama.cpp", destination: URL(string: "https://github.com/ggml-org/llama.cpp")!)
                    Button("Continue anyway", action: onContinue)
                }
                .font(.caption)
            default:   // .preparing / .stopped
                ProgressView()
                Text("Preparing the on-device model…").foregroundStyle(.secondary)
                Text("First launch downloads the model (~5 GB); it’s cached after this.")
                    .font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.regularMaterial)
    }
}

/// Top-level sections: the native chat plus the kernel's web dashboards.
enum AppSection: String, CaseIterable, Identifiable {
    case chat, overview, config, db
    var id: String { rawValue }
    var title: String {
        switch self {
        case .chat: "Chat"
        case .overview: "Overview"
        case .config: "Config"
        case .db: "DB"
        }
    }
    /// Path on the kernel; empty for the native chat.
    var path: String {
        switch self {
        case .chat: ""
        case .overview: "dashboard"
        case .config: "config"
        case .db: "db"
        }
    }
}
