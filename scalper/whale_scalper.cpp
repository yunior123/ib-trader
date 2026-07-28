// whale_scalper.cpp — motor 0DTE QQQ de la tactica espada-ballena (2026-07-21).
// SIM-FIRST: sin --arm-live + scalper/ARM_LIVE (fecha de hoy) JAMAS habla con
// TWS (y la Fase 4 ni existe aun: TwsAdapter aborta). La ley SEÑAL-SOLAMENTE
// de la flota queda intacta: este es el UNICO modulo autorizado a ejecutar,
// solo armado explicitamente.
//
// Modos:
//   --replay F.jsonl   escenario determinista con reloj virtual (tests)
//   --sim --data DIR   corre contra archivos (reales o de sim_feed.py), fills simulados
// build: ./scalper/build.sh   (clang++ -std=c++23 -O3 -march=native)
#include <sys/stat.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <deque>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include "scalper_core.h"
#include "exec_adapter.h"
#include "ledger.h"
#include "tail.h"
#include "../fleet_notify.h"

using namespace scalp;

// ------------------------------------------------------------- relojes
struct RealClock final : Clock {
    int64_t mono_ms() override {
        struct timespec ts{}; clock_gettime(CLOCK_MONOTONIC, &ts);
        return ts.tv_sec * 1000LL + ts.tv_nsec / 1000000;
    }
    int64_t wall_s() override { return ::time(nullptr); }
    int et_hhmm() override {                       // Mac de Yunior = Toronto = ET
        time_t t = ::time(nullptr); struct tm lt{}; localtime_r(&t, &lt);
        return lt.tm_hour * 100 + lt.tm_min;
    }
};
// sim_feed.py escribe simdata/clock.txt ("EPOCH.mmm HHMM"): el motor vive en
// el tiempo del feeder — aceleracion sin tocar ningun timer del FSM.
struct FeedClock final : Clock {
    std::string path; double ep = 0; int hhmm = 0;
    void refresh() {
        FILE* f = std::fopen(path.c_str(), "r");
        if (!f) return;
        double e; int h;
        if (std::fscanf(f, "%lf %d", &e, &h) == 2) { ep = e; hhmm = h; }
        std::fclose(f);
    }
    int64_t mono_ms() override { return (int64_t)(ep * 1000.0); }
    int64_t wall_s()  override { return (int64_t)ep; }
    int     et_hhmm() override { return hhmm; }
};

// ------------------------------------------------------------- helpers I/O
static std::string slurp(const std::string& p) {
    std::ifstream f(p);
    if (!f) return {};
    std::stringstream ss; ss << f.rdbuf();
    return ss.str();
}
static bool exists(const std::string& p) { struct stat st{}; return ::stat(p.c_str(), &st) == 0; }
static int64_t fmtime(const std::string& p) { struct stat st{}; return ::stat(p.c_str(), &st) == 0 ? (int64_t)st.st_mtime : 0; }
// Tail (incremental por offset, robusto a rotacion y lineas gigantes): tail.h

// ------------------------------------------------------------- ejecucion de acciones
static void run_actions(std::vector<Action>& acts, Fsm& fsm, ExecutionAdapter& ex,
                        Ledger& led, Clock& clk, const std::string& halt_path, bool live_banners) {
    for (auto& a : acts) {
        switch (a.k) {
        case Action::SEND_BUY:  ex.send_limit('B', a.con, a.limit_c, a.order_id); break;
        case Action::SEND_SELL: ex.send_limit('S', a.con, a.limit_c, a.order_id); break;
        case Action::CANCEL:    ex.cancel(a.order_id); break;
        case Action::LEDGER:
            led.write(a.ev.c_str(), st_name(fsm.state()), a.con, a.limit_c, a.order_id, a.reason, clk.mono_ms());
            std::fprintf(stderr, "%s | %s | %s\n", st_name(fsm.state()), a.ev.c_str(), a.reason.c_str());
            break;
        case Action::NOTIFY:
            led.write("NOTIFY", st_name(fsm.state()), a.con, 0, 0, a.ev + ": " + a.reason, clk.mono_ms());
            if (live_banners) fleet_notify_urgent(a.ev.c_str(), a.reason.c_str(), "ProAlarm");
            break;
        case Action::HALT_WRITE: {
            FILE* f = std::fopen(halt_path.c_str(), "w");
            if (f) { std::fprintf(f, "%s %s\n", Ledger::jesc(a.reason).c_str(), st_name(fsm.state())); std::fclose(f); }
            led.write("HALT", st_name(fsm.state()), a.con, a.limit_c, 0, a.reason, clk.mono_ms());
            led.postmortem(a.reason);
            break;
        }
        }
    }
    acts.clear();
}

