"use strict";
// gex_heatmap_widget.js — Net GEX Heat Map (strike x vencimiento) del cockpit.
// Dato: data/gex_heatmap_<sym>.json (lo escribe scripts/gex_heatmap.py desde UW
// greek-exposure/strike-expiry). Fichero aparte: live.html lo tocan otros.
// Frescura: se PINTA la edad del dato en la cabecera. Celda sin dato = vacia, jamas 0.
(function () {
  const CSS = `
  #wgt-gexheat .wgbody { padding:0; overflow:auto; }
  .ghwrap { padding:7px 8px 9px; }
  .ghtop { display:flex; align-items:center; gap:6px; margin-bottom:7px; flex-wrap:wrap; }
  .ghpill { background:#16325c; color:#cfe0ff; font-size:10.5px; font-weight:600; padding:3px 8px;
            border-radius:5px; letter-spacing:.3px; }
  .ghpill.dim { background:#1b2130; color:#8a94a8; font-weight:500; }
  .ghpill.warn { background:#2a2113; color:#e0b64a; }
  .ghttl { text-align:center; font-size:12.5px; color:#e6ebf5; font-weight:600; margin:1px 0 2px; }
  .ghleg { text-align:center; font-size:10px; color:#8a94a8; margin-bottom:7px; }
  .ghleg i { font-style:normal; display:inline-block; width:8px; height:8px; border-radius:2px;
             margin:0 4px 0 9px; vertical-align:-1px; }
  .ghleg i.mvc { background:#a855f7; } .ghleg i.spot { background:#3d7de0; }
  .ghtbwrap { overflow-x:auto; }
  table.ghtb { border-collapse:separate; border-spacing:2px; width:100%;
               font-variant-numeric:tabular-nums; }
  table.ghtb th { font-size:9.5px; color:#8a94a8; font-weight:500; padding:2px 1px; }
  table.ghtb th.ghk { text-align:right; padding-right:5px; white-space:nowrap;
                      position:sticky; left:0; z-index:2; background:#161a24; }
  table.ghtb td { font-size:10px; text-align:center; padding:5px 2px; border-radius:3px;
                  color:#e8edf6; white-space:nowrap; }
  table.ghtb td.nd { background:#12161f; color:#39414f; }
  table.ghtb tr td.ghk { background:#161a24; color:#c3cad6; font-size:10.5px; text-align:right;
                         padding-right:6px; font-weight:500;
                         position:sticky; left:0; z-index:2; }
  table.ghtb tr.spot td.ghk { color:#5b9cff; font-weight:700; }
  table.ghtb tr.spot td { box-shadow:inset 0 -1px 0 #2b4a80, inset 0 1px 0 #2b4a80; }
  table.ghtb td.mvc { outline:1.5px solid #a855f7; outline-offset:-1.5px; }
  .ghfoot { display:flex; justify-content:space-between; gap:8px; margin-top:7px;
            font-size:9.5px; color:#5f6878; border-top:1px solid #232838; padding-top:5px; }
  .ghfoot .ghwarn { color:#e0b64a; font-weight:600; }
  .ghscale { display:flex; align-items:center; gap:3px; }
  .ghscale b { width:13px; height:8px; border-radius:2px; display:inline-block; font-size:0; }
  .ghempty { padding:26px 12px; text-align:center; color:#6b7484; font-size:11px; line-height:1.6; }
  .ghempty .ico { font-size:22px; color:#39414f; display:block; margin-bottom:6px; }`;
  const st = document.createElement("style");
  st.textContent = CSS;
  document.head.appendChild(st);

  const POLL_MS = 20000;
  const el = () => document.querySelector("#wgt-gexheat .wgbody");
  const sub = () => document.querySelector("#wgt-gexheat .wgsub");
  let timer = null, lastSym = null;

  const fmt = (v) => {
    const a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(2) + " B";
    if (a >= 1e6) return (v / 1e6).toFixed(2) + " M";
    if (a >= 1e3) return (v / 1e3).toFixed(2) + " K";
    return v.toFixed(0);
  };
  const md = (s) => s.slice(5).replace("-", "/");

  // verde = gamma positiva (dealers amparan ese strike), rojo = negativa (aceleran).
  // La intensidad es RELATIVA al mayor |valor| de la matriz: es un mapa, no una medida.
  function color(v, max) {
    if (v === null || v === undefined) return null;
    const t = max > 0 ? Math.min(1, Math.abs(v) / max) : 0;
    const a = 0.14 + 0.72 * Math.pow(t, 0.55);
    return v >= 0 ? `rgba(20,190,110,${a.toFixed(3)})` : `rgba(230,60,75,${a.toFixed(3)})`;
  }

  function empty(msg) {
    const b = el(); if (!b) return;
    b.innerHTML = `<div class="ghempty"><span class="ico">▦</span>${msg}</div>`;
    const s = sub(); if (s) s.textContent = "sin dato";
  }

  function render(d) {
    const b = el(); if (!b) return;
    const age = Math.max(0, Math.round(Date.now() / 1000 - (d.ts || 0)));
    const spot = d.spot;
    // escala a $ por 1% de movimiento: convencion publica de GEX aplicada POR NOSOTROS
    // sobre el gex crudo de UW (gamma x OI). Se declara en el pie, no se disfraza de dato.
    const K = spot * spot * 0.01;
    let max = 0;
    for (const row of d.cells) for (const v of row) if (v !== null) max = Math.max(max, Math.abs(v * K));

    // fila mas cercana al spot (la que lleva el marcador azul)
    let si = 0, sd = Infinity;
    d.strikes.forEach((k, i) => { const x = Math.abs(k - spot); if (x < sd) { sd = x; si = i; } });

    let h = `<div class="ghwrap"><div class="ghtop">
      <span class="ghpill">${d.sym}</span>
      <span class="ghpill dim">${d.date || "—"}</span>
      <span class="ghpill dim">Net GEX</span>
      <span class="ghpill ${age > 180 ? "warn" : "dim"}">${age < 90 ? age + "s" : Math.round(age / 60) + " min"}</span>
    </div>
    <div class="ghttl">Net GEX Heat Map — ${d.sym}</div>
    <div class="ghleg"><i class="mvc"></i>MVC ($${d.mvc ? d.mvc.strike.toFixed(2) : "—"}${d.mvc ? " " + md(d.mvc.expiry) : ""})
      <i class="spot"></i>${d.sym} ($${spot.toFixed(2)})</div>
    <div class="ghtbwrap"><table class="ghtb"><tr><th class="ghk">Strike</th>`;
    for (const e of d.expiries) h += `<th>${md(e)}</th>`;
    h += "</tr>";
    d.strikes.forEach((k, i) => {
      h += `<tr class="${i === si ? "spot" : ""}"><td class="ghk">$${k.toFixed(2)}</td>`;
      d.cells[i].forEach((v, j) => {
        if (v === null || v === undefined) { h += `<td class="nd">·</td>`; return; }
        const $v = v * K;
        const isMvc = d.mvc && d.mvc.strike === k && d.mvc.expiry === d.expiries[j];
        h += `<td class="${isMvc ? "mvc" : ""}" style="background:${color($v, max)}"
              title="${k.toFixed(2)} · ${d.expiries[j]} · ${fmt($v)}">${fmt($v)}</td>`;
      });
      h += "</tr>";
    });
    const SRC = { uw: "UW", polygon: "Polygon 15min", chain_local: "cadena local" };
    let flags = "";
    if (d.stale) flags += ` <span class="ghwarn">⚠ STALE</span>`;
    if (d.partial) flags += ` <span class="ghwarn">⚠ ${d.note || "parcial"}</span>`;
    h += `</table></div><div class="ghfoot">
      <span class="ghscale">−<b style="background:rgba(230,60,75,.8)"></b><b style="background:rgba(230,60,75,.3)"></b><b style="background:#12161f"></b><b style="background:rgba(20,190,110,.3)"></b><b style="background:rgba(20,190,110,.8)"></b>+</span>
      <span>${SRC[d.src] || d.src || "—"} · ×S²·0,01${flags}</span></div></div>`;
    b.innerHTML = h;
    const s = sub();
    if (s) s.textContent = `${d.sym} · ${age < 90 ? age + "s" : Math.round(age / 60) + "m"}`;
  }

  function curSymbol() {
    try { return (typeof curSym !== "undefined" && curSym) ? String(curSym).toUpperCase() : null; }
    catch (e) { return null; }
  }

  async function tick() {
    const sym = curSymbol();
    if (!sym) { empty("Sin símbolo activo."); return; }
    if (sym !== lastSym) { lastSym = sym; empty("Cargando " + sym + "…"); }
    try {
      const r = await fetch(`/data/gex_heatmap_${sym.toLowerCase()}.json`, { cache: "no-store" });
      if (!r.ok) {
        empty(`Sin heatmap de ${sym} todavía.<br>Lo escribe <code>scripts/gex_heatmap.py</code>.`);
        return;
      }
      const d = await r.json();
      if (!d || !d.cells || !d.cells.length) { empty("Matriz vacía para " + sym + "."); return; }
      render(d);
    } catch (e) {
      empty("Error leyendo el heatmap: " + (e && e.message ? e.message : e));
    }
  }

  function start() {
    if (timer) clearInterval(timer);
    tick();
    timer = setInterval(tick, POLL_MS);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  window.gexHeatRefresh = tick;
})();
