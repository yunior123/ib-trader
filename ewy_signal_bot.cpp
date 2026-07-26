// ewy_signal_bot.cpp — EWY buy/sell signal engine, pure C++
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
// Data: ibkr_bar_bridge (daemon IBKR, fuente unica) streams
//       REAL 1m completed bars as "EPOCH OPEN HIGH LOW CLOSE VOLUME" lines.
//
// build: clang++ -std=c++17 -O2 -o ewy_signal_bot ewy_signal_bot.cpp
// run:   ./ewy_signal_bot            (spawns bridge)
//        ./ewy_signal_bot --stdin    (replay: feed bar lines for testing)

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
// ---- params: por-ticker via env EWY_* (orden Yunior 2026-07-10 "tune per
// ticker") — un solo set de parametros en 4 microestructuras distintas mata
// la expectancy; ahora el keepalive exporta el set ajustado por backtest.
static double envd(const char* k, double d) {
    const char* v = std::getenv(k);
    return (v && *v) ? atof(v) : d;
}
static const int    BB_N = 20;      static const double BB_STD = envd("EWY_BB_STD", 3.0);
static const int    RSI_N = 14;     static const double RSI_OS = envd("EWY_RSI_OS", 25.0);
static const int    VOL_N = 20;     static const double VOL_MULT = envd("EWY_VOL_MULT", 1.2);
static const int    ATR_N = 14;
static const int    CONFIRM_WINDOW = 60;
static const double TARGET_PCT = envd("EWY_TARGET", 4.0),
                    FLOOR_PCT  = envd("EWY_FLOOR", 1.0),
                    TRAIL_ATR  = envd("EWY_TRAIL_ATR", 3.0);
// HARD STOP alert (orden 2026-07-10): a -EWY_STOP% del entry el bot GRITA la
// perdida (SELL-STOP) en vez de callarse a esperar el floor. Humano decide.
static const double STOP_PCT = envd("EWY_STOP", 3.0);
// afinado 2026-07-10 (skills mean-reversion/exit-strategies + estudio 30d):
// SKIP_OPEN: min tras 9:30 sin entradas (los arms del open eran subasta);
// TIME_STOP_MIN: trade que no revirtio en N min = hipotesis muerta -> eject;
// EOD_FORCE: 15:45 plano SIEMPRE (sin bag overnight; para SPCX obligatorio);
// CONFIRM_STRICT: bar de confirmacion con volumen>=volMA y close en mitad alta;
// MAX_DAY: entradas max por dia (0 = sin limite).
static const double SKIP_OPEN      = envd("EWY_SKIP_OPEN", 0);
static const double TIME_STOP_MIN  = envd("EWY_TIME_STOP_MIN", 0);
static const double EOD_FORCE      = envd("EWY_EOD_FORCE", 0);
static const double CONFIRM_STRICT = envd("EWY_CONFIRM_STRICT", 0);
static const double MAX_DAY        = envd("EWY_MAX_DAY", 0);
// ===== MOTOR v3 CONFLUENCE (orden Yunior 2026-07-11: "bollinger 50% en 1m
// y 15m, vwap, rsi, volumen, whales, bids/asks — terremoto sin falsos
// positivos"). SCORE_MIN > 0 activa el arm por confluencia PONDERADA:
//   0.25 BB-1m(z) + 0.25 BB-15m(z) + 0.15 RSI + 0.15 dist-VWAP + 0.15 vol
//   + 0.05 whales (solo live, data/whale_*.txt del daemon)
// SCORE_MIN = 0 (default) -> gate clasico duro, comportamiento previo intacto.
static const double SCORE_MIN  = envd("EWY_SCORE_MIN", 0);
static const double WHALE_USD  = envd("EWY_WHALE_USD", 75000);
// SPREAD_MAX > 0: al confirmar, si el NBBO vivo (data/nbbo_*.txt del daemon)
// muestra spread% mayor, NO se confirma (proteccion live; backtest no afecta).
static const double SPREAD_MAX = envd("EWY_SPREAD_MAX", 0);
// TREND MODE generico (EWY_MODE=trend): flip Supertrend 5m / ruptura max del
// dia con CUSUM >= TREND_CUSUM; TREND_VWAP=1 exige ademas c>VWAP y vol>=volMA.
static const bool TREND_MODE = [] {
    const char* v = std::getenv("EWY_MODE");
    return v && !std::strcmp(v, "trend");
}();
static const double TREND_CUSUM = envd("EWY_TREND_CUSUM", 0.01);
static const double TREND_VWAP  = envd("EWY_TREND_VWAP", 0);
// ===== v4 AMBAS DIRECCIONES (orden Yunior 2026-07-11: señales cuando sube
// Y cuando baja). EWY_SHORTS=1 activa el espejo corto: blow-off arriba de la
// banda + RSI sobrecomprado + volumen, confirmado por bar rojo que pierde el
// minimo del bar de euforia -> "SHORT NOW"; gestion simetrica (target abajo,
// trail sobre el minimo, HARD STOP arriba, EOD cover). En trend mode: flip
// bajista del Supertrend / ruptura del MINIMO del dia con CUSUM negativo.
// El lado largo NO se toca (los cortos ceden ante un largo confirmado:
// cover por reversal). Default 0 -> comportamiento identico byte a byte.
static const double SHORTS = envd("EWY_SHORTS", 0);
// exits propios del corto (los mercados caen distinto a como suben);
// sin definir heredan los del largo
static const double S_TARGET = envd("EWY_S_TARGET", TARGET_PCT);
static const double S_STOP   = envd("EWY_S_STOP", STOP_PCT);
static const double S_TRAIL  = envd("EWY_S_TRAIL", TRAIL_ATR);
static const double S_FLOOR  = envd("EWY_S_FLOOR", FLOOR_PCT);
static const double S_TSTOP  = envd("EWY_S_TSTOP", TIME_STOP_MIN);
// entradas PROPIAS del corto (optimize shorts 2026-07-11): sin definir
// heredan el lado largo. S_MODE fuerza el motor del corto ("mr" o "trend")
// independiente del largo — un ticker trend-largo puede cortear mejor en
// blow-off MR y viceversa.
static const double S_BB_STD    = envd("EWY_S_BB_STD", BB_STD);
static const double S_RSI_OS    = envd("EWY_S_RSI_OS", RSI_OS);
static const double S_VOL_MULT  = envd("EWY_S_VOL_MULT", VOL_MULT);
static const double S_SCORE_MIN = envd("EWY_S_SCORE_MIN", SCORE_MIN);
static const double S_TCUSUM    = envd("EWY_S_TREND_CUSUM", TREND_CUSUM);

// ===== PATRONES DE VELAS (orden Yunior 2026-07-11 "signals have also into
// account candle patterns"; ref TA-Lib CDL*): con {SYM}_CANDLE=1 el bar de
// confirmacion/entrada debe ADEMAS ser patron direccional — engulfing,
// hammer/shooting-star o marubozu. 0 = off (regresion byte-identica). El
// optimizador WFO decide ON/OFF por ticker con datos, no por fe.
static const double CANDLE   = envd("EWY_CANDLE", 0);
static const double S_CANDLE = envd("EWY_S_CANDLE", CANDLE);
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
static const double QUAKE_MIN    = envd("EWY_QUAKE_MIN", 0.02);
static const double QUAKE_BANNER = envd("EWY_QUAKE_BANNER", 0);
static const bool S_MODE_TREND = [] {
    const char* v = std::getenv("EWY_S_MODE");
    if (v && !std::strcmp(v, "trend")) return true;
    if (v && !std::strcmp(v, "mr")) return false;
    const char* m = std::getenv("EWY_MODE");           // hereda el modo largo
    return m && !std::strcmp(m, "trend");
}();
static const char* SPOS_FILE = "data/pos_ewy_s.txt";
static void save_spos(double e, double tr, double fl, double tg, double ep) {
    FILE* f = fopen(SPOS_FILE, "w");
    if (f) { fprintf(f, "%f %f %f %f %f\n", e, tr, fl, tg, ep); fclose(f); }
}
static const char* WHALE_FILE = "data/whale_ewy.txt";
static const char* NBBO_FILE  = "data/nbbo_ewy.txt";

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
static double nbbo_spread_pct() {  // <0 = sin NBBO vivo (fail-closed, nunca 0 disfrazado)
    FILE* f = fopen(NBBO_FILE, "r");
    if (!f) return -1;
    double ep = 0, bid = 0, ask = 0;
    int n = fscanf(f, "%lf %lf %lf", &ep, &bid, &ask);
    fclose(f);
    if (n != 3 || bid <= 0 || ask <= bid) return -1;
    if (time(nullptr) - (time_t)ep > 10) return -1;
    return (ask - bid) / ((ask + bid) / 2) * 100.0;
}
// posicion virtual PERSISTIDA (fix 2026-07-10: un restart perdia la posicion
// y los SELL se desincronizaban de lo que Yunior realmente tiene)
static const char* POS_FILE = "data/pos_ewy.txt";
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
                  ": '%s'; scripts/speak.sh SIGNAL '%s' >/dev/null 2>&1 &",
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
    if (urgent && (bar_is_live() || g_pos_restored)) {
        // banner de warm-up (pos restaurada): tag WARMUP visible en banner y
        // espejo Desktop — el humano compara hora-de-notificacion vs grafico
        // (orden 2026-07-15) y un replay sin tag pareceria un error del bot
        if (bar_is_live()) fleet_notify_urgent(title, msg);
        else {
            char wt[300];
            std::snprintf(wt, sizeof(wt), "WARMUP %s", title);
            fleet_notify_urgent(wt, msg);
        }
    }
    // 3) structured operations log
    FILE* f = std::fopen("ewy_operations.log", "a");
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

// ===== MOTOR v5 — CONFLUENCIA MULTI-TIMEFRAME (orden Yunior 2026-07-15) =====
// "los bots deben usar al menos la barra de 1 min y la de 15 min para
// trabajar con bollinger y ver si revienta la banda... plus macd, plus
// lineas de tendencia, plus breakouts, plus whales... solo buy and sell...
// en los mensajes pon al lado la probabilidad de acierto"
// Capas: BB(20,2) en 1m/5m/15m (banda reventada en >=2 TF = fuerza) +
// MACD(12,26,9) 4-estados en 1m y 15m (CM_MacD_Ult_MTF) + trendlines con
// breaks (LuxAlgo, pivots 14) + ribbon Madrid 15m (EMA5..100) + escenario
// del dia (open-drive/fade, rally, lateral) + VWAP + whales. Señal BUY/SELL
// unica con prob% (logistica calibrada por backtest; EWY_V5_A/B).
// EWY_V5=1 activa; default 0 = byte-identico al motor previo.
static const double V5        = envd("EWY_V5", 0);
static const double V5_MIN    = envd("EWY_V5_MIN", 99.0);   // score minimo (de 8)
static const double V5_A      = envd("EWY_V5_A", -3.2);    // logistica: prob = 1/(1+e^-(A+B*score))
static const double V5_B      = envd("EWY_V5_B", 0.62);
static const double V5_COOL   = envd("EWY_V5_COOL", 1800); // s entre señales mismo lado

struct V5EMA { double v = 0; bool init = false;
    double upd(double x, int n) { double k = 2.0 / (n + 1);
        v = init ? x * k + v * (1 - k) : x; init = true; return v; } };

struct V5MACD {  // CM_MacD_Ult_MTF: EMA12-EMA26, señal SMA9, hist 4 estados
    V5EMA e12, e26; double sig9[9] = {0}; int nsig = 0;
    double macd = 0, sig = 0, hist = 0, hist1 = 0;
    void upd(double c) {
        macd = e12.upd(c, 12) - e26.upd(c, 26);
        sig9[nsig % 9] = macd; nsig++;
        int k = nsig < 9 ? nsig : 9; double s = 0;
        for (int i = 0; i < k; i++) s += sig9[i];
        hist1 = hist; sig = s / k; hist = macd - sig; }
    bool a_up()  const { return hist > hist1 && hist > 0; }   // aqua: impulso arriba
    bool b_up()  const { return hist > hist1 && hist <= 0; }  // maroon: girando desde abajo
    bool a_dn()  const { return hist < hist1 && hist > 0; }   // blue: debilitandose
    bool b_dn()  const { return hist < hist1 && hist <= 0; }  // red: impulso abajo
    bool above() const { return macd >= sig; } };

