// topgainer_watchdog.cpp — C++ port of the per-second position guard.
// Yunior 2026-07-09: "replace by c++ as much as possible... python is too slow,
// there is money in stake". This is the hot loop; IBKR order placement stays in
// Python (ib_insync has no C++ twin here) and is invoked as a subprocess only at
// the rare sell/reconcile moments.
//
// Behavior mirrors topgainer/watchdog.py EXACTLY (same env knobs, same math —
// parity-tested via --calc against day_trading_bot.floor_price/exit_limit_price):
//   STOP LOSS   px <= entry*(1-TG_STOP_PCT%)                  -> flatten now
//   TARGET      px >= exit_limit(entry)                        -> sell (profit)
//   TRAIL LOCK  peak retrace >= WATCHDOG_TRAIL% while >= floor -> sell
//   TIME STOP   held >= TG_MAX_HOLD_SEC (default 15 min)       -> flatten
//   DEAD-MAN    claude_alive stale > TG_DEADMAN_SEC w/ position-> flatten NOW
//   RECONCILE   every TG_RECONCILE_SEC vs IBKR (readonly)      -> clear ghosts
//   COOLDOWN    TG_SELL_RETRY_SEC between sell attempts        -> no spam
// Notifications: Mac osascript banner only (ntfy removed fleet-wide 2026-07-09).
//
// Build: clang++ -std=c++17 -O2 -o topgainer_watchdog topgainer_watchdog.cpp -lcurl
// Run from the repo root (keepalive does): ./topgainer/topgainer_watchdog

#include <curl/curl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <sstream>
#include <string>

// ---------- config (env, defaults identical to watchdog.py) ----------
static double envd(const char* k, double dflt) {
    const char* v = getenv(k);
    return v && *v ? atof(v) : dflt;
}
static const double POLL          = envd("WATCHDOG_POLL", 1.0);
static const double TRAIL_PCT     = envd("WATCHDOG_TRAIL", 1.5);
static const double STOP_PCT      = envd("TG_STOP_PCT", 3.0);
static const double MAX_HOLD      = envd("TG_MAX_HOLD_SEC", 900);
static const double DEADMAN       = envd("TG_DEADMAN_SEC", 240);
static const double RECONCILE_SEC = envd("TG_RECONCILE_SEC", 60);
static const double SELL_RETRY    = envd("TG_SELL_RETRY_SEC", 90);
static const double FLAT_DISCOUNT = 0.97;

// DEFAULT_CONFIG parity (day_trading_bot.py)
static const double MIN_PROFIT_PCT = 5.0;   // target: entry+5%
static const double FLOOR_PCT      = 1.0;   // floor: entry+1%
static const double COMM_FIXED     = 1.0;   // $1/order...
static const double COMM_CAP_PCT   = 0.5;   // ...capped at 0.5% of value

static const char* POSITION = "data/topgainer/position.json";
static const char* SIGNALS  = "data/topgainer/signals.jsonl";
static const char* ALIVE    = "data/topgainer/claude_alive";
static const char* EXECPY   = "topgainer/exec_trade.py";
static const char* VENV_PY  = "venv/bin/python";

// ---------- exit math (parity with day_trading_bot.py) ----------
static double order_commission(double value) {
    return std::fmin(COMM_FIXED, value * COMM_CAP_PCT / 100.0);
}
static double floor_price(double entry, double qty) {
    double f = entry * (1 + FLOOR_PCT / 100.0);
    double comm = order_commission(entry * qty);
    if (qty > 0 && comm > 0) f = std::fmax(f, (entry + (2 * comm) / qty) * 1.001);
    return f;
}
static double exit_limit_price(double entry, double qty) {
    double t = entry * (1 + MIN_PROFIT_PCT / 100.0);
    double comm = order_commission(entry * qty);
    if (qty > 0 && comm > 0) t = std::fmax(t, (entry + (2 * comm) / qty) * 1.001);
    return t;
}

