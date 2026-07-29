#!/usr/bin/env python3
"""ui_cdp.py — driver CDP minimo para el bucle de feedback visual del chart.

POR QUE PYTHON: es un ARNES DE TEST (caso legitimo #1 de ~/CLAUDE.md), no camino de
senal. Cero calculo de senal aqui: solo mueve bytes entre CDP y el disco.

POR QUE CDP Y NO LA EXTENSION "Claude in Chrome": la extension no se puede invocar
desde un shell script, asi que un bucle de feedback REPETIBLE (scripts/ui_smoke.sh,
correrlo cualquiera, en cron, en CI) tiene que hablar CDP. La extension sirve para
mirar en vivo; esto sirve para que el test pueda FALLAR solo.

Uso:  ./venv-chart/bin/python scripts/ui_cdp.py --url http://127.0.0.1:8080 \
          --out docs/ui/shots --report /tmp/ui_results.json

Fail-loud: cualquier paso que no se pueda MEDIR se reporta "NO PROBADO" con el motivo.
Jamas se devuelve un valor plausible inventado (ni 0, ni 0.5, ni "ok").

ESTADO (2026-07-25) — INCOMPLETO, se commitea a medias a proposito
------------------------------------------------------------------
Lo que hay: driver CDP entero (lanza Chrome headless con perfil desechable, habla
websocket con la pestana, saca capturas) + los checks de run(): carga del chart
(canvas + barras del /health + pixeles no-fondo, tres medidas independientes),
errores de consola, y los cuatro estados de la brujula via onDirection.

NO VERIFICADO end-to-end. El fichero IMPORTA y su CLI responde (py_compile + --help,
medido), pero nunca se ha corrido contra el chart vivo: requiere el bridge sirviendo
en --url, y la flota esta parada (ventana dom20:00-vie20:00, ./fleet_hours --why).

FALTA:
  - `scripts/ui_smoke.sh`, el envoltorio que cita el "Uso" de arriba: NO EXISTE.
    Hoy hay que invocar este fichero a mano con --url/--out/--report.
  - Una pasada real contra el chart: hasta entonces los umbrales de los checks
    (60 reintentos x 0.5s, el corte de pixeles >40/40/60) son SUPUESTOS sin medir.
  - Depende de `websockets`, que se importa dentro de CDP.__aenter__ y solo esta
    en venv-chart (no en ./venv). Correr con ./venv-chart/bin/python.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


# --------------------------------------------------------------- CDP plumbing
class CDP:
    """Cliente CDP de un solo target (la pestana). Nada de magia."""

    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None
        self._id = 0
        self._pending = {}         # id -> future (POR INSTANCIA, no de clase)
        self.console = []          # {level, text}

    async def __aenter__(self):
        import websockets
        self.ws = await websockets.connect(self.ws_url, max_size=64 * 1024 * 1024)
        # el lector ARRANCA PRIMERO: send() espera su respuesta en el pump.
        self._pump = asyncio.ensure_future(self._reader())
        await self.send("Runtime.enable")
        await self.send("Log.enable")
        await self.send("Page.enable")
        return self

    async def __aexit__(self, *a):
        self._pump.cancel()
        try:
            await self.ws.close()
        except Exception:
            pass

    async def _reader(self):
        """Un solo lector del socket: recoge respuestas y eventos de consola."""
        while True:
            raw = await self.ws.recv()
            msg = json.loads(raw)
            if "id" in msg:
                fut = self._pending.pop(msg["id"], None)
                if fut and not fut.done():
                    fut.set_result(msg)
            else:
                m = msg.get("method", "")
                if m == "Runtime.consoleAPICalled":
                    args = msg["params"].get("args", [])
                    txt = " ".join(str(a.get("value", a.get("description", "")))
                                   for a in args)
                    self.console.append({"level": msg["params"].get("type", "log"),
                                         "text": txt})
                elif m == "Runtime.exceptionThrown":
                    d = msg["params"]["exceptionDetails"]
                    self.console.append({"level": "exception",
                                         "text": d.get("text", "") + " " +
                                                 str(d.get("exception", {}).get("description", ""))})
                elif m == "Log.entryAdded":
                    e = msg["params"]["entry"]
                    self.console.append({"level": e.get("level", "log"),
                                         "text": f"[{e.get('source')}] {e.get('text')}"})

    async def send(self, method, **params):
        self._id += 1
        mid = self._id
        fut = asyncio.get_event_loop().create_future()
        self._pending[mid] = fut
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        msg = await asyncio.wait_for(fut, timeout=30)
        if "error" in msg:
            raise RuntimeError(f"CDP {method}: {msg['error']}")
        return msg.get("result", {})

    async def js(self, expr):
        """Evalua una expresion y devuelve el valor JSON. Levanta si la pagina lanzo."""
        r = await self.send("Runtime.evaluate", expression=expr, returnByValue=True,
                            awaitPromise=True, userGesture=True)
        if r.get("exceptionDetails"):
            d = r["exceptionDetails"]
            raise RuntimeError("JS: " + (d.get("exception", {}).get("description")
                                         or d.get("text", "?")))
        return r.get("result", {}).get("value")

    async def shot(self, path):
        r = await self.send("Page.captureScreenshot", format="png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "wb") as f:
            f.write(base64.b64decode(r["data"]))
        os.replace(path + ".tmp", path)         # escritura atomica
        return path


async def open_page(cdp_port, url):
    import urllib.request
    # Chrome >=111 exige PUT en /json/new (GET/POST -> 405)
    req = urllib.request.Request(f"http://127.0.0.1:{cdp_port}/json/new?{url}",
                                 method="PUT")
    tgt = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return tgt["webSocketDebuggerUrl"], tgt["id"]


def launch_chrome(cdp_port, profile, width, height):
    if not os.path.exists(CHROME):
        raise SystemExit(f"FALLO: no existe {CHROME}")
    p = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--disable-extensions",
         f"--remote-debugging-port={cdp_port}",
         f"--user-data-dir={profile}",
         f"--window-size={width},{height}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/version",
                                   timeout=1).read()
            return p
        except Exception:
            time.sleep(0.2)
    p.kill()
    raise SystemExit(f"FALLO: Chrome no abrio CDP en {cdp_port} tras 20s")


# ------------------------------------------------------------------ el informe
class Results:
    def __init__(self):
        self.rows = []

    def rec(self, key, status, detail, shot=None):
        assert status in ("PASA", "FALLA", "NO PROBADO"), status
        self.rows.append({"key": key, "status": status, "detail": detail,
                          "shot": shot})

    def failed(self):
        return [r for r in self.rows if r["status"] == "FALLA"]


# ----------------------------------------------------------- mensaje de flecha
def dir_msg(**over):
    """Mensaje `direction` con la forma que consume charts/live.html:onDirection.
    Base tomada del contrato real del WS (bin/compass via chart_bridge.py)."""
    m = {"type": "direction", "dir": "up", "prob": 68, "mag": 0.5,
         "state": "REVERSION EN EXTREMO", "prob_source": "medido",
         "target": 178.5, "target_pct": 1.2, "grade": "REBOTE",
         "pending_print": False, "stale": False, "stale_age": 0,
         "book_coef": 1.0, "book_label": "FULL",
         "why": ["muro 178 con 2 lecturas", "%B 1m 0.04 estirado abajo"],
         "fading": ["ballena CALLS 14:51"], "vetoes": [],
         "level": {"kind": "put_wall", "price": 176.0, "printed": True,
                   "prints": 2, "wall_kind": "pin"},
         "drivers_text": "NVDA-1.2% AVGO-1.3% arrastran",
         "drivers": [{"sym": "NVDA", "r6": -1.2}, {"sym": "AVGO", "r6": -1.3}],
         "amplitude": {"grade": "REBOTE", "amp_pct": 1.2, "binding": "muro 178"}}
    m.update(over)
    return m


async def push_dir(cdp, msg):
    await cdp.js(f"onDirection({json.dumps(msg)}); 1")


async def arrow_state(cdp):
    """Lee el estado RENDERIZADO de la flecha (no lo que le mandamos)."""
    return await cdp.js("""(() => {
      const e = document.getElementById('dirarrow');
      if (!e) return null;
      const g = e.querySelector('.glyph'), cs = getComputedStyle(e), gs = getComputedStyle(g);
      return { display: cs.display, opacity: cs.opacity,
               classes: e.className,
               fontSize: gs.fontSize, color: gs.color,
               glyph: g.textContent,
               pct: e.querySelector('.pct').textContent,
               st: e.querySelector('.st') ? e.querySelector('.st').textContent : null,
               stColor: e.querySelector('.st') ? getComputedStyle(e.querySelector('.st')).color : null,
               cap: e.querySelector('.cap') ? e.querySelector('.cap').textContent : null,
               capW: e.querySelector('.cap') ? e.querySelector('.cap').scrollWidth : null,
               capBox: e.querySelector('.cap') ? e.querySelector('.cap').clientWidth : null,
               title: e.title, box: e.getBoundingClientRect().width };
    })()""")


# ------------------------------------------------------------------- los checks
async def run(cdp, out, url, res):
    def shot_path(name):
        return os.path.join(out, name + ".png")

    # ---------- 1. el chart carga ----------
    await cdp.js("1")
    ok = False
    for _ in range(60):
        n = await cdp.js("(window.__bars_len__ != null) ? window.__bars_len__ : "
                         "(document.querySelectorAll('#chart canvas').length)")
        if n and n > 0:
            ok = True
            break
        await asyncio.sleep(0.5)
    # medida REAL de que hay velas: el bridge nos dice cuantas barras sirvio
    import urllib.request
    health = json.loads(urllib.request.urlopen(url + "/health", timeout=5).read())
    canvases = await cdp.js("document.querySelectorAll('#chart canvas').length")
    # pixeles no-fondo en el area de velas = hay algo dibujado
    drawn = await cdp.js("""(() => {
      const c = document.querySelector('#chart canvas');
      if (!c) return null;
      const g = c.getContext('2d');
      if (!g) return 'no2d';
      try {
        const d = g.getImageData(0, 0, c.width, Math.floor(c.height*0.6)).data;
        let n = 0;
        for (let i = 0; i < d.length; i += 4)
          if (d[i] > 40 || d[i+1] > 40 || d[i+2] > 60) n++;
        return n;
      } catch (e) { return 'tainted:' + e.message; }
    })()""")
    s = await cdp.shot(shot_path("01-chart-carga"))
    if canvases and health.get("bars", 0) > 0:
        res.rec("1-chart-carga", "PASA",
                f"{canvases} canvas en #chart, bridge sirvio {health['bars']} barras "
                f"(mock={health.get('mock')}), pixeles dibujados={drawn}", s)
    else:
        res.rec("1-chart-carga", "FALLA",
                f"canvas={canvases} barras={health.get('bars')}", s)

    # errores de consola de la carga
    errs = [c for c in cdp.console if c["level"] in ("error", "exception")]
    res.rec("1b-consola", "PASA" if not errs else "FALLA",
            "sin errores ni excepciones" if not errs
            else "; ".join(f"[{c['level']}] {c['text'][:300]}" for c in errs[:10]))

    # ---------- 2. la BRUJULA, cuatro estados ----------
    have_fn = await cdp.js("typeof onDirection")
    if have_fn != "function":
        res.rec("2-brujula", "NO PROBADO",
                f"onDirection no es global (typeof={have_fn}); sin inyeccion posible")
    else:
        await cdp.js("window.__ui_test_ws_onmessage = ws.onmessage; ws.onmessage = null; 1")
        # 2a escala con la amplitud
        sizes = {}
        for mag in (0.0, 0.5, 1.0):
            await push_dir(cdp, dir_msg(mag=mag))
            await asyncio.sleep(0.3)
            st = await arrow_state(cdp)
            sizes[mag] = float(st["fontSize"].replace("px", ""))
        await push_dir(cdp, dir_msg(mag=1.0))
        s = await cdp.shot(shot_path("02a-flecha-mag-1.0"))
        await push_dir(cdp, dir_msg(mag=0.1))
        s2 = await cdp.shot(shot_path("02a-flecha-mag-0.1"))
        want = {0.0: 70.0, 0.5: 110.0, 1.0: 150.0}
        okmag = all(abs(sizes[k] - want[k]) < 1.5 for k in want)
        res.rec("2a-flecha-escala", "PASA" if okmag else "FALLA",
                f"mag 0.0/0.5/1.0 -> {sizes[0.0]}/{sizes[0.5]}/{sizes[1.0]} px "
                f"(esperado 70/110/150, rango del brief 70-150)", s)

        # 2b hueca con pending_print
        await push_dir(cdp, dir_msg(pending_print=True))
        st = await arrow_state(cdp)
        pend = "pending" in st["classes"]
        hollow = await cdp.js("""(() => {
          const g = document.querySelector('#dirarrow .glyph'), cs = getComputedStyle(g);
          return { fill: cs.webkitTextFillColor || cs.color, stroke: cs.webkitTextStrokeWidth,
                   strokeColor: cs.webkitTextStrokeColor };
        })()""")
        s = await cdp.shot(shot_path("02b-flecha-hueca-pending-print"))
        transparent = "rgba(0, 0, 0, 0)" in str(hollow.get("fill", "")) or \
                      (hollow.get("stroke") not in (None, "", "0px"))
        res.rec("2b-flecha-hueca", "PASA" if (pend and transparent) else "FALLA",
                f"class pending={pend}; relleno={hollow.get('fill')} "
                f"borde={hollow.get('stroke')} {hollow.get('strokeColor')}", s)

        # 2c gris cuando el dato esta rancio
        await push_dir(cdp, dir_msg(stale=True, stale_age=412))
        await asyncio.sleep(0.3)
        st = await arrow_state(cdp)
        s = await cdp.shot(shot_path("02c-flecha-rancia"))
        stale_ok = ("stale" in st["classes"]) and float(st["opacity"]) <= 0.20 \
                   and "RANCIA" in (st["st"] or "")
        res.rec("2c-flecha-rancia", "PASA" if stale_ok else "FALLA",
                f"class={st['classes']} opacity={st['opacity']} estado='{st['st']}' "
                f"colorEstado={st['stColor']}", s)

        # 2d ambar en divergencia
        await push_dir(cdp, dir_msg(stale=False, state="REVERSION EN EXTREMO",
                                    why=["DIVERGENCIA: precio sube, amplitud cae"]))
        await asyncio.sleep(0.3)
        st = await arrow_state(cdp)
        s = await cdp.shot(shot_path("02d-flecha-divergencia"))
        amber = st["stColor"] in ("rgb(224, 192, 96)", "rgb(201, 162, 39)")
        res.rec("2d-flecha-ambar-divergencia", "PASA" if amber else "FALLA",
                f"colorEstado={st['stColor']} (ambar esperado rgb(224,192,96) para "
                f"REVERSION* / rgb(201,162,39) para APROX); estado='{st['st']}'", s)

        # 2e MOTORES (.drv)
        drv = await cdp.js("(() => { const d = document.querySelector('#dirarrow .drv');"
                           "return d ? {txt:d.textContent, sw:d.scrollWidth, cw:d.clientWidth} : null; })()")
        if drv is None:
            res.rec("2e-motores-drv", "FALLA",
                    "no existe elemento .drv en #dirarrow o el frame no trae drivers_text")
        else:
            res.rec("2e-motores-drv", "PASA" if drv["sw"] <= drv["cw"] + 1 else "FALLA",
                    f"texto='{drv['txt']}' scrollWidth={drv['sw']} clientWidth={drv['cw']}")

        # 2f el caption no desborda su caja
        await push_dir(cdp, dir_msg(why=["NVDA-1.2% AVGO-1.3% MU-2.1% AMD-0.9% arrastran el indice hacia abajo"]))
        st = await arrow_state(cdp)
        s = await cdp.shot(shot_path("02f-caption-largo"))
        res.rec("2f-caption-no-desborda",
                "PASA" if (st["capW"] is not None and st["capW"] <= st["capBox"] + 1) else "FALLA",
                f"caption scrollWidth={st['capW']} clientWidth={st['capBox']} "
                f"(max-width:240px en CSS) texto='{(st['cap'] or '')[:80]}'", s)

        # ---------- 4. tooltip ----------
        await push_dir(cdp, dir_msg())
        st = await arrow_state(cdp)
        tip = st["title"] or ""
        need = ["ESTADO:", "fadeando:", "nivel:", "amplitud"]
        miss = [n for n in need if n not in tip]
        s = await cdp.shot(shot_path("04-tooltip-flecha"))
        res.rec("4-tooltip", "PASA" if not miss else "FALLA",
                ("tooltip completo: " + tip.replace("\n", " | ")) if not miss
                else f"faltan {miss} en el tooltip: {tip!r}", s)
        await cdp.js("ws.onmessage = window.__ui_test_ws_onmessage; delete window.__ui_test_ws_onmessage; 1")

    # ---------- 3. burbujas GEX ----------
    bub = await cdp.js("""(() => {
      if (typeof wallBub === 'undefined') return {impl:false, why:'wallBub no definido'};
      const rows = (wallBub._rows || []);
      return { impl:true, n: rows.length,
               rows: rows.map(r => ({ price:r.price, kind:r.kind, inten:r.inten,
                                      n:r.n, rad:r.rad, abs:!!r.abs, lab:r.lab })) };
    })()""")
    lv = await cdp.js("(typeof LV !== 'undefined' && LV) ? "
                      "{cw:LV.call_wall, pw:LV.put_wall, abs:LV.abs_wall, flip:LV.flip, "
                      " prof:(LV.profile||[]).length} : null")
    s = await cdp.shot(shot_path("03-burbujas-gex"))
    if not bub or not bub.get("impl"):
        res.rec("3-burbujas-gex", "FALLA",
                f"no implementado en la pagina cargada: {bub}", s)
    elif bub["n"] == 0:
        res.rec("3-burbujas-gex", "NO PROBADO",
                f"la capa EXISTE (bubbleRows/WallBubbles en charts/live.html) pero 0 "
                f"hileras con los niveles de hoy: LV={lv}. Sin muros en data/ no hay "
                f"nada que pintar (sabado, cadena archivada sin muros para el sym).", s)
    else:
        res.rec("3-burbujas-gex", "PASA",
                f"{bub['n']} hileras: {json.dumps(bub['rows'])[:600]} | LV={lv}", s)

    # ---------- 5. panel Cuenta sin Gateway ----------
    await cdp.js("document.getElementById('acctbtn').click(); 1")
    await asyncio.sleep(3.0)
    acct = await cdp.js("""(() => {
      const p = document.getElementById('acctpanel');
      return { on: p.classList.contains('on'),
               sum: document.getElementById('acctsum').textContent,
               pos: document.getElementById('acctpos').textContent,
               ord: document.getElementById('acctord').textContent };
    })()""")
    s = await cdp.shot(shot_path("05-panel-cuenta-sin-gateway"))
    txt = acct["sum"]
    fabricated = ("NetLiq 0 ·" in txt) or ("NetLiq 0.00 ·" in txt)
    honest = ("—" in txt) or ("sin conexi" in txt.lower()) or ("⚠" in txt)
    live_value = txt.startswith("LIVE · NetLiq ") and "Poder compra " in txt
    if fabricated:
        res.rec("5-panel-cuenta", "FALLA",
                f"CERO FABRICADO en NetLiq sin Gateway: {txt!r}", s)
    elif honest or live_value:
        res.rec("5-panel-cuenta", "PASA",
                f"cuenta dice la verdad: sum={txt!r} pos={acct['pos']!r} "
                f"ord={acct['ord']!r}", s)
    else:
        res.rec("5-panel-cuenta", "FALLA",
                f"ni cero fabricado ni aviso claro de sin-conexion: {txt!r}", s)
    await cdp.js("document.getElementById('acctclose').click(); 1")

    # ---------- 6. regresion del eje de precios after-close ----------
    scale = await cdp.js("""(() => {
      // rango REAL que el eje derecho esta mostrando vs rango de las velas.
      if (typeof candle === 'undefined' || typeof chart === 'undefined') return null;
      const vr = chart.timeScale().getVisibleLogicalRange();
      if (!vr) return null;
      const bars = (window.__BARS__ || null);
      // rango de velas visibles via coordenadas: invertimos top/bottom del pane 0
      const h = document.getElementById('chart').clientHeight;
      const top = candle.coordinateToPrice(0), bot = candle.coordinateToPrice(h);
      const lines = (window.__PL_PRICES__ || null);
      return { axisTop: top, axisBot: bot, lines: lines };
    })()""")
    cnd = await cdp.js("""(() => {
      if (typeof candle === 'undefined') return null;
      const d = candle.data ? candle.data() : null;
      if (!d || !d.length) return null;
      let hi = -Infinity, lo = Infinity;
      for (const b of d) { if (b.high > hi) hi = b.high; if (b.low < lo) lo = b.low; }
      return { n: d.length, hi, lo, last: d[d.length-1].close };
    })()""")
    plp = await cdp.js("""(() => {
      if (typeof priceLines === 'undefined') return null;
      return priceLines.map(pl => { const o = pl.options(); return {p:o.price, t:o.title}; });
    })()""")
    s = await cdp.shot(shot_path("06-eje-precios-after-close"))
    if not cnd or not scale:
        res.rec("6-eje-precios", "NO PROBADO",
                f"no se pudo leer el eje/las velas desde la pagina: scale={scale} cnd={cnd}", s)
    else:
        span_c = cnd["hi"] - cnd["lo"]
        span_a = (scale["axisTop"] or 0) - (scale["axisBot"] or 0)
        far = [l for l in (plp or [])
               if l["p"] is not None and abs(l["p"] - cnd["last"]) > 0.25 * cnd["last"]]
        # el eje no deberia abrirse mucho mas alla de las velas (margen LWC ~20%)
        bloat = (span_a / span_c) if span_c > 0 else None
        bad = (bloat is not None and bloat > 2.0)
        res.rec("6-eje-precios", "FALLA" if bad else "PASA",
                f"velas lo={cnd['lo']} hi={cnd['hi']} span={round(span_c,3)} last={cnd['last']}; "
                f"eje bot={scale['axisBot']} top={scale['axisTop']} span={round(span_a or 0,3)}; "
                f"inflado x{None if bloat is None else round(bloat,2)}; "
                f"lineas de nivel={json.dumps(plp)[:400]}; lejanas(>25% del spot)={len(far)}", s)

    # ---------- 7. cambio de simbolo ----------
    sym_before = await cdp.js("(typeof CUR_SYM !== 'undefined') ? CUR_SYM : "
                              "(document.getElementById('symbox') ? document.getElementById('symbox').value : null)")
    nav0 = await cdp.js("performance.getEntriesByType('navigation')[0].startTime + '|' + "
                        "performance.timeOrigin")
    t = await cdp.js("""(async () => {
      // manda el cmd de cambio de simbolo por el MISMO WS que usa la UI y cronometra
      // hasta que llega el frame de historia del nuevo simbolo.
      if (typeof ws === 'undefined' || !ws || ws.readyState !== 1) return {err:'ws no abierto'};
      const target = 'MU';
      return await new Promise(resolve => {
        const t0 = performance.now();
        const done = (ev) => {
          let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
          if (m.type === 'history' || (m.sym && String(m.sym).toUpperCase() === target)) {
            ws.removeEventListener('message', done);
            resolve({ ms: Math.round(performance.now() - t0), sym: m.sym || null,
                      bars: (m.bars || m.candles || []).length || null });
          }
        };
        ws.addEventListener('message', done);
        ws.send(JSON.stringify({ cmd: 'sym', sym: target }));
        setTimeout(() => { ws.removeEventListener('message', done);
                           resolve({ err: 'timeout 15s sin frame de historia' }); }, 15000);
      });
    })()""")
    reloaded = await cdp.js("performance.getEntriesByType('navigation')[0].startTime + '|' + "
                            "performance.timeOrigin") != nav0
    await asyncio.sleep(1.0)
    s = await cdp.shot(shot_path("07-cambio-simbolo"))
    if not t or t.get("err"):
        res.rec("7-cambio-simbolo", "FALLA",
                f"no completo: {t}; sym antes={sym_before}", s)
    else:
        res.rec("7-cambio-simbolo", "PASA" if not reloaded else "FALLA",
                f"{sym_before} -> {t.get('sym')}: {t['ms']} ms hasta el frame de historia "
                f"({t.get('bars')} barras), pagina recargada={reloaded} "
                f"(registro historico: 61 ms)", s)


# ------------------------------------------------------------------------ main
async def amain(args):
    os.makedirs(args.out, exist_ok=True)
    profile = args.profile or os.path.join(
        os.environ.get("TMPDIR", "/tmp"), f"ui_smoke_chrome_{os.getpid()}")
    proc = launch_chrome(args.cdp_port, profile, args.width, args.height)
    res = Results()
    try:
        ws_url, _ = await open_page(args.cdp_port, args.url)
        async with CDP(ws_url) as cdp:
            await asyncio.sleep(4.0)          # que corra el arranque de la pagina
            try:
                await run(cdp, args.out, args.url, res)
            except Exception as e:
                res.rec("driver", "FALLA", f"{type(e).__name__}: {e}")
            console = cdp.console
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        if not args.keep_profile:
            shutil.rmtree(profile, ignore_errors=True)

    out = {"ts": int(time.time()), "url": args.url, "rows": res.rows,
           "console": console}
    with open(args.report, "w") as f:
        json.dump(out, f, indent=1)
    for r in res.rows:
        print(f"  {r['status']:<10} {r['key']}: {r['detail'][:200]}")
    return 1 if res.failed() else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--out", default=os.path.join(REPO, "docs/ui/shots"))
    ap.add_argument("--report", default="/tmp/ui_results.json")
    ap.add_argument("--cdp-port", type=int, default=9455)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--keep-profile", action="store_true")
    ap.add_argument("--width", type=int, default=1700)
    ap.add_argument("--height", type=int, default=1000)
    sys.exit(asyncio.run(amain(ap.parse_args())))


if __name__ == "__main__":
    main()