struct V5BB {   // BB(20,2) incremental sobre un ring de closes
    double ring[20] = {0}; int n = 0;
    double mid = 0, up = 0, dn = 0;
    void upd(double c) { ring[n % 20] = c; n++;
        int k = n < 20 ? n : 20; double s = 0, s2 = 0;
        for (int i = 0; i < k; i++) { s += ring[i]; s2 += ring[i] * ring[i]; }
        mid = s / k; double var = s2 / k - mid * mid;
        double sd = var > 0 ? std::sqrt(var) : 0;
        up = mid + 2 * sd; dn = mid - 2 * sd; }
    bool burst_up(double c) const { return n >= 20 && c > up; }
    bool burst_dn(double c) const { return n >= 20 && c < dn; } };

struct V5TF {   // agregador 5m/15m desde bars de 1m
    int mins; double ep0 = 0, o = 0, h = 0, l = 0, c = 0;
    V5BB bb; V5MACD macd; bool closed = false;
    V5TF(int m) : mins(m) {}
    void upd(const Bar& b) {
        closed = false;
        double bucket = b.t - std::fmod(b.t, mins * 60.0);
        if (bucket != ep0) {
            if (ep0 > 0) { bb.upd(c); macd.upd(c); closed = true; }
            ep0 = bucket; o = b.o; h = b.h; l = b.l; c = b.c;
        } else { if (b.h > h) h = b.h; if (b.l < l) l = b.l; c = b.c; } } };

// trendlines con breaks (LuxAlgo 1:1): pivots lookback 14, pendiente ATR/14,
// upos/dnos = flags de ruptura. Incremental, pivote confirmado 14 bars tarde.
struct V5TL {
    static const int N = 14;
    double hs[2 * N + 1] = {0}, ls[2 * N + 1] = {0}; int nb = 0;
    double atr = 0, prev_c = 0;
    double upper = 0, lower = 0, sph = 0, spl = 0;
    int upos = 0, dnos = 0; bool up_break = false, dn_break = false;
    void upd(const Bar& b) {
        up_break = dn_break = false;
        double tr = b.h - b.l;
        if (prev_c > 0) { double a = std::fabs(b.h - prev_c), c2 = std::fabs(b.l - prev_c);
            if (a > tr) tr = a; if (c2 > tr) tr = c2; }
        prev_c = b.c;
        atr = atr > 0 ? (atr * (N - 1) + tr) / N : tr;
        for (int i = 0; i < 2 * N; i++) { hs[i] = hs[i + 1]; ls[i] = ls[i + 1]; }
        hs[2 * N] = b.h; ls[2 * N] = b.l; nb++;
        if (nb < 2 * N + 1) return;
        double slope = atr / N;                       // tlMult = 1.0
        bool is_ph = true, is_pl = true;              // pivote en el centro (lag N)
        for (int i = 0; i < 2 * N + 1; i++) {
            if (i != N && hs[i] >= hs[N]) is_ph = false;
            if (i != N && ls[i] <= ls[N]) is_pl = false; }
        if (is_ph) { sph = slope; upper = hs[N]; upos = 0; }
        else if (upper > 0) upper -= sph;
        if (is_pl) { spl = slope; lower = ls[N]; dnos = 0; }
        else if (lower > 0) lower += spl;
        // breaks contra la linea proyectada al bar actual (offset N del pivote)
        if (!is_ph && upper > 0 && upos == 0 && b.c > upper - sph * N) { upos = 1; up_break = true; }
        if (!is_pl && lower > 0 && dnos == 0 && b.c < lower + spl * N) { dnos = 1; dn_break = true; } } };

// ribbon Madrid 15m: EMAs 5..100; score = (subiendo&&>ema100) - (bajando&&<ema100), norm -1..1
struct V5Ribbon {
    V5EMA e[20]; double prev[20] = {0}; int lens[20] =
        {5,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100};
    double score = 0;
    void upd(double c) {
        double e100 = e[19].upd(c, 100); int up = 0, dn = 0;
        for (int i = 0; i < 19; i++) {
            double v = e[i].upd(c, lens[i]);
            if (v >= prev[i] && v > e100) up++;
            if (v < prev[i] && v < e100) dn++;
            prev[i] = v; }
        score = (up - dn) / 19.0; } };

static V5TF v5_tf5(5), v5_tf15(15);
static V5BB v5_bb1;
static V5MACD v5_macd1;
static V5TL v5_tl;
static V5Ribbon v5_rib;
static double v5_vwap_pv = 0, v5_vwap_v = 0, v5_day = 0;
static double v5_day_open = 0, v5_or_hi = 0, v5_or_lo = 1e18; // opening range 30m
static double v5_last_buy = 0, v5_last_sell = 0;
static int    v5_bb1_dn_ago = 999, v5_bb1_up_ago = 999;      // bars desde burst 1m
static int    v5_bb5_dn_ago = 999, v5_bb5_up_ago = 999;
static int    v5_bb15_dn_ago = 999, v5_bb15_up_ago = 999;

// contexto de opciones (sidecar scripts/options_context.py, <=20 min de edad):
// "EPOCH iv delta gamma theta oi_call oi_put opt_vol"
static int v5_opt(char* out, size_t n) {
    FILE* f = fopen("data/options_ewy.txt", "r");
    if (!f) { out[0] = 0; return 0; }
    double ep, iv, de, ga, th, oic, oip, ov;
    int k = fscanf(f, "%lf %lf %lf %lf %lf %lf %lf %lf", &ep, &iv, &de, &ga, &th, &oic, &oip, &ov);
    fclose(f);
    if (k < 8 || time(nullptr) - (time_t)ep > 1200) { out[0] = 0; return 0; }
    snprintf(out, n, " | IV %.0f%% D%.2f G%.3f Th%.2f OI %.0fk/%.0fk",
             iv * 100, de, ga, th, oic / 1000, oip / 1000);
    return 1;
}

// clasificador de escenario del dia (los 3 casos de Yunior + tendencia)
static const char* v5_scenario(double c) {
    if (v5_day_open <= 0 || v5_or_hi <= 0) return "?";
    double rng = v5_or_hi - v5_or_lo;
    if (rng <= 0) return "lateral";
    if (c > v5_or_hi) return v5_rib.score > 0.15 ? "tendencia-alcista" : "rompimiento-arriba";
    if (c < v5_or_lo) return v5_rib.score < -0.15 ? "tendencia-bajista" : "rompimiento-abajo";
    if (c > v5_day_open && v5_rib.score < -0.1) return "pullback-en-bajada";
    if (c < v5_day_open && v5_rib.score > 0.1) return "pullback-en-subida";
    return "lateral";
}

// hook por bar de 1m: actualiza todo y dispara BUY/SELL con prob%
static void v5_on_bar(const Bar& b, bool alert_hours, int H, int M) {
    // dia nuevo -> reset VWAP/opening-range
    double day = b.t - std::fmod(b.t, 86400.0);
    if (day != v5_day) { v5_day = day; v5_vwap_pv = v5_vwap_v = 0;
        v5_day_open = b.o; v5_or_hi = 0; v5_or_lo = 1e18; }
    double tp = (b.h + b.l + b.c) / 3;
    v5_vwap_pv += tp * b.v; v5_vwap_v += b.v;
    double vwap = v5_vwap_v > 0 ? v5_vwap_pv / v5_vwap_v : b.c;
    int hm = H * 100 + M;
    if (hm >= 930 && hm < 1000) { if (b.h > v5_or_hi) v5_or_hi = b.h;
        if (b.l < v5_or_lo) v5_or_lo = b.l; }
    v5_bb1.upd(b.c); v5_macd1.upd(b.c);
    v5_tf5.upd(b); v5_tf15.upd(b);
    if (v5_tf15.closed) v5_rib.upd(v5_tf15.c);
    v5_tl.upd(b);
    v5_bb1_dn_ago  = v5_bb1.burst_dn(b.c) ? 0 : v5_bb1_dn_ago + 1;
    v5_bb1_up_ago  = v5_bb1.burst_up(b.c) ? 0 : v5_bb1_up_ago + 1;
    if (v5_tf5.closed)  { v5_bb5_dn_ago  = v5_tf5.bb.burst_dn(v5_tf5.c)  ? 0 : v5_bb5_dn_ago + 1;
                          v5_bb5_up_ago  = v5_tf5.bb.burst_up(v5_tf5.c)  ? 0 : v5_bb5_up_ago + 1; }
    if (v5_tf15.closed) { v5_bb15_dn_ago = v5_tf15.bb.burst_dn(v5_tf15.c) ? 0 : v5_bb15_dn_ago + 1;
                          v5_bb15_up_ago = v5_tf15.bb.burst_up(v5_tf15.c) ? 0 : v5_bb15_up_ago + 1; }
    if (V5 <= 0 || !alert_hours || v5_tf15.macd.nsig < 9) return;

    // ---- confluencia BUY (pullback/reversion al alza o breakout con tendencia)
    // banda inferior reventada en >=2 TF hace poco + bar verde = capitulacion multi-TF
    int bb_dn_tfs = (v5_bb1_dn_ago <= 3) + (v5_bb5_dn_ago <= 2) + (v5_bb15_dn_ago <= 1);
    int bb_up_tfs = (v5_bb1_up_ago <= 3) + (v5_bb5_up_ago <= 2) + (v5_bb15_up_ago <= 1);
    double now_w = (double)time(nullptr);
    double wh_buy = whale_score(now_w, 1), wh_sell = whale_score(now_w, -1);
    const char* sc = v5_scenario(b.c);
    double sbuy = 0; char rb[240] = ""; size_t lb = 0;
    auto add = [](char* r, size_t& l, const char* s) {
        size_t n = strlen(s); if (l + n + 2 < 238) { if (l) { r[l++] = '+'; } memcpy(r + l, s, n); l += n; r[l] = 0; } };
    if (bb_dn_tfs >= 2 && b.c > b.o)            { sbuy += 2; add(rb, lb, bb_dn_tfs >= 3 ? "BB-3TF-abajo" : "BB-2TF-abajo"); }
    if (v5_macd1.b_up())                         { sbuy += 1; add(rb, lb, "MACD1-girando"); }
    if (v5_tf15.macd.above() || v5_tf15.macd.b_up()) { sbuy += 1; add(rb, lb, "MACD15-alcista"); }
    if (v5_tl.up_break)                          { sbuy += 1.5; add(rb, lb, "rompe-trendline"); }
    if (v5_rib.score > 0.2)                      { sbuy += 1; add(rb, lb, "ribbon15-alcista"); }
    if (b.c > vwap)                              { sbuy += 0.5; add(rb, lb, "sobre-VWAP"); }
    if (wh_buy > 0.3)                            { sbuy += 1; add(rb, lb, "whales-comprando"); }
    if (!strcmp(sc, "pullback-en-subida") || !strcmp(sc, "tendencia-alcista")) { sbuy += 0.5; add(rb, lb, sc); }
    double ssell = 0; char rs[240] = ""; size_t ls2 = 0;
    if (bb_up_tfs >= 2 && b.c < b.o)             { ssell += 2; add(rs, ls2, bb_up_tfs >= 3 ? "BB-3TF-arriba" : "BB-2TF-arriba"); }
    if (v5_macd1.a_dn() || v5_macd1.b_dn())      { ssell += 1; add(rs, ls2, "MACD1-cayendo"); }
    if (!v5_tf15.macd.above() || v5_tf15.macd.a_dn()) { ssell += 1; add(rs, ls2, "MACD15-bajista"); }
    if (v5_tl.dn_break)                          { ssell += 1.5; add(rs, ls2, "rompe-trendline-abajo"); }
    if (v5_rib.score < -0.2)                     { ssell += 1; add(rs, ls2, "ribbon15-bajista"); }
    if (b.c < vwap)                              { ssell += 0.5; add(rs, ls2, "bajo-VWAP"); }
    if (wh_sell > 0.3)                           { ssell += 1; add(rs, ls2, "whales-vendiendo"); }
    if (!strcmp(sc, "pullback-en-bajada") || !strcmp(sc, "tendencia-bajista")) { ssell += 0.5; add(rs, ls2, sc); }

    char opt[96];
    if (sbuy >= V5_MIN && b.t - v5_last_buy >= V5_COOL && sbuy > ssell) {
        v5_last_buy = b.t;
        double p = 100.0 / (1.0 + std::exp(-(V5_A + V5_B * sbuy)));
        v5_opt(opt, sizeof(opt));
        char m[420];
        std::snprintf(m, sizeof(m), "EWY @ %.2f | prob %.0f%% | %s | %s%s",
                      b.c, p, rb, sc, opt);
        std::printf("[%02d:%02d] *** EWY V5 BUY *** score %.1f prob %.0f%% %s t=%.0f\n",
                    H, M, sbuy, p, rb, b.t);
        std::fflush(stdout);
        notify("EWY: BUY", m, true);
        if (audio_gate(true)) { play("sounds/dram_buy.wav", "Glass"); speak("buy S M H now"); }
    }
    if (ssell >= V5_MIN && b.t - v5_last_sell >= V5_COOL && ssell > sbuy) {
        v5_last_sell = b.t;
        double p = 100.0 / (1.0 + std::exp(-(V5_A + V5_B * ssell)));
        v5_opt(opt, sizeof(opt));
        char m[420];
        std::snprintf(m, sizeof(m), "EWY @ %.2f | prob %.0f%% | %s | %s%s",
                      b.c, p, rs, sc, opt);
        std::printf("[%02d:%02d] *** EWY V5 SELL *** score %.1f prob %.0f%% %s t=%.0f\n",
                    H, M, ssell, p, rs, b.t);
        std::fflush(stdout);
        notify("EWY: SELL", m, true);
        if (audio_gate(true)) { play("sounds/dram_sell.wav", "Basso"); speak("sell S M H now"); }
    }
}
// ===== FIN MOTOR v5 =====

