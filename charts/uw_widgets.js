"use strict";
// uw_widgets.js — tres widgets del cockpit alimentados por Unusual Whales:
//   · wgt-dark   (NUEVO)        prints de bloque fuera de bolsa <- data/uw_darkpool.json
//   · wgt-prem   (existia VACIO) premium neto firmado           <- data/uw_net_prem.json
//   · wgt-gexexp (NUEVO)        GEX por vencimiento, hasta 45 DTE <- data/uw_gex_expiry.json
// Fichero aparte a proposito: live.html lo toca otro agente en paralelo.
// Killlist #3: el dark pool NO es señal. Aqui se DESCRIBE y se declara la latencia; cero
// probabilidad, cero gatillo, cero voz. Un campo ausente se pinta "—", jamas 0.
(function () {
  // CSS aqui dentro: live.html lo esta editando otro agente, se toca lo minimo.
  const CSS = `
  #wgt-dark .wgbody, #wgt-prem .wgbody, #wgt-gexexp .wgbody { padding:6px 9px; overflow-y:auto; }
  .uwwarn { background:#2a2113; border:1px solid #5a4520; color:#e0b64a; font-size:10px;
            border-radius:3px; padding:4px 6px; margin-bottom:6px; line-height:1.35; }
  .uwsec { color:#8a94a8; font-size:10px; text-transform:uppercase; letter-spacing:.4px;
           margin:9px 0 4px; border-bottom:1px solid #232838; padding-bottom:3px; }
  .uwdim { color:#5f6878; font-weight:normal; }
  .uwbar { display:flex; align-items:center; gap:6px; font-size:11px; margin:2px 0; }
  .uwbk { width:96px; color:#c3cad6; flex:none; font-variant-numeric:tabular-nums; }
  .uwbt { flex:1; background:#1b1f2b; height:9px; border-radius:2px; overflow:hidden; }
  .uwbt i { display:block; height:100%; background:#3d7de0; }
  .uwbt i.gpos { background:#26a69a; } .uwbt i.gneg { background:#f23645; }
  .uwbv { width:96px; text-align:right; color:#98a2b3; flex:none;
          font-variant-numeric:tabular-nums; }
  .uwpr { display:flex; gap:6px; font-size:11px; padding:2px 0; border-bottom:1px solid #1b1f2b;
          font-variant-numeric:tabular-nums; }
  .uwpt { width:44px; color:#6b7484; flex:none; }
  .uwpp { width:60px; color:#e0e3eb; flex:none; text-align:right; }
  .uwps { width:52px; color:#98a2b3; flex:none; text-align:right; }
  .uwpm { flex:1; color:#c3cad6; text-align:right; }
  .uwpd { width:52px; flex:none; text-align:right; color:#6b7484; }
  .uwbig { font-size:26px; font-weight:600; text-align:center; margin:4px 0 0;
           font-variant-numeric:tabular-nums; }
  .uwbigsub { text-align:center; color:#6b7484; font-size:10px; margin-bottom:7px; }
  .uwspark { width:100%; height:46px; display:block; margin-top:3px; }
  .uwsrc { color:#5f6878; font-size:9.5px; line-height:1.4; margin-top:9px;
           border-top:1px solid #232838; padding-top:5px; }
  .uwsrc code { color:#7d8798; }`;
  const st = document.createElement("style");
  st.textContent = CSS;
  document.head.appendChild(st);

  const POLL_MS = 20000;
  const NBSP = " ";

  function sym() {
    try { return (typeof curSym !== "undefined" && curSym) ? String(curSym).toUpperCase() : null; }
    catch (e) { return null; }
  }
  function isOpen(id) {
    try {
      if (window.cockpitWidgetOpen) return window.cockpitWidgetOpen(id);
      return typeof WG !== "undefined" && WG.open ? !!WG.open[id] : true;
    }
    catch (e) { return true; }
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // "—" es la respuesta honesta a un null. Nunca 0.
  function money(n) {
    if (n == null || !isFinite(n)) return "—";
    const a = Math.abs(n), s = n < 0 ? "−" : "";
    if (a >= 1e9) return s + "$" + (a / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return s + "$" + (a / 1e6).toFixed(2) + "M";
    if (a >= 1e3) return s + "$" + (a / 1e3).toFixed(1) + "k";
    return s + "$" + a.toFixed(0);
  }
  function qty(n) {
    if (n == null || !isFinite(n)) return "—";
    if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
    return String(n);
  }
  const pct = (n) => (n == null || !isFinite(n)) ? "—" : n.toFixed(1) + "%";
  const px = (n) => (n == null || !isFinite(n)) ? "—" : (+n).toFixed(2);
  function age(s) {
    if (s == null || !isFinite(s)) return "edad ?";
    if (s < 90) return Math.round(s) + " s";
    if (s < 5400) return (s / 60).toFixed(1) + " min";
    if (s < 172800) return (s / 3600).toFixed(1) + " h";
    return (s / 86400).toFixed(1) + " d";
  }
  const hhmm = (ts) => new Date(ts * 1000).toLocaleTimeString("es-ES",
    { timeZone: "America/Toronto", hour: "2-digit", minute: "2-digit" });

  function row(k, v, cls) {
    return `<div class="techrow"><span class="techk">${k}</span>` +
           `<span class="techv ${cls || ""}">${v}</span></div>`;
  }
  function empty(msg, why) {
    return `<div class="wgempty"><div class="wgeico">◌</div>` +
           `<div class="wgemsg">${esc(msg)}</div><p>${esc(why || "")}</p></div>`;
  }
  function parts(id) {
    const w = document.getElementById("wgt-" + id);
    return w ? { body: w.querySelector(".wgbody"), sub: w.querySelector(".wgsub") } : null;
  }
  // Un fallo se enseña con su motivo; el widget nunca se queda con datos viejos mintiendo.
  function fail(p, msg, why) {
    if (!p) return;
    p.sub.textContent = "sin dato";
    p.sub.className = "wgsub tstale";
    p.body.className = "wgbody wgempty";
    p.body.innerHTML = empty(msg, why);
  }
  async function grab(file) {
    const r = await fetch("/data/" + file + "?t=" + Date.now());
    if (!r.ok) throw new Error("HTTP " + r.status + " — ¿daemon parado?");
    return r.json();
  }

  // ------------------------------------------------- dark pool (DESCRIPTIVO)
  const DARK_NOTE = "DESCRIPTIVO · no dispara — killlist #3: el dark pool no es señal";

  function bars(levels) {
    if (!levels || !levels.rows || !levels.rows.length) return "";
    const mx = Math.max.apply(null, levels.rows.map((r) => r.size)) || 1;
    const step = levels.step;
    return `<div class="uwsec">Niveles con más volumen oculto ` +
      `<span class="uwdim">(bucket ${px(step)})</span></div>` +
      levels.rows.map((r) =>
        `<div class="uwbar"><span class="uwbk">${px(r.price)}–${px(r.price + step)}</span>` +
        `<span class="uwbt"><i style="width:${(100 * r.size / mx).toFixed(1)}%"></i></span>` +
        `<span class="uwbv">${qty(r.size)}${NBSP}·${NBSP}${pct(r.pct)}</span></div>`).join("");
  }

  function prints(rows) {
    if (!rows || !rows.length) return "";
    return `<div class="uwsec">Prints grandes recientes</div>` +
      rows.slice(0, 8).map((p) => {
        const d = p.vs_mid;
        const cls = d == null ? "" : d > 0 ? "tpos" : d < 0 ? "tneg" : "";
        const tag = d == null ? "s/NBBO" : (d > 0 ? "+" : "") + d.toFixed(3);
        return `<div class="uwpr"><span class="uwpt">${hhmm(p.ts)}</span>` +
               `<span class="uwpp">${px(p.price)}</span>` +
               `<span class="uwps">${qty(p.size)}</span>` +
               `<span class="uwpm">${money(p.premium)}</span>` +
               `<span class="uwpd ${cls}">${tag}</span></div>`;
      }).join("");
  }

  function drawDark(d) {
    const p = parts("dark"); if (!p) return;
    if (d.error) return fail(p, "Dark pool sin dato", d.error);
    const s = sym();
    if (!s) return fail(p, "Sin símbolo", "el cockpit aún no fijó el ticker");
    const v = (d.syms || {})[s];
    if (!v) return fail(p, "Símbolo no cubierto",
      s + " no está en la lista de uw_darkpool.py (capitanes + memoria). Aquí no se inventa.");
    if (v.error) return fail(p, "Dark pool sin dato para " + s, v.error);

    const lat = v.latency || {};
    p.sub.textContent = "UW · " + age(lat.feed_age_s);
    p.sub.className = "wgsub" + (lat.feed_age_s > 900 ? " tstale" : "");
    p.body.className = "wgbody";

    const ds = v.dark_share, vl = v.vs_last, vm = v.vs_mid;
    p.body.innerHTML =
      `<div class="uwwarn">${DARK_NOTE}</div>` +
      row("prints", qty(v.n_prints)) +
      row("volumen oculto", qty(v.total_size) + " acc") +
      row("prima", money(v.total_premium)) +
      row("último print", px(v.last_price)) +
      (ds ? row("cuota oculta", pct(ds.pct) +
        ` <span class="uwdim">de ${qty(ds.consolidated)} en ${age(ds.window_s)}</span>`) : "") +
      (vl ? row("vs último precio",
        `<span class="tpos">${pct(vl.above_pct)}↑</span> / ` +
        `<span class="tneg">${pct(vl.below_pct)}↓</span>`) : "") +
      (vm ? row("vs punto medio NBBO",
        `${pct(vm.above_mid_pct)}↑ · ${pct(vm.at_mid_pct)}= · ${pct(vm.below_mid_pct)}↓`) : "") +
      bars(v.levels) + prints(v.prints) +
      `<div class="uwsrc">Fuente: UW <code>/api/darkpool/${esc(s)}</code> · print más nuevo ` +
      `${esc(lat.newest_iso || "?")} (${age(lat.feed_age_s)}) · retraso TRF mediano ` +
      `${lat.trf_lag_med_s == null ? "—" : lat.trf_lag_med_s + " s"}.<br>` +
      `El reparto arriba/abajo describe DÓNDE se imprimió, no quién fue el agresor: en dark ` +
      `pool el cruce al punto medio es el diseño.</div>`;
  }

  // ------------------------------------------------- premium neto firmado
  function spark(series, w, h) {
    if (!series || series.length < 2) return "";
    const ys = series.map((r) => r.cum);
    const lo = Math.min.apply(null, ys), hi = Math.max.apply(null, ys);
    const span = (hi - lo) || 1;
    const X = (i) => (w * i / (series.length - 1)).toFixed(1);
    const Y = (y) => (h - (h - 2) * (y - lo) / span - 1).toFixed(1);
    const pts = series.map((r, i) => X(i) + "," + Y(r.cum)).join(" ");
    const last = ys[ys.length - 1];
    const col = last >= 0 ? "#26a69a" : "#f23645";
    const zero = (lo <= 0 && hi >= 0)
      ? `<line x1="0" y1="${Y(0)}" x2="${w}" y2="${Y(0)}" stroke="#3a4460" stroke-dasharray="3 3"/>` : "";
    return `<div class="uwsec">Premium firmado acumulado <span class="uwdim">` +
      `(${series.length} buckets de 1 min)</span></div>` +
      `<svg class="uwspark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">${zero}` +
      `<polyline points="${pts}" fill="none" stroke="${col}" stroke-width="1.5"/></svg>`;
  }

  function win(label, o) {
    if (!o) return row(label, "—", "");   // sin buckets en la ventana: null explicito
    const c = o.signed_premium > 0 ? "tpos" : o.signed_premium < 0 ? "tneg" : "";
    return row(label, money(o.signed_premium) +
      ` <span class="uwdim">(${o.n_buckets} min)</span>`, c);
  }

  function drawPrem(d) {
    const p = parts("prem"); if (!p) return;
    if (d.error) return fail(p, "Premium neto sin dato", d.error);
    const s = sym();
    if (!s) return fail(p, "Sin símbolo", "el cockpit aún no fijó el ticker");
    const v = (d.syms || {})[s];
    if (!v) return fail(p, "Símbolo no cubierto",
      s + " no está en la lista de uw_net_prem.py (capitanes + memoria). Aquí no se inventa.");
    if (v.error) return fail(p, "Premium neto sin dato para " + s, v.error);

    p.sub.textContent = "UW · " + age(v.feed_age_s);
    p.sub.className = "wgsub" + (v.feed_age_s > 900 ? " tstale" : "");
    p.body.className = "wgbody";

    const day = v.day || {};
    const sc = day.signed_premium > 0 ? "tpos" : day.signed_premium < 0 ? "tneg" : "";
    const w = v.windows || {};
    p.body.innerHTML =
      `<div class="uwbig ${sc}">${money(day.signed_premium)}</div>` +
      `<div class="uwbigsub">firmado del día · ${esc(s)}</div>` +
      row("net call premium", money(day.net_call_premium),
          day.net_call_premium > 0 ? "tpos" : day.net_call_premium < 0 ? "tneg" : "") +
      row("net put premium", money(day.net_put_premium),
          day.net_put_premium > 0 ? "tpos" : day.net_put_premium < 0 ? "tneg" : "") +
      win("últimos 15 min", w["15"]) +
      win("últimos 60 min", w["60"]) +
      row("volumen C / P", qty(day.call_volume) + " / " + qty(day.put_volume)) +
      row("delta neto", qty(day.net_delta)) +
      spark(v.series, 260, 46) +
      `<div class="uwsrc">Fuente: UW <code>/api/stock/${esc(s)}/net-prem-ticks</code>, ` +
      `firmado por lado agresor en origen · último bucket ${esc(v.feed_ts || "?")} ` +
      `(${age(v.feed_age_s)}).<br><b>firmado = net call − net put</b> ` +
      `(vender un put es alcista, por eso RESTA). No dispara órdenes: la doctrina reserva ` +
      `el disparo a IBKR en tiempo real.</div>`;
  }

  // ------------------------------------------------- GEX por vencimiento (MAPA, EOD)
  function drawGexExp(d) {
    const p = parts("gexexp"); if (!p) return;
    if (d.error) return fail(p, "GEX por vencimiento sin dato", d.error);
    const s = sym();
    if (!s) return fail(p, "Sin símbolo", "el cockpit aún no fijó el ticker");
    const v = (d.syms || {})[s];
    if (!v) return fail(p, "Símbolo no cubierto",
      s + " no está en data/universe_gamma.txt. Aquí no se inventa.");
    if (v.error) return fail(p, "GEX por vencimiento sin dato para " + s, v.error);

    const days = d.stamp_age_days;
    p.sub.textContent = "UW EOD · cierre " + (v.asof_date || "?") +
      (days == null ? "" : " (" + days + " d)");
    p.sub.className = "wgsub tstale";     // EOD: SIEMPRE marcado rancio, jamas dispara
    p.body.className = "wgbody";

    const rows = v.rows || [];
    const mx = Math.max.apply(null, rows.map((r) => Math.abs(r.net_gex))) || 1;
    const bar = rows.map((r) => {
      const w = (100 * Math.abs(r.net_gex) / mx).toFixed(1);
      const pos = r.net_gex >= 0;
      return `<div class="uwbar"><span class="uwbk">${esc(r.expiry.slice(5))}` +
        `<span class="uwdim"> ${r.dte}d</span></span>` +
        `<span class="uwbt"><i class="${pos ? "gpos" : "gneg"}" style="width:${w}%"></i></span>` +
        `<span class="uwbv ${pos ? "tpos" : "tneg"}">${qty(Math.round(r.net_gex))}</span></div>`;
    }).join("");

    p.body.innerHTML =
      `<div class="uwwarn">MAPA · EOD diario — no dispara. El disparo es de IBKR en vivo.</div>` +
      row("vencimientos", qty(v.n_expiries) + ` <span class="uwdim">≤${d.dte_max} DTE</span>`) +
      row("hasta", esc(v.exp_hasta || "—")) +
      row("net GEX total", qty(Math.round(v.net_gex_total)),
          v.net_gex_total > 0 ? "tpos" : v.net_gex_total < 0 ? "tneg" : "") +
      `<div class="uwsec">Net GEX por vencimiento <span class="uwdim">` +
      `(verde = amparan · rojo = amplían)</span></div>` + bar +
      `<div class="uwsrc">Fuente: UW <code>/api/stock/${esc(s)}/greek-exposure/expiry</code>, ` +
      `un request por símbolo, sin paginar · cierre ${esc(v.asof_date || "?")}` +
      `${days == null ? "" : " (" + days + " días)"}.<br>` +
      `Existe porque el archivo propio se para en el mensual siguiente ` +
      `(<code>poly_chain_archive.py:445</code>) y la cadena viva en 2 vencimientos ` +
      `(<code>provider_bridge.py:160</code>): 08-24…08-31 no estaba en ninguna parte.</div>`;
  }

  // ------------------------------------------------- ciclo
  async function tick() {
    if (window.chartIsLondonOnly && window.chartIsLondonOnly()) {
      if (isOpen("dark")) fail(parts("dark"), "Desactivado en London-only", "Fuente UW no iniciada.");
      if (isOpen("prem")) fail(parts("prem"), "Desactivado en London-only", "Fuente UW no iniciada.");
      if (isOpen("gexexp")) fail(parts("gexexp"), "Desactivado en London-only", "Fuente UW no iniciada.");
      return;
    }
    if (isOpen("dark")) {
      try { drawDark(await grab("uw_darkpool.json")); }
      catch (e) { fail(parts("dark"), "Dark pool no disponible", e.message); }
    }
    if (isOpen("prem")) {
      try { drawPrem(await grab("uw_net_prem.json")); }
      catch (e) { fail(parts("prem"), "Premium neto no disponible", e.message); }
    }
    if (isOpen("gexexp")) {
      try { drawGexExp(await grab("uw_gex_expiry.json")); }
      catch (e) { fail(parts("gexexp"), "GEX por vencimiento no disponible", e.message); }
    }
  }

  function start() {
    tick();
    setInterval(tick, POLL_MS);
    // el bridge fija curSym unos segundos despues de cargar: sin esto los paneles se quedan
    // 20 s diciendo "sin simbolo" al abrir el cockpit.
    let tries = 0;
    const wait = setInterval(() => {
      if (sym() || ++tries > 20) { clearInterval(wait); tick(); }
    }, 700);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
  window.uwWidgetsTick = tick;   // el cambio de simbolo puede forzar un repintado
})();
