/* Order-flow workspace: the detector math lives in orderflow_footprint.cpp. This file
   renders only reported tape; NO_TAPE/STALE/UNKNOWN are first-class states, never zero flow. */
(function () {
  "use strict";

  const COLORS = {
    bg: "#0a0e16", panel: "#101621", grid: "rgba(126,143,170,.14)", text: "#dce4f2",
    muted: "#718097", buy: "#35d0b2", sell: "#ff6973", amber: "#f6c85f",
    blue: "#5a9dff", unknown: "#8893a5", violet: "#c58cff"
  };
  const TFS = ["1m", "5m", "15m", "30m"];
  const host = document.getElementById("chart");
  if (!host) return;

  const css = document.createElement("style");
  css.textContent = `
    :root{--footprintw:0px}
    #chart{right:calc(var(--dockw) + var(--footprintw))!important}
    #ofpanel{position:fixed;z-index:43;display:none;flex-direction:column;overflow:hidden;
      color:#dce4f2;background:#0a0e16;border:1px solid #2c3850;box-shadow:0 20px 55px rgba(0,0,0,.72);
      font:12px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-variant-numeric:tabular-nums}
    #ofpanel.on{display:flex}#ofpanel.full{border-radius:0}#ofpanel.split{border-radius:9px 0 0 9px}
    .ofhead{min-height:48px;display:flex;align-items:center;gap:10px;padding:7px 10px;background:linear-gradient(180deg,#171f2c,#111824);
      border-bottom:1px solid #273248;box-shadow:0 5px 18px rgba(0,0,0,.2);flex-wrap:wrap}
    .ofbrand{display:flex;align-items:center;gap:8px;min-width:178px}.ofmark{display:grid;place-items:center;width:29px;height:29px;
      border:1px solid #3d4b65;border-radius:7px;color:#f6c85f;background:#111722;font:800 11px ui-monospace,SFMono-Regular,Menlo,monospace}
    .oftitle{font-size:11px;font-weight:850;letter-spacing:.09em}.ofsub{font-size:8.5px;color:#6f7e94;margin-top:2px;letter-spacing:.04em}
    .ofbadge{display:inline-flex;align-items:center;gap:5px;min-height:22px;padding:3px 7px;border:1px solid #344158;border-radius:999px;
      color:#8b98ac;background:#141b27;font-size:9px;font-weight:800;letter-spacing:.045em;white-space:nowrap}
    .ofbadge.live{border-color:rgba(53,208,178,.42);color:#52dfc3;background:rgba(23,100,89,.18)}
    .ofbadge.stale,.ofbadge.warn{border-color:rgba(246,200,95,.44);color:#f6c85f;background:rgba(126,90,10,.16)}
    .ofbadge.bad{border-color:rgba(255,105,115,.45);color:#ff7b84;background:rgba(122,32,42,.16)}
    .ofdot{width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor}
    .ofcontrols{display:flex;align-items:center;border:1px solid #303c53;border-radius:6px;overflow:hidden;background:#0e141e}
    .ofcontrols button{border:0;border-right:1px solid #303c53;background:transparent;color:#78869c;padding:5px 8px;
      font-family:inherit;font-size:9px;font-weight:800;cursor:pointer}
    .ofcontrols button:last-child{border-right:0}.ofcontrols button:hover{color:#dce4f2;background:#1b2636}.ofcontrols button.on{color:#fff;background:#315fae}
    .ofheadspacer{flex:1}.ofquality{min-width:138px}.ofqtop{display:flex;justify-content:space-between;color:#7b899d;font-size:8.5px;margin-bottom:4px}
    .ofqtrack{height:3px;border-radius:3px;background:#293347;overflow:hidden}.ofqfill{display:block;height:100%;background:#35d0b2;transition:width .2s}
    .oficon{width:27px;height:27px;padding:0!important;font-size:13px!important}.ofclose:hover{color:#ff6973!important}
    .ofpatterns{display:flex;align-items:center;gap:5px;min-height:35px;padding:5px 9px;border-bottom:1px solid #202a3b;background:#0e141e;overflow-x:auto}
    .ofpatterns:empty:before{content:"SIN PATRÓN ACTIVO";color:#4e5b70;font-size:8px;font-weight:800;letter-spacing:.09em}
    .ofchip{display:inline-flex;align-items:center;gap:5px;flex:none;border:1px solid #354158;border-radius:5px;padding:4px 7px;background:#151d2a;
      color:#aab6c9;font:800 8.5px inherit;letter-spacing:.025em;cursor:pointer}.ofchip:hover,.ofchip.sel{border-color:#6f86aa;color:#eef3fb;background:#1c293c}
    .ofchip.up{color:#53ddc2;border-color:rgba(53,208,178,.35)}.ofchip.dn{color:#ff7c85;border-color:rgba(255,105,115,.38)}
    .ofchip.form{border-style:dashed;color:#f6c85f}.ofchipscore{opacity:.62;font-weight:700}
    .ofbody{position:relative;display:flex;flex:1;min-height:0}.ofviewport{position:relative;flex:1;min-width:0;overflow:auto;background:#0a0e16;
      scrollbar-color:#354158 transparent;overscroll-behavior:contain}.ofcanvas{display:block;background:#0a0e16}
    #ofpanel.degraded .ofcanvas{opacity:.48;filter:saturate(.65)}#ofpanel.degraded .ofviewport:after{content:"";position:sticky;display:block;inset:0;
      pointer-events:none;background:repeating-linear-gradient(-45deg,transparent 0 13px,rgba(246,200,95,.025) 13px 14px)}
    .ofempty{position:absolute;inset:0;display:none;place-items:center;padding:30px;text-align:center;background:radial-gradient(circle at 50% 40%,#131d2b,#0a0e16 65%)}
    .ofempty.on{display:grid}.ofemptybox{max-width:510px}.ofemptyicon{width:54px;height:54px;margin:0 auto 13px;display:grid;place-items:center;border-radius:14px;
      border:1px solid #38445a;background:#121925;color:#f6c85f;font:800 14px ui-monospace}.ofemptytitle{font-size:14px;font-weight:850;letter-spacing:.07em}
    .ofemptywhy{color:#909db1;line-height:1.55;margin-top:8px}.ofemptyfeed{margin-top:12px;color:#627087;font:9px ui-monospace,SFMono-Regular,Menlo,monospace}
    .oftip{position:fixed;z-index:96;display:none;pointer-events:none;max-width:260px;padding:8px 9px;border:1px solid #3b4962;border-radius:6px;
      background:rgba(14,20,30,.97);box-shadow:0 8px 24px rgba(0,0,0,.55);color:#dce4f2;font:10px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-line}
    .ofinspect{display:none;width:260px;flex:none;border-left:1px solid #273248;background:#101722;padding:12px;overflow:auto}.ofinspect.on{display:block}
    .ofihead{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.ofikind{font-size:11px;font-weight:850;letter-spacing:.05em}.ofistatus{font-size:8px;font-weight:850;color:#f6c85f}
    .ofiscore{margin-top:12px;padding:8px;border:1px solid #2f3b51;border-radius:6px;background:#141d2a}.ofiscore strong{font-size:19px;color:#dce4f2}
    .ofilabel{font-size:8px;color:#65738a;letter-spacing:.08em}.ofiwhy{margin-top:11px;color:#b6c1d2;line-height:1.5}.ofimeta{margin-top:12px;color:#68778e;font:9px/1.65 ui-monospace}
    .offoot{min-height:30px;display:flex;align-items:center;gap:13px;padding:5px 10px;border-top:1px solid #263146;background:#101722;color:#65748b;font-size:8.5px;overflow-x:auto;white-space:nowrap}
    .offoot b{font-weight:850}.ofbuy{color:#35d0b2}.ofsell{color:#ff6973}.ofamber{color:#f6c85f}.ofblue{color:#5a9dff}.ofunknown{color:#9ba5b4}
    .ofsource{margin-left:auto;color:#7e8ca2;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
    @media(max-width:800px){#ofpanel.split{border-radius:0}.ofhead{gap:6px}.ofbrand{min-width:142px}.ofquality{display:none}.ofinspect{position:absolute;right:0;top:0;bottom:0;z-index:4;box-shadow:-10px 0 30px #000}.offoot{font-size:8px}}
  `;
  document.head.appendChild(css);

  const panel = document.createElement("section");
  panel.id = "ofpanel";
  panel.setAttribute("aria-label", "Order Flow Bid por Ask");
  panel.innerHTML = `
    <header class="ofhead">
      <div class="ofbrand"><span class="ofmark">B×A</span><div><div class="oftitle">ORDER FLOW · BID × ASK</div><div class="ofsub">HUELLA DE EJECUCIONES · SEÑAL-SOLAMENTE</div></div></div>
      <span class="ofbadge oflive"><i class="ofdot"></i><span>NO TAPE</span></span>
      <span class="ofbadge ofprov">UNKNOWN</span>
      <div class="ofcontrols offeeds" aria-label="Fuente de cinta"><button data-feed="equity">ACCIONES</button><button data-feed="perp">PERP 24/7</button></div>
      <div class="ofcontrols oftfs" aria-label="Temporalidad footprint"></div>
      <div class="ofheadspacer"></div>
      <div class="ofquality"><div class="ofqtop"><span>VOLUMEN CLASIFICADO</span><b>—</b></div><div class="ofqtrack"><i class="ofqfill"></i></div></div>
      <div class="ofcontrols ofmodes"><button data-mode="full" title="Huella a pantalla completa">HUELLA</button><button data-mode="split" title="Velas y huella lado a lado">DIVIDIR</button></div>
      <div class="ofcontrols"><button class="oficon ofclose" title="Volver a velas" aria-label="Cerrar footprint">×</button></div>
    </header>
    <div class="ofpatterns" aria-label="Patrones detectados"></div>
    <div class="ofbody"><div class="ofviewport"><canvas class="ofcanvas" tabindex="0" aria-label="Gráfico footprint Bid por Ask"></canvas>
      <div class="ofempty" role="status" aria-live="polite"><div class="ofemptybox"><div class="ofemptyicon">NO∑</div><div class="ofemptytitle"></div><div class="ofemptywhy"></div><div class="ofemptyfeed"></div></div></div></div>
      <aside class="ofinspect" aria-live="polite"></aside></div>
    <footer class="offoot"><span><b class="ofbuy">ASK</b> compra agresiva</span><span><b class="ofsell">BID</b> venta agresiva</span><span><b class="ofblue">AZUL</b> 3× imbalance</span><span><b class="ofamber">ÁMBAR</b> POC cluster</span><span><b class="ofunknown">···</b> volumen desconocido</span><span class="ofsource">—</span></footer>
    <div class="oftip" role="tooltip"></div>`;
  document.body.appendChild(panel);

  const canvas = panel.querySelector(".ofcanvas"), viewport = panel.querySelector(".ofviewport"),
    empty = panel.querySelector(".ofempty"), patterns = panel.querySelector(".ofpatterns"),
    inspector = panel.querySelector(".ofinspect"), tooltip = panel.querySelector(".oftip"),
    live = panel.querySelector(".oflive"), provenance = panel.querySelector(".ofprov"),
    qnum = panel.querySelector(".ofqtop b"), qfill = panel.querySelector(".ofqfill"),
    sourceEl = panel.querySelector(".ofsource"), tfbox = panel.querySelector(".oftfs"),
    feedbox = panel.querySelector(".offeeds");

  let last = null, visible = false, transport = null, selectedTf = "5m", tfLocked = false;
  let selectedFeed = localStorage.getItem("orderflow_feed") === "perp" ? "perp" : "equity";
  let mode = localStorage.getItem("orderflow_mode") === "split" ? "split" : "full";
  let pollTimer = 0, selectedPattern = null, hits = [], cellHits = [], lastViewportKey = "";
  let rowHeight = Number(localStorage.getItem("orderflow_row_height")) || 18;

  for (const tf of TFS) {
    const b = document.createElement("button"); b.type = "button"; b.dataset.tf = tf; b.textContent = tf;
    b.addEventListener("click", () => { selectedTf = tf; tfLocked = true; paintControls(); requestFrame(); });
    tfbox.appendChild(b);
  }
  feedbox.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
    selectedFeed = b.dataset.feed; localStorage.setItem("orderflow_feed", selectedFeed);
    selectedPattern = null; lastViewportKey = ""; paintControls(); requestFrame();
  }));
  panel.querySelectorAll(".ofmodes button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode)));
  panel.querySelector(".ofclose").addEventListener("click", () => {
    if (window.setIndicator) window.setIndicator("footprint", false); else setVisible(false);
  });

  const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
  const fmt = n => {
    n = Number(n) || 0; const a = Math.abs(n);
    return a >= 1e9 ? (n / 1e9).toFixed(1) + "b" : a >= 1e6 ? (n / 1e6).toFixed(1) + "m" : a >= 1e3 ? (n / 1e3).toFixed(1) + "k" : Math.round(n).toString();
  };
  const signed = n => `${Number(n) >= 0 ? "+" : ""}${fmt(n)}`;
  const pkey = (bar, p) => `${bar.time}|${p.kind}|${(p.zone || []).join(":")}`;
  const pct = n => Number.isFinite(Number(n)) ? `${Number(n).toFixed(0)}%` : "—";

  function setMode(next) {
    mode = next === "split" && window.innerWidth > 800 ? "split" : "full";
    localStorage.setItem("orderflow_mode", mode); syncLayout(); paintControls(); draw();
  }
  function paintControls() {
    tfbox.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.tf === selectedTf));
    feedbox.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.feed === selectedFeed));
    panel.querySelectorAll(".ofmodes button").forEach(b => b.classList.toggle("on", b.dataset.mode === mode));
  }
  function setFeed(next) {
    const wanted = next === "perp" ? "perp" : "equity";
    if (selectedFeed === wanted) return;
    selectedFeed = wanted; localStorage.setItem("orderflow_feed", selectedFeed);
    selectedPattern = null; lastViewportKey = ""; paintControls(); requestFrame();
  }
  function syncLayout() {
    if (!visible) { document.documentElement.style.setProperty("--footprintw", "0px"); return; }
    if (mode === "split" && window.innerWidth <= 800) mode = "full";
    document.documentElement.style.setProperty("--footprintw", "0px");
    requestAnimationFrame(() => {
      const r = host.getBoundingClientRect();
      if (mode === "split") {
        const width = clamp(Math.round(r.width * .54), 520, 820);
        document.documentElement.style.setProperty("--footprintw", `${width}px`);
        Object.assign(panel.style, {top:`${r.top}px`, bottom:`${window.innerHeight-r.bottom}px`,
          left:"auto", right:"var(--dockw)", width:`${width}px`, height:"auto"});
      } else {
        Object.assign(panel.style, {top:`${r.top}px`, left:`${r.left}px`, width:`${r.width}px`,
          height:`${r.height}px`, right:"auto", bottom:"auto"});
      }
      panel.classList.toggle("split", mode === "split"); panel.classList.toggle("full", mode === "full");
      paintControls(); draw();
      try { window.dispatchEvent(new Event("resize")); } catch (_) {}
    });
  }

  function sourceText(m) {
    const parts = [m.source || m.market_provider || "sin proveedor"];
    if (m.quality) parts.push(String(m.quality).replaceAll("_", " "));
    if (m.native_side_pct != null) parts.push(`nativo ${pct(m.native_side_pct)}`);
    if (m.quote_rule_pct != null) parts.push(`quote ${pct(m.quote_rule_pct)}`);
    if (m.tick_rule_pct != null) parts.push(`tick ${pct(m.tick_rule_pct)}`);
    if (m.unknown_pct != null) parts.push(`unknown ${pct(m.unknown_pct)}`);
    return parts.join(" · ");
  }
  function statusStyle(state) {
    live.className = "ofbadge oflive " + (state === "LIVE" ? "live" : ["STALE","QUIET"].includes(state) ? "stale" : state === "BROKEN" ? "bad" : "warn");
    live.querySelector("span").textContent = state === "LIVE" ? `LIVE · ${Math.round(last.age_s || 0)}s` : state.replaceAll("_", " ") + (state === "STALE" ? ` · ${Math.round(last.age_s || 0)}s` : "");
    panel.classList.toggle("degraded", state !== "LIVE" || Number(last.classification_pct || 0) < 70);
    const sp = String(last.side_provenance || "UNKNOWN");
    provenance.textContent = selectedFeed === "perp" ? `${sp} · PROXY ≠ ACCIÓN` : sp;
    provenance.className = "ofbadge ofprov " + (sp === "NATIVE" ? "live" : sp === "INFERRED" || sp === "MIXED" ? "warn" : "bad");
    const q = clamp(Number(last.classification_pct) || 0, 0, 100); qnum.textContent = pct(last.classification_pct); qfill.style.width = `${q}%`;
    qfill.style.background = q >= 85 ? COLORS.buy : q >= 70 ? COLORS.amber : COLORS.sell;
    sourceEl.textContent = sourceText(last); sourceEl.title = sourceText(last);
  }

  function paintEmpty(state) {
    const noBars = !(last?.bars || []).length;
    empty.classList.toggle("on", noBars || ["NO_TAPE", "BROKEN", "UNSUPPORTED_TF"].includes(state));
    canvas.style.visibility = noBars ? "hidden" : "visible";
    const title = empty.querySelector(".ofemptytitle"), why = empty.querySelector(".ofemptywhy"), feed = empty.querySelector(".ofemptyfeed");
    title.textContent = state === "BROKEN" ? "SNAPSHOT DAÑADO" : state === "UNSUPPORTED_TF" ? "TEMPORALIDAD NO DISPONIBLE" : "SIN CINTA COMPLETA";
    why.textContent = last?.reason || "Este indicador necesita cada ejecución y un lado agresor auditable.";
    feed.textContent = `${last?.sym || "—"} · ${selectedTf} · ${selectedFeed === "perp" ? "PERP 24/7, no acción US" : "ACCIONES US"} · proveedor ${last?.market_provider || last?.source || "no conectado"}`;
  }

  function patternLabel(p) {
    const names = {ABSORPTION:"ABSORCIÓN",DELTA_FLIP:"GIRO DELTA",PRICE_DELTA_DIVERGENCE:"DIVERGENCIA",STACKED_IMBALANCE:"IMBALANCE APILADO",DOUBLE_HVN:"DOBLE HVN",TRIPLE_HVN:"TRIPLE HVN"};
    return names[p.kind] || String(p.kind || "PATRÓN").replaceAll("_", " ");
  }
  function allPatterns() {
    const out = [];
    for (const bar of (last?.bars || [])) for (const p of (bar.patterns || [])) out.push({bar, p, key:pkey(bar,p)});
    return out;
  }
  function paintPatterns() {
    patterns.replaceChildren();
    for (const item of allPatterns().slice(-12)) {
      const b = document.createElement("button"); b.type = "button";
      b.className = "ofchip" + (item.p.side === "BULLISH" ? " up" : item.p.side === "BEARISH" ? " dn" : "") + (item.p.status === "FORMING" ? " form" : "") + (selectedPattern === item.key ? " sel" : "");
      const state = item.p.status === "FORMING" ? "◌" : "✓";
      b.append(document.createTextNode(`${state} ${patternLabel(item.p)} `));
      const score = document.createElement("span"); score.className = "ofchipscore"; score.textContent = `${item.p.evidence_score || 0}`; b.appendChild(score);
      b.title = item.p.why || ""; b.addEventListener("click", () => selectPattern(item)); patterns.appendChild(b);
    }
  }
  function selectPattern(item) {
    selectedPattern = item?.key || null; paintPatterns(); inspector.replaceChildren();
    inspector.classList.toggle("on", !!item); if (!item) return;
    const head = document.createElement("div"); head.className = "ofihead";
    const kind = document.createElement("div"); kind.className = "ofikind"; kind.textContent = patternLabel(item.p);
    const status = document.createElement("div"); status.className = "ofistatus"; status.textContent = item.p.status === "FORMING" ? "FORMING" : "CONFIRMADO";
    head.append(kind,status);
    const score = document.createElement("div"); score.className = "ofiscore";
    const label = document.createElement("div"); label.className = "ofilabel"; label.textContent = "EVIDENCIA · NO PROBABILIDAD DE GANAR";
    const value = document.createElement("strong"); value.textContent = `${item.p.evidence_score || 0}/100`; score.append(label,value);
    const why = document.createElement("div"); why.className = "ofiwhy"; why.textContent = item.p.why || "Sin explicación del detector.";
    const meta = document.createElement("div"); meta.className = "ofimeta";
    const when = new Date(Number(item.bar.time) * 1000).toLocaleString([], {month:"short",day:"2-digit",hour:"2-digit",minute:"2-digit"});
    meta.textContent = `LADO  ${item.p.side || "NEUTRAL"}\nZONA  ${(item.p.zone || [item.bar.low,item.bar.high]).map(Number).join(" — ")}\nBARRA ${when}\nFUENTE ${last.source || last.market_provider || "—"}\nCLASIF ${pct(last.classification_pct)}`;
    inspector.append(head,score,why,meta); draw();
  }

  function render(msg, fromPoll) {
    if (!msg || msg.type !== "footprint") return;
    const incomingBase = String(msg.requested_sym || msg.proxy_for || msg.sym || "").replace(/USDT$/, "");
    const currentBase = String(last?.requested_sym || last?.proxy_for || last?.sym || "").replace(/USDT$/, "");
    const symChanged = !!(currentBase && incomingBase && incomingBase !== currentBase);
    if (symChanged) { selectedPattern = null; lastViewportKey = ""; }
    if (!fromPoll && (msg.tape_source || "equity") !== selectedFeed) {
      if (incomingBase) requestFrame(incomingBase);
      return;
    }
    if (!fromPoll && tfLocked && msg.tf !== selectedTf && !symChanged) return;
    if (!fromPoll && !tfLocked && TFS.includes(msg.tf)) selectedTf = msg.tf;
    if (!fromPoll && !TFS.includes(msg.tf)) { selectedTf = TFS.includes(selectedTf) ? selectedTf : "5m"; requestFrame(msg.sym); return; }
    if (fromPoll && (msg.tf !== selectedTf || (msg.tape_source || "equity") !== selectedFeed)) return;
    last = msg; statusStyle(String(msg.state || "NO_TAPE")); paintEmpty(String(msg.state || "NO_TAPE"));
    paintControls(); paintPatterns(); if (selectedPattern) selectPattern(allPatterns().find(x => x.key === selectedPattern) || null); draw();
    if (symChanged && tfLocked) requestFrame(msg.sym);
  }

  async function requestFrame(forceSym) {
    if (!visible) return;
    const sym = forceSym || last?.requested_sym || last?.proxy_for || last?.sym; if (!sym) return;
    try {
      const r = await fetch(`/api/footprint?sym=${encodeURIComponent(String(sym).replace(/USDT$/, ""))}&tf=${encodeURIComponent(selectedTf)}&source=${selectedFeed}`, {cache:"no-store"});
      if (r.ok) render(await r.json(), true);
    } catch (_) {}
  }
  function armPoll() {
    clearInterval(pollTimer); if (visible) pollTimer = setInterval(requestFrame, 500);
  }

  function roundedRect(c,x,y,w,h,r) {
    r=Math.min(r,w/2,h/2); c.beginPath(); c.moveTo(x+r,y); c.arcTo(x+w,y,x+w,y+h,r); c.arcTo(x+w,y+h,x,y+h,r); c.arcTo(x,y+h,x,y,r); c.arcTo(x,y,x+w,y,r); c.closePath();
  }
  function draw() {
    if (!visible || !last || !(last.bars || []).length) return;
    const bars = last.bars.slice(-8), prices = [...new Set(bars.flatMap(b => (b.cells || []).map(x => Number(x.price))))].sort((a,b)=>b-a);
    if (!prices.length) return;
    const left=72, top=28, stats=116, barW=clamp(Math.floor((viewport.clientWidth-left-12)/Math.max(3,bars.length)),112,154);
    const cssW=Math.max(viewport.clientWidth,left+bars.length*barW+16), cssH=Math.max(viewport.clientHeight,top+prices.length*rowHeight+stats);
    const dpr=Math.min(2,window.devicePixelRatio||1); canvas.style.width=`${cssW}px`; canvas.style.height=`${cssH}px`;
    if(canvas.width!==Math.round(cssW*dpr)||canvas.height!==Math.round(cssH*dpr)){canvas.width=Math.round(cssW*dpr);canvas.height=Math.round(cssH*dpr)}
    const c=canvas.getContext("2d"); c.setTransform(dpr,0,0,dpr,0,0); c.clearRect(0,0,cssW,cssH); c.fillStyle=COLORS.bg;c.fillRect(0,0,cssW,cssH);
    c.textBaseline="middle"; c.lineWidth=1; hits=[];cellHits=[];
    const tick=Number(last.tick_size)||.01, digits=tick<.001?4:tick<.01?3:2, index=new Map(prices.map((p,i)=>[p.toFixed(6),i]));
    const yFor = p => { const i=index.get(Number(p).toFixed(6)); if(i!=null)return top+i*rowHeight+rowHeight/2; let best=0;for(let j=1;j<prices.length;j++)if(Math.abs(prices[j]-p)<Math.abs(prices[best]-p))best=j;return top+best*rowHeight+rowHeight/2; };
    c.font="10px ui-monospace,SFMono-Regular,Menlo,monospace";
    prices.forEach((p,i)=>{const y=top+i*rowHeight;c.fillStyle=i%2?"rgba(255,255,255,.009)":"rgba(255,255,255,.018)";c.fillRect(left,y,cssW-left,rowHeight);
      c.strokeStyle=COLORS.grid;c.beginPath();c.moveTo(left,y+rowHeight);c.lineTo(cssW,y+rowHeight);c.stroke();c.fillStyle="#75839a";c.textAlign="right";c.fillText(p.toFixed(digits),left-9,y+rowHeight/2)});
    c.fillStyle="#56647a";c.textAlign="center";c.font="800 8px -apple-system,BlinkMacSystemFont,sans-serif";
    c.fillText("BID",left+barW*.47,14);c.fillText("ASK",left+barW*.77,14);
    const gridBottom=top+prices.length*rowHeight;
    bars.forEach((bar,bi)=>{
      const x=left+bi*barW, cells=bar.cells||[], maxVol=Math.max(1,...cells.map(z=>Number(z.bid||0)+Number(z.ask||0)+Number(z.unknown||0)));
      c.strokeStyle="rgba(115,132,159,.2)";c.beginPath();c.moveTo(x,0);c.lineTo(x,gridBottom+stats);c.stroke();
      // Candle anatomy behind the numbers.
      const cx=x+12, yo=yFor(bar.open), yc=yFor(bar.close), yh=yFor(bar.high), yl=yFor(bar.low);
      c.strokeStyle=Number(bar.close)>=Number(bar.open)?"rgba(53,208,178,.72)":"rgba(255,105,115,.72)";c.lineWidth=1.25;c.beginPath();c.moveTo(cx,yh);c.lineTo(cx,yl);c.stroke();
      c.fillStyle=Number(bar.close)>=Number(bar.open)?"rgba(53,208,178,.22)":"rgba(255,105,115,.22)";c.fillRect(cx-3,Math.min(yo,yc),6,Math.max(2,Math.abs(yc-yo)));
      for(const cell of cells){const ri=index.get(Number(cell.price).toFixed(6));if(ri==null)continue;const y=top+ri*rowHeight,total=Number(cell.bid||0)+Number(cell.ask||0)+Number(cell.unknown||0),d=Number(cell.ask||0)-Number(cell.bid||0),strength=total/maxVol;
        const bx=x+23,bw=barW-27,half=bw/2;c.fillStyle=d>=0?`rgba(53,208,178,${.07+.36*strength})`:`rgba(255,105,115,${.07+.36*strength})`;roundedRect(c,bx+1,y+1,bw-3,rowHeight-2,2);c.fill();
        if(Number(cell.unknown||0)>0){c.fillStyle="rgba(180,190,205,.38)";for(let dx=5;dx<bw-2;dx+=8){c.beginPath();c.arc(bx+dx,y+rowHeight-3,1,0,Math.PI*2);c.fill()}}
        c.strokeStyle="rgba(180,194,215,.13)";c.lineWidth=1;c.beginPath();c.moveTo(bx+half,y+2);c.lineTo(bx+half,y+rowHeight-2);c.stroke();
        if(cell.poc){c.strokeStyle=Number(bar.poc_cluster||1)>=2?COLORS.amber:"#eef3fb";c.lineWidth=Number(bar.poc_cluster||1)>=2?2:1.2;roundedRect(c,bx+1.5,y+1.5,bw-4,rowHeight-3,2);c.stroke()}
        c.font=`${rowHeight>=17?11:10}px ui-monospace,SFMono-Regular,Menlo,monospace`;c.textAlign="right";c.fillStyle=cell.sell_imb?COLORS.blue:COLORS.text;c.fillText(fmt(cell.bid),bx+half-5,y+rowHeight/2);
        c.textAlign="left";c.fillStyle=cell.buy_imb?COLORS.blue:COLORS.text;c.fillText(fmt(cell.ask),bx+half+5,y+rowHeight/2);
        if(cell.sell_imb||cell.buy_imb){c.strokeStyle=COLORS.blue;c.lineWidth=2;c.beginPath();const edge=cell.sell_imb?bx+1:bx+bw-2;c.moveTo(edge,y+2);c.lineTo(edge,y+rowHeight-2);c.stroke()}
        cellHits.push({x:bx,y,w:bw,h:rowHeight,bar,cell,total,delta:d});
      }
      // Pattern geometry at its actual bar and zone.
      for(const p of (bar.patterns||[])){const key=pkey(bar,p),zone=p.zone||[bar.low,bar.high],y1=yFor(Math.max(...zone.map(Number))),y2=yFor(Math.min(...zone.map(Number)));
        c.lineWidth=selectedPattern===key?2.5:1.5;c.strokeStyle=p.status==="FORMING"?COLORS.amber:(p.kind==="ABSORPTION"?COLORS.violet:p.kind==="STACKED_IMBALANCE"?COLORS.blue:COLORS.amber);c.setLineDash(p.status==="FORMING"?[4,3]:[]);
        if(p.kind==="ABSORPTION"){c.strokeRect(x+18,Math.min(y1,y2)-rowHeight/2,barW-22,Math.abs(y2-y1)+rowHeight)}
        else if(p.kind==="STACKED_IMBALANCE"){const edge=p.side==="BULLISH"?x+barW-5:x+18;c.beginPath();c.moveTo(edge,y1-rowHeight/2);c.lineTo(edge,y2+rowHeight/2);c.moveTo(edge+(p.side==="BULLISH"?-7:7),y1-rowHeight/2);c.lineTo(edge,y1-rowHeight/2);c.moveTo(edge+(p.side==="BULLISH"?-7:7),y2+rowHeight/2);c.lineTo(edge,y2+rowHeight/2);c.stroke()}
        else if(p.kind.includes("DELTA")){const py=gridBottom+31;c.fillStyle=p.side==="BULLISH"?COLORS.buy:COLORS.sell;c.beginPath();c.moveTo(x+barW/2,py-6);c.lineTo(x+barW/2-5,py+3);c.lineTo(x+barW/2+5,py+3);c.closePath();c.fill()}
        hits.push({x:x+15,y:Math.min(y1,y2)-8,w:barW-18,h:Math.max(16,Math.abs(y2-y1)+16),bar,p,key});c.setLineDash([]);c.lineWidth=1;
      }
      if(Number(bar.poc_cluster||1)>=2){const py=yFor(bar.poc),count=Math.min(bi+1,Number(bar.poc_cluster));c.strokeStyle=COLORS.amber;c.lineWidth=2.5;c.beginPath();c.moveTo(x-(count-1)*barW+24,py);c.lineTo(x+barW-5,py);c.stroke()}
      // Delta / volume pane.
      const sy=gridBottom+10,known=Number(bar.bid||0)+Number(bar.ask||0),dp=known?100*Number(bar.delta||0)/known:0;
      c.font="800 9px ui-monospace,SFMono-Regular,Menlo,monospace";c.textAlign="center";c.fillStyle=Number(bar.delta)>=0?COLORS.buy:COLORS.sell;c.fillText(signed(bar.delta),x+barW/2,sy+13);
      c.fillStyle="#9aa7ba";c.font="9px ui-monospace,SFMono-Regular,Menlo,monospace";c.fillText(`${dp>=0?"+":""}${dp.toFixed(1)}%`,x+barW/2,sy+31);c.fillText(fmt(bar.volume),x+barW/2,sy+49);c.fillText(signed(bar.cvd),x+barW/2,sy+67);
      const tm=new Date(Number(bar.time)*1000);c.fillStyle=bar.closed?"#6f7e93":COLORS.amber;c.fillText(`${bar.closed?"":"◌ "}${tm.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}`,x+barW/2,sy+88);
    });
    c.fillStyle="#59677d";c.font="800 8px -apple-system,BlinkMacSystemFont,sans-serif";c.textAlign="right";[[23,"DELTA"],[41,"DELTA %"],[59,"VOLUMEN"],[77,"CVD"],[98,"HORA"]].forEach(([dy,t])=>c.fillText(t,left-9,gridBottom+10+dy));
    const latest=bars[bars.length-1],spot=Number(latest.close),spy=yFor(spot);c.strokeStyle="rgba(246,200,95,.78)";c.setLineDash([5,4]);c.beginPath();c.moveTo(left,spy);c.lineTo(cssW,spy);c.stroke();c.setLineDash([]);
    const viewKey=`${last.sym}|${selectedTf}|${prices[0]}|${prices.at(-1)}|${rowHeight}`;
    if(lastViewportKey!==viewKey){lastViewportKey=viewKey;requestAnimationFrame(()=>{viewport.scrollTop=clamp(spy-viewport.clientHeight*.45,0,canvas.offsetHeight-viewport.clientHeight);viewport.scrollLeft=Math.max(0,canvas.offsetWidth-viewport.clientWidth)})}
  }

  function hitAt(ev, pool) { const r=canvas.getBoundingClientRect(),x=ev.clientX-r.left,y=ev.clientY-r.top;return pool.find(h=>x>=h.x&&x<=h.x+h.w&&y>=h.y&&y<=h.y+h.h); }
  canvas.addEventListener("mousemove", ev => {const h=hitAt(ev,cellHits);if(!h){tooltip.style.display="none";return}const c=h.cell,ratio=Math.max(Number(c.ask||0),Number(c.bid||0))/Math.max(1,Math.min(Number(c.ask||0),Number(c.bid||0)));
    tooltip.textContent=`${Number(c.price).toFixed(Number(last.tick_size)<.01?4:2)}\nBID ${fmt(c.bid)}   ASK ${fmt(c.ask)}\nDELTA ${signed(h.delta)}   TOTAL ${fmt(h.total)}\nUNKNOWN ${fmt(c.unknown)}\nIMBALANCE ${ratio.toFixed(2)}×${c.buy_imb?" · BUY 3×":c.sell_imb?" · SELL 3×":""}`;
    tooltip.style.display="block";tooltip.style.left=`${clamp(ev.clientX+14,8,window.innerWidth-270)}px`;tooltip.style.top=`${clamp(ev.clientY+12,8,window.innerHeight-135)}px`;});
  canvas.addEventListener("mouseleave",()=>tooltip.style.display="none");
  canvas.addEventListener("click",ev=>{const h=hitAt(ev,hits);if(h)selectPattern(h)});
  viewport.addEventListener("wheel",ev=>{if(!(ev.ctrlKey||ev.metaKey))return;ev.preventDefault();rowHeight=clamp(rowHeight+(ev.deltaY<0?1:-1),12,26);localStorage.setItem("orderflow_row_height",rowHeight);lastViewportKey="";draw()},{passive:false});
  canvas.addEventListener("keydown",ev=>{if(ev.key==="Escape")selectPattern(null)});

  function setVisible(on) {
    visible=!!on;panel.classList.toggle("on",visible);if(!visible){document.documentElement.style.setProperty("--footprintw","0px");clearInterval(pollTimer);return}
    syncLayout();armPoll();requestFrame();requestAnimationFrame(draw);
  }
  const ro=new ResizeObserver(()=>{if(visible)draw()});ro.observe(viewport);ro.observe(host);
  window.addEventListener("resize",syncLayout);
  window.OrderFlowPanel={render,setVisible,isVisible:()=>visible,setMode,setFeed,setTransport(fn){transport=fn;void transport;}};
})();
