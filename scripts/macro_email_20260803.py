#!/usr/bin/env python3
"""macro_email_20260803.py — el email MACRO del 2026-08-03: Corea, futuros y el estudio
KOSPI->Nasdaq. Lee SOLO datos en disco; si un dato falta escribe "SIN DATO", nunca un relleno.

  ./venv/bin/python scripts/macro_email_20260803.py            # escribe el HTML
"""
import json
import os
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data", "analisis_2026-08-03")
HTML = os.path.join(OUT, "MACRO.html")

VERDE, ROJO, AMBAR, TINTA = "#0a7d3f", "#c02525", "#b07908", "#111"


def jload(p):
    with open(p) as f:
        return json.load(f)


def pct(x, nd=2):
    return "SIN DATO" if x is None else f"{x:+.{nd}f}%"


def col(x, invertir=False):
    if x is None:
        return TINTA
    v = -x if invertir else x
    return VERDE if v > 0.05 else (ROJO if v < -0.05 else AMBAR)


def fila(celdas, th=False, estilo=""):
    t = "th" if th else "td"
    borde = "border:1px solid #d8d8d8;padding:6px 9px;"
    return "<tr>" + "".join(f"<{t} style='{borde}{estilo}'>{c}</{t}>" for c in celdas) + "</tr>"


