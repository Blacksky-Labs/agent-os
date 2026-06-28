import Foundation
import AppKit

/// Runs llama.cpp's `llama-server` on a loopback port so inference is fully on-device —
/// no Ollama. `llama-server` is OpenAI-compatible, so the kernel talks to it through the
/// exact same `/v1/chat/completions` path (`agentos/llm.py`); the app just points
/// `AGENTOS_LLM_API_BASE` at this server's port.
///
/// Phase 0: the binary comes from `brew install llama.cpp` (or a bundled copy at
/// Resources/llama/llama-server once we package it); the GGUF model is pulled from
/// Hugging Face on first run and cached. See ios-port-plan.md §3.
@MainActor
final class LlamaServerController: ObservableObject {

    enum Status: Equatable {
        case stopped, preparing, ready, failed(String)
    }

    @Published private(set) var status: Status = .stopped

    let port: Int
    let hfRepo: String        // Hugging Face GGUF repo:quant — llama-server pulls + caches it
    let alias: String         // model name it reports (matches the manifest's stripped name)

    private var process: Process?
    private var logURL: URL?

    init(port: Int? = nil,
         hfRepo: String = "unsloth/gemma-4-E4B-it-GGUF:Q4_K_M",
         alias: String = "gemma4:e4b") {
        self.port = port ?? Net.freePort()
        self.hfRepo = hfRepo
        self.alias = alias
    }

    var baseURL: URL { URL(string: "http://127.0.0.1:\(port)")! }

    /// llama-server: a bundled copy first (Resources/llama/llama-server), else Homebrew.
    private func serverExecutable() -> URL? {
        if let bundled = Bundle.main.resourceURL?
            .appendingPathComponent("llama/llama-server"),
           FileManager.default.isExecutableFile(atPath: bundled.path) {
            return bundled
        }
        for p in ["/opt/homebrew/bin/llama-server", "/usr/local/bin/llama-server"]
        where FileManager.default.isExecutableFile(atPath: p) {
            return URL(fileURLWithPath: p)
        }
        return nil
    }

    func startAndWait() async -> Bool {
        start()
        for _ in 0..<1200 {                       // up to ~10 min (first run downloads the model)
            switch status {
            case .ready: return true
            case .failed: return false
            default: try? await Task.sleep(nanoseconds: 500_000_000)
            }
        }
        return status == .ready
    }

    func start() {
        guard process == nil else { return }
        status = .preparing
        guard let exe = serverExecutable() else {
            status = .failed("llama-server not found. Install it once with:  brew install llama.cpp")
            return
        }
        do {
            let dir = try dataDir()
            let log = dir.appendingPathComponent("llama-server.log")
            FileManager.default.createFile(atPath: log.path, contents: nil)
            let handle = try FileHandle(forWritingTo: log)
            logURL = log

            let p = Process()
            p.executableURL = exe
            p.arguments = ["-hf", hfRepo, "--host", "127.0.0.1", "--port", "\(port)", "--alias", alias]
            p.standardOutput = handle
            p.standardError = handle
            p.terminationHandler = { [weak self] proc in
                let code = proc.terminationStatus
                Task { @MainActor in self?.handleTermination(code: code) }
            }
            try p.run()
            process = p
            Task { await waitForReady() }
        } catch {
            status = .failed(error.localizedDescription)
        }
    }

    private func dataDir() throws -> URL {
        let base = try FileManager.default.url(
            for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
        let dir = base.appendingPathComponent("Skipper", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func waitForReady() async {
        let url = baseURL.appendingPathComponent("v1/models")
        for _ in 0..<1200 {                        // ~10 min ceiling for the first-run download
            if process == nil { return }
            if let (_, resp) = try? await URLSession.shared.data(from: url),
               let http = resp as? HTTPURLResponse, http.statusCode == 200 {
                if status == .preparing { status = .ready }
                return
            }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
        if status == .preparing {
            status = .failed("llama-server didn’t become ready in time.\n\n\(logTail())")
        }
    }

    private func handleTermination(code: Int32) {
        process = nil
        if status == .preparing {
            status = .failed("llama-server exited (code \(code)).\n\n\(logTail())")
        } else if status == .ready {
            status = .stopped
        }
    }

    private func logTail(_ maxChars: Int = 1500) -> String {
        guard let url = logURL, let s = try? String(contentsOf: url, encoding: .utf8), !s.isEmpty else {
            return "No llama-server output captured."
        }
        return s.count > maxChars ? "…" + String(s.suffix(maxChars)) : s
    }

    func stop() {
        process?.terminate()
        process = nil
        status = .stopped
    }
}
