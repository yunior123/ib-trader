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
#include <cctype>
#include <ctime>
#include <deque>
#include <map>
#include <string>

struct Tick { double t; double px; };

static double g_threshold = 1.0;   // % move that counts as momentum
static double g_window    = 600;   // seconds of lookback (10 min)
static double g_debounce  = 900;   // seconds between alerts per symbol

#include <unistd.h>
#include <csignal>
static void play_async(const char* custom, const char* fallback) {
    // downloaded sound if present, else macOS system sound; always async.
    // Tope de 3 afplay concurrentes en todo el Mac (fix sobrecarga coreaudiod).
    char cmd[512];
    if (access(custom, R_OK) == 0)
        std::snprintf(cmd, sizeof(cmd),
                      "[ $(pgrep -x afplay | wc -l) -lt 3 ] && afplay '%s' >/dev/null 2>&1 &", custom);
    else
        std::snprintf(cmd, sizeof(cmd),
                      "[ $(pgrep -x afplay | wc -l) -lt 3 ] && "
                      "afplay /System/Library/Sounds/%s.aiff >/dev/null 2>&1 &", fallback);
    std::system(cmd);
}

// ---- cierre seguro: SIGTERM/SIGINT tumban tambien al bridge (mismo grupo) ----
static void on_term(int) {
    std::signal(SIGTERM, SIG_IGN);   // inmune a nuestro propio kill de grupo
    kill(0, SIGTERM);                // bridge (sh + python) cae con nosotros
    _exit(0);
}

// shell-safety whitelist (same as the signal bots): sym/msg come from an external
// stream, so anything going into system() is filtered to alnum + " .,%+-:/()_".
static void sh_sanitize(const char* in, char* out, size_t n) {
    size_t j = 0;
    for (size_t i = 0; in && in[i] && j + 1 < n; ++i) {
        unsigned char c = (unsigned char)in[i];
        out[j++] = (std::isalnum(c) || std::strchr(" .,%+-:/()_", c)) ? (char)c : ' ';
    }
    out[j] = 0;
}

// fleet-standard notify: Mac (osascript) + local operations log (solo Mac desde 2026-07-09)
static void notify(const char* title, const char* msg, bool urgent) {
    char st[128], sm[512], cmd[1024];
    sh_sanitize(title, st, sizeof(st));
    sh_sanitize(msg, sm, sizeof(sm));
    std::snprintf(cmd, sizeof(cmd),
        "osascript -e 'display notification \"%s\" with title \"%s\" sound name \"Glass\"' "
        ">/dev/null 2>&1 &", sm, st);
    std::system(cmd);
    // phone push (ntfy) removido 2026-07-09: solo Mac, por orden de Yunior
    (void)urgent;
    FILE* f = std::fopen("momentum_operations.log", "a");
    if (f) {
        time_t now = time(nullptr); struct tm lt; localtime_r(&now, &lt);
        std::fprintf(f, "%04d-%02d-%02d %02d:%02d:%02d | %s | %s\n",
                     lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday,
                     lt.tm_hour, lt.tm_min, lt.tm_sec, st, sm);
        std::fclose(f);
    }
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

    setpgid(0, 0);                    // grupo propio: el kill(0) no toca al keepalive
    std::signal(SIGINT, on_term);  std::signal(SIGTERM, on_term);
    std::signal(SIGHUP, on_term);  std::signal(SIGPIPE, SIG_IGN);

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
            // Mac + phone notification + local log (fleet standard)
            char title[64], msg[160];
            std::snprintf(title, sizeof(title), "MOMENTUM %s %s", sym, dir);
            std::snprintf(msg, sizeof(msg), "%s %+.2f%% en %.0f min (px %.2f)",
                          sym, move, g_window / 60.0, px);
            notify(title, msg, false);
        }
    }
    if (!use_stdin) pclose(in);
    return 0;
}