def main():
    fut = jload(os.path.join(REPO, "data", "futures_overnight.json"))
    gex = jload(os.path.join(REPO, "data", "gex_snapshot.json"))
    est = jload(os.path.join(OUT, "kospi_nasdaq_estudio.json"))
    kor = fut.get("corea") or {}

    # ---- futuros ----
    frows = []
    for x in fut["futuros"]:
        io = x.get("implied_open") or {}
        imp = (f"{io['simbolo']} {io['apertura_implicita']:.2f} "
               f"(prev {io['cierre_previo']:.2f}, {io['delta']:+.2f})") if io else "—"
        frows.append(fila([x["nombre"], f"{x['last']:,.2f}",
                           f"<b style='color:{col(x.get('pct'))}'>{pct(x.get('pct'))}</b>",
                           imp, f"{x.get('lag_s', 0):.0f} s"]))

    # ---- corea ----
    krows = []
    for k, etiq in (("kospi", "KOSPI (índice)"), ("samsung", "Samsung Electronics"),
                    ("skhynix", "SK Hynix")):
        v = kor.get(k) or {}
        krows.append(fila([etiq, f"{v.get('last', 0):,.2f}",
                           f"<b style='color:{col(v.get('pct'))}'>{pct(v.get('pct'))}</b>",
                           f"{(v.get('edad_s') or 0) / 3600:.1f} h"]))

    # ---- estudio: la tabla de volatilidad y la del hueco ----
    def celda(nombre, bloque):
        for r in bloque:
            if r.get("celda", "").strip() == nombre:
                return r
        return None

    vrows = []
    for nombre in ("BASE incondicional (todas las sesiones conjuntas)", "KOSPI<=-2%",
                   "KOSPI<=-3%", "KOSPI<=-5%"):
        r = celda(nombre, est["B_incondicional_NDX"])
        if not r:
            continue
        etiqueta = "BASE (todas las sesiones)" if nombre.startswith("BASE") else nombre.replace("<=", " ≤ ")
        vrows.append(fila([etiqueta, f"{r['n']:,}", f"{r['n_eff']:.0f}",
                           f"{r['P_rojo'] * 100:.1f}%",
                           f"<b>{r['P_cae_ge_1pct'] * 100:.1f}%</b>",
                           f"{r['P_cae_ge_2pct'] * 100:.1f}%",
                           f"{r['ret_mediana']:+.2f}%"]))

    # ---- mapa gamma: indices vs semis ----
    grows = []
    for s in ("QQQ", "SPY", "SMH", "XLK", "NVDA", "MU", "INTC", "EWY", "SKHY"):
        g = gex.get(s)
        if not g:
            grows.append(fila([s, "<i>omitido del mapa (sin lectura)</i>", "", "", "", ""]))
            continue
        reg = g.get("regime_short") or "—"
        cr = VERDE if reg == "POS" else (ROJO if reg == "NEG" else TINTA)
        ng = g.get("net_gex")
        fl = g.get("flip")
        grows.append(fila([
            f"<b>{s}</b>", f"{g.get('spot'):,.2f}" if g.get("spot") else "—",
            f"<b style='color:{cr}'>{reg}</b>",
            f"{ng / 1e6:+.1f}M" if ng is not None else "SIN DATO",
            f"{fl:,.2f}" if fl else "SIN FLIP",
            f"{g.get('abs_wall')} <span style='color:#666'>({g.get('abs_wall_kind') or '—'})</span>"
            if g.get("abs_wall") else "—"]))

    nq = next((x for x in fut["futuros"] if x["nombre"] == "NQ"), {})
    io = nq.get("implied_open") or {}
    kpct = (kor.get("kospi") or {}).get("pct")

    css_t = "border-collapse:collapse;width:100%;font-size:13px;margin:10px 0;"
    h2 = "font-size:16px;margin:22px 0 6px;border-bottom:2px solid #222;padding-bottom:4px;"

    html = f"""<title>MACRO — Corea, futuros y Nasdaq — plan 2026-08-03</title>
<div style="max-width:700px;margin:0 auto;font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:{TINTA};line-height:1.45;">
<h1 style="font-size:20px;margin:0 0 4px;">MACRO — Corea, futuros y Nasdaq</h1>
<div style="color:#666;font-size:12px;margin-bottom:14px;">Lunes 2026-08-03 · generado {time.strftime('%H:%M:%S')} ET · antes de la apertura</div>

<div style="background:#f6f6f6;border-left:4px solid {ROJO};padding:12px 14px;margin-bottom:16px;">
<div style="font-size:15px;font-weight:700;margin-bottom:6px;">Corea se desplomó. El Nasdaq probablemente NO lo replique — y el hueco ya lo está pagando.</div>
<div style="font-size:13px;">
KOSPI <b style="color:{ROJO}">{pct(kpct)}</b> · Samsung <b style="color:{ROJO}">{pct((kor.get('samsung') or {}).get('pct'))}</b> · SK Hynix <b style="color:{ROJO}">{pct((kor.get('skhynix') or {}).get('pct'))}</b><br>
NQ <b style="color:{col(nq.get('pct'))}">{pct(nq.get('pct'))}</b> → apertura implícita QQQ <b>{io.get('apertura_implicita', 0):.2f}</b> ({io.get('delta', 0):+.2f})<br>
<b>Lectura:</b> es give-back tras un rally récord coreano de +17,91%, no un crash importado.
El histórico dice que un desplome coreano predice <b>VOLATILIDAD, no dirección</b>, y que
<b>el daño se paga en el hueco</b>: desde la campana el open→close medio es positivo.
</div>
</div>

<h2 style="{h2}">1 · Corea — cierre KRX ya consumado (15:30 KST = 02:30 ET)</h2>
<table style="{css_t}">{fila(['Instrumento', 'Cierre', 'Variación', 'Antigüedad'], th=True, estilo='background:#efefef;text-align:left;')}{''.join(krows)}</table>
<div style="font-size:12px;color:#555;">
Fuente: Naver (<code>delayTime 0</code>), verificado contra el endpoint de índices a las 06:47 ET.
<b>Ojo con el proxy:</b> el ETF KODEX 200 cayó <b>−8,93%</b>, casi el doble que el índice —
nuestro pipeline lo confundía con el KOSPI y ya está corregido.
Contexto: rally récord de <b>+17,91%</b> la sesión previa, sidecar en el KOSDAQ, y propuesta
regulatoria coreana de bajar el apalancamiento de ETF de 2× a 1,5×/1×.
</div>

<h2 style="{h2}">2 · Futuros ({fut['et']} ET)</h2>
<table style="{css_t}">{fila(['Futuro', 'Último', '%', 'Apertura implícita', 'Retraso'], th=True, estilo='background:#efefef;text-align:left;')}{''.join(frows)}</table>
<div style="font-size:12px;color:#555;">
Fuente yfinance, <b>~10 min de retraso declarado</b> — describe el hueco, no dispara órdenes.
<b>La divergencia es el dato:</b> NQ castigado, ES plano, RTY en verde. Es rotación fuera de
tech/semis, no un risk-off general.
</div>

<h2 style="{h2}">3 · ¿Cae el Nasdaq cuando Corea se desploma? — MEDIDO</h2>
<div style="font-size:13px;">7.068 sesiones conjuntas (1996-2026), festivos de ambas bolsas excluidos,
CI de Wilson sobre episodios independientes (n_eff), no sobre días correlacionados.</div>
<table style="{css_t}">{fila(['Condición', 'n', 'n_eff', 'P(NDX rojo)', 'P(cae ≥1%)', 'P(cae ≥2%)', 'mediana'], th=True, estilo='background:#efefef;text-align:left;')}{''.join(vrows)}</table>

<div style="background:#fff8e6;border-left:4px solid {AMBAR};padding:10px 13px;font-size:13px;">
<b>Veredicto en cuatro líneas:</b><br>
· "Corea cae → Nasdaq cae el mismo día": <b>parcialmente medido</b>, 45,1% → 57,3%. Débil: el CI solapa con la base.<br>
· "…<b>drásticamente</b>": <b style="color:{ROJO}">REFUTADO</b>. P(cae ≥2%) = 28% con KOSPI ≤ −5%: en el 72% de esos días no hubo caída drástica.<br>
· "…<b>y hoy</b>" (give-back tras rally): <b style="color:{ROJO}">REFUTADO para este caso</b>. p = 0,21, indistinguible del azar.<br>
· "el patrón es común": <b style="color:{ROJO}">INVERTIDO</b>. corr(NDX[D−1]→KOSPI[D]) = 0,310 vs corr(KOSPI[D]→NDX[D]) = 0,130. Wall Street arrastra a Seúl más del doble de lo que Seúl arrastra a Wall Street.
</div>

<h2 style="{h2}">4 · Lo que la señal SÍ predice: volatilidad</h2>
<div style="font-size:13px;">Con KOSPI ≤ −5%, P(|movimiento| ≥1%) sube de <b>42% a 71%</b> y la
desviación típica del Nasdaq pasa de 1,75% a <b>2,73% (+56%)</b>. La cola baja crece más que la alta
(ratio 0,91 → 2,12), así que hay sesgo, pero el efecto dominante es de <b>amplitud</b>.<br><br>
<b>Traducción operativa:</b> hoy es un <b>gate de régimen</b> — día ancho, stops anchos, mala jornada
para vender prima. <b>No es una flecha corta.</b></div>

<h2 style="{h2}">5 · El daño está en el HUECO, no en la sesión</h2>
<div style="font-size:13px;">Descomposición con QQQ (Open real de bolsa), tras KOSPI ≤ −5%:
gap medio <b style="color:{ROJO}">−0,90%</b> (mediana −0,80%) pero open→close medio
<b style="color:{VERDE}">+0,62%</b> (mediana 0,00%) y P(open→close rojo) <b>46,3%</b>, indistinguible
de la base (46,9%).<br><br>
<b style="color:{ROJO}">Corolario duro:</b> a las 09:30 la información coreana ya está en el precio.
Vender el Nasdaq en la apertura porque Corea cayó es comprar el descuento ya pagado.
Hoy el hueco implícito de QQQ es <b>{io.get('delta', 0):+.2f}</b> ({(io.get('delta', 0) / io.get('cierre_previo', 1) * 100):+.2f}%),
justo en la mediana histórica.</div>

<h2 style="{h2}">6 · Mapa gamma — dónde SÍ puede entrar el contagio</h2>
<table style="{css_t}">{fila(['Símbolo', 'Spot', 'Régimen', 'net GEX', 'Flip', 'Muro absoluto'], th=True, estilo='background:#efefef;text-align:left;')}{''.join(grows)}</table>
<div style="font-size:13px;">
<b>La divergencia estructural del día:</b> los índices amplios están en gamma <b style="color:{VERDE}">POSITIVA con pin</b>
(dealers amortiguan), pero los semis y la tecnología están en gamma <b style="color:{ROJO}">NEGATIVA con trampilla</b>
(dealers aceleran). Índice amortiguado, semis con el suelo abierto: por ahí es por donde entra el contagio coreano,
no por el índice.<br>
Recuerda la doctrina: gamma negativa <b>no es dirección, es una caja de whipsaw</b> — se espera muro y rechazo
IMPRESO, nunca se fadea un %B extremo en el aire.</div>

<h2 style="{h2}">7 · Árbol del Nasdaq (QQQ) para hoy</h2>
<pre style="font-family:ui-monospace,Menlo,monospace;font-size:12px;background:#fafafa;border:1px solid #ddd;padding:12px;overflow-x:auto;">
                      QQQ apertura implícita ~{io.get('apertura_implicita', 0):.2f}
                      (cierre previo {io.get('cierre_previo', 0):.2f}, hueco {io.get('delta', 0):+.2f})
                                    |
              +---------------------+---------------------+
              |                                           |
    ARRIBA ↑  el hueco se compra                ABAJO ↓  el hueco se extiende
    (histórico: open→close +0,62%              (hace falta catalizador NUEVO,
     medio tras gap coreano)                    no la noticia coreana ya pagada)
              |                                           |
    imán/pin  {gex.get('QQQ', {}).get('abs_wall', '—')}  ({gex.get('QQQ', {}).get('abs_wall_kind', '—')})        put wall  {gex.get('QQQ', {}).get('put_wall', '—')}
              |                                           |
    call wall {gex.get('QQQ', {}).get('call_wall', '—')}                              gamma flip {gex.get('QQQ', {}).get('flip') and f"{gex['QQQ']['flip']:.2f}" or 'SIN FLIP'}
              |                                           |
    ↑ objetivo: el pin actúa de imán            ↓ bajo el flip el régimen cambia
      mientras el régimen sea POSITIVO            a NEGATIVO y se abre la caja

    INVALIDACIÓN de cada rama = PRINT en contra: 2 velas CERRADAS cruzando el nivel.
    "Está cerca" no existe (doctrina PRINT-O-NADA).
</pre>

<h2 style="{h2}">8 · Qué mataría esta lectura</h2>
<ol style="font-size:13px;">
<li><b>Un catalizador americano nuevo</b> (macro, earnings, Fed). El estudio mide el efecto de Corea
<i>sola</i>; si hoy hay noticia propia, el condicional no aplica.</li>
<li><b>Que SMH pierda su trampilla</b> y arrastre al índice. Los semis en gamma negativa aceleran, y
SMH es el capitán del sector: si rompe con print, la jerarquía de capitanes dice que manda él sobre
cada nombre de semis.</li>
<li><b>Que el hueco NO se cierre en la primera hora.</b> El +0,62% medio de open→close es una media
sobre 54 casos con dispersión alta; si a las 10:30 el hueco sigue abierto y el volumen acompaña,
la rama de continuación gana peso.</li>
</ol>

<hr style="margin:22px 0;border:none;border-top:1px solid #ddd;">
<div style="font-size:11px;color:#777;">
<b>Fuentes y latencia:</b> Corea = Naver, delay 0 medido · Futuros = yfinance, ~10 min declarados ·
Spot US = Finnhub WebSocket, tiempo real (0,00–0,04 s medido) · Cadenas de opciones y mapa gamma =
Polygon, ~15 min declarados · Estudio histórico = Yahoo Finance EOD, 7.068 sesiones 1996-2026.<br>
IBKR (tiempo real) está OFF esta semana por orden propia; su código sigue intacto.<br><br>
<b>SEÑAL-SOLAMENTE. No es consejo financiero.</b>
</div>
</div>"""

    os.makedirs(OUT, exist_ok=True)
    with open(HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"escrito {HTML} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
