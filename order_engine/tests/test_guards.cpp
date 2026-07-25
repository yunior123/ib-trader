// test_guards.cpp — arnes de las guardas de DINERO del order_engine.
//
// Se compila SIN la API de IBKR y corre con el mercado cerrado: las decisiones
// que valen dinero son puras (order_engine/guards.h) precisamente para poder
// ejercitarlas un sabado. Cada caso lleva su TESTIGO del bug: se replica la
// logica VIEJA (la que estaba en linea en order_engine.cpp) y se comprueba que
// habria dicho SI donde la nueva dice NO. Sin testigo, un test no prueba que el
// agujero existia.
//
// Casos exigidos por Yunior (2026-07-25), uno por uno:
//   1. sobre-venta que voltearia a corto -> RECHAZADA
//   2. stop rechazado -> GRITA (+ cierra si no hay forma de proteger)
//   3. cap agregado alcanzado -> la SEGUNDA zona se rechaza AL ARMAR
//   4. allowlist con un id que es subcadena de otro -> RECHAZADO
//   5. reconnect con reconcile a medias -> NO arma
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include "../guards.h"

using namespace oe;

static int g_fail = 0, g_pass = 0;

#define CHECK(cond, what)                                                        \
    do {                                                                         \
        if (cond) { ++g_pass; }                                                  \
        else { ++g_fail; std::printf("  FALLO %s:%d  %s\n", __FILE__, __LINE__, what); } \
    } while (0)

static void section(const char* s) { std::printf("\n== %s\n", s); }

// ---------------------------------------------------------------- TESTIGOS
// Logica VIEJA de la allowlist (order_engine.cpp:419 antes del fix).
static bool old_account_match(const std::string& managed_csv, const std::string& expected) {
    return managed_csv.find(expected) != std::string::npos;
}
// Logica VIEJA del clamp del stop de opcion (order_engine.cpp:875-881).
static double old_clamp_option_stop(double fill_px, double delta, double stop_und,
                                    double level_und, char close_side) {
    double opt_stop;
    if (std::fabs(delta) > 1e-6) opt_stop = fill_px + delta * (stop_und - level_und);
    else                         opt_stop = fill_px * 0.6;
    if (close_side == 'S') {
        opt_stop = std::min(opt_stop, fill_px * 0.95);
        opt_stop = std::max(opt_stop, std::max(0.01, fill_px * 0.10));
    } else {
        opt_stop = std::max(opt_stop, fill_px * 1.05);   // <- SIN cota superior
    }
    if (opt_stop < 0.01) opt_stop = 0.01;
    return opt_stop;
}

// ============================================================ #8 allowlist
static void test_allowlist_substring() {
    section("#8 allowlist de cuenta: subcadena NO es coincidencia");

    // El caso real: la cuenta viva es U26942420. Un id que la CONTIENE, o que
    // ESTA CONTENIDO en ella, pasaba el filtro viejo.
    CHECK(old_account_match("U269424201", "U26942420"), "testigo: find() aceptaba el superstring (bug vivo)");
    CHECK(!accounts_match("U269424201", "U26942420"), "fix: superstring RECHAZADO");

    CHECK(old_account_match("U26942420", "U2694242"), "testigo: find() aceptaba el prefijo (bug vivo)");
    CHECK(!accounts_match("U26942420", "U2694242"), "fix: prefijo RECHAZADO");

    // CSV real de managedAccounts: coincidencia exacta de un token SI pasa.
    CHECK(accounts_match("DUR197573,U26942420", "U26942420"), "token exacto en CSV aceptado");
    CHECK(accounts_match(" DUR197573 , U26942420 ", "U26942420"), "CSV con espacios: trim y acepta");
    CHECK(!accounts_match("DUR197573,U26942421", "U26942420"), "cuenta distinta rechazada");

    // Falla cerrado.
    CHECK(!accounts_match("", "U26942420"), "lista vacia -> rechazado");
    CHECK(!accounts_match("U26942420", ""), "expected vacio -> rechazado (falla cerrado)");
    CHECK(!accounts_match("", ""), "ambos vacios -> rechazado");

    // Tokenizador.
    CHECK(split_accounts("A,B,,C").size() == 3, "split ignora tokens vacios");
}

