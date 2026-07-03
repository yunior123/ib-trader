// scalper_core.h — nucleo PURO del whale scalper (2026-07-21).
// Todo lo testeable vive aqui: FSM, dinero (int64 cents), seleccion de
// contrato, parsers (JSONL + Desktop txt), gates, Black-Scholes, Clock.
// Cero I/O, cero sockets, cero threads. El binario y los tests lo incluyen.
//
// Tactica espada-ballena (CLAUDE.md regla 11): BALLENA CALLS = techo local
// -> comprar PUT QQQ 0DTE tras WAIT_MS; BALLENA PUTS = piso -> comprar CALL.
// Profit 1%->5% NETO en <=60s con trailing; sin profit a 60s = fuera a
// cualquier precio. Un trade rojo neto = HALT + post-mortem.
#pragma once
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace scalp {

// ---------------------------------------------------------------- config
struct Cfg {
    // timing (ms salvo indicado)
    int64_t wait_ms            = 2500;   // espera tras alerta (dejar moverse al mercado)
    int64_t entry_timeout_ms   = 1500;   // por intento de entrada
    int     entry_max_attempts = 3;
    int64_t profit_min_ms      = 3000;   // profit check activo desde t_fill+3s
    int64_t profit_window_ms   = 30000;  // ventana 1
    int64_t profit_ext_ms      = 30000;  // extension -> 60s total
    int64_t exit_reprice_ms    = 2000;   // re-price del SELL
    int     exit_escalate_n    = 3;      // tras N reprices: bid - 2 ticks
    int64_t exit_hard_ms       = 60000;  // watchdog EXIT_STUCK
    int64_t cooldown_ms        = 120000; // tras trade verde
    // dinero (cents)
    int64_t budget_c           = 20000;  // $200
    int     max_premium_c      = 200;    // ask por accion <= $2.00
    int     commission_side_c  = 65;     // $0.65/lado -> $1.30 RT
    int     profit_min_bp      = 100;    // +1% NETO minimo
    int     profit_max_bp      = 500;    // +5% NETO: toma inmediata
    int     trail_c            = 3;      // trailing: bid retrocede 3c desde pico
    int64_t trail_arm_after_ms = 0;      // trail activo desde que se alcanza min
    int64_t sell_latest_ms     = 55000;  // con profit armado, vender a los 55s si no salto antes
    // gates
    int     spread_max_bp      = 500;    // 5% del ask
    int     spread_max_abs_c   = 3;      // o 3c, lo que sea MAYOR
    int     max_trades_day     = 3;
    int64_t nbbo_stale_s       = 5;
    int64_t nbbo_hold_grace_ms = 2000;   // gracia antes de salida forzada por NBBO stale en mano
    int64_t chain_stale_s      = 600;
    int     win1_open_hhmm     = 945,  win1_close_hhmm = 1130;   // ventana 1 ET
    int     win2_open_hhmm     = 1400, win2_close_hhmm = 1530;   // ventana 2 ET
    int     force_flat_hhmm    = 1555;
    // sim
    uint64_t sim_seed          = 7;
    int      adverse_pct       = 30;     // % de que el ask escape 1c en la latencia
    int      reject_pct        = 0;
    std::vector<std::string> impact_syms =
        {"QQQ","NVDA","MSFT","AAPL","AVGO","AMZN","META","GOOGL","TSLA","MU"};

    bool is_impact(std::string_view s) const {
        for (auto& x : impact_syms) if (x == s) return true;
        return false;
    }
};

// key=value loader (lineas '#' = comentario). Desconocidos: ignorados con aviso.
inline void cfg_set(Cfg& c, std::string_view k, std::string_view v) {
    auto n = [&]() -> int64_t { return std::strtoll(std::string(v).c_str(), nullptr, 10); };
    if      (k == "WAIT_MS") c.wait_ms = n();
    else if (k == "ENTRY_TIMEOUT_MS") c.entry_timeout_ms = n();
    else if (k == "ENTRY_MAX_ATTEMPTS") c.entry_max_attempts = (int)n();
    else if (k == "PROFIT_MIN_MS") c.profit_min_ms = n();
    else if (k == "PROFIT_WINDOW_MS") c.profit_window_ms = n();
    else if (k == "PROFIT_EXT_MS") c.profit_ext_ms = n();
    else if (k == "EXIT_REPRICE_MS") c.exit_reprice_ms = n();
    else if (k == "EXIT_ESCALATE_N") c.exit_escalate_n = (int)n();
    else if (k == "EXIT_HARD_MS") c.exit_hard_ms = n();
    else if (k == "COOLDOWN_MS") c.cooldown_ms = n();
    else if (k == "BUDGET_C") c.budget_c = n();
    else if (k == "MAX_PREMIUM_C") c.max_premium_c = (int)n();
    else if (k == "COMMISSION_SIDE_C") c.commission_side_c = (int)n();
    else if (k == "PROFIT_MIN_BP") c.profit_min_bp = (int)n();
    else if (k == "PROFIT_MAX_BP") c.profit_max_bp = (int)n();
    else if (k == "TRAIL_C") c.trail_c = (int)n();
    else if (k == "SELL_LATEST_MS") c.sell_latest_ms = n();
    else if (k == "SPREAD_MAX_BP") c.spread_max_bp = (int)n();
    else if (k == "SPREAD_MAX_ABS_C") c.spread_max_abs_c = (int)n();
    else if (k == "MAX_TRADES_DAY") c.max_trades_day = (int)n();
    else if (k == "NBBO_STALE_S") c.nbbo_stale_s = n();
    else if (k == "NBBO_HOLD_GRACE_MS") c.nbbo_hold_grace_ms = n();
    else if (k == "CHAIN_STALE_S") c.chain_stale_s = n();
    else if (k == "WIN1_OPEN") c.win1_open_hhmm = (int)n();
    else if (k == "WIN1_CLOSE") c.win1_close_hhmm = (int)n();
    else if (k == "WIN2_OPEN") c.win2_open_hhmm = (int)n();
    else if (k == "WIN2_CLOSE") c.win2_close_hhmm = (int)n();
    else if (k == "FORCE_FLAT") c.force_flat_hhmm = (int)n();
    else if (k == "SIM_SEED") c.sim_seed = (uint64_t)n();
    else if (k == "ADVERSE_PCT") c.adverse_pct = (int)n();
    else if (k == "REJECT_PCT") c.reject_pct = (int)n();
    else if (k == "IMPACT_SYMS") {
        c.impact_syms.clear();
        std::string cur;
        for (char ch : v) {
            if (ch == ',' || ch == ' ') { if (!cur.empty()) c.impact_syms.push_back(cur); cur.clear(); }
            else cur += ch;
        }
        if (!cur.empty()) c.impact_syms.push_back(cur);
    }
    else std::fprintf(stderr, "cfg: clave desconocida ignorada: %.*s\n", (int)k.size(), k.data());
}

// ---------------------------------------------------------------- clock
struct Clock {
    virtual int64_t mono_ms() = 0;        // duraciones
    virtual int64_t wall_s()  = 0;        // epoch (stamps + staleness)
    virtual int     et_hhmm() = 0;        // hora ET para gates horarios
    virtual ~Clock() = default;
};
struct SimClock final : Clock {
    int64_t m = 0, w = 0; int hhmm = 1000;
    int64_t acc_ = 0;   // resto sub-segundo: sin el, pasos de 50ms jamas avanzan w
    int64_t mono_ms() override { return m; }
    int64_t wall_s()  override { return w; }
    int     et_hhmm() override { return hhmm; }
    void advance_ms(int64_t ms) { m += ms; acc_ += ms; w += acc_ / 1000; acc_ %= 1000; }
};

// ---------------------------------------------------------------- tipos de mercado
struct Nbbo { int64_t epoch_s = 0; int64_t bid_c = 0, ask_c = 0; bool ok() const { return epoch_s > 0 && bid_c > 0 && ask_c > bid_c; } };

struct ChainRow { int64_t strike_c = 0; char right = 0; int exp = 0; int bid_c = 0, ask_c = 0; double iv = 0, delta = 0; };
struct Chain {
    int64_t epoch_s = 0; int64_t spot_c = 0; int exp0 = 0;   // exp0 = primera expiry del header
    std::vector<ChainRow> rows;
    bool ok() const { return epoch_s > 0 && spot_c > 0 && !rows.empty(); }
};

struct OptContract {
    int64_t strike_c = 0; char right = 0; int yyyymmdd = 0;
    bool valid() const { return strike_c > 0 && (right == 'P' || right == 'C'); }
};
struct OptQuote { int bid_c = 0, ask_c = 0; bool ok() const { return bid_c >= 1 && ask_c > bid_c; } };

struct Alert {
    int64_t ts = 0; char side = 0; /* 'C' = BALLENA CALLS, 'P' = PUTS */
    std::string sym; double pc = 0;
    bool esc = false;   // 🐋📈 BALLENA CRECE (prev=ESCALADA): NO es flip — jamas gatillo de entrada
};

// ---------------------------------------------------------------- dinero (int64 cents, SIEMPRE)
inline int64_t net_cost_c(int fill_c, const Cfg& c)  { return (int64_t)fill_c * 100 + c.commission_side_c; }
inline int64_t net_exit_c(int bid_c, const Cfg& c)   { return (int64_t)bid_c  * 100 - c.commission_side_c; }
// umbral: net_exit >= net_cost * (1 + bp/10000), entero, mul antes de div
inline bool profit_reached(int64_t cost_c, int64_t exit_c, int bp) {
    return exit_c * 10000 >= cost_c * (10000 + bp);
}
// cordura: precios en cents dentro de lo fisicamente posible ($200k techo).
// Protege llround/int contra NaN/Inf/overflow de archivos corruptos.
inline bool sane_px_c(int64_t c)     { return c > 0 && c <= 20'000'000; }
inline bool sane_epoch_s(int64_t s)  { return s > 0 && s < 4'102'444'800LL; }  // < año 2100
inline bool finite_all(std::initializer_list<double> xs) {
    for (double x : xs) if (!std::isfinite(x)) return false;
    return true;
}
// edad de una posicion recuperada: tw del ledger (us) vs ahora (us), clamp >=0
inline int64_t age_ms_from_us(int64_t now_us, int64_t then_us) {
    if (then_us <= 0 || now_us <= then_us) return 0;
    return (now_us - then_us) / 1000;
}

// ---------------------------------------------------------------- Black-Scholes (erfc, sin libs)
inline double norm_cdf(double x) { return 0.5 * std::erfc(-x / std::sqrt(2.0)); }
// precio en DOLARES por accion; call/put europeo, r=0 (0DTE, irrelevante)
inline double bs_price(double S, double K, double T_years, double iv, char right) {
    if (T_years <= 0 || iv <= 0) {  // expirado o sin vol: intrinseco
        double intr = (right == 'C') ? S - K : K - S;
        return intr > 0 ? intr : 0.0;
    }
    double sq = iv * std::sqrt(T_years);
    double d1 = (std::log(S / K) + 0.5 * iv * iv * T_years) / sq;
    double d2 = d1 - sq;
    if (right == 'C') return S * norm_cdf(d1) - K * norm_cdf(d2);
    return K * norm_cdf(-d2) - S * norm_cdf(-d1);
}

// ---------------------------------------------------------------- parsers
// NBBO subyacente: "EPOCH BID ASK" (bid/ask en dolares con decimales)
inline std::optional<Nbbo> parse_nbbo(std::string_view line) {
    double ep, b, a;
    if (std::sscanf(std::string(line).c_str(), "%lf %lf %lf", &ep, &b, &a) != 3) return std::nullopt;
    if (!finite_all({ep, b, a})) return std::nullopt;            // "nan"/"inf" parsean en %lf
    if (b <= 0 || a <= 0 || b > 200000.0 || a > 200000.0) return std::nullopt;
    Nbbo n; n.epoch_s = (int64_t)ep;
    n.bid_c = (int64_t)std::llround(b * 100.0); n.ask_c = (int64_t)std::llround(a * 100.0);
    if (!n.ok() || !sane_epoch_s(n.epoch_s) || !sane_px_c(n.ask_c)) return std::nullopt;
    return n;
}

// opt_chain_qqq.txt: header "# opt_chain QQQ | epoch N | fecha | spot X | exps E0 E1" + filas
inline std::optional<Chain> parse_chain(std::string_view text) {
    Chain ch;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t eol = text.find('\n', pos);
        if (eol == std::string_view::npos) eol = text.size();
        std::string line(text.substr(pos, eol - pos));
        pos = eol + 1;
        if (line.empty()) continue;
        if (line[0] == '#') {
            if (line.find("opt_chain") != std::string::npos) {
                double ep = 0, spot = 0; char e0[16] = {0};
                const char* p;
                if ((p = std::strstr(line.c_str(), "epoch "))) ep = std::atof(p + 6);
                if ((p = std::strstr(line.c_str(), "spot ")))  spot = std::atof(p + 5);
                if ((p = std::strstr(line.c_str(), "exps "))) std::sscanf(p + 5, "%15s", e0);
                if (!finite_all({ep, spot}) || spot < 0 || spot > 200000.0) continue;  // header corrupto: ch.ok() vetara
                ch.epoch_s = (int64_t)ep;
                ch.spot_c  = (int64_t)std::llround(spot * 100.0);
                ch.exp0    = std::atoi(e0);
            }
            continue;
        }
        double k, b, a, iv, delta, gamma; char r; long vol, oi; int exp;
        if (std::sscanf(line.c_str(), "%lf %c %d %lf %lf %ld %ld %lf %lf %lf",
                        &k, &r, &exp, &b, &a, &vol, &oi, &iv, &delta, &gamma) != 10) continue;
        // cordura por fila: NaN/Inf/absurdos NO entran al selector (un int negativo
        // por overflow pasaria los gates de premium/presupuesto y compraria basura)
        if (!finite_all({k, b, a, iv, delta})) continue;
        if (k <= 0 || k > 200000.0) continue;                       // strike ($) fisicamente posible
        if (b < -1.0 || b > 20000.0 || a < 0 || a > 20000.0) continue;  // -1.00 = sentinel "sin bid"
        ChainRow row;
        row.strike_c = (int64_t)std::llround(k * 100.0); row.right = r; row.exp = exp;
        row.bid_c = (int)std::llround(b * 100.0); row.ask_c = (int)std::llround(a * 100.0);
        row.iv = iv; row.delta = delta;
        ch.rows.push_back(row);
    }
    if (!ch.ok()) return std::nullopt;
    return ch;
}

// alerta JSONL: {"ts":N,"side":"PUTS"|"CALLS"|"MID","sym":"QQQ","pc":x,...}
// extractor minimo sin lib json: claves conocidas, orden libre, tolerante
// a espacios tras ':' (json.dumps de Python los pone por defecto).
inline size_t json_val_pos(std::string_view line, const char* key) {
    std::string pat = std::string("\"") + key + "\":";
    size_t p = line.find(pat);
    if (p == std::string_view::npos) {
        pat = std::string("\"") + key + "\" :";           // "key" : v
        p = line.find(pat);
        if (p == std::string_view::npos) return std::string_view::npos;
    }
    p += pat.size();
    while (p < line.size() && (line[p] == ' ' || line[p] == '\t')) ++p;
    return p;
}
inline std::optional<Alert> parse_alert_jsonl(std::string_view line) {
    auto find_str = [&](const char* key) -> std::string {
        size_t p = json_val_pos(line, key);
        if (p == std::string_view::npos || p >= line.size() || line[p] != '"') return {};
        ++p;
        size_t q = line.find('"', p);
        if (q == std::string_view::npos) return {};
        return std::string(line.substr(p, q - p));
    };
    auto find_num = [&](const char* key) -> double {
        size_t p = json_val_pos(line, key);
        if (p == std::string_view::npos) return 0;
        return std::atof(std::string(line.substr(p)).c_str());
    };
    std::string side = find_str("side"), sym = find_str("sym");
    if (sym.empty()) return std::nullopt;
    double ts_d = find_num("ts"), pc_d = find_num("pc");
    if (!std::isfinite(ts_d)) return std::nullopt;
    Alert a; a.ts = (int64_t)ts_d; a.sym = sym;
    a.pc = std::isfinite(pc_d) ? pc_d : 0.0;
    if      (side == "CALLS") a.side = 'C';
    else if (side == "PUTS")  a.side = 'P';
    else return std::nullopt;          // "MID" u otros: transicion, no señal operable
    // 🐋📈 BALLENA CRECE (2026-07-22): mismo estado, volumen duplicado. NO es
    // flip — el flujo SIGUE creciendo (evidencia de continuacion, no de extremo).
    a.esc = (find_str("prev") == "ESCALADA");
    if (!sane_epoch_s(a.ts)) return std::nullopt;
    return a;
}
// lote de lineas nuevas del tail -> TODAS las alertas parseables, en orden.
// (antes solo se tomaba la primera y el resto del mismo tick se PERDIA)
inline std::vector<Alert> parse_alert_lines(const std::vector<std::string>& lines) {
    std::vector<Alert> v;
    for (auto& l : lines) if (auto a = parse_alert_jsonl(l)) v.push_back(*a);
    return v;
}

// fallback Desktop txt: "HH:MM:SS | 🐋 BALLENA CALLS | SYM: ..." (emoji UTF-8 literal)
inline std::optional<Alert> parse_alert_txt(std::string_view line, int64_t day_epoch_midnight) {
    int hh, mm, ss;
    if (std::sscanf(std::string(line.substr(0, 8)).c_str(), "%d:%d:%d", &hh, &mm, &ss) != 3) return std::nullopt;
    size_t w = line.find("\xF0\x9F\x90\x8B BALLENA ");   // 🐋
    if (w == std::string_view::npos) return std::nullopt;
    std::string_view rest = line.substr(w + 4 + 9);      // tras "🐋 BALLENA "
    char side = 0;
    if      (rest.starts_with("CALLS")) side = 'C';
    else if (rest.starts_with("PUTS"))  side = 'P';
    else return std::nullopt;
    size_t bar = rest.find("| ");
    if (bar == std::string_view::npos) return std::nullopt;
    std::string_view tail = rest.substr(bar + 2);
    size_t colon = tail.find(':');
    if (colon == std::string_view::npos || colon == 0 || colon > 6) return std::nullopt;
    std::string sym(tail.substr(0, colon));
    for (char c : sym) if (!std::isupper((unsigned char)c)) return std::nullopt;
    Alert a; a.side = side; a.sym = sym;
    a.ts = day_epoch_midnight + hh * 3600 + mm * 60 + ss;
    return a;
}

// ---------------------------------------------------------------- seleccion de contrato
// Primer strike ESTRICTAMENTE OTM vs spot con ask<=max_premium y gates de
// bid/spread; si el primero falla, UN strike mas OTM; luego nada.
inline bool spread_ok(int bid_c, int ask_c, const Cfg& c) {
    int64_t lim = std::max<int64_t>((int64_t)c.spread_max_bp * ask_c / 10000, c.spread_max_abs_c);
    return (ask_c - bid_c) <= lim;
}
struct Selection { OptContract con; int bid_c = 0, ask_c = 0; double iv = 0, delta = 0; };
inline std::optional<Selection> select_contract(const Chain& ch, char buy_right, int today_yyyymmdd, const Cfg& cfg) {
    if (ch.exp0 != today_yyyymmdd) return std::nullopt;   // guard 0DTE (finde/feriado)
    std::vector<const ChainRow*> otm;
    for (auto& r : ch.rows) {
        if (r.right != buy_right || r.exp != today_yyyymmdd) continue;
        bool is_otm = (buy_right == 'P') ? r.strike_c < ch.spot_c : r.strike_c > ch.spot_c;
        if (is_otm) otm.push_back(&r);
    }
    // orden: del mas cercano al spot hacia afuera
    std::sort(otm.begin(), otm.end(), [&](const ChainRow* a, const ChainRow* b) {
        return std::llabs(a->strike_c - ch.spot_c) < std::llabs(b->strike_c - ch.spot_c);
    });
    int tried = 0;
    for (auto* r : otm) {
        if (++tried > 2) break;                            // primer OTM + 1 reserva
        if (r->bid_c < 1) continue;                        // -1.00 = sin bid: veneno
        if (r->ask_c > cfg.max_premium_c) continue;
        if (!spread_ok(r->bid_c, r->ask_c, cfg)) continue;
        if ((int64_t)r->ask_c * 100 + cfg.commission_side_c > cfg.budget_c) continue;
        Selection s; s.con = {r->strike_c, r->right, r->exp};
        s.bid_c = r->bid_c; s.ask_c = r->ask_c; s.iv = r->iv; s.delta = r->delta;
        return s;
    }
    return std::nullopt;
}

// ---------------------------------------------------------------- FSM
enum class St { IDLE, ARMED_WAIT, ENTRY_PENDING, HOLDING, EXIT_PENDING, HALTED };
inline const char* st_name(St s) {
    switch (s) {
        case St::IDLE: return "IDLE"; case St::ARMED_WAIT: return "ARMED_WAIT";
        case St::ENTRY_PENDING: return "ENTRY_PENDING"; case St::HOLDING: return "HOLDING";
        case St::EXIT_PENDING: return "EXIT_PENDING"; case St::HALTED: return "HALTED";
    }
    return "?";
}

// acciones que el motor ejecuta (el FSM no hace I/O)
struct Action {
    enum K { SEND_BUY, SEND_SELL, CANCEL, LEDGER, NOTIFY, HALT_WRITE } k;
    OptContract con{}; int limit_c = 0; int order_id = 0;
    std::string ev, reason;              // LEDGER: ev+reason | NOTIFY: ev=titulo, reason=msg
};

struct Inputs {
    Nbbo und;                            // NBBO subyacente fresco
    const Chain* chain = nullptr;        // cache de cadena (para seleccion)
    OptQuote opt;                        // quote del contrato en mano (del adapter)
    bool halt_file = false;
    int  today_yyyymmdd = 0;
    // eventos del adapter este tick (0 o 1; el motor los drena de a uno)
    enum Ev { NONE, ACK, FILL, CANCELED, REJECTED } ev = NONE;
    int ev_order_id = 0; int ev_px_c = 0;
    std::optional<Alert> alert;          // alerta nueva este tick (ya parseada)
};

class Fsm {
public:
    Fsm(const Cfg& cfg, Clock& clk) : cfg_(cfg), clk_(clk) {}

    St state() const { return st_; }
    int trades_today() const { return trades_today_; }
    const OptContract& held() const { return con_; }
    bool has_position() const { return st_ == St::HOLDING || st_ == St::EXIT_PENDING; }

    // recovery: arrancar ya en HOLDING (posicion viva encontrada en el ledger)
    void recover_holding(const OptContract& c, int fill_c, int64_t age_ms, std::vector<Action>& out) {
        con_ = c; fill_c_ = fill_c; t_fill_ = clk_.mono_ms() - age_ms;
        st_ = St::HOLDING; peak_bid_c_ = 0; profit_armed_ = false;
        last_opt_bid_c_ = 0;   // contrato de procedencia desconocida: sin bid heredado
        led(out, "RECOVER", "posicion recuperada del ledger");
        if (age_ms > cfg_.profit_window_ms + cfg_.profit_ext_ms)
            begin_exit(out, "FORCED", "recovery: posicion mas vieja que la ventana");
    }

    // recovery de contadores del dia (kill -9 tras TRADE_CLOSE): sin esto, un
    // restart borra trades_today/one-loss-halt/cooldown y el bot re-opera un
    // dia ya rojo. red_close = algun TRADE_CLOSE con net<=0 en el ledger.
    void recover_day(int closes, bool red_close, int64_t ms_since_close, std::vector<Action>& out) {
        trades_today_ = closes;
        if (closes > 0 && ms_since_close >= 0 && ms_since_close < cfg_.cooldown_ms) {
            int64_t t = clk_.mono_ms() - ms_since_close;
            t_last_close_ = t > 0 ? t : 1;                 // 0 significaria "sin cierre previo"
        }
        if (red_close) {
            loss_halted_ = true;
            if (!has_position()) st_ = St::HALTED;         // con posicion viva: gestionarla, pero jamas re-entrar
            led(out, "RECOVER", "ledger con trade rojo neto hoy — HALT restaurado tras restart");
        } else if (closes > 0) {
            led(out, "RECOVER", "contadores del dia restaurados: " + std::to_string(closes) + " cierres");
        }
    }

    void step(const Inputs& in, std::vector<Action>& out) {
        const int64_t now = clk_.mono_ms();
        const int hhmm = clk_.et_hhmm();
        if (in.opt.ok()) last_opt_bid_c_ = in.opt.bid_c;   // memoria para salidas a ciegas

        // ordenes canceladas: CANCELED/REJECTED confirman muerte -> olvidarlas
        if (in.ev == Inputs::CANCELED || in.ev == Inputs::REJECTED)
            std::erase_if(cxld_, [&](const CxldOrd& c) { return c.oid == in.ev_order_id; });
        // FILL que el estado actual NO espera (el fill le gano al cancel, o oid
        // desconocido): dinero real — JAMAS ignorarlo en silencio.
        if (in.ev == Inputs::FILL) {
            bool expected = (st_ == St::ENTRY_PENDING || st_ == St::EXIT_PENDING) && in.ev_order_id == oid_;
            if (!expected) { handle_stale_fill(in, out); return; }
        }

        // HALT file: bloquea ENTRADAS; una posicion viva se gestiona hasta salir
        if (in.halt_file && (st_ == St::IDLE || st_ == St::ARMED_WAIT)) {
            if (st_ == St::ARMED_WAIT) { st_ = St::IDLE; led(out, "GATE_SKIP", "HALT file"); }
        }

        switch (st_) {
        case St::HALTED: return;

        case St::IDLE: {
            if (!in.alert) return;
            const Alert& a = *in.alert;
            // ESCALADA = el flujo del MISMO lado se duplico: no hay flip, no hay
            // extremo nuevo — entrar contra una marea que crece es perseguir.
            if (a.esc) { led(out, "ALERT_IGNORED", "escalada (no flip) — no es gatillo: " + a.sym); return; }
            if (!cfg_.is_impact(a.sym)) { led(out, "ALERT_IGNORED", "fuera de IMPACT_SYMS: " + a.sym); return; }
            if (in.halt_file)           { led(out, "GATE_SKIP", "HALT file"); return; }
            if (loss_halted_)           { led(out, "GATE_SKIP", "one-loss halt"); return; }
            if (trades_today_ >= cfg_.max_trades_day) { led(out, "GATE_SKIP", "max trades/dia"); return; }
            if (t_last_close_ && now - t_last_close_ < cfg_.cooldown_ms) { led(out, "GATE_SKIP", "cooldown"); return; }
            if (!window_open(hhmm))     { led(out, "GATE_SKIP", "fuera de ventana horaria"); return; }
            // BALLENA CALLS = techo -> PUT; BALLENA PUTS = piso -> CALL
            buy_right_ = (a.side == 'C') ? 'P' : 'C';
            alert_sym_ = a.sym; t_alert_ = now;
            st_ = St::ARMED_WAIT;
            led(out, "ALERT", a.sym + std::string(1, ' ') + (a.side == 'C' ? "CALLS->PUT" : "PUTS->CALL"));
            return;
        }

        case St::ARMED_WAIT: {
            if (in.alert) {
                const Alert& a = *in.alert;
                // filtro de seguridad: ESCALADA del mismo simbolo y mismo lado
                // durante el wait = la marea sigue entrando (continuacion, no
                // extremo) -> abortar la entrada contraria. Excepcion regla 11.
                if (a.esc && a.sym == alert_sym_ &&
                    ((a.side == 'C') == (buy_right_ == 'P'))) {
                    st_ = St::IDLE;
                    led(out, "GATE_SKIP", "escalada en contra durante wait — flujo sigue creciendo, no fade");
                    return;
                }
                led(out, "ALERT_IGNORED", "ya armado con " + alert_sym_);
            }
            if (now - t_alert_ < cfg_.wait_ms) return;
            // gates al disparo
            const char* skip = nullptr;
            if (!window_open(hhmm))                        skip = "ventana cerro durante wait";
            else if (!in.und.ok())                         skip = "NBBO invalido";
            else if (clk_.wall_s() - in.und.epoch_s > cfg_.nbbo_stale_s) skip = "NBBO stale";
            else if (!in.chain || !in.chain->ok())         skip = "chain ausente";
            else if (clk_.wall_s() - in.chain->epoch_s > cfg_.chain_stale_s) skip = "chain stale";
            if (skip) { st_ = St::IDLE; led(out, "GATE_SKIP", skip); return; }
            auto sel = select_contract(*in.chain, buy_right_, in.today_yyyymmdd, cfg_);
            if (!sel) { st_ = St::IDLE; led(out, "GATE_SKIP", "sin contrato elegible"); return; }
            con_ = sel->con;
            // contrato NUEVO seleccionado: el bid memorizado (posiblemente del
            // contrato de una entrada abandonada que el driver siguio cotizando
            // via held()) JAMAS pone precio a una salida a ciegas de este trade
            last_opt_bid_c_ = 0;
            attempt_ = 1;
            send_buy(out, sel->ask_c);
            st_ = St::ENTRY_PENDING;
            return;
        }

        case St::ENTRY_PENDING: {
            if (in.alert) led(out, "ALERT_IGNORED", "entrada en curso");
            if (in.ev == Inputs::FILL && in.ev_order_id == oid_) {
                fill_c_ = in.ev_px_c; t_fill_ = now;
                peak_bid_c_ = 0; profit_armed_ = false;
                st_ = St::HOLDING;
                // px_c REAL en el evento (el recovery lee px_c, no el reason)
                out.push_back({Action::LEDGER, con_, fill_c_, oid_, "FILL",
                               "BUY @ " + std::to_string(fill_c_) + "c"});
                return;
            }
            if (in.ev == Inputs::REJECTED && in.ev_order_id == oid_) {
                st_ = St::IDLE; led(out, "ORDER_REJECT", "BUY rechazada — sin dinero movido");
                return;
            }
            // aborto de seguridad (2026-07-22): HALT file o force-flat con un BUY
            // vivo = cancelar YA (el fill que gane al cancel se adopta igual y
            // la posicion se gestiona/cierra por la doctrina normal).
            if (in.halt_file || hhmm >= cfg_.force_flat_hhmm) {
                send_cancel(out, 'B');
                st_ = St::IDLE;
                led(out, "GATE_SKIP", in.halt_file ? "HALT file durante entrada — BUY cancelado"
                                                   : "force-flat durante entrada — BUY cancelado");
                return;
            }
            if (now - t_order_ >= cfg_.entry_timeout_ms) {
                send_cancel(out, 'B');
                led(out, "ORDER_CANCEL", "entrada sin fill en timeout, intento " + std::to_string(attempt_));
                if (attempt_ >= cfg_.entry_max_attempts || !in.opt.ok()) {
                    st_ = St::IDLE; led(out, "NO_FILL", "sin fill tras " + std::to_string(attempt_) + " intentos");
                    return;
                }
                int ask = in.opt.ask_c;
                if (ask > cfg_.max_premium_c ||
                    (int64_t)ask * 100 + cfg_.commission_side_c > cfg_.budget_c ||
                    !spread_ok(in.opt.bid_c, ask, cfg_)) {
                    st_ = St::IDLE; led(out, "NO_FILL", "re-price rompe gates (ask " + std::to_string(ask) + "c)");
                    return;
                }
                ++attempt_;
                send_buy(out, ask);
            }
            return;
        }

        case St::HOLDING: {
            if (in.alert) led(out, "ALERT_IGNORED", "posicion abierta");
            const int64_t held_ms = now - t_fill_;
            // salidas forzadas de seguridad
            if (hhmm >= cfg_.force_flat_hhmm) { begin_exit(out, "FORCED", "force-flat 15:55"); return; }
            if (in.halt_file)                 { begin_exit(out, "FORCED", "HALT file en mano"); return; }
            if (in.und.ok() && clk_.wall_s() - in.und.epoch_s > cfg_.nbbo_stale_s && held_ms > cfg_.nbbo_hold_grace_ms) {
                begin_exit(out, "FORCED", "NBBO stale con posicion"); return;
            }
            // NBBO jamas visto/invalido (peor que stale): misma gracia, misma salida
            if (!in.und.ok() && held_ms > cfg_.nbbo_hold_grace_ms) {
                begin_exit(out, "FORCED", "NBBO invalido con posicion"); return;
            }
            if (held_ms >= cfg_.profit_window_ms + cfg_.profit_ext_ms) {
                begin_exit(out, "FORCED", "60s sin profit — cortar"); return;
            }
            if (held_ms < cfg_.profit_min_ms || !in.opt.ok()) return;
            // algoritmo de profit 1%->5% NETO con trailing
            const int64_t cost = net_cost_c(fill_c_, cfg_);
            const int64_t exitv = net_exit_c(in.opt.bid_c, cfg_);
            if (profit_reached(cost, exitv, cfg_.profit_max_bp)) {   // +5%: tomar YA
                begin_exit(out, "PROFIT", "+5% neto alcanzado"); return;
            }
            if (profit_reached(cost, exitv, cfg_.profit_min_bp)) {
                if (!profit_armed_) { profit_armed_ = true; peak_bid_c_ = in.opt.bid_c;
                                      led(out, "TRAIL_ARMED", "min +1% neto alcanzado"); }
                peak_bid_c_ = std::max(peak_bid_c_, in.opt.bid_c);
                if (in.opt.bid_c <= peak_bid_c_ - cfg_.trail_c) { begin_exit(out, "PROFIT", "trailing stop"); return; }
                if (held_ms >= cfg_.sell_latest_ms)             { begin_exit(out, "PROFIT", "55s: cobrar lo armado"); return; }
            } else if (profit_armed_) {
                // el profit se evaporo por debajo del minimo. JAMAS realizar
                // rojo voluntariamente: si aun es verde, cobrar; si no,
                // desarmar y aguantar (re-armado o salida forzada a los 60s).
                if (exitv > cost) { begin_exit(out, "PROFIT", "profit evapora — cobrar verde"); return; }
                profit_armed_ = false; peak_bid_c_ = 0;
                led(out, "TRAIL_DISARM", "profit evaporado bajo breakeven — aguantar");
            }
            return;
        }

        case St::EXIT_PENDING: {
            if (in.alert) led(out, "ALERT_IGNORED", "salida en curso");
            if (in.ev == Inputs::FILL && in.ev_order_id == oid_) {
                close_trade(out, in.ev_px_c);
                return;
            }
            if (in.ev == Inputs::REJECTED && in.ev_order_id == oid_) {
                led(out, "ORDER_REJECT", "SELL rechazada — resend inmediato");
                int px = in.opt.ok() ? in.opt.bid_c : sell_px_c_;
                send_sell(out, px);
                return;
            }
            if (now - t_exit_start_ >= cfg_.exit_hard_ms && !exit_stuck_) {
                exit_stuck_ = true;
                led(out, "EXIT_STUCK", "SELL sin fill en 60s — alarma");
                out.push_back({Action::NOTIFY, {}, 0, 0, "🛑 SCALPER EXIT STUCK",
                               "venta sin fill 60s — revisar TWS/mercado YA"});
            }
            if (now - t_order_ >= cfg_.exit_reprice_ms) {
                send_cancel(out, 'S');
                int px = in.opt.ok() ? in.opt.bid_c : sell_px_c_ - 1;
                ++exit_reprices_;
                if (exit_reprices_ >= cfg_.exit_escalate_n) px -= 2;   // cruce garantizado
                if (px < 1) px = 1;
                send_sell(out, px);
            }
            return;
        }
        }
    }

private:
    // ordenes canceladas cuya muerte aun no se confirmo: un FILL de estas es
    // dinero real (el fill le gano al cancel en el cable) y hay que adoptarlo.
    struct CxldOrd { int oid = 0; char side = 0; OptContract con{}; };
    std::vector<CxldOrd> cxld_;

    void send_cancel(std::vector<Action>& out, char side) {
        out.push_back({Action::CANCEL, con_, 0, oid_, "", ""});
        cxld_.push_back({oid_, side, con_});
        if (cxld_.size() > 8) cxld_.erase(cxld_.begin());   // acotado: jamas crece sin limite
    }

    void handle_stale_fill(const Inputs& in, std::vector<Action>& out) {
        auto it = std::find_if(cxld_.begin(), cxld_.end(),
                               [&](const CxldOrd& c) { return c.oid == in.ev_order_id; });
        if (it == cxld_.end()) {
            led(out, "ORPHAN_FILL", "FILL oid " + std::to_string(in.ev_order_id) +
                     " desconocido en " + st_name(st_) + " — revisar YA");
            out.push_back({Action::NOTIFY, {}, 0, 0, "🛑 SCALPER FILL HUERFANO",
                           "fill de orden desconocida — posicion sin gestionar, revisar TWS/ledger YA"});
            return;
        }
        CxldOrd c = *it; cxld_.erase(it);
        if (c.side == 'B') {
            if (st_ == St::IDLE || st_ == St::ARMED_WAIT || st_ == St::ENTRY_PENDING) {
                // el BUY cancelado lleno igual: adoptar la posicion y gestionarla
                // con la doctrina normal (profit 1->5%, salida forzada a 60s).
                if (st_ == St::ENTRY_PENDING) send_cancel(out, 'B');   // matar la orden viva
                con_ = c.con; fill_c_ = in.ev_px_c; t_fill_ = clk_.mono_ms();
                peak_bid_c_ = 0; profit_armed_ = false;
                st_ = St::HOLDING;
                out.push_back({Action::LEDGER, con_, fill_c_, oid_, "FILL_ADOPT",
                               "BUY cancelado lleno @ " + std::to_string(fill_c_) +
                               "c — el fill gano al cancel; posicion adoptada, gestion normal"});
            } else {
                led(out, "DOUBLE_FILL", "BUY cancelado lleno en " + std::string(st_name(st_)) +
                         " — contrato EXTRA sin gestionar");
                out.push_back({Action::NOTIFY, {}, 0, 0, "🛑 SCALPER DOBLE FILL",
                               "BUY cancelado lleno con posicion ya en curso — contrato extra, revisar YA"});
            }
        } else {
            if (st_ == St::EXIT_PENDING) {
                // el SELL cancelado lleno igual: ese ES el cierre; matar el resend vivo
                send_cancel(out, 'S');
                close_trade(out, in.ev_px_c);
            } else {
                led(out, "DOUBLE_FILL", "SELL cancelado lleno en " + std::string(st_name(st_)) +
                         " — posible venta doble (corto)");
                out.push_back({Action::NOTIFY, {}, 0, 0, "🛑 SCALPER DOBLE VENTA",
                               "SELL cancelado lleno fuera de salida — posible corto, revisar YA"});
            }
        }
    }

    bool window_open(int hhmm) const {
        return (hhmm >= cfg_.win1_open_hhmm && hhmm < cfg_.win1_close_hhmm) ||
               (hhmm >= cfg_.win2_open_hhmm && hhmm < cfg_.win2_close_hhmm);
    }
    void led(std::vector<Action>& out, std::string ev, std::string reason) {
        out.push_back({Action::LEDGER, con_, 0, oid_, std::move(ev), std::move(reason)});
    }
    void send_buy(std::vector<Action>& out, int limit_c) {
        oid_ = next_oid_++;
        t_order_ = clk_.mono_ms();
        out.push_back({Action::SEND_BUY, con_, limit_c, oid_, "", ""});
        led(out, "ORDER_SEND", "BUY lmt " + std::to_string(limit_c) + "c intento " + std::to_string(attempt_));
    }
    void send_sell(std::vector<Action>& out, int limit_c) {
        oid_ = next_oid_++;
        t_order_ = clk_.mono_ms();
        sell_px_c_ = limit_c;
        out.push_back({Action::SEND_SELL, con_, limit_c, oid_, "", ""});
        led(out, "ORDER_SEND", "SELL lmt " + std::to_string(limit_c) + "c");
    }
    void begin_exit(std::vector<Action>& out, const char* kind, const char* why) {
        exit_kind_ = kind; exit_reprices_ = 0; exit_stuck_ = false;
        t_exit_start_ = clk_.mono_ms();
        led(out, std::string("EXIT_") + kind, why);
        send_sell(out, last_opt_bid_c_ > 0 ? last_opt_bid_c_ : 1);
        st_ = St::EXIT_PENDING;
    }
    void close_trade(std::vector<Action>& out, int sell_fill_c) {
        const int64_t net = net_exit_c(sell_fill_c, cfg_) - net_cost_c(fill_c_, cfg_);
        ++trades_today_;
        t_last_close_ = clk_.mono_ms();
        led(out, "TRADE_CLOSE", "net " + std::to_string(net) + "c (buy " + std::to_string(fill_c_) +
                 " sell " + std::to_string(sell_fill_c) + ")");
        if (net <= 0) {
            loss_halted_ = true;
            st_ = St::HALTED;
            out.push_back({Action::HALT_WRITE, con_, (int)net, 0, "HALT",
                           "trade rojo neto " + std::to_string(net) + "c — revision obligatoria"});
            out.push_back({Action::NOTIFY, {}, 0, 0, "🛑 SCALPER HALT",
                           "trade rojo neto — bot parado, post-mortem en ledger"});
        } else {
            st_ = St::IDLE;
            out.push_back({Action::NOTIFY, {}, 0, 0, "💰 SCALPER VERDE",
                           "net +" + std::to_string(net) + "c — cooldown 120s"});
        }
        con_ = {}; fill_c_ = 0; profit_armed_ = false;
        // el bid memorizado era del contrato CERRADO: si el proximo trade
        // necesita una salida a ciegas, jamas usar el precio de otro contrato
        last_opt_bid_c_ = 0;
    }

    const Cfg& cfg_; Clock& clk_;
    St st_ = St::IDLE;
    // señal
    char buy_right_ = 0; std::string alert_sym_; int64_t t_alert_ = 0;
    // orden viva
    int oid_ = 0, next_oid_ = 1, attempt_ = 0; int64_t t_order_ = 0;
    // posicion
    OptContract con_{}; int fill_c_ = 0; int64_t t_fill_ = 0;
    bool profit_armed_ = false; int peak_bid_c_ = 0; int last_opt_bid_c_ = 0;
    // salida
    std::string exit_kind_; int exit_reprices_ = 0; int sell_px_c_ = 0;
    int64_t t_exit_start_ = 0; bool exit_stuck_ = false;
    // dia
    int trades_today_ = 0; int64_t t_last_close_ = 0; bool loss_halted_ = false;
};

} // namespace scalp
