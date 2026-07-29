"""Los consumidores del mapa gamma: sin mapa NADIE afirma un regimen.

gexa.ai murio el 2026-07-25 y el mapa lo calcula en casa `scripts/gex_snapshot.py` ->
`data/gex_snapshot.json` (griegas MEDIDAS de Polygon). Lo que se fija aqui es el borde
peligroso del recableado, no que el mapa se lea bien: **que falte**.

Regla de la casa que estos tests protegen: ante fallo, `None` o levantar — nunca `{}`,
`0`, `0.0` ni `50`. Un numero plausible convierte "no se" en "se, y es cero", y ya nos
costo un denominador fabricado (fleet_consensus) y una flecha diluida (component_bias).
"""
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    """Importa un script de scripts/ por ruta. argv se vacia durante el import porque
    algunos parsean argumentos a nivel de modulo (si no, argparse ve los de pytest y
    llama a sys.exit(2))."""
    import sys
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibtc_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = [path]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = argv
    return mod


def _fake_map(tmp_path, syms=("QQQ",), chain_date=None, score=-481.1):
    """Un data/gex_snapshot.json de juguete, con el contrato real por simbolo."""
    import datetime as dt
    import time
    cd = chain_date or dt.date.today().isoformat()
    d = {s: {"flip": 715.0, "flip_all": 715.0, "score": score, "bias": "PUT", "poc": 695.0,
             "regime": "NEGATIVE" if score < 0 else "POSITIVE",
             "regime_short": "NEG" if score < 0 else "POS", "chain_date": cd,
             "greeks_ok_pct": 0.78, "n_contracts": 668} for s in syms}
    d["_meta"] = {"cobertura": f"{len(syms)}/30", "asof": int(time.time())}
    p = tmp_path / "gex_snapshot.json"
    p.write_text(json.dumps(d))
    return str(p)


# --- posters X: sin mapa, el tweet CALLA el regimen ---------------------------------

@pytest.fixture(scope="module")
def xc():
    return _load("x_post_common")


def test_load_gex_devuelve_None_no_dict_vacio(xc):
    """El `{}` de la vieja load_gexa esta PROHIBIDO: se confunde con "hoy no hay gamma"."""
    assert xc.load_gex(path=os.path.join(REPO, "data", "no_existe_gex.json")) is None
    assert xc.load_gex(max_age_h=0) is None          # rancio = sin mapa, no un mapa viejo


def test_sin_mapa_el_tweet_no_menciona_gamma(xc):
    txt = "QQQ 684: piso 680 techo 705. No es consejo financiero."
    assert xc.gex_line("QQQ", gex=None) == ""
    assert xc.append_gex(txt, "QQQ", gex=None) == txt     # el texto sale intacto


def test_gex_None_no_recarga_del_disco_a_espaldas_del_llamador(xc, tmp_path):
    """Con `gex=None` el codigo viejo RECARGABA: quien ya habia medido "no hay mapa" veia
    su None convertido en datos. El centinela _UNSET separa los dos casos."""
    assert xc.gex_line("QQQ", gex=None) == ""             # None = sin mapa: calla
    p = _fake_map(tmp_path)
    con_mapa = xc.gex_line("QQQ", gex=xc.load_gex(path=p))
    assert "flip 715" in con_mapa and "measured" in con_mapa   # procedencia en la propia linea


def test_simbolo_sin_mapa_no_hereda_el_de_otro(xc, tmp_path):
    g = xc.load_gex(path=_fake_map(tmp_path, syms=("QQQ",)))
    assert xc.gex_line("NOK", gex=g) == ""


def test_meta_no_se_cuela_como_simbolo(xc, tmp_path):
    g = xc.load_gex(path=_fake_map(tmp_path, syms=("QQQ", "SPY")))
    assert set(g) == {"QQQ", "SPY"}          # `_meta` no es un ticker


# --- planes diarios: el PDF no afirma un regimen que no midio ----------------------

@pytest.fixture(scope="module")
def plans():
    return _load("daily_fleet_plans")


def test_plan_sin_mapa_no_afirma_regimen(plans, monkeypatch):
    monkeypatch.setattr(plans.gex_snapshot, "load", lambda **_k: None)
    assert plans.gex_snapshot_for("QQQ") is None


