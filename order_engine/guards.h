// guards.h — DECISIONES de seguridad del order_engine, puras y testeables.
//
// POR QUE EXISTE: las guardas que valen dinero estaban EN LINEA dentro del
// main() de order_engine.cpp (972 lineas) y por tanto no se podian ejercitar sin
// TWS delante. Sin test, una guarda es una opinion. Aqui viven como funciones
// puras (cero IO, cero IBKR, cero red) para que order_engine/tests las conduzca
// con mercado cerrado, y el motor las LLAMA en vez de re-implementarlas.
//
// REGLA DE LA CASA: en camino de ejecucion un error NO devuelve un numero
// plausible. Cada decision devuelve un veredicto EXPLICITO (ok + razon), nunca
// un 0/0.5 que el llamante confunda con "adelante".
//
// ############################################################################
// # ESTADO DE CABLEADO (actualizado 2026-07-26, encargo de los 4 defectos)
// #
// # Que una guarda VIVA aqui y tenga test NO significa que el motor la use.
// #
// #   CABLEADA Y COMPILANDO (release + ASan/UBSan, order_engine/build.sh):
// #     #8 accounts_match  -> verificacion de cuenta al conectar.
// #     #4 stops_orphaned_by_close -> accion "close" del panel: el stop
// #        nativo se cancela ANTES de mandar el close.
// #     #9 clamp_option_stop -> vive DENTRO de option_stop_trigger (#10) que
// #        el motor llama al armar el stop tras un FILL (order_engine.cpp,
// #        bloque "tras FILL: armar stop").
// #     #10 option_greeks_known/option_stop_trigger -> defecto 1 del encargo
// #        2026-07-25 (el centinela -1.0000 usado como delta real). Cablea
// #        AL MISMO SITIO que #9. ZoneRT guarda entry_iv junto a entry_delta
// #        para que el motor sepa distinguir "no se" de "delta real" en el
// #        momento de calcular el stop.
// #     #11 advance_cross_counter -> defecto 4 del encargo 2026-07-25 (el
// #        stop watch-local contaba iteraciones del bucle, no barras). Se usa
// #        en LAS DOS ramas de print-o-nada (entrada Y stop-local).
// #     #3/#7 decide_close_qty/PositionBook -> defecto 3 del encargo
// #        2026-07-25 ("close" sin gate de tamaño). PositionBook se llena
// #        desde tws.reqPositions()/position()/positionEnd() (tws_adapter.h),
// #        NUNCA desde el estado local en RAM. decide_close_qty gatea "cmd
// #        close" ANTES de tocar armed_live/precio.
// #
// #   VERIFICADO EN FRIO (compila 0 warnings + ASan/UBSan limpio + tests
// #   unitarios pasan); la ruta REAL (fills, posiciones reportadas por un
// #   Gateway logueado) sigue PENDIENTE DE PAPER — no hay forma de probarla
// #   sin TWS delante. Cada guarda de arriba necesita su pasada de paper
// #   antes de considerarse viva en produccion.
// #
// #     #1/#2 ExposureBook -> tope AGREGADO por cuenta (--account-cap, default
// #        $3000). Se RESERVA el desembolso real antes de colocar (las dos
// #        ramas: opciones y acciones) y se LIBERA en cada rama terminal sin
// #        posicion (REJECTED/CANCELED/STOP_HIT/DRY/zona borrada sin llenar).
// #        Nota: un `cmd close` del panel NO libera (su orderId no entra en
// #        oid2zone) -> la reserva sobrevive al cierre. Es un sesgo
// #        CONSERVADOR a proposito: sobra-reservar veta de mas, nunca de menos.
// #     #5 decide_stop_failure -> watchdog del stop no confirmado. Los TRES
// #        desenlaces gritan (stderr + ledger + state/NAKED_STOP.jsonl); el
// #        tercero (sin stop nativo Y sin spot para vigilar local) CIERRA la
// #        posicion en vez de dejarla desnuda en silencio.
// #     #6 safe_to_touch_orders -> gatea el bloque de adopcion/re-arme de stops
// #        del RECONNECT. El arranque ya abortaba sin reconcile; el reconnect
// #        pasaba directo y podia colocar un SEGUNDO stop sobre la misma
// #        posicion. Ahora exige openOrderEnd Y positionEnd o no toca nada.
// #     #12 decide_stock_entry -> rama de ACCIONES del TRIGGERED (sizing +
// #        limite marketable). Cierra el limite redondeado a 0.00 y mide el
// #        notional al LIMITE que se paga, no al spot.
// #
// #   ESCRITAS Y PROBADAS PERO **NO CABLEADAS**: ninguna. (2026-07-26)
// #
// # AVISO QUE SIGUE EN PIE: todo lo de arriba esta verificado EN FRIO. Ninguna
// # de estas guardas ha visto un fill real todavia -- no hubo Gateway levantado
// # (4001/4002/7496/7497 cerrados el 2026-07-26). La pasada de PAPER sigue
// # siendo obligatoria antes de considerarlas vivas en produccion.
// ############################################################################
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <map>
#include <string>
#include <vector>

