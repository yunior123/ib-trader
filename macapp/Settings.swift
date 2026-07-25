// Settings.swift — panel de configuración DENTRO de la app, para que cualquiera
// (no solo Yunior) meta su cuenta IBKR y sus claves de API sin tocar ficheros.
//
// DONDE SE GUARDA: ~/Library/Application Support/ib-trader/config.json
// NUNCA dentro del .app (se perderia al actualizar) ni en el repo (son secretos).
// El backend lee ese mismo fichero, asi que el .app y la flota comparten config.

import Cocoa

struct Config: Codable {
    var account   = ""          // U... (live) o DU... (paper) — el motor ABORTA si no coincide
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
    func save() throws {
        try FileManager.default.createDirectory(at: Config.dir, withIntermediateDirectories: true)
        let enc = JSONEncoder(); enc.outputFormatting = .prettyPrinted
        try enc.encode(self).write(to: Config.url, options: .atomic)
        // 0600: son claves de pago. Que no las lea otro usuario de la maquina.
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: Config.url.path)
        // Espejo en feeds.env para que los scripts Python existentes lo lean sin cambios.
        var env = ""
        if !polygonKey.isEmpty { env += "POLYGON_KEY=\(polygonKey)\n" }
        if !finvizAuth.isEmpty { env += "FINVIZ_AUTH=\(finvizAuth)\n" }
        if !finnhubKey.isEmpty { env += "FINNHUB_KEY=\(finnhubKey)\n" }
        if !resendKey.isEmpty  { env += "RESEND_KEY=\(resendKey)\n" }
        if !resendTo.isEmpty   { env += "RESEND_TO=\(resendTo)\n" }
        if !ntfyTopic.isEmpty  { env += "NTFY_TOPIC=\(ntfyTopic)\n" }
        let envURL = Config.dir.appendingPathComponent("feeds.env")
        try? env.write(to: envURL, atomically: true, encoding: .utf8)
        try? FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: envURL.path)
    }
}

final class SettingsWindow: NSWindowController, NSWindowDelegate {
    private var fields: [String: NSTextField] = [:]
    private var cfg = Config.load()
    private let note = NSTextField(labelWithString: "")

    convenience init() {
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 520, height: 560),
                         styleMask: [.titled, .closable], backing: .buffered, defer: false)
        w.title = "Configuración — ib-trader"
        self.init(window: w)
        w.delegate = self
        build()
        w.center()
    }

    private func row(_ y: CGFloat, _ key: String, _ label: String, _ value: String,
                     _ hint: String, secure: Bool = false) -> [NSView] {
        let l = NSTextField(labelWithString: label)
        l.frame = NSRect(x: 20, y: y, width: 150, height: 20)
        l.alignment = .right
        let f: NSTextField = secure ? NSSecureTextField() : NSTextField()
        f.frame = NSRect(x: 180, y: y - 2, width: 315, height: 24)
        f.stringValue = value
        f.placeholderString = hint
        fields[key] = f
        return [l, f]
    }

    private func build() {
        guard let cv = window?.contentView else { return }
        let title = NSTextField(labelWithString: "Tus datos. Se guardan solo en este Mac.")
        title.frame = NSRect(x: 20, y: 515, width: 480, height: 20)
        title.textColor = .secondaryLabelColor
        cv.addSubview(title)

        var y: CGFloat = 470
        let rows: [(String, String, String, String, Bool)] = [
            ("account",     "Cuenta IBKR:",   cfg.account,               "U1234567 (live) o DU1234567 (paper)", false),
            ("paperPort",   "Puerto paper:",  String(cfg.paperPort),     "4002 gateway · 7497 TWS", false),
            ("livePort",    "Puerto live:",   String(cfg.livePort),      "4001 gateway · 7496 TWS", false),
            ("cockpitPort", "Puerto cockpit:", String(cfg.cockpitPort),  "8080", false),
            ("polygonKey",  "Polygon key:",   cfg.polygonKey,            "opcional — backtests históricos", true),
            ("finvizAuth",  "Finviz Elite:",  cfg.finvizAuth,            "opcional — screener", true),
            ("finnhubKey",  "Finnhub key:",   cfg.finnhubKey,            "opcional", true),
            ("resendKey",   "Resend key:",    cfg.resendKey,             "opcional — email de planes", true),
            ("resendTo",    "Email destino:", cfg.resendTo,              "opcional", false),
            ("ntfyTopic",   "ntfy topic:",    cfg.ntfyTopic,             "opcional — push al móvil", false),
        ]
        for (k, l, v, h, sec) in rows {
            row(y, k, l, v, h, secure: sec).forEach { cv.addSubview($0) }
            y -= 34
        }

        note.frame = NSRect(x: 20, y: 60, width: 480, height: 40)
        note.textColor = .secondaryLabelColor
        note.maximumNumberOfLines = 2
        note.stringValue = "Las claves son opcionales: sin ellas el sistema funciona con IBKR solo.\nLa cuenta SÍ es obligatoria — el motor aborta si no coincide con la del broker."
        cv.addSubview(note)

        let save = NSButton(title: "Guardar", target: self, action: #selector(saveCfg))
        save.frame = NSRect(x: 400, y: 18, width: 95, height: 30)
        save.keyEquivalent = "\r"
        cv.addSubview(save)

        let reveal = NSButton(title: "Ver carpeta", target: self, action: #selector(revealCfg))
        reveal.frame = NSRect(x: 285, y: 18, width: 105, height: 30)
        cv.addSubview(reveal)
    }

    @objc private func saveCfg() {
        cfg.account     = fields["account"]!.stringValue.trimmingCharacters(in: .whitespaces).uppercased()
        cfg.paperPort   = Int(fields["paperPort"]!.stringValue)   ?? 4002
        cfg.livePort    = Int(fields["livePort"]!.stringValue)    ?? 4001
        cfg.cockpitPort = Int(fields["cockpitPort"]!.stringValue) ?? 8080
        cfg.polygonKey  = fields["polygonKey"]!.stringValue
        cfg.finvizAuth  = fields["finvizAuth"]!.stringValue
        cfg.finnhubKey  = fields["finnhubKey"]!.stringValue
        cfg.resendKey   = fields["resendKey"]!.stringValue
        cfg.resendTo    = fields["resendTo"]!.stringValue
        cfg.ntfyTopic   = fields["ntfyTopic"]!.stringValue
        do {
            try cfg.save()
            note.stringValue = "✅ Guardado en ~/Library/Application Support/ib-trader/"
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
