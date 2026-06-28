import Foundation
import AgentOSKit

/// Owns the chat state and talks to the kernel via AgentOSKit.
/// @MainActor so all @Published mutations happen on the main thread.
@MainActor
final class ChatViewModel: ObservableObject {

    @Published var messages: [Message] = []
    @Published var input = ""
    @Published var isSending = false
    @Published var agents: [AgentSummary] = []
    @Published var selectedAgentName = "skipper"
    @Published var health: HealthStatus?
    @Published var errorText: String?

    @Published var baseURLString: String
    @Published var userId: String

    let sessionId: String
    private var client: AgentOSClient
    private let transcript = TranscriptStore()

    init() {
        let defaults = UserDefaults.standard

        if let existing = defaults.string(forKey: "skipper.sessionId") {
            sessionId = existing
        } else {
            let sid = "macos-" + String(UUID().uuidString.prefix(12))
            defaults.set(sid, forKey: "skipper.sessionId")
            sessionId = sid
        }

        let urlString = defaults.string(forKey: "skipper.baseURL") ?? "http://127.0.0.1:1776"
        baseURLString = urlString
        userId = defaults.string(forKey: "skipper.userId") ?? "mario"
        client = AgentOSClient(baseURL: URL(string: urlString) ?? URL(string: "http://127.0.0.1:1776")!)
    }

    /// Called once when the window appears: restore transcript, probe the kernel.
    func bootstrap() async {
        messages = transcript.load(sessionId: sessionId)
        await refresh()
    }

    /// Persist settings and repoint the client.
    func applySettings() {
        let defaults = UserDefaults.standard
        defaults.set(baseURLString, forKey: "skipper.baseURL")
        defaults.set(userId, forKey: "skipper.userId")
        client = AgentOSClient(baseURL: URL(string: baseURLString) ?? URL(string: "http://127.0.0.1:1776")!)
        Task { await refresh() }
    }

    /// GET /health + /agents. Defaults the selection to Skipper when present.
    func refresh() async {
        do {
            let h = try await client.health()
            let a = try await client.agents()
            health = h
            agents = a
            if !a.contains(where: { $0.name == selectedAgentName }) {
                selectedAgentName = a.contains(where: { $0.name == "skipper" })
                    ? "skipper"
                    : (a.first?.name ?? selectedAgentName)
            }
            errorText = nil
        } catch {
            health = nil
            errorText = error.localizedDescription
        }
    }

    /// Send the composer text as one turn.
    func send() async {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isSending else { return }
        input = ""
        isSending = true
        defer { isSending = false }

        messages.append(Message(role: .user, text: text))
        transcript.save(messages, sessionId: sessionId)

        do {
            let req = ChatRequest(
                agentName: selectedAgentName,
                userMessage: text,
                sessionId: sessionId,
                mode: "macos",
                userId: userId.isEmpty ? nil : userId
            )
            let resp = try await client.chat(req)
            if let reply = resp.response, !reply.isEmpty {
                messages.append(Message(role: .assistant, text: reply))
            } else if let firstErr = resp.cellErrors.first {
                messages.append(Message(role: .system, text: "\(firstErr.key) — \(firstErr.value)"))
            } else {
                messages.append(Message(role: .system, text: "Empty response from the kernel."))
            }
            errorText = nil
        } catch {
            messages.append(Message(role: .system, text: error.localizedDescription))
            errorText = error.localizedDescription
        }
        transcript.save(messages, sessionId: sessionId)
    }

    func clearTranscript() {
        messages = []
        transcript.save(messages, sessionId: sessionId)
    }
}
