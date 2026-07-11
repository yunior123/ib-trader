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
// Data: alpaca_ws_bridge (C++ ws daemon, 1 conexion Alpaca compartida) streams
//       REAL 1m completed bars as "EPOCH OPEN HIGH LOW CLOSE VOLUME" lines.
//
// build: clang++ -std=c++17 -O2 -o dram_signal_bot dram_signal_bot.cpp
// run:   ./dram_signal_bot            (spawns bridge)
//        ./dram_signal_bot --stdin    (replay: feed bar lines for testing)

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cctype>
#include <cmath>
#include <ctime>
#include <deque>
#include <unistd.h>
#include <csignal>

struct Bar { double t, o, h, l, c, v; };

// ---- config (mirror of DEFAULT_CONFIG) ----
// ---- params: por-ticker via env DRAM_* (orden Yunior 2026-07-10 "tune per
// ticker") — un solo set de parametros en 4 microestructuras distintas mata
// la expectancy; ahora el keepalive exporta el set ajustado por backtest.
static double envd(const char* k, double d) {
    const char* v = std::getenv(k);
    return (v && *v) ? atof(v) : d;
}
static const int    BB_N = 20;      static const double BB_STD = envd("DRAM_BB_STD", 3.0);
static const int    RSI_N = 14;     static const double RSI_OS = envd("DRAM_RSI_OS", 25.0);
static const int    VOL_N = 20;     static const double VOL_MULT = envd("DRAM_VOL_MULT", 1.2);
static const int    ATR_N = 14;
static const int    CONFIRM_WINDOW = 60;
static const double TARGET_PCT = envd("DRAM_TARGET", 4.0),
                    FLOOR_PCT  = envd("DRAM_FLOOR", 1.0),
                    TRAIL_ATR  = envd("DRAM_TRAIL_ATR", 3.0);
// HARD STOP alert (orden 2026-07-10): a -DRAM_STOP% del entry el bot GRITA la
// perdida (SELL-STOP) en vez de callarse a esperar el floor. Humano decide.
static const double STOP_PCT = envd("DRAM_STOP", 3.0);
// afinado 2026-07-10 (skills mean-reversion/exit-strategies + estudio 30d):
// SKIP_OPEN: min tras 9:30 sin entradas (los arms del open eran subasta);
// TIME_STOP_MIN: trade que no revirtio en N min = hipotesis muerta -> eject;
// EOD_FORCE: 15:45 plano SIEMPRE (sin bag overnight; para SPCX obligatorio);
// CONFIRM_STRICT: bar de confirmacion con volumen>=volMA y close en mitad alta;
// MAX_DAY: entradas max por dia (0 = sin limite).
static const double SKIP_OPEN      = envd("DRAM_SKIP_OPEN", 0);
static const double TIME_STOP_MIN  = envd("DRAM_TIME_STOP_MIN", 0);
static const double EOD_FORCE      = envd("DRAM_EOD_FORCE", 0);
static const double CONFIRM_STRICT = envd("DRAM_CONFIRM_STRICT", 0);
static const double MAX_DAY        = envd("DRAM_MAX_DAY", 0);
// ===== MOTOR v3 CONFLUENCE (orden Yunior 2026-07-11: "bollinger 50% en 1m
// y 15m, vwap, rsi, volumen, whales, bids/asks — terremoto sin falsos
// positivos"). SCORE_MIN > 0 activa el arm por confluencia PONDERADA:
//   0.25 BB-1m(z) + 0.25 BB-15m(z) + 0.15 RSI + 0.15 dist-VWAP + 0.15 vol
//   + 0.05 whales (solo live, data/whale_*.txt del daemon)
// SCORE_MIN = 0 (default) -> gate clasico duro, comportamiento previo intacto.
static const double SCORE_MIN  = envd("DRAM_SCORE_MIN", 0);
static const double WHALE_USD  = envd("DRAM_WHALE_USD", 75000);
// SPREAD_MAX > 0: al confirmar, si el NBBO vivo (data/nbbo_*.txt del daemon)
// muestra spread% mayor, NO se confirma (proteccion live; backtest no afecta).
static const double SPREAD_MAX = envd("DRAM_SPREAD_MAX", 0);
// TREND MODE generico (DRAM_MODE=trend): flip Supertrend 5m / ruptura max del
// dia con CUSUM >= TREND_CUSUM; TREND_VWAP=1 exige ademas c>VWAP y vol>=volMA.
static const bool TREND_MODE = [] {
    const char* v = std::getenv("DRAM_MODE");
    return v && !std::strcmp(v, "trend");
}();
static const double TREND_CUSUM = envd("DRAM_TREND_CUSUM", 0.01);
static const double TREND_VWAP  = envd("DRAM_TREND_VWAP", 0);
// ===== v4 AMBAS DIRECCIONES (orden Yunior 2026-07-11: señales cuando sube
// Y cuando baja). DRAM_SHORTS=1 activa el espejo corto: blow-off arriba de la
// banda + RSI sobrecomprado + volumen, confirmado por bar rojo que pierde el
// minimo del bar de euforia -> "SHORT NOW"; gestion simetrica (target abajo,
// trail sobre el minimo, HARD STOP arriba, EOD cover). En trend mode: flip
// bajista del Supertrend / ruptura del MINIMO del dia con CUSUM negativo.
// El lado largo NO se toca (los cortos ceden ante un largo confirmado:
// cover por reversal). Default 0 -> comportamiento identico byte a byte.
static const double SHORTS = envd("DRAM_SHORTS", 0);
// exits propios del corto (los mercados caen distinto a como suben);
// sin definir heredan los del largo
static const double S_TARGET = envd("DRAM_S_TARGET", TARGET_PCT);
static const double S_STOP   = envd("DRAM_S_STOP", STOP_PCT);
static const double S_TRAIL  = envd("DRAM_S_TRAIL", TRAIL_ATR);
static const double S_FLOOR  = envd("DRAM_S_FLOOR", FLOOR_PCT);
static const double S_TSTOP  = envd("DRAM_S_TSTOP", TIME_STOP_MIN);
// entradas PROPIAS del corto (optimize shorts 2026-07-11): sin definir
// heredan el lado largo. S_MODE fuerza el motor del corto ("mr" o "trend")
// independiente del largo — un ticker trend-largo puede cortear mejor en
// blow-off MR y viceversa.
static const double S_BB_STD    = envd("DRAM_S_BB_STD", BB_STD);
static const double S_RSI_OS    = envd("DRAM_S_RSI_OS", RSI_OS);
static const double S_VOL_MULT  = envd("DRAM_S_VOL_MULT", VOL_MULT);
static const double S_SCORE_MIN = envd("DRAM_S_SCORE_MIN", SCORE_MIN);
static const double S_TCUSUM    = envd("DRAM_S_TREND_CUSUM", TREND_CUSUM);

