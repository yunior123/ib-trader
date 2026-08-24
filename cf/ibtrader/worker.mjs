import { vuelta, recolectarMapa, recolectarBarras } from "./lib/recolecta.mjs";
import { cuotaLse, perpTicker, perpVelas, quoteFinnhub } from "./lib/fuentes.mjs";
import { bollinger } from "./lib/calculo.mjs";
import { ventanaAbierta, MAPA, FLOTA } from "./lib/universo.mjs";
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
const aEpoch = s => Math.floor(new Date(String(s).replace(" ", "T") + "Z").getTime() / 1000);

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
  const tf = url.searchParams.get("tf") || (perp ? "1m" : "15m");   // D1 solo guarda 15m en cash
  const finKey = env?.FINNHUB_API_KEY || null;
  let vivo = true;
  server.addEventListener("close", () => { vivo = false; });
  server.addEventListener("error", () => { vivo = false; });
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
    return results?.[0] || null;
  };
  const feedBase = perp ? { provider: "okx", upstream: "www.okx.com", proto: "ws-rest-poll" }
                        : { provider: "d1", upstream: "cloudflare-d1", proto: "snapshot" };

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
        "SELECT ts,o,h,l,c FROM barras WHERE sym=? AND tf=? ORDER BY ts DESC LIMIT 200")
        .bind(sym, tf).all();
      barras = (results || []).reverse();
    }
    const velasUI = (barras || []).map(b =>
      ({ time: aEpoch(b.ts), o: b.o, h: b.h, l: b.l, c: b.c, v: b.v || 0 }));
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
      levels: { sym, ...(nivel || {}) }, feed: feedBase,
      nodata: velasUI.length ? null : `sin barras ${perp ? "OKX" : "D1"} para ${sym}` });
  };
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
                   bar: { time: aEpoch(ultimaVela.ts), o: ultimaVela.o, h: ultimaVela.h,
                          l: ultimaVela.l, c: ultimaVela.c, v: ultimaVela.v || 0 },
                   feed: { ...feedBase, age_s: Math.max(0, Math.floor(Date.now() / 1000 - t.ts / 1000)) } });
        }
      } else if (finKey && ultimaVela) {
        // Cash 24/5: precio REALTIME de la accion via Finnhub (la casa ya lo usa en scripts/).
        // La vela base es la de D1; h/l/c se actualizan con el vivo. Si el mercado esta cerrado,
        // q.ts lo dice: age_s grande = precio viejo declarado, jamas disfrazado de fresco.
        const q = await okxCompartido(`fh:${sym}`, () => quoteFinnhub(sym, finKey), 10100);
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
      const quien = perp ? feedBase
        : { provider: "finnhub", upstream: "finnhub.io", proto: "rest-poll" };
      enviar({ type: "feed_status", feed: { ...quien, error: String(e?.message || e) } });
    }
    setTimeout(paso, 5000);
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
  const tf = url.searchParams.get("tf") || "15m";
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
    ctx.waitUntil(vuelta(env));
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

      if (p === "/api/niveles") return json(await ultimosNiveles(db));

      // Precio vivo de TODA la flota (o los syms que se pidan) bajo el techo del free tier:
      // barrido rotativo con D1 como almacén compartido entre isolates.
      if (p === "/api/quotes") {
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
        const { results } = await db.prepare(
          "SELECT * FROM barras WHERE sym=? ORDER BY ts DESC LIMIT 240").bind(sym).all();
        const filas = (results || []).reverse();
        const bb = bollinger(filas.map(b => b.c));
        return json({ sym, barras: filas.length, bollinger: bb, ultimas: filas.slice(-60) });
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
          ventana_abierta: ventanaAbierta(), universo_mapa: MAPA.length, flota: FLOTA.length,
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
