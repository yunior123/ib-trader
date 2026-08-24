import { cadenaCboe, barrasLse, flujoLse } from "./fuentes.mjs";
import { agregar } from "./calculo.mjs";
import { MAPA, FLOTA } from "./universo.mjs";
import { COCKPIT } from "./panel.mjs";

const TOP_STRIKES = 40;       // solo los que pesan: el perfil completo son cientos de filas por vuelta

async function bitacora(db, tarea, ok, ms, detalle) {
  await db.prepare("INSERT INTO vueltas (ts,tarea,ok,ms,detalle) VALUES (?,?,?,?,?)")
          .bind(Math.floor(Date.now() / 1000), tarea, ok ? 1 : 0, ms, String(detalle).slice(0, 400)).run();
}

// Un simbolo por vuelta, en rueda: 5 MB de cadena por simbolo no caben todos en una invocacion.
export function turno(lista, ahora = Date.now()) {
  const paso = Math.floor(ahora / 60000);
  return lista[paso % lista.length];
}

export async function recolectarMapa(db, sym) {
  const t0 = Date.now();
  try {
    const m = agregar(await cadenaCboe(sym));
    const ts = Math.floor(Date.now() / 1000);
    await db.prepare(`INSERT OR REPLACE INTO niveles
        (sym,ts,fuente_ts,spot,call_wall,call_wall_oi,put_wall,put_wall_oi,flip,flip_raices,
         max_pain,gex_total,gross_gex,strike_span_pct,contratos,strikes,
         net_vex,gross_vex,net_charm,gross_charm,pressure,em,dte,exp,greeks_ok_pct,dex_bruto)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
      .bind(sym, ts, m.fuente_ts, m.spot, m.call_wall, m.call_wall_oi, m.put_wall, m.put_wall_oi,
            m.flip, JSON.stringify(m.flip_raices.slice(0, 6)), m.max_pain, m.gex_total,
            m.gross_gex, m.strike_span_pct, m.contratos, m.strikes,
            m.net_vex, m.gross_vex, m.net_charm, m.gross_charm, m.pressure, m.em, m.dte, m.exp,
            m.greeks_ok_pct, m.dex_bruto).run();

    const top = m.filas.slice().sort((a, b) => Math.abs(b.gex) - Math.abs(a.gex)).slice(0, TOP_STRIKES);
    if (top.length) {
      await db.batch(top.map(k => db.prepare(
        `INSERT OR REPLACE INTO perfil (sym,ts,strike,call_oi,put_oi,call_vol,put_vol,gex,vex,charm) VALUES (?,?,?,?,?,?,?,?,?,?)`)
        .bind(sym, ts, k.strike, k.call_oi, k.put_oi, k.call_vol, k.put_vol, k.gex, k.vex ?? null, k.charm ?? null)));
    }
    await bitacora(db, `mapa:${sym}`, true, Date.now() - t0,
                   `spot=${m.spot} muros=${m.put_wall}/${m.call_wall} flip=${m.flip ?? "sin cruce"}`);
    return { sym, ...m, filas: undefined };
  } catch (e) {
    await bitacora(db, `mapa:${sym}`, false, Date.now() - t0, e.message);
    throw e;
  }
}

export async function recolectarBarras(db, sym, key, tf = "15m") {
  const t0 = Date.now();
  try {
    const filas = await barrasLse(sym, key, { intervalo: tf, limite: 200 });
    if (filas.length) {
      await db.batch(filas.map(b => db.prepare(
        "INSERT OR REPLACE INTO barras (sym,tf,ts,o,h,l,c,v) VALUES (?,?,?,?,?,?,?,?)")
        .bind(sym, tf, b.ts, b.open, b.high, b.low, b.close, b.volume)));
    }
    await bitacora(db, `barras:${sym}:${tf}`, true, Date.now() - t0, `${filas.length} barras`);
    return filas.length;
  } catch (e) {
    await bitacora(db, `barras:${sym}`, false, Date.now() - t0, e.message);
    throw e;
  }
}

export async function recolectarFlujo(db, key) {
  const t0 = Date.now();
  try {
    const filas = await flujoLse(key, { limite: 200 });
    const nuestros = new Set(MAPA);
    const utiles = filas.filter(f => nuestros.has(f.underlying));
    if (utiles.length) {
      await db.batch(utiles.map(f => db.prepare(
        `INSERT OR REPLACE INTO flujo
         (id,ts,underlying,ticker,strike,expiry,tipo,dte,last_price,volume,premium,underlying_price,iv,delta,gamma)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
        .bind(f.id, f.ts, f.underlying, f.ticker, f.strike, f.expiry, f.contract_type, f.dte,
              f.last_price, f.volume, f.premium, f.underlying_price, f.iv, f.delta, f.gamma)));
    }
    await bitacora(db, "flujo", true, Date.now() - t0, `${utiles.length}/${filas.length} de nuestro universo`);
    return utiles.length;
  } catch (e) {
    await bitacora(db, "flujo", false, Date.now() - t0, e.message);
    throw e;
  }
}

