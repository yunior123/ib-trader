// qqq_xray.cpp — radiografía instantánea del QQQ por dentro (señal-solamente).
//
// LEY #0 (Yunior 2026-07-16): SEÑAL-SOLAMENTE. Este binario JAMÁS toca el
// broker: solo LEE archivos locales (data/qqq_weights.txt, data/bars_*_ibkr.txt,
// data/nbbo_*.txt, data/opt_chain_*.txt) y notifica (banner/voz/Desktop).
// Cero ordenes al broker, cero sockets, cero TWS.
//
// Nace del 2026-07-16 ("el mejor día"): QQQ atascado = descomponer el índice.
// DIQUE (MSFT+AAPL ~16%) verde + semis sangrando = empate interno → NO operar
// el índice, operar el semi puro. Hoy se hizo a mano con python lento; esto
// lo imprime en <50ms.
//
// Uso:
//   ./qqq_xray                  radiografía única (lee data/)
//   ./qqq_xray --watch          loop 60s; en CAMBIO de estado del dique o del
//                               veredicto: banner Mac + voz Paulina + línea en
//                               ~/Desktop/trading-signals/YYYY-MM-DD.txt
//                               (anti-spam: solo en cambio, jamás cada tick)
//   ./qqq_xray --data DIR       usar otro directorio de datos (tests sintéticos)
//
// Compilar (UNO a la vez, 8GB): clang++ -std=c++17 -O2 -o qqq_xray scripts/qqq_xray.cpp
//
// Miembros sin feed (COST/NFLX hasta que el bridge los streamee) → "s/d" y los
// pesos presentes se renormalizan al total del config.

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <sstream>
#include <string>
#include <unistd.h>
#include <vector>

static std::string DATA_DIR = "data";

struct Bar { long ts; double o, h, l, c, v; };

struct Member {
    std::string sym;      // mayúsculas
    double weight = 0;    // % del índice (config)
    bool has_data = false;
    double price = 0;     // nbbo mid fresco o último close
    double prev_close = 0;
    double pct = 0;       // % día
    double contrib = 0;   // peso_renormalizado × pct / 100 (puntos de índice en %)
    double slope_pct = 0; // % proyectado del fit OLS sobre 30 closes 1m
    int struct_sign = 0;  // +1 HH/HL, -1 LH/LL, 0 mixto
    std::string trend = "s/d";
    double rvol = -1;     // última barra vs media 20
    double pc = -1;       // put/call por volumen
    long last_ts = 0;
};

static std::string lower(std::string s) {
    for (auto &c : s) c = (char)tolower((unsigned char)c);
    return s;
}

static std::vector<Bar> read_bars(const std::string &sym) {
    std::vector<Bar> out;
    std::ifstream f(DATA_DIR + "/bars_" + lower(sym) + "_ibkr.txt");
    if (!f) return out;
    Bar b;
    while (f >> b.ts >> b.o >> b.h >> b.l >> b.c >> b.v) out.push_back(b);
    return out;
}

// nbbo_<sym>.txt : "EPOCH BID ASK" — usar el mid solo si es tan fresco como la última barra
static bool read_nbbo(const std::string &sym, long &ts, double &mid) {
    std::ifstream f(DATA_DIR + "/nbbo_" + lower(sym) + ".txt");
    if (!f) return false;
    double bid, ask;
    if (!(f >> ts >> bid >> ask)) return false;
    if (bid <= 0 || ask <= 0) return false;
    mid = (bid + ask) / 2.0;
    return true;
}

static std::string day_of(long epoch) {
    time_t t = (time_t)epoch;
    struct tm tmv;
    localtime_r(&t, &tmv);            // reloj del Mac = ET
    char buf[16];
    strftime(buf, sizeof buf, "%Y-%m-%d", &tmv);
    return buf;
}

// close de ayer: 1) último close del día previo en el intradía;
// 2) data/<sym>_daily.csv (última fila con fecha < hoy);
// 3) open de la primera barra del día; 4) primera barra disponible.
static double prev_close_of(const std::string &sym, const std::vector<Bar> &bars) {
    if (bars.empty()) return 0;
    std::string today = day_of(bars.back().ts);
    for (int i = (int)bars.size() - 1; i >= 0; --i)
        if (day_of(bars[i].ts) != today) return bars[i].c;
    // un solo día en el archivo → probar daily csv
    std::ifstream f(DATA_DIR + "/" + lower(sym) + "_daily.csv");
    if (f) {
        std::string line, best;
        std::getline(f, line);                      // header
        while (std::getline(f, line))
            if (line.size() > 10 && line.substr(0, 10) < today) best = line;
        if (!best.empty()) {
            std::stringstream ss(best);
            std::string cell; double close = 0;
            for (int i = 0; i < 5 && std::getline(ss, cell, ','); ++i)
                if (i == 4) close = atof(cell.c_str());
            if (close > 0) return close;
        }
    }
    // primera barra del día (== primera disponible si el archivo abre hoy)
    for (const auto &b : bars)
        if (day_of(b.ts) == today) return b.o > 0 ? b.o : b.c;
    return bars.front().c;
}

