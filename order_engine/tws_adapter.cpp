// tws_adapter.cpp — implementación del adaptador TWS. Ver tws_adapter.h.
#include "tws_adapter.h"

#include <cmath>
#include <cstdio>
#include <cstring>

namespace oe {

static const char* OE_PREFIX = "OE:";
static bool starts_with(const std::string& s, const char* p) {
    return s.rfind(p, 0) == 0;
}

// ---------------------------------------------------------------- conexión
bool TwsAdapter::connect(const char* host, int port, int clientId) {
    if (!client_->eConnect(host, port, clientId)) {
        std::fprintf(stderr, "[tws] eConnect FALLO host=%s port=%d id=%d\n", host, port, clientId);
        return false;
    }
    // Hilo lector: encola mensajes y señala; processMsgs() los despacha en pump().
    reader_ = std::make_unique<EReader>(client_.get(), &signal_);
    reader_->start();
    std::fprintf(stderr, "[tws] conectado host=%s port=%d clientId=%d — esperando nextValidId\n",
                 host, port, clientId);
    return true;
}

bool TwsAdapter::reconnect(const char* host, int port, int clientId) {
    // Socket muerto tras connectionClosed: cerrar limpio y re-conectar de cero.
    if (client_ && client_->isConnected()) client_->eDisconnect();
    reader_.reset();                       // el hilo lector viejo terminó con el socket
    connected_ = false; reconciled_ = false;
    if (!client_->eConnect(host, port, clientId)) {
        std::fprintf(stderr, "[tws] reconnect eConnect FALLO port=%d id=%d\n", port, clientId);
        return false;
    }
    reader_ = std::make_unique<EReader>(client_.get(), &signal_);
    reader_->start();
    std::fprintf(stderr, "[tws] RECONECTADO port=%d id=%d — esperando nextValidId; el motor re-reconcilia\n",
                 port, clientId);
    if (ledger_) ledger_->note("reconnect ok");
    return true;
}

void TwsAdapter::disconnect() {
    if (client_ && client_->isConnected()) client_->eDisconnect();
    connected_ = false;
}

void TwsAdapter::pump() {
    signal_.waitForSignal();       // bloquea hasta timeout (2s) o mensaje
    if (reader_) reader_->processMsgs();   // dispara callbacks EWrapper EN ESTE hilo
}

// ---------------------------------------------------------------- órdenes
void TwsAdapter::place_limit(Contract& c, char side, int qty, double limit,
                             int orderId, const std::string& orderRef, bool outsideRth) {
    Order o;
    o.action = (side == 'B') ? "BUY" : "SELL";
    o.orderType = "LMT";
    o.totalQuantity = DecimalFunctions::stringToDecimal(std::to_string(qty));
    o.lmtPrice = limit;
    o.tif = "DAY";                 // JAMÁS descansa overnight
    o.transmit = true;             // se coloca al PRINT, sin descansar previo
    o.outsideRth = outsideRth;     // acciones en horario extendido (24/5) -> true
    o.orderRef = orderRef;
    OpenOrd& rec = orders_[orderId];
    rec.c = c; rec.o = o; rec.ref = orderRef; rec.ours = starts_with(orderRef, OE_PREFIX);
    rec.live = true; rec.native_stop = false;
    if (ledger_) ledger_->intent(orderId, led_of(c), side, qty, limit, orderRef, "LIVE");
    client_->placeOrder(orderId, c, o);
    std::fprintf(stderr, "[tws] placeOrder LMT id=%d %s %dx %s %.4g%s @ %.2f ref=%s\n",
                 orderId, o.action.c_str(), qty, c.symbol.c_str(), c.strike, c.right.c_str(),
                 limit, orderRef.c_str());
}

void TwsAdapter::place_stop(Contract& c, char side, int qty, double stopPx,
                            int orderId, const std::string& orderRef, bool native) {
    if (!native) return;           // watch-local lo maneja el motor, no toca servidor
    Order o;
    o.action = (side == 'B') ? "BUY" : "SELL";
    o.orderType = "STP";
    o.totalQuantity = DecimalFunctions::stringToDecimal(std::to_string(qty));
    o.auxPrice = stopPx;           // precio de disparo (en términos de la OPCIÓN)
    o.tif = "GTC";                 // stop protectivo debe sobrevivir la sesión
    o.transmit = true;
    o.outsideRth = false;
    o.orderRef = orderRef;
    OpenOrd& rec = orders_[orderId];
    rec.c = c; rec.o = o; rec.ref = orderRef; rec.ours = starts_with(orderRef, OE_PREFIX);
    rec.live = true; rec.native_stop = true;
    if (ledger_) ledger_->intent(orderId, led_of(c), side, qty, stopPx, orderRef, "STOP-NATIVE");
    client_->placeOrder(orderId, c, o);
    std::fprintf(stderr, "[tws] placeOrder STP id=%d %s %dx %s stop@%.2f ref=%s (nativo)\n",
                 orderId, o.action.c_str(), qty, c.symbol.c_str(), stopPx, orderRef.c_str());
}

void TwsAdapter::cancel(int orderId) {
    auto it = orders_.find(orderId);
    std::string ref = (it != orders_.end()) ? it->second.ref : "";
    client_->cancelOrder(orderId, OrderCancel());
    if (ledger_) ledger_->cancel(orderId, ref);
    std::fprintf(stderr, "[tws] cancelOrder id=%d ref=%s\n", orderId, ref.c_str());
}

void TwsAdapter::modify(int orderId, double newLimit) {
    auto it = orders_.find(orderId);
    if (it == orders_.end()) {
        std::fprintf(stderr, "[tws] modify id=%d SIN registro — ignoro\n", orderId);
        return;
    }
    // AUDIT-FIX: el trigger de un STOP vive en auxPrice, NO en lmtPrice. Modificar el
    // campo correcto según el tipo, o mover el stop sería un no-op silencioso (dinero).
    Order& mo = it->second.o;
    if (mo.orderType == "STP") { mo.auxPrice = newLimit; }
    else if (mo.orderType == "STP LMT") { mo.auxPrice = newLimit; mo.lmtPrice = newLimit; }
    else { mo.lmtPrice = newLimit; }   // LMT normal
    if (ledger_)
        ledger_->intent(orderId, led_of(it->second.c),
                        it->second.o.action == "BUY" ? 'B' : 'S',
                        (int)DecimalFunctions::decimalToDouble(it->second.o.totalQuantity),
                        newLimit, it->second.ref, "MODIFY");
    client_->placeOrder(orderId, it->second.c, it->second.o);
    std::fprintf(stderr, "[tws] modify id=%d nuevo límite %.2f\n", orderId, newLimit);
}

void TwsAdapter::cancel_all_own() {
    // AUDIT-FIX (crítico): al desarmar se cancelan las ENTRADAS en vuelo (jamás deben
    // quedar residuales — desastre 2026-07-16), pero los STOPS protectivos se DEJAN
    // vivos: son la red de una posición REAL abierta; cancelarlos la deja desnuda.
    // Se reportan EN VOZ ALTA para que el humano sepa qué queda en el broker.
    int n = 0, kept = 0;
    for (auto& [id, rec] : orders_) {
        if (!rec.ours || !rec.live) continue;
        if (rec.native_stop) {
            ++kept;
            std::fprintf(stderr, "[tws] ⚠ QUEDA VIVO stop protectivo id=%d ref=%s (protege posición abierta)\n",
                         id, rec.ref.c_str());
            if (ledger_) ledger_->note("disarm: stop protectivo QUEDA VIVO id=" + std::to_string(id) + " ref=" + rec.ref);
            continue;
        }
        client_->cancelOrder(id, OrderCancel());
        if (ledger_) ledger_->cancel(id, rec.ref);
        rec.live = false;      // idempotente: no re-cancelar
        ++n;
    }
    if ((n || kept) && ledger_) ledger_->flush();
    std::fprintf(stderr, "[tws] cancel_all_own -> %d entradas canceladas, %d stops protectivos vivos\n", n, kept);
    if (kept) std::fprintf(stderr, "[tws] ⚠⚠ HAY %d STOP(S) EN EL BROKER: si cierras la posición a mano, CANCÉLALOS (scripts/cancel_all_bot_orders.py)\n", kept);
}

void TwsAdapter::reconcile() {
    reconciled_ = false;
    client_->reqAllOpenOrders();   // -> openOrder(...) por cada una, luego openOrderEnd()
    std::fprintf(stderr, "[tws] reqAllOpenOrders — reconciliando huérfanas OE:\n");
}

int TwsAdapter::live_own_count() const {
    int n = 0;
    for (auto& [id, rec] : orders_) if (rec.ours && rec.live) ++n;
    return n;
}

bool TwsAdapter::poll(ExecReport& out) {
    if (events_.empty()) return false;
    out = events_.front();
    events_.pop_front();
    return true;
}

void TwsAdapter::push(int id, ExecReport::K k, int px_c, const std::string& status, double qty) {
    events_.push_back(ExecReport{id, k, px_c, now_ms(), status, qty});
}

// ---------------------------------------------------------------- callbacks
void TwsAdapter::nextValidId(OrderId orderId) {
    if (next_id_ < (int)orderId) next_id_ = (int)orderId;
    connected_ = true;
    frozen_ = false;   // AUDIT-FIX: socket listo de nuevo -> descongelar (1102 no llega en reconnect de cliente)
    std::fprintf(stderr, "[tws] nextValidId=%ld -> listo para ordenar (descongelado)\n", (long)orderId);
}

void TwsAdapter::connectAck() {
    std::fprintf(stderr, "[tws] connectAck\n");
}

void TwsAdapter::managedAccounts(const std::string& accountsList) {
    account_ = accountsList;
    std::fprintf(stderr, "[tws] managedAccounts=%s\n", accountsList.c_str());
}

void TwsAdapter::orderStatus(OrderId orderId, const std::string& status, Decimal filled,
                             Decimal remaining, double avgFillPrice, int, int,
                             double, int, const std::string&, double) {
    double rem = DecimalFunctions::decimalToDouble(remaining);
    double fill_qty = DecimalFunctions::decimalToDouble(filled);
    int px_c = (int)llround(avgFillPrice * 100.0);
    if (status == "Filled" && rem <= 0.0) {
        auto it = orders_.find((int)orderId);
        if (it != orders_.end()) it->second.live = false;   // lleno: ya no cancelable
        push((int)orderId, ExecReport::FILL, px_c, status, fill_qty);
    } else if (status == "Cancelled" || status == "ApiCancelled" || status == "Inactive") {
        auto it = orders_.find((int)orderId);
        if (it != orders_.end()) it->second.live = false;
        // AUDIT-FIX: cancelado PERO con fill parcial -> tratar como FILL (proteger lo llenado).
        if (fill_qty > 0.0) push((int)orderId, ExecReport::FILL, px_c, "PartialThenCancel", fill_qty);
        else                push((int)orderId, ExecReport::CANCELED, 0, status);
    } else {
        // PreSubmitted / Submitted / PendingSubmit -> ACK
        if (ledger_) ledger_->ack((int)orderId, status);
        push((int)orderId, ExecReport::ACK, px_c, status);
    }
    (void)filled;
}

void TwsAdapter::openOrder(OrderId orderId, const Contract& c, const Order& o, const OrderState&) {
    // Reconciliación: adoptar y CANCELAR las órdenes "OE:" de un run anterior.
    bool ours = starts_with(o.orderRef, OE_PREFIX);
    if (ours) {
        OpenOrd& rec = orders_[(int)orderId];
        rec.c = c; rec.o = o; rec.ref = o.orderRef; rec.ours = true; rec.live = true;
        rec.native_stop = (o.orderType == "STP" || o.orderType == "STP LMT");
        if (rec.native_stop) {
            // AUDIT-FIX (crítico): un STOP huérfano PROTEGE una posición real que sigue
            // abierta. Cancelarlo la deja desnuda. Se ADOPTA (queda vivo) y se avisa.
            std::fprintf(stderr, "[tws] openOrder STOP huérfano OE: id=%ld ref=%s -> ADOPTO (protege posición, NO cancelo)\n",
                         (long)orderId, o.orderRef.c_str());
            if (ledger_) ledger_->note("adoptado stop huerfano id=" + std::to_string((int)orderId) + " ref=" + o.orderRef);
        } else {
            std::fprintf(stderr, "[tws] openOrder ENTRADA huérfana OE: id=%ld ref=%s -> cancelo\n",
                         (long)orderId, o.orderRef.c_str());
            client_->cancelOrder((int)orderId, OrderCancel());
            if (ledger_) ledger_->cancel((int)orderId, o.orderRef);
            rec.live = false;
        }
        if ((int)orderId >= next_id_) next_id_ = (int)orderId + 1;
    }
}

void TwsAdapter::openOrderEnd() {
    reconciled_ = true;
    std::fprintf(stderr, "[tws] openOrderEnd — reconciliación completa\n");
}

void TwsAdapter::execDetails(int, const Contract& contract, const Execution& e) {
    double qty = DecimalFunctions::decimalToDouble(e.shares);
    if (ledger_)
        ledger_->fill((int)e.orderId, e.execId,
                      LedgerContract{contract.symbol, contract.lastTradeDateOrContractMonth,
                                     contract.strike, contract.right},
                      e.price, qty, e.time);
    std::fprintf(stderr, "[tws] execDetails id=%ld execId=%s %.4f @ %.4f\n",
                 e.orderId, e.execId.c_str(), qty, e.price);
}

void TwsAdapter::commissionReport(const CommissionReport& cr) {
    if (ledger_) ledger_->commission(cr.execId, cr.commission, cr.realizedPNL);
    std::fprintf(stderr, "[tws] commissionReport execId=%s comm=%.4f realizedPnl=%.4f\n",
                 cr.execId.c_str(), cr.commission, cr.realizedPNL);
}

void TwsAdapter::error(int id, int errorCode, const std::string& msg, const std::string&) {
    switch (errorCode) {
        case 1100:   // conectividad TWS<->IB perdida
        case 502:    // no conecta (API off/puerto)
            frozen_ = true;
            std::fprintf(stderr, "[tws] ERROR %d: %s -> CONGELO entradas\n", errorCode, msg.c_str());
            if (ledger_) ledger_->note("frozen: error " + std::to_string(errorCode));
            break;
        case 1102:   // conectividad restaurada
            frozen_ = false;
            std::fprintf(stderr, "[tws] 1102 conectividad restaurada -> reanudo\n");
            if (ledger_) ledger_->note("resumed: 1102");
            break;
        case 201:    // orden rechazada (margen/permiso) — no reintentar ciego
            if (id >= 0) {
                auto it = orders_.find(id);
                if (it != orders_.end()) it->second.live = false;
                if (ledger_) ledger_->reject(id, errorCode, msg);
                push(id, ExecReport::REJECTED, 0, "Rejected");
            }
            std::fprintf(stderr, "[tws] ERROR 201 id=%d REJECT: %s\n", id, msg.c_str());
            break;
        case 202:    // confirmación de nuestro cancel
            std::fprintf(stderr, "[tws] 202 cancel confirmado id=%d\n", id);
            break;
        case 10147:  // orderId a cancelar no existe
        case 10148:  // ya cancelada
            if (id >= 0) {
                auto it = orders_.find(id);
                if (it != orders_.end()) it->second.live = false;
                push(id, ExecReport::CANCELED, 0, "AlreadyGone");
            }
            break;
        case 103:    // orderId duplicado -> resincronizar
            std::fprintf(stderr, "[tws] ERROR 103 orderId duplicado id=%d — resync reqIds\n", id);
            client_->reqIds(-1);
            break;
        default:
            // 354 (sin market data) es esperado: usamos NBBO de archivos, no esta conexión.
            std::fprintf(stderr, "[tws] error id=%d code=%d: %s\n", id, errorCode, msg.c_str());
            break;
    }
}

void TwsAdapter::connectionClosed() {
    frozen_ = true;
    connected_ = false;
    std::fprintf(stderr, "[tws] connectionClosed -> CONGELO entradas, marco locales\n");
    if (ledger_) { ledger_->note("connectionClosed"); ledger_->flush(); }
}

} // namespace oe
