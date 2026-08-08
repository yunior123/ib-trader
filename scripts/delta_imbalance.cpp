// delta_imbalance.cpp — VETO por divergencia de delta acumulado (opciones UW vs precio).
//
// QUE MIDE (y que NO). El barrido de 85 sesiones x 30 syms (939.784 minutos) midio:
//   · delta por minuto crudo, seguir o fadear ...... edge +0,3..+0,8 pp, CI cruza 0  -> NADA
//   · condicionales (apilado/conviccion/absorcion) . 0 de 128 celdas pasan BH-FDR    -> NADA
//   · divergencia sobre el delta ACUMULADO ......... largo DENTRO de divergencia bajista
//     48,69% vs 49,72% fuera: -1,02 pp, p=1,2e-7, CI [-1,58, -0,50] pp             -> VETO
// Un punto porcentual NO es una entrada (la expectancia Wilson-LB sigue negativa): es un
// VETO, igual que `vol-trigger`. Este binario NO canta entradas y NO tiene voz.
//
// Fuentes (ficheros que ya mantiene la flota, cero red nueva):
//   data/bars_<sym>_ibkr.txt                    epoch o h l c v  (1 min)
//   data/history/<hoy>/uw_greek_flow_<sym>.json dir_delta_flow por minuto (uw_flow_archive)
//   data/research/delta_imbalance_veto.json     los numeros MEDIDOS (sin el, no se afirma nada)
// Salida: data/delta_imbalance.json + una linea JSONL por cambio de estado.
//
// SEÑAL-SOLAMENTE. Jamas ordena.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <deque>
#include <fstream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr int kDivWindow = 15;      // ventana de extremos MEDIDA (w=15 fue la de mayor edge)
constexpr int kAtrN = 14;
constexpr int kBB = 20;             // Bollinger(20,2) 1m: el setup que este veto REFUERZA
constexpr double kBBK = 2.0;
constexpr int kRthOpen = 585;       // 09:45 ET — la ventana del estudio
constexpr int kRthClose = 940;      // 15:40 ET
bool g_forzar = false;              // --forzar: calcula fuera de la ventana (verificacion)
bool g_dump = false;                // --dump: estado de CADA minuto (verificacion cruzada)

struct Bar { long t; double o, h, l, c, v; };

struct Calib {
    double mfe_p60 = 0, mae_p75 = 0, mae_p90 = 0;
    double pp_largo_bajista = 0, pp_corto_bajista = 0;
    double pp_largo_alcista = 0, pp_corto_alcista = 0;
    long n_bajista = 0, n_alcista = 0;
    bool ok = false;
};

// ---------------------------------------------------------------- lectura tolerante
// Los tres ficheros son planos o JSON de forma FIJA que escribe el propio repo. Se extraen
// los campos por nombre; un campo ausente devuelve nullopt y el llamador falla ALTO.

