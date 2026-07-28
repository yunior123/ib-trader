// flow_pulse.cpp v4 — detector de cambios DRASTICOS de flujo de opciones
// v4 (2026-07-22 tarde, caso NVDA-calls vs SPY-puts): JERARQUIA DE CAPITANES.
//   SPY/QQQ = capitanes del MERCADO (tropa: toda la flota).
//   SMH     = capitan de MEMORIA (tropa: MU SKHY DRAM SNDK WDC STX LRCX).
//   🎖 CAPITAN REVIERTE: spike de puts del capitan tras spikes de calls de su
//     tropa (<=20 min) = LA reversion del dia -> voz DANGER si SPY/QQQ.
//     (Evidencia 7/22: FLUJO CALLS NVDA 13:02-14:21 con NVDA resbalando;
//     FLUJO PUTS SPY 14:21 -> piso local: NVDA rebota +0.35% hasta 15:04.)
//   INDEX-OVERRIDE: spike de un NOMBRE con spike VIGENTE del capitan en
//     direccion opuesta -> el mensaje avisa "el indice manda" y la
//     probabilidad sale del bucket tipo|override (medido con el tiempo).
// (2026-07-22, Yunior: "incrementos y decrementos drasticos, solo eso, para
// prevenir rebounds" + "mejora el algoritmo, para prevenirnos").
//
// Señales (probabilidades MEDIDAS con replay del dia real, auto-calibradas
// cada tarde por flow_pulse_calibrate.py -> data/flow_pulse_probs.json):
//   🚀 SPIKE CALLS  chorro de calls >=3x su ritmo -> climax comprador ->
//                   rebote a la BAJA (59% base). VETO si band-walk alcista
//                   1m+5m (la excepcion de la espada: continuacion, no fade).
//   🚀 SPIKE PUTS   panico vendedor -> rebote al ALZA (78% base, la joya).
//                   VETO espejo si band-walk bajista.
//   🧱 EN EL MURO   spike con spot a <=0.4% de un muro top-3 OI de su lado:
//                   rebote reforzado (bucket propio en la calibracion).
//   🐺 MANADA       >=3 tickers de la flota con spike/giro de la MISMA
//                   direccion en 12 min -> extremo de MERCADO -> voz DANGER
//                   (el paraguas preventivo; ej. real: NVDA+SMH+AMZN 13:54).
//   🔄 GIRO (banner) ratio P/C rota — contexto; alimenta la manada.
//   (SECADO eliminado: medido 47-50% = sin filo.)
//
// Fuente: tail 1s de data/whale_flow_hist.jsonl (whale watch, ~300s/simbolo).
// Anti-artefacto (cazado 12:22, ratios 790-2873x por relleno del feed):
// spike bilateral o ratio>50x = mudo y sin tocar la EMA; dominancia 2x.
// Anti crying-wolf: cooldown 600s sym+tipo; DANGER solo manada (30 min).
// Solo RTH 9:35-15:55. Gate de spread en cada canto. SEÑAL-SOLAMENTE.
//
// Build: clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o flow_pulse scripts/flow_pulse.cpp
#include <algorithm>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <deque>
#include <fstream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>

using namespace std::chrono_literals;

// ---- knobs (env overrides) ----
static double envd(const char* k, double d) {
    const char* v = getenv(k);
    return v ? atof(v) : d;
}
static const double SPIKE_X    = envd("FP_SPIKE_X", 3.0);
static const double SPIKE_MIN  = envd("FP_SPIKE_MIN", 2000);
static const double GIRO_ABS   = envd("FP_GIRO_ABS", 0.08);
static const double GIRO_REL   = envd("FP_GIRO_REL", 1.30);
static const long   COOLDOWN_S = (long)envd("FP_COOLDOWN", 600);
static const double EMA_A      = 0.40;
static const double WALL_PCT   = envd("FP_WALL_PCT", 0.004);       // <=0.4% del muro
static const int    MANADA_N   = (int)envd("FP_MANADA_N", 3);
static const long   MANADA_W   = (long)envd("FP_MANADA_W", 720);   // ventana 12 min
static const long   MANADA_CD  = (long)envd("FP_MANADA_CD", 1800);
static const long   CAPT_W     = (long)envd("FP_CAPT_W", 1200);    // vigencia capitan 20 min
static const long   CAPREV_CD  = (long)envd("FP_CAPREV_CD", 1800);

