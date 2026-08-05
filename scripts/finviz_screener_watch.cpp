// finviz_screener_watch.cpp — tres bots Finviz Elite, señal-solamente.
//
// Instancias:
//   --screen buffett   calidad/valor (ROE, deuda, beneficios, valoración)
//   --screen squeeze   short float alto + liquidez + volumen relativo
//   --screen momentum  nuevo máximo 52 semanas + RVOL + tendencia sobre SMAs
//
// Cada instancia guarda membresía/estado diario, deja el primer snapshot en silencio,
// notifica sólo entradas nuevas o cambios BUY<->SELL y agrupa la ráfaga en UN banner.
// El "weather" es un score técnico explícito, no una probabilidad inventada ni una orden.
// Build: clang++ -std=c++17 -O2 -o bin/finviz_screener_watch \
//          scripts/finviz_screener_watch.cpp -lcurl

#include "../bots/fleet_notify.h"

#include <curl/curl.h>
#include <fcntl.h>
#include <spawn.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

struct Profile {
    std::string id, label, filters, signal;
    int poll_rth, poll_extended;
};

struct Row {
    std::string ticker, company;
    double price = NAN, change = NAN, from_open = NAN, rvol = NAN;
    double rsi = NAN, sma20 = NAN, sma50 = NAN, sma200 = NAN;
    double short_float = NAN, short_ratio = NAN;
    std::string weather;
    int score = 0, possible = 0;
    std::vector<std::string> reasons;
};

struct Saved {
    std::string date;
    bool valid = false;
    bool preopen = false;
    std::map<std::string, std::string> current;
    std::set<std::string> alerted;
};

struct HttpResp { long code = 0; bool ok = false; std::string body; };

static std::string trim(std::string s) {
    const char* ws = " \t\r\n";
    size_t a = s.find_first_not_of(ws), b = s.find_last_not_of(ws);
    return a == std::string::npos ? "" : s.substr(a, b - a + 1);
}

static double num(std::string s) {
    s = trim(s);
    if (s.empty() || s == "-" || s == "N/A") return NAN;
    s.erase(std::remove(s.begin(), s.end(), '%'), s.end());
    s.erase(std::remove(s.begin(), s.end(), ','), s.end());
    char* end = nullptr;
    errno = 0;
    double v = std::strtod(s.c_str(), &end);
    return errno || end == s.c_str() ? NAN : v;
}

static std::vector<std::string> csv_split(const std::string& line) {
    std::vector<std::string> out;
    std::string cur;
    bool quote = false;
    for (size_t i = 0; i < line.size(); ++i) {
        char c = line[i];
        if (c == '"') {
            if (quote && i + 1 < line.size() && line[i + 1] == '"') { cur += '"'; ++i; }
            else quote = !quote;
        } else if (c == ',' && !quote) {
            out.push_back(cur); cur.clear();
        } else if (c != '\r') cur += c;
    }
    out.push_back(cur);
    return out;
}

static size_t curl_write(void* p, size_t a, size_t b, void* u) {
    static_cast<std::string*>(u)->append(static_cast<char*>(p), a * b);
    return a * b;
}

static HttpResp http_get(const std::string& url) {
    HttpResp r;
    CURL* c = curl_easy_init();
    if (!c) return r;
    curl_easy_setopt(c, CURLOPT_URL, url.c_str());
    curl_easy_setopt(c, CURLOPT_WRITEFUNCTION, curl_write);
    curl_easy_setopt(c, CURLOPT_WRITEDATA, &r.body);
    curl_easy_setopt(c, CURLOPT_TIMEOUT, 20L);
    curl_easy_setopt(c, CURLOPT_CONNECTTIMEOUT, 8L);
    curl_easy_setopt(c, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(c, CURLOPT_USERAGENT, "ib-trader finviz_screener_watch/1.0");
    CURLcode rc = curl_easy_perform(c);
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &r.code);
    r.ok = rc == CURLE_OK;
    curl_easy_cleanup(c);
    return r;
}

static std::string token() {
    for (const char* k : {"FINVIZ_AUTH3", "FINVIZ_AUTH"}) {
        const char* v = std::getenv(k);
        if (v && *v) return trim(v);
    }
    for (const char* file : {"config/feeds.env", "feeds.env"}) {
        std::ifstream f(file);
        std::string line;
        while (std::getline(f, line)) {
            for (const char* k : {"FINVIZ_AUTH3=", "FINVIZ_AUTH="})
                if (line.rfind(k, 0) == 0 && line.size() > std::strlen(k))
                    return trim(line.substr(std::strlen(k)));
        }
    }
    return "";
}

