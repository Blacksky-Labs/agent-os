import Foundation

#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// Async client for the AgentOS HTTP kernel.
///
/// Local-first by default: points at `http://127.0.0.1:1776` (the kernel's
/// default bind, `AGENTOS_PORT`). An `actor` so concurrent calls are safe.
/// The base URL is immutable per instance — to repoint, make a new client.
public actor AgentOSClient {

    public enum ClientError: Error, LocalizedError {
        case badStatus(code: Int, body: String)
        case notConnected(underlying: String)

        public var errorDescription: String? {
            switch self {
            case let .badStatus(code, body):
                return "Server returned \(code): \(body)"
            case let .notConnected(underlying):
                return "Can't reach the kernel — is `agentos start skipper` running? (\(underlying))"
            }
        }
    }

    public let baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    public init(baseURL: URL = URL(string: "http://127.0.0.1:1776")!,
                session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }

    /// `GET /health` — liveness + which agents/cells the kernel sees.
    public func health() async throws -> HealthStatus {
        try await get("health")
    }

    /// `GET /agents` — every scaffolded agent (powers the picker).
    public func agents() async throws -> [AgentSummary] {
        let wrapper: AgentsResponse = try await get("agents")
        return wrapper.agents
    }

    /// `POST /chat` — run one turn through an agent's pipeline.
    public func chat(_ request: ChatRequest) async throws -> ChatResponse {
        try await post("chat", body: request)
    }

    // MARK: - Transport

    private func get<T: Decodable>(_ path: String) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "GET"
        return try await send(req)
    }

    private func post<Body: Encodable, T: Decodable>(_ path: String, body: Body) async throws -> T {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try encoder.encode(body)
        return try await send(req)
    }

    private func send<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw ClientError.notConnected(underlying: error.localizedDescription)
        }
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw ClientError.badStatus(code: http.statusCode, body: body)
        }
        return try decoder.decode(T.self, from: data)
    }
}