// ---- v4: jerarquia de capitanes ----
static bool is_market_captain(const std::string& s) { return s == "SPY" || s == "QQQ"; }
static bool is_captain(const std::string& s) { return is_market_captain(s) || s == "SMH"; }
static bool in_memory_troop(const std::string& s) {
    static const char* M[] = {"MU", "SKHY", "DRAM", "SNDK", "WDC", "STX", "LRCX"};
    for (auto* m : M) if (s == m) return true;
    return false;
}
static std::vector<std::string> captains_of(const std::string& s) {
    if (is_market_captain(s)) return {};                 // el indice no tiene capitan
    std::vector<std::string> v;
    if (in_memory_troop(s)) v.push_back("SMH");          // sector primero, mas cercano
    v.push_back("SPY"); v.push_back("QQQ");
    return v;
}
static bool in_troop_of(const std::string& cap, const std::string& s) {
    if (s == cap) return false;
    if (is_market_captain(cap)) return !is_market_captain(s);   // mercado: todos
    return in_memory_troop(s);                                  // SMH: memoria
}

struct Rec { long ts; std::string sym; double vc, vp, pc, spot; };
struct Hist {
    Rec prev{};
    bool has_prev = false;
    double ema_c = -1, ema_p = -1;    // contratos/min EMA por lado
};

static std::optional<double> jnum(std::string_view line, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = line.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < line.size() && line[p] == ' ') ++p;
    double out{};
    auto [ptr, ec] = std::from_chars(line.data() + p, line.data() + line.size(), out);
    if (ec != std::errc{}) return std::nullopt;
    return out;
}
static std::optional<std::string> jstr(std::string_view line, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":\"";
    auto p = line.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    auto e = line.find('"', p);
    if (e == std::string_view::npos) return std::nullopt;
    return std::string(line.substr(p, e - p));
}
static std::optional<Rec> parse(std::string_view line) {
    auto ts = jnum(line, "ts"), vc = jnum(line, "vc"), vp = jnum(line, "vp"),
         pc = jnum(line, "pc"), spot = jnum(line, "spot");
    auto sym = jstr(line, "sym");
    if (!ts || !sym || !vc || !vp || !pc) return std::nullopt;
    return Rec{(long)*ts, *sym, *vc, *vp, *pc, spot.value_or(0)};
}

static std::string lower(std::string s) {
    for (auto& c : s) c = (char)tolower(c);
    return s;
}

// ---- probabilidades auto-calibradas (data/flow_pulse_probs.json) ----
static std::map<std::string, int> PROBS = {
    {"SPIKE_PUTS|normal", 78}, {"SPIKE_PUTS|muro", 78}, {"SPIKE_PUTS|override", 78},
    {"SPIKE_CALLS|normal", 59}, {"SPIKE_CALLS|muro", 59}, {"SPIKE_CALLS|override", 59},
};
// prob del bucket pedido; si el bucket no esta medido aun cae al fallback
static int prob_of(const std::string& typ, const std::string& ctx, const std::string& fb) {
    auto it = PROBS.find(typ + "|" + ctx);
    if (it != PROBS.end() && it->second > 0) return it->second;
    return PROBS[typ + "|" + fb];
}
static void load_probs() {
    std::ifstream f("data/flow_pulse_probs.json");
    if (!f) return;
    std::string all((std::istreambuf_iterator<char>(f)), {});
    for (auto& [k, v] : PROBS) {
        // los agregados (con "pct") van DESPUES del bloque "days" -> rfind
        auto p = all.rfind("\"" + k + "\"");
        if (p == std::string::npos) continue;
        auto q2 = all.find("\"pct\":", p);
        if (q2 == std::string::npos || q2 > p + 400) continue;
        int pct = atoi(all.c_str() + q2 + 6);
        if (pct > 0 && pct <= 100) v = pct;
    }
}

