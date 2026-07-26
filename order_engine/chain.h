// chain.h — cadena de opciones y el GATE de tamaño/liquidez, puros y testeables.
//
// POR QUE EXISTE: load_chain/nearest_row/run_gate vivian EN LINEA en
// order_engine.cpp (como guards.h documenta para las guardas de dinero) y por
// tanto no se podian ejercitar con mercado cerrado. Aqui son funciones puras
// (cero IO real salvo un ifstream que el test apunta a un fixture) para que
// order_engine/tests las conduzca un sabado. El motor las usa via `#include
// "chain.h"` + `using namespace oe;` (igual que hace con guards.h).
//
// DOS BUGS MEDIDOS 2026-07-25 que este fichero cierra:
//
//  (1) EL CENTINELA -1.0000 COMO DELTA REAL. scripts/opt_chain_cache.py
//      escribe `nz(v, d=-1.0)` para iv Y delta cuando Ticker.modelGreeks es
//      None (tipico fuera de RTH). MEDIDO: 100% de las filas de
//      data/opt_chain_qqq.txt y opt_chain_nvda.txt, 1.475/1.500 (98,3%)
//      agregado de la flota. La version vieja de order_engine.cpp solo
//      descartaba el 0 EXACTO (`fabs(delta) > 1e-6`, guards.h clamp_option_stop
//      igual) -> -1.0000 pasaba como delta de un PUT profundo ITM e invertia
//      el mapeo subyacente->prima del stop. iv y delta salen del MISMO
//      tk.modelGreeks: si es None, AMBOS son el centinela -> ChainRow.iv es
//      la señal de si el par es de fiar (ver option_greeks_known en guards.h).
//
//  (2) nearest_row() SIN TOPE DE DISTANCIA NI EXIGENCIA DE STRIKE. Sirve bien
//      en la ENTRADA (el "nivel" es el precio del SUBYACENTE al PRINT, se
//      busca el strike mas cercano a proposito). Pero en un CLOSE el strike
//      YA SE CONOCE con certeza (viene de una posicion real): ahi hace falta
//      exact_row(), que exige right+exp+strike EXACTOS o no devuelve nada.
//      Sin esto, cerrar QQQ 700C podia preciar sobre 705C -> el limite sale
//      mal, la orden no llena, y el panel ya respondio {"ok":true}. Crees que
//      estas plano y no lo estas.
#pragma once
#include <cmath>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace oe {

// ======================================================= cadena de opciones
// iv por defecto -1.0: MISMO centinela que escribe opt_chain_cache.py cuando
// no hay dato. Si la columna opcional no esta en el fichero (formato viejo)
// o el parseo falla a medias, iv se queda en "desconocido", nunca en 0
// (0 seria un IV real imposible y otro numero plausible inventado).
struct ChainRow {
    double strike = 0; std::string right, exp;
    double bid = -1, ask = -1; long oi = 0;
    double iv = -1.0; double delta = 0;
};
struct Chain { double spot = 0; long long epoch = 0; std::vector<ChainRow> rows; bool ok = false; };

inline Chain load_chain(const std::string& path) {
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
        ChainRow r; std::string exp; long vol = 0;
        if (!(ss >> r.strike >> r.right >> r.exp >> r.bid >> r.ask >> vol >> r.oi)) continue;
        // iv/delta OPCIONALES: si el par entero no se lee, r.iv se queda en
        // -1.0 (desconocido) -- exactamente el mismo estado que el centinela
        // explicito del escritor, asi que option_greeks_known() (guards.h)
        // los trata igual sin necesitar un caso especial mas.
        double iv = -1.0, delta = 0.0;
        if (ss >> iv >> delta) { r.iv = iv; r.delta = delta; }
        ch.rows.push_back(r);
    }
    ch.ok = !ch.rows.empty();
    return ch;
}

// Fila con strike MAS CERCANO al nivel, para right(+exp). Uso correcto: la
// ENTRADA, donde `level` es el precio del SUBYACENTE al PRINT y no hay un
// strike "correcto" de antemano -- se elige el mas proximo a proposito.
// NO USAR para cerrar una posicion conocida: usar exact_row.
inline const ChainRow* nearest_row(const Chain& ch, const std::string& right,
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

// Fila EXACTA: right+exp+strike deben coincidir (tolerancia 1e-6, los strikes
// reales van en pasos de 0.5/1.0). exp vacio -> nullptr (falla cerrado: si no
// se sabe el vencimiento exacto de una posicion real, no se inventa cual es).
// Uso: CERRAR una posicion conocida (panel "close", stop watch-local sobre
// z.entry_c) -- ahi el contrato NO es una aproximacion, es un hecho.
inline const ChainRow* exact_row(const Chain& ch, const std::string& right,
                                 const std::string& exp, double strike) {
    if (exp.empty()) return nullptr;
    for (auto& r : ch.rows) {
        if (r.right != right) continue;
        if (r.exp != exp) continue;
        if (std::fabs(r.strike - strike) > 1e-6) continue;
        return &r;
    }
    return nullptr;
}

// ======================================================= gate (mirror order_ticket.py)
inline const double MAX_SPREAD_PCT = 5.0;
inline const long   MIN_OI = 500;
inline const double MAX_AGE_S = 900;

struct Gate {
    bool go = false;
    double limit = 0, premium = 0, spread_pct = 0, delta = 0, iv = -1.0;
    long oi = 0; double strike = 0; std::string exp, right;
    std::vector<std::string> why;
};

// side: 'B' (comprar -> paga ask) | 'S' (vender -> cobra bid).
// require_exact_strike: false (default) = ENTRADA, nearest_row aproxima al
// nivel del subyacente. true = se conoce el contrato con certeza (close /
// stop watch-local sobre una posicion ya llena) -> exact_row, sin aproximar.
inline Gate run_gate(const Chain& ch, const std::string& right, const std::string& exp,
                     double level, char side, double budget, long long now_s,
                     bool require_exact_strike = false) {
    Gate g; g.right = right;
    if (!ch.ok) { g.why.push_back("sin cadena fresca"); return g; }
    const ChainRow* r = require_exact_strike ? exact_row(ch, right, exp, level)
                                             : nearest_row(ch, right, exp, level);
    if (!r) {
        g.why.push_back(require_exact_strike ? "sin contrato EXACTO para right/exp/strike"
                                             : "sin contrato para right/exp");
        return g;
    }
    g.strike = r->strike; g.exp = r->exp; g.oi = r->oi; g.delta = r->delta; g.iv = r->iv;
    double age = (double)(now_s - ch.epoch);
    bool fresh = age <= MAX_AGE_S;
    bool quote_ok = r->bid > 0 && r->ask > 0 && r->ask >= r->bid;
    if (quote_ok) {
        double mid = (r->bid + r->ask) / 2.0;
        g.spread_pct = (r->ask - r->bid) / mid * 100.0;
    }
    g.limit = (side == 'B') ? r->ask : r->bid;
    g.premium = (g.limit > 0) ? g.limit * 100.0 : 0;
    bool spread_ok = quote_ok && g.spread_pct >= 0 && g.spread_pct <= MAX_SPREAD_PCT;  // ==0 es el MEJOR spread
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

}  // namespace oe
