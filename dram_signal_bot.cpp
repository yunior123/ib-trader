// dram_signal_bot.cpp — DRAM buy/sell signal engine, pure C++
// ============================================================
// Mirrors the validated Python engine (confirmed capitulation entry +
// adaptive exit) computing all indicators incrementally in C++:
//   BB(20, 3.0) population-std | RSI(14) Wilder | volMA(20) | ATR(14) Wilder
//   BUY : capitulation bar (close<=BB_low && RSI<=25 && vol>=1.2*volMA) arms;
//         a green bar closing above the panic bar's high with rising RSI
//         within 60 bars confirms -> COMPRAR alert (dram_buy.wav)
//   SELL: on the virtual position — target +4% touched, trail 3xATR broken
//         above the +1% floor, or 15:45 ET flatten -> VENDER (dram_sell.wav)
//   Entries only 9:30-15:30 ET (RTH rule).
//
// Data: scripts/dram_bar_bridge.py streams REAL Yahoo 1m completed bars as
//       "EPOCH OPEN HIGH LOW CLOSE VOLUME" lines (stored locally by bridge).
//
// build: clang++ -std=c++17 -O2 -o dram_signal_bot dram_signal_bot.cpp
// run:   ./dram_signal_bot            (spawns bridge)
//        ./dram_signal_bot --stdin    (replay: feed bar lines for testing)

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <ctime>
#include <deque>
#include <unistd.h>

struct Bar { double t, o, h, l, c, v; };

// ---- config (mirror of DEFAULT_CONFIG) ----
static const int    BB_N = 20;      static const double BB_STD = 3.0;
static const int    RSI_N = 14;     static const double RSI_OS = 25.0;
static const int    VOL_N = 20;     static const double VOL_MULT = 1.2;
static const int    ATR_N = 14;
static const int    CONFIRM_WINDOW = 60;
static const double TARGET_PCT = 4.0, FLOOR_PCT = 1.0, TRAIL_ATR = 3.0;

static void play(const char* f, const char* fb) {
    char cmd[512];
    if (access(f, R_OK) == 0)
        std::snprintf(cmd, sizeof(cmd), "afplay '%s' >/dev/null 2>&1 &", f);
    else
        std::snprintf(cmd, sizeof(cmd),
                      "afplay /System/Library/Sounds/%s.aiff >/dev/null 2>&1 &", fb);
    std::system(cmd);
}

static void et_hm(double epoch, int& h, int& m) {  // Mac local tz == Toronto/ET
    time_t t = (time_t)epoch;
    struct tm lt; localtime_r(&t, &lt);
    h = lt.tm_hour; m = lt.tm_min;
}

