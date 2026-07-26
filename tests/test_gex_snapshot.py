"""gex_snapshot: el mapa gamma propio que sustituye a gexa.ai (jubilado el 2026-07-25).

Lo que se fija aqui es sobre todo la HONESTIDAD del dato, que es lo que costo dinero en el
pasado: un simbolo que no se puede leer se OMITE con su motivo, jamas se rellena con un cero
plausible; y load() devuelve None -nunca {}- porque un dict vacio se confunde con "hoy no hay
gamma" (el bug del denominador fabricado de fleet_consensus).
"""
import importlib.util
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    path = os.path.join(REPO, "scripts", name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gs():
    return _load("gex_snapshot")


def _contract(strike, right, oi=500, gamma=0.02, exp="2026-07-27", iv=0.4):
    return {"details": {"strike_price": strike, "contract_type": right,
                        "expiration_date": exp},
            "greeks": {"gamma": gamma}, "open_interest": oi,
            "implied_volatility": iv}


def _chain(tmp_path, sym, contratos, spot=100.0, fecha=None):
    import datetime as dt
    fecha = fecha or dt.date.today().isoformat()
    d = tmp_path / "data" / "history" / fecha
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"chain_full_{sym.lower()}.json"
    p.write_text(json.dumps({"meta": {"sym": sym.upper(), "spot": spot,
                                      "snapshot_local": "2026-07-25 10:18:54"},
                             "results": contratos}))
    return p


# --- el universo del mapa se lee de la fuente unica, en el formato REAL del fichero -----
# NOTA: gex_snapshot.universo() delega en scripts/universe.py (helper compartido), asi que
# el REPO a parchear es el del modulo `universe`, no el de `gs`.

def test_universo_lee_una_sola_linea_separada_por_espacios(gs, tmp_path, monkeypatch):
    """data/universe_gamma.txt es UNA linea de simbolos separados por espacios. Leerlo como
    'un simbolo por linea' daba cobertura 0/1 y omitia el universo entero (cazado al
    construir el fleet.txt original con el mismo formato)."""
    monkeypatch.setattr(gs.universe, "REPO", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "universe_gamma.txt").write_text("QQQ SPY NVDA MU\n")
    assert gs.universo() == ["QQQ", "SPY", "NVDA", "MU"]


def test_universo_admite_tambien_uno_por_linea(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs.universe, "REPO", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "universe_gamma.txt").write_text("QQQ\nSPY\n# comentario\nMU\n")
    assert gs.universo() == ["QQQ", "SPY", "MU"]


def test_universo_vacio_LEVANTA_no_devuelve_lista_vacia(gs, tmp_path, monkeypatch):
    """Sin universo no hay mapa que construir. Una lista vacia se veria como
    'cobertura 0/0 = todo bien' — silencio, justo lo que no queremos."""
    monkeypatch.setattr(gs.universe, "REPO", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "universe_gamma.txt").write_text("\n#solo comentarios\n")
    with pytest.raises(RuntimeError):
        gs.universo()


def test_universo_es_independiente_de_fleet_txt(gs, tmp_path, monkeypatch):
    """gex_snapshot es un productor de MAPA: no puede depender de data/fleet.txt (la flota de
    señales) ni verse afectado por su ausencia. Confundir las dos listas fue el bug del
    denominador fabricado que rompio MANADA el 2026-07-25 (docs/UNIVERSOS.md)."""
    monkeypatch.setattr(gs.universe, "REPO", str(tmp_path))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "universe_gamma.txt").write_text("QQQ SPY SPX XSP NDX DIA IWM\n")
    assert not (tmp_path / "data" / "fleet.txt").exists()
    assert gs.universo() == ["QQQ", "SPY", "SPX", "XSP", "NDX", "DIA", "IWM"]


# --- omitir es la respuesta correcta: nunca un cero plausible ----------------------

