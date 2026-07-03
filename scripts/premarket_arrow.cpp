// premarket_arrow — la flecha ANTES de las 09:30. Calcula el sesgo premarket con lo que de
// verdad tenemos en vivo y lo deja en data/premarket_arrow_<sym>.json para que compass lo lea.
//
// HONESTIDAD DE FUENTE (medido 2026-08-06, no negociable):
//   - EN VIVO no tenemos dato NO CONSOLIDADO. Databento da `A live data license is required`
//     en TODOS los datasets; Polygon sirve acciones a T-1 (403 para hoy); Finnhub /stock/candle
//     403 y su WS no trae exchange ni conditions. Lo unico vivo con barras 1m de 04:00-09:30 es
//     Intrinio `equities_edge`, que es CONSOLIDADO. Por eso clase_dato = "equities_edge_1m".
//   - Lo NO CONSOLIDADO (ARCX.PILLAR/XNAS.ITCH: lado agresor + desequilibrio de subasta) existe
//     en Databento a T-1 y es lo que CALIBRA los umbrales de aqui (data/premarket_calib.json,
//     clase_dato "unconsolidated_direct"). El fichero de salida lo dice en ambos campos: nadie
//     que lo lea puede confundir "calibrado con no-consolidado" con "leido no-consolidado".
//   - `volume` de las barras premarket de equities_edge es SIEMPRE 0: la 6a columna es
//     trade_count. Se publica como n_prints, jamas como volumen ni z-score de volumen.
//
// Regla #3: cada componente es optional; ausente CAE del denominador con motivo publicado.
// Jamas 0.0 plausible. Sin componentes -> usable=false y se dice por que.
#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <unistd.h>
#include <vector>

namespace K {
constexpr int PRE_INI = 4 * 60;          // 04:00 ET: arranca la sesion extendida
constexpr int PRE_FIN = 9 * 60 + 30;     // 09:30 ET: se acabo el premarket
constexpr double CTX_MAX_AGE = 900.0;    // overnight_ctx mas viejo que esto no entra
constexpr double BARS_MAX_AGE = 600.0;   // ultima barra mas vieja que esto: cinta muerta
constexpr int MIN_PRINTS = 200;          // por debajo, la cinta premarket no es una lectura
constexpr int MIN_BARS = 15;             // minutos con barra dentro de la ventana
constexpr double DIR_MIN = 0.12;         // |score| minimo para atreverse a apuntar (%)
constexpr double DOCTRINE_CAP = 65.0;    // techo de una probabilidad NO medida
}  // namespace K

struct Bar { long t; double o, h, l, c, v; };

static std::string slurp(const std::string& p) {
    std::ifstream f(p);
    if (!f) return {};
    std::ostringstream ss; ss << f.rdbuf();
    return ss.str();
}

static std::optional<double> jnum(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t')) ++p;
    if (p < s.size() && (s[p] == 'n' || s[p] == '"')) return std::nullopt;   // null / string
    double out{};
    auto [ptr, ec] = std::from_chars(s.data() + p, s.data() + s.size(), out);
    (void)ptr;
    return ec == std::errc{} ? std::optional<double>(out) : std::nullopt;
}

static std::optional<bool> jbool(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t')) ++p;
    if (s.compare(p, 4, "true") == 0) return true;
    if (s.compare(p, 5, "false") == 0) return false;
    return std::nullopt;
}

// Objeto {...} de `key`, exigiendo que el valor sea un objeto pegado a los dos puntos: la misma
// trampa que documenta compass.cpp (una clave puede ser peso Y seccion en el mismo fichero).
static std::string jsection(const std::string& all, const std::string& key) {
    std::string pat = "\"" + key + "\":";
    size_t p = all.find(pat);
    if (p == std::string::npos) return {};
    p += pat.size();
    while (p < all.size() && (all[p] == ' ' || all[p] == '\t' || all[p] == '\n')) ++p;
    if (p >= all.size() || all[p] != '{') return {};
    int depth = 0;
    for (size_t i = p; i < all.size(); ++i) {
        if (all[i] == '{') ++depth;
        else if (all[i] == '}' && --depth == 0) return all.substr(p, i - p + 1);
    }
    return {};
}

