// finviz_scout.cpp — bot de datos Finviz Elite en tiempo real (2026-07-17).
// SEÑAL-SOLAMENTE (ley #0): cero ordenes al broker, cero TWS — solo datos + banners.
//
// Ciclo: premarket 04:00-09:30 ET cada 60s; RTH 09:30-16:00 cada 180s; fuera
// de eso duerme (chequeo cada 5 min). UN solo request por ciclo (t=lista
// completa) — rate limit: JAMAS <60s entre requests, backoff 5 min en 429/rotura.
//
// Tickers: data/focus_ticker (mapeados a US upper; kospi/samsung/skhynix/sleep
// se saltan — no son simbolos US) + SIEMPRE MSFT,AVGO,AMZN,META,QQQ,SMH; dedup.
// Token: env FINVIZ_AUTH3 > feeds.env FINVIZ_AUTH3 > env/feeds FINVIZ_AUTH.
// JAMAS hardcodeado.
//
// Output por ciclo: data/finviz_<sym>.txt (clave=valor + timestamp) para que
// otros tools lean. Notifica (fleet_notify.h, banner Mac ~1.5ms) SOLO cambios
// de estado vs snapshot previo en memoria: gap >±2%, rel volume cruza 2.5x,
// short float ±0.5pt, earnings <48h (1/dia/ticker, persistido en
// data/finviz_earn_notified.txt), target price / recom cambian.
// Primer ciclo = sin snapshot previo = sin notificaciones (anti-spam).
//
// Fallo EN VOZ ALTA (ley #6): CSV vacio/HTML/HTTP!=200 -> log "FINVIZ ROTO" +
// banner UNA vez + reintento con backoff 5 min. Jamas silencio, jamas delayed.
//
// Compilar: clang++ -std=c++17 -O2 -o finviz_scout scripts/finviz_scout.cpp -lcurl
// Uso: ./finviz_scout            (loop 24/5, via scripts/finviz_scout_keepalive.sh)
//      ./finviz_scout --once [SYM...]  (un fetch+parse+write y sale; SYM extra p/tests)
#include "../fleet_notify.h"

#include <curl/curl.h>

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

// ---------- log (stdout -> finviz_scout.log via keepalive; visible en --once)
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
static std::string lower(std::string s) {
    for (auto& c : s) c = (char)tolower((unsigned char)c);
    return s;
}
static std::string upper(std::string s) {
    for (auto& c : s) c = (char)toupper((unsigned char)c);
    return s;
}

// feeds.env: KEY=VALUE (sin export), gitignored
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

static std::string get_token() {
    const char* keys[] = {"FINVIZ_AUTH3", "FINVIZ_AUTH"};
    auto feeds = read_env_file("feeds.env");
    for (const char* k : keys) {  // env primero (permite el test de token falso)
        const char* e = getenv(k);
        if (e && *e) return e;
        auto it = feeds.find(k);
        if (it != feeds.end() && !it->second.empty()) return it->second;
    }
    return "";
}

