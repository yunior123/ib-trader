// Griegas de segundo orden por Black-Scholes, con las MISMAS formulas que scripts/gex_core.py
// del repo (bs_vanna/bs_charm) para que el numero online y el del Mac no discrepen.
// q=0 declarado: sin dividendos, el termino de dividendo se anula en charm.

export const R_FREE = 0.045;
export const T_FLOOR = 5 / (365 * 24 * 60);   // ~5 min: sin piso, gamma ATM explota en 0DTE

const pdf = x => Math.exp(-x * x / 2) / Math.sqrt(2 * Math.PI);

function d1d2(S, K, T, iv, r = R_FREE) {
  const sq = iv * Math.sqrt(T);
  const a = (Math.log(S / K) + (r + iv * iv / 2) * T) / sq;
  return [a, a - sq, sq];
}

// Vanna por accion (∂vega/∂S = ∂delta/∂vol). Misma magnitud en call y put.
export function bsVanna(S, K, T, iv, r = R_FREE) {
  if (!(iv > 0) || !(S > 0) || !(K > 0)) return null;   // null, no 0: "no se" no es "cero"
  T = Math.max(T, T_FLOOR);
  const [a, b] = d1d2(S, K, T, iv, r);
  return -pdf(a) * b / iv;
}

// Charm por accion (∂delta/∂t). Motor del drift y del pin de la tarde.
export function bsCharm(S, K, T, iv, r = R_FREE) {
  if (!(iv > 0) || !(S > 0) || !(K > 0)) return null;
  T = Math.max(T, T_FLOOR);
  const [a, b, sq] = d1d2(S, K, T, iv, r);
  return -pdf(a) * (2 * r * T - b * sq) / (2 * T * sq);
}

// Anios hasta el vencimiento desde "AAAAMMDD". Se cierra a las 16:00 ET, no a medianoche.
export function tAnios(exp, ahora = Date.now()) {
  const y = +exp.slice(0, 4), m = +exp.slice(4, 6), d = +exp.slice(6, 8);
  const vence = Date.UTC(y, m - 1, d, 20, 0, 0);        // 16:00 ET = 20:00 UTC
  return Math.max((vence - ahora) / (365 * 24 * 3600 * 1000), T_FLOOR);
}

// Pressure −100..+100: gamma 80% + vanna 20%, cada uno normalizado por su exposicion BRUTA.
// Positivo = los dealers PINEAN; negativo = AMPLIFICAN. Es REGIMEN, no direccion.
// null si no hay bruto que normalizar: un 0 aqui se leeria como "neutro medido".
export function pressure(netGex, grossGex, netVex, grossVex) {
  const g = grossGex > 0 ? netGex / grossGex : null;
  const v = grossVex > 0 ? netVex / grossVex : null;
  if (g === null && v === null) return null;
  if (v === null) return Math.max(-100, Math.min(100, g * 100));
  if (g === null) return Math.max(-100, Math.min(100, v * 100));
  return Math.max(-100, Math.min(100, (0.8 * g + 0.2 * v) * 100));
}

// Expected move ±1σ = spot·IV·√T con la IV del vencimiento mas cercano, ponderada por OI en
// los strikes de alrededor del spot (la ATM sola es un solo contrato y puede estar sin cotizar).
export function expectedMove(spot, filasExp, T) {
  const cerca = filasExp.filter(f => f.iv > 0 && Math.abs(f.strike - spot) / spot < 0.05);
  if (!cerca.length || !(T > 0)) return null;
  const peso = cerca.reduce((s, f) => s + (f.oi || 0) + 1, 0);
  const iv = cerca.reduce((s, f) => s + f.iv * ((f.oi || 0) + 1), 0) / peso;
  return iv > 0 ? spot * iv * Math.sqrt(T) : null;
}
