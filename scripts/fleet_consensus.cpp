// fleet_consensus.cpp — alarma de MANADA en C++23: dispara cuando TODA la flota se pone de
// acuerdo en una direccion (orden Yunior 2026-07-24) y la voz sale YA.
//
// POR QUE EXISTE ESTE PORT: LATENCIA, NO LOGICA
// ---------------------------------------------
// El daemon Python (scripts/fleet_consensus.py) duerme sleep(45) entre computos y la histeresis
// exige 2 ciclos consecutivos -> hasta 90 s desde que el consenso EXISTE hasta que suena la voz.
// En 0DTE ese es el movimiento entero. Aqui el ciclo baja a 5 s (--loop 5), asi que la histeresis
// cuesta ~10 s en vez de ~90 s, y el computo por ciclo pasa de decimas de segundo a microsegundos
// (nada de arrancar el interprete ni recalcular la cadena de opciones en Python).
//
// LA LOGICA ES LA DEL COMMIT 531feb7, ya endurecida — el port NO la cambia:
//   * el % se calcula sobre la FLOTA COMPLETA (data/fleet.txt, 30 simbolos), jamas sobre los que
//     parsearon. Aquel dia 4 simbolos fallaban en silencio y 21/26 = 80.8% DISPARABA cuando
//     21/30 = 70% no debia.
//   * MIN_COVER 0.90: por debajo NO hay veredicto direccional. Una cobertura mala es un problema
//     de FEED, no una direccion del mercado — y se dice con esas palabras.
//   * MAX_BAR_AGE 180 s: las barras rancias no votan (mtime del fichero). El disparo de las
//     00:00:45 fue rollover de fecha con barras de 11 h, no mercado.
//   * skipped{sym: motivo} se calcula y se IMPRIME: el que no vota tiene nombre y causa.
//   * ventana 09:25-16:05, capitanes SPY/QQQ/SMH unanimes, histeresis de 2 ciclos y solo en la
//     TRANSICION a consenso.
// SENAL-SOLAMENTE: voz + banner + linea al ledger. Jamas manda una orden.
//
// DEPENDENCIA DEL FLIP (la unica diferencia real con el Python — leer esto antes de conmutar)
// ------------------------------------------------------------------------------------------
// El voto de cada simbolo es el lado del gamma-flip. El Python llama chart_levels.gen(sym,
// spot=<vivo>, write=False), que RECALCULA el GEX desde la cadena de opciones al spot en vivo.
// Aqui NO se reimplementa el GEX: se lee "flip" de charts/data/levels_<sym>.json, que ya escribe
// scripts/chart_levels.py. Consecuencias, dichas en voz alta:
//   (a) esos JSON se escriben SIN atomicidad (json.dump directo sobre el fichero): puede leerse
//       truncado. Por eso se valida el parseo y, si no aparece un "flip" numerico y != 0, el
//       simbolo va a `skipped` con motivo. Nunca se asume nada.
//   (b) se comprueba la ANTIGUEDAD del fichero de niveles igual que la de las barras
//       (FLEET_CONS_MAX_LEVEL_AGE, default = MAX_BAR_AGE = 180 s). Ese gate estricto es
//       justamente lo que legitima leer un flip precocinado: si el mapa se escribio hace
//       segundos, se escribio a un spot ~= el spot vivo, asi que el flip es el mismo que
//       recalcularia el Python. Con un mapa viejo el flip podria estar desplazado -> no vota.
//   (c) si el mapa falta o esta rancio en >10% de la flota, eso es cobertura insuficiente y no
//       hay veredicto (comprobacion explicita, ademas de la de MIN_COVER).
// OPERATIVA: hoy NADIE reescribe charts/data/levels_*.json en bucle (chart_bridge.py solo
// regenera el simbolo del chart, y en memoria). Sin un refresco <=180 s de la flota este binario
// dira "cobertura insuficiente" para siempre — que es lo honesto, pero es SILENCIO. Antes de
// conmutar hay que poner a chart_levels.py a escribir la flota en bucle.
//
// Uso:  ./fleet_consensus --once                 (un computo, imprime y sale)
//       ./fleet_consensus --daemon [--loop 5]    (bucle; default 5 s)
//       ./fleet_consensus --ev-stdin < ev.json   (TEST: snapshot inyectado, CERO efectos)
// Umbrales por env (mismos nombres que el Python): FLEET_CONS_PCT (78), FLEET_CONS_MAX_BAR_AGE
// (180), FLEET_CONS_MIN_COVER (0.90), FLEET_CONS_WIN_OPEN (565), FLEET_CONS_WIN_CLOSE (965),
// FLEET_CONS_MAX_LEVEL_AGE (=MAX_BAR_AGE). FLEET_CONS_DRY=1 imprime el disparo en vez de
// ejecutarlo (arnes de test: sin voz, sin banner, sin escribir en el ledger).
// compilar: ./scripts/build_fleet_consensus.sh
#include <spawn.h>
#include <sys/stat.h>

