import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fetch_bars3mo5m", REPO / "scripts" / "fetch_bars3mo5m.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class FakeLSE:
    def candles(self, *_args, **_kwargs):
        return [
            {"ts": "2026-08-07T13:00:00Z", "open": 9, "high": 10,
             "low": 8, "close": 9.5, "volume": 10},  # premarket: fuera
            {"ts": "2026-08-07T14:30:00Z", "open": 10, "high": 12,
             "low": 9, "close": 11, "volume": 100},
        ]


def test_lse_backfill_filters_rth_and_preserves_real_ohlcv():
    rows = M.fetch_lse(FakeLSE(), "SPY", days=1)
    assert len(rows) == 1
    assert rows[0][1:] == (10.0, 12.0, 9.0, 11.0, 100)


def test_backfill_has_no_yahoo_fallback():
    source = (REPO / "scripts" / "fetch_bars3mo5m.py").read_text().lower()
    assert "import yfinance" not in source
    assert "fallback yfinance" not in source