static std::vector<Bar> load_bars(const std::string& sym_lo) {
    std::vector<Bar> b;
    for (const char* suf : {"_ibkr.txt", ".txt"}) {
        FILE* f = fopen(("data/bars_" + sym_lo + suf).c_str(), "r");
        if (!f) continue;
        Bar x{};
        while (fscanf(f, "%ld %lf %lf %lf %lf %lf", &x.t, &x.o, &x.h, &x.l, &x.c, &x.v) == 6)
            b.push_back(x);
        fclose(f);
        if (!b.empty()) return b;
    }
    return b;
}

// Costura de test (mismo espiritu que compass --ev-stdin): la ventana premarket la fija el
// reloj, asi que sin esto los tests solo pasarian entre las 04:00 y las 09:30. Solo la lee el
// arnes; en produccion la variable no existe y manda time().
static time_t now_ts() {
    if (const char* e = getenv("PREMKT_NOW")) {
        long v = atol(e);
        if (v > 0) return (time_t)v;
    }
    return time(nullptr);
}

static int et_minute(long t) {
    time_t tt = t; struct tm v{}; localtime_r(&tt, &v);
    return v.tm_hour * 60 + v.tm_min;
}
static std::string et_day(long t) {
    time_t tt = t; struct tm v{}; localtime_r(&tt, &v);
    char b[16]; strftime(b, sizeof b, "%Y-%m-%d", &v);
    return b;
}

struct Comp {                              // un componente del score
    const char* nombre;
    std::optional<double> valor;           // en % con signo
    double peso;
    std::string ausente_por;               // por que no esta (vacio si esta)
};

struct Salida {
    std::string sym, session_date, unusable_reason, dir = "flat", prob_source = "sin_medir";
    std::string calib_bucket, calib_clase;
    bool usable = false;
    std::optional<double> score, gap, drift, prints, nq, es, korea, prob, prob_lo, prob_n;
    std::optional<double> last, prev_close, bars_age_s;
    int n_bars = 0, et_now = 0;
    std::vector<Comp> comps;
};

static void add(std::string& s, const char* k, std::optional<double> v, int dec = 4) {
    char b[128];
    if (v) snprintf(b, sizeof b, "\"%s\":%.*f,", k, dec, *v);
    else   snprintf(b, sizeof b, "\"%s\":null,", k);
    s += b;
}

static std::string to_json(const Salida& o) {
    std::string s = "{";
    s += "\"sym\":\"" + o.sym + "\",";
    s += "\"session_date\":\"" + o.session_date + "\",";
    s += std::string("\"usable\":") + (o.usable ? "true," : "false,");
    s += "\"unusable_reason\":" + (o.unusable_reason.empty()
             ? std::string("null,") : "\"" + o.unusable_reason + "\",");
    // las dos etiquetas que impiden confundir calibrado-con vs leido-de
    s += "\"clase_dato\":\"equities_edge_1m\",";
    s += "\"unconsolidated_live\":false,";
    s += "\"unconsolidated_live_why\":\"Databento sin licencia live en todos los datasets; "
         "Polygon acciones a T-1; Finnhub WS sin exchange ni conditions\",";
    s += "\"calib_clase\":\"" + (o.calib_clase.empty() ? std::string("sin_calibracion")
                                                       : o.calib_clase) + "\",";
    s += "\"volumen_no_disponible\":\"equities_edge da volume=0 en premarket; n_prints es "
         "trade_count, no acciones\",";
    s += "\"ventana\":\"04:00-09:30 ET\",";
    char b[64]; snprintf(b, sizeof b, "\"et_minute\":%d,\"n_bars\":%d,", o.et_now, o.n_bars);
    s += b;
    add(s, "last", o.last, 4); add(s, "prev_close", o.prev_close, 4);
    add(s, "bars_age_s", o.bars_age_s, 1);
    add(s, "gap_pct", o.gap); add(s, "drift_pct", o.drift);
    add(s, "n_prints", o.prints, 0);
    add(s, "nq_pct", o.nq); add(s, "es_pct", o.es); add(s, "korea_pct", o.korea);
    add(s, "score", o.score);
    s += "\"dir\":\"" + o.dir + "\",";
    add(s, "prob", o.prob, 0); add(s, "prob_lo", o.prob_lo); add(s, "prob_n", o.prob_n, 0);
    s += "\"prob_source\":\"" + o.prob_source + "\",";
    s += "\"calib_bucket\":\"" + o.calib_bucket + "\",";
    s += "\"componentes\":[";
    for (size_t i = 0; i < o.comps.size(); ++i) {
        const auto& c = o.comps[i];
        s += "{\"nombre\":\"" + std::string(c.nombre) + "\",";
        add(s, "valor", c.valor);
        snprintf(b, sizeof b, "\"peso\":%.2f,", c.peso); s += b;
        s += "\"ausente_por\":" + (c.ausente_por.empty() ? std::string("null")
                                                         : "\"" + c.ausente_por + "\"");
        s += "}";
        if (i + 1 < o.comps.size()) s += ",";
    }
    s += "],";
    snprintf(b, sizeof b, "\"ts\":%ld}", (long)now_ts());
    s += b;
    return s;
}

