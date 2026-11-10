import UIKit
import WebKit

/// The whole screen is the game's own pages, served by the Python inside the app.
final class GameViewController: UIViewController, WKNavigationDelegate, WKUIDelegate {
    private var webView: WKWebView!
    private let status = UILabel()
    private let spinner = UIActivityIndicatorView(style: .large)
    private var background: UIBackgroundTaskIdentifier = .invalid
    private var loaded = false
    private let pitch = UIColor(red: 0.07, green: 0.09, blue: 0.11, alpha: 1)

    override var preferredStatusBarStyle: UIStatusBarStyle { .lightContent }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = pitch

        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        // No pinch zoom or long-press callouts: it should feel like an app, not a page.
        let quiet = """
        (function () {
          var m = document.querySelector('meta[name=viewport]');
          if (m && m.content.indexOf('user-scalable') < 0) { m.content += ', maximum-scale=1, user-scalable=no'; }
          var s = document.createElement('style');
          s.textContent = 'body{-webkit-touch-callout:none;}';
          document.head.appendChild(s);
        })();
        """
        config.userContentController.addUserScript(
            WKUserScript(source: quiet, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        webView = WKWebView(frame: view.bounds, configuration: config)
        webView.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.isOpaque = false
        webView.backgroundColor = pitch
        webView.scrollView.backgroundColor = pitch
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.scrollView.bounces = false
        webView.allowsLinkPreview = false
        webView.isHidden = true
        if #available(iOS 16.4, *) { webView.isInspectable = true }
        view.addSubview(webView)

        spinner.color = .white
        spinner.startAnimating()
        status.text = "Starting the game…"
        status.textColor = .white
        status.numberOfLines = 0
        status.textAlignment = .center
        status.font = .preferredFont(forTextStyle: .body)
        let stack = UIStackView(arrangedSubviews: [spinner, status])
        stack.axis = .vertical
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
        ])

        let center = NotificationCenter.default
        center.addObserver(self, selector: #selector(didEnterBackground),
                           name: UIApplication.didEnterBackgroundNotification, object: nil)
        center.addObserver(self, selector: #selector(willEnterForeground),
                           name: UIApplication.willEnterForegroundNotification, object: nil)

        GameServer.shared.start()
        GameServer.shared.whenReady { [weak self] failure in
            if let failure { self?.fail(failure) } else { self?.open() }
        }
    }

    /// Give the web view the launch's key, then load the game.
    private func open() {
        let server = GameServer.shared
        let cookie = HTTPCookie(properties: [
            .domain: "127.0.0.1", .path: "/", .name: GameServer.cookieName, .value: server.secret,
        ])!
        webView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie) { [weak self] in
            guard let self else { return }
            var request = URLRequest(url: server.origin)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            self.webView.load(request)
        }
    }

    private func fail(_ message: String) {
        spinner.stopAnimating()
        status.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        status.textAlignment = .left
        status.text = "The game couldn't start.\n\n" + String(message.suffix(1500))
        webView.isHidden = true
    }

    // MARK: Leaving and returning

    @objc private func didEnterBackground() {
        // Keep serving for the moments iOS allows (a quick look at another app shouldn't cut a
        // match off), then stop listening before the app is suspended.
        background = UIApplication.shared.beginBackgroundTask { [weak self] in
            GameServer.shared.pause()
            self?.endBackground()
        }
    }

    @objc private func willEnterForeground() {
        endBackground()
        let server = GameServer.shared
        if server.resume() {
            server.whenReady(timeout: 15) { [weak self] _ in self?.reload() }
            return
        }
        // The listener was never stopped by us; make sure iOS hasn't taken it meanwhile.
        var request = URLRequest(url: server.origin.appendingPathComponent("api/health"))
        request.timeoutInterval = 1.5
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            if (response as? HTTPURLResponse)?.statusCode == 200 { return }
            server.restart()
            server.whenReady(timeout: 15) { _ in self?.reload() }
        }.resume()
    }

    private func endBackground() {
        if background != .invalid {
            UIApplication.shared.endBackgroundTask(background)
            background = .invalid
        }
    }

    private func reload() {
        guard loaded else { return open() }
        webView.reload()
    }

    // MARK: WKNavigationDelegate

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loaded = true
        spinner.stopAnimating()
        status.isHidden = true
        webView.isHidden = false
        UIApplication.shared.isIdleTimerDisabled = true  // sims and matches run for minutes
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: Error) {
        GameServer.shared.whenReady(timeout: 15) { [weak self] failure in
            if let failure { self?.fail(failure) } else { self?.open() }
        }
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        reload()
    }

    /// The game's own pages stay in the app; anything else opens in Safari.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { return decisionHandler(.cancel) }
        if url.host == "127.0.0.1" || url.scheme == "about" || url.scheme == "blob" {
            decisionHandler(.allow)
        } else {
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
        }
    }

    // MARK: WKUIDelegate (the pages' alert / confirm / prompt)

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
        present(alert, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(false) })
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler(true) })
        present(alert, animated: true)
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                 defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (String?) -> Void) {
        let alert = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
        alert.addTextField { $0.text = defaultText }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(nil) })
        alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in
            completionHandler(alert.textFields?.first?.text)
        })
        present(alert, animated: true)
    }
}
