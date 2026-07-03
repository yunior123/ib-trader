"""daily_archive: find_ranking_json prueba 3 rutas (hoy/repunto, raiz vieja,
archivo/) y NUNCA revienta; su ausencia total debe GRITAR (CRITICAL en stderr),
no callar. Repunto Desktop 2026-07-26.
"""
import importlib.util
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(REPO, "scripts", "daily_archive.py")
    spec = importlib.util.spec_from_file_location("ibt_daily_archive", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_finds_new_hoy_path(tmp_path, monkeypatch):
    mod = _load()
    hoy = tmp_path / "hoy"
    (hoy / "planes-2026-09-01").mkdir(parents=True)
    rk = hoy / "planes-2026-09-01" / "ranking.json"
    rk.write_text("{}")
    monkeypatch.setattr(mod, "IBT_DESKTOP_HOY", str(hoy))
    assert mod.find_ranking_json("2026-09-01") == str(rk)


def test_falls_back_to_old_desktop_root(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "IBT_DESKTOP_HOY", str(tmp_path / "hoy-vacio"))

    def fake_candidates(date):
        return [
            str(tmp_path / "hoy-vacio" / f"planes-{date}" / "ranking.json"),
            str(tmp_path / "old-root" / f"planes-{date}" / "ranking.json"),
            str(tmp_path / "archivo" / f"planes-{date}" / "ranking.json"),
        ]
    monkeypatch.setattr(mod, "ranking_json_candidates", fake_candidates)
    old = tmp_path / "old-root" / "planes-2026-09-02"
    old.mkdir(parents=True)
    (old / "ranking.json").write_text('{"x":1}')
    assert mod.find_ranking_json("2026-09-02") == str(old / "ranking.json")


def test_missing_everywhere_returns_none_never_raises(tmp_path, monkeypatch):
    mod = _load()

    def fake_candidates(date):
        return [str(tmp_path / "a" / "ranking.json"),
                str(tmp_path / "b" / "ranking.json"),
                str(tmp_path / "c" / "ranking.json")]
    monkeypatch.setattr(mod, "ranking_json_candidates", fake_candidates)
    assert mod.find_ranking_json("2026-09-03") is None


def test_archive_ranking_shouts_critical_when_missing(tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod, "ranking_json_candidates", lambda date: ["/nope/a", "/nope/b"])
    ok = mod.archive_ranking(str(tmp_path), "2026-01-01")
    err = capsys.readouterr().err
    assert ok is False
    assert "CRITICAL" in err
    assert "ranking.json" in err
    assert "2026-01-01" in err


def test_archive_ranking_copies_when_found(tmp_path, monkeypatch, capsys):
    mod = _load()
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    rk = src_dir / "ranking.json"
    rk.write_text('{"ok":1}')
    monkeypatch.setattr(mod, "ranking_json_candidates", lambda date: [str(rk)])
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    ok = mod.archive_ranking(str(dst_dir), "2026-01-02")
    assert ok is True
    assert (dst_dir / "ranking.json").exists()
    assert "CRITICAL" not in capsys.readouterr().err
