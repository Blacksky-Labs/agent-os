import Foundation
import Darwin

enum Net {
    /// Ask the OS for an open loopback TCP port (falls back to `fallback`).
    /// Used so the kernel and the llama.cpp server never collide on fixed ports.
    static func freePort(fallback: Int = 1776) -> Int {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return fallback }
        defer { close(fd) }
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_addr.s_addr = inet_addr("127.0.0.1")
        addr.sin_port = 0                       // 0 → OS assigns a free ephemeral port
        let bound = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bound == 0 else { return fallback }
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        let named = withUnsafeMutablePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(fd, $0, &len)
            }
        }
        guard named == 0 else { return fallback }
        return Int(UInt16(bigEndian: addr.sin_port))
    }
}
