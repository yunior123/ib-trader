// gate_core.hpp — LA ARITMETICA DEL GATE DE OPCIONES, ESCRITA UNA SOLA VEZ.
// Orden Yunior 2026-07-25: "python solo para test, la computacion en C++".
//
// POR QUE EXISTE ESTE ARCHIVO (auditoria 2026-07-25)
// -------------------------------------------------
// La regla de la casa es UNA (CLAUDE.md #4: "spread <5% del premium o no se paga", OI>500,
// y la ENMIENDA del 2026-07-22: prima <= $200 por contrato). Habia CUATRO implementaciones
// de esa misma regla, y no coincidian:
//
//   1. scripts/optgate.py     spread = (ask-bid)/ASK   + frescura que FALLABA ABIERTA
//   2. scripts/order_ticket.py spread = (ask-bid)/MID  + OI >= 500  + presupuesto ANULADO
//   3. order_engine/order_engine.cpp  spread = (ask-bid)/MID + OI > 500  (la mas correcta)
//   4. (el mismo run_gate, duplicado a mano, "mirror order_ticket.py")
//
// Los tres bugs del camino del DINERO que este archivo cierra, con numeros medidos:
//
//   B1. FALLA ABIERTA de frescura (optgate.py:41)
//       `if not spot or (epoch and time.time() - epoch > MAX_AGE_S): continue`
//       Con `epoch 0` en la cabecera (cadena de 1970) el `and` corta en falso y el chequeo
//       de edad se salta ENTERO: medido -> "OPCIONES OK (spread 2%)" sobre quotes fosiles.
//       Es el desastre DRAM documentado (spread real 8-20%, -15% al entrar).
//       AQUI: sin epoch valido y > 0 NO HAY VEREDICTO. Nunca "OK". Fail-loud.
//
//   B2. DOS matematicas del mismo 5%: /ask vs /mid. Medido con bid 1.425 / ask 1.50 (prima
//       $150, dentro de presupuesto, OI alto, cadena fresca):
//           optgate      (ask-bid)/ask = 5.0%   -> "OPCIONES OK"
//           order_ticket (ask-bid)/mid = 5.1%   -> NO-GO
//       El caso del brief (bid 0.95 / ask 1.00) da 5.0% vs 5.13%: ambos vetan solo por ruido
//       de coma flotante (/ask sale 5.000000000000004 > 5.0). La divergencia es real igual.
//       AQUI: /MID y punto. mid = (bid+ask)/2. Es el estandar y el conservador de los dos.
//
//   B3. PRESUPUESTO ANULADO (order_ticket.py:90)
//       `size = max(1, int(BUDGET_USD // prem))`. Con prem=250 y budget=200:
//       200//250 = 0 -> max(1,0) = 1 -> compraba UN contrato de $250 con $200 de presupuesto,
//       y encima lo clasificaba CAUTION (amarillo), no NO-GO. Medido.
//       AQUI: size = floor(budget/prima) SIN max(); size==0 => NO-GO. El presupuesto es un
//       VETO, no una advertencia.
//
//   B3b (encontrado al auditar): OI en la frontera. order_ticket usaba `oi >= 500` y
//       order_engine `oi > 500`. Con OI=500 exacto uno pasaba y el otro vetaba.
//       AQUI: la doctrina dice "OI > 500" -> ESTRICTO. 500 rechaza, 501 pasa.
//
// "NO HAY DATO" NO ES "SPREAD MALO". IBKR escribe bid/ask = -1.00 cuando no cotiza (fuera de
// RTH la flota entera sale asi: ver data/opt_chain_nvda.txt de las 16:16). Eso es CIEGO, no
// caro: verdict NO-GO con known=false, jamas un "OK" ni un "spread 0%".
//
// FRONTERAS (una sola respuesta en todo el sistema, documentada):
//   spread <= 5.0%  PASA   (con tolerancia EPS: "exactamente 5.0%" no puede depender de que
//                           2.05-1.95 de 0.10000000000000009 en binario)
//   OI    >  500    PASA   (estricto)
//   prima <= $200   PASA   (tolerancia EPS)
//   edad  <= 900s   PASA
//
// SENAL-SOLAMENTE: este header solo JUZGA. No conecta, no ordena, no toca la red.
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace gate {

// Igualdad en la frontera: sin esto, "exactamente 5.0%" o "prima exactamente $200" dependen
// del ultimo bit del double y el sistema deja de ser determinista donde mas importa.
constexpr double EPS = 1e-9;

// ------------------------------- parametros ---------------------------------
// Nombres de entorno: OPT_BUDGET_USD es el que YA usa el repo (order_ticket.py:27). Los demas
// siguen el mismo prefijo. Los defaults son la doctrina, no una preferencia.
struct Params {
    double max_spread_pct     = 5.0;    // OPT_MAX_SPREAD_PCT   (CLAUDE.md #4)
    long   min_oi             = 500;    // OPT_MIN_OI           (estricto: >)
    double budget_usd         = 200.0;  // OPT_BUDGET_USD       (ENMIENDA 2026-07-22)
    double max_age_s          = 900.0;  // OPT_MAX_AGE_S
    double caution_spread_pct = 3.0;    // OPT_CAUTION_SPREAD_PCT  (pasa, pero caro)
    long   caution_oi         = 1000;   // OPT_CAUTION_OI          (pasa, pero flaco)
};

inline double env_d(const char* k, double dflt) {
    const char* v = std::getenv(k);
    if (!v || !*v) return dflt;
    char* e = nullptr;
    double x = std::strtod(v, &e);
    return (e && e != v) ? x : dflt;
}
inline Params params_from_env() {
    Params p;
    p.max_spread_pct     = env_d("OPT_MAX_SPREAD_PCT", p.max_spread_pct);
    p.min_oi             = (long)env_d("OPT_MIN_OI", (double)p.min_oi);
    p.budget_usd         = env_d("OPT_BUDGET_USD", p.budget_usd);
    p.max_age_s          = env_d("OPT_MAX_AGE_S", p.max_age_s);
    p.caution_spread_pct = env_d("OPT_CAUTION_SPREAD_PCT", p.caution_spread_pct);
    p.caution_oi         = (long)env_d("OPT_CAUTION_OI", (double)p.caution_oi);
    return p;
}

// ------------------------------- la cadena ----------------------------------
// FORMATO (contrato con scripts/opt_chain_cache.py — NO desviarse):
//   # opt_chain NVDA | epoch 1784298180 | 2026-07-17 10:03:00 | spot 208.35 | exps 20260717 ...
//   # strike right exp bid ask vol oi iv delta gamma        (n/d = -1)
//   207.50 C 20260717 1.23 1.27 15234 8211 0.4310 0.5512 0.0410
struct Row {
    double strike = 0;
    std::string right, exp;
    double bid = -1, ask = -1;
    long vol = 0, oi = 0;
    double iv = -1, delta = -1, gamma = -1;
};

struct Chain {
    std::string sym;
    bool file_ok = false;      // habia archivo Y al menos una fila parseable
    bool have_epoch = false;   // epoch presente, entero y > 0   <- B1 vive aqui
    long long epoch = 0;
    bool have_spot = false;
    double spot = 0;
    std::vector<std::string> exps;
    std::vector<Row> rows;
};

// devuelve el trozo tras `key` hasta el siguiente '|' (o fin de linea), sin blancos al borde
inline std::string hdr_field(const std::string& line, const char* key) {
    auto p = line.find(key);
    if (p == std::string::npos) return {};
    p += std::strlen(key);
    auto e = line.find('|', p);
    std::string v = line.substr(p, e == std::string::npos ? std::string::npos : e - p);
    size_t a = v.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return {};
    size_t b = v.find_last_not_of(" \t\r\n");
    return v.substr(a, b - a + 1);
}

inline Chain parse_chain_text(const std::string& text, const std::string& sym) {
    Chain ch;
    ch.sym = sym;
    std::istringstream in(text);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        if (line[0] == '#') {
            if (!ch.have_epoch) {
                std::string v = hdr_field(line, "epoch ");
                // "epoch 0" (1970), "epoch NaN", "epoch " vacio -> NO hay epoch. Fail-loud.
                if (!v.empty() && v.find_first_not_of("0123456789") == std::string::npos) {
                    long long e = std::atoll(v.c_str());
                    if (e > 0) { ch.epoch = e; ch.have_epoch = true; }
                }
            }
            if (!ch.have_spot) {
                std::string v = hdr_field(line, "spot ");
                if (!v.empty()) {
                    char* e = nullptr;
                    double s = std::strtod(v.c_str(), &e);
                    if (e && e != v.c_str() && s > 0) { ch.spot = s; ch.have_spot = true; }
                }
            }
            if (ch.exps.empty()) {
                std::istringstream es(hdr_field(line, "exps "));
                std::string x;
                while (es >> x) ch.exps.push_back(x);
            }
            continue;
        }
        std::istringstream ss(line);
        Row r;
        if (!(ss >> r.strike >> r.right >> r.exp >> r.bid >> r.ask >> r.vol >> r.oi)) continue;
        if (r.right != "C" && r.right != "P") continue;
        ss >> r.iv >> r.delta >> r.gamma;   // opcionales (n/d = -1)
        ch.rows.push_back(r);
    }
    ch.file_ok = !ch.rows.empty();
    return ch;
}

