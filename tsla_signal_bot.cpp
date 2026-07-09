// tsla_signal_bot.cpp — TSLA buy/sell signal engine, pure C++
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
// Data: scripts/ws_bar_bridge.py finnhub TSLA tsla streams REAL Yahoo 1m completed bars as
//       "EPOCH OPEN HIGH LOW CLOSE VOLUME" lines (stored locally by bridge).
//
// build: clang++ -std=c++17 -O2 -o tsla_signal_bot tsla_signal_bot.cpp
// run:   ./tsla_signal_bot            (spawns bridge)
//        ./tsla_signal_bot --stdin    (replay: feed bar lines for testing)

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

static void speak(const char* phrase) {
    // System TTS (macOS `say`), async. Voice: $DRAM_VOICE override, else Daniel
    // (most natural installed). For an even more human voice: System Settings >
    // Accessibility > Spoken Content > Manage Voices > download "Ava (Premium)"
    // or "Zoe (Premium)", then export DRAM_VOICE="Ava (Premium)".
    const char* v = std::getenv("DRAM_VOICE");
    if (!v || !*v) v = "Daniel";
    char cmd[400];
    // una sola voz a la vez: corta cualquier locucion previa antes de hablar
    std::snprintf(cmd, sizeof(cmd),
                  "killall say >/dev/null 2>&1; say -v '%s' -r 170 '%s' >/dev/null 2>&1 &",
                  v, phrase);
    std::system(cmd);
}

static void play(const char* f, const char* fb) {
    char cmd[512];
    if (access(f, R_OK) == 0)
        std::snprintf(cmd, sizeof(cmd), "afplay '%s' >/dev/null 2>&1 &", f);
    else
        std::snprintf(cmd, sizeof(cmd),
                      "afplay /System/Library/Sounds/%s.aiff >/dev/null 2>&1 &", fb);
    std::system(cmd);
}

