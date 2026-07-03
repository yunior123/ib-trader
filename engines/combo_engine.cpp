// ============================================================================
// engines/combo_engine.cpp — MOTOR 3 (B8): combo BOLLINGER + FLUJO, aislado.
//
// SEÑAL-SOLAMENTE: jamas toca broker, jamas ejecuta ordenes, sin voz.
//
// Modos:
//   --backtest <5m.csv> --sym SYM --flow <jsonl> [--csv1m <1m.csv>] [--out f.csv]
//       Replay: barras + flujo fusionados por tiempo (cero look-ahead: solo
//       registros de flujo con ts <= cierre de la barra que decide). Señales
//       en el formato compartido (docs/ENGINE-SCORING-SPEC.md).
//       HONESTIDAD: data/whale_flow_hist.jsonl existe SOLO desde 2026-07-21.
//       En dias sin flujo el combo NO emite — eso ES el diseño (sin contexto
//       no hay señal); el resumen separa candidatos con/sin cobertura.
//   --live SYM [--once] [--data-dir data] [--out data/engine_signals_combo.jsonl]
//       Tail de data/bars_<sym>_ibkr.txt (1m) + data/whale_flow_hist.jsonl
//       (todos los simbolos: capitanes incluidos). Señales frescas -> JSONL,
//       SIN voz. --once = una pasada y salir (tests; sin daemon).
//
// clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o combo_engine combo_engine.cpp
// ============================================================================
#include "combo_core.h"

#include <cctype>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <unistd.h>

using namespace combocore;
using bbcore::Bar;
using bbcore::Config;
using bbcore::Signal;

// HHMM hora del Este (TZ=America/New_York en main; DST correcto).
static int hm_et(double epoch) {
    time_t t = (time_t)epoch;
    struct tm tmv{};
    localtime_r(&t, &tmv);
    return tmv.tm_hour * 100 + tmv.tm_min;
}

static std::string lower(std::string s) {
    for (auto& ch : s) ch = (char)std::tolower((unsigned char)ch);
    return s;
}

static std::vector<Bar> load_bars(const std::string& path, size_t* bad = nullptr) {
    std::vector<Bar> bars;
    std::ifstream f(path);
    if (!f) return bars;
    std::string line;
    size_t nbad = 0;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        Bar b;
        if (bbcore::parse_bar_line(line.c_str(), b)) bars.push_back(b);
        else ++nbad;
    }
    // Orden estable + DEDUP por timestamp: barras con t <= t previo se DESCARTAN
    // (misma semantica que live `b.t <= last_seen`). Sin esto, una barra 5m/1m
    // repetida en el feed (IBKR/yfinance reappends) se procesaria DOS veces y
    // envenenaria la BB rodante ~20 barras -> señal distinta (ref/tgt/stop) y
    // backtest que MIENTE. Se conserva la PRIMERA ocurrencia (orden de archivo).
    std::stable_sort(bars.begin(), bars.end(),
                     [](const Bar& a, const Bar& b) { return a.t < b.t; });
    size_t w = 0, ndup = 0;
    for (size_t r = 0; r < bars.size(); ++r) {
        if (w == 0 || bars[r].t > bars[w - 1].t) bars[w++] = bars[r];
        else ++ndup;  // t <= t previo: dup/desordenada -> descartada
    }
    bars.resize(w);
    if (bad) *bad = nbad + ndup;  // malformadas + dups descartadas
    return bars;
}

// jsonl completo -> registros ordenados por ts. Malformadas se cuentan, jamas crashean.
static std::vector<FlowRec> load_flow(const std::string& path, size_t* bad = nullptr) {
    std::vector<FlowRec> recs;
    std::ifstream f(path);
    if (!f) return recs;
    std::string line;
    size_t nbad = 0;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        FlowRec r;
        if (parse_flow_line(line.c_str(), r)) recs.push_back(std::move(r));
        else ++nbad;
    }
    std::stable_sort(recs.begin(), recs.end(),
                     [](const FlowRec& a, const FlowRec& b) { return a.ts < b.ts; });
    if (bad) *bad = nbad;
    return recs;
}

static std::string fmt_et(double epoch) {
    if (epoch <= 0) return "s/d";
    time_t t = (time_t)epoch;
    struct tm tmv{};
    localtime_r(&t, &tmv);
    char buf[32];
    std::strftime(buf, sizeof buf, "%Y-%m-%d %H:%M ET", &tmv);
    return buf;
}

