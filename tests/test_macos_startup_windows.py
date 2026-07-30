from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "macapp" / "main.swift").read_text()


def test_icon_launch_defaults_to_six_independent_ports():
    assert "let DEFAULT_WINDOW_COUNT = 6" in SOURCE
    assert 'arg("--windows").flatMap(Int.init) ?? DEFAULT_WINDOW_COUNT' in SOURCE
    assert "return (0..<want).map { url(port: p0 + $0) }" in SOURCE


def test_explicit_ports_and_windows_remain_overrides():
    ports = SOURCE.index('if let s = arg("--ports")')
    windows = SOURCE.index('arg("--windows").flatMap(Int.init)')
    assert ports < windows
    assert "return ps.prefix(MAX_WINDOWS).map { url(port: $0) }" in SOURCE
