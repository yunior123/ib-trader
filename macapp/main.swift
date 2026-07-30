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
// MULTI-VENTANA: N ventanas en UN proceso, cada una en SU puerto -> SU simbolo.
// chart_bridge.py tiene un solo `state.sym` por proceso (scripts/chart_bridge.py:1735):
// dos ventanas en el mismo puerto se pisan el simbolo. Por eso una ventana = un puerto.
//
// build: zsh macapp/build.sh
//   1 ventana:    open "macapp/ib-trader Cockpit.app"
//   6 simbolos:   open "…app" --args --windows 6          (puertos 8080..8085)
//   a la carta:   open "…app" --args --ports 8080,8083,8085

import Cocoa
import WebKit

let DEFAULT_URL = "http://127.0.0.1:8080/"
let MAX_WINDOWS = 12
let DEFAULT_WINDOW_COUNT = 6

/// Sello del build LEIDO DEL BUNDLE (build.sh lo escribe en Info.plist). Nunca `git` en
/// runtime: la .app tiene que arrancar en un Mac sin el repo.
let BUILD_VERSION: String = {
    let i = Bundle.main.infoDictionary ?? [:]
    let raw = (i["IBTVersion"] as? String)
        ?? (i["CFBundleShortVersionString"] as? String)
        ?? "?"
    return raw.hasPrefix("v") ? raw : "v\(raw)"
}()

