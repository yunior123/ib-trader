// ============================================================================
// engines/bb_engine.cpp — MOTOR 2 (B7): bb_engine, SOLO BOLLINGER, aislado.
//
// SEÑAL-SOLAMENTE: jamas toca broker, jamas ejecuta ordenes, sin voz.
//
// Modos:
//   --backtest <5m.csv> --sym SYM [--csv1m <1m.csv>] [--out señales.csv]
//       Emite señales en el formato compartido (docs/ENGINE-SCORING-SPEC.md):
//       epoch,sym,side,kind,ref_px,target_px,stop_px
//       Con --csv1m el stream base es el 1m (elastic 1m + 5m/15m agregados);
//       sin el, el stream base es el 5m (elastic 5m, degradacion declarada).
//   --live SYM [--once] [--data-dir data] [--out data/engine_signals_bb.jsonl]
//       Tail de data/bars_<sym>_ibkr.txt (1m, espacio-separado); señales
//       frescas -> JSONL. --once = una pasada y salir (para tests; sin
//       daemon). Sin --once: loop con sleep (lanzar solo cuando Yunior mande).
//
// Config por ticker (degradacion limpia si faltan los .json):
//   data/bollinger_probs.json  -> elastic/bandwalk enabled (disabled = no emite)
//   data/bollinger_plus.json   -> veto_filters implementables con SOLO Bollinger:
//       F5_squeeze, F6_0945/1030/1130/1400 (ventanas ET), F7_15m_in.
//       F1/F2/F3/F4/F8 (RVOL/RSI/depth/zVWAP/ADX) se IGNORAN (se avisa por
//       stderr) — necesitan datos fuera del nucleo BB. Fallback total: elastic
//       basico con todos los defaults.
//
// clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o bb_engine bb_engine.cpp
// ============================================================================
#include "bb_core.h"

#include <cctype>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <sstream>
#include <unistd.h>

using namespace bbcore;

// ------------------------------ util ---------------------------------------
static std::string slurp(const std::string& path) {
    std::ifstream f(path);
    if (!f) return "";
    std::ostringstream ss; ss << f.rdbuf();
    return ss.str();
}

static std::string lower(std::string s) {
    for (auto& ch : s) ch = (char)std::tolower((unsigned char)ch);
    return s;
}

// HHMM en hora del Este (TZ=America/New_York fijada en main; DST correcto).
static int hm_et(double epoch) {
    time_t t = (time_t)epoch;
    struct tm tmv{};
    localtime_r(&t, &tmv);
    return tmv.tm_hour * 100 + tmv.tm_min;
}

// ---------------------- mini-extraccion de JSON -----------------------------
// Suficiente para bollinger_probs/plus.json (llaves sin '{' en strings).
static std::string json_obj(const std::string& js, const std::string& key, size_t from = 0) {
    const std::string pat = "\"" + key + "\"";
    const size_t p = js.find(pat, from);
    if (p == std::string::npos) return "";
    const size_t brace = js.find_first_of("{[", p + pat.size());
    if (brace == std::string::npos) return "";
    const char open = js[brace], close = open == '{' ? '}' : ']';
    int depth = 0;
    for (size_t i = brace; i < js.size(); ++i) {
        if (js[i] == open) ++depth;
        else if (js[i] == close && --depth == 0) return js.substr(brace, i - brace + 1);
    }
    return "";
}

static bool json_bool(const std::string& obj, const char* key, bool dflt) {
    const size_t p = obj.find(std::string("\"") + key + "\"");
    if (p == std::string::npos) return dflt;
    const size_t c = obj.find(':', p);
    if (c == std::string::npos) return dflt;
    const size_t q = obj.find_first_not_of(" \t\n\r", c + 1);
    if (q == std::string::npos) return dflt;
    return obj[q] == 't';
}

