// alpaca_ws_bridge.cpp — Alpaca WEBSOCKET 1m-bar bridge for the signal fleet.
// Yunior 2026-07-10: "avoid rest api calls when u can use websockets" — this
// replaces the REST-polling alpaca_bar_bridge AND two python bridges
// (nok_bar_bridge.py, ws_bar_bridge.py polygon SPCX que NUNCA conecto:
// "Your plan doesn't include websocket access").
//
// Alpaca free tier = UNA sola conexion ws por cuenta -> un daemon compartido
// es dueño de ella y reparte los bars por archivo; cada bot popen-ea un
// reader ligero. WebSocket nativo via Network.framework (macOS, cero deps;
// el libcurl del sistema no trae ws/wss).
//
//   daemon:  ./alpaca_ws_bridge NOK SPCX ...   (lo vigila ensure_all/start_all)
//            wss://stream.data.alpaca.markets/v2/iex, canal "bars" (bares de
//            1 min NATIVOS, llegan ~1s despues de cerrar el minuto) ->
//            append "EPOCH O H L C V" a data/bars_<sym>.txt
//   reader:  ./alpaca_ws_bridge read NOK       (popen del bot, mismo contrato
//            que los bridges python: "EPOCH OPEN HIGH LOW CLOSE VOLUME")
//            REST solo UNA vez para el warm-up historico (la historia no
//            existe por ws) y despues sigue el archivo vivo cada 200ms.
//
// Nota feed: iex = solo prints de IEX; un minuto sin trades IEX no genera bar
// (el REST tiene el MISMO hueco — es el mismo feed, no se pierde nada).
//
// build: clang++ -std=c++17 -O2 -o alpaca_ws_bridge alpaca_ws_bridge.cpp \
//        -lcurl -framework Network
#include <Network/Network.h>
#include <curl/curl.h>
#include <dispatch/dispatch.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <map>
#include <set>
#include <string>
#include <vector>

static std::string KEY, SEC;

static void load_keys() {
    std::ifstream f("alpaca.env");
    std::string line;
    while (std::getline(f, line)) {
        auto strip = [](std::string s) {
            while (!s.empty() && (s.back() == '\r' || s.back() == '"' || s.back() == ' '))
                s.pop_back();
            if (!s.empty() && s.front() == '"') s.erase(0, 1);
            return s;
        };
        if (line.rfind("ALPACA_KEY=", 0) == 0) KEY = strip(line.substr(11));
        if (line.rfind("ALPACA_SECRET=", 0) == 0) SEC = strip(line.substr(14));
    }
}

static std::string lower(std::string s) {
    for (char& c : s) c = (char)std::tolower((unsigned char)c);
    return s;
}
static std::string bars_path(const std::string& sym) {
    return "data/bars_" + lower(sym) + ".txt";
}

// "2026-07-10T19:59:00Z" -> epoch (UTC)
static double iso_epoch(const char* s) {
    struct tm tmv{};
    if (!strptime(s, "%Y-%m-%dT%H:%M:%S", &tmv)) return 0;
    return (double)timegm(&tmv);
}

static bool num_key(const std::string& j, const char* key, double& out) {
    std::string k = std::string("\"") + key + "\":";
    size_t i = j.find(k);
    if (i == std::string::npos) return false;
    out = atof(j.c_str() + i + k.size());
    return true;
}

// ============================ daemon (websocket) ============================
static dispatch_queue_t g_q;
static nw_connection_t g_conn;
static dispatch_semaphore_t g_dead;         // signaled when the connection dies
static volatile time_t g_last_msg = 0;
static std::vector<std::string> g_syms;
static bool g_subscribed = false;
// quotes vivos para topgainer_alert (fix 429 2026-07-10: Finnhub free = 60
// req/min y el poll de 2s sobre el watchlist entero lo reventaba). El alert
// bot escribe data/topgainer/ws_watch (1 simbolo/linea); el daemon suscribe
// "trades" de esos nombres y escribe el ultimo precio en data/quote_<sym>.txt.
static std::set<std::string> g_trades;               // suscritos (solo en g_q)
static std::map<std::string, time_t> g_qwrite;       // throttle 1 write/s/sym
static void ws_send(const std::string& s);