// Peticiones LSE gastadas hoy (dia ET), contadas desde la bitacora: barras y flujo son las
// unicas tareas que van al vault (el mapa es CBOE, gratis). Sin llamada extra al upstream.
export async function gastoLseHoy(db) {
  const ny = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
  const inicio = Math.floor(new Date(ny.getFullYear(), ny.getMonth(), ny.getDate()).getTime() / 1000)
               + (Math.floor(Date.now() / 1000) - Math.floor(ny.getTime() / 1000));
  const r = await db.prepare(
    "SELECT COUNT(*) n FROM vueltas WHERE ts >= ? AND (tarea LIKE 'barras:%' OR tarea = 'flujo')")
    .bind(inicio).first();
  return r?.n ?? 0;
}

export const TECHO_LSE = 12000;   // de 15.000/dia; el resto es margen para /panel, /chart y manual

export async function vuelta(env, { tfs = ["15m", "1m"] } = {}) {
  const db = env.DB, key = env.LSE_API_KEY;
  // Los SEIS del cockpit se refrescan en CADA vuelta: son los que se miran. El resto del
  // universo va en rueda, un simbolo por vuelta, porque 5 MB de cadena no caben todos juntos.
  const resto = MAPA.filter(s => !COCKPIT.includes(s));
  const symMapa = turno(resto);
  const res = { cockpit: COCKPIT, mapa: symMapa, errores: [] };

  res.barras_ok = 0;
  res.tfs = tfs;
  // El vault declara vault_concurrency 2 y en paralelo devuelve 429 (medido; ya escrito en
  // scripts/lse_client.py:174). Antes se lanzaban 2 simbolos x 2 tf = CUATRO peticiones a la vez:
  // el doble de lo permitido. Ahora la lista se aplana y se va de DOS PETICIONES en dos.
  const trabajos = COCKPIT.flatMap(s => tfs.map(tf => ({ sym: s, tf })));
  // Una peticion que devuelve 429 GASTA cuota igual. Sin freno, el worker seguia martilleando
  // el vault todo el dia para nada (medido 2026-08-24: "daily request limit reached (15000/day)"
  // a las 07:20 y las vueltas siguiendo). Si el vault viene rechazando, se para y se deja
  // respirar; el mapa (CBOE, gratis) sigue corriendo igual.
  const recientes = await db.prepare(
    `SELECT detalle FROM vueltas WHERE ts >= ? AND ok = 0
       AND (tarea LIKE 'barras:%' OR tarea = 'flujo') LIMIT 20`)
    .bind(Math.floor(Date.now() / 1000) - 600).all();
  const rechazos = (recientes.results || []).filter(r => String(r.detalle).includes("429")).length;
  const gastado = await gastoLseHoy(db);
  res.lse_gastado = gastado;
  // Saltar el VAULT no es saltar la vuelta: el mapa sale de CBOE, que es gratis, y es lo que
  // pinta muros/flip. Cortarlo tambien dejaria el chart sin niveles por un problema de LSE.
  let saltar = null;
  if (rechazos >= 3) saltar = `vault en 429 (${rechazos} en 10 min)`;
  else if (gastado + trabajos.length + 1 > TECHO_LSE) saltar = `presupuesto agotado ${gastado}/${TECHO_LSE}`;
  if (saltar) {
    res.errores.push(`${saltar}: se salta el vault, el mapa sigue`);
    await bitacora(db, "freno", true, 0, saltar);
  }
  for (let i = 0; !saltar && i < trabajos.length; i += 2) {
    const par = trabajos.slice(i, i + 2);
    const r = await Promise.allSettled(par.map(t => recolectarBarras(db, t.sym, key, t.tf)));
    r.forEach((x, j) => x.status === "fulfilled" ? res.barras_ok++
                                                 : res.errores.push(`barras ${par[j].sym} ${par[j].tf}: ${x.reason?.message}`));
  }

  // mapa: dos del cockpit por vuelta (en rueda entre los seis) + uno del resto
  const seisEnRueda = turno(COCKPIT);
  for (const sym of [seisEnRueda, symMapa]) {
    try { await recolectarMapa(db, sym); }
    catch (e) { res.errores.push(`mapa ${sym}: ${e.message}`); }
  }
  res.mapa_ok = [seisEnRueda, symMapa];

  if (!saltar) {
    try { res.flujo_ok = await recolectarFlujo(db, key); }
    catch (e) { res.errores.push(`flujo: ${e.message}`); }
  }

  // Retencion: sin esto la base crece sin fin y el sistema deja de sostenerse solo. Se conserva
  // el historico de NIVELES (es el producto) y se poda lo voluminoso: perfiles y bitacora.
  try {
    const corte = Math.floor(Date.now() / 1000) - 7 * 24 * 3600;
    await db.batch([
      db.prepare("DELETE FROM perfil WHERE ts < ?").bind(corte),
      db.prepare("DELETE FROM vueltas WHERE ts < ?").bind(corte),
      db.prepare("DELETE FROM flujo WHERE ts < datetime('now','-14 days')"),
      db.prepare("DELETE FROM niveles WHERE ts < ?").bind(Math.floor(Date.now() / 1000) - 90 * 24 * 3600),
    ]);
  } catch (e) { res.errores.push(`retencion: ${e.message}`); }
  return res;
}