static Profile profile(const std::string& id) {
    if (id == "buffett") return {
        id, "BUFFETT",
        "fa_debteq_u0.5,fa_eps5years_pos,fa_netmargin_pos,fa_pe_u20,fa_roe_o15,"
        "sh_avgvol_o500,sh_price_o5", "", 600, 900};
    if (id == "squeeze") return {
        id, "SHORT SQUEEZE",
        "sh_avgvol_o500,sh_float_u50,sh_price_o5,sh_relvol_o1.5,sh_short_o15", "", 120, 300};
    if (id == "momentum") return {
        id, "MOMENTUM BREAKOUT",
        "sh_avgvol_o500,sh_price_o5,sh_relvol_o1.5,ta_sma20_pa,ta_sma50_pa,ta_sma200_pa",
        "ta_newhigh", 60, 180};
    return {};
}

static std::string today() {
    time_t now = time(nullptr); struct tm t{}; localtime_r(&now, &t);
    char b[16]; std::snprintf(b, sizeof b, "%04d-%02d-%02d", t.tm_year + 1900, t.tm_mon + 1, t.tm_mday);
    return b;
}

enum Phase { OFF, EXTENDED, RTH };
static Phase phase() {
    if (std::getenv("FINVIZ_FORCE_OPEN")) return RTH;
    time_t now = time(nullptr); struct tm t{}; localtime_r(&now, &t);
    if (t.tm_wday == 0 || t.tm_wday == 6) return OFF;
    int hm = t.tm_hour * 100 + t.tm_min;
    if (hm >= 930 && hm < 1600) return RTH;
    if (hm >= 400 && hm < 2000) return EXTENDED;
    return OFF;
}

static std::string get(const std::vector<std::string>& f,
                       const std::map<std::string, int>& ix, const std::string& key) {
    auto it = ix.find(key);
    return it != ix.end() && it->second < static_cast<int>(f.size()) ? trim(f[it->second]) : "";
}

static void add(Row& r, int delta, const std::string& why) {
    r.score += delta; r.possible += 1; r.reasons.push_back((delta > 0 ? "+" : "-") + why);
}

static void score(Row& r, const Profile& p) {
    if (!std::isnan(r.change)) add(r, r.change > 0.3 ? 1 : r.change < -0.3 ? -1 : 0, "día");
    if (!std::isnan(r.from_open)) add(r, r.from_open > 0.2 ? 1 : r.from_open < -0.2 ? -1 : 0, "apertura");
    if (!std::isnan(r.rsi)) {
        if (r.rsi >= 50 && r.rsi <= 75) add(r, 1, "RSI");
        else if (r.rsi < 42 || r.rsi > 82) add(r, -1, r.rsi > 82 ? "RSI extremo" : "RSI débil");
        else add(r, 0, "RSI");
    }
    if (!std::isnan(r.sma20)) add(r, r.sma20 > 0 ? 1 : -1, "SMA20");
    if (!std::isnan(r.sma50)) add(r, r.sma50 > 0 ? 1 : -1, "SMA50");
    if (!std::isnan(r.sma200)) add(r, r.sma200 > 0 ? 1 : -1, "SMA200");
    if (!std::isnan(r.rvol)) add(r, r.rvol >= 1.5 ? 1 : 0, "RVOL");
    // Un squeeze necesita precio comprador; short float alto por sí solo NO es BUY.
    // Un breakout que se vuelve rojo desde apertura pierde el voto del preset.
    if (p.id == "squeeze" && !std::isnan(r.short_float))
        add(r, r.short_float >= 20 && r.change > 0 ? 1 : 0, "short+impulso");
    if (p.id == "momentum")
        add(r, (!std::isnan(r.change) && r.change > 0 &&
                !std::isnan(r.from_open) && r.from_open > 0) ? 1 : -1, "breakout sostiene");
    int threshold = std::max(2, static_cast<int>(std::ceil(r.possible * 0.45)));
    r.weather = r.score >= threshold ? "BUY" : r.score <= -threshold ? "SELL" : "WATCH";
}

