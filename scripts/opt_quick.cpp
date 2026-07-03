// opt_quick.cpp — lector instantaneo del cache de cadenas de opciones (v6.1).
// SEÑAL-SOLAMENTE (ley #0): SOLO lee data/opt_chain_<sym>.txt (escrito por
// scripts/opt_chain_cache.py cada 3 min en RTH). Cero red, cero TWS, cero ordenes.
//
// Uso:
//   ./opt_quick NVDA           resumen: P/C vol y OI, top-5 muros (OI+vol),
//                              max pain, spread% por strike + gates
//   ./opt_quick NVDA 210 C     detalle de un contrato (todos los vencimientos)
//
// Gates del PLAYBOOK 2026-07-16 (regla 8: "spread <5% del premium SIEMPRE"):
//   spread% = (ask-bid)/mid <= 5%   y   OI > 500  ->  APTO
//
// Compilar (root del repo): clang++ -std=c++17 -O2 -o opt_quick scripts/opt_quick.cpp
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>

struct Row {
    double strike = 0, bid = -1, ask = -1, vol = 0, oi = 0, iv = -1,
           delta = -1, gamma = -1;
    char right = '?';
    char exp[12] = "";
    double mid() const { return (bid > 0 && ask > 0) ? (bid + ask) / 2 : -1; }
    double spread_pct() const {
        double m = mid();
        return (m > 0) ? 100.0 * (ask - bid) / m : -1; }
    bool gate_spread() const { double s = spread_pct(); return s >= 0 && s <= 5.0; }
    bool gate_oi() const { return oi > 500; }
    bool apto() const { return gate_spread() && gate_oi(); }
};

static double max_pain(const std::vector<Row>& rows, const char* exp) {
    // pain(S) = sum_calls OI*max(0,S-K) + sum_puts OI*max(0,K-S); argmin = pin
    std::vector<double> ks;
    for (const auto& r : rows)
        if (!strcmp(r.exp, exp)) ks.push_back(r.strike);
    std::sort(ks.begin(), ks.end());
    ks.erase(std::unique(ks.begin(), ks.end()), ks.end());
    double best_k = 0, best_pain = 1e18;
    for (double S : ks) {
        double pain = 0;
        for (const auto& r : rows) {
            if (strcmp(r.exp, exp)) continue;
            if (r.right == 'C' && S > r.strike) pain += r.oi * (S - r.strike);
            if (r.right == 'P' && S < r.strike) pain += r.oi * (r.strike - S);
        }
        if (pain < best_pain) { best_pain = pain; best_k = S; }
    }
    return best_k;
}

