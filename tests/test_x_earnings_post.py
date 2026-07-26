"""x_earnings_post: el calendario de earnings de la semana que viene (PNG + 1 tweet).

Las filas de abajo son REALES, copiadas del export de Finviz Elite del 2026-07-25/26
(v=171 tecnicos, v=152 short float / vol relativo / `Earnings Date` con hora). SKHY va
a proposito: es un ADR reciente y Finviz lo sirve SIN Beta y SIN RSI -> tiene que salir
en la rejilla (su fecha SI esta medida) y quedarse SIN escalera, jamas con un 0 relleno.
"""
import importlib.util
import os
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

import x_post_common as xc  # noqa: E402


def _load():
    path = os.path.join(REPO, "scripts", "x_earnings_post.py")
    spec = importlib.util.spec_from_file_location("ibt_x_earnings_post", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


M = _load()
FLEET = {"AAPL", "STX", "SKHY", "MSFT", "META", "QCOM", "LRCX", "AMZN", "QQQ", "SPY"}
REF = datetime(2026, 7, 26)          # sabado; la semana que viene = 27-31 jul

H171 = ("No.", "Ticker", "Beta", "Average True Range",
        "20-Day Simple Moving Average", "50-Day Simple Moving Average",
        "200-Day Simple Moving Average", "52-Week High", "52-Week Low",
        "Relative Strength Index (14)", "Price", "Change", "Change from Open",
        "Gap", "Volume")
H152 = ("Ticker", "Short Float", "Relative Volume", "Price", "Earnings Date")

ROWS171 = [
    dict(zip(H171, ("2", "AAPL", "1.07", "8.26", "5.93%", "8.75%", "20.67%",
                    "-0.59%", "65.27%", "65.23", "333.02", "3.53%", "3.49%",
                    "0.04%", "47489415"))),
    dict(zip(H171, ("652", "STX", "2.09", "74.41", "-2.07%", "-4.03%", "69.10%",
                    "-25.62%", "515.83%", "47.77", "851.69", "-6.75%", "-3.13%",
                    "-3.74%", "5226252"))),
    dict(zip(H171, ("626", "SKHY", "", "19.91", "-6.04%", "-6.04%", "-6.04%",
                    "-20.65%", "6.18%", "", "154.57", "-8.81%", "-5.70%",
                    "-3.30%", "26255531"))),
    dict(zip(H171, ("96", "BE", "3.82", "28.43", "-24.42%", "-31.49%", "4.85%",
                    "-47.37%", "518.36%", "36.11", "184.89", "-14.91%",
                    "-13.68%", "-1.43%", "16017691"))),
]
ROWS152 = [
    dict(zip(H152, ("AAPL", "1.00%", "0.86", "333.02", "7/30/2026 4:30:00 PM"))),
    dict(zip(H152, ("STX", "3.28%", "1.13", "851.69", "7/28/2026 4:30:00 PM"))),
    dict(zip(H152, ("SKHY", "", "0.45", "154.57", "7/28/2026 4:30:00 PM"))),
    dict(zip(H152, ("BE", "7.20%", "1.29", "184.89", "7/28/2026 4:30:00 PM"))),
]


def _merged():
    m = M.merge(ROWS171, ROWS152, today=REF)
    assert m is not None
    return m


# --- (b) BMO/AMC salen de la HORA, no de una suposicion -----------------------
def test_bmo_desde_8_30_am():
    assert M.parse_earn("7/30/2026 8:30:00 AM")[1] == "BMO"


def test_amc_desde_4_30_pm():
    assert M.parse_earn("7/30/2026 4:30:00 PM")[1] == "AMC"


def test_mediodia_en_punto_es_amc():
    assert M.parse_earn("7/30/2026 12:00:00 PM")[1] == "AMC"


def test_las_11_59_am_es_bmo():
    assert M.parse_earn("7/30/2026 11:59:00 AM")[1] == "BMO"


def test_la_fecha_tambien_se_devuelve():
    date_s, sess, dt = M.parse_earn("7/28/2026 4:30:00 PM")
    assert (date_s, sess, dt.weekday()) == ("2026-07-28", "AMC", 1)   # martes


def test_sin_hora_no_se_adivina_sesion():
    assert M.parse_earn("7/30/2026") is None


def test_fecha_basura_es_none():
    for bad in ("", None, "manana", "30/07/2026 8:30:00 AM"):
        assert M.parse_earn(bad) is None


def test_fila_sin_hora_queda_fuera_de_la_rejilla():
    rows152 = [dict(r) for r in ROWS152]
    rows152[0]["Earnings Date"] = "7/30/2026"
    m = M.merge(ROWS171, rows152, today=REF)
    assert "AAPL" not in m and "STX" in m


def test_fecha_pasada_o_lejana_queda_fuera():
    rows152 = [dict(r) for r in ROWS152]
    rows152[0]["Earnings Date"] = "6/24/2026 4:30:00 PM"      # MU real de junio
    rows152[1]["Earnings Date"] = "9/30/2026 4:30:00 PM"
    m = M.merge(ROWS171, rows152, today=REF)
    assert "AAPL" not in m and "STX" not in m and "SKHY" in m


# --- (c) sin datos de Finviz NO se genera nada --------------------------------
def test_merge_sin_datos_es_none():
    assert M.merge(None, None) is None
    assert M.merge([], ROWS152) is None
    assert M.merge(ROWS171, []) is None


def test_parse_csv_de_html_de_login_es_none():
    assert M.parse_csv("<html>login</html>") is None
    assert M.parse_csv("") is None
    assert M.parse_csv(None) is None


def test_sin_datos_no_hay_texto():
    assert M.build_tweet_text(None, FLEET) is None
    assert M.build_tweet_text({}, FLEET) is None


def test_sin_datos_no_hay_png(tmp_path):
    out = tmp_path / "nada.png"
    assert M.render_calendar(None, FLEET, str(out)) is None
    assert not out.exists()


def test_sin_fleet_no_se_prioriza_a_ciegas(tmp_path):
    assert M.build_tweet_text(_merged(), None) is None
    assert M.render_calendar(_merged(), None, str(tmp_path / "x.png")) is None


def test_fleet_syms_none_si_falta_el_fichero(tmp_path):
    assert M.fleet_syms(str(tmp_path / "no_existe.txt")) is None


def test_num_nunca_fabrica_cero():
    assert M.num("") is None and M.num("-") is None and M.num(None) is None
    assert M.num("3.53%") == 3.53 and M.num("-6.75%") == -6.75
    assert M.num("47,489,415") == 47489415.0


# --- tecnicos incompletos: tile si, escalera no -------------------------------
def test_skhy_sale_en_rejilla_sin_tecnicos():
    r = _merged()["SKHY"]
    assert r["tech"] is False
    assert r["sess"] == "AMC" and r["date"] == "2026-07-28"
    assert M.ladder(r) == [] and M.picaro_bits(r) == []
    assert r["sma20"] is None and r["atr_pct"] is None      # None, jamas 0.0


def test_sin_tecnicos_solo_puntua_el_bono_de_flota():
    m = _merged()
    assert M.score(m["SKHY"], FLEET) == 25.0
    assert M.score(m["AAPL"], FLEET) > 25.0


def test_las_escaleras_solo_las_arman_filas_con_tecnicos():
    assert all(r["tech"] for r in M.rank_ladders(_merged(), FLEET))


# --- escalera: descendente, roles correctos, niveles medidos -------------------
def test_escalera_estrictamente_descendente():
    for r in M.rank_ladders(_merged(), FLEET):
        vals = [v for _, v in M.ladder(r)]
        assert vals == sorted(vals, reverse=True)
        assert len(vals) == len(set(vals))


def test_escalera_lleva_el_spot_y_la_valla_atr():
    r = _merged()["AAPL"]
    rungs = dict((e, v) for e, v in M.ladder(r))
    assert abs(rungs["📍"] - 333.02) < 1e-6                  # spot medido
    assert abs(rungs["🔴"] - (333.02 + 8.26)) < 1e-6         # techo = precio + ATR
    assert abs(rungs["🟢"] - (333.02 - 8.26)) < 1e-6         # AAPL no tiene SMA a <=2 ATR


def test_cada_peldano_tiene_color_de_su_rol():
    for r in M.rank_ladders(_merged(), FLEET):
        for emo, _ in M.ladder(r):
            assert emo in M.LADDER_DOTS


def test_sma20_se_reconstruye_desde_la_distancia():
    r = _merged()["AAPL"]
    assert abs(r["sma20"] - 333.02 / 1.0593) < 0.01


# --- (a) y (d) el TEXTO del tweet ---------------------------------------------
def test_texto_maximo_un_cashtag():
    text = M.build_tweet_text(_merged(), FLEET, quip_seed=7)
    assert xc.count_cashtags(text) <= 1
    assert xc.count_cashtags(xc.sanitize_cashtags(text)) <= 1


def test_texto_un_cashtag_con_cualquier_quip():
    m = _merged()
    for seed in range(len(M.QUIPS) * 3):
        text = M.build_tweet_text(m, FLEET, quip_seed=seed)
        assert text is not None
        assert xc.count_cashtags(text) <= 1, text
        assert len(text) <= xc.MAX_CHARS, (len(text), text)


def test_texto_dentro_del_limite_de_x():
    text = M.build_tweet_text(_merged(), FLEET, quip_seed=3)
    assert 0 < len(text) <= xc.MAX_CHARS


def test_texto_lleva_el_aviso_y_no_recomienda_comprar():
    text = M.build_tweet_text(_merged(), FLEET, quip_seed=1).lower()
    assert "no es consejo financiero" in text
    for prohibido in ("compra ", "comprar ahora", "vende ", "garantiz"):
        assert prohibido not in text


def test_texto_sin_urls():
    text = M.build_tweet_text(_merged(), FLEET, quip_seed=2)
    assert "http" not in text and "www." not in text


def test_texto_cuenta_lo_medido():
    m = _merged()
    text = M.build_tweet_text(m, FLEET, quip_seed=4)
    assert f"{len(m)} empresas" in text
    assert f"{len([s for s in m if s in FLEET])} son de la flota" in text


# --- (e) y (f) el PNG ---------------------------------------------------------
def test_png_se_genera_y_no_esta_vacio(tmp_path):
    out = tmp_path / "cal.png"
    got = M.render_calendar(_merged(), FLEET, str(out))
    assert got == str(out) and out.exists()
    assert out.stat().st_size > 10000
    with open(out, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    assert not (tmp_path / "cal.png.tmp.png").exists()      # escritura atomica


def test_la_flota_sale_destacada_en_los_tiles(tmp_path, monkeypatch):
    seen = {}
    real = M._tile

    def spy(ax, x, y, w, h, label, is_fleet, muted=False):
        seen[label] = is_fleet
        return real(ax, x, y, w, h, label, is_fleet, muted=muted)

    monkeypatch.setattr(M, "_tile", spy)
    M.render_calendar(_merged(), FLEET, str(tmp_path / "cal.png"))
    for sym in ("AAPL", "STX", "SKHY"):
        assert seen.get(sym) is True, (sym, seen)
    assert seen.get("BE") is False


def test_los_destacados_tienen_color_distinto():
    assert M.C_FLEET != M.C_TILE
    assert M.C_FLEET_EDGE != M.C_TILE_TXT
    assert M.C_FLEET_TXT != M.C_TILE_TXT


def test_el_png_no_usa_logos_de_empresa(tmp_path):
    """Sin imagenes externas: el render es 100% texto+formas (marca registrada ajena)."""
    src = open(os.path.join(REPO, "scripts", "x_earnings_post.py")).read()
    for prohibido in ("imread", "AnnotationBbox", "OffsetImage", "figimage"):
        assert prohibido not in src


def test_el_log_cuenta_para_el_cap_diario_compartido():
    """Sin esto, este poster se saltaria el cap de 10/dia de los otros."""
    assert any(p.endswith("x_earnings_post.log") for p in xc.POSTER_LOGS)
