// replay.cpp — EL GATEWAY IBKR FALSO: la flota entera corriendo sobre historia real.
//
// PREGUNTA DE YUNIOR (2026-07-25): "¿tenemos un gateway IBKR falso por websocket para
// backtestear todo, con datos de Polygon y del chart, y ver la UI moviendose en tiempo
// real?" — Habia PIEZAS (scalper/sim_feed.py para el scalper, chart_bridge --mock solo 5m)
// pero no el arnes unico. Esto lo es.
//
// LA IDEA, EN UNA LINEA: no se simula la flota; se simula EL DISCO. La flota entera
// (compass, bots, chart_bridge, scalper) no habla con TWS: lee data/bars_<sym>_ibkr.txt,
// data/nbbo_<sym>.txt y charts/data/levels_<sym>.json. Si otro proceso escribe esos ficheros
// en un SANDBOX con el reloj virtual correcto, los MISMOS binarios de produccion corren
// contra historia sin una sola linea de codigo condicional dentro de ellos.
//   ./compass usa rutas RELATIVAS -> basta lanzarlo con cwd = sandbox. Cero cambios en compass.
//
// POR QUE ESTO ES LO QUE FALTABA (y no un backtest mas)
// ----------------------------------------------------
// El miedo literal de Yunior: "si la flecha apunta con retraso de 2 segundos y compramos call
// en el retroceso cuando esta en su punto maximo, no bueno". Eso NO se puede medir con un
// backtest vectorizado: hay que reproducir el pipeline con su reloj y cronometrar CUANDO
// aparece el veredicto respecto a CUANDO existia la condicion. Dos retrasos distintos:
//   (1) MECANICO  = del append de la barra al JSON de la brujula en disco (--probe).
//   (2) ESTRUCTURAL = de la vela del extremo REAL a la vela en que la flecha gira (--walk).
// El (2) es el que cuesta dinero: una flecha que gira 3 velas DESPUES del suelo compra el
// retroceso ya hecho.
//
// SIN LOOK-AHEAD (el invariante que hace que todo lo demas valga algo)
// -------------------------------------------------------------------
// Una barra de 1 minuto con timestamp T cubre [T, T+60) y SOLO se conoce en T+60. Por eso el
// feeder no la escribe hasta el instante virtual T+60 (igual que ibkr_bar_bridge, que jamas
// emite la vela en curso). Invariante verificable desde fuera, sin creer nada de este codigo:
//     en el instante virtual V, todas las barras del sandbox cumplen ts + 60 <= V.
// (tests/test_replay.py lo comprueba muestreando clock.txt y el fichero de barras a la vez.)
// HONESTIDAD: los ticks sub-minuto del NBBO se construyen por puente browniano DENTRO del
// rango O/H/L/C de la barra en curso, asi que la ruta intra-minuto conoce el H/L de ese
// minuto. Es exactamente la licencia que ya se documento en scalper/sim_feed.py y no puede
// filtrar nada MAS ALLA del minuto actual. La brujula y los bots de barras no la usan.
//
// SEÑAL-SOLAMENTE: no ordena, no toca trades.db mas que para LEER (SQLITE_OPEN_READONLY),
// y jamas escribe fuera del sandbox (guardia dura en sandbox_guard()).
//
// FUENTE: trades.db tabla poly_bars (1m, 30 simbolos, ts en MILISEGUNDOS).
//
//   compilar: ./scripts/build_replay.sh
//   uso:
//     ./replay --date 2026-07-23 --fleet --out /tmp/replay-0723 --speed 1
//     ./replay --date 2026-07-23 --syms qqq --out /tmp/rw --walk qqq        (medir retraso)
//     ./replay --date 2026-07-23 --syms qqq --out /tmp/rp --probe qqq --speed 5
#include <sqlite3.h>

#include <dirent.h>
#include <algorithm>
#include <cctype>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <numeric>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

// ------------------------------- constantes ---------------------------------
namespace K {
constexpr long BAR_S      = 60;      // barra base 1m: se conoce en t+60
constexpr int  WARM_BARS  = 780;     // igual que el tail de chart_bridge (13h de contexto)
constexpr double TICK_S   = 0.25;    // 250 ms por tick, paridad con sim_feed.py
constexpr double SPEED_HONEST = 5.0; // >5x distorsiona la mecanica de fills (sim_feed.py)
constexpr int  HYST_N     = 2;       // = compass.cpp K::HYST_N (para reproducir su histeresis)
constexpr int  LAG_WIN    = 15;      // ventana (velas) donde buscar el extremo real
constexpr int  MFE_H      = 15;      // horizonte (velas) de MFE/MAE tras el giro
}

static const char* S_REV = "REVERSION EN EXTREMO";

// ------------------------ JSON minimo (idiom del repo) ----------------------
// jstr SALTA blancos tras los dos puntos: json.dump() de Python escribe ": " y asi salen
// charts/data/levels_<sym>.json y data/compass_<sym>.json. Sin esto el valor se lee ausente.
static std::optional<double> jnum(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n')) ++p;
    if (p >= s.size() || s[p] == 'n' || s[p] == '"') return std::nullopt;
    try { return std::stod(std::string(s.substr(p, 32))); } catch (...) { return std::nullopt; }
}
static std::optional<std::string> jstr(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n')) ++p;
    if (p >= s.size() || s[p] != '"') return std::nullopt;
    ++p;
    auto e = s.find('"', p);
    if (e == std::string_view::npos) return std::nullopt;
    return std::string(s.substr(p, e - p));
}
static bool jbool(std::string_view s, std::string_view key, bool dflt) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return dflt;
    p += pat.size();
    while (p < s.size() && s[p] == ' ') ++p;
    if (s.compare(p, 4, "true") == 0) return true;
    if (s.compare(p, 5, "false") == 0) return false;
    return dflt;
}
static std::string slurp(const std::string& path) {
    std::ifstream f(path);
    if (!f) return {};
    std::ostringstream ss; ss << f.rdbuf();
    return ss.str();
}
static std::string jesc(const std::string& s) {
    std::string o; o.reserve(s.size() + 8);
    for (char c : s) { if (c == '"' || c == '\\') o += '\\'; o += c; }
    return o;
}

