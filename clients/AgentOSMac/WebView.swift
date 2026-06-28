import SwiftUI
import WebKit
import AppKit

/// Hosts a kernel web page (Overview / Config / DB explorer) inside the app.
/// The kernel serves these as dark-themed HTML on loopback; this just embeds them
/// so the dashboards live in the app instead of a separate browser.
struct WebView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> WKWebView {
        let wv = WKWebView()
        // Match the dashboard background so there's no white flash on load.
        wv.underPageBackgroundColor = NSColor(red: 6/255, green: 6/255, blue: 8/255, alpha: 1)
        wv.load(URLRequest(url: url))
        return wv
    }

    func updateNSView(_ wv: WKWebView, context: Context) {
        if wv.url != url {
            wv.load(URLRequest(url: url))
        }
    }
}
