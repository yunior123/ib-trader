// ============================================================================
// engines/bb_core.h — MOTOR 2 (B7): nucleo Bollinger PURO, header-only.
//
// SOLO Bollinger. Sin I/O de broker, sin voz, sin ordenes (SEÑAL-SOLAMENTE).
// - BB(20,2) POBLACIONAL (/N) incremental O(1) (patron V5BB de
//   scripts/v5_block.cpp.tmpl, mejorado a sumas rodantes: resta el saliente).
// - %B, bandwidth y percentil rodante de bandwidth (ventana 125).
// - Deteccion: elastic pierce+re-entrada (base TF: 1m si hay, si no 5m),
//   band-walk 5m/15m (veto de reversion / señal de continuacion),
//   squeeze-break direccional (bandwidth pctile <= 20 antes del break).
// - Cero look-ahead: cada decision usa SOLO barras cerradas <= su timestamp.
//   El epoch de la señal es el START de la barra que dispara; el scorer entra
//   en el OPEN de la siguiente barra 5m (start > epoch) — sin mirar adelante.
// ============================================================================
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

namespace bbcore {

struct Bar { double t = 0, o = 0, h = 0, l = 0, c = 0, v = 0; };

// ---------------------------------------------------------------------------
// BB(20,2) POBLACIONAL (/N), incremental O(1): sumas rodantes sobre un ring.
// sd = sqrt(max(0, E[x^2]-E[x]^2)) — jamas divide por cero ni produce NaN.
// ---------------------------------------------------------------------------
class BB {
public:
    static constexpr int P = 20;
    void update(double c) {
        const int i = n_ % P;
        if (n_ >= P) { sum_ -= ring_[i]; sum2_ -= ring_[i] * ring_[i]; }
        ring_[i] = c; sum_ += c; sum2_ += c * c; ++n_;
        const int k = n_ < P ? n_ : P;
        mid = sum_ / k;
        const double var = sum2_ / k - mid * mid;   // varianza POBLACIONAL /N
        sd = var > 0 ? std::sqrt(var) : 0.0;        // degenerada -> sd=0, no NaN
        up = mid + 2 * sd; dn = mid - 2 * sd;
    }
    bool   ready() const { return n_ >= P; }
    int    count() const { return n_; }
    // %B: 0 = banda inferior, 1 = superior. sd=0 (banda plana) -> 0.5.
    double pctB(double c) const { const double w = up - dn; return w > 0 ? (c - dn) / w : 0.5; }
    double bandwidth() const { return mid != 0 ? (up - dn) / std::fabs(mid) : 0.0; }
    double mid = 0, up = 0, dn = 0, sd = 0;
private:
    double ring_[P] = {0};
    double sum_ = 0, sum2_ = 0;
    int    n_ = 0;
};

// ---------------------------------------------------------------------------
// Percentil rodante de bandwidth, ventana 125 (~2 sesiones en 5m).
// rank(bw) = % de valores de la ventana <= bw. Se consulta ANTES de push
// para que el valor actual no se compare consigo mismo.
// ---------------------------------------------------------------------------
class BWPct {
public:
    static constexpr int W = 125;
    void push(double bw) { ring_[n_ % W] = bw; ++n_; }
    bool ready() const { return n_ >= W; }
    double rank(double bw) const {
        const int k = n_ < W ? n_ : W;
        if (k <= 0) return 50.0;
        int c = 0;
        for (int i = 0; i < k; ++i) if (ring_[i] <= bw) ++c;
        return 100.0 * c / k;
    }
private:
    double ring_[W] = {0};
    int    n_ = 0;
};

// --------------------------- ATR(14) Wilder --------------------------------
class ATR14 {
public:
    void update(const Bar& b) {
        double tr = b.h - b.l;
        if (n_ > 0) {
            tr = std::max(tr, std::fabs(b.h - prev_c_));
            tr = std::max(tr, std::fabs(b.l - prev_c_));
        }
        prev_c_ = b.c;
        atr_ = n_ == 0 ? tr : (atr_ * 13 + tr) / 14;
        ++n_;
    }
    bool   ready() const { return n_ >= 14; }
    double value() const { return atr_; }
private:
    double atr_ = 0, prev_c_ = 0;
    int    n_ = 0;
};

// ---------------------------------------------------------------------------
// Agregador de TF (patron V5TF): barras base -> barras de `secs`. La barra
// del TF se declara CERRADA cuando llega la primera barra base del bucket
// siguiente (unico momento en que su OHLC es definitivo — cero look-ahead).
// ---------------------------------------------------------------------------
class TFAgg {
public:
    explicit TFAgg(int secs) : secs_(secs) {}
    // true si esta barra base cerro una barra del TF (leer con closed()).
    bool update(const Bar& b) {
        bool closed_now = false;
        const double bucket = b.t - std::fmod(b.t, (double)secs_);
        if (!have_ || bucket != ep0_) {
            if (have_) { closed_ = cur_; closed_now = true; have_closed_ = true; }
            ep0_ = bucket; cur_ = b; cur_.t = bucket; have_ = true;
        } else {
            cur_.h = std::max(cur_.h, b.h);
            cur_.l = std::min(cur_.l, b.l);
            cur_.c = b.c; cur_.v += b.v;
        }
        return closed_now;
    }
    bool       has_closed() const { return have_closed_; }
    const Bar& closed() const { return closed_; }
private:
    int    secs_;
    double ep0_ = 0;
    Bar    cur_{}, closed_{};
    bool   have_ = false, have_closed_ = false;
};

// ---------------------------------------------------------------------------
// Elastic pierce + re-entrada. Pierce = CIERRE fuera de la banda (el wick
// solo no arma el gatillo — menos ruido, doctrina "print o nada"). Durante
// el pierce se acumula el extremo (min low / max high). La primera barra que
// CIERRA de vuelta dentro de la banda dispara el evento.
// ---------------------------------------------------------------------------
struct ElasticEvent {
    int    dir = 0;          // +1 = LONG (rebote desde abajo), -1 = SHORT, 0 = nada
    double pierce_ext = 0;   // min low (LONG) / max high (SHORT) del pierce
    double mid = 0;          // media BB al disparo (target natural)
    double px = 0;           // close de la barra de re-entrada (ref_px)
    int    pierce_bars = 0;  // nº de barras que duro el pierce
};
class Elastic {
public:
    // Llamar con la BB YA actualizada con b.c (patron V5BB).
    ElasticEvent on_close(const BB& bb, const Bar& b) {
        ElasticEvent ev;
        if (!bb.ready()) { in_dn_ = in_up_ = false; return ev; }
        if (b.c < bb.dn) {
            if (!in_dn_) { in_dn_ = true; ext_lo_ = b.l; ndn_ = 1; }
            else { ext_lo_ = std::min(ext_lo_, b.l); ++ndn_; }
            in_up_ = false;
            return ev;
        }
        if (b.c > bb.up) {
            if (!in_up_) { in_up_ = true; ext_hi_ = b.h; nup_ = 1; }
            else { ext_hi_ = std::max(ext_hi_, b.h); ++nup_; }
            in_dn_ = false;
            return ev;
        }
        if (in_dn_) { ev.dir = +1; ev.pierce_ext = ext_lo_; ev.pierce_bars = ndn_; }
        else if (in_up_) { ev.dir = -1; ev.pierce_ext = ext_hi_; ev.pierce_bars = nup_; }
        if (ev.dir) { ev.mid = bb.mid; ev.px = b.c; }
        in_dn_ = in_up_ = false;
        return ev;
    }
    bool in_pierce_dn() const { return in_dn_; }
    bool in_pierce_up() const { return in_up_; }
private:
    bool   in_dn_ = false, in_up_ = false;
    double ext_lo_ = 0, ext_hi_ = 0;
    int    ndn_ = 0, nup_ = 0;
};

// -------- band-walk: racha de cierres consecutivos fuera de la banda -------
class BandWalk {
public:
    void on_close(const BB& bb, double c) {
        if (!bb.ready()) { run_up_ = run_dn_ = 0; return; }
        run_up_ = c > bb.up ? run_up_ + 1 : 0;
        run_dn_ = c < bb.dn ? run_dn_ + 1 : 0;
    }
    bool burst_up() const { return run_up_ >= 1; }   // ultimo cierre fuera
    bool burst_dn() const { return run_dn_ >= 1; }
    bool walking_up(int k = 3) const { return run_up_ >= k; }
    bool walking_dn(int k = 3) const { return run_dn_ >= k; }
private:
    int run_up_ = 0, run_dn_ = 0;
};

// ------------------------------- señal -------------------------------------
struct Signal {
    double      epoch = 0;       // START de la barra que dispara
    std::string sym, side, kind; // side = LONG|SHORT
    double      ref_px = 0, target_px = 0, stop_px = 0;
    double      pctb = 0;        // %B del TF base al disparo (contexto)
};

// ------------------------------- config ------------------------------------
struct Config {
    bool elastic_enabled  = true;   // fallback: elastic basico
    bool bandwalk_enabled = false;
    bool squeeze_enabled  = true;
    // vetos implementables de bollinger_plus.json (F1/F2/F3/F4/F8 se ignoran
    // con degradacion limpia — necesitan RVOL/RSI/VWAP/ADX, fuera del nucleo BB)
    bool veto_f5_squeeze  = false;  // suprimir elastic si bw pctile <= 20
    bool veto_f7_15m_in   = false;  // suprimir elastic si cierre 15m DENTRO de banda
    bool veto_win[4] = {false, false, false, false}; // 945-1030,1030-1130,1130-1400,1400-1530
    double cool_elastic_s = 900, cool_squeeze_s = 1800, cool_bwalk_s = 3600;
    double squeeze_pct_max = 20.0;  // umbral F5
    int    rth_open_hm = 945, rth_close_hm = 1555; // 9:30-9:45 jamas (subasta)
};

// ---------------------------------------------------------------------------
// Engine: recibe barras BASE cerradas (1m o 5m), agrega 5m/15m, emite señales.
// hm_fn(epoch) -> HHMM hora ET del instante (inyectable para tests).
// ---------------------------------------------------------------------------
class Engine {
public:
    Engine(std::string sym, Config cfg, int base_tf_secs,
           std::function<int(double)> hm_fn)
        : sym_(std::move(sym)), cfg_(cfg), base_tf_(base_tf_secs),
          hm_fn_(std::move(hm_fn)), agg5_(300), agg15_(900) {}

