// Settings.swift — panel de configuración DENTRO de la app.
//
// DONDE SE GUARDA: ~/Library/Application Support/ib-trader/config.json
// NUNCA dentro del .app (se perderia al actualizar) ni en el repo (son secretos).
// El backend lee ese mismo fichero, asi que el .app y la flota comparten config.
//
// PRECARGA (Yunior 2026-07-25: "the credentials files when opening the app should
// already be in place, no need to introduce data manually"): al abrir, los campos
// vienen RELLENOS desde las fuentes que ya existen en el repo, y cada fila DICE de
// donde salio el valor. Yunior no teclea nada.
//
// PRECEDENCIA — es la MISMA que ya implementan el motor y los scripts, a proposito:
// si la UI mostrara otro orden, estaria mintiendo sobre lo que el motor va a usar.
//   order_engine/account_cfg.h:41  expected_account()
//   scripts/ib_mode.py:28          _acct()
// Orden (gana el primero que exista):
//   1. env IBTRADER_ACCOUNT_LIVE / IBTRADER_ACCOUNT_PAPER   (tests y CI)
//   2. ~/Library/Application Support/ib-trader/config.json  (lo guardado aqui)
//   3. ~/Library/Application Support/ib-trader/account.txt  (espejo del panel)
//   4. <repo>/data/account.txt                              (fichero del repo)
//   5. vacio
// La peticion decia "config guardada > fichero del repo > vacio"; se respeta, y se
// añade env por encima porque el motor lo lee primero — omitirlo haria que el panel
// enseñara una cuenta distinta de la que el motor usaria.
//
// SECRETOS — regla dura: las claves de API NO se copian a sitios nuevos. Si una clave
// ya vive en <repo>/feeds.env (gitignored), el campo se deja VACIO y la fila enseña
// "✓ ya configurada — desde feeds.env (••••1234)". Guardar NO la duplica en
// Application Support. Solo se escribe lo que el usuario teclea a mano.
//
// SEGURIDAD — precargar la cuenta LIVE es comodidad de UI, JAMAS consentimiento para
// operar. Este panel no escribe order_engine/ARM_LIVE ni data/ib_mode.txt: la doble
// llave del motor (--arm-live + fichero ARM_LIVE con la fecha de hoy + paper-primero
// + disarm-on-exit) queda intacta. El check de cuenta del motor es una guarda de
// NO-COINCIDENCIA que falla cerrado, no una llave de armado.

import Cocoa

// ---------------------------------------------------------------- fuentes del repo
// Todo lo de aqui es SOLO LECTURA. Nada escribe en el repo.
enum RepoSource {

    /// Raiz del repo, si esta a mano. Devuelve nil si la .app corre suelta (un amigo
    /// que solo tiene el bundle): entonces los campos salen vacios y se teclean.
    static let url: URL? = {
        let fm = FileManager.default
        var cands: [URL] = []
        if let e = ProcessInfo.processInfo.environment["IBTRADER_REPO"], !e.isEmpty {
            cands.append(URL(fileURLWithPath: (e as NSString).expandingTildeInPath))
        }
        // build de desarrollo: <repo>/macapp/ib-trader Cockpit.app/Contents/MacOS/cockpit
        var up = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        for _ in 0..<5 { up = up.deletingLastPathComponent() }
        cands.append(up)
        // ruta canonica (JAMAS ~/Documents: TCC rompe launchd, 2026-07-25)
        cands.append(fm.homeDirectoryForCurrentUser.appendingPathComponent("ib-trader"))
        for c in cands {
            let marker = c.appendingPathComponent("data/fleet.txt")
            if fm.fileExists(atPath: marker.path),
               fm.fileExists(atPath: c.appendingPathComponent("scripts").path) {
                return c.standardizedFileURL
            }
        }
        return nil
    }()

