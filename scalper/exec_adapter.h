// exec_adapter.h — capa de ejecucion del whale scalper.
// ExecutionAdapter: interfaz unica; SimAdapter (completo, determinista) para
// SIM/replay; TwsAdapter = STUB Fase 4 (API C++ oficial vendoreada, ver skill
// ibkr-tws). El FSM jamas sabe contra que corre — mismo codigo sim y live.
#pragma once
#include <cstdint>
#include <deque>
#include <random>
#include "scalper_core.h"

namespace scalp {

struct ExecReport {
    int order_id = 0;
    enum K { ACK, FILL, CANCELED, REJECTED } kind = ACK;
    int px_c = 0;
    int64_t t_mono_ms = 0;
};

struct ExecutionAdapter {
    virtual int  send_limit(char side /*'B'|'S'*/, const OptContract&, int limit_c, int order_id) = 0;
    virtual void cancel(int order_id) = 0;
    virtual bool poll(ExecReport& out) = 0;                       // drena de a uno, no bloquea
    virtual OptQuote quote(const OptContract&) = 0;               // NBBO del contrato en mano
    virtual ~ExecutionAdapter() = default;
};

// ------------------------------------------------------------- SimAdapter
// Fill model honesto para limits marketable:
//  - BUY lmt L: al llegar (latencia U(50,300)ms) si ask<=L -> fill al ASK
//    actual (jamas mejora, deriva adversa si). Con prob ADVERSE_PCT el ask
//    escapa +1c durante la latencia. Si ask>L la orden DESCANSA y solo llena
//    si el ask vuelve <=L antes del cancel. SELL simetrico contra el bid.
//  - Cancel tambien viaja (latencia): un fill puede ganarle al cancel.
// Quote sintetico: BS sobre el mid del subyacente con IV/spread sembrados
// del chain real; theta emerge de T decreciente hacia las 16:00 ET.
class SimAdapter final : public ExecutionAdapter {
public:
    SimAdapter(const Cfg& cfg, Clock& clk) : cfg_(cfg), clk_(clk), rng_(cfg.sim_seed) {}

    // el motor sim alimenta el mundo: subyacente + parametros del contrato
    void set_underlying(const Nbbo& n) { und_ = n; }
    void set_iv(double iv) { iv_ = iv; }
    void set_secs_to_close(int64_t s) { secs_to_close_ = s; }
    void set_opt_spread_c(int c) { opt_spread_c_ = c > 0 ? c : 4; }

    OptQuote quote(const OptContract& con) override {
        OptQuote q;
        if (!und_.ok() || !con.valid()) return q;
        double S = (double)(und_.bid_c + und_.ask_c) / 200.0;      // mid en dolares
        double K = (double)con.strike_c / 100.0;
        double T = (double)std::max<int64_t>(secs_to_close_, 0) / (365.0 * 24 * 3600);
        double px = bs_price(S, K, T, iv_, con.right);
        int mid_c = (int)std::llround(px * 100.0);
        if (mid_c < 1) mid_c = 1;
        q.bid_c = std::max(1, mid_c - opt_spread_c_ / 2);
        q.ask_c = q.bid_c + std::max(1, opt_spread_c_);
        return q;
    }

    int send_limit(char side, const OptContract& con, int limit_c, int order_id) override {
        Pending p; p.oid = order_id; p.side = side; p.con = con; p.limit_c = limit_c;
        p.t_arrive = clk_.mono_ms() + lat_ms_();
        // seleccion adversa modelada como TIEMPO: el mercado se mueve contra
        // el limit y el fill tarda 300-900ms extra (chase real de 0DTE).
        if (pct_(cfg_.adverse_pct)) p.t_arrive += 300 + (int64_t)(rng_() % 601);
        p.reject = pct_(cfg_.reject_pct);
        working_.push_back(p);
        return order_id;
    }

    void cancel(int order_id) override {
        int64_t t = clk_.mono_ms() + lat_ms_();
        for (auto& p : working_) if (p.oid == order_id && !p.done) p.t_cancel = t;
    }

    // avanzar el mundo: llamar cada tick ANTES de poll()
    void tick() {
        int64_t now = clk_.mono_ms();
        for (auto& p : working_) {
            if (p.done || now < p.t_arrive) continue;
            if (p.reject) { emit(p, ExecReport::REJECTED, 0); continue; }
            OptQuote q = quote(p.con);
            if (!q.ok()) continue;                       // mundo sin quote: la orden espera
            if (p.side == 'B') {
                if (q.ask_c <= p.limit_c) { emit(p, ExecReport::FILL, q.ask_c); continue; }
            } else {
                if (q.bid_c >= p.limit_c) { emit(p, ExecReport::FILL, q.bid_c); continue; }
            }
            if (p.t_cancel && now >= p.t_cancel) emit(p, ExecReport::CANCELED, 0);
        }
        while (!working_.empty() && working_.front().done && working_.front().reported)
            working_.pop_front();
    }

    bool poll(ExecReport& out) override {
        for (auto& p : working_) {
            if (p.done && !p.reported) { p.reported = true; out = p.report; return true; }
        }
        return false;
    }

private:
    struct Pending {
        int oid = 0; char side = 0; OptContract con{}; int limit_c = 0;
        int64_t t_arrive = 0, t_cancel = 0;
        bool reject = false, done = false, reported = false;
        ExecReport report{};
    };
    void emit(Pending& p, ExecReport::K k, int px) {
        p.done = true;
        p.report = {p.oid, k, px, clk_.mono_ms()};
    }
    int64_t lat_ms_() { return 50 + (int64_t)(rng_() % 251); }     // U(50,300)
    bool pct_(int pct) { return pct > 0 && (int)(rng_() % 100) < pct; }

    const Cfg& cfg_; Clock& clk_;
    std::mt19937_64 rng_;
    Nbbo und_{}; double iv_ = 0.20; int64_t secs_to_close_ = 3600; int opt_spread_c_ = 4;
    std::deque<Pending> working_;
};

// ------------------------------------------------------------- TwsAdapter (Fase 4 — STUB)
// Implementacion futura con la API C++ oficial (EClientSocket/EWrapper/EReader,
// clientId 90, paper 7497 primero). Doble llave: --arm-live + scalper/ARM_LIVE
// con la fecha de hoy. Ver .claude/skills/ibkr-tws/SKILL.md para el patron
// completo (nextValidId, orderStatus/execDetails/commissionReport, errores).
class TwsAdapter final : public ExecutionAdapter {
public:
    int  send_limit(char, const OptContract&, int, int) override { die(); return 0; }
    void cancel(int) override { die(); }
    bool poll(ExecReport&) override { return false; }
    OptQuote quote(const OptContract&) override { return {}; }
private:
    [[noreturn]] void die() {
        std::fprintf(stderr, "TwsAdapter: Fase 4 no implementada — SIM solamente\n");
        std::abort();
    }
};

} // namespace scalp
