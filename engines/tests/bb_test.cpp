// ============================================================================
// engines/tests/bb_test.cpp — tests de bb_core.h (MOTOR 2, B7).
// Compilar normal Y con -fsanitize=address,undefined. Sin daemons, solo asserts.
// clang++ -std=c++23 -O3 -Wall -Wextra -I.. -o bb_test bb_test.cpp
// ============================================================================
#include "../bb_core.h"

#include <cassert>
#include <cmath>
#include <cstdio>
#include <vector>

using namespace bbcore;

static int g_checks = 0;
#define CHECK(x) do { assert(x); ++g_checks; } while (0)
static bool near(double a, double b, double eps = 1e-9) { return std::fabs(a - b) < eps; }

// -------- 1. BB(20,2) poblacional /N vs valores a mano ----------------------
static void test_bb_math() {
    BB bb;
    for (int i = 1; i <= 20; ++i) bb.update(i);          // closes 1..20
    CHECK(bb.ready());
    CHECK(near(bb.mid, 10.5));                            // media a mano
    // var poblacional: sum2/20 - mid^2 = 2870/20 - 110.25 = 33.25
    CHECK(near(bb.sd, std::sqrt(33.25)));
    CHECK(near(bb.up, 10.5 + 2 * std::sqrt(33.25)));
    CHECK(near(bb.dn, 10.5 - 2 * std::sqrt(33.25)));
    // rodante O(1): entra 21, sale 1 -> ventana 2..21, misma varianza, media+1
    bb.update(21);
    CHECK(near(bb.mid, 11.5));
    CHECK(near(bb.sd, std::sqrt(33.25), 1e-8));
}

// -------- 2. %B en los bordes y caso sd=0 (jamas divide por cero) -----------
static void test_pctb_and_flat() {
    BB bb;
    for (int i = 1; i <= 20; ++i) bb.update(i);
    CHECK(near(bb.pctB(bb.dn), 0.0));                     // banda inferior -> 0
    CHECK(near(bb.pctB(bb.up), 1.0));                     // banda superior -> 1
    CHECK(near(bb.pctB(bb.mid), 0.5));                    // media -> 0.5
    BB flat;
    for (int i = 0; i < 25; ++i) flat.update(5.0);        // serie degenerada
    CHECK(flat.sd == 0.0);                                // sd=0 exacto, no NaN
    CHECK(std::isfinite(flat.up) && std::isfinite(flat.dn));
    CHECK(near(flat.pctB(5.0), 0.5));                     // banda plana -> 0.5
    CHECK(flat.bandwidth() == 0.0);
}

// helper: 20 closes alternando 99/101 -> mid=100 sd=1 up=102 dn=98
static void warm_bb(BB& bb, Elastic* el = nullptr) {
    for (int i = 0; i < 20; ++i) {
        const double c = (i % 2 == 0) ? 99.0 : 101.0;
        bb.update(c);
        if (el) { Bar b{(double)i, c, c, c, c, 0}; (void)el->on_close(bb, b); }
    }
    CHECK(near(bb.mid, 100.0) && near(bb.sd, 1.0));
}

// -------- 3. Elastic: pierce (cierre fuera) + re-entrada = evento LONG ------
static void test_elastic_long() {
    BB bb; Elastic el;
    warm_bb(bb, &el);
    // barra 21: c=90 (muy por debajo de dn), low=89 -> arma pierce
    bb.update(90);
    Bar p{2100, 95, 95, 89, 90, 0};
    ElasticEvent ev = el.on_close(bb, p);
    CHECK(ev.dir == 0);                                   // durante el pierce, nada
    CHECK(el.in_pierce_dn());
    // barra 22: c=99 cierra DENTRO -> dispara
    bb.update(99);
    Bar r{2400, 96, 99.5, 95.5, 99, 0};
    ev = el.on_close(bb, r);
    CHECK(ev.dir == +1);
    CHECK(near(ev.pierce_ext, 89.0));                     // min low del pierce
    CHECK(ev.pierce_bars == 1);
    CHECK(near(ev.px, 99.0));
    CHECK(near(ev.mid, bb.mid));                          // target natural = media
    CHECK(ev.mid > ev.px);                                // rebote: media por encima
    CHECK(!el.in_pierce_dn());                            // estado limpio tras evento
}

