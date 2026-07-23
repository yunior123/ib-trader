// ============================================================================
// engines/tests/combo_test.cpp — tests de combo_core.h (MOTOR 3, B8).
// Compilar normal Y con -fsanitize=address,undefined. Sin daemons, solo asserts.
// clang++ -std=c++23 -O3 -Wall -Wextra -I.. -o combo_test combo_test.cpp
// ============================================================================
#include "../combo_core.h"

#include <cassert>
#include <cmath>
#include <cstdio>
#include <functional>
#include <vector>

using namespace combocore;
using bbcore::Bar;
using bbcore::Config;
using bbcore::Signal;

static int g_checks = 0;
#define CHECK(x) do { assert(x); ++g_checks; } while (0)

// --------------------------- helpers de flujo --------------------------------
// seed: dos registros con delta simetrico 500/500 sobre 5 min -> ema_c=ema_p=100
// contratos/min, sin spike (el primer delta solo SIEMBRA la EMA, como flow_pulse).
static void seed(FlowBook& fb, const char* sym, double t0) {
    fb.on_record(t0, sym, 1000, 1000);
    fb.on_record(t0 + 300, sym, 1500, 1500);
}
// spike calls: dc=3000 dp=0 sobre 10 min -> ritmo 300 = 3x EMA(100), delta>=2000,
// dominancia total, <50x. Llamar SOLO tras seed (prev = 1500/1500).
static void spike_calls(FlowBook& fb, const char* sym, double ts) {
    fb.on_record(ts, sym, 4500, 1500);
}
static void spike_puts(FlowBook& fb, const char* sym, double ts) {
    fb.on_record(ts, sym, 1500, 4500);
}

// --------------------------- 1. FlowBook: spikes -----------------------------
static void test_flow_spikes() {
    FlowBook fb;
    seed(fb, "SPY", 10000);
    CHECK(!fb.calls_active("SPY", 10300));      // seed jamas es spike
    spike_calls(fb, "SPY", 10900);
    CHECK(fb.calls_active("SPY", 10900));
    CHECK(fb.calls_active("SPY", 10900 + 1200));    // borde: 20 min exactos
    CHECK(!fb.calls_active("SPY", 10900 + 1201));   // 20 min + 1 s = expirado
    CHECK(!fb.calls_active("SPY", 10899));          // el futuro no contamina el pasado
    CHECK(!fb.puts_active("SPY", 10900));           // lado correcto
    CHECK(fb.fresh("SPY", 10900 + 1799) && !fb.fresh("SPY", 10900 + 1801));
    CHECK(!fb.fresh("QQQ", 10900));                 // simbolo sin registros: sin contexto
    FlowBook fp;
    seed(fp, "SMH", 10000);
    spike_puts(fp, "SMH", 10900);
    CHECK(fp.puts_active("SMH", 11000) && !fp.calls_active("SMH", 11000));
}

// ------------------- 2. Anti-artefacto: bilateral y >50x ---------------------
static void test_flow_artifacts() {
    FlowBook fb;
    seed(fb, "SPY", 10000);
    fb.on_record(10900, "SPY", 4500, 4500);     // bilateral: ambos lados 3x
    CHECK(!fb.calls_active("SPY", 10900) && !fb.puts_active("SPY", 10900));
    CHECK(fb.artifacts() == 1);
    FlowBook f2;
    seed(f2, "SPY", 10000);
    f2.on_record(10600, "SPY", 32000, 1500);    // rc=6100 > 50x EMA(100): relleno
    CHECK(!f2.calls_active("SPY", 10600));
    CHECK(f2.artifacts() == 1);
    // EMA quedo INTACTA (100): un 6x normal despues SI spikea
    f2.on_record(11200, "SPY", 35000, 1500);    // dc=3000/5min=600=6x EMA(100) -> spike
    CHECK(f2.calls_active("SPY", 11200));
}

// ------------------------ 3. parser jsonl robusto ----------------------------
static void test_parse_flow_line() {
    FlowRec r;
    CHECK(parse_flow_line("{\"ts\":1784727120,\"sym\":\"NVDA\",\"vc\":2481,\"vp\":1220,"
                          "\"pc\":0.492,\"spot\":205.61,\"src\":\"strikes\",\"exp\":\"20260724\"}", r));
    CHECK(r.ts == 1784727120 && r.sym == "NVDA" && r.vc == 2481 && r.vp == 1220);
    CHECK(!parse_flow_line("", r));
    CHECK(!parse_flow_line("garbage not json at all", r));
    CHECK(!parse_flow_line("{\"ts\":123,\"vc\":1,\"vp\":2}", r));            // sin sym
    CHECK(!parse_flow_line("{\"ts\":123,\"sym\":\"QQQ\",\"vc\":abc,\"vp\":2}", r));
    CHECK(!parse_flow_line("{\"ts\":-5,\"sym\":\"QQQ\",\"vc\":1,\"vp\":2}", r));   // ts invalido
    CHECK(!parse_flow_line("{\"ts\":123,\"sym\":\"QQQ\",\"vc\":1,\"vp\":-3}", r)); // vp negativo
    CHECK(!parse_flow_line("{\"ts\":123,\"sym\":\"QQQ", r));                 // truncada
    CHECK(!parse_flow_line("{\"ts\":123,\"sym\":\"\",\"vc\":1,\"vp\":2}", r));     // sym vacio
    CHECK(parse_flow_line("{ \"vp\" : 9 , \"sym\" : \"MU\" , \"ts\" : 55 , \"vc\" : 7 }", r));
    CHECK(r.sym == "MU" && r.ts == 55 && r.vc == 7 && r.vp == 9);            // orden libre
}