    std::vector<Signal> on_bar(const Bar& b) {
        std::vector<Signal> out;
        // --- 15m siempre agregado desde base
        if (agg15_.update(b)) {
            const Bar& k = agg15_.closed();
            bb15_.update(k.c); walk15_.on_close(bb15_, k.c);
            last15_close_ = k.c; have15_ = bb15_.ready();
        }
        // --- 5m: agregado si base=1m; la propia barra si base=5m
        bool closed5 = false; Bar bar5{};
        if (base_tf_ < 300) {
            if (agg5_.update(b)) { closed5 = true; bar5 = agg5_.closed(); }
        } else { closed5 = true; bar5 = b; }
        if (closed5) {
            bb5_.update(bar5.c); walk5_.on_close(bb5_, bar5.c);
            atr5_.update(bar5);
            const double bw = bb5_.bandwidth();
            prev_bw_pct_ = cur_bw_pct_;               // pctile ANTES de esta barra
            cur_bw_pct_ = bwpct_.rank(bw);            // rank vs ventana previa
            bwpct_.push(bw);
            squeeze_signals(bar5, out);
            bandwalk_signals(bar5, out);
        }
        // --- TF base para elastic (1m si base=1m, la misma 5m si no)
        if (base_tf_ < 300) { bb1_.update(b.c); elastic_signal(bb1_, b, out); }
        else if (closed5)   { elastic_signal(bb5_, bar5, out); }
        return out;
    }