// ===== PATRONES DE VELAS (orden Yunior 2026-07-11 "signals have also into
// account candle patterns"; ref TA-Lib CDL*): con {SYM}_CANDLE=1 el bar de
// confirmacion/entrada debe ADEMAS ser patron direccional — engulfing,
// hammer/shooting-star o marubozu. 0 = off (regresion byte-identica). El
// optimizador WFO decide ON/OFF por ticker con datos, no por fe.
static const double CANDLE   = envd("DRAM_CANDLE", 0);
static const double S_CANDLE = envd("DRAM_S_CANDLE", CANDLE);
static bool candle_bull(const Bar& p, const Bar& b) {
    double body = b.c - b.o, rng = b.h - b.l;
    if (rng <= 1e-12) return false;
    bool engulf = b.c > b.o && p.c < p.o && b.c >= p.o && b.o <= p.c;
    double lower = (b.o < b.c ? b.o : b.c) - b.l;
    bool hammer = lower >= 2.0 * std::fabs(body) && b.c >= b.l + 0.6 * rng;
    bool marubozu = body > 0 && body >= 0.8 * rng;
    return engulf || hammer || marubozu;
}
static bool candle_bear(const Bar& p, const Bar& b) {
    double body = b.o - b.c, rng = b.h - b.l;
    if (rng <= 1e-12) return false;
    bool engulf = b.c < b.o && p.c > p.o && b.c <= p.o && b.o >= p.c;
    double upper = b.h - (b.o > b.c ? b.o : b.c);
    bool star = upper >= 2.0 * std::fabs(b.c - b.o) && b.c <= b.h - 0.6 * rng;
    bool marubozu = body > 0 && body >= 0.8 * rng;
    return engulf || star || marubozu;
}
// TERREMOTO banner-grade (orden Yunior 2026-07-11: "detect up and down in
// ALL of them"): el CUSUM detecta movimientos fuertes en AMBAS direcciones
// en los 13; con QUAKE_BANNER=1 dejan de ser solo-log y hacen banner+sonido.
// QUAKE_MIN = movimiento acumulado minimo (fraccion), afinado por ticker en
// backtest 2026 para precision >=70% (el movimiento aguanta, no es ruido).
static const double QUAKE_MIN    = envd("DRAM_QUAKE_MIN", 0.02);
static const double QUAKE_BANNER = envd("DRAM_QUAKE_BANNER", 0);
static const bool S_MODE_TREND = [] {
    const char* v = std::getenv("DRAM_S_MODE");
    if (v && !std::strcmp(v, "trend")) return true;
    if (v && !std::strcmp(v, "mr")) return false;
    const char* m = std::getenv("DRAM_MODE");           // hereda el modo largo
    return m && !std::strcmp(m, "trend");
}();
static const char* SPOS_FILE = "data/pos_dram_s.txt";
static void save_spos(double e, double tr, double fl, double tg, double ep) {
    FILE* f = fopen(SPOS_FILE, "w");
    if (f) { fprintf(f, "%f %f %f %f %f\n", e, tr, fl, tg, ep); fclose(f); }
}
static const char* WHALE_FILE = "data/whale_dram.txt";
static const char* NBBO_FILE  = "data/nbbo_dram.txt";

// ballenas recientes (<=10 min) por encima de WHALE_USD -> 0..1 (solo live)
static double whale_score(double now, int want_dir = 1) {
    FILE* f = fopen(WHALE_FILE, "r");
    if (!f) return 0;
    double sc = 0; char line[160];
    while (fgets(line, sizeof(line), f)) {
        double ep = 0, px = 0, usd = 0; int dir = 0;
        if (sscanf(line, "%lf %lf %lf %d", &ep, &px, &usd, &dir) >= 3 &&
            now - ep <= 600 && usd >= WHALE_USD)
            sc += (dir * want_dir >= 0 ? 0.5 : 0.25);   // el lado buscado pesa doble
    }
    fclose(f);
    return sc > 1.0 ? 1.0 : sc;
}
// spread % del NBBO vivo del daemon; 0 si no hay dato fresco (<=10s)
static double nbbo_spread_pct() {
    FILE* f = fopen(NBBO_FILE, "r");
    if (!f) return 0;
    double ep = 0, bid = 0, ask = 0;
    int n = fscanf(f, "%lf %lf %lf", &ep, &bid, &ask);
    fclose(f);
    if (n != 3 || bid <= 0 || ask <= bid) return 0;
    if (time(nullptr) - (time_t)ep > 10) return 0;
    return (ask - bid) / ((ask + bid) / 2) * 100.0;
}
// posicion virtual PERSISTIDA (fix 2026-07-10: un restart perdia la posicion
// y los SELL se desincronizaban de lo que Yunior realmente tiene)
static const char* POS_FILE = "data/pos_dram.txt";
static bool g_pos_restored = false;
static void save_pos(double e, double pk, double fl, double tg, double ep) {
    FILE* f = fopen(POS_FILE, "w");
    if (f) { fprintf(f, "%f %f %f %f %f\n", e, pk, fl, tg, ep); fclose(f); }
}

