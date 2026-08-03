import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
sys.path.insert(0, SCRIPTS)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


xc = load("x_post_common")
xs = load("x_signal_poster")


def test_public_guard_rejects_mixed_spanish_and_korean():
    assert not xc.public_text_is_english("Bullish wrapper: señal alcista de ballena")
    assert not xc.public_text_is_english("Samsung earnings 삼성전자")
    assert xc.public_text_is_english("Bullish reclaim confirmed. Not financial advice.")


def test_public_privacy_guard_fails_closed():
    assert xc.public_text_is_private_safe("$NVDA momentum breakout. Not financial advice.")
    assert not xc.public_text_is_private_safe("Built by Yunior")
    assert not xc.public_text_is_private_safe("source /Users/example/private/data.json")
    assert not xc.public_text_is_private_safe("auth=123456")
    assert not xc.public_text_is_private_safe("mail me at private@example.com")


def test_live_signal_does_not_copy_spanish_source_text():
    text = xs.build_post(
        "AAPL",
        "BALLENA DE CALLS",
        "tendencia alcista; ruptura confirmada; alto volumen",
        340.0,
        342.5,
        338.5,
        76,
    )
    assert xc.public_text_is_english(text)
    assert "Unusual call volume" in text
    assert "alcista" not in text.lower()
    assert "ruptura" not in text.lower()


def test_bearish_retest_is_rendered_in_english():
    text = xs.build_post(
        "QQQ", "SEÑAL", "SELL bajista retest-ok px=660", 660, 655, 663, 74
    )
    assert "Bearish break-and-retest confirmed" in text
    assert xc.public_text_is_english(text)


def _finviz(**overrides):
    event = {
        "ts": 1_800_000_000,
        "screen": "momentum",
        "ticker": "NVDA",
        "event": "new_match",
        "weather": "BUY",
        "score": 7,
        "possible": 9,
        "price": 201.25,
        "change_pct": 2.4,
        "rvol": 2.8,
    }
    event.update(overrides)
    return event


def test_finviz_post_is_english_market_only_and_private_safe():
    text = xs.build_finviz_post(_finviz())
    assert "$NVDA" in text
    assert "Finviz momentum-breakout screen: BUY" in text
    assert "relative volume 2.8x" in text
    assert "ib-trader" not in text.lower()
    assert xc.public_text_is_english(text)
    assert xc.public_text_is_private_safe(text)


def test_finviz_relevance_keeps_only_strong_directional_events():
    assert xs.finviz_relevance(_finviz())[0]
    assert not xs.finviz_relevance(_finviz(weather="WATCH"))[0]
    assert not xs.finviz_relevance(_finviz(score=3, possible=9))[0]
    assert not xs.finviz_relevance(_finviz(rvol=1.2))[0]
    assert not xs.finviz_relevance(_finviz(change_pct=0.1))[0]
    assert not xs.finviz_relevance(_finviz(weather="SELL", score=7))[0]


def test_finviz_sell_copy_is_directional():
    event = _finviz(weather="SELL", score=-7, change_pct=-3.1)
    ok, _ = xs.finviz_relevance(event)
    text = xs.build_finviz_post(event)
    assert ok
    assert "SELL" in text and "-3.10%" in text


def test_process_finviz_posts_structured_event_once(tmp_path, monkeypatch):
    event_path = tmp_path / "finviz.jsonl"
    state_path = tmp_path / "state.json"
    event = _finviz(ts=time.time())
    event_path.write_text(json.dumps(event) + "\n")
    monkeypatch.setattr(xs, "FINVIZ_EVENTS", str(event_path))
    monkeypatch.setattr(xs, "STATE_FILE", str(state_path))
    posted = []

    def fake_post(text, tag, log, dry_run=False, auth=None, media_path=None):
        posted.append((text, tag))
        return True

    monkeypatch.setattr(xs.xc, "post_text", fake_post)
    st = xs.load_state()
    now = datetime.now(ZoneInfo("America/New_York"))
    xs.process_finviz(st, now, False, object())
    xs.process_finviz(st, now, False, object())

    assert len(posted) == 1
    assert "$NVDA" in posted[0][0]
    assert st["finviz_posts"] == 1
    assert st["finviz_keys"] == ["momentum:NVDA:BUY"]