// ------------------------------ backtest ------------------------------------
static int run_backtest(const std::string& csv5m, const std::string& csv1m,
                        const std::string& flow_path, const std::string& sym,
                        const std::string& out_path) {
    const bool use1m = !csv1m.empty();
    const int base_tf = use1m ? 60 : 300;
    size_t bad_bars = 0, bad_flow = 0;
    const std::vector<Bar> bars = load_bars(use1m ? csv1m : csv5m, &bad_bars);
    if (bars.empty()) {
        std::fprintf(stderr, "[combo] sin barras en %s\n", (use1m ? csv1m : csv5m).c_str());
        return 1;
    }
    const std::vector<FlowRec> flow = load_flow(flow_path, &bad_flow);
    std::fprintf(stderr,
                 "[combo] %s: %zu barras %s (%zu malformadas), flujo %zu registros "
                 "(%zu malformados) ventana %s .. %s\n",
                 sym.c_str(), bars.size(), use1m ? "1m" : "5m [SIN --csv1m: elastic en 5m — declarado]",
                 bad_bars, flow.size(), bad_flow,
                 fmt_et(flow.empty() ? 0 : flow.front().ts).c_str(),
                 fmt_et(flow.empty() ? 0 : flow.back().ts).c_str());
    std::fprintf(stderr,
                 "[combo] DECLARADO: whale_flow_hist.jsonl existe SOLO desde 2026-07-21 — "
                 "3 meses de flujo NO EXISTEN; en dias sin flujo el combo NO emite (diseño).\n");

    FlowBook fb;
    ComboEngine eng(sym, Config{}, base_tf, hm_et, fb);
    {
        std::string caps;
        for (const auto& c : eng.captains()) { caps += c; caps += ' '; }
        std::fprintf(stderr, "[combo] %s capitanes: %s(memoria=%s)\n", sym.c_str(),
                     caps.c_str(), memory_troop().count(sym) ? "si" : "no");
    }
    FILE* out = out_path.empty() ? stdout : std::fopen(out_path.c_str(), "w");
    if (!out) { std::fprintf(stderr, "[combo] no puedo abrir %s\n", out_path.c_str()); return 1; }
    std::fprintf(out, "epoch,sym,side,kind,ref_px,target_px,stop_px\n");
    size_t j = 0, n = 0;
    for (const Bar& b : bars) {
        const double tdec = b.t + base_tf;               // cierre de la barra
        while (j < flow.size() && flow[j].ts <= tdec) {  // cero look-ahead
            fb.on_record(flow[j].ts, flow[j].sym, flow[j].vc, flow[j].vp);
            ++j;
        }
        for (const Signal& s : eng.on_bar(b)) {
            std::fprintf(out, "%.0f,%s,%s,%s,%.4f,%.4f,%.4f\n",
                         s.epoch, s.sym.c_str(), s.side.c_str(), s.kind.c_str(),
                         s.ref_px, s.target_px, s.stop_px);
            ++n;
        }
    }
    if (out != stdout) std::fclose(out);
    const ComboStats& st = eng.stats();
    std::fprintf(stderr,
                 "[combo] %s resumen: candidatos_elastic=%zu | sin_contexto(dias/horas sin flujo)=%zu | "
                 "veto_propio=%zu veto_capitan=%zu | EMITIDAS=%zu (combo_elastic=%zu combo_captain=%zu) | "
                 "artefactos_flujo=%zu%s%s\n",
                 sym.c_str(), st.cand, st.sin_contexto, st.veto_propio, st.veto_capitan,
                 n, st.emit_plain, st.emit_captain, fb.artifacts(),
                 out_path.empty() ? "" : " -> ", out_path.c_str());
    return 0;
}