// -------- 4. Elastic espejo SHORT -------------------------------------------
static void test_elastic_short() {
    BB bb; Elastic el;
    warm_bb(bb, &el);
    bb.update(110);
    (void)el.on_close(bb, Bar{2100, 105, 111, 105, 110, 0});
    CHECK(el.in_pierce_up());
    bb.update(112);                                       // sigue fuera: acumula
    (void)el.on_close(bb, Bar{2400, 110, 113, 110, 112, 0});
    CHECK(el.in_pierce_up());
    bb.update(101);                                       // cierra dentro -> SHORT
    ElasticEvent ev = el.on_close(bb, Bar{2700, 104, 104, 100, 101, 0});
    CHECK(ev.dir == -1);
    CHECK(near(ev.pierce_ext, 113.0));                    // max high del pierce
    CHECK(ev.pierce_bars == 2);
}

// -------- 5. Wick solo NO arma el pierce (print o nada) ---------------------
static void test_wick_no_pierce() {
    BB bb; Elastic el;
    warm_bb(bb, &el);
    bb.update(99);                                        // cierre DENTRO, wick 90
    ElasticEvent ev = el.on_close(bb, Bar{2100, 99, 99.5, 90, 99, 0});
    CHECK(ev.dir == 0);
    CHECK(!el.in_pierce_dn() && !el.in_pierce_up());
}

// -------- 6. parse_bar_line: header/basura jamas crashea --------------------
static void test_parser() {
    Bar b;
    CHECK(!parse_bar_line("epoch,o,h,l,c,v", b));         // header -> false
    CHECK(parse_bar_line("1776951000,653.49,653.62,652.31,653.29,917818", b));
    CHECK(near(b.t, 1776951000) && near(b.c, 653.29) && near(b.v, 917818));
    CHECK(parse_bar_line("1776951000 653.49 653.62 652.31 653.29 917818", b));
    CHECK(near(b.h, 653.62));                             // espacio-separado (live)
    CHECK(parse_bar_line("100,1,2,0.5,1.5", b) && b.v == 0.0);  // v opcional
    CHECK(!parse_bar_line("abc,1,2,3,4,5", b));           // token no numerico
    CHECK(!parse_bar_line("100,1,2,3", b));               // faltan campos
    CHECK(!parse_bar_line("100,10,5,9,8,0", b));          // h < l roto
    CHECK(!parse_bar_line("-5,1,2,1,1,0", b));            // epoch invalido
    CHECK(!parse_bar_line("", b));
    CHECK(!parse_bar_line("100,1,inf,0.5,1.5,0", b));     // no finito
}

// -------- 7. TFAgg 1m -> 5m: OHLC del bucket, cierre sin look-ahead ---------
static void test_tfagg() {
    TFAgg agg(300);
    CHECK(!agg.update(Bar{600, 10, 12, 9, 11, 100}));
    CHECK(!agg.update(Bar{660, 11, 15, 10, 14, 200}));
    CHECK(!agg.update(Bar{720, 14, 14.5, 8, 9, 50}));
    CHECK(!agg.has_closed());                             // bucket abierto: nada
    CHECK(agg.update(Bar{900, 9, 9, 9, 9, 10}));          // bucket nuevo -> cierra
    const Bar& k = agg.closed();
    CHECK(near(k.t, 600) && near(k.o, 10) && near(k.h, 15) && near(k.l, 8));
    CHECK(near(k.c, 9) && near(k.v, 350));
}

// -------- 8. ATR14 Wilder ----------------------------------------------------
static void test_atr() {
    ATR14 atr;
    atr.update(Bar{0, 9, 10, 8, 9, 0});                   // tr=2 -> atr=2
    CHECK(near(atr.value(), 2.0));
    atr.update(Bar{60, 9, 11, 9, 10, 0});                 // tr=max(2,|11-9|,|9-9|)=2
    CHECK(near(atr.value(), 2.0));                        // (2*13+2)/14 = 2
    for (int i = 0; i < 12; ++i) atr.update(Bar{120.0 + i, 10, 11, 9, 10, 0});
    CHECK(atr.ready());
    CHECK(atr.value() > 1.9 && atr.value() < 2.1);
}

// -------- 9. BWPct: percentil rodante ----------------------------------------
static void test_bwpct() {
    BWPct p;
    for (int i = 1; i <= 125; ++i) p.push(i);
    CHECK(p.ready());
    CHECK(near(p.rank(0.5), 0.0));                        // por debajo de todo
    CHECK(near(p.rank(125), 100.0));                      // por encima de todo
    CHECK(near(p.rank(25), 20.0));                        // 25/125 = pctile 20
}