// ---------------------------- 4. capitanes -----------------------------------
static void test_captains() {
    auto has = [](const std::vector<std::string>& v, const char* s) {
        for (const auto& x : v) if (x == s) return true;
        return false;
    };
    const auto mu = captains_of("MU");
    CHECK(mu.size() == 3 && has(mu, "SMH") && has(mu, "SPY") && has(mu, "QQQ"));
    const auto nok = captains_of("NOK");
    CHECK(nok.size() == 2 && !has(nok, "SMH") && has(nok, "SPY") && has(nok, "QQQ"));
    const auto spy = captains_of("SPY");
    CHECK(spy.size() == 1 && spy[0] == "QQQ");      // jamas capitan de si mismo
    const auto smh = captains_of("SMH");
    CHECK(smh.size() == 2 && has(smh, "SPY") && has(smh, "QQQ"));
}

// ------------------- escenario end-to-end reutilizable -----------------------
// Calienta 20 barras 5m (99/101), pierce + re-entrada -> candidato elastic
// LONG (o SHORT). flow_setup(fb, tp) se llama con tp = start de la barra del
// pierce; la decision cae en tdec = tp + 600 (cierre de la re-entrada).
static std::vector<Signal> scenario(const char* sym, bool short_side,
                                    const std::function<void(FlowBook&, double)>& flow_setup,
                                    ComboStats* stats = nullptr) {
    FlowBook fb;
    ComboEngine eng(sym, Config{}, 300, [](double) { return 1100; }, fb);
    std::vector<Signal> got;
    double t = 300000;
    for (int i = 0; i < 20; ++i, t += 300) {
        const double c = (i % 2 == 0) ? 99.0 : 101.0;
        for (auto& s : eng.on_bar(Bar{t, c, c + 0.2, c - 0.2, c, 0})) got.push_back(s);
    }
    flow_setup(fb, t);                              // tp = t (barra del pierce)
    if (!short_side) {
        for (auto& s : eng.on_bar(Bar{t, 95, 95, 89, 90, 0})) got.push_back(s);
        t += 300;
        for (auto& s : eng.on_bar(Bar{t, 96, 99.5, 95.5, 99, 0})) got.push_back(s);
    } else {
        for (auto& s : eng.on_bar(Bar{t, 105, 111, 105, 110, 0})) got.push_back(s);
        t += 300;
        for (auto& s : eng.on_bar(Bar{t, 104, 104, 100, 101, 0})) got.push_back(s);
    }
    if (stats) *stats = eng.stats();
    return got;
}
// contexto fresco para sym + sus capitanes (solo seeds, cero spikes)
static void fresh_all(FlowBook& fb, const char* sym, double tp) {
    seed(fb, sym, tp - 1000);
    for (const auto& c : captains_of(sym)) seed(fb, c.c_str(), tp - 1000);
}

// ------- 5. matriz de capitanes: los 4 cuadrantes (regla 12, espejo) ---------
static void test_captain_quadrants() {
    ComboStats st;
    // (1) LONG + capitan SPIKE_CALLS vigente -> VETADO (capitan en contra)
    auto got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
        spike_calls(fb, "SPY", tp - 100);           // vigente en tdec (700 s)
    }, &st);
    CHECK(got.empty());
    CHECK(st.cand == 1 && st.veto_capitan == 1 && st.veto_propio == 0 && st.sin_contexto == 0);
    // (2) LONG + capitan SPIKE_PUTS vigente -> REFUERZO combo_captain
    got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
        spike_puts(fb, "QQQ", tp - 100);
    }, &st);
    CHECK(got.size() == 1 && got[0].side == "LONG" && got[0].kind == "combo_captain");
    CHECK(st.emit_captain == 1 && st.veto_capitan == 0);
    // (3) SHORT + capitan SPIKE_PUTS vigente -> VETADO (espejo)
    got = scenario("NOK", true, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
        spike_puts(fb, "SPY", tp - 100);
    }, &st);
    CHECK(got.empty() && st.veto_capitan == 1);
    // (4) SHORT + capitan SPIKE_CALLS vigente -> REFUERZO combo_captain
    got = scenario("NOK", true, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
        spike_calls(fb, "QQQ", tp - 100);
    }, &st);
    CHECK(got.size() == 1 && got[0].side == "SHORT" && got[0].kind == "combo_captain");
    // niveles coherentes (formato compartido)
    CHECK(got[0].target_px < got[0].ref_px && got[0].stop_px > got[0].ref_px);
}

