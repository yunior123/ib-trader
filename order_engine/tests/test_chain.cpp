// test_chain.cpp — cadena de opciones y el gate de tamaño/liquidez.
//
// Cobertura que faltaba (encargo 2026-07-25): load_chain, nearest_row,
// exact_row, run_gate y el mapeo delta->stop de order_engine.cpp:918-919
// tenian CERO tests pese a ser el modulo que SI ordena en TWS. Cada caso
// lleva su TESTIGO: se replica la logica VIEJA (la que estaba en linea en
// order_engine.cpp antes del fix) y se comprueba que habria hecho DAÑO donde
// la nueva no lo hace.
//
//   1. centinela -1.0000 en iv/delta usado como delta REAL (defecto 1)
//   2. nearest_row() sin tope de distancia cruza de contrato (defecto 2)
//   3. run_gate(require_exact_strike=true) exige identidad exacta
//   4. run_gate: frescura/spread/OI/budget (comportamiento base, sin regresion)
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <unistd.h>

#include "../chain.h"
#include "../guards.h"

using namespace oe;

static int g_fail = 0, g_pass = 0;

#define CHECK(cond, what)                                                        \
    do {                                                                         \
        if (cond) { ++g_pass; }                                                  \
        else { ++g_fail; std::printf("  FALLO %s:%d  %s\n", __FILE__, __LINE__, what); } \
    } while (0)

static void section(const char* s) { std::printf("\n== %s\n", s); }

// Escribe un fixture de cadena a /tmp y lo parsea. Formato real de
// opt_chain_cache.py: "strike right exp bid ask vol oi iv delta gamma".
static std::string write_fixture(const std::string& body, long long epoch = 1000, double spot = 100.0) {
    static int n = 0;
    std::string path = "/tmp/oe_test_chain_" + std::to_string(::getpid()) + "_" + std::to_string(n++) + ".txt";
    std::ofstream f(path);
    f << "# epoch " << epoch << " spot " << spot << "\n";
    f << body;
    return path;
}