// -------------------------------- live --------------------------------------
// SIN voz, SIN broker. --once = una pasada (tests); sin --once: loop con sleep
// (lanzar solo cuando Yunior mande — no somos daemon por defecto).
static int run_live(const std::string& sym, const std::string& data_dir,
                    const std::string& out_path, bool once, int interval_s) {
    const std::string bars_path = data_dir + "/bars_" + lower(sym) + "_ibkr.txt";
    const std::string flow_path = data_dir + "/whale_flow_hist.jsonl";
    FlowBook fb;
    ComboEngine eng(sym, Config{}, 60, hm_et, fb);
    double last_seen = 0;
    std::streamoff flow_off = 0;
    std::fprintf(stderr, "[combo] live %s <- %s + %s -> %s (%s)\n", sym.c_str(),
                 bars_path.c_str(), flow_path.c_str(), out_path.c_str(), once ? "once" : "loop");
    do {
        // flujo nuevo (todos los simbolos: el capitan tambien cuenta)
        {
            std::ifstream f(flow_path);
            if (f) {
                f.seekg(0, std::ios::end);
                const std::streamoff end = f.tellg();
                if (end < flow_off) flow_off = 0;         // archivo rotado: releer
                f.seekg(flow_off);
                std::string line;
                while (std::getline(f, line)) {
                    FlowRec r;
                    if (!line.empty() && parse_flow_line(line.c_str(), r))
                        fb.on_record(r.ts, r.sym, r.vc, r.vp);
                }
                flow_off = end;
            }
        }
        for (const Bar& b : load_bars(bars_path)) {
            if (b.t <= last_seen) continue;
            last_seen = b.t;
            for (const Signal& s : eng.on_bar(b)) {
                const double now = (double)time(nullptr);
                if (now - s.epoch > 600) continue;        // replay viejo: no se canta
                FILE* out = std::fopen(out_path.c_str(), "a");
                if (!out) { std::fprintf(stderr, "[combo] no puedo abrir %s\n", out_path.c_str()); continue; }
                std::fprintf(out,
                    "{\"epoch\":%.0f,\"sym\":\"%s\",\"side\":\"%s\",\"kind\":\"%s\","
                    "\"ref_px\":%.4f,\"target_px\":%.4f,\"stop_px\":%.4f,"
                    "\"pctb\":%.3f,\"ts_emit\":%.0f,\"engine\":\"combo\"}\n",
                    s.epoch, s.sym.c_str(), s.side.c_str(), s.kind.c_str(),
                    s.ref_px, s.target_px, s.stop_px, s.pctb, now);
                std::fclose(out);
                std::fprintf(stderr, "[combo] SEÑAL %s %s %s ref %.2f tgt %.2f stop %.2f\n",
                             s.sym.c_str(), s.side.c_str(), s.kind.c_str(),
                             s.ref_px, s.target_px, s.stop_px);
            }
        }
        if (!once) sleep((unsigned)interval_s);
    } while (!once);
    return 0;
}

// -------------------------------- main --------------------------------------
int main(int argc, char** argv) {
    setenv("TZ", "America/New_York", 1);  // ventanas horarias ET, DST-correcto
    tzset();
    std::string mode, csv5m, csv1m, flow_path, sym, out_path, data_dir = "data";
    bool once = false;
    int interval_s = 5;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        auto next = [&](const char* what) -> std::string {
            if (i + 1 >= argc) { std::fprintf(stderr, "falta valor para %s\n", what); std::exit(2); }
            return argv[++i];
        };
        if      (a == "--backtest") { mode = "backtest"; csv5m = next("--backtest"); }
        else if (a == "--live")     { mode = "live"; sym = next("--live"); }
        else if (a == "--flow")     flow_path = next("--flow");
        else if (a == "--csv1m")    csv1m = next("--csv1m");
        else if (a == "--sym")      sym = next("--sym");
        else if (a == "--out")      out_path = next("--out");
        else if (a == "--data-dir") data_dir = next("--data-dir");
        else if (a == "--once")     once = true;
        else if (a == "--interval-s") interval_s = std::atoi(next("--interval-s").c_str());
        else {
            std::fprintf(stderr,
                "uso: combo_engine --backtest <5m.csv> --sym SYM --flow <jsonl> [--csv1m <1m.csv>] [--out f.csv]\n"
                "     combo_engine --live SYM [--once] [--data-dir data] [--out data/engine_signals_combo.jsonl]\n");
            return 2;
        }
    }
    for (auto& ch : sym) ch = (char)std::toupper((unsigned char)ch);
    if (mode == "backtest") {
        if (sym.empty())       { std::fprintf(stderr, "--sym obligatorio en backtest\n"); return 2; }
        if (flow_path.empty()) { std::fprintf(stderr, "--flow obligatorio en backtest (sin flujo no hay combo)\n"); return 2; }
        return run_backtest(csv5m, csv1m, flow_path, sym, out_path);
    }
    if (mode == "live") {
        if (out_path.empty()) out_path = data_dir + "/engine_signals_combo.jsonl";
        return run_live(sym, data_dir, out_path, once, interval_s);
    }
    std::fprintf(stderr, "modo obligatorio: --backtest o --live\n");
    return 2;
}
