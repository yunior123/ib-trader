// x_whale_bot.cpp — daily X (Twitter) semiconductor/whale post for ib-trader.
// SEÑAL-SOLAMENTE (ley #0): cero ordenes al broker. Solo datos + 1 post/dia.
//
// Budget discipline ($5/mo hard cap, 2026 pay-per-use X API):
//   post sin URL ≈ $0.015  → 30 posts/mes ≈ $0.45  (OK)
//   post con URL ≈ $0.20   → 30 posts/mes ≈ $6.00  (OVER — PROHIBIDO)
// Ledger: data/x_budget.txt  (YYYY-MM posts_count estimated_usd)
// Posts:  data/x_posts.jsonl
// Auth:   x.env (gitignored) X_BEARER_TOKEN y/o OAuth1 X_API_KEY/SECRET + ACCESS
//
// Fuente: Finviz Elite (FINVIZ_AUTH3 en feeds.env) o cache data/finviz_<sym>.txt
//         si fresca (<2h). Backup: columnas de cache existentes (IBKR no tiene
//         short float / rel vol de flota).
//
// Schedule: America/Toronto. --daemon espera 09:00 y postea 1x/dia laboral.
// Compilar: clang++ -std=c++17 -O2 -o x_whale_bot scripts/x_whale_bot.cpp \
//             -lcurl -lcrypto
// Uso:
//   ./x_whale_bot --dry-run          # compone, no gasta
//   ./x_whale_bot --post-now         # 1 post inmediato (si budget OK)
//   ./x_whale_bot --budget           # estado del mes
//   ./x_whale_bot --daemon           # loop 9:00 Toronto (skip fin de semana)
//   ./x_whale_bot --compose-only     # imprime texto y sale 0
#include "../fleet_notify.h"

#include <curl/curl.h>
#include <openssl/hmac.h>
#include <openssl/evp.h>
#include <openssl/buffer.h>
#include <openssl/rand.h>

#include <algorithm>
#include <cctype>
#include <cmath>
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

// ---------- log
static void logln(const std::string& s) {
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    char ts[32];
    snprintf(ts, sizeof(ts), "%04d-%02d-%02d %02d:%02d:%02d", lt.tm_year + 1900,
             lt.tm_mon + 1, lt.tm_mday, lt.tm_hour, lt.tm_min, lt.tm_sec);
    printf("%s | %s\n", ts, s.c_str());
    fflush(stdout);
}

// ---------- helpers
static std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}
static std::string upper(std::string s) {
    for (auto& c : s) c = (char)toupper((unsigned char)c);
    return s;
}
static std::string lower(std::string s) {
    for (auto& c : s) c = (char)tolower((unsigned char)c);
    return s;
}