// Pesos: el gap y la deriva son la cinta premarket del propio nombre; los futuros son el
// contexto de indice; Corea solo pesa en los que arrastra (misma lista que compass.cpp).
static bool korea_symbol(const std::string& s) {
    static const char* L[] = {"MU","SKHY","DRAM","SMH","NVDA","TSM","ASML","AMD","INTC",
                              "AVGO","TXN","QCOM","EWY","LRCX","SNDK","WDC","STX"};
    for (auto x : L) if (s == x) return true;
    return false;
}

static Salida build(const std::string& sym_up, const std::string& sym_lo) {
    Salida o; o.sym = sym_up;
    time_t now = now_ts();
    o.session_date = et_day(now);
    o.et_now = et_minute(now);

    auto bars = load_bars(sym_lo);
    if ((int)bars.size() < 2) { o.unusable_reason = "sin barras"; return o; }

    // ventana premarket del DIA DE HOY (no de ayer: la sesion la fija el reloj, no el fichero)
    std::vector<Bar> pre, prev_rth;
    std::string hoy = o.session_date, ult_dia_rth;
    for (const auto& x : bars) {
        int m = et_minute(x.t); std::string d = et_day(x.t);
        if (d == hoy && m >= K::PRE_INI && m < K::PRE_FIN) pre.push_back(x);
        if (d != hoy && m >= 570 && m < 960) { if (d != ult_dia_rth) { prev_rth.clear(); ult_dia_rth = d; } prev_rth.push_back(x); }
    }
    o.n_bars = (int)pre.size();
    if (!prev_rth.empty()) o.prev_close = prev_rth.back().c;
    if (pre.empty()) { o.unusable_reason = "aun no hay barras de premarket hoy"; return o; }
    o.last = pre.back().c;
    o.bars_age_s = (double)(now - pre.back().t);

    double prints = 0; for (const auto& x : pre) prints += x.v;
    o.prints = prints;

    // ---- componentes (cada uno optional; el ausente CAE del denominador diciendo por que)
    std::string ctx = slurp("data/overnight_ctx.json");
    auto cts = jnum(ctx, "ts");
    bool ctx_ok = !ctx.empty() && cts && (double)now - *cts <= K::CTX_MAX_AGE;
    std::string ctx_no = ctx.empty() ? "sin overnight_ctx"
                       : (!cts ? "overnight_ctx sin ts" : "overnight_ctx rancio");

    if (o.prev_close && *o.prev_close > 0) o.gap = (*o.last / *o.prev_close - 1) * 100.0;
    o.drift = (pre.back().c / pre.front().o - 1) * 100.0;
    if (ctx_ok) { o.nq = jnum(ctx, "nq_pct"); o.es = jnum(ctx, "es_pct"); }
    if (ctx_ok && korea_symbol(sym_up)) {
        double num = 0, den = 0;
        for (auto [k, w] : {std::pair{"hynix_pct", 0.40}, std::pair{"samsung_pct", 0.35},
                            std::pair{"kospi_pct", 0.25}})
            if (auto v = jnum(ctx, k)) { num += *v * w; den += w; }
        if (den > 0) o.korea = num / den;
    }

    o.comps = {
        {"gap",    o.gap,    0.35, o.gap ? "" : "sin cierre RTH previo en el fichero"},
        {"drift",  o.drift,  0.25, ""},
        {"nq",     o.nq,     0.20, o.nq ? "" : ctx_no},
        {"es",     o.es,     0.10, o.es ? "" : ctx_no},
        {"korea",  o.korea,  0.10, o.korea ? ""
                                   : (korea_symbol(sym_up) ? ctx_no : "no arrastrado por Corea")},
    };
    double num = 0, den = 0;
    for (const auto& c : o.comps) if (c.valor) { num += *c.valor * c.peso; den += c.peso; }
    if (den <= 0) { o.unusable_reason = "ningun componente disponible"; return o; }
    o.score = num / den;

    // ---- porteros: la cinta premarket tiene que existir de verdad antes de apuntar
    if (prints < K::MIN_PRINTS) {
        o.unusable_reason = "cinta premarket demasiado fina (" + std::to_string((long)prints)
                          + " prints < " + std::to_string(K::MIN_PRINTS) + ")";
        return o;
    }
    if (o.n_bars < K::MIN_BARS) {
        o.unusable_reason = "solo " + std::to_string(o.n_bars) + " minutos con barra";
        return o;
    }
    if (o.bars_age_s && *o.bars_age_s > K::BARS_MAX_AGE) {
        o.unusable_reason = "ultima barra de hace " + std::to_string((long)*o.bars_age_s) + " s";
        return o;
    }
    o.usable = true;
    if (std::fabs(*o.score) >= K::DIR_MIN) o.dir = *o.score > 0 ? "up" : "down";

    // ---- probabilidad: SOLO si esta MEDIDA con no-consolidado; si no, se calla
    std::string cal = slurp("data/premarket_calib.json");
    if (!cal.empty()) {
        std::string meta = jsection(cal, "_meta");
        size_t q = meta.find("\"clase_dato\":");
        if (q != std::string::npos) {
            size_t a = meta.find('"', q + 13), b2 = meta.find('"', a + 1);
            if (a != std::string::npos && b2 != std::string::npos)
                o.calib_clase = meta.substr(a + 1, b2 - a - 1);
        }
        int q5 = std::min(4, (int)(std::fabs(*o.score) / 0.25));      // q1..q5 por |score|
        o.calib_bucket = "SIGNED_VOL|q" + std::to_string(q5 + 1);
        std::string buckets = jsection(cal, "buckets");
        std::string b3 = jsection(buckets, o.calib_bucket);
        auto medido = jbool(b3, "medido");
        auto wr = jnum(b3, "wr"), lo = jnum(b3, "lo"), n = jnum(b3, "n_eff");
        if (medido && *medido && wr && lo && n) {
            o.prob = std::round(*wr * 100.0); o.prob_lo = *lo; o.prob_n = *n;
            o.prob_source = "medido";
        } else {
            o.prob_source = b3.empty() ? "sin_celda" : "sin_medir";
        }
    } else {
        o.prob_source = "sin_calibracion";
    }
    if (o.prob_source != "medido" && o.dir != "flat") {
        // doctrina TOPADA: nunca una probabilidad inventada por encima del techo
        o.prob = std::min(50.0 + std::fabs(*o.score) * 20.0, K::DOCTRINE_CAP);
    }
    return o;
}