static void check_watch() {                          // corre SIEMPRE en g_q
    if (!g_subscribed) return;
    std::set<std::string> want;
    // los 4 syms de bars TAMBIEN por trades: el daemon arma el bar 1m el
    // mismo (SELF-AGG) y lo emite AL CERRAR el minuto — sin esperar el push
    // agregado de Alpaca (~0.1-1s). Orden Yunior 2026-07-10: "1ms average".
    for (auto& s : g_syms) want.insert(s);
    std::ifstream f("data/topgainer/ws_watch");
    std::string line;
    while (std::getline(f, line) && want.size() < 30) {   // 30 syms/conn: 13 flota + 17 watchlist
        while (!line.empty() && (line.back() == '\r' || line.back() == ' '))
            line.pop_back();
        if (!line.empty()) want.insert(line);
    }
    std::string add, del;
    for (auto& s : want) if (!g_trades.count(s)) add += (add.empty() ? "\"" : ",\"") + s + "\"";
    for (auto& s : g_trades) if (!want.count(s)) del += (del.empty() ? "\"" : ",\"") + s + "\"";
    if (!add.empty()) ws_send("{\"action\":\"subscribe\",\"trades\":[" + add + "]}");
    if (!del.empty()) ws_send("{\"action\":\"unsubscribe\",\"trades\":[" + del + "]}");
    if (!add.empty() || !del.empty()) {
        g_trades = want;
        fprintf(stderr, "ws: trades watch -> %zu syms\n", g_trades.size());
    }
}

static void ws_send(const std::string& s) {
    nw_protocol_metadata_t meta = nw_ws_create_metadata(nw_ws_opcode_text);
    nw_content_context_t ctx = nw_content_context_create("msg");
    nw_content_context_set_metadata_for_protocol(ctx, meta);
    dispatch_data_t d = dispatch_data_create(s.data(), s.size(), g_q,
                                             DISPATCH_DATA_DESTRUCTOR_DEFAULT);
    nw_connection_send(g_conn, d, ctx, true, ^(nw_error_t) {});
    dispatch_release(d);
    nw_release(ctx);
    nw_release(meta);
}

static void write_bar(const std::string& sym, double ep, double o, double h,
                      double l, double c, double v) {
    FILE* f = fopen(bars_path(sym).c_str(), "a");
    if (!f) return;
    fprintf(f, "%.0f %.4f %.4f %.4f %.4f %.0f\n", ep, o, h, l, c, v);
    fclose(f);
    printf("%s bar %.0f c=%.4f v=%.0f\n", sym.c_str(), ep, c, v);
    fflush(stdout);
}

// ---- SELF-AGG: bar 1m armado de los trades en vivo, emitido al cerrar el
// minuto (+250ms de gracia para stragglers). El canal "bars" oficial queda
// de respaldo: el reader dedupe-a por epoch, el primero que llega gana.
// Nota: agregamos todos los prints entregados; el bar oficial filtra algunas
// condiciones SIP — diferencias de centavos/volumen, irrelevantes para BB/RSI.
struct AggBar { double ep = 0, o = 0, h = 0, l = 0, c = 0, v = 0; };
static std::map<std::string, AggBar> g_agg;         // solo en g_q

static void agg_trade(const std::string& sym, double p, double sz, time_t now) {
    double ep = (double)(now - now % 60);
    AggBar& a = g_agg[sym];
    if (a.ep != ep) {
        if (a.ep > 0 && a.c > 0)                     // minuto previo -> fuera ya
            write_bar(sym, a.ep, a.o, a.h, a.l, a.c, a.v);
        a = AggBar{ep, p, p, p, p, 0};
    }
    a.h = std::max(a.h, p); a.l = std::min(a.l, p); a.c = p; a.v += sz;
}

static void agg_flush(time_t now) {                  // timer 250ms en g_q
    for (auto& [sym, a] : g_agg)
        if (a.ep > 0 && a.c > 0 && (double)now >= a.ep + 60) {
            write_bar(sym, a.ep, a.o, a.h, a.l, a.c, a.v);
            a.ep = -a.ep;                            // marcado emitido
        }
}