static std::vector<Row> parse_csv(const std::string& body, const Profile& p, std::string& error) {
    std::stringstream ss(body); std::string line;
    if (!std::getline(ss, line)) { error = "CSV vacío"; return {}; }
    auto h = csv_split(line);
    std::map<std::string, int> ix;
    for (int i = 0; i < static_cast<int>(h.size()); ++i) ix[trim(h[i])] = i;
    if (!ix.count("Ticker") || !ix.count("Price") || !ix.count("Change")) {
        error = "header sin Ticker/Price/Change"; return {};
    }
    std::vector<Row> out;
    while (std::getline(ss, line)) {
        if (trim(line).empty()) continue;
        auto f = csv_split(line); Row r;
        r.ticker = get(f, ix, "Ticker");
        if (r.ticker.empty()) continue;
        r.company = get(f, ix, "Company");
        r.price = num(get(f, ix, "Price"));
        r.change = num(get(f, ix, "Change"));
        r.from_open = num(get(f, ix, "Change from Open"));
        r.rvol = num(get(f, ix, "Relative Volume"));
        r.rsi = num(get(f, ix, "Relative Strength Index (14)"));
        r.sma20 = num(get(f, ix, "20-Day Simple Moving Average"));
        r.sma50 = num(get(f, ix, "50-Day Simple Moving Average"));
        r.sma200 = num(get(f, ix, "200-Day Simple Moving Average"));
        r.short_float = num(get(f, ix, "Short Float"));
        r.short_ratio = num(get(f, ix, "Short Ratio"));
        score(r, p); out.push_back(r);
    }
    std::sort(out.begin(), out.end(), [](const Row& a, const Row& b) {
        double ar = std::isnan(a.rvol) ? -1 : a.rvol, br = std::isnan(b.rvol) ? -1 : b.rvol;
        return ar == br ? a.score > b.score : ar > br;
    });
    return out;
}

static Saved load_state(const std::string& path) {
    Saved s; std::ifstream f(path); std::string line;
    while (std::getline(f, line)) {
        if (line.rfind("date=", 0) == 0) s.date = trim(line.substr(5));
        else if (line.rfind("current|", 0) == 0) {
            size_t x = line.find('|', 8);
            if (x != std::string::npos) s.current[line.substr(8, x - 8)] = line.substr(x + 1);
        } else if (line.rfind("alerted|", 0) == 0) s.alerted.insert(trim(line.substr(8)));
        else if (line.rfind("preopen|", 0) == 0) s.preopen = trim(line.substr(8)) == "1";
    }
    s.valid = !s.date.empty();
    return s;
}

static bool save_state(const std::string& path, const Saved& s) {
    std::string tmp = path + ".tmp" + std::to_string(getpid());
    std::ofstream f(tmp, std::ios::trunc);
    if (!f) return false;
    f << "date=" << s.date << "\n";
    if (s.preopen) f << "preopen|1\n";
    for (const auto& kv : s.current) f << "current|" << kv.first << "|" << kv.second << "\n";
    for (const auto& x : s.alerted) f << "alerted|" << x << "\n";
    f.close();
    return rename(tmp.c_str(), path.c_str()) == 0;
}

static bool save_snapshot(const Profile& p, const std::vector<Row>& rows) {
    std::string path = "data/finviz_" + p.id + "_signals.csv";
    std::string tmp = path + ".tmp" + std::to_string(getpid());
    std::ofstream f(tmp, std::ios::trunc);
    if (!f) return false;
    f << "ticker,weather,score,possible,price,change_pct,from_open_pct,rvol,rsi,sma20_pct,"
         "sma50_pct,sma200_pct,short_float_pct,short_ratio\n";
    auto val = [&](double x) { if (!std::isnan(x)) f << x; };
    for (const Row& r : rows) {
        f << r.ticker << ',' << r.weather << ',' << r.score << ',' << r.possible << ',';
        val(r.price); f << ','; val(r.change); f << ','; val(r.from_open); f << ',';
        val(r.rvol); f << ','; val(r.rsi); f << ','; val(r.sma20); f << ',';
        val(r.sma50); f << ','; val(r.sma200); f << ','; val(r.short_float); f << ',';
        val(r.short_ratio); f << '\n';
    }
    f.close(); return rename(tmp.c_str(), path.c_str()) == 0;
}

