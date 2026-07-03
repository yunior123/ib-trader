// chase.h — persecución de fill (repeg) para CIERRES, pura y testeable.
//
// POR QUE: "orders always get filled by default" (Yunior 2026-07-29). Las
// ENTRADAS ya salen marketables al tope revisado por el humano (jamás se
// persigue por encima de ese tope) y en RTH llevan Adaptive (order_policy.h).
// Lo que sí puede quedarse dormido es un CIERRE: su límite se calcula una vez
// y si el mercado se mueve la orden descansa mientras la posición sigue
// expuesta. Este módulo re-pega el límite hacia el marketable FRESCO cada
// intervalo, acotado por un tope de slippage anclado al límite inicial: al
// agotarse el tope la orden descansa ahí y se GRITA — nunca se remata a 0.01.
// El repeg usa modify() (cancel/replace mismo id): legal también overnight,
// donde IBKR solo admite LMT plano.
#pragma once
#include <cmath>
#include <string>

namespace oe {

struct ChaseCfg {
    int interval_s = 15;            // mínimo entre repegs (pacing IBKR)
    int max_repegs = 40;            // backstop anti-churn (~10 min a 15s)
    double stk_slip_pct = 1.0;      // tope de slippage acciones vs límite inicial
    double opt_slip_pct = 15.0;     // tope opciones (la prima se mueve más)
};

struct RepegDecision {
    bool modify = false;
    bool exhausted = false;         // tope alcanzado y sigue sin llenar -> gritar
    double new_limit = 0;
};

// Peor precio permitido: ancla en el límite INICIAL del cierre, no en el vigente
// (anclar en el vigente haría el tope una escalera sin fondo).
inline double chase_worst(char side, double ref_lim, bool is_opt, const ChaseCfg& cfg) {
    double slip = (is_opt ? cfg.opt_slip_pct : cfg.stk_slip_pct) / 100.0;
    return (side == 'B') ? ref_lim * (1.0 + slip) : ref_lim * (1.0 - slip);
}

// side: lado de la orden de CIERRE. fresh = marketable actual (B: ask, S: bid);
// <=0 significa "sin precio de fiar" y no se persigue (fail-closed).
inline RepegDecision decide_repeg(char side, double placed_lim, double ref_lim,
                                  double fresh, int repegs, long long last_s,
                                  long long now_s, bool is_opt, const ChaseCfg& cfg) {
    RepegDecision d;
    if (fresh <= 0 || ref_lim <= 0 || placed_lim <= 0) return d;
    if (now_s - last_s < cfg.interval_s) return d;
    if (repegs >= cfg.max_repegs) { d.exhausted = true; return d; }
    const double worst = chase_worst(side, ref_lim, is_opt, cfg);
    double target = (side == 'B') ? std::min(fresh, worst) : std::max(fresh, worst);
    target = std::round(target * 100.0) / 100.0;
    if (target <= 0) return d;
    const double eps = 0.005;       // medio centavo: no repegar por ruido sub-tick
    bool better_chase = (side == 'B') ? (target > placed_lim + eps)
                                      : (target < placed_lim - eps);
    if (!better_chase) {
        // Ya estamos al tope y el mercado sigue lejos -> exhausto (gritar una vez).
        bool at_worst = std::fabs(placed_lim - std::round(worst * 100.0) / 100.0) <= eps;
        bool market_beyond = (side == 'B') ? (fresh > worst) : (fresh < worst);
        if (at_worst && market_beyond) d.exhausted = true;
        return d;
    }
    d.modify = true;
    d.new_limit = target;
    return d;
}

}  // namespace oe