// tendencia: OLS sobre los últimos 30 closes 1m + estructura HH/HL vs LH/LL
static void trend_of(const std::vector<Bar> &bars, Member &m) {
    int n = (int)bars.size();
    int win = std::min(30, n);
    if (win < 5) { m.trend = "s/d"; return; }
    double sx = 0, sy = 0, sxy = 0, sxx = 0;
    for (int i = 0; i < win; ++i) {
        double y = bars[n - win + i].c;
        sx += i; sy += y; sxy += (double)i * y; sxx += (double)i * i;
    }
    double denom = win * sxx - sx * sx;
    double slope = denom != 0 ? (win * sxy - sx * sy) / denom : 0;
    m.slope_pct = bars.back().c > 0 ? slope * (win - 1) / bars.back().c * 100.0 : 0;
    int slope_sign = m.slope_pct > 0.05 ? 1 : (m.slope_pct < -0.05 ? -1 : 0);

    // pivotes (k=2) sobre las últimas 180 barras → últimos swings
    int lo = std::max(0, n - 180);
    std::vector<double> sh, sl;
    for (int i = lo + 2; i < n - 2; ++i) {
        const auto &b = bars[i];
        if (b.h > bars[i-1].h && b.h > bars[i-2].h && b.h >= bars[i+1].h && b.h >= bars[i+2].h)
            sh.push_back(b.h);
        if (b.l < bars[i-1].l && b.l < bars[i-2].l && b.l <= bars[i+1].l && b.l <= bars[i+2].l)
            sl.push_back(b.l);
    }
    m.struct_sign = 0;
    if (sh.size() >= 2 && sl.size() >= 2) {
        bool hh = sh.back() > sh[sh.size()-2], hl = sl.back() > sl[sl.size()-2];
        bool lh = sh.back() < sh[sh.size()-2], ll = sl.back() < sl[sl.size()-2];
        if (hh && hl) m.struct_sign = 1;
        else if (lh && ll) m.struct_sign = -1;
    }
    int s = slope_sign + m.struct_sign;
    m.trend = s > 0 ? "ALCISTA" : (s < 0 ? "BAJISTA" : "LATERAL");
}

static double rvol_of(const std::vector<Bar> &bars) {
    int n = (int)bars.size();
    if (n < 21) return -1;
    double sum = 0;
    for (int i = n - 21; i < n - 1; ++i) sum += bars[i].v;
    double avg = sum / 20.0;
    return avg > 0 ? bars.back().v / avg : -1;
}

