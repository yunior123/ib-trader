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
  .ghpill { background:#2563eb; color:#fff; font-size:10.5px; font-weight:600; padding:3px 8px;
            border-radius:5px; letter-spacing:.3px; }
  .ghpill.dim { background:#1b2130; color:#8a94a8; font-weight:500; }
  .ghpill.warn { background:#2a2113; color:#e0b64a; }
  .ghpill.up { background:#123b31; color:#64d6b1; }
  .ghpill.down { background:#442127; color:#ff7b86; }
  .gharch { text-align:center; font-size:10px; color:#aeb8ca; margin:0 0 7px; }
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
                      position:sticky; left:0; z-index:2; background:#0a0f1e; }
  table.ghtb td { font-size:10px; text-align:center; padding:5px 2px; border-radius:3px;
                  color:#e8edf6; white-space:nowrap; }
  table.ghtb td.nd { background:#12161f; color:#39414f; }
  table.ghtb tr td.ghk { background:#0a0f1e; color:#e6ebf5; font-size:10.5px; text-align:right;
                         padding-right:6px; font-weight:500;
                         position:sticky; left:0; z-index:2; }
  table.ghtb tr.spot td.ghk { color:#3b82f6; font-weight:700; }
  table.ghtb tr.spot td { box-shadow:inset 0 -1px 0 #2b4a80, inset 0 1px 0 #2b4a80; }
  table.ghtb td.mvc { outline:2px solid #a855f7; outline-offset:-2px; background:#a855f7 !important; }
  .ghfoot { display:flex; justify-content:space-between; gap:8px; margin-top:7px;
            font-size:9.5px; color:#5f6878; border-top:1px solid #232838; padding-top:5px; }
  .ghfoot .ghwarn { color:#e0b64a; font-weight:600; }
  .ghscale { display:flex; align-items:center; gap:3px; }
  .ghscale b { width:13px; height:8px; border-radius:2px; display:inline-block; font-size:0; }
  .ghempty { padding:26px 12px; text-align:center; color:#6b7484; font-size:11px; line-height:1.6; }
  .ghempty .ico { font-size:22px; color:#39414f; display:block; margin-bottom:6px; }
  .ghspin { display:inline-block; width:11px; height:11px; border:2px solid #33405a;
            border-top-color:#5b8cff; border-radius:50%; animation:ghspin .75s linear infinite;
            vertical-align:-2px; margin-right:5px; }
  @keyframes ghspin { to { transform:rotate(360deg); } }`;
  const st = document.createElement("style");
  st.textContent = CSS;
  document.head.appendChild(st);

  // El JSON se vuelve a leer cada minuto, igual que walls/magnets/GEX aguas arriba.
  // Fuera de RTH se conserva la última foto y su edad visible: nunca se finge gamma nueva.
  const POLL_MS = 1000;   // fichero local; prints LSE WS refit <=1 s, REST reconcilia cada 5 min
  const el = () => document.querySelector("#wgt-gexheat .wgbody");
  const sub = () => document.querySelector("#wgt-gexheat .wgsub");
  let timer = null, metaTimer = null, lastSym = null, requestSeq = 0, lastPayload = null;
  let lastData = null, lastFetchMs = null, loadingAt = null;

  const fmt = (v) => {
    const a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(2) + " B";
    if (a >= 1e6) return (v / 1e6).toFixed(2) + " M";
    if (a >= 1e3) return (v / 1e3).toFixed(2) + " K";
    return v.toFixed(0);
  };
  const md = (s) => s.slice(5).replace("-", "/");

  // En London: verde = actividad gamma de calls; rojo = actividad gamma de puts.
  // Sin OI no se atribuye el color a inventario dealer. La intensidad es relativa.
  function color(v, max) {
    if (v === null || v === undefined) return null;
    const t = max > 0 ? Math.min(1, Math.abs(v) / max) : 0;
    const a = 0.14 + 0.72 * Math.pow(t, 0.55);
    return v >= 0 ? `rgba(34,197,94,${a.toFixed(3)})` : `rgba(220,38,38,${a.toFixed(3)})`;
  }

  function empty(msg, label) {
    loadingAt = null;
    const b = el(); if (!b) return;
    b.innerHTML = `<div class="ghempty"><span class="ico">▦</span>${msg}</div>`;
    const s = sub(); if (s) s.textContent = label || "sin dato";
  }

  function ageText(d) {
    const age = Math.max(0, Math.round(Date.now() / 1000 - (d && (d.source_ts || d.ts) || 0)));
    return age < 90 ? age + "s" : Math.round(age / 60) + "m";
  }

  function reloadText(d) {
    if (!d || !d.next_refresh_ts) return "↻ —";
    const left = Math.max(0, Math.ceil(d.next_refresh_ts - Date.now() / 1000));
    return `↻ ${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
  }

  function sourceText(d) {
    const src = { uw: "UW", polygon: "Polygon 15min", chain_local: "cadena local",
                  lse: "London Strategic Edge" };
    const mode = d && d.update_mode === "websocket_prints_rest_greeks"
      ? "WS prints · REST Greeks"
      : "REST snapshot";
    return `${src[d && d.src] || d && d.src || "—"} · ${mode}`;
  }

  function refreshMeta() {
    const s = sub(); if (!s) return;
    if (loadingAt != null) {
      s.innerHTML = `<span class="ghspin"></span>REST · ${(performance.now()-loadingAt).toFixed(0)}ms`;
    } else if (lastData) {
      s.textContent = `${lastData.sym} · ${sourceText(lastData)} · ${reloadText(lastData)} · fuente ${ageText(lastData)}`;
    }
  }

  function loading(sym, replace) {
    loadingAt = performance.now();
    if (replace) {
      const b = el(); if (b) b.innerHTML = `<div class="ghempty"><span class="ghspin"></span>Cargando ${sym} por REST…</div>`;
    }
    refreshMeta();
  }

  function render(d, fetchMs) {
    const b = el(); if (!b) return;
    const age = Math.max(0, Math.round(Date.now() / 1000 - (d.source_ts || d.ts || 0)));
    const spot = d.spot;
    // escala a $ por 1% de movimiento: convencion publica de GEX aplicada POR NOSOTROS
    // sobre el gex crudo de UW (gamma x OI). Se declara en el pie, no se disfraza de dato.
    const K = spot * spot * 0.01;
    let max = 0;
    for (const row of d.cells) for (const v of row) if (v !== null) max = Math.max(max, Math.abs(v * K));

    // fila mas cercana al spot (la que lleva el marcador azul)
    let si = 0, sd = Infinity;
    d.strikes.forEach((k, i) => { const x = Math.abs(k - spot); if (x < sd) { sd = x; si = i; } });

    const london = d.metric === "gamma_volume";
    const title = london ? "London Γ×Volume Heat Map" : "Net GEX Heat Map";
    const metric = london ? "Γ × volume_today · sin OI" : "Net GEX";
    const arch = london && d.architect ? d.architect : null;
    const archScore = arch && arch.activity_score != null ? arch.activity_score : null;
    const archClass = archScore == null ? "dim" : archScore > 20 ? "up" : archScore < -20 ? "down" : "dim";
    const archText = archScore == null ? "ARCH —" : `ARCH ${archScore > 0 ? "+" : ""}${archScore.toFixed(0)} ${arch.activity_side}`;
    const ac = arch && arch.components || {};
    const bal = (v) => v == null ? "—" : `${v >= 0 ? "+" : ""}${(100 * v).toFixed(0)}`;
    const rr = arch && arch.rr25_mean_vol_points;
    const triad = arch && arch.reversal;
    const revText = triad ? `REV3 ${triad.label}${triad.direction ? " " + triad.direction : ""}` : "REV3 —";
    const archTitle = arch ? `Actividad London, no dealer GEX · Γ ${bal(ac.gamma_volume_balance)} · Δ ${bal(ac.delta_volume_balance)} · premium ${bal(ac.premium_balance)} · RR25 ${rr == null ? "—" : rr.toFixed(2) + " vol"} · ${revText} · ${arch.validation}` : "";
    const name = document.querySelector("#wgt-gexheat .wgname"); if (name) name.textContent = title;
    const pop = document.querySelector('#wgt-gexheat .popover-box[data-widget="gexheat"]');
    if (pop && london) pop.innerHTML = '<div class="popover-title">London Γ×Volume Heat Map</div><p><strong>Qué mide:</strong> gamma de modelo × volume_today por strike y vencimiento. Verde = calls; rojo = puts; morado = mayor |actividad|.</p><div class="popover-source"><strong>Fuente:</strong> London Strategic Edge, snapshots por contrato filtrados a una sesión coherente.</div><div class="popover-doctrine"><strong>Guardas:</strong> sin OI no es Net GEX, dealer inventory ni gamma flip. REV3 queda DATA sin ejecuciones Bid×Ask.</div>';
    let h = `<div class="ghwrap"><div class="ghtop">
      <span class="ghpill">${d.sym}</span>
      <span class="ghpill dim">${d.date || "—"}</span>
      <span class="ghpill dim">${metric}</span>
      ${arch ? `<span class="ghpill ${archClass}" title="${archTitle}">${archText}</span>` : ""}
      <span class="ghpill dim">${reloadText(d)}</span>
      <span class="ghpill ${age > 180 ? "warn" : "dim"}">${age < 90 ? age + "s" : Math.round(age / 60) + " min"}</span>
    </div>
    <div class="ghttl">${title} — ${d.sym}</div>
    <div class="ghleg"><i class="mvc"></i>MVC ($${d.mvc ? d.mvc.strike.toFixed(2) : "—"}${d.mvc ? " " + md(d.mvc.expiry) : ""})
      <i class="spot"></i>${d.sym} ($${spot.toFixed(2)}) · MAG ${d.magnet == null ? "—" : "$" + d.magnet.toFixed(2)}</div>
    ${arch ? `<div class="gharch">Γ ${bal(ac.gamma_volume_balance)} · Δ ${bal(ac.delta_volume_balance)} · premium ${bal(ac.premium_balance)} · RR25 ${rr == null ? "—" : (rr >= 0 ? "+" : "") + rr.toFixed(2)} vol · ${revText} · UNPROVEN</div>` : ""}
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
    let flags = "";
    if (d.stale) flags += ` <span class="ghwarn">⚠ STALE</span>`;
    if (d.partial) flags += ` <span class="ghwarn">⚠ ${d.note || "parcial"}</span>`;
    h += `</table></div><div class="ghfoot">
      <span class="ghscale">−<b style="background:rgba(230,60,75,.8)"></b><b style="background:rgba(230,60,75,.3)"></b><b style="background:#12161f"></b><b style="background:rgba(20,190,110,.3)"></b><b style="background:rgba(20,190,110,.8)"></b>+</span>
      <span>${sourceText(d)} · ${london ? "Γ×volume, NO dealer GEX" : "×S²·0,01"} · fetch ${Math.round(fetchMs)}ms${flags}</span></div></div>`;
    b.innerHTML = h;
    lastData = d; lastFetchMs = fetchMs; loadingAt = null;
    refreshMeta();
    window.dispatchEvent(new CustomEvent("lseHeatmapMeta", { detail: d }));
  }

  function curSymbol() {
    try {
      const s = (typeof curSym !== "undefined" && curSym) ? String(curSym).toUpperCase() : null;
      return s && s.endsWith("USDT") ? s.slice(0, -4) : s;
    }
    catch (e) { return null; }
  }

  async function tick() {
    if (window.cockpitWidgetOpen && !window.cockpitWidgetOpen("gexheat")) return;
    const sym = curSymbol();
    if (!sym) { empty("Sin símbolo activo."); return; }
    const londonOnly = Boolean(window.chartIsLondonOnly && window.chartIsLondonOnly());
    const changed = sym !== lastSym;
    if (changed) { lastSym = sym; lastData = null; lastPayload = null; }
    const seq = ++requestSeq;
    loading(sym, changed || !el()?.querySelector("table.ghtb"));
    const t0 = performance.now();
    try {
      const r = await fetch(`/data/gex_heatmap_${sym.toLowerCase()}.json`, { cache: "no-store" });
      if (seq !== requestSeq || sym !== curSymbol()) return;
      if (!r.ok) {
        loadingAt = null;
        empty(londonOnly
          ? `Esperando el primer mapa Γ×volumen de London para ${sym}.`
          : `Sin heatmap de ${sym} todavía.<br>Lo escribe <code>scripts/gex_heatmap.py</code>.`);
        return;
      }
      const raw = await r.text();
      if (seq !== requestSeq || sym !== curSymbol()) return;
      // The local file is polled frequently for London WS refits.  Do not rebuild a large
      // strike×expiry table when only its on-screen age/countdown has changed.
      if (raw === lastPayload && lastData) {
        loadingAt = null;
        refreshMeta();
        return;
      }
      const d = JSON.parse(raw);
      if (!d || !d.cells || !d.cells.length) { empty("Matriz vacía para " + sym + "."); return; }
      if (londonOnly && d.src !== "lse") {
        lastData = null; loadingAt = null;
        empty(`Esperando mapa London de ${sym}; el snapshot no-London anterior no se mostrará.`, "London-only");
        return;
      }
      if (window.providerMark) window.providerMark(d.src);
      if (window.providerEnabled && !window.providerEnabled(d.src)) {
        lastData = null; loadingAt = null;
        empty(`${sourceText(d)} oculto en 🛰 Fuentes.`);
        return;
      }
      lastPayload = raw;
      render(d, performance.now() - t0);
    } catch (e) {
      if (seq !== requestSeq) return;
      loadingAt = null;
      empty("Error leyendo el heatmap: " + (e && e.message ? e.message : e));
    }
  }

  function start() {
    if (timer) clearInterval(timer);
    tick();
    timer = setInterval(tick, POLL_MS);
    metaTimer = setInterval(refreshMeta, 1000);
  }
  window.addEventListener("cockpitWidgetsVisibility", (e) => {
    if (e.detail && e.detail.visible && window.cockpitWidgetOpen("gexheat")) tick();
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  window.gexHeatRefresh = tick;
})();