// ---- Bollinger 1m+5m para el VETO band-walk (math de bollinger_alarm.py) ----
struct Bands { bool ok = false, walk_up = false, walk_dn = false; };
static void bb_of(const std::vector<double>& cl, double& lo, double& up) {
    double m = 0;
    for (double c : cl) m += c;
    m /= cl.size();
    double sd = 0;
    for (double c : cl) sd += (c - m) * (c - m);
    sd = std::sqrt(sd / cl.size());
    lo = m - 2 * sd; up = m + 2 * sd;
}
static Bands bands_of(const std::string& sym) {
    Bands b;
    std::ifstream f("data/bars_" + lower(sym) + "_ibkr.txt");
    if (!f) return b;                                  // sin barras: sin veto (degradacion limpia)
    std::deque<std::pair<long, double>> bars;          // (ts, close)
    std::string ln;
    while (std::getline(f, ln)) {
        std::istringstream ss(ln);
        double t, o, h, l, c;
        if (ss >> t >> o >> h >> l >> c) {
            bars.emplace_back((long)t, c);
            if (bars.size() > 160) bars.pop_front();
        }
    }
    if (bars.size() < 25 || time(nullptr) - bars.back().first > 240) return b;
    std::vector<double> c1;
    for (size_t i = bars.size() - 21; i < bars.size() - 1; ++i) c1.push_back(bars[i].second);
    double lo1, up1; bb_of(c1, lo1, up1);
    double last = bars.back().second;
    std::map<long, double> a5;                         // 5m: cierre = ultimo del bucket 300s
    for (auto& [t, c] : bars) a5[t - t % 300] = c;
    if (a5.size() < 21) { b.ok = true; return b; }     // sin 5m suficiente: sin veto
    std::vector<double> c5;
    for (auto& [k2, c] : a5) c5.push_back(c);
    double last5 = c5.back();
    std::vector<double> c5w(c5.end() - 21, c5.end() - 1);
    double lo5, up5; bb_of(c5w, lo5, up5);
    b.ok = true;
    b.walk_up = last > up1 && last5 > up5;
    b.walk_dn = last < lo1 && last5 < lo5;
    return b;
}

// ---- cadena: gate de spread + muro top-3 OI del lado del spike ----
struct ChainInfo { std::string veh = "OPCIONES s/d — default ACCIONES"; double wall = 0; };
static ChainInfo chain_info(const std::string& sym, char side, double spot_hint) {
    ChainInfo ci;
    std::ifstream f("data/opt_chain_" + lower(sym) + ".txt");
    if (!f) return ci;
    std::string ln;
    double spot = spot_hint; long epoch = 0;
    std::string exp0;
    double best_dist = 1e18, best_pct = -1;
    std::vector<std::pair<double, double>> side_oi;    // (oi, strike) lado pedido, exp cercano
    while (std::getline(f, ln)) {
        if (ln.starts_with("#")) {
            if (auto p = ln.find("epoch "); p != std::string::npos)
                epoch = atol(ln.c_str() + p + 6);
            if (spot <= 0)
                if (auto p = ln.find("spot "); p != std::string::npos)
                    spot = atof(ln.c_str() + p + 5);
            continue;
        }
        if (spot <= 0 || (epoch && time(nullptr) - epoch > 900)) break;
        std::istringstream ss(ln);
        double k, bid, ask, vol, oi;
        std::string right, exp;
        if (!(ss >> k >> right >> exp >> bid >> ask >> vol >> oi)) continue;
        if (exp0.empty()) exp0 = exp;
        if (exp == exp0 && right[0] == side && oi > 0) side_oi.push_back({oi, k});
        if (bid <= 0 || ask <= 0 || ask > 3.5 || oi < 200) continue;
        bool otm = (right == "P") ? k < spot : k > spot;
        if (!otm) continue;
        double dist = std::fabs(k - spot) / spot;
        if (dist < best_dist) { best_dist = dist; best_pct = (ask - bid) / ask * 100; }
    }
    if (best_pct >= 0) {
        char buf[80];
        if (best_pct <= 5.0) snprintf(buf, sizeof buf, "OPCIONES OK (spread %.0f%%)", best_pct);
        else snprintf(buf, sizeof buf, "OPCIONES VETADAS spread %.0f%% — acciones/ETF", best_pct);
        ci.veh = buf;
    }
    std::sort(side_oi.rbegin(), side_oi.rend());
    for (size_t i = 0; i < side_oi.size() && i < 3; ++i)
        if (spot > 0 && std::fabs(side_oi[i].second - spot) / spot <= WALL_PCT) {
            ci.wall = side_oi[i].second;
            break;
        }
    return ci;
}