// P/C por volumen desde data/opt_chain_<sym>.txt (vol -1/n-d se ignora)
static double pc_of(const std::string &sym) {
    std::ifstream f(DATA_DIR + "/opt_chain_" + lower(sym) + ".txt");
    if (!f) return -1;
    std::string line;
    double cv = 0, pv = 0;
    while (std::getline(f, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::stringstream ss(line);
        double strike, bid, ask, vol; std::string right, exp;
        if (!(ss >> strike >> right >> exp >> bid >> ask >> vol)) continue;
        if (vol <= 0) continue;
        if (right == "C") cv += vol; else if (right == "P") pv += vol;
    }
    return cv > 0 ? pv / cv : -1;
}

static bool load_member(Member &m) {
    auto bars = read_bars(m.sym);
    if (bars.empty()) return false;
    m.last_ts = bars.back().ts;
    m.prev_close = prev_close_of(m.sym, bars);
    long nts; double mid;
    m.price = bars.back().c;
    if (read_nbbo(m.sym, nts, mid) && nts >= m.last_ts) { m.price = mid; m.last_ts = nts; }
    if (m.prev_close > 0) m.pct = (m.price / m.prev_close - 1.0) * 100.0;
    trend_of(bars, m);
    m.rvol = rvol_of(bars);
    m.pc = pc_of(m.sym);
    m.has_data = true;
    return true;
}

static std::string q_escape(const std::string &s) {
    std::string out;
    for (char c : s) if (c != '"' && c != '\\' && c != '\'') out += c;
    return out;
}

// notificación de cambio de estado (banner + voz + Desktop) — nunca cada tick
static void notify(const std::string &msg) {
    std::string m = q_escape(msg);
    // ProAlert = sonido de BALLENAS/muros (eleccion Yunior 2026-07-18); voz via
    // cola serializada speak.sh (el say -v directo se pisaba con otras alarmas).
    std::string cmd = "osascript -e 'delay (random number from 0.0 to 0.45)' "
                      "-e 'display notification \"" + m +
                      "\" with title \"QQQ X-RAY\" sound name \"ProAlert\"' "
                      "-e 'delay 0.6' >/dev/null 2>&1 & "
                      "scripts/speak.sh SIGNAL \"" + m + "\" >/dev/null 2>&1";
    system(cmd.c_str());
    const char *home = getenv("HOME");
    if (!home) return;
    time_t now = time(nullptr);
    struct tm tmv; localtime_r(&now, &tmv);
    char day[16], hm[8];
    strftime(day, sizeof day, "%Y-%m-%d", &tmv);
    strftime(hm, sizeof hm, "%H:%M", &tmv);
    std::string dir = std::string(home) + "/Desktop/trading-signals";
    system(("mkdir -p '" + dir + "'").c_str());
    std::ofstream f(dir + "/" + day + ".txt", std::ios::app);
    if (f) f << hm << " QQQ-XRAY | " << msg << "\n";
}

struct Snapshot {
    std::vector<Member> members;
    Member qqq;                 // el índice mismo
    double contrib_sum = 0;     // Σ peso_renorm × pct / 100
    double w_present = 0, w_total = 0;
    std::string dique, lastre, verdict;
    double dam_avg = 0, sem_avg = 0;
};

static Snapshot build() {
    Snapshot s;
    std::ifstream wf(DATA_DIR + "/qqq_weights.txt");
    std::string line;
    while (std::getline(wf, line)) {
        std::stringstream ss(line);
        std::string sym; double w;
        if (line.empty() || line[0] == '#' || !(ss >> sym >> w)) continue;
        Member m; m.sym = sym; m.weight = w;
        load_member(m);
        s.w_total += w;
        if (m.has_data) s.w_present += w;
        s.members.push_back(m);
    }
    double renorm = s.w_present > 0 ? s.w_total / s.w_present : 1.0;
    for (auto &m : s.members)
        if (m.has_data) { m.contrib = m.weight * renorm * m.pct / 100.0; s.contrib_sum += m.contrib; }

    s.qqq.sym = "QQQ"; s.qqq.weight = 0;
    load_member(s.qqq);

    // DIQUE = MSFT+AAPL (los presentes); LASTRE = NVDA+AVGO(+AMD si hay barras)
    double dam_sum = 0, dam_min = 1e9; int dam_n = 0;
    double sem_sum = 0; int sem_n = 0;
    for (const auto &m : s.members) {
        if (!m.has_data) continue;
        if (m.sym == "MSFT" || m.sym == "AAPL") {
            dam_sum += m.pct; dam_min = std::min(dam_min, m.pct); ++dam_n;
        }
        if (m.sym == "NVDA" || m.sym == "AVGO") { sem_sum += m.pct; ++sem_n; }
    }
    Member amd; amd.sym = "AMD";
    if (load_member(amd)) { sem_sum += amd.pct; ++sem_n; }

    if (dam_n == 0) s.dique = "s/d";
    else {
        s.dam_avg = dam_sum / dam_n;
        if (s.dam_avg >= 0.05 && dam_min > -0.10) s.dique = "VERDE";
        else if (s.dam_avg <= -0.35 || dam_min <= -0.60) s.dique = "ROTO";
        else s.dique = "MIXTO";
    }
    if (sem_n == 0) s.lastre = "s/d";
    else {
        s.sem_avg = sem_sum / sem_n;
        s.lastre = s.sem_avg <= -0.40 ? "SANGRAN" : (s.sem_avg >= 0.40 ? "EMPUJAN" : "NEUTRO");
    }

    if (s.dique == "VERDE" && s.lastre == "SANGRAN")
        s.verdict = "DIQUE aguanta + semis sangran = empate interno, no operar QQQ — operar el semi puro";
    else if (s.dique == "ROTO" && s.lastre == "SANGRAN")
        s.verdict = "DIQUE cayo + semis sangran = alineados abajo, indice libre abajo — operar QQQ";
    else if (s.dique == "ROTO")
        s.verdict = "DIQUE cayo = indice libre abajo — QQQ vulnerable";
    else if (s.dique == "VERDE" && s.lastre == "EMPUJAN")
        s.verdict = "DIQUE y semis alineados arriba — operar el indice largo";
    else if (s.dique == "VERDE")
        s.verdict = "DIQUE aguanta, semis neutros — QQQ sostenido, sin edge direccional";
    else
        s.verdict = "MIXTO (dique " + s.dique + ", semis " + s.lastre + ") — esperar prints";
    return s;
}

static void print_snapshot(const Snapshot &s, bool color) {
    const char *G = color ? "\033[32m" : "", *R = color ? "\033[31m" : "",
               *Y = color ? "\033[33m" : "", *B = color ? "\033[1m"  : "",
               *N = color ? "\033[0m"  : "";
    time_t now = time(nullptr);
    struct tm tmv; localtime_r(&now, &tmv);
    char hm[32]; strftime(hm, sizeof hm, "%Y-%m-%d %H:%M:%S", &tmv);

    long age = s.qqq.has_data ? now - s.qqq.last_ts : -1;
    printf("%sQQQ X-RAY%s  %s", B, N, hm);
    if (age > 900) printf("  %s[datos de hace %ldmin — mercado cerrado?]%s", Y, age / 60, N);
    printf("\n");
    printf("%-6s %9s %7s %8s %8s %6s %6s\n",
           "SYM", "PRECIO", "%DIA", "CONTRIB", "TEND", "RVOL", "P/C");
    for (const auto &m : s.members) {
        if (!m.has_data) {
            printf("%-6s %9s %7s %8s %8s %6s %6s   (sin feed)\n",
                   m.sym.c_str(), "s/d", "s/d", "s/d", "s/d", "s/d", "s/d");
            continue;
        }
        const char *pc_col = m.pct >= 0 ? G : R;
        char rv[16], pcs[16];
        m.rvol >= 0 ? snprintf(rv, sizeof rv, "%.1fx", m.rvol) : snprintf(rv, sizeof rv, "s/d");
        m.pc > 0 ? snprintf(pcs, sizeof pcs, "%.2f", m.pc) : snprintf(pcs, sizeof pcs, "s/d");
        printf("%-6s %9.2f %s%+6.2f%%%s %+7.2f%% %8s %6s %6s\n",
               m.sym.c_str(), m.price, pc_col, m.pct, N, m.contrib,
               m.trend.c_str(), rv, pcs);
    }
    printf("---\n");
    if (s.qqq.has_data) {
        double div = s.qqq.pct - s.contrib_sum;
        printf("contrib top-10: %+.2f%%  |  QQQ real: %s%+.2f%%%s (%.2f)  |  divergencia (resto+drift): %+.2f%%\n",
               s.contrib_sum, s.qqq.pct >= 0 ? G : R, s.qqq.pct, N, s.qqq.price, div);
    } else
        printf("contrib top-10: %+.2f%%  |  QQQ real: s/d\n", s.contrib_sum);
    if (s.w_present < s.w_total - 0.01)
        printf("pesos presentes %.1f/%.1f%% (renormalizados; faltan feeds)\n", s.w_present, s.w_total);

    const char *dc = s.dique == "VERDE" ? G : (s.dique == "ROTO" ? R : Y);
    const char *lc = s.lastre == "SANGRAN" ? R : (s.lastre == "EMPUJAN" ? G : Y);
    printf("DIQUE (MSFT+AAPL): %s%s%s (%+.2f%%)   LASTRE (NVDA+AVGO+AMD): %s%s%s (%+.2f%%)\n",
           dc, s.dique.c_str(), N, s.dam_avg, lc, s.lastre.c_str(), N, s.sem_avg);
    printf("%sVEREDICTO:%s %s\n", B, N, s.verdict.c_str());
}

int main(int argc, char **argv) {
    bool watch = false;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--watch")) watch = true;
        else if (!strcmp(argv[i], "--data") && i + 1 < argc) DATA_DIR = argv[++i];
        else { fprintf(stderr, "uso: qqq_xray [--watch] [--data DIR]\n"); return 1; }
    }
    bool color = isatty(1);
    std::string prev_state;
    for (;;) {
        Snapshot s = build();
        if (watch) printf("\033[2J\033[H");
        print_snapshot(s, color);
        fflush(stdout);
        if (!watch) return 0;
        std::string state = s.dique + "|" + s.verdict;
        if (!prev_state.empty() && state != prev_state)
            notify("Dique " + s.dique + ". " + s.verdict);
        prev_state = state;
        sleep(60);
    }
}