int main(int argc, char** argv) {
    std::vector<std::string> syms;
    bool stdout_only = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--stdout") stdout_only = true;
        else syms.push_back(a);
    }
    if (syms.empty()) { fprintf(stderr, "uso: premarket_arrow SYM [SYM...] [--stdout]\n"); return 2; }
    int rc = 0;
    for (auto s : syms) {
        std::string up = s, lo = s;
        for (auto& c : up) c = (char)toupper(c);
        for (auto& c : lo) c = (char)tolower(c);
        Salida o = build(up, lo);
        std::string j = to_json(o);
        if (stdout_only) { printf("%s\n", j.c_str()); continue; }
        std::string dst = "data/premarket_arrow_" + lo + ".json";
        std::string tmp = dst + ".tmp" + std::to_string(getpid());
        FILE* f = fopen(tmp.c_str(), "w");
        if (!f) { fprintf(stderr, "premarket_arrow: no puedo escribir %s\n", tmp.c_str()); rc = 1; continue; }
        fprintf(f, "%s\n", j.c_str());
        fclose(f);
        if (rename(tmp.c_str(), dst.c_str()) != 0) {
            fprintf(stderr, "premarket_arrow: rename fallo %s\n", dst.c_str()); rc = 1; continue;
        }
        printf("%s %s score=%s dir=%s prints=%s %s\n", up.c_str(),
               o.usable ? "USABLE" : "NO-USABLE",
               o.score ? std::to_string(*o.score).substr(0, 6).c_str() : "n/d",
               o.dir.c_str(),
               o.prints ? std::to_string((long)*o.prints).c_str() : "n/d",
               o.unusable_reason.c_str());
    }
    return rc;
}