#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <csignal>
#include <ctime>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include "../bots/fleet_notify.h"   // banner urgente por posix_spawn + espejo atomico al ledger

extern char** environ;

// ------------------------------- constantes ---------------------------------
namespace K {
constexpr int    HYST_N     = 2;      // ciclos consecutivos para disparar (anti-flicker)
constexpr size_t MIN_BARS   = 7;      // menos de 7 barras = sin momentum -> no vota
constexpr size_t MOM_LOOK   = 6;      // momentum sobre 6 barras (c[-1] vs c[-6])
constexpr double MOM_UP     = 0.03;   // % que cuenta como "con momentum" arriba
constexpr double MOM_DN     = -0.03;  // idem abajo
constexpr double LEVELS_MISS_MAX = 0.10;  // >10% de la flota sin mapa GEX = FEED, no direccion
constexpr size_t PCTB_N     = 20;     // ventana de Bollinger para %B
}

static const char* UP_S = "UP";
static const char* DN_S = "DN";

// ------------------------------- config -------------------------------------
struct Cfg {
    double pct           = 78.0;
    double max_bar_age   = 240.0;   // AUDIT #5: 180 dejo la MANADA ciega 238/239 ciclos (feed delayed)
    double min_cover     = 0.90;
    double max_level_age = 240.0;   // sigue = max_bar_age, como declara la cabecera
    int    win_open      = 9 * 60 + 25;
    int    win_close     = 16 * 60 + 5;
};

static double envd(const char* k, double dflt) {
    const char* v = getenv(k);
    if (!v || !*v) return dflt;
    char* end = nullptr;
    double x = strtod(v, &end);
    return (end && end != v) ? x : dflt;
}
static Cfg load_cfg() {
    Cfg c;
    c.pct           = envd("FLEET_CONS_PCT", c.pct);
    c.max_bar_age   = envd("FLEET_CONS_MAX_BAR_AGE", c.max_bar_age);
    c.min_cover     = envd("FLEET_CONS_MIN_COVER", c.min_cover);
    c.win_open      = (int)envd("FLEET_CONS_WIN_OPEN", (double)c.win_open);
    c.win_close     = (int)envd("FLEET_CONS_WIN_CLOSE", (double)c.win_close);
    c.max_level_age = envd("FLEET_CONS_MAX_LEVEL_AGE", c.max_bar_age);
    return c;
}