// ---- notifications: Mac (osascript) + phone (ntfy, same topic as scriptures) + ops log
static void notify(const char* title, const char* msg, bool urgent) {
    char cmd[1024];
    // 1) macOS notification center
    std::snprintf(cmd, sizeof(cmd),
        "osascript -e 'display notification \"%s\" with title \"%s\" sound name \"Glass\"' "
        ">/dev/null 2>&1 &", msg, title);
    std::system(cmd);
    // 2) phone via ntfy (church-scriptures pattern, topic yunior-daily-brief-2026)
    std::snprintf(cmd, sizeof(cmd),
        "curl -s -m 10 -X POST 'https://ntfy.sh/yunior-daily-brief-2026' "
        "-H 'Title: %s' -H 'Priority: %s' -H 'Tags: %s' -d '%s' >/dev/null 2>&1 &",
        title, urgent ? "urgent" : "default", urgent ? "rotating_light,chart" : "chart", msg);
    std::system(cmd);
    // 3) structured operations log
    FILE* f = std::fopen("tsla_operations.log", "a");
    if (f) {
        time_t now = time(nullptr); struct tm lt; localtime_r(&now, &lt);
        std::fprintf(f, "%04d-%02d-%02d %02d:%02d:%02d | %s | %s\n",
                     lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday,
                     lt.tm_hour, lt.tm_min, lt.tm_sec, title, msg);
        std::fclose(f);
    }
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
        in = popen("venv/bin/python scripts/ws_bar_bridge.py finnhub TSLA tsla 2>/dev/null", "r");
        if (!in) { std::fprintf(stderr, "no bridge\n"); return 1; }
        std::fprintf(stderr, "tsla_signal_bot (C++): bridge TSLA 1m real iniciado\n");
    }

    std::deque<double> closes, vols;      // rolling 20
    double avg_gain = 0, avg_loss = 0, prev_close = 0, atr = 0;
    long   nbars = 0;

    // confirmed-entry state
    bool armed = false; double armed_high = 0, armed_rsi = 0; long armed_bar = 0;
    bool pending_buy = false;
    // --- detection layers (alerting, not trading) ---
    // CUSUM (Lopez de Prado structural breaks): all abrupt falls/rises
    double cusum_up = 0, cusum_dn = 0, ret_var = 1e-6;
    // Supertrend(10,3): tendency change
    double st_upper = 0, st_lower = 0; int st_trend = 0;  // 1 up, -1 down
    // Donchian(20): breakout of prior range
    std::deque<double> dh20, dl20;
    // debounce per alert type
    double last_cusum = 0, last_st = 0, last_don = 0;
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
        bool alert_hours = (H >= 4) && (H < 20);   // pre/post incluidos para ALERTAS

        // ===== DETECTION LAYERS =====
        // 1) CUSUM filter (Lopez de Prado): statistical break -> falls/rises of ANY kind
        if (nbars > 1 && prev_close > 0) { /* prev_close ya actualizado: usar retorno del bar */ }
        {
            static double last_c_for_ret = 0;
            if (last_c_for_ret > 0) {
                double r = std::log(b.c / last_c_for_ret);
                ret_var += (r * r - ret_var) / 50.0;           // EWMA variance
                double hthr = std::max(8.0 * std::sqrt(ret_var), 0.020);  // 8-sigma y minimo 2%
                cusum_up = std::max(0.0, cusum_up + r);
                cusum_dn = std::min(0.0, cusum_dn + r);
                if (alert_hours && b.t - last_cusum > 3600) {
                    if (cusum_up > hthr) {
                        std::printf("[%02d:%02d] CUSUM: TSLA SUBIENDO fuerte (+%.2f%% acumulado) px %.2f\n",
                                    H, M, cusum_up * 100, b.c);
                        std::fflush(stdout);
                        play("sounds/momentum_up.wav", "Ping"); speak("Tesla rising fast");
                        { char m[160]; std::snprintf(m, sizeof(m), "CUSUM: subiendo fuerte %+.2f%% px %.2f", cusum_up*100, b.c); notify("TSLA alza", m, false); }
                        cusum_up = 0; cusum_dn = 0; last_cusum = b.t;
                    } else if (cusum_dn < -hthr) {
                        std::printf("[%02d:%02d] CUSUM: TSLA CAYENDO fuerte (%.2f%% acumulado) px %.2f\n",
                                    H, M, cusum_dn * 100, b.c);
                        std::fflush(stdout);
                        play("sounds/momentum_down.wav", "Basso"); speak("Tesla falling fast");
                        { char m[160]; std::snprintf(m, sizeof(m), "CUSUM: cayendo fuerte %.2f%% px %.2f", cusum_dn*100, b.c); notify("TSLA caida", m, false); }
                        cusum_up = 0; cusum_dn = 0; last_cusum = b.t;
                    }
                }
            }
            last_c_for_ret = b.c;
        }
        // 2) Supertrend(10,3) sobre barras 5m agregadas (menos ruido que 1m)
        static double a5o = 0, a5h = -1e18, a5l = 1e18, a5c = 0; static int a5n = 0;
        static double atr5 = 0, prev5c = 0; static long n5 = 0;
        if (a5n == 0) { a5o = b.o; a5h = b.h; a5l = b.l; }
        a5h = std::max(a5h, b.h); a5l = std::min(a5l, b.l); a5c = b.c; a5n++;
        bool bar5 = (a5n >= 5);
        if (bar5) {
            n5++;
            if (prev5c > 0) {
                double tr5 = a5h - a5l;
                tr5 = std::max(tr5, std::fabs(a5h - prev5c));
                tr5 = std::max(tr5, std::fabs(a5l - prev5c));
                atr5 = (n5 <= 10) ? (atr5 * (n5 - 1) + tr5) / n5 : atr5 + (tr5 - atr5) / 10.0;
            }
        }
        if (bar5 && atr5 > 0 && n5 > 10) {
            double mid = (a5h + a5l) / 2.0;
            double bu = mid + 4.0 * atr5, bl = mid - 4.0 * atr5;
            double bc = a5c;
            static double prev_c2 = 0;
            double b_c_save = b.c; (void)b_c_save;
            st_upper = (st_upper == 0 || bu < st_upper || prev_c2 > st_upper) ? bu : st_upper;
            st_lower = (st_lower == 0 || bl > st_lower || prev_c2 < st_lower) ? bl : st_lower;
            int nt = st_trend;
            if (st_trend >= 0) nt = (bc < st_lower) ? -1 : 1;
            else               nt = (bc > st_upper) ? 1 : -1;
            if (st_trend != 0 && nt != st_trend && alert_hours && b.t - last_st > 3600) {
                if (nt > 0) {
                    std::printf("[%02d:%02d] SUPERTREND: tendencia TSLA cambio a ALCISTA px %.2f\n", H, M, b.c);
                    play("sounds/momentum_up.wav", "Ping"); speak("Tesla trend is now up");
                    { char m[120]; std::snprintf(m, sizeof(m), "Supertrend: tendencia ALCISTA px %.2f", b.c); notify("TSLA tendencia", m, false); }
                } else {
                    std::printf("[%02d:%02d] SUPERTREND: tendencia TSLA cambio a BAJISTA px %.2f\n", H, M, b.c);
                    play("sounds/momentum_down.wav", "Basso"); speak("Tesla trend is now down");
                    { char m[120]; std::snprintf(m, sizeof(m), "Supertrend: tendencia BAJISTA px %.2f", b.c); notify("TSLA tendencia", m, false); }
                }
                std::fflush(stdout);
                last_st = b.t;
                st_upper = bu; st_lower = bl;  // reset bands on flip
            }
            st_trend = nt;
            prev_c2 = bc;
        }
        if (bar5) { a5n = 0; prev5c = a5c; a5h = -1e18; a5l = 1e18; }
        // 3) Donchian(20): ruptura del rango previo (Turtle)
        if ((int)dh20.size() == 390 && alert_hours && b.t - last_don > 3600) {
            double hi = -1e18, lo = 1e18;
            for (double x : dh20) hi = std::max(hi, x);
            for (double x : dl20) lo = std::min(lo, x);
            if (b.c > hi) {
                std::printf("[%02d:%02d] DONCHIAN: TSLA rompe maximo del dia px %.2f > %.2f\n", H, M, b.c, hi);
                std::fflush(stdout);
                play("sounds/momentum_up.wav", "Ping"); speak("Tesla breaking out");
                { char m[120]; std::snprintf(m, sizeof(m), "Donchian: rompe maximo del dia px %.2f", b.c); notify("TSLA breakout", m, false); }
                last_don = b.t;
            } else if (b.c < lo) {
                std::printf("[%02d:%02d] DONCHIAN: TSLA rompe minimo del dia px %.2f < %.2f\n", H, M, b.c, lo);
                std::fflush(stdout);
                play("sounds/momentum_down.wav", "Basso"); speak("Tesla breaking down");
                { char m[120]; std::snprintf(m, sizeof(m), "Donchian: rompe minimo del dia px %.2f", b.c); notify("TSLA breakdown", m, false); }
                last_don = b.t;
            }
        }
        dh20.push_back(b.h); if (dh20.size() > 390) dh20.pop_front();
        dl20.push_back(b.l); if (dl20.size() > 390) dl20.pop_front();

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
                std::printf("[%02d:%02d] *** TSLA: VENDER *** ~%.2f (%s, entrada %.2f)\n",
                            H, M, b.c, why, entry);
                std::fflush(stdout);
                play("sounds/dram_sell.wav", "Hero");
                speak("sell Tesla now");
                { char m[200]; std::snprintf(m, sizeof(m),
                    "VENDER TSLA @ %.2f | %s | entrada %.2f | PnL %+.1f%%",
                    b.c, why, entry, (b.c / entry - 1) * 100);
                  notify("TSLA: SELL NOW", m, true); }
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
                std::printf("[%02d:%02d] *** TSLA: COMPRAR *** ~%.2f (capitulacion confirmada; "
                            "target %.2f, floor %.2f)\n", H, M, entry, target_px, floor_px);
                std::fflush(stdout);
                play("sounds/dram_buy.wav", "Glass");
                speak("buy Tesla now");
                { char m[200]; std::snprintf(m, sizeof(m),
                    "COMPRAR TSLA @ %.2f | target %.2f (+4%%) | floor %.2f | capitulacion confirmada",
                    entry, target_px, floor_px);
                  notify("TSLA: BUY NOW", m, true); }
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