namespace oe {

// ===================================================================== #8
// Allowlist de cuenta: `managedAccounts` llega como CSV ("DU123,DU456").
// El motor comparaba con find() -> coincidencia por SUBCADENA: la cuenta
// esperada "U2694242" pasaba el filtro contra un broker logueado en
// "U26942420" (y viceversa). Eso es apuntar dinero real a otra cuenta.
// Aqui: tokenizar por coma, trim, comparacion EXACTA.
inline std::string g_trim(const std::string& s) {
    const auto a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    const auto b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

inline std::vector<std::string> split_accounts(const std::string& csv) {
    std::vector<std::string> out;
    std::string cur;
    for (char c : csv) {
        if (c == ',') { const std::string t = g_trim(cur); if (!t.empty()) out.push_back(t); cur.clear(); }
        else cur += c;
    }
    const std::string t = g_trim(cur);
    if (!t.empty()) out.push_back(t);
    return out;
}

// true SOLO si `expected` es uno de los tokens exactos de la lista del broker.
// Lista vacia o expected vacio -> false (FALLA CERRADO).
inline bool accounts_match(const std::string& managed_csv, const std::string& expected) {
    const std::string want = g_trim(expected);
    if (want.empty()) return false;
    for (const auto& a : split_accounts(managed_csv)) if (a == want) return true;
    return false;
}

enum class DisarmAction { IGNORE, CANCEL_ENTRY, KEEP_PROTECTIVE_STOP };

inline DisarmAction disarm_action(bool ours, bool live, bool native_stop) {
    if (!ours || !live) return DisarmAction::IGNORE;
    return native_stop ? DisarmAction::KEEP_PROTECTIVE_STOP : DisarmAction::CANCEL_ENTRY;
}

// ===================================================================== #1/#2
// Tope de exposicion AGREGADA por cuenta. Los topes viejos eran POR ZONA
// (prima <= $200 / notional <= $3000) y POR ORDEN (qty*prima). N zonas armadas
// multiplicaban el desembolso sin techo global: 20 zonas de $200 = $4.000
// comprometidos sin que ninguna guarda dijera nada.
//
// Contabilidad: dolares COMPROMETIDOS por zona (qty*prima*100 en opciones,
// qty*spot en acciones). Se reserva ANTES de colocar y se libera cuando la zona
// llega a un estado terminal sin posicion. Re-reservar la misma clave REEMPLAZA
// (una zona no se cuenta dos veces).
struct ExposureBook {
    double cap = 0;                              // 0 -> ninguna reserva pasa (falla cerrado)
    std::map<std::string, double> committed;     // clave estable por zona -> dolares

    double total() const {
        double t = 0;
        for (const auto& [k, v] : committed) t += v;
        return t;
    }
    // Total si la clave `key` pasara a valer `amount` (reemplazo, no suma).
    double total_with(const std::string& key, double amount) const {
        double t = amount;
        for (const auto& [k, v] : committed) if (k != key) t += v;
        return t;
    }
    bool would_exceed(const std::string& key, double amount) const {
        if (!(cap > 0)) return true;             // sin cap configurado -> no se opera
        if (!(amount > 0)) return true;          // desembolso desconocido -> no se opera
        return total_with(key, amount) > cap + 1e-9;
    }
    // Reserva. false = RECHAZADO (el llamante debe VETAR la zona, no ejecutar).
    bool reserve(const std::string& key, double amount) {
        if (would_exceed(key, amount)) return false;
        committed[key] = amount;
        return true;
    }
    void release(const std::string& key) { committed.erase(key); }
    double reserved(const std::string& key) const {
        const auto it = committed.find(key);
        return it == committed.end() ? 0.0 : it->second;
    }
};

// Clave estable de una zona en el libro de exposicion. sym+zona: dos zonas del
// mismo simbolo son dos desembolsos distintos, la misma zona re-armada es uno.
inline std::string exposure_key(const std::string& sym, const std::string& zone_id) {
    return sym + "|" + zone_id;
}

// ===================================================================== #12
// ENTRADA DE ACCIONES. Vivia EN LINEA en order_engine.cpp (el bloque "ACCIONES"
// del TRIGGERED) y por eso el unico camino de orden de ACCIONES no tenia ni un
// test, pese a que las acciones son las que SI llenan 24/5 y por tanto las que
// mas se ejercitan en paper. Dos agujeros que cierra al hacerse pura:
//
//  (a) LIMITE REDONDEADO A CERO. `lim = round(spot*1.001*100)/100` con un spot
//      sub-centavo (SPCX/DRAM han cotizado por debajo de $0.01 en premarket)
//      da 0.00 y la orden sale a precio CERO. El gate viejo solo miraba
//      `spot <= 0`, no el limite ya redondeado.
//  (b) NOTIONAL MEDIDO AL SPOT, NO AL LIMITE. Se comprometia `qty*spot` pero se
//      paga `qty*limit` (limit = spot*1.001 en la compra). Con el notional justo
//      en el tope se rebasaba el presupuesto por la diferencia. El desembolso
//      que se reserva debe ser el que de verdad se paga.
struct StockEntry {
    bool ok = false;
    double limit = 0;        // marketable, ya redondeado al centavo
    double notional = 0;     // desembolso REAL = qty * limit
    std::string reason;
};

inline StockEntry decide_stock_entry(double spot, int qty, double budget, char side) {
    StockEntry d;
    if (!(spot > 0))            { d.reason = "spot desconocido o <= 0: no se inventa un precio"; return d; }
    if (qty <= 0)               { d.reason = "qty <= 0"; return d; }
    if (side != 'B' && side != 'S') { d.reason = "side invalido"; return d; }
    if (!(budget > 0))          { d.reason = "sin presupuesto de acciones configurado (falla cerrado)"; return d; }
    double lim = (side == 'B') ? spot * 1.001 : spot * 0.999;
    lim = std::round(lim * 100.0) / 100.0;
    if (!(lim > 0)) { d.reason = "limite redondeado a 0.00 (spot sub-centavo): NO se manda a precio cero"; return d; }
    const double notional = (double)qty * lim;
    if (notional > budget + 1e-9) {
        char b[128];
        std::snprintf(b, sizeof b, "notional $%.2f (%d x $%.2f) > budget $%.2f", notional, qty, lim, budget);
        d.reason = b;
        return d;
    }
    d.ok = true; d.limit = lim; d.notional = notional; d.reason = "ok";
    return d;
}

// ===================================================================== #3/#7
// Fuente de verdad de POSICIONES = la cuenta IBKR remota (reqPositions), no el
// estado local en RAM. `ready` solo pasa a true cuando llego positionEnd().
// Mientras no este ready, TODA decision que dependa de la posicion se RECHAZA.
struct PosKey {
    std::string sym, exp, right;                 // right: "" acciones, "C"/"P" opciones
    double strike = 0;
    bool operator<(const PosKey& o) const {
        if (sym != o.sym) return sym < o.sym;
        if (exp != o.exp) return exp < o.exp;
        if (right != o.right) return right < o.right;
        return strike < o.strike - 1e-9;
    }
};

inline PosKey pos_key_stock(const std::string& sym) { return PosKey{sym, "", "", 0}; }
inline PosKey pos_key_option(const std::string& sym, const std::string& exp,
                             double strike, const std::string& right) {
    return PosKey{sym, exp, right, strike};
}

struct PositionBook {
    bool ready = false;                          // positionEnd() visto
    std::map<PosKey, double> qty;                // firmada: >0 largo, <0 corto

    void begin() { ready = false; qty.clear(); }
    void set(const PosKey& k, double q) {
        if (std::fabs(q) < 1e-9) qty.erase(k); else qty[k] = q;
    }
    void end() { ready = true; }
    bool known() const { return ready; }
    // Valido SOLO si known(). Ausente = plano de verdad (IBKR lista todo lo abierto).
    double qty_of(const PosKey& k) const {
        const auto it = qty.find(k);
        return it == qty.end() ? 0.0 : it->second;
    }
};

// Veredicto de un cierre pedido por el panel.
struct CloseDecision {
    bool ok = false;
    int  qty = 0;              // cantidad AUTORIZADA (nunca > |posicion|)
    bool clamped = false;      // se pidio mas de lo que hay -> exceso rechazado
    std::string reason;
};

// side 'S' = vender para cerrar un LARGO. side 'B' = comprar para cerrar un CORTO.
// TFSA U26942420 NO shortea: vender mas de lo que se tiene volteria a corto ->
// se RECHAZA el exceso, jamas se manda.
inline CloseDecision decide_close_qty(const PositionBook& pb, const PosKey& k,
                                      int requested, char side) {
    CloseDecision d;
    if (!pb.known()) { d.reason = "posiciones NO reconciliadas con el broker (reqPositions pendiente)"; return d; }
    if (requested <= 0) { d.reason = "qty pedida <= 0"; return d; }
    if (side != 'B' && side != 'S') { d.reason = "side invalido"; return d; }
    const double pos = pb.qty_of(k);
    const double avail = (side == 'S') ? pos : -pos;    // cantidad cerrable en ese lado
    if (avail <= 1e-9) {
        d.reason = (side == 'S')
            ? "no hay posicion LARGA (" + std::to_string(pos) + "): vender ABRIRIA un corto"
            : "no hay posicion CORTA (" + std::to_string(pos) + "): comprar ABRIRIA un largo";
        return d;
    }
    const int cap_qty = (int)std::floor(avail + 1e-9);
    d.qty = std::min(requested, cap_qty);
    d.clamped = (requested > cap_qty);
    d.ok = d.qty > 0;
    if (d.clamped)
        d.reason = "CLAMP: pedidos " + std::to_string(requested) + " pero la posicion real es " +
                   std::to_string(cap_qty) + " -> el exceso se RECHAZA (evita flip a corto)";
    else
        d.reason = "ok";
    return d;
}

// ===================================================================== #9
// Clamp SIMETRICO del stop de una opcion. El nivel del SUBYACENTE se mapea a
// precio de la OPCION por delta; un delta malo podia poner el STP donde dispara
// al instante o donde NUNCA dispara. El caso largo (cierre 'S') tenia suelo y
// techo; el caso corto (cierre 'B') solo tenia suelo -> sin cota superior el
// stop de un corto podia quedar en el infinito = sin proteccion.
//   largo  (close 'S'): stop en [max(0.01, fill*0.10), fill*0.95]
//   corto  (close 'B'): stop en [fill*1.05, fill*2.50]  (perdida topada ~150%)
inline double clamp_option_stop(double fill_px, double delta, double stop_und,
                                double level_und, char close_side) {
    const bool long_pos = (close_side == 'S');
    double opt_stop;
    if (std::fabs(delta) > 1e-6) opt_stop = fill_px + delta * (stop_und - level_und);
    else                         opt_stop = long_pos ? fill_px * 0.60 : fill_px * 1.40;
    if (long_pos) {
        const double hi = fill_px * 0.95;
        const double lo = std::max(0.01, fill_px * 0.10);
        opt_stop = std::min(opt_stop, hi);
        opt_stop = std::max(opt_stop, std::min(lo, hi));
    } else {
        const double lo = fill_px * 1.05;
        const double hi = fill_px * 2.50;
        opt_stop = std::max(opt_stop, lo);
        opt_stop = std::min(opt_stop, std::max(hi, lo));
    }
    return std::max(0.01, opt_stop);
}

// ===================================================================== #5
// STOP nativo RECHAZADO = la posicion esta DESNUDA y hasta ahora nadie se
// enteraba (REJECTED solo se manejaba para la entrada; el watchdog degradaba a
// watch-local en silencio). Ahora: GRITA siempre (voz DANGER + bandera en disco
// que ve el healthcheck) y, si no hay forma de proteger, CIERRA la posicion.
enum class NakedAction { RETRY, DEGRADE_LOCAL, EMERGENCY_CLOSE };

struct NakedDecision {
    NakedAction action = NakedAction::RETRY;
    bool shout = true;                 // SIEMPRE: un stop caido nunca es silencioso
    std::string msg;
};

// retries = re-armes ya gastados. local_watch_possible = hay dato fresco del
// subyacente para vigilar el stop desde el motor.
inline NakedDecision decide_stop_failure(int retries, int max_retries, bool local_watch_possible) {
    NakedDecision d;
    if (retries < max_retries) {
        d.action = NakedAction::RETRY;
        d.msg = "stop nativo sin proteccion: re-armo (" + std::to_string(retries + 1) + "/" +
                std::to_string(max_retries) + ")";
        return d;
    }
    if (local_watch_possible) {
        d.action = NakedAction::DEGRADE_LOCAL;
        d.msg = "stop nativo IMPOSIBLE tras " + std::to_string(max_retries) +
                " intentos -> watch-local (el motor es la proteccion)";
        return d;
    }
    d.action = NakedAction::EMERGENCY_CLOSE;
    d.msg = "stop nativo IMPOSIBLE y sin dato para vigilar local -> CIERRO la posicion";
    return d;
}

// ===================================================================== #6
// Tras un reconnect el motor re-armaba stops sin comprobar que reconcile
// hubiera terminado (el arranque SI aborta, el reconnect no) -> podia colocar
// un SEGUNDO stop sobre la misma posicion o armar sobre un estado fantasma.
// Nada que toque ordenes puede correr sin AMBAS verdades del broker.
inline bool safe_to_touch_orders(bool orders_reconciled, bool positions_ready) {
    return orders_reconciled && positions_ready;
}

// ===================================================================== #10
// CENTINELA -1.0000 USADO COMO DELTA REAL — el mas grave de los 4 defectos
// del encargo 2026-07-25. scripts/opt_chain_cache.py escribe `nz(v, d=-1.0)`
// para iv Y delta cuando Ticker.modelGreeks es None (tipico FUERA de RTH).
// MEDIDO 2026-07-25: 100% de las filas de data/opt_chain_qqq.txt y
// opt_chain_nvda.txt, 1.475/1.500 (98,3%) agregado de la flota.
//
// order_engine.cpp (linea 918-919, version vieja) solo descartaba el 0
// EXACTO: `if (std::fabs(z.entry_delta) > 1e-6) opt_stop = fill + delta*...`.
// -1.0000 tiene magnitud 1.0 > 1e-6, asi que PASABA como delta real de un put
// profundo ITM -> invertia el signo del mapeo subyacente->prima. Los clamps
// de cordura de clamp_option_stop (#9, arriba) limitaban el daño pero no lo
// evitaban: con delta=-1 y un stop tipico por debajo del entry, el termino
// `delta*(stop_und-level_und)` se vuelve POSITIVO y grande -> clamp_option_stop
// lo topa al TECHO (fill*0.95 en largo) = stop nativo nace a -5% de la prima,
// stop-out casi instantaneo. El fallback honesto (fill*0.60) nunca se alcanza
// porque el guard `fabs(delta) > 1e-6` NO distingue "no se" de "se, y es -1".
//
// iv y delta salen del MISMO tk.modelGreeks en el escritor: si modelGreeks es
// None, AMBOS son el centinela. Por eso basta con mirar iv (siempre > 0 para
// un IV real -- nunca 0 ni negativo) para saber si el delta que lo acompaña
// es de fiar. Patron de la casa (~/CLAUDE.md): un `except`/valor-por-defecto
// SOLO puede devolver "no se" o levantar, jamas un numero plausible.
inline bool option_greeks_known(double iv) { return iv > 0.0; }

// Combina la deteccion del centinela con el clamp #9: delta desconocido -> se
// pasa 0.0 a clamp_option_stop, que YA sabe caer al fallback DECLARADO
// (0.60*fill largo / 1.40*fill corto via el `else` de clamp_option_stop),
// nunca al numero inventado del centinela.
inline double option_stop_trigger(double fill_px, double iv, double delta,
                                  double stop_und, double level_und, char close_side) {
    const double d = option_greeks_known(iv) ? delta : 0.0;
    return clamp_option_stop(fill_px, d, stop_und, level_und, close_side);
}

// ===================================================================== #11
// PRINT-O-NADA DEL STOP: BARRAS NUEVAS, NO ITERACIONES DEL BUCLE. El fix
// 2026-07-24 se aplico a la ENTRADA (order_engine.cpp:779, cross_cnt) pero NO
// a la rama del stop watch-local (:983): `z.s_cnt = cr ? z.s_cnt + 1 : 0`
// cuenta cada vuelta del bucle (~2s), asi que con el mismo epoch de barra
// repetido el stop-local disparaba un cierre marketable en ~4s -- la doctrina
// pide 2 LECTURAS CRUZANDO (2 barras nuevas), no 2 vueltas de pump().
// Funcion unica para ambas ramas (entrada y stop): epoch repetido no avanza
// el contador; epoch nuevo con `crossed`=false lo resetea a 0 igual que antes.
inline void advance_cross_counter(int& count, long long& last_epoch,
                                  bool crossed, long long bar_epoch) {
    if (!crossed) { count = 0; return; }
    if (bar_epoch != last_epoch) { ++count; last_epoch = bar_epoch; }
}

// Testigo de la logica VIEJA (order_engine.cpp:983 antes del fix): contaba
// iteraciones del bucle, ignorando el epoch de la barra por completo.
inline int old_advance_cross_counter_iterations(int prev_count, bool crossed) {
    return crossed ? prev_count + 1 : 0;
}

// ===================================================================== #4
// EL STOP HUERFANO — el agujero (a), el mas grave de los cuatro.
//
// El `close` del panel (order_engine.cpp, accion "close") manda una orden
// opuesta marketable y se va. El stop NATIVO que protegia esa posicion se queda
// VIVO en el servidor de IBKR. Al llenarse el close la posicion es 0, pero el
// stop sigue ahi como GTC: cuando el precio lo toque, ABRE una posicion nueva
// —y en el lado contrario— sin que nadie lo haya pedido.
//
// En la cuenta viva (TFSA U26942420) eso es peor que una perdida: la TFSA **no
// shortea**, asi que un stop de venta huerfano sobre una posicion ya cerrada
// intenta abrir un corto prohibido. Los GTC residuales son la causa DOCUMENTADA
// del desastre que motivo la ley SEÑAL-SOLAMENTE (~/CLAUDE.md, memoria
// ib-trader-signals-only-law).
//
// Esta funcion es pura y solo sabe DECIDIR. Cancelar es monotonicamente seguro:
// una cancelacion jamas abre una posicion, solo puede quitar proteccion — por
// eso el llamante debe, ademas de cancelar, dejar la zona lista para RE-ARMAR
// el stop del remanente (ver la nota de fill parcial abajo).
struct StopRef {
    std::string zone_id;
    std::string instrument = "opt";   // "opt" | "stk"
    std::string exp;                  // vacio en acciones
    double strike = 0;                // 0 en acciones
    char right = 0;                   // 'C' | 'P' | 0 en acciones
    int stop_id = -1;                 // orderId del stop nativo vivo
    double filled_qty = 0;            // lo que realmente se lleno en la entrada
};

struct CloseReq {
    bool is_opt = false;
    std::string exp;
    double strike = 0;
    char right = 0;
    int qty = 0;
};

struct OrphanCancel {
    int stop_id = -1;
    std::string zone_id;
    bool partial = false;   // el close no cubre toda la posicion -> hay que re-armar
    std::string msg;
};

// Empareja por IDENTIDAD DE CONTRATO. Un `close` de QQQ 700C no puede tocar el
// stop de QQQ 705C: cancelar el stop equivocado deja desnuda una posicion que
// nadie pidio cerrar. Por eso el emparejamiento es estricto y no "por simbolo".
inline bool same_contract(const CloseReq& c, const StopRef& s) {
    const bool s_is_opt = (s.instrument == "opt");
    if (c.is_opt != s_is_opt) return false;
    if (!c.is_opt) return true;              // acciones: el simbolo ya lo filtro el llamante
    if (c.right != s.right) return false;
    if (c.exp != s.exp) return false;
    // strikes en double: comparacion por tolerancia, jamas ==. Los strikes reales
    // van en pasos de 0.5/1.0, asi que 1e-6 distingue sin falsos positivos.
    const double d = c.strike - s.strike;
    return (d > -1e-6 && d < 1e-6);
}

// Fill PARCIAL: si el close cubre menos de lo que hay, el stop tampoco puede
// quedarse (protege mas cantidad de la que quedara: al dispararse venderia de
// mas y VOLTEARIA A CORTO, prohibido en TFSA). Se cancela igual y se marca
// `partial` para que el motor RE-ARME un stop por el remanente. Cancelar sin
// re-armar dejaria la posicion desnuda — por eso `partial` no es informativo,
// es una obligacion del llamante.
inline std::vector<OrphanCancel> stops_orphaned_by_close(
        const CloseReq& c, const std::vector<StopRef>& stops) {
    std::vector<OrphanCancel> out;
    for (const StopRef& s : stops) {
        if (s.stop_id < 0) continue;         // no hay stop vivo que huerfanar
        if (!same_contract(c, s)) continue;
        OrphanCancel oc;
        oc.stop_id = s.stop_id;
        oc.zone_id = s.zone_id;
        oc.partial = (c.qty > 0 && s.filled_qty > 0 && (double)c.qty < s.filled_qty);
        oc.msg = "stop huerfano id=" + std::to_string(s.stop_id) + " zona " + s.zone_id +
                 (oc.partial ? " (close PARCIAL: cancelo y hay que RE-ARMAR el remanente)"
                             : " (close total: cancelo)");
        out.push_back(oc);
    }
    return out;
}

}  // namespace oe
