// swift-tools-version: 5.9
import PackageDescription

// AgentOSKit — the shared, platform-independent core for every native AgentOS
// surface. The macOS app depends on it today; the iOS app will import it
// unchanged (Phase 3). Networking + models + local transcript only — no UI.
let package = Package(
    name: "AgentOSKit",
    platforms: [
        .macOS(.v13),
        .iOS(.v16),
    ],
    products: [
        .library(name: "AgentOSKit", targets: ["AgentOSKit"]),
    ],
    targets: [
        .target(name: "AgentOSKit"),
        .testTarget(name: "AgentOSKitTests", dependencies: ["AgentOSKit"]),
    ]
)
