// math_test.cpp — tests de correccion sobre el CODIGO REAL de la flota.
// =====================================================================
// HISTORIA (2026-07-24): este archivo NO probaba nada del proyecto. Reimplementaba
// EMA/SMA/RSI/ATR/BB/VWAP/CUSUM en copias PRIVADAS y testeaba a esas copias — sin
// un solo #include del repo. El "25/25 correctness pass" que se reportaba en
// TODOS.md no decia absolutamente nada sobre engines/ ni sobre los 24 bots.
// Ademas las aserciones eran tautologicas ("atr >= 0", "rsi > 70"): pasaban con
// casi cualquier implementacion, incluida una rota.
//
// Ahora incluye engines/bb_core.h y prueba las clases REALES, con VALORES DE
// REFERENCIA exactos calculados a mano.
//
// ---------------------------------------------------------------------------
// COBERTURA HONESTA — leer antes de confiar en un "ALL OK":
//   CUBIERTO   : bbcore::BB, bbcore::BWPct, bbcore::ATR14  (engines/bb_core.h)
//   NO CUBIERTO: las copias INLINE de los 24 *_signal_bot.cpp (V5BB :325,
//                V6BBX :588, y el BB principal :1449). Viven dentro del .cpp
//                del binario y no son incluibles. Quedaran cubiertas cuando se
//                consoliden contra este header (fase de deduplicacion).
//                Hasta entonces: un verde AQUI no es un verde para los bots.
// ---------------------------------------------------------------------------
// build:  clang++ -std=c++23 -O3 -mcpu=native -Wall -Wextra -I. \
//                 -o /tmp/math_test tests/cpp/math_test.cpp && /tmp/math_test
//         (desde la raiz del repo; ver tests/cpp/run.sh para el build ASan)

#include <cmath>
#include <cstdio>

#include "engines/bb_core.h"

// ---- harness minimo (patron de la skill cpp23-testing) ----
static int g_pass = 0, g_fail = 0;

static void check(bool cond, const char* name) {
    if (cond) { ++g_pass; std::printf("  [PASS] %s\n", name); }
    else      { ++g_fail; std::printf("  [FAIL] %s\n", name); }
}
static void near(double got, double want, double eps, const char* name) {
    if (std::fabs(got - want) <= eps) { ++g_pass; std::printf("  [PASS] %s\n", name); }
    else { ++g_fail; std::printf("  [FAIL] %s  (obtenido %.12f, esperado %.12f)\n",
                                 name, got, want); }
}

// ===========================================================================
// bbcore::BB — BB(20,2) POBLACIONAL (/N)
// ===========================================================================
// Referencia: closes 1..20 -> mean = 10.5.
// Varianza poblacional de 1..n = (n^2 - 1)/12 = (400-1)/12 = 33.25 EXACTO.
static void test_bb_referencia() {
    std::printf("bbcore::BB — valores de referencia\n");
    bbcore::BB bb;
    for (int i = 1; i <= 20; ++i) bb.update((double)i);

    const double sd_ref = std::sqrt(33.25);
    check(bb.ready(),                          "BB lista tras 20 barras");
    near(bb.mid, 10.5,              1e-12,     "mid = 10.5");
    near(bb.sd,  sd_ref,            1e-12,     "sd = sqrt(33.25) [POBLACIONAL /N]");
    near(bb.up,  10.5 + 2 * sd_ref, 1e-12,     "up = mid + 2sd");
    near(bb.dn,  10.5 - 2 * sd_ref, 1e-12,     "dn = mid - 2sd");

    // Discriminador poblacional vs muestral: con /(N-1) la sd seria sqrt(35)
    // = 5.9160798, que difiere en >0.14. Este test lo detecta.
    check(std::fabs(bb.sd - std::sqrt(35.0)) > 0.1,
          "sd NO es muestral (/N-1) — la doctrina exige poblacional");

    near(bb.pctB(10.5),  0.5, 1e-12, "%B = 0.5 en la media");
    near(bb.pctB(bb.up), 1.0, 1e-12, "%B = 1.0 en banda superior");
    near(bb.pctB(bb.dn), 0.0, 1e-12, "%B = 0.0 en banda inferior");
    near(bb.bandwidth(), (bb.up - bb.dn) / 10.5, 1e-12, "bandwidth = (up-dn)/|mid|");
}

// La ventana rodante DEBE restar el saliente. Tras empujar 21 la ventana es
// 2..21 -> mean 11.5 y la MISMA sd (una traslacion no cambia sigma). Este test
// caza el bug clasico de sumas incrementales que acumulan sin restar.
static void test_bb_ventana_rodante() {
    std::printf("bbcore::BB — ventana rodante\n");
    bbcore::BB bb;
    for (int i = 1; i <= 21; ++i) bb.update((double)i);
    near(bb.mid, 11.5,             1e-12, "mid = 11.5 tras rodar (ventana 2..21)");
    near(bb.sd,  std::sqrt(33.25), 1e-12, "sd invariante a traslacion");

    bbcore::BB b2;
    for (int i = 1; i <= 40; ++i) b2.update((double)i);
    near(b2.mid, 30.5,             1e-12, "mid = 30.5 tras 40 barras (ventana 21..40)");
    near(b2.sd,  std::sqrt(33.25), 1e-10, "sd estable tras 40 barras (sin deriva)");
}

