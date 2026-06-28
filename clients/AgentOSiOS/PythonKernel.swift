import Foundation
#if canImport(PythonKit) && STAGE2_EMBED
import PythonKit
#endif

/// Bridges Swift ↔ the embedded AgentOS Python kernel.
///
/// Two modes, chosen at compile time by whether PythonKit (the embedded Python) is linked:
///  • **Real** (`canImport(PythonKit)`) — points the embedded CPython at the bundled `app/`
///    sources, sets `AGENTOS_DATA_DIR` to the sandbox container (memory survives updates),
///    imports `agentos.runtime`, registers the Swift/Gemma inference backend, and runs turns
///    via `ao_call`.
///  • **Demo** (no PythonKit yet) — a SwiftUI shell with stub replies, so you can sideload to a
///    device and validate signing/deploy before doing the embedding (IOS_BUILD.md stage 1).
@MainActor
final class PythonKernel: ObservableObject {
    static let shared = PythonKernel()

    @Published private(set) var ready = false

    /// The app's sandbox container — data lives here (NOT in the bundle), so it survives
    /// every Xcode redeploy. Only deleting the app wipes it.
    private var dataDir: String {
        (try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                      appropriateFor: nil, create: true).path) ?? NSTemporaryDirectory()
    }

#if canImport(PythonKit) && STAGE2_EMBED
    private var runtime: PythonObject!

    func start() {
        guard !ready else { return }
        let res = Bundle.main.resourceURL!
        let home = res.appendingPathComponent("python").path     // PYTHONHOME → contains lib/python3.13
        let appDir = res.appendingPathComponent("app").path

        setenv("PYTHONHOME", home, 1)
        setenv("PYTHONPATH", appDir, 1)
        setenv("PYTHONUTF8", "1", 1)
        setenv("AGENTOS_DATA_DIR", dataDir, 1)
        // Help PythonKit locate the embedded libpython — the part most likely to need tuning.
        setenv("PYTHON_LIBRARY",
               Bundle.main.bundleURL.appendingPathComponent("Frameworks/Python.framework/Python").path, 1)

        NSLog("AGENTOS: home=%@", home)
        let sys = Python.import("sys")                  // crash here → interpreter/libpython not found
        NSLog("AGENTOS: Python %@", String(describing: sys.version))

        let rt = Python.import("agentos.runtime")        // crash here → staged app not on sys.path
        rt.ao_init(appDir, dataDir)
        self.runtime = rt
        NSLog("AGENTOS: kernel runtime ready")

        // Python calls back here for every model turn; Swift runs Gemma.
        let llm = Python.import("agentos.llm")
        let backend = PythonFunction { (args: [PythonObject]) -> PythonConvertible in
            let prompt = Self.lastUserText(args[0]["messages"])
            return ["content": PythonObject(GemmaBackend.shared.complete(prompt: prompt)),
                    "usage": Python.None]
        }
        llm.set_inference_backend(backend.pythonObject)
        ready = true
        NSLog("AGENTOS: ready ✓")
    }

    func send(_ message: String, session: String = "default") -> String {
        guard ready else { return "(kernel not ready)" }
        let payload: [String: Any] = ["agent": "skipper", "message": message, "session_id": session]
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let jsonIn = String(data: data, encoding: .utf8) else { return "(bad request)" }
        let jsonOut = String(runtime.ao_call(jsonIn)) ?? "{}"
        guard let d = jsonOut.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else {
            return "(bad response)"
        }
        return (obj["response"] as? String) ?? (obj["error"] as? String) ?? "(no response)"
    }

    private static func lastUserText(_ messages: PythonObject) -> String {
        guard let count = Int(Python.len(messages)) else { return "" }
        for i in stride(from: count - 1, through: 0, by: -1) {
            let m = messages[i]
            if String(m["role"]) == "user" { return String(m["content"]) ?? "" }
        }
        return ""
    }
#else
    // Demo mode — embedded Python not wired yet. Proves the iOS shell on a real device.
    func start() { ready = true }

    func send(_ message: String, session: String = "default") -> String {
        "(demo — embedded Python not wired yet)\n" + GemmaBackend.shared.complete(prompt: message)
    }
#endif
}