int main(int argc, char** argv) {
    bool use_stdin = (argc > 1 && !std::strcmp(argv[1], "--stdin"));
    FILE* in = stdin;
    if (!use_stdin) {
        in = popen("venv/bin/python scripts/dram_bar_bridge.py 2>/dev/null", "r");
        if (!in) { std::fprintf(stderr, "no bridge\n"); return 1; }
        std::fprintf(stderr, "dram_signal_bot (C++): bridge DRAM 1m real iniciado\n");
    }

    std::deque<double> closes, vols;      // rolling 20
    double avg_gain = 0, avg_loss = 0, prev_close = 0, atr = 0;
    long   nbars = 0;

    // confirmed-entry state
    bool armed = false; double armed_high = 0, armed_rsi = 0; long armed_bar = 0;
    bool pending_buy = false;
    // virtual position
    bool in_pos = false; double entry = 0, peak = 0, floor_px = 0, target_px = 0;

    char line[512]; Bar b;
    while (std::fgets(line, sizeof(line), in)) {
        if (std::sscanf(line, "%lf %lf %lf %lf %lf %lf",
                        &b.t, &b.o, &b.h, &b.l, &b.c, &b.v) != 6) continue;
        nbars++;

        // ---- incremental indicators ----
        double gain = 0, loss = 0;
        if (prev_close > 0) {
            double d = b.c - prev_close;
            gain = d > 0 ? d : 0; loss = d < 0 ? -d : 0;
            double tr = b.h - b.l;
            double hc = std::fabs(b.h - prev_close), lc = std::fabs(b.l - prev_close);
            if (hc > tr) tr = hc; if (lc > tr) tr = lc;
            atr = (nbars <= ATR_N) ? (atr * (nbars - 1) + tr) / nbars
                                   : atr + (tr - atr) / ATR_N;
        }
        avg_gain = nbars <= RSI_N ? (avg_gain * (nbars - 1) + gain) / nbars
                                  : avg_gain + (gain - avg_gain) / RSI_N;
        avg_loss = nbars <= RSI_N ? (avg_loss * (nbars - 1) + loss) / nbars
                                  : avg_loss + (loss - avg_loss) / RSI_N;
        double rsi = avg_loss > 1e-12 ? 100.0 - 100.0 / (1.0 + avg_gain / avg_loss) : 50.0;
        prev_close = b.c;

        closes.push_back(b.c); if ((int)closes.size() > BB_N) closes.pop_front();
        vols.push_back(b.v);   if ((int)vols.size() > VOL_N)  vols.pop_front();
        double bb_low = 0, vol_ma = 0; bool ind_ok = false;
        if ((int)closes.size() == BB_N && nbars > RSI_N) {
            double mean = 0; for (double x : closes) mean += x; mean /= BB_N;
            double var = 0;  for (double x : closes) var += (x - mean) * (x - mean);
            bb_low = mean - BB_STD * std::sqrt(var / BB_N);
            for (double x : vols) vol_ma += x; vol_ma /= VOL_N;
            ind_ok = vol_ma > 0;
        }

        int H, M; et_hm(b.t, H, M);
        bool rth_entry = (H > 9 || (H == 9 && M >= 30)) && (H < 15 || (H == 15 && M < 30));

        // ---- SELL management on virtual position ----
        if (in_pos) {
            if (b.h > peak) peak = b.h;
            bool sold = false; const char* why = "";
            if (b.h >= target_px) { sold = true; why = "target +4%"; }
            else if (atr > 0 && b.c < peak - TRAIL_ATR * atr && b.c > floor_px) {
                sold = true; why = "trail 3xATR roto";
            } else if (H > 15 || (H == 15 && M >= 45)) {
                if (b.c >= floor_px) { sold = true; why = "EOD flatten 15:45"; }
            }
            if (sold) {
                std::printf("[%02d:%02d] *** DRAM: VENDER *** ~%.2f (%s, entrada %.2f)\n",
                            H, M, b.c, why, entry);
                std::fflush(stdout);
                play("sounds/dram_sell.wav", "Hero");
                in_pos = false;
            }
        }

        // ---- BUY: pending fill then arming (mirrors engine order) ----
        if (pending_buy && !in_pos) {
            pending_buy = false;
            if (rth_entry) {
                in_pos = true; entry = b.o; peak = b.h;
                floor_px = entry * (1 + FLOOR_PCT / 100.0);
                target_px = entry * (1 + TARGET_PCT / 100.0);
                std::printf("[%02d:%02d] *** DRAM: COMPRAR *** ~%.2f (capitulacion confirmada; "
                            "target %.2f, floor %.2f)\n", H, M, entry, target_px, floor_px);
                std::fflush(stdout);
                play("sounds/dram_buy.wav", "Glass");
            }
        }
        if (ind_ok && !in_pos && !pending_buy && rth_entry) {
            bool capit = b.c <= bb_low && rsi <= RSI_OS && b.v >= vol_ma * VOL_MULT;
            if (capit) { armed = true; armed_high = b.h; armed_rsi = rsi; armed_bar = nbars; }
            else if (armed && nbars - armed_bar <= CONFIRM_WINDOW
                     && b.c > armed_high && b.c > b.o && rsi > armed_rsi) {
                pending_buy = true; armed = false;
            }
            if (armed && nbars - armed_bar > CONFIRM_WINDOW) armed = false;
        }
    }
    if (!use_stdin) pclose(in);
    return 0;
}