static void shell_bg(const std::string& cmd) {
    if (getenv("FP_TEST")) return;               // test: sin voz ni banners reales
    if (fork() == 0) {
        execl("/bin/bash", "bash", "-c", cmd.c_str(), (char*)nullptr);
        _exit(127);
    }
}
static std::string q(const std::string& s) {
    std::string o = "'";
    for (char c : s) { if (c == '\'') o += "'\\''"; else o += c; }
    return o + "'";
}
static void sing(const std::string& title, const std::string& msg, bool voice,
                 const char* prio = "SIGNAL") {
    if (getenv("FP_TEST")) { printf("[%s] ", voice ? prio : "MUTE"); }   // harness: prio visible
    if (voice) shell_bg(std::string("scripts/speak.sh ") + prio + " " + q(msg));
    shell_bg("/usr/bin/osascript -e " + q("display notification \"" + msg +
             "\" with title \"" + title + "\" sound name \"ProAlert\""));
    time_t t = time(nullptr);
    tm lt{}; localtime_r(&t, &lt);
    char path[256], line[640];
    snprintf(path, sizeof path, "data/trading-signals/%04d-%02d-%02d.txt",
             lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday);
    snprintf(line, sizeof line, "%02d:%02d:%02d | %s | %s\n",
             lt.tm_hour, lt.tm_min, lt.tm_sec, title.c_str(), msg.c_str());
    if (FILE* f = fopen(path, "a")) { fputs(line, f); fclose(f); }
    printf("%s", line); fflush(stdout);
}

static bool rth_open() {
    if (getenv("FP_FORCE_OPEN")) return true;    // tests fuera de horario
    time_t t = time(nullptr);
    tm lt{}; localtime_r(&t, &lt);
    int hm = lt.tm_hour * 100 + lt.tm_min;
    return lt.tm_wday >= 1 && lt.tm_wday <= 5 && hm >= 935 && hm < 1555;
}

static double qqq_spot() {
    std::ifstream f("data/nbbo_qqq.txt");
    double t, b, a;
    if (f >> t >> b >> a) return (b + a) / 2;
    return 0;
}

