// order_engine.cpp — motor de EJECUCIÓN de opciones "under-the-ground" (C++23).
// El gráfico es el mando: Yunior pinta zonas (precio+call/put+expiry+stop) en
// data/exec_zones_<sym>.json; el motor las vigila LOCAL contra el NBBO del
// subyacente (archivos de la flota, NUNCA por la conexión de órdenes: pacing),
// y al PRINT del nivel (2 lecturas) coloca la orden de la opción en TWS.
//
// SEGURIDAD (no negociable):
//  - DRY por defecto. LIVE exige DOBLE LLAVE: --arm-live Y order_engine/ARM_LIVE
//    con la fecha de hoy. Sin ambas -> sólo registra lo que colocaría.
//  - PAPER (7497) es el default; --live (7496) es opt-in.
//  - Entries jamás descansan (tif DAY, transmit true, colocadas al PRINT).
//  - Sólo los stops protectivos pueden ser nativos; TODO nativo lleva orderRef
//    "OE:" y entra en cancel_all_own().
//  - Disarm-on-exit (SIGINT/SIGTERM/crash/atexit) cancela lo propio ANTES de morir.
//  - clientId 92 dedicado.
//
// Uso:
//   order_engine --paper --sym NVDA --sym QQQ --budget 200
//   order_engine --live --arm-live --sym QQQ        (requiere ARM_LIVE con hoy)
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>
#include <unistd.h>          // sleep() para el backoff de reconexión
#include <sys/socket.h>      // sondeo de puerto (gateway vs tws)
#include <netinet/in.h>
#include <arpa/inet.h>

#include "tws_adapter.h"
#include "safety.h"
#include "ledger.h"

using namespace oe;

// ======================================================= JSON mínimo
// Parser recursivo suficiente para el schema de exec_zones (obj/arr/str/num/bool/null).
struct JVal {
    enum T { NUL, BOOL, NUM, STR, ARR, OBJ } t = NUL;
    bool b = false;
    double num = 0;
    std::string str;
    std::vector<JVal> arr;
    std::map<std::string, JVal> obj;

    bool has(const std::string& k) const { return t == OBJ && obj.count(k); }
    double n(const std::string& k, double d) const { auto it = obj.find(k); return (it != obj.end() && it->second.t == NUM) ? it->second.num : d; }
    bool   flag(const std::string& k, bool d) const { auto it = obj.find(k); return (it != obj.end() && it->second.t == BOOL) ? it->second.b : d; }
    std::string s(const std::string& k, const std::string& d) const { auto it = obj.find(k); return (it != obj.end() && it->second.t == STR) ? it->second.str : d; }
    const JVal* child(const std::string& k) const { auto it = obj.find(k); return it != obj.end() ? &it->second : nullptr; }
};