static void handle_msg(const std::string& m) {
    if (m.find("\"msg\":\"connected\"") != std::string::npos) {
        fprintf(stderr, "ws: connected -> auth\n");
        ws_send("{\"action\":\"auth\",\"key\":\"" + KEY +
                "\",\"secret\":\"" + SEC + "\"}");
        return;
    }
    if (m.find("\"msg\":\"authenticated\"") != std::string::npos) {
        std::string list;
        for (auto& s : g_syms) list += (list.empty() ? "\"" : ",\"") + s + "\"";
        fprintf(stderr, "ws: authenticated -> subscribe bars [%s]\n", list.c_str());
        ws_send("{\"action\":\"subscribe\",\"bars\":[" + list + "]}");
        return;
    }
    if (m.find("\"T\":\"subscription\"") != std::string::npos) {
        g_subscribed = true;
        fprintf(stderr, "ws: subscribed OK: %.300s\n", m.c_str());
        return;
    }
    if (m.find("\"T\":\"error\"") != std::string::npos) {
        fprintf(stderr, "ws ERROR: %.300s\n", m.c_str());
        return;
    }
    // trade ticks del watchlist: {"T":"t","S":"RXT","p":5.41,...} ->
    // data/quote_<sym>.txt "EPOCH PRICE" (throttle 1/s por simbolo)
    size_t k = 0;
    while ((k = m.find("\"T\":\"t\"", k)) != std::string::npos) {
        size_t beg = m.rfind('{', k);
        size_t end = m.find('}', k);
        if (beg == std::string::npos || end == std::string::npos) break;
        std::string obj = m.substr(beg, end - beg + 1);
        k = end + 1;
        size_t sq = obj.find("\"S\":\"");
        double p = 0;
        if (sq == std::string::npos || !num_key(obj, "p", p) || p <= 0) continue;
        std::string sym = obj.substr(sq + 5, obj.find('"', sq + 5) - (sq + 5));
        time_t now = time(nullptr);
        // syms de la flota: armar el bar 1m nosotros (emision al cierre)
        for (auto& fs : g_syms)
            if (fs == sym) { double sz = 0; num_key(obj, "s", sz); agg_trade(sym, p, sz, now); break; }
        if (now == g_qwrite[sym]) continue;
        g_qwrite[sym] = now;
        FILE* f = fopen(("data/quote_" + lower(sym) + ".txt").c_str(), "w");
        if (f) { fprintf(f, "%ld %.4f\n", (long)now, p); fclose(f); }
    }
    // bar objects: {"T":"b","S":"NOK","o":..,"h":..,"l":..,"c":..,"v":..,"t":"..Z",..}
    size_t i = 0;
    while ((i = m.find("\"T\":\"b\"", i)) != std::string::npos) {
        size_t beg = m.rfind('{', i);
        size_t end = m.find('}', i);
        if (beg == std::string::npos || end == std::string::npos) break;
        std::string obj = m.substr(beg, end - beg + 1);
        i = end + 1;
        size_t sq = obj.find("\"S\":\"");
        size_t tq = obj.find("\"t\":\"");
        if (sq == std::string::npos || tq == std::string::npos) continue;
        std::string sym = obj.substr(sq + 5, obj.find('"', sq + 5) - (sq + 5));
        double ep = iso_epoch(obj.c_str() + tq + 5);
        double o = 0, h = 0, l = 0, c = 0, v = 0;
        num_key(obj, "o", o); num_key(obj, "h", h); num_key(obj, "l", l);
        num_key(obj, "c", c); num_key(obj, "v", v);
        if (ep > 0 && c > 0) write_bar(sym, ep, o, h, l, c, v);
    }
}

static void arm_receive() {
    nw_connection_receive_message(g_conn,
        ^(dispatch_data_t content, nw_content_context_t, bool, nw_error_t err) {
            if (content) {
                const void* buf = nullptr; size_t len = 0;
                dispatch_data_t map = dispatch_data_create_map(content, &buf, &len);
                g_last_msg = time(nullptr);
                handle_msg(std::string((const char*)buf, len));
                dispatch_release(map);
            }
            if (err) nw_connection_cancel(g_conn);   // state handler signals g_dead
            else arm_receive();
        });
}