static std::map<std::string, std::string> read_env_file(const char* path) {
    std::map<std::string, std::string> m;
    std::ifstream f(path);
    std::string line;
    while (std::getline(f, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        std::string k = trim(line.substr(0, eq));
        std::string v = trim(line.substr(eq + 1));
        if (!v.empty() && (v.front() == '"' || v.front() == '\'')) v = v.substr(1);
        if (!v.empty() && (v.back() == '"' || v.back() == '\'')) v.pop_back();
        m[k] = v;
    }
    return m;
}

static std::string env_or_file(const std::string& key,
                               const std::map<std::string, std::string>& file) {
    const char* e = getenv(key.c_str());
    if (e && *e) return e;
    auto it = file.find(key);
    if (it != file.end()) return it->second;
    return "";
}

static double parse_double(const std::string& raw) {
    std::string s;
    for (char c : raw)
        if (c != '%' && c != ',' && c != '$' && c != ' ') s += c;
    if (s.empty() || s == "-") return NAN;
    char* end = nullptr;
    double v = strtod(s.c_str(), &end);
    if (end == s.c_str()) return NAN;
    return v;
}

// ---------- budget ledger
struct Budget {
    std::string yyyymm;
    int posts = 0;
    double spent = 0.0;
    double cap = 5.0;
    double cost_no_url = 0.015;
    double cost_url = 0.20;
    int max_day = 1;
    int max_month = 30;
};

static std::string yyyymm_now() {
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    char b[16];
    snprintf(b, sizeof(b), "%04d-%02d", lt.tm_year + 1900, lt.tm_mon + 1);
    return b;
}
static std::string yyyymmdd_now() {
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    char b[16];
    snprintf(b, sizeof(b), "%04d-%02d-%02d", lt.tm_year + 1900, lt.tm_mon + 1,
             lt.tm_mday);
    return b;
}

static Budget load_budget(const std::map<std::string, std::string>& xenv) {
    Budget b;
    b.yyyymm = yyyymm_now();
    auto d = [&](const char* k, double def) {
        std::string v = env_or_file(k, xenv);
        if (v.empty()) return def;
        return parse_double(v);
    };
    auto i = [&](const char* k, int def) {
        std::string v = env_or_file(k, xenv);
        if (v.empty()) return def;
        return (int)parse_double(v);
    };
    b.cap = d("X_MONTHLY_BUDGET_USD", 5.0);
    b.cost_no_url = d("X_COST_POST_NO_URL", 0.015);
    b.cost_url = d("X_COST_POST_WITH_URL", 0.20);
    b.max_day = i("X_MAX_POSTS_PER_DAY", 1);
    b.max_month = i("X_MAX_POSTS_PER_MONTH", 30);

    std::ifstream f("data/x_budget.txt");
    std::string ym;
    int posts = 0;
    double spent = 0;
    if (f >> ym >> posts >> spent) {
        if (ym == b.yyyymm) {
            b.posts = posts;
            b.spent = spent;
        }
        // new month → zero (implicit)
    }
    return b;
}

static void save_budget(const Budget& b) {
    std::ofstream f("data/x_budget.txt", std::ios::trunc);
    f << b.yyyymm << " " << b.posts << " " << b.spent << "\n";
}

static int posts_today() {
    std::string today = yyyymmdd_now();
    std::ifstream f("data/x_posts.jsonl");
    std::string line;
    int n = 0;
    while (std::getline(f, line)) {
        // only successful live posts burn the daily quota
        if (line.find(today) == std::string::npos) continue;
        if (line.find("\"mode\":\"live\"") == std::string::npos) continue;
        n++;
    }
    return n;
}

static bool has_url(const std::string& text) {
    std::string lo = lower(text);
    return lo.find("http://") != std::string::npos ||
           lo.find("https://") != std::string::npos ||
           lo.find("www.") != std::string::npos ||
           lo.find(" t.co/") != std::string::npos;
}

// ---------- fleet tickers (semiconductor-weighted + focus)
static std::vector<std::string> fleet_tickers() {
    std::vector<std::string> out;
    std::set<std::string> seen;
    auto add = [&](const std::string& raw) {
        std::string s = upper(trim(raw));
        if (s.empty()) return;
        std::string lo = lower(s);
        static const std::set<std::string> skip = {
            "kospi", "samsung", "skhynix", "sleep", "wake", "gld", "slv",
            "cper", "uso"};
        if (skip.count(lo)) return;
        for (char c : s)
            if (!isalpha((unsigned char)c) && c != '.' && c != '-') return;
        if (s.size() > 5) return;
        if (seen.insert(s).second) out.push_back(s);
    };
    std::ifstream f("data/focus_ticker");
    std::string line;
    while (std::getline(f, line)) {
        std::stringstream ss(line);
        std::string tok;
        while (std::getline(ss, tok, ',')) {
            std::stringstream ws(tok);
            std::string w;
            while (ws >> w) add(w);
        }
    }
    // full semis + mega tech always in the whale universe
    for (const char* s :
         {"NVDA", "AMD", "INTC", "TSM", "ASML", "MU", "SMH", "TXN", "AVGO",
          "QCOM", "SKHY", "DRAM", "SPCX", "NOK", "AAPL", "MSFT", "AMZN", "META",
          "GOOGL", "QQQ", "TSLA"})
        add(s);
    return out;
}

// ---------- Finviz row
struct Row {
    std::string ticker;
    double price = NAN;
    double change = NAN;
    double gap = NAN;
    double rel_vol = NAN;
    double short_float = NAN;
    double volume = NAN;
    double avg_vol = NAN;
    double target = NAN;
    double recom = NAN;
    double inst_own = NAN;    // institutional ownership %
    double inst_trans = NAN;  // recent inst transaction %
    double ah_change = NAN;   // after-hours change %
    double score = 0;
};

static std::map<std::string, std::string> read_kv_file(const std::string& path) {
    std::map<std::string, std::string> m;
    std::ifstream f(path);
    std::string line;
    while (std::getline(f, line)) {
        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        m[trim(line.substr(0, eq))] = trim(line.substr(eq + 1));
    }
    return m;
}

static bool cache_fresh(const std::string& path, int max_age_sec) {
    std::ifstream f(path);
    if (!f) return false;
    auto kv = read_kv_file(path);
    auto it = kv.find("ts");
    if (it == kv.end()) return false;
    time_t ts = (time_t)strtoll(it->second.c_str(), nullptr, 10);
    if (ts <= 0) return false;
    return (time(nullptr) - ts) <= max_age_sec;
}

static Row row_from_kv(const std::map<std::string, std::string>& kv) {
    Row r;
    auto g = [&](const char* k) -> std::string {
        auto it = kv.find(k);
        return it == kv.end() ? "" : it->second;
    };
    r.ticker = upper(g("ticker"));
    r.price = parse_double(g("price"));
    r.change = parse_double(g("change"));
    r.gap = parse_double(g("gap"));
    r.rel_vol = parse_double(g("relative_volume"));
    r.short_float = parse_double(g("short_float"));
    r.volume = parse_double(g("volume"));
    r.avg_vol = parse_double(g("average_volume"));
    r.target = parse_double(g("target_price"));
    r.recom = parse_double(g("analyst_recom"));
    r.inst_own = parse_double(g("institutional_ownership"));
    if (std::isnan(r.inst_own)) r.inst_own = parse_double(g("inst_own"));
    r.inst_trans = parse_double(g("institutional_transactions"));
    if (std::isnan(r.inst_trans)) r.inst_trans = parse_double(g("inst_trans"));
    r.ah_change = parse_double(g("after_hours_change"));
    if (std::isnan(r.ah_change)) r.ah_change = parse_double(g("ah_change"));
    return r;
}

// HTTP
static size_t curl_sink(char* p, size_t sz, size_t nm, void* ud) {
    ((std::string*)ud)->append(p, sz * nm);
    return sz * nm;
}
struct HttpResp {
    long code = 0;
    std::string body;
    bool ok = false;
};

static HttpResp http_get(const std::string& url) {
    HttpResp r;
    CURL* c = curl_easy_init();
    if (!c) return r;
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, curl_sink);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &r.body);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(c, CURLOPT_CONNECTTIMEOUT, 10L);
    curl_easy_setopt(c, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(c, CURLOPT_USERAGENT, "ib-trader x_whale_bot/1.0");
    curl_easy_setopt(c, CURLOPT_ACCEPT_ENCODING, "");
    CURLcode rc = curl_easy_perform(c);
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &r.code);
    curl_easy_cleanup(c);
    r.ok = (rc == CURLE_OK);
    return r;
}

