"""Tests de las noticias de la flota: dedup 24 h, filtro de ruido, enrutado y publicacion.

Cero red: ninguna fuente se llama de verdad y ningun POST sale a Discord. Un test que
publicara de verdad llenaria #noticias-flota cada vez que corre la suite.
"""
import importlib.util
import json
import os
import sys
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def _load(name):
    path = os.path.join(SCRIPTS, name + ".py")
    spec = importlib.util.spec_from_file_location("ibt_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


NS = _load("news_store")
FN = _load("fleet_news_watch")
L = _load("discord_layout")


@pytest.fixture
def store(tmp_path):
    return NS.Store(str(tmp_path / "news_seen.json"))


# --- dedup -------------------------------------------------------------------------------
def test_mismo_titular_no_se_repite(store):
    it = [("Nvidia beats earnings and raises guidance", "https://x.com/a")]
    assert len(store.filter_new(it)) == 1
    assert store.filter_new(it) == []


def test_dedup_cruza_fuentes_con_titulo_distinto(store):
    """La misma nota por Yahoo y por Reuters: el sufijo del publisher no la hace nueva."""
    store.filter_new([("Nvidia stock rises, as Musk says SpaceX will use its chips - Yahoo Finance",
                       "https://finance.yahoo.com/news/a")])
    otra = [("Nvidia stock rises as Musk says SpaceX will use its chips",
             "https://reuters.com/tech/b")]
    assert store.filter_new(otra) == [], "el titulo normalizado deberia colisionar"


def test_dedup_por_url_ignora_query(store):
    store.filter_new([("Titular cualquiera de prueba largo", "https://fool.com/x?source=ied")])
    assert store.filter_new([("Otro titular completamente distinto aqui",
                              "https://www.fool.com/x/")]) == []


def test_url_de_google_news_no_sirve_de_clave():
    """Los enlaces de Google News son redirecciones unicas: usarlos como clave rompe el dedup."""
    assert NS.canon_url("https://news.google.com/rss/articles/CBMiXYZ") is None


def test_dos_titulares_distintos_no_colisionan(store):
    a = [("Micron sinks 31 percent after guidance cut", None)]
    b = [("Micron jumps 6 percent as DRAM market share expands", None)]
    assert len(store.filter_new(a)) == 1
    assert len(store.filter_new(b)) == 1


def test_dedup_dentro_del_mismo_lote(store):
    lote = [("La misma noticia repetida en el lote", "https://a.com/1"),
            ("La misma noticia repetida en el lote", "https://a.com/1")]
    assert len(store.filter_new(lote)) == 1


def test_ttl_24h_borra_lo_viejo(store):
    store.filter_new([("Noticia de ayer que ya no importa", None)])
    assert len(store.load()) >= 1
    assert store.load(time.time() + 25 * 3600) == {}, "nada puede sobrevivir 24 h"


def test_ttl_no_borra_lo_de_hace_23h(store):
    store.filter_new([("Noticia de hace veintitres horas justas", None)])
    assert len(store.load(time.time() + 23 * 3600)) >= 1


def test_store_ilegible_no_revienta_y_avisa(tmp_path, capsys):
    p = tmp_path / "roto.json"
    p.write_text("{esto no es json")
    s = NS.Store(str(p))
    assert s.load() == {}
    assert "ilegible" in capsys.readouterr().err


def test_titular_sin_identidad_no_se_publica(store):
    assert store.filter_new([("", None), (None, None)]) == []


# --- filtro de ruido ----------------------------------------------------------------------
@pytest.mark.parametrize("titulo,fuente", [
    ("Uncover the latest developments among dow jones stocks in today's session.", "ChartMill"),
    ("NVIDIA Corp Stock (NVDA) Moved Up by 4.31% on Aug 5: What Investors Need To Know",
     "TradingKey"),
    ("Top movers Wednesday: AMD, NVDA and more", "Seeking Alpha"),
    ("3 reasons to buy Micron stock now", "The Motley Fool"),
    ("Should you buy NVDA stock today?", "Zacks"),
])
def test_ruido_de_agregador_se_filtra(titulo, fuente):
    malo, motivo = FN.es_ruido({"title": titulo, "source": fuente})
    assert malo, "deberia filtrarse: %s" % titulo


@pytest.mark.parametrize("titulo,fuente", [
    ("Micron cuts fourth-quarter guidance on weaker DRAM pricing", "Reuters"),
    ("SpaceX Stock Dives. Analysts React To Earnings Beat, Shift Price Targets.",
     "Investor's Business Daily"),
    ("US expands export controls on advanced memory chips to China", "Bloomberg"),
])
def test_noticia_real_no_se_filtra(titulo, fuente):
    malo, motivo = FN.es_ruido({"title": titulo, "source": fuente})
    assert not malo, "no deberia filtrarse (%s): %s" % (motivo, titulo)


def test_catalizador_se_marca_en_rojo():
    assert FN.impacto({"title": "Micron cuts guidance after earnings"}) == "🔴"
    assert FN.impacto({"title": "Nvidia shares drift in quiet trading session"}) == "📰"
    assert FN.impacto({"title": "cualquier cosa", "major": True}) == "🔴"


# --- fechas -------------------------------------------------------------------------------
def test_fecha_ilegible_devuelve_none_no_ahora():
    """Un ts inventado a 'ahora' publicaria noticias rancias como frescas."""
    assert FN._iso_ts("no es una fecha") is None
    assert FN._iso_ts(None) is None
    assert FN._rfc822_ts("basura") is None
    assert abs(FN._iso_ts("2026-08-05T17:23:25Z") - 1785950605.0) < 1.0


# --- publicacion --------------------------------------------------------------------------
def test_embeds_uno_por_simbolo_y_tope_por_simbolo():
    ahora = time.time()
    por_sym = {"NVDA": [{"title": "Titular numero %d de nvidia aqui" % i, "url": None,
                         "ts": ahora - i * 60, "source": "Reuters"} for i in range(6)],
               "MU": [{"title": "Micron corta guia tras resultados", "url": None,
                       "ts": ahora, "source": "Bloomberg"}]}
    emb = FN.build_embeds(por_sym, ahora, max_sym=3)
    assert len(emb) == 2
    nvda = next(e for e in emb if "NVDA" in e["title"])
    assert nvda["description"].count("\n`") == 3, "tope de 3 titulares por simbolo"


def test_publicar_sin_webhook_no_finge_exito():
    env, fallos = FN.publicar([{"title": "x"}], hooks={})
    assert env == 0 and fallos and "sin webhook" in fallos[0]


def test_publicar_agrupa_en_tandas_de_10(monkeypatch):
    llamadas = []
    monkeypatch.setattr(FN.S, "_post", lambda url, body, hdr: (llamadas.append(
        json.loads(body.decode())) or (True, None)))
    embeds = [{"title": "e%d" % i, "description": "x"} for i in range(23)]
    monkeypatch.setattr(FN.time, "sleep", lambda s: None)
    env, fallos = FN.publicar(embeds, hooks={FN.CANAL: "https://discord.com/api/webhooks/1/x"})
    assert env == 23 and not fallos
    assert [len(c["embeds"]) for c in llamadas] == [10, 10, 3]
    assert all(c["allowed_mentions"]["parse"] == [] for c in llamadas), "jamas @everyone"


# --- integracion con el layout -------------------------------------------------------------
def test_canal_de_noticias_existe_y_tiene_webhook_declarado():
    assert FN.CANAL in L.all_channel_keys()
    assert FN.CANAL in L.webhook_channels()


def test_una_noticia_no_se_va_al_canal_de_earnings():
    ch, _ = L.classify("📰 NVDA | Nvidia beats earnings and raises guidance")
    assert ch == "noticias-flota"


def test_las_noticias_de_asia_siguen_en_su_pais():
    """La regla nueva no puede robarle los titulares a #taiwan-japon ni a #china-semis."""
    assert L.classify("🇹🇼 NOTICIA SEMIS | TSMC July revenue")[0] == "taiwan-japon"
    assert L.classify("🇨🇳 NOTICIA SEMIS | CXMT expands DRAM")[0] == "china-semis"
    assert L.classify("🇰🇷 NOTICIA | Samsung guidance")[0] == "corea-overnight"


def test_fuente_rota_no_inventa_titulares(monkeypatch):
    """Si una fuente revienta se dice; nunca se devuelve lista vacia como si fuera exito."""
    monkeypatch.setattr(FN.dc, "secret", lambda n: "clave-falsa")

    def revienta(*a, **k):
        raise urllib_error()

    def urllib_error():
        import urllib.error
        return urllib.error.URLError("sin red")

    monkeypatch.setattr(FN, "src_uw", revienta)
    items, rotas = FN.recolectar(["NVDA"], 3600, {"uw"})
    assert items == [] and rotas and "uw" in rotas[0]
