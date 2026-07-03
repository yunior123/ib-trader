import importlib.util
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_bridge():
    path = ROOT / "scripts" / "chart_bridge.py"
    spec = importlib.util.spec_from_file_location("chart_bridge_order_preflight", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def safe_runtime(cb, monkeypatch, *, double_arm=False):
    monkeypatch.setattr(cb, "execution_guard_status", lambda: {
        "engine_up": double_arm, "arm_file_today": double_arm,
        "engine_arm_flag": double_arm, "double_arm": double_arm,
    })
    monkeypatch.setattr(cb.ib_mode, "get_mode", lambda: "paper")
    monkeypatch.setattr(cb.ib_mode, "get_account", lambda: "DU123")
    monkeypatch.setattr(cb.ib_mode, "any_up", lambda _mode: True)


def test_option_preflight_is_rth_only_and_read_only(tmp_path, monkeypatch):
    cb = load_bridge()
    safe_runtime(cb, monkeypatch)
    monkeypatch.setattr(cb, "REPO", str(tmp_path))
    monkeypatch.setattr(cb, "chain_contract", lambda *args: {
        "right": "P", "strike": 690.0, "exp": "20260730",
        "bid": 2.10, "ask": 2.20, "oi": 900,
    })
    result = cb.order_preflight("qqq", {
        "instrument": "opt", "side": "buy", "kind": "put",
        "exp": "20260730", "price": 690, "qty": 2,
    })
    assert result["ok"] and result["can_prepare"]
    assert result["session"] == "DAY (RTH)"
    assert result["overnight_eligible"] is False
    assert result["draft"]["strike"] == 690.0 and result["draft"]["right"] == "P"
    assert result["limit_estimate"] == 2.20
    assert result["signal_only"] is True
    assert not (tmp_path / "order_engine" / "commands.jsonl").exists()
    assert not (tmp_path / "data" / "exec_zones_qqq.json").exists()


def test_stock_preflight_exposes_overnight_only_for_stock(monkeypatch):
    cb = load_bridge()
    safe_runtime(cb, monkeypatch, double_arm=True)
    result = cb.order_preflight("mu", {
        "instrument": "stk", "side": "sell", "kind": "",
        "exp": "", "price": 120, "qty": 10,
    })
    assert result["ok"]
    assert result["session"] == "OVERNIGHT+DAY"
    assert result["overnight_eligible"] is True
    assert result["limit_estimate"] == 119.76
    assert result["guard"]["double_arm"] is True
    assert any("Overnight+DAY" in warning for warning in result["warnings"])


def test_invalid_option_contract_fails_closed(monkeypatch):
    cb = load_bridge()
    safe_runtime(cb, monkeypatch)
    monkeypatch.setattr(cb, "chain_contract", lambda *args: None)
    result = cb.order_preflight("QQQ", {
        "instrument": "opt", "side": "buy", "kind": "call",
        "exp": "tomorrow", "price": 700, "qty": 1,
    })
    assert result["ok"] is False
    assert result["can_prepare"] is False
    assert any("YYYYMMDD" in error for error in result["errors"])


def test_pure_ui_flow_requires_human_confirmation_and_never_defaults_armed():
    script = r"""
const assert = require("assert");
const ui = require("./charts/order_ticket_ui.js");
const sent = [];
const socket = { send: payload => sent.push(JSON.parse(payload)) };
const pre = ui.preflightRequest({
  sym:"qqq", instrument:"opt", side:"buy", kind:"put",
  exp:"20260730", price:690, qty:2
});
socket.send(JSON.stringify(pre));
assert.strictEqual(sent[0].cmd, "order_preflight");
assert.strictEqual(Object.hasOwn(sent[0], "exec"), false);
const mockedBackend = {
  ok:true, can_prepare:true,
  limit_estimate:2.20,
  draft:{sym:"QQQ", instrument:"opt", side:"buy", kind:"put",
         exp:"20260730", price:690, qty:2, strike:690, right:"P"}
};
socket.send(JSON.stringify(ui.zoneRequest(mockedBackend)));
assert.deepStrictEqual(sent[1], {
  cmd:"zone", act:"add", price:690, side:"buy", kind:"put",
  exp:"20260730", qty:2, instrument:"opt",
  strike:690, right:"P", reviewed_limit:2.20, exec:false
});
assert.throws(() => ui.armRequest({id:"z1"}, false, {confirmation_token:"token"}), /confirmación humana/);
assert.throws(() => ui.armRequest({id:"z1"}, true, {}), /token/);
socket.send(JSON.stringify(ui.armRequest({id:"z1", instrument:"opt"}, true, {
  confirmation_token:"one-time-token", limit_estimate:2.20,
  draft:{strike:690, right:"P"}
})));
assert.deepStrictEqual(sent[2], {
  cmd:"zone", act:"set", id:"z1", exec:true,
  human_confirmed:true, confirmation_token:"one-time-token",
  strike:690, right:"P", reviewed_limit:2.20
});
const armNew = Object.assign({}, mockedBackend, {confirmation_token:"new-token"});
socket.send(JSON.stringify(ui.zoneRequest(armNew, true, true)));
assert.strictEqual(sent[3].exec, true);
assert.strictEqual(sent[3].human_confirmed, true);
assert.strictEqual(sent[3].confirmation_token, "new-token");
console.log(JSON.stringify(sent));
"""
    proc = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=True
    )
    sent = json.loads(proc.stdout)
    assert [row["cmd"] for row in sent] == ["order_preflight", "zone", "zone", "zone"]


