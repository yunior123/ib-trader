// bench.cpp — benchmarks de la matematica de los signal bots
// ======================================================================
// HISTORIA (2026-07-25): este fichero MEDIA AL OPTIMIZADOR, no al codigo.
// Reportaba 2.4e13 ops/sec y hasta `inf` en RSI/stddev, y el binario entero
// terminaba en 0.017 s para 9.1M iteraciones — fisicamente imposible en un
// M1 (~3.2 GHz => ~0.31 ns por CICLO). Causa: el lambda no tenia consumidor,
// asi que clang -O3 borraba el cuerpo del bucle entero (dead-store
// elimination) y cronometraba un bucle vacio. El "9.46 ns/op de Bollinger"
// que se cito como prueba de rendimiento salio del unico caso que por
// casualidad NO se pudo borrar.
//
// ARREGLO, tres capas:
//  1. `sink()` — barrera de optimizacion (inline asm sin clobber) que obliga
//     al compilador a materializar el valor. Equivale a
//     benchmark::DoNotOptimize sin depender de Google Benchmark.
//  2. `clobber()` tras cada iteracion: la memoria escrita no puede
//     considerarse muerta.
//  3. GUARDA FAIL-LOUD: cualquier medida por debajo de MIN_NS_PER_OP se
//     declara BORRADA-POR-EL-OPTIMIZADOR y el binario sale con codigo 1.
//     Una cifra imposible ya NO se puede publicar como si fuera real.
//
// Bollinger se mide sobre el CODIGO REAL (`engines/bb_core.h`), igual que
// math_test tras el fix fc26ddf. EMA/RSI/ATR/VWAP siguen siendo copias
// locales porque no existen como motor compartido en el repo: estan
// marcadas [COPIA] en la salida para que nadie las cite como medida del bot.
// ======================================================================

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "engines/bb_core.h"

// ---------------------------------------------------------------------------
// Barreras de optimizacion. Sin estas el bucle se borra y se cronometra nada.
// ---------------------------------------------------------------------------
template <typename T>
inline void sink(T const& value) {
    asm volatile("" : : "r,m"(value) : "memory");
}
inline void clobber() { asm volatile("" : : : "memory"); }

// Suelo fisico: un M1 a ~3.2 GHz da ~0.31 ns/ciclo. Nada real baja de 0.05
// ns/op (equivaldria a >6 ops por ciclo sostenidas con dependencias).
constexpr double MIN_NS_PER_OP = 0.05;

// ---- Nucleos [COPIA] (no existen como motor compartido) --------------------

struct EMA {
    double v = 0; bool init = false;
    double update(double x, int n) {
        double k = 2.0 / (n + 1);
        v = init ? x * k + v * (1 - k) : x;
        init = true;
        return v;
    }
};

struct RSI {
    double ag = 0, al = 0, prev = 0, rsi = 50;
    long n = 0;
    void add(double c) {
        if (n > 0) {
            double d = c - prev;
            double g = d > 0 ? d : 0;
            double L = d < 0 ? -d : 0;
            ag = n <= 14 ? (ag * (n - 1) + g) / n : ag + (g - ag) / 14;
            al = n <= 14 ? (al * (n - 1) + L) / n : al + (L - al) / 14;
            rsi = al > 1e-12 ? 100.0 - 100.0 / (1.0 + ag / al) : 50.0;
        }
        prev = c;
        n++;
    }
    double get() const { return rsi; }
};

struct ATR {
    double atr = 0, prev_c = 0;
    int n = 0;
    int period = 14;
    void add(double h, double l, double c) {
        double tr = h - l;
        if (n > 0) {
            double a = std::fabs(h - prev_c);
            double d = std::fabs(l - prev_c);
            if (a > tr) tr = a;
            if (d > tr) tr = d;
        }
        atr = (n < period) ? (atr * n + tr) / (n + 1)
                           : (atr * (period - 1) + tr) / period;
        prev_c = c;
        n++;
    }
    double get() const { return atr; }
};

struct VWAP {
    double pv = 0, v = 0;
    void add(double h, double l, double c, double vol) {
        double tp = (h + l + c) / 3.0;
        pv += tp * vol;
        v += vol;
    }
    double get() const { return v > 0 ? pv / v : 0; }
};

inline double true_range(double h, double l, double prev_c) {
    double tr = h - l;
    double a = std::fabs(h - prev_c);
    double d = std::fabs(l - prev_c);
    if (a > tr) tr = a;
    if (d > tr) tr = d;
    return tr;
}

// ====== Arnes ======

static int g_deleted = 0;   // cuantas medidas salieron imposibles

// `f` DEBE devolver un valor; el arnes lo consume con sink() para que el
// cuerpo no pueda eliminarse.
template <typename Func>
double bench(const char* name, Func f, long iterations) {
    // calentamiento: 1% de las iteraciones, tambien consumido
    for (long i = 0; i < iterations / 100 + 1; i++) { sink(f()); clobber(); }

    auto start = std::chrono::steady_clock::now();
    for (long i = 0; i < iterations; i++) {
        sink(f());
        clobber();
    }
    auto end = std::chrono::steady_clock::now();

    auto elapsed_ns =
        std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
    double ns_per_op = (double)elapsed_ns / (double)iterations;
    double ops_per_sec = ns_per_op > 0 ? 1e9 / ns_per_op : 0;

    const bool bad = !(ns_per_op >= MIN_NS_PER_OP);   // cubre 0, negativo y NaN
    if (bad) ++g_deleted;
    printf("%-28s: %8.3f ns/op | %14.0f ops/sec%s\n", name, ns_per_op,
           ops_per_sec, bad ? "   🔴 BORRADO POR EL OPTIMIZADOR" : "");
    return ns_per_op;
}