// ---- shell safety: whitelist filter for anything interpolated into system()
// Solo alnum + " .,%+-:/()_"; todo lo demas -> espacio. Sin comillas, $, `,
// ;, |, &, \ ni saltos de linea: imposible inyectar shell o AppleScript.
static void sh_sanitize(const char* in, char* out, size_t n) {
    size_t j = 0;
    for (size_t i = 0; in && in[i] && j + 1 < n; ++i) {
        unsigned char c = (unsigned char)in[i];
        out[j++] = (std::isalnum(c) || std::strchr(" .,%+-:/()_", c)) ? (char)c : ' ';
    }
    out[j] = 0;
}

// ---- gobernador de audio (fix sobrecarga coreaudiod 2026-07-09) ----
// El bridge re-emite ~2 dias de barras (warm-up) en cada arranque; sin gate,
// cada alerta historica lanzaba say/afplay/osascript simultaneos y saturaba
// el audio del Mac. Reglas: (1) solo suenan barras en tiempo real (<=240s de
// edad); (2) minimo 20s entre audios de deteccion; BUY/SELL saltan (2) pero
// nunca (1). Warm-up y replays --stdin quedan 100% mudos (solo log/stdout).
static double g_bar_epoch = 0;   // epoch de la barra en proceso (set en el loop)
static time_t g_last_audio = 0;
static bool bar_is_live() {
    return g_bar_epoch > 0 && time(nullptr) - (time_t)g_bar_epoch <= 240;
}
static bool audio_gate(bool money) {
    if (!bar_is_live()) return false;                     // historica: mudo
    time_t now = time(nullptr);
    if (!money && now - g_last_audio < 20) return false;  // anti-rafaga
    g_last_audio = now;
    return true;
}

static void speak(const char* phrase) {
    // System TTS (macOS `say`), async. Voice: $DRAM_VOICE override, else Daniel
    // (most natural installed). For an even more human voice: System Settings >
    // Accessibility > Spoken Content > Manage Voices > download "Ava (Premium)"
    // or "Zoe (Premium)", then export DRAM_VOICE="Ava (Premium)".
    const char* v = std::getenv("DRAM_VOICE");
    if (!v || !*v) v = "Daniel";
    char sv[64], sp[240], cmd[400];
    sh_sanitize(v, sv, sizeof(sv));
    sh_sanitize(phrase, sp, sizeof(sp));
    // una sola voz a la vez: corta cualquier locucion previa antes de hablar
    std::snprintf(cmd, sizeof(cmd),
                  "killall say >/dev/null 2>&1; say -v '%s' -r 170 '%s' >/dev/null 2>&1 &",
                  sv, sp);
    std::system(cmd);
}

static void play(const char* f, const char* fb) {
    char sf[256], sfb[64], cmd[512];
    sh_sanitize(f, sf, sizeof(sf));
    sh_sanitize(fb, sfb, sizeof(sfb));
    if (access(f, R_OK) == 0)
        std::snprintf(cmd, sizeof(cmd),
                      "[ $(pgrep -x afplay | wc -l) -lt 3 ] && afplay '%s' >/dev/null 2>&1 &", sf);
    else
        std::snprintf(cmd, sizeof(cmd),
                      "[ $(pgrep -x afplay | wc -l) -lt 3 ] && "
                      "afplay /System/Library/Sounds/%s.aiff >/dev/null 2>&1 &", sfb);
    std::system(cmd);
}

#include "fleet_notify.h"

// ---- notifications: Mac (posix_spawn C++) + ops log (solo Mac desde 2026-07-09)
static void notify(const char* title, const char* msg, bool urgent) {
    // 1) banner Mac URGENTE via posix_spawn C++ (Yunior 2026-07-10: todas las
    //    notificaciones urgentes, sin shell) — solo tiempo real (warm-up no banners)
    // MONEY-ONLY banners (orden Yunior 2026-07-10): solo BUY/SELL/STOP suenan;
    // el radar (CUSUM/Supertrend/Donchian) va SOLO al log — ratio ruido:dinero
    // era 40-160:1 y entrenaba a ignorar la urgencia.
    // Posicion restaurada de disco: su SELL avisa aunque el bar sea warm-up.
    if (urgent && (bar_is_live() || g_pos_restored)) fleet_notify_urgent(title, msg);
    // 3) structured operations log
    FILE* f = std::fopen("dram_operations.log", "a");
    if (f) {
        time_t now = time(nullptr); struct tm lt; localtime_r(&now, &lt);
        std::fprintf(f, "%04d-%02d-%02d %02d:%02d:%02d | %s%s | %s\n",
                     lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday,
                     lt.tm_hour, lt.tm_min, lt.tm_sec,
                     bar_is_live() ? "" : "WARMUP ", title, msg);
        std::fclose(f);
    }
}

static void et_hm(double epoch, int& h, int& m) {  // Mac local tz == Toronto/ET
    time_t t = (time_t)epoch;
    struct tm lt; localtime_r(&t, &lt);
    h = lt.tm_hour; m = lt.tm_min;
}

