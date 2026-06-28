import Foundation

/// Local, on-device transcript persistence — one JSON file per session under
/// Application Support. This is deliberately simple for the POC; when the
/// server-side `memory` cell becomes the source of truth, this becomes a cache.
///
/// Privacy note (see skipper-audit.md): nothing here leaves the device.
public final class TranscriptStore {

    private let directory: URL
    private let fileManager = FileManager.default

    public init(appFolder: String = "Skipper") {
        let base = (try? fileManager.url(for: .applicationSupportDirectory,
                                         in: .userDomainMask,
                                         appropriateFor: nil,
                                         create: true))
            ?? fileManager.temporaryDirectory
        self.directory = base.appendingPathComponent(appFolder, isDirectory: true)
        try? fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    private func url(for sessionId: String) -> URL {
        let safe = sessionId.replacingOccurrences(of: "/", with: "_")
        return directory.appendingPathComponent("transcript-\(safe).json")
    }

    public func load(sessionId: String) -> [Message] {
        let url = url(for: sessionId)
        guard let data = try? Data(contentsOf: url) else { return [] }
        return (try? JSONDecoder().decode([Message].self, from: data)) ?? []
    }

    public func save(_ messages: [Message], sessionId: String) {
        let url = url(for: sessionId)
        guard let data = try? JSONEncoder().encode(messages) else { return }
        try? data.write(to: url, options: .atomic)
    }
}
