import Foundation

// Codable mirrors of the AgentOS HTTP contract (agentos/main.py).
// snake_case on the wire ↔ camelCase in Swift via CodingKeys.

/// `POST /chat` request body — matches `ChatRequest` in main.py.
public struct ChatRequest: Codable, Sendable {
    public let agentName: String
    public let userMessage: String
    public let sessionId: String
    public let mode: String
    public let userId: String?

    enum CodingKeys: String, CodingKey {
        case agentName = "agent_name"
        case userMessage = "user_message"
        case sessionId = "session_id"
        case mode
        case userId = "user_id"
    }

    public init(
        agentName: String,
        userMessage: String,
        sessionId: String,
        mode: String = "macos",
        userId: String? = nil
    ) {
        self.agentName = agentName
        self.userMessage = userMessage
        self.sessionId = sessionId
        self.mode = mode
        self.userId = userId
    }
}

/// `POST /chat` response — matches `ChatResponse` in main.py.
/// We decode the fields the UI needs; `cell_timings`/`usage` are ignored for now.
public struct ChatResponse: Codable, Sendable {
    public let response: String?
    public let turnId: String
    public let namespace: String
    public let cellErrors: [String: String]

    enum CodingKeys: String, CodingKey {
        case response
        case turnId = "turn_id"
        case namespace
        case cellErrors = "cell_errors"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        response = try c.decodeIfPresent(String.self, forKey: .response)
        turnId = try c.decode(String.self, forKey: .turnId)
        namespace = try c.decode(String.self, forKey: .namespace)
        cellErrors = try c.decodeIfPresent([String: String].self, forKey: .cellErrors) ?? [:]
    }
}

/// One entry from `GET /agents`.
public struct AgentSummary: Codable, Identifiable, Sendable, Hashable {
    public var id: String { name }
    public let name: String
    public let displayName: String?
    public let provider: String?
    public let model: String?

    enum CodingKeys: String, CodingKey {
        case name
        case displayName = "display_name"
        case provider
        case model
    }

    public var title: String { displayName ?? name }
}

struct AgentsResponse: Codable { let agents: [AgentSummary] }

/// `GET /health`.
public struct HealthStatus: Codable, Sendable {
    public let status: String
    public let version: String
    public let agentsLoaded: [String]
    public let cellsAvailable: [String]

    enum CodingKeys: String, CodingKey {
        case status
        case version
        case agentsLoaded = "agents_loaded"
        case cellsAvailable = "cells_available"
    }
}

/// A single line in a conversation, persisted locally on device.
public struct Message: Codable, Identifiable, Sendable, Hashable {
    public enum Role: String, Codable, Sendable { case user, assistant, system }

    public let id: UUID
    public let role: Role
    public let text: String
    public let date: Date

    public init(id: UUID = UUID(), role: Role, text: String, date: Date = Date()) {
        self.id = id
        self.role = role
        self.text = text
        self.date = date
    }
}