inline Chain load_chain(const std::string& path, const std::string& sym) {
    std::ifstream f(path);
    if (!f) return Chain{sym, false, false, 0, false, 0, {}, {}};
    std::ostringstream ss;
    ss << f.rdbuf();
    return parse_chain_text(ss.str(), sym);
}

// ------------------------------- la cotizacion -------------------------------
enum class QState { NO_DATA, CROSSED, OK };

struct Quote {
    QState state = QState::NO_DATA;
    double bid = 0, ask = 0, mid = 0, spread_pct = 0;
    bool ok() const { return state == QState::OK; }
};

// LA formula. Una. `/mid`.
inline Quote quote_of(const Row& r) {
    Quote q;
    q.bid = r.bid;
    q.ask = r.ask;
    if (r.bid <= 0 || r.ask <= 0) { q.state = QState::NO_DATA; return q; }  // IBKR -1.00 / 0
    if (r.ask < r.bid - EPS) { q.state = QState::CROSSED; return q; }
    q.mid = (r.bid + r.ask) / 2.0;
    q.spread_pct = q.mid > 0 ? (r.ask - r.bid) / q.mid * 100.0 : 0.0;
    q.state = QState::OK;
    return q;
}

// ------------------------------- seleccion ----------------------------------
// Modo FICHA (order_ticket / order_engine): strike mas cercano al nivel, para right+exp.
inline const Row* nearest_row(const Chain& ch, const std::string& right,
                              const std::string& exp, double level) {
    const Row* best = nullptr;
    double bd = 1e18;
    for (const auto& r : ch.rows) {
        if (r.right != right) continue;
        if (!exp.empty() && r.exp != exp) continue;
        double d = std::fabs(r.strike - level);
        if (d < bd) { bd = d; best = &r; }
    }
    return best;
}