    // estado expuesto (tests / live)
    const BB& bb_base() const { return base_tf_ < 300 ? bb1_ : bb5_; }
    const BB& bb5() const { return bb5_; }
    const BB& bb15() const { return bb15_; }
    double bw_pct() const { return cur_bw_pct_; }

private:
    static bool in_win(int hm, int a, int b) { return hm >= a && hm < b; }

    bool rth_ok(double bar_close_epoch, int& hm) const {
        hm = hm_fn_(bar_close_epoch);
        return hm >= cfg_.rth_open_hm && hm < cfg_.rth_close_hm;
    }
    bool window_vetoed(int hm) const {
        static constexpr int W[4][2] = {{945,1030},{1030,1130},{1130,1400},{1400,1530}};
        for (int i = 0; i < 4; ++i)
            if (cfg_.veto_win[i] && in_win(hm, W[i][0], W[i][1])) return true;
        return false;
    }
    // check-only: el timestamp se estampa SOLO si push() emite de verdad
    // (antes cooled() mutaba antes de validar la geometria -> una señal
    // degenerada quemaba el cooldown y suprimia la siguiente señal buena).
    static bool cool_ok(double last, double now, double cool) {
        return !(last > 0 && now - last < cool);
    }
    bool push(std::vector<Signal>& out, double epoch, const char* side,
              const char* kind, double ref, double tgt, double stp, double pctb) {
        // sanity: target y stop al lado correcto; degenerado = no emite
        const bool lng = !std::strcmp(side, "LONG");
        if (lng && !(tgt > ref && stp < ref)) return false;
        if (!lng && !(tgt < ref && stp > ref)) return false;
        out.push_back({epoch, sym_, side, kind, ref, tgt, stp, pctb});
        return true;
    }