static std::vector<std::string> csv_split(const std::string& line) {
    std::vector<std::string> out;
    std::string cur;
    bool q = false;
    for (size_t i = 0; i < line.size(); i++) {
        char c = line[i];
        if (q) {
            if (c == '"') {
                if (i + 1 < line.size() && line[i + 1] == '"') {
                    cur += '"';
                    i++;
                } else
                    q = false;
            } else
                cur += c;
        } else {
            if (c == '"')
                q = true;
            else if (c == ',') {
                out.push_back(cur);
                cur.clear();
            } else if (c != '\r')
                cur += c;
        }
    }
    out.push_back(cur);
    return out;
}

static std::string finviz_token() {
    auto feeds = read_env_file("feeds.env");
    for (const char* k : {"FINVIZ_AUTH3", "FINVIZ_AUTH"}) {
        std::string v = env_or_file(k, feeds);
        if (!v.empty()) return v;
    }
    return "";
}

// Claude-way Finviz: cache-first (scout already rate-limited), live export only
// if cache cold. Extra whale cols: Inst Own/Trans, AH when present.
static bool cache_universe_fresh(const std::vector<std::string>& syms,
                                 int max_age_sec, int min_hits) {
    int hits = 0;
    for (auto& s : syms) {
        std::string path = "data/finviz_" + lower(s) + ".txt";
        if (cache_fresh(path, max_age_sec)) hits++;
    }
    return hits >= min_hits;
}

static std::vector<Row> fetch_finviz_live(const std::vector<std::string>& syms) {
    std::vector<Row> rows;
    std::string token = finviz_token();
    if (token.empty()) {
        logln("FINVIZ: sin token — usando solo cache");
        return rows;
    }
    std::string tlist;
    for (auto& s : syms) tlist += (tlist.empty() ? "" : ",") + s;
    // scout base + whale extras (28 InstOwn 29 InstTrans 71 AH-Close 72 AH-Change)
    // header-name parse tolerates missing ids
    std::string url =
        "https://elite.finviz.com/export/screener?v=152&t=" + tlist +
        "&auth=" + token +
        "&c=1,6,24,25,26,28,29,30,31,59,60,61,62,63,64,65,66,67,68,69,70,71,72";
    HttpResp r = http_get(url);
    if (!r.ok || r.code != 200 || r.body.empty() || r.body[0] == '<' ||
        r.body.find("Ticker") == std::string::npos) {
        logln("FINVIZ ROTO live fetch code=" + std::to_string(r.code) +
              " — fallback cache");
        return rows;
    }
    std::stringstream body(r.body);
    std::string line;
    std::getline(body, line);
    auto header = csv_split(line);
    std::map<std::string, int> idx;
    for (int i = 0; i < (int)header.size(); i++) idx[header[i]] = i;
    auto col = [&](const std::vector<std::string>& f, const char* name) -> std::string {
        auto it = idx.find(name);
        if (it == idx.end() || it->second >= (int)f.size()) return "";
        return f[it->second];
    };
    auto col_find = [&](const std::vector<std::string>& f, const char* needle) -> std::string {
        for (auto& h : header) {
            if (h.find(needle) != std::string::npos) return col(f, h.c_str());
        }
        return "";
    };
    while (std::getline(body, line)) {
        if (trim(line).empty()) continue;
        auto f = csv_split(line);
        Row row;
        row.ticker = upper(col(f, "Ticker"));
        if (row.ticker.empty()) continue;
        row.price = parse_double(col(f, "Price"));
        row.change = parse_double(col(f, "Change"));
        row.gap = parse_double(col(f, "Gap"));
        row.rel_vol = parse_double(col(f, "Relative Volume"));
        row.short_float = parse_double(col(f, "Short Float"));
        row.volume = parse_double(col(f, "Volume"));
        row.avg_vol = parse_double(col(f, "Average Volume"));
        row.target = parse_double(col(f, "Target Price"));
        row.recom = parse_double(col_find(f, "Recom"));
        row.inst_own = parse_double(col_find(f, "Inst Own"));
        if (std::isnan(row.inst_own))
            row.inst_own = parse_double(col_find(f, "Institutional"));
        row.inst_trans = parse_double(col_find(f, "Inst Trans"));
        row.ah_change = parse_double(col_find(f, "After-Hours Change"));
        if (std::isnan(row.ah_change))
            row.ah_change = parse_double(col_find(f, "AH Change"));
        rows.push_back(row);
    }
    logln("FINVIZ live: " + std::to_string(rows.size()) + " filas (header-parsed)");
    return rows;
}

