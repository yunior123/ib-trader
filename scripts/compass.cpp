// compass.cpp — LA BRUJULA: la flecha apunta al PROXIMO movimiento, no al que ya paso.
// Orden Yunior 2026-07-25: "la flecha deberia ser como una brujula; si a las 10am SPY esta
// tocando el Muro put de 740 y hay flujo masivo de puts con posibilidad de rebote fuerte,
// entonces la flecha debe moverse hacia ARRIBA, y asi para todos los casos, ultraprecisa"
// + "puede revertir fuerte o solo un poco: calculalo y mueve la flecha en consecuencia"
// + "python solo para test, la computacion en C++".
//
// POR QUE NO SIRVE LA MEDIA PONDERADA (el bug de FORMA que esto arregla)
// ---------------------------------------------------------------------
// direction_view.py combinaba TODOS los factores en una media ponderada. En el escenario de
// arriba, con los pesos reales del archivo:
//     walls        +0.96 x1.0  = +0.96   <- piso, rebote
//     captain_flow +1.00 x1.2  = +1.20   <- piso, rebote (reglas 11 y 12)
//     bollinger    +0.67 x1.15 = +0.77   <- sobreventa, rebote
//     flip         -0.80 x1.5  = -1.20   <- ya cayo
//     fleet        -1.00 x1.4  = -1.40   <- ya cayo
//     components   -0.70 x1.3  = -0.91   <- ya cayo
//     momentum     -1.00 x1.0  = -1.00   <- ya cayo
//     magnet       -1.00 x1.1  = -1.10   <- ya cayo
//     score = -2.68/9.65 = -0.278  ->  FLECHA ABAJO 61%
// ...justo cuando la doctrina canta REBOTE. La causa raiz no es un peso mal puesto: una media
// mezcla factores de DONDE HA ESTADO (momentum, lado del flip, amplitud, flota, iman) con los
// de DONDE VA A GIRAR (Muro, %B extremo, flujo del capitan, agotamiento). En TODO extremo real
// los de tendencia estan maximamente en contra, asi que promediar SIEMPRE diluye la reversion.
//
// LA BRUJULA: maquina de estados. EL ESTADO FIJA EL SIGNO; los factores solo modulan la
// confianza DENTRO del estado. Y en reversion el momentum cambia de papel: su magnitud es
// COMBUSTIBLE (cuanto mas fuerte cayo hacia un piso IMPRESO con puts inundando, mas elastico
// el latigazo), no un voto en contra.
//
// ESTADOS (excluyentes, por precedencia)
//   SIN LECTURA          sin mapa / libro THIN / barras con hueco -> plana, y DICE por que
//   REVERSION EN EXTREMO nivel IMPRESO + >=2 familias + ningun veto -> la brujula GIRA
//   CONTINUACION         un veto de doctrina activo -> NO gira ("no fadear")
//   APROXIMANDO          va hacia el nivel pero AUN NO HA IMPRESO -> flecha hueca
//   CAJA / PIN           gamma+ densa entre Muros sin extremo -> plana
//
// VETOS (doctrina existente, no inventada)
//   V1 band-walk >=2 TF a favor del movimiento     (regla 1)
//   V2 regimen NEG sin pin impreso                 (memoria negative-gamma-whipsaw)
//   V3 spot bajo el VT congelado                   (fadear prohibido)
//   V4 el Muro es TRAMPILLA, no pin                (gex_core *_kind)
//   V5 3+ toques del Muro                          (protocolo imanes: exhausto)
//   V6 dia de catalizador del lider                (excepcion de la regla 11)
//
// AMPLITUD (cuanto): minimo de restricciones, nunca prometer mas de lo que cabe:
//   room (siguiente nivel; jamas a traves de un Muro) / pull (media de Bollinger, iman SMA20)
//   / retrace (50% de la pata) / em_left (lo que queda del expected move del dia)
//
// PRINT O NADA: sin 2 lecturas el estado es APROXIMANDO, jamas la flecha confiada.
// HISTERESIS: un estado nuevo necesita 2 computos consecutivos (regla 3).
// HONESTIDAD: prob_source='medido' solo con celda propia n>=30; si no 'doctrina', topada.
//   NO se usa prob_retroceso_50 como prob de la flecha: condiciona en "hubo un impulso", no
//   en "hubo NUESTRO setup". Se publica en amplitude.retrace_prob como lo que es.
//
// SENAL-SOLAMENTE: escribe JSON de diagnostico, jamas ordena.
//   compilar: ./scripts/build_compass.sh
//   uso: ./compass qqq spy nvda            (lee data/, escribe data/compass_<sym>.json)
//        ./compass --loop 5 qqq            (bucle cada 5s)
//        ./compass --ev-stdin < ev.json    (modo TEST: evidencia inyectada -> stdout)
#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

// ------------------------------- umbrales -----------------------------------
namespace K {
constexpr double NEAR_PCT       = 0.0015;  // 0.15% del spot = "en el nivel"
constexpr int    PRINT_MIN      = 2;       // PRINT O NADA (regla 2)
constexpr int    PRINT_LOOKBACK = 8;       // barras 1m donde buscar las lecturas
constexpr double APPROACH_EM    = 0.35;    // <0.35 EM al nivel = aproximando
constexpr double FLOW_MIN       = 0.25;    // |flujo capitan| minimo para contar
constexpr double PCTB_HI        = 0.85;
constexpr double PCTB_LO        = 0.15;
constexpr int    BANDWALK_TF_MIN= 2;       // >=2 TF a favor = continuacion (regla 1)
constexpr int    TOUCH_EXHAUST  = 3;       // 3+ toques = muro exhausto
constexpr double FUEL_SAT       = 2.5;     // |z| de saturacion del combustible
constexpr double FUEL_MAX       = 8.0;     // puntos de prob que aporta el combustible
constexpr double DOCTRINE_CAP   = 78.0;    // tope de prob cuando la fuente es doctrina
constexpr int    HYST_N         = 2;       // computos consecutivos para cambiar de estado
constexpr int    CALIB_MIN_N    = 30;      // n minima para llamar a algo "medido"
constexpr double FORCE_MAX_AGE  = 120.0;   // force.json solo si es de hace <2min
}

static const char* S_REV  = "REVERSION EN EXTREMO";
static const char* S_CONT = "CONTINUACION";
static const char* S_APPR = "APROXIMANDO";
static const char* S_BOX  = "CAJA / PIN";
static const char* S_NONE = "SIN LECTURA";

