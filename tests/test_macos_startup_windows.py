from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "macapp" / "main.swift").read_text()
STARTUP = (ROOT / "scripts" / "chart_qa_windows.sh").read_text()


def test_icon_launch_defaults_to_one_window():
    """Yunior 2026-08-05: al abrir el icono se abre UNA ventana, no 6."""
    assert "let DEFAULT_WINDOW_COUNT = 1" in SOURCE
    assert 'arg("--windows").flatMap(Int.init) ?? DEFAULT_WINDOW_COUNT' in SOURCE
    assert "return (0..<want).map { url(port: p0 + $0) }" in SOURCE


def test_explicit_ports_and_windows_remain_overrides():
    ports = SOURCE.index('if let s = arg("--ports")')
    windows = SOURCE.index('arg("--windows").flatMap(Int.init)')
    assert ports < windows
    assert "return ps.prefix(MAX_WINDOWS).map { url(port: $0) }" in SOURCE


def test_six_window_london_fleet_uses_requested_default_symbols():
    assert "SYMS=(qqq nvda smh spy tsla spcx)" in STARTUP
    assert "SYMS=(qqq nvda smh mu tsla spcx)" not in STARTUP
    assert "SYMS=(qqq nvda smh mu aapl msft)" not in STARTUP
