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
// # ESTADO DE CABLEADO (2026-07-25) — LEER ANTES DE DAR NADA POR CERRADO
// #
// # Que una guarda VIVA aqui y tenga test NO significa que el motor la use.
// # Ahora mismo order_engine.cpp solo llama a UNA:
// #
// #   CABLEADA Y COMPILANDO:
// #     #8 accounts_match  -> order_engine.cpp (verificacion de cuenta al
// #        conectar). Sustituye al find() por subcadena. El agujero (d) del
// #        encargo esta CERRADO en codigo, pero solo VERIFICADO EN FRIO:
// #        compila y sus 82 checks pasan; la ruta real necesita un Gateway
// #        logueado -> PENDIENTE DE PAPER EL DOMINGO.
// #
// #   ESCRITAS Y PROBADAS PERO **NO CABLEADAS** (el motor sigue con su logica
// #   vieja en linea; los agujeros siguen ABIERTOS en produccion):
// #     #1/#2 ExposureBook       - tope AGREGADO por cuenta
// #     #3/#7 decide_close_qty   - close contra la posicion REAL (no voltear
// #                                a corto). Agujero (b) del encargo: ABIERTO.
// #     #5    decide_stop_failure- stop nativo rechazado = fallo de proteccion
// #                                que GRITA. Agujero (c) del encargo: ABIERTO.
// #     #6    safe_to_touch_orders- no tocar ordenes sin reconcile completo
// #     #9    clamp_option_stop  - clamp simetrico del stop de opcion
// #
// #   NI ESCRITA NI CABLEADA:
// #     el agujero (a) del encargo — `close` no cancela el stop nativo, que
// #     queda GTC HUERFANO. Es la causa documentada del desastre que motivo la
// #     ley SEÑAL-SOLAMENTE, y es el mas grave de los cuatro. Sigue ABIERTO.
// #
// # No se cablearon las demas a proposito: tocan el camino de orden de un
// # motor de ~970 lineas y no hay forma de validarlas sin fills, con TWS
// # apagado un sabado. Cablearlas a ciegas es exactamente como se pierde
// # dinero. Cada una necesita su pasada de paper antes de considerarse viva.
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

}  // namespace oe