// ==================== MOTOR v6 MTF (2026-07-16) ====================
// v6 EXTIENDE al bloque v5 (no lo reemplaza): lee v5_tf5/v5_tf15/v5_macd1/
// v5_tl/v5_rib/v5_vwap_pv/v5_vwap_v/v5_bbN_*_ago ya calculados arriba.
// SEÑAL-SOLAMENTE (ley Yunior 2026-07-16): cero ordenes, cero sockets.
// Añade: fase de sesion (dip&rip / spike&fade / tendencia / lateral),
// pullback-vs-reversal (Fib+Dow+MACD15+BB15mid), ADX15 de regimen,
// BB %B + squeeze (bandwidth percentil), Supertrend 5m, trendlines 15m,
// clases de señal cerradas con prob% calibrada (data/prob_table_ewy.txt,
// shrinkage k=20 hacia prior; fallback prior si no hay tabla).
// Anti-lookahead: TODO decide con el bar 1m CERRADO. Determinista en replay
// (cooldowns/reloj con b.t, whales solo live). O(1)/bar, cero heap.
// v6.1 (2026-07-16 noche): RETEST-CONFIRM anti-trampa en las clases de
// ruptura (TLINE_BREAK_*, ORB_*, SQUEEZE_BREAK_*, VWAP_LOSS_*) — la ruptura
// ARMA la señal; solo dispara con pullback+rechazo del nivel roto (tag
// retest-ok) o 3 cierres sosteniendo sin retest (tag breakaway). Pullback
// que atraviesa el nivel = TRAMPA-EVITADA (cancelada + log). EWY_V6_RETEST=0
// restaura el disparo inmediato v6.0.
#include <sys/stat.h>
#include <algorithm>

static const double V6_ON       = envd("EWY_V6", 1);           // 1 = activo
static const double V6_MIN      = envd("EWY_V6_MIN", 6.0);     // score minimo (de 10)
static const double V6_COOL     = envd("EWY_V6_COOL", 1800);   // s entre señales mismo lado
static const double V6_PROB_MIN = envd("EWY_V6_PROB_MIN", 55.0);
static const double V6_MAX_CLASS_DAY = envd("EWY_V6_MAX_CLASS_DAY", 2);
static const double V6_RVOL     = envd("EWY_V6_RVOL", 1.5);
static const double V6_RVOL_RECLAIM = envd("EWY_V6_RVOL_RECLAIM", 2.0);
static const double V6_RETR_CONT = envd("EWY_V6_RETR_CONT", 0.50);
static const double V6_RETR_REV  = envd("EWY_V6_RETR_REV", 0.62);
static const double V6_SQUEEZE_PCT = envd("EWY_V6_SQUEEZE_PCT", 10.0);
static const double V6_ADX_TREND = envd("EWY_V6_ADX_TREND", 25.0);
static const double V6_ADX_RANGE = envd("EWY_V6_ADX_RANGE", 20.0);
static const double V6_OR_LATERAL = envd("EWY_V6_OR_LATERAL", 1.2);
static const double V6_GAP_BREAKAWAY = envd("EWY_V6_GAP_BREAKAWAY", 1.0);
static const double V6_KRX      = envd("EWY_KRX", 0);          // 1 = sesion KST (open min 540)
static const double V6_DEBUG    = envd("EWY_V6_DEBUG", 0);
static const double V6_RETEST   = envd("EWY_V6_RETEST", 1);    // v6.1: 1 = retest-confirm en rupturas
static const double V6_RETEST_MAX = envd("EWY_V6_RETEST_MAX", 20); // bars 1m armada antes de expirar

// ---- ATR Wilder generico (periodo configurable, default 14) ----
struct V6ATR {
    double atr = 0, prev_c = 0; int n = 0, period = 14;
    void add(double h, double l, double c) {
        double tr = h - l;
        if (n > 0) { double a = std::fabs(h - prev_c), d = std::fabs(l - prev_c);
            if (a > tr) tr = a; if (d > tr) tr = d; }
        atr = (n < period) ? (atr * n + tr) / (n + 1) : (atr * (period - 1) + tr) / period;
        prev_c = c; n++; } };

// ---- ADX(14) Wilder — alimentado con bars 15m CERRADOS ----
struct V6ADX {
    double spdm = 0, sndm = 0, str = 0, adx = 0, dx_acc = 0;
    double prev_h = 0, prev_l = 0, prev_c = 0; int n = 0, ndx = 0;
    void add(double h, double l, double c) {
        if (n > 0) {
            double up = h - prev_h, dn = prev_l - l;
            double pdm = (up > dn && up > 0) ? up : 0;
            double ndm = (dn > up && dn > 0) ? dn : 0;
            double tr = h - l;
            { double a = std::fabs(h - prev_c), d = std::fabs(l - prev_c);
              if (a > tr) tr = a; if (d > tr) tr = d; }
            if (n <= 14) { spdm += pdm; sndm += ndm; str += tr; }
            else { spdm += pdm - spdm / 14; sndm += ndm - sndm / 14; str += tr - str / 14; }
            if (n >= 14 && str > 1e-12) {
                double dip = 100 * spdm / str, din = 100 * sndm / str;
                double dx = (dip + din > 1e-12) ? 100 * std::fabs(dip - din) / (dip + din) : 0;
                if (ndx < 14) { dx_acc += dx; ndx++; adx = dx_acc / ndx; }
                else adx = (adx * 13 + dx) / 14; } }
        prev_h = h; prev_l = l; prev_c = c; n++; }
    bool trending() const { return n >= 28 && adx > V6_ADX_TREND; }
    bool ranging()  const { return n >= 28 && adx < V6_ADX_RANGE; } };
    // 20-25 = zona muerta: ni breakout ni reversion de origen BB

// ---- BB(20,2) extendida: %B + BandWidth + percentil de bandwidth (ring 125) ----
struct V6BBX {
    double ring[20] = {0}; int n = 0;
    double mid = 0, up = 0, dn = 0;
    double bwr[125] = {0}; int bn = 0, bi = 0;
    void add(double c) {
        ring[n % 20] = c; n++;
        int k = n < 20 ? n : 20; double s = 0, s2 = 0;
        for (int i = 0; i < k; i++) { s += ring[i]; s2 += ring[i] * ring[i]; }
        mid = s / k; double var = s2 / k - mid * mid;
        double sd = var > 0 ? std::sqrt(var) : 0;
        up = mid + 2 * sd; dn = mid - 2 * sd;
        if (n >= 20 && mid > 0) { bwr[bi] = (up - dn) / mid; bi = (bi + 1) % 125;
            if (bn < 125) bn++; } }
    double pctB(double c) const { return (up > dn) ? (c - dn) / (up - dn) : 0.5; }
    double bandwidth() const { return mid > 0 ? (up - dn) / mid : 0; }
    double bw_pctile() const {                    // % de valores del ring <= bw actual
        if (!bn) return 100.0;
        double cur = bandwidth(); int le = 0;
        for (int i = 0; i < bn; i++) if (bwr[i] <= cur) le++;
        return 100.0 * le / bn; }
    bool squeeze() const { return bn >= 100 && bw_pctile() <= V6_SQUEEZE_PCT; } };

// ---- Supertrend(10, 3xATR) sobre bars 5m cerrados — filtro de regimen ----
struct V6ST {
    V6ATR atr; double st_up = 0, st_dn = 0, prev_c = 0;
    int dir = 0; bool flip_up = false, flip_dn = false;
    V6ST() { atr.period = 10; }
    void add(double h, double l, double c) {
        flip_up = flip_dn = false;
        atr.add(h, l, c);
        if (atr.n <= 10) { prev_c = c; return; }
        double mid = (h + l) / 2;
        double bu = mid + 3.0 * atr.atr, bl = mid - 3.0 * atr.atr;
        st_up = (st_up == 0 || bu < st_up || prev_c > st_up) ? bu : st_up;
        st_dn = (st_dn == 0 || bl > st_dn || prev_c < st_dn) ? bl : st_dn;
        int nd = (dir >= 0) ? (c < st_dn ? -1 : 1) : (c > st_up ? 1 : -1);
        if (dir != 0 && nd != dir) {
            if (nd > 0) flip_up = true; else flip_dn = true;
            st_up = bu; st_dn = bl; }                 // reset bandas en flip
        dir = nd; prev_c = c; } };

// ---- RSI(14) Wilder 1m propio (el del motor clasico es local al main) ----
struct V6RSI {
    double ag = 0, al = 0, prev = 0, rsi = 50, rsi1 = 50; long n = 0;
    void add(double c) {
        if (n > 0) {
            double d = c - prev, g = d > 0 ? d : 0, L = d < 0 ? -d : 0;
            ag = n <= 14 ? (ag * (n - 1) + g) / n : ag + (g - ag) / 14;
            al = n <= 14 ? (al * (n - 1) + L) / n : al + (L - al) / 14;
            rsi1 = rsi; rsi = al > 1e-12 ? 100.0 - 100.0 / (1.0 + ag / al) : 50.0; }
        prev = c; n++; }
    bool rising()  const { return rsi > rsi1; }
    bool falling() const { return rsi < rsi1; } };

// ---- swings 1m: pivots fractal N=8, confirmados con lag 8 (anti-repaint) ----
struct V6Swing {
    static const int P = 8;
    double hbuf[2 * P + 1] = {0}, lbuf[2 * P + 1] = {0}; long n = 0;
    double swing_hi = 0, swing_lo = 0, last_confirmed_low = 0, last_confirmed_high = 0;
    void add(double h, double l) {
        for (int i = 0; i < 2 * P; i++) { hbuf[i] = hbuf[i + 1]; lbuf[i] = lbuf[i + 1]; }
        hbuf[2 * P] = h; lbuf[2 * P] = l; n++;
        if (n < 2 * P + 1) return;
        bool ph = true, pl = true;
        for (int i = 0; i < 2 * P + 1; i++) {
            if (i != P && hbuf[i] >= hbuf[P]) ph = false;
            if (i != P && lbuf[i] <= lbuf[P]) pl = false; }
        if (ph) { swing_hi = hbuf[P]; last_confirmed_high = hbuf[P]; }
        if (pl) { swing_lo = lbuf[P]; last_confirmed_low  = lbuf[P]; } }
    double retr_dn(double c) const {              // retroceso desde swing_hi (para longs)
        return (swing_hi > swing_lo && swing_lo > 0) ? (swing_hi - c) / (swing_hi - swing_lo) : 0; }
    double retr_up(double c) const {
        return (swing_hi > swing_lo && swing_lo > 0) ? (c - swing_lo) / (swing_hi - swing_lo) : 0; }
    bool broke_last_low(double c)  const { return last_confirmed_low  > 0 && c < last_confirmed_low; }
    bool broke_last_high(double c) const { return last_confirmed_high > 0 && c > last_confirmed_high; } };

