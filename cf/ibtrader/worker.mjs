import { vuelta, recolectarMapa, recolectarBarras, gastoLseHoy, TECHO_LSE } from "./lib/recolecta.mjs";
import { cuotaLse, perpTicker, perpVelas, quoteFinnhub, abrirTickerLse } from "./lib/fuentes.mjs";
import { bollinger } from "./lib/calculo.mjs";
import { ventanaAbierta, fase, CADENCIA, MAPA, FLOTA } from "./lib/universo.mjs";
import { pagina, COCKPIT } from "./lib/panel.mjs";

const json = (o, status = 200) => new Response(JSON.stringify(o, null, 1),
  { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });

// Cache compartida de OKX a nivel de ISOLATE: 6 ventanas del cockpit abren 6 WebSockets y cada
// uno quiere ticker+velas cada pocos segundos. Sin cache eso es un 429 seguro (medido 2026-08-23:
// /api/panel?modo=perp con 6 syms ya devolvio QQQ HTTP 429). Un solo vuelo por clave y TTL corto:
// el precio sigue siendo vivo, solo se desduplica la rafaga.
const _okxCache = new Map();
function okxCompartido(clave, fn, ttlMs = 6000) {
  const hit = _okxCache.get(clave);
  if (hit && Date.now() - hit.t < ttlMs) return hit.promesa;
  const promesa = fn();
  _okxCache.set(clave, { t: Date.now(), promesa });
  promesa.catch(() => {}).finally(() => setTimeout(() => {
    const h = _okxCache.get(clave);
    if (h && h.promesa === promesa) _okxCache.delete(clave);
  }, ttlMs));
  return promesa;
}

// "2026-08-24 06:07:00" (UTC, como sirve OKX via perpVelas) -> epoch segundos para lightweight-charts.
const VERSION = "2026-08-24-lse-ws";
const aEpoch = s => Math.floor(new Date(String(s).replace(" ", "T") + "Z").getTime() / 1000);

