#pragma once

#include <cmath>
#include <string>

#include "Contract.h"
#include "Decimal.h"
#include "EDecoder.h"
#include "Order.h"

namespace oe {

enum class OrderSession {
    RTH_ONLY,
    OVERNIGHT_AND_DAY,
};

struct LimitOrderPlan {
    bool ok = false;
    Contract contract;
    Order order;
    std::string error;
};

// Pure boundary: constructs every field sent to TWS and rejects unsupported
// combinations before EClientSocket::placeOrder can see them.
inline LimitOrderPlan make_limit_order_plan(const Contract& input, char side, int qty,
                                            double limit, const std::string& order_ref,
                                            OrderSession session, int server_version,
                                            bool what_if, const std::string& account) {
    LimitOrderPlan p;
    p.contract = input;

    if (side != 'B' && side != 'S') {
        p.error = "side must be B or S";
        return p;
    }
    if (qty <= 0 || !std::isfinite(limit) || limit <= 0.0) {
        p.error = "quantity and limit must be positive";
        return p;
    }
    if (input.symbol.empty() || input.currency != "USD" || input.exchange != "SMART") {
        p.error = "only qualified USD SMART contracts are supported";
        return p;
    }
    if (input.secType != "STK" && input.secType != "OPT") {
        p.error = "only STK and OPT contracts are supported";
        return p;
    }
    if (account.empty()) {
        p.error = "execution account is not explicitly selected";
        return p;
    }

    Order& o = p.order;
    o.action = (side == 'B') ? "BUY" : "SELL";
    o.orderType = "LMT";
    o.totalQuantity = DecimalFunctions::stringToDecimal(std::to_string(qty));
    o.lmtPrice = limit;
    o.tif = "DAY";
    // IBKR must receive the request to calculate margin, so transmit stays true.
    // `whatIf=true` is the protocol-level instruction that makes it a simulation
    // instead of a working order (transmit=false never produced an openOrder result).
    o.whatIf = what_if;
    o.transmit = true;
    o.orderRef = order_ref;
    o.account = account;

    if (session == OrderSession::OVERNIGHT_AND_DAY) {
        if (input.secType != "STK") {
            p.error = "overnight session is not enabled for options";
            return p;
        }
        if (server_version < MIN_SERVER_VER_INCLUDE_OVERNIGHT) {
            p.error = "TWS/Gateway server lacks includeOvernight support";
            return p;
        }
        // Official IBKR wire policy for "Overnight + Day".
        p.contract.exchange = "SMART";
        o.outsideRth = true;
        o.includeOvernight = true;
    } else {
        // Options and explicit RTH-only stock orders never leak into extended
        // or overnight sessions.
        o.outsideRth = false;
        o.includeOvernight = false;
    }

    p.ok = true;
    return p;
}

} // namespace oe