struct JParser {
    const char* p; const char* end; bool okv = true;
    explicit JParser(const std::string& s) : p(s.data()), end(s.data() + s.size()) {}
    void ws() { while (p < end && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')) ++p; }
    JVal parse() { ws(); return value(); }
    JVal value() {
        ws();
        if (p >= end) { okv = false; return {}; }
        char c = *p;
        if (c == '{') return object();
        if (c == '[') return array();
        if (c == '"') { JVal v; v.t = JVal::STR; v.str = pstr(); return v; }
        if (c == 't' || c == 'f') return boolean();
        if (c == 'n') { p += (end - p >= 4 ? 4 : 0); JVal v; v.t = JVal::NUL; return v; }
        return number();
    }
    std::string pstr() {
        std::string o; ++p; // skip "
        while (p < end && *p != '"') {
            if (*p == '\\' && p + 1 < end) {
                ++p;
                switch (*p) {
                    case 'n': o += '\n'; break; case 't': o += '\t'; break;
                    case 'r': o += '\r'; break; case '"': o += '"'; break;
                    case '\\': o += '\\'; break; case '/': o += '/'; break;
                    default: o += *p; break;
                }
                ++p;
            } else { o += *p++; }
        }
        if (p < end) ++p; // skip closing "
        return o;
    }
    JVal number() {
        char* e = nullptr; double d = strtod(p, &e);
        if (e == p) { okv = false; return {}; }
        p = e; JVal v; v.t = JVal::NUM; v.num = d; return v;
    }
    JVal boolean() {
        JVal v; v.t = JVal::BOOL;
        if (end - p >= 4 && strncmp(p, "true", 4) == 0) { v.b = true; p += 4; }
        else if (end - p >= 5 && strncmp(p, "false", 5) == 0) { v.b = false; p += 5; }
        else okv = false;
        return v;
    }
    JVal array() {
        JVal v; v.t = JVal::ARR; ++p; ws();
        if (p < end && *p == ']') { ++p; return v; }
        while (p < end) {
            v.arr.push_back(value()); ws();
            if (p < end && *p == ',') { ++p; continue; }
            if (p < end && *p == ']') { ++p; break; }
            break;
        }
        return v;
    }
    JVal object() {
        JVal v; v.t = JVal::OBJ; ++p; ws();
        if (p < end && *p == '}') { ++p; return v; }
        while (p < end) {
            ws(); if (p >= end || *p != '"') break;
            std::string key = pstr(); ws();
            if (p < end && *p == ':') ++p;
            v.obj[key] = value(); ws();
            if (p < end && *p == ',') { ++p; continue; }
            if (p < end && *p == '}') { ++p; break; }
            break;
        }
        return v;
    }
};

// ======================================================= cadena de opciones
struct ChainRow { double strike = 0; std::string right, exp; double bid = -1, ask = -1; long oi = 0; double delta = 0; };
struct Chain { double spot = 0; long long epoch = 0; std::vector<ChainRow> rows; bool ok = false; };

static Chain load_chain(const std::string& path) {
    Chain ch;
    std::ifstream f(path);
    if (!f.is_open()) return ch;
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        if (line[0] == '#') {
            auto ep = line.find("epoch ");
            if (ep != std::string::npos) ch.epoch = atoll(line.c_str() + ep + 6);
            auto sp = line.find("spot ");
            if (sp != std::string::npos) ch.spot = atof(line.c_str() + sp + 5);
            continue;
        }
        std::istringstream ss(line);
        ChainRow r; std::string exp; long vol = 0; double iv = 0;
        if (!(ss >> r.strike >> r.right >> r.exp >> r.bid >> r.ask >> vol >> r.oi)) continue;
        ss >> iv >> r.delta;   // opcionales
        ch.rows.push_back(r);
    }
    ch.ok = !ch.rows.empty();
    return ch;
}

// Fila con strike más cercano al nivel, para el right+exp pedidos.
static const ChainRow* nearest_row(const Chain& ch, const std::string& right,
                                   const std::string& exp, double level) {
    const ChainRow* best = nullptr; double bd = 1e18;
    for (auto& r : ch.rows) {
        if (r.right != right) continue;
        if (!exp.empty() && r.exp != exp) continue;
        double d = std::fabs(r.strike - level);
        if (d < bd) { bd = d; best = &r; }
    }
    return best;
}

// ======================================================= gate (mirror order_ticket.py)
static const double MAX_SPREAD_PCT = 5.0;
static const long   MIN_OI = 500;
static const double MAX_AGE_S = 900;

struct Gate {
    bool go = false;
    double limit = 0, premium = 0, spread_pct = 0, delta = 0;
    long oi = 0; double strike = 0; std::string exp, right;
    std::vector<std::string> why;
};

// side: 'B' (comprar -> paga ask) | 'S' (vender -> cobra bid).
static Gate run_gate(const Chain& ch, const std::string& right, const std::string& exp,
                     double level, char side, double budget, long long now_s) {
    Gate g; g.right = right;
    if (!ch.ok) { g.why.push_back("sin cadena fresca"); return g; }
    const ChainRow* r = nearest_row(ch, right, exp, level);
    if (!r) { g.why.push_back("sin contrato para right/exp"); return g; }
    g.strike = r->strike; g.exp = r->exp; g.oi = r->oi; g.delta = r->delta;
    double age = (double)(now_s - ch.epoch);
    bool fresh = age <= MAX_AGE_S;
    bool quote_ok = r->bid > 0 && r->ask > 0 && r->ask >= r->bid;
    if (quote_ok) {
        double mid = (r->bid + r->ask) / 2.0;
        g.spread_pct = (r->ask - r->bid) / mid * 100.0;
    }
    g.limit = (side == 'B') ? r->ask : r->bid;
    g.premium = (g.limit > 0) ? g.limit * 100.0 : 0;
    bool spread_ok = quote_ok && g.spread_pct > 0 && g.spread_pct <= MAX_SPREAD_PCT;
    bool oi_ok = r->oi > MIN_OI;                 // doctrina: OI > 500 (estricto)
    bool budget_ok = g.premium > 0 && g.premium <= budget;
    if (!fresh) g.why.push_back("cadena vieja " + std::to_string((int)age) + "s");
    if (!quote_ok) g.why.push_back("sin bid/ask valido (iliquido)");
    else { char b[48]; std::snprintf(b, sizeof b, "spread %.1f%% %s", g.spread_pct, spread_ok ? "OK" : ">5% NO"); g.why.push_back(b); }
    if (!oi_ok) g.why.push_back("OI " + std::to_string(r->oi) + " < 500");
    if (!budget_ok) { char b[64]; std::snprintf(b, sizeof b, "prima $%.0f > $%.0f", g.premium, budget); g.why.push_back(b); }
    g.go = fresh && quote_ok && spread_ok && oi_ok && budget_ok;
    return g;
}

// ======================================================= NBBO del subyacente
// Último close del archivo de barras de la flota (space-delimited).
static bool last_close(const std::string& path, double& out) {
    std::ifstream f(path);
    if (!f.is_open()) return false;
    std::string line, last;
    while (std::getline(f, line)) if (!line.empty()) last = line;
    if (last.empty()) return false;
    std::istringstream ss(last);
    long long ep; double o, h, l, c;
    if (!(ss >> ep >> o >> h >> l >> c)) return false;
    out = c; return true;
}

// ======================================================= zona (estado runtime)
struct ZoneRT {
    // estáticos (del archivo, refrescables en vivo)
    std::string id, side, kind, exp, armed_date;
    std::string instrument = "opt";      // "opt" | "stk" (acciones tradean 24/5)
    double price = 0; int qty = 1; bool exec = false;
    bool stop_on = false, stop_native = true; double stop_px = 0;
    // runtime
    enum St { PLACED, TRIGGERED, SENT, FILLED, STOP_HIT, CANCELED, VETOED, REJECTED, DONE } st = PLACED;
    bool present = true;                 // sigue en el archivo
    // detección de PRINT (entrada)
    bool have_prev = false; double prev_spot = 0; int approach_sign = 0; int cross_cnt = 0;
    // ejecución
    int entry_id = -1; double fill_px = 0; double entry_delta = 0; Contract entry_c;
    double filled_qty = 0;               // cantidad REALMENTE llenada (proteger fills parciales)
    char entry_side = 'B';
    // stop
    int stop_id = -1; int close_id = -1;
    bool stop_armed = false; double placed_stop_px = 0;
    bool stop_confirmed = false;          // orderStatus Submitted/PreSubmitted visto (HIGH #1)
    int  stop_wait = 0;                   // ciclos esperando confirmación (watchdog)
    bool s_have_prev = false; double s_prev = 0; int s_sign = 0; int s_cnt = 0;
};

static const char* st_name(ZoneRT::St s) {
    switch (s) {
        case ZoneRT::PLACED: return "PLACED"; case ZoneRT::TRIGGERED: return "TRIGGERED";
        case ZoneRT::SENT: return "SENT"; case ZoneRT::FILLED: return "FILLED";
        case ZoneRT::STOP_HIT: return "STOP_HIT"; case ZoneRT::CANCELED: return "CANCELED";
        case ZoneRT::VETOED: return "VETOED"; case ZoneRT::REJECTED: return "REJECTED";
        default: return "DONE";
    }
}

// hysteresis del nivel
static double eps_of(double level) { return std::max(0.01, level * 0.0003); }
static int sgn(double x) { return (x > 0) - (x < 0); }

// ¿el precio está EN/ATRAVESANDO el nivel viniendo del lado de aproximación?
static bool crossed(int approach_sign, double cur, double level) {
    double e = eps_of(level);
    if (approach_sign >= 0) return cur <= level + e;   // veníamos de arriba -> baja al nivel
    return cur >= level - e;                            // veníamos de abajo -> sube al nivel
}

// ======================================================= estado a disco (chart)
static void write_state(const std::string& dir, const std::string& sym, const ZoneRT& z,
                        const std::string& extra) {
    std::string path = dir + "/" + sym + ".jsonl";
    std::ofstream out(path, std::ios::app);
    if (!out.is_open()) return;
    out << "{\"ts\":" << now_ms() << ",\"sym\":\"" << sym << "\",\"zone\":\"" << json_escape(z.id)
        << "\",\"state\":\"" << st_name(z.st) << "\",\"price\":" << z.price
        << ",\"side\":\"" << z.side << "\",\"kind\":\"" << z.kind << "\"";
    if (!extra.empty()) out << ',' << extra;
    out << "}\n";
}

// ======================================================= config CLI
struct Cfg {
    std::string repo = ".";
    std::string host = "127.0.0.1";
    int port = 7497;               // PAPER default
    int client = 92;               // dedicado order_engine
    bool arm_flag = false;         // --arm-live
    double budget = 200.0;         // prima máx por contrato de opción
    double stock_budget = 3000.0;  // notional máx por entrada de acciones
    std::vector<std::string> syms;
};

static std::string lower(std::string s) { for (auto& c : s) c = (char)tolower(c); return s; }

// ¿algo escucha en 127.0.0.1:port? (connect bloqueante a localhost = instantáneo).
static bool port_open(int port) {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return false;
    struct timeval tv{0, 300000};                  // 300ms guard
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
    sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons((uint16_t)port);
    inet_pton(AF_INET, "127.0.0.1", &a.sin_addr);
    bool ok = (::connect(fd, (sockaddr*)&a, sizeof a) == 0);
    ::close(fd);
    return ok;
}

// Puerto del modo: GATEWAY primero (4002/4001), TWS fallback (7497/7496). Auto-detecta
// el que esté escuchando. Espeja scripts/ib_mode.py -> el sistema entero usa el mismo.
static int resolve_port(const std::string& mode) {
    std::vector<int> ports = (mode == "live") ? std::vector<int>{4001, 7496}
                                              : std::vector<int>{4002, 7497};
    for (int p : ports) if (port_open(p)) return p;
    return ports[0];
}

int main(int argc, char** argv) {
    Cfg cfg;
    std::string cli_mode;         // "" | "paper" | "live" (de --paper/--live)
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&](const char* def) -> std::string { return (i + 1 < argc) ? argv[++i] : def; };
        if (a == "--paper") cli_mode = "paper";
        else if (a == "--live") cli_mode = "live";
        else if (a == "--arm-live") cfg.arm_flag = true;
        else if (a == "--sym") cfg.syms.push_back(next(""));
        else if (a == "--budget") cfg.budget = atof(next("200").c_str());
        else if (a == "--stock-budget") cfg.stock_budget = atof(next("3000").c_str());
        else if (a == "--host") cfg.host = next("127.0.0.1");
        else if (a == "--client") cfg.client = atoi(next("92").c_str());
        else if (a == "--repo") cfg.repo = next(".");
        else { std::fprintf(stderr, "flag desconocida: %s\n", a.c_str()); return 2; }
    }
    if (cfg.syms.empty()) { std::fprintf(stderr, "faltan --sym; ej: --sym QQQ --sym NVDA\n"); return 2; }

    // Modo: --paper/--live, o data/ib_mode.txt (fuente única, igual que ib_mode.py).
    // Puerto: env IBKR_PORT gana; si no, AUTO-DETECTA gateway(4002/4001)/tws(7497/7496).
    std::string mode = cli_mode;
    if (mode.empty()) {
        std::ifstream mf(cfg.repo + "/data/ib_mode.txt");
        std::string m; if (mf) std::getline(mf, m);
        size_t a0 = m.find_first_not_of(" \t\r\n"), b0 = m.find_last_not_of(" \t\r\n");
        m = (a0 == std::string::npos) ? "" : m.substr(a0, b0 - a0 + 1);
        for (auto& c : m) c = (char)tolower(c);
        mode = (m == "live") ? "live" : "paper";
    }
    const char* env_port = getenv("IBKR_PORT");
    if (env_port && atoi(env_port) > 0) cfg.port = atoi(env_port);
    else cfg.port = resolve_port(mode);
    std::fprintf(stderr, "[modo] %s -> puerto %d (%s)\n", mode.c_str(), cfg.port,
                 (cfg.port == 4002 || cfg.port == 4001) ? "gateway" : "tws");

    const std::string oe_dir     = cfg.repo + "/order_engine";
    const std::string arm_file   = oe_dir + "/ARM_LIVE";
    const std::string ledger_pth = oe_dir + "/ledger/orders.jsonl";
    const std::string state_dir  = oe_dir + "/state";
    const std::string cmd_path   = oe_dir + "/commands.jsonl";   // panel -> cancel/close/modify
    // arrancar al FINAL del archivo de comandos: ignorar comandos viejos/estancados (seguridad).
    long long cmd_off = 0;
    { std::ifstream cf0(cmd_path); if (cf0) { cf0.seekg(0, std::ios::end); cmd_off = (long long)cf0.tellg(); } }
    // crear dirs (mkdir superficial; el ledger crea su propio parent)
    (void)system(("mkdir -p '" + oe_dir + "/ledger' '" + state_dir + "' >/dev/null 2>&1").c_str());

    Ledger ledger(ledger_pth);
    if (!ledger.ok()) { std::fprintf(stderr, "no pude abrir ledger %s\n", ledger_pth.c_str()); return 1; }

    bool live_port = (mode == "live");
    std::fprintf(stderr,
        "=== order_engine ===  puerto=%d(%s) clientId=%d budget=$%.0f syms=%zu\n",
        cfg.port, live_port ? "LIVE" : "PAPER", cfg.client, cfg.budget, cfg.syms.size());
    ledger.note("boot port=" + std::to_string(cfg.port) + (live_port ? " LIVE" : " PAPER"));

    TwsAdapter tws(&ledger);

    if (!tws.connect(cfg.host.c_str(), cfg.port, cfg.client)) {
        std::fprintf(stderr, "conexión TWS falló (¿TWS arriba? ¿API on? ¿puerto %d?)\n", cfg.port);
        return 1;
    }
    // Esperar nextValidId (sin él no se ordena).
    for (int i = 0; i < 50 && !tws.have_ids(); ++i) tws.pump();
    if (!tws.have_ids()) { std::fprintf(stderr, "sin nextValidId — abortando\n"); tws.disconnect(); return 1; }

    // Allowlist de cuenta en LIVE: jamás apuntar dinero real a la cuenta equivocada.
    // AUDIT-FIX (crítico): verificar la cuenta SIEMPRE, no solo en --live. Si el Gateway
    // está logueado en la cuenta REAL y el modo dice "paper", sin este check ordenaríamos
    // con dinero real creyendo que es simulado. La cuenta del BROKER manda, no el modo.
    {
        for (int i = 0; i < 30 && tws.account().empty(); ++i) tws.pump();
        const std::string expected = live_port ? "U26942420" : "DUR197573";
        if (tws.account().find(expected) == std::string::npos) {
            std::fprintf(stderr, "[SEGURIDAD] modo=%s espera cuenta %s pero el broker reporta '%s' — ABORTO\n",
                         live_port ? "LIVE" : "PAPER", expected.c_str(), tws.account().c_str());
            ledger.note(std::string("ABORT cuenta no coincide: modo=") + (live_port ? "live" : "paper") +
                        " esperada=" + expected + " real='" + tws.account() + "'");
            tws.disconnect(); return 1;
        }
        std::fprintf(stderr, "[SEGURIDAD] cuenta verificada: %s (modo %s)\n",
                     tws.account().c_str(), live_port ? "LIVE" : "PAPER");
    }
    if (false) {
        if (tws.account().find("U26942420") == std::string::npos) {
            std::fprintf(stderr, "[SEGURIDAD] cuenta conectada '%s' NO es la TFSA live U26942420 — ABORTO\n",
                         tws.account().c_str());
            ledger.note("ABORT live account mismatch: '" + tws.account() + "'");
            tws.disconnect(); return 1;
        }
        std::fprintf(stderr, "[SEGURIDAD] cuenta live verificada: %s\n", tws.account().c_str());
    }

    // Reconciliar: cancelar huérfanas OE: de un run anterior. NO operar sin esto (MEDIUM #5).
    tws.reconcile();
    for (int i = 0; i < 80 && !tws.reconciled(); ++i) tws.pump();
    if (!tws.reconciled()) {
        std::fprintf(stderr, "[SEGURIDAD] reconcile no completó (openOrderEnd) — ABORTO: no opero con huérfanas desconocidas\n");
        ledger.note("ABORT reconcile timeout");
        tws.disconnect(); return 1;
    }

    // Disarm-on-exit: instalar DESPUÉS de connect+ids+reconcile (evita que atexit corra
    // sobre objetos ya destruidos en un early-return, MEDIUM #4) y ANTES del loop de órdenes.
    Guard::install([&tws, &ledger]() {
        tws.cancel_all_own();
        ledger.note("disarm-on-exit");
        ledger.flush();
    });

    std::string today = today_date();
    std::map<std::string, std::map<std::string, ZoneRT>> book;   // sym -> (zoneId -> ZoneRT)

    // AUDIT-FIX (crítico): IDEMPOTENCIA ENTRE REINICIOS. El estado runtime vive en RAM,
    // pero exec_zones_<sym>.json persiste con exec:true -> al reiniciar, una zona QUE YA
    // COMPRÓ volvería a comprar (doble gasto). Releemos state/<sym>.jsonl y marcamos como
    // DONE toda zona que ya pasó de PLACED: no vuelve a disparar salvo que se re-cree.
    {
        int blocked = 0;
        for (auto& sym : cfg.syms) {
            std::ifstream sf(state_dir + "/" + sym + ".jsonl");
            if (!sf) continue;
            std::string line;
            while (std::getline(sf, line)) {
                if (line.empty()) continue;
                JParser jp(line); JVal o = jp.parse();
                if (o.t != JVal::OBJ) continue;
                std::string zid = o.s("zone", ""), st = o.s("state", "");
                if (zid.empty() || st.empty() || st == "PLACED") continue;
                ZoneRT& z = book[sym][zid];
                z.id = zid; z.st = ZoneRT::DONE; z.present = false;
                ++blocked;
            }
        }
        if (blocked) {
            std::fprintf(stderr, "[idempotencia] %d zona(s) con ejecución previa marcadas DONE — no re-disparan\n", blocked);
            ledger.note("idempotencia: " + std::to_string(blocked) + " zonas previas bloqueadas");
        }
    }
    std::map<int, std::pair<std::string, std::string>> oid2zone; // orderId -> (sym, zoneId)

    std::fprintf(stderr, "loop activo. Ctrl-C para desarme limpio.\n");

    int reconnect_backoff = 1;
    while (!Guard::stop_requested()) {
        // --- HIGH #2: socket caído (connectionClosed) -> reconectar, no quedar congelado para siempre
        if (!tws.socket_alive()) {
            std::fprintf(stderr, "[tws] socket caído — reconnect en %ds\n", reconnect_backoff);
            ledger.note("socket caído -> reconnect backoff " + std::to_string(reconnect_backoff) + "s");
            sleep(reconnect_backoff);
            if (Guard::stop_requested()) break;
            if (tws.reconnect(cfg.host.c_str(), cfg.port, cfg.client)) {
                for (int i = 0; i < 50 && !tws.have_ids(); ++i) tws.pump();
                tws.reconcile();                              // cancela huérfanas OE: (incl. el stop viejo)
                for (int i = 0; i < 80 && !tws.reconciled(); ++i) tws.pump();
                reconnect_backoff = 1;
                // re-armar stops de posiciones vivas: reconcile canceló el nativo viejo, lo re-colocamos
                for (auto& [bsym, bmap] : book)
                    for (auto& [bk, bz] : bmap)
                        if (bz.st == ZoneRT::FILLED && bz.stop_on) {
                            bz.stop_armed = false; bz.stop_confirmed = false; bz.stop_id = -1; bz.stop_wait = 0;
                        }
                ledger.note("reconnect+reconcile ok -> re-armo stops de posiciones vivas");
            } else {
                reconnect_backoff = std::min(reconnect_backoff * 2, 30);
            }
            continue;
        }
        tws.pump();                 // procesa callbacks entrantes (hasta 2s)

        // --- drenar eventos de ejecución -> avanzar FSM
        ExecReport ev;
        while (tws.poll(ev)) {
            auto it = oid2zone.find(ev.order_id);
            if (it == oid2zone.end()) continue;
            auto& sym = it->second.first;
            auto zit = book[sym].find(it->second.second);
            if (zit == book[sym].end()) continue;
            ZoneRT& z = zit->second;
            if (ev.kind == ExecReport::FILL) {
                if (ev.order_id == z.entry_id && (z.st == ZoneRT::SENT || z.st == ZoneRT::TRIGGERED)) {
                    z.st = ZoneRT::FILLED;
                    z.fill_px = ev.px_c / 100.0;
                    z.filled_qty = ev.qty > 0 ? ev.qty : (double)(z.qty > 0 ? z.qty : 1);   // proteger lo llenado
                    write_state(state_dir, sym, z, "\"fill_px\":" + std::to_string(z.fill_px));
                    std::fprintf(stderr, "[%s] zona %s FILLED @ %.2f\n", sym.c_str(), z.id.c_str(), z.fill_px);
                } else if (ev.order_id == z.stop_id || ev.order_id == z.close_id) {
                    z.st = ZoneRT::STOP_HIT;
                    write_state(state_dir, sym, z, "\"close_px\":" + std::to_string(ev.px_c / 100.0));
                }
            } else if (ev.kind == ExecReport::REJECTED) {
                if (ev.order_id == z.entry_id) { z.st = ZoneRT::REJECTED; write_state(state_dir, sym, z, "\"note\":\"reject\""); }
            } else if (ev.kind == ExecReport::CANCELED) {
                if (ev.order_id == z.entry_id && z.st == ZoneRT::SENT) { z.st = ZoneRT::CANCELED; write_state(state_dir, sym, z, "\"note\":\"canceled\""); }
            } else if (ev.kind == ExecReport::ACK) {
                // HIGH #1: el stop nativo sólo cuenta como PROTECCIÓN cuando el servidor
                // lo acepta (Submitted/PreSubmitted). Hasta entonces stop_confirmed=false.
                if (ev.order_id == z.stop_id && !z.stop_confirmed) {
                    z.stop_confirmed = true;
                    ledger.note("stop nativo CONFIRMADO " + sym + " " + z.id);
                    std::fprintf(stderr, "[%s] zona %s stop nativo confirmado (%s)\n", sym.c_str(), z.id.c_str(), ev.status.c_str());
                }
            }
        }

        bool frozen = tws.frozen();
        long long now_s = now_ms() / 1000;

        // --- comandos del panel de cuenta: cancel / modify / close (líneas NUEVAS) ---
        {
            std::ifstream cf(cmd_path);
            if (cf) {
                cf.seekg(0, std::ios::end);
                long long sz = (long long)cf.tellg();
                if (sz > cmd_off) {
                    cf.seekg(cmd_off);
                    std::string buf(sz - cmd_off, '\0');
                    cf.read(&buf[0], sz - cmd_off);
                    size_t last_nl = buf.rfind('\n');       // AUDIT-FIX: solo líneas COMPLETAS
                    if (last_nl != std::string::npos) {
                    cmd_off += (long long)last_nl + 1;       // avanzar SOLO lo consumido (no 'sz')
                    std::stringstream cs(buf.substr(0, last_nl));
                    std::string line;
                    while (std::getline(cs, line)) {
                        if (line.empty()) continue;
                        JParser jp(line); JVal c = jp.parse();
                        if (c.t != JVal::OBJ) continue;
                        std::string act = c.s("act", "");
                        if (act == "cancel") {                       // cancelar SIEMPRE permitido (risk-off)
                            int oid = (int)c.n("orderId", -1);
                            if (oid >= 0) { tws.cancel(oid); ledger.note("cmd cancel " + std::to_string(oid)); }
                        } else if (act == "modify") {
                            int oid = (int)c.n("orderId", -1);
                            double lim = c.n("limit", 0);
                            if (oid >= 0 && lim > 0) {
                                if (armed_live(cfg.arm_flag, arm_file)) { tws.modify(oid, lim); ledger.note("cmd modify " + std::to_string(oid) + " -> " + std::to_string(lim)); }
                                else ledger.note("cmd modify DRY (sin doble llave) id=" + std::to_string(oid));
                            }
                        } else if (act == "close") {                 // cerrar posición = orden opuesta marketable
                            std::string csym = c.s("sym", ""), cright = c.s("right", ""), cexp = c.s("exp", ""), cside = c.s("side", "");
                            double cstrike = c.n("strike", 0);
                            int cqty = (int)c.n("qty", 0);
                            char side = (cside == "buy") ? 'B' : 'S';
                            bool is_opt = (cstrike > 0 && (cright == "C" || cright == "P"));
                            if (csym.empty() || cqty <= 0) { ledger.note("cmd close inválido"); continue; }
                            if (!armed_live(cfg.arm_flag, arm_file)) { ledger.note("cmd close DRY (sin doble llave) " + csym); continue; }
                            Contract cc; double lim = 0; bool outside = false;
                            if (is_opt) {
                                cc = make_option(csym, cexp, cstrike, cright);
                                Chain ch2 = load_chain(cfg.repo + "/data/opt_chain_" + lower(csym) + ".txt");
                                const ChainRow* r = nearest_row(ch2, cright, cexp, cstrike);
                                if (r && r->bid > 0 && r->ask > 0) lim = (side == 'B') ? r->ask : r->bid;
                                if (lim <= 0) { ledger.note("cmd close opt sin precio de cadena " + csym); continue; }
                            } else {
                                cc = make_stock(csym); outside = true;
                                double sp = 0;
                                if (!last_close(cfg.repo + "/data/bars_" + lower(csym) + "_ibkr.txt", sp) || sp <= 0) { ledger.note("cmd close stk sin spot " + csym); continue; }
                                lim = (side == 'B') ? sp * 1.002 : sp * 0.998;
                                lim = std::round(lim * 100.0) / 100.0;
                            }
                            int oid = tws.next_order_id();
                            tws.place_limit(cc, side, cqty, lim, oid, "OE:CLOSE", outside);
                            ledger.note("cmd close " + csym + " " + cside + " " + std::to_string(cqty) + " @ " + std::to_string(lim));
                        }
                    }
                    }  // if last_nl (línea a medio escribir se procesa el próximo ciclo)
                }
            }
        }

        for (auto& sym : cfg.syms) {
            std::string lo = lower(sym);
            // 1) recargar zonas del gráfico (refresca stop arrastrado, exec, etc.)
            std::string zpath = cfg.repo + "/data/exec_zones_" + lo + ".json";
            std::ifstream zf(zpath);
            std::map<std::string, ZoneRT>& zmap = book[sym];
            for (auto& [k, v] : zmap) v.present = false;
            if (zf.is_open()) {
                std::stringstream buf; buf << zf.rdbuf();
                std::string js = buf.str();        // NOMBRADO: JParser guarda punteros a ESTA string
                JParser jp(js); JVal arr = jp.parse();  // (buf.str() temporal colgaría el puntero)
                if (arr.t == JVal::ARR) {
                    for (auto& o : arr.arr) {
                        if (o.t != JVal::OBJ) continue;
                        std::string id = o.s("id", "");
                        if (id.empty()) continue;
                        ZoneRT& z = zmap[id];
                        z.id = id; z.present = true;
                        z.price = o.n("price", z.price);
                        z.side = o.s("side", z.side.empty() ? "buy" : z.side);
                        z.kind = o.s("kind", z.kind.empty() ? "call" : z.kind);
                        z.exp = o.s("exp", z.exp);
                        z.instrument = o.s("instrument", z.instrument.empty() ? "opt" : z.instrument);
                        z.qty = (int)o.n("qty", z.qty ? z.qty : 1);
                        z.exec = o.flag("exec", false);
                        z.armed_date = o.s("armed_date", z.armed_date);
                        if (const JVal* st = o.child("stop")) {
                            z.stop_on = st->flag("on", false);
                            z.stop_px = st->n("px", z.stop_px);
                            z.stop_native = st->flag("native", true);
                        }
                    }
                }
            }
            // zonas que desaparecieron: cancelar lo propio y marcar terminal
            for (auto& [k, z] : zmap) {
                if (!z.present && (z.entry_id >= 0 || z.stop_id >= 0) &&
                    z.st != ZoneRT::DONE) {
                    // Cancelar la ENTRADA en vuelo siempre (no debe quedar residual).
                    if (z.entry_id >= 0 && z.st != ZoneRT::FILLED) tws.cancel(z.entry_id);
                    // AUDIT-FIX: si la zona estaba LLENA, la posición sigue abierta ->
                    // NO cancelar su stop (la dejaría desnuda). Se avisa en voz alta.
                    if (z.stop_id >= 0 && z.st == ZoneRT::FILLED) {
                        std::fprintf(stderr, "[%s] ⚠ zona %s borrada del chart PERO la posición sigue abierta — DEJO el stop vivo\n",
                                     sym.c_str(), z.id.c_str());
                        ledger.note("zona borrada con posicion abierta: stop QUEDA vivo " + sym + " " + z.id);
                    } else if (z.stop_id >= 0) {
                        tws.cancel(z.stop_id);
                    }
                    z.st = ZoneRT::DONE;
                }
            }

            // 2) NBBO del subyacente (archivo de la flota)
            double spot = 0;
            if (!last_close(cfg.repo + "/data/bars_" + lo + "_ibkr.txt", spot)) continue;

            // 3) cadena para el gate / límite
            Chain ch = load_chain(cfg.repo + "/data/opt_chain_" + lo + ".txt");

            for (auto& [k, z] : zmap) {
                if (!z.present) continue;

                // ---- detección de PRINT de la entrada (sólo exec:true) ----
                if (z.st == ZoneRT::PLACED && z.exec) {
                    if (!z.have_prev) { z.have_prev = true; z.prev_spot = spot; z.approach_sign = sgn(spot - z.price); }
                    bool cr = crossed(z.approach_sign, spot, z.price);
                    z.cross_cnt = cr ? z.cross_cnt + 1 : 0;
                    z.prev_spot = spot;
                    if (z.cross_cnt >= 2) {          // PRINT-O-NADA: 2 lecturas
                        z.st = ZoneRT::TRIGGERED;
                        write_state(state_dir, sym, z, "\"spot\":" + std::to_string(spot));
                        std::fprintf(stderr, "[%s] zona %s TRIGGERED spot=%.2f nivel=%.2f\n",
                                     sym.c_str(), z.id.c_str(), spot, z.price);
                    }
                }

                // ---- gate + colocación (o DRY) ----
                if (z.st == ZoneRT::TRIGGERED) {
                    if (frozen) { std::fprintf(stderr, "[%s] zona %s congelada (1100/desconexión) — espero\n", sym.c_str(), z.id.c_str()); continue; }
                    char side = (z.side == "buy") ? 'B' : 'S';

                    // ===== ACCIONES (activos, 24/5 con horario extendido) =====
                    if (z.instrument == "stk") {
                        int qty = z.qty > 0 ? z.qty : 1;
                        if (spot <= 0) { write_state(state_dir, sym, z, "\"wait\":\"spot 0\""); continue; }
                        double notional = qty * spot;
                        if (notional > cfg.stock_budget) {
                            z.st = ZoneRT::VETOED;
                            char b[96]; std::snprintf(b, sizeof b, "notional $%.0f > budget $%.0f", notional, cfg.stock_budget);
                            write_state(state_dir, sym, z, std::string("\"veto\":\"") + b + "\"");
                            ledger.note(std::string("VETOED ") + sym + " " + z.id + ": " + b);
                            std::fprintf(stderr, "[%s] zona %s VETOED acciones: %s\n", sym.c_str(), z.id.c_str(), b);
                            continue;
                        }
                        double lim = (side == 'B') ? spot * 1.001 : spot * 0.999;   // marketable ext-hours
                        lim = std::round(lim * 100.0) / 100.0;
                        Contract c = make_stock(sym);
                        z.entry_c = c; z.entry_delta = 0; z.entry_side = side;
                        bool armed = armed_live(cfg.arm_flag, arm_file);
                        if (!armed) {
                            char b[224];
                            std::snprintf(b, sizeof b, "DRY colocaría %c %d acc %s @ %.2f (notional $%.0f)",
                                          side, qty, sym.c_str(), lim, notional);
                            ledger.note(std::string(b));
                            write_state(state_dir, sym, z, std::string("\"dry\":\"") + json_escape(b) + "\"");
                            std::fprintf(stderr, "[%s] zona %s %s  (sin doble llave)\n", sym.c_str(), z.id.c_str(), b);
                            z.st = ZoneRT::DONE; continue;
                        }
                        int oid = tws.next_order_id();
                        z.entry_id = oid; oid2zone[oid] = {sym, z.id};
                        tws.place_limit(c, side, qty, lim, oid, "OE:" + z.id, true);   // outsideRth=true
                        z.st = ZoneRT::SENT;
                        write_state(state_dir, sym, z, "\"instrument\":\"stk\",\"order_id\":" + std::to_string(oid) + ",\"limit\":" + std::to_string(lim));
                        continue;
                    }

                    // ===== OPCIONES =====
                    std::string right = (lower(z.kind)[0] == 'c') ? "C" : "P";
                    Gate g = run_gate(ch, right, z.exp, z.price, side, cfg.budget, now_s);
                    if (!g.go) {
                        std::string w; for (auto& s : g.why) { if (!w.empty()) w += "; "; w += s; }
                        // Transient (cadena vieja / sin cadena fresca): NO latchear VETOED;
                        // la cadena refrescará -> reintenta próximo ciclo desde TRIGGERED (LOW).
                        bool transient = false;
                        for (auto& s : g.why) if (s.find("cadena") != std::string::npos) transient = true;
                        if (transient) {
                            write_state(state_dir, sym, z, "\"wait\":\"" + json_escape(w) + "\"");
                            continue;
                        }
                        z.st = ZoneRT::VETOED;
                        write_state(state_dir, sym, z, "\"veto\":\"" + json_escape(w) + "\"");
                        ledger.note("VETOED " + sym + " " + z.id + ": " + w);
                        std::fprintf(stderr, "[%s] zona %s VETOED: %s\n", sym.c_str(), z.id.c_str(), w.c_str());
                        continue;
                    }
                    int qty = z.qty > 0 ? z.qty : std::max(1, (int)(cfg.budget / g.premium));
                    Contract c = make_option(sym, g.exp, g.strike, right);
                    z.entry_c = c; z.entry_delta = g.delta; z.entry_side = side;
                    // DOBLE LLAVE re-evaluada al momento (borrar ARM_LIVE desarma ya).
                    bool armed = armed_live(cfg.arm_flag, arm_file);
                    if (!armed) {
                        char b[256];
                        std::snprintf(b, sizeof b,
                            "DRY colocaría %c %dx %s %.4g%s exp %s @ %.2f (prima $%.0f)",
                            side, qty, sym.c_str(), g.strike, right.c_str(), g.exp.c_str(), g.limit, g.premium);
                        ledger.note(std::string(b));
                        write_state(state_dir, sym, z, std::string("\"dry\":\"") + json_escape(b) + "\"");
                        std::fprintf(stderr, "[%s] zona %s %s  (sin doble llave)\n", sym.c_str(), z.id.c_str(), b);
                        z.st = ZoneRT::DONE;    // DRY: no re-disparar en bucle
                        continue;
                    }
                    int oid = tws.next_order_id();
                    z.entry_id = oid; oid2zone[oid] = {sym, z.id};
                    tws.place_limit(c, side, qty, g.limit, oid, "OE:" + z.id);
                    z.st = ZoneRT::SENT;
                    write_state(state_dir, sym, z, "\"order_id\":" + std::to_string(oid) + ",\"limit\":" + std::to_string(g.limit));
                }

                // ---- stop apagado (toggle off) -> cancelar el nativo si estaba ----
                if (z.st == ZoneRT::FILLED && !z.stop_on && z.stop_id >= 0) {
                    tws.cancel(z.stop_id); z.stop_id = -1; z.stop_armed = false;
                }
                // ---- stop nativo arrastrado (nivel movido) -> re-armar ----
                if (z.st == ZoneRT::FILLED && z.stop_on && z.stop_native && z.stop_armed &&
                    z.stop_id >= 0 && std::fabs(z.stop_px - z.placed_stop_px) > eps_of(z.price)) {
                    tws.cancel(z.stop_id); z.stop_id = -1; z.stop_armed = false;
                }

                // ---- tras FILL: armar stop (una sola vez). NO armar congelado (HIGH #1). ----
                if (z.st == ZoneRT::FILLED && z.stop_on && !z.stop_armed && z.close_id < 0 && !frozen) {
                    char close_side = (z.entry_side == 'B') ? 'S' : 'B';   // cerrar = lado opuesto
                    int qty = z.filled_qty > 0 ? (int)z.filled_qty : (z.qty > 0 ? z.qty : 1);  // protege lo llenado
                    if (z.stop_native) {
                        double stop_trigger;
                        if (z.instrument == "stk") {
                            // acciones: el stop del subyacente ES el precio de la acción (directo).
                            stop_trigger = z.stop_px;
                        } else {
                            // opciones: mapear el nivel del SUBYACENTE a precio de la OPCIÓN vía delta.
                            // Aproximación honesta: opt_stop ≈ fill + delta*(stop_und - trigger_und).
                            double opt_stop;
                            if (std::fabs(z.entry_delta) > 1e-6)
                                opt_stop = z.fill_px + z.entry_delta * (z.stop_px - z.price);
                            else
                                opt_stop = z.fill_px * 0.6;   // fallback: stop -40% de la prima
                            // clamp de cordura (LOW): un delta malo no debe poner el STP donde
                            // dispara al instante o nunca. long(close=S): bajo el fill; short: sobre.
                            if (close_side == 'S') {
                                opt_stop = std::min(opt_stop, z.fill_px * 0.95);
                                opt_stop = std::max(opt_stop, std::max(0.01, z.fill_px * 0.10));
                            } else {
                                opt_stop = std::max(opt_stop, z.fill_px * 1.05);
                            }
                            if (opt_stop < 0.01) opt_stop = 0.01;
                            stop_trigger = opt_stop;
                        }
                        int oid = tws.next_order_id();
                        // stop_armed=true pero stop_confirmed=false: NO cuenta como protección
                        // hasta ver orderStatus Submitted (watchdog re-arma si no llega).
                        z.stop_id = oid; z.stop_armed = true; z.stop_confirmed = false; z.stop_wait = 0;
                        z.placed_stop_px = z.stop_px;
                        oid2zone[oid] = {sym, z.id};
                        tws.place_stop(z.entry_c, close_side, qty, stop_trigger, oid, "OE:" + z.id + ":STOP", true);
                        write_state(state_dir, sym, z, "\"stop_native\":true,\"stop_confirmed\":false,\"stop_trigger\":" + std::to_string(stop_trigger));
                        std::fprintf(stderr, "[%s] zona %s STOP nativo @%.2f (%s) — esperando confirmación\n",
                                     sym.c_str(), z.id.c_str(), stop_trigger, z.instrument.c_str());
                    } else {
                        // watch-local: el MOTOR es la protección (no hay orden server) -> confirmado ya.
                        z.s_have_prev = false; z.stop_id = -1; z.stop_armed = true; z.stop_confirmed = true;
                        write_state(state_dir, sym, z, "\"stop_native\":false,\"watch\":" + std::to_string(z.stop_px));
                        std::fprintf(stderr, "[%s] zona %s STOP watch-local und@%.2f\n", sym.c_str(), z.id.c_str(), z.stop_px);
                    }
                }

                // ---- watchdog HIGH #1: stop nativo colocado pero SIN confirmar -> re-armar + alerta ----
                if (z.st == ZoneRT::FILLED && z.stop_on && z.stop_native && z.stop_armed && !z.stop_confirmed) {
                    if (++z.stop_wait > 15) {   // ~30s (pump 2s)
                        std::fprintf(stderr, "[%s] zona %s STOP NO CONFIRMADO tras %d ciclos -> POSICIÓN SIN PROTECCIÓN, re-armo\n",
                                     sym.c_str(), z.id.c_str(), z.stop_wait);
                        ledger.note("ALERTA stop no confirmado " + sym + " " + z.id + " — posicion sin proteccion, re-armo");
                        if (z.stop_id >= 0) tws.cancel(z.stop_id);
                        z.stop_armed = false; z.stop_id = -1; z.stop_wait = 0;   // re-arma próximo ciclo si !frozen
                    }
                }

                // ---- watch-local del stop: PRINT del stop.px -> cerrar marketable ----
                if (z.st == ZoneRT::FILLED && z.stop_on && !z.stop_native && z.close_id < 0) {
                    if (!z.s_have_prev) { z.s_have_prev = true; z.s_prev = spot; z.s_sign = sgn(spot - z.stop_px); }
                    bool cr = crossed(z.s_sign, spot, z.stop_px);
                    z.s_cnt = cr ? z.s_cnt + 1 : 0;
                    z.s_prev = spot;
                    if (z.s_cnt >= 2 && !frozen) {
                        char close_side = (z.entry_side == 'B') ? 'S' : 'B';
                        std::string right = z.entry_c.right;
                        Gate g = run_gate(ch, right, z.entry_c.lastTradeDateOrContractMonth, z.entry_c.strike, close_side, 1e9, now_s);
                        // AUDIT-FIX: cerrar SOLO lo realmente llenado (z.qty sobre-vendería
                        // en un fill parcial -> corto no deseado). Sin precio de cadena NO
                        // rematamos a 0.01 (regalo): esperamos cadena fresca.
                        if (g.limit <= 0) {
                            ledger.note("ALERTA stop-local sin precio de cadena " + sym + " " + z.id + " — no remato a 0.01, espero");
                            std::fprintf(stderr, "[%s] zona %s STOP-LOCAL sin precio de cadena — espero (no remato)\n", sym.c_str(), z.id.c_str());
                            continue;
                        }
                        double lim = g.limit;
                        int qty = z.filled_qty > 0 ? (int)z.filled_qty : (z.qty > 0 ? z.qty : 1);
                        int oid = tws.next_order_id();
                        z.close_id = oid; oid2zone[oid] = {sym, z.id};
                        tws.place_limit(z.entry_c, close_side, qty, lim, oid, "OE:" + z.id + ":CLOSE");
                        write_state(state_dir, sym, z, "\"stop_close\":" + std::to_string(lim));
                        std::fprintf(stderr, "[%s] zona %s STOP-LOCAL PRINT und=%.2f -> cierro @ %.2f\n",
                                     sym.c_str(), z.id.c_str(), spot, lim);
                    }
                }
            }
        }
    }

    // salida limpia: desarme (idempotente) + flush + disconnect
    std::fprintf(stderr, "saliendo -> desarme\n");
    Guard::run_disarm_once();
    // drenar confirmaciones de cancelación un momento
    for (int i = 0; i < 10; ++i) tws.pump();
    tws.disconnect();
    ledger.flush();
    std::fprintf(stderr, "P&L neto realizado (broker): $%.2f | comisiones $%.2f\n",
                 ledger.net_realized_pnl(), ledger.total_commission());
    return 0;
}