static void append_event(const Profile& p, const Row& r, const std::string& kind) {
    std::ofstream f("data/finviz_screener_events.jsonl", std::ios::app);
    if (!f) return;
    f << "{\"ts\":" << time(nullptr) << ",\"screen\":\"" << p.id
      << "\",\"ticker\":\"" << r.ticker << "\",\"event\":\"" << kind
      << "\",\"weather\":\"" << r.weather << "\",\"score\":" << r.score
      << ",\"possible\":" << r.possible;
    if (!std::isnan(r.price)) f << ",\"price\":" << r.price;
    if (!std::isnan(r.change)) f << ",\"change_pct\":" << r.change;
    if (!std::isnan(r.rvol)) f << ",\"rvol\":" << r.rvol;
    f << "}\n";
}

static void phone_push(const std::string& title, const std::string& msg) {
    if (std::getenv("FINVIZ_TEST")) return;
    const char* py = access("venv/bin/python", X_OK) == 0 ? "venv/bin/python" : "/usr/bin/python3";
    const char* argv[] = {py, "scripts/notify_short.py", title.c_str(), msg.c_str(), nullptr};
    pid_t pid;
    posix_spawn(&pid, py, nullptr, nullptr, const_cast<char* const*>(argv), environ);
}

// ANTI-RUIDO (Yunior 2026-08-04 "avoid too much noise with finviz"; numeros del backtest
// docs/BACKTEST-ALERTAS-FINVIZ-2026-08-04.md — 184 alertas/dia a -8,4pp CONTRA el azar):
//   ventana 09:45-15:30 (fuera: 82 muertas, 17 buenas), solo BUY/SELL (WATCH no interrumpe),
//   RVOL>=1.5 (el unico corte con vida propia: concentracion +6,5pp), 1 alerta/ticker/dia
//   (la mediana de momentum era UNA interrupcion cada 3 minutos por oscilacion WATCH<->BUY).
// El CSV, el estado y los eventos se escriben SIEMPRE: solo se gatea la interrupcion.
static bool notify_window_open() {
    time_t t = time(nullptr); struct tm lt; localtime_r(&t, &lt);
    int hm = lt.tm_hour * 100 + lt.tm_min;
    return hm >= 945 && hm <= 1530;
}

static bool row_alertable(const Row& r) {
    return (r.weather == "BUY" || r.weather == "SELL") &&
           !std::isnan(r.rvol) && r.rvol >= 1.5;
}

// Re-canto de apertura (backtest 2026-08-04: PLTR/AAOI gap-up premarket jamas sonaron
// porque solo cantan matches NUEVOS y el gap ya estaba en la lista antes de abrir).
static bool preopen_recant_window() {
    if (std::getenv("FINVIZ_FORCE_PREOPEN")) return true;
    time_t t = time(nullptr); struct tm lt; localtime_r(&t, &lt);
    int hm = lt.tm_hour * 100 + lt.tm_min;
    return hm >= 931 && hm <= 935;
}

static void notify(const Profile& p, const std::vector<Row>& rows, const std::string& kind) {
    if (rows.empty()) return;
    int buy = 0, sell = 0, watch = 0;
    for (const auto& r : rows) (r.weather == "BUY" ? buy : r.weather == "SELL" ? sell : watch)++;
    std::string msg;
    size_t shown = std::min<size_t>(3, rows.size());
    for (size_t i = 0; i < shown; ++i) {
        const Row& r = rows[i];
        char b[160];
        std::snprintf(b, sizeof b, "%s%s %s $%.2f %+.1f%% RVOL %.1fx score %d/%d",
                      i ? " | " : "", r.ticker.c_str(), r.weather.c_str(),
                      std::isnan(r.price) ? 0 : r.price, std::isnan(r.change) ? 0 : r.change,
                      std::isnan(r.rvol) ? 0 : r.rvol, r.score, r.possible);
        msg += b;
    }
    if (rows.size() > shown) msg += " | +" + std::to_string(rows.size() - shown) + " más";
    std::string title = "FINVIZ " + p.label + " · " + kind + " · BUY " +
                        std::to_string(buy) + " SELL " + std::to_string(sell) +
                        " WATCH " + std::to_string(watch);
    if (!std::getenv("FINVIZ_TEST")) fleet_notify_urgent(title.c_str(), msg.c_str(), "ProAlert");
    phone_push(title, msg);
    std::printf("%s | %s\n", title.c_str(), msg.c_str()); std::fflush(stdout);
}

static bool claim_incident(const std::string& why) {
    const char* p = "data/finviz_screeners_broken";
    int fd = open(p, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) return false;
    write(fd, why.data(), why.size()); close(fd); return true;
}