// ---------- tickers: focus_ticker + esenciales, dedup
static std::vector<std::string> build_tickers(const std::vector<std::string>& extra) {
    std::vector<std::string> out;
    std::set<std::string> seen;
    auto add = [&](const std::string& raw) {
        std::string s = upper(trim(raw));
        if (s.empty()) return;
        std::string lo = lower(s);
        // no-US / no-tickers del focus_ticker: se saltan
        static const std::set<std::string> skip = {"kospi", "samsung", "skhynix", "sleep", "wake"};
        if (skip.count(lo)) return;
        for (char c : s)
            if (!isalpha((unsigned char)c) && c != '.' && c != '-') return;
        if (s.size() > 5) return;  // simbolos US <=5 letras
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
    for (const char* s : {"MSFT", "AVGO", "AMZN", "META", "QQQ", "SMH"}) add(s);
    for (auto& s : extra) add(s);
    return out;
}

// ---------- HTTP
static size_t curl_sink(char* p, size_t sz, size_t nm, void* ud) {
    ((std::string*)ud)->append(p, sz * nm);
    return sz * nm;
}
struct HttpResp {
    long code = 0;
    std::string body;
    bool ok = false;  // transporte OK (no valida contenido)
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
    curl_easy_setopt(c, CURLOPT_USERAGENT, "ib-trader finviz_scout/1.0");
    curl_easy_setopt(c, CURLOPT_ACCEPT_ENCODING, "");  // gzip ok
    CURLcode rc = curl_easy_perform(c);
    curl_easy_getinfo(c, CURLINFO_RESPONSE_CODE, &r.code);
    curl_easy_cleanup(c);
    r.ok = (rc == CURLE_OK);
    return r;
}

// ---------- CSV (comillas + comas internas)
static std::vector<std::string> csv_split(const std::string& line) {
    std::vector<std::string> out;
    std::string cur;
    bool q = false;
    for (size_t i = 0; i < line.size(); i++) {
        char c = line[i];
        if (q) {
            if (c == '"') {
                if (i + 1 < line.size() && line[i + 1] == '"') { cur += '"'; i++; }
                else q = false;
            } else cur += c;
        } else {
            if (c == '"') q = true;
            else if (c == ',') { out.push_back(cur); cur.clear(); }
            else if (c != '\r') cur += c;
        }
    }
    out.push_back(cur);
    return out;
}

static std::string sanitize_key(const std::string& h) {
    std::string k;
    for (char c : h) {
        if (isalnum((unsigned char)c)) k += (char)tolower((unsigned char)c);
        else if (!k.empty() && k.back() != '_') k += '_';
    }
    while (!k.empty() && k.back() == '_') k.pop_back();
    return k;
}

// "17.23%" / "1,234.5" / "-" -> double (NAN si n/d)
static double num(const std::string& raw) {
    std::string s;
    for (char c : raw)
        if (c != '%' && c != ',' && c != '$' && c != ' ') s += c;
    if (s.empty() || s == "-") return NAN;
    char* end = nullptr;
    double v = strtod(s.c_str(), &end);
    if (end == s.c_str()) return NAN;
    return v;
}

// Earnings Date -> epoch (0 si no parsea). Formatos: "7/23/2026 4:30:00 PM",
// "7/23/2026", "2026-07-23 16:30:00", "2026-07-23", "Jul 23/a" (web).
static time_t parse_earnings(const std::string& raw_in) {
    std::string raw = trim(raw_in);
    if (raw.empty() || raw == "-") return 0;
    int hint = 0;  // /a = AMC 16:30, /b = BMO 08:00
    if (raw.size() > 2 && raw[raw.size() - 2] == '/') {
        char c = (char)tolower((unsigned char)raw.back());
        if (c == 'a') hint = 1;
        if (c == 'b') hint = 2;
        if (hint) raw = trim(raw.substr(0, raw.size() - 2));
    }
    const char* fmts[] = {"%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S",
                          "%m/%d/%Y %H:%M", "%m/%d/%Y",
                          "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%b %d %Y", "%b %d"};
    for (const char* f : fmts) {
        struct tm tmv;
        memset(&tmv, 0, sizeof(tmv));
        tmv.tm_isdst = -1;
        char* end = strptime(raw.c_str(), f, &tmv);
        if (!end || *end) continue;
        if (tmv.tm_year == 0) {  // "%b %d" sin año -> el mas cercano al futuro
            time_t now = time(nullptr);
            struct tm nowtm;
            localtime_r(&now, &nowtm);
            tmv.tm_year = nowtm.tm_year;
            if (tmv.tm_mon < nowtm.tm_mon - 6) tmv.tm_year++;
        }
        bool has_time = strstr(f, "%H") || strstr(f, "%I");
        if (!has_time) {
            tmv.tm_hour = (hint == 1) ? 16 : (hint == 2) ? 8 : 12;
            tmv.tm_min = (hint == 1) ? 30 : 0;
        }
        return mktime(&tmv);
    }
    return 0;
}

// ---------- estado por ticker (solo-cambios; primer ciclo silencioso)
struct SymState {
    bool have = false;
    bool gap_alert = false;   // |gap| > 2%
    bool rv_alert = false;    // rel volume > 2.5x
    double sf_ref = NAN;      // short float de referencia (ultima notificada)
    std::string target, recom;
};

static std::map<std::string, std::string> load_earn_notified() {
    std::map<std::string, std::string> m;
    std::ifstream f("data/finviz_earn_notified.txt");
    std::string sym, day;
    while (f >> sym >> day) m[sym] = day;
    return m;
}
static void save_earn_notified(const std::map<std::string, std::string>& m) {
    std::ofstream f("data/finviz_earn_notified.txt", std::ios::trunc);
    for (auto& kv : m) f << kv.first << " " << kv.second << "\n";
}

// ---------- fases de mercado (TZ forzada a America/Toronto = ET)
enum Phase { OFF, PRE, RTH };
static Phase market_phase() {
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    if (lt.tm_wday == 0 || lt.tm_wday == 6) return OFF;  // finde
    int m = lt.tm_hour * 60 + lt.tm_min;
    if (m >= 4 * 60 && m < 9 * 60 + 30) return PRE;
    if (m >= 9 * 60 + 30 && m < 16 * 60) return RTH;
    return OFF;
}

int main(int argc, char** argv) {
    setenv("TZ", "America/Toronto", 1);  // ET siempre, aunque el Mac viaje
    tzset();
    bool once = false;
    std::vector<std::string> extra;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--once")) once = true;
        else extra.push_back(argv[i]);
    }

    std::string token = get_token();
    if (token.empty()) {
        logln("FINVIZ ROTO: sin token (FINVIZ_AUTH3/FINVIZ_AUTH en feeds.env)");
        fleet_notify_urgent("🛰 FINVIZ ROTO", "Sin token en feeds.env — scout muerto");
        return 1;
    }
    curl_global_init(CURL_GLOBAL_DEFAULT);

    std::vector<std::string> syms = build_tickers(extra);
    if (syms.empty()) {
        logln("FINVIZ ROTO: lista de tickers vacia");
        return 1;
    }
    {
        std::string all;
        for (auto& s : syms) all += (all.empty() ? "" : ",") + s;
        logln("finviz_scout arriba | tickers: " + all);
    }

    // Columnas VERIFICADAS (skill finviz-elite): base + Target Price / Recom
    // (sondeadas 2026-07-17 leyendo el header CSV; ver ids abajo). Los ids
    // candidatos se validan contra el header en el primer fetch: si Finviz
    // los mueve, se caen solos y se loguea.
    std::vector<int> base_cols = {1, 6, 24, 25, 26, 30, 31, 59, 60, 61,
                                  63, 64, 65, 66, 67, 68, 70};
    // Sondeados en vivo 2026-07-17 leyendo el header CSV: 62=Analyst Recom,
    // 69=Target Price (vecinos probados 27-58 y 71-85: fundamentales/AH/etc).
    std::vector<int> cand_cols = {62, 69};
    bool probed = false;
    std::vector<int> cols = base_cols;  // primer fetch: base+candidatos
    for (int c : cand_cols) cols.push_back(c);

    std::map<std::string, SymState> state;
    auto earn_notified = load_earn_notified();
    bool broken_banner = false;
    time_t last_req = 0;

    for (;;) {
        Phase ph = market_phase();
        if (ph == OFF && !once) {
            sleep(300);  // fuera de horario: chequeo cada 5 min
            continue;
        }
        // rate limit duro: jamas <60s entre requests
        time_t now = time(nullptr);
        if (last_req && now - last_req < 60) sleep((unsigned)(60 - (now - last_req)));

        // focus_ticker cambia durante el dia: re-leer cada ciclo (log al cambiar)
        {
            std::vector<std::string> fresh = build_tickers(extra);
            if (!fresh.empty() && fresh != syms) {
                syms = fresh;
                std::string all;
                for (auto& s : syms) all += (all.empty() ? "" : ",") + s;
                logln("tickers actualizados: " + all);
            }
        }

        // URL: UN request con la flota completa
        std::string tlist, clist;
        for (auto& s : syms) tlist += (tlist.empty() ? "" : ",") + s;
        {
            std::vector<int> sorted = cols;
            std::sort(sorted.begin(), sorted.end());
            sorted.erase(std::unique(sorted.begin(), sorted.end()), sorted.end());
            for (int c : sorted) clist += (clist.empty() ? "" : ",") + std::to_string(c);
            cols = sorted;
        }
        std::string url = "https://elite.finviz.com/export/screener?v=152&t=" +
                          tlist + "&auth=" + token + "&c=" + clist;
        last_req = time(nullptr);
        HttpResp r = http_get(url);

        // ---- validacion: fallar EN VOZ ALTA, jamas silencio
        std::string fail;
        if (!r.ok) fail = "transporte curl fallo";
        else if (r.code == 429) fail = "HTTP 429 rate limit";
        else if (r.code != 200) fail = "HTTP " + std::to_string(r.code);
        else if (trim(r.body).empty()) fail = "CSV vacio (token/URL rotos?)";
        else if (r.body[0] == '<') fail = "HTML devuelto (login/token roto)";
        else if (r.body.find("Ticker") == std::string::npos)
            fail = "header sin Ticker (formato roto)";
        if (!fail.empty()) {
            logln("FINVIZ ROTO: " + fail + " — reintento en 5 min");
            if (!broken_banner) {
                fleet_notify_urgent("🛰 FINVIZ ROTO", (fail + " — reintento 5min").c_str());
                broken_banner = true;
            }
            if (once) return 1;
            sleep(300);  // backoff (tambien 429)
            continue;
        }
        if (broken_banner) {
            logln("FINVIZ recuperado");
            fleet_notify_urgent("🛰 FINVIZ", "Feed recuperado — scout de vuelta");
            broken_banner = false;
        }

        // ---- parse
        std::stringstream body(r.body);
        std::string line;
        std::getline(body, line);
        std::vector<std::string> header = csv_split(line);
        int i_tick = -1, i_gap = -1, i_rv = -1, i_sf = -1, i_earn = -1,
            i_tgt = -1, i_rec = -1;
        for (int i = 0; i < (int)header.size(); i++) {
            std::string h = header[i];
            if (h == "Ticker") i_tick = i;
            else if (h == "Gap") i_gap = i;
            else if (h == "Relative Volume") i_rv = i;
            else if (h == "Short Float") i_sf = i;
            else if (h.find("Earnings") != std::string::npos) i_earn = i;
            else if (h.find("Target Price") != std::string::npos) i_tgt = i;
            else if (h.find("Recom") != std::string::npos) i_rec = i;
        }
        // ---- sonda de columnas (solo primera vez): quedarse SOLO con los
        // candidatos que resultaron ser Target Price / Recom
        if (!probed) {
            probed = true;
            std::vector<int> keep = base_cols;
            // header viene en orden ascendente de ids -> mapear posicion->id
            std::vector<int> ids = cols;
            for (int i = 0; i < (int)header.size() && i < (int)ids.size(); i++) {
                bool is_cand = std::find(cand_cols.begin(), cand_cols.end(),
                                         ids[i]) != cand_cols.end();
                if (!is_cand) continue;
                if (header[i].find("Target Price") != std::string::npos ||
                    header[i].find("Recom") != std::string::npos) {
                    keep.push_back(ids[i]);
                    logln("columna extra confirmada: id " + std::to_string(ids[i]) +
                          " = " + header[i]);
                }
            }
            if (keep.size() == base_cols.size())
                logln("Target Price/Recom no estan en los ids sondeados — sigo con base");
            cols = keep;
        }
        if (i_tick < 0) {
            logln("FINVIZ ROTO: sin columna Ticker tras parse");
            if (once) return 1;
            sleep(300);
            continue;
        }

        // ---- filas -> archivos + notificaciones solo-cambios
        time_t ts = time(nullptr);
        struct tm lt;
        localtime_r(&ts, &lt);
        char tbuf[32];
        snprintf(tbuf, sizeof(tbuf), "%04d-%02d-%02d %02d:%02d:%02d",
                 lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday, lt.tm_hour,
                 lt.tm_min, lt.tm_sec);
        char today[16];
        snprintf(today, sizeof(today), "%04d-%02d-%02d", lt.tm_year + 1900,
                 lt.tm_mon + 1, lt.tm_mday);
        int rows = 0;
        while (std::getline(body, line)) {
            if (trim(line).empty()) continue;
            std::vector<std::string> f = csv_split(line);
            if ((int)f.size() <= i_tick) continue;
            std::string sym = upper(trim(f[i_tick]));
            if (sym.empty()) continue;
            rows++;

            // snapshot a data/finviz_<sym>.txt (atomico: tmp+rename)
            std::string path = "data/finviz_" + lower(sym) + ".txt";
            std::string tmp = path + ".tmp";
            {
                std::ofstream o(tmp, std::ios::trunc);
                o << "ts=" << ts << "\ntime=" << tbuf << "\n";
                for (int i = 0; i < (int)header.size() && i < (int)f.size(); i++)
                    o << sanitize_key(header[i]) << "=" << f[i] << "\n";
            }
            rename(tmp.c_str(), path.c_str());

            // ---- deltas
            SymState& st = state[sym];
            double gap = (i_gap >= 0 && i_gap < (int)f.size()) ? num(f[i_gap]) : NAN;
            double rv = (i_rv >= 0 && i_rv < (int)f.size()) ? num(f[i_rv]) : NAN;
            double sf = (i_sf >= 0 && i_sf < (int)f.size()) ? num(f[i_sf]) : NAN;
            std::string earn = (i_earn >= 0 && i_earn < (int)f.size()) ? trim(f[i_earn]) : "";
            std::string tgt = (i_tgt >= 0 && i_tgt < (int)f.size()) ? trim(f[i_tgt]) : "";
            std::string rec = (i_rec >= 0 && i_rec < (int)f.size()) ? trim(f[i_rec]) : "";
            char msg[256];

            if (st.have) {  // sin snapshot previo = sin spam
                // (a) gap abre >±2% (cambio de estado)
                bool ga = !std::isnan(gap) && fabs(gap) > 2.0;
                if (ga && !st.gap_alert) {
                    snprintf(msg, sizeof(msg), "%s: gap %+.1f%% — abre fuera de rango",
                             sym.c_str(), gap);
                    fleet_notify_urgent("🛰 FINVIZ", msg);
                }
                st.gap_alert = ga;
                // (b) rel volume cruza 2.5x
                bool rva = !std::isnan(rv) && rv > 2.5;
                if (rva && !st.rv_alert) {
                    snprintf(msg, sizeof(msg), "%s: rel volume %.1fx — cruza 2.5x",
                             sym.c_str(), rv);
                    fleet_notify_urgent("🛰 FINVIZ", msg);
                }
                st.rv_alert = rva;
                // (c) short float ±0.5pt vs referencia
                if (!std::isnan(sf)) {
                    if (std::isnan(st.sf_ref)) st.sf_ref = sf;
                    else if (fabs(sf - st.sf_ref) >= 0.5) {
                        snprintf(msg, sizeof(msg), "%s: short float %.1f%%→%.1f%% — %s",
                                 sym.c_str(), st.sf_ref, sf,
                                 sf > st.sf_ref ? "combustible de squeeze"
                                                : "cortos cubriendo");
                        fleet_notify_urgent("🛰 FINVIZ", msg);
                        st.sf_ref = sf;
                    }
                }
                // (d) earnings a <48h (una vez/dia por ticker, persistido)
                time_t et = parse_earnings(earn);
                if (et > ts && et - ts < 48 * 3600 && earn_notified[sym] != today) {
                    snprintf(msg, sizeof(msg), "%s: earnings en %ldh (%s)",
                             sym.c_str(), (long)((et - ts) / 3600), earn.c_str());
                    fleet_notify_urgent("🛰 FINVIZ", msg);
                    earn_notified[sym] = today;
                    save_earn_notified(earn_notified);
                }
                // (e) target price / recom cambian (si existen las columnas)
                if (!tgt.empty() && !st.target.empty() && tgt != st.target && tgt != "-") {
                    snprintf(msg, sizeof(msg), "%s: target price %s→%s",
                             sym.c_str(), st.target.c_str(), tgt.c_str());
                    fleet_notify_urgent("🛰 FINVIZ", msg);
                }
                if (!rec.empty() && !st.recom.empty() && rec != st.recom && rec != "-") {
                    double a = num(st.recom), b = num(rec);
                    snprintf(msg, sizeof(msg), "%s: recom %s→%s%s", sym.c_str(),
                             st.recom.c_str(), rec.c_str(),
                             (!std::isnan(a) && !std::isnan(b))
                                 ? (b < a ? " (mejora)" : " (empeora)") : "");
                    fleet_notify_urgent("🛰 FINVIZ", msg);
                }
            } else {
                st.gap_alert = !std::isnan(gap) && fabs(gap) > 2.0;
                st.rv_alert = !std::isnan(rv) && rv > 2.5;
                st.sf_ref = sf;
            }
            if (!tgt.empty()) st.target = tgt;
            if (!rec.empty()) st.recom = rec;
            st.have = true;
        }
        {
            char s[128];
            snprintf(s, sizeof(s), "ciclo OK: %d filas / %d tickers (fase %s)",
                     rows, (int)syms.size(), ph == PRE ? "PRE" : ph == RTH ? "RTH" : "OFF");
            logln(s);
        }
        if (rows == 0) {  // header sano pero cero filas = tickers rotos: en voz alta
            logln("FINVIZ ROTO: 0 filas para " + tlist);
            if (!broken_banner) {
                fleet_notify_urgent("🛰 FINVIZ ROTO", "0 filas devueltas — revisar tickers/token");
                broken_banner = true;
            }
            if (once) return 1;
            sleep(300);
            continue;
        }
        if (once) return 0;
        sleep(ph == PRE ? 60 : 180);
    }
}