    /// Nombre corto para enseñar en la UI ("~/ib-trader/feeds.env").
    static func pretty(_ u: URL) -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return u.path.hasPrefix(home) ? "~" + u.path.dropFirst(home.count) : u.path
    }

    /// Parser de ficheros CLAVE=VALOR (feeds.env). Ignora comentarios y comillas.
    static func envFile(_ u: URL) -> [String: String] {
        guard let txt = try? String(contentsOf: u, encoding: .utf8) else { return [:] }
        var out: [String: String] = [:]
        for raw in txt.split(separator: "\n", omittingEmptySubsequences: false) {
            let ln = raw.trimmingCharacters(in: .whitespaces)
            if ln.isEmpty || ln.hasPrefix("#") { continue }
            guard let eq = ln.firstIndex(of: "=") else { continue }
            let k = String(ln[ln.startIndex..<eq]).trimmingCharacters(in: .whitespaces)
            var v = String(ln[ln.index(after: eq)...]).trimmingCharacters(in: .whitespaces)
            if v.count >= 2, v.hasPrefix("\""), v.hasSuffix("\"") { v = String(v.dropFirst().dropLast()) }
            if !k.isEmpty { out[k] = v }
        }
        return out
    }

    /// account.txt del repo o del panel: "paper=DU1234567" / "live=U1234567".
    static func accountFile(_ u: URL) -> [String: String] { envFile(u) }

    /// data/ib_mode.txt — "paper" | "live". SOLO se enseña; el panel no lo escribe.
    static var mode: (String, String)? {
        guard let r = url else { return nil }
        let f = r.appendingPathComponent("data/ib_mode.txt")
        guard let t = try? String(contentsOf: f, encoding: .utf8) else { return nil }
        let m = t.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return m.isEmpty ? nil : (m, pretty(f))
    }

    static var feedsURL: URL?   { url.map { $0.appendingPathComponent("config").appendingPathComponent("feeds.env") } }
    static var accountURL: URL? { url.map { $0.appendingPathComponent("data/account.txt") } }
}

/// Un valor resuelto + de donde salio. `masked` != "" significa: el valor YA existe
/// en una fuente externa (feeds.env) y NO se copia al campo — solo se acusa recibo.
struct Resolved {
    var value  = ""       // lo que va en el campo de texto
    var origin = ""       // etiqueta para la UI ("desde feeds.env")
    var masked = ""       // "••••1234" si es un secreto que vive fuera
    var external = false  // true = el valor NO se toca al guardar
}

struct Config: Codable {
    var accountPaper = ""       // DU... — cuenta de PAPEL
    var accountLive  = ""       // U...  — cuenta REAL. El motor ABORTA si no coincide.
    var account      = ""       // legado: se mantiene por compatibilidad con configs viejas
    var paperPort = 4002
    var livePort  = 4001
    var cockpitPort = 8080
    var polygonKey = ""
    var finvizAuth = ""
    var finnhubKey = ""
    var resendKey  = ""
    var resendTo   = ""
    var ntfyTopic  = ""

    static var dir: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("ib-trader", isDirectory: true)
    }
    static var url: URL { dir.appendingPathComponent("config.json") }

    static func load() -> Config {
        guard let d = try? Data(contentsOf: url),
              let c = try? JSONDecoder().decode(Config.self, from: d) else { return Config() }
        return c
    }

    /// ¿Existe ya un config.json guardado? (para etiquetar la procedencia)
    static var saved: Bool { FileManager.default.fileExists(atPath: url.path) }

    func save() throws {
        try FileManager.default.createDirectory(at: Config.dir, withIntermediateDirectories: true)
        let enc = JSONEncoder(); enc.outputFormatting = .prettyPrinted
        try enc.encode(self).write(to: Config.url, options: .atomic)
        // 0600: son claves de pago. Que no las lea otro usuario de la maquina.
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: Config.url.path)
        // Espejo en feeds.env para que los scripts Python existentes lo lean sin cambios.
        // OJO: solo lo que el usuario tecleo. Las claves que viven en <repo>/feeds.env
        // se quedan DONDE ESTAN — no se duplican aqui (regla: cero secretos en sitios nuevos).
        var env = ""
        if !polygonKey.isEmpty { env += "POLYGON_KEY=\(polygonKey)\n" }
        if !finvizAuth.isEmpty { env += "FINVIZ_AUTH=\(finvizAuth)\n" }
        if !finnhubKey.isEmpty { env += "FINNHUB_KEY=\(finnhubKey)\n" }
        if !resendKey.isEmpty  { env += "RESEND_KEY=\(resendKey)\n" }
        if !resendTo.isEmpty   { env += "RESEND_TO=\(resendTo)\n" }
        if !ntfyTopic.isEmpty  { env += "NTFY_TOPIC=\(ntfyTopic)\n" }
        // espejo a account.txt (mismo formato que lee el motor y los scripts)
        var acct = "# generado por el panel de la app — no editar a mano\n"
        if !accountPaper.isEmpty { acct += "paper=\(accountPaper)\n" }
        if !accountLive.isEmpty  { acct += "live=\(accountLive)\n" }
        try? acct.write(to: Config.dir.appendingPathComponent("account.txt"),
                        atomically: true, encoding: .utf8)
        let envURL = Config.dir.appendingPathComponent("config").appendingPathComponent("feeds.env")
        if env.isEmpty {
            // Nada tecleado: no dejar un feeds.env vacio tapando al del repo.
            try? FileManager.default.removeItem(at: envURL)
        } else {
            try? env.write(to: envURL, atomically: true, encoding: .utf8)
            try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: envURL.path)
        }
    }
}