// -------- 10. BandWalk: rachas y reset ---------------------------------------
static void test_bandwalk() {
    BB bb; warm_bb(bb);                                   // up=102, dn=98
    BandWalk w;
    w.on_close(bb, 103); w.on_close(bb, 104); w.on_close(bb, 105);
    CHECK(w.burst_up() && w.walking_up(3) && !w.walking_dn(1));
    w.on_close(bb, 100);                                  // dentro -> reset
    CHECK(!w.burst_up() && !w.walking_up(1));
    w.on_close(bb, 97);
    CHECK(w.burst_dn() && !w.burst_up());
}

// -------- 11. Engine end-to-end 5m: ELASTIC LONG con niveles coherentes -----
static void test_engine_elastic() {
    Config cfg;                                           // defaults: elastic on
    Engine eng("TEST", cfg, 300, [](double) { return 1100; });  // 11:00 ET fijo
    std::vector<Signal> got;
    double t = 1000 * 300.0;
    for (int i = 0; i < 20; ++i, t += 300) {              // calienta BB+ATR
        const double c = (i % 2 == 0) ? 99.0 : 101.0;
        for (auto& s : eng.on_bar(Bar{t, c, c + 0.2, c - 0.2, c, 0})) got.push_back(s);
    }
    CHECK(got.empty());
    for (auto& s : eng.on_bar(Bar{t, 95, 95, 89, 90, 0})) got.push_back(s);  // pierce
    CHECK(got.empty());
    t += 300;
    for (auto& s : eng.on_bar(Bar{t, 96, 99.5, 95.5, 99, 0})) got.push_back(s);  // re-entrada
    CHECK(got.size() == 1);
    const Signal& s = got[0];
    CHECK(s.side == "LONG" && s.kind == "ELASTIC" && s.sym == "TEST");
    CHECK(near(s.epoch, t));                              // epoch = START de la barra
    CHECK(near(s.ref_px, 99.0));
    CHECK(s.target_px > s.ref_px);                        // target = media BB > ref
    CHECK(s.stop_px < 89.0);                              // stop = min pierce - 0.5*ATR
    CHECK(s.pctb >= 0.0 && s.pctb <= 1.0);
}

// -------- 12. Engine: señal disabled por config = no emite -------------------
static void test_engine_disabled() {
    Config cfg; cfg.elastic_enabled = false;
    Engine eng("TEST", cfg, 300, [](double) { return 1100; });
    std::vector<Signal> got;
    double t = 1000 * 300.0;
    for (int i = 0; i < 20; ++i, t += 300) {
        const double c = (i % 2 == 0) ? 99.0 : 101.0;
        for (auto& s : eng.on_bar(Bar{t, c, c, c, c, 0})) got.push_back(s);
    }
    for (auto& s : eng.on_bar(Bar{t, 95, 95, 89, 90, 0})) got.push_back(s);
    t += 300;
    for (auto& s : eng.on_bar(Bar{t, 96, 99.5, 95.5, 99, 0})) got.push_back(s);
    CHECK(got.empty());                                   // gating: disabled = mudo
}

// -------- 13. Engine: fuera de RTH (subasta 9:30-9:45) = no emite ------------
static void test_engine_rth() {
    Config cfg;
    Engine eng("TEST", cfg, 300, [](double) { return 935; });  // 9:35 = subasta
    std::vector<Signal> got;
    double t = 1000 * 300.0;
    for (int i = 0; i < 20; ++i, t += 300) {
        const double c = (i % 2 == 0) ? 99.0 : 101.0;
        for (auto& s : eng.on_bar(Bar{t, c, c + 0.2, c - 0.2, c, 0})) got.push_back(s);
    }
    for (auto& s : eng.on_bar(Bar{t, 95, 95, 89, 90, 0})) got.push_back(s);
    t += 300;
    for (auto& s : eng.on_bar(Bar{t, 96, 99.5, 95.5, 99, 0})) got.push_back(s);
    CHECK(got.empty());
}

int main() {
    test_bb_math();
    test_pctb_and_flat();
    test_elastic_long();
    test_elastic_short();
    test_wick_no_pierce();
    test_parser();
    test_tfagg();
    test_atr();
    test_bwpct();
    test_bandwalk();
    test_engine_elastic();
    test_engine_disabled();
    test_engine_rth();
    std::printf("bb_test OK — %d checks\n", g_checks);
    return 0;
}