// ---- trendlines 15m (LuxAlgo como V5TL pero pivots N=10, slope ATR14/14) ----
// V5TL tiene N=14 fijo; copia con pivote mas corto para el TF lento.
struct V6TL {
    static const int P = 10;
    double hs[2 * P + 1] = {0}, ls[2 * P + 1] = {0}; long nb = 0, natr = 0;
    double atr = 0, prev_c = 0;
    double upper = 0, lower = 0, sph = 0, spl = 0;
    int upos = 0, dnos = 0; bool up_break = false, dn_break = false;
    void add(double h, double l, double c) {
        up_break = dn_break = false;
        double tr = h - l;
        if (prev_c > 0) { double a = std::fabs(h - prev_c), d = std::fabs(l - prev_c);
            if (a > tr) tr = a; if (d > tr) tr = d; }
        prev_c = c; natr++;
        atr = natr <= 14 ? (atr * (natr - 1) + tr) / natr : atr + (tr - atr) / 14.0;
        for (int i = 0; i < 2 * P; i++) { hs[i] = hs[i + 1]; ls[i] = ls[i + 1]; }
        hs[2 * P] = h; ls[2 * P] = l; nb++;
        if (nb < 2 * P + 1) return;
        double slope = atr / 14.0;                // spec: ATR14_15m / 14
        bool ph = true, pl = true;
        for (int i = 0; i < 2 * P + 1; i++) {
            if (i != P && hs[i] >= hs[P]) ph = false;
            if (i != P && ls[i] <= ls[P]) pl = false; }
        if (ph) { sph = slope; upper = hs[P]; upos = 0; } else if (upper > 0) upper -= sph;
        if (pl) { spl = slope; lower = ls[P]; dnos = 0; } else if (lower > 0) lower += spl;
        if (!ph && upper > 0 && upos == 0 && c > upper - sph * P) { upos = 1; up_break = true; }
        if (!pl && lower > 0 && dnos == 0 && c < lower + spl * P) { dnos = 1; dn_break = true; } }
    // linea bajista 15m intacta a < dist del precio: bloquea TLINE_BREAK long 1m
    bool bear_line_near(double c, double dist) const {
        if (upos != 0 || upper <= 0) return false;
        double proj = upper - sph * P;
        return proj > c && proj - c < dist; }
    bool bull_line_near(double c, double dist) const {
        if (dnos != 0 || lower <= 0) return false;
        double proj = lower + spl * P;
        return proj < c && c - proj < dist; } };

// ---- agregador 5m/15m propio: conserva el OHLC COMPLETO del bar cerrado
// (V5TF pisa o/h/l al abrir el bucket nuevo; ATR/ADX/ST necesitan h/l cerrados)
struct V6TFA {
    int mins; double ep0 = 0, o = 0, h = 0, l = 0, c = 0;
    double co = 0, ch = 0, cl = 0, cc = 0; bool closed = false;
    V6TFA(int m) : mins(m) {}
    void upd(const Bar& b) {
        closed = false;
        double bucket = b.t - std::fmod(b.t, mins * 60.0);
        if (bucket != ep0) {
            if (ep0 > 0) { co = o; ch = h; cl = l; cc = c; closed = true; }
            ep0 = bucket; o = b.o; h = b.h; l = b.l; c = b.c;
        } else { if (b.h > h) h = b.h; if (b.l < l) l = b.l; c = b.c; } } };

// ---- clasificador de fase de la sesion (10:00, re-eval 10:30, luego congelada) ----
struct V6Session {
    enum Phase { UNKNOWN = 0, SPIKE_FADE, DIP_CLIMB, TREND_UP, TREND_DOWN, LATERAL };
    Phase phase = UNKNOWN;
    double prev_rth_close = 0, open930 = 0, hi_0945 = 0, lo_0945 = 1e18;
    int bars_above = 0, bars_below = 0, bars_total = 0;   // solo primeros 60 min
    bool dipped = false, reclaimed = false; double reclaim_vr = 0;
    int below_streak = 0, max_below_streak45 = 0;
    double vwap_at_1000 = 0;
    bool no_fade = false; int gap_dir = 0; double gap_ratio = 0;  // gap context (OPEN-1)
    void roll(double last_rth_close) {                    // 15:59 -> reset del dia
        prev_rth_close = last_rth_close; phase = UNKNOWN;
        open930 = 0; hi_0945 = 0; lo_0945 = 1e18;
        bars_above = bars_below = bars_total = 0;
        dipped = reclaimed = false; reclaim_vr = 0;
        below_streak = max_below_streak45 = 0;
        vwap_at_1000 = 0; no_fade = false; gap_dir = 0; gap_ratio = 0; }
    void on_open(double o, double atr15_prev) {
        open930 = o;
        if (prev_rth_close > 0 && atr15_prev > 0) {
            double gap = o - prev_rth_close;
            gap_dir = gap > 0 ? 1 : (gap < 0 ? -1 : 0);
            gap_ratio = std::fabs(gap) / atr15_prev;
            no_fade = gap_ratio > V6_GAP_BREAKAWAY; } }   // gaps >1xATR: no fade contra
    void on_bar(int mso, double c, double v, double vwap, double volma) {
        if (mso < 15) { if (c > hi_0945 || hi_0945 == 0) hi_0945 = c;
            if (c < lo_0945) lo_0945 = c; }
        bars_total++;
        if (c > vwap) { bars_above++; below_streak = 0; }
        else { bars_below++; below_streak++;
            if (mso < 45 && below_streak > max_below_streak45)
                max_below_streak45 = below_streak; }
        if (mso >= 5 && mso <= 45 && c < vwap) dipped = true;
        if (dipped && !reclaimed && c > vwap) {           // reclaim del VWAP tras el dip
            reclaimed = true;
            reclaim_vr = volma > 0 ? v / volma : 0; } }
    void classify(double c, double vwap, double atr15, double or_hi, double or_lo,
                  bool adx_trend) {
        if (atr15 <= 0 || prev_rth_close <= 0) { phase = UNKNOWN; return; }
        // 1) DIP_CLIMB (dip-and-rip, OPEN-6)
        if (open930 > prev_rth_close && dipped && reclaimed && reclaim_vr >= 2.0) {
            phase = DIP_CLIMB; return; }
        // 2) SPIKE_FADE (OPEN-7): spike inicial y >=3 cierres bajo VWAP sin reclaim
        if (hi_0945 > open930 + 0.5 * atr15 && max_below_streak45 >= 3 && !reclaimed) {
            phase = SPIKE_FADE; return; }
        // 3) TREND_UP / TREND_DOWN (OPEN-8): >=80% del mismo lado del VWAP
        if (bars_total > 0) {
            double fa = (double)bars_above / bars_total, fb = (double)bars_below / bars_total;
            if (fa >= 0.8 && c - vwap > 0.5 * atr15) { phase = TREND_UP; return; }
            if (fb >= 0.8 && vwap - c > 0.5 * atr15) { phase = TREND_DOWN; return; } }
        // 4) LATERAL: OR estrecho + VWAP plano + ADX no trending
        if (or_hi > or_lo && or_hi - or_lo <= V6_OR_LATERAL * atr15 &&
            std::fabs(vwap - vwap_at_1000) < 0.25 * atr15 && !adx_trend) {
            phase = LATERAL; return; }
        phase = UNKNOWN; } };

// ---- clases de señal (enum CERRADO — contrato con M3/M4; nombres exactos) ----
enum V6Class { TREND_PULLBACK_LONG, TREND_PULLBACK_SHORT,
               VWAP_RECLAIM_LONG,  VWAP_LOSS_SHORT,
               SQUEEZE_BREAK_LONG, SQUEEZE_BREAK_SHORT,
               ORB_LONG,           ORB_SHORT,
               MTF_BB_REV_LONG,    MTF_BB_REV_SHORT,
               TLINE_BREAK_LONG,   TLINE_BREAK_SHORT,
               TREND_REVERSAL_LONG, TREND_REVERSAL_SHORT, V6_N_CLASSES };
static const char* V6_CLS[V6_N_CLASSES] = {
    "TREND_PULLBACK_LONG", "TREND_PULLBACK_SHORT",
    "VWAP_RECLAIM_LONG",  "VWAP_LOSS_SHORT",
    "SQUEEZE_BREAK_LONG", "SQUEEZE_BREAK_SHORT",
    "ORB_LONG",           "ORB_SHORT",
    "MTF_BB_REV_LONG",    "MTF_BB_REV_SHORT",
    "TLINE_BREAK_LONG",   "TLINE_BREAK_SHORT",
    "TREND_REVERSAL_LONG", "TREND_REVERSAL_SHORT" };
// priors conservadores (fallback sin tabla; base research V6_SPEC §2.9)
static const double V6_PRIOR[V6_N_CLASSES] =
    { 62, 62, 60, 60, 56, 56, 53, 53, 55, 55, 55, 55, 55, 55 };
static const char* V6_PHASE_NAME[6] =
    { "UNKNOWN", "SPIKE_FADE", "DIP_CLIMB", "TREND_UP", "TREND_DOWN", "LATERAL" };

// v6.1: clases EXENTAS del retest-confirm — disparan INMEDIATO como v6.0.
// Default VWAP_LOSS_SHORT (decision Yunior 2026-07-16 noche; backtest 30d:
// 62.3%->43.8% CON retest — es momentum ya confirmado por diseño (3er cierre
// bajo VWAP), exigirle retest retrasa la entrada al punto muerto).
// Override CSV: export EWY_V6_RETEST_EXEMPT="VWAP_LOSS_SHORT,ORB_SHORT"
// ("" = ninguna exenta; nombres EXACTOS del enum).
static bool v6_retest_exempt[V6_N_CLASSES] = {false};
static const bool v6_retest_exempt_init = []() {
    const char* v = std::getenv("EWY_V6_RETEST_EXEMPT");
    const char* csv = v ? v : "VWAP_LOSS_SHORT";
    for (int i = 0; i < V6_N_CLASSES; i++)
        v6_retest_exempt[i] = strstr(csv, V6_CLS[i]) != nullptr;
    return true; }();

// ---- tabla de probabilidades por clase (calibrada por v6_backtest.py) ----
// formato: "CLASE n wins wr_pct" por linea; '#'=comentario; #FAIL_OOS se ignora.
// prob final = shrinkage bayesiano k=20 hacia el prior (evita WR=100% con n=3).
struct V6Prob {
    struct Row { char cls[40]; int n; int w; };
    Row rows[40]; int nrows = 0;
    double last_check = 0; time_t last_mtime = 0;
    void maybe_reload(const char* path, double now) {     // stat cada 3600s (reloj = bar)
        if (last_check > 0 && now - last_check < 3600) return;
        last_check = now;
        struct stat st;
        if (stat(path, &st) != 0) { nrows = 0; last_mtime = 0; return; }
        if (st.st_mtime == last_mtime) return;
        last_mtime = st.st_mtime; nrows = 0;
        FILE* f = fopen(path, "r");
        if (!f) return;
        char line[200];
        while (fgets(line, sizeof(line), f) && nrows < 40) {
            if (line[0] == '#') continue;
            if (strstr(line, "#FAIL_OOS")) continue;      // clase reprobada OOS -> prior
            Row r; double wr = 0;
            if (sscanf(line, "%39s %d %d %lf", r.cls, &r.n, &r.w, &wr) >= 3 && r.n > 0)
                rows[nrows++] = r; }
        fclose(f); }
    double prob(const char* cls, double prior) const {
        for (int i = 0; i < nrows; i++)
            if (!strcmp(rows[i].cls, cls))
                return 100.0 * ((rows[i].w + (prior / 100.0) * 20.0) / (rows[i].n + 20.0));
        return prior; } };

// ---- estado global v6 ----
static V6ATR   v6_atr1;                 // ATR14 1m propio (cero acoplamiento al clasico)
static V6ATR   v6_atr15;                // ATR14 sobre bars 15m cerrados
static V6ADX   v6_adx15;
static V6BBX   v6_bb5, v6_bb15;
static V6ST    v6_st5;
static V6RSI   v6_rsi1;
static V6Swing v6_sw;
static V6TL    v6_tl15;
static V6TFA   v6_a5(5), v6_a15(15);
static V6Session v6_sess;
static V6Prob  v6_prob;
static double  v6_day = 0, v6_last_rth_close = 0, v6_atr15_prev = 0;
static double  v6_or_hi = 0, v6_or_lo = 1e18;            // OR 30m propio (offset de sesion, vale KRX)
static double  v6_volring[20] = {0}; static long v6_voln = 0;
static double  v6_lows[10] = {0}, v6_highs[10] = {0};    // extremos recientes (hold del pullback)
static double  v6_prev_high = 0, v6_prev_low = 0, v6_prev_c = 0, v6_prev_vwap = 0;
static int     v6_m1_prev = 0, v6_m15_prev = 0;          // estados MACD 4-color previos
static int     v6_m15_flipup_ago = 999, v6_m15_flipdn_ago = 999;   // bars 15m desde flip
static int     v6_tl15_upbrk_ago = 999, v6_tl15_dnbrk_ago = 999;   // bars 15m desde break
static int     v6_squeeze_ago = 999;                     // bars 15m desde squeeze activo
static bool    v6_sq_up_done = false, v6_sq_dn_done = false;       // latch 1er cierre fuera
static bool    v6_bwalk_up[10] = {false}, v6_bwalk_dn[10] = {false}; static long v6_bw_i = 0;
static int     v6_tlong_ago = 999, v6_tshort_ago = 999;  // mins desde tendencia activa
static int     v6_below_run = 0;                         // cierres 1m consecutivos < VWAP
static double  v6_last_fire_buy = 0, v6_last_fire_sell = 0;
static int     v6_fires_today[V6_N_CLASSES] = {0};

