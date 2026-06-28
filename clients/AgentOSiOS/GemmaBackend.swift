import Foundation

/// On-device Gemma inference — the Swift side of the seam. The embedded Python pipeline
/// calls this for every model turn (via `llm.set_inference_backend`), passing the prompt;
/// this runs Gemma 4 on the Neural Engine and returns the reply.
///
/// v0 is a STUB so the whole loop (UI → kernel → backend → reply) is testable before the
/// model is wired. Replace `complete(prompt:)` with MediaPipe LLM Inference or MLX-Swift
/// loading Gemma 4 E4B (download to the sandbox on first launch). See IOS_BUILD.md §4.
@MainActor
final class GemmaBackend {
    static let shared = GemmaBackend()

    func complete(prompt: String) -> String {
        // TODO: real inference (MediaPipe / MLX). For now, prove the round-trip:
        "(Gemma stub) You said: \(prompt)"
    }
}
