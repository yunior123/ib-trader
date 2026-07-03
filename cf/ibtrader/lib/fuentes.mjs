// Las dos fuentes que sobrevivieron y que Cloudflare alcanza (medido 2026-08-23):
//   CBOE  cadena completa con griegas y OI, sin clave. Delayed y DESIGUAL entre simbolos:
//         por eso se guarda su last_trade_time y no la hora nuestra.
//   LSE   barras 1m y flujo de opciones con prima y griegas. Necesita X-API-Key.
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0 Safari/537.36";
const LSE = "https://api.londonstrategicedge.com/vault";

async function pedir(url, cabeceras = {}) {
  const r = await fetch(url, { headers: { "User-Agent": UA, ...cabeceras } });
  if (!r.ok) throw new Error(`${new URL(url).host} HTTP ${r.status}`);   // fail-loud, sin fallback mudo
  return r;
}

// CBOE llama _SPX/_VIX a los indices; los ETF van tal cual.
export const cboeSym = sym => (["SPX", "VIX", "NDX", "RUT", "XSP"].includes(sym) ? `_${sym}` : sym);

export async function cadenaCboe(sym) {
  const r = await pedir(`https://cdn.cboe.com/api/global/delayed_quotes/options/${cboeSym(sym)}.json`);
  return r.json();
}

export async function barrasLse(sym, key, { intervalo = "1m", limite = 120 } = {}) {
  const u = `${LSE}/candles?symbol=${encodeURIComponent(sym)}&interval=${intervalo}&limit=${limite}&order=desc`;
  const filas = await (await pedir(u, { "X-API-Key": key })).json();
  if (!Array.isArray(filas)) throw new Error("candles: respuesta no es lista");
  return filas.reverse();                       // el vault sirve desc; aqui se quiere cronologico
}

export async function flujoLse(key, { limite = 200 } = {}) {
  const filas = await (await pedir(`${LSE}/options/flow?limit=${limite}`, { "X-API-Key": key })).json();
  if (!Array.isArray(filas)) throw new Error("flow: respuesta no es lista");
  return filas;
}

export async function cuotaLse(key) {
  return (await pedir(`${LSE}/usage`, { "X-API-Key": key })).json();
}

// OKX: perpetuales de acciones tokenizadas. Cotizan 24/7, traen LIBRO (bid/ask) y son lo unico
// con precio VIVO fuera del horario de bolsa. No son la accion: es un derivado con su propia
// base, asi que sirve para el pulso y el spread, NO para fijar un nivel de la cadena.
const OKX = "https://www.okx.com/api/v5";

export async function perpTicker(sym) {
  const r = await pedir(`${OKX}/market/ticker?instId=${sym.toUpperCase()}-USDT-SWAP`);
  const d = (await r.json())?.data?.[0];
  if (!d?.last) throw new Error(`okx sin ticker para ${sym}`);
  return { last: +d.last, bid: +d.bidPx, ask: +d.askPx, ts: +d.ts,
           vol24h: +d.volCcy24h || 0, open24h: +d.open24h || 0 };
}

export async function perpVelas(sym, { bar = "1m", limite = 120 } = {}) {
  const r = await pedir(`${OKX}/market/candles?instId=${sym.toUpperCase()}-USDT-SWAP&bar=${bar}&limit=${limite}`);
  const d = (await r.json())?.data;
  if (!Array.isArray(d) || !d.length) throw new Error(`okx sin velas para ${sym}`);
  // OKX sirve mas reciente primero: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
  return d.map(v => ({ ts: new Date(+v[0]).toISOString().replace("T", " ").slice(0, 19),
                       o: +v[1], h: +v[2], l: +v[3], c: +v[4], v: +v[5] })).reverse();
}

export async function perpDisponibles() {
  const r = await pedir(`${OKX}/public/instruments?instType=SWAP`);
  const d = (await r.json())?.data || [];
  return new Set(d.map(x => String(x.instId).replace("-USDT-SWAP", "")));
}
