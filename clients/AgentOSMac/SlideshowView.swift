import SwiftUI
import AppKit

/// Full-screen first-launch slideshow, shown while the on-device model downloads
/// (LlamaServerController.Status == .preparing). That download is a one-time,
/// multi-minute wait; instead of a bare spinner we run a cinematic slideshow of
/// images + inspirational copy so the wait feels like an overture, not a hang.
///
/// Images come from the bundled `Slides/` folder (a folder reference — see
/// project.yml). Drop your own in there; they're shown full-screen in filename
/// order, each paired with one of the built-in quotes. If the folder has no
/// images yet, each slide falls back to an on-brand gradient so it's never blank.
struct SlideshowView: View {
    let status: LlamaServerController.Status
    let onContinue: () -> Void

    @State private var slides: [NSImage] = []
    @State private var index = 0
    @State private var zoomIn = false
    @State private var showContinue = false

    private let interval: TimeInterval = 7
    private let timer = Timer.publish(every: 7, on: .main, in: .common).autoconnect()

    /// Number of frames: one per image, or — before any images are added — one per quote.
    private var frameCount: Int { slides.isEmpty ? Quote.all.count : slides.count }

    var body: some View {
        ZStack {
            Color.black
            background
            scrim
            content
        }
        .ignoresSafeArea()
        .onAppear {
            slides = SlideLoader.load()
            kickZoom()
        }
        .onReceive(timer) { _ in advance() }
        .task {
            // Give the escape hatch a moment so people don't bail before they've read a slide.
            try? await Task.sleep(nanoseconds: 18 * 1_000_000_000)
            withAnimation(.easeInOut(duration: 0.5)) { showContinue = true }
        }
    }

    // MARK: layers

    private var background: some View {
        ZStack {
            ForEach(0..<frameCount, id: \.self) { i in
                if i == index {
                    SlideFrame(image: slides.indices.contains(i) ? slides[i] : nil,
                               gradient: Palette.gradient(i))
                        .scaleEffect(zoomIn ? 1.08 : 1.0)
                        .transition(.opacity)
                }
            }
        }
        .animation(.easeInOut(duration: 1.2), value: index)
        .clipped()
    }

    private var scrim: some View {
        // Top + bottom darkening so the wordmark and quote stay legible over any image.
        LinearGradient(
            stops: [
                .init(color: .black.opacity(0.55), location: 0.0),
                .init(color: .black.opacity(0.08), location: 0.30),
                .init(color: .black.opacity(0.30), location: 0.62),
                .init(color: .black.opacity(0.88), location: 1.0),
            ],
            startPoint: .top, endPoint: .bottom
        )
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 0) {
            wordmark
            Spacer()
            quoteBlock
                .id(index)   // re-key so each slide's quote animates in
                .transition(.asymmetric(
                    insertion: .move(edge: .bottom).combined(with: .opacity),
                    removal: .opacity))
                .animation(.easeOut(duration: 0.8), value: index)
            footer
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private var wordmark: some View {
        HStack(spacing: 9) {
            Circle().fill(Palette.cyan)
                .frame(width: 8, height: 8)
                .shadow(color: Palette.cyan.opacity(0.9), radius: 6)
            Text("SKIPPER")
                .font(.system(size: 13, weight: .bold, design: .rounded)).tracking(3)
                .foregroundStyle(.white)
            Text("· AgentOS")
                .font(.system(size: 13, weight: .regular, design: .rounded))
                .foregroundStyle(.white.opacity(0.55))
        }
        .padding(.top, 30).padding(.horizontal, 44)
    }

    private var quoteBlock: some View {
        let q = Quote.all[index % Quote.all.count]
        return VStack(alignment: .leading, spacing: 12) {
            Text(q.line1)
                .font(.system(size: 40, weight: .semibold, design: .rounded))
                .foregroundStyle(.white)
                .fixedSize(horizontal: false, vertical: true)
            Text(q.line2)
                .font(.system(size: 21, weight: .regular, design: .rounded))
                .foregroundStyle(.white.opacity(0.74))
                .fixedSize(horizontal: false, vertical: true)
        }
        .lineSpacing(3)
        .shadow(color: .black.opacity(0.45), radius: 12, y: 4)
        .frame(maxWidth: 780, alignment: .leading)
        .padding(.horizontal, 44)
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 15) {
            ShimmerBar()
            Text(statusText)
                .font(.system(size: 12.5, weight: .regular, design: .rounded))
                .foregroundStyle(.white.opacity(0.62))
            HStack(spacing: 12) {
                if frameCount <= 12 { dots }   // dots are meaningless for large image sets
                Spacer()
                if showContinue {
                    Button(action: onContinue) {
                        Text("Continue without the on-device model")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.white.opacity(0.5))
                            .underline()
                    }
                    .buttonStyle(.plain)
                    .help("Skip the download and use the model declared in the manifest instead.")
                    .transition(.opacity)
                }
            }
        }
        .padding(.horizontal, 44).padding(.top, 24).padding(.bottom, 32)
        .frame(maxWidth: 820, alignment: .leading)
    }

    private var dots: some View {
        HStack(spacing: 6) {
            ForEach(0..<min(frameCount, 12), id: \.self) { i in
                Capsule()
                    .fill(i == index ? Color.white.opacity(0.92) : Color.white.opacity(0.28))
                    .frame(width: i == index ? 20 : 6, height: 6)
            }
        }
        .animation(.easeInOut(duration: 0.4), value: index)
    }

    private var statusText: String {
        switch status {
        case .preparing:
            return "Preparing your on-device model — the first launch downloads it once (about 5 GB), then it's instant, forever."
        case .ready:
            return "Ready — composing your workspace…"
        default:
            return "Setting the stage…"
        }
    }

    // MARK: behavior

    private func advance() {
        guard frameCount > 0 else { return }
        withAnimation { index = (index + 1) % frameCount }
        kickZoom()
    }

    /// Restart the slow Ken Burns zoom for the current slide.
    private func kickZoom() {
        zoomIn = false
        DispatchQueue.main.async {
            withAnimation(.easeOut(duration: interval + 1.2)) { zoomIn = true }
        }
    }
}