def test_sin_cadena_devuelve_None_y_motivo(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    snap, why = gs.snapshot_sym("QQQ")
    assert snap is None
    assert "sin cadena" in why


def test_pocos_strikes_se_omite_con_motivo(gs, tmp_path, monkeypatch):
    """Con 2-7 strikes poblados el perfil es ruido (umbral 8 de la casa, el mismo que
    book_quality). Es el caso real de NVDA/QCOM/NFLX/NOK/SKHY hoy: se omiten, no se inventan."""
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = [_contract(100 + i, "call") for i in range(3)]
    _chain(tmp_path, "NOK", cs, spot=100.0)
    snap, why = gs.snapshot_sym("NOK")
    assert snap is None
    assert "strikes poblados" in why


def test_griegas_insuficientes_se_omite(gs, tmp_path, monkeypatch):
    """Mas de la mitad de los contratos sin gamma medida = libro ilegible. Es exactamente el
    fallo que book_quality sufre leyendo ibkr_tws fuera de RTH (0% de griegas)."""
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = [_contract(100 + i, "call") for i in range(4)]
    for c in cs:
        c["greeks"] = {}                      # sin gamma: no usable
    cs += [_contract(200 + i, "put") for i in range(1)]
    _chain(tmp_path, "MU", cs, spot=100.0)
    snap, why = gs.snapshot_sym("MU")
    assert snap is None
    assert "griegas" in why


def test_un_simbolo_roto_no_tumba_el_mapa_y_queda_en_skipped(gs, tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    monkeypatch.setattr(gs.universe, "REPO", str(tmp_path))
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "universe_gamma.txt").write_text("QQQ NOK\n")
    _chain(tmp_path, "NOK", [_contract(100, "call")], spot=100.0)
    d = gs.build()
    assert "NOK" in d["_meta"]["skipped"]
    assert d["_meta"]["cobertura"].endswith("/2")


# --- load(): None, jamas {} --------------------------------------------------------

def test_load_sin_fichero_es_None(gs, tmp_path):
    assert gs.load(path=str(tmp_path / "no_existe.json")) is None


def test_load_json_roto_es_None(gs, tmp_path):
    p = tmp_path / "roto.json"
    p.write_text("{no es json")
    assert gs.load(path=str(p)) is None


def test_load_solo_meta_es_None_no_dict_vacio(gs, tmp_path):
    """Un mapa con `_meta` pero sin ningun simbolo NO es {} — es 'no hay lectura'. Devolver
    un dict vacio dejaria al consumidor afirmando un regimen que nadie midio."""
    p = tmp_path / "vacio.json"
    p.write_text(json.dumps({"_meta": {"cobertura": "0/30"}}))
    assert gs.load(path=str(p)) is None


def test_load_filtra_meta_y_respeta_la_edad(gs, tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"_meta": {"cobertura": "1/30"},
                             "QQQ": {"flip": 715.0, "regime": "NEGATIVE"}}))
    d = gs.load(path=str(p))
    assert d is not None and "_meta" not in d and d["QQQ"]["flip"] == 715.0
    os.utime(p, (0, 0))                       # rancio de 1970
    assert gs.load(path=str(p), max_age_h=12) is None


# --- el contrato que consumen los planes ------------------------------------------

def test_contrato_del_dict_por_simbolo(gs, tmp_path, monkeypatch):
    """Los planes heredaron la forma de gexa: el SIGNO de `score` fija el regimen. Si esto se
    rompe, los PDFs cantan el regimen contrario."""
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = []
    for i in range(12):                       # strikes de sobra a ambos lados del spot
        k = 90.0 + i * 2
        cs.append(_contract(k, "call", oi=800, gamma=0.03))
        cs.append(_contract(k, "put", oi=900, gamma=0.03))
    _chain(tmp_path, "QQQ", cs, spot=100.0)
    snap, why = gs.snapshot_sym("QQQ")
    assert why is None and snap is not None
    for k in ("flip", "flip_all", "score", "bias", "poc", "magnets", "regime",
              "call_usd", "put_usd", "ts", "src", "chain_date", "greeks_ok_pct"):
        assert k in snap, f"falta la clave {k} del contrato"
    assert snap["bias"] in ("CALL", "PUT")
    assert snap["regime"] in ("POSITIVE", "NEGATIVE")
    # el signo de score y el regimen no pueden contradecirse
    assert (snap["score"] < 0) == (snap["regime"] == "NEGATIVE")
    assert snap["regime_short"] in ("POS", "NEG")
    # procedencia: MEDIDO dicho en el propio dato (nunca mezclar sin decirlo)
    assert "MEDIDAS" in snap["src"] or "Polygon" in snap["src"]


def test_escritura_atomica_no_deja_tmp(gs, tmp_path):
    p = str(tmp_path / "out.json")
    gs.write({"_meta": {"cobertura": "0/0"}}, path=p)
    assert os.path.exists(p) and not os.path.exists(p + ".tmp")


def test_fin_de_semana_usa_la_cadena_del_viernes(gs, tmp_path, monkeypatch):
    """El sabado no hay cadena nueva y la del viernes SIGUE siendo el mapa vigente. Si
    latest_chain solo mirase hoy, la flota entera se quedaria sin gamma el fin de semana."""
    import datetime as dt
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    ayer = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    _chain(tmp_path, "SPY", [_contract(100, "call")], spot=100.0, fecha=ayer)
    path, fecha = gs.latest_chain("SPY")
    assert path is not None and fecha == ayer


def test_score_nunca_pierde_el_SIGNO_por_redondeo(gs, tmp_path, monkeypatch):
    """round(-40000/1e6, 1) == -0.0 y en Python `-0.0 < 0` es False: un nombre pequeño en
    regimen NEG se leeria como POSITIVO en los planes, porque los consumidores heredaron de
    gexa la logica 'signo de score = regimen'. El signo manda sobre la estetica."""
    monkeypatch.setattr(gs, "REPO", str(tmp_path))
    cs = []
    for i in range(12):
        k = 90.0 + i * 2
        cs.append(_contract(k, "call", oi=1, gamma=1e-9))
        cs.append(_contract(k, "put", oi=2, gamma=1e-9))
    _chain(tmp_path, "NOK", cs, spot=100.0)
    snap, why = gs.snapshot_sym("NOK")
    assert why is None and snap is not None
    # magnitud minuscula, pero el signo tiene que seguir coincidiendo con el regimen
    assert (snap["score"] < 0) == (snap["regime"] == "NEGATIVE"), (
        f"score {snap['score']!r} contradice regime {snap['regime']}")
    assert (snap["score"] < 0) == (snap["net_gex"] < 0)
