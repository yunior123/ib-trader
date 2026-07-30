import os
import tempfile
from types import SimpleNamespace

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
import chart_bridge as cb


def main():
    old_run, old_path = cb.subprocess.run, cb.CMD_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            cb.CMD_PATH = os.path.join(td, "commands.jsonl")
            cb.subprocess.run = lambda *a, **k: SimpleNamespace(stdout=b"")
            r = cb.route_order_action({"act": "close", "sym": "AAPL", "qty": 1,
                                       "side": "sell", "secType": "STK"})
            assert not r["ok"]
            assert not os.path.exists(cb.CMD_PATH), "engine-down command must not queue"

        saved = [{"id": "z1", "exec": False, "instrument": "stk", "price": 100,
                  "qty": 1, "exp": "20260807"}]
        cb.zones_load = lambda sym: [dict(z) for z in saved]
        def save(_sym, zones):
            saved[:] = [dict(z) for z in zones]
        cb.zones_save = save
        out = cb.zone_update("AAPL", "z1", exec=True, overnight_gap_ack=True,
                             reviewed_limit=100.20)
        assert out[0]["exec"]
        assert len(out[0]["confirm_id"]) == 32
        assert out[0]["confirmed_at"] > 0
        assert out[0]["armed_date"]
        out = cb.zone_update("AAPL", "z1", price=101)
        assert not out[0]["exec"]
        assert "confirm_id" not in out[0]

        saved[:] = [{"id": "z3", "exec": False, "instrument": "stk",
                     "price": 100, "qty": 1}]
        out = cb.zone_update("AAPL", "z3", exec=True)
        assert not out[0]["exec"]
        assert "STP/GTC overnight" in out[0]["confirm_error"]

        saved[:] = [{"id": "z2", "exec": False, "instrument": "opt",
                     "price": 220, "qty": 1, "side": "buy",
                     "kind": "put", "exp": "20260807"}]
        cb.chain_contract = lambda *a, **k: {
            "strike": 220.0, "right": "P", "exp": "20260807",
            "bid": 3.10, "ask": 3.20}
        out = cb.zone_update("AAPL", "z2", exec=True, locked_strike=220,
                             locked_right="P", reviewed_limit=3.20)
        assert out[0]["exec"]
        assert out[0]["locked_strike"] == 220.0
        assert out[0]["locked_right"] == "P"
        assert out[0]["locked_exp"] == "20260807"
        assert out[0]["locked_limit"] == 3.20
    finally:
        cb.subprocess.run, cb.CMD_PATH = old_run, old_path
    quick_order_tests()
    print("bridge order backend: OK")


def quick_order_tests():
    import asyncio
    import json

    assert not cb._nbbo_good(None)
    assert not cb._nbbo_good(float("nan"))
    assert not cb._nbbo_good(0)
    assert not cb._nbbo_good(-1.2)
    assert cb._nbbo_good(8.43)

    buy = cb.build_quick_order_cmd("TSLL", "stk", "buy", 10, 12.34)
    assert buy["act"] == "open" and buy["side"] == "buy" and buy["limit"] == 12.34
    assert buy["secType"] == "STK" and buy["strike"] == 0 and buy["exp"] == ""
    sell = cb.build_quick_order_cmd("TSLL", "stk", "sell", 10, 12.34)
    assert sell["act"] == "close" and sell["side"] == "sell"   # reduce-only, jamás abre corto
    assert "limit" not in sell                                  # el motor precia el close fresco
    opt = cb.build_quick_order_cmd("QQQ", "opt", "buy", 1, 2.05, "20260731", 670.0, "C")
    assert opt["act"] == "open" and opt["secType"] == "OPT" and opt["strike"] == 670.0

    old_guard, old_acct, old_chain = cb.execution_guard_status, cb.ib_mode.get_account, cb.chain_contract
    old_path = cb.CMD_PATH
    try:
        cb.ib_mode.get_account = lambda: "U_TEST"
        # motor apagado -> error honesto, nada encolado
        cb.execution_guard_status = lambda now=None: {
            "engine_up": False, "arm_file_today": False,
            "engine_arm_flag": False, "double_arm": False}
        r = asyncio.run(cb.quick_order("QQQ", {"sym": "TSLL", "instrument": "stk",
                                               "side": "buy", "qty": 10}))
        assert not r["ok"] and any("APAGADO" in e for e in r["errors"])

        cb.execution_guard_status = lambda now=None: {
            "engine_up": True, "arm_file_today": True,
            "engine_arm_flag": True, "double_arm": True}
        # opción sin cadena local -> error, sin encolar
        cb.chain_contract = lambda *a, **k: None
        r = asyncio.run(cb.quick_order("QQQ", {"sym": "ZZZZ", "instrument": "opt",
                                               "side": "buy", "kind": "call",
                                               "exp": "20260731", "qty": 1, "price": 100}))
        assert not r["ok"] and any("cadena" in e for e in r["errors"])

        # opción del universo -> encola act=open con límite = ask de la cadena
        with tempfile.TemporaryDirectory() as td:
            cb.CMD_PATH = os.path.join(td, "commands.jsonl")
            cb.chain_contract = lambda *a, **k: {"strike": 670.0, "right": "C",
                                                 "exp": "20260731", "bid": 2.00, "ask": 2.05}
            r = asyncio.run(cb.quick_order("QQQ", {"sym": "QQQ", "instrument": "opt",
                                                   "side": "buy", "kind": "call",
                                                   "exp": "20260731", "qty": 1, "price": 670}))
            assert r["ok"] and r["armed"] and r["limit"] == 2.05
            line = json.loads(open(cb.CMD_PATH).read().strip())
            assert line["act"] == "open" and line["sym"] == "QQQ" and line["limit"] == 2.05

        # lado basura -> jamás encola
        r = asyncio.run(cb.quick_order("QQQ", {"sym": "QQQ", "instrument": "stk",
                                               "side": "hold", "qty": 1}))
        assert not r["ok"]

        # doble toque (<2.5s) -> la segunda se ignora; pasado el umbral, pasa
        cb._QUICK_LAST.clear()
        assert not cb.quick_order_duplicate("NOK", "stk", "buy", 5, now=100.0)
        assert cb.quick_order_duplicate("NOK", "stk", "buy", 5, now=101.0)
        assert not cb.quick_order_duplicate("NOK", "stk", "buy", 5, now=104.0)
        assert not cb.quick_order_duplicate("NOK", "stk", "sell", 5, now=104.1)
    finally:
        cb.execution_guard_status, cb.ib_mode.get_account = old_guard, old_acct
        cb.chain_contract, cb.CMD_PATH = old_chain, old_path


if __name__ == "__main__":
    main()
