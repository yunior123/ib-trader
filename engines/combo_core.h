// ============================================================================
// engines/combo_core.h — MOTOR 3 (B8): COMBO Bollinger + FLUJO, header-only.
//
// SEÑAL-SOLAMENTE. La señal BB elastic (bb_core.h, B7) SOLO se emite si el
// CONTEXTO DE FLUJO esta de acuerdo, con la JERARQUIA DE CAPITANES
// (regla 12 de ~/CLAUDE.md, 2026-07-22):
//   - SPY/QQQ = capitanes del MERCADO (para todos).
//   - SMH = capitan de SEMIS/memoria (tropa: MU SKHY DRAM SNDK WDC STX LRCX
//     NVDA AMD TSM).
//   - elastic LONG requiere: sin SPIKE_CALLS vigente (<=20 min) del PROPIO
//     ticker Y capitan(es) SIN SPIKE_CALLS vigente. SPIKE_PUTS vigente del
//     capitan = REFUERZO (kind=combo_captain). Espejo exacto para SHORT.
//   - Conflicto capitan-contra vs capitan-a-favor: el CONTRA gana (conservador,
//     "el capitan prevalece y la señal del nombre queda anulada").
//   - SIN CONTEXTO DE FLUJO (propio o capitan sin registro fresco <=30 min)
//     = SIN SEÑAL. Eso ES el diseño, no un fallo: sin flujo no hay combo.
//
// Estado de flujo: replay del MISMO nucleo de spikes de flow_pulse v3/v4
// (== scripts/flow_signals_export.py): ritmo por lado sobre mins∈[1,30],
// EMA alfa 0.40 (primer valor = seed), SPIKE = ritmo >= 3x EMA y delta >=
// 2000 contratos, dominancia 2x, anti-artefacto (bilateral o >50x = mudo,
// EMA intacta). Aqui NO hay cooldown: el spike solo actualiza el reloj de
// vigencia (repetirse extiende la ventana — mas flujo, mas vigente).
//
// CERO look-ahead: el driver solo alimenta registros de flujo con
// ts <= (bar.t + base_tf) — el instante del CIERRE de la barra que decide.
// ============================================================================
#pragma once

#include "bb_core.h"

#include <cstring>
#include <unordered_map>
#include <unordered_set>

