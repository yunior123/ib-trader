#include "../scripts/options_alert_engine_core.h"
#include <cassert>
#include <iostream>
using namespace options_alert;

int main() {
    assert(normalize_symbol("brk.b") == "BRK.B");
    assert(normalize_symbol("BF-B") == "BF-B");
    assert(normalize_symbol("../NVDA").empty());
    Config c; c.now = 1786204800; c.target_dte = 5; c.max_age_s = 900; // 2026-08-08 UTC
    Chain ch; ch.epoch = c.now - 30; ch.spot = 225;
    ch.rows.push_back({230, 1.00, 1.04, 900, 2200, .40, .54, 'C', "20260813"});
    ch.rows.push_back({225, 2.50, 2.55, 2000, 5000, .35, .60, 'C', "20260813"});
    Pick p = select(ch, 'C', c);
    assert(p.ok); assert(p.row.strike == 230); assert(p.dte == 5);
    assert(format("NVDA", 'C', p) == "nvda call 230 5-DTE");
    ch.epoch = c.now - 901;
    assert(!select(ch, 'C', c).ok);
    std::cout << "options_alert_engine tests OK\n";
}