static int run_cycle(const Profile& p, bool alert_existing) {
    std::string tok = token();
    if (tok.empty()) {
        if (claim_incident("sin token")) {
            std::string title = "FINVIZ SCREENERS ROTO";
            std::string msg = "Sin FINVIZ_AUTH3/FINVIZ_AUTH · los 3 screeners están ciegos";
            if (!std::getenv("FINVIZ_TEST")) fleet_notify_urgent(title.c_str(), msg.c_str(), "Sosumi");
            phone_push(title, msg);
        }
        std::fprintf(stderr, "FINVIZ %s ROTO: sin FINVIZ_AUTH3/FINVIZ_AUTH\n", p.id.c_str());
        return 1;
    }
    // IDs verificados por header: 53/54/55 son SMA20/50/200; 59 RSI; 60 cambio
    // desde apertura; 64 RVOL; 65/66 precio/cambio. El parser usa NOMBRES, no posiciones.
    std::string url = "https://elite.finviz.com/export/screener?v=152&f=" + p.filters;
    if (!p.signal.empty()) url += "&s=" + p.signal;
    url += "&o=-relativevolume&c=1,2,6,30,31,53,54,55,59,60,61,63,64,65,66,67&auth=" + tok;
    HttpResp h = http_get(url);
    std::string err;
    if (!h.ok) err = "transporte curl";
    else if (h.code != 200) err = "HTTP " + std::to_string(h.code);
    else if (trim(h.body).empty()) err = "CSV vacío";
    else if (h.body[0] == '<') err = "HTML/login";
    std::vector<Row> rows;
    if (err.empty()) rows = parse_csv(h.body, p, err);
    if (!err.empty()) {
        std::fprintf(stderr, "FINVIZ %s ROTO: %s\n", p.id.c_str(), err.c_str());
        if (claim_incident(p.id + ": " + err)) {
            std::string title = "FINVIZ SCREENERS ROTO", msg = p.label + ": " + err + " · reintento 5m";
            if (!std::getenv("FINVIZ_TEST")) fleet_notify_urgent(title.c_str(), msg.c_str(), "Sosumi");
            phone_push(title, msg);
        }
        return 1;
    }
    if (access("data/finviz_screeners_broken", F_OK) == 0) {
        unlink("data/finviz_screeners_broken");
        std::string title = "FINVIZ SCREENERS", msg = "Feed recuperado";
        if (!std::getenv("FINVIZ_TEST")) fleet_notify_urgent(title.c_str(), msg.c_str());
        phone_push(title, msg);
    }
    std::string path = "data/finviz_" + p.id + "_state.txt";
    Saved old = load_state(path), next;
    next.date = today(); next.valid = true;
    bool first = !old.valid || old.date != next.date;
    if (!first) { next.alerted = old.alerted; next.preopen = old.preopen; }
    std::vector<Row> fresh, changed, preopen;
    const bool window = notify_window_open();
    // UNA vez 09:31-09:35: canta los matches momentum VIVOS de antes de la apertura.
    const bool recant = p.id == "momentum" && !first && !next.preopen && preopen_recant_window();
    if (recant) {
        next.preopen = true;
        for (const Row& r : rows)
            if (old.current.count(r.ticker) && row_alertable(r) && !next.alerted.count(r.ticker)) {
                append_event(p, r, "preopen_match");
                preopen.push_back(r); next.alerted.insert(r.ticker);
            }
    }
    for (const Row& r : rows) {
        next.current[r.ticker] = r.weather;
        auto it = old.current.find(r.ticker);
        bool is_new = !first && it == old.current.end() && !old.alerted.count(r.ticker);
        // Alertar cuando APARECE una dirección nueva. BUY/SELL -> WATCH se registra en el
        // snapshot pero no genera otra interrupción: perdió convicción, no nació una señal.
        bool direction_change = !first && it != old.current.end() && it->second != r.weather &&
                                (r.weather == "BUY" || r.weather == "SELL");
        // El EVENTO se registra siempre (es la memoria del backtest); la INTERRUPCION exige
        // ventana + BUY/SELL + RVOL>=1.5 + cupo de 1/ticker/dia (direction_change tambien
        // lo consume: WATCH<->BUY oscilando era una interrupcion cada 3 minutos).
        if (is_new || (first && alert_existing)) {
            append_event(p, r, "new_match");
            if (window && row_alertable(r) && !next.alerted.count(r.ticker)) {
                fresh.push_back(r); next.alerted.insert(r.ticker);
            }
        } else if (direction_change) {
            append_event(p, r, "weather_change");
            if (window && row_alertable(r) && !next.alerted.count(r.ticker)) {
                changed.push_back(r); next.alerted.insert(r.ticker);
            }
        }
    }
    if (!save_state(path, next)) {
        std::fprintf(stderr, "FINVIZ %s ROTO: no pude guardar %s\n", p.id.c_str(), path.c_str());
        return 1;
    }
    if (!save_snapshot(p, rows)) {
        std::fprintf(stderr, "FINVIZ %s ROTO: no pude guardar snapshot CSV\n", p.id.c_str());
        return 1;
    }
    notify(p, preopen, "(pre-open match)");
    notify(p, fresh, "NUEVOS"); notify(p, changed, "WEATHER");
    std::printf("FINVIZ %s OK: %zu matches, nuevos=%zu, weather=%zu, preopen=%zu%s\n", p.id.c_str(),
                rows.size(), fresh.size(), changed.size(), preopen.size(),
                first ? " (snapshot inicial silencioso)" : "");
    return 0;
}