// MARK: - One slide's background (image over gradient, or just gradient)

private struct SlideFrame: View {
    let image: NSImage?
    let gradient: LinearGradient

    var body: some View {
        GeometryReader { geo in
            ZStack {
                gradient
                if let image {
                    Image(nsImage: image)
                        .resizable()
                        .scaledToFill()
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
    }
}

// MARK: - Indeterminate "tuning" shimmer (no real % — llama-server doesn't report one)

private struct ShimmerBar: View {
    @State private var animate = false

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            ZStack(alignment: .leading) {
                Capsule().fill(Color.white.opacity(0.10))
                Capsule()
                    .fill(LinearGradient(
                        colors: [.clear, Palette.cyan.opacity(0.95), .clear],
                        startPoint: .leading, endPoint: .trailing))
                    .frame(width: w * 0.38)
                    .offset(x: animate ? w * 0.62 : -w * 0.38)
            }
            .clipShape(Capsule())
            .onAppear {
                withAnimation(.easeInOut(duration: 1.7).repeatForever(autoreverses: false)) {
                    animate = true
                }
            }
        }
        .frame(height: 3)
    }
}

// MARK: - Copy + palette

/// An inspirational two-line slide caption. Orchestral framing ties the wait to
/// the "symphony" idea; the second line keeps reassuring how close the user is.
struct Quote {
    let line1: String
    let line2: String

    static let all: [Quote] = [
        Quote(line1: "The instruments are tuning.",     line2: "Your symphony is moments away."),
        Quote(line1: "Intelligence, composed for one.", line2: "Private, on-device, almost ready."),
        Quote(line1: "No cloud. No eavesdroppers.",     line2: "Just you and a mind of your own."),
        Quote(line1: "One download, then never again.", line2: "Brilliance, cached forever."),
        Quote(line1: "The conductor raises the baton…",  line2: "AgentOS is ready to play."),
    ]
}

private enum Palette {
    static let cyan = Color(red: 0.0, green: 0.83, blue: 1.0)        // #00D4FF

    // 10 distinct on-brand gradients — the fallback backdrop when a slot has no image.
    private static let pairs: [(top: Color, bottom: Color)] = [
        (Color(red: 0.04, green: 0.06, blue: 0.12), Color(red: 0.02, green: 0.20, blue: 0.30)),
        (Color(red: 0.07, green: 0.04, blue: 0.13), Color(red: 0.24, green: 0.10, blue: 0.32)),
        (Color(red: 0.03, green: 0.08, blue: 0.10), Color(red: 0.05, green: 0.26, blue: 0.24)),
        (Color(red: 0.10, green: 0.05, blue: 0.06), Color(red: 0.30, green: 0.12, blue: 0.10)),
        (Color(red: 0.05, green: 0.06, blue: 0.14), Color(red: 0.10, green: 0.16, blue: 0.40)),
        (Color(red: 0.09, green: 0.05, blue: 0.11), Color(red: 0.35, green: 0.16, blue: 0.22)),
        (Color(red: 0.04, green: 0.07, blue: 0.09), Color(red: 0.06, green: 0.22, blue: 0.34)),
        (Color(red: 0.08, green: 0.06, blue: 0.04), Color(red: 0.32, green: 0.22, blue: 0.08)),
        (Color(red: 0.05, green: 0.05, blue: 0.12), Color(red: 0.18, green: 0.10, blue: 0.38)),
        (Color(red: 0.03, green: 0.06, blue: 0.11), Color(red: 0.00, green: 0.28, blue: 0.30)),
    ]

    static func gradient(_ i: Int) -> LinearGradient {
        let p = pairs[i % pairs.count]
        return LinearGradient(colors: [p.top, p.bottom],
                              startPoint: .topLeading, endPoint: .bottomTrailing)
    }
}

// MARK: - Load images from the bundled Slides/ folder

enum SlideLoader {
    static func load() -> [NSImage] {
        guard let dir = Bundle.main.resourceURL?
            .appendingPathComponent("Slides", isDirectory: true) else { return [] }
        let exts: Set<String> = ["jpg", "jpeg", "png", "heic", "heif", "tiff", "tif", "gif", "bmp"]
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: dir, includingPropertiesForKeys: nil)) ?? []
        return urls
            .filter { exts.contains($0.pathExtension.lowercased()) }
            .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
            .compactMap { NSImage(contentsOf: $0) }
    }
}