// ------------------------------------------------------------- REPLAY (tests)
// eventos: {"t_ms":N,"ev":"und","bid_c":..,"ask_c":..[,"stale_s":S]}
//          {"t_ms":N,"ev":"chain","spot_c":..,"iv":..,"spread_c":..,"exp":..[,"nobid":1][,"stale_s":S]}
//          {"t_ms":N,"ev":"alert","side":"CALLS|PUTS","sym":"QQQ"}
//          {"t_ms":N,"ev":"hhmm","v":1005}   {"t_ms":N,"ev":"halt"} {"ev":"unhalt"}
//          {"t_ms":N,"ev":"expect_state","v":"HOLDING"}  {"ev":"expect_trades","v":1}
static double jnum(const std::string& l, const char* k, double dflt = 0) {
    std::string p = std::string("\"") + k + "\":";
    size_t q = l.find(p);
    return q == std::string::npos ? dflt : std::atof(l.c_str() + q + p.size());
}
static std::string jstr(const std::string& l, const char* k) {
    std::string p = std::string("\"") + k + "\":\"";
    size_t q = l.find(p);
    if (q == std::string::npos) return {};
    q += p.size();
    size_t e = l.find('"', q);
    return e == std::string::npos ? std::string{} : l.substr(q, e - q);
}
// cadena sintetica: strikes de $1 alrededor del spot, BS + spread fijo
static Chain synth_chain(int64_t spot_c, double iv, int spread_c, int exp, bool nobid, int64_t epoch, int64_t secs_to_close) {
    Chain ch; ch.epoch_s = epoch; ch.spot_c = spot_c; ch.exp0 = exp;
    double S = (double)spot_c / 100.0;
    double T = (double)secs_to_close / (365.0 * 24 * 3600);
    for (int d = -5; d <= 5; ++d) {
        int64_t k_c = ((spot_c + 50) / 100 + d) * 100;             // strike redondo en cents
        for (char r : {'C', 'P'}) {
            ChainRow row; row.strike_c = k_c; row.right = r; row.exp = exp; row.iv = iv;
            int mid = (int)std::llround(bs_price(S, (double)k_c / 100.0, T, iv, r) * 100.0);
            if (mid < 1) mid = 1;
            row.bid_c = nobid ? -100 : std::max(1, mid - spread_c / 2);
            row.ask_c = std::max(row.bid_c + std::max(1, spread_c), 2);
            ch.rows.push_back(row);
        }
    }
    return ch;
}

