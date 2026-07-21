// bench.cpp — performance benchmarks for core signal bot math functions
// ======================================================================
// Measures: ops/sec and ns/op for each core function over 1e6 iterations

#include <cstdio>
#include <cmath>
#include <chrono>
#include <vector>

// ---- Core math functions (copied from signal bot) ----

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

struct BollingerBands {
    double ring[20] = {0};
    int n = 0;
    double mid = 0, up = 0, dn = 0;
    
    void add(double c) {
        ring[n % 20] = c;
        n++;
        int k = n < 20 ? n : 20;
        double s = 0, s2 = 0;
        for (int i = 0; i < k; i++) {
            s += ring[i];
            s2 += ring[i] * ring[i];
        }
        mid = s / k;
        double var = s2 / k - mid * mid;
        double sd = var > 0 ? std::sqrt(var) : 0;
        up = mid + 2 * sd;
        dn = mid - 2 * sd;
    }
    
    double pctB(double c) const {
        return (up > dn) ? (c - dn) / (up - dn) : 0.5;
    }
};

struct VWAP {
    double pv = 0, v = 0;
    
    void add(double h, double l, double c, double vol) {
        double tp = (h + l + c) / 3.0;
        pv += tp * vol;
        v += vol;
    }
    
    double get() const {
        return v > 0 ? pv / v : 0;
    }
};

// True range calculation
inline double true_range(double h, double l, double prev_c) {
    double tr = h - l;
    double a = std::fabs(h - prev_c);
    double d = std::fabs(l - prev_c);
    if (a > tr) tr = a;
    if (d > tr) tr = d;
    return tr;
}

// ====== Benchmarks ======

template<typename Func>
double bench(const char* name, Func f, long iterations) {
    auto start = std::chrono::high_resolution_clock::now();
    for (long i = 0; i < iterations; i++) {
        f();
    }
    auto end = std::chrono::high_resolution_clock::now();
    auto elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
    double ns_per_op = (double)elapsed_ns / iterations;
    double ops_per_sec = 1e9 / ns_per_op;
    printf("%-25s: %8.2f ns/op | %12.0f ops/sec\n", name, ns_per_op, ops_per_sec);
    return ns_per_op;
}

int main() {
    const long N = 1000000;
    printf("\n=== C++ Math Performance Benchmarks (N=%ld iterations) ===\n\n", N);
    
    // Warm-up
    volatile double dummy = 0;
    for (long i = 0; i < 1000; i++) {
        dummy += std::sin(i * 0.001);
    }
    
    // Benchmark 1: EMA update (12-period)
    {
        EMA ema;
        double price = 100.0;
        bench("EMA(12).update()", [&]() {
            ema.update(price, 12);
            price += 0.01;
        }, N);
    }
    
    // Benchmark 2: RSI add
    {
        RSI rsi;
        double price = 100.0;
        bench("RSI(14).add()", [&]() {
            rsi.add(price);
            price += 0.01;
        }, N);
    }
    
    // Benchmark 3: ATR add
    {
        ATR atr;
        double h = 100.5, l = 99.5, c = 100.0;
        bench("ATR(14).add()", [&]() {
            atr.add(h, l, c);
            h += 0.01; l += 0.01; c += 0.01;
        }, N);
    }
    
    // Benchmark 4: Bollinger Bands add
    {
        BollingerBands bb;
        double c = 100.0;
        bench("BollingerBands.add()", [&]() {
            bb.add(c);
            c += 0.001;
        }, N);
    }
    
    // Benchmark 5: Bollinger %B calc
    {
        BollingerBands bb;
        for (int i = 0; i < 20; i++) bb.add(100.0 + i * 0.1);
        double c = 100.5;
        bench("BollingerBands.pctB()", [&]() {
            volatile double result = bb.pctB(c);
            (void)result;
            c += 0.001;
        }, N);
    }
    
    // Benchmark 6: VWAP add
    {
        VWAP vwap;
        double h = 100.5, l = 99.5, c = 100.0, vol = 1000;
        bench("VWAP.add()", [&]() {
            vwap.add(h, l, c, vol);
            h += 0.001; l += 0.001; c += 0.001;
        }, N);
    }
    
    // Benchmark 7: VWAP get
    {
        VWAP vwap;
        for (int i = 0; i < 100; i++) {
            vwap.add(100.0 + i * 0.1, 99.0 + i * 0.1, 100.0 + i * 0.1, 1000);
        }
        bench("VWAP.get()", [&]() {
            volatile double result = vwap.get();
            (void)result;
        }, N);
    }
    
    // Benchmark 8: True Range calc
    {
        double h = 100.5, l = 99.5, prev_c = 100.0;
        bench("true_range()", [&]() {
            volatile double tr = true_range(h, l, prev_c);
            (void)tr;
            h += 0.01; l += 0.01; prev_c = h - 0.5;
        }, N);
    }
    
    // Benchmark 9: Bollinger stddev (embedded in add)
    {
        double sum = 0, sum2 = 0;
        std::vector<double> ring(20);
        int idx = 0;
        bench("Bollinger.stddev()", [&]() {
            ring[idx % 20] = 100.0 + idx * 0.01;
            int k = idx < 20 ? idx + 1 : 20;
            sum = 0; sum2 = 0;
            for (int i = 0; i < k; i++) {
                sum += ring[i];
                sum2 += ring[i] * ring[i];
            }
            double mid = sum / k;
            double var = sum2 / k - mid * mid;
            double sd = var > 0 ? std::sqrt(var) : 0;
            (void)sd;
            idx++;
        }, N / 10);  // Reduced iterations for stddev
    }
    
    // Benchmark 10: log (used in CUSUM)
    {
        double x = 1.0;
        bench("std::log()", [&]() {
            volatile double r = std::log(x);
            (void)r;
            x += 0.0001;
        }, N);
    }
    
    printf("\n=== Summary ===\n");
    printf("All functions compiled with -O3 -march=native\n");
    printf("Focus: single-instance, incremental computations\n");
    printf("(Real bot uses rolling windows/rings for memory efficiency)\n\n");
    
    return 0;
}