// ---------- tiny helpers ----------
static std::string read_file(const char* p) {
    std::ifstream f(p);
    if (!f) return "";
    std::stringstream ss; ss << f.rdbuf();
    return ss.str();
}
static bool extract_num(const std::string& j, const char* key, double& out) {
    std::string k = std::string("\"") + key + "\"";
    size_t i = j.find(k);
    if (i == std::string::npos) return false;
    i = j.find(':', i);
    if (i == std::string::npos) return false;
    out = atof(j.c_str() + i + 1);
    return true;
}
static bool extract_str(const std::string& j, const char* key, std::string& out) {
    std::string k = std::string("\"") + key + "\"";
    size_t i = j.find(k);
    if (i == std::string::npos) return false;
    i = j.find(':', i);
    size_t a = j.find('"', i + 1);
    if (a == std::string::npos) return false;
    size_t b = j.find('"', a + 1);
    if (b == std::string::npos) return false;
    out = j.substr(a + 1, b - a - 1);
    return true;
}
static bool extract_bool(const std::string& j, const char* key, bool dflt) {
    std::string k = std::string("\"") + key + "\"";
    size_t i = j.find(k);
    if (i == std::string::npos) return dflt;
    return j.find("true", i) == j.find_first_not_of(": ", i + k.size());
}
static void sh_sanitize(const char* in, char* out, size_t n) {
    size_t o = 0;
    for (size_t i = 0; in[i] && o + 1 < n; i++) {
        char c = in[i];
        if (c == '"' || c == '\'' || c == '\\' || c == '`' || c == '$') c = ' ';
        if ((unsigned char)c < 0x20) c = ' ';   // newlines/CR/tab rompen el JSON de una linea
        out[o++] = c;
    }
    out[o] = 0;
}
static std::string run_capture(const std::string& cmd) {
    std::string out;
    FILE* p = popen((cmd + " 2>&1").c_str(), "r");
    if (!p) return out;
    char buf[512];
    while (fgets(buf, sizeof(buf), p)) out += buf;
    pclose(p);
    return out;
}
static std::string now_iso() {
    time_t t = time(nullptr); struct tm lt; localtime_r(&t, &lt);
    char b[64]; strftime(b, sizeof(b), "%Y-%m-%dT%H:%M:%S%z", &lt);
    return b;
}

// ---------- position state (atomic write, python-json compatible) ----------
struct Pos {
    std::string sym, opened;
    double qty = 0, entry = 0, peak = 0, last = 0, opened_ts = 0, last_sell_ts = 0;
    bool reached_floor = false, valid = false;
};
static Pos read_position() {
    Pos p;
    std::string j = read_file(POSITION);
    if (j.empty() || j.find('{') == std::string::npos) return p;
    if (!extract_str(j, "sym", p.sym)) return p;
    extract_num(j, "qty", p.qty);
    extract_num(j, "entry", p.entry);
    extract_num(j, "peak", p.peak);
    extract_num(j, "last", p.last);
    extract_num(j, "opened_ts", p.opened_ts);
    extract_num(j, "last_sell_ts", p.last_sell_ts);
    extract_str(j, "opened", p.opened);
    p.reached_floor = extract_bool(j, "reached_floor", false);
    if (p.peak <= 0) p.peak = p.entry;
    if (p.opened_ts <= 0 && !p.opened.empty()) {          // fallback: ISO local
        struct tm tmv{}; if (strptime(p.opened.c_str(), "%Y-%m-%dT%H:%M:%S", &tmv)) {
            tmv.tm_isdst = -1; p.opened_ts = (double)mktime(&tmv);
        }
    }
    p.valid = !p.sym.empty() && p.qty > 0 && p.entry > 0;
    return p;
}
static void write_position(const Pos& p) {
    char tmp[256]; snprintf(tmp, sizeof(tmp), "%s.tmp.%d", POSITION, getpid());
    FILE* f = fopen(tmp, "w");
    if (!f) return;
    fprintf(f,
        "{\n  \"sym\": \"%s\",\n  \"qty\": %d,\n  \"entry\": %.6f,\n"
        "  \"opened\": \"%s\",\n  \"opened_ts\": %.3f,\n  \"peak\": %.6f,\n"
        "  \"reached_floor\": %s,\n  \"last\": %.6f,\n  \"last_sell_ts\": %.3f\n}",
        p.sym.c_str(), (int)p.qty, p.entry, p.opened.c_str(), p.opened_ts,
        p.peak, p.reached_floor ? "true" : "false", p.last, p.last_sell_ts);
    fclose(f);
    rename(tmp, POSITION);
}