// El vault solo sirve barras de 1 minuto (ignora `interval`, medido). Las velas mayores se
// agregan aqui a partir de esas: cero peticiones extra y sin inventar nada — el open es el
// del primer minuto del cubo, el close el del ultimo, y h/l los extremos reales.
// Los niveles TAL COMO los consume el chart. Portado de public/ibt-online.js (el shim que
// hacia polling): el chart pinta estos numeros tal cual y necesita `profile` para dibujar
// muros e imanes — sin el, la cabecera dice "GEX: sin perfil en este libro".
// `fuente_ts` llega como cadena ISO SIN zona y en hora de Nueva York; el chart hace
// new Date(t*1000), o sea que espera EPOCH EN SEGUNDOS. Pasarle la cadena reventaba
// drawHeader con "RangeError: Invalid time value" y esa excepcion se llevaba por delante
// el resto del manejador de `history`: ni zoom, ni endChartLoad — de ahi el "conectando
// chart" eterno y el pie clavado en NO REALTIME.
function etAEpoch(v) {
  if (v == null) return null;
  if (typeof v === "number") return Math.floor(v);
  const base = Date.parse(String(v).replace(" ", "T") + "Z");   // leido como si fuera UTC
  if (!Number.isFinite(base)) return null;
  const d = new Date(base);
  const enEt = new Date(d.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const enUtc = new Date(d.toLocaleString("en-US", { timeZone: "UTC" }));
  return Math.floor((base + (enUtc - enEt)) / 1000);   // el epoch cuyo reloj ET es esa cadena
}

function nivelesUI(d, perp) {
  const red = (x, n) => (typeof x === "number" && isFinite(x) ? +x.toFixed(n) : null);
  return {
    sym: d.sym, spot: red(d.spot, 2), call_wall: d.call_wall, put_wall: d.put_wall,
    call_wall_oi: d.call_wall_oi, put_wall_oi: d.put_wall_oi,
    flip: red(d.flip, 2),
    flip_raices: (() => { try { return JSON.parse(d.flip_raices || "[]").map(x => +Number(x).toFixed(2)); } catch { return []; } })(),
    max_pain: d.max_pain, net_gex: d.gex_total, gross_gex: d.gross_gex,
    net_vex: d.net_vex, gross_vex: d.gross_vex, net_charm: d.net_charm, gross_charm: d.gross_charm,
    pressure: red(d.pressure, 1),
    pressure_lab: d.pressure == null ? null : (d.pressure >= 0 ? "PINEAN" : "AMPLIFICAN"),
    em: red(d.em, 2), dte: d.dte, exp: d.exp, greeks_ok_pct: d.greeks_ok_pct,
    oi_available: true, oi_source: "cboe_delayed",
    regime: d.gex_total == null ? null : (d.gex_total >= 0 ? "POS" : "NEG"),
    asof: etAEpoch(d.fuente_ts) ?? d.ts ?? null,
    chain_ts: d.ts ?? null,   // el chart compara con Date.now()/1000: SEGUNDOS, no ms
    chain_src: perp ? "okx" : "cboe", scale: "dollar1pct", profile_metric: "gex",
    profile: (d.profile || []).map(p => ({
      strike: p.strike, gex: p.gex, vex: p.vex, charm: p.charm,
      call_oi: p.call_oi, put_oi: p.put_oi, oi: (p.call_oi || 0) + (p.put_oi || 0),
      call_pct: (p.call_oi + p.put_oi) > 0 ? p.call_oi / (p.call_oi + p.put_oi) : null,
    })),
    strikes: d.strikes, contratos: d.contratos,
    flip_why: d.flip == null
      ? "El GEX acumulado no cruza cero en este libro: no hay flip, y el borde del recorte no es un nivel."
      : "Raiz del GEX acumulado mas cercana al spot (todas las raices en flip_raices).",
  };
}

const MINUTOS = { "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60 };
// Las velas del ws vienen en cubos de 1 minuto con `time` epoch. Para dibujarlas en la
// temporalidad pedida hay que agregarlas igual que las de D1, o el chart recibe cubos que no
// encajan con los suyos y aparecen velas sueltas al borde.
function agregarEpoch(velas, tf) {
  const m = MINUTOS[tf] || 1;
  if (m === 1) return velas.map(v => ({ time: v.time, o: v.o, h: v.h, l: v.l, c: v.c, v: v.v }));
  const cubos = new Map();
  for (const b of velas) {
    const k = b.time - (b.time % (m * 60));
    const c = cubos.get(k);
    if (!c) cubos.set(k, { time: k, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0 });
    else { c.h = Math.max(c.h, b.h); c.l = Math.min(c.l, b.l); c.c = b.c; c.v += b.v || 0; }
  }
  return [...cubos.values()].sort((a, b) => a.time - b.time);
}

function agregarVelas(filas, tf) {
  const m = MINUTOS[tf] || 1;
  if (m === 1) return filas;
  const cubos = new Map();
  for (const b of filas) {
    const t = aEpoch(b.ts), k = t - (t % (m * 60));
    const c = cubos.get(k);
    if (!c) cubos.set(k, { ts: b.ts, _t: k, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0 });
    else { c.h = Math.max(c.h, b.h); c.l = Math.min(c.l, b.l); c.c = b.c; c.v += b.v || 0; }
  }
  return [...cubos.values()].sort((a, b) => a._t - b._t);
}

// ---- Cotaciones de TODA la flota bajo el techo del free tier de Finnhub (~60/min) ----
// No se puede preguntar 36 simbolos cada 5 s: son 432/min y el limite salta. Ademas el worker
// corre en VARIOS isolates que NO comparten memoria (medido 2026-08-24: con cache en RAM el
// barrido no avanzaba — cada isolate repetia el trabajo). Diseno final: D1 como almacén
// compartido de la ultima cotacion + ROTACION con presupuesto por peticion: cada llamada
// refresca los simbolos mas viejos que el presupuesto permita (~1 upstream/1.1s => barrido
// completo de la flota en ~40-60 s mientras haya demanda). age_s declara la edad: honesto.
const Q_VIEJO_MS = 45000;    // un precio mas viejo que esto vuelve a la cola de refresco
let _qLastFetch = 0;         // ritmo por isolate: el presupuesto global lo manda D1, esto evita rafagas

async function rellenarQuotes(db, syms, key, msEntre = 1100, techoRafaga = 3) {
  const marcadores = new Map(syms.map(s => [s, { sym: s }]));
  const filas = await db.prepare(
    `SELECT sym,price,prev,ts,at FROM quotes WHERE sym IN (${syms.map(() => "?").join(",")})`)
    .bind(...syms).all();
  for (const r of filas.results || []) {
    if (r.price != null) marcadores.set(r.sym, { price: r.price, prev: r.prev, ts: r.ts, at: r.at });
    else marcadores.set(r.sym, { err: "sin dato", at: r.at || 0 });
  }
  const ahora = Date.now();
  let presupuesto = Math.min(techoRafaga, Math.floor((ahora - _qLastFetch) / msEntre));
  const pendientes = syms
    .filter(s => { const m = marcadores.get(s); return !m || !m.at || ahora - m.at > Q_VIEJO_MS; })
    .sort((a, b) => (marcadores.get(a)?.at ?? 0) - (marcadores.get(b)?.at ?? 0));
  const frescos = [];
  for (const sym of pendientes) {
    if (presupuesto <= 0) break;
    const espera = msEntre - (Date.now() - _qLastFetch);
    if (espera > 0) await new Promise(r => setTimeout(r, espera));
    _qLastFetch = Date.now();
    presupuesto--;
    try {
      const q = await quoteFinnhub(sym, key);
      const fila = { price: q.last, prev: q.prev_close, ts: q.ts, at: Date.now() };
      marcadores.set(sym, fila);
      frescos.push(fila.sym = sym);
    } catch (e) {
      // fallo POR SIMBOLO, no del lote: se registra y el barrido sigue
      const previa = marcadores.get(sym) || {};
      if (previa.price == null) marcadores.set(sym, { err: String(e?.message || e), at: Date.now() });
    }
  }
  if (frescos.length) {
    await db.batch(frescos.map(sym => {
      const f = marcadores.get(sym);
      return db.prepare(`INSERT OR REPLACE INTO quotes (sym,price,prev,ts,at) VALUES (?,?,?,?,?)`)
        .bind(sym, f.price, f.prev ?? null, f.ts ?? null, f.at);
    }));
  }
  return syms.map(sym => marcadores.get(sym) || { err: "en cola: el barrido la alcanza en ~1 min" });
}

// /stream — WebSocket realtime del worker. Habla UN SUBCONJUNTO honesto del protocolo del puente
// local (history/tick/levels/feed_status/stale): lo que el chart necesita para vivir sin el Mac.
//   · modo=perp (o perp=...): precio VIVO 24/7 desde OKX (perpetuo, no es la accion).
//   · sin modo=perp: snapshot de D1 (barras ya recolectadas) + niveles; sin ticks, declarado.
async function streamWs(server, db, url, env) {
  const sym = (url.searchParams.get("sym") || url.searchParams.get("perp") || "QQQ")
    .toUpperCase().replace(/USDT$/, "").trim();
  const perp = url.searchParams.get("modo") === "perp" || !!url.searchParams.get("perp");
  let tf = url.searchParams.get("tf") || "15m";  // por defecto 15m (Yunior); el vault solo
                                                  // sirve 1m y lo mayor se agrega aqui
  const finKey = env?.FINNHUB_API_KEY || null;
  let vivo = true;
  // Un ticker del vault POR CONEXION: los eventos de un ws saliente solo llegan al contexto
  // que lo abrio (medido 2026-08-24 — compartirlo dejaba mudas las ventanas que no lo abrian).
  const tickerLse = perp ? null : abrirTickerLse(env?.LSE_API_KEY);
  const morir = () => { vivo = false; try { tickerLse?.cerrar(); } catch {} };
  server.addEventListener("close", morir);
  server.addEventListener("error", morir);
  const enviar = o => {
    try { if (vivo && server.readyState === 1) server.send(JSON.stringify(o)); }
    catch { vivo = false; }
  };

  // Muros/flip/GEX: lo que D1 tiene de la cadena CBOE. No corren por segundo: 1/min sobra.
  const nivelesDe = async () => {
    const { results } = await db.prepare(
      `SELECT n.* FROM niveles n
        JOIN (SELECT sym, MAX(ts) AS ts FROM niveles WHERE sym=? GROUP BY sym) u
          ON n.sym = u.sym AND n.ts = u.ts`).bind(sym).all();
    const n = results?.[0];
    if (!n) return null;
    // El perfil por strike ES lo que el chart dibuja como muros e imanes. Sin el no hay muros.
    const pr = await db.prepare(
      "SELECT strike,call_oi,put_oi,call_vol,put_vol,gex,vex,charm FROM perfil WHERE sym=? AND ts=? ORDER BY strike")
      .bind(sym, n.ts).all();
    return nivelesUI({ sym, ...n, profile: pr.results || [] }, perp);
  };
  const feedBase = perp ? { provider: "okx", upstream: "www.okx.com", proto: "ws-rest-poll" }
                        : { provider: "lse", upstream: "data-ws.londonstrategicedge.com",
                            proto: "ws-bbo-mid", tier: "registered" };

  // Snapshot inicial -> history. Los indicadores van VACIOS declarados: el worker no calcula
  // Supertrend/Madrid/RSI (eso vive en el puente local); mejor una serie ausente que una inventada.
  // Si OKX da 429 hasta con reintentos, se reintenta el snapshot entero un par de veces: mientras
  // tanto los TICKS ya fluyen y el chart no se queda muerto para siempre.
  let ciclo = 0;
  let ultimaVela = null;   // {ts,o,h,l,c,v} — base para los ticks intermedios
  const enviarHistoria = async () => {
    let barras;
    if (perp) {
      barras = await okxCompartido(`velas:${sym}:${tf}`, () => perpVelas(sym, { bar: tf, limite: 150 }));
    } else {
      const { results } = await db.prepare(
        "SELECT ts,o,h,l,c,v FROM barras WHERE sym=? AND tf='1m' ORDER BY ts DESC LIMIT 3000")
        .bind(sym).all();
      barras = agregarVelas((results || []).reverse(), tf);
    }
    // lightweight-charts exige open/high/low/close. Con o/h/l/c el chart pintaba vacio y por
    // eso existia el shim de polling en public/ibt-online.js.
    let velasUI = (barras || []).map(b =>
      ({ time: b._t ?? aEpoch(b.ts), open: b.o, high: b.h, low: b.l, close: b.c, v: b.v || 0 }));
    // Las de D1 son historia del vault (REST); las del ws son las de HOY. Se pegan detras,
    // nunca solapando: si el REST esta sin cuota, el chart vive igual de las del ws.
    if (!perp && tickerLse) {
      const corte = velasUI.length ? velasUI[velasUI.length - 1].time : 0;
      for (const v of agregarEpoch(tickerLse.velas(sym), tf))
        if (v.time > corte) velasUI.push({ time: v.time, open: v.o, high: v.h, low: v.l, close: v.c, v: v.v });
    }
    if (barras?.length) ultimaVela = { ...barras[barras.length - 1] };
    const nivel = await nivelesDe();
    enviar({ type: "history", bars: velasUI, tf, mock: false,
      indicators: { bbUpper: [], bbLower: [], bbMid: [], sma40: [], sma100: [], sma200: [],
                    vwap: [], stUp: [], stDn: [], madrid: [],
                    volume: velasUI.map(v => ({ time: v.time, value: v.v })),
                    hist: [], macd: [], signal: [], rsi: [], rsiDivergence: [],
                    stMarkers: [], ttMarkers: [], whaleMarkers: [], rsiDivMarkers: [],
                    ttUp: [], ttDn: [], ttLevels: [], trendlines: [] },
      signals: [], engineOps: [],
      levels: nivel || { sym }, feed: feedBase,
      nodata: velasUI.length ? null
        : (perp ? `sin barras OKX para ${sym}`
                : `sin historico de ${sym} en D1 (el recolector solo guarda los seis del cockpit): `
                  + `el chart se construye desde el feed vivo del vault`) });
  };
  // El chart HABLA: pide mas historia al hacer pan y reenvio de history al cambiar de
  // temporalidad. Sin contestar, su spinner se queda encendido para siempre ("cargando
  // historial · 19.7s" en la captura) aunque el precio vaya vivo.
  server.addEventListener("message", async ev => {
    let c; try { c = JSON.parse(ev.data); } catch { return; }
    if (c?.cmd === "tf" && c.tf) {
      if (!MINUTOS[c.tf] && c.tf !== tf) {
        enviar({ type: "backfill", bars: [], exhausted: true, feed: feedBase,
                 reason: `temporalidad ${c.tf} no disponible aqui: el vault sirve 1m y el worker agrega 5m/15m/30m/1h` });
        return;
      }
      tf = c.tf; ultimaVela = null;
      await conReintento();
      return;
    }
    if (c?.cmd === "more") {
      // Honesto: aqui NO hay mas historia que dar. D1 guarda 200 barras por simbolo y el
      // vault REST esta sin cuota. Se dice y el chart deja de girar, en vez de fingir.
      enviar({ type: "backfill", bars: [], exhausted: true, feed: feedBase,
               reason: "no hay mas historial guardado para este simbolo" });
      return;
    }
  });

  let historiaIntentos = 0;
  const conReintento = async () => {
    try { await enviarHistoria(); }
    catch (e) {
      enviar({ type: "stale", text: String(e?.message || e) });
      if (++historiaIntentos <= 3 && vivo)
        setTimeout(conReintento, 6000 + historiaIntentos * 3000);
    }
  };
  await conReintento();

  // Bucle vivo: tick cada ~5s (con arranque escalonado para no clavar OKX al abrir 6 ventanas),
  // niveles cada ~60s. Muere con el socket.
  //
  // Presion sobre OKX medida (2026-08-23): las IPs de salida del worker son compartidas y OKX
  // responde 429 por rafaga. Por eso el bucle pide TICKER cada ciclo (1 peticion) y VELAS solo
  // cada 12 ciclos (~1/min, resync de la vela real); los ticks intermedios se construyen con el
  // ultimo precio vivo sobre la ultima vela conocida. La mitad de llamadas, mismo pulso.
  const paso = async () => {
    if (!vivo) return;
    ciclo++;
    try {
      if (perp) {
        const t = await okxCompartido(`tick:${sym}`, () => perpTicker(sym));
        let u = ultimaVela;
        if (!u || ciclo % 12 === 1) {
          const velas = await okxCompartido(`velas:${sym}:${tf}`, () => perpVelas(sym, { bar: tf, limite: 2 }));
          u = velas[velas.length - 1] || u;
        }
        if (u) {
          ultimaVela = { ...u,
            h: Math.max(u.h ?? t.last, t.last), l: Math.min(u.l ?? t.last, t.last), c: t.last };
          enviar({ type: "tick",
                   bar: { time: aEpoch(ultimaVela.ts), open: ultimaVela.o, high: ultimaVela.h,
                          low: ultimaVela.l, close: ultimaVela.c, v: ultimaVela.v || 0 },
                   feed: { ...feedBase, age_s: Math.max(0, Math.floor(Date.now() / 1000 - t.ts / 1000)) } });
        }
      } else if (!perp) {
        // Antes esto exigia `ultimaVela`, que solo existe si D1 tenia barras. Como el
        // recolector solo guarda los SEIS del cockpit, los otros 35 simbolos del universo
        // daban chart vacio: cero velas Y cero ticks, aunque el vault los sirva en vivo
        // (medido: AAPL, MSFT, AMD, MU, META y GLD con 0 barras y 0 ticks, spot y perfil OK).
        // El ws construye sus propias velas, asi que no necesita semilla de D1.
        // REALTIME DE CASH = WEBSOCKET DEL VAULT. Es lo mismo que usa el puente local y es lo
        // unico que da premarket: verificado 2026-08-24 08:12 ET con NVDA a 214,32 y ts de hace
        // un segundo, CON la cuota REST en 429 — el stream no gasta el presupuesto diario.
        // (Finnhub comentado por orden de Yunior y porque en premarket daba el cierre del
        // viernes: t=2026-08-21 16:00 medido a las 07:39 del lunes.)
        const t = await tickerLse.tick(sym);
        if (!t) throw new Error(`vault ws sin tick de ${sym} todavia (${tickerLse.estado().estado})`);
        // La vela la CONSTRUYE el ws con sus propios ticks (mid del BBO, cubos de 1 minuto),
        // igual que el puente local. El chart se mueve sin tocar el REST ni su cuota.
        // Agregar las ~600 velas guardadas EN CADA tick (1/s) reconstruia un Map entero cada
        // segundo y quemaba el presupuesto de CPU del isolate: el socket moria con CLOSE 1006
        // a los ~6 s y solo llegaban 2 ticks en 75 s (lo cazo test-online). Aqui solo se
        // recorre el cubo ACTUAL hacia atras: como mucho 15 velas en 15m, no 600.
        const vs = tickerLse.velas(sym);
        const mm = (MINUTOS[tf] || 1) * 60;
        const ult = vs[vs.length - 1];
        if (!ult) throw new Error(`vault ws sin vela de ${sym} todavia`);
        const k = ult.time - (ult.time % mm);
        let viva = null;
        for (let i = vs.length - 1; i >= 0 && vs[i].time >= k; i--) {
          const b = vs[i];
          if (!viva) viva = { time: k, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0 };
          else { viva.o = b.o; viva.h = Math.max(viva.h, b.h); viva.l = Math.min(viva.l, b.l); viva.v += b.v || 0; }
        }
        ultimaVela = { ts: new Date(viva.time * 1000).toISOString().replace("T", " ").slice(0, 19),
                       o: viva.o, h: viva.h, l: viva.l, c: viva.c, v: viva.v };
        const r4 = x => Math.round(x * 1e4) / 1e4;   // el chart no tiene por que ver ruido binario
        enviar({ type: "tick",
                 bar: { time: viva.time, open: r4(viva.o), high: r4(viva.h), low: r4(viva.l),
                        close: r4(viva.c), v: viva.v },
                 feed: (() => {
                   const edad = Math.max(0, Math.floor((Date.now() - t.ts) / 1000));
                   const est = tickerLse.estado();
                   // realtime SOLO si el ultimo tick es fresco. Con el socket vivo pero el
                   // precio parado (nombre fino en premarket) el chart dice PRICE STALE, que
                   // es la verdad, en vez de pintarse de verde.
                   return { ...feedBase, bid: t.bid, ask: t.ask, age_s: edad,
                            realtime: edad <= 30,
                            lse_ws: { connected: est.estado === "listo", status: est.estado === "listo"
                                      ? "SUBSCRIBED" : est.estado.toUpperCase(), reconnects: 0 } };
                 })() });
      } else if (false && ultimaVela) {   // rama Finnhub, conservada por si vuelve a hacer falta
        // Cash 24/5: precio de la accion via Finnhub. La vela base es la de D1; h/l/c se
        // actualizan con el vivo. Si el mercado esta cerrado, q.ts lo dice: age_s grande =
        // precio viejo DECLARADO, jamas disfrazado de fresco.
        //
        // El cache de okxCompartido es POR ISOLATE: con las 6 ventanas del cockpit (6 iframes =
        // 6 sockets, repartidos entre isolates) eran hasta 72 peticiones/min contra un techo de
        // 60 -> 429 permanente (medido 2026-08-24 07:19: 7 feed_status seguidos con HTTP 429).
        // La tabla `quotes` de D1 SI es compartida entre isolates y ya trae su propio
        // estrangulador: una sola llamada a Finnhub sirve a todas las ventanas.
        const [m] = await rellenarQuotes(db, [sym], finKey);
        if (m?.price == null) throw new Error(m?.err || "sin quote en D1");
        const q = { last: m.price, ts: m.ts ?? Date.now() };
        const u = ultimaVela;
        ultimaVela = { ...u,
          h: Math.max(u.h ?? q.last, q.last), l: Math.min(u.l ?? q.last, q.last), c: q.last };
        enviar({ type: "tick",
                 bar: { time: aEpoch(u.ts), o: u.o, h: ultimaVela.h, l: ultimaVela.l,
                        c: ultimaVela.c, v: u.v || 0 },
                 feed: { provider: "finnhub", upstream: "finnhub.io", proto: "rest-poll",
                         age_s: Math.max(0, Math.floor(Date.now() / 1000 - q.ts / 1000)) } });
      }
      if (ciclo % 12 === 0) {
        const n = await nivelesDe();
        if (n) enviar({ type: "levels", levels: n });
      }
    } catch (e) {
      // El resto de Finnhub estaba AQUI: el frame de error seguia diciendo
      // provider:"finnhub" upstream:"finnhub.io" aunque el dato fuese del vault, y el pie del
      // chart lo pintaba tal cual -> "NO REALTIME · finnhub" en la ventana de SMH mientras las
      // otras cinco decian "REALTIME · lse". La etiqueta mentia, el dato no.
      const msg = String(e?.message || e);
      const calentando = /sin tick|sin vela|conectando/.test(msg);
      enviar({ type: "feed_status",
               feed: { ...feedBase, realtime: false,
                       lse_ws: perp ? undefined : { connected: !calentando, status: calentando ? "SUBSCRIBING" : "ERROR" },
                       note: calentando
                         ? "esperando el segundo tick fresco del vault (nombre fino en premarket)"
                         : msg,
                       error: calentando ? undefined : msg } });
    }
    // En cash el pulso NO cuesta nada aguas arriba: el ws ya esta entregando ticks y aqui solo
    // se reenvia la vela viva. El puente local pinta a 4 Hz (LSE_CHART_PAINT_S); 1 s es de sobra
    // para el cockpit y no castiga al isolate. En perp cada vuelta SI es una peticion a OKX: 5 s.
    // 2 s en cash: el ws ya entrega los ticks y esto solo reenvia la vela viva, pero cada
    // vuelta cuesta CPU del isolate y el socket tiene presupuesto. 2 s va sobrado para el ojo.
    setTimeout(paso, perp ? 5000 : 2000);
  };
  setTimeout(paso, 1500 + Math.random() * 2500);
}


// Ultima instantanea de cada simbolo.
async function ultimosNiveles(db) {
  const { results } = await db.prepare(
    `SELECT n.* FROM niveles n
      JOIN (SELECT sym, MAX(ts) AS ts FROM niveles GROUP BY sym) u
        ON n.sym = u.sym AND n.ts = u.ts
     ORDER BY n.sym`).all();
  return results || [];
}

// Niveles + ultimas barras de los seis, en un solo viaje.
async function datosPanel(db, url) {
  const syms = (url.searchParams.get("syms") || COCKPIT.join(",")).toUpperCase().split(",").slice(0, 6);
  let tf = url.searchParams.get("tf") || "15m";
  // modo=perp: precio VIVO 24/7 desde OKX. Los niveles siguen siendo los de la cadena (CBOE):
  // el perpetual tiene su propia base, asi que sirve para el pulso, no para fijar el nivel.
  if (url.searchParams.get("modo") === "perp") {
    const niv = Object.fromEntries((await ultimosNiveles(db)).map(n => [n.sym, n]));
    return Promise.all(syms.map(async sym => {
      const n = niv[sym] || {};
      try {
        const [t, velas] = await Promise.all([perpTicker(sym), perpVelas(sym, { bar: tf })]);
        return { sym, modo: "perp", barras: velas, spot: t.last, bid: t.bid, ask: t.ask,
                 spread_pct: t.ask > 0 ? (t.ask - t.bid) / t.ask * 100 : null,
                 fuente_ts: new Date(t.ts).toISOString().slice(0, 19),
                 call_wall: n.call_wall ?? null, put_wall: n.put_wall ?? null,
                 flip: n.flip ?? null, max_pain: n.max_pain ?? null, gex_total: n.gex_total ?? null };
      } catch (e) {
        return { sym, modo: "perp", barras: [], spot: null, error: e.message,
                 call_wall: n.call_wall ?? null, put_wall: n.put_wall ?? null,
                 flip: n.flip ?? null, max_pain: n.max_pain ?? null, gex_total: n.gex_total ?? null };
      }
    }));
  }
  const niveles = await ultimosNiveles(db);
  const porSym = Object.fromEntries(niveles.map(n => [n.sym, n]));
  return Promise.all(syms.map(async sym => {
    const { results } = await db.prepare(
      "SELECT ts,o,h,l,c FROM barras WHERE sym=? AND tf=? ORDER BY ts DESC LIMIT 200")
      .bind(sym, tf).all();
    const n = porSym[sym] || {};
    // El perfil por strike es lo que el chart dibuja como muros e imanes (oro = iman,
    // morado = acelerador). Sin el, la cabecera avisa "GEX: sin perfil en este libro".
    let profile = [];
    if (n.ts) {
      const pr = await db.prepare(
        "SELECT strike,call_oi,put_oi,call_vol,put_vol,gex,vex,charm FROM perfil WHERE sym=? AND ts=? ORDER BY strike")
        .bind(sym, n.ts).all();
      profile = pr.results || [];
    }
    return { sym, barras: (results || []).reverse(), profile, ...n };
  }));
}

export default {
  async scheduled(event, env, ctx) {
    if (!ventanaAbierta()) {
      await env.DB.prepare("INSERT INTO vueltas (ts,tarea,ok,ms,detalle) VALUES (?,?,?,?,?)")
        .bind(Math.floor(Date.now() / 1000), "ventana", 1, 0, "fuera de ventana: no se recolecta").run();
      return;
    }
    // El cron dispara cada minuto (es la granularidad de Cloudflare), pero la VUELTA solo
    // corre cuando toca segun la fase: RTH 1/min con 15m+1m, extendida 1/3min y noche 1/15min.
    // A 13 peticiones/min 24h eran 18.720/dia contra un techo de 15.000 -> cuota muerta a diario.
    const f = fase();
    const { cada, tfs } = CADENCIA[f];
    const min = Math.floor(Date.now() / 60000);
    if (min % cada !== 0) return;
    ctx.waitUntil(vuelta(env, { tfs }));
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const p = url.pathname.replace(/\/+$/, "") || "/";
    const db = env.DB;

    try {
      // Realtime del worker: WebSocket propio (el puente local vive en el Mac; esto es lo que
      // se puede servir desde el borde). Sin upgrade -> 426 con explicacion.
      if (p === "/stream") {
        if (request.headers.get("upgrade") !== "websocket")
          return json({ error: "se espera upgrade websocket", pista: "wss://…/stream?sym=NVDA&modo=perp" }, 426);
        const par = new WebSocketPair();
        par[1].accept();   // sin accept() el extremo servidor nunca llega a OPEN y todo send se cae
        // Diagnostico: mensaje de arranque sincrono ANTES de cualquier await — si esto no llega,
        // el problema es del socket/handshake, no de la recoleccion.
        try { par[1].send(JSON.stringify({ type: "feed_status", feed: { provider: "worker", proto: "boot", ts: Date.now() } })); } catch {}
        ctx.waitUntil(streamWs(par[1], db, url, env));
        return new Response(null, { status: 101, webSocket: par[0] });
      }

      if (p === "/panel") {
        const datos = await datosPanel(db, url);
        let cuota = null;
        try { cuota = await cuotaLse(env.LSE_API_KEY); } catch { /* el panel se pinta igual */ }
        return new Response(pagina({ datos, cuota }),
          { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
      }

      // Diagnostico del WebSocket del vault: sin esto un simbolo mudo no se distingue de uno
      // sin suscribir. Abre el socket si hace falta y contesta lo que el vault confirmo.
      if (p === "/api/lse") {
        const syms = (url.searchParams.get("syms") || "QQQ").toUpperCase().split(",").filter(Boolean);
        const tk = abrirTickerLse(env.LSE_API_KEY);
        for (const s2 of syms) { try { await tk.tick(s2); } catch { /* se ve en estado */ } }
        await new Promise(r => setTimeout(r, 3000));
        for (const s2 of syms) { try { await tk.tick(s2); } catch {} }
        await new Promise(r => setTimeout(r, 1500));
        const est = tk.estado();
        const ticks = Object.fromEntries(syms.map(s2 => {
          const t = tk.ver(s2);
          return [s2, t ? { price: t.price, bid: t.bid, ask: t.ask,
                            age_s: Math.max(0, Math.floor((Date.now() - t.ts) / 1000)) } : null];
        }));
        tk.cerrar();
        return json({ ...est, ticks });
      }

      // El chart pide /version al arrancar; sin ruta eran 6 peticiones 404 por carga de la
      // rejilla y un "v?" en la cabecera.
      if (p === "/version") return json({ name: "ibtrader-worker", version: VERSION });

      if (p === "/api/niveles") return json(await ultimosNiveles(db));

      // Precio vivo de TODA la flota (o los syms que se pidan) bajo el techo del free tier:
      // barrido rotativo con D1 como almacén compartido entre isolates.
      if (p === "/api/quotes") {
        // FINNHUB COMENTADO (orden Yunior 2026-08-24: solo fuentes gratis). Esta ruta era la
        // unica que lo usaba para toda la flota; el precio vive ahora en las barras del vault.
        return json({ error: "ruta retirada: Finnhub fuera, usa /api/barras o /stream" }, 410);
        /* eslint-disable no-unreachable */
        const key = env.FINNHUB_API_KEY;
        if (!key) return json({ error: "worker sin FINNHUB_API_KEY" }, 503);
        const syms = (url.searchParams.get("syms") || FLOTA.join(",")).toUpperCase()
          .split(",").map(s => s.trim()).filter(Boolean).slice(0, 60);
        const marcadores = await rellenarQuotes(db, syms, key);
        const ahoraS = Math.floor(Date.now() / 1000);
        return json(syms.map((sym, i) => {
          const m = marcadores[i] || {};
          if (m.price == null)
            return { sym, price: null, error: m.err || "en cola: el barrido la alcanza en ~1 min" };
          return { sym, price: m.price, prev_close: m.prev ?? null,
                   ts: Math.floor((m.ts || 0) / 1000),
                   age_s: m.ts ? Math.max(0, ahoraS - Math.floor(m.ts / 1000)) : null };
        }));
      }


      // Lo que pinta el panel, para refrescar sin recargar la pagina.
      if (p === "/api/panel") return json(await datosPanel(db, url));

      if (p === "/api/perfil") {
        const sym = (url.searchParams.get("sym") || "QQQ").toUpperCase();
        const ts = await db.prepare("SELECT MAX(ts) AS ts FROM perfil WHERE sym=?").bind(sym).first();
        if (!ts?.ts) return json({ error: `sin perfil para ${sym}` }, 404);
        const { results } = await db.prepare(
          "SELECT * FROM perfil WHERE sym=? AND ts=? ORDER BY strike").bind(sym, ts.ts).all();
        return json({ sym, ts: ts.ts, strikes: results || [] });
      }

      if (p === "/api/flujo") {
        const min = Number(url.searchParams.get("min_prima") || 0);
        const { results } = await db.prepare(
          "SELECT * FROM flujo WHERE premium >= ? ORDER BY premium DESC LIMIT 100").bind(min).all();
        return json(results || []);
      }

      if (p === "/api/barras") {
        const sym = (url.searchParams.get("sym") || "QQQ").toUpperCase();
        // Sin filtrar por tf, 1m y 15m salian INTERCALADAS con el mismo ts: velas duplicadas
        // en el grafico y una Bollinger calculada sobre la serie doblada (sd 0,06 en QQQ).
        const tf = (url.searchParams.get("tf") || "1m").toLowerCase();
        const { results } = await db.prepare(
          "SELECT * FROM barras WHERE sym=? AND tf=? ORDER BY ts DESC LIMIT 240").bind(sym, tf).all();
        const filas = (results || []).reverse();
        const bb = bollinger(filas.map(b => b.c));
        return json({ sym, tf, barras: filas.length, bollinger: bb, ultimas: filas.slice(-60) });
      }

      if (p === "/api/estado") {
        const [nv, fl, ba, vu] = await Promise.all([
          db.prepare("SELECT COUNT(*) n, COUNT(DISTINCT sym) syms, MAX(ts) ult FROM niveles").first(),
          db.prepare("SELECT COUNT(*) n FROM flujo").first(),
          db.prepare("SELECT COUNT(*) n, COUNT(DISTINCT sym) syms FROM barras").first(),
          db.prepare("SELECT * FROM vueltas ORDER BY ts DESC LIMIT 5").all().then(r => r.results || []),
        ]);
        let cuota = null, cuotaErr = null;
        try { cuota = await cuotaLse(env.LSE_API_KEY); } catch (e) { cuotaErr = e.message; }
        return json({
          ventana_abierta: ventanaAbierta(), fase: fase(), cadencia: CADENCIA[fase()],
          lse_presupuesto: { gastado: await gastoLseHoy(db), techo: TECHO_LSE, limite_diario: 15000 },
          universo_mapa: MAPA.length, flota: FLOTA.length,
          niveles: nv, flujo: fl, barras: ba, ultimas_vueltas: vu, cuota_lse: cuota, cuota_error: cuotaErr,
        });
      }

      // Disparo manual de una vuelta: util para verificar sin esperar al cron.
      if (p === "/tarea/vuelta") {
        if (url.searchParams.get("key") !== env.ADMIN_KEY) return json({ error: "no autorizado" }, 401);
        return json(await vuelta(env));
      }
      if (p === "/tarea/barras") {
        if (url.searchParams.get("key") !== env.ADMIN_KEY) return json({ error: "no autorizado" }, 401);
        const sym = (url.searchParams.get("sym") || "QQQ").toUpperCase();
        return json({ sym, barras: await recolectarBarras(db, sym, env.LSE_API_KEY) });
      }
      if (p === "/tarea/mapa") {
        if (url.searchParams.get("key") !== env.ADMIN_KEY) return json({ error: "no autorizado" }, 401);
        const sym = (url.searchParams.get("sym") || "QQQ").toUpperCase();
        return json(await recolectarMapa(db, sym));
      }

      // El chart de la .app, servido tal cual desde public/ (ver public/ibt-online.js).
      if (env.ASSETS) {
        const candidatos = p === "/chart" ? ["/live.html"]
                         : (p === "/" || p === "/6" || p === "/seis") ? ["/seis.html"] : [p];
        for (const c of candidatos) {
          const r = await env.ASSETS.fetch(new Request(new URL(c, url).toString(), request));
          if (r.status !== 404) return r;
        }
      }
      return json({ error: "no existe", ruta: p }, 404);
    } catch (e) {
      return json({ error: "fallo del servidor", detalle: String(e?.message || e) }, 500);
    }
  },
};
