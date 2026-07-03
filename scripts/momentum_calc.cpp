// momentum_calc.cpp — calculador de momentum/trampas (2026-07-21, orden Yunior).
// Ecuaciones: docs/MOMENTUM-MATH.md. Datos: data/bars_<sym>_ibkr.txt ("epoch O H L C V").
// Umbrales medidos: data/momentum_thresholds.txt (de momentum_decay.json, refresh semanal).
// SEÑAL-SOLAMENTE: imprime diagnóstico, jamás ordena.
//   compilar: clang++ -std=c++2b -O3 -march=native -o momentum_calc scripts/momentum_calc.cpp
//   uso: ./momentum_calc qqq [dram mu ...]
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <string>
#include <vector>
#include <algorithm>

struct Bar { long t; double o, h, l, c, v; };

static std::vector<Bar> load_bars(const std::string& sym) {
    std::vector<Bar> b;
    std::string p = "data/bars_" + sym + "_ibkr.txt";
    FILE* f = fopen(p.c_str(), "r");
    if (!f) { p = "data/bars_" + sym + ".txt"; f = fopen(p.c_str(), "r"); }
    if (!f) return b;
    Bar x{};
    while (fscanf(f, "%ld %lf %lf %lf %lf %lf", &x.t, &x.o, &x.h, &x.l, &x.c, &x.v) == 6)
        b.push_back(x);
    fclose(f);
    return b;
}

struct Thresh { double bull_med=5, bull_p75=11, bear_med=5, bear_p75=13, bear_morn_p75=6; };
static Thresh load_thresh() {
    Thresh t; FILE* f = fopen("data/momentum_thresholds.txt", "r");
    if (!f) return t;
    char k[64]; double v;
    while (fscanf(f, "%63s %lf", k, &v) == 2) {
        if (!strcmp(k,"bull_med")) t.bull_med=v; else if (!strcmp(k,"bull_p75")) t.bull_p75=v;
        else if (!strcmp(k,"bear_med")) t.bear_med=v; else if (!strcmp(k,"bear_p75")) t.bear_p75=v;
        else if (!strcmp(k,"bear_morn_p75")) t.bear_morn_p75=v;
    }
    fclose(f); return t;
}

static double median(std::vector<double> v) {
    if (v.empty()) return 0;
    std::sort(v.begin(), v.end());
    return v[v.size()/2];
}

int main(int argc, char** argv) {
    if (argc < 2) { std::puts("uso: momentum_calc SYM [SYM2 ...]"); return 1; }
    Thresh th = load_thresh();
    time_t now = time(nullptr); struct tm lt; localtime_r(&now, &lt);
    bool manana = (lt.tm_hour*60+lt.tm_min) < 690;   // <11:30 ET
    for (int a = 1; a < argc; ++a) {
        std::string sym = argv[a];
        for (auto& ch : sym) ch = (char)tolower(ch);
        auto b = load_bars(sym);
        if (b.size() < 40) { std::printf("%-5s: sin barras suficientes (%zu)\n", argv[a], b.size()); continue; }
        long age_s = now - b.back().t;
        // sesión de hoy: barras desde 9:30 locales del último día presente
        struct tm bt; time_t t0 = b.back().t; localtime_r(&t0, &bt);
        bt.tm_hour = 9; bt.tm_min = 30; bt.tm_sec = 0;
        time_t open_t = mktime(&bt);
        std::vector<Bar> d;
        for (auto& x : b) if (x.t >= open_t) d.push_back(x);
        if (d.size() < 25) d.assign(b.end()-std::min<size_t>(90,b.size()), b.end());
        size_t n = d.size();
        // 1) momentum EMA half-life 4
        double lam = 1.0 - std::pow(2.0, -1.0/4.0), M = 0;
        std::vector<double> Ms(n, 0.0);
        for (size_t i = 1; i < n; ++i) { double r = std::log(d[i].c/d[i-1].c); M = lam*r + (1-lam)*M; Ms[i]=M; }
        // 2) Kaufman ER(10)
        double num = std::fabs(d[n-1].c - d[n-11].c), den = 1e-12;
        for (size_t i = n-10; i < n; ++i) den += std::fabs(d[i].c - d[i-1].c);
        double ER = num/den;
        // 3) VWAP z
        double pv = 0, vv = 0; std::vector<double> devs;
        double vwap_prev30 = 0;
        for (size_t i = 0; i < n; ++i) {
            double tp = (d[i].h + d[i].l + d[i].c)/3.0;
            pv += tp*d[i].v; vv += d[i].v;
            double vw = pv/std::max(vv,1e-9);
            devs.push_back(tp - vw);
            if (n >= 31 && i == n-31) vwap_prev30 = vw;
        }
        double vwap = pv/std::max(vv,1e-9), sd = 0;
        for (double x : devs) sd += x*x;
        sd = std::sqrt(sd/std::max<size_t>(devs.size(),1));
        double z = sd > 1e-9 ? (d[n-1].c - vwap)/sd : 0;
        double vwap_slope = vwap - vwap_prev30;   // >0 = dia alcista
        // BB %B(20,2)
        double mean=0; for (size_t i=n-20;i<n;++i) mean+=d[i].c; mean/=20;
        double s2=0; for (size_t i=n-20;i<n;++i) s2+=(d[i].c-mean)*(d[i].c-mean);
        double bsd=std::sqrt(s2/20), pctB = bsd>1e-9 ? (d[n-1].c-(mean-2*bsd))/(4*bsd) : 0.5;
        // 4) edad del impulso (min con signo M constante)
        int A = 0; int sgn = Ms[n-1] >= 0 ? 1 : -1;
        for (size_t i = n-1; i > 0 && (Ms[i] >= 0 ? 1 : -1) == sgn; --i) ++A;
        bool bull = sgn > 0;
        double med = bull ? th.bull_med : th.bear_med;
        double p75 = bull ? th.bull_p75 : (manana ? th.bear_morn_p75 : th.bear_p75);
        // 5) trampa de dealers
        std::vector<double> vols; for (size_t i=n-20;i<n;++i) vols.push_back(d[i].v);
        double vmed = median(vols);
        double v3 = (d[n-1].v + d[n-2].v + d[n-3].v)/3.0;
        bool vol_fade = v3 < 0.7*vmed;
        bool band_no_follow = (pctB > 1.0 && Ms[n-1] < Ms[n-2]) || (pctB < 0.0 && Ms[n-1] > Ms[n-2]);
        int T = 30*(std::fabs(z) > 2.0) + 25*(ER < 0.3) + 20*vol_fade + 15*(A > p75) + 10*band_no_follow;
        // fase
        const char* fase = A < med ? "IMPULSO" : (A <= p75 ? "MADURO" : "AGOTAMIENTO");
        if (((z > 2 && !bull) || (z < -2 && bull)) && A <= 2) fase = "GIRO";
        // 6) dip del día
        bool dip = z < -1.5 && vwap_slope > 0 && ER > 0.35;
        bool cima = z > 2.5;
        std::printf("%-5s %8.2f (%lds) | M %+0.5f %s | edad %dmin (med %.0f p75 %.0f) %s | ER %.2f | z_vwap %+.2f%s | %%B %.2f | TRAMPA %d/100%s%s\n",
            argv[a], d[n-1].c, age_s, Ms[n-1], bull?"BULL":"BEAR", A, med, p75, fase, ER, z,
            cima ? " ⛰️CIMA-NO-COMPRAR" : "", pctB, T, T>=50?" 🪤TRAMPA-PROBABLE":"",
            dip ? " 🟢DIP-DEL-DIA(comprable con print)" : "");
    }
    return 0;
}