// ---------- notify: Mac banner + signals.jsonl (NO ntfy — Yunior 2026-07-09) ----------
static void append_signal(const char* title, const char* msg) {
    FILE* f = fopen(SIGNALS, "a");
    if (!f) return;
    char st[128], sm[400]; sh_sanitize(title, st, sizeof(st)); sh_sanitize(msg, sm, sizeof(sm));
    fprintf(f, "{\"ts\": \"%s\", \"kind\": \"watchdog\", \"title\": \"%s\", \"msg\": \"%s\"}\n",
            now_iso().c_str(), st, sm);
    fclose(f);
}
static void notify(const char* title, const char* msg) {
    char st[128], sm[400], cmd[1024];
    sh_sanitize(title, st, sizeof(st)); sh_sanitize(msg, sm, sizeof(sm));
    snprintf(cmd, sizeof(cmd),
        "osascript -e 'display notification \"%s\" with title \"%s\" sound name \"Glass\"' "
        ">/dev/null 2>&1 &", sm, st);
    std::system(cmd);
    append_signal(title, msg);
}

// ---------- price: Finnhub (libcurl, sub-second) -> price.py fallback ----------
static size_t curl_sink(void* d, size_t s, size_t n, void* u) {
    ((std::string*)u)->append((char*)d, s * n);
    return s * n;
}
static std::string finnhub_key() {
    static std::string key = [] {
        std::ifstream f("feeds.env"); std::string line, k;
        while (std::getline(f, line))
            if (line.rfind("FINNHUB_KEY=", 0) == 0) { k = line.substr(12); }
        while (!k.empty() && (k.back() == '"' || k.back() == '\r' || k.back() == ' ')) k.pop_back();
        if (!k.empty() && k.front() == '"') k.erase(0, 1);
        return k;
    }();
    return key;
}
static double last_price(const std::string& sym) {
    std::string key = finnhub_key();
    if (!key.empty()) {
        std::string url = "https://finnhub.io/api/v1/quote?symbol=" + sym + "&token=" + key, body;
        CURL* c = curl_easy_init();
        if (c) {
            curl_easy_setopt(c, CURLOPT_URL, url.c_str());
            curl_easy_setopt(c, CURLOPT_TIMEOUT, 4L);
            curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, curl_sink);
            curl_easy_setopt(c, CURLOPT_WRITEDATA, &body);
            CURLcode rc = curl_easy_perform(c);
            curl_easy_cleanup(c);
            if (rc == CURLE_OK) {
                double px = 0;
                if (extract_num(body, "c", px) && px > 0) return px;
            }
        }
    }
    // slow path: python price.py (Yahoo etc). Rare — only when Finnhub fails.
    std::string out = run_capture(std::string(VENV_PY) + " topgainer/price.py " + sym);
    size_t i = out.find("'price':");
    if (i != std::string::npos) { double px = atof(out.c_str() + i + 8); if (px > 0) return px; }
    return 0;
}

// ---------- sell / flatten / reconcile via exec_trade.py ----------
static bool sell(Pos& p, const std::string& reason, bool force, double limit) {
    double now = (double)time(nullptr);
    if (now - p.last_sell_ts < SELL_RETRY) return false;   // cooldown: no spam
    p.last_sell_ts = now;
    write_position(p);
    char cmd[1024];
    snprintf(cmd, sizeof(cmd), "%s %s sell %s %d --entry %.6f%s%s",
             VENV_PY, EXECPY, p.sym.c_str(), (int)p.qty, p.entry,
             limit > 0 ? (" --limit " + std::to_string(limit)).c_str() : "",
             force ? " --force-flat" : "");
    std::string out = run_capture(cmd);
    std::string m = reason + " — " + out.substr(0, 110);
    notify(("VENDER " + p.sym).c_str(), m.c_str());
    printf("[watchdog] SELL %s: %s\n%s\n", p.sym.c_str(), reason.c_str(), out.c_str());
    fflush(stdout);
    return true;
}
static bool flatten(Pos& p, const std::string& reason, double px) {
    return sell(p, reason, true, std::round(px * FLAT_DISCOUNT * 10000.0) / 10000.0);
}
static bool reconcile(const Pos& p) {   // true -> position cleared externally
    std::string out = run_capture(std::string(VENV_PY) + " " + EXECPY + " reconcile " + p.sym);
    if (out.find("CLEARED") != std::string::npos) {
        notify((p.sym + " vendido fuera del bot").c_str(),
               "IBKR ya no tiene las acciones — dejo de vigilar");
        printf("[watchdog] reconcile: %s\n", out.c_str()); fflush(stdout);
        return true;
    }
    if (out.find("ADJUSTED") != std::string::npos) {
        printf("[watchdog] reconcile: %s\n", out.c_str()); fflush(stdout);
    }
    return false;
}

