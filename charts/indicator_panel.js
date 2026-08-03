/* indicator_panel.js — PULSO: tarjeta RSI/Bollinger arriba-izquierda del cockpit.
   Todo el dato viene del backend (frame.pulse de chart_bridge.compute_pulse): aqui NO se
   calcula ni un indicador, solo se pinta. Una sola fuente de verdad = el panel jamas puede
   contradecir a las bandas dibujadas ni a bollinger_alarm.
   Se auto-actualiza con cada frame history/bar del WebSocket + reloj de edad cada 1s. */
(function () {
  "use strict";

  const CSS = `
  #pulsecard { position:absolute; top:6px; left:8px; z-index:19; width:186px;
    background:rgba(30,34,45,.88); border:1px solid rgba(255,255,255,.07);
    border-radius:10px; padding:7px 8px 6px; backdrop-filter:blur(10px);
    box-shadow:0 4px 14px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.05);
    font-variant-numeric:tabular-nums; user-select:none; }
  #pulsecard.min { width:auto; padding:4px 7px; }
  #pulsecard.min .pgrid, #pulsecard.min .pverd, #pulsecard.min .page { display:none; }
  #pulsecard .phdr { display:flex; align-items:center; gap:5px; cursor:pointer;
    font-size:9.5px; letter-spacing:.09em; text-transform:uppercase; color:#787b86;
    font-weight:600; }
  #pulsecard .phdr .psym { color:#d1d4dc; letter-spacing:.04em; }
  #pulsecard .phdr .pcar { margin-left:auto; opacity:.5; font-size:9px; }
  #pulsecard .pgrid { display:grid; grid-template-columns:30px 1fr 1fr; gap:2px 4px;
    margin-top:6px; align-items:center; }
  #pulsecard .pgh { font-size:9px; letter-spacing:.07em; text-transform:uppercase;
    color:#787b86; font-weight:600; text-align:center; }
  #pulsecard .ptf { font-size:10px; font-weight:700; color:#9aa5b8; letter-spacing:.03em; }
  #pulsecard .ptf.on { color:#2962ff; }
  #pulsecard .cell { font-size:11.5px; font-weight:600; color:#d1d4dc; text-align:center;
    border-radius:4px; padding:2px 0; background:rgba(255,255,255,.03);
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
  #pulsecard .cell.up   { color:#26a69a; background:rgba(38,166,154,.13); }
  #pulsecard .cell.dn   { color:#ef5350; background:rgba(239,83,80,.13); }
  #pulsecard .cell.warn { color:#ffb74d; background:rgba(255,183,77,.13); }
  #pulsecard .cell.nd   { color:#787b86; background:rgba(255,255,255,.02); font-style:italic;
    font-size:9.5px; letter-spacing:-.02em; }
  #pulsecard .pverd { margin-top:6px; border-top:1px solid #363a45; padding-top:5px;
    display:flex; align-items:center; gap:6px; }
  #pulsecard .pverd .bar { width:3px; align-self:stretch; min-height:22px; border-radius:2px;
    background:#787b86; }
  #pulsecard .pverd .lab { font-size:13px; font-weight:800; letter-spacing:.04em; color:#d1d4dc; }
  #pulsecard .pverd .kind { font-size:9px; letter-spacing:.07em; text-transform:uppercase;
    color:#787b86; font-weight:600; margin-left:auto; text-align:right; line-height:1.15; }
  #pulsecard.v-up   .pverd .bar { background:#26a69a; } #pulsecard.v-up   .pverd .lab { color:#26a69a; }
  #pulsecard.v-dn   .pverd .bar { background:#ef5350; } #pulsecard.v-dn   .pverd .lab { color:#ef5350; }
  #pulsecard.v-warn .pverd .bar { background:#ffb74d; } #pulsecard.v-warn .pverd .lab { color:#ffb74d; }
  #pulsecard.v-nd   .pverd .lab { color:#787b86; font-size:11px; font-style:italic; }
  #pulsecard .page { margin-top:3px; font-size:9px; color:#787b86; letter-spacing:.02em; }
  #pulsecard .page.old { color:#e0b13c; font-style:italic; }

  /* --- rejilla de 6 ventanas (~560px de chart): la tarjeta se COMPACTA, no desaparece --- */
  #pulsecard.narrow { width:152px; padding:6px 6px 5px; }
  #pulsecard.narrow .phdr { font-size:8.5px; gap:4px; }
  #pulsecard.narrow .pgrid { grid-template-columns:26px 1fr 1fr; gap:2px 3px; margin-top:5px; }
  #pulsecard.narrow .pgh { font-size:8px; }
  #pulsecard.narrow .ptf { font-size:9px; }
  #pulsecard.narrow .cell { font-size:10.5px; }
  #pulsecard.narrow .cell.nd { font-size:8.5px; }
  #pulsecard.narrow .pverd { margin-top:5px; padding-top:4px; gap:5px; }
  #pulsecard.narrow .pverd .lab { font-size:11.5px; }
  #pulsecard.narrow .pverd .kind { font-size:8px; }
  /* la EDAD no se encoge por debajo de lo legible: un RSI de hace 19 min presentado como
     fresco es justo la mentira que la casa prohibe — en estrecho tiene que verse igual */
  #pulsecard.narrow .page { font-size:9px; }

  /* --- REFLUJO de los vecinos: nadie comparte banda horizontal con la tarjeta ---
     El pill del iman se centraba en el 100% del chart con z-index 20 > 19: en ventana ancha
     no estorbaba, pero en la rejilla de 6 su texto (nowrap) cubria la esquina y GANABA el
     apilado -> la tarjeta era invisible justo en el caso de uso real. No se sube el z-index
     (taparia el nivel del iman, que tambien importa): se centra en la franja LIBRE que queda
     a la derecha de la tarjeta, y los chips de alarma bajan debajo de ella.
     --pulse-w/--pulse-h las escribe syncMetrics() desde la caja REAL; sin panel valen 0 y
     todo vuelve exactamente al comportamiento anterior. */
  #chart { --pulse-w:0px; --pulse-h:0px; }
  #structpill { left:calc(var(--pulse-w) + (100% - var(--pulse-w)) / 2);
                max-width:calc(100% - var(--pulse-w) - 16px);
                overflow:hidden; text-overflow:ellipsis; }
  #chipbar { top:calc(var(--pulse-h) + 10px); left:8px; max-width:52%; }
  /* franja libre demasiado corta para el pill entero: en vez de RECORTARLE el "pin · 77%"
     (perder el tipo de muro y su probabilidad seria cambiar un problema por otro), baja de
     FILA y recupera el ancho completo. Lo decide syncMetrics con el scrollWidth REAL. */
  #chart.pillbelow #structpill { left:50%; top:calc(var(--pulse-h) + 10px);
                                 max-width:calc(100% - 16px); }
  #chart.pillbelow #chipbar { top:calc(var(--pulse-h) + 48px); }
  `;

  const NARROW_PX = 560;   // por debajo: rejilla de 6 ventanas -> tarjeta compacta

  const OB = 70, OS = 30;   // umbrales canonicos de Wilder para RSI(14)

  function el(tag, cls, txt) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  function fmtAgeS(s) {
    if (s < 60) return s + "s";
    if (s < 3600) return Math.floor(s / 60) + "m";
    return Math.floor(s / 3600) + "h" + Math.floor((s % 3600) / 60) + "m";
  }

  const Panel = {
    card: null, host: null, grid: null, lab: null, kind: null, ageEl: null, symEl: null,
    _ro: null, _mw: null, _mh: null,      // última caja publicada (evita reescribir la var)
    last: null,          // último pulse recibido
    lastRx: 0,           // epoch (s) de recepción — delata un puente mudo

    mount() {
      if (this.card) return;
      const host = document.getElementById("chart");
      if (!host) return;
      const st = el("style"); st.textContent = CSS; document.head.appendChild(st);

      const c = el("div"); c.id = "pulsecard"; c.className = "v-nd";
      const hdr = el("div", "phdr");
      this.symEl = el("span", "psym", "—");
      hdr.appendChild(this.symEl);
      hdr.appendChild(el("span", null, "pulso"));
      const car = el("span", "pcar", "▾"); hdr.appendChild(car);
      hdr.title = "RSI(14) + Bollinger(20,2) por marco temporal. Clic = plegar.\n"
        + "Se recalcula en el puente con las MISMAS funciones que dibujan las bandas "
        + "(confluence_engine) y que usa la alarma Bollinger — no puede contradecirlas.";
      hdr.addEventListener("click", () => {
        const min = c.classList.toggle("min");
        car.textContent = min ? "▸" : "▾";
        try { localStorage.setItem("pulseMin", min ? "1" : "0"); } catch (e) {}
        this.syncMetrics();
      });
      c.appendChild(hdr);

      this.grid = el("div", "pgrid");
      c.appendChild(this.grid);

      const v = el("div", "pverd");
      v.appendChild(el("div", "bar"));
      this.lab = el("div", "lab", "SIN DATOS");
      this.kind = el("div", "kind", "esperando");
      v.appendChild(this.lab); v.appendChild(this.kind);
      c.appendChild(v);

      this.ageEl = el("div", "page", "");
      c.appendChild(this.ageEl);

      host.appendChild(c);
      this.card = c;
      this.host = host;
      try {
        if (localStorage.getItem("pulseMin") === "1") { c.classList.add("min"); car.textContent = "▸"; }
      } catch (e) {}
      this.syncMetrics();
      if (window.ResizeObserver) {
        this._ro = new ResizeObserver(() => this.syncMetrics());
        this._ro.observe(host); this._ro.observe(c);
      }
      window.addEventListener("resize", () => this.syncMetrics());
      setInterval(() => this.tickAge(), 1000);
    },

    // Publica la caja REAL de la tarjeta como --pulse-w/--pulse-h para que el pill del imán
    // y los chips se recoloquen a su alrededor. Se escribe solo si cambia (sin bucle de RO).
    syncMetrics() {
      const host = this.host, c = this.card;
      if (!host || !c) return;
      const narrow = host.clientWidth > 0 && host.clientWidth < NARROW_PX;
      if (narrow !== c.classList.contains("narrow")) c.classList.toggle("narrow", narrow);
      const hb = host.getBoundingClientRect(), cb = c.getBoundingClientRect();
      const w = Math.round(cb.right - hb.left) + 8, h = Math.round(cb.bottom - hb.top);
      if (this._mw !== w) { host.style.setProperty("--pulse-w", w + "px"); this._mw = w; }
      if (this._mh !== h) { host.style.setProperty("--pulse-h", h + "px"); this._mh = h; }
      const pill = document.getElementById("structpill");
      const was = host.classList.contains("pillbelow");
      let below = was;
      if (!pill || pill.classList.contains("hidden")) {
        below = false;
      } else {
        const free = host.clientWidth - w - 16;
        // histéresis de 24px: en la frontera el pill no puede saltar arriba/abajo cada segundo
        if (pill.scrollWidth > free) below = true;
        else if (pill.scrollWidth < free - 24) below = false;
      }
      if (below !== was) host.classList.toggle("pillbelow", below);
    },

    // %B -> celda. Fuera de banda = estado, no adorno: >1 arriba, <0 abajo.
    pctbCell(r) {
      if (r.pctb == null) return { txt: "—", cls: "nd", tip: r.why || "sin dato" };
      const p = r.pctb;
      const txt = (p * 100).toFixed(0) + "%";
      let cls = "", tip = "%B = posición del cierre dentro de BB(20,2). 0% = banda inferior, "
        + "100% = superior. Ancho de banda " + (r.bw != null ? r.bw.toFixed(2) + "% del precio" : "—") + ".";
      if (p > 1) { cls = "up"; tip = "BANDA SUPERIOR REVENTADA (%B " + txt + "). " + tip; }
      else if (p < 0) { cls = "dn"; tip = "BANDA INFERIOR REVENTADA (%B " + txt + "). " + tip; }
      else if (p > 0.8 || p < 0.2) { cls = "warn"; tip = "Pegado a la banda. " + tip; }
      return { txt, cls, tip };
    },

    rsiCell(r) {
      if (r.rsi == null) return { txt: "—", cls: "nd", tip: r.why || "sin dato" };
      const v = r.rsi;
      const cls = v >= OB ? "dn" : v <= OS ? "up" : "";   // sobrecompra = riesgo bajista
      const tip = "RSI(14) Wilder = " + v.toFixed(2) + " sobre " + r.n + " velas de " + r.tf
        + ". ≥70 sobrecompra · ≤30 sobreventa. En medio no dice nada y por eso no se colorea.";
      return { txt: v.toFixed(1), cls, tip };
    },

    render(pulse) {
      this.mount();
      if (!this.card || !pulse) return;
      this.last = pulse;
      this.lastRx = Math.floor(Date.now() / 1000);
      this.symEl.textContent = pulse.sym || "—";

      this.grid.textContent = "";
      this.grid.appendChild(el("div", "pgh", ""));
      this.grid.appendChild(el("div", "pgh", "RSI"));
      this.grid.appendChild(el("div", "pgh", "%B"));
      (pulse.rows || []).forEach(r => {
        const tf = el("div", "ptf" + (r.active ? " on" : ""), r.tf);
        tf.title = (r.active ? "timeframe ACTIVO del chart — mismas velas que las bandas dibujadas"
                             : "contexto multi-marco desde las barras 1m del puente")
                   + "\nn=" + r.n + " velas" + (r.why ? "\n⚠ " + r.why : "");
        this.grid.appendChild(tf);
        [this.rsiCell(r), this.pctbCell(r)].forEach(cc => {
          const d = el("div", "cell " + cc.cls, cc.txt);
          d.title = cc.tip;
          this.grid.appendChild(d);
        });
      });

      const vd = pulse.verdict || { label: "SIN DATOS", kind: "nodata", why: "" };
      this.card.classList.remove("v-up", "v-dn", "v-warn", "v-nd");
      this.card.classList.add(vd.label === "ALCISTA" ? "v-up" : vd.label === "BAJISTA" ? "v-dn"
                            : vd.label === "NEUTRO" ? "v-warn" : "v-nd");
      this.lab.textContent = vd.label;
      this.kind.textContent = vd.kind === "bandwalk" ? "band-walk" :
                              vd.kind === "elastico" ? "elástico" :
                              vd.kind === "neutro" ? "en banda" : "sin dato";
      const doctrina = vd.kind === "bandwalk"
        ? "BAND-WALK: banda reventada en 2+ marcos a la vez = continuación. NO fadear."
        : vd.kind === "elastico"
        ? "ELÁSTICO: banda reventada en UN solo marco = rebote hacia la media. El sesgo es el CONTRARIO al lado roto."
        : vd.kind === "neutro"
        ? "Precio dentro de las bandas en todos los marcos: Bollinger no opina."
        : "Sin barras suficientes: el panel NO inventa un neutro.";
      this.card.title = vd.label + " — " + (vd.why || "") + "\n\n" + doctrina;
      this.tickAge();
      this.syncMetrics();   // 2 filas vs 3 cambia la altura -> los chips bajan con ella
    },

    // Edad del dato, misma regla que #h-age: si está rancio se DICE, no se disfraza.
    tickAge() {
      if (!this.ageEl) return;
      const p = this.last;
      if (!p) { this.ageEl.textContent = ""; return; }
      const now = Math.floor(Date.now() / 1000);
      if (p.ts == null) {
        this.ageEl.textContent = "sin vela";
        this.ageEl.className = "page old";
        return;
      }
      const aVela = now - p.ts, aFrame = now - this.lastRx;
      this.ageEl.textContent = "vela " + fmtAgeS(aVela) + " · frame " + fmtAgeS(aFrame);
      this.ageEl.className = "page" + (aVela > 180 || aFrame > 120 ? " old" : "");
      this.ageEl.title = "Antigüedad de la última vela usada y del último frame recibido del "
        + "puente. Si crecen, lo de arriba NO es de ahora.";
      this.syncMetrics();   // el texto del pill del imán cambia solo: se re-mide a 1 Hz
    }
  };

  window.PulsePanel = Panel;
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", () => Panel.mount());
  else Panel.mount();
})();