// ============================================== #1 centinela -1.0000
static void test_delta_sentinel() {
    section("DEFECTO 1: centinela -1.0000 (iv/delta) NO es delta real");

    // Fila FUERA de RTH: opt_chain_cache.py escribe nz(v, d=-1.0) para iv Y
    // delta cuando Ticker.modelGreeks es None. MEDIDO 2026-07-25: asi salen
    // el 100% de las filas de data/opt_chain_qqq.txt y opt_chain_nvda.txt.
    std::string p = write_fixture(
        "700.00 C 20260731 2.00 2.10 500 900 -1.0000 -1.0000\n");
    Chain ch = load_chain(p);
    CHECK(ch.ok, "cadena parseada");
    CHECK(ch.rows.size() == 1, "una fila");
    const ChainRow* r = nearest_row(ch, "C", "20260731", 700.0);
    CHECK(r != nullptr, "fila encontrada");
    CHECK(r && std::fabs(r->delta - (-1.0)) < 1e-9, "delta leido = -1.0000 (el centinela crudo, tal cual el fichero)");
    CHECK(r && std::fabs(r->iv - (-1.0)) < 1e-9, "iv leido = -1.0000 (el centinela crudo)");

    // EL AGUJERO: el guard viejo `fabs(delta) > 1e-6` NO distingue el
    // centinela de un delta real -- -1.0 tiene magnitud 1.0, pasa el filtro.
    CHECK(std::fabs(r->delta) > 1e-6, "testigo: el guard viejo ACEPTABA -1.0000 como delta real (bug vivo)");

    // option_greeks_known() (guards.h #10) mira iv, que SIEMPRE acompaña a un
    // delta real y nunca es <= 0 salvo el centinela.
    CHECK(!option_greeks_known(r->iv), "fix: iv=-1.0 -> greeks NO conocidos");

    // El mapeo delta->stop completo: con el centinela, DEBE caer al fallback
    // declarado de clamp_option_stop, jamas usar -1.0 como si fuera un delta
    // real de un put profundo ITM.
    const double fill = 2.05, stop_und = 695.0, level_und = 700.0;
    // TESTIGO de la logica vieja de order_engine.cpp (918-919 antes del fix):
    // `if (fabs(delta) > 1e-6) opt_stop = fill + delta*(stop_und-level_und);`
    double viejo_opt_stop = fill + r->delta * (stop_und - level_und);   // delta=-1.0
    // fill=2.05 + (-1.0)*(695-700) = 2.05 + 5.0 = 7.05 -- MAS DE 3x el fill,
    // muy por ENCIMA de la prima pagada: el clamp de cordura viejo (fill*0.95
    // para un largo) lo topa al 95% del fill = stop nativo nace a -5% de la
    // prima, casi el fill mismo -> STOP-OUT INSTANTANEO en el primer tick.
    CHECK(viejo_opt_stop > fill * 3.0, "testigo: el centinela invierte el signo y dispara el stop MUY por encima del fill");
    double viejo_clamped = std::min(viejo_opt_stop, fill * 0.95);       // clamp del largo, close_side='S'
    CHECK(std::fabs(viejo_clamped - fill * 0.95) < 1e-9, "testigo: el clamp viejo topa al 95% del fill = stop-out casi instantaneo");

    // fix: option_stop_trigger ignora el delta cuando iv dice "no se" y cae
    // al fallback DECLARADO de clamp_option_stop (0.60*fill en un largo).
    double nuevo_stop = option_stop_trigger(fill, r->iv, r->delta, stop_und, level_und, 'S');
    CHECK(std::fabs(nuevo_stop - fill * 0.60) < 1e-9, "fix: centinela -> fallback declarado 0.60*fill, NO el numero invertido");
    CHECK(nuevo_stop < fill, "fix: el stop de un largo queda POR DEBAJO del fill (sano)");

    // Sanity: con un delta REAL (iv>0 lo acompaña) el mapeo normal SI se usa.
    std::string p2 = write_fixture("700.00 C 20260731 2.00 2.10 500 900 0.2200 0.4800\n");
    Chain ch2 = load_chain(p2);
    const ChainRow* r2 = nearest_row(ch2, "C", "20260731", 700.0);
    CHECK(r2 && option_greeks_known(r2->iv), "delta real: iv=0.22 > 0 -> greeks conocidos");
    double stop_real = option_stop_trigger(fill, r2->iv, r2->delta, stop_und, level_und, 'S');
    double esperado = fill + 0.48 * (stop_und - level_und);   // 2.05 + 0.48*(-5) = -0.35 -> clamp al suelo
    esperado = std::max(esperado, std::max(0.01, fill * 0.10));
    esperado = std::min(esperado, fill * 0.95);
    CHECK(std::fabs(stop_real - esperado) < 1e-6, "delta real: se usa el mapeo, no el fallback");
    CHECK(std::fabs(stop_real - fill * 0.60) > 1e-6, "delta real: NO coincide por casualidad con el fallback del centinela");

    // iv ausente del todo (formato viejo sin columnas opcionales): tambien
    // "no se", no un 0 inventado.
    std::string p3 = write_fixture("700.00 C 20260731 2.00 2.10 500 900\n");
    Chain ch3 = load_chain(p3);
    const ChainRow* r3 = nearest_row(ch3, "C", "20260731", 700.0);
    CHECK(r3 && std::fabs(r3->iv - (-1.0)) < 1e-9, "sin columnas iv/delta: iv se queda en el centinela -1.0 (desconocido), no en 0");
    CHECK(r3 && !option_greeks_known(r3->iv), "sin columnas: greeks NO conocidos");
}

