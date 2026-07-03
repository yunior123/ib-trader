import { vuelta, recolectarMapa, recolectarBarras } from "./lib/recolecta.mjs";
import { cuotaLse, perpTicker, perpVelas } from "./lib/fuentes.mjs";
import { bollinger } from "./lib/calculo.mjs";
import { ventanaAbierta, MAPA, FLOTA } from "./lib/universo.mjs";
import { pagina, COCKPIT } from "./lib/panel.mjs";

const json = (o, status = 200) => new Response(JSON.stringify(o, null, 1),
  { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });

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

  async fetch(request, env) {
    const url = new URL(request.url);
    const p = url.pathname.replace(/\/+$/, "") || "/";
    const db = env.DB;

    try {
      if (p === "/panel") {
        const datos = await datosPanel(db, url);
        let cuota = null;
        try { cuota = await cuotaLse(env.LSE_API_KEY); } catch { /* el panel se pinta igual */ }
        return new Response(pagina({ datos, cuota }),
          { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
      }

      if (p === "/api/niveles") return json(await ultimosNiveles(db));

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