// ================================================== #1/#2 cap agregado
static void test_aggregate_cap() {
    section("#1/#2 tope de exposicion AGREGADA por cuenta");

    // Escenario del agujero: cap por zona $200; con 3 zonas de $200 el viejo
    // motor comprometia $600 sin que nada lo dijera.
    ExposureBook bk; bk.cap = 400.0;
    CHECK(bk.reserve("QQQ|z1", 200.0), "1a zona $200 dentro del cap $400");
    CHECK(bk.reserve("QQQ|z2", 200.0), "2a zona $200 llega justo al cap");
    CHECK(std::fabs(bk.total() - 400.0) < 1e-9, "total comprometido = $400");

    // CASO EXIGIDO: la zona que rebasa se rechaza AL ARMAR, no al ejecutar.
    CHECK(!bk.reserve("QQQ|z3", 200.0), "3a zona RECHAZADA: rebasaria el cap agregado");
    CHECK(bk.reserved("QQQ|z3") == 0.0, "la zona rechazada no queda contabilizada");
    CHECK(std::fabs(bk.total() - 400.0) < 1e-9, "el rechazo no altera el total");

    // Re-reservar la MISMA zona reemplaza (no suma dos veces).
    CHECK(bk.reserve("QQQ|z2", 150.0), "re-reserva de z2 mas barata pasa");
    CHECK(std::fabs(bk.total() - 350.0) < 1e-9, "reemplazo, no acumulacion");
    CHECK(bk.reserve("QQQ|z3", 50.0), "ahora si cabe una zona de $50");

    // Liberar deja sitio.
    bk.release("QQQ|z1");
    CHECK(std::fabs(bk.total() - 200.0) < 1e-9, "release descuenta");
    CHECK(bk.reserve("QQQ|z4", 200.0), "liberado el sitio, entra otra zona");

    // qty>1 (agujero #2): el desembolso que se reserva es qty*prima, no la prima.
    ExposureBook bk2; bk2.cap = 1000.0;
    const double prima = 180.0;
    CHECK(!bk2.reserve("NVDA|z1", 6 * prima), "qty=6 x $180 = $1080 > cap $1000 -> RECHAZADO");
    CHECK(bk2.reserve("NVDA|z1", 5 * prima), "qty=5 x $180 = $900 cabe");

    // Acciones y opciones comparten el mismo bolsillo.
    ExposureBook bk3; bk3.cap = 3000.0;
    CHECK(bk3.reserve("MU|zstk", 2900.0), "notional de acciones $2900 cabe");
    CHECK(!bk3.reserve("QQQ|zopt", 200.0), "una opcion de $200 encima ya NO cabe");

    // Falla cerrado: sin cap, o con desembolso desconocido, nada pasa.
    ExposureBook nocap;
    CHECK(!nocap.reserve("X|z", 1.0), "cap=0 -> ninguna reserva pasa (falla cerrado)");
    ExposureBook bk4; bk4.cap = 500;
    CHECK(!bk4.reserve("X|z", 0.0), "desembolso 0 (desconocido) -> RECHAZADO, no 'gratis'");
    CHECK(!bk4.reserve("X|z", -10.0), "desembolso negativo -> RECHAZADO");
}