// -------------------------- config por ticker -------------------------------
static Config load_config(const std::string& data_dir, const std::string& sym, bool quiet) {
    Config cfg;  // defaults = elastic basico
    const std::string probs = slurp(data_dir + "/bollinger_probs.json");
    if (!probs.empty()) {
        const std::string tk = json_obj(probs, sym);
        if (!tk.empty()) {
            cfg.elastic_enabled  = json_bool(json_obj(tk, "elastic"), "enabled", true);
            cfg.bandwalk_enabled = json_bool(json_obj(tk, "bandwalk"), "enabled", false);
        }
    } else if (!quiet) {
        std::fprintf(stderr, "[bb_engine] %s: sin bollinger_probs.json -> elastic basico\n", sym.c_str());
    }
    const std::string plus = slurp(data_dir + "/bollinger_plus.json");
    if (!plus.empty()) {
        const std::string tk = json_obj(plus, sym);
        const std::string vetos = tk.empty() ? "" : json_obj(tk, "veto_filters");
        size_t p = 0;
        while ((p = vetos.find("\"filtro\"", p)) != std::string::npos) {
            const size_t a = vetos.find('"', vetos.find(':', p) + 1);
            const size_t b = a == std::string::npos ? a : vetos.find('"', a + 1);
            if (b == std::string::npos) break;
            const std::string f = vetos.substr(a + 1, b - a - 1);
            if      (f == "F5_squeeze") cfg.veto_f5_squeeze = true;
            else if (f == "F7_15m_in")  cfg.veto_f7_15m_in = true;
            else if (f == "F6_0945")    cfg.veto_win[0] = true;
            else if (f == "F6_1030")    cfg.veto_win[1] = true;
            else if (f == "F6_1130")    cfg.veto_win[2] = true;
            else if (f == "F6_1400")    cfg.veto_win[3] = true;
            else if (!quiet)
                std::fprintf(stderr, "[bb_engine] %s: veto %s NO implementable solo-BB -> ignorado (degradacion limpia)\n",
                             sym.c_str(), f.c_str());
            p = b;
        }
    }
    if (!quiet)
        std::fprintf(stderr,
                     "[bb_engine] %s config: elastic=%d bandwalk=%d squeeze=%d vetoF5=%d vetoF7=%d win=%d%d%d%d\n",
                     sym.c_str(), cfg.elastic_enabled, cfg.bandwalk_enabled, cfg.squeeze_enabled,
                     cfg.veto_f5_squeeze, cfg.veto_f7_15m_in,
                     cfg.veto_win[0], cfg.veto_win[1], cfg.veto_win[2], cfg.veto_win[3]);
    return cfg;
}

// ------------------------------ carga de barras -----------------------------
static std::vector<Bar> load_bars(const std::string& path, size_t* bad = nullptr) {
    std::vector<Bar> bars;
    std::ifstream f(path);
    if (!f) return bars;
    std::string line;
    size_t nbad = 0;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        Bar b;
        if (parse_bar_line(line.c_str(), b)) bars.push_back(b);
        else ++nbad;  // header u otra basura: se salta, jamas crashea
    }
    std::sort(bars.begin(), bars.end(), [](const Bar& a, const Bar& b) { return a.t < b.t; });
    if (bad) *bad = nbad;
    return bars;
}

// ------------------------------ backtest ------------------------------------
static int run_backtest(const std::string& csv5m, const std::string& csv1m,
                        const std::string& sym, const std::string& out_path,
                        const std::string& data_dir) {
    const bool use1m = !csv1m.empty();
    const std::string src = use1m ? csv1m : csv5m;
    size_t bad = 0;
    const std::vector<Bar> bars = load_bars(src, &bad);
    if (bars.empty()) {
        std::fprintf(stderr, "[bb_engine] sin barras en %s\n", src.c_str());
        return 1;
    }
    std::fprintf(stderr, "[bb_engine] %s backtest: %zu barras %s (%zu lineas malformadas saltadas)%s\n",
                 sym.c_str(), bars.size(), use1m ? "1m" : "5m", bad,
                 use1m ? " [elastic en 1m]" : " [SIN --csv1m: elastic corre en 5m — declarado]");
    Engine eng(sym, load_config(data_dir, sym, false), use1m ? 60 : 300, hm_et);
    FILE* out = out_path.empty() ? stdout : std::fopen(out_path.c_str(), "w");
    if (!out) { std::fprintf(stderr, "[bb_engine] no puedo abrir %s\n", out_path.c_str()); return 1; }
    std::fprintf(out, "epoch,sym,side,kind,ref_px,target_px,stop_px\n");
    size_t n = 0;
    for (const Bar& b : bars)
        for (const Signal& s : eng.on_bar(b)) {
            std::fprintf(out, "%.0f,%s,%s,%s,%.4f,%.4f,%.4f\n",
                         s.epoch, s.sym.c_str(), s.side.c_str(), s.kind.c_str(),
                         s.ref_px, s.target_px, s.stop_px);
            ++n;
        }
    if (out != stdout) std::fclose(out);
    std::fprintf(stderr, "[bb_engine] %s: %zu señales%s%s\n", sym.c_str(), n,
                 out_path.empty() ? "" : " -> ", out_path.c_str());
    return 0;
}

