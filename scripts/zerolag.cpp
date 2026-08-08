// zerolag.cpp — Zero Lag Trend Signals (MTF) [AlgoAlpha], port fiel del Pine v5.
//
// MEDIDO ANTES DE ENCHUFARLO (scripts/zerolag_backtest.py, 939.784 minutos, 30 syms, 85 dias):
//   entrada (flecha pequeña)  wr 0,496 vs null 0,494  -> edge +0,12 pp, CI cruza 0
//   giro de tendencia          wr 0,389 vs null 0,392  -> negativo
//   **0 de 24 celdas pasan BH-FDR q=0,10**
// Por eso este binario es DESCRIPTIVO: publica el estado, NO canta señales y NO tiene voz.
// Su valor es la TABLA MULTI-TEMPORALIDAD (que es lo que el indicador aporta de verdad):
// ver de un vistazo si 5m/15m/60m/240m/1D estan alineados.
//
// Formulas, tal cual el Pine:
//   lag        = floor((length-1)/2)
//   zlema      = EMA(src + (src - src[lag]), length)
//   volatility = highest(ATR(length), length*3) * mult
//   trend      = +1 al cruzar close por encima de zlema+volatility, -1 por debajo de zlema-vol
//   entrada    = cruce del close con el zlema, con la tendencia YA establecida (trend[1] igual)
//
// Entrada: data/bars_<sym>_ibkr.txt (1 min).  Salida: data/zerolag.json.  SEÑAL-SOLAMENTE.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