int main(int argc, char** argv) {
    if (argc == 4 && strcmp(argv[1], "--calc") == 0) {     // parity-test hook
        double e = atof(argv[2]), q = atof(argv[3]);
        printf("%.10f %.10f\n", floor_price(e, q), exit_limit_price(e, q));
        return 0;
    }
    curl_global_init(CURL_GLOBAL_DEFAULT);
    printf("[watchdog-c++] up. poll=%.1fs trail=%.1f%% stop=%.1f%% max_hold=%ds "
           "deadman=%ds reconcile=%ds\n", POLL, TRAIL_PCT, STOP_PCT,
           (int)MAX_HOLD, (int)DEADMAN, (int)RECONCILE_SEC);
    fflush(stdout);
    double start = (double)time(nullptr), last_rec = 0;
    long idle = 0;
    while (true) {
        Pos p = read_position();
        if (!p.valid) {
            if (idle++ % 300 == 0) { printf("[watchdog-c++] no position, waiting\n"); fflush(stdout); }
            usleep((useconds_t)(POLL * 1e6));
            continue;
        }
        idle = 0;
        double now = (double)time(nullptr);

        // 1) broker truth — manual/external sells clear the ghost
        if (RECONCILE_SEC > 0 && now - last_rec >= RECONCILE_SEC) {
            last_rec = now;
            if (reconcile(p)) continue;
            p = read_position();                    // qty may have been adjusted
            if (!p.valid) continue;
        }

        // 2) dead-man — Claude Code silent while money at risk -> sell NOW
        struct stat st{};
        double alive = (stat(ALIVE, &st) == 0) ? (double)st.st_mtime : 0;
        double silent = now - std::fmax(alive, start);
        if (DEADMAN > 0 && silent > DEADMAN) {
            double px = last_price(p.sym);
            if (px <= 0) px = p.last > 0 ? p.last : p.entry;
            char r[160]; snprintf(r, sizeof(r), "DEADMAN: Claude sin responder %ds — vendo ya", (int)silent);
            if (flatten(p, r, px)) { printf("[watchdog-c++] DEADMAN fired for %s\n", p.sym.c_str()); fflush(stdout); }
            usleep((useconds_t)(POLL * 1e6));
            continue;
        }

        // 3) manage: stop -> target -> trail -> time-stop (first match wins)
        double px = last_price(p.sym);
        if (px > 0) {
            double flr = floor_price(p.entry, p.qty);
            double tgt = exit_limit_price(p.entry, p.qty);
            double stop = p.entry * (1 - STOP_PCT / 100.0);
            if (px > p.peak) p.peak = px;
            if (px >= flr) p.reached_floor = true;
            p.last = px;
            write_position(p);
            char r[200];
            if (px <= stop) {
                snprintf(r, sizeof(r), "STOP-LOSS px %.4f <= %.4f (-%.1f%%)", px, stop, STOP_PCT);
                flatten(p, r, px);
            } else if (px >= tgt) {
                snprintf(r, sizeof(r), "target hit px %.4f >= %.4f", px, tgt);
                sell(p, r, false, 0);
            } else if (p.reached_floor && px >= flr &&
                       p.peak > 0 && (p.peak - px) / p.peak * 100.0 >= TRAIL_PCT) {
                snprintf(r, sizeof(r), "trail lock px %.4f (peak %.4f) >= floor %.4f", px, p.peak, flr);
                sell(p, r, false, 0);
            } else if (p.opened_ts > 0 && now - p.opened_ts >= MAX_HOLD) {
                snprintf(r, sizeof(r), "TIME-STOP %ds cumplidos px %.4f (entry %.4f)", (int)MAX_HOLD, px, p.entry);
                flatten(p, r, px);
            }
        }
        usleep((useconds_t)(POLL * 1e6));
    }
}
