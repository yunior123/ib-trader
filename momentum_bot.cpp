// momentum_bot.cpp — C++ momentum detector for Yunior's favorite tickers
// ======================================================================
// Reads a live price stream from TWS (via scripts/tws_price_bridge.py, which
// speaks the IBKR API through ib_insync and prints "SYMBOL PRICE EPOCH" lines)
// and fires ASYNC sound alerts the moment any ticker shows real momentum.
//
//   build:  clang++ -std=c++17 -O2 -o momentum_bot momentum_bot.cpp
//   run:    ./momentum_bot                    (spawns the TWS bridge itself)
//           ./momentum_bot --stdin            (read stream from stdin: testing)
//           ./momentum_bot --threshold 1.5 --window 600
//
// Sounds (macOS, async — never blocks the detector):
//   Ping.aiff  = bullish momentum      Basso.aiff = bearish momentum
// Debounce: one alert per symbol per 15 minutes.

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <deque>
#include <map>
#include <string>

struct Tick { double t; double px; };

static double g_threshold = 1.0;   // % move that counts as momentum
static double g_window    = 600;   // seconds of lookback (10 min)
static double g_debounce  = 900;   // seconds between alerts per symbol

#include <unistd.h>
static void play_async(const char* custom, const char* fallback) {
    // downloaded sound if present, else macOS system sound; always async
    char cmd[512];
    if (access(custom, R_OK) == 0)
        std::snprintf(cmd, sizeof(cmd), "afplay '%s' >/dev/null 2>&1 &", custom);
    else
        std::snprintf(cmd, sizeof(cmd),
                      "afplay /System/Library/Sounds/%s.aiff >/dev/null 2>&1 &", fallback);
    std::system(cmd);
}

int main(int argc, char** argv) {
    bool use_stdin = false;
    const char* bridge_cmd =
        "venv/bin/python scripts/tws_price_bridge.py 2>/dev/null";

    for (int i = 1; i < argc; i++) {
        if (!std::strcmp(argv[i], "--stdin")) use_stdin = true;
        else if (!std::strcmp(argv[i], "--threshold") && i + 1 < argc)
            g_threshold = std::atof(argv[++i]);
        else if (!std::strcmp(argv[i], "--window") && i + 1 < argc)
            g_window = std::atof(argv[++i]);
    }

    FILE* in = stdin;
    if (!use_stdin) {
        in = popen(bridge_cmd, "r");
        if (!in) { std::fprintf(stderr, "cannot start TWS bridge\n"); return 1; }
        std::fprintf(stderr, "momentum_bot: TWS bridge started (threshold %.2f%%, window %.0fs)\n",
                     g_threshold, g_window);
    }

    std::map<std::string, std::deque<Tick>> hist;
    std::map<std::string, double> last_alert;

    char line[256];
    while (std::fgets(line, sizeof(line), in)) {
        char sym[32]; double px, ts;
        if (std::sscanf(line, "%31s %lf %lf", sym, &px, &ts) != 3) continue;
        if (px <= 0) continue;
        auto& dq = hist[sym];
        dq.push_back({ts, px});
        while (!dq.empty() && dq.front().t < ts - g_window) dq.pop_front();
        if (dq.size() < 3) continue;

        double move = (px / dq.front().px - 1.0) * 100.0;
        if (move >= g_threshold || move <= -g_threshold) {
            double& la = last_alert[sym];
            if (ts - la < g_debounce) continue;
            la = ts;
            const char* dir = move > 0 ? "ALCISTA" : "BAJISTA";
            std::printf("[MOMENTUM %s] %s %+.2f%% en %.0f min (px %.2f)\n",
                        dir, sym, move, g_window / 60.0, px);
            std::fflush(stdout);
            if (move > 0) play_async("sounds/momentum_up.wav", "Ping");
            else play_async("sounds/momentum_down.wav", "Basso");
        }
    }
    if (!use_stdin) pclose(in);
    return 0;
}
