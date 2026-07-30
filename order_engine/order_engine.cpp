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
#include "account_cfg.h"
#include "guards.h"        // decisiones de dinero PURAS y testeables (tests/test_guards.cpp)
#include "chain.h"         // cadena de opciones + gate, PURAS y testeables (tests/test_chain.cpp)
#include "chase.h"         // persecución de fill en cierres, PURA (tests/test_chase.cpp)
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

// cadena de opciones + Gate/run_gate/nearest_row/exact_row: movidos a chain.h
// (funciones puras, testeables sin TWS -- ver order_engine/tests/test_chain.cpp).

// ======================================================= NBBO del subyacente
// Último close del archivo de barras de la flota (space-delimited).
static bool last_close(const std::string& path, double& out, long long* out_ep = nullptr) {
    std::ifstream f(path);
    if (!f.is_open()) return false;
    std::string line, last;
    while (std::getline(f, line)) if (!line.empty()) last = line;
    if (last.empty()) return false;
    std::istringstream ss(last);
    long long ep; double o, h, l, c;
    if (!(ss >> ep >> o >> h >> l >> c)) return false;
    out = c; if (out_ep) *out_ep = ep; return true;
}

// ======================================================= zona (estado runtime)
struct ZoneRT {
    // estáticos (del archivo, refrescables en vivo)
    std::string id, side, kind, exp, armed_date, confirm_id;
    long long confirmed_at_ms = 0;
    std::string instrument = "opt";      // "opt" | "stk" (acciones tradean 24/5)
    double price = 0, locked_strike = 0, locked_limit = 0; int qty = 1;
    bool exec = false, overnight_gap_ack = false;
    std::string locked_right, locked_exp;
    bool stop_on = false, stop_native = true; double stop_px = 0;
    // runtime
    enum St { PLACED, TRIGGERED, SENT, FILLED, STOP_HIT, CANCELED, VETOED, REJECTED, DONE } st = PLACED;
    bool present = true;                 // sigue en el archivo
    // detección de PRINT (entrada)
    bool have_prev = false; double prev_spot = 0; int approach_sign = 0; int cross_cnt = 0;
    long long last_cross_ep = 0;   // epoch de la ultima BARRA contada (print-o-nada real)
    // ejecución
    int entry_id = -1; double fill_px = 0; double entry_delta = 0; Contract entry_c;
    // iv del contrato AL LLENAR: entry_delta por si sola no dice si es de fiar
    // (el centinela -1.0000 tiene magnitud > 1e-6, ver guards.h #10). Guardar
    // el iv que la acompañaba es lo único que permite distinguir "delta real"
    // de "modelGreeks ausente" en el momento de calcular el stop.
    double entry_iv = -1.0;
    double filled_qty = 0;               // cantidad REALMENTE llenada (proteger fills parciales)
    char entry_side = 'B';
    // stop
    int stop_id = -1; int close_id = -1;
    bool stop_armed = false; double placed_stop_px = 0;
    bool stop_confirmed = false;          // orderStatus Submitted/PreSubmitted visto (HIGH #1)
    int  stop_wait = 0;                   // ciclos esperando confirmación (watchdog)
    int  stop_retries = 0;                // re-armes del watchdog; tope 3 -> watch-local
    bool stop_degraded = false;           // stop nativo imposible -> watch-local PEGAJOSO
    bool s_have_prev = false; double s_prev = 0; int s_sign = 0; int s_cnt = 0;
    long long s_last_cross_ep = 0;        // epoch de la ultima BARRA contada en el stop-local (defecto 4)
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

// Bandera en disco de POSICIÓN DESNUDA (guarda #5). stderr se lo lleva el log y
// nadie lo mira; un fichero con mtime de hoy lo ve el healthcheck y el panel.
static void shout_naked_stop(const std::string& dir, const std::string& sym,
                             const std::string& zone, const std::string& msg) {
    std::ofstream f(dir + "/NAKED_STOP.jsonl", std::ios::app);
    if (!f.is_open()) return;
    f << "{\"ts\":" << now_ms() << ",\"sym\":\"" << json_escape(sym) << "\",\"zone\":\""
      << json_escape(zone) << "\",\"msg\":\"" << json_escape(msg) << "\"}\n";
}

// ======================================================= config CLI
struct Cfg {
    std::string repo = ".";
    std::string host = "127.0.0.1";
    int port = 7497;               // PAPER default
    int client = 92;               // dedicado order_engine
    bool arm_flag = false;         // --arm-live
    double budget = 200.0;         // prima máx por CONTRATO de opción
    double max_order = 0;          // desembolso máx por ORDEN (qty*prima); 0 = sigue a budget
    double stock_budget = 3000.0;  // notional máx por entrada de acciones
    // Tope AGREGADO por cuenta (guarda #1/#2). Los otros topes son POR ZONA y POR
    // ORDEN: N zonas armadas multiplicaban el desembolso sin techo global (20 zonas
    // de $200 = $4.000 comprometidos sin que ninguna guarda dijera nada). Este es el
    // único que mira la SUMA. Falla cerrado: 0 -> no se opera.
    double account_cap = 3000.0;
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
        else if (a == "--max-order") cfg.max_order = atof(next("200").c_str());
        else if (a == "--stock-budget") cfg.stock_budget = atof(next("3000").c_str());
        else if (a == "--account-cap") cfg.account_cap = atof(next("3000").c_str());
        else if (a == "--host") cfg.host = next("127.0.0.1");
        else if (a == "--client") cfg.client = atoi(next("92").c_str());
        else if (a == "--repo") cfg.repo = next(".");
        else { std::fprintf(stderr, "flag desconocida: %s\n", a.c_str()); return 2; }
    }
    if (cfg.syms.empty()) { std::fprintf(stderr, "faltan --sym; ej: --sym QQQ --sym NVDA\n"); return 2; }
    // Sin --max-order explícito, el tope por orden = el tope por contrato: qty>1 exige
    // decisión consciente. Subirlo es un acto deliberado, no un descuido del chart.
    if (cfg.max_order <= 0) cfg.max_order = cfg.budget;

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
        // La cuenta esperada ya NO esta en el codigo: sale de la config del usuario
        // (env / config.json de la .app / data/account.txt). FALLA CERRADO: sin cuenta
        // configurada el motor NO opera — si nadie declaro que cuenta espera, no hay
        // forma de saber que el Gateway esta logueado donde crees.
        const std::string expected = oe::expected_account(live_port, cfg.repo);
        if (expected.empty()) {
            std::fprintf(stderr,
                "[SEGURIDAD] no hay cuenta %s configurada — ABORTO.\n"
                "  Configurala de UNA de estas formas:\n"
                "   - la app: menu 📈 -> Configuracion -> Cuenta IBKR\n"
                "   - fichero: %s/data/account.txt  con  %s=%s\n"
                "   - entorno: export IBTRADER_ACCOUNT_%s=...\n",
                live_port ? "LIVE" : "PAPER", cfg.repo.c_str(),
                live_port ? "live" : "paper", live_port ? "U1234567" : "DU1234567",
                live_port ? "LIVE" : "PAPER");
            ledger.note(std::string("ABORT sin cuenta configurada modo=") + (live_port ? "live" : "paper"));
            tws.disconnect(); return 1;
        }
        // `managedAccounts` llega como CSV ("DUR197573,U26942420"). El find() que habia
        // aqui era coincidencia por SUBCADENA: "U2694242" pasaba el filtro contra un
        // Gateway logueado en "U26942420", y al reves. Eso es apuntar dinero real a otra
        // cuenta. oe::accounts_match tokeniza por coma y compara EXACTO (falla cerrado).
        // Testigo del bug + fix en order_engine/tests/test_guards.cpp (#8).
        if (!oe::accounts_match(tws.account(), expected)) {
            std::fprintf(stderr, "[SEGURIDAD] modo=%s espera cuenta %s pero el broker reporta '%s' — ABORTO\n",
                         live_port ? "LIVE" : "PAPER", expected.c_str(), tws.account().c_str());
            ledger.note(std::string("ABORT cuenta no coincide: modo=") + (live_port ? "live" : "paper") +
                        " esperada=" + expected + " real='" + tws.account() + "'");
            tws.disconnect(); return 1;
        }
        std::fprintf(stderr, "[SEGURIDAD] cuenta verificada: %s (modo %s)\n",
                     tws.account().c_str(), live_port ? "LIVE" : "PAPER");
        // managedAccounts puede listar varias cuentas; fijar Order.account evita
        // depender de la cuenta por defecto seleccionada en TWS.
        tws.set_execution_account(expected);
    }
    // (eliminado 2026-07-25: bloque muerto `if (false)` con la cuenta a fuego;
    //  la verificacion real y configurable es la de arriba)

    // Reconciliar: cancelar huérfanas OE: de un run anterior. NO operar sin esto (MEDIUM #5).
    tws.reconcile();
    for (int i = 0; i < 80 && !tws.reconciled(); ++i) tws.pump();
    if (!tws.reconciled()) {
        std::fprintf(stderr, "[SEGURIDAD] reconcile no completó (openOrderEnd) — ABORTO: no opero con huérfanas desconocidas\n");
        ledger.note("ABORT reconcile timeout");
        tws.disconnect(); return 1;
    }

    // Posiciones REALES (#3/#7, defecto 3 del encargo 2026-07-25): "cmd close"
    // del panel debe validar cqty contra lo que el broker de verdad tiene
    // abierto, NUNCA contra el estado local en RAM (book[] no decrementa
    // filled_qty cuando un close se llena -- su orderId ni entra en oid2zone).
    // decide_close_qty() (guards.h) ya falla CERRADO mientras positions() no
    // este known(), asi que esto no aborta el arranque -- solo avisa. reqPositions
    // puede tardar mas que reconcile; el loop principal sigue pumpeando y
    // positionEnd() puede llegar mas tarde igual.
    tws.reqPositions();
    for (int i = 0; i < 80 && !tws.positions().known(); ++i) tws.pump();
    if (!tws.positions().known())
        std::fprintf(stderr, "[SEGURIDAD] posiciones aun no confirmadas (positionEnd pendiente) — 'close' se rechazara hasta entonces\n");
    else
        std::fprintf(stderr, "[SEGURIDAD] posiciones confirmadas\n");

    // Disarm-on-exit: instalar DESPUÉS de connect+ids+reconcile (evita que atexit corra
    // sobre objetos ya destruidos en un early-return, MEDIUM #4) y ANTES del loop de órdenes.
    Guard::install([&tws, &ledger]() {
        tws.cancel_all_own();
        ledger.note("disarm-on-exit");
        ledger.flush();
    });

    std::string today = today_date();
    std::map<std::string, std::map<std::string, ZoneRT>> book;   // sym -> (zoneId -> ZoneRT)
    // Libro de exposicion AGREGADA (guarda #1/#2, guards.h). Se reserva el
    // desembolso REAL justo antes de colocar y se libera cuando la zona muere sin
    // posicion. Es el unico tope que ve la SUMA de todas las zonas de todos los
    // simbolos; los demas (budget/max_order/stock_budget) son por contrato/orden.
    ExposureBook expo; expo.cap = cfg.account_cap;
    if (!(expo.cap > 0))
        std::fprintf(stderr, "[SEGURIDAD] --account-cap %.0f: sin tope agregado NO se coloca nada (falla cerrado)\n", cfg.account_cap);

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
    // ---- persecución de fill de CIERRES (chase.h). Un cierre que descansa es
    // exposición viva: se re-pega hacia el marketable fresco, acotado al tope.
    struct ChaseRec {
        std::string sym, label; Contract c; char side = 'S';
        double placed = 0, ref = 0; long long last_s = 0;
        int repegs = 0; bool is_opt = true, shouted = false;
    };
    std::map<int, ChaseRec> chase;                               // orderId -> chase
    const oe::ChaseCfg chase_cfg;
    // quick-orders humanos (cmd "open"): exposición reservada hasta cancel/reject.
    // Un fill deja el dinero reservado (conservador: el cap agregado nunca sub-cuenta).
    std::map<int, std::string> open_expo;                        // orderId -> expo key
    auto chase_track = [&chase](int oid, const std::string& sym, const Contract& c,
                                char side, double lim, long long now_s,
                                const std::string& label) {
        ChaseRec cr; cr.sym = sym; cr.label = label; cr.c = c; cr.side = side;
        cr.placed = lim; cr.ref = lim; cr.last_s = now_s;
        cr.is_opt = (c.secType == "OPT");
        chase[oid] = cr;
    };

    std::fprintf(stderr, "loop activo. Ctrl-C para desarme limpio.\n");

    int reconnect_backoff = 1;
    long long last_positions_req_s = now_ms() / 1000;
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
                tws.reqPositions();                           // refresca posiciones tras reconnect (#3/#7)
                for (int i = 0; i < 80 && !tws.positions().known(); ++i) tws.pump();
                // GUARDA #6 (safe_to_touch_orders): el ARRANQUE aborta si reconcile no
                // completa, el RECONNECT no lo comprobaba y pasaba directo a re-armar
                // stops. Sin openOrderEnd el motor no sabe qué stop sobrevivió ->
                // adopted_stop_id() devuelve -1 sobre un mapa a medio llenar y coloca
                // un SEGUNDO stop sobre la misma posición: al disparar vende el doble
                // y deja CORTO en descubierto, con ambos GTC. Si falta cualquiera de
                // las dos verdades del broker, no se toca NADA y se reintenta.
                if (!oe::safe_to_touch_orders(tws.reconciled(), tws.positions().known())) {
                    std::fprintf(stderr, "[SEGURIDAD] reconnect a medias (reconcile=%d posiciones=%d) — NO toco stops, reintento\n",
                                 (int)tws.reconciled(), (int)tws.positions().known());
                    ledger.note("reconnect a medias -> no se tocan ordenes (reconcile=" +
                                std::to_string((int)tws.reconciled()) + " positions=" +
                                std::to_string((int)tws.positions().known()) + ")");
                    reconnect_backoff = std::min(reconnect_backoff * 2, 30);
                    continue;
                }
                reconnect_backoff = 1;
                // Stops tras reconnect. OJO: reconcile NO cancela los STP — los ADOPTA
                // (tws_adapter.cpp:224, protegen una posición real). Resetear a ciegas
                // colocaba un SEGUNDO stop sobre la misma posición: al disparar vendía
                // el doble y te dejaba CORTO en descubierto, con ambos GTC (sobreviven
                // la noche). Fix 2026-07-24: adoptar el que ya existe; re-armar sólo si
                // de verdad no quedó ninguno.
                for (auto& [bsym, bmap] : book)
                    for (auto& [bk, bz] : bmap)
                        if (bz.st == ZoneRT::FILLED && bz.stop_on) {
                            int adopted = tws.adopted_stop_id("OE:" + bz.id + ":STOP");
                            if (adopted >= 0) {
                                bz.stop_id = adopted; bz.stop_armed = true;
                                bz.stop_confirmed = true; bz.stop_wait = 0;
                                ledger.note("stop nativo ADOPTADO tras reconnect id=" +
                                            std::to_string(adopted) + " zona " + bz.id);
                                std::fprintf(stderr, "[%s] stop nativo adoptado id=%d zona %s (no re-coloco)\n",
                                             bsym.c_str(), adopted, bz.id.c_str());
                            } else {
                                bz.stop_armed = false; bz.stop_confirmed = false;
                                bz.stop_id = -1; bz.stop_wait = 0;
                            }
                        }
                ledger.note("reconnect+reconcile ok -> stops adoptados/re-armados");
            } else {
                reconnect_backoff = std::min(reconnect_backoff * 2, 30);
            }
            continue;
        }
        tws.pump();                 // procesa callbacks entrantes (hasta 2s)

        // --- drenar eventos de ejecución -> avanzar FSM
        ExecReport ev;
        while (tws.poll(ev)) {
            // chase: soltar la orden al terminar. "Partial" sigue viva -> se sigue
            // persiguiendo el remanente; "Filled"/"PartialThenCancel" ya no existen.
            if (auto cit = chase.find(ev.order_id); cit != chase.end()) {
                if ((ev.kind == ExecReport::FILL && ev.status != "Partial") ||
                    ev.kind == ExecReport::CANCELED || ev.kind == ExecReport::REJECTED)
                    chase.erase(cit);
            }
            if (auto oit = open_expo.find(ev.order_id); oit != open_expo.end()) {
                if (ev.kind == ExecReport::CANCELED || ev.kind == ExecReport::REJECTED) {
                    expo.release(oit->second);                   // nunca se gastó
                    open_expo.erase(oit);
                } else if (ev.kind == ExecReport::FILL && ev.status != "Partial") {
                    open_expo.erase(oit);                        // gastado de verdad; la reserva queda
                }
            }
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
                } else if (ev.order_id == z.entry_id && z.st == ZoneRT::FILLED &&
                           ev.qty > z.filled_qty + 1e-9) {
                    // Llegó MÁS cantidad de la misma entrada (parcial que sigue llenando):
                    // el stop vigente protege de menos. Re-armar por el total.
                    const double antes = z.filled_qty;
                    z.filled_qty = ev.qty;
                    z.fill_px = ev.px_c / 100.0;          // avgFillPrice acumulado de TWS
                    if (z.stop_id >= 0) { tws.cancel(z.stop_id); z.stop_id = -1; }
                    z.stop_armed = false; z.stop_confirmed = false; z.stop_wait = 0;
                    ledger.note("fill parcial crece " + std::to_string(antes) + " -> " +
                                std::to_string(z.filled_qty) + " zona " + z.id + " -> re-armo stop");
                    std::fprintf(stderr, "[%s] zona %s parcial %.0f -> %.0f, re-armo stop\n",
                                 sym.c_str(), z.id.c_str(), antes, z.filled_qty);
                } else if (ev.order_id == z.stop_id || ev.order_id == z.close_id) {
                    z.st = ZoneRT::STOP_HIT;
                    // posicion cerrada -> el dinero vuelve al bolsillo agregado
                    expo.release(oe::exposure_key(sym, z.id));
                    write_state(state_dir, sym, z, "\"close_px\":" + std::to_string(ev.px_c / 100.0));
                }
            } else if (ev.kind == ExecReport::REJECTED) {
                if (ev.order_id == z.entry_id) {
                    z.st = ZoneRT::REJECTED;
                    expo.release(oe::exposure_key(sym, z.id));   // nunca se gasto
                    write_state(state_dir, sym, z, "\"note\":\"reject\"");
                }
            } else if (ev.kind == ExecReport::CANCELED) {
                if (ev.order_id == z.entry_id && z.st == ZoneRT::SENT) {
                    z.st = ZoneRT::CANCELED;
                    expo.release(oe::exposure_key(sym, z.id));   // nunca se gasto
                    write_state(state_dir, sym, z, "\"note\":\"canceled\"");
                }
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
        // SELL gates use broker inventory, never a local guess. Refresh it so a
        // BUY filled during this run can later be reduced safely.
        if (now_s - last_positions_req_s >= 15) {
            tws.reqPositions();
            last_positions_req_s = now_s;
        }

        // --- chase: re-pegar cierres dormidos hacia el marketable fresco ---
        if (!frozen) for (auto& [coid, cr] : chase) {
            if (now_s - cr.last_s < chase_cfg.interval_s) continue;   // pacing antes de tocar disco
            double fresh = 0;
            if (cr.is_opt) {
                Chain chf = load_chain(cfg.repo + "/data/opt_chain_" + lower(cr.sym) + ".txt");
                Gate gf = run_gate(chf, cr.c.right, cr.c.lastTradeDateOrContractMonth,
                                   cr.c.strike, cr.side, 1e9, now_s, /*require_exact_strike=*/true);
                if (gf.go) fresh = gf.limit;   // sin cadena fresca no se persigue (fail-closed)
            } else {
                double sp = 0;
                if (last_close(cfg.repo + "/data/bars_" + lower(cr.sym) + "_ibkr.txt", sp) && sp > 0)
                    fresh = (cr.side == 'B') ? sp * 1.002 : sp * 0.998;
            }
            const oe::RepegDecision d = oe::decide_repeg(cr.side, cr.placed, cr.ref, fresh,
                                                         cr.repegs, cr.last_s, now_s,
                                                         cr.is_opt, chase_cfg);
            if (d.modify) {
                tws.modify(coid, d.new_limit);
                cr.placed = d.new_limit; cr.last_s = now_s; ++cr.repegs;
                char b[160];
                std::snprintf(b, sizeof b, "CHASE %s %s id=%d repeg %d -> %.2f",
                              cr.sym.c_str(), cr.label.c_str(), coid, cr.repegs, d.new_limit);
                ledger.note(b);
                std::fprintf(stderr, "[%s] %s\n", cr.sym.c_str(), b);
            } else if (d.exhausted && !cr.shouted) {
                cr.shouted = true;
                char b[192];
                std::snprintf(b, sizeof b,
                              "CHASE EXHAUSTO %s %s id=%d: tope de slippage; la orden descansa en %.2f",
                              cr.sym.c_str(), cr.label.c_str(), coid, cr.placed);
                ledger.note(b);
                std::fprintf(stderr, "[%s] ⚠ %s\n", cr.sym.c_str(), b);
            }
        }

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
                            // NUNCA asumir el lado de una orden de dinero: si falta o es basura,
                            // se RECHAZA. El default silencioso 'S' duplicaba cortos (2026-07-24).
                            if (cside != "buy" && cside != "sell") {
                                ledger.note("cmd close RECHAZADO: side ausente o invalido ('" + cside + "') " + csym);
                                std::fprintf(stderr, "[cmd] close RECHAZADO %s: side='%s' no es buy/sell\n",
                                             csym.c_str(), cside.c_str());
                                continue;
                            }
                            char side = (cside == "buy") ? 'B' : 'S';
                            bool is_opt = (cstrike > 0 && (cright == "C" || cright == "P"));
                            if (csym.empty() || cqty <= 0) { ledger.note("cmd close inválido"); continue; }

                            // --- DEFECTO 3 (2026-07-25): GATE DE TAMAÑO -----------------------
                            // "close" era la UNICA ruta de orden sin gate de tamaño: validaba
                            // side (arriba, fix 24-jul) pero nunca cqty contra lo que el broker
                            // de verdad tiene abierto. decide_close_qty (guards.h #3/#7) es la
                            // guarda ya escrita y testeada (test_guards.cpp) que faltaba cablear.
                            // La fuente es tws.positions() = reqPositions() REAL, nunca book[]
                            // local (que no decrementa filled_qty en un close, ver tws_adapter.h)
                            // -- eso habria sido otro numero plausible como el centinela del
                            // defecto 1. Se corre ANTES de tocar armed_live/precio: si el tamaño
                            // no cuadra, ni se molesta en preciar.
                            oe::PosKey cpk = is_opt ? oe::pos_key_option(csym, cexp, cstrike, cright)
                                                    : oe::pos_key_stock(csym);
                            oe::CloseDecision cdec = oe::decide_close_qty(tws.positions(), cpk, cqty, side);
                            if (!cdec.ok) {
                                ledger.note("cmd close RECHAZADO " + csym + ": " + cdec.reason);
                                std::fprintf(stderr, "[cmd] close RECHAZADO %s: %s\n", csym.c_str(), cdec.reason.c_str());
                                continue;
                            }
                            if (cdec.clamped) {
                                ledger.note("cmd close CLAMP " + csym + ": " + cdec.reason);
                                std::fprintf(stderr, "[cmd] close CLAMP %s: %s\n", csym.c_str(), cdec.reason.c_str());
                            }
                            cqty = cdec.qty;   // jamas mas de lo que el broker reporta abierto

                            if (!armed_live(cfg.arm_flag, arm_file)) { ledger.note("cmd close DRY (sin doble llave) " + csym); continue; }
                            Contract cc; double lim = 0;
                            if (is_opt) {
                                cc = make_option(csym, cexp, cstrike, cright);
                                Chain ch2 = load_chain(cfg.repo + "/data/opt_chain_" + lower(csym) + ".txt");
                                // DEFECTO 3 (a) + DEFECTO 2: nearest_row() sin tope de distancia
                                // podia preciar sobre un contrato VECINO (la orden sale, no llena,
                                // y el panel ya respondio {"ok":true} -- "crees que estas plano y
                                // no lo estas"). run_gate(..., require_exact_strike=true) exige
                                // right+exp+strike EXACTOS (exact_row) y de paso aporta la
                                // frescura/spread/OI que este camino jamas tuvo, igual que ya hace
                                // el stop watch-local en :988 con presupuesto infinito (cerrar no
                                // se veta por dinero, pero si por cadena podrida o contrato erroneo).
                                Gate g = run_gate(ch2, cright, cexp, cstrike, side, 1e9, now_s, /*require_exact_strike=*/true);
                                if (!g.go) {
                                    std::string w; for (auto& s : g.why) { if (!w.empty()) w += "; "; w += s; }
                                    ledger.note("cmd close opt VETADO " + csym + ": " + w);
                                    std::fprintf(stderr, "[cmd] close VETADO %s: %s\n", csym.c_str(), w.c_str());
                                    continue;
                                }
                                lim = g.limit;
                            } else {
                                cc = make_stock(csym);
                                double sp = 0;
                                if (!last_close(cfg.repo + "/data/bars_" + lower(csym) + "_ibkr.txt", sp) || sp <= 0) { ledger.note("cmd close stk sin spot " + csym); continue; }
                                lim = (side == 'B') ? sp * 1.002 : sp * 0.998;
                                lim = std::round(lim * 100.0) / 100.0;
                            }
                            const oe::OrderSession close_session = is_opt
                                ? oe::OrderSession::RTH_ONLY
                                : oe::OrderSession::OVERNIGHT_AND_DAY;
                            const oe::LimitOrderPlan close_plan = oe::make_limit_order_plan(
                                cc, side, cqty, lim, "OE:CLOSE", close_session,
                                tws.server_version(), false, tws.execution_account());
                            if (!close_plan.ok) {
                                ledger.note("cmd close VETADO " + csym + ": " + close_plan.error);
                                std::fprintf(stderr, "[cmd] close VETADO %s: %s\n",
                                             csym.c_str(), close_plan.error.c_str());
                                continue;
                            }
                            oe::PreflightReport close_pf;
                            if (!tws.preflight_limit(cc, side, cqty, lim, "OE:WHATIF:CLOSE",
                                                     close_session, close_pf)) {
                                ledger.note("cmd close WHAT-IF RECHAZADO " + csym + ": " +
                                            close_pf.warning);
                                std::fprintf(stderr, "[cmd] close WHAT-IF RECHAZADO %s: %s\n",
                                             csym.c_str(), close_pf.warning.c_str());
                                continue;
                            }
                            // --- STOP HUERFANO (guarda #4, la causa documentada del desastre) ---
                            // ANTES de mandar el close: el stop NATIVO que protege esta posicion
                            // vive en el servidor de IBKR. Si no se cancela, al llenarse el close
                            // la posicion es 0 pero el stop sigue GTC: cuando el precio lo toque
                            // ABRE una posicion nueva, del lado contrario, sin que nadie lo pida.
                            // En la TFSA (no shortea) un stop de venta huerfano intenta abrir un
                            // corto prohibido. Se cancela PRIMERO: cancelar solo puede quitar una
                            // orden, jamas crearla, asi que el orden es el seguro.
                            {
                                oe::CloseReq creq;
                                creq.is_opt = is_opt; creq.exp = cexp; creq.strike = cstrike;
                                creq.right = cright.empty() ? 0 : cright[0]; creq.qty = cqty;
                                std::vector<oe::StopRef> refs;
                                std::map<std::string, ZoneRT>& zb = book[csym];
                                for (auto& [zk, zz] : zb) {
                                    // El emparejamiento va contra `entry_c`, el contrato REAL que
                                    // se lleno y sobre el que se coloco el stop (place_stop(z.entry_c
                                    // ...)). NO contra `z.price`: ese es el nivel de DISPARO de la
                                    // zona (se compara con el spot en la deteccion de print), y el
                                    // strike efectivo lo elige el gate (`g.strike`), que puede no
                                    // coincidir. Emparejar por z.price cancelaria el stop equivocado.
                                    oe::StopRef sr;
                                    sr.zone_id = zk;
                                    sr.instrument = (zz.entry_c.secType == "OPT") ? "opt" : "stk";
                                    sr.exp = zz.entry_c.lastTradeDateOrContractMonth;
                                    sr.strike = zz.entry_c.strike;
                                    sr.right = zz.entry_c.right.empty() ? 0 : zz.entry_c.right[0];
                                    sr.stop_id = zz.stop_id; sr.filled_qty = zz.filled_qty;
                                    refs.push_back(sr);
                                }
                                for (const oe::OrphanCancel& oc : oe::stops_orphaned_by_close(creq, refs)) {
                                    tws.cancel(oc.stop_id);
                                    ZoneRT& zz = zb[oc.zone_id];
                                    zz.stop_id = -1;
                                    // stop_armed=false deja que el armador de stops (mas abajo)
                                    // RE-ARME el remanente del fill parcial. Cancelar sin re-armar
                                    // dejaria desnuda la parte que no se cierra.
                                    zz.stop_armed = false;
                                    zz.stop_confirmed = false;
                                    ledger.note("cmd close: " + oc.msg);
                                    std::fprintf(stderr, "[cmd] %s\n", oc.msg.c_str());
                                }
                            }
                            int oid = tws.next_order_id();
                            if (!tws.place_limit(cc, side, cqty, lim, oid, "OE:CLOSE", close_session)) {
                                // La prevalidación de arriba y ésta usan la misma función pura.
                                // Si aun así difieren, no afirmar que el close fue colocado.
                                ledger.note("cmd close fallo local inesperado " + csym);
                                continue;
                            }
                            chase_track(oid, csym, cc, side, lim, now_s, "CLOSE");
                            ledger.note("cmd close " + csym + " " + cside + " " + std::to_string(cqty) + " @ " + std::to_string(lim));
                        } else if (act == "open") {
                            // quick-order humano (un toque en el cockpit): abrir YA.
                            // SOLO BUY abre; SELL viaja como "close" reduce-only.
                            std::string qsym = c.s("sym", ""), qright = c.s("right", ""),
                                        qexp = c.s("exp", ""), qside = c.s("side", "");
                            double qstrike = c.n("strike", 0), qlimit = c.n("limit", 0);
                            int qqty = (int)c.n("qty", 0);
                            if (qside != "buy") {
                                ledger.note("cmd open RECHAZADO: solo BUY abre (SELL = close) " + qsym);
                                continue;
                            }
                            bool q_opt = (qstrike > 0 && (qright == "C" || qright == "P"));
                            if (qsym.empty() || qqty <= 0 || qlimit <= 0 || (q_opt && qexp.empty())) {
                                ledger.note("cmd open inválido " + qsym); continue;
                            }
                            const oe::PosKey qpk = q_opt
                                ? oe::pos_key_option(qsym, qexp, qstrike, qright)
                                : oe::pos_key_stock(qsym);
                            const oe::EntrySideDecision qok =
                                oe::decide_entry_side(tws.positions(), qpk, qqty, 'B');
                            if (!qok.ok) {
                                ledger.note("cmd open RECHAZADO " + qsym + ": " + qok.reason);
                                continue;
                            }
                            if (q_opt) {
                                // mismo gate que las zonas: cadena fresca, spread, OI, prima<=budget
                                Chain qch = load_chain(cfg.repo + "/data/opt_chain_" + lower(qsym) + ".txt");
                                Gate qg = run_gate(qch, qright, qexp, qstrike, 'B',
                                                   cfg.budget, now_s, /*require_exact_strike=*/true);
                                if (!qg.go) {
                                    std::string w; for (auto& s : qg.why) { if (!w.empty()) w += "; "; w += s; }
                                    ledger.note("cmd open opt VETADO " + qsym + ": " + w);
                                    std::fprintf(stderr, "[cmd] open VETADO %s: %s\n", qsym.c_str(), w.c_str());
                                    continue;
                                }
                                if (qg.limit < qlimit) qlimit = qg.limit;   // jamás peor que el fresco
                            }
                            const double q_cost = q_opt ? qqty * qlimit * 100.0 : qqty * qlimit;
                            const double q_cap  = q_opt ? (cfg.max_order > 0 ? cfg.max_order : cfg.budget)
                                                        : cfg.stock_budget;
                            if (q_cost > q_cap) {
                                char b[160];
                                std::snprintf(b, sizeof b, "cmd open VETADO %s: $%.0f > tope $%.0f",
                                              qsym.c_str(), q_cost, q_cap);
                                ledger.note(b); std::fprintf(stderr, "[cmd] %s\n", b);
                                continue;
                            }
                            const std::string qkey = "cmd:" + qsym + ":" + std::to_string(now_ms());
                            if (!expo.reserve(qkey, q_cost)) {
                                char b[160];
                                std::snprintf(b, sizeof b, "cmd open VETADO %s: tope AGREGADO $%.0f + $%.0f > $%.0f",
                                              qsym.c_str(), expo.total(), q_cost, expo.cap);
                                ledger.note(b); std::fprintf(stderr, "[cmd] %s\n", b);
                                continue;
                            }
                            if (!armed_live(cfg.arm_flag, arm_file)) {
                                expo.release(qkey);
                                char b[192];
                                std::snprintf(b, sizeof b, "cmd open DRY (sin doble llave) %s BUY %d @ %.2f",
                                              qsym.c_str(), qqty, qlimit);
                                ledger.note(b); std::fprintf(stderr, "[cmd] %s\n", b);
                                continue;
                            }
                            Contract qc = q_opt ? make_option(qsym, qexp, qstrike, qright)
                                                : make_stock(qsym);
                            const oe::OrderSession q_sess = q_opt ? oe::OrderSession::RTH_ONLY
                                                                  : oe::OrderSession::OVERNIGHT_AND_DAY;
                            oe::PreflightReport qpf;
                            if (!tws.preflight_limit(qc, 'B', qqty, qlimit, "OE:WHATIF:OPEN",
                                                     q_sess, qpf)) {
                                expo.release(qkey);
                                ledger.note("cmd open WHAT-IF RECHAZADO " + qsym + ": " + qpf.warning);
                                std::fprintf(stderr, "[cmd] open WHAT-IF RECHAZADO %s: %s\n",
                                             qsym.c_str(), qpf.warning.c_str());
                                continue;
                            }
                            int qoid = tws.next_order_id();
                            if (!tws.place_limit(qc, 'B', qqty, qlimit, qoid, "OE:OPEN", q_sess)) {
                                expo.release(qkey);
                                ledger.note("cmd open fallo local " + qsym);
                                continue;
                            }
                            open_expo[qoid] = qkey;
                            char b[192];
                            std::snprintf(b, sizeof b, "cmd open %s BUY %d @ %.2f id=%d ($%.0f)",
                                          qsym.c_str(), qqty, qlimit, qoid, q_cost);
                            ledger.note(b); std::fprintf(stderr, "[cmd] %s\n", b);
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
                        // caza de bugs 2026-07-28: side/kind ausentes en AMBOS (JSON entrante y
                        // estado previo) defaulteaban en silencio a "buy"/"call" -- un JSON parcial
                        // (escritura no atomica del chart, ya arreglada en zones_save(), o un bug
                        // futuro de UI) podia comprar una CALL sin que nadie la pidiera. Mismo
                        // patron que "cmd close" (linea 610-617): sin dato real, se RECHAZA -- se
                        // trata la zona como ausente este ciclo (reutiliza el camino ya probado de
                        // "zona desaparecida", linea 764+: si no estaba viva no hace nada; si SI
                        // estaba viva, cancela lo que corresponda sin dejar nada huerfano).
                        std::string in_side = o.s("side", ""), in_kind = o.s("kind", "");
                        if ((in_side.empty() && z.side.empty()) || (in_kind.empty() && z.kind.empty())) {
                            // z.present = false a proposito (el default del struct es true para
                            // una entrada NUEVA en zmap): fuerza el MISMO camino ya probado que
                            // "zona desaparecida" (linea 764+): si nunca llego a colocar nada, no
                            // hace nada; si YA tenia una posicion real abierta, protege sin dejarla
                            // huerfana. Nunca queda a medio inicializar con side/kind vacios.
                            z.present = false;
                            std::fprintf(stderr, "[%s] zona %s SIN side/kind (JSON incompleto) -- rechazada este ciclo\n",
                                         sym.c_str(), id.c_str());
                            ledger.note("zona rechazada sin side/kind: " + sym + " " + id);
                            continue;
                        }
                        z.id = id; z.present = true;
                        z.price = o.n("price", z.price);
                        z.side = in_side.empty() ? z.side : in_side;
                        z.kind = in_kind.empty() ? z.kind : in_kind;
                        z.exp = o.s("exp", z.exp);
                        z.instrument = o.s("instrument", z.instrument.empty() ? "opt" : z.instrument);
                        z.qty = (int)o.n("qty", z.qty ? z.qty : 1);
                        z.exec = o.flag("exec", false);
                        z.armed_date = o.s("armed_date", z.armed_date);
                        z.confirm_id = o.s("confirm_id", z.confirm_id);
                        z.confirmed_at_ms = (long long)o.n("confirmed_at", (double)z.confirmed_at_ms);
                        z.locked_strike = o.n("locked_strike", z.locked_strike);
                        z.locked_right = o.s("locked_right", z.locked_right);
                        z.locked_exp = o.s("locked_exp", z.locked_exp);
                        z.locked_limit = o.n("locked_limit", z.locked_limit);
                        z.overnight_gap_ack = o.flag("overnight_gap_ack", false);
                        if (const JVal* st = o.child("stop")) {
                            z.stop_on = st->flag("on", false);
                            z.stop_px = st->n("px", z.stop_px);
                            // La degradación a watch-local es PEGAJOSA: si el broker ya
                            // rechazó el stop nativo 3 veces, la relectura del JSON no
                            // debe devolverlo a "native" y reabrir el bucle de reintentos.
                            if (!z.stop_degraded) z.stop_native = st->flag("native", true);
                        }
                    }
                }
            }
            // zonas que desaparecieron: cancelar lo propio y marcar terminal
            for (auto& [k, z] : zmap) {
                if (!z.present && (z.entry_id >= 0 || z.stop_id >= 0) &&
                    z.st != ZoneRT::DONE) {
                    // Cancelar la ENTRADA en vuelo siempre (no debe quedar residual).
                    // Zona borrada SIN llenar: la entrada se cancela -> el desembolso
                    // reservado nunca ocurrio, se devuelve al bolsillo agregado. Si SI
                    // se lleno, la posicion sigue abierta y el dinero sigue comprometido:
                    // ahi NO se libera (liberar dejaria sitio para gastar dos veces).
                    if (z.entry_id >= 0 && z.st != ZoneRT::FILLED) {
                        tws.cancel(z.entry_id);
                        expo.release(oe::exposure_key(sym, z.id));
                    }
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
            double spot = 0; long long spot_ep = 0;
            if (!last_close(cfg.repo + "/data/bars_" + lo + "_ibkr.txt", spot, &spot_ep)) continue;
            // FRESCURA DEL SPOT (fix 2026-07-24): antes se disparaban entradas con el
            // ultimo precio conocido aunque el feed llevara horas muerto.
            if (spot_ep > 0 && (double)(now_s - spot_ep) > MAX_AGE_S) {
                static std::map<std::string,long long> warned;
                if (warned[sym] != spot_ep) { warned[sym] = spot_ep;
                    std::fprintf(stderr, "[%s] barras RANCIAS (%llds) — no disparo entradas\n",
                                 sym.c_str(), (long long)(now_s - spot_ep)); }
                continue;
            }

            // 3) cadena para el gate / límite
            Chain ch = load_chain(cfg.repo + "/data/opt_chain_" + lo + ".txt");

            for (auto& [k, z] : zmap) {
                if (!z.present) continue;

                // ---- detección de PRINT de la entrada (sólo exec:true) ----
                if (z.st == ZoneRT::PLACED && z.exec) {
                    if (!z.have_prev) { z.have_prev = true; z.prev_spot = spot; z.approach_sign = sgn(spot - z.price); }
                    bool cr = crossed(z.approach_sign, spot, z.price);
                    // PRINT O NADA (fix 2026-07-24): antes esto contaba ITERACIONES del
                    // bucle (~2s), no barras: un unico print sostenido disparaba a las dos
                    // vueltas. Ahora solo cuenta cuando llega una BARRA NUEVA (epoch
                    // distinto), que es lo que dice la doctrina: 2 lecturas cruzando.
                    // advance_cross_counter (guards.h #11) es la MISMA funcion que usa la
                    // rama del stop watch-local mas abajo -- una sola definicion probada.
                    advance_cross_counter(z.cross_cnt, z.last_cross_ep, cr, spot_ep);
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
                    const oe::HumanConfirmationDecision hc = oe::validate_human_confirmation(
                        z.armed_date, oe::today_date(), z.confirm_id,
                        z.confirmed_at_ms, now_ms());
                    if (!hc.ok) {
                        z.st = ZoneRT::VETOED;
                        write_state(state_dir, sym, z, "\"veto\":\"" + json_escape(hc.reason) + "\"");
                        ledger.note("VETOED " + sym + " " + z.id + ": " + hc.reason);
                        std::fprintf(stderr, "[%s] zona %s VETOED: %s\n",
                                     sym.c_str(), z.id.c_str(), hc.reason.c_str());
                        continue;
                    }
                    char side = (z.side == "buy") ? 'B' : 'S';

                    // ===== ACCIONES (activos, 24/5 con horario extendido) =====
                    if (z.instrument == "stk") {
                        if (!z.overnight_gap_ack) {
                            z.st = ZoneRT::VETOED;
                            write_state(state_dir, sym, z,
                                        "\"veto\":\"falta ack de hueco de stop overnight\"");
                            ledger.note("VETOED " + sym + " " + z.id +
                                        ": no overnight stop-gap ack");
                            continue;
                        }
                        int qty = z.qty > 0 ? z.qty : 1;
                        // decide_stock_entry (guards.h #12): mismo veto de notional de
                        // siempre, pero medido al LIMITE que de verdad se paga (no al
                        // spot) y rechazando el limite que se redondea a 0.00.
                        oe::StockEntry se = oe::decide_stock_entry(spot, qty, cfg.stock_budget, side);
                        if (!se.ok) {
                            // spot ausente es TRANSITORIO (el bridge refresca): esperar, no
                            // latchear VETOED. El resto son veredictos firmes.
                            if (se.reason.rfind("spot", 0) == 0) {
                                write_state(state_dir, sym, z, "\"wait\":\"" + json_escape(se.reason) + "\"");
                                continue;
                            }
                            z.st = ZoneRT::VETOED;
                            write_state(state_dir, sym, z, "\"veto\":\"" + json_escape(se.reason) + "\"");
                            ledger.note("VETOED " + sym + " " + z.id + ": " + se.reason);
                            std::fprintf(stderr, "[%s] zona %s VETOED acciones: %s\n", sym.c_str(), z.id.c_str(), se.reason.c_str());
                            continue;
                        }
                        const oe::EntrySideDecision side_ok = oe::decide_entry_side(
                            tws.positions(), oe::pos_key_stock(sym), qty, side);
                        if (!side_ok.ok) {
                            if (side == 'S' && !tws.positions().known()) {
                                write_state(state_dir, sym, z,
                                            "\"wait\":\"broker positions refresh pending\"");
                                continue;
                            }
                            z.st = ZoneRT::VETOED;
                            write_state(state_dir, sym, z,
                                        "\"veto\":\"" + json_escape(side_ok.reason) + "\"");
                            ledger.note("VETOED " + sym + " " + z.id + ": " + side_ok.reason);
                            continue;
                        }
                        const double lim = se.limit;
                        if (!(z.locked_limit > 0) ||
                            std::fabs(z.locked_limit - lim) > 0.005) {
                            z.st = ZoneRT::VETOED;
                            write_state(state_dir, sym, z,
                                        "\"veto\":\"límite cambió desde confirmación humana\"");
                            ledger.note("VETOED " + sym + " " + z.id +
                                        ": stock limit changed after review");
                            continue;
                        }
                        // TOPE AGREGADO (#1/#2): la suma de TODAS las zonas vivas. Se
                        // reserva ANTES de colocar; si no cabe, la zona se VETA aqui —
                        // no al ejecutar, cuando ya seria dinero fuera.
                        if (!expo.reserve(oe::exposure_key(sym, z.id), se.notional)) {
                            z.st = ZoneRT::VETOED;
                            char b[160];
                            std::snprintf(b, sizeof b, "tope AGREGADO: $%.0f + $%.0f > cap cuenta $%.0f",
                                          expo.total(), se.notional, expo.cap);
                            write_state(state_dir, sym, z, std::string("\"veto\":\"") + b + "\"");
                            ledger.note(std::string("VETOED ") + sym + " " + z.id + ": " + b);
                            std::fprintf(stderr, "[%s] zona %s VETOED acciones: %s\n", sym.c_str(), z.id.c_str(), b);
                            continue;
                        }
                        Contract c = make_stock(sym);
                        z.entry_c = c; z.entry_delta = 0; z.entry_side = side;
                        bool armed = armed_live(cfg.arm_flag, arm_file);
                        if (!armed) {
                            char b[224];
                            std::snprintf(b, sizeof b, "DRY colocaría %c %d acc %s @ %.2f (notional $%.0f)",
                                          side, qty, sym.c_str(), lim, se.notional);
                            ledger.note(std::string(b));
                            write_state(state_dir, sym, z, std::string("\"dry\":\"") + json_escape(b) + "\"");
                            std::fprintf(stderr, "[%s] zona %s %s  (sin doble llave)\n", sym.c_str(), z.id.c_str(), b);
                            expo.release(oe::exposure_key(sym, z.id));   // DRY no gasta: devolver el sitio
                            z.st = ZoneRT::DONE; continue;
                        }
                        oe::PreflightReport pf;
                        if (!tws.preflight_limit(c, side, qty, z.locked_limit, "OE:WHATIF:" + z.id,
                                                 oe::OrderSession::OVERNIGHT_AND_DAY, pf)) {
                            expo.release(oe::exposure_key(sym, z.id));
                            z.st = ZoneRT::VETOED;
                            write_state(state_dir, sym, z,
                                        "\"veto\":\"IBKR what-if: " + json_escape(pf.warning) + "\"");
                            continue;
                        }
                        int oid = tws.next_order_id();
                        if (!tws.place_limit(c, side, qty, z.locked_limit, oid, "OE:" + z.id,
                                             oe::OrderSession::OVERNIGHT_AND_DAY)) {
                            expo.release(oe::exposure_key(sym, z.id));
                            z.st = ZoneRT::VETOED;
                            write_state(state_dir, sym, z,
                                        "\"veto\":\"IBKR overnight no soportado por contrato/servidor\"");
                            continue;
                        }
                        z.entry_id = oid; oid2zone[oid] = {sym, z.id};
                        z.st = ZoneRT::SENT;
                        write_state(state_dir, sym, z, "\"instrument\":\"stk\",\"order_id\":" + std::to_string(oid) + ",\"limit\":" + std::to_string(lim));
                        continue;
                    }

                    // ===== OPCIONES =====
                    std::string right = (lower(z.kind)[0] == 'c') ? "C" : "P";
                    // Execute the exact contract the human reviewed. A fresh quote may
                    // improve, but a nearby strike must never be silently substituted.
                    Gate g = run_gate(ch, right, z.locked_exp, z.locked_strike,
                                      side, cfg.budget, now_s,
                                      /*require_exact_strike=*/true);
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
                    const bool price_within_reviewed_cap =
                        side == 'B' ? g.limit <= z.locked_limit + 0.005
                                    : g.limit + 0.005 >= z.locked_limit;
                    if (!(z.locked_strike > 0) || !(z.locked_limit > 0) ||
                        z.locked_right != right || z.locked_exp != g.exp ||
                        std::fabs(z.locked_strike - g.strike) > 1e-9 ||
                        !price_within_reviewed_cap) {
                        z.st = ZoneRT::VETOED;
                        write_state(state_dir, sym, z,
                                    "\"veto\":\"contrato/precio excede confirmacion humana\"");
                        ledger.note("VETOED " + sym + " " + z.id +
                                    ": contrato cambió o precio empeoró desde confirmación");
                        continue;
                    }
                    int qty = z.qty > 0 ? z.qty : std::max(1, (int)(cfg.budget / g.premium));
                    const oe::PosKey opt_key = oe::pos_key_option(sym, g.exp, g.strike, right);
                    const oe::EntrySideDecision side_ok = oe::decide_entry_side(
                        tws.positions(), opt_key, qty, side);
                    if (!side_ok.ok) {
                        if (side == 'S' && !tws.positions().known()) {
                            write_state(state_dir, sym, z,
                                        "\"wait\":\"broker positions refresh pending\"");
                            continue;
                        }
                        z.st = ZoneRT::VETOED;
                        write_state(state_dir, sym, z,
                                    "\"veto\":\"" + json_escape(side_ok.reason) + "\"");
                        ledger.note("VETOED " + sym + " " + z.id + ": " + side_ok.reason);
                        continue;
                    }
                    // TOPE POR ORDEN (fix 2026-07-24): run_gate() solo valida la prima de UN
                    // contrato (:202). Con z.qty del JSON de zona (que viene de un <input> del
                    // chart sin máximo) el desembolso real era qty*prima, múltiplos del tope.
                    // Las acciones ya tenían este control (:626); las opciones no. Mismo patrón.
                    double desembolso = qty * g.premium;
                    if (desembolso > cfg.max_order) {
                        z.st = ZoneRT::VETOED;
                        char b[128];
                        std::snprintf(b, sizeof b, "desembolso $%.0f (%dx $%.0f) > tope orden $%.0f",
                                      desembolso, qty, g.premium, cfg.max_order);
                        write_state(state_dir, sym, z, std::string("\"veto\":\"") + b + "\"");
                        ledger.note(std::string("VETOED ") + sym + " " + z.id + ": " + b);
                        std::fprintf(stderr, "[%s] zona %s VETOED opciones: %s\n",
                                     sym.c_str(), z.id.c_str(), b);
                        continue;
                    }
                    // TOPE AGREGADO (#1/#2): el tope de arriba es POR ORDEN; este mira la
                    // SUMA de todas las zonas vivas de todos los simbolos. Se reserva
                    // ANTES de colocar y se libera si la zona muere sin posicion.
                    if (!expo.reserve(oe::exposure_key(sym, z.id), desembolso)) {
                        z.st = ZoneRT::VETOED;
                        char b[160];
                        std::snprintf(b, sizeof b, "tope AGREGADO: $%.0f + $%.0f > cap cuenta $%.0f",
                                      expo.total(), desembolso, expo.cap);
                        write_state(state_dir, sym, z, std::string("\"veto\":\"") + b + "\"");
                        ledger.note(std::string("VETOED ") + sym + " " + z.id + ": " + b);
                        std::fprintf(stderr, "[%s] zona %s VETOED opciones: %s\n",
                                     sym.c_str(), z.id.c_str(), b);
                        continue;
                    }
                    Contract c = make_option(sym, g.exp, g.strike, right);
                    z.entry_c = c; z.entry_delta = g.delta; z.entry_iv = g.iv; z.entry_side = side;
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
                        expo.release(oe::exposure_key(sym, z.id));   // DRY no gasta: devolver el sitio
                        z.st = ZoneRT::DONE;    // DRY: no re-disparar en bucle
                        continue;
                    }
                    oe::PreflightReport pf;
                    if (!tws.preflight_limit(c, side, qty, z.locked_limit, "OE:WHATIF:" + z.id,
                                             oe::OrderSession::RTH_ONLY, pf)) {
                        expo.release(oe::exposure_key(sym, z.id));
                        z.st = ZoneRT::VETOED;
                        write_state(state_dir, sym, z,
                                    "\"veto\":\"IBKR what-if: " + json_escape(pf.warning) + "\"");
                        continue;
                    }
                    int oid = tws.next_order_id();
                    if (!tws.place_limit(c, side, qty, z.locked_limit, oid, "OE:" + z.id)) {
                        expo.release(oe::exposure_key(sym, z.id));
                        z.st = ZoneRT::VETOED;
                        write_state(state_dir, sym, z,
                                    "\"veto\":\"orden de opción no soportada localmente\"");
                        continue;
                    }
                    z.entry_id = oid; oid2zone[oid] = {sym, z.id};
                    z.st = ZoneRT::SENT;
                    write_state(state_dir, sym, z, "\"order_id\":" + std::to_string(oid) + ",\"limit\":" + std::to_string(z.locked_limit));
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
                            // opciones: mapear el nivel del SUBYACENTE a precio de la OPCIÓN vía
                            // delta. option_stop_trigger (guards.h #10) es la version CORREGIDA:
                            // antes `fabs(z.entry_delta) > 1e-6` no distinguia "no se" (iv/delta
                            // en -1.0, el centinela que escribe opt_chain_cache.py fuera de RTH,
                            // medido 100% de las filas 2026-07-25) de "delta real". -1.0000 tiene
                            // magnitud > 1e-6 y pasaba como delta de un put profundo ITM,
                            // invirtiendo el mapeo. option_stop_trigger mira z.entry_iv (SIEMPRE
                            // acompaña a un delta real) y descarta el par entero si es el
                            // centinela, cayendo al fallback declarado -- nunca al numero
                            // inventado. clamp_option_stop (#9) sigue aplicando el clamp
                            // simetrico de cordura en ambos lados.
                            stop_trigger = option_stop_trigger(z.fill_px, z.entry_iv, z.entry_delta,
                                                               z.stop_px, z.price, close_side);
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
                        // GUARDA #5 (decide_stop_failure): un STOP nativo que el broker no
                        // confirma es una posición DESNUDA. Antes esto degradaba a
                        // watch-local en silencio, y si tampoco había dato del subyacente
                        // para vigilar local nadie protegía nada — te crees protegido y no
                        // lo estás. Ahora los tres desenlaces GRITAN, y el tercero CIERRA.
                        // El tope de 3 re-armes se conserva: sin él, un STOP rechazado sin
                        // orderStatus hacía girar el watchdog para siempre (medido en el
                        // soak: 24 cancel/replace por stop en 80s), churn que viola el
                        // pacing y deja un hueco desprotegido en cada cancel/re-place.
                        const bool local_ok = (spot > 0 && spot_ep > 0);
                        const oe::NakedDecision nd = oe::decide_stop_failure(z.stop_retries, 3, local_ok);
                        if (nd.shout) {
                            ledger.note("PROTECCION CAIDA " + sym + " " + z.id + ": " + nd.msg);
                            std::fprintf(stderr, "[%s] ⚠ DANGER zona %s: %s\n", sym.c_str(), z.id.c_str(), nd.msg.c_str());
                            shout_naked_stop(state_dir, sym, z.id, nd.msg);
                        }
                        if (nd.action == oe::NakedAction::RETRY) {
                            ++z.stop_retries;
                            if (z.stop_id >= 0) tws.cancel(z.stop_id);
                            z.stop_armed = false; z.stop_id = -1; z.stop_wait = 0;
                        } else if (nd.action == oe::NakedAction::DEGRADE_LOCAL) {
                            z.stop_native = false; z.stop_degraded = true;   // watch-local PEGAJOSO
                            z.stop_armed = false; z.stop_id = -1;            // el MOTOR es la protección
                            z.s_have_prev = false; z.stop_wait = 0;
                        } else {   // EMERGENCY_CLOSE: sin stop nativo Y sin dato para vigilar
                            z.stop_native = false; z.stop_degraded = true;
                            z.stop_armed = false; z.stop_id = -1; z.stop_wait = 0;
                            if (z.close_id < 0 && !frozen) {
                                char close_side = (z.entry_side == 'B') ? 'S' : 'B';
                                int cq = z.filled_qty > 0 ? (int)z.filled_qty : (z.qty > 0 ? z.qty : 1);
                                double lim = 0;
                                if (z.entry_c.secType == "OPT") {
                                    Gate gx = run_gate(ch, z.entry_c.right, z.entry_c.lastTradeDateOrContractMonth,
                                                       z.entry_c.strike, close_side, 1e9, now_s, true);
                                    lim = gx.limit;
                                }
                                // Sin precio de cadena NO se remata a 0.01 (regalo): se
                                // queda gritando cada ciclo hasta poder cerrar de verdad.
                                if (lim > 0) {
                                    int oid = tws.next_order_id();
                                    z.close_id = oid; oid2zone[oid] = {sym, z.id};
                                    tws.place_limit(z.entry_c, close_side, cq, lim, oid, "OE:" + z.id + ":EMERG");
                                    chase_track(oid, sym, z.entry_c, close_side, lim, now_s, "EMERG");
                                    ledger.note("CIERRE DE EMERGENCIA " + sym + " " + z.id + " @ " + std::to_string(lim));
                                    std::fprintf(stderr, "[%s] zona %s CIERRE DE EMERGENCIA @ %.2f\n", sym.c_str(), z.id.c_str(), lim);
                                } else {
                                    ledger.note("CIERRE DE EMERGENCIA IMPOSIBLE (sin precio) " + sym + " " + z.id);
                                    std::fprintf(stderr, "[%s] ⚠ zona %s: cierre de emergencia SIN PRECIO — sigo gritando\n",
                                                 sym.c_str(), z.id.c_str());
                                }
                            }
                        }
                    }
                }

                // ---- watch-local del stop: PRINT del stop.px -> cerrar marketable ----
                if (z.st == ZoneRT::FILLED && z.stop_on && !z.stop_native && z.close_id < 0) {
                    if (!z.s_have_prev) { z.s_have_prev = true; z.s_prev = spot; z.s_sign = sgn(spot - z.stop_px); }
                    bool cr = crossed(z.s_sign, spot, z.stop_px);
                    // DEFECTO 4 (2026-07-25): esta rama contaba ITERACIONES del bucle
                    // (~2s cada una), no barras nuevas -- el fix de :779 para la ENTRADA
                    // (2026-07-24) nunca se copio aqui. Con `cr` sostenido por la MISMA
                    // barra, `z.s_cnt = cr ? z.s_cnt+1 : 0` llegaba a 2 en ~4s y disparaba
                    // un cierre marketable con UNA sola lectura real, no las 2 que exige
                    // print-o-nada. advance_cross_counter (guards.h #11) es la misma
                    // funcion ya usada en la entrada: solo avanza con epoch de barra nuevo.
                    advance_cross_counter(z.s_cnt, z.s_last_cross_ep, cr, spot_ep);
                    z.s_prev = spot;
                    if (z.s_cnt >= 2 && !frozen) {
                        char close_side = (z.entry_side == 'B') ? 'S' : 'B';
                        std::string right = z.entry_c.right;
                        // require_exact_strike=true (defecto 2): el contrato ya se conoce
                        // con certeza (z.entry_c es el que de verdad se lleno) -- nearest_row
                        // sin tope de distancia podia preciar sobre un contrato VECINO si el
                        // exacto faltaba en la cadena. exact_row exige right+exp+strike
                        // identicos o el gate falla limpio (espera cadena, no adivina).
                        Gate g = run_gate(ch, right, z.entry_c.lastTradeDateOrContractMonth, z.entry_c.strike, close_side, 1e9, now_s, /*require_exact_strike=*/true);
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
                        chase_track(oid, sym, z.entry_c, close_side, lim, now_s, "STOP-LOCAL");
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