static int run_replay(const std::string& file, Cfg& cfg, const std::string& led_dir) {
    std::ifstream f(file);
    if (!f) { std::fprintf(stderr, "replay: no existe %s\n", file.c_str()); return 2; }
    SimClock clk;
    SimAdapter ex(cfg, clk);
    Ledger led(led_dir);
    Fsm fsm(cfg, clk);
    std::string halt_path = led_dir + "/HALT_replay";
    ::unlink(halt_path.c_str());
    Inputs in{}; in.today_yyyymmdd = 20260721;
    Chain chain{}; bool have_chain = false, halt = false;
    int fails = 0;
    std::vector<Action> acts;
    std::string line;
    int64_t iv_spread_c = 4;
    int64_t und_stale_s = 0, chain_stale_s = 0;   // staleness PEGAJOSA del escenario

    auto advance_to = [&](int64_t t_ms) {
        while (clk.m < t_ms) {
            clk.advance_ms(std::min<int64_t>(50, t_ms - clk.m));
            in.und.epoch_s = clk.wall_s() - und_stale_s;      // frescura automatica
            chain.epoch_s  = clk.wall_s() - chain_stale_s;
            ex.set_underlying(in.und);
            ex.tick();
            Inputs step = in; step.alert.reset();
            step.chain = have_chain ? &chain : nullptr;
            step.halt_file = halt;
            if (fsm.held().valid()) step.opt = ex.quote(fsm.held());
            ExecReport r;
            if (ex.poll(r)) {
                step.ev = r.kind == ExecReport::FILL ? Inputs::FILL :
                          r.kind == ExecReport::REJECTED ? Inputs::REJECTED :
                          r.kind == ExecReport::CANCELED ? Inputs::CANCELED : Inputs::ACK;
                step.ev_order_id = r.order_id; step.ev_px_c = r.px_c;
            }
            fsm.step(step, acts);
            run_actions(acts, fsm, ex, led, clk, halt_path, false);
        }
    };

    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        int64_t t = (int64_t)jnum(line, "t_ms", (double)clk.m);
        advance_to(t);
        in.und.epoch_s = clk.wall_s() - und_stale_s;
        chain.epoch_s  = clk.wall_s() - chain_stale_s;
        std::string ev = jstr(line, "ev");
        if (ev == "und") {
            in.und.bid_c = (int64_t)jnum(line, "bid_c"); in.und.ask_c = (int64_t)jnum(line, "ask_c");
            und_stale_s = (int64_t)jnum(line, "stale_s");
            in.und.epoch_s = clk.wall_s() - und_stale_s;
            ex.set_underlying(in.und);
        } else if (ev == "chain") {
            iv_spread_c = (int64_t)jnum(line, "spread_c", 4);
            int64_t stc = 3600 * 3;
            chain_stale_s = (int64_t)jnum(line, "stale_s");
            chain = synth_chain((int64_t)jnum(line, "spot_c"), jnum(line, "iv", 0.20), (int)iv_spread_c,
                                (int)jnum(line, "exp", 20260721), jnum(line, "nobid") > 0,
                                clk.wall_s() - chain_stale_s, stc);
            have_chain = true;
            ex.set_iv(jnum(line, "iv", 0.20));
            ex.set_opt_spread_c((int)iv_spread_c);
            ex.set_secs_to_close(stc);
        } else if (ev == "alert") {
            Alert a; a.ts = clk.wall_s(); a.sym = jstr(line, "sym");
            a.side = jstr(line, "side") == "CALLS" ? 'C' : 'P';
            a.esc = jstr(line, "prev") == "ESCALADA";   // 🐋📈 BALLENA CRECE
            Inputs step = in; step.chain = have_chain ? &chain : nullptr;
            step.halt_file = halt; step.alert = a;
            if (fsm.held().valid()) step.opt = ex.quote(fsm.held());
            fsm.step(step, acts);
            run_actions(acts, fsm, ex, led, clk, halt_path, false);
        } else if (ev == "hhmm") { clk.hhmm = (int)jnum(line, "v");
        } else if (ev == "halt") { halt = true;
        } else if (ev == "unhalt") { halt = false;
        } else if (ev == "cfg") { cfg_set(cfg, jstr(line, "k"), jstr(line, "v"));
        } else if (ev == "expect_state") {
            std::string want = jstr(line, "v");
            if (want != st_name(fsm.state())) {
                ++fails;
                std::fprintf(stderr, "REPLAY FAIL t=%lld: estado %s, esperado %s\n",
                             (long long)clk.m, st_name(fsm.state()), want.c_str());
            }
        } else if (ev == "expect_trades") {
            int want = (int)jnum(line, "v");
            if (want != fsm.trades_today()) {
                ++fails;
                std::fprintf(stderr, "REPLAY FAIL t=%lld: trades %d, esperado %d\n",
                             (long long)clk.m, fsm.trades_today(), want);
            }
        }
    }
    std::printf("%s: %s\n", file.c_str(), fails ? "FAIL" : "OK");
    return fails ? 1 : 0;
}

