"""DEX (delta exposure) en gex_core — feature diseñada dos veces y nunca construida
(designs-menthorq.md:219 #9, designs-spotgamma.md:182 #12).

Lo que se fija aqui:
  - la TRAMPA DE SIGNO: DEX positivo es cliente alcista Y creador comprando subyacente. Son
    dos hechos opuestos en el mismo numero, asi que publicar UN campo de signo esta prohibido
    y `check_dex_signs` levanta.
  - sin delta medido ni IV para reconstruirlo, `net_dex` es None. Un 0.0 leeria "libro
    neutral" donde no hay libro (los 3 peligros medidos, ~/CLAUDE.md).
  - el `-1.0000` de las 16:16 de IBKR es su centinela de "sin dato" y es TAMBIEN un delta de
    put legal: fila real de data/history/2026-07-24/opt_chain_qqq_1615.txt.
"""
import datetime as dt
import json
import os
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import gex_core as G           # noqa: E402


def _c(k, right, oi=1000, **kw):
    d = {"strike": k, "right": right, "oi": oi, "exp": "20260727", "T": 0.02}
    d.update(kw)
    return d


def _chain_file(tmp_path, rows, spot, epoch, exps):
    p = tmp_path / "opt_chain_x.txt"
    p.write_text("\n".join(
        [f"# opt_chain X | epoch {int(epoch)} | ts | spot {spot:.2f} | exps {' '.join(exps)}",
         "# strike right exp bid ask vol oi iv delta gamma"] + rows) + "\n")
    return str(p)


def _weekday_1100():
    d = dt.date.today()
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return time.mktime(dt.datetime.combine(d, dt.time(11, 0)).timetuple())


# ------------------------------------------------------------------ bs_delta
def test_bs_delta_cumple_la_paridad_call_menos_put_igual_uno():
    """Δc - Δp = 1 con q=0: si no se cumple, el delta de put esta mal firmado y el DEX neto
    sale con el signo contrario — que es justo el error que este modulo debe hacer imposible."""
    dc = G.bs_delta(685.0, 685.0, 0.02, 0.2875, "C")
    dp = G.bs_delta(685.0, 685.0, 0.02, 0.2875, "P")
    assert dc == pytest.approx(dp + 1.0, abs=1e-12)
    assert 0 < dc < 1 and -1 < dp < 0


def test_bs_delta_sin_plazo_es_none_no_cero():
    """`gex_snapshot.contracts_from` construye contratos sin `T` cuando el vencimiento es
    ilegible. Un 0.0 ahi seria 'OTM lejano' publicado como medida (fix de cf0baaf)."""
    assert G.bs_delta(685.0, 685.0, None, 0.28, "C") is None
    assert G.bs_delta(685.0, 685.0, 0.02, None, "C") is None
    assert G.bs_delta(685.0, 685.0, 0.02, 0.0, "C") is None


# ------------------------------------------------------- la trampa de signo
def test_prohibido_publicar_dex_con_un_solo_campo_de_signo():
    """designs-menthorq.md:224 lo exige: 'Two fields, never one'. Quien lea solo
    `dex_sentiment` cree que el creador tambien compra, y es lo contrario."""
    with pytest.raises(ValueError, match="dex_flow_impact"):
        G.check_dex_signs({"net_dex": 1e9, "dex_sentiment": "alcista"})
    with pytest.raises(ValueError, match="dex_sentiment"):
        G.check_dex_signs({"net_dex": 1e9, "dex_flow_impact": "mm_compra"})
    # los dos, o ninguno (ninguno = no hay DEX que publicar, es legitimo)
    G.check_dex_signs({"dex_sentiment": "alcista", "dex_flow_impact": "mm_compra"})
    G.check_dex_signs({"net_dex": None, "dex_sentiment": None, "dex_flow_impact": None})


def test_build_dex_siempre_saca_los_dos_campos_y_son_opuestos():
    """Cliente largo delta => creador corto delta => el creador COMPRA subyacente para quedar
    neutral. El mismo numero cuenta las dos mitades y las dos se publican."""
    alcista = G.build_dex([_c(690, "C", 5000, delta=0.45)], 685.0)
    assert alcista["net_dex"] > 0
    assert (alcista["dex_sentiment"], alcista["dex_flow_impact"]) == ("alcista", "mm_compra")
    bajista = G.build_dex([_c(680, "P", 5000, delta=-0.45)], 685.0)
    assert bajista["net_dex"] < 0
    assert (bajista["dex_sentiment"], bajista["dex_flow_impact"]) == ("bajista", "mm_vende")


# ------------------------------------------------------------- fail-loud
def test_sin_delta_ni_iv_el_neto_es_none_jamas_cero():
    """Cadena de NOK/DRAM despues del cierre: OI real, cero griegas. `net_dex=0.0` se leeria
    como 'libro perfectamente equilibrado' — un cero plausible."""
    d = G.build_dex([_c(10, "C"), _c(10, "P")], 10.0)
    assert d["net_dex"] is None and d["gross_dex"] is None
    assert d["dex_sentiment"] is None and d["dex_flow_impact"] is None
    assert d["n_contracts_oi"] == 2 and d["n_oi_delta_ok"] == 0 and d["n_oi_no_delta"] == 2
    assert d["delta_ok_pct_oi"] == 0.0


