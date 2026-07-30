// tws_adapter.h — capa de ejecución REAL contra IBKR TWS (API C++ oficial).
// TwsAdapter hereda DefaultEWrapper (≈100 virtuales ya stubeados) y sólo pisa
// los callbacks que importan. Patrón EReaderOSSignal + EClientSocket + EReader
// del skill ibkr-tws: el hilo lector encola mensajes; pump() los DESPACHA en el
// hilo del motor -> los callbacks corren single-thread, sin locks en el FSM.
//
// clientId 92 (dedicado order_engine). Paper 7497 primero, live 7496.
// SÓLO este módulo coloca órdenes en toda la flota (ley AGENTS.md #0 enmendada).
//
// Shapes ExecReport/OptContract/OptQuote se ESPEJAN de scalper/exec_adapter.h
// para que el scalper pueda compartir este adaptador más adelante.
#pragma once
#include <deque>
#include <map>
#include <memory>
#include <string>

#include "EClientSocket.h"
#include "EReader.h"
#include "EReaderOSSignal.h"
#include "DefaultEWrapper.h"
#include "Contract.h"
#include "Order.h"
#include "OrderCancel.h"
#include "Execution.h"
#include "CommissionReport.h"
#include "OrderState.h"
#include "Decimal.h"

#include "guards.h"        // PositionBook/PosKey -- fuente de verdad de posiciones (#3/#7)
#include "ledger.h"

namespace oe {

// --- shapes espejadas de scalper/exec_adapter.h (compat futuro) -----------
struct OptContract {          // mirror: symbol/exp/strike/right (aquí en dólares)
    std::string symbol, exp, right;   // right = "C" | "P"
    double strike = 0;
    bool valid() const { return !symbol.empty() && strike > 0 && (right == "C" || right == "P"); }
};
struct OptQuote { int bid_c = 0, ask_c = 0; bool ok() const { return bid_c > 0 && ask_c >= bid_c; } };
struct ExecReport {
    int order_id = 0;
    enum K { ACK, FILL, CANCELED, REJECTED } kind = ACK;
    int px_c = 0;             // precio en centavos (mirror scalper)
    long long t_mono_ms = 0;
    std::string status;       // status crudo de TWS (extra, no rompe el mirror)
    double qty = 0;           // cantidad LLENADA (para proteger fills parciales)
};

// Construye un Contract IBKR de ACCIÓN (secType STK). Acciones tradean 24/5
// (con outsideRth) -> se puede probar el ciclo completo en paper a cualquier hora.
inline Contract make_stock(const std::string& sym) {
    Contract c;
    c.symbol = sym;
    c.secType = "STK";
    c.exchange = "SMART";
    c.primaryExchange = "NASDAQ";   // ayuda a desambiguar (QQQ/NVDA/etc.)
    c.currency = "USD";
    return c;
}

// Construye un Contract IBKR de opción (secType OPT, SMART, USD, multiplier 100).
inline Contract make_option(const std::string& sym, const std::string& exp,
                            double strike, const std::string& right) {
    Contract c;
    c.symbol = sym;
    c.secType = "OPT";
    c.exchange = "SMART";
    c.currency = "USD";
    c.multiplier = "100";
    c.lastTradeDateOrContractMonth = exp;
    c.strike = strike;
    c.right = right;              // "C" | "P"
    c.tradingClass = sym;        // ayuda a cualificar el contrato
    return c;
}

class TwsAdapter : public DefaultEWrapper {
public:
    explicit TwsAdapter(Ledger* led) : ledger_(led) {
        client_ = std::make_unique<EClientSocket>(this, &signal_);
    }
    ~TwsAdapter() override { disconnect(); }

    // --- conexión --------------------------------------------------------
    bool connect(const char* host, int port, int clientId);
    // Reconecta tras connectionClosed: re-eConnect + nuevo EReader. El motor
    // debe re-correr reconcile() después (cancela huérfanas OE: y re-verifica).
    bool reconnect(const char* host, int port, int clientId);
    void disconnect();
    void pump();                                   // waitForSignal + processMsgs (hilo motor)

    bool connected() const { return connected_; }  // hay nextValidId (socket vivo + listo)
    bool socket_alive() const { return client_ && client_->isConnected(); }
    bool frozen() const { return frozen_; }        // 1100/502/connectionClosed -> congelar entradas
    bool reconciled() const { return reconciled_; }
    const std::string& account() const { return account_; }