// ------------------------------------------------------------------- resolución
/// Resuelve CADA campo por la cadena de precedencia y anota la procedencia.
struct Prefill {
    let cfg: Config
    let hasSaved: Bool
    let repoEnv: [String: String]
    let repoEnvPath: String
    let repoAcct: [String: String]
    let repoAcctPath: String
    let panelAcct: [String: String]

    init(_ cfg: Config) {
        self.cfg = cfg
        self.hasSaved = Config.saved
        if let f = RepoSource.feedsURL, FileManager.default.fileExists(atPath: f.path) {
            repoEnv = RepoSource.envFile(f); repoEnvPath = RepoSource.pretty(f)
        } else { repoEnv = [:]; repoEnvPath = "" }
        if let a = RepoSource.accountURL, FileManager.default.fileExists(atPath: a.path) {
            repoAcct = RepoSource.accountFile(a); repoAcctPath = RepoSource.pretty(a)
        } else { repoAcct = [:]; repoAcctPath = "" }
        let pa = Config.dir.appendingPathComponent("account.txt")
        panelAcct = FileManager.default.fileExists(atPath: pa.path) ? RepoSource.accountFile(pa) : [:]
    }

    private static func mask(_ s: String) -> String {
        s.count <= 4 ? "••••" : "••••" + String(s.suffix(4))
    }

    /// Cuenta (paper o live). Misma cadena que order_engine/account_cfg.h:41.
    func account(live: Bool) -> Resolved {
        let envKey = live ? "IBTRADER_ACCOUNT_LIVE" : "IBTRADER_ACCOUNT_PAPER"
        if let e = ProcessInfo.processInfo.environment[envKey], !e.trimmingCharacters(in: .whitespaces).isEmpty {
            return Resolved(value: e.trimmingCharacters(in: .whitespaces), origin: "desde env \(envKey)")
        }
        let saved = live ? cfg.accountLive : cfg.accountPaper
        if !saved.isEmpty { return Resolved(value: saved, origin: "config guardada") }
        // config vieja de UNA sola cuenta: el prefijo dice si es live (U...) o paper (DU...)
        if !cfg.account.isEmpty {
            let isPaper = cfg.account.hasPrefix("DU")
            if live != isPaper { return Resolved(value: cfg.account, origin: "config guardada (formato antiguo)") }
        }
        let want = live ? "live" : "paper"
        if let v = panelAcct[want], !v.isEmpty {
            return Resolved(value: v, origin: "desde account.txt del panel")
        }
        if let v = repoAcct[want], !v.isEmpty {
            return Resolved(value: v, origin: "desde \(repoAcctPath)")
        }
        return Resolved(origin: "sin configurar")
    }

    /// Clave de API. Si vive en <repo>/feeds.env NO se copia: se acusa recibo y punto.
    func secret(_ field: String, envKeys: [String]) -> Resolved {
        let saved: String
        switch field {
        case "polygonKey": saved = cfg.polygonKey
        case "finvizAuth": saved = cfg.finvizAuth
        case "finnhubKey": saved = cfg.finnhubKey
        case "resendKey":  saved = cfg.resendKey
        case "ntfyTopic":  saved = cfg.ntfyTopic
        case "resendTo":   saved = cfg.resendTo
        default:           saved = ""
        }
        if !saved.isEmpty { return Resolved(value: saved, origin: "config guardada") }
        for k in envKeys {
            if let v = repoEnv[k], !v.isEmpty {
                // resendTo / ntfyTopic no son secretos: se pueden enseñar enteros.
                let plain = (field == "resendTo" || field == "ntfyTopic")
                if plain { return Resolved(value: v, origin: "desde \(repoEnvPath)") }
                return Resolved(origin: "✓ ya configurada — desde \(repoEnvPath)",
                                masked: Prefill.mask(v), external: true)
            }
        }
        return Resolved(origin: "sin configurar (opcional)")
    }