// ---- v6.1 RETEST-CONFIRM (anti-trampa, regla 2 del PLAYBOOK 2026-07-16:
// "nunca comprar la ruptura en el 1er toque del muro — esperar
// retest-y-rechazo"). La ruptura NO dispara: queda ARMADA y confirma con
//   (a) pullback al nivel roto (retrace 30-70% del impulso o toque ±0.25*ATR)
//   (b) + vela 1m de RECHAZO que cierra en la direccion de la ruptura
//   (c) o breakaway: 3 cierres 1m consecutivos sosteniendo sin retest.
// Pullback que ATRAVIESA el nivel (cierre en contra >50% del impulso pasado
// el nivel) = trampa de ballena: señal CANCELADA + "TRAMPA-EVITADA" al log.
struct V6Armed {
    int cls = -1; bool isbuy = false;
    double level = 0, ext = 0, score = 0, prob = 0, t0 = 0;
    int bars = 0, hold = 0; bool pulled = false;
    char r[240] = "";
    void clear() { cls = -1; pulled = false; bars = hold = 0; } };
static V6Armed v6_arm_b, v6_arm_s;
static double  v6_retest_block_b = 0, v6_retest_block_s = 0;   // anti-rearme tras trampa

static bool v6_is_breakout_cls(int c) {
    return c == TLINE_BREAK_LONG || c == TLINE_BREAK_SHORT ||
           c == ORB_LONG || c == ORB_SHORT ||
           c == SQUEEZE_BREAK_LONG || c == SQUEEZE_BREAK_SHORT ||
           c == VWAP_LOSS_SHORT; }

// nivel roto por clase (congelado al armar; el retest 1m dura ~minutos)
static double v6_break_level(int cls, double vwap, double bc) {
    switch (cls) {
        case ORB_LONG:            return v6_or_hi > 0 ? v6_or_hi : bc;
        case ORB_SHORT:           return v6_or_lo < 1e17 ? v6_or_lo : bc;
        case SQUEEZE_BREAK_LONG:  return v6_bb15.up > 0 ? v6_bb15.up : bc;
        case SQUEEZE_BREAK_SHORT: return v6_bb15.dn > 0 ? v6_bb15.dn : bc;
        case TLINE_BREAK_LONG: {  // proyeccion de la linea bajista 1m al bar del break
            double p = v5_tl.upper - v5_tl.sph * 14;
            return (p > 0 && p < bc) ? p : bc; }
        case TLINE_BREAK_SHORT: {
            double p = v5_tl.lower + v5_tl.spl * 14;
            return (p > bc) ? p : bc; }
        case VWAP_LOSS_SHORT:     return vwap;
        default:                  return bc; } }

// emision unica (usada por disparo inmediato y por confirmacion de retest)
static void v6_emit(bool isbuy, int cls, double prob, double score, const char* r,
                    const Bar& b, int H, int M, int ph) {
    if (isbuy) v6_last_fire_buy = b.t; else v6_last_fire_sell = b.t;
    v6_fires_today[cls]++;
    std::printf("[%02d:%02d] *** EWY V6 %s *** prob %.0f%% clase %s score %.1f %s t=%.0f\n",
                H, M, isbuy ? "BUY" : "SELL", prob, V6_CLS[cls], score, r, b.t);
    std::fflush(stdout);
    char m[420];
    std::snprintf(m, sizeof(m), "EWY @ %.2f | prob %.0f%% | %s | fase=%s",
                  b.c, prob, r, V6_PHASE_NAME[ph]);
    notify(isbuy ? "EWY: BUY" : "EWY: SELL", m, true);
    // INSTRUMENTACION 2026-07-25: en TODO el historial hay 0 voces con la firma
    // "probability" pese a 616 disparos V6 en los logs -> el speak() de V6 nunca
    // suena, mientras el del camino clasico si. speak.sh probado a mano con la
    // frase exacta: funciona. Dejamos rastro para cazarlo en vivo.
    std::fprintf(stderr, "[v6] emit gate: bar_live=%d audio_gate=%d\n",
                 (int)bar_is_live(), (int)audio_gate(false));
    if (audio_gate(true)) {
        if (isbuy) { play("sounds/dram_buy.wav", "Glass");
            char sp[120]; std::snprintf(sp, sizeof(sp),
                "buy S M H now, probability %.0f percent", prob); speak(sp); }
        else { play("sounds/dram_sell.wav", "Basso");
            char sp[120]; std::snprintf(sp, sizeof(sp),
                "sell S M H now, probability %.0f percent", prob); speak(sp); } } }

// razones: 2-5 tokens cortos unidos por '+', sin espacios (whitelist sh_sanitize)
static void v6_addtok(char* r, size_t& l, int& nt, const char* s) {
    if (nt >= 5) return;
    size_t n = strlen(s);
    if (l + n + 2 < 238) { if (l) r[l++] = '+'; memcpy(r + l, s, n); l += n; r[l] = 0; nt++; } }

// score comun (§2.10): bonos +1 sobre el +2 nuclear de la clase (max 10)
static double v6_bonus(bool isbuy, double c, double vwap, double rvol, bool phase_fav,
                       char* r, size_t& l, int& nt) {
    const V5MACD& m15 = v5_tf15.macd;
    double s = 0;
    bool m15b = m15.a_up() || m15.b_up(), m15s = m15.a_dn() || m15.b_dn();
    if (isbuy ? m15b : m15s) { s += 1; v6_addtok(r, l, nt, isbuy ? "MACD15-verde" : "MACD15-rojo"); }
    if (isbuy ? v6_st5.dir == 1 : v6_st5.dir == -1) { s += 1; v6_addtok(r, l, nt, "ST5-alineado"); }
    if (isbuy ? v5_rib.score > 0.2 : v5_rib.score < -0.2) { s += 1;
        v6_addtok(r, l, nt, isbuy ? "ribbon15-alcista" : "ribbon15-bajista"); }
    if (isbuy ? c > vwap : c < vwap) { s += 1; v6_addtok(r, l, nt, isbuy ? "sobre-VWAP" : "bajo-VWAP"); }
    if (rvol >= 2.0) { s += 1; char t[24];
        std::snprintf(t, sizeof(t), "RVOL-%.1fx", rvol); v6_addtok(r, l, nt, t); }
    if (bar_is_live() && whale_score((double)time(nullptr), isbuy ? 1 : -1) > 0.3) { s += 1;
        v6_addtok(r, l, nt, isbuy ? "whales-comprando" : "whales-vendiendo"); }
    if (phase_fav) { s += 1; v6_addtok(r, l, nt, "fase-favorable"); }
    if (isbuy ? (v5_tl.up_break || v6_tl15_upbrk_ago <= 3)
              : (v5_tl.dn_break || v6_tl15_dnbrk_ago <= 3)) { s += 1;
        v6_addtok(r, l, nt, "TL-a-favor"); }
    return s; }

struct V6Cand { int cls = -1; double score = 0, prob = 0; char r[240] = ""; };