static std::vector<Row> load_from_cache(const std::vector<std::string>& syms) {
    std::vector<Row> rows;
    for (auto& s : syms) {
        std::string path = "data/finviz_" + lower(s) + ".txt";
        // also try upper (scout writes lower keys file name as finviz_NVDA?)
        if (!std::ifstream(path)) path = "data/finviz_" + s + ".txt";
        // scout uses lowercase ticker in filename: finviz_nvda.txt
        path = "data/finviz_" + lower(s) + ".txt";
        if (!std::ifstream(path)) continue;
        auto kv = read_kv_file(path);
        Row r = row_from_kv(kv);
        if (r.ticker.empty()) r.ticker = upper(s);
        rows.push_back(r);
    }
    logln("CACHE: " + std::to_string(rows.size()) + " filas");
    return rows;
}

// Session-aware scoring (Claude way): overnight RVOL ~0.1x is noise — weight
// gap/short/AH pre-open; full RVOL weight once RTH (or post 9:30 Toronto).
static bool is_rth_or_post() {
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    int m = lt.tm_hour * 60 + lt.tm_min;
    return m >= 9 * 60 + 30 && m < 16 * 60;
}

static void score_rows(std::vector<Row>& rows) {
    bool rth = is_rth_or_post();
    for (auto& r : rows) {
        double sc = 0;
        // RVOL: full weight in RTH; muted premarket (scout still tracks it)
        if (!std::isnan(r.rel_vol)) {
            double w = rth ? 1.0 : 0.35;
            if (r.rel_vol >= 3.0)
                sc += 40 * w;
            else if (r.rel_vol >= 2.0)
                sc += 28 * w;
            else if (r.rel_vol >= 1.5)
                sc += 16 * w;
            else if (r.rel_vol >= 1.2)
                sc += 8 * w;
        }
        // gap = primary premarket whale proxy
        if (!std::isnan(r.gap)) {
            double ag = fabs(r.gap);
            double w = rth ? 0.85 : 1.25;
            if (ag >= 3.0)
                sc += 25 * w;
            else if (ag >= 1.5)
                sc += 15 * w;
            else if (ag >= 0.8)
                sc += 8 * w;
        }
        // short float squeeze fuel
        if (!std::isnan(r.short_float)) {
            if (r.short_float >= 15)
                sc += 22;
            else if (r.short_float >= 8)
                sc += 14;
            else if (r.short_float >= 4)
                sc += 7;
        }
        // AH move (when Finviz returns it)
        if (!std::isnan(r.ah_change)) {
            double a = fabs(r.ah_change);
            if (a >= 3.0)
                sc += 18;
            else if (a >= 1.5)
                sc += 10;
            else if (a >= 0.8)
                sc += 5;
        }
        // day change magnitude
        if (!std::isnan(r.change)) {
            double ac = fabs(r.change);
            if (ac >= 3.0)
                sc += 12;
            else if (ac >= 1.5)
                sc += 6;
        }
        // institutional footprint
        if (!std::isnan(r.inst_trans) && fabs(r.inst_trans) >= 2.0)
            sc += 8;
        if (!std::isnan(r.inst_own) && r.inst_own >= 70)
            sc += 3;
        // semis preference (slight)
        static const std::set<std::string> semis = {
            "NVDA", "AMD", "INTC", "TSM", "ASML", "MU", "SMH", "TXN", "AVGO",
            "QCOM", "SKHY", "DRAM", "SPCX"};
        if (semis.count(r.ticker)) sc += 5;
        r.score = sc;
    }
    std::sort(rows.begin(), rows.end(),
              [](const Row& a, const Row& b) { return a.score > b.score; });
}