// ===================================== #3/#7 close contra la posicion REAL
static void test_close_against_real_position() {
    section("#3/#7 close: clamp contra la posicion REAL (TFSA no shortea)");

    PositionBook pb;
    // Antes de reconciliar con reqPositions NO se sabe nada -> se rechaza.
    const PosKey k = pos_key_option("QQQ", "20260815", 560, "C");
    CloseDecision d0 = decide_close_qty(pb, k, 1, 'S');
    CHECK(!d0.ok, "sin reqPositions completado -> close RECHAZADO (no se adivina)");
    CHECK(d0.qty == 0, "y la cantidad autorizada es 0, no un default plausible");

    pb.begin();
    pb.set(k, 2);                       // 2 contratos LARGOS de verdad
    pb.set(pos_key_stock("MU"), 40);    // 40 acciones largas
    pb.end();

    // CASO EXIGIDO: el panel manda cqty=5 con solo 2 en cartera.
    CloseDecision d1 = decide_close_qty(pb, k, 5, 'S');
    CHECK(d1.ok, "hay 2 largos: se autoriza cerrar");
    CHECK(d1.qty == 2, "CLAMP a 2 (vender 5 dejaria -3 = CORTO en TFSA)");
    CHECK(d1.clamped, "el exceso se marca para gritarlo");

    // Cierre exacto y parcial: intactos.
    CHECK(decide_close_qty(pb, k, 2, 'S').qty == 2 && !decide_close_qty(pb, k, 2, 'S').clamped,
          "cierre exacto pasa sin clamp");
    CHECK(decide_close_qty(pb, k, 1, 'S').qty == 1, "cierre parcial de 1 pasa");

    // Sin posicion: vender abriria un corto -> RECHAZO TOTAL, no clamp a 0 mudo.
    const PosKey vacio = pos_key_option("QQQ", "20260815", 600, "P");
    CloseDecision d2 = decide_close_qty(pb, vacio, 1, 'S');
    CHECK(!d2.ok, "sin posicion: vender RECHAZADO (abriria corto)");
    CHECK(d2.reason.find("ABRIRIA un corto") != std::string::npos, "la razon lo dice en voz alta");

    // Doble close en ratsaga: tras cerrar 2, la posicion es 0 -> el segundo se rechaza.
    PositionBook pb2; pb2.begin(); pb2.set(k, 0); pb2.end();
    CHECK(!decide_close_qty(pb2, k, 2, 'S').ok, "posicion ya plana -> segundo close RECHAZADO");

    // Buy-to-close solo con posicion CORTA; con largo abriria mas largo.
    CHECK(!decide_close_qty(pb, k, 1, 'B').ok, "buy-to-close sobre un LARGO rechazado");
    PositionBook pbs; pbs.begin(); pbs.set(k, -3); pbs.end();
    CloseDecision d3 = decide_close_qty(pbs, k, 5, 'B');
    CHECK(d3.ok && d3.qty == 3 && d3.clamped, "corto de 3: buy-to-close clampa a 3");
    CHECK(!decide_close_qty(pbs, k, 1, 'S').ok, "vender sobre un CORTO rechazado (lo agrandaria)");

    // Acciones por la misma puerta.
    CloseDecision d4 = decide_close_qty(pb, pos_key_stock("MU"), 100, 'S');
    CHECK(d4.ok && d4.qty == 40 && d4.clamped, "acciones: 100 pedidas, 40 reales -> clamp 40");

    // Basura del panel.
    CHECK(!decide_close_qty(pb, k, 0, 'S').ok, "qty 0 rechazada");
    CHECK(!decide_close_qty(pb, k, -1, 'S').ok, "qty negativa rechazada");
    CHECK(!decide_close_qty(pb, k, 1, 'X').ok, "side invalido rechazado");

    // La clave discrimina contrato: mismo sym, otro strike/expiry/right = otra cosa.
    CHECK(!decide_close_qty(pb, pos_key_option("QQQ", "20260815", 560, "P"), 1, 'S').ok,
          "el PUT del mismo strike no es el CALL en cartera");
    CHECK(!decide_close_qty(pb, pos_key_option("QQQ", "20260919", 560, "C"), 1, 'S').ok,
          "otra expiry no es la misma posicion");
}