    // --- posiciones REALES (#3/#7) -----------------------------------------
    // Fuente de verdad para "close": el estado local en RAM (book[]) NUNCA
    // decrementa filled_qty cuando un close se llena (el orderId de close ni
    // siquiera entra en oid2zone), asi que confiar en book[] para el gate de
    // TAMAÑO seria tan plausible-e-inventado como el centinela del defecto 1.
    // reqPositions()/position()/positionEnd() son el reqPositions real de
    // IBKR: PositionBook.known() solo es true tras ver positionEnd().
    void reqPositions();
    const PositionBook& positions() const { return positions_; }

    // Stop nativo VIVO adoptado con este orderRef -> su orderId, o -1 si no hay.
    // Tras un reconnect los STP huérfanos se ADOPTAN (siguen protegiendo la
    // posición); el motor debe re-usarlos en vez de colocar un segundo stop.
    int adopted_stop_id(const std::string& ref) const {
        for (const auto& kv : orders_)
            if (kv.second.ours && kv.second.live && kv.second.native_stop && kv.second.ref == ref)
                return kv.first;
        return -1;
    }

    // orderId: se siembra con nextValidId y se incrementa localmente.
    int next_order_id() { return next_id_++; }
    bool have_ids() const { return next_id_ > 0; }

    // --- órdenes (SÓLO se llaman con doble llave; DRY jamás llega aquí) ---
    // Límite marketable DAY, transmit=true, orderRef "OE:..". NUNCA descansa
    // salvo que sea un stop nativo (place_stop native=true).
    void place_limit(Contract& c, char side /*'B'|'S'*/, int qty, double limit,
                     int orderId, const std::string& orderRef, bool outsideRth = false);
    // Stop protectivo. native=true -> STP server-side (sobrevive al crash),
    // SIEMPRE en el set de cancel-all. native=false -> el motor lo vigila local.
    void place_stop(Contract& c, char side, int qty, double stopPx,
                    int orderId, const std::string& orderRef, bool native);
    void cancel(int orderId);
    void modify(int orderId, double newLimit);     // = placeOrder MISMO id (cancel/replace)

    // Desarme: cancela entradas propias vivas; conserva stops protectivos propios.
    // Ignora órdenes ajenas y terminales. Idempotente.
    void cancel_all_own();
    // Al arrancar: pide TODAS las órdenes abiertas para adoptar/cancelar las
    // huérfanas "OE:" de un run anterior (reconciliación).
    void reconcile();
    int  live_own_count() const;

    // Drena eventos de ejecución de a uno (mirror ExecutionAdapter::poll).
    bool poll(ExecReport& out);

    // --- callbacks EWrapper (sólo los que importan) ----------------------
    void nextValidId(OrderId orderId) override;
    void connectAck() override;
    void managedAccounts(const std::string& accountsList) override;
    void orderStatus(OrderId orderId, const std::string& status, Decimal filled,
                     Decimal remaining, double avgFillPrice, int permId, int parentId,
                     double lastFillPrice, int clientId, const std::string& whyHeld,
                     double mktCapPrice) override;
    void openOrder(OrderId orderId, const Contract&, const Order&, const OrderState&) override;
    void openOrderEnd() override;
    void position(const std::string& account, const Contract& contract, Decimal position,
                 double avgCost) override;
    void positionEnd() override;
    void execDetails(int reqId, const Contract& contract, const Execution& execution) override;
    void commissionReport(const CommissionReport& cr) override;
    void error(int id, int errorCode, const std::string& errorString,
               const std::string& advancedOrderRejectJson) override;
    void connectionClosed() override;

private:
    struct OpenOrd {
        Contract c;
        Order    o;
        std::string ref;
        bool ours = false;     // orderRef empieza con "OE:"
        bool live = true;      // aún puede cancelarse en el servidor
        bool native_stop = false;
    };
    LedgerContract led_of(const Contract& c) const {
        return LedgerContract{c.symbol, c.lastTradeDateOrContractMonth, c.strike, c.right};
    }
    void push(int id, ExecReport::K k, int px_c, const std::string& status, double qty = 0);

    EReaderOSSignal signal_{2000};                 // timeout ms
    std::unique_ptr<EClientSocket> client_;
    std::unique_ptr<EReader> reader_;

    Ledger* ledger_ = nullptr;
    std::map<int, OpenOrd> orders_;                // id -> última orden nuestra
    std::deque<ExecReport> events_;                // cola para el motor

    int  next_id_ = 0;
    bool connected_ = false;
    bool frozen_ = false;
    bool reconciled_ = false;
    std::string account_;
    PositionBook positions_;
};

} // namespace oe