static std::string fmt_pct(double v) {
    if (std::isnan(v)) return "n/d";
    char b[32];
    snprintf(b, sizeof(b), "%+.1f%%", v);
    return b;
}
static std::string fmt_num(double v, int dec = 1) {
    if (std::isnan(v)) return "n/d";
    char b[32];
    if (dec <= 0)
        snprintf(b, sizeof(b), "%.0f", v);
    else if (dec == 1)
        snprintf(b, sizeof(b), "%.1f", v);
    else if (dec == 2)
        snprintf(b, sizeof(b), "%.2f", v);
    else
        snprintf(b, sizeof(b), "%.3f", v);
    return b;
}

// Compose post: NO URLs (budget). Max ~270 chars. Insight + fleet whale top.
static std::string compose_post(const std::vector<Row>& ranked) {
    std::string day = yyyymmdd_now();
    // top 3 with any signal
    std::vector<Row> top;
    for (auto& r : ranked) {
        if (r.score <= 0 && top.empty()) continue;
        top.push_back(r);
        if (top.size() >= 3) break;
    }
    if (top.empty() && !ranked.empty()) {
        // quiet day — still post fleet snapshot of top semis by |change|
        std::vector<Row> bychg = ranked;
        std::sort(bychg.begin(), bychg.end(), [](const Row& a, const Row& b) {
            double ac = std::isnan(a.change) ? 0 : fabs(a.change);
            double bc = std::isnan(b.change) ? 0 : fabs(b.change);
            return ac > bc;
        });
        for (size_t i = 0; i < bychg.size() && top.size() < 3; i++)
            top.push_back(bychg[i]);
    }

    // X free/pay-per-use: MAX ONE cashtag ($SYM) per post (403 otherwise).
    // Only the lead name gets "$"; others are plain ticker text.
    std::ostringstream oss;
    oss << "SEMICON WHALE SCAN " << day.substr(5) << " (Toronto premarket)\n";

    if (top.empty()) {
        oss << "Fleet quiet: no unusual rel-vol/gap on semis watchlist. "
               "Stay systematic — no chase.\n"
               "#semiconductors #stocks";
        return oss.str();
    }

    for (size_t i = 0; i < top.size(); i++) {
        const Row& r = top[i];
        // single cashtag on #1 only
        if (i == 0)
            oss << (i + 1) << ") $" << r.ticker;
        else
            oss << (i + 1) << ") " << r.ticker;
        if (!std::isnan(r.change)) oss << " " << fmt_pct(r.change);
        if (!std::isnan(r.rel_vol)) oss << " RVOL " << fmt_num(r.rel_vol) << "x";
        if (!std::isnan(r.gap) && fabs(r.gap) >= 0.5)
            oss << " gap " << fmt_pct(r.gap);
        if (!std::isnan(r.short_float) && r.short_float >= 3.0)
            oss << " short " << fmt_num(r.short_float) << "%";
        oss << "\n";
    }

    // insight line — refer to lead by bare ticker (no second $)
    const Row& lead = top[0];
    if (!std::isnan(lead.rel_vol) && lead.rel_vol >= 2.0) {
        oss << "Insight: " << lead.ticker
            << " unusual flow (RVOL>=2x). Whales show interest — wait for "
               "open acceptance, not the first print.\n";
    } else if (!std::isnan(lead.gap) && fabs(lead.gap) >= 1.5) {
        oss << "Insight: gap on " << lead.ticker
            << ". Map OR then trade resolution, not the gap itself.\n";
    } else if (!std::isnan(lead.short_float) && lead.short_float >= 10) {
        oss << "Insight: elevated short float on " << lead.ticker
            << " — fuel if volume expands; trap if it dies.\n";
    } else {
        oss << "Insight: mixed/quiet flow across the semis fleet. "
               "Protect capital; only A+ setups.\n";
    }
    oss << "#semiconductors #stocks";

    std::string text = oss.str();
    // hard strip URLs if any slipped in
    if (has_url(text)) {
        // remove common url patterns crudely
        size_t p;
        while ((p = lower(text).find("http")) != std::string::npos) {
            size_t e = text.find_first_of(" \n\t", p);
            if (e == std::string::npos) text.erase(p);
            else text.erase(p, e - p);
        }
    }
    // X limit 280 — trim insight if needed
    if (text.size() > 275) {
        text = text.substr(0, 272) + "...";
    }
    return text;
}

// ---------- OAuth 1.0a helpers (macOS openssl)
static std::string b64_encode(const unsigned char* data, size_t len) {
    BIO* b64 = BIO_new(BIO_f_base64());
    BIO* mem = BIO_new(BIO_s_mem());
    b64 = BIO_push(b64, mem);
    BIO_set_flags(b64, BIO_FLAGS_BASE64_NO_NL);
    BIO_write(b64, data, (int)len);
    BIO_flush(b64);
    BUF_MEM* bptr = nullptr;
    BIO_get_mem_ptr(b64, &bptr);
    std::string out(bptr->data, bptr->length);
    BIO_free_all(b64);
    return out;
}

