from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = (ROOT / "scripts" / "ibtrader").read_text()
OPTIONS_BUILD = (ROOT / "scripts" / "build_options_alerts.sh").read_text()


def test_start_builds_everything_before_fleet_launch():
    assert 'start)    build_all && zsh scripts/fleet_up.sh "$@" ;;' in CLI
    build = CLI.split("build_all() {")[1].split("\n}", 1)[0]
    assert "for b in scripts/build_*.sh" in build
    assert "zsh macapp/build.sh" in build
    assert "la flota NO arrancó" in build


def test_options_engine_and_backtest_are_in_unified_build():
    assert "bin/options_alert_engine" in OPTIONS_BUILD
    assert "bin/options_alert_backtest" in OPTIONS_BUILD
    assert "-lsqlite3" in OPTIONS_BUILD