// ------------------------------------------------------------- SIM contra archivos
static int run_sim(const std::string& data, Cfg& cfg, const std::string& led_dir, bool live_banners) {
    RealClock rclk;
    FeedClock fclk; fclk.path = data + "/clock.txt";
    bool feed_clock = exists(fclk.path);
    Clock& clk = feed_clock ? (Clock&)fclk : (Clock&)rclk;
    if (feed_clock) std::fprintf(stderr, "sim: reloj del feeder (%s)\n", fclk.path.c_str());

    SimAdapter ex(cfg, clk);
    Ledger led(led_dir);
    Fsm fsm(cfg, clk);
    const std::string halt_path = "scalper/HALT";
    Tail alerts{data + "/whale_alerts.jsonl"};
    Tail desktop{std::string(getenv("HOME") ? getenv("HOME") : "") + "/ib-trader/data/trading-signals/" + today_str() + ".txt"};
    std::deque<Alert> alert_q;
    std::vector<Action> acts;

    // recovery: posicion viva en el ledger de hoy
    if (auto open = led.find_open_position()) {
        // caza de bugs 2026-07-28: un ledger corrupto (strike_c/exp ausentes en la linea FILL)
        // hacia que num() devolviera 0 en silencio -> recover_holding() arrancaba el FSM en
        // HOLDING gestionando un contrato invalido. OptContract::valid() ya existia pero nadie
        // la llamaba aqui. Sin contrato valido no hay nada seguro que gestionar: grita y sale
        // sin recovery (mejor una posicion sin gestionar automatica que una gestionada a ciegas).
        if (!open->con.valid()) {
            std::fprintf(stderr, "RECOVERY ABORTADO: contrato invalido en el ledger "
                         "(strike_c=%lld right=%c) — revisar %s a mano, NO se gestiona a ciegas\n",
                         (long long)open->con.strike_c, open->con.right ? open->con.right : '?',
                         led.path().c_str());
        } else {
        if (feed_clock) fclk.refresh();
        // edad REAL desde el tw del FILL (el ledger escribe CLOCK_REALTIME en us);
        // 0 (dato raro) = gestionar la ventana entera, que es lo conservador-activo
        struct timespec rts{}; clock_gettime(CLOCK_REALTIME, &rts);
        int64_t now_us = rts.tv_sec * 1000000LL + rts.tv_nsec / 1000;
        int64_t age_ms = age_ms_from_us(now_us, open->tw_us);
        fsm.recover_holding(open->con, open->fill_c, age_ms, acts);
        run_actions(acts, fsm, ex, led, clk, halt_path, live_banners);
        std::fprintf(stderr, "RECOVERY: posicion %lld%c del ledger, edad %llds — gestion inmediata\n",
                     (long long)open->con.strike_c, open->con.right, (long long)(age_ms / 1000));
        }
    }
    // recovery de contadores del dia: kill -9 tras un cierre no borra la ley
    // (trades/dia, one-loss halt, cooldown). Sin esto un restart re-opera un dia rojo.
    if (auto ds = led.day_state(); ds.closes > 0 || ds.red) {
        struct timespec rts{}; clock_gettime(CLOCK_REALTIME, &rts);
        int64_t now_us = rts.tv_sec * 1000000LL + rts.tv_nsec / 1000;
        fsm.recover_day(ds.closes, ds.red, age_ms_from_us(now_us, ds.last_close_us), acts);
        run_actions(acts, fsm, ex, led, clk, halt_path, live_banners);
        std::fprintf(stderr, "RECOVERY DIA: %d cierres, rojo=%d\n", ds.closes, (int)ds.red);
        if (fsm.state() == St::HALTED) { std::fprintf(stderr, "HALTED del ledger — fin.\n"); return 0; }
    }

    Inputs in{};
    Chain chain{}; bool have_chain = false;
    int64_t chain_mtime = 0;
    std::fprintf(stderr, "whale_scalper SIM | data=%s | ledger=%s | banners=%d\n",
                 data.c_str(), led_dir.c_str(), live_banners);

    while (true) {
        if (feed_clock) {
            fclk.refresh();
            if (fclk.ep <= 0) { usleep(100000); continue; }
        }
        in.today_yyyymmdd = today_yyyymmdd((time_t)clk.wall_s());
        // NBBO subyacente (archivo sobrescrito: 1 linea)
        std::string nb = slurp(data + "/nbbo_qqq.txt");
        if (auto n = parse_nbbo(nb)) { in.und = *n; ex.set_underlying(*n); }
        // cadena (reparse solo si cambio)
        std::string cp = data + "/opt_chain_qqq.txt";
        int64_t mt = fmtime(cp);
        if (mt && mt != chain_mtime) {
            chain_mtime = mt;
            if (auto ch = parse_chain(slurp(cp))) {
                chain = *ch; have_chain = true;
                // sembrar el mundo sim con el ATM real
                double best = 1e18; double iv = 0.20; int spr = 4;
                for (auto& r : chain.rows) {
                    double d = std::llabs(r.strike_c - chain.spot_c);
                    if (d < best && r.iv > 0) { best = d; iv = r.iv; if (r.bid_c > 0) spr = r.ask_c - r.bid_c; }
                }
                ex.set_iv(iv); ex.set_opt_spread_c(spr);
            }
        }
        // segundos a las 16:00 ET para theta del sim
        int hh = clk.et_hhmm();
        int64_t stc = (int64_t)(16 * 3600) - ((hh / 100) * 3600 + (hh % 100) * 60);
        ex.set_secs_to_close(std::max<int64_t>(stc, 0));
        // alertas: JSONL primero, fallback Desktop txt. TODAS a la cola —
        // una por tick (antes, 2 alertas en el mismo tick = la segunda se perdia,
        // p.ej. NOK no-impact seguido de QQQ operable).
        for (auto& a : parse_alert_lines(alerts.read_new())) alert_q.push_back(a);
        if (alert_q.empty()) {
            for (auto& l : desktop.read_new())
                if (auto a = parse_alert_txt(l, 0)) { a->ts = clk.wall_s(); alert_q.push_back(*a); }
        }
        in.alert.reset();
        if (!alert_q.empty()) { in.alert = alert_q.front(); alert_q.pop_front(); }
        in.halt_file = exists(halt_path);
        in.chain = have_chain ? &chain : nullptr;
        if (fsm.held().valid()) in.opt = ex.quote(fsm.held());
        else in.opt = {};

        ex.tick();
        ExecReport r;
        in.ev = Inputs::NONE;
        if (ex.poll(r)) {
            in.ev = r.kind == ExecReport::FILL ? Inputs::FILL :
                    r.kind == ExecReport::REJECTED ? Inputs::REJECTED :
                    r.kind == ExecReport::CANCELED ? Inputs::CANCELED : Inputs::ACK;
            in.ev_order_id = r.order_id; in.ev_px_c = r.px_c;
        }
        fsm.step(in, acts);
        run_actions(acts, fsm, ex, led, clk, halt_path, live_banners);
        if (fsm.state() == St::HALTED) { std::fprintf(stderr, "HALTED — fin. Revisar post-mortem.\n"); return 0; }
        usleep(100000);   // 100ms
    }
}