static std::string pct_encode(const std::string& s) {
    static const char* hex = "0123456789ABCDEF";
    std::string o;
    for (unsigned char c : s) {
        if (isalnum(c) || c == '-' || c == '.' || c == '_' || c == '~')
            o += (char)c;
        else {
            o += '%';
            o += hex[c >> 4];
            o += hex[c & 15];
        }
    }
    return o;
}

static std::string oauth_nonce() {
    unsigned char buf[16];
    RAND_bytes(buf, sizeof(buf));
    static const char* hex = "0123456789abcdef";
    std::string o;
    for (int i = 0; i < 16; i++) {
        o += hex[buf[i] >> 4];
        o += hex[buf[i] & 15];
    }
    return o;
}

static std::string hmac_sha1_b64(const std::string& key, const std::string& data) {
    unsigned char md[EVP_MAX_MD_SIZE];
    unsigned int md_len = 0;
    HMAC(EVP_sha1(), key.data(), (int)key.size(),
         (const unsigned char*)data.data(), data.size(), md, &md_len);
    return b64_encode(md, md_len);
}

struct XAuth {
    std::string bearer;
    std::string api_key, api_secret, access_token, access_secret;
    bool has_oauth1() const {
        return !api_key.empty() && !api_secret.empty() && !access_token.empty() &&
               !access_secret.empty();
    }
    bool has_bearer() const { return !bearer.empty(); }
};

static XAuth load_xauth() {
    auto xenv = read_env_file("x.env");
    XAuth a;
    a.bearer = env_or_file("X_BEARER_TOKEN", xenv);
    // also accept unprefixed
    if (a.bearer.empty()) a.bearer = env_or_file("BEARER_TOKEN", xenv);
    a.api_key = env_or_file("X_API_KEY", xenv);
    if (a.api_key.empty()) a.api_key = env_or_file("API_KEY", xenv);
    a.api_secret = env_or_file("X_API_SECRET", xenv);
    if (a.api_secret.empty()) a.api_secret = env_or_file("API_SECRET", xenv);
    a.access_token = env_or_file("X_ACCESS_TOKEN", xenv);
    if (a.access_token.empty()) a.access_token = env_or_file("ACCESS_TOKEN", xenv);
    a.access_secret = env_or_file("X_ACCESS_SECRET", xenv);
    if (a.access_secret.empty())
        a.access_secret = env_or_file("ACCESS_TOKEN_SECRET", xenv);
    return a;
}

static HttpResp http_post_json(const std::string& url, const std::string& json,
                               const std::string& auth_header) {
    HttpResp r;
    CURL* c = curl_easy_init();
    if (!c) return r;
    struct curl_slist* headers = nullptr;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    std::string ah = "Authorization: " + auth_header;
    headers = curl_slist_append(headers, ah.c_str());
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(c, CURLOPT_POSTFIELDS, json.c_str());
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, curl_sink);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &r.body);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, 30L);
    curl_easy_setopt(c, CURLOPT_USERAGENT, "ib-trader x_whale_bot/1.0");
    CURLcode rc = curl_easy_perform(c);
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &r.code);
    curl_slist_free_all(headers);
    curl_easy_cleanup(c);
    r.ok = (rc == CURLE_OK);
    return r;
}

static std::string oauth1_header(const XAuth& a, const std::string& method,
                                 const std::string& url,
                                 const std::map<std::string, std::string>& extra) {
    std::string nonce = oauth_nonce();
    std::string ts = std::to_string((long long)time(nullptr));
    std::map<std::string, std::string> p = extra;
    p["oauth_consumer_key"] = a.api_key;
    p["oauth_nonce"] = nonce;
    p["oauth_signature_method"] = "HMAC-SHA1";
    p["oauth_timestamp"] = ts;
    p["oauth_token"] = a.access_token;
    p["oauth_version"] = "1.0";

    std::string param_str;
    for (auto& kv : p) {
        if (!param_str.empty()) param_str += "&";
        param_str += pct_encode(kv.first) + "=" + pct_encode(kv.second);
    }
    std::string base = method + "&" + pct_encode(url) + "&" + pct_encode(param_str);
    std::string key =
        pct_encode(a.api_secret) + "&" + pct_encode(a.access_secret);
    std::string sig = hmac_sha1_b64(key, base);
    p["oauth_signature"] = sig;

    std::string h = "OAuth ";
    bool first = true;
    for (const char* k : {"oauth_consumer_key", "oauth_nonce", "oauth_signature",
                          "oauth_signature_method", "oauth_timestamp",
                          "oauth_token", "oauth_version"}) {
        if (!first) h += ", ";
        first = false;
        h += std::string(k) + "=\"" + pct_encode(p[k]) + "\"";
    }
    return h;
}

static std::string json_escape(const std::string& s) {
    std::string o;
    for (char c : s) {
        if (c == '"')
            o += "\\\"";
        else if (c == '\\')
            o += "\\\\";
        else if (c == '\n')
            o += "\\n";
        else if (c == '\r')
            o += "\\r";
        else if (c == '\t')
            o += "\\t";
        else
            o += c;
    }
    return o;
}