int main() {
    // fuera de RTH: salir MUDO antes de cantar nada. Cazado 2026-07-28: el launcher relanzaba
    // cada 5 min toda la noche -> banner "arriba" + "fuera hasta manana" en bucle (16:00-24:00).
    if (!rth_open()) {
        fprintf(stderr, "flow_pulse: fuera de RTH, salida silenciosa\n");
        return 0;
    }
    std::map<std::string, Hist> hist;
    std::map<std::string, long> cool;
    auto cooled = [&](const std::string& k, long cd = 0) {
        long now = time(nullptr);
        if (now - cool[k] < (cd ? cd : COOLDOWN_S)) return false;
        cool[k] = now; return true;
    };
    std::deque<std::pair<long, std::string>> herd_p, herd_c;   // manada por direccion
    auto herd_add = [&](std::deque<std::pair<long, std::string>>& hd, const Rec& r,
                        const char* dir) {
        long now = time(nullptr);
        hd.emplace_back(now, r.sym);
        while (!hd.empty() && now - hd.front().first > MANADA_W) hd.pop_front();
        std::map<std::string, int> uniq;
        for (auto& [t, s] : hd) uniq[s] = 1;
        if ((int)uniq.size() >= MANADA_N && cooled(std::string("MANADA|") + dir, MANADA_CD)) {
            std::string lista;
            for (auto& [s, one] : uniq) lista += s + " ";
            char m[512];
            snprintf(m, sizeof m, "MANADA A %s: %d tickers en 12 minutos — %s. Extremo de "
                     "mercado, rebote del indice %s probable. QQQ %.2f",
                     dir, (int)uniq.size(), lista.c_str(),
                     std::string(dir) == "PUTS" ? "al alza" : "a la baja", qqq_spot());
            sing(std::string("🐺 MANADA A ") + dir, m, true, "DANGER");
        }
    };

    // ---- v4: estado de capitanes + spikes de tropa (ventana CAPT_W) ----
    struct CapState { char dir = 0; long ts = 0; };            // 'C'/'P'
    std::map<std::string, CapState> cap_last;
    std::deque<std::tuple<long, std::string, char>> troop_spk; // (ts, sym, dir)
    auto note_spike = [&](const std::string& sym, char dir) {
        long now = time(nullptr);
        if (is_captain(sym)) cap_last[sym] = {dir, now};
        troop_spk.emplace_back(now, sym, dir);
        while (!troop_spk.empty() && now - std::get<0>(troop_spk.front()) > CAPT_W)
            troop_spk.pop_front();
    };
    // capitan vigente en direccion OPUESTA al spike del nombre -> nota de override
    auto override_note = [&](const std::string& sym, char my_dir) -> std::string {
        long now = time(nullptr);
        for (const auto& c : captains_of(sym)) {
            auto it = cap_last.find(c);
            if (it == cap_last.end()) continue;
            if (it->second.dir == my_dir || now - it->second.ts > CAPT_W) continue;
            char buf[300];
            long mins = (now - it->second.ts) / 60;
            snprintf(buf, sizeof buf, " OJO: %s mando flujo de %s hace %ld min — el "
                     "indice manda, el %s de %s puede abortarse", c.c_str(),
                     it->second.dir == 'P' ? "puts" : "calls", mins,
                     my_dir == 'C' ? "fade a la baja" : "rebote al alza", sym.c_str());
            return buf;
        }
        return "";
    };
    // 🎖 capitan revierte: spike del capitan tras spikes opuestos de su tropa
    auto capitan_revierte = [&](const Rec& r, char cap_dir) {
        if (!is_captain(r.sym)) return;
        long now = time(nullptr);
        char troop_dir = cap_dir == 'P' ? 'C' : 'P';
        std::map<std::string, int> uniq;
        for (auto& [t, s, d] : troop_spk)
            if (d == troop_dir && now - t <= CAPT_W && in_troop_of(r.sym, s)) uniq[s] = 1;
        if (uniq.empty() || !cooled("CAPREV|" + r.sym, CAPREV_CD)) return;
        std::string lista;
        for (auto& [s, one] : uniq) lista += s + " ";
        if (!lista.empty()) lista.pop_back();
        bool market = is_market_captain(r.sym);
        char m[512];
        if (cap_dir == 'P')
            snprintf(m, sizeof m, "%s dispara puts tras el climax de calls de %s — "
                     "reversion %s probable: piso local, rebote al alza. Los nombres "
                     "obedecen al capitan.", r.sym.c_str(), lista.c_str(),
                     market ? "de mercado" : "del sector memoria");
        else
            snprintf(m, sizeof m, "%s dispara calls tras el panico de puts de %s — "
                     "reversion %s probable: techo local, fade a la baja. Los nombres "
                     "obedecen al capitan.", r.sym.c_str(), lista.c_str(),
                     market ? "de mercado" : "del sector memoria");
        sing("🎖 CAPITAN REVIERTE " + r.sym, m, true, market ? "DANGER" : "SIGNAL");
    };

    const char* path = "data/whale_flow_hist.jsonl";
    off_t off = 0;
    { struct stat st{}; if (!stat(path, &st)) off = st.st_size; }

    load_probs();
    char hello[240];
    snprintf(hello, sizeof hello, "Pulso de flujo v4 arriba: spikes %.0fx con veto band-walk, "
             "muros OI, manada y jerarquia de capitanes SPY QQQ SMH. "
             "Probabilidades vivas: puts %d, calls %d",
             SPIKE_X, PROBS["SPIKE_PUTS|normal"], PROBS["SPIKE_CALLS|normal"]);
    sing("🌊 FLOW PULSE v4", hello, false);

    while (true) {
        time_t t0 = time(nullptr);
        tm lt{}; localtime_r(&t0, &lt);
        if (!getenv("FP_FORCE_OPEN") &&
            (lt.tm_hour * 100 + lt.tm_min >= 1556 || lt.tm_wday == 0 || lt.tm_wday == 6)) break;

        struct stat st{};
        if (stat(path, &st) == 0 && st.st_size != off) {
            if (st.st_size < off) off = 0;
            std::ifstream f(path);
            f.seekg(off);
            std::string ln;
            while (std::getline(f, ln)) {
                auto r = parse(ln);
                if (!r) continue;
                Hist& h = hist[r->sym];
                bool fresh = time(nullptr) - r->ts < 120;
                if (h.has_prev && r->ts > h.prev.ts) {
                    double mins = (r->ts - h.prev.ts) / 60.0;
                    if (mins >= 1.0 && mins <= 30.0) {
                        double dc = r->vc - h.prev.vc, dp = r->vp - h.prev.vp;
                        if (dc >= 0 && dp >= 0) {
                            double rc = dc / mins, rp = dp / mins;
                            char m[512];
                            bool spike_c = h.ema_c > 0 && rc >= SPIKE_X * h.ema_c && dc >= SPIKE_MIN;
                            bool spike_p = h.ema_p > 0 && rp >= SPIKE_X * h.ema_p && dp >= SPIKE_MIN;
                            // ARTEFACTO: relleno del feed tras hueco -> mudo, EMA intacta
                            bool artifact = (spike_c && spike_p) ||
                                (h.ema_c > 0 && rc > 50 * h.ema_c) ||
                                (h.ema_p > 0 && rp > 50 * h.ema_p);
                            if (artifact) { h.prev = *r; h.has_prev = true; continue; }
                            // ---- SPIKE CALLS: climax comprador -> fade, salvo band-walk
                            if (fresh && rth_open() && spike_c && dc >= 2 * dp &&
                                cooled(r->sym + "|SC")) {
                                Bands b = bands_of(r->sym);
                                if (b.ok && b.walk_up) {
                                    snprintf(m, sizeof m, "SPIKE de calls en %s (%.0fk, %.0fx) "
                                             "pero BAND-WALK alcista 1m+5m — climax si, fade NO: "
                                             "continuacion probable", r->sym.c_str(), dc / 1000,
                                             rc / h.ema_c);
                                    sing("🚀 SPIKE CALLS (VETADO) " + r->sym, m, false);
                                } else {
                                    ChainInfo ci = chain_info(r->sym, 'C', r->spot);
                                    std::string ovr = override_note(r->sym, 'C');
                                    const char* ctx = !ovr.empty() ? "override"
                                                    : ci.wall > 0 ? "muro" : "normal";
                                    int pr = prob_of("SPIKE_CALLS", ctx,
                                                     ci.wall > 0 ? "muro" : "normal");
                                    if (ci.wall > 0)
                                        snprintf(m, sizeof m, "SPIKE de calls en %s EN EL MURO "
                                                 "%.6g: %.0f mil contratos, %.0f veces su ritmo. "
                                                 "Climax contra la pared — rebote a la baja "
                                                 "reforzado, probabilidad %d. %s", r->sym.c_str(),
                                                 ci.wall, dc / 1000, rc / h.ema_c, pr, ci.veh.c_str());
                                    else
                                        snprintf(m, sizeof m, "SPIKE de calls en %s: %.0f mil "
                                                 "contratos, %.0f veces su ritmo. Climax comprador "
                                                 "— rebote a la baja, probabilidad %d. %s",
                                                 r->sym.c_str(), dc / 1000, rc / h.ema_c, pr,
                                                 ci.veh.c_str());
                                    std::string msg = std::string(m) + ovr;
                                    // regla 12: capitan opuesto vigente = el nombre
                                    // queda ANULADO (banner sin voz; la voz es del capitan)
                                    sing(std::string(!ovr.empty() ? "🔇🚀 SPIKE CALLS (capitan opuesto) "
                                         : ci.wall > 0 ? "🧱🚀 SPIKE CALLS " : "🚀 SPIKE CALLS ")
                                         + r->sym, msg, ovr.empty());
                                    capitan_revierte(*r, 'C');   // capitan-calls tras puts de tropa
                                }
                                note_spike(r->sym, 'C');         // v4: jerarquia (vetado o no)
                                herd_add(herd_c, *r, "CALLS");   // el extremo cuenta, vetado o no
                            }
                            // ---- SPIKE PUTS: panico vendedor -> rebote, salvo band-walk abajo
                            if (fresh && rth_open() && spike_p && dp >= 2 * dc &&
                                cooled(r->sym + "|SP")) {
                                Bands b = bands_of(r->sym);
                                if (b.ok && b.walk_dn) {
                                    snprintf(m, sizeof m, "SPIKE de puts en %s (%.0fk, %.0fx) "
                                             "pero BAND-WALK bajista 1m+5m — panico si, rebote NO: "
                                             "continuacion probable", r->sym.c_str(), dp / 1000,
                                             rp / h.ema_p);
                                    sing("🚀 SPIKE PUTS (VETADO) " + r->sym, m, false);
                                } else {
                                    ChainInfo ci = chain_info(r->sym, 'P', r->spot);
                                    std::string ovr = override_note(r->sym, 'P');
                                    const char* ctx = !ovr.empty() ? "override"
                                                    : ci.wall > 0 ? "muro" : "normal";
                                    int pr = prob_of("SPIKE_PUTS", ctx,
                                                     ci.wall > 0 ? "muro" : "normal");
                                    if (ci.wall > 0)
                                        snprintf(m, sizeof m, "SPIKE de puts en %s EN EL MURO "
                                                 "%.6g: %.0f mil contratos, %.0f veces su ritmo. "
                                                 "Panico contra el piso — rebote al alza reforzado, "
                                                 "probabilidad %d. %s", r->sym.c_str(), ci.wall,
                                                 dp / 1000, rp / h.ema_p, pr, ci.veh.c_str());
                                    else
                                        snprintf(m, sizeof m, "SPIKE de puts en %s: %.0f mil "
                                                 "contratos, %.0f veces su ritmo. Panico vendedor — "
                                                 "rebote al alza, probabilidad %d. %s",
                                                 r->sym.c_str(), dp / 1000, rp / h.ema_p, pr,
                                                 ci.veh.c_str());
                                    std::string msg = std::string(m) + ovr;
                                    // regla 12: capitan opuesto vigente = anulado sin voz
                                    sing(std::string(!ovr.empty() ? "🔇🚀 SPIKE PUTS (capitan opuesto) "
                                         : ci.wall > 0 ? "🧱🚀 SPIKE PUTS " : "🚀 SPIKE PUTS ")
                                         + r->sym, msg, ovr.empty());
                                    capitan_revierte(*r, 'P');   // EL caso del dia (SPY tras NVDA)
                                }
                                note_spike(r->sym, 'P');         // v4: jerarquia (vetado o no)
                                herd_add(herd_p, *r, "PUTS");
                            }
                            // ---- GIRO de ratio: banner; alimenta la manada
                            if (fresh && rth_open() && h.prev.pc > 0.01) {
                                if (r->pc - h.prev.pc >= GIRO_ABS && r->pc / h.prev.pc >= GIRO_REL &&
                                    cooled(r->sym + "|GP")) {
                                    snprintf(m, sizeof m, "%s girando a puts: ratio %.2f desde %.2f",
                                             r->sym.c_str(), r->pc, h.prev.pc);
                                    sing("🔄 GIRO A PUTS " + r->sym, m, false);
                                    herd_add(herd_p, *r, "PUTS");
                                } else if (h.prev.pc - r->pc >= GIRO_ABS &&
                                           r->pc / h.prev.pc <= 1.0 / GIRO_REL &&
                                           cooled(r->sym + "|GC")) {
                                    snprintf(m, sizeof m, "%s girando a calls: ratio %.2f desde %.2f",
                                             r->sym.c_str(), r->pc, h.prev.pc);
                                    sing("🔄 GIRO A CALLS " + r->sym, m, false);
                                    herd_add(herd_c, *r, "CALLS");
                                }
                            }
                            h.ema_c = h.ema_c < 0 ? rc : EMA_A * rc + (1 - EMA_A) * h.ema_c;
                            h.ema_p = h.ema_p < 0 ? rp : EMA_A * rp + (1 - EMA_A) * h.ema_p;
                        }
                    }
                }
                h.prev = *r; h.has_prev = true;
            }
            off = f.tellg() == -1 ? st.st_size : (off_t)f.tellg();
        }
        std::this_thread::sleep_for(1s);
    }
    sing("🌊 FLOW PULSE v4", "15:56 — pulso de flujo fuera hasta manana", false);
    return 0;
}