// --------------------------- JSON minimo (idiom del repo: compass.cpp) ------------------
static std::optional<double> jnum(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n')) ++p;
    if (p < s.size() && (s[p] == 'n' || s[p] == '"')) return std::nullopt;   // null / string
    double out{};
    auto [ptr, ec] = std::from_chars(s.data() + p, s.data() + s.size(), out);
    if (ec != std::errc{}) return std::nullopt;
    (void)ptr;
    return out;
}
static std::optional<std::string> jstr(std::string_view s, std::string_view key) {
    // OJO: no se puede exigir la comilla pegada a los dos puntos. json.dump() de Python escribe
    // ": " CON espacio (asi salen charts/data/levels_<sym>.json y los data/*.json del repo).
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
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n')) ++p;
    if (s.compare(p, 4, "true") == 0) return true;
    if (s.compare(p, 5, "false") == 0) return false;
    return dflt;
}
// texto del valor de `key` cuando es un array [...] (respeta anidamiento)
static std::optional<std::string> jarr(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n')) ++p;
    if (p >= s.size() || s[p] != '[') return std::nullopt;
    int depth = 0;
    for (size_t i = p; i < s.size(); ++i) {
        if (s[i] == '[') ++depth;
        else if (s[i] == ']') { if (--depth == 0) return std::string(s.substr(p, i - p + 1)); }
    }
    return std::nullopt;
}
static std::vector<std::string> jobjs(const std::string& arr) {
    std::vector<std::string> out;
    int depth = 0; size_t st = 0;
    for (size_t i = 0; i < arr.size(); ++i) {
        if (arr[i] == '{') { if (depth++ == 0) st = i; }
        else if (arr[i] == '}') { if (--depth == 0) out.push_back(arr.substr(st, i - st + 1)); }
    }
    return out;
}
static std::vector<std::string> jstrs(const std::string& arr) {
    std::vector<std::string> out;
    for (size_t i = 0; i < arr.size(); ++i) {
        if (arr[i] != '"') continue;
        auto e = arr.find('"', i + 1);
        if (e == std::string::npos) break;
        out.push_back(arr.substr(i + 1, e - i - 1));
        i = e;
    }
    return out;
}
static std::vector<double> jnums(const std::string& arr) {
    std::vector<double> out;
    const char* p = arr.c_str();
    const char* e = p + arr.size();
    if (p < e) ++p;                                  // saltar el '['
    while (p < e) {
        while (p < e && (*p == ' ' || *p == ',' || *p == '\n' || *p == '\t' || *p == '[')) ++p;
        if (p >= e || *p == ']') break;
        double v{};
        auto [np, ec] = std::from_chars(p, e, v);
        if (ec != std::errc{}) break;
        out.push_back(v);
        p = np;
    }
    return out;
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
// edad del fichero en segundos; nullopt si no existe
static std::optional<double> file_age(const std::string& path, double now) {
    struct stat st{};
    if (stat(path.c_str(), &st) != 0) return std::nullopt;
    return now - (double)st.st_mtime;
}

// ------------------------------- flota --------------------------------------
static std::vector<std::string> load_fleet(const std::string& path = "data/fleet.txt") {
    std::vector<std::string> f;
    std::ifstream in(path);
    std::string s;
    while (in >> s) f.push_back(s);
    return f;
}
static bool is_captain(const std::string& s) { return s == "SPY" || s == "QQQ" || s == "SMH"; }
static std::string lower(std::string s) {
    for (auto& c : s) c = (char)tolower((unsigned char)c);
    return s;
}

// ------------------------------- %B (paridad con _pb del Python) ------------
// Devuelve nullopt = "no se". JAMAS 0.5 por defecto: un %B de 0.5 dice "en el centro de la banda,
// nada que ver" cuando la verdad es "no hay datos", e indistinguible de una medicion real
// (fix 2026-07-25). Presente por paridad con el Python; hoy es DIAGNOSTICO: no vota ni veta
// (snapshot() del Python tampoco lo usa). Sale en el JSON de --ev-stdin.
static std::optional<double> pctb(const std::vector<double>& c, size_t n = K::PCTB_N) {
    if (c.size() < n) return std::nullopt;
    double m = 0;
    for (size_t i = c.size() - n; i < c.size(); ++i) m += c[i];
    m /= (double)n;
    double sd = 0;
    for (size_t i = c.size() - n; i < c.size(); ++i) sd += (c[i] - m) * (c[i] - m);
    sd = std::sqrt(sd / (double)n);                 // pstdev (poblacional), como statistics.pstdev
    double up = m + 2 * sd, lo = m - 2 * sd;
    return up > lo ? (c.back() - lo) / (up - lo) : 0.5;
}

// ------------------------------- materia prima -------------------------------
struct SymSnap {
    std::string sym;
    bool present = true;                  // en --ev-stdin: si el simbolo venia en el snapshot
    bool have_bars = false;
    double bar_age = 0;
    std::vector<double> closes;           // cierres 1m
    std::optional<double> flip;           // ya resuelto (solo --ev-stdin)
    std::string levels_path;              // si no hay flip: de donde leerlo (produccion / test)
};

struct Vote {
    bool voted = false;
    int side = 0;                         // +1 sobre el flip / -1 bajo el flip
    double mom = 0;
    std::optional<double> pb;
    std::string skip;                     // motivo si no voto
    bool levels_problem = false;          // el motivo fue el mapa GEX (falta/rancio/corrupto)
};

// Un simbolo -> un voto (o un motivo). Mismo orden de gates que snapshot() del Python.
static Vote evaluate(const SymSnap& s, const Cfg& cfg, double now) {
    Vote v;
    char buf[192];
    if (!s.present)  { v.skip = "ausente del snapshot"; return v; }
    if (!s.have_bars) { v.skip = "sin fichero de barras"; return v; }
    if (s.bar_age > cfg.max_bar_age) {
        snprintf(buf, sizeof buf, "barras rancias (%.0fmin)", s.bar_age / 60.0);
        v.skip = buf; return v;
    }
    if (s.closes.size() < K::MIN_BARS) { v.skip = "menos de 7 barras"; return v; }
    double spot = s.closes.back();

    std::optional<double> flip = s.flip;
    if (!flip) {
        if (s.levels_path.empty()) { v.skip = "sin flip en el mapa GEX"; v.levels_problem = true; return v; }
        auto age = file_age(s.levels_path, now);
        if (!age) {
            snprintf(buf, sizeof buf, "sin mapa GEX (%s)", s.levels_path.c_str());
            v.skip = buf; v.levels_problem = true; return v;
        }
        if (*age > cfg.max_level_age) {
            snprintf(buf, sizeof buf, "mapa GEX rancio (%.0fmin)", *age / 60.0);
            v.skip = buf; v.levels_problem = true; return v;
        }
        // Escritura NO atomica en el lado del productor -> se puede leer truncado. Se valida el
        // parseo; si no hay "flip" numerico y != 0, no se asume nada.
        std::string txt = slurp(s.levels_path);
        auto f = jnum(txt, "flip");
        if (!f || *f == 0.0) { v.skip = "sin flip en el mapa GEX"; v.levels_problem = true; return v; }
        flip = *f;
    }

    size_t n = s.closes.size();
    double ref = s.closes[n - K::MOM_LOOK];          // c1[-6]
    if (ref == 0.0) { v.skip = "cierre de referencia 0"; return v; }
    v.mom = 100.0 * (spot - ref) / ref;
    v.side = spot >= *flip ? 1 : -1;
    v.pb = pctb(s.closes);
    v.voted = true;
    return v;
}

// ------------------------------- agregado -----------------------------------
struct Agg {
    int up = 0, dn = 0, n = 0, mom_up = 0, mom_dn = 0, no_levels = 0;
    std::vector<std::pair<std::string, std::string>> caps;      // orden de la flota
    std::vector<std::pair<std::string, std::string>> skipped;   // sym -> motivo
    std::vector<std::pair<std::string, Vote>> votes;            // diagnostico
};

static Agg aggregate(const std::vector<SymSnap>& snaps, const Cfg& cfg, double now) {
    Agg a;
    for (const auto& s : snaps) {
        Vote v = evaluate(s, cfg, now);
        a.votes.emplace_back(s.sym, v);
        if (!v.voted) {
            a.skipped.emplace_back(s.sym, v.skip);
            if (v.levels_problem) ++a.no_levels;
            continue;
        }
        if (v.side > 0) { ++a.up; if (v.mom > K::MOM_UP) ++a.mom_up; }
        else            { ++a.dn; if (v.mom < K::MOM_DN) ++a.mom_dn; }
        if (is_captain(s.sym)) a.caps.emplace_back(s.sym, v.side > 0 ? UP_S : DN_S);
    }
    a.n = a.up + a.dn;
    return a;
}

// Capitanes unanimes + flota >= PCT del mismo lado + COBERTURA suficiente.
// Devuelve {"" | "UP" | "DN", motivo}. Textos identicos al Python (531feb7).
static std::pair<std::string, std::string> consensus_dir(const Agg& a, size_t nf, const Cfg& cfg) {
    char buf[256];
    int need = (int)((double)nf * cfg.min_cover);
    if (a.n < need) {
        snprintf(buf, sizeof buf,
                 "cobertura insuficiente %d/%zu (min %d) — esto es FEED, no direccion",
                 a.n, nf, need);
        return {"", buf};
    }
    // mapa GEX ausente/rancio en >10% de la flota: tampoco hay direccion (gate explicito, por si
    // MIN_COVER viene relajado por env)
    if ((double)a.no_levels > K::LEVELS_MISS_MAX * (double)nf) {
        snprintf(buf, sizeof buf,
                 "mapa GEX ausente/rancio en %d/%zu (>%.0f%%) — esto es FEED, no direccion",
                 a.no_levels, nf, K::LEVELS_MISS_MAX * 100.0);
        return {"", buf};
    }
    if (a.caps.size() < 3) {
        snprintf(buf, sizeof buf, "faltan capitanes (%zu/3)", a.caps.size());
        return {"", buf};
    }
    const std::string& cdir = a.caps.front().second;
    for (const auto& [c, d] : a.caps) { (void)c; if (d != cdir) return {"", "capitanes divididos"}; }
    int aligned = (cdir == UP_S) ? a.up : a.dn;
    double pct = 100.0 * (double)aligned / (double)nf;    // <- FLOTA COMPLETA, no los que parsearon
    if (pct >= cfg.pct) {
        snprintf(buf, sizeof buf, "%d/%zu = %.0f%%", aligned, nf, pct);
        return {cdir, buf};
    }
    snprintf(buf, sizeof buf, "%d/%zu = %.0f%% < %.0f%%", aligned, nf, pct, cfg.pct);
    return {"", buf};
}

// ------------------------------- histeresis ---------------------------------
struct Hyst { std::string last, pending; int cnt = 0; };

// Port literal del Python: 2 ciclos consecutivos y SOLO en la transicion a consenso; si el
// consenso se rompe, se re-arma. Devuelve true cuando toca disparar.
static bool hyst_step(Hyst& h, const std::string& cdir) {
    if (!cdir.empty() && cdir != h.last) {
        if (h.pending == cdir) h.cnt += 1;
        else { h.pending = cdir; h.cnt = 1; }
        if (h.cnt >= K::HYST_N) {
            h.last = cdir; h.pending.clear(); h.cnt = 0;
            return true;
        }
    } else if (cdir.empty()) {
        h.last.clear(); h.pending.clear(); h.cnt = 0;
    }
    return false;
}

// ------------------------------- disparo ------------------------------------
static void speak_danger(const char* text) {
    const char* argv[] = {"/bin/bash", "scripts/speak.sh", "DANGER", text, nullptr};
    pid_t pid = 0;
    posix_spawn(&pid, "/bin/bash", nullptr, nullptr, (char* const*)argv, environ);
}

static void fire(const std::string& cdir, const Agg& a, size_t nf) {
    bool up = (cdir == UP_S);
    const char* veh = up ? "CALLS" : "PUTS";
    int aligned = up ? a.up : a.dn;
    int mom = up ? a.mom_up : a.mom_dn;
    char faltan[48] = "";
    if (!a.skipped.empty()) snprintf(faltan, sizeof faltan, " (%zu sin voto)", a.skipped.size());
    // El mensaje completo va al banner Y (por el espejo de fleet_notify) al ledger. La linea
    // resultante ("HH:MM:SS | titulo | msg") ronda los 300 bytes: por debajo de PIPE_BUF, asi que
    // el append con O_APPEND sigue siendo ATOMICO. No alargar sin recontar.
    char msg[700];
    snprintf(msg, sizeof msg,
             "🐘 MANADA %s %s: %d/%zu%s de la flota alineados %s del flip + los 3 capitanes de "
             "acuerdo (%d con momentum). Sesgo direccional FUERTE -> comprar %s. VERIFICA spread "
             "<=5%% y print antes de entrar (optgate). No es consejo financiero.",
             up ? "ALCISTA" : "BAJISTA", up ? "📈" : "📉", aligned, nf, faltan,
             up ? "ARRIBA" : "ABAJO", mom, veh);
    char title[64];
    snprintf(title, sizeof title, "🐘 MANADA %s", up ? "ALCISTA" : "BAJISTA");
    char voice[192];
    snprintf(voice, sizeof voice, "Manada %s: la flota se puso de acuerdo. Comprar %s.",
             up ? "alcista" : "bajista", up ? "calls" : "puts");
    if (getenv("FLEET_CONS_DRY")) {             // arnes (idiom FP_TEST de flow_pulse.cpp):
        printf("[DRY] VOZ | %s\n", voice);      // se imprime lo que se HABRIA hecho, sin efectos
        printf("[DRY] BANNER | %s | %s\n", title, msg);
        time_t t = time(nullptr); struct tm lt{}; localtime_r(&t, &lt);
        printf("[DRY] LEDGER | %02d:%02d:%02d | %s | %s\n", lt.tm_hour, lt.tm_min, lt.tm_sec,
               title, msg);
    } else {
        speak_danger(voice);                       // voz DANGER (preempta) via posix_spawn
        fleet_notify_urgent(title, msg, "Hero");   // banner + append atomico a data/trading-signals
    }
    printf("[consensus] DISPARADA %s: %d/%zu (n=%d, sin voto %zu)\n",
           cdir.c_str(), aligned, nf, a.n, a.skipped.size());
    fflush(stdout);
}

// ------------------------ produccion: leer data/ ----------------------------
static std::vector<double> load_closes(const std::string& path) {
    std::vector<double> c;
    FILE* f = fopen(path.c_str(), "r");
    if (!f) return c;
    long t = 0; double o = 0, h = 0, l = 0, cl = 0, v = 0;
    while (fscanf(f, "%ld %lf %lf %lf %lf %lf", &t, &o, &h, &l, &cl, &v) == 6) c.push_back(cl);
    fclose(f);
    return c;
}

static std::vector<SymSnap> gather(const std::vector<std::string>& fleet, const Cfg& cfg,
                                   double now) {
    std::vector<SymSnap> out;
    out.reserve(fleet.size());
    for (const auto& sym : fleet) {
        SymSnap s;
        s.sym = sym;
        std::string lo = lower(sym);
        std::string bp = "data/bars_" + lo + "_ibkr.txt";
        auto age = file_age(bp, now);
        if (age) {
            s.have_bars = true;
            s.bar_age = *age;
            // solo se leen las barras si la edad pasa el gate: con el mercado cerrado esto ahorra
            // 30 lecturas de fichero por ciclo, y el motivo del skip es el mismo ("rancias").
            if (*age <= cfg.max_bar_age) s.closes = load_closes(bp);
        }
        s.levels_path = "charts/data/levels_" + lo + ".json";
        out.push_back(std::move(s));
    }
    return out;
}

// ------------------------ TEST: snapshot inyectado --------------------------
// Esquema (todo opcional salvo "syms"):
//   {"fleet":["QQQ",...],           // default: data/fleet.txt
//    "now_min":600,                 // default: reloj local (ventana horaria)
//    "last":"DN","pending":"DN","pend_cnt":1,     // histeresis de entrada
//    "syms":[{"sym":"QQQ","spot":100.0,"flip":99.0,"mom":0.4,"bar_age":10,
//             "have_bars":true,"closes":[...],"levels_file":"/tmp/x.json"}]}
// Los simbolos de la flota que no aparecen en "syms" cuentan como skipped (denominador intacto).
// En este modo NO se habla, NO se notifica y NO se escribe nada: solo JSON por stdout.
static std::vector<SymSnap> ev_snaps(const std::string& j, std::vector<std::string>& fleet) {
    if (auto fa = jarr(j, "fleet")) {
        auto v = jstrs(*fa);
        if (!v.empty()) fleet = v;
    }
    std::vector<SymSnap> byfleet;
    byfleet.reserve(fleet.size());
    for (const auto& f : fleet) { SymSnap s; s.sym = f; s.present = false; byfleet.push_back(s); }

    auto arr = jarr(j, "syms");
    if (!arr) return byfleet;
    for (const auto& ob : jobjs(*arr)) {
        auto nm = jstr(ob, "sym");
        if (!nm) continue;
        SymSnap s;
        s.sym = *nm;
        s.present = true;
        s.have_bars = jbool(ob, "have_bars", true);
        s.bar_age = jnum(ob, "bar_age").value_or(0.0);
        if (auto ca = jarr(ob, "closes")) s.closes = jnums(*ca);
        if (s.closes.empty()) {
            // sin serie explicita: se sintetiza la MINIMA que reproduce spot y mom, para que el
            // gate de "menos de 7 barras" y el calculo de momentum sean el MISMO codigo que en
            // produccion (c[-6] es el ancla del momentum).
            auto sp = jnum(ob, "spot");
            if (sp) {
                double mom = jnum(ob, "mom").value_or(0.0);
                double base = *sp / (1.0 + mom / 100.0);
                s.closes.assign(K::MIN_BARS, base);
                s.closes.back() = *sp;
            }
        }
        if (auto fl = jnum(ob, "flip")) s.flip = *fl;
        if (auto lf = jstr(ob, "levels_file")) s.levels_path = *lf;
        bool placed = false;
        for (auto& b : byfleet) if (b.sym == s.sym) { b = s; placed = true; break; }
        if (!placed) byfleet.push_back(s);       // simbolo fuera de la flota: se respeta y suma
    }
    return byfleet;
}

static void ev_print(const Agg& a, size_t nf, const std::string& cdir, const std::string& why,
                     bool in_window, bool fired, const Hyst& h) {
    std::string s = "{";
    char b[512];
    snprintf(b, sizeof b, "\"up\":%d,\"dn\":%d,\"n\":%d,\"fleet\":%zu,\"mom_up\":%d,\"mom_dn\":%d,"
                          "\"no_levels\":%d,", a.up, a.dn, a.n, nf, a.mom_up, a.mom_dn, a.no_levels);
    s += b;
    s += "\"caps\":{";
    for (size_t i = 0; i < a.caps.size(); ++i)
        s += (i ? "," : "") + std::string("\"") + jesc(a.caps[i].first) + "\":\"" + a.caps[i].second + "\"";
    s += "},";
    s += "\"consensus\":" + (cdir.empty() ? std::string("null") : "\"" + cdir + "\"") + ",";
    s += "\"why\":\"" + jesc(why) + "\",";
    snprintf(b, sizeof b, "\"in_window\":%s,\"fired\":%s,",
             in_window ? "true" : "false", fired ? "true" : "false");
    s += b;
    s += "\"skipped\":{";
    for (size_t i = 0; i < a.skipped.size(); ++i)
        s += (i ? "," : "") + std::string("\"") + jesc(a.skipped[i].first) + "\":\"" +
             jesc(a.skipped[i].second) + "\"";
    s += "},";
    s += "\"votes\":[";
    bool first = true;
    for (const auto& [sym, v] : a.votes) {
        if (!v.voted) continue;
        snprintf(b, sizeof b, "%s{\"sym\":\"%s\",\"side\":%d,\"mom\":%.4f,\"pctb\":",
                 first ? "" : ",", jesc(sym).c_str(), v.side, v.mom);
        s += b;
        if (v.pb) { snprintf(b, sizeof b, "%.4f}", *v.pb); s += b; }
        else s += "null}";
        first = false;
    }
    s += "],";
    snprintf(b, sizeof b, "\"hyst\":{\"last\":%s,\"pending\":%s,\"pend_cnt\":%d}}",
             h.last.empty() ? "null" : ("\"" + h.last + "\"").c_str(),
             h.pending.empty() ? "null" : ("\"" + h.pending + "\"").c_str(), h.cnt);
    s += b;
    printf("%s\n", s.c_str());
}

// ------------------------------- main ---------------------------------------
int main(int argc, char** argv) {
    std::signal(SIGCHLD, SIG_IGN);        // fire-and-forget: sin zombies ni waitpid
    bool once = false, ev_stdin = false;
    int loop_s = 5;                       // 5 s: la razon de ser del port (era sleep(45))
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--once") once = true;
        else if (a == "--daemon") once = false;
        else if (a == "--ev-stdin") ev_stdin = true;
        else if (a == "--loop" && i + 1 < argc) loop_s = atoi(argv[++i]);
    }
    Cfg cfg = load_cfg();

    if (ev_stdin) {   // TEST: snapshot inyectado, cero efectos secundarios
        std::ostringstream ss; ss << std::cin.rdbuf();
        std::string j = ss.str();
        std::vector<std::string> fleet = load_fleet();
        auto snaps = ev_snaps(j, fleet);
        double now = (double)time(nullptr);
        Agg a = aggregate(snaps, cfg, now);
        auto [cdir, why] = consensus_dir(a, fleet.size(), cfg);
        int nowm;
        if (auto nm = jnum(j, "now_min")) nowm = (int)*nm;
        else { time_t t = (time_t)now; struct tm lt{}; localtime_r(&t, &lt); nowm = lt.tm_hour * 60 + lt.tm_min; }
        bool in_window = (cfg.win_open <= nowm && nowm <= cfg.win_close);
        std::string eff = in_window ? cdir : std::string();
        Hyst h;
        if (auto s = jstr(j, "last")) h.last = *s;
        if (auto s = jstr(j, "pending")) h.pending = *s;
        if (auto v = jnum(j, "pend_cnt")) h.cnt = (int)*v;
        bool fired = hyst_step(h, eff);
        ev_print(a, fleet.size(), cdir, why, in_window, fired, h);
        return 0;
    }

    std::vector<std::string> fleet = load_fleet();
    if (fleet.empty()) { fprintf(stderr, "[consensus] data/fleet.txt vacio o ausente\n"); return 2; }
    printf("[consensus] monitor MANADA — umbral %.1f%% + capitanes unanimes (ciclo %ds)\n",
           cfg.pct, once ? 0 : loop_s);
    fflush(stdout);
    Hyst h;
    for (;;) {
        double now = (double)time(nullptr);
        auto snaps = gather(fleet, cfg, now);
        Agg a = aggregate(snaps, cfg, now);
        auto [cdir, why] = consensus_dir(a, fleet.size(), cfg);
        double dom = 100.0 * (double)std::max(a.up, a.dn) / (double)fleet.size();
        time_t tt = (time_t)now; struct tm lt{}; localtime_r(&tt, &lt);
        printf("  %02d:%02d:%02d flota %d↑/%d↓ de %zu (%.0f%% dom, n=%d) caps={",
               lt.tm_hour, lt.tm_min, lt.tm_sec, a.up, a.dn, fleet.size(), dom, a.n);
        for (size_t i = 0; i < a.caps.size(); ++i)
            printf("%s'%s': '%s'", i ? ", " : "", a.caps[i].first.c_str(), a.caps[i].second.c_str());
        printf("} -> consenso=%s [%s]\n", cdir.empty() ? "no" : cdir.c_str(), why.c_str());
        if (!a.skipped.empty()) {
            printf("    NO VOTARON (%zu): ", a.skipped.size());
            for (size_t i = 0; i < a.skipped.size() && i < 6; ++i)
                printf("%s%s=%s", i ? ", " : "", a.skipped[i].first.c_str(), a.skipped[i].second.c_str());
            printf("\n");
        }
        // ventana horaria: fuera de sesion no hay veredicto direccional (rollover, feeds caidos)
        int nowm = lt.tm_hour * 60 + lt.tm_min;
        std::string eff = cdir;
        if (!(cfg.win_open <= nowm && nowm <= cfg.win_close)) {
            if (!cdir.empty())
                printf("    fuera de ventana %d:%02d-%d:%02d: no se dispara\n",
                       cfg.win_open / 60, cfg.win_open % 60, cfg.win_close / 60, cfg.win_close % 60);
            eff.clear();
        }
        if (hyst_step(h, eff)) fire(eff, a, fleet.size());
        if (once) {
            if (eff.empty()) printf("  -> sin consenso ahora (flota dividida o capitanes discordes)\n");
            break;
        }
        fflush(stdout);
        struct timespec ts{loop_s > 0 ? loop_s : 5, 0};
        nanosleep(&ts, nullptr);
    }
    fflush(stdout);
    return 0;
}
