import Foundation

/// Launches the bundled AgentOS kernel as a child process and shuts it down on
/// quit. The kernel runs on a loopback port; the app talks to it via
/// AgentOSClient. All mutable state lives in Application Support (set via
/// AGENTOS_DATA_DIR) so software updates never touch what the entity has learned.
///
/// Direct-download build (no App Sandbox): launching the embedded kernel and
/// reaching localhost work without sandbox temporary-exception gymnastics.
/// Hardened runtime + entitlements (see Skipper.entitlements) cover notarization.
@MainActor
final class KernelController: ObservableObject {

    enum Status: Equatable {
        case stopped, starting, ready, failed(String)
    }

    @Published private(set) var status: Status = .stopped

    let agent: String
    let port: Int
    /// When set (by the app once the embedded llama.cpp server is up), the kernel
    /// routes all inference here via AGENTOS_LLM_API_BASE instead of the manifest's
    /// default. Left nil → the kernel falls back to whatever the manifest declares.
    var llmApiBase: URL?
    private var process: Process?
    private var logURL: URL?

    init(agent: String = "skipper", port: Int? = nil) {
        self.agent = agent
        self.port = port ?? Net.freePort()
    }

    var baseURL: URL { URL(string: "http://127.0.0.1:\(port)")! }

    /// ~/Library/Application Support/Skipper — survives every app update.
    private func dataDir() throws -> URL {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory, in: .userDomainMask,
            appropriateFor: nil, create: true)
        let dir = base.appendingPathComponent("Skipper", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    /// The compiled kernel ships at Contents/Resources/kernel/agentos,
    /// alongside cells.registry.yaml + manifests/ + personas/ (read at runtime).
    private func kernelExecutable() -> URL? {
        Bundle.main.resourceURL?
            .appendingPathComponent("kernel", isDirectory: true)
            .appendingPathComponent("agentos")
    }

    func start() {
        guard process == nil else { return }
        status = .starting
        do {
            guard let exe = kernelExecutable(),
                  FileManager.default.fileExists(atPath: exe.path) else {
                status = .failed("Bundled kernel not found at Resources/kernel/agentos")
                return
            }
            let kernelRoot = exe.deletingLastPathComponent()  // contains the registry + manifests
            let data = try dataDir()

            // Capture the kernel's stdout+stderr to a log so a startup crash is
            // visible (in the failure overlay + on disk) instead of an endless spinner.
            let log = data.appendingPathComponent("kernel.log")
            FileManager.default.createFile(atPath: log.path, contents: nil)
            let logHandle = try FileHandle(forWritingTo: log)
            logURL = log

            let p = Process()
            p.executableURL = exe
            p.arguments = ["resume", agent, "--host", "127.0.0.1", "--port", "\(port)"]
            p.currentDirectoryURL = kernelRoot
            var env = ProcessInfo.processInfo.environment
            env["AGENTOS_DATA_DIR"] = data.path
            env["AGENTOS_AGENT"] = agent
            env["AGENTOS_PORT"] = "\(port)"
            // A GUI-launched process inherits no locale, so the embedded Python would
            // default to ASCII and crash on non-ASCII (— → • …) in the YAML manifests.
            // Force UTF-8 for the interpreter and its file I/O.
            env["PYTHONUTF8"] = "1"
            env["LANG"] = "en_US.UTF-8"
            env["LC_ALL"] = "en_US.UTF-8"
            if let api = llmApiBase {
                env["AGENTOS_LLM_API_BASE"] = api.absoluteString   // route inference to the embedded runtime
            }
            p.environment = env
            p.standardOutput = logHandle
            p.standardError = logHandle
            p.terminationHandler = { [weak self] proc in
                let code = proc.terminationStatus
                Task { @MainActor in self?.handleTermination(code: code) }
            }
            try p.run()
            process = p
            Task { await waitForHealth() }
        } catch {
            status = .failed(error.localizedDescription)
        }
    }

    /// Start the kernel and wait until it's healthy (or has failed). Returns true on ready.
    func startAndWait() async -> Bool {
        start()
        for _ in 0..<160 {                  // ~40s at 250ms
            switch status {
            case .ready: return true
            case .failed, .stopped: return false
            default: try? await Task.sleep(nanoseconds: 250_000_000)
            }
        }
        return status == .ready
    }

    private func handleTermination(code: Int32) {
        process = nil
        switch status {
        case .starting:
            // Exited before reporting healthy — surface why instead of spinning forever.
            status = .failed("Kernel exited (code \(code)).\n\n\(logTail())")
        case .ready:
            status = .stopped
        default:
            break
        }
    }

    /// Tail of the kernel log, shown in the failure overlay.
    private func logTail(_ maxChars: Int = 1500) -> String {
        guard let url = logURL,
              let s = try? String(contentsOf: url, encoding: .utf8), !s.isEmpty else {
            return "No kernel output was captured."
        }
        return s.count > maxChars ? "…" + String(s.suffix(maxChars)) : s
    }

    private func waitForHealth() async {
        let url = baseURL.appendingPathComponent("health")
        for _ in 0..<60 {  // up to ~30s for first-launch model warmup etc.
            if let (_, resp) = try? await URLSession.shared.data(from: url),
               let http = resp as? HTTPURLResponse, http.statusCode == 200 {
                if status == .starting { status = .ready }
                return
            }
            try? await Task.sleep(nanoseconds: 500_000_000)
        }
        if status == .starting {
            status = .failed("Kernel did not report healthy in time.\n\n\(logTail())")
        }
    }

    /// Must be called on quit — a child Process does not die with its parent.
    func stop() {
        process?.terminate()
        process = nil
        status = .stopped
    }
}
