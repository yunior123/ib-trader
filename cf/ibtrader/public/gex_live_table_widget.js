"use strict";
// gex_live_table_widget.js — GEX Live Table estilo Tanuki para el cockpit.
// Dato: data/gex_heatmap_<sym>.json (el MISMO fichero que ya sirve el Heat Map;
// cero red nueva y funciona en London-only). Arriba: rail de vencimientos DTE
// (fecha, N DTE, tag W#/M#, punto verde/rojo por signo, barra de magnitud y total)
// cuando la fuente trae desglose real; si solo existe el perfil agregado, muestra UNA
// pildora ALL. Abajo: tabla strike-level con spot, CW/PW reales y MVC. MAPA, no gatillo:
// celda sin dato = vacia, jamas 0. Fuente y recoleccion tienen edades separadas y estado
// FRESH/STALE explicito.
(function () {
  const CSS = `
  #wgt-gexlive .wgbody { padding:0; overflow:auto; }
  .gltwrap { padding:7px 8px 9px; }
  .gltrail { display:flex; gap:5px; overflow-x:auto; padding-bottom:2px; }
  .gltexp { flex:0 0 auto; min-width:64px; display:flex; flex-direction:column; align-items:center;
            gap:2px; padding:5px 7px 6px; border-radius:8px; cursor:pointer;
            background:#111623; border:1px solid #232838; color:#e6ebf5; }
  .gltexp:hover { border-color:#31405e; }
  .gltexp.sel { border-color:#2f6bff; background:#101b31; box-shadow:0 0 0 1px #2f6bff inset; }
  .gltdatelbl { font-size:9.5px; font-weight:700; letter-spacing:.4px; color:#aeb8ca; }
  .gltdte { font-size:9px; font-weight:600; color:#8a94a8; }
  .gltdte.zero { color:#f4c430; font-weight:700; }
  .glttag { font-size:8.5px; color:#5f6878; }
  .glttag b { color:#8a94a8; font-weight:600; }
  .gltdot { width:16px; height:16px; border-radius:50%; display:flex; align-items:center;
            justify-content:center; font-size:10px; font-weight:700; line-height:1; margin:2px 0 1px; }
  .gltdot.pos { color:#4ade80; background:rgba(34,197,94,.12); box-shadow:0 0 7px rgba(34,197,94,.55);
                border:1px solid rgba(34,197,94,.5); }
  .gltdot.neg { color:#ff7b86; background:rgba(230,60,75,.12); box-shadow:0 0 7px rgba(230,60,75,.55);
                border:1px solid rgba(230,60,75,.5); }
  .gltdot.mut { color:#5f6878; background:#171c29; border:1px solid #232838; box-shadow:none; }
  .gltvbar { width:7px; height:16px; border-radius:2px; background:#171c29; position:relative; overflow:hidden; }
  .gltvbar i { position:absolute; left:0; right:0; bottom:0; border-radius:2px; }
  .gltvbar i.pos { background:linear-gradient(180deg,#22c55e,#15803d); }
  .gltvbar i.neg { background:linear-gradient(180deg,#f87171,#b91c1c); }
  .gltamt { font-size:10px; font-variant-numeric:tabular-nums; color:#e6ebf5; }
  .gltamt.pos { color:#4ade80; } .gltamt.neg { color:#ff7b86; }
  .gltamt.mut { color:#5f6878; }
  .gltexp.gltall { border-style:dashed; }
  .glttbwrap { margin-top:7px; overflow-y:auto; }
  table.glttb { border-collapse:separate; border-spacing:2px; width:100%;
                font-variant-numeric:tabular-nums; }
  table.glttb th { font-size:9px; color:#8a94a8; font-weight:500; padding:1px 3px; text-align:left; }
  table.glttb td { font-size:10px; padding:2px 3px; border-radius:3px; white-space:nowrap; }
  table.glttb tr td.glstk { color:#e6ebf5; font-size:10.5px; text-align:right; width:52px; font-weight:500; }
  .glttrack { position:relative; height:11px; background:#12161f; border-radius:2px; overflow:hidden; }
  .glttrack i { position:absolute; top:0; bottom:0; left:0; border-radius:2px; }
  .glttrack i.pos { background:linear-gradient(90deg,rgba(34,197,94,.35),rgba(34,197,94,.85)); }
  .glttrack i.neg { background:linear-gradient(90deg,rgba(230,60,75,.35),rgba(230,60,75,.85)); }
  td.gltval { text-align:right; color:#aeb8ca; width:62px; }
  td.gltval.pos { color:#4ade80; } td.gltval.neg { color:#ff7b86; }
  td.gltbadge { width:30px; text-align:center; font-size:8.5px; font-weight:700; }
  td.gltbadge .cw { color:#f4c430; } td.gltbadge .pw { color:#ff7b86; }
  td.gltbadge .mvc { color:#a855f7; }
  tr.gltmvc td.glstk { color:#a855f7; font-weight:700; }
  tr.gltmvc .glttrack { box-shadow:0 0 0 1px #a855f7 inset; }
  tr.gltspot td { background:#101b31; color:#e6ebf5; font-weight:700; font-size:10px;
                  box-shadow:inset 0 -1px 0 #2b4a80, inset 0 1px 0 #2b4a80; }
  tr.gltspot td .gltsval { color:#3b82f6; font-variant-numeric:tabular-nums; }
  .gltfoot { display:flex; justify-content:space-between; gap:8px; margin-top:7px;
             font-size:9.5px; color:#5f6878; border-top:1px solid #232838; padding-top:5px; }
  .gltfoot .gltwarn { color:#e0b64a; font-weight:600; }
  .gltleg { text-align:center; font-size:10px; color:#8a94a8; margin:6px 0 0; }
  .gltleg i { font-style:normal; display:inline-block; width:8px; height:8px; border-radius:2px;
              margin:0 4px 0 9px; vertical-align:-1px; }
  .gltleg i.cw { background:#f4c430; } .gltleg i.pw { background:#ff7b86; } .gltleg i.mvc { background:#a855f7; }
  .gltempty { padding:26px 12px; text-align:center; color:#6b7484; font-size:11px; line-height:1.6; }
  .gltempty .ico { font-size:22px; color:#39414f; display:block; margin-bottom:6px; }
  .gltspin { display:inline-block; width:11px; height:11px; border:2px solid #33405a;
             border-top-color:#5b8cff; border-radius:50%; animation:gltspin .75s linear infinite;
             vertical-align:-2px; margin-right:5px; }
  @keyframes gltspin { to { transform:rotate(360deg); } }`;
  const st = document.createElement("style");
  st.textContent = CSS;
  document.head.appendChild(st);

  // El mapa del borde rota por simbolo, no cambia a 1 Hz. Cinco segundos conserva una UX
  // fluida en el bridge local y evita duplicar consultas D1 cada segundo por cada ventana.
  const POLL_MS = 5000;
  const el = () => document.querySelector("#wgt-gexlive .wgbody");
  const sub = () => document.querySelector("#wgt-gexlive .wgsub");
  let timer = null, metaTimer = null, lastSym = null, requestSeq = 0, lastPayload = null;
  let lastData = null, lastFetchMs = null, selKey = null; // selKey: expiry | "all"

  const fmt = (v) => {
    if (v === null || v === undefined) return "—";
    const a = Math.abs(v), s = v < 0 ? "-" : "";
    if (a >= 1e9) return s + (a / 1e9).toFixed(1) + "B";
    if (a >= 1e6) return s + (a / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return s + (a / 1e3).toFixed(1) + "K";
    return s + a.toFixed(0);
  };
  const MES = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
  // DTE calendario desde HOY local (igual que Tanuki pinta "0 DTE / 3 DTE / ...").
  function dteOf(expiry) {
    const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
    const d = new Date(expiry + "T00:00:00");
    return Math.round((d - hoy) / 86400000);
  }
  // W# = semana del mes; M# = mensual (tercer viernes). La estrella 0DTE se anade aparte.
  function tagOf(expiry) {
    const d = new Date(expiry + "T00:00:00");
    const day = d.getDate();
    const thirdFriday = d.getDay() === 5 && day >= 15 && day <= 21;
    return thirdFriday ? "M" + (d.getMonth() + 1) : "W" + Math.ceil(day / 7);
  }
  function srcText(d) {
    return { lse: "London Γ×volumen", polygon: "Polygon", cboe: "CBOE", uw: "Unusual Whales" }[d.src] || (d.src || "?");
  }
  function fmtAge(s) {
    if (s === null || s === undefined || !Number.isFinite(+s)) return "?";
    s = Math.max(0, Math.floor(+s));
    if (s < 90) return s + "s";
    if (s < 5400) return Math.round(s / 60) + " min";
    return (s / 3600).toFixed(1) + " h";
  }
  function freshness(d) {
    const f = d.freshness || {};
    const now = Math.floor(Date.now() / 1000);
    const collectionTs = f.collection_ts || d.collection_ts || d.fetch_ts || d.ts;
    const sourceTs = f.source_ts || d.source_ts;
    const collectionAge = collectionTs ? now - collectionTs : (f.collection_age_s ?? d.collection_age_s ?? null);
    const sourceAge = sourceTs ? now - sourceTs : (f.source_age_s ?? d.source_age_s ?? null);
    const collectionStale = f.collection_stale_after_s != null && collectionAge != null
      ? collectionAge > f.collection_stale_after_s : f.collection_stale === true;
    const sourceStale = f.source_stale_after_s != null && sourceAge != null
      ? sourceAge > f.source_stale_after_s : f.source_stale === true;
    const stale = d.stale === true || f.state === "stale" || collectionStale || sourceStale;
    return { stale, text: `fuente ${fmtAge(sourceAge)} · recolectado ${fmtAge(collectionAge)}` };
  }
  function empty(msg, tag) {
    const b = el(); if (!b) return;
    b.innerHTML = `<div class="gltempty"><span class="ico">◍</span>${msg}` +
      (tag ? `<div style="margin-top:5px;color:#e0b64a;font-weight:600">${tag}</div>` : "") + `</div>`;
    const s = sub(); if (s) s.textContent = tag || "—";
  }
  function loading(msg) {
    const b = el(); if (!b) return;
    if (b.querySelector("table.glttb")) { const s = sub(); if (s) s.textContent = msg; return; }
    b.innerHTML = `<div class="gltempty"><span class="gltspin"></span>${msg}</div>`;
  }

  // Valor neto del strike i para la seleccion actual (columna j o suma ALL). Sin dato -> null.
  function cellVal(d, i, key) {
    if (key === "all") {
      let acc = null;
      for (let j = 0; j < d.expiries.length; j++) {
        const row = Array.isArray(d.cells[i]) ? d.cells[i] : [];
        const v = row[j];
        if (v === null || v === undefined) continue;
        acc = (acc === null ? 0 : acc) + v;
      }
      return acc;
    }
    const j = d.expiries.indexOf(key);
    const row = Array.isArray(d.cells[i]) ? d.cells[i] : [];
    return j < 0 ? null : (row[j] ?? null);
  }
  function colTotal(d, key) {
    if (key === "all") {
      const known = (d.col_totals || []).filter(v => v !== null && v !== undefined);
      return known.length ? known.reduce((a, v) => a + v, 0) : null;
    }
    const j = d.expiries.indexOf(key);
    return j < 0 ? null : d.col_totals[j];
  }

  function render(d) {
    const b = el(); if (!b) return;
    if (!Array.isArray(d.expiries) || !d.expiries.length || !Array.isArray(d.cells) || !d.cells.length) {
      empty("Matriz vacía para " + d.sym + "."); return;
    }
    const allOnly = d.expiry_scope === "all" || (d.expiries.length === 1 && d.expiries[0] === "ALL");
    if (allOnly) selKey = "all";
    else if (selKey === null || (selKey !== "all" && d.expiries.indexOf(selKey) < 0)) selKey = d.expiries[0];
    const totals = d.expiries.map((e, j) => d.col_totals ? d.col_totals[j] : null);
    const maxAbs = Math.max(1e-9, ...totals.map((t) => Math.abs(t || 0)));
    const allTot = colTotal(d, "all");

    // ---- rail DTE (arriba): expiries reales, o una unica pildora ALL si D1 solo
    // guarda el perfil agregado. Nunca se inventa un 0DTE con el `exp` del EM.
    let rail = "";
    if (!allOnly) d.expiries.forEach((exp, j) => {
      const t = totals[j];
      const dte = dteOf(exp);
      const cls = t === null || t === undefined ? "mut" : (t >= 0 ? "pos" : "neg");
      const parts = exp.split("-");
      rail += `<button class="gltexp${selKey === exp ? " sel" : ""}" data-key="${exp}" ` +
        `title="Net GEX ${exp} — click para ver sus strikes">` +
        `<span class="gltdatelbl">${MES[+parts[1] - 1]} ${+parts[2]}</span>` +
        `<span class="gltdte${dte <= 0 ? " zero" : ""}">${Math.max(0, dte)} DTE</span>` +
        `<span class="glttag"><b>${tagOf(exp)}</b>${dte <= 0 ? " ★" : ""}</span>` +
        `<span class="gltdot ${cls}">${t === null || t === undefined ? "·" : (t >= 0 ? "+" : "−")}</span>` +
        `<span class="gltvbar"><i class="${cls}" style="height:${t === null || t === undefined ? 0 : Math.max(8, Math.round(100 * Math.abs(t) / maxAbs))}%"></i></span>` +
        `<span class="gltamt ${cls}">${fmt(t)}</span></button>`;
    });
    const allCls = allTot === null || allTot === undefined ? "mut" : (allTot >= 0 ? "pos" : "neg");
    rail += `<button class="gltexp gltall${selKey === "all" ? " sel" : ""}" data-key="all" title="Perfil agregado de todos los vencimientos disponibles">` +
      `<span class="gltdatelbl">ALL</span>` +
      `<span class="gltdte">${allOnly ? "libro" : d.expiries.length + " exp"}</span>` +
      `<span class="glttag">Σ real</span>` +
      `<span class="gltdot ${allCls}">${allTot === null || allTot === undefined ? "·" : (allTot >= 0 ? "+" : "−")}</span>` +
      `<span class="gltvbar"><i class="${allCls}" style="height:${allTot === null || allTot === undefined ? 0 : Math.max(8, Math.round(100 * Math.abs(allTot) / maxAbs))}%"></i></span>` +
      `<span class="gltamt ${allCls}">${fmt(allTot)}</span></button>`;

    // ---- tabla strike-level del vencimiento elegido ----
    const vals = d.strikes.map((_, i) => cellVal(d, i, selKey));
    const known = vals.filter((v) => v !== null && v !== undefined);
    const rowMax = Math.max(1e-9, ...known.map(Math.abs));
    const strikeIndex = (v) => v === null || v === undefined ? -1
      : d.strikes.findIndex(k => Math.abs(Number(k) - Number(v)) < 1e-9);
    // CW/PW son los muros OI calculados por el motor. El extremo positivo/negativo del GEX
    // neto NO equivale a call/put wall y no se vuelve a etiquetar como tal en el navegador.
    const iCW = strikeIndex(d.call_wall);
    const iPW = strikeIndex(d.put_wall);
    const iMVC = strikeIndex(d.mvc && d.mvc.strike);
    let rows = "";
    let spotInserted = false;
    const spotRow = () => `<tr class="gltspot"><td class="glstk" style="text-align:left">SPOT</td>` +
      `<td colspan="3"><span class="gltsval">${(+d.spot).toFixed(2)}</span> · ${d.sym}</td></tr>`;
    d.strikes.forEach((k, i) => {
      if (!spotInserted && k < d.spot) {   // strikes descendentes: el spot va antes del 1o que lo cruza
        rows += spotRow(); spotInserted = true;
      }
      const v = vals[i];
      const cls = v === null || v === undefined ? "mut" : (v >= 0 ? "pos" : "neg");
      const w = v === null || v === undefined ? 0 : Math.max(1.5, 100 * Math.abs(v) / rowMax);
      const badges = [];
      if (i === iCW) badges.push(`<span class="cw" title="Call wall real por OI">CW</span>`);
      if (i === iPW) badges.push(`<span class="pw" title="Put wall real por OI">PW</span>`);
      if (i === iMVC) badges.push(`<span class="mvc" title="Mayor |GEX| del perfil visible">Γ</span>`);
      const badge = badges.join(" ");
      rows += `<tr${i === iMVC ? ' class="gltmvc"' : ""}><td class="glstk">${k}</td>` +
        `<td><div class="glttrack"><i class="${cls}" style="width:${w}%"></i></div></td>` +
        `<td class="gltval ${cls}">${fmt(v === null ? null : v)}</td>` +
        `<td class="gltbadge">${badge}</td></tr>`;
    });
    if (!spotInserted) rows += spotRow();

    const lse = d.src === "lse";
    const fr = freshness(d);
    b.innerHTML = `<div class="gltwrap"><div class="gltrail">${rail}</div>` +
      `<div class="glttbwrap"><table class="glttb">` +
      `<tr><th>Strike</th><th>Net ${lse ? "Γ×vol" : "GEX"}${selKey === "all" ? " · ALL expiries" : ""}</th><th style="text-align:right">Total</th><th></th></tr>` +
      `${rows}</table></div>` +
      `<div class="gltleg"><i class="cw"></i>CW ${d.call_wall ?? "—"}<i class="pw"></i>PW ${d.put_wall ?? "—"}<i class="mvc"></i>Γ mayor |GEX|</div>` +
      `<div class="gltfoot"><span class="${fr.stale ? "gltwarn" : ""}">${fr.stale ? "STALE · " : "FRESH · "}${srcText(d)} · ${fr.text} · fetch ${Math.round(lastFetchMs || 0)}ms</span>` +
      `<span class="gltwarn">MAPA, no gatillo</span></div></div>`;

    b.querySelectorAll(".gltexp").forEach((btn) => {
      btn.addEventListener("click", () => {
        selKey = btn.dataset.key;
        if (lastData) { lastPayload = null; render(lastData); }   // re-render local, sin refetch
      });
    });
    const s = sub();
    if (s) s.textContent = `${fr.stale ? "STALE · " : ""}${d.sym} · ${selKey === "all" ? "ALL" : selKey.slice(5)} · ${srcText(d)} · ${fr.text}`;
    if (window.providerMark) window.providerMark(d.src);
  }

  function curSymbol() {
    try {
      const s = (typeof curSym !== "undefined" && curSym) ? String(curSym).toUpperCase() : null;
      return s && s.endsWith("USDT") ? s.slice(0, -4) : s;
    }
    catch (e) { return null; }
  }

  async function tick() {
    if (window.cockpitWidgetOpen && !window.cockpitWidgetOpen("gexlive")) return;
    const sym = curSymbol();
    if (!sym) { empty("Sin símbolo activo."); return; }
    if (!/^[A-Z0-9._-]{1,12}$/.test(sym)) { empty("Símbolo inválido."); return; }
    const londonOnly = Boolean(window.chartIsLondonOnly && window.chartIsLondonOnly());
    if (sym !== lastSym) { lastSym = sym; lastData = null; lastPayload = null; selKey = null; }
    const seq = ++requestSeq;
    loading(`${sym} · leyendo cadena…`);
    const t0 = performance.now();
    try {
      const r = await fetch(`/data/gex_heatmap_${sym.toLowerCase()}.json`, { cache: "no-store" });
      if (seq !== requestSeq || sym !== curSymbol()) return;
      if (!r.ok) {
        empty(londonOnly
          ? `Esperando el primer mapa Γ×volumen de London para ${sym}.`
          : `Sin GEX live de ${sym} todavía.<br>Lo escribe <code>scripts/gex_heatmap.py</code>.`);
        return;
      }
      const raw = await r.text();
      if (seq !== requestSeq || sym !== curSymbol()) return;
      // Solo la edad cambio: no re-render de la tabla completa (mismo truco que el Heat Map).
      if (raw === lastPayload && lastData) { meta(); return; }
      const d = JSON.parse(raw);
      if (!d || !d.cells || !d.cells.length) { empty("Matriz vacía para " + sym + "."); return; }
      if (londonOnly && d.src !== "lse") {
        lastData = null;
        empty(`Esperando mapa London de ${sym}; el snapshot no-London anterior no se mostrará.`, "London-only");
        return;
      }
      if (window.providerEnabled && !window.providerEnabled(d.src)) {
        lastData = null;
        empty(`${srcText(d)} oculto en 🛰 Fuentes.`);
        return;
      }
      lastPayload = raw; lastData = d; lastFetchMs = performance.now() - t0;
      render(d);
    } catch (e) {
      if (seq !== requestSeq) return;
      empty("Error leyendo GEX live: " + (e && e.message ? e.message : e));
    }
  }
  function meta() {   // re-evalua solo la edad en la cabecera (1 Hz, sin tocar la tabla)
    if (!lastData) return;
    const s = sub();
    const fr = freshness(lastData);
    if (s) s.textContent = `${fr.stale ? "STALE · " : ""}${lastData.sym} · ${selKey === "all" ? "ALL" : String(selKey).slice(5)} · ${srcText(lastData)} · ${fr.text}`;
  }

  function start() {
    if (timer) clearInterval(timer);
    if (metaTimer) clearInterval(metaTimer);
    tick();
    timer = setInterval(tick, POLL_MS);
    metaTimer = setInterval(meta, 1000);
  }
  window.addEventListener("cockpitWidgetsVisibility", (e) => {
    if (e.detail && e.detail.visible && window.cockpitWidgetOpen("gexlive")) tick();
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
  window.gexLiveRefresh = tick;
})();