namespace combocore {

using bbcore::Bar;
using bbcore::Config;
using bbcore::Signal;

// ------------------------------ constantes ----------------------------------
constexpr double SPIKE_X    = 3.0;     // ritmo >= 3x su EMA
constexpr double SPIKE_MIN  = 2000.0;  // delta >= 2000 contratos
constexpr double EMA_A      = 0.40;    // alfa EMA (flow_pulse)
constexpr double ARTIFACT_X = 50.0;    // ritmo > 50x EMA = relleno del feed
constexpr double VIGENCIA_S = 1200.0;  // spike vigente 20 min
constexpr double FRESH_S    = 1800.0;  // contexto: registro <= 30 min

// -------------------------- jerarquia de capitanes ---------------------------
// captains_of(sym): SMH si sym es tropa de memoria, y SPY/QQQ para todos;
// nunca se incluye a si mismo (SPY tiene de capitan a QQQ y viceversa).
inline const std::unordered_set<std::string>& memory_troop() {
    static const std::unordered_set<std::string> s = {
        "MU", "SKHY", "DRAM", "SNDK", "WDC", "STX", "LRCX", "NVDA", "AMD", "TSM"};
    return s;
}
inline std::vector<std::string> captains_of(const std::string& sym) {
    std::vector<std::string> c;
    if (memory_troop().count(sym)) c.push_back("SMH");
    for (const char* m : {"SPY", "QQQ"}) if (sym != m) c.push_back(m);
    return c;
}

// ------------------------- registro de flujo (jsonl) -------------------------
struct FlowRec { double ts = 0; std::string sym; double vc = 0, vp = 0; };

// Parser tolerante de una linea de data/whale_flow_hist.jsonl
// {"ts":...,"sym":"X","vc":...,"vp":...,...}. Malformada -> false, JAMAS crashea.
inline bool parse_flow_line(const char* line, FlowRec& r) {
    auto num = [&](const char* key, double& out) -> bool {
        const char* p = std::strstr(line, key);
        if (!p) return false;
        p = std::strchr(p + std::strlen(key), ':');
        if (!p) return false;
        ++p;
        while (*p == ' ' || *p == '\t') ++p;
        char* end = nullptr;
        const double v = std::strtod(p, &end);
        if (end == p || !std::isfinite(v)) return false;
        out = v;
        return true;
    };
    if (!num("\"ts\"", r.ts) || !num("\"vc\"", r.vc) || !num("\"vp\"", r.vp)) return false;
    if (r.ts <= 0 || r.vc < 0 || r.vp < 0) return false;
    const char* p = std::strstr(line, "\"sym\"");
    if (!p) return false;
    p = std::strchr(p + 5, ':');
    if (!p) return false;
    while (*p && *p != '"') ++p;
    if (!*p) return false;
    const char* a = ++p;
    while (*p && *p != '"') ++p;
    if (!*p || p == a || p - a > 15) return false;  // sin cierre / vacio / absurdo
    r.sym.assign(a, (size_t)(p - a));
    return true;
}

// ---------------------------------------------------------------------------
// FlowBook: estado de spikes por simbolo (replay flow_pulse). on_record()
// en orden temporal; consultas *_active()/fresh() a un instante t dado.
// ---------------------------------------------------------------------------
class FlowBook {
public:
    void on_record(double ts, const std::string& sym, double vc, double vp) {
        if (!(ts > 0) || vc < 0 || vp < 0) return;
        S& h = m_[sym];
        h.last_seen = std::max(h.last_seen, ts);
        if (h.have_prev && ts > h.prev_ts) {
            const double mins = (ts - h.prev_ts) / 60.0;
            if (mins >= 1.0 && mins <= 30.0) {
                const double dc = vc - h.prev_vc, dp = vp - h.prev_vp;
                if (dc >= 0 && dp >= 0) {
                    const double rc = dc / mins, rp = dp / mins;
                    const bool spike_c = h.ema_c > 0 && rc >= SPIKE_X * h.ema_c && dc >= SPIKE_MIN;
                    const bool spike_p = h.ema_p > 0 && rp >= SPIKE_X * h.ema_p && dp >= SPIKE_MIN;
                    const bool artifact = (spike_c && spike_p) ||
                                          (h.ema_c > 0 && rc > ARTIFACT_X * h.ema_c) ||
                                          (h.ema_p > 0 && rp > ARTIFACT_X * h.ema_p);
                    if (artifact) {
                        ++artifacts_;                       // mudo, EMA INTACTA
                        h.prev_ts = ts; h.prev_vc = vc; h.prev_vp = vp;
                        return;
                    }
                    if (spike_c && dc >= 2 * dp) h.last_calls = ts;  // dominancia 2x
                    if (spike_p && dp >= 2 * dc) h.last_puts = ts;
                    h.ema_c = h.ema_c < 0 ? rc : EMA_A * rc + (1 - EMA_A) * h.ema_c;
                    h.ema_p = h.ema_p < 0 ? rp : EMA_A * rp + (1 - EMA_A) * h.ema_p;
                }
            }
        }
        h.have_prev = true;
        h.prev_ts = ts; h.prev_vc = vc; h.prev_vp = vp;
    }