def test_plan_simbolo_omitido_por_el_builder_es_None(plans, monkeypatch):
    monkeypatch.setattr(plans.gex_snapshot, "load", lambda **_k: {"SPY": {"flip": 1.0}})
    assert plans.gex_snapshot_for("QQQ") is None


def test_plan_cadena_rancia_es_None_aunque_el_fichero_sea_de_hoy(plans, monkeypatch):
    """La mtime del fichero envejece sin que el mapa deje de ser vigente, asi que la
    caducidad de verdad la fija `chain_date`: una cadena de hace 40 dias no vale."""
    import datetime as dt
    viejo = (dt.date.today() - dt.timedelta(days=40)).isoformat()
    monkeypatch.setattr(plans.gex_snapshot, "load",
                        lambda **_k: {"QQQ": {"flip": 715.0, "score": -1.0, "chain_date": viejo}})
    assert plans.gex_snapshot_for("QQQ") is None


def test_plan_score_no_numerico_es_None_no_un_cero(plans, monkeypatch):
    """Sin score no hay signo, y sin signo no hay regimen. Cero seria una afirmacion."""
    import datetime as dt
    hoy = dt.date.today().isoformat()
    monkeypatch.setattr(plans.gex_snapshot, "load",
                        lambda **_k: {"QQQ": {"flip": 715.0, "score": None, "chain_date": hoy}})
    assert plans.gex_snapshot_for("QQQ") is None


def test_plan_con_mapa_del_dia_lo_usa(plans, monkeypatch):
    import datetime as dt
    hoy = dt.date.today().isoformat()
    g = {"QQQ": {"flip": 715.0, "score": -481.1, "chain_date": hoy, "n_contracts": 668,
                 "greeks_ok_pct": 0.78}}
    monkeypatch.setattr(plans.gex_snapshot, "load", lambda **_k: g)
    assert plans.gex_snapshot_for("qqq") == g["QQQ"]      # case-insensitive


# --- skills por ticker: sin dato, sin linea ----------------------------------------

def test_skill_sin_mapa_no_escribe_regimen():
    spr = _load("skill_patterns_refresh")
    assert spr.gex_line("QQQ", None) is None
    assert spr.gex_line("QQQ", {}) is None
    assert spr.gex_line("QQQ", {"QQQ": {"flip": None}}) is None


# --- archivo diario: lee el historico viejo, pero DICE de cual salio ---------------

def test_archive_sin_ningun_mapa_devuelve_None_None(tmp_path):
    da = _load("daily_archive")
    assert da.read_gex_map(str(tmp_path)) == (None, None)


def test_archive_prefiere_el_medido_y_declara_procedencia(tmp_path):
    da = _load("daily_archive")
    (tmp_path / "gex_snapshot.json").write_text(json.dumps({"QQQ": {"flip": 715.0}}))
    (tmp_path / "gexa_snapshot.json").write_text(json.dumps({"QQQ": {"flip": 208.0}}))
    mapa, src = da.read_gex_map(str(tmp_path))
    assert mapa["QQQ"]["flip"] == 715.0          # gana el MEDIDO
    assert "MEDIDO" in src


def test_archive_cae_al_historico_de_gexa_y_lo_confiesa(tmp_path):
    """Los dias 2026-07-21..24 solo tienen el scrape: se siguen leyendo, marcados."""
    da = _load("daily_archive")
    (tmp_path / "gexa_snapshot.json").write_text(json.dumps({"QQQ": {"flip": 208.0}}))
    mapa, src = da.read_gex_map(str(tmp_path))
    assert mapa["QQQ"]["flip"] == 208.0
    assert "gexa" in src and "jubilado" in src


def test_archive_fichero_roto_no_se_confunde_con_ausente(tmp_path):
    """Un JSON truncado cae al siguiente candidato en vez de fabricar un mapa vacio."""
    da = _load("daily_archive")
    (tmp_path / "gex_snapshot.json").write_text("{esto no es json")
    (tmp_path / "gexa_snapshot.json").write_text(json.dumps({"QQQ": {"flip": 208.0}}))
    mapa, src = da.read_gex_map(str(tmp_path))
    assert mapa["QQQ"]["flip"] == 208.0 and "gexa" in src