    func port(_ field: String) -> Resolved {
        switch field {
        case "paperPort":
            return cfg.paperPort != 4002 || hasSaved
                ? Resolved(value: String(cfg.paperPort), origin: "config guardada")
                : Resolved(value: "4002", origin: "por defecto (IB Gateway paper)")
        case "livePort":
            return cfg.livePort != 4001 || hasSaved
                ? Resolved(value: String(cfg.livePort), origin: "config guardada")
                : Resolved(value: "4001", origin: "por defecto (IB Gateway live)")
        default:
            return cfg.cockpitPort != 8080 || hasSaved
                ? Resolved(value: String(cfg.cockpitPort), origin: "config guardada")
                : Resolved(value: "8080", origin: "por defecto")
        }
    }
}

// ----------------------------------------------------------------------- ventana
final class SettingsWindow: NSWindowController, NSWindowDelegate {
    private var fields: [String: NSTextField] = [:]
    private var external: Set<String> = []      // campos cuyo valor vive fuera: no tocar al guardar
    private var cfg = Config.load()
    private let note = NSTextField(labelWithString: "")

    convenience init() {
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 720, height: 610),
                         styleMask: [.titled, .closable], backing: .buffered, defer: false)
        w.title = "Configuración — ib-trader"
        self.init(window: w)
        w.delegate = self
        build()
        w.center()
    }

    private func row(_ y: CGFloat, _ key: String, _ label: String, _ r: Resolved,
                     _ hint: String, secure: Bool) -> [NSView] {
        let l = NSTextField(labelWithString: label)
        l.frame = NSRect(x: 16, y: y, width: 132, height: 20)
        l.alignment = .right
        let f: NSTextField = secure ? NSSecureTextField() : NSTextField()
        f.frame = NSRect(x: 156, y: y - 2, width: 268, height: 24)
        f.stringValue = r.value
        // Secreto que vive en feeds.env: el campo queda vacio y el placeholder acusa
        // recibo con los 4 ultimos caracteres. Teclear algo lo SUSTITUYE.
        f.placeholderString = r.external ? "\(r.masked) — ya configurada, no hace falta tocarla" : hint
        fields[key] = f
        if r.external { external.insert(key) }

        let src = NSTextField(labelWithString: r.origin)
        src.frame = NSRect(x: 432, y: y, width: 272, height: 20)
        src.font = .systemFont(ofSize: 10)
        src.lineBreakMode = .byTruncatingMiddle
        if r.origin.hasPrefix("sin configurar") {
            src.textColor = .tertiaryLabelColor
        } else if r.origin == "config guardada" || r.origin.hasPrefix("config guardada") {
            src.textColor = .secondaryLabelColor
        } else {
            src.textColor = .systemGreen          // precargado de una fuente del repo
        }
        return [l, f, src]
    }

    private func build() {
        guard let cv = window?.contentView else { return }

        let title = NSTextField(labelWithString:
            "Ya está todo puesto. Cada fila dice de dónde salió el valor.")
        title.frame = NSRect(x: 16, y: 570, width: 690, height: 20)
        title.font = .boldSystemFont(ofSize: 13)
        cv.addSubview(title)

        let repoLbl = NSTextField(labelWithString: RepoSource.url.map {
            "Precedencia: config guardada → repo (\(RepoSource.pretty($0))) → vacío"
        } ?? "Repo no encontrado — los campos vacíos hay que teclearlos a mano.")
        repoLbl.frame = NSRect(x: 16, y: 550, width: 690, height: 18)
        repoLbl.font = .systemFont(ofSize: 10)
        repoLbl.textColor = .secondaryLabelColor
        cv.addSubview(repoLbl)

        let pf = Prefill(cfg)
        var y: CGFloat = 508
        let rows: [(String, String, Resolved, String, Bool)] = [
            ("accountPaper", "Cuenta PAPER:", pf.account(live: false), "DU1234567 — empieza SIEMPRE aquí", false),
            ("accountLive",  "Cuenta LIVE:",  pf.account(live: true),  "U1234567 — dinero real", false),
            ("paperPort",    "Puerto paper:", pf.port("paperPort"),    "4002 gateway · 7497 TWS", false),
            ("livePort",     "Puerto live:",  pf.port("livePort"),     "4001 gateway · 7496 TWS", false),
            ("cockpitPort",  "Puerto cockpit:", pf.port("cockpitPort"), "8080", false),
            ("polygonKey",   "Polygon key:",  pf.secret("polygonKey", envKeys: ["POLYGON_KEY", "POLYGON"]),
                                                                       "opcional — backtests históricos", true),
            ("finvizAuth",   "Finviz Elite:", pf.secret("finvizAuth", envKeys: ["FINVIZ_AUTH3", "FINVIZ_AUTH"]),
                                                                       "opcional — screener", true),
            ("finnhubKey",   "Finnhub key:",  pf.secret("finnhubKey", envKeys: ["FINNHUB_KEY"]),
                                                                       "opcional", true),
            ("resendKey",    "Resend key:",   pf.secret("resendKey", envKeys: ["RESEND_KEY"]),
                                                                       "opcional — email de planes", true),
            ("resendTo",     "Email destino:", pf.secret("resendTo", envKeys: ["RESEND_TO"]),
                                                                       "opcional", false),
            ("ntfyTopic",    "ntfy topic:",   pf.secret("ntfyTopic", envKeys: ["NTFY_TOPIC"]),
                                                                       "opcional — push al móvil", false),
        ]
        for (k, l, r, h, sec) in rows {
            row(y, k, l, r, h, secure: sec).forEach { cv.addSubview($0) }
            y -= 34
        }

        // Modo actual — SOLO LECTURA a proposito. Cambiar de paper a live es una
        // decision de trading, no de configuracion: se hace con scripts/ib_mode.sh.
        let modeTxt: String
        if let (m, path) = RepoSource.mode {
            modeTxt = "Modo actual: \(m.uppercased())  (desde \(path) — solo lectura; se cambia con scripts/ib_mode.sh)"
        } else {
            modeTxt = "Modo actual: desconocido (no encuentro data/ib_mode.txt)"
        }
        let mode = NSTextField(labelWithString: modeTxt)
        mode.frame = NSRect(x: 16, y: y - 6, width: 690, height: 18)
        mode.font = .systemFont(ofSize: 11)
        mode.textColor = (RepoSource.mode?.0 == "live") ? .systemRed : .systemBlue
        cv.addSubview(mode)

        note.frame = NSRect(x: 16, y: 56, width: 690, height: 58)
        note.textColor = .secondaryLabelColor
        note.font = .systemFont(ofSize: 11)
        note.maximumNumberOfLines = 4
        note.stringValue = """
        Las claves marcadas «ya configurada» viven en feeds.env y NO se copian aquí al guardar.
        La cuenta SÍ es obligatoria — sin ella el motor NO opera, y aborta si el broker reporta otra.
        Precargar la cuenta LIVE es comodidad de pantalla: NO arma nada. La doble llave del motor sigue intacta.
        """
        cv.addSubview(note)

        let save = NSButton(title: "Guardar", target: self, action: #selector(saveCfg))
        save.frame = NSRect(x: 600, y: 16, width: 100, height: 30)
        save.keyEquivalent = "\r"
        cv.addSubview(save)

        let reveal = NSButton(title: "Ver carpeta", target: self, action: #selector(revealCfg))
        reveal.frame = NSRect(x: 485, y: 16, width: 105, height: 30)
        cv.addSubview(reveal)
    }

    /// Lee un campo; si su valor vive fuera (feeds.env) y el usuario NO tecleó nada,
    /// devuelve "" para que save() lo deje donde está en vez de duplicarlo.
    private func text(_ key: String) -> String {
        let raw = fields[key]?.stringValue ?? ""
        if external.contains(key) && raw.isEmpty { return "" }
        return raw
    }

    @objc private func saveCfg() {
        cfg.accountPaper = text("accountPaper").trimmingCharacters(in: .whitespaces).uppercased()
        cfg.accountLive  = text("accountLive").trimmingCharacters(in: .whitespaces).uppercased()
        cfg.account      = cfg.accountPaper.isEmpty ? cfg.accountLive : cfg.accountPaper
        cfg.paperPort   = Int(text("paperPort"))   ?? 4002
        cfg.livePort    = Int(text("livePort"))    ?? 4001
        cfg.cockpitPort = Int(text("cockpitPort")) ?? 8080
        cfg.polygonKey  = text("polygonKey")
        cfg.finvizAuth  = text("finvizAuth")
        cfg.finnhubKey  = text("finnhubKey")
        cfg.resendKey   = text("resendKey")
        cfg.resendTo    = text("resendTo")
        cfg.ntfyTopic   = text("ntfyTopic")
        do {
            try cfg.save()
            note.stringValue = "✅ Guardado en ~/Library/Application Support/ib-trader/ — las claves de feeds.env siguen donde estaban."
            note.textColor = .systemGreen
        } catch {
            note.stringValue = "🔴 No pude guardar: \(error.localizedDescription)"
            note.textColor = .systemRed
        }
    }
    @objc private func revealCfg() {
        try? FileManager.default.createDirectory(at: Config.dir, withIntermediateDirectories: true)
        NSWorkspace.shared.open(Config.dir)
    }
}