def test_ticket_one_tap_contract():
    # Política 2026-07-29 (orden de Yunior): un toque = orden real, sin diálogo ni
    # selector FICHA/ARMAR. La seguridad vive en motor (doble llave, gates, what-if).
    html = (ROOT / "charts" / "live.html").read_text(encoding="utf-8")
    for control in ("zone-sym", "zone-inst", "zone-side", "zone-kind", "zone-exp",
                    "zone-qty", "zone-strike", "zone-limit"):
        assert f'for="{control}"' in html
    assert "zone-dest" not in html
    assert 'cmd = "quick_order"' in html.replace("d.cmd", "cmd")
    assert "exec: !z.exec" not in html
    assert "onQuickOrder" in html


def test_server_confirmation_token_is_one_time_bound_and_expiring(tmp_path, monkeypatch):
    cb = load_bridge()
    monkeypatch.setattr(cb, "REPO", str(tmp_path))
    (tmp_path / "data").mkdir()
    zone = {
        "id": "z1", "instrument": "stk", "side": "buy", "kind": "call",
        "exp": "", "price": 120.0, "qty": 10, "exec": False,
    }
    cb.zones_save("MU", [zone])
    preflight = {"draft": {
        "instrument": "stk", "side": "buy", "kind": "",
        "exp": "", "price": 120.0, "qty": 10,
    }}
    token, error = cb.issue_arm_confirmation("MU", "z1", preflight, now=100)
    assert error is None and token
    assert cb.consume_arm_confirmation("MU", "z1", token, False, now=101)[0] is False
    # El intento sin confirmación consume/falla cerrado; se requiere preflight fresco.
    token, _ = cb.issue_arm_confirmation("MU", "z1", preflight, now=102)
    assert cb.consume_arm_confirmation("MU", "z1", token, True, now=103) == (True, None)
    assert cb.consume_arm_confirmation("MU", "z1", token, True, now=104)[0] is False
    expired, _ = cb.issue_arm_confirmation("MU", "z1", preflight, now=200)
    assert cb.consume_arm_confirmation("MU", "z1", expired, True, now=400)[0] is False
    new_pf = {"draft": {
        "instrument": "opt", "side": "buy", "kind": "put",
        "exp": "20260730", "price": 120.0, "qty": 1,
    }}
    new_token = cb.issue_new_arm_confirmation("MU", new_pf, now=500)
    request = dict(new_pf["draft"])
    assert cb.consume_new_arm_confirmation("MU", request, new_token, True, now=501) == (True, None)
    assert cb.consume_new_arm_confirmation("MU", request, new_token, True, now=502)[0] is False


def test_server_rejects_remote_websocket_origins():
    cb = load_bridge()
    assert cb.local_websocket_origin("http://127.0.0.1:8080")
    assert cb.local_websocket_origin("http://localhost:8085")
    assert cb.local_websocket_origin(None)
    assert not cb.local_websocket_origin("https://evil.example")
    assert not cb.local_websocket_origin("http://localhost.evil.example")


def test_websocket_exec_true_is_guarded_before_zone_update():
    source = (ROOT / "scripts" / "chart_bridge.py").read_text(encoding="utf-8")
    branch = source[source.index('elif isinstance(ctl, dict) and ctl.get("cmd") == "zone"'):]
    branch = branch[:branch.index('elif isinstance(ctl, dict) and ctl.get("cmd") == "optquote"')]
    assert "consume_arm_confirmation(" in branch
    assert "consume_new_arm_confirmation(" in branch
    assert branch.index("consume_new_arm_confirmation(") < branch.index("zone_add(")
    assert branch.index("consume_arm_confirmation(") < branch.index("zone_update(")
    assert 'ctl.get("human_confirmed")' in branch
