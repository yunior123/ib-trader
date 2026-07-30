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
    print("bridge order backend: OK")


if __name__ == "__main__":
    main()