int main() {
    const long N = 1000000;
    printf("\n=== Benchmarks matematica signal bots (N=%ld) ===\n", N);
    printf("Suelo de credibilidad: %.2f ns/op (M1 ~3.2 GHz = ~0.31 ns/ciclo)\n\n",
           MIN_NS_PER_OP);

    {   // 1. EMA(12) [COPIA]
        EMA ema; double price = 100.0;
        bench("EMA(12).update() [COPIA]", [&] {
            double r = ema.update(price, 12);
            price += 0.01;
            return r;
        }, N);
    }
    {   // 2. RSI(14) [COPIA]
        RSI rsi; double price = 100.0;
        bench("RSI(14).add() [COPIA]", [&] {
            rsi.add(price);
            price += 0.01;
            return rsi.get();
        }, N);
    }
    {   // 3. ATR(14) [COPIA]
        ATR atr; double h = 100.5, l = 99.5, c = 100.0;
        bench("ATR(14).add() [COPIA]", [&] {
            atr.add(h, l, c);
            h += 0.01; l += 0.01; c += 0.01;
            return atr.get();
        }, N);
    }
    {   // 4. BB real (engines/bb_core.h) — update O(1) con sumas rodantes
        bbcore::BB bb; double c = 100.0;
        bench("bbcore::BB.update() REAL", [&] {
            bb.update(c);
            c += 0.001;
            return bb.mid + bb.up + bb.dn;
        }, N);
    }
    {   // 5. %B real
        bbcore::BB bb;
        for (int i = 0; i < 40; i++) bb.update(100.0 + i * 0.1);
        double c = 100.5;
        bench("bbcore::BB.pctB() REAL", [&] {
            double r = bb.pctB(c);
            c += 0.001;
            return r;
        }, N);
    }
    {   // 6. bandwidth real
        bbcore::BB bb;
        for (int i = 0; i < 40; i++) bb.update(100.0 + i * 0.1);
        bench("bbcore::BB.bandwidth() REAL", [&] {
            return bb.bandwidth();
        }, N);
    }
    {   // 7. VWAP add [COPIA]
        VWAP vwap; double h = 100.5, l = 99.5, c = 100.0, vol = 1000;
        bench("VWAP.add() [COPIA]", [&] {
            vwap.add(h, l, c, vol);
            h += 0.001; l += 0.001; c += 0.001;
            return vwap.v;
        }, N);
    }
    {   // 8. VWAP get [COPIA]
        VWAP vwap;
        for (int i = 0; i < 100; i++)
            vwap.add(100.0 + i * 0.1, 99.0 + i * 0.1, 100.0 + i * 0.1, 1000);
        bench("VWAP.get() [COPIA]", [&] { return vwap.get(); }, N);
    }
    {   // 9. true_range [COPIA]
        double h = 100.5, l = 99.5, prev_c = 100.0;
        bench("true_range() [COPIA]", [&] {
            double r = true_range(h, l, prev_c);
            h += 0.01; l += 0.01; prev_c = h - 0.5;
            return r;
        }, N);
    }
    {   // 10. stddev O(k) ingenua — el patron que bb_core REEMPLAZA.
        // Se mide para justificar el cambio a sumas rodantes, no como codigo vivo.
        std::vector<double> ring(20);
        int idx = 0;
        bench("stddev O(k) ingenua [VIEJA]", [&] {
            ring[idx % 20] = 100.0 + idx * 0.01;
            int k = idx < 20 ? idx + 1 : 20;
            double sum = 0, sum2 = 0;
            for (int i = 0; i < k; i++) { sum += ring[i]; sum2 += ring[i] * ring[i]; }
            double mid = sum / k;
            double var = sum2 / k - mid * mid;
            idx++;
            return var > 0 ? std::sqrt(var) : 0.0;
        }, N / 10);
    }
    {   // 11. std::log (CUSUM)
        double x = 1.0;
        bench("std::log()", [&] {
            double r = std::log(x);
            x += 0.0001;
            return r;
        }, N);
    }

    printf("\n=== Resumen ===\n");
    if (g_deleted) {
        printf("🔴 %d de las medidas son IMPOSIBLES: el optimizador borro el bucle.\n",
               g_deleted);
        printf("   NO publicar ninguna cifra de este fichero hasta arreglarlo.\n\n");
        return 1;
    }
    printf("✅ Las %d medidas estan por encima del suelo fisico: son creibles.\n", 11);
    printf("   Bollinger se mide sobre engines/bb_core.h (codigo REAL del bot).\n");
    printf("   [COPIA] = nucleo duplicado aqui, NO es el del bot: no citar como tal.\n\n");
    return 0;
}