std::optional<std::string> slurp(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return std::nullopt;
    std::ostringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

// valor numerico de "clave": acepta 12.3 y "12.3" (UW sirve numeros como string)
std::optional<double> num_after(const std::string& s, size_t pos) {
    while (pos < s.size() && (s[pos] == ' ' || s[pos] == ':' || s[pos] == '"')) ++pos;
    if (pos >= s.size()) return std::nullopt;
    char* endp = nullptr;
    double v = std::strtod(s.c_str() + pos, &endp);
    if (endp == s.c_str() + pos) return std::nullopt;
    return v;
}

std::optional<double> field_num(const std::string& s, const std::string& key, size_t from = 0) {
    const std::string pat = "\"" + key + "\"";
    size_t i = s.find(pat, from);
    if (i == std::string::npos) return std::nullopt;
    return num_after(s, i + pat.size());
}

std::vector<Bar> read_bars(const std::string& path) {
    std::vector<Bar> out;
    std::ifstream f(path);
    if (!f) return out;
    std::string line;
    while (std::getline(f, line)) {
        Bar b{};
        if (std::sscanf(line.c_str(), "%ld %lf %lf %lf %lf %lf",
                        &b.t, &b.o, &b.h, &b.l, &b.c, &b.v) >= 5)
            out.push_back(b);
    }
    std::sort(out.begin(), out.end(), [](const Bar& a, const Bar& b) { return a.t < b.t; });
    return out;
}

// (epoch del minuto -> dir_delta_flow) del fichero de uw_flow_archive
std::map<long, double> read_delta(const std::string& path, std::string* err) {
    std::map<long, double> out;
    auto txt = slurp(path);
    if (!txt) { *err = "sin " + path; return out; }
    const std::string& s = *txt;
    size_t i = 0;
    while (true) {
        size_t t = s.find("\"timestamp\"", i);
        if (t == std::string::npos) break;
        size_t q1 = s.find('"', t + 11);          // comilla que ABRE el valor
        if (q1 == std::string::npos) break;
        size_t q2 = s.find('"', q1 + 1);          // comilla que lo CIERRA
        if (q1 == std::string::npos || q2 == std::string::npos) break;
        const std::string iso = s.substr(q1 + 1, q2 - q1 - 1);
        std::tm tm{};
        if (std::sscanf(iso.c_str(), "%d-%d-%dT%d:%d:%d", &tm.tm_year, &tm.tm_mon, &tm.tm_mday,
                        &tm.tm_hour, &tm.tm_min, &tm.tm_sec) == 6) {
            tm.tm_year -= 1900;
            tm.tm_mon -= 1;
            const long epoch = static_cast<long>(timegm(&tm));
            size_t nxt = s.find("\"timestamp\"", q2);
            auto d = field_num(s, "dir_delta_flow", q2);
            if (d && (nxt == std::string::npos || s.find("\"dir_delta_flow\"", q2) < nxt))
                out[epoch - epoch % 60] = *d;
        }
        i = q2 + 1;
    }
    if (out.empty()) *err = "0 filas legibles en " + path;
    return out;
}

Calib read_calib(const std::string& path, std::string* err) {
    Calib c;
    auto txt = slurp(path);
    if (!txt) { *err = "sin calibracion medida (" + path + ")"; return c; }
    const std::string& s = *txt;
    // celdas: los MFE/MAE del lado que se veta (largo dentro de divergencia bajista)
    size_t cell = s.find("LARGO dentro de divergencia BAJISTA");
    if (cell == std::string::npos) { *err = "calibracion sin la celda del veto"; return c; }
    auto mfe = field_num(s, "mfe_p60", cell);
    auto mae75 = field_num(s, "mae_p75", cell);
    auto mae90 = field_num(s, "mae_p90", cell);
    if (!mfe || !mae75 || !mae90) { *err = "calibracion sin MFE/MAE"; return c; }
    c.mfe_p60 = *mfe; c.mae_p75 = *mae75; c.mae_p90 = *mae90;
    size_t tests = s.find("\"tests\"");
    auto grab = [&](const char* dentro, double* dst, long* n) {
        size_t k = s.find(dentro, tests);
        if (k == std::string::npos) return false;
        auto d = field_num(s, "delta_wr", k);
        if (!d) return false;
        *dst = *d * 100.0;
        if (n) { auto nn = field_num(s, "n_dentro", k); *n = nn ? static_cast<long>(*nn) : 0; }
        return true;
    };
    bool ok = grab("LARGO dentro de divergencia BAJISTA", &c.pp_largo_bajista, &c.n_bajista);
    ok &= grab("CORTO dentro de divergencia BAJISTA", &c.pp_corto_bajista, nullptr);
    ok &= grab("CORTO dentro de divergencia ALCISTA", &c.pp_corto_alcista, &c.n_alcista);
    ok &= grab("LARGO dentro de divergencia ALCISTA", &c.pp_largo_alcista, nullptr);
    if (!ok) { *err = "calibracion sin los contrastes del veto"; return c; }
    c.ok = true;
    return c;
}

// ---------------------------------------------------------------- calculo

double atr_wilder(const std::vector<Bar>& b, size_t upto) {
    if (upto + 1 < static_cast<size_t>(kAtrN) + 1) return 0.0;
    double a = 0;
    for (int i = 1; i <= kAtrN; ++i) {
        const Bar& x = b[upto - kAtrN + i];
        const Bar& p = b[upto - kAtrN + i - 1];
        a += std::max(x.h - x.l, std::max(std::fabs(x.h - p.c), std::fabs(x.l - p.c)));
    }
    a /= kAtrN;
    for (size_t i = upto - kAtrN + 1; i <= upto; ++i) {
        const Bar& x = b[i];
        const Bar& p = b[i - 1];
        const double tr = std::max(x.h - x.l, std::max(std::fabs(x.h - p.c), std::fabs(x.l - p.c)));
        a = (a * (kAtrN - 1) + tr) / kAtrN;
    }
    return a;
}

int minute_et(long epoch) {
    const std::time_t t = epoch;
    std::tm lt{};
    localtime_r(&t, &lt);          // el reloj del Mac ES ET (ley de la casa)
    return lt.tm_hour * 60 + lt.tm_min;
}

struct State {
    std::string sym;
    int banda = 0;                  // +1 cierre fuera de la banda alta, -1 de la baja, 0 dentro
    bool refuerzo = false;          // ruptura de banda Y divergencia en el sentido del fade
    bool tiene_dato = false;
    std::string motivo;            // por que no hay estado (jamas silencio)
    double spot = 0, atr = 0, cumdelta = 0;
    const char* div = nullptr;     // "BAJISTA" | "ALCISTA" | nullptr
    int minutos = 0;               // cuantos minutos seguidos lleva la divergencia
    double objetivo = 0, stop = 0;
    long asof = 0;
};

State evaluate(const std::string& sym, const Calib& cal) {
    State st;
    st.sym = sym;
    std::string lower;
    for (char ch : sym) lower.push_back(static_cast<char>(std::tolower(ch)));

    const auto bars = read_bars("data/bars_" + lower + "_ibkr.txt");
    if (bars.size() < static_cast<size_t>(kAtrN + kDivWindow + 2)) {
        st.motivo = "barras insuficientes (" + std::to_string(bars.size()) + ")";
        return st;
    }
    std::string err;
    const char* tzday = nullptr;
    char day[16];
    if (const char* env = std::getenv("IBT_DIA")) {   // replay/verificacion: dia explicito
        std::snprintf(day, sizeof day, "%s", env);
        tzday = day;
    } else {
        std::time_t now = std::time(nullptr);
        std::tm lt{};
        localtime_r(&now, &lt);
        std::strftime(day, sizeof day, "%Y-%m-%d", &lt);
        tzday = day;
    }
    const auto delta = read_delta(std::string("data/history/") + tzday +
                                  "/uw_greek_flow_" + lower + ".json", &err);
    if (delta.empty()) { st.motivo = err; return st; }

    // recorrido de la sesion: delta acumulado alineado al minuto de la barra
    const long hoy0 = bars.back().t - (bars.back().t % 86400);
    (void)hoy0;
    std::vector<double> cum;
    std::vector<size_t> idx;
    double acc = 0;
    long sesion = -1;
    for (size_t i = 0; i < bars.size(); ++i) {
        const long m = bars[i].t - bars[i].t % 60;
        std::tm lt{};
        std::time_t tt = m;
        localtime_r(&tt, &lt);
        const long dia = lt.tm_year * 10000 + lt.tm_mon * 100 + lt.tm_mday;
        if (dia != sesion) { sesion = dia; acc = 0; cum.clear(); idx.clear(); }
        auto it = delta.find(m);
        if (it != delta.end()) acc += it->second;
        cum.push_back(acc);
        idx.push_back(i);
    }
    if (cum.size() < static_cast<size_t>(kDivWindow + 1)) {
        st.motivo = "sesion demasiado corta para la ventana de " + std::to_string(kDivWindow) + " min";
        return st;
    }
    const size_t last = cum.size() - 1;
    const size_t bi = idx[last];
    st.spot = bars[bi].c;
    st.asof = bars[bi].t;
    st.cumdelta = cum[last];
    st.atr = atr_wilder(bars, bi);
    if (st.atr <= 0) { st.motivo = "ATR no calculable todavia"; return st; }

    auto divergente = [&](size_t k) -> const char* {
        if (k + 1 < static_cast<size_t>(kDivWindow)) return nullptr;
        double hp = -1e18, lp = 1e18, hd = -1e18, ld = 1e18;
        for (size_t j = k + 1 - kDivWindow; j <= k; ++j) {
            hp = std::max(hp, bars[idx[j]].h);
            lp = std::min(lp, bars[idx[j]].l);
            hd = std::max(hd, cum[j]);
            ld = std::min(ld, cum[j]);
        }
        if (bars[idx[k]].h >= hp - 1e-9 && cum[k] < hd - 1e-9) return "BAJISTA";
        if (bars[idx[k]].l <= lp + 1e-9 && cum[k] > ld + 1e-9) return "ALCISTA";
        return nullptr;
    };

    const int mm = minute_et(bars[bi].t);
    if (!g_forzar && (mm < kRthOpen || mm >= kRthClose)) {
        st.motivo = "fuera de la ventana medida 09:45-15:40 ET";
        st.tiene_dato = true;
        return st;
    }
    if (g_dump) {
        for (size_t k = 0; k < cum.size(); ++k) {
            const char* d = divergente(k);
            std::printf("%ld %s %.4f %.0f\n", bars[idx[k]].t, d ? d : "-",
                        bars[idx[k]].c, cum[k]);
        }
    }
    // Bollinger(20,2) del ultimo minuto sobre las mismas barras
    if (bi + 1 >= static_cast<size_t>(kBB)) {
        double m = 0, m2 = 0;
        for (size_t j = bi + 1 - kBB; j <= bi; ++j) { m += bars[j].c; m2 += bars[j].c * bars[j].c; }
        m /= kBB;
        const double sd = std::sqrt(std::max(m2 / kBB - m * m, 0.0));
        if (sd > 0) {
            if (bars[bi].c > m + kBBK * sd) st.banda = 1;
            else if (bars[bi].c < m - kBBK * sd) st.banda = -1;
        }
    }
    st.div = divergente(last);
    // MEDIDO (scripts/bollinger_delta_study.py, 20.643 disparos): fadear la banda a secas da
    // edge +0,24 pp; exigiendo ademas la divergencia sube a +0,85 pp, consistente en las 6
    // celdas de barrera/horizonte. Sigue UNPROVEN (edge_lo -0,0012), asi que es un GATE de
    // confirmacion sobre un setup que ya existe, no una alerta nueva.
    if (st.div) {
        st.refuerzo = (st.banda == 1 && std::strcmp(st.div, "BAJISTA") == 0) ||
                      (st.banda == -1 && std::strcmp(st.div, "ALCISTA") == 0);
    }
    if (st.div) {
        for (size_t k = last + 1; k-- > 0;) {
            const char* d = divergente(k);
            if (d == nullptr || std::strcmp(d, st.div) != 0) break;
            ++st.minutos;
        }
        const int dir = std::strcmp(st.div, "BAJISTA") == 0 ? -1 : +1;
        st.objetivo = st.spot + dir * cal.mfe_p60 * st.atr;
        st.stop = st.spot - dir * cal.mae_p75 * st.atr;
    }
    st.tiene_dato = true;
    return st;
}

void write_json(const std::vector<State>& sts, const Calib& cal, const std::string& path) {
    std::string tmp = path + ".tmp";
    FILE* f = std::fopen(tmp.c_str(), "w");
    if (!f) { std::fprintf(stderr, "delta_imbalance: no puedo escribir %s\n", tmp.c_str()); return; }
    std::fprintf(f, "{\"asof\":%ld,\"w_div\":%d,\"uso\":\"VETO\",", (long)std::time(nullptr), kDivWindow);
    std::fprintf(f, "\"medido\":{\"pp_largo_en_bajista\":%.3f,\"pp_corto_en_bajista\":%.3f,"
                    "\"pp_largo_en_alcista\":%.3f,\"pp_corto_en_alcista\":%.3f,"
                    "\"n_bajista\":%ld,\"n_alcista\":%ld,\"mfe_p60_atr\":%.3f,\"mae_p75_atr\":%.3f},",
                 cal.pp_largo_bajista, cal.pp_corto_bajista, cal.pp_largo_alcista,
                 cal.pp_corto_alcista, cal.n_bajista, cal.n_alcista, cal.mfe_p60, cal.mae_p75);
    std::fprintf(f, "\"syms\":{");
    bool first = true;
    for (const auto& s : sts) {
        if (!first) std::fprintf(f, ",");
        first = false;
        std::fprintf(f, "\"%s\":{", s.sym.c_str());
        if (!s.tiene_dato) {
            std::fprintf(f, "\"motivo\":\"%s\"}", s.motivo.c_str());
            continue;
        }
        std::fprintf(f, "\"spot\":%.4f,\"atr\":%.4f,\"cumdelta\":%.0f,\"asof\":%ld",
                     s.spot, s.atr, s.cumdelta, s.asof);
        if (!s.motivo.empty()) std::fprintf(f, ",\"motivo\":\"%s\"", s.motivo.c_str());
        std::fprintf(f, ",\"banda\":%d,\"refuerzo_bollinger\":%s", s.banda,
                     s.refuerzo ? "true" : "false");
        if (s.div) {
            const bool bajista = std::strcmp(s.div, "BAJISTA") == 0;
            std::fprintf(f, ",\"divergencia\":\"%s\",\"minutos\":%d,"
                            "\"veta_largos\":%s,\"veta_cortos\":%s,"
                            "\"objetivo\":%.4f,\"stop\":%.4f",
                         s.div, s.minutos, bajista ? "true" : "false",
                         bajista ? "false" : "true", s.objetivo, s.stop);
        } else {
            std::fprintf(f, ",\"divergencia\":null");
        }
        std::fprintf(f, "}");
    }
    std::fprintf(f, "}}\n");
    std::fclose(f);
    std::rename(tmp.c_str(), path.c_str());
}

std::vector<std::string> fleet() {
    std::vector<std::string> out;
    std::ifstream f("data/fleet.txt");
    std::string s;
    while (f >> s) out.push_back(s);
    return out;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> syms;
    bool quiet = false;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--quiet") quiet = true;
        else if (a == "--forzar") g_forzar = true;
        else if (a == "--dump") { g_dump = true; g_forzar = true; }
        else if (a == "--sym" && i + 1 < argc) syms.push_back(argv[++i]);
        else if (a.rfind("--", 0) != 0) syms.push_back(a);
    }
    if (syms.empty()) syms = fleet();
    if (syms.empty()) {
        std::fprintf(stderr, "delta_imbalance ROTO: data/fleet.txt vacio\n");
        return 2;
    }
    std::string err;
    const Calib cal = read_calib("data/research/delta_imbalance_veto.json", &err);
    if (!cal.ok) {
        // fail-loud: sin la medida no hay veto que afirmar (jamas un numero plausible)
        std::fprintf(stderr, "delta_imbalance ROTO: %s\n", err.c_str());
        return 3;
    }
    std::vector<State> sts;
    for (const auto& s : syms) {
        std::string up;
        for (char c : s) up.push_back(static_cast<char>(std::toupper(c)));
        sts.push_back(evaluate(up, cal));
    }
    write_json(sts, cal, "data/delta_imbalance.json");
    if (!quiet) {
        for (const auto& s : sts) {
            if (!s.tiene_dato) { std::printf("%-6s SIN DATO: %s\n", s.sym.c_str(), s.motivo.c_str()); continue; }
            if (s.div)
                std::printf("%-6s %.2f  DIVERGENCIA %s (%d min)  veta %s  objetivo %.2f  stop %.2f  [%.2f pp medidos, n=%ld]\n",
                            s.sym.c_str(), s.spot, s.div, s.minutos,
                            std::strcmp(s.div, "BAJISTA") == 0 ? "LARGOS" : "CORTOS",
                            s.objetivo, s.stop,
                            std::strcmp(s.div, "BAJISTA") == 0 ? cal.pp_largo_bajista : cal.pp_corto_alcista,
                            std::strcmp(s.div, "BAJISTA") == 0 ? cal.n_bajista : cal.n_alcista);
            else
                std::printf("%-6s %.2f  sin divergencia%s\n", s.sym.c_str(), s.spot,
                            s.motivo.empty() ? "" : ("  (" + s.motivo + ")").c_str());
        }
    }
    return 0;
}