// ---- 6. jerarquia memoria: SMH capitan de MU; capitan-contra > capitan-favor
static void test_memory_hierarchy() {
    ComboStats st;
    // MU LONG + SMH SPIKE_CALLS -> vetado (SMH es capitan de la tropa memoria)
    auto got = scenario("MU", false, [](FlowBook& fb, double tp) {
        fresh_all(fb, "MU", tp);                    // MU + SMH + SPY + QQQ frescos
        spike_calls(fb, "SMH", tp - 100);
    }, &st);
    CHECK(got.empty() && st.veto_capitan == 1);
    // NOK LONG + SMH SPIKE_CALLS -> SMH NO es su capitan: emite combo_elastic
    got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
        seed(fb, "SMH", tp - 1000);
        spike_calls(fb, "SMH", tp - 100);
    }, &st);
    CHECK(got.size() == 1 && got[0].kind == "combo_elastic");
    // conflicto: QQQ puts (favor) + SPY calls (contra) -> el CONTRA prevalece
    got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
        spike_puts(fb, "QQQ", tp - 100);
        spike_calls(fb, "SPY", tp - 100);
    }, &st);
    CHECK(got.empty() && st.veto_capitan == 1);
}

// --------- 7. spike EN CONTRA del PROPIO ticker = veto_propio ---------------
static void test_own_spike_veto() {
    ComboStats st;
    auto got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
        spike_calls(fb, "NOK", tp - 100);           // el propio NOK con climax calls
    }, &st);
    CHECK(got.empty());
    CHECK(st.veto_propio == 1 && st.veto_capitan == 0);
    // espejo: SHORT con el propio en SPIKE_PUTS -> vetado
    got = scenario("NOK", true, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
        spike_puts(fb, "NOK", tp - 100);
    }, &st);
    CHECK(got.empty() && st.veto_propio == 1);
}

// --------- 8. ventana de 20 min: spike viejo ya NO veta ----------------------
static void test_window_expiry() {
    ComboStats st;
    auto got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        seed(fb, "NOK", tp - 1000);
        seed(fb, "QQQ", tp - 1000);
        seed(fb, "SPY", tp - 1600);
        spike_calls(fb, "SPY", tp - 700);           // tdec - spike = 1300 s > 1200
    }, &st);
    CHECK(got.size() == 1);
    CHECK(got[0].kind == "combo_elastic");          // expirado: ni veta ni refuerza
    CHECK(st.veto_capitan == 0 && st.emit_plain == 1);
}

// --------- 9. SIN flujo = SIN señal (eso ES el diseño) -----------------------
static void test_no_flow_no_signal() {
    ComboStats st;
    auto got = scenario("NOK", false, [](FlowBook&, double) {}, &st);  // cero registros
    CHECK(got.empty());
    CHECK(st.cand == 1 && st.sin_contexto == 1);
    // capitan sin registros (solo el propio fresco) -> tampoco hay contexto
    got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        seed(fb, "NOK", tp - 1000);                 // falta SPY/QQQ
    }, &st);
    CHECK(got.empty() && st.sin_contexto == 1);
    // flujo VIEJO (>30 min) -> sin contexto
    got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp - 2000);            // last_seen a 3300 s del tdec
    }, &st);
    CHECK(got.empty() && st.sin_contexto == 1);
}

// --------- 10. contexto fresco neutro (sin spikes) -> combo_elastic ----------
static void test_neutral_context() {
    ComboStats st;
    auto got = scenario("NOK", false, [](FlowBook& fb, double tp) {
        fresh_all(fb, "NOK", tp);
    }, &st);
    CHECK(got.size() == 1);
    CHECK(got[0].kind == "combo_elastic" && got[0].side == "LONG" && got[0].sym == "NOK");
    CHECK(got[0].target_px > got[0].ref_px && got[0].stop_px < got[0].ref_px);
    CHECK(st.cand == 1 && st.emit_plain == 1 && st.sin_contexto == 0);
}

// --------- 11. FlowBook con basura: jamas crashea ---------------------------
static void test_flowbook_garbage() {
    FlowBook fb;
    fb.on_record(-5, "SPY", 100, 100);              // ts invalido: ignorado
    fb.on_record(100, "SPY", -1, 100);              // vc negativo: ignorado
    CHECK(!fb.fresh("SPY", 100));
    seed(fb, "SPY", 10000);
    fb.on_record(9000, "SPY", 99999, 99999);        // ts hacia ATRAS: sin delta
    CHECK(!fb.calls_active("SPY", 10300));
    fb.on_record(10330, "SPY", 1, 1);               // mins=0.5 < 1: sin ritmo, sin crash
    CHECK(!fb.calls_active("SPY", 10330));
}

int main() {
    test_flow_spikes();
    test_flow_artifacts();
    test_parse_flow_line();
    test_captains();
    test_captain_quadrants();
    test_memory_hierarchy();
    test_own_spike_veto();
    test_window_expiry();
    test_no_flow_no_signal();
    test_neutral_context();
    test_flowbook_garbage();
    std::printf("combo_test OK — %d checks\n", g_checks);
    return 0;
}