// ============================================ #9 clamp simetrico del stop
static void test_option_stop_clamp_symmetry() {
    section("#9 clamp del stop de opcion: simetrico en los dos lados");

    const double fill = 2.00;
    // Delta sano, largo: el stop cae bajo el fill.
    const double s1 = clamp_option_stop(fill, 0.50, 199.0, 200.0, 'S');
    CHECK(s1 < fill && s1 > 0, "largo con delta sano: stop bajo el fill");

    // Delta absurdo hacia arriba en un LARGO: techo fill*0.95 (ya existia).
    CHECK(clamp_option_stop(fill, 5.0, 210.0, 200.0, 'S') <= fill * 0.95 + 1e-9,
          "largo: techo 0.95*fill");
    CHECK(clamp_option_stop(fill, 5.0, 150.0, 200.0, 'S') >= 0.20 - 1e-9,
          "largo: suelo 0.10*fill (no dispara al instante)");

    // EL AGUJERO: en un CORTO el clamp viejo no tenia cota superior.
    const double viejo = old_clamp_option_stop(fill, 0.50, 400.0, 200.0, 'B');
    CHECK(viejo > fill * 10, "testigo: el corto quedaba en el infinito (102.0) = sin proteccion");
    const double nuevo = clamp_option_stop(fill, 0.50, 400.0, 200.0, 'B');
    CHECK(nuevo <= fill * 2.50 + 1e-9, "fix: corto topado a 2.50*fill");
    CHECK(nuevo >= fill * 1.05 - 1e-9, "corto: suelo 1.05*fill se conserva");

    // Fallback sin delta: cada lado a su sitio, no el 0.6 de ambos.
    CHECK(clamp_option_stop(fill, 0.0, 190.0, 200.0, 'S') <= fill * 0.95 + 1e-9,
          "largo sin delta: fallback bajo el fill");
    const double fb_short = clamp_option_stop(fill, 0.0, 210.0, 200.0, 'B');
    CHECK(fb_short >= fill * 1.05 - 1e-9 && fb_short <= fill * 2.50 + 1e-9,
          "corto sin delta: fallback DENTRO de la banda");

    // Nunca por debajo del tick minimo.
    CHECK(clamp_option_stop(0.02, -3.0, 300.0, 200.0, 'S') >= 0.01, "jamas < 0.01");
    // Prima ridicula: el suelo no puede quedar por encima del techo.
    const double tiny = clamp_option_stop(0.05, 0.5, 100.0, 200.0, 'S');
    CHECK(tiny >= 0.01 && tiny <= 0.05 * 0.95 + 1e-9, "prima minima: suelo no invade el techo");
}

// ============================================ #5 stop rechazado -> grita
static void test_naked_stop_shouts() {
    section("#5 stop nativo rechazado: GRITA siempre, y cierra si no hay proteccion");

    NakedDecision d0 = decide_stop_failure(0, 3, true);
    CHECK(d0.action == NakedAction::RETRY, "1er rechazo: re-armar");
    CHECK(d0.shout, "y AVISA (antes era silencio: REJECTED solo se miraba en la entrada)");

    CHECK(decide_stop_failure(2, 3, true).action == NakedAction::RETRY, "3er intento aun re-arma");

    NakedDecision d3 = decide_stop_failure(3, 3, true);
    CHECK(d3.action == NakedAction::DEGRADE_LOCAL, "agotados los re-armes: watch-local");
    CHECK(d3.shout, "degradar tambien GRITA");

    // CASO EXIGIDO: sin forma de vigilar local, la posicion desnuda se CIERRA.
    NakedDecision d4 = decide_stop_failure(3, 3, false);
    CHECK(d4.action == NakedAction::EMERGENCY_CLOSE, "sin dato para watch-local -> CIERRO la posicion");
    CHECK(d4.shout, "y grita");
    CHECK(d4.msg.find("CIERRO") != std::string::npos, "el mensaje dice lo que va a pasar");

    // Ningun camino es mudo.
    for (int r = 0; r <= 5; ++r)
        for (int loc = 0; loc < 2; ++loc)
            CHECK(decide_stop_failure(r, 3, loc != 0).shout, "ninguna rama del fallo de stop es silenciosa");
}

// ====================================== #6 reconnect con reconcile a medias
static void test_reconnect_gate() {
    section("#6 reconnect: sin reconcile Y posiciones no se toca nada");

    CHECK(!safe_to_touch_orders(false, false), "reconnect a medias: NO arma");
    CHECK(!safe_to_touch_orders(true, false), "ordenes ok pero posiciones desconocidas: NO arma");
    CHECK(!safe_to_touch_orders(false, true), "posiciones ok pero openOrderEnd ausente: NO arma");
    CHECK(safe_to_touch_orders(true, true), "ambas verdades del broker -> se puede armar");
}

// ====================================== #4 el stop GTC HUERFANO
// TESTIGO de la logica VIEJA: el `close` del panel (order_engine.cpp accion
// "close") mandaba la orden opuesta y NO cancelaba nada. Se replica como una
// funcion que siempre devuelve "no hay nada que cancelar".
static int old_close_cancels_nothing() { return 0; }

