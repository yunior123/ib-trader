"""Tests de scripts/backtest_alertas_flota.py (lote de medicion, no camino de señal).

Lo que se blinda aqui:
  - la taxonomia de alertas y su DIRECCION salen de los strings REALES del feed;
  - la triple barrera no convierte un timeout en victoria y resuelve la barra
    ambigua contra nosotros;
  - fail-loud: sin barras contiguas el ATR es None y la etiqueta es None,
    JAMAS 0 / 0.5 / 50;
  - n_eff nunca supera el numero de clusters;
  - la entrada no mira al futuro.
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import backtest_alertas_flota as B  # noqa: E402


# ------------------------------------------------------------- taxonomia

REAL = [
    ("\U0001F388 BB REBOTE [VETO medido]",
     "SMH reventó la banda ABAJO y re-entró en 528.50. Elastico: rebote hacia la media 529.51",
     "BB_REBOTE_VETO", 1),
    ("\U0001F388 BB REBOTE",
     "QCOM reventó la banda ARRIBA y re-entró en 144.81. Elastico: reversion corta",
     "BB_REBOTE", -1),
    ("\U0001F388 BB REBOTE ⭐[degradada]",
     "MU reventó la banda ABAJO y re-entró en 784.62.", "BB_REBOTE_STAR", 1),
    ("\U0001F388 BB 15m RE-ENTRADA [MUTED p<55]",
     "SPY reventó la banda 15 minutos ARRIBA y re-entró en 751.12 — elastico mayor",
     "BB15_REENTRADA_MUTED", -1),
    ("\U0001F388 BB 15m RE-ENTRADA",
     "XLK reventó la banda 15 minutos ABAJO y re-entró en 174.75 — elastico mayor",
     "BB15_REENTRADA", 1),
    ("\U0001F388 BB BAND-WALK",
     "GOOGL camina la banda ARRIBA tambien en 5 minutos (367.21). Continuacion probable",
     "BB_BANDWALK", 1),
    ("\U0001F388 BB BAND-WALK [MUTED p<55]",
     "META camina la banda ABAJO tambien en 5 minutos (563.90).",
     "BB_BANDWALK_MUTED", -1),
    ("\U0001F3AF APERTURA FUERA DE BANDA",
     "MSFT abrio 474.15 arriba de la banda 15m (466.32). Patron medido: 60 por ciento",
     "APERTURA_FUERA_BANDA", -1),
    ("\U0001F3AF APERTURA FUERA DE BANDA",
     "INTC abrio 87.99 abajo de la banda 15m (91.11).", "APERTURA_FUERA_BANDA", 1),
    ("MU TERREMOTO CAIDA", "CUSUM: cayendo fuerte -5.20% px 780.12", "CUSUM_TERREMOTO", -1),
    ("INTC TERREMOTO ALZA", "CUSUM: subiendo fuerte +5.38% px 90.59", "CUSUM_TERREMOTO", 1),
    ("\U0001F9F2 ESTRUCTURAL magnet MU",
     "MU se dirige a su imán 835.0 ↑ · prob 79% (estructural, no WR medido)",
     "ESTRUCTURAL_MAGNET", 1),
    ("\U0001F9F2 ESTRUCTURAL pin QQQ",
     "QQQ en su imán 690.0 — pin · prob 76% (estructural, no WR medido)",
     "ESTRUCTURAL_PIN", 0),
    ("\U0001F40B ALERTA BALLENA CALLS",
     "Alerta ballena: alto volumen agregado de calls en TSLA; strike dominante 310",
     "BALLENA_CALLS", -1),
    ("\U0001F40B ALERTA BALLENA PUTS",
     "Alerta ballena: alto volumen agregado de puts en SPY", "BALLENA_PUTS", 1),
    ("\U0001F680 SPIKE PUTS AVGO",
     "SPIKE de puts en AVGO: 3 mil contratos, 13 veces su ritmo. Panico vendedor",
     "SPIKE_PUTS", 1),
    ("\U0001F43A MANADA A CALLS",
     "MANADA A CALLS: 3 tickers en 12 minutos — GOOGL QCOM XLK . Extremo de mercado",
     "MANADA_CALLS", -1),
    ("\U0001FA78 DIP REAL", "DIP REAL en MU: -19.8% desde el high de 5 dias", "DIP_REAL", 1),
]


@pytest.mark.parametrize("kind,msg,typ,direction", REAL)
def test_classify_strings_reales(kind, msg, typ, direction):
    got = B.classify(kind, msg)
    assert got is not None, kind
    assert got == (typ, direction)


def test_warmup_no_es_alerta_viva():
    assert B.classify("WARMUP AMD TERREMOTO CAIDA", "CUSUM: cayendo fuerte -3.02%") is None


def test_ruido_no_clasifica():
    assert B.classify("\U0001F512 TRUTH-LOCK INFO", "MU: PASADO reescrito") is None
    assert B.classify("\U0001F573 CINTA CIEGA", "3 de la flota sin tape") is None
    assert B.classify("FINVIZ BUFFETT · WEATHER · BUY 1 SELL 0", "SPNT BUY $23.64") is None


def test_extract_symbol_prefiere_el_kind():
    fs = {"MU", "QQQ", "SPY"}
    assert B.extract_symbol("\U0001F9F2 ESTRUCTURAL magnet MU", "QQQ tambien", fs) == "MU"
    assert B.extract_symbol("sin ticker", "SPY se mueve", fs) == "SPY"
    assert B.extract_symbol("nada", "nada", fs) is None


def test_magnet_regex():
    a = B.MAGNET_RE.search("QQQ en su imán 690.0 — pin")
    assert a and float(a.group(1)) == 690.0


# ------------------------------------------------------------- barras / ATR

def mkbars(n, start=1785744000, o=100.0, rng=1.0, step=60, skip=()):
    """Serie sintetica contigua salvo los indices en `skip`."""
    out = []
    for i in range(n):
        if i in skip:
            continue
        px = o + i * 0.0
        out.append((start + i * step, (px, px + rng, px - rng, px)))
    return out


def test_atr14_exige_contiguidad():
    bars = mkbars(40)
    assert B.atr14(bars, 20) == pytest.approx(2.0)
    # una barra ausente en la ventana invalida el ATR: None, jamas 0
    gap = [b for k, b in enumerate(mkbars(40)) if k != 12]
    assert B.atr14(gap, 20) is None


def test_atr14_sin_historia_es_none():
    assert B.atr14(mkbars(40), 3) is None
    assert B.atr14(mkbars(40), 14) is None


def test_triple_barrera_tp_primero():
    bars = mkbars(40)
    # subimos la barra 21 por encima del TP
    ep, (o, h, l, c) = bars[21]
    bars[21] = (ep, (o, 100.0 + 5.0, l, c))
    lab, mfe, mae, amb, atr = B.triple_barrier(bars, 20, 1, 1.0, 1.0, 10)
    assert lab == 1 and not amb and atr == pytest.approx(2.0)
    assert mfe > 0


def test_triple_barrera_sl_primero():
    bars = mkbars(40)
    ep, (o, h, l, c) = bars[21]
    bars[21] = (ep, (o, h, 100.0 - 5.0, c))
    lab = B.triple_barrier(bars, 20, 1, 1.0, 1.0, 10)[0]
    assert lab == 0


def test_triple_barrera_timeout_es_none_no_victoria():
    bars = mkbars(60, rng=0.001)      # rango minusculo: no se toca ninguna barrera
    lab = B.triple_barrier(bars, 20, 1, 5.0, 5.0, 10)[0]
    assert lab is None


def test_triple_barrera_ambigua_resuelve_contra_nosotros():
    bars = mkbars(40)
    ep, (o, _h, _l, c) = bars[21]
    bars[21] = (ep, (o, 100.0 + 5.0, 100.0 - 5.0, c))   # TP y SL en la misma barra
    lab, _mfe, _mae, amb, _atr = B.triple_barrier(bars, 20, 1, 1.0, 1.0, 10)
    assert lab == 0 and amb is True


def test_triple_barrera_sin_atr_no_inventa_numero():
    bars = mkbars(40)
    lab, mfe, mae, amb, atr = B.triple_barrier(bars, 2, 1, 1.0, 1.0, 10)
    assert lab is None and atr is None and mfe is None and mae is None


def test_containment():
    bars = mkbars(40)
    assert B.containment(bars, 20, 5.0, 10) == 1
    ep, (o, h, l, c) = bars[22]
    bars[22] = (ep, (o, 100.0 + 99.0, l, c))
    assert B.containment(bars, 20, 5.0, 10) == 0
    assert B.containment(mkbars(40), 2, 1.0, 10) is None      # sin ATR -> None


def test_entry_index_no_mira_al_futuro():
    bars = mkbars(40)
    open_ep = bars[0][0]
    ts = bars[10][0] + 30              # alerta a mitad de la barra 10
    i = B.entry_index(bars, ts, open_ep)
    assert i == 10                     # se entra al CIERRE de la barra que la contiene
    assert bars[i][0] + 60 >= ts
    # alerta justo en el segundo en que cierra la barra 9: esa barra YA cerro,
    # asi que entrar a su cierre tampoco mira al futuro
    ts_exacto = bars[10][0]
    assert B.entry_index(bars, ts_exacto, open_ep) == 9


def test_entry_index_ignora_premarket():
    bars = mkbars(40)
    open_ep = bars[20][0]
    assert B.entry_index(bars, bars[0][0], open_ep) == 20


def test_load_symbol_day_descarta_barras_en_conflicto(tmp_path, monkeypatch):
    date = "2026-08-03"
    _warm, op, _cl = B.day_bounds(date)
    hd = tmp_path / "history" / date / "bars"
    hd.mkdir(parents=True)
    dd = tmp_path / "data"
    dd.mkdir()
    (hd / "zzz.txt").write_text("%d 1 2 0.5 1.5 0\n%d 1 2 0.5 1.5 0\n" % (op, op + 60))
    (dd / "bars_zzz_ibkr.txt").write_text("%d 1 2 0.5 1.5 0\n%d 9 9 9 9 0\n" % (op, op + 60))
    monkeypatch.setattr(B, "HISTDIR", str(tmp_path / "history"))
    monkeypatch.setattr(B, "DATADIR", str(dd))
    bars, conflicts = B.load_symbol_day("ZZZ", date)
    assert conflicts == 1
    assert op in bars and (op + 60) not in bars     # la discrepante se DESCARTA


def test_audit_bars_excluye_sym_dia_sin_barras(tmp_path, monkeypatch):
    date = "2026-08-03"
    monkeypatch.setattr(B, "HISTDIR", str(tmp_path / "history"))
    monkeypatch.setattr(B, "DATADIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(parents=True)
    admitted, excluded = B.audit_bars([date], ["QQQ", "EWY"])
    assert admitted == {}
    assert {e["sym"] for e in excluded} == {"QQQ", "EWY"}
    assert all(e["missing"] == B.RTH_BARS for e in excluded)


# ------------------------------------------------------------- estadistica

def test_wilson_valores_conocidos():
    p, lo, hi = B.wilson(50, 100)
    assert p == 0.5
    assert lo == pytest.approx(0.4038, abs=1e-3)
    assert hi == pytest.approx(0.5962, abs=1e-3)
    assert B.wilson(0, 0) == (None, None, None)


def test_wilson_cero_aciertos_no_devuelve_nada_plausible():
    p, lo, hi = B.wilson(0, 20)
    assert p == 0.0 and lo == 0.0 and hi < 0.20


def test_n_effective_topado_por_clusters():
    rows = [{"date": "2026-08-03", "ts": 1785744000} for _ in range(30)]
    neff, nc = B.n_effective(rows, 0.4)
    assert nc == 1
    assert neff == 1.0                       # 30 alertas del mismo minuto = 1 observacion
    rows2 = [{"date": "2026-08-03", "ts": 1785744000 + i * 300} for i in range(30)]
    neff2, nc2 = B.n_effective(rows2, 0.4)
    assert nc2 == 30 and neff2 == 30.0       # k=1 -> sin penalizacion


def test_n_effective_sin_rho_es_conservador():
    rows = [{"date": "2026-08-03", "ts": 1785744000 + (i // 10) * 300} for i in range(30)]
    neff, nc = B.n_effective(rows, None)
    assert neff == float(nc) == 3.0


def test_n_effective_vacio():
    assert B.n_effective([], 0.4) == (0.0, 0)


def test_bh_fdr():
    assert B.bh_fdr([0.001, 0.9, 0.95], 0.10) == [True, False, False]
    assert B.bh_fdr([0.4, 0.5, 0.6], 0.10) == [False, False, False]
    assert B.bh_fdr([], 0.10) == []


def test_corr_exige_muestra():
    assert B._corr([1, 2, 3], [1, 2, 3]) is None            # n<30 -> None
    x = list(range(40))
    assert B._corr(x, x) == pytest.approx(1.0)
    assert B._corr(x, [40 - v for v in x]) == pytest.approx(-1.0)
    assert B._corr(x, [7] * 40) is None                     # varianza cero -> None


def test_verdict_data_insuficiente_manda():
    assert B.verdict(10.0, 0.9, 0.8, 0.4, True, 0.3) == "DATA-INSUFICIENTE"
    assert B.verdict(50.0, 0.9, 0.8, 0.4, True, 0.3) == "KEEP"
    # bate al null pero no llega al suelo operable -> no es KEEP
    assert B.verdict(50.0, 0.30, 0.25, 0.10, True, 0.05) == "KILL"
    # no pasa FDR -> KILL
    assert B.verdict(50.0, 0.9, 0.8, 0.4, False, 0.3) == "KILL"
    assert B.verdict(50.0, None, None, None, True, None) == "DATA-INSUFICIENTE"


def test_boot_diff_muestra_corta_es_none():
    import random
    assert B.boot_diff([1, 0, 1], 0.5, random.Random(1)) == (None, None)
    assert B.boot_diff([1] * 20, None, random.Random(1)) == (None, None)


# ------------------------------------------------------------- utilidades

def test_atomic_write(tmp_path):
    p = str(tmp_path / "x.json")
    B.atomic_write(p, "hola")
    with open(p) as fh:
        assert fh.read() == "hola"
    B.atomic_write(p, "adios")
    with open(p) as fh:
        assert fh.read() == "adios"
    assert [f for f in os.listdir(str(tmp_path)) if ".tmp." in f] == []


def test_expand_days_rango():
    days = B.expand_days("2026-07-30..2026-08-03")
    assert "2026-07-30" in days and "2026-08-03" in days
    assert "2026-07-29" not in days
    assert B.expand_days("2026-08-03") == ["2026-08-03"]


def test_confluence_separa():
    a = {"date": "d", "sym": "QQQ", "ts": 100, "type": "BB_REBOTE"}
    b = {"date": "d", "sym": "QQQ", "ts": 160, "type": "CUSUM_TERREMOTO"}
    c = {"date": "d", "sym": "SPY", "ts": 100, "type": "BB_REBOTE"}
    solo, conf = B.confluence([a, b, c])
    assert [x["sym"] for x in solo] == ["SPY"]
    assert len(conf) == 2


def test_pct():
    assert B._pct([], 0.5) is None
    assert B._pct([1.0, 2.0, 3.0, 4.0], 0.5) == 3.0


# ------------------------------------------------------------- integracion real

@pytest.mark.skipif(not os.path.exists(os.path.join(B.SIGDIR, "2026-08-03.txt")),
                    reason="feed del 2026-08-03 ausente")
def test_parse_day_real_2026_08_03():
    """Parser contra un dia REAL. La fecha NO se clava: `2026-08-03` se trunco a 2,6 KB
    (frente a los 122 KB del 08-04) y el test rojo enmascaraba fallos de verdad. Se toma el
    dia mas reciente con registro completo; si no hay ninguno, se dice por que."""
    import glob
    with open(os.path.join(REPO, "data", "fleet.txt")) as fh:
        fs = set(fh.read().split())
    dias = sorted((os.path.getsize(f), os.path.basename(f)[:-4])
                  for f in glob.glob(os.path.join(REPO, "data", "trading-signals", "2026-*.txt")))
    completos = [d for tam, d in dias if tam > 50_000]
    if not completos:
        pytest.skip(f"sin dia completo en data/trading-signals (mayor: {dias[-1] if dias else 'ninguno'})")
    al = B.parse_day(completos[-1], fs)
    assert len(al) > 300
    tipos = set(a["type"] for a in al)
    assert "ESTRUCTURAL_PIN" in tipos and "BB_REBOTE" in tipos
    for a in al:
        assert a["sym"] in fs
        assert a["dir"] in (-1, 0, 1)
        assert a["type"] != "ESTRUCTURAL_PIN" or a["dir"] == 0