static int selftest() {
    Profile p = profile("momentum");
    std::string csv =
        "\"Ticker\",\"Company\",\"Short Float\",\"Short Ratio\",\"20-Day Simple Moving Average\",\"50-Day Simple Moving Average\",\"200-Day Simple Moving Average\",\"Relative Strength Index (14)\",\"Change from Open\",\"Relative Volume\",\"Price\",\"Change\"\n"
        "\"ABC\",\"A, Inc.\",20%,4.2,5%,8%,12%,64,3%,2.5,10.50,4%\n"
        "\"XYZ\",\"X Inc.\",18%,3,-4%,-8%,-10%,35,-3%,2.0,8.00,-5%\n";
    std::string err; auto rows = parse_csv(csv, p, err);
    if (!err.empty() || rows.size() != 2) return 2;
    std::map<std::string, Row> by; for (auto& r : rows) by[r.ticker] = r;
    if (by["ABC"].company != "A, Inc." || by["ABC"].weather != "BUY") return 3;
    if (by["XYZ"].weather != "SELL") return 4;
    if (profile("buffett").filters.find("fa_roe_o15") == std::string::npos) return 5;
    if (profile("squeeze").filters.find("sh_short_o15") == std::string::npos) return 6;
    if (profile("momentum").signal != "ta_newhigh") return 7;
    // roundtrip del flag preopen (dedup del re-canto de apertura)
    Saved s; s.date = today(); s.preopen = true; s.current["PLTR"] = "BUY"; s.alerted.insert("PLTR");
    std::string sp = std::string("/tmp/finviz_selftest_state.") + std::to_string(getpid());
    if (!save_state(sp, s)) return 8;
    Saved back = load_state(sp); unlink(sp.c_str());
    if (!back.valid || !back.preopen || back.current["PLTR"] != "BUY" || !back.alerted.count("PLTR")) return 9;
    setenv("FINVIZ_FORCE_PREOPEN", "1", 1);
    if (!preopen_recant_window()) return 10;
    unsetenv("FINVIZ_FORCE_PREOPEN");
    std::puts("finviz_screener_watch selftest OK"); return 0;
}

int main(int argc, char** argv) {
    std::string id; bool once = false, alert_existing = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--selftest") return selftest();
        if (a == "--once") once = true;
        else if (a == "--alert-existing") alert_existing = true;
        else if (a == "--screen" && i + 1 < argc) id = argv[++i];
    }
    Profile p = profile(id);
    if (p.id.empty()) {
        std::fprintf(stderr, "uso: finviz_screener_watch --screen buffett|squeeze|momentum [--once] [--alert-existing]\n");
        return 2;
    }
    curl_global_init(CURL_GLOBAL_DEFAULT);
    std::printf("finviz_%s arriba · señal-solamente\n", p.id.c_str());
    while (true) {
        Phase ph = phase();
        if (ph == OFF && !once) { sleep(300); continue; }
        int rc = run_cycle(p, alert_existing);
        if (once) { curl_global_cleanup(); return rc; }
        sleep(rc ? 300 : ph == RTH ? p.poll_rth : p.poll_extended);
    }
}
