// test_chase.cpp — persecución de fill de cierres (chase.h, puro).
// Un cierre dormido es exposición viva: el chaser debe (1) respetar el pacing,
// (2) perseguir SOLO hacia el marketable, (3) frenar en el tope de slippage
// anclado al límite INICIAL, y (4) fallar cerrado sin precio de fiar.
#include <cmath>
#include <cstdio>

#include "../chase.h"

using namespace oe;

static int g_fail = 0, g_pass = 0;
#define CHECK(cond, what)                                                        \
    do {                                                                         \
        if (cond) { ++g_pass; }                                                  \
        else { ++g_fail; std::printf("  FALLO %s:%d  %s\n", __FILE__, __LINE__, what); } \
    } while (0)

int main() {
    ChaseCfg cfg;   // interval 15s, max 40, stk 1%, opt 15%

    // pacing: antes del intervalo NO se toca la orden
    auto d = decide_repeg('S', 2.00, 2.00, 1.90, 0, 100, 110, true, cfg);
    CHECK(!d.modify && !d.exhausted, "antes del intervalo: quieto");

    // SELL opt: bid cayó -> perseguir hacia abajo
    d = decide_repeg('S', 2.00, 2.00, 1.90, 0, 100, 120, true, cfg);
    CHECK(d.modify && std::fabs(d.new_limit - 1.90) < 1e-9, "SELL persigue al bid fresco");

    // SELL opt: tope 15% -> jamás por debajo de 1.70
    d = decide_repeg('S', 1.80, 2.00, 1.20, 3, 100, 120, true, cfg);
    CHECK(d.modify && std::fabs(d.new_limit - 1.70) < 1e-9, "SELL frena en el tope de slippage");

    // SELL en el tope y mercado más allá -> exhausto (gritar), no regalar
    d = decide_repeg('S', 1.70, 2.00, 1.20, 4, 100, 120, true, cfg);
    CHECK(!d.modify && d.exhausted, "en el tope: exhausto, la orden descansa");

    // SELL: bid SUBIÓ por encima del límite -> se llenará sola, no repegar
    d = decide_repeg('S', 2.00, 2.00, 2.30, 0, 100, 120, true, cfg);
    CHECK(!d.modify && !d.exhausted, "mercado mejor que el límite: quieto");

    // BUY opt: ask subió -> perseguir hacia arriba, acotado
    d = decide_repeg('B', 2.00, 2.00, 2.10, 0, 100, 120, true, cfg);
    CHECK(d.modify && std::fabs(d.new_limit - 2.10) < 1e-9, "BUY persigue al ask fresco");
    d = decide_repeg('B', 2.00, 2.00, 9.99, 0, 100, 120, true, cfg);
    CHECK(d.modify && std::fabs(d.new_limit - 2.30) < 1e-9, "BUY frena en 2.00*1.15");

    // acciones: tope 1%
    d = decide_repeg('S', 100.00, 100.00, 97.00, 0, 100, 120, false, cfg);
    CHECK(d.modify && std::fabs(d.new_limit - 99.00) < 1e-9, "STK SELL tope 1%%");

    // ruido sub-tick: no repegar por medio centavo
    d = decide_repeg('S', 1.90, 2.00, 1.897, 1, 100, 120, true, cfg);
    CHECK(!d.modify, "sub-tick: quieto (anti-churn)");

    // sin precio de fiar -> fail-closed
    d = decide_repeg('S', 2.00, 2.00, 0.0, 0, 100, 120, true, cfg);
    CHECK(!d.modify && !d.exhausted, "sin precio fresco: quieto");
    d = decide_repeg('S', 2.00, 2.00, -1.0, 0, 100, 120, true, cfg);
    CHECK(!d.modify, "precio negativo: quieto");

    // backstop de repegs
    d = decide_repeg('S', 1.80, 2.00, 1.75, cfg.max_repegs, 100, 120, true, cfg);
    CHECK(!d.modify && d.exhausted, "max_repegs: exhausto");

    // el ancla es el límite INICIAL, no el vigente (escalera sin fondo)
    CHECK(std::fabs(chase_worst('S', 2.00, true, cfg) - 1.70) < 1e-9, "ancla en ref_lim");

    std::printf("chase: %d OK, %d FALLOS\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
