import SwiftUI

/// A dashboard tab. Loads the kernel page once the kernel is healthy; until then
/// it shows a spinner (the page would 404/refuse before the server is up).
struct DashboardPane: View {
    let baseURL: URL
    let path: String          // "dashboard" | "config" | "db"
    let ready: Bool

    var body: some View {
        if ready {
            WebView(url: baseURL.appendingPathComponent(path))
        } else {
            VStack(spacing: 10) {
                ProgressView()
                Text("Waiting for the kernel…").foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(.regularMaterial)
        }
    }
}