// hook por bar 1m CERRADO — enganchar despues de v5_on_bar (v5 ya actualizo su estado)
static void v6_on_bar(const Bar& b, bool alert_hours, int H, int M) {
    // ---- dia nuevo: roll de sesion ----
    double day = b.t - std::fmod(b.t, 86400.0);
    if (day != v6_day) {
        if (v6_day > 0) v6_atr15_prev = v6_atr15.atr;      // ATR15 al cierre previo (gap ratio)
        v6_sess.roll(v6_last_rth_close);
        v6_day = day;
        v6_or_hi = 0; v6_or_lo = 1e18; v6_below_run = 0;
        for (int i = 0; i < V6_N_CLASSES; i++) v6_fires_today[i] = 0;
        v6_arm_b.clear(); v6_arm_s.clear();                // v6.1: armadas mueren con el dia
        v6_retest_block_b = v6_retest_block_s = 0;
    }
    int open_min = V6_KRX > 0.5 ? 540 : 570;              // KRX abre 9:00 KST; US 9:30 ET
    int mso = H * 60 + M - open_min;                      // mins desde el open de sesion

    // ---- indicadores propios (siempre, tambien warm-up: alimentan estado) ----
    v6_atr1.add(b.h, b.l, b.c);
    v6_rsi1.add(b.c);
    v6_volring[v6_voln % 20] = b.v; v6_voln++;
    double volma = 0; { int k = v6_voln < 20 ? (int)v6_voln : 20;
        for (int i = 0; i < k; i++) volma += v6_volring[i]; if (k) volma /= k; }
    v6_sw.add(b.h, b.l);
    v6_lows[v6_voln % 10] = b.l; v6_highs[v6_voln % 10] = b.h;
    v6_a5.upd(b); v6_a15.upd(b);
    if (v6_a5.closed) { v6_st5.add(v6_a5.ch, v6_a5.cl, v6_a5.cc); v6_bb5.add(v6_a5.cc); }
    if (v6_a15.closed) {
        v6_atr15.add(v6_a15.ch, v6_a15.cl, v6_a15.cc);
        v6_adx15.add(v6_a15.ch, v6_a15.cl, v6_a15.cc);
        v6_bb15.add(v6_a15.cc);
        v6_tl15.add(v6_a15.ch, v6_a15.cl, v6_a15.cc);
        v6_tl15_upbrk_ago = v6_tl15.up_break ? 0 : v6_tl15_upbrk_ago + 1;
        v6_tl15_dnbrk_ago = v6_tl15.dn_break ? 0 : v6_tl15_dnbrk_ago + 1;
        // squeeze: percentil del bandwidth (BB-4); re-arma latches al re-entrar
        if (v6_bb15.squeeze()) { if (v6_squeeze_ago > 0) { v6_sq_up_done = v6_sq_dn_done = false; }
            v6_squeeze_ago = 0; }
        else v6_squeeze_ago++;
        // MACD15 4-color: flips para el detector de reversal (§2.5 c2)
        const V5MACD& m = v5_tf15.macd;                    // v5_tf15 ya cerro este mismo bucket
        int s15 = m.a_up() ? 1 : m.b_up() ? 2 : m.a_dn() ? 3 : 4;
        bool fdn = (s15 == 3 && v6_m15_prev != 3 && v6_m15_prev != 0) || (m.hist < 0 && m.hist1 >= 0);
        bool fup = (s15 == 1 && v6_m15_prev != 1 && v6_m15_prev != 0) || (m.hist > 0 && m.hist1 <= 0);
        v6_m15_flipdn_ago = fdn ? 0 : v6_m15_flipdn_ago + 1;
        v6_m15_flipup_ago = fup ? 0 : v6_m15_flipup_ago + 1;
        v6_m15_prev = s15;
        // band-walk (§2.5 c3): pctB extremo del close 15m, ring de 10
        double pb = v6_bb15.pctB(v6_a15.cc);
        v6_bwalk_up[v6_bw_i % 10] = (v6_bb15.n >= 20 && pb >= 0.9);
        v6_bwalk_dn[v6_bw_i % 10] = (v6_bb15.n >= 20 && pb <= 0.1);
        v6_bw_i++;
    }

    // ---- sesion: VWAP del bloque v5, OR propio por offset (vale para KRX) ----
    double vwap = v5_vwap_v > 0 ? v5_vwap_pv / v5_vwap_v : b.c;
    if (mso == 0) v6_sess.on_open(b.o, v6_atr15_prev);
    if (mso >= 0 && mso < 390) v6_last_rth_close = b.c;   // close RTH del dia (para el gap de mañana)
    if (mso >= 0 && mso < 30) { if (b.h > v6_or_hi) v6_or_hi = b.h;
        if (b.l < v6_or_lo) v6_or_lo = b.l; }
    if (mso >= 0 && mso <= 60) {
        v6_sess.on_bar(mso, b.c, b.v, vwap, volma);
        if (mso == 30) { v6_sess.vwap_at_1000 = vwap;      // eval 10:00
            v6_sess.classify(b.c, vwap, v6_atr15.atr, v6_or_hi,
                             v6_or_lo < 1e17 ? v6_or_lo : 0, v6_adx15.trending()); }
        if (mso == 60)                                     // re-eval 10:30; luego congelada
            v6_sess.classify(b.c, vwap, v6_atr15.atr, v6_or_hi,
                             v6_or_lo < 1e17 ? v6_or_lo : 0, v6_adx15.trending());
    }
    v6_below_run = b.c < vwap ? v6_below_run + 1 : 0;

    // MACD 1m: transicion de estado = gatillo de timing (§2.8)
    int m1s = v5_macd1.a_up() ? 1 : v5_macd1.b_up() ? 2 : v5_macd1.a_dn() ? 3 : 4;
    bool m1_turn_up = (m1s == 1 || m1s == 2) && (v6_m1_prev == 3 || v6_m1_prev == 4);
    bool m1_turn_dn = (m1s == 3 || m1s == 4) && (v6_m1_prev == 1 || v6_m1_prev == 2);

    // contexto de tendencia (§2.5) — se trackea siempre para el detector de reversal
    const V5MACD& m15 = v5_tf15.macd;
    bool m15_bull = m15.a_up() || m15.b_up(), m15_bear = m15.a_dn() || m15.b_dn();
    int ph = (int)v6_sess.phase;
    bool trend_long  = m15_bull && (v6_st5.dir == 1  || ph == V6Session::TREND_UP);
    bool trend_short = m15_bear && (v6_st5.dir == -1 || ph == V6Session::TREND_DOWN);
    v6_tlong_ago  = trend_long  ? 0 : v6_tlong_ago + 1;
    v6_tshort_ago = trend_short ? 0 : v6_tshort_ago + 1;

    // guardas de cierre de bar previo (se actualizan al final)
    double prev_high = v6_prev_high, prev_low = v6_prev_low;
    double prev_c = v6_prev_c, prev_vwap = v6_prev_vwap;
    v6_prev_high = b.h; v6_prev_low = b.l; v6_prev_c = b.c; v6_prev_vwap = vwap;
    v6_m1_prev = m1s;

    // ---- gate de disparo ----
    if (V6_ON <= 0 || !alert_hours) return;
    if (v5_tf15.macd.nsig < 9 || v6_atr15.n < 15) return; // warm-up multi-TF
    if (mso < 5 || mso > 330) return;                     // ventana de entradas (SIN flatten)

    v6_prob.maybe_reload("data/prob_table_ewy.txt", b.t);

    double atr15 = v6_atr15.atr;
    double rvol = volma > 0 ? b.v / volma : 0;
    bool green = b.c > b.o, red = b.c < b.o;

    // regla dura "15m manda" (§2.8) — exentas: MTF_BB_REV (rango) y TREND_REVERSAL
    bool veto_buy  = m15.a_dn() || (b.c < vwap && v6_st5.dir == -1);
    bool veto_sell = m15.a_up() || (b.c > vwap && v6_st5.dir == 1);

    // ---- v6.1: procesar señales ARMADAS (retest-confirm) — antes de evaluar
    // candidatos nuevos, con el mismo bar 1m cerrado ----
    auto v6_retest_step = [&](V6Armed& a, double& blk, bool veto_now) {
        if (a.cls < 0) return;
        bool ib = a.isbuy;
        a.bars++;
        double atr = v6_atr1.atr > 0 ? v6_atr1.atr : 1e-6;
        if (ib) { if (b.h > a.ext) a.ext = b.h; } else { if (b.l < a.ext) a.ext = b.l; }
        double imp = ib ? a.ext - a.level : a.level - a.ext;
        if (imp < 1e-9) imp = 1e-9;
        // TRAMPA: el pullback ATRAVIESA el nivel de vuelta (cierre en contra
        // >50% del impulso pasado el nivel) -> cancelada + log
        double cross = ib ? a.level - b.c : b.c - a.level;
        if (cross > 0 && cross > 0.5 * imp) {
            std::printf("[%02d:%02d] EWY V6 TRAMPA-EVITADA clase %s nivel %.2f px %.2f "
                        "impulso %.2f t=%.0f\n",
                        H, M, V6_CLS[a.cls], a.level, b.c, imp, b.t);
            std::fflush(stdout);
            blk = b.t + 300;                       // 5 min sin re-armar este lado
            a.clear(); return; }
        // pullback valido: retrace 30-70% del impulso o toque del nivel ±0.25*ATR
        double retr = ib ? (a.ext - b.l) / imp : (b.h - a.ext) / imp;
        bool touch = ib ? (b.l <= a.level + 0.25 * atr && b.l >= a.level - 0.25 * atr)
                        : (b.h >= a.level - 0.25 * atr && b.h <= a.level + 0.25 * atr);
        if ((retr >= 0.30 && retr <= 0.70) || touch) a.pulled = true;
        bool holding = ib ? b.c > a.level : b.c < a.level;
        if (!a.pulled) a.hold = holding ? a.hold + 1 : 0;
        bool fire = false; const char* tag = nullptr;
        if (!a.pulled && a.hold >= 3) { fire = true; tag = "breakaway"; }
        else if (a.pulled && holding && (ib ? b.c > b.o : b.c < b.o)) {
            fire = true; tag = "retest-ok"; }      // rechazo: cierra en la direccion
        if (fire) {
            // recheck de gates al confirmar: 15m pudo girar en contra durante
            // el retest (G3), y otro disparo pudo consumir cooldown/cupo
            double last = ib ? v6_last_fire_buy : v6_last_fire_sell;
            if (veto_now) {
                if (V6_DEBUG > 0) { std::printf("[%02d:%02d] V6-DBG retest %s cancelada "
                    "(veto-15m-en-confirmacion)\n", H, M, V6_CLS[a.cls]); std::fflush(stdout); }
                a.clear(); return; }
            if (b.t - last < V6_COOL || v6_fires_today[a.cls] >= (int)V6_MAX_CLASS_DAY) {
                if (V6_DEBUG > 0) { std::printf("[%02d:%02d] V6-DBG retest %s cancelada "
                    "(cooldown/cupo)\n", H, M, V6_CLS[a.cls]); std::fflush(stdout); }
                a.clear(); return; }
            char r2[256];
            std::snprintf(r2, sizeof(r2), "%s+%s", a.r, tag);
            v6_emit(ib, a.cls, a.prob, a.score, r2, b, H, M, ph);
            a.clear(); return; }
        if (a.bars >= (int)V6_RETEST_MAX) {
            if (V6_DEBUG > 0) { std::printf("[%02d:%02d] V6-DBG retest %s expirada "
                "(%d bars sin confirmar)\n", H, M, V6_CLS[a.cls], a.bars); std::fflush(stdout); }
            a.clear(); } };
    v6_retest_step(v6_arm_b, v6_retest_block_b, veto_buy);
    v6_retest_step(v6_arm_s, v6_retest_block_s, veto_sell);

    auto long_allowed = [&](int cls) -> bool {
        bool exempt = (cls == MTF_BB_REV_LONG || cls == TREND_REVERSAL_LONG);
        const char* why = nullptr;
        if (veto_buy && !exempt) why = "veto-15m-manda";
        else if (ph == V6Session::TREND_DOWN && cls != TREND_REVERSAL_LONG) why = "fase-TREND_DOWN";
        else if (ph == V6Session::SPIKE_FADE && !v6_sess.reclaimed) why = "fase-SPIKE_FADE-sin-reclaim";
        else if (ph == V6Session::LATERAL &&
                 (cls == SQUEEZE_BREAK_LONG || cls == ORB_LONG || cls == TLINE_BREAK_LONG))
            why = "fase-LATERAL-veta-breakouts";
        if (why && V6_DEBUG > 0) {
            std::printf("[%02d:%02d] V6-DBG veto BUY clase %s (%s)\n", H, M, V6_CLS[cls], why);
            std::fflush(stdout); }
        return why == nullptr; };
    auto short_allowed = [&](int cls) -> bool {
        bool exempt = (cls == MTF_BB_REV_SHORT || cls == TREND_REVERSAL_SHORT);
        const char* why = nullptr;
        if (veto_sell && !exempt) why = "veto-15m-manda";
        else if (ph == V6Session::TREND_UP && cls != TREND_REVERSAL_SHORT) why = "fase-TREND_UP";
        else if (ph == V6Session::LATERAL &&
                 (cls == SQUEEZE_BREAK_SHORT || cls == ORB_SHORT || cls == TLINE_BREAK_SHORT))
            why = "fase-LATERAL-veta-breakouts";
        if (why && V6_DEBUG > 0) {
            std::printf("[%02d:%02d] V6-DBG veto SELL clase %s (%s)\n", H, M, V6_CLS[cls], why);
            std::fflush(stdout); }
        return why == nullptr; };

    V6Cand cb, cs;
    auto consider = [&](V6Cand& best, int cls, double sc, const char* r) {
        double p = v6_prob.prob(V6_CLS[cls], V6_PRIOR[cls]);
        if (best.cls < 0 || p > best.prob + 1e-9 ||
            (std::fabs(p - best.prob) < 1e-9 && sc > best.score)) {
            best.cls = cls; best.score = sc; best.prob = p;
            strncpy(best.r, r, sizeof(best.r) - 1); best.r[sizeof(best.r) - 1] = 0; } };
    bool phase_fav_l = (ph == V6Session::TREND_UP || ph == V6Session::DIP_CLIMB);
    bool phase_fav_s = (ph == V6Session::TREND_DOWN || ph == V6Session::SPIKE_FADE);

    // extremos del pullback: min/max de los ultimos 10 bars 1m
    double pull_low = 1e18, pull_high = 0;
    { int k = v6_voln < 10 ? (int)v6_voln : 10;
      for (int i = 0; i < k; i++) { if (v6_lows[i] < pull_low) pull_low = v6_lows[i];
          if (v6_highs[i] > pull_high) pull_high = v6_highs[i]; } }

    // == 1. TREND_PULLBACK (§2.5 continuacion) ==
    {
        double retr = v6_sw.retr_dn(b.c);
        double hold_ref = std::max(vwap, v6_bb15.n >= 20 ? v6_bb15.mid : vwap);
        if (trend_long && v6_adx15.trending() && retr > 0 && retr <= V6_RETR_CONT &&
            pull_low >= hold_ref - 0.10 * atr15 &&
            m1_turn_up && green && prev_high > 0 && b.c > prev_high && rvol >= 1.2 &&
            long_allowed(TREND_PULLBACK_LONG)) {
            char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
            std::snprintf(t, sizeof(t), "pullback-%.0f%%", retr * 100);
            v6_addtok(r, l, nt, t); v6_addtok(r, l, nt, "MACD1-gira");
            double sc = 2 + v6_bonus(true, b.c, vwap, rvol, phase_fav_l, r, l, nt);
            consider(cb, TREND_PULLBACK_LONG, sc, r); }
        // espejo corto: rebote <=50% desde swing_lo, high del rebote no supera
        // min(VWAP, BB15.mid) + 0.10*ATR15, bar rojo que pierde el low previo
        double retru = v6_sw.retr_up(b.c);
        double hold_ref_s = std::min(vwap, v6_bb15.n >= 20 ? v6_bb15.mid : vwap);
        if (trend_short && v6_adx15.trending() && retru > 0 && retru <= V6_RETR_CONT &&
            pull_high <= hold_ref_s + 0.10 * atr15 &&
            m1_turn_dn && red && prev_low > 0 && b.c < prev_low && rvol >= 1.2 &&
            short_allowed(TREND_PULLBACK_SHORT)) {
            char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
            std::snprintf(t, sizeof(t), "rebote-%.0f%%", retru * 100);
            v6_addtok(r, l, nt, t); v6_addtok(r, l, nt, "MACD1-gira-abajo");
            double sc = 2 + v6_bonus(false, b.c, vwap, rvol, phase_fav_s, r, l, nt);
            consider(cs, TREND_PULLBACK_SHORT, sc, r); }
    }

    // == 2. VWAP_RECLAIM_LONG / VWAP_LOSS_SHORT (§2.9-2) ==
    if (ph == V6Session::DIP_CLIMB && mso < 120 &&
        prev_c > 0 && prev_c <= prev_vwap && b.c > vwap &&
        volma > 0 && b.v >= V6_RVOL_RECLAIM * volma &&
        long_allowed(VWAP_RECLAIM_LONG)) {
        char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
        v6_addtok(r, l, nt, "reclaim-VWAP");
        std::snprintf(t, sizeof(t), "vol-%.1fx", rvol); v6_addtok(r, l, nt, t);
        double sc = 2 + v6_bonus(true, b.c, vwap, rvol, phase_fav_l, r, l, nt);
        consider(cb, VWAP_RECLAIM_LONG, sc, r); }
    if (ph == V6Session::SPIKE_FADE && v6_below_run >= 3 &&
        volma > 0 && b.v >= 1.5 * volma && !m15_bull &&
        short_allowed(VWAP_LOSS_SHORT)) {
        char r[240] = ""; size_t l = 0; int nt = 0;
        v6_addtok(r, l, nt, "perdida-VWAP-3bars"); v6_addtok(r, l, nt, "spike-fade");
        double sc = 2 + v6_bonus(false, b.c, vwap, rvol, phase_fav_s, r, l, nt);
        consider(cs, VWAP_LOSS_SHORT, sc, r); }

    // == 3. SQUEEZE_BREAK (§2.7 BB-4/BB-5: sin volumen no hay señal) ==
    bool sq_recent = v6_squeeze_ago <= 5 && v6_bb15.n >= 20;
    if (sq_recent && b.c > v6_bb15.up && !v6_sq_up_done) {
        if (rvol >= V6_RVOL && !m15.a_dn() && long_allowed(SQUEEZE_BREAK_LONG)) {
            char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
            std::snprintf(t, sizeof(t), "squeeze-p%.0f", v6_bb15.bw_pctile());
            v6_addtok(r, l, nt, t); v6_addtok(r, l, nt, "cierre-fuera-BB15");
            double sc = 2 + v6_bonus(true, b.c, vwap, rvol, phase_fav_l, r, l, nt);
            consider(cb, SQUEEZE_BREAK_LONG, sc, r); } }
    if (sq_recent && b.c < v6_bb15.dn && !v6_sq_dn_done) {
        if (rvol >= V6_RVOL && !m15.a_up() && short_allowed(SQUEEZE_BREAK_SHORT)) {
            char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
            std::snprintf(t, sizeof(t), "squeeze-p%.0f", v6_bb15.bw_pctile());
            v6_addtok(r, l, nt, t); v6_addtok(r, l, nt, "cierre-bajo-BB15");
            double sc = 2 + v6_bonus(false, b.c, vwap, rvol, phase_fav_s, r, l, nt);
            consider(cs, SQUEEZE_BREAK_SHORT, sc, r); } }
    // latch: el "primer cierre fuera" solo existe una vez por squeeze
    if (sq_recent) { if (b.c > v6_bb15.up) v6_sq_up_done = true;
                     if (b.c < v6_bb15.dn) v6_sq_dn_done = true; }

    // == 4. ORB (§2.9-4; OR propio de 30 min por offset de sesion) ==
    if (mso >= 30 && mso <= 120 && v6_or_hi > 0 && v6_or_lo < 1e17) {
        bool gap_veto_l = v6_sess.no_fade && v6_sess.gap_dir < 0;   // breakaway en contra
        bool gap_veto_s = v6_sess.no_fade && v6_sess.gap_dir > 0;
        if (b.c > v6_or_hi && rvol >= V6_RVOL && b.c > vwap &&
            ph != V6Session::LATERAL && !gap_veto_l && long_allowed(ORB_LONG)) {
            char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
            v6_addtok(r, l, nt, "rompe-OR-arriba");
            std::snprintf(t, sizeof(t), "vol-%.1fx", rvol); v6_addtok(r, l, nt, t);
            double sc = 2 + v6_bonus(true, b.c, vwap, rvol, phase_fav_l, r, l, nt);
            consider(cb, ORB_LONG, sc, r); }
        if (b.c < v6_or_lo && rvol >= V6_RVOL && b.c < vwap &&
            ph != V6Session::LATERAL && !gap_veto_s && short_allowed(ORB_SHORT)) {
            char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
            v6_addtok(r, l, nt, "rompe-OR-abajo");
            std::snprintf(t, sizeof(t), "vol-%.1fx", rvol); v6_addtok(r, l, nt, t);
            double sc = 2 + v6_bonus(false, b.c, vwap, rvol, phase_fav_s, r, l, nt);
            consider(cs, ORB_SHORT, sc, r); } }

    // == 5. MTF_BB_REV (logica v5 de bandas reventadas en >=2 TF + regimen ADX) ==
    {
        int bb_dn_tfs = (v5_bb1_dn_ago <= 3) + (v5_bb5_dn_ago <= 2) + (v5_bb15_dn_ago <= 1);
        int bb_up_tfs = (v5_bb1_up_ago <= 3) + (v5_bb5_up_ago <= 2) + (v5_bb15_up_ago <= 1);
        bool gap_veto_l = v6_sess.no_fade && v6_sess.gap_dir < 0;   // fade contra gap-down
        bool gap_veto_s = v6_sess.no_fade && v6_sess.gap_dir > 0;
        if (bb_dn_tfs >= 2 && green && v6_rsi1.rsi > 30 && v6_rsi1.rising() &&
            v6_adx15.ranging() && !gap_veto_l && long_allowed(MTF_BB_REV_LONG)) {
            char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
            v6_addtok(r, l, nt, bb_dn_tfs >= 3 ? "BB-3TF-abajo" : "BB-2TF-abajo");
            std::snprintf(t, sizeof(t), "RSI-%.0f-sube", v6_rsi1.rsi); v6_addtok(r, l, nt, t);
            double sc = 2 + v6_bonus(true, b.c, vwap, rvol, phase_fav_l, r, l, nt);
            consider(cb, MTF_BB_REV_LONG, sc, r); }
        if (bb_up_tfs >= 2 && red && v6_rsi1.rsi < 70 && v6_rsi1.falling() &&
            v6_adx15.ranging() && !gap_veto_s && short_allowed(MTF_BB_REV_SHORT)) {
            char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
            v6_addtok(r, l, nt, bb_up_tfs >= 3 ? "BB-3TF-arriba" : "BB-2TF-arriba");
            std::snprintf(t, sizeof(t), "RSI-%.0f-baja", v6_rsi1.rsi); v6_addtok(r, l, nt, t);
            double sc = 2 + v6_bonus(false, b.c, vwap, rvol, phase_fav_s, r, l, nt);
            consider(cs, MTF_BB_REV_SHORT, sc, r); }
    }

    // == 6. TLINE_BREAK (break 1m + trendline 15m no intacta EN CONTRA, §2.6) ==
    if (v5_tl.up_break && rvol >= V6_RVOL && b.c > vwap &&
        (v6_tl15_upbrk_ago <= 3 || !v6_tl15.bear_line_near(b.c, 0.5 * atr15)) &&
        long_allowed(TLINE_BREAK_LONG)) {
        char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
        v6_addtok(r, l, nt, "rompe-TL-1m");
        std::snprintf(t, sizeof(t), "vol-%.1fx", rvol); v6_addtok(r, l, nt, t);
        double sc = 2 + v6_bonus(true, b.c, vwap, rvol, phase_fav_l, r, l, nt);
        consider(cb, TLINE_BREAK_LONG, sc, r); }
    if (v5_tl.dn_break && rvol >= V6_RVOL && b.c < vwap &&
        (v6_tl15_dnbrk_ago <= 3 || !v6_tl15.bull_line_near(b.c, 0.5 * atr15)) &&
        short_allowed(TLINE_BREAK_SHORT)) {
        char r[240] = ""; size_t l = 0; int nt = 0; char t[32];
        v6_addtok(r, l, nt, "rompe-TL-1m-abajo");
        std::snprintf(t, sizeof(t), "vol-%.1fx", rvol); v6_addtok(r, l, nt, t);
        double sc = 2 + v6_bonus(false, b.c, vwap, rvol, phase_fav_s, r, l, nt);
        consider(cs, TLINE_BREAK_SHORT, sc, r); }

    // == 7. TREND_REVERSAL (§2.5: >=2 de 3; sin RVOL, es aviso de estructura) ==
    {
        // desde tendencia LARGA reciente (<=30 min): reversal = SELL
        if (v6_tlong_ago <= 30) {
            int nwalk = 0; for (int i = 0; i < 10; i++) if (v6_bwalk_up[i]) nwalk++;
            bool c1 = v6_sw.retr_dn(b.c) > V6_RETR_REV || v6_sw.broke_last_low(b.c);
            bool c2 = v6_m15_flipdn_ago <= 1;
            bool c3 = v6_bb15.n >= 20 && b.c < v6_bb15.mid && nwalk >= 3;
            if ((int)c1 + (int)c2 + (int)c3 >= 2 && short_allowed(TREND_REVERSAL_SHORT)) {
                char r[240] = ""; size_t l = 0; int nt = 0;
                if (c1) v6_addtok(r, l, nt, "estructura-rota");
                if (c2) v6_addtok(r, l, nt, "MACD15-flip-abajo");
                if (c3) v6_addtok(r, l, nt, "pierde-BB15mid");
                double sc = 2 + v6_bonus(false, b.c, vwap, rvol, phase_fav_s, r, l, nt);
                consider(cs, TREND_REVERSAL_SHORT, sc, r); } }
        // desde tendencia CORTA reciente: reversal = BUY
        if (v6_tshort_ago <= 30) {
            int nwalk = 0; for (int i = 0; i < 10; i++) if (v6_bwalk_dn[i]) nwalk++;
            bool c1 = v6_sw.retr_up(b.c) > V6_RETR_REV || v6_sw.broke_last_high(b.c);
            bool c2 = v6_m15_flipup_ago <= 1;
            bool c3 = v6_bb15.n >= 20 && b.c > v6_bb15.mid && nwalk >= 3;
            if ((int)c1 + (int)c2 + (int)c3 >= 2 && long_allowed(TREND_REVERSAL_LONG)) {
                char r[240] = ""; size_t l = 0; int nt = 0;
                if (c1) v6_addtok(r, l, nt, "estructura-rota-arriba");
                if (c2) v6_addtok(r, l, nt, "MACD15-flip-arriba");
                if (c3) v6_addtok(r, l, nt, "recupera-BB15mid");
                double sc = 2 + v6_bonus(true, b.c, vwap, rvol, phase_fav_l, r, l, nt);
                consider(cb, TREND_REVERSAL_LONG, sc, r); } }
    }

    // ---- gates finales: score, prob, cooldown por lado, limite por clase/dia ----
    bool bq = cb.cls >= 0 && cb.score >= V6_MIN && cb.prob >= V6_PROB_MIN &&
              b.t - v6_last_fire_buy >= V6_COOL &&
              v6_fires_today[cb.cls] < (int)V6_MAX_CLASS_DAY;
    bool sq = cs.cls >= 0 && cs.score >= V6_MIN && cs.prob >= V6_PROB_MIN &&
              b.t - v6_last_fire_sell >= V6_COOL &&
              v6_fires_today[cs.cls] < (int)V6_MAX_CLASS_DAY;
    if (V6_DEBUG > 0) {
        if (cb.cls >= 0 && !bq) { std::printf("[%02d:%02d] V6-DBG BUY %s gated score %.1f prob %.0f\n",
            H, M, V6_CLS[cb.cls], cb.score, cb.prob); std::fflush(stdout); }
        if (cs.cls >= 0 && !sq) { std::printf("[%02d:%02d] V6-DBG SELL %s gated score %.1f prob %.0f\n",
            H, M, V6_CLS[cs.cls], cs.score, cs.prob); std::fflush(stdout); } }
    if (bq && sq) {                                        // ambos lados: gana mayor prob
        if (cb.prob > cs.prob) sq = false;
        else if (cs.prob > cb.prob) bq = false;
        else bq = sq = false;                              // empate -> silencio
    }
    // v6.1: clases de ruptura NO disparan al instante — quedan ARMADAS (retest);
    // el resto de clases dispara inmediato como v6.0
    auto v6_arm_or_fire = [&](bool isbuy, const V6Cand& c) {
        if (V6_RETEST > 0.5 && v6_is_breakout_cls(c.cls) && !v6_retest_exempt[c.cls]) {
            V6Armed& a = isbuy ? v6_arm_b : v6_arm_s;
            double blk = isbuy ? v6_retest_block_b : v6_retest_block_s;
            if (a.cls >= 0 || b.t < blk) return;   // slot ocupado o trampa reciente
            a.cls = c.cls; a.isbuy = isbuy;
            a.level = v6_break_level(c.cls, vwap, b.c);
            a.ext = isbuy ? b.h : b.l;
            a.score = c.score; a.prob = c.prob; a.t0 = b.t;
            a.bars = 0; a.hold = 0; a.pulled = false;
            strncpy(a.r, c.r, sizeof(a.r) - 1); a.r[sizeof(a.r) - 1] = 0;
            if (V6_DEBUG > 0) { std::printf("[%02d:%02d] V6-DBG ARMADA %s %s nivel %.2f "
                "(retest-confirm)\n", H, M, isbuy ? "BUY" : "SELL", V6_CLS[c.cls], a.level);
                std::fflush(stdout); }
        } else {
            v6_emit(isbuy, c.cls, c.prob, c.score, c.r, b, H, M, ph); } };
    if (bq) v6_arm_or_fire(true, cb);
    if (sq) v6_arm_or_fire(false, cs);
}
// ==================== FIN MOTOR v6 ====================






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
        // daemon IBKR escribe data/bars_ewy_ibkr.txt; tail -F lo sigue 
        // (Yunior 2026-07-20: only ibkr — fuente unica)
        in = popen("tail -n +1 -F data/bars_ewy_ibkr.txt 2>>bridge_ewy.log", "r");
        if (!in) { std::fprintf(stderr, "no bridge\n"); return 1; }
        std::fprintf(stderr, "ewy_signal_bot (C++): bridge EWY 1m real iniciado\n");
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
    // Dedupe por epoch (2026-07-26): estado del ultimo bar ACEPTADO.
    double last_bar_ep = 0; long ndup = 0;
    while (std::fgets(line, sizeof(line), in)) {
        if (std::sscanf(line, "%lf %lf %lf %lf %lf %lf",
                        &b.t, &b.o, &b.h, &b.l, &b.c, &b.v) != 6) continue;
        // ---- DEDUPE POR EPOCH: solo cuenta la barra ESTRICTAMENTE NUEVA ----
        // El bridge REESCRIBE data/bars_<sym>_ibkr.txt entero en cada warm-up
        // (ibkr_bar_bridge.warmup_sym: open(path,"w") con 2 dias de 1m) y el
        // `tail -n +1 -F` que nos alimenta reemite el fichero COMPLETO al detectar
        // el truncado — probado: 5 lineas reescritas => 10 emitidas. Con el fichero
        // real (1691 barras) eso son hasta 1691 barras reinyectadas en indicadores
        // VIVOS. ATR/RSI/BB/CUSUM/VWAP son ACUMULADORES: contar dos veces la misma
        // barra los envenena y el bot habla de un movimiento que no ocurrio (medido
        // en NVDA: dos TRAMPA-EVITADA y un CUSUM "CAYENDO -2.04%" inventados, y el
        // CUSUM real perdido). Mismo patron que order_engine: epoch nuevo o nada.
        if (b.t <= last_bar_ep) {
            if (++ndup == 1 || ndup % 500 == 0)
                std::fprintf(stderr, "dedupe: barra repetida epoch %.0f ignorada "
                             "(%ld en total; warm-up del bridge)\n", b.t, ndup);
            continue;
        }
        last_bar_ep = b.t;
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

        v5_on_bar(b, alert_hours, H, M);   // motor v5 MTF (2026-07-15)
        v6_on_bar(b, alert_hours, H, M);   // motor v6 (2026-07-16)
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
                        std::printf("[%02d:%02d] CUSUM: EWY SUBIENDO fuerte (+%.2f%% acumulado) px %.2f t=%.0f\n",
                                    H, M, cusum_up * 100, b.c, b.t);
                        std::fflush(stdout);
                        { char m[160]; std::snprintf(m, sizeof(m), "CUSUM: subiendo fuerte %+.2f%% px %.2f", cusum_up*100, b.c); notify("EWY TERREMOTO ALZA", m, QUAKE_BANNER > 0); }
                        cusum_up = 0; cusum_dn = 0; last_cusum = b.t;
                    } else if (cusum_dn < -hthr) {
                        std::printf("[%02d:%02d] CUSUM: EWY CAYENDO fuerte (%.2f%% acumulado) px %.2f t=%.0f\n",
                                    H, M, cusum_dn * 100, b.c, b.t);
                        std::fflush(stdout);
                        { char m[160]; std::snprintf(m, sizeof(m), "CUSUM: cayendo fuerte %.2f%% px %.2f", cusum_dn*100, b.c); notify("EWY TERREMOTO CAIDA", m, QUAKE_BANNER > 0); }
                        cusum_up = 0; cusum_dn = 0; last_cusum = b.t;
                    }
                }
            }
            last_c_for_ret = b.c;
        }
        // 2) Supertrend 5m: bandas mid +/- 4.0*ATR5(10) (menos ruido que 1m)
        static double a5h = -1e18, a5l = 1e18, a5c = 0; static int a5n = 0;
        static double atr5 = 0, prev5c = 0; static long n5 = 0;
        if (a5n == 0) { a5h = b.h; a5l = b.l; }
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
                    std::printf("[%02d:%02d] SUPERTREND: tendencia EWY cambio a ALCISTA px %.2f\n", H, M, b.c);
                    { char m[120]; std::snprintf(m, sizeof(m), "Supertrend: tendencia ALCISTA px %.2f", b.c); notify("EWY tendencia", m, false); }
                } else {
                    std::printf("[%02d:%02d] SUPERTREND: tendencia EWY cambio a BAJISTA px %.2f\n", H, M, b.c);
                    { char m[120]; std::snprintf(m, sizeof(m), "Supertrend: tendencia BAJISTA px %.2f", b.c); notify("EWY tendencia", m, false); }
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
                std::printf("[%02d:%02d] DONCHIAN: EWY rompe maximo del dia px %.2f > %.2f\n", H, M, b.c, hi);
                std::fflush(stdout);
                { char m[120]; std::snprintf(m, sizeof(m), "Donchian: rompe maximo del dia px %.2f", b.c); notify("EWY breakout", m, false); }
                last_don = b.t;
            } else if (b.c < lo) {
                std::printf("[%02d:%02d] DONCHIAN: EWY rompe minimo del dia px %.2f < %.2f\n", H, M, b.c, lo);
                std::fflush(stdout);
                { char m[120]; std::snprintf(m, sizeof(m), "Donchian: rompe minimo del dia px %.2f", b.c); notify("EWY breakdown", m, false); }
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
            // INTRABAR (fix 2026-07-24): antes solo miraba el CIERRE, asi que una
            // barra que BARRIA el stop por el minimo y cerraba encima dejaba la
            // alarma MUDA — justo en una caida rapida. Ahora dispara con el low, y
            // el fill es pesimista (stop o open si abrio por debajo), igual que la
            // rama del bar ambiguo de abajo (que asi queda cubierta por esta).
            if (b.l <= stop_px) { sold = true; why = "HARD STOP";
                                  exit_px = std::min(b.o, stop_px); }
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
                if ((b.c >= floor_px || EOD_FORCE > 0) && envd("EWY_EOD_FLATTEN", 0) > 0.5) { sold = true; why = "EOD flatten 15:45"; }
            }
            if (sold) {
                std::printf("[%02d:%02d] *** EWY: VENDER *** ~%.2f (%s, entrada %.2f) t=%.0f\n",
                            H, M, exit_px, why, entry, b.t);
                std::fflush(stdout);
                if (audio_gate(true)) { play("sounds/dram_sell.wav", "Hero"); speak("sell S M H now"); }
                { char m[200]; std::snprintf(m, sizeof(m),
                    "VENDER EWY @ %.2f | %s | entrada %.2f | PnL %+.1f%%",
                    exit_px, why, entry, (exit_px / entry - 1) * 100);
                  notify(why[0] == 'H' ? "EWY: SELL (STOP)" : "EWY: SELL", m, true); }
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
                    std::printf("[%02d:%02d] *** EWY: VENDER PUT *** ~%.2f (reversal a largo, entrada %.2f) t=%.0f\n",
                                H, M, px, s_entry, b.t);
                    std::fflush(stdout);
                    if (audio_gate(true)) { play("sounds/dram_buy.wav", "Glass"); speak("buy S M H now"); }
                    { char m[200]; std::snprintf(m, sizeof(m),
                        "COMPRAR EWY @ %.2f | reversal a alza | entrada %.2f | mov %+.1f%%",
                        px, s_entry, (s_entry / px - 1) * 100);
                      notify("EWY: BUY", m, true); }
                    in_short = false; unlink(SPOS_FILE);
                }
                in_pos = true; entry = b.o; peak = b.h;
                floor_px = entry * (1 + FLOOR_PCT / 100.0);
                target_px = entry * (1 + TARGET_PCT / 100.0);
                pos_epoch = b.t; day_entries++;
                save_pos(entry, peak, floor_px, target_px, pos_epoch);
                std::printf("[%02d:%02d] *** EWY: COMPRAR *** ~%.2f (capitulacion confirmada; "
                            "target %.2f, floor %.2f) t=%.0f\n", H, M, entry, target_px, floor_px, b.t);
                std::fflush(stdout);
                if (audio_gate(true)) { play("sounds/dram_buy.wav", "Glass"); speak("buy S M H now"); }
                { char m[200]; std::snprintf(m, sizeof(m),
                    "COMPRAR EWY @ %.2f | target %.2f | floor %.2f | capitulacion confirmada",
                    entry, target_px, floor_px);
                  notify("EWY: BUY", m, true); }
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
                bool sp_gate = SPREAD_MAX > 0 && bar_is_live();
                double sp = sp_gate ? nbbo_spread_pct() : 0;
                if (sp_gate && (sp < 0 || sp > SPREAD_MAX)) {  // fail-closed: sin NBBO no pasa
                    std::printf("[%02d:%02d] confirm BLOQUEADO: spread %.2f%% (max %.2f%%%s)\n",
                                H, M, sp, SPREAD_MAX, sp < 0 ? " sin-NBBO" : "");
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
                // INTRABAR (fix 2026-07-24): espejo corto — el HIGH barre el stop
                // aunque el cierre quede debajo. Fill pesimista al stop/open.
                if (b.h >= s_stop_px) { cov = true; why = "HARD STOP";
                                        exit_px = std::max(b.o, s_stop_px); }
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
                    if ((b.c <= s_floor || EOD_FORCE > 0) && envd("EWY_EOD_FLATTEN", 0) > 0.5) { cov = true; why = "EOD cover 15:45"; }
                }
                if (cov) {
                    std::printf("[%02d:%02d] *** EWY: VENDER PUT *** ~%.2f (%s, entrada %.2f) t=%.0f\n",
                                H, M, exit_px, why, s_entry, b.t);
                    std::fflush(stdout);
                    if (audio_gate(true)) { play("sounds/dram_buy.wav", "Ping"); speak("buy S M H now"); }
                    { char m[200]; std::snprintf(m, sizeof(m),
                        "COMPRAR EWY @ %.2f | %s | entrada %.2f | mov %+.1f%%",
                        exit_px, why, s_entry, (s_entry / exit_px - 1) * 100);
                      notify(why[0] == 'H' ? "EWY: BUY (STOP)" : "EWY: BUY", m, true); }
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
                    std::printf("[%02d:%02d] *** EWY: PUT *** ~%.2f (blow-off confirmado; "
                                "target %.2f, floor %.2f) t=%.0f\n", H, M, s_entry, s_target, s_floor, b.t);
                    std::fflush(stdout);
                    if (audio_gate(true)) { play("sounds/dram_sell.wav", "Basso"); speak("sell S M H now"); }
                    { char m[200]; std::snprintf(m, sizeof(m),
                        "VENDER EWY @ %.2f | target %.2f | floor %.2f | senal de BAJADA (blow-off)",
                        s_entry, s_target, s_floor);
                      notify("EWY: SELL", m, true); }
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
                    bool sp_gate = SPREAD_MAX > 0 && bar_is_live();
                    double sp = sp_gate ? nbbo_spread_pct() : 0;
                    if (!(sp_gate && (sp < 0 || sp > SPREAD_MAX))) { pending_short = true; armed_s = false; }
                }
                if (armed_s && nbars - armed_bar_s > CONFIRM_WINDOW) armed_s = false;
            }
        }
        pb = b; has_pb = true;
    }
    if (!use_stdin) pclose(in);
    return 0;
}
