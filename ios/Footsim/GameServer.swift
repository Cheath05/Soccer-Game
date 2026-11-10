import Foundation

/// The game's server inside the app: the embedded Python serving footsim on 127.0.0.1.
/// Sets the FOOTSIM_* environment, starts Python, and pauses and resumes its listener as the
/// app leaves and returns (iOS can take a suspended app's listening socket without telling it).
final class GameServer {
    static let shared = GameServer()
    static let cookieName = "footsim_key"
    private static let firstPort: UInt16 = 47631  // fixed, so the pages' localStorage survives

    let port: UInt16
    let secret: String
    private(set) var failure: String?
    private var paused = false

    var origin: URL { URL(string: "http://127.0.0.1:\(port)")! }

    private init() {
        port = GameServer.freePort(from: GameServer.firstPort)
        secret = (0..<4).map { _ in String(UInt64.random(in: 0...UInt64.max), radix: 36) }.joined()
    }

    func start() {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let saves = support.appendingPathComponent("saves", isDirectory: true)
        try? FileManager.default.createDirectory(at: saves, withIntermediateDirectories: true)
        setenv("FOOTSIM_SAVES_DIR", saves.path, 1)
        setenv("FOOTSIM_PHONE_PORT", String(port), 1)
        setenv("FOOTSIM_PHONE_SECRET", secret, 1)
        setenv("TMPDIR", NSTemporaryDirectory(), 1)
        PythonHost.start { [weak self] message in
            self?.failure = message
        }
    }

    /// Calls back on the main queue once the server answers, or with what went wrong.
    func whenReady(timeout: TimeInterval = 60, _ done: @escaping (String?) -> Void) {
        let deadline = Date().addingTimeInterval(timeout)
        let health = origin.appendingPathComponent("api/health")
        func attempt() {
            if let failure = self.failure {
                return DispatchQueue.main.async { done(failure) }
            }
            var request = URLRequest(url: health)
            request.timeoutInterval = 2
            request.cachePolicy = .reloadIgnoringLocalCacheData
            URLSession.shared.dataTask(with: request) { _, response, _ in
                if (response as? HTTPURLResponse)?.statusCode == 200 {
                    DispatchQueue.main.async { done(nil) }
                } else if Date() > deadline {
                    DispatchQueue.main.async { done(self.failure ?? "The game didn't start in time.") }
                } else {
                    DispatchQueue.global().asyncAfter(deadline: .now() + 0.15) { attempt() }
                }
            }.resume()
        }
        attempt()
    }

    /// Stop listening (the app is about to be suspended). Careers stay in memory.
    func pause() {
        guard !paused else { return }
        paused = true
        DispatchQueue.global(qos: .userInitiated).async {
            PythonHost.run("import footsim.phone.main as _m; _m.pause()")
        }
    }

    /// Listen again. Returns whether the listener had been stopped (the pages need a reload).
    @discardableResult
    func resume() -> Bool {
        guard paused else { return false }
        paused = false
        DispatchQueue.global(qos: .userInitiated).async {
            PythonHost.run("import footsim.phone.main as _m; _m.resume()")
        }
        return true
    }

    /// Stop and start the listener: for a socket iOS took while the app was suspended.
    func restart() {
        DispatchQueue.global(qos: .userInitiated).async {
            PythonHost.run("import footsim.phone.main as _m, time; _m.pause(); time.sleep(0.5); _m.resume()")
        }
    }

    private static func freePort(from first: UInt16) -> UInt16 {
        for candidate in first..<(first + 50) where canBind(candidate) {
            return candidate
        }
        return first
    }

    private static func canBind(_ port: UInt16) -> Bool {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var yes: Int32 = 1
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
        var address = sockaddr_in()
        address.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        address.sin_family = sa_family_t(AF_INET)
        address.sin_port = port.bigEndian
        address.sin_addr.s_addr = inet_addr("127.0.0.1")
        return withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) == 0
            }
        }
    }
}
