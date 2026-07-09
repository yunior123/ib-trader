// topgainer_alert.cpp — C++ port of alert_bot.py (Yunior 2026-07-09: avoid python).
// Watches today's watchlist and fires BUY-CONSIDER signals to the Mac + the
// Claude decision session (signals.jsonl) when a candidate makes a fresh
// intraday high with real gain inside the execution window. Never places orders.
//
// Behavior parity with alert_bot.py:
//   poll ALERT_POLL (2s) | window ALERT_WIN_START/END (09:30-10:00, Mon-Fri)
//   signal when: px > running-high AND in window AND gain>=5% AND once per sym/day
// Notifications: Mac osascript banner only (ntfy removed fleet-wide 2026-07-09).
//
// Build: clang++ -std=c++17 -O2 -o topgainer_alert topgainer_alert.cpp -lcurl
// Run from repo root: ./topgainer/topgainer_alert

#include <curl/curl.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

static double envd(const char* k, double d) { const char* v = getenv(k); return v && *v ? atof(v) : d; }
static std::string envs(const char* k, const char* d) { const char* v = getenv(k); return v && *v ? v : d; }
static const double POLL = envd("ALERT_POLL", 2.0);
static const std::string WIN_START = envs("ALERT_WIN_START", "09:30");
static const std::string WIN_END = envs("ALERT_WIN_END", "10:00");
static const double MIN_GAIN = envd("ALERT_MIN_GAIN", 5.0);
static const char* SIGNALS = "data/topgainer/signals.jsonl";

static void sh_sanitize(const char* in, char* out, size_t n) {
    size_t o = 0;
    for (size_t i = 0; in[i] && o + 1 < n; i++) {
        char c = in[i];
        if (c == '"' || c == '\'' || c == '\\' || c == '`' || c == '$') c = ' ';
        out[o++] = c;
    }
    out[o] = 0;
}
static std::string now_iso() {
    time_t t = time(nullptr); struct tm lt; localtime_r(&t, &lt);
    char b[64]; strftime(b, sizeof(b), "%Y-%m-%dT%H:%M:%S%z", &lt);
    return b;
}
static void notify(const char* title, const char* msg) {
    char st[128], sm[400], cmd[1024];
    sh_sanitize(title, st, sizeof(st)); sh_sanitize(msg, sm, sizeof(sm));
    snprintf(cmd, sizeof(cmd),
        "osascript -e 'display notification \"%s\" with title \"%s\" sound name \"Glass\"' "
        ">/dev/null 2>&1 &", sm, st);
    std::system(cmd);
}

static bool in_window() {
    time_t t = time(nullptr); struct tm lt; localtime_r(&t, &lt);
    if (lt.tm_wday == 0 || lt.tm_wday == 6) return false;      // weekend
    char hm[6]; strftime(hm, sizeof(hm), "%H:%M", &lt);
    return WIN_START <= std::string(hm) && std::string(hm) <= WIN_END;
}

// ---------- price (Finnhub REST; c=last, pc=prev close) ----------
static size_t curl_sink(void* d, size_t s, size_t n, void* u) {
    ((std::string*)u)->append((char*)d, s * n);
    return s * n;
}
static bool extract_num(const std::string& j, const char* key, double& out, size_t from = 0) {
    std::string k = std::string("\"") + key + "\"";
    size_t i = j.find(k, from);
    if (i == std::string::npos) return false;
    i = j.find(':', i);
    if (i == std::string::npos) return false;
    out = atof(j.c_str() + i + 1);
    return true;
}
static std::string finnhub_key() {
    static std::string key = [] {
        std::ifstream f("feeds.env"); std::string line, k;
        while (std::getline(f, line))
            if (line.rfind("FINNHUB_KEY=", 0) == 0) k = line.substr(12);
        while (!k.empty() && (k.back() == '"' || k.back() == '\r' || k.back() == ' ')) k.pop_back();
        if (!k.empty() && k.front() == '"') k.erase(0, 1);
        return k;
    }();
    return key;
}
static bool quote(const std::string& sym, double& px, double& prev_close) {
    std::string key = finnhub_key();
    if (key.empty()) return false;
    std::string url = "https://finnhub.io/api/v1/quote?symbol=" + sym + "&token=" + key, body;
    CURL* c = curl_easy_init();
    if (!c) return false;
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_TIMEOUT, 4L);
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, curl_sink);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &body);
    CURLcode rc = curl_easy_perform(c);
    curl_easy_cleanup(c);
    if (rc != CURLE_OK) return false;
    px = prev_close = 0;
    extract_num(body, "c", px);
    extract_num(body, "pc", prev_close);
    return px > 0;
}

