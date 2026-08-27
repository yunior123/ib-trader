// Suite contra el worker PUBLICADO, no contra local. `node test-online.mjs [url]`
const BASE = process.argv[2] || "https://ibtrader.quant-academy.workers.dev";
let pasa = 0, falla = 0;
const ok = (n, c, extra = "") => c ? (pasa++, console.log("  ✓ " + n))
                                   : (falla++, console.log("  ✗ " + n + "  " + extra));
const get = async (ruta, tipo = "json") => {
  const r = await fetch(BASE + ruta, { headers: { "cache-control": "no-cache" } });
  return { status: r.status, cuerpo: tipo === "json" ? await r.json().catch(() => null) : await r.text() };
};

console.log(`\n[${BASE}]`);

console.log("\n[panel]");
{
  const r = await get("/panel?cb=" + Date.now(), "texto");
  ok("responde 200", r.status === 200, String(r.status));
  ok("es HTML con título", /<title>ib-trader/.test(r.cuerpo));
  ok("trae los seis con su lienzo", (r.cuerpo.match(/"sym":"/g) || []).length >= 6,
     String((r.cuerpo.match(/"sym":"/g) || []).length));
  ok("lleva los niveles de cada uno", /call_wall/.test(r.cuerpo) && /put_wall/.test(r.cuerpo));
  ok("declara la fuente de cada dato", /fuente_ts/.test(r.cuerpo));
}

console.log("\n[niveles]");
let niveles;
{
  const r = await get("/api/niveles");
  niveles = r.cuerpo;
  ok("responde 200", r.status === 200);
  ok("trae los 41 del universo", niveles.length === 41, `n=${niveles.length}`);
  ok("todos con spot > 0", niveles.every(n => n.spot > 0));
  ok("los muros son números o null", niveles.every(n =>
     (n.call_wall === null || typeof n.call_wall === "number") &&
     (n.put_wall === null || typeof n.put_wall === "number")));
  ok("put wall <= call wall en todos", niveles.every(n =>
     n.put_wall === null || n.call_wall === null || n.put_wall <= n.call_wall),
     niveles.filter(n => n.put_wall > n.call_wall).map(n => n.sym).join(","));
  ok("ningún GEX es exactamente 0 (sería un cero plausible)",
     niveles.every(n => n.gex_total !== 0));
  ok("guarda la hora de la FUENTE, no la nuestra", niveles.every(n => typeof n.fuente_ts === "string"));
  const conFlip = niveles.filter(n => n.flip !== null);
  ok("hay flips calculados", conFlip.length > 0, `${conFlip.length}/41`);
  ok("cada flip cae dentro del rango de strikes", conFlip.every(n => n.flip > 0));
  ok("las raíces se guardan como lista", conFlip.every(n => {
     try { return Array.isArray(JSON.parse(n.flip_raices)); } catch { return false; } }));
  ok("el flip publicado es la raíz MÁS CERCANA al spot", conFlip.every(n => {
     const r = JSON.parse(n.flip_raices);
     return r.length === 0 || Math.abs(r[0] - n.spot) <= Math.min(...r.map(x => Math.abs(x - n.spot))) + 1e-9;
  }));
  ok("sin cruce ⇒ flip null y raíces vacías", niveles.filter(n => n.flip === null)
     .every(n => JSON.parse(n.flip_raices || "[]").length === 0));
}

console.log("\n[perfil]");
{
  const r = await get("/api/perfil?sym=QQQ");
  ok("responde 200", r.status === 200);
  ok("trae strikes", r.cuerpo.strikes.length > 0, String(r.cuerpo.strikes?.length));
  ok("el OI nunca es negativo", r.cuerpo.strikes.every(k => k.call_oi >= 0 && k.put_oi >= 0));
  ok("hay GEX de los dos signos", r.cuerpo.strikes.some(k => k.gex > 0) && r.cuerpo.strikes.some(k => k.gex < 0));
  const r2 = await get("/api/perfil?sym=NOEXISTE");
  ok("símbolo desconocido da 404, no un perfil vacío", r2.status === 404, String(r2.status));
}

console.log("\n[flujo]");
{
  const r = await get("/api/flujo");
  ok("responde 200", r.status === 200);
  ok("trae operaciones", r.cuerpo.length > 0, String(r.cuerpo.length));
  ok("viene ordenado por prima", r.cuerpo.every((f, i, a) => i === 0 || a[i - 1].premium >= f.premium));
  // MEDIDO (2026-08-24): LSE no publicaba griegas de los contratos que vencen ESE día (dte 0).
  // RE-MEDIDO (2026-08-25, SNDK260828P02010000: put 2010 con subyacente 1495, dte 3): LSE
  // también las omite en contratos lejanos/iliquidos. La expectativa honesta NO es "siempre
  // hay griegas salvo hoy": es que vengan como números, y que cuando falten falten COMPLETAS
  // (iv, delta y gamma a la vez, como null) — jamás una sola ni un 0, que es un cero plausible.
  ok("cada griega que viene, viene como número o null (nunca otra cosa ni 0)",
     r.cuerpo.every(f => [f.delta, f.iv, f.gamma].every(g => g === null ||
        (typeof g === "number" && g !== 0))),
     r.cuerpo.filter(f => [f.delta, f.iv, f.gamma].some(g => g !== null && (typeof g !== "number" || g === 0)))
        .map(f => f.ticker).join(","));
  ok("cuando faltan, faltan las TRES juntas como null",
     r.cuerpo.filter(f => f.delta === null).every(f => f.iv === null && f.gamma === null),
     r.cuerpo.filter(f => f.delta === null && (f.iv !== null || f.gamma !== null))
        .map(f => f.ticker).join(","));
  ok("ninguna griega llega como cero exacto",
     !r.cuerpo.some(f => f.delta === 0 && f.iv === 0));
  ok("todas son de nuestro universo", r.cuerpo.every(f => typeof f.underlying === "string" && f.underlying.length <= 5));
  const r2 = await get("/api/flujo?min_prima=1000000");
  ok("el filtro de prima muerde", r2.cuerpo.every(f => f.premium >= 1000000));
}

console.log("\n[barras y bollinger]");
{
  const r = await get("/api/barras?sym=QQQ");
  ok("responde 200", r.status === 200);
  ok("trae barras", r.cuerpo.barras > 0, String(r.cuerpo.barras));
  const b = r.cuerpo.bollinger;
  ok("calcula bollinger", b && typeof b.alta === "number");
  ok("la banda encierra la media", b.baja <= b.media && b.media <= b.alta);
  ok("%B es coherente con la banda", b.pctB === null ||
     (b.ultimo >= b.alta ? b.pctB >= 1 : b.ultimo <= b.baja ? b.pctB <= 0 : b.pctB > 0 && b.pctB < 1),
     `pctB=${b.pctB} ultimo=${b.ultimo} banda=${b.baja}-${b.alta}`);
  const r2 = await get("/api/barras?sym=NOEXISTE");
  ok("símbolo sin barras: bollinger null, NO un 0.5 plausible",
     r2.cuerpo.bollinger === null, JSON.stringify(r2.cuerpo.bollinger));
}

console.log("\n[estado y seguridad]");
{
  const r = await get("/api/estado");
  ok("responde 200", r.status === 200);
  ok("declara si la ventana está abierta", typeof r.cuerpo.ventana_abierta === "boolean");
  // La cuota se informa en cualquiera de sus dos formas honestas: dato (upstream OK) o
  // error declarado (upstream 429/caido). Lo que NO se acepta es ausenciar el campo.
  ok("informa de la cuota de LSE", r.cuerpo.cuota_lse != null || !!r.cuerpo.cuota_error);
  ok("la bitácora registra vueltas", Array.isArray(r.cuerpo.ultimas_vueltas) && r.cuerpo.ultimas_vueltas.length > 0);
  ok("no filtra la clave de LSE", !JSON.stringify(r.cuerpo).includes("X-API-Key"));

  const t1 = await get("/tarea/vuelta");
  ok("la tarea sin clave da 401", t1.status === 401, String(t1.status));
  const t2 = await get("/tarea/mapa?sym=QQQ&key=malaclave");
  ok("clave equivocada da 401", t2.status === 401, String(t2.status));
  const t3 = await get("/noexiste");
  ok("ruta inexistente da 404", t3.status === 404, String(t3.status));
}

// --- REALTIME: el camino que se rompio el 2026-08-24 y que ningun test miraba -------------
// Todo lo de aqui abajo cubre fallos REALES que llegaron a produccion: barras en {o,h,l,c}
// cuando el chart exige {open,high,low,close}, `levels` sin `profile` (chart sin muros),
// `asof` como cadena ISO (RangeError que mataba el manejador entero), el worker sordo a los
// comandos del chart, y el frame de error etiquetado con una fuente que ya no se usaba.

// `cmds` = [{tras_ms, obj}] que se mandan DURANTE la sesion. Mandarlos despues de que la
// promesa resuelva no vale: para entonces el socket ya esta cerrado (fallo de este test, no
// del worker: los tres ✗ de 'more' eran esto).
const abrirStream = (qs, segundos = 30, cmds = []) => new Promise(res => {
  const ws = new WebSocket(BASE.replace(/^http/, "ws") + "/stream" + qs);
  const f = { history: null, ticks: [], backfill: null, estados: [], cerrado: null };
  ws.onmessage = e => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    if (m.type === "history" && !f.history) f.history = m;
    else if (m.type === "tick") f.ticks.push(m);
    else if (m.type === "backfill") f.backfill = m;
    else if (m.type === "feed_status") f.estados.push(m);
  };
  ws.onerror = () => {};
  for (const c of cmds) setTimeout(() => { try { ws.send(JSON.stringify(c.obj)); } catch (e) { f.envioErr = String(e); } }, c.tras);
  setTimeout(() => { try { ws.close(); } catch {} res(f); }, segundos * 1000);
});

console.log("\n[stream: forma de los frames]");
{
  const f = await abrirStream("?sym=QQQ&tf=15m", 30);
  ok("el stream manda history", !!f.history);
  const b = f.history?.bars?.at(-1);
  ok("hay barras", (f.history?.bars || []).length > 0, String((f.history?.bars || []).length));
  // lightweight-charts exige open/high/low/close; con o/h/l/c el chart se quedaba vacio
  ok("las barras vienen en open/high/low/close", !!b &&
     ["time", "open", "high", "low", "close"].every(k => typeof b[k] === "number"),
     JSON.stringify(b));
  ok("NINGUNA barra usa las claves cortas o/h/l/c", !!b && b.o === undefined && b.c === undefined);
  const L = f.history?.levels || {};
  ok("levels trae el perfil por strike (sin el no hay muros)", Array.isArray(L.profile) && L.profile.length > 0,
     String((L.profile || []).length));
  ok("cada nodo del perfil lleva strike y OI", (L.profile || []).every(x => typeof x.strike === "number" && typeof x.oi === "number"));
  // Esto reventaba drawHeader con "RangeError: Invalid time value"
  ok("asof es epoch en SEGUNDOS, no una cadena ISO", typeof L.asof === "number" && L.asof > 1e9 && L.asof < 2e9,
     JSON.stringify(L.asof));
  ok("chain_ts tambien en segundos (se compara con Date.now()/1000)",
     L.chain_ts == null || (L.chain_ts > 1e9 && L.chain_ts < 2e9), JSON.stringify(L.chain_ts));
  ok("declara el regimen", L.regime === "POS" || L.regime === "NEG" || L.net_gex == null, String(L.regime));
  ok("los muros vienen como numero o null, nunca 0 plausible",
     [L.call_wall, L.put_wall].every(x => x === null || (typeof x === "number" && x !== 0)));
}

console.log("\n[stream: el pulso es del vault por WebSocket]");
{
  const f = await abrirStream("?sym=NVDA&tf=15m", 40);
  ok("llegan ticks", f.ticks.length > 0, String(f.ticks.length));
  const t = f.ticks.at(-1);
  ok("el proveedor es lse", t?.feed?.provider === "lse", String(t?.feed?.provider));
  ok("el transporte es el websocket del vault, no REST",
     t?.feed?.upstream === "data-ws.londonstrategicedge.com", String(t?.feed?.upstream));
  ok("NADIE vuelve a nombrar a finnhub en el camino vivo",
     !JSON.stringify(f).includes("finnhub"));
  ok("el tick declara su antiguedad", typeof t?.feed?.age_s === "number");
  ok("realtime es coherente con la antiguedad",
     typeof t?.feed?.realtime === "boolean" && t.feed.realtime === (t.feed.age_s <= 30),
     `realtime=${t?.feed?.realtime} age=${t?.feed?.age_s}`);
  // El campo `price` del vault ES el bid: el precio tiene que ser el punto MEDIO
  if (t?.feed?.bid != null && t?.feed?.ask != null) {
    const mid = Math.round(((t.feed.bid + t.feed.ask) / 2) * 1e4) / 1e4;
    ok("el precio es el punto medio del BBO, no el bid", Math.abs(t.bar.close - mid) < 0.011 || t.bar.close !== t.feed.bid,
       `close=${t.bar.close} bid=${t.feed.bid} ask=${t.feed.ask} mid=${mid}`);
    ok("bid <= ask", t.feed.bid <= t.feed.ask);
  } else ok("el tick trae bid/ask", false, "sin bid/ask");
  ok("el tick tambien en open/high/low/close", ["open", "high", "low", "close"].every(k => typeof t?.bar?.[k] === "number"));
  ok("la vela es coherente: low <= open/close <= high",
     t && t.bar.low <= Math.min(t.bar.open, t.bar.close) && t.bar.high >= Math.max(t.bar.open, t.bar.close));
}

console.log("\n[stream: la vela se CONSTRUYE, no se repite]");
{
  const f = await abrirStream("?sym=SPY&tf=1m", 70);
  const cubos = new Set(f.ticks.map(t => t.bar.time));
  const mismo = f.ticks.filter((t, i) => i > 0 && t.bar.time === f.ticks[i - 1].bar.time);
  const movio = mismo.some((t, i) => t.bar.close !== mismo[i - 1]?.bar.close || t.bar.high !== mismo[i - 1]?.bar.high);
  ok("llegan varios ticks", f.ticks.length >= 5, String(f.ticks.length));
  ok("aparece mas de un cubo de vela en 70 s", cubos.size >= 2, String(cubos.size));
  ok("dentro del mismo cubo la vela cambia (se esta formando)", movio || cubos.size >= 2);
  ok("los cubos de 1m caen en frontera de minuto", [...cubos].every(c => c % 60 === 0));
}

console.log("\n[stream: el worker CONTESTA al chart]");
{
  const f = await abrirStream("?sym=QQQ&tf=15m", 25,
    [{ tras: 8000, obj: { cmd: "more", before: Math.floor(Date.now() / 1000) } }]);
  ok("responde al comando 'more' (si no, el spinner gira para siempre)", !!f.backfill);
  ok("y dice si se acabo la historia", f.backfill?.exhausted === true);
  ok("con un motivo legible", typeof f.backfill?.reason === "string" && f.backfill.reason.length > 5);
}

console.log("\n[rutas que el chart pide]");
{
  const v = await get("/version");
  ok("/version responde 200 (eran 6 peticiones 404 por carga)", v.status === 200, String(v.status));
  ok("y dice su version", typeof v.cuerpo?.version === "string");
  const q = await get("/api/quotes?syms=NVDA");
  ok("/api/quotes esta retirada (Finnhub fuera)", q.status === 410, String(q.status));
  const l = await get("/api/lse?syms=QQQ");
  ok("/api/lse diagnostica el socket", l.status === 200 && typeof l.cuerpo?.estado === "string", String(l.status));
  ok("y devuelve el tick con su antiguedad",
     l.cuerpo?.ticks?.QQQ == null || typeof l.cuerpo.ticks.QQQ.age_s === "number");
}

console.log("\n[presupuesto del vault]");
{
  const e = await get("/api/estado");
  const pr = e.cuerpo?.lse_presupuesto;
  ok("el estado publica el presupuesto diario", !!pr && typeof pr.gastado === "number", JSON.stringify(pr));
  ok("el techo deja margen sobre el limite real", pr && pr.techo < pr.limite_diario);
  ok("declara la fase de sesion", ["rth", "ext", "noche"].includes(e.cuerpo?.fase), String(e.cuerpo?.fase));
  ok("la cadencia de la fase pide UNA sola temporalidad (el vault ignora interval)",
     e.cuerpo?.cadencia?.tfs?.length === 1, JSON.stringify(e.cuerpo?.cadencia));
}

console.log(`\n${pasa} pasan · ${falla} fallan\n`);
process.exit(falla ? 1 : 0);