int main(int argc, char** argv) {
    std::string data = "data", led_dir = "scalper/ledger", conf = "scalper/scalper.conf", replay;
    bool sim = false, arm_live = false, banners = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&]() -> std::string { return i + 1 < argc ? argv[++i] : ""; };
        if      (a == "--data") data = next();
        else if (a == "--ledger") led_dir = next();
        else if (a == "--conf") conf = next();
        else if (a == "--replay") replay = next();
        else if (a == "--sim") sim = true;
        else if (a == "--banners") banners = true;      // banners macOS en shadow-sim
        else if (a == "--arm-live") arm_live = true;
        else { std::fprintf(stderr, "uso: whale_scalper [--sim|--replay F] [--data DIR] [--conf F] [--banners]\n"); return 2; }
    }
    Cfg cfg;
    if (std::ifstream cf(conf); cf) {
        std::string l;
        while (std::getline(cf, l)) {
            if (l.empty() || l[0] == '#') continue;
            size_t eq = l.find('=');
            if (eq != std::string::npos) cfg_set(cfg, l.substr(0, eq), l.substr(eq + 1));
        }
    }
    if (arm_live) {
        // doble llave Fase 4: hoy NO existe camino live — negarse siempre.
        std::fprintf(stderr, "ARM-LIVE: Fase 4 no implementada. SIM solamente. Abortando.\n");
        return 3;
    }
    if (!replay.empty()) return run_replay(replay, cfg, led_dir);
    if (sim) return run_sim(data, cfg, led_dir, banners);
    std::fprintf(stderr, "nada que hacer: usar --sim o --replay\n");
    return 2;
}
