import SwiftUI

// Entry point for the AgentOS iOS app. Starts the embedded Python kernel, then shows
// the chat. Everything runs on-device; memory lives in the app's sandbox container so it
// survives every Xcode redeploy. See agentos-ios-build-plan.md.
@main
struct AgentOSApp: App {
    @StateObject private var kernel = PythonKernel.shared

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(kernel)
                .task { kernel.start() }
        }
    }
}
