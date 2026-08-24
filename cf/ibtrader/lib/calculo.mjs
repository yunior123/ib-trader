// Mapa de posicionamiento a partir de la cadena de CBOE. Las griegas vienen MEDIDAS en la
// cadena (gamma, delta, iv por contrato): aqui no se reconstruye ninguna.
//
// Convencion de signo (la clasica, y hay que declararla porque cambia el resultado): el dealer
// esta LARGO de calls y CORTO de puts. GEX>0 = cobertura estabilizadora; GEX<0 = amplificadora.
// El lado real del OI NO se observa, asi que esto es un SUPUESTO, no una medicion. Ver M3.

import { bsVanna, bsCharm, tAnios, pressure, expectedMove } from "./griegas.mjs";

const RE = /^([A-Z]+)(\d{6})([CP])(\d{8})$/;
const DIAS_ANIO = 365;

export function agregar(json) {
  const d = json?.data;
  if (!d) throw new Error("cadena sin campo data");
  const spot = d.current_price ?? d.close;
  if (!(spot > 0)) throw new Error(`spot invalido: ${spot}`);   // fail-loud: sin spot no hay mapa

  const ahora = Date.now();
  const porStrike = new Map();
  const porExp = new Map();
  let contratos = 0, ivOk = 0, gammaOk = 0, deltaOk = 0;
  // Acumuladores de las griegas de segundo orden: vanna y charm NO vienen en la cadena, se
  // calculan por Black-Scholes con la IV MEDIDA de cada contrato. Sin IV, el contrato no entra
  // y se cuenta: nunca se rellena con una IV plana.
  let dexBruto = 0, vexNeto = 0, vexBruto = 0, charmNeto = 0, charmBruto = 0;
  for (const o of d.options || []) {
    const m = RE.exec(o.option);
    if (!m) continue;
    contratos++;
    const strike = Number(m[4]) / 1000;
    const call = m[3] === "C";
    const exp = "20" + m[2].slice(0, 2) + m[2].slice(2, 4) + m[2].slice(4);
    const k = porStrike.get(strike) ||
      { strike, call_oi: 0, put_oi: 0, call_vol: 0, put_vol: 0, gamma_call: 0, gamma_put: 0,
        vex: 0, charm: 0, iv: 0, iv_peso: 0,
        // Los muros que actuan HOY son los del vencimiento cercano. Sumando toda la cadena,
        // el "put wall" de SPY salia en 520 con el spot en 763 (un LEAP de enero) y el de
        // QQQ en 660: numeros que no defienden nada esta semana.
        call_oi_cerca: 0, put_oi_cerca: 0, gamma_call_cerca: 0, gamma_put_cerca: 0 };
    const cerca = tAnios(exp, ahora) * DIAS_ANIO <= HORIZONTE_MUROS_D;
    const oi = o.open_interest || 0, vol = o.volume || 0, g = o.gamma || 0;
    if (typeof o.gamma === "number" && o.gamma !== 0) gammaOk++;
    const iv = o.iv > 0 ? o.iv : null;
    if (call) {
      k.call_oi += oi; k.call_vol += vol; k.gamma_call += g * oi;
      if (cerca) { k.call_oi_cerca += oi; k.gamma_call_cerca += g * oi; }
    } else {
      k.put_oi += oi; k.put_vol += vol; k.gamma_put += g * oi;
      if (cerca) { k.put_oi_cerca += oi; k.gamma_put_cerca += g * oi; }
    }
    if (typeof o.delta === "number") { dexBruto += Math.abs(o.delta) * oi; deltaOk++; }
    if (iv) {
      ivOk++;
      k.iv += iv * (oi + 1); k.iv_peso += oi + 1;
      const T = tAnios(exp, ahora);
      const va = bsVanna(spot, strike, T, iv), ch = bsCharm(spot, strike, T, iv);
      // Convencion de la casa, la misma del GEX: calls +, puts −.
      const signo = call ? 1 : -1;
      if (va !== null) { const x = signo * va * oi; k.vex += x; vexNeto += x; vexBruto += Math.abs(va * oi); }
      if (ch !== null) { const x = signo * ch * oi; k.charm += x; charmNeto += x; charmBruto += Math.abs(ch * oi); }
      const fe = porExp.get(exp) || [];
      fe.push({ strike, iv, oi });
      porExp.set(exp, fe);
    }
    porStrike.set(strike, k);
  }
  if (!porStrike.size) throw new Error("cadena sin contratos legibles");

  // GEX por strike en $ por cada 1% de movimiento: gamma x OI x 100 x spot^2 x 0.01
  const f = 100 * spot * spot * 0.01;
  const filas = [...porStrike.values()].map(k => ({ ...k, gex: (k.gamma_call - k.gamma_put) * f }))
                                       .sort((a, b) => a.strike - b.strike);

  const gex_total = filas.reduce((s, k) => s + k.gex, 0);
  // VEX en $ por punto de IV y CHARM en $ por DIA (a 0DTE el charm por año no dice nada).
  const f100 = 100 * spot;
  const net_vex = vexNeto * f100, gross_vex = vexBruto * f100;
  const net_charm = charmNeto * f100 / DIAS_ANIO, gross_charm = charmBruto * f100 / DIAS_ANIO;
  const gross_gex_val = filas.reduce((t, k) => t + Math.abs(k.gex), 0);
  const expVivos = [...porExp.keys()].sort();
  const expCerca = expVivos[0] || null;
  const em = expCerca ? expectedMove(spot, porExp.get(expCerca), tAnios(expCerca, ahora)) : null;
  const dte = expCerca ? Math.max(0, Math.round(tAnios(expCerca, ahora) * DIAS_ANIO)) : null;
  const hayCerca = filas.some(k => k.call_oi_cerca || k.put_oi_cerca);
  const campoC = hayCerca ? "call_oi_cerca" : "call_oi";
  const campoP = hayCerca ? "put_oi_cerca" : "put_oi";
  const call_wall = mayor(filas, campoC);
  const put_wall = mayor(filas, campoP);
  // El flip tambien: con toda la cadena, MU daba flip 276 con el spot en 914 (2026-08-24).
  const filasFlip = hayCerca
    ? filas.map(k => ({ strike: k.strike, gex: (k.gamma_call_cerca - k.gamma_put_cerca) * f }))
    : filas;

  // Sin griegas legibles NO hay GEX: un 0 aqui es "cero plausible" — se lee igual que un libro
  // neutro de verdad. AAPL llego asi (greeks_ok_pct 0, gex_total 0) y el panel lo pintaba como
  // dato. Los MUROS sobreviven: son OI, no dependen de griegas.
  // Cada familia depende de SU griega: el GEX de gamma, vex/charm de la IV, el DEX de delta.
  const oNull = (v, hay) => (hay ? v : null);

  return { spot, contratos, strikes: filas.length, filas, gex_total: oNull(gex_total, gammaOk),
           net_vex: oNull(net_vex, ivOk), gross_vex: oNull(gross_vex, ivOk),
           net_charm: oNull(net_charm, ivOk), gross_charm: oNull(gross_charm, ivOk),
           dex_bruto: oNull(dexBruto * f100, deltaOk),
           pressure: (gammaOk && ivOk)
             ? pressure(gex_total, gross_gex_val, net_vex, gross_vex) : null,
           em, dte, exp: expCerca, exps: expVivos.slice(0, 12),
           greeks_ok_pct: contratos ? ivOk / contratos : null,
           gamma_ok_pct: contratos ? gammaOk / contratos : null,
           call_wall: call_wall?.strike ?? null, call_wall_oi: call_wall?.[campoC] ?? null,
           put_wall: put_wall?.strike ?? null, put_wall_oi: put_wall?.[campoP] ?? null,
           muros_dte: hayCerca ? HORIZONTE_MUROS_D : null,   // null = no habia vencimiento cercano
           flip: gammaFlip(filasFlip, spot), flip_raices: flipRaices(filasFlip, spot),
           gross_gex: oNull(gross_gex_val, gammaOk),
           strike_span_pct: filas.length > 1
             ? (filas[filas.length - 1].strike - filas[0].strike) / 2 / spot : null,
           max_pain: maxPain(filas),
           fuente_ts: d.last_trade_time ?? null };
}