static double clampd(double x, double lo, double hi) { return std::max(lo, std::min(hi, x)); }
static int sgn(double x) { return x > 0 ? 1 : (x < 0 ? -1 : 0); }

// --------------------------- JSON minimo (idiom del repo, flow_pulse.cpp) ---------------
static std::optional<double> jnum(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t')) ++p;
    if (p < s.size() && (s[p] == 'n' || s[p] == '"')) return std::nullopt;  // null / string
    double out{};
    auto [ptr, ec] = std::from_chars(s.data() + p, s.data() + s.size(), out);
    if (ec != std::errc{}) return std::nullopt;
    (void)ptr;
    return out;
}
static std::optional<std::string> jstr(std::string_view s, std::string_view key) {
    // OJO: no se puede exigir la comilla pegada a los dos puntos. json.dump() de Python
    // escribe ": " CON espacio, y asi salen charts/data/levels_<sym>.json y data/*.json que
    // generan los scripts. Hay que saltar los blancos o el valor se lee como ausente.
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n')) ++p;
    if (p >= s.size() || s[p] != '"') return std::nullopt;   // null / numero / objeto
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
// devuelve el texto del valor de `key` cuando es un array [...] (respeta anidamiento)
static std::optional<std::string> jarr(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && s[p] == ' ') ++p;
    if (p >= s.size() || s[p] != '[') return std::nullopt;
    int depth = 0;
    for (size_t i = p; i < s.size(); ++i) {
        if (s[i] == '[') ++depth;
        else if (s[i] == ']') { if (--depth == 0) return std::string(s.substr(p, i - p + 1)); }
    }
    return std::nullopt;
}
// trocea un array de objetos en sus "{...}"
static std::vector<std::string> jobjs(const std::string& arr) {
    std::vector<std::string> out;
    int depth = 0; size_t st = 0;
    for (size_t i = 0; i < arr.size(); ++i) {
        if (arr[i] == '{') { if (depth++ == 0) st = i; }
        else if (arr[i] == '}') { if (--depth == 0) out.push_back(arr.substr(st, i - st + 1)); }
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

// ------------------------------- modelo -------------------------------------
struct Bar { long t; double o, h, l, c, v; };

struct Level {
    double price = 0;
    std::string kind;        // "Muro put" | "Muro call" | "Muro absoluto" | "POC" | "flip"
    std::string wall_kind;   // "pin" | "trampilla" | ""
    int touch_idx = -1;      // -1 = desconocido
    // derivados
    double dist = 0; int above = 0; int prints = 0; bool printed = false;
};

struct Ev {
    std::string sym = "?";
    std::optional<double> spot, em, flip, r6, r15, z6, pctb_1m, pctb_15m, flow,
        vt, bb_mid, leg_pct, em_used_pct, exhaustion;
    std::string regime, force_phase, book_label;
    std::optional<double> book_coef;
    int bandwalk_tf = 0, bandwalk_dir = 0, candle_bias = 0;
    bool leader_catalyst = false, bars_contig = true;
    std::optional<double> now_min;
    std::vector<Level> levels;
    std::vector<Bar> bars;
    // celda de calibracion propia (calibration_ledger): lo unico que puede decir "medido"
    std::optional<double> calib_lo; std::optional<double> calib_n;
};

struct Amp {
    bool ok = false;
    double amp_pct = 0, amp_price = 0, mag = 0, ratio_em = 0;
    std::string grade, binding, retrace_src;
    std::optional<double> retrace_prob, retrace_n, leg_minutes_median;
    bool capped_by_rule11 = false;
    std::vector<std::pair<std::string, double>> constraints;
};

struct Out {
    std::string sym, state, state_pending, dir = "flat", prob_source = "doctrina";
    int prob = 50; bool pending_print = false;
    int families = 0;
    std::vector<std::string> families_why, vetoes, fading, state_why;
    bool has_level = false; Level level;
    Amp amp;
};

// --------------------------- PRINT O NADA ----------------------------------
static int prints_at(const std::vector<Bar>& bars, double level, double spot) {
    if (bars.empty() || level == 0 || spot == 0) return 0;
    double band = spot * K::NEAR_PCT;
    int n = 0;
    size_t start = bars.size() > (size_t)K::PRINT_LOOKBACK ? bars.size() - K::PRINT_LOOKBACK : 0;
    for (size_t i = start; i < bars.size(); ++i)
        if (bars[i].l - band <= level && level <= bars[i].h + band) ++n;
    return n;
}

// El nivel que el precio esta PROBANDO AHORA. Tres reglas, en este orden:
//
//  1. Si un nivel se esta TOCANDO (dentro de NEAR y con lecturas), ESE manda, venga el precio
//     de donde venga. Es lo que pidio Yunior 2026-07-25: "la flecha tambien se mueve si choca
//     un call wall en rebote". Durante el rebote r6 (6 barras) SIGUE siendo negativo porque la
//     ventana todavia incluye la caida, asi que filtrar por "el lado del que viene" se perderia
//     el Muro call que acaba de chocar. El toque tiene prioridad sobre la procedencia.
//  2. Si no se toca ninguno, el del lado hacia el que VA el precio (el que se aproxima).
//  3. Sin momentum, el mas cercano en valor absoluto.
static std::optional<Level> nearest_level(const Ev& ev) {
    if (!ev.spot || ev.levels.empty()) return std::nullopt;
    double spot = *ev.spot;
    auto finish = [&](Level c) {
        c.dist = std::fabs(c.price - spot) / spot;
        c.above = c.price > spot ? 1 : -1;
        c.prints = prints_at(ev.bars, c.price, spot);
        c.printed = c.prints >= K::PRINT_MIN;
        return c;
    };
    // (1) nivel EN CONTACTO: prioridad absoluta. Criterio ESTRICTO — dentro de NEAR_PCT y con
    // el print completo. Con una zona ancha, un Muro que solo esta cerca (y que lo unico que
    // hace es recortar el recorrido del rebote) se confundia con el nivel bajo prueba.
    std::optional<Level> touching;
    for (const auto& L : ev.levels) {
        if (L.price == 0) continue;
        if (std::fabs(L.price - spot) / spot > K::NEAR_PCT) continue;
        Level c = finish(L);
        if (!c.printed) continue;
        if (!touching || c.prints > touching->prints ||
            (c.prints == touching->prints && c.dist < touching->dist)) touching = c;
    }
    if (touching) return touching;
    // (2)/(3) hacia donde va el precio; sin momentum, el mas cercano
    int side = sgn(ev.r6.value_or(0.0));
    auto pick = [&](bool filter) -> std::optional<Level> {
        std::optional<Level> best;
        for (const auto& L : ev.levels) {
            if (L.price == 0) continue;
            if (filter && side != 0) {
                int s = sgn(L.price - spot);
                if (s != side && s != 0) continue;
            }
            Level c = finish(L);
            if (!best || c.dist < best->dist) best = c;
        }
        return best;
    };
    auto best = side != 0 ? pick(true) : std::nullopt;
    if (!best) best = pick(false);
    return best;
}

static int rebound_dir(const Level& L, const Ev& ev) {
    if (L.above > 0) return -1;
    if (L.above < 0) return 1;
    return ev.r6.value_or(0.0) < 0 ? 1 : -1;
}

// familias INDEPENDIENTES que confirman el giro hacia rdir
static void families(const Ev& ev, int rdir, std::vector<std::string>& fam) {
    char buf[160];
    if (ev.flow && std::fabs(*ev.flow) >= K::FLOW_MIN && sgn(*ev.flow) == rdir) {
        snprintf(buf, sizeof buf, "flujo capitan %s (%+.2f)",
                 rdir > 0 ? "puts=piso" : "calls=techo", *ev.flow);
        fam.emplace_back(buf);
    }
    if (ev.pctb_1m && ev.pctb_15m) {
        if (rdir > 0 && *ev.pctb_1m <= K::PCTB_LO && *ev.pctb_15m <= K::PCTB_LO) {
            snprintf(buf, sizeof buf, "%%B 1m %.2f y 15m %.2f extremo bajo", *ev.pctb_1m, *ev.pctb_15m);
            fam.emplace_back(buf);
        } else if (rdir < 0 && *ev.pctb_1m >= K::PCTB_HI && *ev.pctb_15m >= K::PCTB_HI) {
            snprintf(buf, sizeof buf, "%%B 1m %.2f y 15m %.2f extremo alto", *ev.pctb_1m, *ev.pctb_15m);
            fam.emplace_back(buf);
        }
    }
    if (ev.force_phase == "AGOTAMIENTO" || ev.force_phase == "GIRO")
        fam.emplace_back("fuerza en " + ev.force_phase);
    if (ev.candle_bias != 0 && sgn((double)ev.candle_bias) == rdir)
        fam.emplace_back("vela de reversion");
}

static void vetoes_of(const Ev& ev, const Level& L, int rdir, std::vector<std::string>& v) {
    char buf[200];
    int move = sgn(ev.r6.value_or(0.0));
    if (ev.bandwalk_tf >= K::BANDWALK_TF_MIN && ev.bandwalk_dir != 0 &&
        sgn((double)ev.bandwalk_dir) == move && move == -rdir) {
        snprintf(buf, sizeof buf, "band-walk en %d TF a favor: continuacion, NO fadear", ev.bandwalk_tf);
        v.emplace_back(buf);
    }
    if (ev.regime == "NEG" && L.wall_kind != "pin")
        v.emplace_back("regimen NEG (acelerador): el nivel no es piso, NO fadear en el aire");
    if (ev.vt && ev.spot && *ev.spot < *ev.vt) {
        snprintf(buf, sizeof buf, "bajo el VT %.2f congelado: fadear prohibido", *ev.vt);
        v.emplace_back(buf);
    }
    if (L.wall_kind == "trampilla") {
        snprintf(buf, sizeof buf, "%s es TRAMPILLA (gamma NEG), no piso",
                 L.kind.empty() ? "el nivel" : L.kind.c_str());
        v.emplace_back(buf);
    }
    if (L.touch_idx >= K::TOUCH_EXHAUST) {
        snprintf(buf, sizeof buf, "%dº toque: muro exhausto -> lado de la ruptura", L.touch_idx);
        v.emplace_back(buf);
    }
    if (ev.leader_catalyst)
        v.emplace_back("catalizador del lider: la ballena puede ser continuacion");
}

// ------------------- retrocesos MEDIDOS (data/momentum_decay.json) ----------
struct DecayCell { double n = 0, ext_med = 0, prob_ret50 = 0, med_min = 0; bool ok = false; std::string src; };

static std::string json_section(const std::string& all, const std::string& key) {
    auto p = all.find("\"" + key + "\"");
    if (p == std::string::npos) return {};
    p = all.find('{', p);
    if (p == std::string::npos) return {};
    int depth = 0;
    for (size_t i = p; i < all.size(); ++i) {
        if (all[i] == '{') ++depth;
        else if (all[i] == '}') { if (--depth == 0) return all.substr(p, i - p + 1); }
    }
    return {};
}

static DecayCell decay_cell(const std::string& decay_json, const std::string& sym,
                            int move_dir, double now_min) {
    DecayCell c;
    if (decay_json.empty()) return c;
    const char* leg = move_dir < 0 ? "bear" : "bull";
    const char* ses = now_min < 12 * 60 ? "manana" : "tarde";
    auto take = [&](const std::string& blob, const char* src) {
        auto n = jnum(blob, "n");
        if (!n || *n < K::CALIB_MIN_N) return false;
        c.n = *n; c.ext_med = jnum(blob, "ext_mediana_pct").value_or(0);
        c.prob_ret50 = jnum(blob, "prob_retroceso_50").value_or(0);
        c.med_min = jnum(blob, "mediana_min").value_or(0);
        c.src = src; c.ok = true; return true;
    };
    // celda del propio ticker solo si tiene n suficiente; si es fina, mejor el agregado
    std::string pt = json_section(decay_json, "por_ticker");
    if (!pt.empty()) {
        std::string s = json_section(json_section(pt, sym), leg);
        if (!s.empty() && take(json_section(s, ses), "medido")) return c;
    }
    std::string ag = json_section(json_section(decay_json, "agregado"), leg);
    if (!ag.empty()) {
        if (take(json_section(ag, ses), "medido-agregado")) return c;
        if (take(json_section(ag, "todo"), "medido-agregado")) return c;
    }
    return c;
}

// ------------------------------- AMPLITUD ----------------------------------
static Amp amplitude(const Ev& ev, int rdir, const std::string& decay_json) {
    Amp a;
    if (!ev.spot || rdir == 0) return a;
    double spot = *ev.spot;
    double em_pct = (ev.em.value_or(spot * 0.02) / spot) * 100.0;
    std::vector<std::pair<std::string, double>> cons;
    auto put = [&](const char* k, double v) { cons.emplace_back(k, v); };

    // room: siguiente nivel estructural en el sentido del rebote (excluye el que se toca).
    // Doctrina imanes: JAMAS contar con atravesar un Muro intermedio.
    auto touched = nearest_level(ev);
    double tp = touched ? touched->price : 0.0;
    double nxt = 0;
    for (const auto& L : ev.levels) {
        if (L.price == 0 || L.price == tp) continue;
        if ((rdir > 0 && L.price > spot) || (rdir < 0 && L.price < spot))
            if (nxt == 0 || std::fabs(L.price - spot) < std::fabs(nxt - spot)) nxt = L.price;
    }
    if (nxt != 0) put("room", std::fabs(nxt - spot) / spot * 100.0);

    // pull: la media de Bollinger como iman de reversion (efecto iman a la SMA20)
    if (ev.bb_mid && sgn(*ev.bb_mid - spot) == rdir)
        put("pull", std::fabs(*ev.bb_mid - spot) / spot * 100.0);

    // retrace: 50% de la pata + extension mediana MEDIDA
    DecayCell dc = decay_cell(decay_json, ev.sym, -rdir, ev.now_min.value_or(600.0));
    if (ev.leg_pct) put("retrace", std::fabs(*ev.leg_pct) * 0.5);
    if (dc.ok && dc.ext_med > 0) put("ext_medido", dc.ext_med);

    // em_left: techo por presupuesto de movimiento del dia
    if (ev.em_used_pct && em_pct > 0)
        put("em_left", std::max(0.0, em_pct - std::fabs(*ev.em_used_pct)));

    if (cons.empty()) return a;
    double upside = 0; bool have_up = false;
    for (auto& [k, v] : cons)
        if (k == "pull" || k == "retrace" || k == "ext_medido") { upside = std::max(upside, v); have_up = true; }
    if (!have_up || upside <= 0) {
        upside = cons.front().second;
        for (auto& [k, v] : cons) upside = std::min(upside, v);
    }
    double amp = upside; bool capped = false;
    for (auto& [k, v] : cons)
        if (k == "room" || k == "em_left") { amp = std::min(amp, v); capped = true; }
    amp = std::max(0.0, amp);

    double ratio = em_pct > 0 ? amp / em_pct : 0.0;
    a.grade = ratio >= 0.50 ? "LATIGAZO" : (ratio >= 0.20 ? "REBOTE" : "SCALP");
    // regla 11 (espada-ballena): si el giro lo sostiene SOLO el flujo, no pedir el latigazo
    bool flow_only = ev.flow.has_value() && !ev.bb_mid.has_value() && !ev.leg_pct.has_value();
    if (flow_only && a.grade == "LATIGAZO") { a.grade = "REBOTE"; a.capped_by_rule11 = true; }

    if (capped) {
        std::string bk; double bv = 1e18;
        for (auto& [k, v] : cons) if (v < bv) { bv = v; bk = k; }
        a.binding = bk;
    }
    a.ok = true;
    a.amp_pct = amp;
    a.amp_price = spot * (1.0 + rdir * amp / 100.0);
    a.mag = clampd(ratio / 0.6, 0.0, 1.0);
    a.ratio_em = ratio;
    a.constraints = cons;
    if (dc.ok) {
        a.retrace_prob = dc.prob_ret50; a.retrace_n = dc.n;
        a.leg_minutes_median = dc.med_min; a.retrace_src = dc.src;
    }
    return a;
}

// ------------------------------ probabilidad --------------------------------
// Orden: (1) celda propia de calibration_ledger n>=30 -> "medido"; (2) prior DOCTRINAL topado.
// NO se usa prob_retroceso_50 aqui: condiciona en "hubo un impulso", no en "hubo NUESTRO
// setup (nivel impreso + >=2 familias + sin vetos)". Son poblaciones distintas; usarla
// inflaria la flecha al 90% con una n que no es de este setup. Va en amplitude.retrace_prob.
static std::pair<int, std::string> prob_of(const std::string& state, int nfam, const Ev& ev,
                                          const Amp& amp) {
    if (ev.calib_n && *ev.calib_n >= K::CALIB_MIN_N && ev.calib_lo)
        return {(int)std::lround(clampd(*ev.calib_lo * 100.0, 50, 90)), "medido"};
    double base;
    if (state == S_REV) {
        base = nfam >= 4 ? 72 : (nfam == 3 ? 68 : 62);
        // MOMENTUM COMO COMBUSTIBLE: cuanto mas fuerte llego, mas elastico el latigazo
        double z = ev.z6 ? *ev.z6 : (ev.r6 ? *ev.r6 / 0.5 : 0.0);
        base += clampd(std::fabs(z) / K::FUEL_SAT, 0.0, 1.0) * K::FUEL_MAX;
    } else if (state == S_CONT) {
        base = ev.bandwalk_tf >= K::BANDWALK_TF_MIN ? 65 : 60;
    } else if (state == S_APPR) {
        base = (nfam >= 4 ? 72 : (nfam == 3 ? 68 : 62)) - 8;   // aun no ha impreso
    } else {
        base = 50;
    }
    (void)amp;
    return {(int)std::lround(clampd(base, 50, K::DOCTRINE_CAP)), "doctrina"};
}

// ------------------------------- histeresis ---------------------------------
struct Hist { std::string state, cand; int n = 0; bool has = false; };
static std::unordered_map<std::string, Hist> g_hist;

// ------------------------------- classify -----------------------------------
static Out classify(const Ev& ev, Hist* hist, const std::string& decay_json) {
    Out o; o.sym = ev.sym;
    auto lvl = nearest_level(ev);
    int rdir = 0;
    std::vector<std::string>& why = o.state_why;

    if (!ev.spot) { o.state = S_NONE; why.emplace_back("sin spot"); }
    else if (!ev.bars_contig) {
        o.state = S_NONE;
        why.emplace_back("barras no contiguas (hueco de feed): no se afirma nada");
    } else if (ev.book_label == "THIN" || (ev.book_coef && *ev.book_coef == 0.0)) {
        o.state = S_NONE;
        why.emplace_back("libro THIN: los niveles gamma son decoracion en este nombre");
    } else if (ev.regime.empty() || !lvl) {
        o.state = S_NONE;
        why.emplace_back(ev.regime.empty() ? "sin mapa GEX fresco" : "sin niveles estructurales");
    } else {
        rdir = rebound_dir(*lvl, ev);
        families(ev, rdir, o.families_why);
        o.families = (int)o.families_why.size();
        vetoes_of(ev, *lvl, rdir, o.vetoes);
        double spot = *ev.spot;
        double em_pct = (ev.em.value_or(spot * 0.02)) / spot;
        bool near = lvl->dist <= K::NEAR_PCT * 2;
        bool approaching = lvl->dist <= std::max(K::APPROACH_EM * em_pct, K::NEAR_PCT * 2);
        char lbl[96];
        snprintf(lbl, sizeof lbl, "%s %.2f", lvl->kind.empty() ? "nivel" : lvl->kind.c_str(), lvl->price);

        if (!o.vetoes.empty() && (near || approaching)) {
            o.state = S_CONT;
            int move = sgn(ev.r6.value_or(0.0));
            if (move == 0 && ev.flip) move = spot >= *ev.flip ? 1 : -1;
            o.dir = move > 0 ? "up" : (move < 0 ? "down" : "flat");
            why.emplace_back(o.vetoes[0].find("NO fadear") == std::string::npos
                                 ? o.vetoes[0] + ": NO fadear" : o.vetoes[0]);
            if (o.vetoes.size() > 1) why.emplace_back(o.vetoes[1]);
            if (!o.families_why.empty()) {
                std::string s = "se ignoran " + std::to_string(o.families) + " familia(s) de giro: ";
                for (size_t i = 0; i < o.families_why.size(); ++i)
                    s += (i ? "; " : "") + o.families_why[i];
                o.fading.push_back(s);
            }
        } else if (lvl->printed && o.families >= 2) {
            o.state = S_REV;
            o.dir = rdir > 0 ? "up" : "down";
            char b[160]; snprintf(b, sizeof b, "%s IMPRESO (%d lecturas)", lbl, lvl->prints);
            why.emplace_back(b);
            for (size_t i = 0; i < o.families_why.size() && i < 3; ++i) why.push_back(o.families_why[i]);
            if (ev.r6 && sgn(*ev.r6) == -rdir) {
                snprintf(b, sizeof b,
                         "momentum %+.2f%% (es el COMBUSTIBLE del latigazo, no un voto en contra)", *ev.r6);
                o.fading.emplace_back(b);
            }
            if (ev.flip && sgn(spot - *ev.flip) == -rdir) {
                snprintf(b, sizeof b, "spot del lado %s del flip %.2f", rdir > 0 ? "bajo" : "sobre", *ev.flip);
                o.fading.emplace_back(b);
            }
        } else if (approaching && o.families >= 2) {
            o.state = S_APPR;
            o.dir = rdir > 0 ? "up" : "down";
            char b[160];
            snprintf(b, sizeof b, "aproximando %s — esperando print (%d/%d)", lbl, lvl->prints, K::PRINT_MIN);
            why.emplace_back(b);
            for (size_t i = 0; i < o.families_why.size() && i < 2; ++i) why.push_back(o.families_why[i]);
        } else if (ev.regime == "POS" && !near) {
            o.state = S_BOX;
            why.emplace_back("gamma+ entre Muros, sin extremo: caja");
        } else {
            o.state = S_CONT;
            int m = sgn(ev.r6.value_or(0.0));
            o.dir = m > 0 ? "up" : (m < 0 ? "down" : "flat");
            why.emplace_back("sin extremo confirmado: manda la tendencia");
        }
    }

    // histeresis (regla 3): un estado nuevo necesita HYST_N computos consecutivos
    if (hist) {
        std::string want = o.state;
        if (!hist->has || hist->state == want) {
            hist->has = true; hist->state = want; hist->cand = want; hist->n = 0;
        } else if (hist->cand == want) {
            hist->n += 1;
            if (hist->n + 1 >= K::HYST_N) { hist->state = want; hist->cand = want; hist->n = 0; }
            else {
                o.state_pending = want; o.state = hist->state;
                char b[120]; snprintf(b, sizeof b, "estado %s pendiente de confirmar (%d/%d)",
                                      want.c_str(), hist->n + 1, K::HYST_N);
                why.insert(why.begin(), b);
            }
        } else {
            hist->cand = want; hist->n = 0;
            o.state_pending = want; o.state = hist->state;
            char b[120]; snprintf(b, sizeof b, "estado %s pendiente de confirmar (1/%d)",
                                  want.c_str(), K::HYST_N);
            why.insert(why.begin(), b);
        }
        if (!o.state_pending.empty() && (o.state == S_BOX || o.state == S_NONE)) o.dir = "flat";
    }

    // AMPLITUD: cuanto se espera que se mueva (y con ella se escala la flecha)
    if ((o.state == S_REV || o.state == S_APPR) && rdir != 0) {
        o.amp = amplitude(ev, rdir, decay_json);
        if (o.amp.ok) {
            char b[240];
            if (o.amp.retrace_prob && o.amp.retrace_n)
                snprintf(b, sizeof b, "%s esperado %+.2f%% -> %.2f (retroceso 50%% medido %.0f%%, n=%.0f)",
                         o.amp.grade.c_str(), rdir * o.amp.amp_pct, o.amp.amp_price,
                         *o.amp.retrace_prob * 100.0, *o.amp.retrace_n);
            else
                snprintf(b, sizeof b, "%s esperado %+.2f%% -> %.2f",
                         o.amp.grade.c_str(), rdir * o.amp.amp_pct, o.amp.amp_price);
            why.emplace_back(b);
            if (o.amp.capped_by_rule11)
                why.emplace_back("solo flujo lo sostiene: scalp seguro, no pedir el latigazo (regla 11)");
        }
    }

    auto [p, src] = prob_of(o.state, o.families, ev, o.amp);
    o.prob = p; o.prob_source = src;
    o.pending_print = (o.state == S_APPR);
    if (o.state == S_BOX || o.state == S_NONE) { o.prob = 50; o.dir = "flat"; o.amp = Amp{}; }
    if (why.size() > 6) why.resize(6);
    if (lvl) { o.has_level = true; o.level = *lvl; }
    return o;
}

// ------------------------------- salida JSON --------------------------------
static void arr_out(std::string& s, const char* key, const std::vector<std::string>& v) {
    s += "\"" + std::string(key) + "\":[";
    for (size_t i = 0; i < v.size(); ++i) { if (i) s += ","; s += "\"" + jesc(v[i]) + "\""; }
    s += "],";
}
static std::string to_json(const Out& o) {
    std::string s = "{";
    char b[512];
    s += "\"sym\":\"" + jesc(o.sym) + "\",";
    s += "\"state\":\"" + jesc(o.state) + "\",";
    s += "\"state_pending\":" + (o.state_pending.empty() ? std::string("null")
                                 : "\"" + jesc(o.state_pending) + "\"") + ",";
    s += "\"dir\":\"" + o.dir + "\",";
    snprintf(b, sizeof b, "\"prob\":%d,\"prob_source\":\"%s\",\"pending_print\":%s,\"families\":%d,",
             o.prob, o.prob_source.c_str(), o.pending_print ? "true" : "false", o.families);
    s += b;
    arr_out(s, "families_why", o.families_why);
    arr_out(s, "vetoes", o.vetoes);
    arr_out(s, "fading", o.fading);
    arr_out(s, "state_why", o.state_why);
    if (o.has_level) {
        snprintf(b, sizeof b,
                 "\"level\":{\"price\":%.4f,\"kind\":\"%s\",\"wall_kind\":%s,\"touch_idx\":%s,"
                 "\"prints\":%d,\"printed\":%s,\"dist_pct\":%.4f},",
                 o.level.price, jesc(o.level.kind).c_str(),
                 o.level.wall_kind.empty() ? "null" : ("\"" + jesc(o.level.wall_kind) + "\"").c_str(),
                 o.level.touch_idx < 0 ? "null" : std::to_string(o.level.touch_idx).c_str(),
                 o.level.prints, o.level.printed ? "true" : "false", o.level.dist * 100.0);
        s += b;
    } else s += "\"level\":null,";
    if (o.amp.ok) {
        snprintf(b, sizeof b,
                 "\"amplitude\":{\"amp_pct\":%.4f,\"amp_price\":%.4f,\"grade\":\"%s\",\"mag\":%.4f,"
                 "\"ratio_em\":%.4f,\"binding\":%s,\"capped_by_rule11\":%s",
                 o.amp.amp_pct, o.amp.amp_price, o.amp.grade.c_str(), o.amp.mag, o.amp.ratio_em,
                 o.amp.binding.empty() ? "null" : ("\"" + jesc(o.amp.binding) + "\"").c_str(),
                 o.amp.capped_by_rule11 ? "true" : "false");
        s += b;
        if (o.amp.retrace_prob) {
            snprintf(b, sizeof b, ",\"retrace_prob\":%.4f,\"retrace_n\":%.0f,\"retrace_src\":\"%s\"",
                     *o.amp.retrace_prob, o.amp.retrace_n.value_or(0), o.amp.retrace_src.c_str());
            s += b;
        }
        s += ",\"constraints\":{";
        for (size_t i = 0; i < o.amp.constraints.size(); ++i) {
            snprintf(b, sizeof b, "%s\"%s\":%.4f", i ? "," : "",
                     o.amp.constraints[i].first.c_str(), o.amp.constraints[i].second);
            s += b;
        }
        s += "}},";
        snprintf(b, sizeof b, "\"mag\":%.4f,\"target\":%.4f,\"grade\":\"%s\",",
                 o.amp.mag, o.amp.amp_price, o.amp.grade.c_str());
        s += b;
    } else {
        s += "\"amplitude\":null,\"mag\":0.0,\"target\":null,\"grade\":null,";
    }
    snprintf(b, sizeof b, "\"ts\":%ld}", (long)time(nullptr));
    s += b;
    return s;
}

// ------------------------- lectura de evidencia (TEST) ----------------------
static Ev ev_from_json(const std::string& j) {
    Ev e;
    if (auto s = jstr(j, "sym")) e.sym = *s;
    auto opt = [&](const char* k) { return jnum(j, k); };
    e.spot = opt("spot"); e.em = opt("em"); e.flip = opt("flip");
    e.r6 = opt("r6"); e.r15 = opt("r15"); e.z6 = opt("z6");
    e.pctb_1m = opt("pctb_1m"); e.pctb_15m = opt("pctb_15m");
    e.flow = opt("flow"); e.vt = opt("vt"); e.bb_mid = opt("bb_mid");
    e.leg_pct = opt("leg_pct"); e.em_used_pct = opt("em_used_pct");
    e.exhaustion = opt("exhaustion"); e.now_min = opt("now_min");
    e.book_coef = opt("book_coef");
    e.calib_lo = opt("calib_lo"); e.calib_n = opt("calib_n");
    if (auto s = jstr(j, "regime")) e.regime = *s;
    if (auto s = jstr(j, "force_phase")) e.force_phase = *s;
    if (auto s = jstr(j, "book_label")) e.book_label = *s;
    e.bandwalk_tf = (int)jnum(j, "bandwalk_tf").value_or(0);
    e.bandwalk_dir = (int)jnum(j, "bandwalk_dir").value_or(0);
    e.candle_bias = (int)jnum(j, "candle_bias").value_or(0);
    e.leader_catalyst = jbool(j, "leader_catalyst", false);
    e.bars_contig = jbool(j, "bars_contig", true);
    if (auto a = jarr(j, "levels"))
        for (const auto& ob : jobjs(*a)) {
            Level L;
            L.price = jnum(ob, "price").value_or(0);
            L.kind = jstr(ob, "kind").value_or("");
            L.wall_kind = jstr(ob, "wall_kind").value_or("");
            auto ti = jnum(ob, "touch_idx");
            L.touch_idx = ti ? (int)*ti : -1;
            if (L.price != 0) e.levels.push_back(L);
        }
    if (auto a = jarr(j, "bars")) {
        // [[t,o,h,l,c,v],...]
        const std::string& s = *a;
        size_t i = 0;
        while (true) {
            auto st = s.find('[', i ? i : 1);
            if (st == std::string::npos) break;
            auto en = s.find(']', st);
            if (en == std::string::npos) break;
            std::string row = s.substr(st + 1, en - st - 1);
            double vals[6] = {0, 0, 0, 0, 0, 0};
            int k = 0; const char* p = row.c_str(); const char* e2 = p + row.size();
            while (k < 6 && p < e2) {
                while (p < e2 && (*p == ' ' || *p == ',')) ++p;
                double v{}; auto [np, ec] = std::from_chars(p, e2, v);
                if (ec != std::errc{}) break;
                vals[k++] = v; p = np;
            }
            if (k >= 5) e.bars.push_back(Bar{(long)vals[0], vals[1], vals[2], vals[3], vals[4], vals[5]});
            i = en + 1;
        }
    }
    return e;
}

// ------------------------- produccion: leer data/ ---------------------------
static std::vector<Bar> load_bars(const std::string& sym) {
    std::vector<Bar> b;
    std::string p = "data/bars_" + sym + "_ibkr.txt";
    FILE* f = fopen(p.c_str(), "r");
    if (!f) return b;
    Bar x{};
    while (fscanf(f, "%ld %lf %lf %lf %lf %lf", &x.t, &x.o, &x.h, &x.l, &x.c, &x.v) == 6)
        b.push_back(x);
    fclose(f);
    return b;
}
static double pctb_of(const std::vector<double>& c, int n, double k, double* mid_out) {
    if ((int)c.size() < n) return -1;
    double m = 0;
    for (int i = (int)c.size() - n; i < (int)c.size(); ++i) m += c[i];
    m /= n;
    double sd = 0;
    for (int i = (int)c.size() - n; i < (int)c.size(); ++i) sd += (c[i] - m) * (c[i] - m);
    sd = std::sqrt(sd / n);
    if (mid_out) *mid_out = m;
    if (sd == 0) return 0.5;
    double up = m + k * sd, lo = m - k * sd;
    return (c.back() - lo) / (up - lo);
}
static Ev gather(const std::string& sym_lo) {
    Ev e;
    std::string SYM = sym_lo;
    for (auto& ch : SYM) ch = (char)toupper(ch);
    e.sym = SYM;
    e.bars = load_bars(sym_lo);
    if (e.bars.size() < 21) return e;                 // sin barras suficientes -> SIN LECTURA
    // contigüidad: el hueco real de feed (07-24 13:15->13:31) no puede pasar por "6 min"
    size_t n = e.bars.size();
    if (n >= 16) {
        long d6 = e.bars[n - 1].t - e.bars[n - 7].t;
        long d15 = e.bars[n - 1].t - e.bars[n - 16].t;
        if (d6 > 8 * 60 || d15 > 18 * 60) e.bars_contig = false;
    }
    std::vector<double> c;
    c.reserve(n);
    for (auto& b : e.bars) c.push_back(b.c);
    e.spot = c.back();
    if (n >= 7) e.r6 = 100.0 * (c[n - 1] - c[n - 7]) / c[n - 7];
    if (n >= 16) e.r15 = 100.0 * (c[n - 1] - c[n - 16]) / c[n - 16];
    // z6 = r6 / (sigma_1m * sqrt(6))  (escalado random-walk)
    if (n >= 61 && e.r6) {
        std::vector<double> r;
        for (size_t i = n - 60; i < n; ++i) r.push_back((c[i] - c[i - 1]) / c[i - 1] * 100.0);
        double m = 0; for (double x : r) m += x; m /= r.size();
        double sd = 0; for (double x : r) sd += (x - m) * (x - m);
        sd = std::sqrt(sd / r.size());
        if (sd > 0) e.z6 = *e.r6 / (sd * std::sqrt(6.0));
    }
    double mid = 0;
    double b1 = pctb_of(c, 20, 2.0, &mid);
    if (b1 >= 0) { e.pctb_1m = b1; e.bb_mid = mid; }
    // %B 15m: agregar cierres cada 15 barras
    std::vector<double> c15;
    for (size_t i = (n >= 15 * 21 ? n - 15 * 21 : 0); i + 15 <= n; i += 15) c15.push_back(c[i + 14]);
    if (c15.size() >= 20) { double b15 = pctb_of(c15, 20, 2.0, nullptr); if (b15 >= 0) e.pctb_15m = b15; }
    // pata actual: recorrido desde el extremo local de las ultimas 30 barras
    if (n >= 30) {
        double hi = c[n - 30], lo = c[n - 30];
        for (size_t i = n - 30; i < n; ++i) { hi = std::max(hi, c[i]); lo = std::min(lo, c[i]); }
        double from = (e.r6.value_or(0) < 0) ? hi : lo;
        if (from > 0) e.leg_pct = (c.back() - from) / from * 100.0;
    }
    struct tm tmv{}; time_t tt = (time_t)e.bars.back().t; localtime_r(&tt, &tmv);
    e.now_min = tmv.tm_hour * 60 + tmv.tm_min;

    // niveles + regimen del mapa GEX (charts/data/levels_<sym>.json, de chart_levels.py)
    std::string lv = slurp("charts/data/levels_" + sym_lo + ".json");
    if (!lv.empty()) {
        if (auto s = jstr(lv, "regime")) e.regime = *s;
        if (auto v = jnum(lv, "flip")) e.flip = *v;
        if (auto v = jnum(lv, "em")) e.em = *v;
        if (auto v = jnum(lv, "spot")) e.spot = *v;      // el spot del mapa manda si existe
        struct WSpec { const char* key; const char* kind; };
        for (auto ws : {WSpec{"put_wall", "Muro put"}, WSpec{"call_wall", "Muro call"},
                        WSpec{"abs_wall", "Muro absoluto"}, WSpec{"poc_dom", "POC"}}) {
            if (auto p = jnum(lv, ws.key)) {
                Level L; L.price = *p; L.kind = ws.kind;
                if (auto k = jstr(lv, std::string(ws.key) + "_kind")) L.wall_kind = *k;
                e.levels.push_back(L);
            }
        }
    }
    // fuerza: SOLO si data/force.json es fresco (<2min). force_meter cae a yfinance con
    // barras rancias = red en camino de senal (prohibido, ley #6) -> mejor no usarlo.
    std::string fj = slurp("data/force.json");
    if (!fj.empty()) {
        std::string sec = json_section(fj, SYM);
        if (!sec.empty()) {
            auto ts = jnum(sec, "ts");
            if (ts && std::fabs((double)time(nullptr) - *ts) <= K::FORCE_MAX_AGE) {
                if (auto ph = jstr(sec, "phase")) e.force_phase = *ph;
                if (auto ex = jnum(sec, "exhaustion")) e.exhaustion = *ex;
            }
        }
    }
    // VT congelado y calidad de libro (features minadas; degradan limpio si no existen)
    std::string vt = slurp("data/vt_" + sym_lo + ".json");
    if (!vt.empty()) if (auto v = jnum(vt, "vt_open")) e.vt = *v;
    std::string bq = slurp("data/book_quality.json");
    if (!bq.empty()) {
        std::string sec = json_section(bq, SYM);
        if (!sec.empty()) {
            if (auto s = jstr(sec, "book_label")) e.book_label = *s;
            if (auto v = jnum(sec, "coef")) e.book_coef = *v;
        }
    }
    return e;
}

// flujo de capitanes: mismo criterio que signal_conditioning.captain_flow_bias
// (SPIKE/BALLENA de PUTS del capitan = piso -> +, de CALLS = techo -> -)
static double captain_flow(const std::string& SYM) {
    static const char* SEMIS[] = {"NVDA","AMD","AVGO","ASML","TSM","TXN","QCOM","LRCX","INTC",
                                  "MU","SKHY","SNDK","STX","WDC","SMH","DRAM","NOK"};
    bool is_semi = false;
    for (auto s : SEMIS) if (SYM == s) { is_semi = true; break; }
    const char* cap = (SYM == "SMH" || is_semi) ? "SMH" : nullptr;
    time_t now = time(nullptr); struct tm tmv{}; localtime_r(&now, &tmv);
    char path[128];
    snprintf(path, sizeof path, "data/trading-signals/%04d-%02d-%02d.txt",
             tmv.tm_year + 1900, tmv.tm_mon + 1, tmv.tm_mday);
    std::ifstream f(path);
    if (!f) return 0.0;
    long now_s = tmv.tm_hour * 3600 + tmv.tm_min * 60 + tmv.tm_sec;
    double out = 0.0;
    std::string ln;
    while (std::getline(f, ln)) {
        std::string up = ln;
        for (auto& ch : up) ch = (char)toupper(ch);
        if (up.find("SPIKE") == std::string::npos && up.find("BALLENA") == std::string::npos) continue;
        bool hit = false;
        if (cap && up.find(cap) != std::string::npos) hit = true;
        if (!cap && (up.find("SPY") != std::string::npos || up.find("QQQ") != std::string::npos)) hit = true;
        if (!hit) continue;
        int hh = 0, mm = 0, ss = 0;
        if (sscanf(ln.c_str(), "%d:%d:%d", &hh, &mm, &ss) != 3) continue;
        long age = now_s - (hh * 3600 + mm * 60 + ss);
        if (age < 0 || age > 8 * 60) continue;
        double rec = std::max(0.3, 1.0 - (double)age / (8 * 60));
        double sign = up.find("PUTS") != std::string::npos ? 1.0
                    : (up.find("CALLS") != std::string::npos ? -1.0 : 0.0);
        out = clampd(out + sign * rec, -1.0, 1.0);
    }
    return out;
}

int main(int argc, char** argv) {
    std::vector<std::string> syms;
    // RETRASO = DINERO (Yunior 2026-07-25): "si la flecha apunta con retraso de 2 segundos y
    // compramos call en el retroceso cuando esta en su punto maximo, no bueno". El throttle
    // del chart era de 2.0 s con el computo en Python (100-180 ms POR SIMBOLO). Un ciclo de
    // esta brujula son 1.09 ms por simbolo (32.7 ms los 30, medido, incluyendo el spawn), asi
    // que el bucle admite SUB-SEGUNDO: --loop 0.25 deja el retraso en <=250 ms.
    double loop_s = 0; bool ev_stdin = false, to_stdout = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--ev-stdin") ev_stdin = true;
        else if (a == "--json") to_stdout = true;
        else if (a == "--loop" && i + 1 < argc) loop_s = atof(argv[++i]);
        else if (a.rfind("--", 0) == 0) { /* ignorar desconocidos */ }
        else { for (auto& ch : a) ch = (char)tolower(ch); syms.push_back(a); }
    }
    std::string decay = slurp("data/momentum_decay.json");

    if (ev_stdin) {   // modo TEST: evidencia inyectada, sin tocar data/
        std::ostringstream ss; ss << std::cin.rdbuf();
        std::string j = ss.str();
        Ev e = ev_from_json(j);
        // histeresis opcional en test: "hist_state"/"hist_cand"/"hist_n"
        Hist h; bool use_h = false;
        if (auto s = jstr(j, "hist_state")) { h.state = *s; h.has = true; use_h = true; }
        if (auto s = jstr(j, "hist_cand")) { h.cand = *s; use_h = true; }
        if (auto v = jnum(j, "hist_n")) { h.n = (int)*v; use_h = true; }
        if (jbool(j, "use_hist", false)) use_h = true;
        Out o = classify(e, use_h ? &h : nullptr, decay);
        std::string js = to_json(o);
        // devolver tambien el histerico resultante, para que el test encadene computos
        js.pop_back();
        js += ",\"hist\":{\"state\":\"" + jesc(h.state) + "\",\"cand\":\"" + jesc(h.cand) +
              "\",\"n\":" + std::to_string(h.n) + "}}";
        printf("%s\n", js.c_str());
        return 0;
    }

    if (syms.empty()) { fprintf(stderr, "uso: compass [--loop S] [--json] SYM...\n"); return 2; }
    do {
        for (const auto& s : syms) {
            Ev e = gather(s);
            std::string SYM = e.sym;
            double cf = captain_flow(SYM);
            if (cf != 0.0) e.flow = cf;
            Hist& h = g_hist[SYM];
            Out o = classify(e, &h, decay);
            std::string js = to_json(o);
            std::string tmp = "data/.compass_" + s + ".tmp";
            FILE* f = fopen(tmp.c_str(), "w");
            if (f) {
                fprintf(f, "%s\n", js.c_str());
                fclose(f);
                rename(tmp.c_str(), ("data/compass_" + s + ".json").c_str());
            } else {
                fprintf(stderr, "[compass] no puedo escribir %s\n", tmp.c_str());
            }
            if (to_stdout || loop_s == 0) {
                const char* g = o.dir == "up" ? "^" : (o.dir == "down" ? "v" : "-");
                printf("%s %-5s %-4s %d%% [%s] %s%s\n", g, SYM.c_str(), o.dir.c_str(), o.prob,
                       o.state.c_str(), o.amp.ok ? o.amp.grade.c_str() : "",
                       o.pending_print ? " (esperando print)" : "");
                for (const auto& w : o.state_why) printf("    - %s\n", w.c_str());
            }
        }
        if (loop_s > 0) {
            struct timespec ts{(time_t)loop_s, (long)((loop_s - (double)(time_t)loop_s) * 1e9)};
            nanosleep(&ts, nullptr);
        }
    } while (loop_s > 0);
    return 0;
}
