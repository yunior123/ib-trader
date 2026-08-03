"""Carpetas data/history de un dia NO bursatil no pueden pasar por "ultima sesion".

Precedente 2026-08-02: com.ibtrader.polychains corre 08:45/16:20 los 7 dias; el domingo archivo
35 chain_full_*.json con la foto del VIERNES (spot_age_s=159.611 = 44,3 h) bajo
data/history/2026-08-02/. skew.py:latest_dates()[0] cogia ese domingo y su drr_1d salia
domingo-viernes = 0 FABRICADO.
"""
import datetime as dt
import importlib.util
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import session_dirs  # noqa: E402


def _mk(tmp_path, *names):
    for n in names:
        (tmp_path / n).mkdir()
    return str(tmp_path)


def test_domingo_y_sabado_fuera(tmp_path):
    hist = _mk(tmp_path, "2026-07-31", "2026-08-01", "2026-08-02", "2026-08-03")
    assert session_dirs.session_dirs(hist) == ["2026-08-03", "2026-07-31"]


def test_festivo_fuera(tmp_path):
    # 2026-07-03 = Independence Day observado (tabla de em_envelope)
    hist = _mk(tmp_path, "2026-07-02", "2026-07-03", "2026-07-06")
    assert session_dirs.session_dirs(hist) == ["2026-07-06", "2026-07-02"]


def test_nombre_que_no_es_fecha_no_es_sesion(tmp_path):
    hist = _mk(tmp_path, "2026-07-31", "bars", "gexa_hist")
    assert session_dirs.session_dirs(hist) == ["2026-07-31"]
    assert session_dirs.is_session_dir("bars") is None


def test_sin_carpeta_devuelve_vacio_no_levanta():
    assert session_dirs.session_dirs("/no/existe/jamas") == []


def test_tabla_de_festivos_agotada_LEVANTA():
    # jamas asumir "sin festivos" en un año sin tabla: es fabricar un dia de mercado
    with pytest.raises(ValueError):
        session_dirs.is_session_dir("2099-06-15")


def test_skew_latest_dates_salta_el_domingo(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "skew_mod", os.path.join(REPO, "scripts", "skew.py"))
    skew = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(skew)
    for d in ("2026-07-31", "2026-08-02"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "chain_full_spy.json").write_text("{}")
    monkeypatch.setattr(skew, "HIST", str(tmp_path))
    assert skew.latest_dates() == ["2026-07-31"]


def test_poly_chain_archive_no_archiva_en_no_sesion(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location(
        "pca_mod", os.path.join(REPO, "scripts", "poly_chain_archive.py"))
    pca = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pca)

    llamado = []
    monkeypatch.setattr(pca, "run", lambda *a, **k: llamado.append(a))

    class Domingo(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2026, 8, 2)

    monkeypatch.setattr(pca.dt, "date", Domingo)
    monkeypatch.setattr(sys, "argv", ["poly_chain_archive.py"])
    pca.main()
    assert llamado == []
    assert "no es dia de mercado" in capsys.readouterr().out