static void pc_line(const std::vector<Row>& rows, const char* exp) {
    double vc = 0, vp = 0, oc = 0, op = 0;
    for (const auto& r : rows) {
        if (exp && strcmp(r.exp, exp)) continue;
        if (r.right == 'C') { vc += r.vol; oc += r.oi; }
        else { vp += r.vol; op += r.oi; }
    }
    std::printf("  P/C volumen %.2f (P %.0f / C %.0f) | P/C OI %.2f (P %.0f / C %.0f)\n",
                vp / std::max(vc, 1.0), vp, vc, op / std::max(oc, 1.0), op, oc);
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr, "uso: opt_quick SYM [strike C|P]\n");
        return 2;
    }
    std::string sym = argv[1];
    for (auto& c : sym) c = (char)std::toupper(c);
    std::string lo = argv[1];
    for (auto& c : lo) c = (char)std::tolower(c);
    std::string path = "data/opt_chain_" + lo + ".txt";
    FILE* f = fopen(path.c_str(), "r");
    if (!f) {
        std::fprintf(stderr, "%s: sin cache %s (¿corre opt_chain_cache.py? "
                     "ventana 9:00-16:15 ET)\n", sym.c_str(), path.c_str());
        return 1;
    }
    long epoch = 0; double spot = 0;
    char stamp[40] = "", exps[64] = "";
    std::vector<Row> rows;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        if (line[0] == '#') {
            const char* p;
            if ((p = strstr(line, "epoch "))) epoch = atol(p + 6);
            if ((p = strstr(line, "spot "))) spot = atof(p + 5);
            if ((p = strstr(line, "| 20")) && strstr(line, "epoch"))
                sscanf(p + 2, "%39[0-9:\\- ]", stamp);
            if ((p = strstr(line, "exps "))) {
                sscanf(p + 5, "%63[0-9 ]", exps);
                size_t n = strlen(exps);
                while (n && (exps[n-1] == ' ' || exps[n-1] == '\n')) exps[--n] = 0;
            }
            continue;
        }
        Row r;
        char right[4] = "";
        if (sscanf(line, "%lf %3s %11s %lf %lf %lf %lf %lf %lf %lf",
                   &r.strike, right, r.exp, &r.bid, &r.ask, &r.vol, &r.oi,
                   &r.iv, &r.delta, &r.gamma) >= 7) {
            r.right = right[0];
            rows.push_back(r);
        }
    }
    fclose(f);
    if (rows.empty()) {
        std::fprintf(stderr, "%s: cache vacio\n", sym.c_str());
        return 1;
    }
    long age = time(nullptr) - epoch;
    std::printf("%s | spot %.2f | cache %s (edad %ldm%02lds)%s | exps %s\n",
                sym.c_str(), spot, stamp, age / 60, age % 60,
                age > 300 ? "  ** CACHE VIEJO **" : "", exps);

    // vencimientos presentes (orden del header = cercano primero)
    std::vector<std::string> evec;
    { char tmp[64]; strncpy(tmp, exps, 63); tmp[63] = 0;
      for (char* t = strtok(tmp, " "); t; t = strtok(nullptr, " "))
          evec.push_back(t); }
    if (evec.empty()) { for (const auto& r : rows) {
        if (std::find(evec.begin(), evec.end(), r.exp) == evec.end())
            evec.push_back(r.exp); } std::sort(evec.begin(), evec.end()); }

    // ---- modo detalle: opt_quick SYM STRIKE C|P ----
    if (argc >= 4) {
        double k = atof(argv[2]);
        char rt = (char)std::toupper(argv[3][0]);
        bool found = false;
        for (const auto& r : rows) {
            if (std::fabs(r.strike - k) > 1e-6 || r.right != rt) continue;
            found = true;
            std::printf("\n%s %.2f %c %s\n", sym.c_str(), r.strike, r.right, r.exp);
            std::printf("  bid %.2f / ask %.2f (mid %.2f) | spread %.1f%%\n",
                        r.bid, r.ask, r.mid(), r.spread_pct());
            std::printf("  vol %.0f | OI %.0f | IV %.0f%% | delta %.2f | gamma %.4f\n",
                        r.vol, r.oi, r.iv > 0 ? r.iv * 100 : -1, r.delta, r.gamma);
            if (r.apto())
                std::printf("  GATES: APTO (spread %.1f%% <= 5%%, OI %.0f > 500)\n",
                            r.spread_pct(), r.oi);
            else {
                std::printf("  GATES: NO-APTO (");
                bool first = true;
                if (!r.gate_spread()) {
                    if (r.mid() <= 0) std::printf("sin quote — ¿fuera de RTH?");
                    else std::printf("spread %.1f%% > 5%%", r.spread_pct());
                    first = false; }
                if (!r.gate_oi()) std::printf("%sOI %.0f <= 500", first ? "" : ", ", r.oi);
                std::printf(")\n");
            }
        }
        if (!found)
            std::printf("  %.2f %c: no esta en el cache (banda ±6%% ATM)\n", k, rt);
        return found ? 0 : 1;
    }

    // ---- resumen ----
    std::printf("\nTOTAL (todos los vencimientos cacheados):\n");
    pc_line(rows, nullptr);
    for (const auto& e : evec) {
        std::printf("\nVENC %s%s:\n", e.c_str(), &e == &evec[0] ? " (cercano)" : "");
        pc_line(rows, e.c_str());
        std::printf("  MAX PAIN %.1f\n", max_pain(rows, e.c_str()));
    }

    // muros top-5 por OI+vol (todos los vencimientos)
    std::vector<const Row*> bywall;
    for (const auto& r : rows) bywall.push_back(&r);
    std::sort(bywall.begin(), bywall.end(), [](const Row* a, const Row* b) {
        return a->oi + a->vol > b->oi + b->vol; });
    std::printf("\nMUROS top-5 (OI+vol):\n");
    for (size_t i = 0; i < bywall.size() && i < 5; i++) {
        const Row* r = bywall[i];
        std::printf("  %.1f%c %s  OI %.0f  vol %.0f%s\n", r->strike, r->right,
                    r->exp, r->oi, r->vol,
                    (r->right == 'C' && spot > 0 && r->strike >= spot) ||
                    (r->right == 'P' && spot > 0 && r->strike <= spot)
                        ? "  <- campo de fuerza" : "");
    }

    // tabla por strike del vencimiento cercano: spread% + gates
    const std::string& e0 = evec[0];
    std::vector<double> ks;
    for (const auto& r : rows) if (r.exp == e0) ks.push_back(r.strike);
    std::sort(ks.begin(), ks.end());
    ks.erase(std::unique(ks.begin(), ks.end()), ks.end());
    int aptos = 0, total = 0;
    std::printf("\nVENC %s — spread%% por strike (gate: spread<=5%% y OI>500):\n", e0.c_str());
    std::printf("  %8s | %22s | %22s\n", "strike", "CALL spr% OI gate", "PUT  spr% OI gate");
    for (double k : ks) {
        const Row *rc = nullptr, *rp = nullptr;
        for (const auto& r : rows)
            if (r.exp == e0 && std::fabs(r.strike - k) < 1e-6)
                (r.right == 'C' ? rc : rp) = &r;
        char cbuf[40] = "      -", pbuf[40] = "      -";
        auto fmt = [](char* buf, size_t n, const Row* r) {
            if (r->spread_pct() < 0)
                std::snprintf(buf, n, "%5s %7.0f %s", "n/d", r->oi,
                              r->apto() ? "APTO" : "no");
            else
                std::snprintf(buf, n, "%4.1f%% %7.0f %s", r->spread_pct(), r->oi,
                              r->apto() ? "APTO" : "no"); };
        if (rc) { fmt(cbuf, sizeof(cbuf), rc); total++; aptos += rc->apto(); }
        if (rp) { fmt(pbuf, sizeof(pbuf), rp); total++; aptos += rp->apto(); }
        std::printf("  %8.2f | %22s | %22s%s\n", k, cbuf, pbuf,
                    spot > 0 && std::fabs(k - spot) ==
                        [&]{ double m = 1e18; for (double x : ks)
                             m = std::min(m, std::fabs(x - spot)); return m; }()
                        ? "  <- ATM" : "");
    }
    std::printf("\nGATES: %d/%d contratos APTOS en %s\n", aptos, total, e0.c_str());
    return 0;
}
