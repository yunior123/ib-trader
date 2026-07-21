// math_test.cpp — correctness tests for core signal bot math functions
// =====================================================================
// Tests: Bollinger Bands, %B, RSI, ATR, VWAP, SMA, EMA, CUSUM

#include <cstdio>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <deque>

const double EPS = 1e-9;

struct TestResult { int pass = 0, fail = 0; };
TestResult g_results;

void test_assert(bool cond, const char* test_name) {
    if (cond) {
        g_results.pass++;
        printf("  [PASS] %s\n", test_name);
    } else {
        g_results.fail++;
        printf("  [FAIL] %s\n", test_name);
    }
}

// ---- EMA (Exponential Moving Average) ----
struct EMA {
    double v = 0; bool init = false;
    double update(double x, int n) {
        double k = 2.0 / (n + 1);
        v = init ? x * k + v * (1 - k) : x;
        init = true;
        return v;
    }
};

// ---- SMA (Simple Moving Average) ----
double sma(const std::vector<double>& data, int n) {
    if ((int)data.size() < n) return 0;
    double sum = 0;
    for (int i = (int)data.size() - n; i < (int)data.size(); i++) {
        sum += data[i];
    }
    return sum / n;
}

// ---- RSI(14) Wilder ----
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

// ---- ATR(14) Wilder ----
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

// ---- Bollinger Bands(20, 2) ----
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

// ---- VWAP (Volume Weighted Average Price) ----
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

// ---- CUSUM (Cumulative Sum Filter) ----
struct CUSUM {
    double cusum_up = 0, cusum_dn = 0;
    double prev_c = 0;
    double ret_var = 1e-6;
    
    void add(double c) {
        if (prev_c > 0) {
            double r = std::log(c / prev_c);
            ret_var += (r * r - ret_var) / 50.0;  // EWMA variance
            cusum_up = std::max(0.0, cusum_up + r);
            cusum_dn = std::min(0.0, cusum_dn + r);
        }
        prev_c = c;
    }
    
    double getUp() const { return cusum_up; }
    double getDn() const { return cusum_dn; }
};

// ===================== TESTS =====================

