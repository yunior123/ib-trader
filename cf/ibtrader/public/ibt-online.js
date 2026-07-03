// Adaptador para servir el chart de la .app SIN su bridge de Python.
//
// live.html habla con `ws://<host>/stream`. Aqui no hay bridge: se sustituye WebSocket por un
// doble que hace polling a /api/panel y emite los MISMOS frames (history, tick, levels) que
// enviaba chart_bridge. Lo que el bridge daba y aqui no existe (cuenta, ordenes, narrador,
// footprint, cinta de ballenas) NO se finge: simplemente no se emite, y el chart deja esos
// paneles vacios en vez de enseñar datos inventados.
(function () {
  const REAL = window.WebSocket;
  const PARAM = new URLSearchParams(location.search);
  // El widget PULSO necesita cinta en vivo, que aqui no hay. Se puede pedir con ?pulso=1;
  // por defecto se oculta para no dejar un "SIN DATOS · ESPERANDO" permanente en pantalla.
  const PULSO = PARAM.get("pulso") === "1";
  if (!PULSO) addEventListener("DOMContentLoaded", () => {
    const p = document.getElementById("pulsebox") || document.querySelector(".pulse-box, #pulso");
    if (p) p.style.display = "none";
    document.querySelectorAll("*").forEach(el => {
      if (el.children.length === 0 && /^\s*PULSO\s*$/i.test(el.textContent || "")) {
        const caja = el.closest("div");
        if (caja) caja.style.display = "none";
      }
    });
  });
  const SYM = (PARAM.get("sym") || "QQQ").toUpperCase();
  const MODO = PARAM.get("modo") === "perp" ? "perp" : "cash";
  const TF = PARAM.get("tf") || "15m";   // el mismo por defecto que la .app

  function sma(v, n) {
    const out = [];
    for (let i = 0; i < v.length; i++)
      out.push(i < n - 1 ? null : v.slice(i - n + 1, i + 1).reduce((a, b) => a + b, 0) / n);
    return out;
  }
  function bandas(cierres, n = 20, k = 2) {
    const alta = [], baja = [], media = sma(cierres, n);
    for (let i = 0; i < cierres.length; i++) {
      if (media[i] === null) { alta.push(null); baja.push(null); continue; }
      const v = cierres.slice(i - n + 1, i + 1);
      const sd = Math.sqrt(v.reduce((a, b) => a + (b - media[i]) ** 2, 0) / n);
      alta.push(media[i] + k * sd); baja.push(media[i] - k * sd);
    }
    return { alta, baja, media };
  }
  const puntos = (t, v) => t.map((x, i) => (v[i] === null ? null : { time: x, value: v[i] }))
                            .filter(Boolean);

  function frames(d) {
    const barras = d.barras || [];
    const tiempos = barras.map(b => Math.floor(new Date(b.ts.replace(" ", "T") + "Z").getTime() / 1000));
    const cierres = barras.map(b => b.c);
    const bb = bandas(cierres);
    const velas = barras.map((b, i) => ({ time: tiempos[i], open: b.o, high: b.h, low: b.l, close: b.c }));
    const indicators = {
      bbUpper: puntos(tiempos, bb.alta), bbLower: puntos(tiempos, bb.baja),
      bbMid: puntos(tiempos, bb.media), sma20: puntos(tiempos, sma(cierres, 20)),
      sma40: puntos(tiempos, sma(cierres, 40)), sma100: puntos(tiempos, sma(cierres, 100)),
    };
    // Todo lo que el worker calcula viaja al chart. Lo que una fuente gratuita NO da (cuenta,
    // ordenes, cinta de ballenas, lado agresor) sigue sin emitirse: el chart lo deja en "—",
    // que es la verdad, en vez de un numero inventado.
    // El chart pinta estos numeros TAL CUAL: chart_levels ya se los daba redondeados. Sin esto
    // salia "flip 224.89775113158154" en la cabecera.
    const red = (x, n) => (typeof x === "number" && isFinite(x) ? +x.toFixed(n) : null);
    const levels = {
      sym: d.sym, spot: red(d.spot, 2), call_wall: d.call_wall, put_wall: d.put_wall,
      flip: red(d.flip, 2), flip_raices: (() => { try { return (JSON.parse(d.flip_raices || "[]")).map(x => +x.toFixed(2)); } catch { return []; } })(),
      max_pain: d.max_pain, net_gex: d.gex_total, gross_gex: d.gross_gex,
      net_vex: d.net_vex, gross_vex: d.gross_vex,
      net_charm: d.net_charm, gross_charm: d.gross_charm,
      pressure: red(d.pressure, 1), pressure_lab: d.pressure == null ? null
        : (d.pressure >= 0 ? "PINEAN" : "AMPLIFICAN"),
      em: red(d.em, 2), dte: d.dte, exp: d.exp, greeks_ok_pct: d.greeks_ok_pct,
      oi_available: true, oi_source: "cboe_delayed",
      regime: d.gex_total == null ? null : (d.gex_total >= 0 ? "POS" : "NEG"),
      asof: d.fuente_ts, chain_ts: d.ts ? d.ts * 1000 : null,
      chain_src: MODO === "perp" ? "okx" : "cboe",
      scale: "dollar1pct", profile_metric: "gex",
      // Muros e imanes: el chart los dibuja de aqui. Cada nodo lleva su dominancia call/put.
      profile: (d.profile || []).map(p => ({
        strike: p.strike, gex: p.gex, vex: p.vex, charm: p.charm,
        call_oi: p.call_oi, put_oi: p.put_oi,
        oi: (p.call_oi || 0) + (p.put_oi || 0),
        call_pct: (p.call_oi + p.put_oi) > 0 ? p.call_oi / (p.call_oi + p.put_oi) : null,
      })),
      strikes: d.strikes, contratos: d.contratos,
      charm_why: "Charm por DÍA (∂delta/∂t · OI) calculado por Black-Scholes con la IV medida de "
                 + "cada contrato de la cadena de CBOE. Sin IV, el contrato NO entra.",
      flip_why: d.flip == null
        ? "El GEX acumulado no cruza cero en este libro: no hay flip, y el borde del recorte no es un nivel."
        : "Raíz del GEX acumulado más cercana al spot (todas las raíces en flip_raices).",
    };
    return { velas, indicators, levels };
  }

  class WSFalso {
    constructor(url) {
      this.url = url; this.readyState = 0;
      this._oyentes = {}; this._vivo = true;
      setTimeout(() => this._arrancar(), 0);
    }
    addEventListener(t, f) { (this._oyentes[t] = this._oyentes[t] || []).push(f); }
    removeEventListener(t, f) {
      this._oyentes[t] = (this._oyentes[t] || []).filter(x => x !== f);
    }
    _emitir(t, ev) {
      (this._oyentes[t] || []).forEach(f => { try { f(ev); } catch (e) { console.error(e); } });
      const h = this["on" + t];
      if (typeof h === "function") { try { h(ev); } catch (e) { console.error(e); } }
    }
    _mandar(obj) { this._emitir("message", { data: JSON.stringify(obj) }); }
    send() { /* el chart manda comandos (zonas, ordenes): aqui no hay a quien */ }
    close() { this._vivo = false; this.readyState = 3; clearInterval(this._t); }

    async _arrancar() {
      this.readyState = 1;
      this._emitir("open", {});
      const primera = await this._traer();
      if (!primera) return;
      const f = frames(primera);
      this._mandar({ type: "history", tf: TF, bars: f.velas, indicators: f.indicators,
                     levels: f.levels, signals: [], engineOps: [], nodata: f.velas.length ? null : "sin barras",
                     mock: false, feed: { src: f.levels.chain_src, live: MODO === "perp" },
                     server_ms: Date.now() });
      this._mandar({ type: "levels", tf: TF, levels: f.levels });
      this._t = setInterval(() => this._latido(), 5000);
    }
    async _traer() {
      try {
        const r = await fetch(`/api/panel?syms=${SYM}&tf=${TF}` + (MODO === "perp" ? "&modo=perp" : ""),
                              { cache: "no-store" });
        if (!r.ok) return null;
        const j = await r.json();
        return Array.isArray(j) ? j[0] : null;
      } catch { return null; }
    }
    async _latido() {
      if (!this._vivo) return;
      const d = await this._traer();
      if (!d || !d.barras || !d.barras.length) return;
      const f = frames(d);
      this._mandar({ type: "tick", bar: f.velas[f.velas.length - 1],
                     feed: { src: f.levels.chain_src, live: MODO === "perp" } });
      this._mandar({ type: "bar", tf: TF, bar: f.velas[f.velas.length - 1],
                     indicators: {
                       bbUpper: f.indicators.bbUpper.at(-1), bbLower: f.indicators.bbLower.at(-1),
                       bbMid: f.indicators.bbMid.at(-1), sma20: f.indicators.sma20.at(-1),
                       sma40: f.indicators.sma40.at(-1), sma100: f.indicators.sma100.at(-1),
                     } });
      this._mandar({ type: "levels", tf: "1m", levels: f.levels });
    }
  }
  WSFalso.CONNECTING = 0; WSFalso.OPEN = 1; WSFalso.CLOSING = 2; WSFalso.CLOSED = 3;

  window.WebSocket = function (url, protos) {
    // Solo se intercepta el stream del bridge; cualquier otro WS sigue siendo el de verdad.
    return /\/stream\b/.test(String(url)) ? new WSFalso(url) : new REAL(url, protos);
  };
  window.WebSocket.prototype = WSFalso.prototype;
  Object.assign(window.WebSocket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
})();