static void run_connection() {
    g_subscribed = false;
    g_last_msg = time(nullptr);
    dispatch_async(g_q, ^{ g_trades.clear(); });   // re-suscribir tras reconectar
    nw_endpoint_t ep =
        nw_endpoint_create_url("wss://stream.data.alpaca.markets/v2/iex");
    nw_parameters_t params = nw_parameters_create_secure_tcp(
        NW_PARAMETERS_DEFAULT_CONFIGURATION, NW_PARAMETERS_DEFAULT_CONFIGURATION);
    nw_protocol_stack_t stack = nw_parameters_copy_default_protocol_stack(params);
    nw_protocol_options_t ws = nw_ws_create_options(nw_ws_version_13);
    nw_ws_options_set_auto_reply_ping(ws, true);
    nw_protocol_stack_prepend_application_protocol(stack, ws);
    g_conn = nw_connection_create(ep, params);
    nw_release(ws); nw_release(stack); nw_release(params); nw_release(ep);

    nw_connection_set_queue(g_conn, g_q);
    nw_connection_set_state_changed_handler(g_conn,
        ^(nw_connection_state_t st, nw_error_t err) {
            if (st == nw_connection_state_ready)
                fprintf(stderr, "ws: tcp/tls/upgrade ready\n");
            if (st == nw_connection_state_failed ||
                st == nw_connection_state_cancelled) {
                if (err) fprintf(stderr, "ws: died (%d)\n", nw_error_get_error_code(err));
                dispatch_semaphore_signal(g_dead);
            }
        });
    nw_connection_start(g_conn);
    arm_receive();

    // stall watchdog: en RTH un silencio largo = conexion zombi -> reconectar.
    // (los pings del server se auto-responden y no cuentan como mensaje, por
    // eso el umbral es generoso: 300s sin NADA en horario 9:30-16:00)
    while (true) {
        if (!dispatch_semaphore_wait(
                g_dead, dispatch_time(DISPATCH_TIME_NOW, 10 * NSEC_PER_SEC)))
            break;                                   // murio de verdad
        dispatch_async(g_q, ^{ check_watch(); });    // trades del watchlist
        time_t now = time(nullptr); struct tm lt; localtime_r(&now, &lt);
        bool rth = lt.tm_wday >= 1 && lt.tm_wday <= 5 &&
                   (lt.tm_hour > 9 || (lt.tm_hour == 9 && lt.tm_min >= 30)) &&
                   lt.tm_hour < 16;
        if (rth && g_subscribed && now - g_last_msg > 300) {
            fprintf(stderr, "ws: 300s sin mensajes en RTH -> reconectar\n");
            nw_connection_cancel(g_conn);            // dispara g_dead
        }
    }
    nw_release(g_conn); g_conn = nullptr;
}

static int daemon_main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) g_syms.push_back(argv[i]);
    g_q = dispatch_queue_create("ws", DISPATCH_QUEUE_SERIAL);
    g_dead = dispatch_semaphore_create(0);
    // archivo limpio por arranque: los readers dedupe-an por epoch y el
    // warm-up historico viene del REST del reader, no de este archivo
    for (auto& s : g_syms) { FILE* f = fopen(bars_path(s).c_str(), "w"); if (f) fclose(f); }
    fprintf(stderr, "alpaca_ws_bridge daemon: %zu syms, feed iex, canal bars "
                    "+ SELF-AGG de trades (bar emitido <=250ms tras cerrar el minuto)\n",
            g_syms.size());
    // timer 250ms: emite el bar formado apenas su minuto cierra
    dispatch_source_t tm = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, g_q);
    dispatch_source_set_timer(tm, DISPATCH_TIME_NOW, 250 * NSEC_PER_MSEC, 50 * NSEC_PER_MSEC);
    dispatch_source_set_event_handler(tm, ^{ agg_flush(time(nullptr)); });
    dispatch_resume(tm);
    while (true) {
        run_connection();
        fprintf(stderr, "ws: reintento en 3s\n");
        sleep(3);
    }
}

// ============================ reader (per bot) ==============================
static size_t sink(void* d, size_t s, size_t n, void* u) {
    ((std::string*)u)->append((char*)d, s * n);
    return s * n;
}