    // spike-calls vigente en t (<=20 min y no del futuro)
    bool calls_active(const std::string& sym, double t) const {
        const S* h = find(sym);
        return h && h->last_calls > 0 && t >= h->last_calls && t - h->last_calls <= VIGENCIA_S;
    }
    bool puts_active(const std::string& sym, double t) const {
        const S* h = find(sym);
        return h && h->last_puts > 0 && t >= h->last_puts && t - h->last_puts <= VIGENCIA_S;
    }
    // contexto de flujo: ALGUN registro del simbolo a <=30 min de t
    bool fresh(const std::string& sym, double t) const {
        const S* h = find(sym);
        return h && h->last_seen > 0 && t - h->last_seen <= FRESH_S && h->last_seen - t <= FRESH_S;
    }
    size_t artifacts() const { return artifacts_; }

private:
    struct S {
        bool   have_prev = false;
        double prev_ts = 0, prev_vc = 0, prev_vp = 0;
        double ema_c = -1.0, ema_p = -1.0;
        double last_calls = -1.0, last_puts = -1.0, last_seen = -1.0;
    };
    const S* find(const std::string& sym) const {
        const auto it = m_.find(sym);
        return it == m_.end() ? nullptr : &it->second;
    }
    std::unordered_map<std::string, S> m_;
    size_t artifacts_ = 0;
};

// ------------------------------ contadores ----------------------------------
struct ComboStats {
    size_t cand = 0;          // candidatos elastic del nucleo BB
    size_t sin_contexto = 0;  // sin flujo fresco (propio o capitan) -> NO emite
    size_t veto_propio = 0;   // spike EN CONTRA del propio ticker vigente
    size_t veto_capitan = 0;  // spike EN CONTRA de un capitan vigente
    size_t emit_plain = 0;    // emitidas kind=combo_elastic
    size_t emit_captain = 0;  // emitidas kind=combo_captain (refuerzo capitan)
};

// ---------------------------------------------------------------------------
// ComboEngine: envuelve bbcore::Engine (SOLO elastic — squeeze/bandwalk
// apagados a la fuerza) y filtra por contexto de flujo + capitanes.
// El FlowBook lo alimenta el driver (merge temporal, cero look-ahead).
// ---------------------------------------------------------------------------
class ComboEngine {
public:
    ComboEngine(std::string sym, Config cfg, int base_tf_secs,
                std::function<int(double)> hm_fn, const FlowBook& fb)
        : sym_(sym), base_tf_(base_tf_secs), fb_(fb),
          captains_(captains_of(sym)),
          eng_(std::move(sym), force_elastic_only(cfg), base_tf_secs, std::move(hm_fn)) {}

    std::vector<Signal> on_bar(const Bar& b) {
        std::vector<Signal> out;
        const double tdec = b.t + base_tf_;   // decision al CIERRE de la barra
        for (const Signal& s : eng_.on_bar(b)) {
            if (s.kind != "ELASTIC") continue;  // combo = solo elastic (diseño)
            ++st_.cand;
            bool ctx = fb_.fresh(sym_, tdec);
            for (const auto& cap : captains_) ctx = ctx && fb_.fresh(cap, tdec);
            if (!ctx) { ++st_.sin_contexto; continue; }   // sin flujo = sin señal
            const bool lng = s.side == "LONG";
            // (a/b) spike EN CONTRA del propio ticker: LONG<-calls, SHORT<-puts
            if (lng ? fb_.calls_active(sym_, tdec) : fb_.puts_active(sym_, tdec)) {
                ++st_.veto_propio; continue;
            }
            bool cap_contra = false, cap_favor = false;
            for (const auto& cap : captains_) {
                if (lng ? fb_.calls_active(cap, tdec) : fb_.puts_active(cap, tdec)) cap_contra = true;
                if (lng ? fb_.puts_active(cap, tdec) : fb_.calls_active(cap, tdec)) cap_favor = true;
            }
            if (cap_contra) { ++st_.veto_capitan; continue; }  // capitan prevalece
            Signal o = s;
            o.kind = cap_favor ? "combo_captain" : "combo_elastic";
            (cap_favor ? st_.emit_captain : st_.emit_plain)++;
            out.push_back(std::move(o));
        }
        return out;
    }

    const ComboStats& stats() const { return st_; }
    const std::vector<std::string>& captains() const { return captains_; }

private:
    static Config force_elastic_only(Config c) {
        c.squeeze_enabled = false;   // combo = SOLO elastic gated por flujo
        c.bandwalk_enabled = false;
        return c;
    }
    std::string sym_;
    int         base_tf_;
    const FlowBook& fb_;
    std::vector<std::string> captains_;
    ComboStats  st_;
    bbcore::Engine eng_;
};

} // namespace combocore
