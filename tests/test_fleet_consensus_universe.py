"""El mensaje de MANADA debe DECLARAR si el universo está recortado.

Con market_source != ibkr el denominador pasa de fleet.txt (30) a provider_syms.txt (26). Eso baja
el listón sin avisar: 21 alineados son 81% sobre 26 (DANGER) pero 70% sobre 30 (silencio). Es el
mismo terreno del false-DANGER que ya disparó voz "comprar PUTS" con 21/26. No se prohíbe el
recorte — se EXIGE que la frase lo diga.
"""
import importlib.util
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(REPO, "scripts", "fleet_consensus.py")
    spec = importlib.util.spec_from_file_location("ibt_fleet_consensus_u", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_conoce_la_flota_completa_ademas_del_universo_recortado():
    m = _load()
    assert len(m.FULL_FLEET) >= 30, "fleet.txt es la flota COMPLETA (30 + los que se añadan)"
    assert len(m.FLEET) <= len(m.FULL_FLEET)


def test_el_umbral_efectivo_baja_con_el_recorte_por_eso_hay_que_declararlo():
    """Deja constancia numérica de POR QUÉ importa: mismo 21, veredicto opuesto."""
    m = _load()
    assert 100 * 21 / 26 >= m.PCT      # sobre el universo recortado: DISPARA
    assert 100 * 21 / 30 < m.PCT       # sobre la flota entera: NO dispara


def test_el_mensaje_declara_el_recorte(monkeypatch):
    m = _load()
    if len(m.FLEET) == len(m.FULL_FLEET):
        return  # sin recorte no hay nada que declarar
    fuente = open(os.path.join(REPO, "scripts", "fleet_consensus.py")).read()
    assert "universo RECORTADO" in fuente
    assert "FULL_FLEET" in fuente


def test_los_recortados_son_los_que_yunior_desactivo():
    m = _load()
    fuera = set(m.FULL_FLEET) - set(m.FLEET)
    assert fuera <= {"DRAM", "SPCX", "SKHY", "EWY"}, f"recorte inesperado: {fuera}"