// Modo SONDEO (optgate): "¿se pueden pagar opciones en este nombre AHORA MISMO?".
// Criterio de SELECCION calcado de optgate.py:50 a proposito (ask <= 3.5, oi >= 200, primer
// OTM de cualquiera de los dos lados, el mas cercano al spot) para que la unica diferencia
// contra el Python viejo sean los BUGS arreglados, no un universo de contratos distinto.
inline const Row* first_otm_row(const Chain& ch, double max_ask = 3.5, long min_oi_sel = 200) {
    if (!ch.have_spot) return nullptr;
    const Row* best = nullptr;
    double bd = 1e18;
    for (const auto& r : ch.rows) {
        if (r.bid <= 0 || r.ask <= 0) continue;
        if (r.ask > max_ask || r.oi < min_oi_sel) continue;
        bool otm = (r.right == "P") ? (r.strike < ch.spot) : (r.strike > ch.spot);
        if (!otm) continue;
        double d = std::fabs(r.strike - ch.spot) / ch.spot;
        if (d < bd) { bd = d; best = &r; }
    }
    return best;
}

// ------------------------------- el veredicto -------------------------------
// codigo primario (lo que un test o un banner necesita en una palabra)
namespace code {
constexpr const char* SIN_CADENA   = "SIN_CADENA";
constexpr const char* SIN_EPOCH    = "SIN_EPOCH";
constexpr const char* SIN_SPOT     = "SIN_SPOT";
constexpr const char* SIN_CONTRATO = "SIN_CONTRATO";
constexpr const char* SIN_DATO     = "SIN_DATO";
constexpr const char* CRUZADO      = "CRUZADO";
constexpr const char* VIEJA        = "VIEJA";
constexpr const char* SPREAD       = "SPREAD";
constexpr const char* OI           = "OI";
constexpr const char* PRESUPUESTO  = "PRESUPUESTO";
constexpr const char* OK           = "OK";
}  // namespace code