static bool http_get(const std::string& url, std::string& body) {
    CURL* c = curl_easy_init();
    if (!c) return false;
    struct curl_slist* h = nullptr;
    h = curl_slist_append(h, ("APCA-API-KEY-ID: " + KEY).c_str());
    h = curl_slist_append(h, ("APCA-API-SECRET-KEY: " + SEC).c_str());
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_HTTPHEADER, h);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, 15L);
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, sink);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &body);
    CURLcode rc = curl_easy_perform(c);
    long code = 0;
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &code);
    curl_slist_free_all(h);
    curl_easy_cleanup(c);
    if (rc != CURLE_OK) { fprintf(stderr, "curl: %s\n", curl_easy_strerror(rc)); return false; }
    if (code != 200) { fprintf(stderr, "http %ld: %.150s\n", code, body.c_str()); return false; }
    return true;
}

static double backfill(const std::string& sym) {   // returns last epoch emitted
    // warm-up UNA vez: ~3 dias de bares 1m para calentar BB/RSI/ATR/Donchian.
    // REST es inevitable aqui — el ws no sirve historia.
    time_t start = time(nullptr) - 3 * 86400;
    char iso[32]; struct tm g; gmtime_r(&start, &g);
    strftime(iso, sizeof(iso), "%Y-%m-%dT%H:%M:%SZ", &g);
    std::string body, url =
        "https://data.alpaca.markets/v2/stocks/" + sym +
        "/bars?timeframe=1Min&feed=iex&limit=10000&start=" + iso;
    double last = 0;
    if (!http_get(url, body)) return 0;
    size_t i = 0;
    while ((i = body.find("\"t\":\"", i)) != std::string::npos) {
        size_t end = body.find('}', i);
        size_t beg = body.rfind('{', i);
        if (end == std::string::npos || beg == std::string::npos) break;
        std::string obj = body.substr(beg, end - beg + 1);
        i = end + 1;
        double ep = iso_epoch(obj.c_str() + obj.find("\"t\":\"") + 5);
        double o = 0, h = 0, l = 0, c = 0, v = 0;
        num_key(obj, "o", o); num_key(obj, "h", h); num_key(obj, "l", l);
        num_key(obj, "c", c); num_key(obj, "v", v);
        if (ep > last && c > 0 && ep + 63 <= (double)time(nullptr)) {
            printf("%.0f %.4f %.4f %.4f %.4f %.0f\n", ep, o, h, l, c, v);
            last = ep;
        }
    }
    return last;
}

static int reader_main(const std::string& sym) {
    setvbuf(stdout, nullptr, _IOLBF, 0);   // line-buffered al pipe del bot
    fprintf(stderr, "%s reader: warm-up REST + follow %s (ws daemon)\n",
            sym.c_str(), bars_path(sym).c_str());
    double last = backfill(sym);
    std::string path = bars_path(sym);
    long off = 0;
    while (true) {
        struct stat st;
        if (stat(path.c_str(), &st) == 0) {
            if (st.st_size < off) off = 0;         // daemon reinicio/truncado
            if (st.st_size > off) {
                FILE* f = fopen(path.c_str(), "r");
                if (f) {
                    fseek(f, off, SEEK_SET);
                    char line[256];
                    while (fgets(line, sizeof(line), f)) {
                        size_t L = strlen(line);
                        if (!L || line[L - 1] != '\n') break;   // linea a medias
                        off = ftell(f);
                        double t, o, h, l, c, v;
                        if (sscanf(line, "%lf %lf %lf %lf %lf %lf",
                                   &t, &o, &h, &l, &c, &v) == 6 && t > last) {
                            printf("%.0f %.4f %.4f %.4f %.4f %.0f\n", t, o, h, l, c, v);
                            last = t;
                        }
                    }
                    fclose(f);
                }
            }
        }
        usleep(50000);    // 50ms: el daemon emite el bar <=250ms tras el cierre
    }
}

int main(int argc, char** argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: alpaca_ws_bridge SYM [SYM..]   (daemon)\n"
                        "       alpaca_ws_bridge read SYM      (bot reader)\n");
        return 2;
    }
    curl_global_init(CURL_GLOBAL_DEFAULT);
    load_keys();
    if (KEY.empty() || SEC.empty()) { fprintf(stderr, "no alpaca.env keys\n"); return 1; }
    if (!strcmp(argv[1], "read") && argc >= 3) return reader_main(argv[2]);
    return daemon_main(argc, argv);
}