static void test_orphan_stop_on_close() {
    section("#4 close deja el stop nativo huerfano (GTC residual)");

    // Libro realista: dos zonas de QQQ con stop vivo en contratos DISTINTOS,
    // una accion, y una zona sin stop.
    std::vector<StopRef> libro = {
        {"z1", "opt", "20260731", 700.0, 'C', 4001, 2.0},
        {"z2", "opt", "20260731", 705.0, 'C', 4002, 1.0},
        {"z3", "opt", "20260731", 700.0, 'C',   -1, 1.0},   // sin stop vivo
        {"z4", "stk", "",           0.0,   0, 4004, 100.0},
    };

    // (a) cerrar QQQ 700C entero -> cancela SOLO el stop de z1
    CloseReq c_total; c_total.is_opt = true; c_total.exp = "20260731";
    c_total.strike = 700.0; c_total.right = 'C'; c_total.qty = 2;
    auto r = stops_orphaned_by_close(c_total, libro);
    CHECK(r.size() == 1, "close de 700C cancela exactamente un stop");
    CHECK(r.size() == 1 && r[0].stop_id == 4001, "cancela el stop de SU contrato (z1)");
    CHECK(r.size() == 1 && !r[0].partial, "close que cubre todo no es parcial");
    // EL TESTIGO: la logica vieja no cancelaba NADA -> el 4001 quedaba GTC vivo.
    CHECK(old_close_cancels_nothing() == 0 && r.size() > 0,
          "TESTIGO: antes quedaba un stop GTC huerfano; ahora se cancela");

    // (b) el stop del contrato VECINO no se toca: cancelarlo dejaria desnuda una
    //     posicion que nadie pidio cerrar.
    for (const auto& oc : r) CHECK(oc.stop_id != 4002, "no toca el stop de 705C");
    for (const auto& oc : r) CHECK(oc.stop_id != 4004, "no toca el stop de la accion");

    // (c) fill PARCIAL: se cancela igual (un stop por MAS cantidad de la que
    //     quedara voltearia a corto al dispararse) y se marca para RE-ARMAR.
    CloseReq c_parc = c_total; c_parc.qty = 1;      // hay 2, se cierra 1
    auto rp = stops_orphaned_by_close(c_parc, libro);
    CHECK(rp.size() == 1 && rp[0].partial,
          "close parcial cancela Y marca que hay que re-armar el remanente");

    // (d) una zona sin stop vivo no genera cancelacion fantasma
    std::vector<StopRef> solo_sin_stop = {{"z3", "opt", "20260731", 700.0, 'C', -1, 1.0}};
    CHECK(stops_orphaned_by_close(c_total, solo_sin_stop).empty(),
          "sin stop vivo no se inventa una cancelacion");

    // (e) opcion vs accion no se cruzan nunca
    CloseReq c_stk; c_stk.is_opt = false; c_stk.qty = 100;
    auto rs = stops_orphaned_by_close(c_stk, libro);
    CHECK(rs.size() == 1 && rs[0].stop_id == 4004, "close de accion solo toca el stop de accion");

    // (f) mismo strike, expiry distinta -> NO es el mismo contrato
    CloseReq c_otra_exp = c_total; c_otra_exp.exp = "20260807";
    CHECK(stops_orphaned_by_close(c_otra_exp, libro).empty(),
          "misma cifra de strike con otra expiry no es el mismo contrato");

    // (g) mismo strike y expiry, derecho contrario -> NO es el mismo contrato
    CloseReq c_put = c_total; c_put.right = 'P';
    CHECK(stops_orphaned_by_close(c_put, libro).empty(),
          "un put no huerfana el stop de un call");

    // (h) ningun mensaje es silencioso: todo lo que se cancela se puede narrar
    for (const auto& oc : r) CHECK(!oc.msg.empty(), "toda cancelacion lleva su motivo");
}

int main() {
    std::printf("=== order_engine :: guardas de dinero ===\n");
    test_allowlist_substring();
    test_aggregate_cap();
    test_close_against_real_position();
    test_option_stop_clamp_symmetry();
    test_naked_stop_shouts();
    test_reconnect_gate();
    test_orphan_stop_on_close();
    std::printf("\n=== %d OK, %d FALLOS ===\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