/// Una ventana de cockpit = un WKWebView. Todas comparten configuracion (y por tanto
/// el process pool de WebKit), que es lo que hace barato tener seis.
final class CockpitWindow: NSObject, NSWindowDelegate, WKNavigationDelegate {
    let window: NSWindow
    let web: WKWebView
    let zoomLabel = NSTextField()
    let idx: Int
    let url: URL
    weak var owner: AppDelegate?
    private var backendRetry: Timer?
    private var pageTitleObservation: NSKeyValueObservation?

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
        web.pageZoom = AppDelegate.savedZoom()
        web.navigationDelegate = self
        pageTitleObservation = web.observe(\.title, options: [.new]) {
            [weak self] _, change in
            guard let self, let pageTitle = change.newValue ?? nil,
                  pageTitle.hasPrefix("IBT:") else { return }
            let sym = String(pageTitle.dropFirst(4))
            guard !sym.isEmpty else { return }
            self.window.title = self.title(sym: sym)
        }
        window.contentView!.addSubview(web)
        window.title = title(sym: nil)
        installRefreshButton()
        // Autoguardado por PUERTO, no por indice: con "cockpit-<idx>" seis procesos
        // distintos usaban todos "cockpit-0" y restauraban el MISMO marco -> apiladas.
        window.setFrameAutosaveName("cockpit-p\(url.port ?? 80)")
        window.delegate = self
        window.makeKeyAndOrderFront(nil)
        load()
        refreshTitle()
    }

    func load() { web.load(URLRequest(url: url)) }

    /// La app y los seis bridges arrancan en procesos distintos. En un relanzamiento limpio,
    /// WebKit puede intentar cargar 8080..8085 unos segundos antes de que fleet_keepalive los
    /// ponga a escuchar. Antes mostraba el error para siempre aunque el backend ya estuviera
    /// sano. Se sondea /health y se recarga SOLA cuando aparece; una sola tarea por ventana.
    func retryWhenBackendAppears() {
        guard backendRetry == nil else { return }
        backendRetry = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) {
            [weak self] _ in self?.probeBackend()
        }
        probeBackend()
    }

    func probeBackend() {
        guard let h = URL(string: "health", relativeTo: url) else { return }
        URLSession.shared.dataTask(with: URLRequest(url: h, timeoutInterval: 0.8)) {
            [weak self] data, response, _ in
            guard let self,
                  let http = response as? HTTPURLResponse,
                  (200..<300).contains(http.statusCode) else { return }
            let sym = data.flatMap {
                (try? JSONSerialization.jsonObject(with: $0) as? [String: Any])?["sym"] as? String
            }
            DispatchQueue.main.async {
                self.backendRetry?.invalidate()
                self.backendRetry = nil
                if let sym, !sym.isEmpty { self.window.title = self.title(sym: sym) }
                self.load()
            }
        }.resume()
    }

    /// SIMBOLO · puerto · version publica, en ese orden.
    func title(sym: String?) -> String {
        let p = url.port ?? 80
        let head = (sym?.isEmpty == false) ? "\(sym!.uppercased()) · :\(p)" : "cockpit :\(p)"
        return "\(head) · \(BUILD_VERSION)"
    }

    /// Boton de recarga en la barra de titulo: ⌘R no se descubre mirando.
    func installRefreshButton() {
        let b = NSButton(frame: NSRect(x: 2, y: 2, width: 30, height: 22))
        b.bezelStyle = .texturedRounded
        b.image = NSImage(systemSymbolName: "arrow.clockwise", accessibilityDescription: "Recargar")
        b.imagePosition = .imageOnly
        b.toolTip = "Recargar esta ventana (⌘R)"
        b.target = self
        b.action = #selector(reloadThisWindow)
        // Ajustador de zoom VISIBLE (Yunior 2026-07-27 "put zoom adjuster too"): los atajos
        // ⌘+/⌘−/⌘0 tampoco se descubren mirando. Aplica a las 6 ventanas, como el menu.
        let zOut = NSButton(frame: NSRect(x: 34, y: 2, width: 26, height: 22))
        let zIn  = NSButton(frame: NSRect(x: 60, y: 2, width: 26, height: 22))
        for (btn, sym, tip, sel) in [
            (zOut, "minus.magnifyingglass", "Reducir zoom (⌘−)", #selector(zoomOutHere)),
            (zIn,  "plus.magnifyingglass",  "Ampliar zoom (⌘+)", #selector(zoomInHere)),
        ] {
            btn.bezelStyle = .texturedRounded
            btn.image = NSImage(systemSymbolName: sym, accessibilityDescription: tip)
            btn.imagePosition = .imageOnly
            btn.toolTip = tip
            btn.target = self
            btn.action = sel
        }
        zoomLabel.frame = NSRect(x: 88, y: 3, width: 40, height: 20)
        zoomLabel.isBezeled = false; zoomLabel.drawsBackground = false
        zoomLabel.isEditable = false; zoomLabel.isSelectable = false
        zoomLabel.alignment = .center
        zoomLabel.font = .monospacedDigitSystemFont(ofSize: 11, weight: .semibold)
        zoomLabel.textColor = .secondaryLabelColor
        zoomLabel.toolTip = "Zoom actual. ⌘0 lo vuelve a 100%."
        syncZoomLabel()
        let host = NSView(frame: NSRect(x: 0, y: 0, width: 132, height: 26))
        host.addSubview(b); host.addSubview(zOut); host.addSubview(zIn); host.addSubview(zoomLabel)
        let acc = NSTitlebarAccessoryViewController()
        acc.view = host
        acc.layoutAttribute = .right
        window.addTitlebarAccessoryViewController(acc)
    }

    /// Recarga SOLO esta ventana: con 6 abiertas, recargar las seis tira 6 WebSockets.
    @objc func reloadThisWindow() { load() }

    @objc func zoomInHere()  { owner?.zoomIn() }
    @objc func zoomOutHere() { owner?.zoomOut() }
    func syncZoomLabel() {
        zoomLabel.stringValue = "\(Int((AppDelegate.savedZoom() * 100).rounded()))%"
    }

    /// El titulo dice QUE SIMBOLO hay en esa ventana: /health del bridge devuelve `sym`.
    func refreshTitle() {
        guard let h = URL(string: "health", relativeTo: url) else { return }
        URLSession.shared.dataTask(with: URLRequest(url: h, timeoutInterval: 3)) { d, _, _ in
            guard let d, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
                  let s = j["sym"] as? String, !s.isEmpty else { return }
            DispatchQueue.main.async { self.window.title = self.title(sym: s) }
        }.resume()
    }

    func webView(_ w: WKWebView, didFinish nav: WKNavigation!) {
        // `loadHTMLString` del error tiene URL about:blank; sólo una navegación HTTP real
        // demuestra que el backend respondió y permite cancelar el retry.
        if w.url?.host == url.host && w.url?.port == url.port {
            backendRetry?.invalidate()
            backendRetry = nil
        }
        refreshTitle()
    }

    func windowWillClose(_ n: Notification) {
        backendRetry?.invalidate()
        backendRetry = nil
        pageTitleObservation?.invalidate()
        pageTitleObservation = nil
        owner?.forget(self)
    }

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
        <p style="color:#787b86;font-size:12px">Reconectando automáticamente… También puedes pulsar ↻ o ⌘R.</p>
        </div></body></html>
        """
        w.loadHTMLString(html, baseURL: nil)
        retryWhenBackendAppears()
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

    func arg(_ name: String) -> String? {
        guard let i = CommandLine.arguments.firstIndex(of: name),
              i + 1 < CommandLine.arguments.count else { return nil }
        return CommandLine.arguments[i + 1]
    }

    /// URL de un puerto, conservando el host de la URL base.
    func url(port: Int) -> URL {
        var c = URLComponents(url: targetURL(), resolvingAgainstBaseURL: false)!
        c.port = port
        return c.url!
    }

    /// Que ventanas al arrancar. Una ventana = un puerto = un simbolo.
    ///   --ports 8080,8083   -> esos puertos
    ///   --windows N         -> N puertos CONSECUTIVOS desde el base (8080..8080+N-1)
    ///   --windows N --same-url -> N ventanas del mismo puerto (comportamiento viejo)
    func startupURLs() -> [URL] {
        if let s = arg("--ports") {
            let ps = s.split(separator: ",").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
            if !ps.isEmpty { return ps.prefix(MAX_WINDOWS).map { url(port: $0) } }
        }
        let base = targetURL()
        let n = arg("--windows").flatMap(Int.init) ?? DEFAULT_WINDOW_COUNT
        let want = max(1, min(MAX_WINDOWS, n))
        if CommandLine.arguments.contains("--same-url") { return Array(repeating: base, count: want) }
        let p0 = base.port ?? 8080
        return (0..<want).map { url(port: p0 + $0) }
    }

    /// Siguiente puerto libre a partir del base: lo que usa ⌘N.
    func nextFreeURL() -> URL {
        let used = Set(cockpits.compactMap { $0.url.port })
        var p = targetURL().port ?? 8080
        while used.contains(p) { p += 1 }
        return url(port: p)
    }

    func applicationDidFinishLaunching(_ n: Notification) {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "📈"
        let m = NSMenu()
        m.addItem(NSMenuItem(title: "Mostrar cockpit", action: #selector(show), keyEquivalent: "1"))
        m.addItem(NSMenuItem(title: "Nueva ventana (siguiente puerto)", action: #selector(newWindow), keyEquivalent: "n"))
        m.addItem(NSMenuItem(title: "Nueva ventana en puerto…", action: #selector(newWindowAsk), keyEquivalent: "N"))
        m.addItem(NSMenuItem(title: "Repartir en rejilla", action: #selector(tileWindows), keyEquivalent: "d"))
        m.addItem(NSMenuItem(title: "Recargar (ventana activa)", action: #selector(reloadKey), keyEquivalent: "r"))
        m.addItem(NSMenuItem(title: "Recargar TODAS", action: #selector(reload), keyEquivalent: "R"))
        m.addItem(NSMenuItem(title: "Zoom +", action: #selector(zoomIn), keyEquivalent: "+"))
        m.addItem(NSMenuItem(title: "Zoom −", action: #selector(zoomOut), keyEquivalent: "-"))
        m.addItem(NSMenuItem(title: "Zoom 100%", action: #selector(zoomReset), keyEquivalent: "0"))
        m.addItem(NSMenuItem(title: "Configuración…", action: #selector(openSettings), keyEquivalent: ","))
        m.addItem(NSMenuItem.separator())
        m.addItem(NSMenuItem(title: "Salir", action: #selector(quit), keyEquivalent: "q"))
        m.items.forEach { $0.target = self }
        // Version publica secuencial; el commit queda interno en Info.plist para diagnostico.
        let info = Bundle.main.infoDictionary ?? [:]
        let rawVersion = info["IBTVersion"] as? String ?? "?"
        let version = rawVersion.hasPrefix("v") ? rawVersion : "v\(rawVersion)"
        let built = info["IBTBuildDate"] as? String ?? "?"
        m.addItem(NSMenuItem.separator())
        let stamp = NSMenuItem(title: "\(version) · \(built)", action: nil, keyEquivalent: "")
        stamp.isEnabled = false
        m.addItem(stamp)
        statusItem.menu = m
        installMainMenu()   // sin barra de menus reales, ⌘N/⌘W no llegaban con la app al frente

        let urls = startupURLs()
        for u in urls { _ = openWindow(url: u, tile: false) }
        if urls.count > 1 { tile() } else { cockpits.first?.window.center() }
        // En rejilla de >=4 cada ventana es una fraccion de pantalla: se sube el zoom la
        // PRIMERA vez (si el usuario ya lo ajusto, manda el suyo).
        if urls.count >= 4 && UserDefaults.standard.double(forKey: AppDelegate.ZOOM_KEY) == 0 {
            setZoom(AppDelegate.ZOOM_TILED)
        }

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
    func installMainMenu() {
        let bar = NSMenu()
        let appItem = NSMenuItem(); bar.addItem(appItem)
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Configuración…", action: #selector(openSettings), keyEquivalent: ",")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Salir", action: #selector(quit), keyEquivalent: "q")
        appMenu.items.forEach { $0.target = self }
        appItem.submenu = appMenu

        let winItem = NSMenuItem(title: "Ventana", action: nil, keyEquivalent: ""); bar.addItem(winItem)
        let winMenu = NSMenu(title: "Ventana")
        winMenu.addItem(withTitle: "Nueva ventana", action: #selector(newWindow), keyEquivalent: "n")
        winMenu.addItem(withTitle: "Nueva ventana en puerto…", action: #selector(newWindowAsk), keyEquivalent: "N")
        winMenu.addItem(withTitle: "Repartir en rejilla", action: #selector(tileWindows), keyEquivalent: "d")
        winMenu.addItem(withTitle: "Recargar", action: #selector(reloadKey), keyEquivalent: "r")
        winMenu.addItem(withTitle: "Recargar TODAS", action: #selector(reload), keyEquivalent: "R")
        winMenu.items.forEach { $0.target = self }
        winMenu.addItem(NSMenuItem.separator())
        winMenu.addItem(withTitle: "Cerrar ventana", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winMenu.addItem(withTitle: "Minimizar", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        winItem.submenu = winMenu
        NSApp.mainMenu = bar
        NSApp.windowsMenu = winMenu
    }

    @discardableResult
    func openWindow(url u: URL? = nil, tile doTile: Bool = true) -> CockpitWindow? {
        guard cockpits.count < MAX_WINDOWS else {
            NSSound.beep()
            statusItem.button?.title = "📈\(MAX_WINDOWS)"
            return nil
        }
        // el indice es el primer hueco libre: cerrar la 2 de 3 y abrir otra no duplica marco
        var idx = 0
        let used = Set(cockpits.map { $0.idx })
        while used.contains(idx) { idx += 1 }
        let c = CockpitWindow(idx: idx, url: u ?? nextFreeURL(), cfg: webCfg, owner: self)
        cockpits.append(c)
        if doTile && cockpits.count > 1 { tile() }
        return c
    }

    func forget(_ c: CockpitWindow) { cockpits.removeAll { $0 === c } }

    // ZOOM (Yunior 2026-07-27: "increase zoom for tiny 6 windows"). En rejilla de 6 cada
    // ventana es 1/6 de pantalla y el texto se lee pequeno. Se persiste para que sobreviva al
    // rebuild, y es ajustable en vivo: la temporalidad correcta depende de la pantalla.
    static let ZOOM_KEY = "cockpitPageZoom"
    static let ZOOM_TILED = 1.25          // default cuando se abren >=4 ventanas a la vez
    static func savedZoom() -> CGFloat {
        let v = UserDefaults.standard.double(forKey: ZOOM_KEY)
        return v > 0 ? CGFloat(v) : 1.0
    }
    func setZoom(_ z: CGFloat) {
        let c = min(max(z, 0.6), 2.5)      // topado: por debajo no se lee, por encima no cabe nada
        UserDefaults.standard.set(Double(c), forKey: AppDelegate.ZOOM_KEY)
        cockpits.forEach { $0.web.pageZoom = c; $0.syncZoomLabel() }
    }
    @objc func zoomIn()    { setZoom(AppDelegate.savedZoom() + 0.1) }
    @objc func zoomOut()   { setZoom(AppDelegate.savedZoom() - 0.1) }
    @objc func zoomReset() { setZoom(1.0) }

    /// Reparte las ventanas abiertas en una rejilla que cubre la pantalla, sin solapes
    /// y con celdas del MISMO tamaño (lo que Yunior llamo "equally distributed").
    ///   1 -> 1x1 · 2 -> 2x1 · 3 -> 3x1 · 4 -> 2x2 · 5,6 -> 3x2 · >6 -> rejilla cuadrada
    func tile() {
        let wins = cockpits.sorted { $0.idx < $1.idx }
        let n = wins.count
        guard n > 0, let screen = NSScreen.main else { return }
        let f = screen.visibleFrame          // excluye barra de menu y Dock
        let cols = n <= 3 ? n : (n <= 6 ? (n + 1) / 2 : Int(ceil(Double(n).squareRoot())))
        let rows = n <= 3 ? 1 : Int(ceil(Double(n) / Double(cols)))
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

    /// ⇧⌘N: ventana en el puerto que se teclee -> el simbolo de ESE bridge.
    @objc func newWindowAsk() {
        let a = NSAlert()
        a.messageText = "Nueva ventana del cockpit"
        a.informativeText = "Puerto del bridge (un puerto = un símbolo).\nArráncalo antes con:  scripts/chart_bridge.py --sym nvda --http-port 8082"
        let tf = NSTextField(frame: NSRect(x: 0, y: 0, width: 220, height: 24))
        tf.stringValue = String(nextFreeURL().port ?? 8080)
        a.accessoryView = tf
        a.addButton(withTitle: "Abrir"); a.addButton(withTitle: "Cancelar")
        NSApp.activate(ignoringOtherApps: true)
        guard a.runModal() == .alertFirstButtonReturn, let p = Int(tf.stringValue.trimmingCharacters(in: .whitespaces)),
              p > 0, p < 65536 else { return }
        openWindow(url: url(port: p))
    }

    @objc func show() {
        if cockpits.isEmpty { openWindow(tile: false) }
        cockpits.forEach { $0.window.makeKeyAndOrderFront(nil) }
        NSApp.activate(ignoringOtherApps: true)
    }
    @objc func reload() { cockpits.forEach { $0.load() } }
    /// ⌘R = la ventana que se esta mirando; ⇧⌘R = las seis.
    @objc func reloadKey() {
        if let w = NSApp.keyWindow, let c = cockpits.first(where: { $0.window === w }) { c.load() }
        else { reload() }
    }
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