    void elastic_signal(const BB& bb, const Bar& b, std::vector<Signal>& out) {
        const ElasticEvent ev = elastic_.on_close(bb, b);
        if (!ev.dir || !cfg_.elastic_enabled || !atr5_.ready()) return;
        int hm;
        if (!rth_ok(b.t + base_tf_, hm) || window_vetoed(hm)) return;
        // veto F5: post-squeeze la banda es estrecha, el rebote no paga
        if (cfg_.veto_f5_squeeze && bwpct_.ready() && cur_bw_pct_ <= cfg_.squeeze_pct_max) return;
        // veto F7: cierre 15m DENTRO de su banda
        if (cfg_.veto_f7_15m_in && have15_ && last15_close_ < bb15_.up && last15_close_ > bb15_.dn) return;
        // veto band-walk EN CONTRA en TF mayores (doctrina: 2-3 TF a favor = continuacion)
        const bool walk_dn = (base_tf_ < 300 ? (walk5_.burst_dn() && walk15_.burst_dn())
                                             : (have15_ && walk15_.burst_dn()));
        const bool walk_up = (base_tf_ < 300 ? (walk5_.burst_up() && walk15_.burst_up())
                                             : (have15_ && walk15_.burst_up()));
        const double a = atr5_.value();
        if (ev.dir > 0 && !walk_dn && cool_ok(last_el_long_, b.t, cfg_.cool_elastic_s)
            && push(out, b.t, "LONG", "ELASTIC", ev.px, ev.mid, ev.pierce_ext - 0.5 * a, bb.pctB(ev.px)))
            last_el_long_ = b.t;
        if (ev.dir < 0 && !walk_up && cool_ok(last_el_short_, b.t, cfg_.cool_elastic_s)
            && push(out, b.t, "SHORT", "ELASTIC", ev.px, ev.mid, ev.pierce_ext + 0.5 * a, bb.pctB(ev.px)))
            last_el_short_ = b.t;
    }