static bool extract_tweet_id(const std::string& body, std::string& id_out) {
    // naive: "id":"123"
    size_t p = body.find("\"id\"");
    if (p == std::string::npos) return false;
    p = body.find('"', p + 4);
    if (p == std::string::npos) return false;
    size_t q = body.find('"', p + 1);
    // might be "id": "123" with colon
    p = body.find(':', body.find("\"id\""));
    if (p == std::string::npos) return false;
    while (p < body.size() && (body[p] == ':' || body[p] == ' ' || body[p] == '"'))
        p++;
    size_t e = p;
    while (e < body.size() && isdigit((unsigned char)body[e])) e++;
    if (e == p) return false;
    id_out = body.substr(p, e - p);
    return true;
}

static HttpResp post_tweet(const XAuth& a, const std::string& text) {
    const std::string url = "https://api.x.com/2/tweets";
    std::string json = std::string("{\"text\":\"") + json_escape(text) + "\"}";

    // Prefer OAuth1 user context (required for most write tiers)
    if (a.has_oauth1()) {
        logln("auth: OAuth 1.0a user context");
        auto h = oauth1_header(a, "POST", url, {});
        return http_post_json(url, json, h);
    }
    if (a.has_bearer()) {
        logln("auth: Bearer (app-only may be rejected for POST)");
        return http_post_json(url, json, "Bearer " + a.bearer);
    }
    HttpResp r;
    r.code = 0;
    r.body = "no credentials";
    return r;
}

static void append_post_log(const std::string& text, long code,
                            const std::string& id, double cost,
                            const std::string& mode) {
    std::ofstream f("data/x_posts.jsonl", std::ios::app);
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    char ts[32];
    snprintf(ts, sizeof(ts), "%04d-%02d-%02dT%02d:%02d:%02d", lt.tm_year + 1900,
             lt.tm_mon + 1, lt.tm_mday, lt.tm_hour, lt.tm_min, lt.tm_sec);
    f << "{\"ts\":\"" << ts << "\",\"mode\":\"" << mode << "\",\"http\":" << code
      << ",\"id\":\"" << id << "\",\"cost\":" << cost << ",\"text\":\""
      << json_escape(text) << "\"}\n";
}

// ---------- schedule: 09:00 America/Toronto
static bool is_weekend() {
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    return lt.tm_wday == 0 || lt.tm_wday == 6;
}

static int minutes_to_nine() {
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    int nowm = lt.tm_hour * 60 + lt.tm_min;
    int target = 9 * 60;
    if (nowm < target) return target - nowm;
    // already past 9 → next day
    return (24 * 60 - nowm) + target;
}

static int run_once(bool dry, bool force, Budget& budget) {
    auto syms = fleet_tickers();
    logln("universe: " + std::to_string(syms.size()) + " tickers");

    // Claude-way: cache-first if scout warm (≥ half universe < 30m), else live
    std::vector<Row> rows;
    int need = std::max(3, (int)syms.size() / 2);
    if (cache_universe_fresh(syms, 30 * 60, need)) {
        logln("FINVIZ path: cache-first (scout warm, ≥" + std::to_string(need) +
              " files <30m)");
        rows = load_from_cache(syms);
    }
    if (rows.empty()) {
        logln("FINVIZ path: live Elite export");
        rows = fetch_finviz_live(syms);
    }
    if (rows.empty()) {
        logln("FINVIZ path: cold cache fallback");
        rows = load_from_cache(syms);
    }
    if (rows.empty()) {
        logln("ERROR: sin datos Finviz ni cache — abort");
        if (!dry)
            fleet_notify_urgent("X WHALE BOT", "Sin datos Finviz/cache — no post");
        return 2;
    }
    score_rows(rows);
    std::string text = compose_post(rows);
    logln("compose (" + std::to_string(text.size()) + " chars):\n" + text);

    bool url = has_url(text);
    double cost = url ? budget.cost_url : budget.cost_no_url;

    if (dry) {
        logln("DRY-RUN: cost est $" + fmt_num(cost, 3) + " | month spent $" +
              fmt_num(budget.spent, 3) + "/" + fmt_num(budget.cap, 2) +
              " | posts " + std::to_string(budget.posts) + "/" +
              std::to_string(budget.max_month));
        append_post_log(text, 0, "", 0, "dry");
        return 0;
    }

    // budget gates
    if (posts_today() >= budget.max_day && !force) {
        logln("SKIP: ya se posteó hoy (max_day=" + std::to_string(budget.max_day) +
              ")");
        return 0;
    }
    // force still respects hard money cap
    if (budget.posts >= budget.max_month) {
        logln("BLOCK: max posts/month reached");
        return 3;
    }
    if (budget.spent + cost > budget.cap) {
        logln("BLOCK: budget cap $" + fmt_num(budget.cap, 2) + " would be exceeded");
        fleet_notify_urgent("X BUDGET", "Cap $5 alcanzado — post bloqueado");
        return 3;
    }
    if (url) {
        logln("BLOCK: URL detectada — posts con link cuestan ~$0.20 (over budget risk)");
        return 3;
    }

    XAuth auth = load_xauth();
    if (!auth.has_bearer() && !auth.has_oauth1()) {
        logln("ERROR: sin X credentials en x.env");
        return 1;
    }

    HttpResp r = post_tweet(auth, text);
    logln("POST http=" + std::to_string(r.code) + " body=" +
          (r.body.size() > 300 ? r.body.substr(0, 300) + "..." : r.body));

    std::string id;
    bool ok = (r.code == 201 || r.code == 200) && extract_tweet_id(r.body, id);
    if (ok) {
        budget.posts += 1;
        budget.spent += cost;
        save_budget(budget);
        append_post_log(text, r.code, id, cost, "live");
        logln("OK tweet id=" + id + " cost=$" + fmt_num(cost, 3) +
              " month=$" + fmt_num(budget.spent, 3));
        fleet_notify_urgent("X POSTED",
                            ("Whale scan live id=" + id).c_str());
        return 0;
    }

    // auth failure diagnostics
    if (r.code == 401 || r.code == 403) {
        logln("AUTH FAIL: Bearer app-only often cannot create posts. "
              "Add OAuth1 X_API_KEY/X_API_SECRET/X_ACCESS_TOKEN/X_ACCESS_SECRET "
              "to x.env (user context).");
        fleet_notify_urgent("X AUTH FAIL",
                            "Need OAuth1 user tokens in x.env — see skill");
    }
    append_post_log(text, r.code, "", 0, "fail");
    return 4;
}

