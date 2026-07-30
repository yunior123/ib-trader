#include "../order_policy.h"

#include <cassert>
#include <cmath>
#include <iostream>

using namespace oe;

static Contract stock() {
    Contract c;
    c.symbol = "AAPL";
    c.secType = "STK";
    c.exchange = "SMART";
    c.primaryExchange = "NASDAQ";
    c.currency = "USD";
    return c;
}

static Contract option() {
    Contract c = stock();
    c.secType = "OPT";
    c.lastTradeDateOrContractMonth = "20260807";
    c.strike = 220;
    c.right = "P";
    c.multiplier = "100";
    return c;
}

int main() {
    {
        auto p = make_limit_order_plan(stock(), 'B', 7, 219.25, "OE:STK",
                                       OrderSession::OVERNIGHT_AND_DAY,
                                       MIN_SERVER_VER_INCLUDE_OVERNIGHT, false, "U_TEST");
        assert(p.ok);
        assert(p.contract.secType == "STK");
        assert(p.contract.exchange == "SMART");
        assert(p.contract.currency == "USD");
        assert(p.order.action == "BUY");
        assert(p.order.orderType == "LMT");
        assert(p.order.tif == "DAY");
        assert(p.order.outsideRth);
        assert(p.order.includeOvernight);
        assert(p.order.transmit);
        assert(p.order.orderRef == "OE:STK");
        assert(p.order.account == "U_TEST");
        assert(std::abs(p.order.lmtPrice - 219.25) < 1e-9);
        assert(std::abs(DecimalFunctions::decimalToDouble(p.order.totalQuantity) - 7.0) < 1e-9);
    }
    {
        auto p = make_limit_order_plan(option(), 'S', 2, 3.40, "OE:OPT",
                                       OrderSession::RTH_ONLY, 999, false, "U_TEST");
        assert(p.ok);
        assert(p.contract.secType == "OPT");
        assert(p.contract.exchange == "SMART");
        assert(p.order.action == "SELL");
        assert(p.order.tif == "DAY");
        assert(!p.order.outsideRth);
        assert(!p.order.includeOvernight);
        assert(p.order.transmit);
    }
    {
        auto p = make_limit_order_plan(stock(), 'B', 1, 219.25, "OE:WHATIF",
                                       OrderSession::OVERNIGHT_AND_DAY, 999, true, "U_TEST");
        assert(p.ok);
        assert(p.order.whatIf);
        assert(p.order.transmit);
        assert(p.order.outsideRth);
        assert(p.order.includeOvernight);
        assert(p.order.orderType == "LMT");
        assert(p.order.tif == "DAY");
    }
    {
        auto p = make_limit_order_plan(option(), 'B', 1, 1.25, "OE:BAD",
                                       OrderSession::OVERNIGHT_AND_DAY, 999, false, "U_TEST");
        assert(!p.ok);
        assert(!p.error.empty());
    }
    {
        auto p = make_limit_order_plan(stock(), 'B', 1, 219.25, "OE:OLD",
                                       OrderSession::OVERNIGHT_AND_DAY,
                                       MIN_SERVER_VER_INCLUDE_OVERNIGHT - 1, false, "U_TEST");
        assert(!p.ok);
        assert(!p.error.empty());
    }
    {
        Contract c = stock();
        c.exchange = "OVERNIGHT";
        auto p = make_limit_order_plan(c, 'B', 1, 219.25, "OE:DIRECT",
                                       OrderSession::OVERNIGHT_AND_DAY, 999, false, "U_TEST");
        assert(!p.ok); // this engine supports SMART Overnight+Day only
    }
    {
        Contract c = stock();
        c.currency = "CAD";
        assert(!make_limit_order_plan(c, 'B', 1, 1, "OE:CAD",
                                      OrderSession::RTH_ONLY, 999, false, "U_TEST").ok);
        c = stock();
        c.secType = "FUT";
        assert(!make_limit_order_plan(c, 'B', 1, 1, "OE:FUT",
                                      OrderSession::RTH_ONLY, 999, false, "U_TEST").ok);
        assert(!make_limit_order_plan(stock(), 'X', 1, 1, "OE:SIDE",
                                      OrderSession::RTH_ONLY, 999, false, "U_TEST").ok);
        assert(!make_limit_order_plan(stock(), 'B', 0, 1, "OE:QTY",
                                      OrderSession::RTH_ONLY, 999, false, "U_TEST").ok);
        assert(!make_limit_order_plan(stock(), 'B', 1, 1, "OE:NOACCT",
                                      OrderSession::RTH_ONLY, 999, false, "").ok);
    }

    std::cout << "policy: OK\n";
}
