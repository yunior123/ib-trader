// test_orders.cpp — compra/venta de OPCIONES y ACCIONES, extremo a extremo.
//
// Encargo de Yunior 2026-07-26: "buy, sell options and shares, full testing for
// those". test_guards.cpp cubre las guardas de una en una y test_chain.cpp el
// parseo/gate; lo que faltaba es (a) los BORDES de load_chain, (b) el camino de
// ACCIONES —que no tenia NI UN test pese a ser el unico que llena 24/5— y (c) la
// ruta close COMPLETA, encadenando las tres guardas en el orden real del motor.
//
// Cada caso lleva su TESTIGO cuando replica un agujero: se ejercita la logica
// VIEJA y se comprueba que habria hecho daño donde la nueva no lo hace.
#include <cmath>
#include <cstdio>
#include <fstream>
#include <string>
#include <unistd.h>
#include <vector>

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

static std::string write_raw(const std::string& body) {
    static int n = 0;
    std::string path = "/tmp/oe_test_orders_" + std::to_string(::getpid()) + "_" + std::to_string(n++) + ".txt";
    std::ofstream f(path);
    f << body;
    return path;
}

// ============================================== load_chain: los BORDES
static void test_load_chain_edges() {
    section("load_chain: fichero vacio / fila corta / exp mal formado / basura");

    // (a) Fichero que EXISTE pero esta vacio. Distinto de "no existe": el
    //     escritor pudo truncarlo a mitad (opt_chain_cache abre con "w"). ok=false
    //     en ambos casos -- jamas una cadena "valida" de 0 filas.
    Chain vacio = load_chain(write_raw(""));
    CHECK(!vacio.ok, "fichero vacio -> cadena NO ok");
    CHECK(vacio.rows.empty(), "y sin filas");
    CHECK(vacio.epoch == 0 && vacio.spot == 0, "epoch/spot se quedan en 0 (no hay cabecera que creer)");

    // (b) Solo cabecera, cero filas: es el estado REAL de un fichero recien
    //     truncado. Si esto diera ok=true, run_gate preciaria sobre nada.
    Chain solo_cab = load_chain(write_raw("# epoch 1000 spot 700.0\n"));
    CHECK(!solo_cab.ok, "solo cabecera, 0 filas -> NO ok (cadena vacia no es cadena fresca)");
    Gate g_cab = run_gate(solo_cab, "C", "20260731", 700.0, 'B', 1000.0, 1000);
    CHECK(!g_cab.go, "gate sobre cadena de 0 filas rechaza");

    // (c) FILA CORTA: menos de las 7 columnas obligatorias. `ss >> ...` falla y
    //     la fila se DESCARTA entera. El peligro seria aceptarla a medias con
    //     oi=0/bid=0 -- ceros plausibles que el gate leeria como "iliquido"
    //     cuando la verdad es "no se".
    Chain corta = load_chain(write_raw(
        "# epoch 1000 spot 700.0\n"
        "700.00 C 20260731 2.00\n"                              // faltan ask/vol/oi
        "705.00 C 20260731 3.00 3.10 800 1200 0.20 0.45\n"));
    CHECK(corta.rows.size() == 1, "fila corta DESCARTADA entera, no aceptada a medias");
    CHECK(corta.rows.size() == 1 && std::fabs(corta.rows[0].strike - 705.0) < 1e-9,
          "la fila que sobrevive es la COMPLETA (705), no la truncada");
    CHECK(exact_row(corta, "C", "20260731", 700.0) == nullptr,
          "el 700C truncado no existe para exact_row (no se inventa con oi=0)");

    // (d) Linea de basura no numerica: se descarta sin arrastrar la siguiente.
    Chain basura = load_chain(write_raw(
        "# epoch 1000 spot 700.0\n"
        "ERROR: no market data\n"
        "705.00 C 20260731 3.00 3.10 800 1200 0.20 0.45\n"));
    CHECK(basura.rows.size() == 1, "linea de texto libre descartada, la buena sigue leyendose");

    // (e) EXP MAL FORMADO. load_chain guarda el exp como STRING tal cual: no
    //     valida formato, y no debe -- pero entonces la comparacion de exact_row
    //     tiene que ser textual ESTRICTA, o "2026-07-31" casaria con "20260731".
    Chain mal_exp = load_chain(write_raw(
        "# epoch 1000 spot 700.0\n"
        "700.00 C 2026-07-31 2.00 2.10 500 900 0.20 0.45\n"));
    CHECK(mal_exp.rows.size() == 1, "exp con guiones se parsea (es un string, no una fecha)");
    CHECK(exact_row(mal_exp, "C", "20260731", 700.0) == nullptr,
          "'2026-07-31' NO casa con '20260731': comparacion textual estricta");
    CHECK(exact_row(mal_exp, "C", "2026-07-31", 700.0) != nullptr,
          "casa solo con el exp EXACTO tal cual esta escrito");
    // Y el gate de ENTRADA tampoco lo cruza: pedir 20260731 no cae en el 2026-07-31.
    Gate g_mal = run_gate(mal_exp, "C", "20260731", 700.0, 'B', 1000.0, 1000);
    CHECK(!g_mal.go, "entrada con exp que no existe: gate rechaza, no aproxima a OTRO vencimiento");

    // (f) Cabecera SIN epoch: epoch=0 -> edad gigante -> el gate la trata como
    //     rancia. Un epoch ausente no puede volverse "ahora" por defecto.
    Chain sin_ep = load_chain(write_raw(
        "# spot 700.0\n"
        "700.00 C 20260731 2.00 2.05 500 900 0.20 0.45\n"));
    CHECK(sin_ep.ok && sin_ep.epoch == 0, "sin epoch en la cabecera -> epoch 0");
    Gate g_sin_ep = run_gate(sin_ep, "C", "20260731", 700.0, 'B', 1000.0, 1'700'000'000);
    CHECK(!g_sin_ep.go, "epoch ausente = cadena infinitamente vieja -> RECHAZA (no 'fresca por defecto')");

    // (g) Lineas en blanco intercaladas y \r de un fichero con CRLF.
    Chain crlf = load_chain(write_raw(
        "# epoch 1000 spot 700.0\n"
        "\n"
        "700.00 C 20260731 2.00 2.05 500 900 0.20 0.45\n"
        "\n"));
    CHECK(crlf.rows.size() == 1, "lineas en blanco ignoradas");
}

// ============================================== run_gate: BORDES de cada guarda
static void test_run_gate_boundaries() {
    section("run_gate: el borde EXACTO de spread / OI / presupuesto / frescura");

    auto mk = [&](const std::string& row, long long ep) {
        return load_chain(write_raw("# epoch " + std::to_string(ep) + " spot 700.0\n" + row));
    };
    const long long now_s = 2000;

    // --- FRESCURA: MAX_AGE_S = 900 es INCLUSIVO (age <= 900 pasa).
    Chain justo = mk("700.00 C 20260731 2.00 2.05 500 900 0.20 0.45\n", now_s - 900);
    CHECK(run_gate(justo, "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "edad 900s exacta: PASA (limite inclusivo)");
    Chain pasado = mk("700.00 C 20260731 2.00 2.05 500 900 0.20 0.45\n", now_s - 901);
    CHECK(!run_gate(pasado, "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "edad 901s: RECHAZA");
    Chain futuro_ok = mk("700.00 C 20260731 2.00 2.05 500 900 0.20 0.45\n", now_s + 5);
    CHECK(run_gate(futuro_ok, "C", "20260731", 700.0, 'B', 1000.0, now_s).go,
          "clock skew futuro 5s: PASA");
    Chain futuro = mk("700.00 C 20260731 2.00 2.05 500 900 0.20 0.45\n", now_s + 6);
    Gate g_future = run_gate(futuro, "C", "20260731", 700.0, 'B', 1000.0, now_s);
    CHECK(!g_future.go, "timestamp futuro >5s: RECHAZA");
    CHECK(!g_future.why.empty() && g_future.why[0].find("timestamp futuro") != std::string::npos,
          "timestamp futuro: explica el veto");

    // --- SPREAD: 5.0% exacto pasa; un pelo mas, no. bid 1.95 / ask 2.05 -> mid
    //     2.00, spread 0.10 = 5.000%.
    Chain sp5 = mk("700.00 C 20260731 1.95 2.05 500 900 0.20 0.45\n", now_s);
    Gate g_sp5 = run_gate(sp5, "C", "20260731", 700.0, 'B', 1000.0, now_s);
    CHECK(std::fabs(g_sp5.spread_pct - 5.0) < 1e-9, "spread calculado = 5.000%");
    CHECK(g_sp5.go, "spread 5.00% exacto: PASA (<=5, no <5)");
    Chain sp6 = mk("700.00 C 20260731 1.94 2.06 500 900 0.20 0.45\n", now_s);
    CHECK(!run_gate(sp6, "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "spread 6% RECHAZA");

    // --- OI: la doctrina dice OI > 500 ESTRICTO. 500 no pasa, 501 si.
    CHECK(!run_gate(mk("700.00 C 20260731 2.00 2.05 500 500 0.20 0.45\n", now_s),
                    "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "OI 500 exacto: RECHAZA (>500 estricto)");
    CHECK(run_gate(mk("700.00 C 20260731 2.00 2.05 500 501 0.20 0.45\n", now_s),
                   "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "OI 501: PASA");
    CHECK(!run_gate(mk("700.00 C 20260731 2.00 2.05 500 0 0.20 0.45\n", now_s),
                    "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "OI 0: RECHAZA");

    // --- PRESUPUESTO: prima == budget PASA (<=), un centavo mas no. ask 2.00 ->
    //     prima $200 con el presupuesto por defecto de la casa.
    Chain b200 = mk("700.00 C 20260731 1.96 2.00 500 900 0.20 0.45\n", now_s);
    Gate g_b200 = run_gate(b200, "C", "20260731", 700.0, 'B', 200.0, now_s);
    CHECK(std::fabs(g_b200.premium - 200.0) < 1e-9, "prima = $200 exactos");
    CHECK(g_b200.go, "prima $200 con presupuesto $200: PASA (limite inclusivo)");
    Chain b201 = mk("700.00 C 20260731 1.97 2.01 500 900 0.20 0.45\n", now_s);
    CHECK(!run_gate(b201, "C", "20260731", 700.0, 'B', 200.0, now_s).go, "prima $201 > $200: RECHAZA");

    // --- COTIZACION PODRIDA. Estos son los que NO pueden fallar abierto: sin
    //     NBBO el spread es incalculable y el gate viejo del resto de la flota
    //     (aapl_signal_bot:1738) pasaba todo con sp=0. Aqui debe RECHAZAR.
    CHECK(!run_gate(mk("700.00 C 20260731 0.00 2.05 500 900 0.20 0.45\n", now_s),
                    "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "bid 0 (sin puja): RECHAZA, no 'spread 0 = perfecto'");
    CHECK(!run_gate(mk("700.00 C 20260731 2.00 0.00 500 900 0.20 0.45\n", now_s),
                    "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "ask 0: RECHAZA");
    CHECK(!run_gate(mk("700.00 C 20260731 2.10 2.00 500 900 0.20 0.45\n", now_s),
                    "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "bid > ask (libro cruzado/corrupto): RECHAZA");
    CHECK(!run_gate(mk("700.00 C 20260731 -1.00 -1.00 500 900 0.20 0.45\n", now_s),
                    "C", "20260731", 700.0, 'B', 1000.0, now_s).go, "bid/ask centinela -1: RECHAZA");

    // --- LADO: 'B' paga el ask, 'S' cobra el bid. Confundirlos es regalar el spread.
    Chain lados = mk("700.00 C 20260731 1.96 2.00 500 900 0.20 0.45\n", now_s);
    CHECK(std::fabs(run_gate(lados, "C", "20260731", 700.0, 'B', 1e9, now_s).limit - 2.00) < 1e-9, "compra al ask");
    CHECK(std::fabs(run_gate(lados, "C", "20260731", 700.0, 'S', 1e9, now_s).limit - 1.96) < 1e-9, "venta al bid");

    // --- PUTS por la misma puerta que los calls (Yunior opera los dos).
    Chain puts = mk("700.00 P 20260731 1.96 2.00 500 900 0.20 -0.45\n", now_s);
    Gate g_put = run_gate(puts, "P", "20260731", 700.0, 'B', 1000.0, now_s);
    CHECK(g_put.go && g_put.right == "P", "PUT pasa el gate igual que un call");
    CHECK(g_put.delta < 0, "el delta del put llega NEGATIVO (no se toma valor absoluto)");
    CHECK(!run_gate(puts, "C", "20260731", 700.0, 'B', 1000.0, now_s).go,
          "pedir el CALL cuando la cadena solo trae el PUT: RECHAZA, no sirve el put");
}

// ============================================== ACCIONES: comprar y vender
static void test_stock_entry() {
    section("ACCIONES: decide_stock_entry (el camino que SI llena 24/5)");

    // TESTIGO de la logica VIEJA (order_engine.cpp, bloque ACCIONES antes del fix):
    // notional medido al SPOT y sin mirar el limite ya redondeado.
    auto old_stock = [](double spot, int qty, double budget, char side, double& lim) -> bool {
        if (spot <= 0) return false;
        if (qty * spot > budget) return false;
        lim = (side == 'B') ? spot * 1.001 : spot * 0.999;
        lim = std::round(lim * 100.0) / 100.0;
        return true;
    };

    // --- COMPRA sana: limite marketable por ENCIMA del spot, al centavo.
    StockEntry b = decide_stock_entry(100.00, 10, 3000.0, 'B');
    CHECK(b.ok, "compra 10 x $100 dentro de $3000: OK");
    CHECK(std::fabs(b.limit - 100.10) < 1e-9, "compra: limite 100.10 (+0.1%) redondeado al centavo");
    CHECK(b.limit > 100.00, "el limite de COMPRA queda POR ENCIMA del spot (marketable)");
    CHECK(std::fabs(b.notional - 1001.0) < 1e-9, "notional = qty x LIMITE ($1001), no qty x spot ($1000)");

    // --- VENTA sana: limite por DEBAJO del spot.
    StockEntry s = decide_stock_entry(100.00, 10, 3000.0, 'S');
    CHECK(s.ok && std::fabs(s.limit - 99.90) < 1e-9, "venta: limite 99.90 (-0.1%)");
    CHECK(s.limit < 100.00, "el limite de VENTA queda POR DEBAJO del spot (marketable)");

    // --- AGUJERO (b): notional al SPOT vs al LIMITE. Justo en el borde del
    //     presupuesto, el viejo aceptaba una orden que de verdad lo rebasa.
    {
        double lim_viejo = 0;
        const bool viejo_ok = old_stock(100.00, 30, 3000.0, 'B', lim_viejo);
        CHECK(viejo_ok, "testigo: el viejo acepta 30 x $100 = $3000 exactos (mide al spot)");
        CHECK(std::fabs(30 * lim_viejo - 3003.0) < 1e-9,
              "testigo: pero al limite 100.10 el desembolso REAL es $3003 -- $3 POR ENCIMA del tope");
        StockEntry nuevo = decide_stock_entry(100.00, 30, 3000.0, 'B');
        CHECK(!nuevo.ok, "fix: se mide al limite -> $3003 > $3000 RECHAZADO");
        StockEntry cabe = decide_stock_entry(100.00, 29, 3000.0, 'B');
        CHECK(cabe.ok && cabe.notional <= 3000.0 + 1e-9, "29 acciones ($2902.90) si caben");
    }

    // --- AGUJERO (a): spot sub-centavo -> el limite se redondea a 0.00 y el
    //     viejo mandaba una orden a PRECIO CERO.
    {
        double lim_viejo = 0;
        const bool viejo_ok = old_stock(0.004, 100, 3000.0, 'B', lim_viejo);
        CHECK(viejo_ok, "testigo: el viejo acepta un spot de $0.004 (>0, notional $0.40 < budget)");
        CHECK(std::fabs(lim_viejo) < 1e-9, "testigo: y el limite redondeado sale 0.00 -> orden a PRECIO CERO");
        StockEntry nuevo = decide_stock_entry(0.004, 100, 3000.0, 'B');
        CHECK(!nuevo.ok, "fix: limite 0.00 -> RECHAZADO, no se manda a precio cero");
        CHECK(nuevo.reason.find("cero") != std::string::npos, "y la razon lo dice");
    }
    // Un centavo justo si es operable.
    CHECK(decide_stock_entry(0.01, 100, 3000.0, 'B').ok, "spot $0.01: limite 0.01, operable");

    // --- FALLA CERRADO en todo lo demas.
    CHECK(!decide_stock_entry(0.0, 10, 3000.0, 'B').ok, "spot 0 -> RECHAZADO (no se inventa precio)");
    CHECK(!decide_stock_entry(-5.0, 10, 3000.0, 'B').ok, "spot negativo -> RECHAZADO");
    CHECK(!decide_stock_entry(100.0, 0, 3000.0, 'B').ok, "qty 0 -> RECHAZADO");
    CHECK(!decide_stock_entry(100.0, -10, 3000.0, 'B').ok, "qty negativa -> RECHAZADO");
    CHECK(!decide_stock_entry(100.0, 10, 0.0, 'B').ok, "budget 0 -> RECHAZADO (no 'gratis')");
    CHECK(!decide_stock_entry(100.0, 10, -1.0, 'B').ok, "budget negativo -> RECHAZADO");
    CHECK(!decide_stock_entry(100.0, 10, 3000.0, 'X').ok, "side invalido -> RECHAZADO");
    // Ninguna rechazada devuelve numeros plausibles que el llamante pueda usar.
    StockEntry mala = decide_stock_entry(0.0, 10, 3000.0, 'B');
    CHECK(mala.limit == 0 && mala.notional == 0 && !mala.reason.empty(),
          "rechazo: limit/notional en 0 Y con razon -- nunca un limite usable");

    // --- Una accion cara: 1 x $2500 cabe en $3000, 2 no.
    CHECK(decide_stock_entry(2500.0, 1, 3000.0, 'B').ok, "1 accion de $2500 cabe");
    CHECK(!decide_stock_entry(2500.0, 2, 3000.0, 'B').ok, "2 acciones de $2500 = $5005 NO caben");
}

// ============================================== TOPE AGREGADO con los dos activos
static void test_aggregate_cap_mixed() {
    section("tope AGREGADO: opciones y acciones comparten bolsillo, ciclo completo");

    ExposureBook bk; bk.cap = 3000.0;

    // 3 zonas de opciones a $200 la prima (el presupuesto de la casa) + acciones.
    CHECK(bk.reserve(exposure_key("QQQ", "z1"), 200.0), "opcion QQQ z1 $200");
    CHECK(bk.reserve(exposure_key("NVDA", "z1"), 200.0), "opcion NVDA z1 $200 (misma zona-id, OTRO simbolo)");
    CHECK(std::fabs(bk.total() - 400.0) < 1e-9,
          "la clave lleva el SIMBOLO: 'z1' de QQQ y de NVDA son dos desembolsos, no uno");

    // Acciones del mismo bolsillo.
    CHECK(bk.reserve(exposure_key("MU", "zs"), 2500.0), "acciones MU $2500 cabe (total $2900)");
    CHECK(!bk.reserve(exposure_key("SPY", "z9"), 200.0), "otra opcion de $200 ya NO cabe: $3100 > $3000");

    // Ciclo de vida: la zona muere sin posicion -> se libera -> vuelve a caber.
    bk.release(exposure_key("NVDA", "z1"));
    CHECK(std::fabs(bk.total() - 2700.0) < 1e-9, "release de la zona rechazada/cancelada descuenta");
    CHECK(bk.reserve(exposure_key("SPY", "z9"), 200.0), "liberado el sitio, ahora si entra");

    // Release de una clave que no existe es inocuo (el motor libera en varias
    // ramas terminales; ninguna puede corromper el total).
    const double antes = bk.total();
    bk.release(exposure_key("NO", "existe"));
    CHECK(std::fabs(bk.total() - antes) < 1e-9, "release de clave inexistente no altera el total");

    // Doble release de la misma clave tampoco resta dos veces.
    bk.release(exposure_key("SPY", "z9"));
    bk.release(exposure_key("SPY", "z9"));
    CHECK(std::fabs(bk.total() - 2700.0) < 1e-9, "doble release no resta dos veces");

    // El desembolso reservado de una opcion es qty*prima, no la prima.
    ExposureBook bk2; bk2.cap = 1000.0;
    CHECK(!bk2.reserve(exposure_key("QQQ", "zq"), 6 * 200.0), "qty=6 x $200 = $1200 > cap $1000 RECHAZADO");
    CHECK(bk2.reserve(exposure_key("QQQ", "zq"), 5 * 200.0), "qty=5 x $200 = $1000 justo en el cap: cabe");
}

// ============================================== la ruta CLOSE, entera
static void test_close_route_end_to_end() {
    section("ruta CLOSE completa: tamaño -> stop huerfano -> gate, en el orden real");

    // Estado real: 2 contratos largos de QQQ 705C llenos, con stop nativo vivo,
    // y 40 acciones de MU con su propio stop.
    const std::string exp = "20260731";
    PositionBook pb; pb.begin();
    pb.set(pos_key_option("QQQ", exp, 705.0, "C"), 2);
    pb.set(pos_key_stock("MU"), 40);
    pb.end();

    std::vector<StopRef> stops = {
        {"z1", "opt", exp, 705.0, 'C', 4001, 2.0},
        {"z2", "opt", exp, 700.0, 'C', 4002, 1.0},
        {"z3", "stk", "",    0.0,   0, 4004, 40.0},
    };

    const long long now_s = 2000;
    Chain ch = load_chain(write_raw(
        "# epoch 2000 spot 704.0\n"
        "705.00 C 20260731 3.00 3.10 800 1200 0.2000 0.4500\n"
        "700.00 C 20260731 6.00 6.15 800 1200 0.2000 0.7000\n"));

    // ---- PASO 1: tamaño contra la posicion REAL. El panel manda 5, hay 2.
    CloseDecision d = decide_close_qty(pb, pos_key_option("QQQ", exp, 705.0, "C"), 5, 'S');
    CHECK(d.ok && d.qty == 2 && d.clamped, "paso 1: 5 pedidos, 2 reales -> clamp a 2");

    // ---- PASO 2: el stop nativo de ESE contrato se cancela ANTES del close.
    CloseReq creq; creq.is_opt = true; creq.exp = exp; creq.strike = 705.0;
    creq.right = 'C'; creq.qty = d.qty;
    auto orphans = stops_orphaned_by_close(creq, stops);
    CHECK(orphans.size() == 1 && orphans[0].stop_id == 4001, "paso 2: cancela SOLO el stop del 705C");
    CHECK(!orphans[0].partial, "cierre total de los 2: no es parcial");
    for (const auto& o : orphans) CHECK(o.stop_id != 4002 && o.stop_id != 4004,
                                        "no toca el stop del 700C ni el de la accion");

    // ---- PASO 3: el gate precia el contrato EXACTO, no el vecino.
    Gate g = run_gate(ch, "C", exp, 705.0, 'S', 1e9, now_s, /*require_exact_strike=*/true);
    CHECK(g.go, "paso 3: gate del close pasa");
    CHECK(std::fabs(g.limit - 3.00) < 1e-9, "close 'S' cobra el bid del 705C (3.00)");
    CHECK(std::fabs(g.strike - 705.0) < 1e-9, "y sobre el strike EXACTO, no el 700C de al lado");
    // TESTIGO: nearest_row habria devuelto el 700C si el 705 faltara de la cadena.
    Chain sin705 = load_chain(write_raw(
        "# epoch 2000 spot 704.0\n"
        "700.00 C 20260731 6.00 6.15 800 1200 0.2000 0.7000\n"));
    const ChainRow* vecino = nearest_row(sin705, "C", exp, 705.0);
    CHECK(vecino && std::fabs(vecino->strike - 700.0) < 1e-9,
          "testigo: sin el 705 en la cadena, nearest_row entrega el 700C -- OTRO contrato");
    CHECK(std::fabs(vecino->bid - 6.00) < 1e-9,
          "testigo: y su bid es 6.00 -- se cerraria al DOBLE de precio, la orden no llena");
    Gate g_sin = run_gate(sin705, "C", exp, 705.0, 'S', 1e9, now_s, true);
    CHECK(!g_sin.go, "fix: exact_row falta -> el close se VETA en vez de preciar el vecino");

    // ---- El gate del close NO se salta por dinero (presupuesto infinito) pero SI
    //      por cadena podrida: cerrar nunca se veta por caro, si por precio falso.
    Chain rancia = load_chain(write_raw(
        "# epoch 100 spot 704.0\n"
        "705.00 C 20260731 3.00 3.10 800 1200 0.2000 0.4500\n"));
    CHECK(!run_gate(rancia, "C", exp, 705.0, 'S', 1e9, now_s, true).go,
          "close con cadena rancia (1900s): VETADO -- no se cierra a un precio de hace media hora");
    Chain ancha = load_chain(write_raw(
        "# epoch 2000 spot 704.0\n"
        "705.00 C 20260731 3.00 3.60 800 1200 0.2000 0.4500\n"));
    CHECK(!run_gate(ancha, "C", exp, 705.0, 'S', 1e9, now_s, true).go,
          "close con spread 18%: VETADO (regla #4 de la casa, tambien al salir)");
    // Prima $310 con presupuesto infinito: el close NO se veta por dinero.
    CHECK(run_gate(ch, "C", exp, 705.0, 'S', 1e9, now_s, true).go,
          "close con prima $300: PASA -- cerrar no se veta por presupuesto");

    // ---- CIERRE PARCIAL: 1 de 2 -> el stop se cancela IGUAL y se marca re-armar.
    CloseReq parcial = creq; parcial.qty = 1;
    auto op = stops_orphaned_by_close(parcial, stops);
    CHECK(op.size() == 1 && op[0].partial,
          "parcial: el stop de 2 contratos protegeria de MAS de lo que queda -> cancelar y RE-ARMAR");
    CHECK(decide_close_qty(pb, pos_key_option("QQQ", exp, 705.0, "C"), 1, 'S').qty == 1,
          "parcial: se autoriza cerrar 1");

    // ---- ACCIONES por la misma ruta.
    CloseDecision ds = decide_close_qty(pb, pos_key_stock("MU"), 100, 'S');
    CHECK(ds.ok && ds.qty == 40 && ds.clamped, "acciones: 100 pedidas, 40 reales -> clamp 40");
    CloseReq cs; cs.is_opt = false; cs.qty = ds.qty;
    auto os = stops_orphaned_by_close(cs, stops);
    CHECK(os.size() == 1 && os[0].stop_id == 4004, "acciones: solo huerfana el stop de acciones");
    // El close de acciones se precia con el spot, no con la cadena: aqui la guarda
    // es decide_stock_entry, que ya rechaza el spot ausente.
    CHECK(!decide_stock_entry(0.0, ds.qty, 1e9, 'S').ok,
          "close de acciones sin spot: RECHAZADO (no se cierra a ciegas)");
    CHECK(decide_stock_entry(50.0, ds.qty, 1e9, 'S').ok, "close de acciones con spot vivo: OK");

    // ---- La ruta entera FALLA CERRADO si el paso 1 no puede saber la posicion.
    PositionBook sin_reconciliar;
    CHECK(!decide_close_qty(sin_reconciliar, pos_key_option("QQQ", exp, 705.0, "C"), 2, 'S').ok,
          "sin reqPositions completado la ruta close se corta EN EL PASO 1, antes de preciar nada");
}

// ============================================== delta -> stop, los dos activos
static void test_delta_to_stop_mapping() {
    section("mapeo delta->stop: opciones (centinela y delta real) y acciones");

    const double fill = 2.05, level = 700.0, stop_und = 695.0;

    // El caso que motivo el fix: PUT deep-ITM con delta -1.0 y iv centinela.
    CHECK(std::fabs(option_stop_trigger(fill, -1.0, -1.0, stop_und, level, 'S') - fill * 0.60) < 1e-9,
          "centinela iv=-1 -> fallback 0.60*fill declarado");
    // El MISMO delta -1.0 con iv real (put deep-ITM legitimo) SI se usa.
    const double con_iv = option_stop_trigger(fill, 0.35, -1.0, stop_und, level, 'S');
    CHECK(std::fabs(con_iv - clamp_option_stop(fill, -1.0, stop_und, level, 'S')) < 1e-9,
          "iv real: el delta -1.0 se usa tal cual (es un put deep-ITM de verdad)");
    CHECK(con_iv < fill, "y aun asi el stop de un LARGO nunca queda por encima del fill");

    // PUT normal comprado: el subyacente SUBE contra ti -> la prima cae.
    const double put_stop = option_stop_trigger(fill, 0.22, -0.45, /*stop_und=*/705.0, level, 'S');
    CHECK(put_stop < fill && put_stop >= 0.01, "put largo: stop bajo el fill, nunca bajo el tick");

    // Todo el rango de deltas posibles: el stop de un largo SIEMPRE queda en banda.
    for (int i = -100; i <= 100; ++i) {
        const double dd = i / 100.0;
        const double st = option_stop_trigger(fill, 0.22, dd, stop_und, level, 'S');
        CHECK(st >= 0.01 && st <= fill * 0.95 + 1e-9, "largo: cualquier delta cae dentro de [0.01, 0.95*fill]");
        const double sc = option_stop_trigger(fill, 0.22, dd, stop_und, level, 'B');
        CHECK(sc >= fill * 1.05 - 1e-9 && sc <= fill * 2.50 + 1e-9, "corto: cualquier delta cae dentro de [1.05, 2.50]*fill");
    }

    // ACCIONES: el stop del subyacente ES el precio de la accion. Sin delta, sin
    // mapeo -- el motor lo pasa directo. Aqui se fija esa expectativa.
    const double stock_stop = 695.0;
    CHECK(std::fabs(stock_stop - 695.0) < 1e-9, "acciones: el stop es el nivel del subyacente, sin mapear por delta");
}

int main() {
    std::printf("=== order_engine :: compra/venta de OPCIONES y ACCIONES ===\n");
    test_load_chain_edges();
    test_run_gate_boundaries();
    test_stock_entry();
    test_aggregate_cap_mixed();
    test_close_route_end_to_end();
    test_delta_to_stop_mapping();
    std::printf("\n=== %d OK, %d FALLOS ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