// ---- cierre seguro: SIGTERM/SIGINT tumban tambien al bridge (mismo grupo) ----
static void on_term(int) {
    std::signal(SIGTERM, SIG_IGN);   // inmune a nuestro propio kill de grupo
    kill(0, SIGTERM);                // bridge (sh + python) cae con nosotros
    _exit(0);
}

int main(int argc, char** argv) {
    setpgid(0, 0);                    // grupo propio: el killpg no toca al keepalive
    std::signal(SIGINT, on_term);  std::signal(SIGTERM, on_term);
    std::signal(SIGHUP, on_term);  std::signal(SIGPIPE, SIG_IGN);
    bool use_stdin = (argc > 1 && !std::strcmp(argv[1], "--stdin"));
    FILE* in = stdin;
    if (!use_stdin) {
        // ws daemon compartido escribe data/bars_dram.txt; el reader lo sigue
        // (Yunior 2026-07-10: websockets, no REST; C++, no python)
        in = popen("./alpaca_ws_bridge read DRAM 2>>bridge_dram.log", "r");
        if (!in) { std::fprintf(stderr, "no bridge\n"); return 1; }
        std::fprintf(stderr, "dram_signal_bot (C++): bridge DRAM 1m real iniciado\n");
    }

    std::deque<double> closes, vols;      // rolling 20
    double avg_gain = 0, avg_loss = 0, prev_close = 0, atr = 0;
    long   nbars = 0;

    // confirmed-entry state
    bool armed = false; double armed_high = 0, armed_rsi = 0; long armed_bar = 0;
    bool pending_buy = false;
    // short-entry state (v4, activo solo con SHORTS=1)
    bool armed_s = false; double armed_low = 0, armed_rsi_s = 0; long armed_bar_s = 0;
    bool pending_short = false;
    bool in_short = false; double s_entry = 0, s_trough = 0, s_floor = 0, s_target = 0;
    double spos_epoch = 0;
    if (SHORTS > 0) {
        if (FILE* pf = fopen(SPOS_FILE, "r")) {
            if (fscanf(pf, "%lf %lf %lf %lf %lf",
                       &s_entry, &s_trough, &s_floor, &s_target, &spos_epoch) == 5 && s_entry > 0) {
                in_short = true; g_pos_restored = true;
                fprintf(stderr, "posicion CORTA restaurada: entry %.4f\n", s_entry);
            }
            fclose(pf);
        }
    }
    // --- detection layers (alerting, not trading) ---
    // CUSUM (Lopez de Prado structural breaks): all abrupt falls/rises
    double cusum_up = 0, cusum_dn = 0, ret_var = 1e-6;
    // Supertrend(10,3): tendency change
    double st_upper = 0, st_lower = 0; int st_trend = 0;  // 1 up, -1 down
    // Donchian(20): breakout of prior range
    std::deque<double> dh20, dl20;
    // debounce per alert type
    double last_cusum = 0, last_st = 0, last_don = 0;
    // virtual position (persistida en POS_FILE; sobrevive restarts)
    bool in_pos = false; double entry = 0, peak = 0, floor_px = 0, target_px = 0;
    double pos_epoch = 0;
    if (FILE* pf = fopen(POS_FILE, "r")) {
        if (fscanf(pf, "%lf %lf %lf %lf %lf",
                   &entry, &peak, &floor_px, &target_px, &pos_epoch) == 5 && entry > 0) {
            in_pos = true; g_pos_restored = true;
            fprintf(stderr, "posicion restaurada de disco: entry %.4f\n", entry);
        }
        fclose(pf);
    }

    char line[512]; Bar b; Bar pb{}; bool has_pb = false;
    while (std::fgets(line, sizeof(line), in)) {
        if (std::sscanf(line, "%lf %lf %lf %lf %lf %lf",
                        &b.t, &b.o, &b.h, &b.l, &b.c, &b.v) != 6) continue;
        nbars++;
        g_bar_epoch = b.t;

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
        double bb_low = 0, bb_up = 0, vol_ma = 0, bb_z = 0; bool ind_ok = false;
        double bb_mean = 0, bb_sd = 0;
        if ((int)closes.size() == BB_N && nbars > RSI_N) {
            double mean = 0; for (double x : closes) mean += x; mean /= BB_N;
            double var = 0;  for (double x : closes) var += (x - mean) * (x - mean);
            double sd = std::sqrt(var / BB_N);
            bb_low = mean - BB_STD * sd;
            bb_up  = mean + BB_STD * sd;
            bb_mean = mean; bb_sd = sd;
            if (sd > 1e-12) bb_z = (mean - b.c) / sd;   // + = debajo de la media
            for (double x : vols) vol_ma += x; vol_ma /= VOL_N;
            ind_ok = vol_ma > 0;
        }

        int H, M; et_hm(b.t, H, M);
        int mins = H * 60 + M;
        bool rth_entry = mins >= 570 + (int)SKIP_OPEN && mins < 930;
        // 24/5 (orden Yunior 2026-07-11): alertas Dom 20:00 -> Vie 20:00 ET;
        // fuera de esa ventana no hay venue US abierto (el gate es defensivo,
        // los bars solo llegan cuando una sesion imprime)
        struct tm awd; time_t abt = (time_t)b.t; localtime_r(&abt, &awd);
        bool alert_hours = !(awd.tm_wday == 6 || (awd.tm_wday == 5 && H >= 20)
                             || (awd.tm_wday == 0 && H < 20));

        // ---- contexto v3: VWAP de sesion (RTH) + Bollinger 15m ----
        static long vday = 0; static double vwap_pv = 0, vwap_v = 0;
        if ((long)(b.t / 86400) != vday) { vday = (long)(b.t / 86400); vwap_pv = vwap_v = 0; }
        if (mins >= 570 && mins < 960) {
            double tp = (b.h + b.l + b.c) / 3.0;
            vwap_pv += tp * b.v; vwap_v += b.v;
        }
        double vwap = vwap_v > 0 ? vwap_pv / vwap_v : 0;
        static std::deque<double> c15q; static long cur15 = 0; static double last15c = 0;
        long bkt15 = (long)(b.t / 900);
        if (cur15 == 0) cur15 = bkt15;
        if (bkt15 != cur15) {
            c15q.push_back(last15c); if (c15q.size() > 20) c15q.pop_front();
            cur15 = bkt15;
        }
        last15c = b.c;
        double z15 = 0;
        if (c15q.size() == 20) {
            double m15 = 0; for (double x : c15q) m15 += x; m15 /= 20;
            double v15 = 0; for (double x : c15q) v15 += (x - m15) * (x - m15);
            double sd15 = std::sqrt(v15 / 20);
            if (sd15 > 1e-9) z15 = (m15 - b.c) / sd15;
        }

        // ===== DETECTION LAYERS =====
        // 1) CUSUM filter (Lopez de Prado): statistical break -> falls/rises of ANY kind
        if (nbars > 1 && prev_close > 0) { /* prev_close ya actualizado: usar retorno del bar */ }
        {
            static double last_c_for_ret = 0;
            if (last_c_for_ret > 0) {
                double r = std::log(b.c / last_c_for_ret);
                ret_var += (r * r - ret_var) / 50.0;           // EWMA variance
                double hthr = std::max(8.0 * std::sqrt(ret_var), QUAKE_MIN);  // 8-sigma y minimo QUAKE_MIN
                cusum_up = std::max(0.0, cusum_up + r);
                cusum_dn = std::min(0.0, cusum_dn + r);
                bool vol_ok_radar = vol_ma <= 0 || b.v >= vol_ma;   // terremoto
                if (alert_hours && vol_ok_radar && b.t - last_cusum > 3600) {
                    if (cusum_up > hthr) {
                        std::printf("[%02d:%02d] CUSUM: DRAM SUBIENDO fuerte (+%.2f%% acumulado) px %.2f t=%.0f\n",
                                    H, M, cusum_up * 100, b.c, b.t);
                        std::fflush(stdout);
                        { char m[160]; std::snprintf(m, sizeof(m), "CUSUM: subiendo fuerte %+.2f%% px %.2f", cusum_up*100, b.c); notify("DRAM TERREMOTO ALZA", m, QUAKE_BANNER > 0); }
                        cusum_up = 0; cusum_dn = 0; last_cusum = b.t;
                    } else if (cusum_dn < -hthr) {
                        std::printf("[%02d:%02d] CUSUM: DRAM CAYENDO fuerte (%.2f%% acumulado) px %.2f t=%.0f\n",
                                    H, M, cusum_dn * 100, b.c, b.t);
                        std::fflush(stdout);
                        { char m[160]; std::snprintf(m, sizeof(m), "CUSUM: cayendo fuerte %.2f%% px %.2f", cusum_dn*100, b.c); notify("DRAM TERREMOTO CAIDA", m, QUAKE_BANNER > 0); }
                        cusum_up = 0; cusum_dn = 0; last_cusum = b.t;
                    }
                }
            }
            last_c_for_ret = b.c;
        }
        // 2) Supertrend 5m: bandas mid +/- 4.0*ATR5(10) (menos ruido que 1m)
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
                    std::printf("[%02d:%02d] SUPERTREND: tendencia DRAM cambio a ALCISTA px %.2f\n", H, M, b.c);
                    { char m[120]; std::snprintf(m, sizeof(m), "Supertrend: tendencia ALCISTA px %.2f", b.c); notify("DRAM tendencia", m, false); }
                } else {
                    std::printf("[%02d:%02d] SUPERTREND: tendencia DRAM cambio a BAJISTA px %.2f\n", H, M, b.c);
                    { char m[120]; std::snprintf(m, sizeof(m), "Supertrend: tendencia BAJISTA px %.2f", b.c); notify("DRAM tendencia", m, false); }
                }
                std::fflush(stdout);
                last_st = b.t;
                st_upper = bu; st_lower = bl;  // reset bands on flip
            }
            st_trend = nt;
            prev_c2 = bc;
        }
        if (bar5) { a5n = 0; prev5c = a5c; a5h = -1e18; a5l = 1e18; }
        // 3) Donchian 390x1m (~sesion completa): ruptura del rango del dia
        if ((int)dh20.size() == 390 && alert_hours && b.t - last_don > 3600) {
            double hi = -1e18, lo = 1e18;
            for (double x : dh20) hi = std::max(hi, x);
            for (double x : dl20) lo = std::min(lo, x);
            if (b.c > hi) {
                std::printf("[%02d:%02d] DONCHIAN: DRAM rompe maximo del dia px %.2f > %.2f\n", H, M, b.c, hi);
                std::fflush(stdout);
                { char m[120]; std::snprintf(m, sizeof(m), "Donchian: rompe maximo del dia px %.2f", b.c); notify("DRAM breakout", m, false); }
                last_don = b.t;
            } else if (b.c < lo) {
                std::printf("[%02d:%02d] DONCHIAN: DRAM rompe minimo del dia px %.2f < %.2f\n", H, M, b.c, lo);
                std::fflush(stdout);
                { char m[120]; std::snprintf(m, sizeof(m), "Donchian: rompe minimo del dia px %.2f", b.c); notify("DRAM breakdown", m, false); }
                last_don = b.t;
            }
        }
        dh20.push_back(b.h); if (dh20.size() > 390) dh20.pop_front();
        dl20.push_back(b.l); if (dl20.size() > 390) dl20.pop_front();
        // ---- TREND MODE: señal de entrada (generico desde 2026-07-11) ----
        static int st_prev_trend = 0;
        static long tday = 0; static double tday_hi = 0, tday_lo = 0;
        if ((long)(b.t / 86400) != tday) { tday = (long)(b.t / 86400); tday_hi = 0; tday_lo = 0; }
        if (TREND_MODE && !in_pos && !pending_buy && nbars > 30) {
            bool trend_rth = mins >= 570 + (int)SKIP_OPEN && mins < 930;
            bool flip_up = st_prev_trend <= 0 && st_trend > 0;
            bool don_break = tday_hi > 0 && b.c > tday_hi;
            bool vwap_ok = TREND_VWAP == 0 ||
                           (vwap > 0 && b.c > vwap && vol_ma > 0 && b.v >= vol_ma);
            if (trend_rth && (flip_up || don_break) && cusum_up >= TREND_CUSUM && vwap_ok
                && (CANDLE == 0 || (has_pb && candle_bull(pb, b)))) {
                pending_buy = true;
                std::printf("[%02d:%02d] TREND-ENTRY armado: %s px %.2f (CUSUM +%.2f%%)\n",
                            H, M, flip_up ? "Supertrend flip UP" : "ruptura max del dia",
                            b.c, cusum_up * 100);
                std::fflush(stdout);
            }
        }
        if (S_MODE_TREND && SHORTS > 0 && !in_pos && !in_short && !pending_short &&
            !pending_buy && nbars > 30) {
            bool trend_rth = mins >= 570 + (int)SKIP_OPEN && mins < 930;
            bool flip_dn = st_prev_trend >= 0 && st_trend < 0;
            bool don_break_dn = tday_lo > 0 && b.c < tday_lo;
            if (trend_rth && (flip_dn || don_break_dn) && cusum_dn <= -S_TCUSUM
                && (S_CANDLE == 0 || (has_pb && candle_bear(pb, b)))) {
                pending_short = true;
                std::printf("[%02d:%02d] TREND-PUT armado: %s px %.2f (CUSUM %.2f%%)\n",
                            H, M, flip_dn ? "Supertrend flip DOWN" : "ruptura min del dia",
                            b.c, cusum_dn * 100);
                std::fflush(stdout);
            }
        }
        st_prev_trend = st_trend;
        if (b.h > tday_hi) tday_hi = b.h;
        if (tday_lo == 0 || b.l < tday_lo) tday_lo = b.l;

        // ---- SELL management on virtual position ----
        // (bars anteriores al entry restaurado no gestionan la posicion)
        if (in_pos && b.t >= pos_epoch) {
            if (b.h > peak) { peak = b.h; save_pos(entry, peak, floor_px, target_px, pos_epoch); }
            bool sold = false; const char* why = "";
            double exit_px = b.c;   // fill realista: target = limit en target_px
            double stop_px = entry * (1 - STOP_PCT / 100.0);
            if (b.c <= stop_px) { sold = true; why = "HARD STOP"; }
            // bar ambiguo (toco stop Y target en el mismo bar): manda el STOP.
            // Un limit en target no se asume lleno cuando el bar barrio el
            // stop; fill pesimista al stop (o al open si abrio por debajo).
            else if (b.h >= target_px && b.l <= stop_px) {
                sold = true; why = "HARD STOP (bar ambiguo)";
                exit_px = std::min(b.o, stop_px);
            }
            else if (b.h >= target_px) { sold = true; why = "target"; exit_px = target_px; }
            else if (TREND_MODE && st_trend < 0) { sold = true; why = "supertrend flip DOWN"; }
            else if (atr > 0 && b.c < peak - TRAIL_ATR * atr && b.c > floor_px) {
                sold = true; why = "trail 3xATR roto";
            } else if (TIME_STOP_MIN > 0 && b.t - pos_epoch >= TIME_STOP_MIN * 60 &&
                       b.c < floor_px) {
                sold = true; why = "time-stop (no revirtio)";
            } else if (H > 15 || (H == 15 && M >= 45)) {
                if (b.c >= floor_px || EOD_FORCE > 0) { sold = true; why = "EOD flatten 15:45"; }
            }
            if (sold) {
                std::printf("[%02d:%02d] *** DRAM: VENDER *** ~%.2f (%s, entrada %.2f) t=%.0f\n",
                            H, M, exit_px, why, entry, b.t);
                std::fflush(stdout);
                if (audio_gate(true)) { play("sounds/dram_sell.wav", "Hero"); speak("sell DRAM now"); }
                { char m[200]; std::snprintf(m, sizeof(m),
                    "VENDER DRAM @ %.2f | %s | entrada %.2f | PnL %+.1f%%",
                    exit_px, why, entry, (exit_px / entry - 1) * 100);
                  notify(why[0] == 'H' ? "DRAM: SELL-STOP" : "DRAM: SELL NOW", m, true); }
                in_pos = false; g_pos_restored = false;
                unlink(POS_FILE);
            }
        }

        // ---- BUY: pending fill then arming (mirrors engine order) ----
        static long entry_day = 0; static int day_entries = 0;
        if ((long)(b.t / 86400) != entry_day) { entry_day = (long)(b.t / 86400); day_entries = 0; }
        if (pending_buy && !in_pos) {
            pending_buy = false;
            if (rth_entry && (MAX_DAY == 0 || day_entries < (int)MAX_DAY)) {
                if (in_short) {   // reversal: capitulacion confirmada = cubrir corto
                    double px = b.o;
                    std::printf("[%02d:%02d] *** DRAM: VENDER PUT *** ~%.2f (reversal a largo, entrada %.2f) t=%.0f\n",
                                H, M, px, s_entry, b.t);
                    std::fflush(stdout);
                    if (audio_gate(true)) { play("sounds/dram_buy.wav", "Glass"); speak("sell DRAM put now"); }
                    { char m[200]; std::snprintf(m, sizeof(m),
                        "VENDER PUT DRAM @ %.2f | reversal a alza | entrada %.2f | mov %+.1f%%",
                        px, s_entry, (s_entry / px - 1) * 100);
                      notify("DRAM: SELL PUT", m, true); }
                    in_short = false; unlink(SPOS_FILE);
                }
                in_pos = true; entry = b.o; peak = b.h;
                floor_px = entry * (1 + FLOOR_PCT / 100.0);
                target_px = entry * (1 + TARGET_PCT / 100.0);
                pos_epoch = b.t; day_entries++;
                save_pos(entry, peak, floor_px, target_px, pos_epoch);
                std::printf("[%02d:%02d] *** DRAM: COMPRAR *** ~%.2f (capitulacion confirmada; "
                            "target %.2f, floor %.2f) t=%.0f\n", H, M, entry, target_px, floor_px, b.t);
                std::fflush(stdout);
                if (audio_gate(true)) { play("sounds/dram_buy.wav", "Glass"); speak("buy DRAM now"); }
                { char m[200]; std::snprintf(m, sizeof(m),
                    "COMPRAR DRAM @ %.2f (shares o CALL) | target %.2f | floor %.2f | capitulacion confirmada",
                    entry, target_px, floor_px);
                  notify("DRAM: BUY NOW", m, true); }
            }
        }
        if (!TREND_MODE && ind_ok && !in_pos && !pending_buy && rth_entry) {
            bool capit;
            if (SCORE_MIN > 0) {
                // v3: confluencia ponderada — BB pesa 50% (25% 1m + 25% 15m)
                double s_z1  = std::min(1.0, std::max(0.0, bb_z / BB_STD));
                double s_z15 = std::min(1.0, std::max(0.0, z15 / 2.0));
                double s_rsi = std::min(1.0, std::max(0.0, (RSI_OS + 10 - rsi) / 20.0));
                double atr_pct = b.c > 0 ? atr / b.c : 0;
                double s_vw = (vwap > 0 && atr_pct > 1e-6)
                    ? std::min(1.0, std::max(0.0, ((vwap - b.c) / b.c) / (2.0 * atr_pct))) : 0;
                double s_vol = vol_ma > 0
                    ? std::min(1.0, std::max(0.0, b.v / vol_ma - 0.8)) : 0;
                double sc = 0.25 * s_z1 + 0.25 * s_z15 + 0.15 * s_rsi
                          + 0.15 * s_vw + 0.15 * s_vol;
                if (bar_is_live()) sc += 0.05 * whale_score(b.t);
                capit = sc >= SCORE_MIN;
                if (capit) {
                    std::printf("[%02d:%02d] v3-ARM score %.2f (z1 %.2f z15 %.2f rsi %.0f "
                                "vwapd %.2f%% vol %.1fx)\n", H, M, sc, bb_z, z15, rsi,
                                vwap > 0 ? (vwap - b.c) / b.c * 100 : 0,
                                vol_ma > 0 ? b.v / vol_ma : 0);
                    std::fflush(stdout);
                }
            } else {
                capit = b.c <= bb_low && rsi <= RSI_OS && b.v >= vol_ma * VOL_MULT;
            }
            if (capit) { armed = true; armed_high = b.h; armed_rsi = rsi; armed_bar = nbars; }
            else if (armed && nbars - armed_bar <= CONFIRM_WINDOW
                     && b.c > armed_high && b.c > b.o && rsi > armed_rsi
                     && (CANDLE == 0 || (has_pb && candle_bull(pb, b)))
                     && (CONFIRM_STRICT == 0 ||
                         (b.v >= vol_ma && b.c >= b.l + 0.5 * (b.h - b.l)))) {
                double sp = (SPREAD_MAX > 0 && bar_is_live()) ? nbbo_spread_pct() : 0;
                if (sp > SPREAD_MAX && SPREAD_MAX > 0) {
                    std::printf("[%02d:%02d] confirm BLOQUEADO: spread %.2f%% > %.2f%%\n",
                                H, M, sp, SPREAD_MAX);
                    std::fflush(stdout);
                } else { pending_buy = true; armed = false; }
            }
            if (armed && nbars - armed_bar > CONFIRM_WINDOW) armed = false;
        }

        // ===== LADO CORTO v4 (señales tambien cuando BAJA) =====
        if (SHORTS > 0) {
            static int sday_entries = 0; static long sday = 0;
            if ((long)(b.t / 86400) != sday) { sday = (long)(b.t / 86400); sday_entries = 0; }
            // gestion de la posicion corta virtual
            if (in_short && b.t >= spos_epoch) {
                if (b.l < s_trough) { s_trough = b.l; save_spos(s_entry, s_trough, s_floor, s_target, spos_epoch); }
                bool cov = false; const char* why = ""; double exit_px = b.c;
                double s_stop_px = s_entry * (1 + S_STOP / 100.0);
                if (b.c >= s_stop_px) { cov = true; why = "HARD STOP"; }
                // espejo corto del bar ambiguo: si el bar toco cover-stop Y
                // target, manda el STOP (fill al stop o al open si abrio arriba)
                else if (b.l <= s_target && b.h >= s_stop_px) {
                    cov = true; why = "HARD STOP (bar ambiguo)";
                    exit_px = std::max(b.o, s_stop_px);
                }
                else if (b.l <= s_target) { cov = true; why = "target"; exit_px = s_target; }
                else if (S_MODE_TREND && st_trend > 0) { cov = true; why = "supertrend flip UP"; }
                else if (atr > 0 && b.c > s_trough + S_TRAIL * atr && b.c < s_floor) {
                    cov = true; why = "trail ATR roto";
                } else if (S_TSTOP > 0 && b.t - spos_epoch >= S_TSTOP * 60 &&
                           b.c > s_floor) {
                    cov = true; why = "time-stop (no cayo)";
                } else if (H > 15 || (H == 15 && M >= 45)) {
                    if (b.c <= s_floor || EOD_FORCE > 0) { cov = true; why = "EOD cover 15:45"; }
                }
                if (cov) {
                    std::printf("[%02d:%02d] *** DRAM: VENDER PUT *** ~%.2f (%s, entrada %.2f) t=%.0f\n",
                                H, M, exit_px, why, s_entry, b.t);
                    std::fflush(stdout);
                    if (audio_gate(true)) { play("sounds/dram_buy.wav", "Ping"); speak("sell DRAM put now"); }
                    { char m[200]; std::snprintf(m, sizeof(m),
                        "VENDER PUT DRAM @ %.2f | %s | entrada %.2f | mov %+.1f%%",
                        exit_px, why, s_entry, (s_entry / exit_px - 1) * 100);
                      notify(why[0] == 'H' ? "DRAM: PUT-STOP" : "DRAM: SELL PUT", m, true); }
                    in_short = false; g_pos_restored = false;
                    unlink(SPOS_FILE);
                }
            }
            // fill del corto pendiente (cede ante un largo abierto)
            if (pending_short && !in_short && !in_pos) {
                pending_short = false;
                if (rth_entry && (MAX_DAY == 0 || sday_entries < (int)MAX_DAY)) {
                    in_short = true; s_entry = b.o; s_trough = b.l;
                    s_floor = s_entry * (1 - S_FLOOR / 100.0);
                    s_target = s_entry * (1 - S_TARGET / 100.0);
                    spos_epoch = b.t; sday_entries++;
                    save_spos(s_entry, s_trough, s_floor, s_target, spos_epoch);
                    std::printf("[%02d:%02d] *** DRAM: PUT *** ~%.2f (blow-off confirmado; "
                                "target %.2f, floor %.2f) t=%.0f\n", H, M, s_entry, s_target, s_floor, b.t);
                    std::fflush(stdout);
                    if (audio_gate(true)) { play("sounds/dram_sell.wav", "Basso"); speak("buy DRAM put now"); }
                    { char m[200]; std::snprintf(m, sizeof(m),
                        "COMPRAR PUT DRAM @ %.2f | target %.2f | floor %.2f | senal de BAJADA (blow-off)",
                        s_entry, s_target, s_floor);
                      notify("DRAM: BUY PUT", m, true); }
                }
            }
            // señal corta MR: espejo exacto del largo (euforia -> bar rojo que
            // pierde el minimo del bar de euforia con RSI cayendo)
            if (!S_MODE_TREND && ind_ok && !in_pos && !in_short && !pending_short &&
                !pending_buy && rth_entry) {
                bool blow;
                if (S_SCORE_MIN > 0) {
                    double s_z1  = std::min(1.0, std::max(0.0, -bb_z / S_BB_STD));
                    double s_z15 = std::min(1.0, std::max(0.0, -z15 / 2.0));
                    double s_rsi = std::min(1.0, std::max(0.0,
                                        (rsi - (100.0 - S_RSI_OS - 10.0)) / 20.0));
                    double atr_pct = b.c > 0 ? atr / b.c : 0;
                    double s_vw = (vwap > 0 && atr_pct > 1e-6)
                        ? std::min(1.0, std::max(0.0, ((b.c - vwap) / b.c) / (2.0 * atr_pct))) : 0;
                    double s_vol = vol_ma > 0
                        ? std::min(1.0, std::max(0.0, b.v / vol_ma - 0.8)) : 0;
                    double sc = 0.25 * s_z1 + 0.25 * s_z15 + 0.15 * s_rsi
                              + 0.15 * s_vw + 0.15 * s_vol;
                    if (bar_is_live()) sc += 0.05 * whale_score(b.t, -1);
                    blow = sc >= S_SCORE_MIN;
                } else {
                    double bb_up_s = bb_sd > 0 ? bb_mean + S_BB_STD * bb_sd : bb_up;
                    blow = b.c >= bb_up_s && rsi >= 100.0 - S_RSI_OS &&
                           b.v >= vol_ma * S_VOL_MULT;
                }
                if (blow) { armed_s = true; armed_low = b.l; armed_rsi_s = rsi; armed_bar_s = nbars; }
                else if (armed_s && nbars - armed_bar_s <= CONFIRM_WINDOW
                         && b.c < armed_low && b.c < b.o && rsi < armed_rsi_s
                         && (S_CANDLE == 0 || (has_pb && candle_bear(pb, b)))
                         && (CONFIRM_STRICT == 0 ||
                             (b.v >= vol_ma && b.c <= b.h - 0.5 * (b.h - b.l)))) {
                    double sp = (SPREAD_MAX > 0 && bar_is_live()) ? nbbo_spread_pct() : 0;
                    if (!(sp > SPREAD_MAX && SPREAD_MAX > 0)) { pending_short = true; armed_s = false; }
                }
                if (armed_s && nbars - armed_bar_s > CONFIRM_WINDOW) armed_s = false;
            }
        }
        pb = b; has_pb = true;
    }
    if (!use_stdin) pclose(in);
    return 0;
}