namespace {

constexpr int kLength = 70;
constexpr double kMult = 1.2;
const int kTF[] = {5, 15, 60, 240, 1440};          // las 5 del Pine; 1440 = 1D
const char* kTFName[] = {"5m", "15m", "60m", "240m", "1D"};

struct Bar { long t; double o, h, l, c, v; };

std::vector<Bar> read_bars(const std::string& path) {
    std::vector<Bar> out;
    std::ifstream f(path);
    if (!f) return out;
    std::string ln;
    while (std::getline(f, ln)) {
        Bar b{};
        if (std::sscanf(ln.c_str(), "%ld %lf %lf %lf %lf %lf",
                        &b.t, &b.o, &b.h, &b.l, &b.c, &b.v) >= 5) out.push_back(b);
    }
    std::sort(out.begin(), out.end(), [](const Bar& a, const Bar& b) { return a.t < b.t; });
    return out;
}

// Reagrupa 1m en velas de `mins`. El bucket es el minuto de epoch truncado: mismo criterio
// que el resto de la casa, y asi 1D no depende de la zona horaria del proceso.
std::vector<Bar> resample(const std::vector<Bar>& in, int mins) {
    std::vector<Bar> out;
    const long w = static_cast<long>(mins) * 60;
    for (const Bar& b : in) {
        const long k = b.t - (b.t % w);
        if (out.empty() || out.back().t != k) {
            out.push_back(Bar{k, b.o, b.h, b.l, b.c, b.v});
        } else {
            Bar& x = out.back();
            x.h = std::max(x.h, b.h);
            x.l = std::min(x.l, b.l);
            x.c = b.c;
            x.v += b.v;
        }
    }
    return out;
}

struct State {
    bool ok = false;
    std::string motivo;
    int trend = 0;             // +1 alcista, -1 bajista, 0 sin definir
    bool entrada_alcista = false, entrada_bajista = false;
    bool giro = false;         // la vela actual CAMBIO la tendencia
    double zlema = 0, banda = 0, close = 0;
    long t = 0;
};

State compute(const std::vector<Bar>& b, int length = kLength, double mult = kMult) {
    State s;
    const size_t need = static_cast<size_t>(length) * 3 + 2;
    if (b.size() < need) {
        s.motivo = "necesita " + std::to_string(need) + " velas, hay " + std::to_string(b.size());
        return s;
    }
    const int lag = (length - 1) / 2;
    const double a = 2.0 / (length + 1.0);

    // ATR de Wilder(length) y su maximo movil de length*3 (la "volatility" del Pine)
    std::vector<double> atr(b.size(), 0.0);
    double acc = 0;
    for (int i = 1; i <= length; ++i)
        acc += std::max(b[i].h - b[i].l,
                        std::max(std::fabs(b[i].h - b[i - 1].c), std::fabs(b[i].l - b[i - 1].c)));
    atr[length] = acc / length;
    for (size_t i = length + 1; i < b.size(); ++i) {
        const double tr = std::max(b[i].h - b[i].l,
                                   std::max(std::fabs(b[i].h - b[i - 1].c),
                                            std::fabs(b[i].l - b[i - 1].c)));
        atr[i] = (atr[i - 1] * (length - 1) + tr) / length;
    }

    double z = b[lag].c;
    int trend = 0, prev_trend = 0;
    double prev_c = b[lag].c, prev_up = 0, prev_dn = 0, prev_z = z;
    for (size_t i = lag; i < b.size(); ++i) {
        const double src2 = b[i].c + (b[i].c - b[i - lag].c);
        z = (i == static_cast<size_t>(lag)) ? src2 : a * src2 + (1 - a) * z;
        double vmax = 0;
        const size_t w = static_cast<size_t>(length) * 3;
        if (i >= w) for (size_t j = i + 1 - w; j <= i; ++j) vmax = std::max(vmax, atr[j]);
        const double vol = vmax * mult;
        const double up = z + vol, dn = z - vol;
        prev_trend = trend;
        if (i > static_cast<size_t>(lag) && vol > 0) {
            if (b[i].c > up && prev_c <= prev_up) trend = 1;
            else if (b[i].c < dn && prev_c >= prev_dn) trend = -1;
            if (i + 1 == b.size()) {
                s.entrada_alcista = (b[i].c > z && prev_c <= prev_z && trend == 1 && prev_trend == 1);
                s.entrada_bajista = (b[i].c < z && prev_c >= prev_z && trend == -1 && prev_trend == -1);
                s.giro = (trend != prev_trend);
                s.zlema = z; s.banda = vol; s.close = b[i].c; s.t = b[i].t;
            }
        }
        prev_c = b[i].c; prev_up = up; prev_dn = dn; prev_z = z;
    }
    s.trend = trend;
    s.ok = true;
    return s;
}

std::vector<std::string> fleet() {
    std::vector<std::string> out;
    std::ifstream f("data/fleet.txt");
    std::string s;
    while (f >> s) out.push_back(s);
    return out;
}

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> syms;
    bool quiet = false;
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        if (a == "--quiet") quiet = true;
        else if (a.rfind("--", 0) != 0) syms.push_back(a);
    }
    if (syms.empty()) syms = fleet();
    if (syms.empty()) { std::fprintf(stderr, "zerolag ROTO: data/fleet.txt vacio\n"); return 2; }

    std::string json = "{\"asof\":" + std::to_string(static_cast<long>(std::time(nullptr)))
                     + ",\"length\":" + std::to_string(kLength)
                     + ",\"mult\":1.2,\"uso\":\"DESCRIPTIVO\","
                       "\"medido\":\"0 de 24 celdas pasan BH-FDR; wr 0,496 vs null 0,494\","
                       "\"syms\":{";
    bool first = true;
    for (const auto& raw : syms) {
        std::string sym, lower;
        for (char c : raw) { sym.push_back(static_cast<char>(std::toupper(c)));
                             lower.push_back(static_cast<char>(std::tolower(c))); }
        // historico primero (bars_hist_*, meses) y encima el vivo: sin el, 60m/240m/1D
        // nunca juntan las 212 velas que pide length*3
        auto b1 = read_bars("data/bars_hist_" + lower + ".txt");
        const auto vivo = read_bars("data/bars_" + lower + "_ibkr.txt");
        {
            const long ultimo = b1.empty() ? 0 : b1.back().t;
            for (const Bar& b : vivo) if (b.t > ultimo) b1.push_back(b);
        }
        if (!first) json += ",";
        first = false;
        json += "\"" + sym + "\":{";
        if (b1.empty()) {
            json += "\"motivo\":\"sin barras\"}";
            if (!quiet) std::printf("%-6s SIN BARRAS\n", sym.c_str());
            continue;
        }
        std::string tfs;
        int alcistas = 0, definidos = 0;
        char linea[256];
        std::string vista;
        for (size_t k = 0; k < sizeof(kTF) / sizeof(kTF[0]); ++k) {
            const State s = compute(resample(b1, kTF[k]));
            if (!tfs.empty()) tfs += ",";
            if (!s.ok) { tfs += "\"" + std::string(kTFName[k]) + "\":{\"motivo\":\"" + s.motivo + "\"}";
                         vista += std::string(kTFName[k]) + "=? "; continue; }
            if (s.trend != 0) { ++definidos; alcistas += (s.trend == 1); }
            std::snprintf(linea, sizeof linea,
                          "\"%s\":{\"trend\":%d,\"zlema\":%.4f,\"banda\":%.4f,"
                          "\"entrada_alcista\":%s,\"entrada_bajista\":%s,\"giro\":%s}",
                          kTFName[k], s.trend, s.zlema, s.banda,
                          s.entrada_alcista ? "true" : "false",
                          s.entrada_bajista ? "true" : "false", s.giro ? "true" : "false");
            tfs += linea;
            vista += std::string(kTFName[k]) + (s.trend == 1 ? "=+ " : s.trend == -1 ? "=- " : "=? ");
        }
        json += tfs + ",\"alineacion\":\"" + std::to_string(alcistas) + "/"
              + std::to_string(definidos) + " alcistas\"}";
        if (!quiet) std::printf("%-6s %s (%d/%d alcistas)\n", sym.c_str(), vista.c_str(),
                                alcistas, definidos);
    }
    json += "}}\n";
    const std::string out = "data/zerolag.json";
    const std::string tmp = out + ".tmp";
    if (FILE* f = std::fopen(tmp.c_str(), "w")) {
        std::fputs(json.c_str(), f);
        std::fclose(f);
        std::rename(tmp.c_str(), out.c_str());
    }
    return 0;
}