// -------------------------------- live --------------------------------------
// Lee data/bars_<sym>_ibkr.txt (1m "epoch o h l c v"), procesa lo nuevo y
// escribe señales FRESCAS (barra <= 10 min de antiguedad) a JSONL.
// SIN voz, SIN broker. --once = una pasada (test); si no, loop con sleep.
static int run_live(const std::string& sym, const std::string& data_dir,
                    const std::string& out_path, bool once, int interval_s) {
    const std::string bars_path = data_dir + "/bars_" + lower(sym) + "_ibkr.txt";
    Engine eng(sym, load_config(data_dir, sym, false), 60, hm_et);
    double last_seen = 0;
    std::fprintf(stderr, "[bb_engine] live %s <- %s -> %s (%s)\n", sym.c_str(),
                 bars_path.c_str(), out_path.c_str(), once ? "once" : "loop");
    do {
        const std::vector<Bar> bars = load_bars(bars_path);
        for (const Bar& b : bars) {
            if (b.t <= last_seen) continue;
            last_seen = b.t;
            for (const Signal& s : eng.on_bar(b)) {
                const double now = (double)time(nullptr);
                if (now - s.epoch > 600) continue;  // replay viejo: no se canta
                FILE* out = std::fopen(out_path.c_str(), "a");
                if (!out) { std::fprintf(stderr, "[bb_engine] no puedo abrir %s\n", out_path.c_str()); continue; }
                std::fprintf(out,
                    "{\"epoch\":%.0f,\"sym\":\"%s\",\"side\":\"%s\",\"kind\":\"%s\","
                    "\"ref_px\":%.4f,\"target_px\":%.4f,\"stop_px\":%.4f,"
                    "\"pctb\":%.3f,\"ts_emit\":%.0f,\"engine\":\"bb\"}\n",
                    s.epoch, s.sym.c_str(), s.side.c_str(), s.kind.c_str(),
                    s.ref_px, s.target_px, s.stop_px, s.pctb, now);
                std::fclose(out);
                std::fprintf(stderr, "[bb_engine] SEÑAL %s %s %s ref %.2f tgt %.2f stop %.2f\n",
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
    setenv("TZ", "America/New_York", 1);  // ventanas horarias en ET, DST-correcto
    tzset();
    std::string mode, csv5m, csv1m, sym, out_path, data_dir = "data";
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
        else if (a == "--csv1m")    csv1m = next("--csv1m");
        else if (a == "--sym")      sym = next("--sym");
        else if (a == "--out")      out_path = next("--out");
        else if (a == "--data-dir") data_dir = next("--data-dir");
        else if (a == "--once")     once = true;
        else if (a == "--interval-s") interval_s = std::atoi(next("--interval-s").c_str());
        else {
            std::fprintf(stderr,
                "uso: bb_engine --backtest <5m.csv> --sym SYM [--csv1m <1m.csv>] [--out f.csv] [--data-dir data]\n"
                "     bb_engine --live SYM [--once] [--data-dir data] [--out data/engine_signals_bb.jsonl]\n");
            return 2;
        }
    }
    for (auto& ch : sym) ch = (char)std::toupper((unsigned char)ch);
    if (mode == "backtest") {
        if (sym.empty()) { std::fprintf(stderr, "--sym obligatorio en backtest\n"); return 2; }
        return run_backtest(csv5m, csv1m, sym, out_path, data_dir);
    }
    if (mode == "live") {
        if (out_path.empty()) out_path = data_dir + "/engine_signals_bb.jsonl";
        return run_live(sym, data_dir, out_path, once, interval_s);
    }
    std::fprintf(stderr, "modo obligatorio: --backtest o --live\n");
    return 2;
}