// Dias naturales que cuentan como "vencimiento cercano" para muros y flip: cubre 0DTE y la
// semana en curso, que es lo que los dealers cubren hoy.
export const HORIZONTE_MUROS_D = 8;

const mayor = (filas, campo) => filas.reduce((a, b) => (b[campo] > (a?.[campo] ?? -1) ? b : a), null);

// TODAS las raices del GEX acumulado, no solo la primera. Alineado con gex_core._flip_roots
// del repo ("flip-honesty", 2026-07-27): quedarse con la primera raiz engaña, porque una segunda
// raiz POR DEBAJO del spot es la trampilla — la zona donde los dealers amplifican a la baja.
// Sin cruce no hay flip y se devuelve lista vacia: el extremo del recorte no es un nivel de mercado.
export const MAX_DIST_FLIP = 0.25;   // fraccion del spot

export function flipRaices(filas, spot = null) {
  const raices = [];
  let acum = 0, previo = null, acumPrevio = 0;
  for (const k of filas) {
    acumPrevio = acum;
    acum += k.gex;
    if (previo !== null && ((acumPrevio < 0 && acum >= 0) || (acumPrevio > 0 && acum <= 0))) {
      const tramo = acum - acumPrevio;
      raices.push(Math.abs(tramo) < 1e-12 ? k.strike : previo + (-acumPrevio / tramo) * (k.strike - previo));
    }
    previo = k.strike;
  }
  // Una raiz al 70% del spot no es un flip: es el extremo del recorte. MU publicaba 276 con
  // el spot en 914 (2026-08-24) y el chart lo pintaba como nivel.
  if (spot !== null) {
    const cerca = raices.filter(r => Math.abs(r - spot) / spot <= MAX_DIST_FLIP);
    cerca.sort((a, b) => Math.abs(a - spot) - Math.abs(b - spot));
    return cerca;
  }
  return raices;
}