// ============================================== #2 nearest_row sin tope / exact_row
static void test_exact_vs_nearest() {
    section("DEFECTO 2: nearest_row() sin tope de distancia cruza de contrato");

    // Cadena con DOS strikes del mismo right/exp: 700 y 705. Solo 705 tiene
    // cotizacion (700 fue removido/deslistado, el caso real que dispara el bug).
    std::string p = write_fixture(
        "705.00 C 20260731 3.00 3.10 800 1200 0.2000 0.4500\n"
        "700.00 P 20260731 1.00 1.10 400 600 0.1800 -0.3800\n");
    Chain ch = load_chain(p);
    CHECK(ch.rows.size() == 2, "dos filas");

    // Pedimos el CALL de 700 (no existe en la cadena, solo el 705C y el 700P).
    const ChainRow* n = nearest_row(ch, "C", "20260731", 700.0);
    CHECK(n != nullptr, "testigo: nearest_row() SIEMPRE devuelve algo si hay right+exp que matchee");
    CHECK(n && std::fabs(n->strike - 705.0) < 1e-9, "testigo: nearest_row() devolvio el 705C -- OTRO CONTRATO -- para un pedido de 700C");

    // exact_row: mismo pedido, strike inexistente -> nullptr, no adivina.
    const ChainRow* e = exact_row(ch, "C", "20260731", 700.0);
    CHECK(e == nullptr, "fix: exact_row() rechaza cuando el strike EXACTO no esta -- no inventa el vecino");

    // exact_row SI encuentra el 705C cuando se pide el 705C real.
    const ChainRow* e2 = exact_row(ch, "C", "20260731", 705.0);
    CHECK(e2 != nullptr && std::fabs(e2->strike - 705.0) < 1e-9, "exact_row encuentra el contrato EXACTO que si esta");

    // exp vacio (el caso que "puede cruzar vencimientos" del encargo): exact_row
    // falla cerrado en vez de matchear cualquier expiry.
    const ChainRow* e3 = exact_row(ch, "C", "", 705.0);
    CHECK(e3 == nullptr, "fix: exact_row() con exp vacio -> nullptr (falla cerrado, no cruza vencimientos)");

    // right distinto al mismo strike/exp no es el mismo contrato.
    const ChainRow* e4 = exact_row(ch, "P", "20260731", 705.0);
    CHECK(e4 == nullptr, "un PUT de 705 no es el CALL de 705 aunque el strike coincida");

    // expiry distinta con mismo strike/right tampoco.
    const ChainRow* e5 = exact_row(ch, "C", "20260807", 705.0);
    CHECK(e5 == nullptr, "misma cifra de strike con otra expiry no es el mismo contrato");
}

// ============================================== #3 run_gate(require_exact_strike)
static void test_run_gate_exact_vs_approx() {
    section("run_gate: require_exact_strike cablea exact_row, false sigue aproximando (entrada)");

    std::string p = write_fixture(
        "705.00 C 20260731 3.00 3.10 800 1200 0.2000 0.4500\n", 1000, 700.0);
    Chain ch = load_chain(p);
    long long now_s = 1000;   // == epoch: cadena fresca

    // ENTRADA (comportamiento base, sin regresion): level=700 es el precio del
    // SUBYACENTE, no un strike -- debe aproximar al 705C.
    Gate g_approx = run_gate(ch, "C", "20260731", 700.0, 'B', 1000.0, now_s);
    CHECK(g_approx.go, "entrada: aproxima al 705C y pasa el gate");
    CHECK(std::fabs(g_approx.strike - 705.0) < 1e-9, "entrada: strike elegido = 705 (el mas cercano a 700)");

    // CLOSE de una posicion conocida en 700C (strike EXACTO, no existe en la
    // cadena): con require_exact_strike=true el gate debe RECHAZAR, no
    // preciar sobre el 705C vecino.
    Gate g_exact = run_gate(ch, "C", "20260731", 700.0, 'S', 1e9, now_s, /*require_exact_strike=*/true);
    CHECK(!g_exact.go, "close exacto: strike 700 no existe -> gate RECHAZA (no adivina el 705C)");
    bool menciona_exacto = false;
    for (auto& w : g_exact.why) if (w.find("EXACTO") != std::string::npos) menciona_exacto = true;
    CHECK(menciona_exacto, "el motivo dice explicitamente que faltaba el contrato EXACTO");

    // Con el strike EXACTO correcto (705), el gate SI pasa.
    Gate g_exact_ok = run_gate(ch, "C", "20260731", 705.0, 'S', 1e9, now_s, true);
    CHECK(g_exact_ok.go, "close exacto sobre el strike REAL (705): gate pasa");
    CHECK(std::fabs(g_exact_ok.limit - 3.00) < 1e-9, "close 'S' cobra el bid (3.00)");
}

