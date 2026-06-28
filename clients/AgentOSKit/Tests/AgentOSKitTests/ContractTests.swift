import XCTest
@testable import AgentOSKit

/// Decoding tests against literal payloads shaped exactly like agentos/main.py
/// returns. These run with no server — they pin the wire contract so a backend
/// rename can't silently break the client.
final class ContractTests: XCTestCase {

    func testDecodeChatResponse() throws {
        let json = """
        {
          "response": "Hey Mario. What's on your mind?",
          "turn_id": "t_abc123",
          "namespace": "skipper",
          "cell_timings": {"mode-control": 0.4, "llm-interface": 812.0},
          "cell_errors": {},
          "usage": {"prompt_tokens": 120, "completion_tokens": 18, "total_tokens": 138}
        }
        """.data(using: .utf8)!

        let r = try JSONDecoder().decode(ChatResponse.self, from: json)
        XCTAssertEqual(r.turnId, "t_abc123")
        XCTAssertEqual(r.namespace, "skipper")
        XCTAssertEqual(r.response, "Hey Mario. What's on your mind?")
        XCTAssertTrue(r.cellErrors.isEmpty)
    }

    func testDecodeChatResponseWithCellError() throws {
        let json = """
        {
          "response": null,
          "turn_id": "t_def456",
          "namespace": "skipper",
          "cell_timings": {},
          "cell_errors": {"llm-interface": "APIConnectionError: ollama not reachable"}
        }
        """.data(using: .utf8)!

        let r = try JSONDecoder().decode(ChatResponse.self, from: json)
        XCTAssertNil(r.response)
        XCTAssertEqual(r.cellErrors["llm-interface"], "APIConnectionError: ollama not reachable")
    }

    func testDecodeAgents() throws {
        let json = """
        {"agents": [{"name": "skipper", "display_name": "Skipper", "provider": "ollama", "model": "ollama/gemma3:4b"}]}
        """.data(using: .utf8)!

        let wrapper = try JSONDecoder().decode(AgentsResponse.self, from: json)
        XCTAssertEqual(wrapper.agents.first?.title, "Skipper")
        XCTAssertEqual(wrapper.agents.first?.model, "ollama/gemma3:4b")
    }

    func testEncodeChatRequestUsesSnakeCase() throws {
        let req = ChatRequest(agentName: "skipper", userMessage: "hi", sessionId: "s1")
        let data = try JSONEncoder().encode(req)
        let obj = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(obj["agent_name"] as? String, "skipper")
        XCTAssertEqual(obj["user_message"] as? String, "hi")
        XCTAssertEqual(obj["session_id"] as? String, "s1")
        XCTAssertEqual(obj["mode"] as? String, "macos")
    }
}