struct Verdict {
    std::string verdict = "NO-GO";   // GO | CAUTION | NO-GO   (jamas otra cosa)
    std::string codigo = code::SIN_CADENA;
    bool known = false;   // false = SIN VEREDICTO: no hubo dato para juzgar (nunca "OK")
    bool go = false;
    // contrato
    bool have_row = false;
    double strike = 0;
    std::string right, exp;
    long oi = 0;
    double delta = -1, iv = -1;
    bool oi_ok = false;
    // cotizacion
    QState qstate = QState::NO_DATA;
    bool quote_ok = false, have_spread = false, spread_ok = false;
    double bid = 0, ask = 0, mid = 0, spread_pct = 0;
    // frescura
    bool have_age = false, fresh = false;
    double age_s = 0;
    // dinero
    char side = 'B';
    double limit = 0, premium = 0;
    int size = 0;
    bool budget_ok = false;
    // por que
    std::vector<std::string> why;
    Params p;
};

// side: 'B' comprar (paga el ask) | 'S' vender (cobra el bid).
inline Verdict evaluate(const Chain& ch, const Row* r, char side, const Params& p,
                        long long now_s) {
    Verdict v;
    v.p = p;
    v.side = side;
    char b[256];

    // ---- 1. cadena ----------------------------------------------------------
    if (!ch.file_ok) {
        v.codigo = code::SIN_CADENA;
        v.why.emplace_back("sin cadena de opciones (archivo ausente o sin filas)");
        return v;   // known=false, NO-GO
    }
    // ---- 2. FRESCURA OBLIGATORIA (B1): sin epoch NO hay veredicto -----------
    if (!ch.have_epoch) {
        v.codigo = code::SIN_EPOCH;
        v.why.emplace_back("cadena SIN epoch valido (>0): la frescura no es verificable "
                           "-> SIN VEREDICTO, jamas OK");
        return v;
    }
    if (!ch.have_spot) {
        v.codigo = code::SIN_SPOT;
        v.why.emplace_back("cadena sin spot en la cabecera -> SIN VEREDICTO");
        return v;
    }
    v.have_age = true;
    v.age_s = (double)(now_s - ch.epoch);
    if (v.age_s < -60.0) {
        v.codigo = code::VIEJA;
        v.known = true;
        std::snprintf(b, sizeof b, "epoch en el FUTURO (%.0fs): cadena o reloj corruptos",
                      -v.age_s);
        v.why.emplace_back(b);
        return v;
    }
    v.fresh = v.age_s <= p.max_age_s + EPS;
    if (!v.fresh) {
        v.known = true;   // que este vieja SI es un veredicto
        std::snprintf(b, sizeof b, "cadena vieja %.0fs (> %.0fs)", v.age_s, p.max_age_s);
        v.why.emplace_back(b);
    }
    // ---- 3. contrato --------------------------------------------------------
    if (!r) {
        v.codigo = code::SIN_CONTRATO;
        v.why.emplace_back("sin contrato en la cadena para el right/expiry/nivel pedidos");
        return v;
    }
    v.have_row = true;
    v.strike = r->strike; v.right = r->right; v.exp = r->exp;
    v.oi = r->oi; v.delta = r->delta; v.iv = r->iv;
    v.oi_ok = r->oi > p.min_oi;   // B3b: ESTRICTO. 500 rechaza, 501 pasa.

    // ---- 4. cotizacion: "no hay dato" != "spread malo" ---------------------
    Quote q = quote_of(*r);
    v.qstate = q.state;
    v.bid = q.bid; v.ask = q.ask; v.mid = q.mid;
    if (q.state == QState::NO_DATA) {
        v.codigo = code::SIN_DATO;
        std::snprintf(b, sizeof b,
                      "SIN DATO de bid/ask (%.2f/%.2f; IBKR escribe -1.00 cuando no cotiza): "
                      "fuera de RTH o contrato ilíquido. No es 'spread malo': es CIEGO",
                      r->bid, r->ask);
        v.why.emplace_back(b);
        // known se queda en false si la cadena es fresca: no hay con que juzgar.
        return v;
    }
    if (q.state == QState::CROSSED) {
        v.codigo = code::CRUZADO;
        v.known = true;   // dato hay, y es malo
        std::snprintf(b, sizeof b, "libro CRUZADO: ask %.2f < bid %.2f — cotizacion corrupta",
                      r->ask, r->bid);
        v.why.emplace_back(b);
        return v;
    }
    v.quote_ok = true;
    v.known = true;
    v.have_spread = true;
    v.spread_pct = q.spread_pct;
    v.spread_ok = q.spread_pct <= p.max_spread_pct + EPS;   // B2: /mid, frontera <= con EPS
    std::snprintf(b, sizeof b, "spread %.2f%% de %.2f/%.2f (mid %.3f) %s",
                  v.spread_pct, r->bid, r->ask, q.mid,
                  v.spread_ok ? "OK" : "⛔ >5% NO PAGAR");
    v.why.emplace_back(b);
    if (!v.oi_ok) {
        std::snprintf(b, sizeof b, "OI %ld no supera %ld (poca liquidez)", r->oi, p.min_oi);
        v.why.emplace_back(b);
    }

    // ---- 5. dinero (B3): el presupuesto es un VETO, no un aviso ------------
    v.limit = (side == 'B') ? r->ask : r->bid;
    v.premium = v.limit > 0 ? v.limit * 100.0 : 0.0;
    v.budget_ok = v.premium > 0 && v.premium <= p.budget_usd + EPS;
    // SIN max(1,...): floor honesto. Si no cabe ni uno, size = 0 y el veredicto es NO-GO.
    v.size = v.premium > 0 ? (int)std::floor((p.budget_usd + EPS) / v.premium) : 0;
    if (!v.budget_ok || v.size == 0) {
        std::snprintf(b, sizeof b, "prima $%.0f > presupuesto $%.0f -> caben %d contratos: VETO",
                      v.premium, p.budget_usd, v.size);
        v.why.emplace_back(b);
    }

    // ---- 6. veredicto ------------------------------------------------------
    v.go = v.fresh && v.quote_ok && v.spread_ok && v.oi_ok && v.budget_ok && v.size >= 1;
    if (v.go) {
        v.verdict = "GO";
        v.codigo = code::OK;
        // CAUTION = pasa los gates DUROS pero hay motivo para pedir mas paciencia.
        bool caro   = v.spread_pct > p.caution_spread_pct;
        bool flaco  = v.oi <= p.caution_oi;
        bool tibia  = v.age_s > p.max_age_s / 2.0;
        if (caro || flaco || tibia) {
            v.verdict = "CAUTION";
            if (caro) {
                std::snprintf(b, sizeof b, "spread %.2f%% pasa pero es caro (>%.1f%%)",
                              v.spread_pct, p.caution_spread_pct);
                v.why.emplace_back(b);
            }
            if (flaco) {
                std::snprintf(b, sizeof b, "OI %ld justo (<=%ld): salida puede costar",
                              v.oi, p.caution_oi);
                v.why.emplace_back(b);
            }
            if (tibia) {
                std::snprintf(b, sizeof b, "cadena de hace %.0fs: refresca antes del clic",
                              v.age_s);
                v.why.emplace_back(b);
            }
        }
    } else {
        v.verdict = "NO-GO";
        // codigo primario por PRECEDENCIA de gravedad
        if (!v.fresh)             v.codigo = code::VIEJA;
        else if (!v.spread_ok)    v.codigo = code::SPREAD;
        else if (!v.oi_ok)        v.codigo = code::OI;
        else if (!v.budget_ok || v.size == 0) v.codigo = code::PRESUPUESTO;
        else                      v.codigo = code::SIN_DATO;
    }
    return v;
}

}  // namespace gate