// ---------- watchlist: data/topgainer/watchlist_YYYYMMDD.json ----------
struct Cand { std::string sym; double price = 0, score = 0; };
static std::vector<Cand> read_watchlist(const std::string& day) {
    std::vector<Cand> out;
    std::ifstream f("data/topgainer/watchlist_" + day + ".json");
    if (!f) return out;
    std::stringstream ss; ss << f.rdbuf();
    std::string j = ss.str();
    size_t i = 0;
    while ((i = j.find("\"sym\"", i)) != std::string::npos) {
        size_t a = j.find('"', j.find(':', i) + 1);
        size_t b = j.find('"', a + 1);
        if (a == std::string::npos || b == std::string::npos) break;
        Cand c;
        c.sym = j.substr(a + 1, b - a - 1);
        extract_num(j, "price", c.price, b);
        extract_num(j, "score", c.score, b);
        if (!c.sym.empty()) out.push_back(c);
        i = b + 1;
    }
    return out;
}

static void append_signal(const Cand& c, double px, double gain) {
    FILE* f = fopen(SIGNALS, "a");
    if (!f) return;
    fprintf(f, "{\"ts\": \"%s\", \"kind\": \"buy_consider\", \"sym\": \"%s\", "
               "\"price\": %.4f, \"gain_pct\": %.2f, \"watchlist_score\": %.2f, "
               "\"note\": \"fresh intraday high in window\"}\n",
            now_iso().c_str(), c.sym.c_str(), px, gain, c.score);
    fclose(f);
}

int main() {
    curl_global_init(CURL_GLOBAL_DEFAULT);
    printf("[alert-c++] up. window %s-%s ET, poll %.1fs, min gain %.1f%%\n",
           WIN_START.c_str(), WIN_END.c_str(), POLL, MIN_GAIN);
    fflush(stdout);
    std::map<std::string, double> highs;   // sym -> running intraday high
    std::set<std::string> fired;           // one BUY-CONSIDER per sym per day
    std::string day;
    while (true) {
        time_t t = time(nullptr); struct tm lt; localtime_r(&t, &lt);
        char today[16]; strftime(today, sizeof(today), "%Y%m%d", &lt);
        if (day != today) { day = today; highs.clear(); fired.clear(); }
        for (const Cand& c : read_watchlist(day)) {
            double px = 0, pc = 0;
            if (!quote(c.sym, px, pc)) continue;
            double ref = pc > 0 ? pc : (c.price > 0 ? c.price : px);
            double gain = ref > 0 ? (px - ref) / ref * 100.0 : 0;
            double prev_high = highs.count(c.sym) ? highs[c.sym] : (c.price > 0 ? c.price : px);
            if (px > prev_high) {
                highs[c.sym] = px;
                if (in_window() && !fired.count(c.sym) && gain >= MIN_GAIN) {
                    fired.insert(c.sym);
                    char msg[240];
                    snprintf(msg, sizeof(msg),
                             "%s rompe maximo intradia $%.4f (+%.1f%%). Candidato de compra — claude evalua.",
                             c.sym.c_str(), px, gain);
                    notify("BUY-CONSIDER", msg);
                    append_signal(c, px, gain);
                    printf("[alert-c++] SIGNAL %s $%.4f +%.1f%%\n", c.sym.c_str(), px, gain);
                    fflush(stdout);
                }
            }
        }
        usleep((useconds_t)(POLL * 1e6));
    }
}