static void test_bb_degenerada() {
    std::printf("bbcore::BB — casos degenerados\n");
    bbcore::BB bb;
    for (int i = 0; i < 20; ++i) bb.update(100.0);
    near(bb.sd, 0.0, 1e-12,          "sd = 0 en serie constante");
    check(!std::isnan(bb.sd),        "sd no es NaN");
    near(bb.up, 100.0, 1e-12,        "up = mid con sd=0");
    near(bb.dn, 100.0, 1e-12,        "dn = mid con sd=0");
    near(bb.pctB(100.0), 0.5, 1e-12, "%B = 0.5 con banda plana (no divide por cero)");
    near(bb.bandwidth(), 0.0, 1e-12, "bandwidth = 0 con banda plana");

    bbcore::BB b0;
    b0.update(0.0);
    check(!b0.ready(),               "no lista con 1 barra");
    near(b0.mid, 0.0, 1e-12,         "mid = 0 con un solo close 0");
    near(b0.bandwidth(), 0.0, 1e-12, "bandwidth = 0 con mid=0 (no divide por cero)");

    // Precios reales de la flota (QQQ ~685): la varianza naive E[x^2]-E[x]^2
    // sufre cancelacion catastrofica con magnitudes grandes. Debe aguantar.
    bbcore::BB bq;
    for (int i = 0; i < 20; ++i) bq.update(685.0 + (i % 2 ? 0.01 : -0.01));
    near(bq.mid, 685.0, 1e-9, "mid estable a magnitud 685 (cancelacion catastrofica)");
    near(bq.sd,  0.01,  1e-6, "sd = 0.01 a magnitud 685");
}

// ===========================================================================
// bbcore::BWPct — percentil rodante de bandwidth
// ===========================================================================
static void test_bwpct() {
    std::printf("bbcore::BWPct — percentil rodante\n");
    bbcore::BWPct p;
    check(!p.ready(),              "no lista vacia");
    near(p.rank(1.0), 50.0, 1e-12, "rank = 50 sin datos (neutral, ni 0 ni 100)");

    for (int i = 1; i <= 100; ++i) p.push((double)i);
    check(!p.ready(),                 "no lista con 100 < W=125");
    near(p.rank(50.0),  50.0, 1e-12,  "rank(50) = 50% sobre 1..100");
    near(p.rank(100.0), 100.0, 1e-12, "rank(max) = 100%");
    near(p.rank(0.5),   0.0,  1e-12,  "rank(bajo todo) = 0%");
    near(p.rank(1.0),   1.0,  1e-12,  "rank(1) = 1% (comparacion <=, inclusiva)");

    for (int i = 101; i <= 125; ++i) p.push((double)i);
    check(p.ready(),                  "lista al llegar a W=125");
}

// ===========================================================================
// bbcore::ATR14 — Wilder
// ===========================================================================
static void test_atr14() {
    std::printf("bbcore::ATR14 — Wilder\n");
    bbcore::ATR14 flat;
    for (int i = 0; i < 20; ++i) flat.update({0, 100, 100, 100, 100, 0});
    near(flat.value(), 0.0, 1e-12, "ATR = 0 en serie perfectamente plana");
    check(flat.ready(),            "ATR lista tras 14 barras");

    // OJO con el orden de los campos: Bar es {t, o, h, l, c, v} (bb_core.h:27).
    bbcore::ATR14 c;
    for (int i = 0; i < 50; ++i) c.update({0, 100, 101, 99, 100, 0});
    near(c.value(), 2.0, 1e-9, "ATR converge a 2 con TR constante 2");

    // Primera barra: sin cierre previo TR = h-l. Si usara prev_c_=0 daria un TR
    // gigante (101) y contaminaria todo el suavizado.
    bbcore::ATR14 f;
    f.update({0, 100, 101, 99, 100, 0});
    near(f.value(), 2.0, 1e-12, "primera barra: TR = h-l, sin prev_c fantasma");

    // Gap: prev close 100, barra o=111 h=112 l=110 -> TR = |112-100| = 12.
    // Wilder: (2*13 + 12)/14 = 38/14.
    bbcore::ATR14 g;
    g.update({0, 100, 101, 99, 100, 0});
    g.update({0, 111, 112, 110, 111, 0});
    near(g.value(), 38.0 / 14.0, 1e-12, "gap: ATR = (2*13 + 12)/14");
    check(g.value() >= 0,               "ATR nunca negativo");
}

int main() {
    std::printf("=== tests sobre engines/bb_core.h (CODIGO REAL del repo) ===\n\n");
    test_bb_referencia();
    test_bb_ventana_rodante();
    test_bb_degenerada();
    test_bwpct();
    test_atr14();
    std::printf("\n%d pass, %d fail\n", g_pass, g_fail);
    if (g_fail == 0)
        std::printf("OK — recuerda: las copias inline de los 24 bots NO estan cubiertas.\n");
    return g_fail ? 1 : 0;
}
