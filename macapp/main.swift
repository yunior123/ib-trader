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
// MULTI-VENTANA (Yunior 2026-07-25: "we should be able to have multiple instances of
// the software open in our mac, up to 6 ... equally distributed"):
// hasta 6 cockpits a la vez, repartidos en rejilla sobre la pantalla. Van como VENTANAS
// DE UN SOLO PROCESO, no como 6 procesos: 6 procesos serian 6 WKWebView independientes
// (~84 MB cada uno + su propio WebKit) y en 8 GB eso es swap. En un proceso comparten el
// process pool y el data store de WebKit. `open -n` (instancias de verdad) sigue
// funcionando: cada instancia usa su propio nombre de autoguardado para no pelearse por
// el marco de ventana.
//
// build: zsh macapp/build.sh
//   1 ventana:   open "macapp/ib-trader Cockpit.app"
//   6 repartidas: open -n "…app" --args --windows 6

import Cocoa
import WebKit

let DEFAULT_URL = "http://127.0.0.1:8080/"
let MAX_WINDOWS = 6          // tope pedido por Yunior

/// Una ventana de cockpit = un WKWebView. Todas comparten configuracion (y por tanto
/// el process pool de WebKit), que es lo que hace barato tener seis.
final class CockpitWindow: NSObject, NSWindowDelegate, WKNavigationDelegate {
    let window: NSWindow
    let web: WKWebView
    let idx: Int
    private let url: URL
    weak var owner: AppDelegate?

    init(idx: Int, url: URL, cfg: WKWebViewConfiguration, owner: AppDelegate) {
        self.idx = idx
        self.url = url
        self.owner = owner
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .resizable, .miniaturizable],
                          backing: .buffered, defer: false)
        web = WKWebView(frame: window.contentView!.bounds, configuration: cfg)
        super.init()
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        window.contentView!.addSubview(web)
        window.title = idx == 0 ? "ib-trader cockpit" : "ib-trader cockpit \(idx + 1)"
        // Nombre de autoguardado DISTINTO por ventana: con el mismo nombre las seis se
        // pisaban el marco guardado y arrancaban una encima de otra.
        window.setFrameAutosaveName("cockpit-\(idx)")
        window.delegate = self
        window.makeKeyAndOrderFront(nil)
        load()
    }

    func load() { web.load(URLRequest(url: url)) }

    func windowWillClose(_ n: Notification) { owner?.forget(self) }

    // Si el backend no esta arriba, decirlo CLARO en vez de una pagina en blanco:
    // el fallo silencioso es lo que costo señales dos veces (TCC, 2026-07-24).
    func webView(_ w: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError e: Error) {
        let u = url.absoluteString
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
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var cockpits: [CockpitWindow] = []
    var statusItem: NSStatusItem!
    var settings: SettingsWindow?
    lazy var webCfg: WKWebViewConfiguration = {
        let c = WKWebViewConfiguration(); c.websiteDataStore = .default(); return c
    }()

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

    /// Cuantas ventanas al arrancar: `--windows N` (1..6).
    func startupWindows() -> Int {
        if let i = CommandLine.arguments.firstIndex(of: "--windows"),
           i + 1 < CommandLine.arguments.count,
           let n = Int(CommandLine.arguments[i + 1]) {
            return max(1, min(MAX_WINDOWS, n))
        }
        return 1
    }

    func applicationDidFinishLaunching(_ n: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "📈"
        let m = NSMenu()
        m.addItem(NSMenuItem(title: "Mostrar cockpit", action: #selector(show), keyEquivalent: "1"))
        m.addItem(NSMenuItem(title: "Nueva ventana", action: #selector(newWindow), keyEquivalent: "n"))
        m.addItem(NSMenuItem(title: "Repartir en rejilla", action: #selector(tileWindows), keyEquivalent: "d"))
        m.addItem(NSMenuItem(title: "Recargar", action: #selector(reload), keyEquivalent: "r"))
        m.addItem(NSMenuItem(title: "Configuración…", action: #selector(openSettings), keyEquivalent: ","))
        m.addItem(NSMenuItem.separator())
        m.addItem(NSMenuItem(title: "Salir", action: #selector(quit), keyEquivalent: "q"))
        m.items.forEach { $0.target = self }
        statusItem.menu = m

        let want = startupWindows()
        for _ in 0..<want { _ = openWindow(tile: false) }
        if want > 1 { tile() } else { cockpits.first?.window.center() }

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

    // ------------------------------------------------------------- ventanas
    @discardableResult
    func openWindow(tile doTile: Bool = true) -> CockpitWindow? {
        guard cockpits.count < MAX_WINDOWS else {
            NSSound.beep()
            statusItem.button?.title = "📈\(MAX_WINDOWS)"
            return nil
        }
        // el indice es el primer hueco libre: cerrar la 2 de 3 y abrir otra no duplica marco
        var idx = 0
        let used = Set(cockpits.map { $0.idx })
        while used.contains(idx) { idx += 1 }
        let c = CockpitWindow(idx: idx, url: targetURL(), cfg: webCfg, owner: self)
        cockpits.append(c)
        if doTile && cockpits.count > 1 { tile() }
        return c
    }

    func forget(_ c: CockpitWindow) { cockpits.removeAll { $0 === c } }

    /// Reparte las ventanas abiertas en una rejilla que cubre la pantalla, sin solapes
    /// y con celdas del MISMO tamaño (lo que Yunior llamo "equally distributed").
    ///   1 -> 1x1 · 2 -> 2x1 · 3 -> 3x1 · 4 -> 2x2 · 5,6 -> 3x2
    func tile() {
        let wins = cockpits.sorted { $0.idx < $1.idx }
        let n = wins.count
        guard n > 0, let screen = NSScreen.main else { return }
        let f = screen.visibleFrame          // excluye barra de menu y Dock
        let cols = n <= 3 ? n : (n + 1) / 2
        let rows = n <= 3 ? 1 : 2
        let w = floor(f.width / CGFloat(cols))
        let h = floor(f.height / CGFloat(rows))
        for (i, c) in wins.enumerated() {
            let r = i / cols, col = i % cols
            // origen en coordenadas de Cocoa: y crece hacia ARRIBA -> la fila 0 va arriba
            let x = f.minX + CGFloat(col) * w
            let y = f.minY + f.height - CGFloat(r + 1) * h
            c.window.setFrame(NSRect(x: x, y: y, width: w, height: h), display: true)
        }
    }

    @objc func newWindow()   { openWindow() }
    @objc func tileWindows() { tile() }
    @objc func show() {
        if cockpits.isEmpty { openWindow(tile: false) }
        cockpits.forEach { $0.window.makeKeyAndOrderFront(nil) }
        NSApp.activate(ignoringOtherApps: true)
    }
    @objc func reload() { cockpits.forEach { $0.load() } }
    @objc func quit()   { NSApp.terminate(nil) }
    @objc func openSettings() {
        if settings == nil { settings = SettingsWindow() }
        settings?.showWindow(nil)
        settings?.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ a: NSApplication) -> Bool { false }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