int main() {
    printf("\n=== C++ Math Correctness Tests ===\n\n");
    
    // Test 1: EMA convergence
    {
        printf("TEST 1: EMA(12) converges toward recent values\n");
        EMA ema;
        double last_ema = 0;
        for (int i = 1; i <= 30; i++) {
            last_ema = ema.update(100.0 + i, 12);
        }
        test_assert(last_ema >= 124.0, "EMA approaches recent price level");
    }
    
    // Test 2: SMA exact
    {
        printf("\nTEST 2: SMA(3) on [10, 20, 30]\n");
        std::vector<double> data = {10, 20, 30};
        double sma_val = sma(data, 3);
        test_assert(std::fabs(sma_val - 20.0) < EPS, "SMA(3) = 20.0");
    }
    
    // Test 3: RSI in overbought territory (with mixed up/down but biased up)
    {
        printf("\nTEST 3: RSI on uptrend with minor pullbacks\n");
        RSI rsi;
        // Create uptrend with occasional small pullbacks
        double price = 1000.0;
        for (int i = 0; i < 30; i++) {
            if (i % 4 == 3) price -= 5.0;  // Small pullback
            else price += 15.0;             // Larger up move
            rsi.add(price);
        }
        double r = rsi.get();
        test_assert(r > 70, "RSI > 70 on uptrend (overbought condition)");
    }
    
    // Test 4: RSI in oversold territory
    {
        printf("\nTEST 4: RSI on downtrend with minor rebounds\n");
        RSI rsi;
        double price = 1000.0;
        for (int i = 0; i < 30; i++) {
            if (i % 4 == 3) price += 5.0;  // Small rebound
            else price -= 15.0;             // Larger down move
            rsi.add(price);
        }
        double r = rsi.get();
        test_assert(r < 30, "RSI < 30 on downtrend (oversold condition)");
    }
    
    // Test 5: ATR with zero range
    {
        printf("\nTEST 5: ATR on flat bars (h=l=c)\n");
        ATR atr;
        for (int i = 0; i < 20; i++) {
            atr.add(100, 100, 100);
        }
        test_assert(atr.get() < 1e-9, "ATR → 0 on flat series");
    }
    
    // Test 6: ATR with gap
    {
        printf("\nTEST 6: ATR captures gaps (prev_close to high/low)\n");
        ATR atr;
        atr.add(100, 100, 100);     // bar 1: TR = 0
        atr.add(110, 105, 107);     // bar 2: gap from 100 to 110, TR = max(5, 10, 5) = 10
        test_assert(atr.get() > 1.0, "ATR captures gap move");
    }
    
    // Test 7: Bollinger Bands %B at exact levels
    {
        printf("\nTEST 7: Bollinger %%B at band edges\n");
        BollingerBands bb;
        std::vector<double> flat = {100, 100, 100, 100, 100, 100, 100, 100, 100, 100,
                                     100, 100, 100, 100, 100, 100, 100, 100, 100, 100};
        for (double c : flat) bb.add(c);
        test_assert(std::fabs(bb.mid - 100.0) < EPS, "BB mid = 100 (flat)");
        test_assert(bb.dn == bb.up, "BB upper = lower (stddev=0)");
        double pct = bb.pctB(100.0);
        test_assert(std::fabs(pct - 0.5) < EPS, "BB %%B = 0.5 at collapsed bands");
    }
    
    // Test 8: Bollinger Bands %B rising series
    {
        printf("\nTEST 8: Bollinger %%B on rising series\n");
        BollingerBands bb;
        for (double i = 1; i <= 20; i++) {
            bb.add(i * 10);
        }
        double pct_at_low = bb.pctB(bb.dn);
        double pct_at_high = bb.pctB(bb.up);
        test_assert(pct_at_low < 0.1, "%%B near 0 at lower band");
        test_assert(pct_at_high > 0.9, "%%B near 1.0 at upper band");
    }
    
    // Test 9: VWAP simple
    {
        printf("\nTEST 9: VWAP on uniform volume\n");
        VWAP vwap;
        for (int i = 0; i < 5; i++) {
            vwap.add(100, 100, 100, 100);
        }
        test_assert(std::fabs(vwap.get() - 100.0) < EPS, "VWAP = 100 (flat)");
    }
    
    // Test 10: VWAP weighted toward high-volume bar
    {
        printf("\nTEST 10: VWAP biased to high-volume bar\n");
        VWAP vwap;
        vwap.add(100, 100, 100, 1);        // TP=100, vol=1
        vwap.add(102, 102, 102, 100);      // TP=102, vol=100 (dominates)
        double v = vwap.get();
        test_assert(v > 101.5 && v < 101.99, "VWAP pulled toward 102");
    }
    
    // Test 11: CUSUM detects large price move
    {
        printf("\nTEST 11: CUSUM accumulates on consistent moves\n");
        CUSUM cusum;
        cusum.add(100.0);
        for (int i = 0; i < 10; i++) {
            cusum.add(100.0 * std::pow(1.05, i + 1));
        }
        test_assert(cusum.getUp() > 0.3, "CUSUM_UP accumulates on consistent rises");
    }
    
    // Test 12: Bollinger std-dev edge case (single bar)
    {
        printf("\nTEST 12: Bollinger with single bar\n");
        BollingerBands bb;
        bb.add(50.5);
        test_assert(std::fabs(bb.mid - 50.5) < EPS, "Single bar: mid = value");
        test_assert(std::fabs(bb.dn - 50.5) < EPS, "Single bar: dn = mid (stddev=0)");
        test_assert(std::fabs(bb.up - 50.5) < EPS, "Single bar: up = mid (stddev=0)");
    }
    
    // Test 13: RSI neutral at equal gains/losses
    {
        printf("\nTEST 13: RSI oscillating (equal up/down)\n");
        RSI rsi;
        for (int i = 0; i < 40; i++) {
            rsi.add(100.0 + ((i % 2) ? 1.0 : -1.0));
        }
        double r = rsi.get();
        test_assert(r > 40 && r < 60, "RSI ≈ 50 on equal oscillation");
    }
    
    // Test 14: ATR initialization (period 14)
    {
        printf("\nTEST 14: ATR period initialization\n");
        ATR atr;
        atr.period = 14;
        for (int i = 0; i < 30; i++) {
            atr.add(100 + i, 100 + i, 100 + i);
        }
        test_assert(atr.n == 30, "ATR.n counts all bars");
        test_assert(atr.get() >= 0, "ATR never negative");
    }
    
    // Test 15: Bollinger %B division by zero safety
    {
        printf("\nTEST 15: Bollinger %%B when bands collapse\n");
        BollingerBands bb;
        bb.mid = 0; bb.up = 0; bb.dn = 0;
        double pct = bb.pctB(0);
        test_assert(pct == 0.5, "%%B returns 0.5 when upper=lower");
    }
    
    // Test 16: CUSUM down on consistent falls
    {
        printf("\nTEST 16: CUSUM_DN accumulates on consistent falls\n");
        CUSUM cusum;
        cusum.add(100.0);
        for (int i = 0; i < 10; i++) {
            cusum.add(100.0 * std::pow(0.95, i + 1));
        }
        test_assert(cusum.getDn() < -0.3, "CUSUM_DN accumulates on falls");
    }
    
    // Test 17: %B never produces NaN
    {
        printf("\nTEST 17: %%B never produces NaN\n");
        BollingerBands bb;
        for (int i = 0; i < 20; i++) {
            bb.add(100.0);
        }
        double pct = bb.pctB(100.0);
        test_assert(!std::isnan(pct), "%%B is never NaN");
    }
    
    // Test 18: RSI never NaN or Inf
    {
        printf("\nTEST 18: RSI never produces NaN/Inf\n");
        RSI rsi;
        for (int i = 0; i < 30; i++) {
            rsi.add(100.0 + (i % 3) - 1.0);
        }
        double r = rsi.get();
        test_assert(!std::isnan(r) && !std::isinf(r), "RSI is finite");
    }
    
    // Test 19: BBands behavior on range-bound market
    {
        printf("\nTEST 19: BBands adapts to range-bound series\n");
        BollingerBands bb;
        for (int i = 0; i < 30; i++) {
            double c = 100.0 + 2.0 * std::sin(i * 0.3);
            bb.add(c);
        }
        test_assert(bb.up > bb.mid && bb.mid > bb.dn, "BBands expand on volatility");
    }
    
    // Print summary
    printf("\n=== Results ===\n");
    printf("PASS: %d\n", g_results.pass);
    printf("FAIL: %d\n", g_results.fail);
    printf("Total: %d\n\n", g_results.pass + g_results.fail);
    
    return g_results.fail > 0 ? 1 : 0;
}