// ------------------------------- utilidades ---------------------------------
static void die(const std::string& msg) {
    fprintf(stderr, "[replay] ERROR: %s\n", msg.c_str());
    exit(2);
}
// escritura atomica tmp+rename (idiom de compass.cpp / opt_chain_cache)
static void write_atomic(const std::string& path, const std::string& body) {
    std::string tmp = path + ".tmp";
    FILE* f = fopen(tmp.c_str(), "w");
    if (!f) die("no puedo escribir " + tmp + ": " + strerror(errno));
    fwrite(body.data(), 1, body.size(), f);
    fclose(f);
    if (rename(tmp.c_str(), path.c_str()) != 0) die("rename " + path);
}
static void mkdirp(const std::string& p) {
    std::string cur;
    for (size_t i = 0; i <= p.size(); ++i) {
        if (i == p.size() || p[i] == '/') {
            if (!cur.empty() && cur != ".") mkdir(cur.c_str(), 0755);
        }
        if (i < p.size()) cur += p[i];
    }
}
static bool is_dir(const std::string& p) {
    struct stat st{};
    return stat(p.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
}
static double now_real() {   // CLOCK_REALTIME: comparable con los mtime de los ficheros
    struct timespec ts{};
    clock_gettime(CLOCK_REALTIME, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}
static std::optional<double> mtime_of(const std::string& p) {
    struct stat st{};
    if (stat(p.c_str(), &st) != 0) return std::nullopt;
#if defined(__APPLE__)
    return (double)st.st_mtimespec.tv_sec + (double)st.st_mtimespec.tv_nsec * 1e-9;
#else
    return (double)st.st_mtim.tv_sec + (double)st.st_mtim.tv_nsec * 1e-9;
#endif
}
static std::string upper(std::string s) { for (auto& c : s) c = (char)toupper(c); return s; }
static std::string lower(std::string s) { for (auto& c : s) c = (char)tolower(c); return s; }

// epoch LOCAL (la maquina esta en ET, igual que todo el repo: mktime/localtime)
static long epoch_of(const std::string& date, int hh, int mm) {
    struct tm tmv{};
    if (sscanf(date.c_str(), "%d-%d-%d", &tmv.tm_year, &tmv.tm_mon, &tmv.tm_mday) != 3)
        die("fecha invalida (YYYY-MM-DD): " + date);
    tmv.tm_year -= 1900; tmv.tm_mon -= 1;
    tmv.tm_hour = hh; tmv.tm_min = mm; tmv.tm_sec = 0; tmv.tm_isdst = -1;
    return (long)mktime(&tmv);
}
static void parse_hhmm(const std::string& s, int& hh, int& mm) {
    if (sscanf(s.c_str(), "%d:%d", &hh, &mm) != 2) die("hora invalida (HH:MM): " + s);
}
static std::string hhmm_str(long ep) {
    struct tm tmv{}; time_t t = (time_t)ep; localtime_r(&t, &tmv);
    char b[8]; snprintf(b, sizeof b, "%02d%02d", tmv.tm_hour, tmv.tm_min);
    return b;
}

// --------------------------- PRNG determinista ------------------------------
// splitmix64 + Box-Muller propios: std::mt19937 es portable pero std::normal_distribution
// NO lo es entre implementaciones. Determinismo = requisito (misma semilla, mismos bytes).
struct Rng {
    uint64_t s;
    bool has_spare = false;
    double spare = 0;
    explicit Rng(uint64_t seed) : s(seed ? seed : 0x9E3779B97F4A7C15ull) {}
    uint64_t next() {
        s += 0x9E3779B97F4A7C15ull;
        uint64_t z = s;
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
        return z ^ (z >> 31);
    }
    double uni() { return (double)(next() >> 11) * 0x1.0p-53; }
    double gauss() {
        if (has_spare) { has_spare = false; return spare; }
        double u1 = std::max(1e-12, uni()), u2 = uni();
        double r = std::sqrt(-2.0 * std::log(u1)), th = 6.283185307179586 * u2;
        spare = r * std::sin(th); has_spare = true;
        return r * std::cos(th);
    }
};
// semilla por simbolo: la salida de un simbolo NO depende de cuantos otros se replayan
static uint64_t sym_seed(uint64_t seed, const std::string& sym) {
    uint64_t h = 1469598103934665603ull ^ seed;
    for (char c : sym) { h ^= (uint64_t)(unsigned char)c; h *= 1099511628211ull; }
    return h;
}

// ------------------------------- modelo -------------------------------------
struct Bar { long t; double o, h, l, c, v; };

// puente browniano por la barra: O -> (H,L en el orden que sugiere el cierre) -> C.
// MISMO enfoque que scalper/sim_feed.py::bridge_ticks (no se reinventa distinto).
static std::vector<double> bridge_ticks(const Bar& b, int n, Rng& rng) {
    bool up_first = (rng.uni() > 0.3) ? (b.c >= b.o) : (b.c < b.o);
    double anchors[4] = {b.o, up_first ? b.h : b.l, up_first ? b.l : b.h, b.c};
    std::vector<double> out;
    out.reserve((size_t)n);
    int seg = std::max(1, n / 3);
    double rng_hl = std::fabs(b.h - b.l);
    for (int i = 0; i < 3; ++i) {
        double a = anchors[i], z = anchors[i + 1];
        for (int j = 0; j < seg; ++j) {
            double f = (double)(j + 1) / seg;
            double px = a + (z - a) * f + rng.gauss() * rng_hl * 0.05;
            out.push_back(std::min(std::max(px, b.l), b.h));   // JAMAS fuera del rango real
        }
    }
    if (out.empty()) out.push_back(b.c);
    if ((int)out.size() > n) out.resize((size_t)n);
    return out;
}

// ------------------------------ sqlite (RO) ---------------------------------
struct Db {
    sqlite3* h = nullptr;
    explicit Db(const std::string& path) {
        // READONLY: el arnes JAMAS escribe en trades.db (ley señal-solamente).
        if (sqlite3_open_v2(path.c_str(), &h, SQLITE_OPEN_READONLY, nullptr) != SQLITE_OK)
            die("no puedo abrir (RO) " + path + ": " + (h ? sqlite3_errmsg(h) : "?"));
    }
    ~Db() { if (h) sqlite3_close(h); }
};
static std::vector<Bar> db_bars(Db& db, const std::string& SYM, long t0, long t1) {
    static const char* Q =
        "SELECT ts,o,h,l,c,v FROM poly_bars WHERE sym=?1 AND ts>=?2 AND ts<?3 ORDER BY ts";
    sqlite3_stmt* st = nullptr;
    if (sqlite3_prepare_v2(db.h, Q, -1, &st, nullptr) != SQLITE_OK)
        die(std::string("prepare poly_bars: ") + sqlite3_errmsg(db.h));
    sqlite3_bind_text(st, 1, SYM.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_int64(st, 2, (sqlite3_int64)t0 * 1000);   // poly_bars.ts en MILISEGUNDOS
    sqlite3_bind_int64(st, 3, (sqlite3_int64)t1 * 1000);
    std::vector<Bar> out;
    while (sqlite3_step(st) == SQLITE_ROW) {
        Bar b{};
        b.t = (long)(sqlite3_column_int64(st, 0) / 1000);
        b.t -= b.t % K::BAR_S;
        b.o = sqlite3_column_double(st, 1); b.h = sqlite3_column_double(st, 2);
        b.l = sqlite3_column_double(st, 3); b.c = sqlite3_column_double(st, 4);
        b.v = sqlite3_column_double(st, 5);
        if (b.c > 0) out.push_back(b);
    }
    sqlite3_finalize(st);
    return out;
}

// -------------------------------- sandbox -----------------------------------
// GUARDIA: escribir sobre los data/*.txt reales contaminaria la flota VIVA (bots leyendo
// esos ficheros ahora mismo). Preferimos morir antes que tocarlos.
static void sandbox_guard(const std::string& out, const std::string& repo) {
    auto norm = [](std::string p) {
        while (p.size() > 1 && p.back() == '/') p.pop_back();
        char buf[4096];
        if (realpath(p.c_str(), buf)) return std::string(buf);
        return p;
    };
    std::string o = norm(out), r = norm(repo);
    for (const char* bad : {"", "/data", "/charts/data", "/charts", "/scripts"}) {
        if (o == r + bad) die("el sandbox NO puede ser " + o + " (contaminaria la flota viva)");
    }
    if (o == "/" || o == "/tmp") die("sandbox invalido: " + o);
    const std::string marker = o + "/.replay-sandbox";
    if (is_dir(o)) {
        struct stat st{};
        // si el directorio existe y NO lo creamos nosotros, exigimos que este vacio
        if (stat(marker.c_str(), &st) != 0) {
            std::string probe = o + "/data";
            if (is_dir(probe) || stat((o + "/trades.db").c_str(), &st) == 0)
                die("el directorio " + o + " ya tiene contenido y no es un sandbox de replay "
                    "(falta .replay-sandbox); elige otro --out");
        }
    }
    mkdirp(o + "/data/trading-signals");
    mkdirp(o + "/charts/data");
    write_atomic(marker, "replay sandbox — generado por scripts/replay.cpp\n");
}

// niveles: copia del mapa REAL con "spot" NEUTRALIZADO (si no, el spot de HOY manda sobre el
// cierre replayado y la brujula mira un precio que no existe en el replay). El mapa GEX
// historico NO es medible (memoria gex-gamma-walls-tooling) -> se dice, no se finge.
static bool levels_copy(const std::string& repo, const std::string& out, const std::string& lo) {
    std::string j = slurp(repo + "/charts/data/levels_" + lo + ".json");
    if (j.empty()) return false;
    const std::string from = "\"spot\":", to = "\"spot_replay_off\":";
    for (size_t p = j.find(from); p != std::string::npos; p = j.find(from, p + to.size()))
        j.replace(p, from.size(), to);
    j.insert(1, "\n \"replay_levels_src\": \"copia del mapa vivo, spot neutralizado\",");
    write_atomic(out + "/charts/data/levels_" + lo + ".json", j);
    return true;
}
// SPOT del mapa == spot replayado. En produccion chart_bridge recalcula levels_<sym>.json con
// el spot EN VIVO en cada frame; en el replay el mapa solo se regenera cuando llega un snapshot
// de cadena (cada ~5 min). Si no se refresca el spot, la brujula lee un precio de hasta 5 min
// de antigüedad (jnum(lv,"spot") MANDA sobre el cierre de la barra, compass.cpp:1080) y el
// retraso medido de la flecha seria un ARTEFACTO del arnes. Parche numerico barato: muros,
// flip y regimen siguen siendo los del snapshot (solo cambian con la cadena); el spot, fresco.
static void patch_levels_spot(const std::string& out, const std::string& lo, double px) {
    const std::string p = out + "/charts/data/levels_" + lo + ".json";
    std::string j = slurp(p);
    if (j.empty()) return;
    const std::string key = "\"spot\":";
    auto a = j.find(key);
    if (a == std::string::npos) return;
    size_t b = a + key.size();
    while (b < j.size() && (j[b] == ' ' || j[b] == '\t')) ++b;
    size_t e = b;
    while (e < j.size() && (isdigit((unsigned char)j[e]) || j[e] == '.' || j[e] == '-' ||
                            j[e] == 'e' || j[e] == '+')) ++e;
    if (e == b) return;                       // "spot": null -> no se toca (fail-quiet honesto)
    char num[32];
    snprintf(num, sizeof num, "%.4f", px);
    write_atomic(p, j.substr(0, b) + num + j.substr(e));
}

// niveles SINTETICOS de la sesion ANTERIOR (cero look-ahead: solo pasado). Permite medir el
// retraso de la flecha en CUALQUIER dia historico, no solo en aquellos con mapa GEX guardado.
static bool levels_synth(const std::string& out, const std::string& lo,
                         const std::vector<Bar>& prev, const std::string& regime) {
    if (prev.size() < 30) return false;
    double hi = prev[0].h, lo_p = prev[0].l, sum = 0;
    for (const auto& b : prev) { hi = std::max(hi, b.h); lo_p = std::min(lo_p, b.l); sum += b.c; }
    double poc = sum / (double)prev.size(), close = prev.back().c;
    char buf[768];
    snprintf(buf, sizeof buf,
             "{\n \"sym\": \"%s\",\n \"replay_levels_src\": \"sesion anterior (sin look-ahead)\",\n"
             " \"regime\": \"%s\",\n \"flip\": %.4f,\n \"em\": %.4f,\n"
             " \"put_wall\": %.4f,\n \"call_wall\": %.4f,\n \"abs_wall\": %.4f,\n"
             " \"poc_dom\": %.4f\n}\n",
             upper(lo).c_str(), regime.c_str(), close, (hi - lo_p) * 0.5,
             lo_p, hi, (close >= poc ? hi : lo_p), poc);
    write_atomic(out + "/charts/data/levels_" + lo + ".json", buf);
    return true;
}

// ------------------------- CADENAS DE OPCIONES -------------------------------
// El gateway TWS falso a nivel socket se CANCELO (Yunior 2026-07-25): un simulador de protocolo
// que se desvie del real da CONFIANZA FALSA, y simular el DISCO basta. Pero la mitad del valor
// de la flota son los muros/GEX, que salen de data/opt_chain_<sym>.txt (lo produce
// opt_chain_cache.py hablando con TWS). Sin cadenas no hay levels_<sym>.json y la brujula sale
// "SIN LECTURA": no habria nada que medir.
//
// LA FUENTE YA EXISTE EN DISCO: data/history/<fecha>/opt_chain_<sym>[_HHMM].txt, con el
// `epoch` en la cabecera. Se publica el snapshot MAS RECIENTE con epoch <= reloj virtual.
//
// EL NOMBRE DEL FICHERO NO MANDA, MANDA EL EPOCH: en data/history conviven TRES convenciones
// (opt_chain_qqq_09.txt horario, opt_chain_qqq_1325.txt de 5 min, y opt_chain_qqq.txt sin
// sufijo). Ordenar por nombre daria "1325" < "14" y publicaria fuera de orden. Se parsea la
// cabecera de cada fichero y se ordena por epoch: asi el invariante anti-look-ahead no depende
// de una convencion de nombres que ya cambio dos veces.
//
// LOS -1.00 SE PASAN TAL CUAL: fuera de RTH los snapshots traen bid/ask/iv/delta/gamma a -1.00.
// Eso NO es corrupcion, es la realidad del feed. Si un consumidor no distingue "sin dato" de
// "dato malo", ese bug queremos VERLO, no taparlo con una interpolacion.
struct Snap { long epoch = 0; std::string path; };

static std::vector<Snap> scan_chains(const std::string& dir, const std::string& lo) {
    std::vector<Snap> v;
    DIR* d = opendir(dir.c_str());
    if (!d) return v;
    const std::string pre = "opt_chain_" + lo;
    while (struct dirent* e = readdir(d)) {
        std::string n = e->d_name;
        if (n.rfind(pre, 0) != 0) continue;
        if (n.size() <= pre.size()) continue;
        // tras el prefijo solo vale '_' (sufijo horario) o '.' (sin sufijo): asi "mu" no
        // captura "msft"/"mus..." ni "wdc" a otro simbolo con el mismo comienzo.
        if (n[pre.size()] != '_' && n[pre.size()] != '.') continue;
        if (n.size() < 4 || n.compare(n.size() - 4, 4, ".txt") != 0) continue;
        std::string p = dir + "/" + n;
        std::ifstream f(p);
        std::string h;
        if (!std::getline(f, h)) continue;
        auto q = h.find("epoch ");
        if (q == std::string::npos) continue;                 // sin cabecera valida -> se ignora
        long ep = atol(h.c_str() + (long)q + 6);
        if (ep <= 0) continue;
        v.push_back({ep, p});
    }
    closedir(d);
    std::sort(v.begin(), v.end(), [](const Snap& a, const Snap& b) { return a.epoch < b.epoch; });
    // opt_chain_<sym>.txt suele ser copia del ultimo snapshot -> mismo epoch, se deduplica
    v.erase(std::unique(v.begin(), v.end(),
                        [](const Snap& a, const Snap& b) { return a.epoch == b.epoch; }),
            v.end());
    return v;
}

// --------------------------------- feed -------------------------------------
struct Feed {
    std::string lo, up;
    std::vector<Bar> bars;
    size_t pi = 0;                 // primera barra AUN no publicada (t+60 > reloj virtual)
    size_t cur = (size_t)-1;       // indice de la barra EN CURSO (para la ruta intra-minuto)
    std::vector<double> path;
    double last_px = 0, half_spread = 0.01;
    double last_close = 0;         // cierre de la ULTIMA barra publicada = spot del replay
    Rng rng{1};
    std::string bars_path, nbbo_path, tick_log, chain_path, chain_log;
    double pending_ns = 0;         // instante real del append de la barra pendiente (probe)
    long pending_bar = 0;
    double first_write = 0;        // 1er mtime del JSON de la brujula tras el append
    bool newbar = false;           // se publico barra nueva en este instante virtual
    std::vector<Snap> snaps;       // cadenas del dia ordenadas por epoch
    size_t si = 0;                 // primera cadena AUN no publicada
    long pub_epoch = 0;            // epoch de la cadena publicada ahora mismo (0 = ninguna)
};

// append de UNA barra ya CERRADA, formato exacto de ibkr_bar_bridge::emit
static void append_bar(Feed& f, const Bar& b) {
    char line[160];
    snprintf(line, sizeof line, "%ld %.4f %.4f %.4f %.4f %.0f\n", b.t, b.o, b.h, b.l, b.c, b.v);
    FILE* fp = fopen(f.bars_path.c_str(), "a");
    if (!fp) die("append " + f.bars_path);
    fputs(line, fp);
    fclose(fp);
    f.last_close = b.c;
}

// publica la cadena mas reciente con epoch <= v. Devuelve el epoch publicado, o 0 si no hay
// cadena nueva. NUNCA mira snaps[i].epoch > v: ahi esta el invariante.
static long publish_chain(Feed& f, double v) {
    size_t best = (size_t)-1;
    while (f.si < f.snaps.size() && (double)f.snaps[f.si].epoch <= v) { best = f.si; ++f.si; }
    if (best == (size_t)-1) return 0;
    std::string body = slurp(f.snaps[best].path);
    if (body.empty()) {
        fprintf(stderr, "[replay] AVISO: snapshot vacio %s (se ignora)\n",
                f.snaps[best].path.c_str());
        return 0;
    }
    write_atomic(f.chain_path, body);          // tmp+rename: el consumidor jamas ve media cadena
    f.pub_epoch = f.snaps[best].epoch;
    char b[512];
    snprintf(b, sizeof b, "{\"clock\":%.3f,\"chain_epoch\":%ld,\"src\":\"%s\"}\n", v,
             f.pub_epoch, jesc(f.snaps[best].path).c_str());
    FILE* g = fopen(f.chain_log.c_str(), "a");   // rastro auditable: el test lo verifica
    if (g) { fputs(b, g); fclose(g); }
    return f.pub_epoch;
}

// ------------------------- analisis del retraso -----------------------------
struct WalkRow { long ts; double close; std::string state, dir; int prob; double us; };

// reproduce la histeresis de compass.cpp sobre la secuencia CRUDA de estados. Un proceso
// ./compass persistente la lleva en memoria (g_hist); en --walk cada barra es un proceso
// nuevo (hist->has=false -> adopta al instante), asi que la aplicamos aqui: mismo resultado,
// y ademas explicito y auditable.
static void apply_hyst(const std::vector<WalkRow>& raw, std::vector<std::string>& st,
                       std::vector<std::string>& dr) {
    std::string state, cand; int n = 0; bool has = false;
    std::string dir_cur = "flat";
    for (const auto& r : raw) {
        const std::string& want = r.state;
        bool commit = false;
        if (!has || state == want) { has = true; state = want; cand = want; n = 0; commit = true; }
        else if (cand == want) {
            n += 1;
            if (n + 1 >= K::HYST_N) { state = want; cand = want; n = 0; commit = true; }
        } else { cand = want; n = 0; }
        if (commit) dir_cur = r.dir;
        st.push_back(state);
        dr.push_back(commit ? dir_cur : std::string("flat"));
    }
}
static double median(std::vector<double> v) {
    if (v.empty()) return 0;
    std::sort(v.begin(), v.end());
    size_t n = v.size();
    return n % 2 ? v[n / 2] : 0.5 * (v[n / 2 - 1] + v[n / 2]);
}
static double pctile(std::vector<double> v, double q) {
    if (v.empty()) return 0;
    std::sort(v.begin(), v.end());
    size_t i = (size_t)std::llround(q * (double)(v.size() - 1));
    return v[std::min(i, v.size() - 1)];
}

// ---------------------------------- main ------------------------------------
int main(int argc, char** argv) {
    std::string date, out, syms_arg, probe, walk, repo = ".", regime_synth, compass = "./compass";
    std::string start = "09:30", end = "16:00";
    std::string chains = "auto", levels = "auto", python, history;
    double speed = 1.0, tick = K::TICK_S;
    long warm = K::WARM_BARS, seed = 7;
    bool fleet = false, no_ticks = false, synth = false, quiet = false;

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto need = [&](const char* n) -> std::string {
            if (i + 1 >= argc) die(std::string("falta el valor de ") + n);
            return argv[++i];
        };
        if (a == "--date") date = need("--date");
        else if (a == "--out") out = need("--out");
        else if (a == "--syms") syms_arg = need("--syms");
        else if (a == "--fleet") fleet = true;
        else if (a == "--start") start = need("--start");
        else if (a == "--end") end = need("--end");
        else if (a == "--warm") warm = atol(need("--warm").c_str());
        else if (a == "--seed") seed = atol(need("--seed").c_str());
        else if (a == "--tick") tick = atof(need("--tick").c_str());
        else if (a == "--repo") repo = need("--repo");
        else if (a == "--probe") probe = lower(need("--probe"));
        else if (a == "--walk") walk = lower(need("--walk"));
        else if (a == "--compass") compass = need("--compass");
        else if (a == "--chains") chains = lower(need("--chains"));
        else if (a == "--levels") levels = lower(need("--levels"));
        else if (a == "--python") python = need("--python");
        else if (a == "--history") history = need("--history");
        else if (a == "--synth-levels") { synth = true; regime_synth = upper(need("--synth-levels")); }
        else if (a == "--no-ticks") no_ticks = true;
        else if (a == "--quiet") quiet = true;
        else if (a == "--speed") {
            std::string v = need("--speed");
            speed = (v == "max") ? 0.0 : atof(v.c_str());
        } else if (a == "-h" || a == "--help") {
            printf("uso: replay --date YYYY-MM-DD (--syms a,b|--fleet) --out DIR\n"
                   "     [--start HH:MM] [--end HH:MM] [--warm N] [--speed N|max] [--tick S]\n"
                   "     [--seed N] [--no-ticks] [--probe SYM] [--walk SYM]\n"
                   "     [--chains on|off] [--levels auto|chain|copy|synth|off]\n"
                   "     [--synth-levels POS|NEG] [--history DIR] [--python PATH]\n"
                   "     [--repo DIR] [--compass PATH] [--quiet]\n"
                   "\n  cadenas: data/history/<fecha>/opt_chain_<sym>[_HHMM].txt, publicadas por\n"
                   "  EPOCH de cabecera (<= reloj virtual). --levels chain regenera los\n"
                   "  charts/data/levels_<sym>.json del sandbox con scripts/chart_levels.py.\n");
            return 0;
        } else die("argumento desconocido: " + a);
    }
    if (date.empty()) die("--date es obligatorio");
    if (out.empty()) die("--out es obligatorio (sandbox; nunca los data/ reales)");
    if (tick <= 0 || tick > 60) die("--tick fuera de rango");
    if (speed > K::SPEED_HONEST)
        fprintf(stderr, "[replay] AVISO: speed %.0fx > %.0fx distorsiona la mecanica de fills "
                        "(sim_feed.py); solo para tests del invariante\n", speed, K::SPEED_HONEST);
    if (synth && regime_synth != "POS" && regime_synth != "NEG")
        die("--synth-levels exige el regimen explicito: POS o NEG (no se fabrica)");
    if (chains != "on" && chains != "off" && chains != "auto")
        die("--chains solo admite on|off (o auto)");
    if (levels != "auto" && levels != "chain" && levels != "copy" && levels != "synth" &&
        levels != "off")
        die("--levels solo admite auto|chain|copy|synth|off");
    if (synth && levels == "auto") levels = "synth";
    if (levels == "synth" && !synth)
        die("--levels synth exige --synth-levels POS|NEG (el regimen no se fabrica)");
    { char buf[4096];                       // repo ABSOLUTO: los hijos corren con cwd = sandbox
      if (!realpath(repo.c_str(), buf)) die("--repo no existe: " + repo);
      repo = buf; }
    if (history.empty()) history = repo + "/data/history/" + date;
    if (python.empty()) python = repo + "/venv/bin/python";

    // La brujula se EJECUTA con cwd = sandbox (usa rutas relativas), asi que su ruta tiene que
    // ser ABSOLUTA o "./compass" apuntaria dentro del sandbox y no existiria. Fallo real.
    {
        char buf[4096];
        bool ok = !compass.empty() && realpath(compass.c_str(), buf) != nullptr;
        if (!ok && !compass.empty()) {
            std::string cand = repo + "/" + compass;
            ok = realpath(cand.c_str(), buf) != nullptr;
        }
        if (ok) compass = buf;
        else if (!walk.empty())            // solo --walk EJECUTA la brujula; sin ella no hay medida
            die("no encuentro el binario de la brujula (" + compass +
                "); compila compass o pasa --compass RUTA_ABSOLUTA");
    }

    // simbolos
    std::vector<std::string> syms;
    if (fleet) {
        std::string f = slurp(repo + "/data/fleet.txt");
        if (f.empty()) die("no puedo leer " + repo + "/data/fleet.txt");
        std::istringstream ss(f);
        std::string s;
        while (ss >> s) syms.push_back(lower(s));
    }
    for (size_t p = 0; p < syms_arg.size();) {
        size_t q = syms_arg.find(',', p);
        if (q == std::string::npos) q = syms_arg.size();
        std::string s = lower(syms_arg.substr(p, q - p));
        if (!s.empty()) syms.push_back(s);
        p = q + 1;
    }
    if (!walk.empty() && std::find(syms.begin(), syms.end(), walk) == syms.end()) syms.push_back(walk);
    if (!probe.empty() && std::find(syms.begin(), syms.end(), probe) == syms.end()) syms.push_back(probe);
    std::sort(syms.begin(), syms.end());
    syms.erase(std::unique(syms.begin(), syms.end()), syms.end());
    if (syms.empty()) die("sin simbolos: usa --syms qqq,spy o --fleet");

    int h0, m0, h1, m1;
    parse_hhmm(start, h0, m0);
    parse_hhmm(end, h1, m1);
    long t_start = epoch_of(date, h0, m0), t_end = epoch_of(date, h1, m1);
    if (t_end <= t_start) die("--end debe ser posterior a --start");

    sandbox_guard(out, repo);
    Db db(repo + "/trades.db");

    // carga: warm-up (pasado) + sesion. El warm-up es contexto, no look-ahead.
    std::vector<Feed> feeds;
    long total_bars = 0;
    for (const auto& lo : syms) {
        Feed f;
        f.lo = lo; f.up = upper(lo);
        f.rng = Rng(sym_seed((uint64_t)seed, f.up));
        f.bars = db_bars(db, f.up, t_start - warm * K::BAR_S - 4 * 86400, t_end);
        // recortar el warm-up a las `warm` ultimas barras ANTES de t_start
        size_t k = 0;
        while (k < f.bars.size() && f.bars[k].t + K::BAR_S <= t_start) ++k;
        if ((long)k > warm) f.bars.erase(f.bars.begin(), f.bars.begin() + (long)(k - (size_t)warm));
        f.bars_path = out + "/data/bars_" + lo + "_ibkr.txt";
        f.nbbo_path = out + "/data/nbbo_" + lo + ".txt";
        f.tick_log  = out + "/data/nbbo_hist_" + lo + "_" + date + ".txt";
        f.chain_path = out + "/data/opt_chain_" + lo + ".txt";
        f.chain_log  = out + "/chains_" + lo + ".jsonl";
        if (chains != "off") f.snaps = scan_chains(history, lo);
        { FILE* z = fopen(f.bars_path.c_str(), "w"); if (z) fclose(z); }   // trunca / crea
        { FILE* z = fopen(f.tick_log.c_str(), "w"); if (z) fclose(z); }
        { FILE* z = fopen(f.chain_log.c_str(), "w"); if (z) fclose(z); }
        unlink(f.chain_path.c_str());       // sin cadena hasta que el reloj alcance un snapshot
        total_bars += (long)f.bars.size();
        feeds.push_back(std::move(f));
    }
    if (total_bars == 0) {
        std::string lst;
        for (const auto& f : feeds) { if (!lst.empty()) lst += ","; lst += f.up; }
        die("rango VACIO: poly_bars no tiene barras de {" + lst + "} en " + date +
            " " + start + "-" + end + " (¿simbolo inexistente o dia sin datos?)");
    }
    for (auto& f : feeds)
        if (f.bars.empty())
            fprintf(stderr, "[replay] AVISO: %s sin barras en el rango (queda vacio)\n", f.up.c_str());

    // ------------------- COBERTURA DE CADENAS (limite honesto) ------------------
    // Solo hay historia de cadenas de 3 dias (2026-07-22/23/24) y con granularidad DESIGUAL:
    // el 22 y el 23 antes de las 13:25 son snapshots HORARIOS; de 13:25 en adelante y todo el
    // 24 son de 5 min. Ademas poly_bars termina el 23 -> la interseccion barras+cadenas es
    // 07-22 y 07-23. Esto se DECLARA, no se disimula.
    long snap_total = 0, syms_with = 0;
    for (const auto& f : feeds) { snap_total += (long)f.snaps.size(); if (!f.snaps.empty()) ++syms_with; }
    if (chains == "on" && snap_total == 0)
        die("--chains on pero no hay snapshots en " + history +
            " (solo existen data/history/2026-07-22|23|24)");
    if (chains != "off" && !quiet)
        printf("[replay] cadenas: %ld snapshots en %zu/%zu simbolos (%s)\n", snap_total,
               (size_t)syms_with, feeds.size(), history.c_str());
    if (chains != "off")
        for (const auto& f : feeds)
            if (f.snaps.empty())
                fprintf(stderr, "[replay] AVISO: %s SIN cadenas historicas ese dia -> sin muros "
                                "GEX (la brujula dira 'sin mapa GEX fresco')\n", f.up.c_str());
    const bool has_chains = snap_total > 0 && chains != "off";
    if (levels == "auto") levels = has_chains ? "chain" : "copy";
    if (levels == "chain" && !has_chains)
        die("--levels chain exige cadenas historicas y no hay ninguna en " + history);

    // regenera charts/data/levels_<sym>.json del SANDBOX desde la cadena ya publicada.
    // El spot se pasa EXPLICITO (cierre de la ultima barra publicada): si se dejara el de la
    // cabecera del snapshot, la brujula miraria un spot de hasta 5 min de antigüedad y el
    // retraso medido de la flecha seria un artefacto del arnes, no del sistema.
    auto regen_levels = [&](Feed& f) {
        char px[32] = "";
        if (f.last_close > 0) snprintf(px, sizeof px, "@%.4f", f.last_close);
        std::string cmd = "cd '" + out + "' && IBT_ROOT='" + out + "' IBT_ASOF=auto '" + python +
                          "' '" + repo + "/scripts/chart_levels.py' " + f.lo + px +
                          " >/dev/null 2>&1";
        if (system(cmd.c_str()) != 0)
            fprintf(stderr, "[replay] AVISO: chart_levels fallo para %s (sin niveles nuevos)\n",
                    f.up.c_str());
    };

    // mapa de niveles del sandbox
    if (levels == "copy" || levels == "synth") for (auto& f : feeds) {
        bool ok;
        if (synth) {
            // sesion anterior = barras del dia natural previo con datos, DENTRO del warm-up
            std::vector<Bar> prev;
            long day0 = t_start - (t_start % 86400);
            for (const auto& b : f.bars) if (b.t < day0) prev.push_back(b);
            if (prev.size() > 400) prev.erase(prev.begin(), prev.end() - 400);
            ok = levels_synth(out, f.lo, prev, regime_synth);
        } else {
            ok = levels_copy(repo, out, f.lo);
        }
        if (!ok)
            fprintf(stderr, "[replay] AVISO: sin niveles para %s -> la brujula dira "
                            "'sin mapa GEX fresco' (SIN LECTURA)\n", f.up.c_str());
    }
    // CONFIG (no precios) que la brujula lee y que sin ella degradaria a otra cosa distinta de
    // produccion. Se copia solo lo que NO es una cotizacion:
    //   momentum_decay.json -> retrocesos MEDIDOS (amplitud), etf_weights.json -> engranaje
    //   QQQ/SPY, book_quality.json -> etiqueta THIN.
    // data/force.json NO se copia a proposito: es fuerza VIVA de hoy y la brujula la descarta
    // por antigüedad (FORCE_MAX_AGE); copiarla seria inyectar el presente en el pasado.
    for (const char* n : {"momentum_decay.json", "etf_weights.json", "book_quality.json"}) {
        std::string d = slurp(repo + "/data/" + n);
        if (!d.empty()) write_atomic(out + "/data/" + n, d);
    }

    const std::string clock_root = out + "/clock.txt";        // reloj virtual (raiz)
    const std::string clock_data = out + "/data/clock.txt";    // idem para --data DIR (scalper)
    auto write_clock = [&](double v) {
        char b[64];
        snprintf(b, sizeof b, "%.3f %s\n", v, hhmm_str((long)v).c_str());
        write_atomic(clock_root, b);
        write_atomic(clock_data, b);
    };

    // =========================== modo WALK (determinista) ====================
    // Barra a barra, sin dormir: publica la barra i y CRONOMETRA la brujula. Mide el retraso
    // ESTRUCTURAL (velas entre el extremo real y el giro de la flecha) sobre historia real.
    if (!walk.empty()) {
        Feed* fp = nullptr;
        for (auto& f : feeds) if (f.lo == walk) fp = &f;
        if (!fp) die("--walk " + walk + " no esta entre los simbolos");
        Feed& f = *fp;
        const std::string cjson = out + "/data/compass_" + f.lo + ".json";
        const std::string cmd = "cd '" + out + "' && '" + compass + "' --json " + f.lo +
                                " >/dev/null 2>&1";
        std::vector<WalkRow> raw;
        std::string jl;
        long n_sess = 0;
        for (size_t i = 0; i < f.bars.size(); ++i) {
            const Bar& b = f.bars[i];
            double v = (double)(b.t + K::BAR_S);
            write_clock(v);
            append_bar(f, b);
            // cadena del instante virtual (epoch <= v) + niveles recalculados al spot replayado
            long pub = publish_chain(f, v);
            if (levels == "chain") {
                if (pub) regen_levels(f);                        // cadena nueva: mapa completo
                else patch_levels_spot(out, f.lo, f.last_close); // solo el spot, como el chart
            }
            if (b.t < t_start) continue;    // warm-up: contexto, no se evalua
            ++n_sess;
            double w0 = now_real();
            int rc = system(cmd.c_str());
            double us = (now_real() - w0) * 1e6;
            if (rc != 0) die("la brujula fallo (rc=" + std::to_string(rc) + "): " + cmd);
            std::string j = slurp(cjson);
            if (j.empty()) die("la brujula no escribio " + cjson);
            WalkRow r{b.t, b.c, jstr(j, "state").value_or("?"), jstr(j, "dir").value_or("?"),
                      (int)jnum(j, "prob").value_or(50), us};
            raw.push_back(r);
            char line[512];
            snprintf(line, sizeof line,
                     "{\"bar_ts\":%ld,\"clock\":%.0f,\"bars_visible\":%zu,\"close\":%.4f,"
                     "\"state\":\"%s\",\"dir\":\"%s\",\"prob\":%d,\"printed\":%s,"
                     "\"compass_us\":%.0f}\n",
                     b.t, v, i + 1, b.c, jesc(r.state).c_str(), r.dir.c_str(), r.prob,
                     jbool(j, "printed", false) ? "true" : "false", us);
            jl += line;
        }
        write_atomic(out + "/walk_" + f.lo + ".jsonl", jl);
        if (raw.empty()) die("el walk no evaluo ninguna barra de sesion");

        // --- retraso ESTRUCTURAL: extremo real vs vela del giro -------------
        std::vector<std::string> st, dr;
        apply_hyst(raw, st, dr);

        // Dos poblaciones de "giro", y la primera es LA QUE PREGUNTO YUNIOR:
        //  FLIP  = la FLECHA cambia de sentido (dir up<->down). Es lo que se ve en la UI y lo
        //          que hace comprar; ocurre decenas de veces al dia.
        //  REV   = el ESTADO entra en "REVERSION EN EXTREMO" (el gatillo de fade). En regimen
        //          NEG puede no ocurrir NI UNA VEZ en todo el dia (veto de doctrina), asi que
        //          medir solo esto daba n=0 y la falsa impresion de "nada que medir".
        struct Stat { std::vector<double> lag, mae, mfe; int late = 0; std::string ev = "["; };
        Stat FL, RV;
        auto measure = [&](Stat& S, size_t i, int d) {
            // extremo real de cierres en [i-LAG_WIN, i+LAG_WIN]: el suelo si la flecha apunta
            // arriba, el techo si apunta abajo. lag>0 = la flecha giro DESPUES del extremo.
            size_t a = (i >= (size_t)K::LAG_WIN) ? i - K::LAG_WIN : 0;
            size_t z = std::min(raw.size() - 1, i + K::LAG_WIN);
            size_t m = a;
            for (size_t k = a; k <= z; ++k)
                if (d > 0 ? raw[k].close < raw[m].close : raw[k].close > raw[m].close) m = k;
            double lg = (double)i - (double)m;
            size_t hz = std::min(raw.size() - 1, i + K::MFE_H);
            double worst = raw[i].close, best = raw[i].close;
            for (size_t k = i; k <= hz; ++k) {
                worst = d > 0 ? std::min(worst, raw[k].close) : std::max(worst, raw[k].close);
                best  = d > 0 ? std::max(best,  raw[k].close) : std::min(best,  raw[k].close);
            }
            double mae_p = d * (worst - raw[i].close) / raw[i].close * 100.0;
            double mfe_p = d * (best - raw[i].close) / raw[i].close * 100.0;
            S.lag.push_back(lg); S.mae.push_back(mae_p); S.mfe.push_back(mfe_p);
            if (lg > 0) ++S.late;
            char b[320];
            snprintf(b, sizeof b, "%s{\"bar_ts\":%ld,\"dir\":\"%s\",\"state\":\"%s\",\"prob\":%d,"
                     "\"lag_bars\":%.0f,\"mae_pct\":%.4f,\"mfe_pct\":%.4f}",
                     S.lag.size() > 1 ? "," : "", raw[i].ts, dr[i].c_str(),
                     jesc(st[i]).c_str(), raw[i].prob, lg, mae_p, mfe_p);
            S.ev += b;
        };
        std::string last_dir = "flat";
        for (size_t i = 1; i < raw.size(); ++i) {
            int d = dr[i] == "up" ? 1 : (dr[i] == "down" ? -1 : 0);
            if (d != 0 && dr[i] != last_dir && last_dir != "flat") measure(FL, i, d);
            if (d != 0) last_dir = dr[i];
            if (d != 0 && st[i] == S_REV && st[i - 1] != S_REV) measure(RV, i, d);
        }
        FL.ev += "]"; RV.ev += "]";
        std::vector<double> cus;
        for (const auto& r : raw) cus.push_back(r.us);

        auto blk = [](const char* name, Stat& S) {
            char b[600];
            snprintf(b, sizeof b,
                     " \"%s\": {\"n\": %zu, \"lag_bars_median\": %.1f, \"lag_bars_p90\": %.1f,\n"
                     "   \"pct_late\": %.1f, \"mae_pct_median\": %.4f, \"mfe_pct_median\": %.4f,\n"
                     "   \"events\": %s},\n",
                     name, S.lag.size(), median(S.lag), pctile(S.lag, 0.9),
                     S.lag.empty() ? 0.0 : 100.0 * S.late / (double)S.lag.size(),
                     median(S.mae), median(S.mfe), S.ev.c_str());
            return std::string(b);
        };
        char hdr[900];
        snprintf(hdr, sizeof hdr,
                 "{\n \"sym\": \"%s\",\n \"date\": \"%s\",\n \"bars_evaluated\": %ld,\n"
                 " \"compass_us_median\": %.0f,\n \"compass_us_p90\": %.0f,\n"
                 " \"levels_src\": \"%s\",\n \"chain_snapshots\": %zu,\n"
                 " \"hysteresis_n\": %d,\n \"lag_window_bars\": %d,\n \"mfe_horizon_bars\": %d,\n",
                 f.up.c_str(), date.c_str(), n_sess, median(cus), pctile(cus, 0.9),
                 levels.c_str(), f.snaps.size(), K::HYST_N, K::LAG_WIN, K::MFE_H);
        std::string rep = hdr;
        rep += blk("arrow_flip", FL);
        rep += blk("reversion_entry", RV);
        rep.erase(rep.size() - 2);              // la ultima coma
        rep += "\n}\n";
        write_atomic(out + "/lag_report_" + f.lo + ".json", rep);
        if (!quiet) {
            printf("== WALK %s %s — %ld barras de sesion evaluadas ==\n", f.up.c_str(),
                   date.c_str(), n_sess);
            auto show = [&](const char* t, Stat& S) {
                printf("  %s: n=%zu", t, S.lag.size());
                if (S.lag.empty()) { printf(" (no ocurrio ese dia)\n"); return; }
                printf(" | retraso mediana %.1f velas, p90 %.1f, tarde %.0f%% | "
                       "MAE %+.3f%% MFE %+.3f%% (+%d velas)\n",
                       median(S.lag), pctile(S.lag, 0.9),
                       100.0 * S.late / (double)S.lag.size(), median(S.mae), median(S.mfe),
                       K::MFE_H);
            };
            show("GIRO DE FLECHA (dir up<->down)", FL);
            show("entrada en REVERSION EN EXTREMO ", RV);
            printf("  ciclo de la brujula (incluye spawn del proceso): mediana %.0f us, "
                   "p90 %.0f us\n", median(cus), pctile(cus, 0.9));
            printf("  informe: %s/lag_report_%s.json\n", out.c_str(), f.lo.c_str());
        }
        return 0;
    }

    // ======================= modo REALTIME (reloj virtual) ===================
    const int nticks = (int)std::llround(60.0 / tick);
    const double t0_wall = now_real();
    double v = (double)t_start;
    std::string probe_jl;
    long probe_n = 0;
    std::vector<double> probe_lag, probe_safe;
    const std::string probe_json = out + "/data/compass_" + probe + ".json";

    if (!quiet) {
        printf("[replay] %s %s-%s | %zu simbolos | %ld barras | speed %s | tick %.2fs | seed %ld\n",
               date.c_str(), start.c_str(), end.c_str(), syms.size(), total_bars,
               speed == 0 ? "max" : std::to_string((int)speed).c_str(), tick, seed);
        printf("[replay] niveles: %s | sandbox: %s\n", levels.c_str(), out.c_str());
        printf("[replay] brujula: (cd %s && %s --loop 0.25 %s)\n", out.c_str(), compass.c_str(),
               probe.empty() ? syms[0].c_str() : probe.c_str());
        fflush(stdout);
    }

    write_clock(v);
    while (v <= (double)t_end) {
        // ORDEN QUE IMPORTA: el reloj se publica ANTES de las barras de este instante. Al revés
        // (como estaba) un lector externo podia ver clock=v y a la vez una barra de v+tick ya
        // apendada, o sea un look-ahead APARENTE de una iteracion. Reloj primero => cualquier
        // lector que lea barras-y-despues-reloj ve siempre ts+60 <= clock. Invariante duro.
        write_clock(v);
        for (auto& f : feeds) {
            // 1) publicar TODA barra ya cerrada (t+60 <= v). NUNCA la que se esta formando:
            //    ese es el invariante anti-look-ahead.
            while (f.pi < f.bars.size() && (double)(f.bars[f.pi].t + K::BAR_S) <= v) {
                append_bar(f, f.bars[f.pi]);
                f.newbar = true;
                if (f.lo == probe && f.bars[f.pi].t >= t_start) {
                    f.pending_ns = now_real();
                    f.pending_bar = f.bars[f.pi].t;
                    f.first_write = 0;
                }
                ++f.pi;
            }
            if (no_ticks) continue;
            // 2) tape intra-minuto de la barra EN CURSO (ruta acotada a su O/H/L/C real)
            if (f.pi < f.bars.size() && (double)f.bars[f.pi].t <= v) {
                if (f.cur != f.pi) {
                    f.cur = f.pi;
                    f.path = bridge_ticks(f.bars[f.pi], nticks, f.rng);
                    f.half_spread = std::max(0.01, (f.bars[f.pi].h - f.bars[f.pi].l) * 0.02);
                }
                size_t k = (size_t)((v - (double)f.bars[f.pi].t) / tick);
                f.last_px = f.path[std::min(k, f.path.size() - 1)];
            }
            if (f.last_px <= 0) continue;
            char b[128];
            snprintf(b, sizeof b, "%.0f %.4f %.4f\n", v, f.last_px - f.half_spread,
                     f.last_px + f.half_spread);
            FILE* q = fopen(f.nbbo_path.c_str(), "w");           // sobrescrito, como el real
            if (q) { fputs(b, q); fclose(q); }
            snprintf(b, sizeof b, "%.3f %.4f %.4f\n", v, f.last_px - f.half_spread,
                     f.last_px + f.half_spread);
            FILE* g = fopen(f.tick_log.c_str(), "a");            // traza completa (determinismo)
            if (g) { fputs(b, g); fclose(g); }
        }
        // 2b) CADENAS: el snapshot mas reciente con epoch <= v (jamas uno futuro). Se hace tras
        //     las barras para que un chart_levels lento no retrase la publicacion de la vela.
        for (auto& f : feeds) {
            long pub = publish_chain(f, v);
            if (levels == "chain") {
                if (pub) regen_levels(f);
                else if (f.newbar) patch_levels_spot(out, f.lo, f.last_close);
            }
            f.newbar = false;
        }

        // 3) PROBE: retraso MECANICO END-TO-END = del append de la barra al JSON de la brujula
        //    ya en disco. La brujula reescribe su JSON CADA ciclo aunque nada cambie, asi que el
        //    PRIMER mtime posterior al append podria venir de un ciclo que leyo el fichero justo
        //    ANTES (ventana = su computo, ~1.1 ms de 250 ms). Por eso se miden DOS cotas y el
        //    valor real esta entre ellas:
        //      lag_ms      = 1er escritura posterior al append  -> cota INFERIOR
        //      lag_ms_safe = 2a escritura posterior al append   -> cota SUPERIOR (garantiza que
        //                    el ciclo empezo despues del append, o sea que VIO la barra)
        if (!probe.empty()) {
            for (auto& f : feeds) {
                if (f.lo != probe || f.pending_ns == 0) continue;
                auto mt = mtime_of(probe_json);
                if (!mt || *mt <= f.pending_ns) continue;
                if (f.first_write == 0) { f.first_write = *mt; continue; }
                if (*mt <= f.first_write) continue;
                double lag_ms = (f.first_write - f.pending_ns) * 1000.0;
                double safe_ms = (*mt - f.pending_ns) * 1000.0;
                probe_lag.push_back(lag_ms);
                probe_safe.push_back(safe_ms);
                char b[320];
                snprintf(b, sizeof b, "{\"bar_ts\":%ld,\"appended\":%.6f,\"compass_mtime\":%.6f,"
                         "\"lag_ms\":%.2f,\"lag_ms_safe\":%.2f}\n", f.pending_bar, f.pending_ns,
                         f.first_write, lag_ms, safe_ms);
                probe_jl += b;
                ++probe_n;
                f.pending_ns = 0;
                f.first_write = 0;
            }
        }

        v += tick;
        if (speed > 0) {
            double target = t0_wall + (v - (double)t_start) / speed;
            double dt = target - now_real();
            if (dt > 0) {
                struct timespec ts{(time_t)dt, (long)((dt - std::floor(dt)) * 1e9)};
                nanosleep(&ts, nullptr);
            }
        }
    }

    if (!probe.empty()) {
        write_atomic(out + "/probe_" + probe + ".jsonl", probe_jl);
        if (!quiet) {
            if (probe_n == 0)
                printf("[probe] 0 muestras: ¿esta corriendo la brujula? "
                       "(cd %s && %s --loop 0.25 %s)\n", out.c_str(), compass.c_str(), probe.c_str());
            else {
                printf("[probe] %s: n=%ld | retraso MECANICO END-TO-END barra->JSON de la "
                       "brujula\n", upper(probe).c_str(), probe_n);
                printf("  cota INFERIOR (1a escritura): mediana %.0f ms, p90 %.0f ms, max %.0f ms\n",
                       median(probe_lag), pctile(probe_lag, 0.9), pctile(probe_lag, 1.0));
                printf("  cota SUPERIOR (2a escritura, garantiza que vio la barra): mediana "
                       "%.0f ms, p90 %.0f ms, max %.0f ms\n", median(probe_safe),
                       pctile(probe_safe, 0.9), pctile(probe_safe, 1.0));
            }
        }
    }
    if (!quiet) printf("[replay] fin: reloj virtual %s\n", hhmm_str((long)v).c_str());
    return 0;
}