// ============================================== #4 run_gate: base (sin regresion)
static void test_run_gate_base_behavior() {
    section("run_gate: frescura/spread/OI/budget (comportamiento base intacto)");

    long long now_s = 2000;
    // Cadena vieja (epoch 1000, now_s 2000 -> age 1000s > MAX_AGE_S 900).
    std::string p_stale = write_fixture("700.00 C 20260731 2.00 2.10 500 900 0.20 0.45\n", 1000);
    Chain ch_stale = load_chain(p_stale);
    Gate g_stale = run_gate(ch_stale, "C", "20260731", 700.0, 'B', 1000.0, now_s);
    CHECK(!g_stale.go, "cadena vieja (>900s) -> gate rechaza");

    // Spread > 5%.
    std::string p_wide = write_fixture("700.00 C 20260731 2.00 2.30 500 900 0.20 0.45\n", 2000);
    Chain ch_wide = load_chain(p_wide);
    Gate g_wide = run_gate(ch_wide, "C", "20260731", 700.0, 'B', 1000.0, now_s);
    CHECK(!g_wide.go, "spread ~13.6% > 5% -> gate rechaza");

    // OI <= 500.
    std::string p_oi = write_fixture("700.00 C 20260731 2.00 2.05 500 500 0.20 0.45\n", 2000);
    Chain ch_oi = load_chain(p_oi);
    Gate g_oi = run_gate(ch_oi, "C", "20260731", 700.0, 'B', 1000.0, now_s);
    CHECK(!g_oi.go, "OI == 500 (no > 500) -> gate rechaza");

    // Budget: prima 205 > 200.
    std::string p_budget = write_fixture("700.00 C 20260731 2.00 2.05 500 900 0.20 0.45\n", 2000);
    Chain ch_budget = load_chain(p_budget);
    Gate g_budget = run_gate(ch_budget, "C", "20260731", 700.0, 'B', 200.0, now_s);
    CHECK(!g_budget.go, "prima $205 > presupuesto $200 -> gate rechaza");
    // El mismo contrato con presupuesto infinito (patron de un close) SI pasa.
    Gate g_nobudget = run_gate(ch_budget, "C", "20260731", 700.0, 'B', 1e9, now_s);
    CHECK(g_nobudget.go, "presupuesto infinito (patron de close): pasa si el resto esta OK");

    // Cadena vacia / inexistente.
    Chain ch_empty = load_chain("/tmp/oe_test_chain_no_existe_" + std::to_string(::getpid()) + ".txt");
    CHECK(!ch_empty.ok, "fichero inexistente -> cadena no ok");
    Gate g_empty = run_gate(ch_empty, "C", "20260731", 700.0, 'B', 1000.0, now_s);
    CHECK(!g_empty.go, "sin cadena -> gate rechaza");

    // Todo sano: gate pasa.
    Gate g_ok = run_gate(ch_budget, "C", "20260731", 700.0, 'S', 1000.0, now_s);
    CHECK(g_ok.go, "todo sano (fresca, spread 2.5%, OI 900, dentro de presupuesto): gate pasa");
    CHECK(std::fabs(g_ok.limit - 2.00) < 1e-9, "side 'S' cobra el bid");
}

int main() {
    std::printf("=== order_engine :: cadena de opciones + gate ===\n");
    test_delta_sentinel();
    test_exact_vs_nearest();
    test_run_gate_exact_vs_approx();
    test_run_gate_base_behavior();
    std::printf("\n=== %d OK, %d FALLOS ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