static void print_budget(const Budget& b) {
    printf("month=%s posts=%d/%d spent=$%.3f cap=$%.2f remaining=$%.2f "
           "today=%d/%d cost_no_url=$%.3f cost_url=$%.2f\n",
           b.yyyymm.c_str(), b.posts, b.max_month, b.spent, b.cap,
           std::max(0.0, b.cap - b.spent), posts_today(), b.max_day,
           b.cost_no_url, b.cost_url);
    printf("policy: 1 post/day, NO URLs, ~$%.2f/mo at full utilization\n",
           b.max_month * b.cost_no_url);
}

int main(int argc, char** argv) {
    setenv("TZ", "America/Toronto", 1);
    tzset();

    bool dry = false, post_now = false, daemon = false, budget_only = false,
         compose_only = false, force = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--dry-run")) dry = true;
        else if (!strcmp(argv[i], "--post-now")) post_now = true;
        else if (!strcmp(argv[i], "--daemon")) daemon = true;
        else if (!strcmp(argv[i], "--budget")) budget_only = true;
        else if (!strcmp(argv[i], "--compose-only")) compose_only = true;
        else if (!strcmp(argv[i], "--force")) force = true;
        else if (!strcmp(argv[i], "--help")) {
            printf("x_whale_bot — daily semiconductor whale posts to X\n"
                   "  --dry-run | --compose-only | --post-now [--force]\n"
                   "  --budget | --daemon (09:00 America/Toronto)\n");
            return 0;
        }
    }

    auto xenv = read_env_file("x.env");
    Budget budget = load_budget(xenv);

    if (budget_only) {
        print_budget(budget);
        return 0;
    }

    curl_global_init(CURL_GLOBAL_DEFAULT);

    if (compose_only) {
        return run_once(true, false, budget);
    }

    if (post_now || dry) {
        int rc = run_once(dry, force || post_now, budget);
        curl_global_cleanup();
        return rc;
    }

    if (daemon) {
        logln("daemon up | TZ=America/Toronto | post window 09:00 weekdays");
        for (;;) {
            if (is_weekend()) {
                logln("weekend — sleep 6h");
                sleep(6 * 3600);
                continue;
            }
            int mins = minutes_to_nine();
            // if within 0..5 min of 9:00 or past 9:00 and not yet posted today
            time_t now = time(nullptr);
            struct tm lt;
            localtime_r(&now, &lt);
            int nowm = lt.tm_hour * 60 + lt.tm_min;
            bool morning_window = (nowm >= 9 * 60 && nowm < 9 * 60 + 15);
            if (morning_window && posts_today() == 0) {
                budget = load_budget(xenv);
                run_once(false, false, budget);
                sleep(60 * 20);  // avoid double fire
                continue;
            }
            // sleep until ~09:00, but wake every 10 min max for log heartbeat
            int sleep_s = std::min(600, std::max(30, mins * 60 - 30));
            logln("sleep " + std::to_string(sleep_s) + "s (mins_to_9=" +
                  std::to_string(mins) + ")");
            sleep((unsigned)sleep_s);
        }
    }

    // default: dry-run safe
    logln("no mode flag → dry-run (use --post-now to spend)");
    int rc = run_once(true, false, budget);
    curl_global_cleanup();
    return rc;
}
