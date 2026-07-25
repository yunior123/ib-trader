// ib-trader Cockpit — envoltorio nativo del chart en WKWebView.
//
// POR QUE Swift + WKWebView y no Electron: Electron empaqueta su propio Chromium
// (250-400 MB residentes). En un Mac de 8 GB con la flota + TWS Gateway eso empuja
// al swap, y el swap en un sistema de trading es latencia impredecible. WKWebView es
// del sistema: medido 84 MB de proceso + 65 MB de WebKit compartido.
//
// NO afecta al trading: la ruta de señal y ordenes son daemons C++ hablando por socket
// con TWS. Esta ventana solo consume el WebSocket del cockpit. Si se congela, los bots
// siguen operando.
//
// build: zsh macapp/build.sh

import Cocoa
import WebKit

let DEFAULT_URL = "http://127.0.0.1:8080/"

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var statusItem: NSStatusItem!
    var settings: SettingsWindow?

    // El puerto se puede sobreescribir sin recompilar: COCKPIT_URL o --url.
    func targetURL() -> URL {
        if let i = CommandLine.arguments.firstIndex(of: "--url"),
           i + 1 < CommandLine.arguments.count,
           let u = URL(string: CommandLine.arguments[i + 1]) { return u }
        if let s = ProcessInfo.processInfo.environment["COCKPIT_URL"], let u = URL(string: s) { return u }
        // el puerto sale de la config del usuario -> cada amigo el suyo, sin recompilar
        let port = Config.load().cockpitPort
        return URL(string: "http://127.0.0.1:\(port)/")!
    }

    func applicationDidFinishLaunching(_ n: Notification) {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .resizable, .miniaturizable],
                          backing: .buffered, defer: false)
        web = WKWebView(frame: window.contentView!.bounds, configuration: cfg)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        window.contentView!.addSubview(web)
        window.title = "ib-trader cockpit"
        window.setFrameAutosaveName("cockpit")   // recuerda tamaño/posicion
        window.center()
        window.makeKeyAndOrderFront(nil)

        // Icono en la barra de menu: recargar / abrir en navegador / salir.
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "📈"
        let m = NSMenu()
        m.addItem(NSMenuItem(title: "Mostrar cockpit", action: #selector(show), keyEquivalent: "1"))
        m.addItem(NSMenuItem(title: "Recargar", action: #selector(reload), keyEquivalent: "r"))
        m.addItem(NSMenuItem(title: "Configuración…", action: #selector(openSettings), keyEquivalent: ","))
        m.addItem(NSMenuItem.separator())
        m.addItem(NSMenuItem(title: "Salir", action: #selector(quit), keyEquivalent: "q"))
        m.items.forEach { $0.target = self }
        statusItem.menu = m

        load()
        // Primera ejecucion SIN cuenta por ningun lado: abrir Configuracion en vez de
        // dejar al usuario adivinando por que no funciona. Ojo: se pregunta por la cadena
        // COMPLETA (env -> config.json -> account.txt del panel -> data/account.txt del
        // repo), no solo por config.json. Si el repo ya tiene la cuenta, el panel NO
        // salta: Yunior no tiene nada que teclear (orden 2026-07-25).
        let pf0 = Prefill(Config.load())
        if CommandLine.arguments.contains("--settings")     // para verificar la precarga
            || (pf0.account(live: false).value.isEmpty && pf0.account(live: true).value.isEmpty) {
            openSettings()
        }
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func load() { web.load(URLRequest(url: targetURL())) }
    @objc func show()   { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func reload() { load() }
    @objc func quit()   { NSApp.terminate(nil) }
    @objc func openSettings() {
        if settings == nil { settings = SettingsWindow() }
        settings?.showWindow(nil)
        settings?.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    // Si el backend no esta arriba, decirlo CLARO en vez de una pagina en blanco:
    // el fallo silencioso es lo que costo señales dos veces (TCC, 2026-07-24).
    func webView(_ w: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError e: Error) {
        let u = targetURL().absoluteString
        let html = """
        <html><body style="background:#131722;color:#d1d4dc;font:14px -apple-system;
        display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
        <div style="text-align:center;max-width:520px">
        <div style="font-size:42px">🔌</div>
        <h2>El backend del cockpit no responde</h2>
        <p style="color:#787b86">No hay nadie escuchando en <code>\(u)</code>.</p>
        <p style="text-align:left;background:#1e222d;padding:14px;border-radius:8px">
        Arráncalo con:<br><code>cd ~/ib-trader &amp;&amp; zsh scripts/fleet_up.sh --chart</code></p>
        <p style="color:#787b86;font-size:12px">Menú 📈 → Recargar cuando esté arriba.</p>
        </div></body></html>
        """
        w.loadHTMLString(html, baseURL: nil)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ a: NSApplication) -> Bool { false }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