def test_sin_delta_del_proveedor_se_reconstruye_desde_la_iv_medida():
    """Polygon trae delta directo, pero un libro con IV y sin delta (o con delta 0.00 por
    redondeo) sigue siendo medible: BS desde la IV MEDIDA, nunca desde una supuesta."""
    con_iv = G.build_dex([_c(685, "C", 2348, iv=0.2875)], 685.0)
    assert con_iv["n_oi_delta_ok"] == 1
    assert con_iv["dex_profile"][685.0] == pytest.approx(
        G.bs_delta(685.0, 685.0, 0.02, 0.2875, "C") * 2348 * 100 * 685.0)


# ------------------------------------------------- centinela -1.00 de IBKR
def test_el_centinela_menos_uno_de_las_1615_no_pasa_por_delta_de_put(tmp_path):
    """Fila REAL de opt_chain_qqq_1615.txt: `685.00 C 20260724 -1.00 -1.00 ... -1.0000 -1.0000
    -1.0000`. Delta -1 en una CALL es imposible, pero |-1| = 1 es un delta legal: si el
    centinela entrara, el strike aportaria OI x 100 x spot de delta INVENTADO."""
    exp = (dt.date.today() + dt.timedelta(days=1)).strftime("%Y%m%d")
    rows = [f"685.00 C {exp} -1.00 -1.00 238672 2348 -1.0000 -1.0000 -1.0000",
            f"685.00 P {exp} -1.00 -1.00 370080 26591 -1.0000 -1.0000 -1.0000"]
    now = _weekday_1100()
    g = G.from_ibkr_cache(_chain_file(tmp_path, rows, 684.66, now, [exp]), 684.66, now=now)
    assert g["n_oi_delta_ok"] == 0 and g["net_dex"] is None
    assert g["dex_sentiment"] is None and g["dex_flow_impact"] is None


def test_el_signo_del_delta_lo_fija_el_tipo_no_el_fichero():
    """IBKR escribe el delta de put en negativo, otras fuentes en positivo. El DEX no puede
    depender de eso: un put SIEMPRE aporta delta negativo."""
    neg = G._delta_of(_c(680, "P", delta=-0.45), 685.0)
    pos = G._delta_of(_c(680, "P", delta=0.45), 685.0)
    assert neg == pytest.approx(-0.45) and pos == pytest.approx(-0.45)
    assert G._delta_of(_c(690, "C", delta=0.45), 685.0) == pytest.approx(0.45)


def test_dex_por_vencimiento_cuadra_con_el_bruto_total():
    """`dex_by_exp` es lo que pide designs-spotgamma #12 para `delta_share_e`: si no suma el
    bruto total, la cuota del proximo vencimiento sale mal y con ella el flag NEXT_EXP_HEAVY."""
    cs = [_c(690, "C", 5000, delta=0.45, exp="20260727"),
          _c(680, "P", 3000, delta=-0.40, exp="20260731", T=0.03)]
    d = G.build_dex(cs, 685.0)
    assert sorted(d["dex_by_exp"]) == ["20260727", "20260731"]
    assert sum(e["gross"] for e in d["dex_by_exp"].values()) == pytest.approx(d["gross_dex"])


# ----------------------------------------------- referee Unusual Whales (trial)
def _uw_legs(sym):
    p = os.path.join(REPO, "data", "history", "2026-07-26",
                     f"uw_greek_exposure_strike_{sym}.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        rows = json.load(f)["payload"]["data"]
    ultimo = max(r["date"] for r in rows)
    call, put = {}, {}
    for r in rows:
        if r["date"] != ultimo:
            continue
        k = float(r["strike"])
        call[k] = call.get(k, 0.0) + float(r["call_delta"])
        put[k] = put.get(k, 0.0) + float(r["put_delta"])
    return call, put


def _corr(a, b):
    import math
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    ca, cb = [x - ma for x in a], [x - mb for x in b]
    da, db = math.sqrt(sum(x * x for x in ca)), math.sqrt(sum(x * x for x in cb))
    return sum(x * y for x, y in zip(ca, cb)) / (da * db) if da and db else None


@pytest.mark.parametrize("sym", ["QQQ", "SPY", "MU"])
def test_convencion_de_signo_concuerda_por_pata_con_unusual_whales(sym):
    """Referee EXTERNO, nunca dependencia (trial que caduca ~2026-08-01: si el fichero no
    esta, se salta). Se compara PATA A PATA, no el neto: UW agrega TODA la cadena y nuestro
    `chain_full` es `dte_max=10`, asi que los netos no son la misma magnitud — en MU el neto
    hasta cambia de signo. Lo que si tiene que concordar es la CONVENCION: nuestras calls
    positivas contra sus `call_delta`, nuestros puts negativos contra sus `put_delta`."""
    legs = _uw_legs(sym)
    if legs is None:
        pytest.skip("sin fichero de referee UW (trial caducado)")
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import gex_snapshot as gs
    path, _ = gs.latest_chain(sym)
    if not path:
        pytest.skip(f"sin chain_full de {sym}")
    cs, spot, _, _ = gs.contracts_from(path)
    dx = G.build_dex(cs, spot, scale="shares")
    for mine, ref in ((dx["call_dex"], legs[0]), (dx["put_dex"], legs[1])):
        ks = sorted(set(mine) & set(ref))
        assert len(ks) >= 10, f"{sym}: solo {len(ks)} strikes en comun"
        assert _corr([mine[k] for k in ks], [ref[k] for k in ks]) > 0.4
        assert (sum(mine[k] for k in ks) > 0) == (sum(ref[k] for k in ks) > 0)