    void squeeze_signals(const Bar& b5, std::vector<Signal>& out) {
        if (!cfg_.squeeze_enabled || !bwpct_.ready() || !atr5_.ready() || !bb5_.ready()) return;
        int hm;
        if (!rth_ok(b5.t + 300, hm)) return;
        if (prev_bw_pct_ > cfg_.squeeze_pct_max) return;  // sin squeeze previo, no hay break
        const double a = atr5_.value();
        if (b5.c > bb5_.up && cool_ok(last_sq_long_, b5.t, cfg_.cool_squeeze_s)
            && push(out, b5.t, "LONG", "SQZ_BRK", b5.c, b5.c + 2 * a, b5.c - a, bb5_.pctB(b5.c)))
            last_sq_long_ = b5.t;
        else if (b5.c < bb5_.dn && cool_ok(last_sq_short_, b5.t, cfg_.cool_squeeze_s)
                 && push(out, b5.t, "SHORT", "SQZ_BRK", b5.c, b5.c - 2 * a, b5.c + a, bb5_.pctB(b5.c)))
            last_sq_short_ = b5.t;
    }

    void bandwalk_signals(const Bar& b5, std::vector<Signal>& out) {
        if (!cfg_.bandwalk_enabled || !atr5_.ready() || !have15_) return;
        int hm;
        if (!rth_ok(b5.t + 300, hm)) return;
        const double a = atr5_.value();
        if (walk5_.walking_up() && walk15_.burst_up() && cool_ok(last_bw_long_, b5.t, cfg_.cool_bwalk_s)
            && push(out, b5.t, "LONG", "BWALK", b5.c, b5.c + 2 * a, b5.c - a, bb5_.pctB(b5.c)))
            last_bw_long_ = b5.t;
        else if (walk5_.walking_dn() && walk15_.burst_dn() && cool_ok(last_bw_short_, b5.t, cfg_.cool_bwalk_s)
                 && push(out, b5.t, "SHORT", "BWALK", b5.c, b5.c - 2 * a, b5.c + a, bb5_.pctB(b5.c)))
            last_bw_short_ = b5.t;
    }

    std::string sym_;
    Config      cfg_;
    int         base_tf_;
    std::function<int(double)> hm_fn_;
    TFAgg  agg5_, agg15_;
    BB     bb1_, bb5_, bb15_;
    BandWalk walk5_, walk15_;
    ATR14  atr5_;
    BWPct  bwpct_;
    Elastic elastic_;
    double prev_bw_pct_ = 100, cur_bw_pct_ = 100;
    double last15_close_ = 0;
    bool   have15_ = false;
    double last_el_long_ = 0, last_el_short_ = 0;
    double last_sq_long_ = 0, last_sq_short_ = 0;
    double last_bw_long_ = 0, last_bw_short_ = 0;
};

// ---------------------------------------------------------------------------
// Parser de linea de barra: acepta "epoch,o,h,l,c,v" o "epoch o h l c v"
// (los bars_<sym>_ibkr.txt vivos van con espacios). Header/linea malformada
// -> false, jamas crashea. v opcional (default 0).
// ---------------------------------------------------------------------------
inline bool parse_bar_line(const char* line, Bar& b) {
    double f[6] = {0, 0, 0, 0, 0, 0};
    int nf = 0;
    const char* p = line;
    while (*p && nf < 6) {
        while (*p == ',' || *p == ' ' || *p == '\t' || *p == '\r') ++p;
        if (!*p || *p == '\n') break;
        char* end = nullptr;
        const double x = std::strtod(p, &end);
        if (end == p) return false;  // token no numerico (header, basura)
        if (!std::isfinite(x)) return false;
        f[nf++] = x;
        p = end;
    }
    if (nf < 5) return false;
    if (f[0] <= 0) return false;                       // epoch invalido
    b = {f[0], f[1], f[2], f[3], f[4], f[5]};
    if (b.h < b.l || b.c <= 0 || b.o <= 0) return false;  // OHLC roto
    return true;
}

} // namespace bbcore