// El flip que se publica es la raiz MAS CERCANA al spot: es la que el precio puede cruzar hoy.
export function gammaFlip(filas, spot = null) {
  const r = flipRaices(filas, spot);
  return r.length ? r[0] : null;
}

// Max pain: strike que minimiza el valor intrinseco total que pagan los vendedores.
export function maxPain(filas) {
  let mejor = null, minimo = Infinity;
  for (const s of filas) {
    let dolor = 0;
    for (const k of filas) {
      if (k.strike < s.strike) dolor += (s.strike - k.strike) * k.call_oi;
      if (k.strike > s.strike) dolor += (k.strike - s.strike) * k.put_oi;
    }
    if (dolor < minimo) { minimo = dolor; mejor = s.strike; }
  }
  return mejor;
}

// Bandas de Bollinger(20,2) y %B sobre cierres. Sin 20 cierres devuelve null: la ley de la casa
// prohibe devolver un numero plausible cuando no se sabe.
export function bollinger(cierres, n = 20, k = 2) {
  if (!Array.isArray(cierres) || cierres.length < n) return null;
  const v = cierres.slice(-n);
  const media = v.reduce((a, b) => a + b, 0) / n;
  const varianza = v.reduce((a, b) => a + (b - media) ** 2, 0) / n;
  const sd = Math.sqrt(varianza);
  const alta = media + k * sd, baja = media - k * sd;
  const ultimo = v[n - 1];
  return { media, sd, alta, baja, ultimo,
           pctB: alta === baja ? null : (ultimo - baja) / (alta - baja) };
}
