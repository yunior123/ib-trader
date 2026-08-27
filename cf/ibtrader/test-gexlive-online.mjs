// e2e del widget GEX Live Table contra el worker PUBLICADO. Fichero aparte a proposito:
// test-online.mjs es de otro frente de trabajo y no se toca. `node test-gexlive-online.mjs [url]`
const BASE = process.argv[2] || "https://ibtrader.quant-academy.workers.dev";
let pasa = 0, falla = 0;
const ok = (n, c, extra = "") => c ? (pasa++, console.log("  ✓ " + n))
                                   : (falla++, console.log("  ✗ " + n + "  " + extra));
const get = async (ruta, tipo = "json") => {
  const r = await fetch(BASE + ruta, { headers: { "cache-control": "no-cache" } });
  return { status: r.status, cuerpo: tipo === "json" ? await r.json().catch(() => null) : await r.text() };
};

console.log(`\n[${BASE}]`);

console.log("\n[gexlive: assets]");
{
  const c = await get("/chart?cb=" + Date.now(), "texto");
  ok("el chart responde 200", c.status === 200, String(c.status));
  ok("declara el widget GEX Live Table", c.cuerpo.includes('id="wgt-gexlive"'));
  ok("lo carga en el menu de widgets", c.cuerpo.includes('"gexlive"') && c.cuerpo.includes("GEX Live Table"));
  ok("carga su fichero JS", c.cuerpo.includes("gex_live_table_widget.js"));
  const j = await get("/gex_live_table_widget.js?v=" + Date.now(), "texto");
  ok("el JS del widget responde 200", j.status === 200, String(j.status));
  ok("el JS es el rail DTE (tiene pildora ALL)", j.cuerpo.includes("gltrail") && j.cuerpo.includes('data-key="all"'));
}

console.log("\n[gexlive: dato adaptado de D1]");
{
  const r = await get("/data/gex_heatmap_QQQ.json");
  ok("responde 200", r.status === 200, String(r.status));
  const d = r.cuerpo;
  ok("declara sim y spot", d?.sym === "QQQ" && d?.spot > 0, JSON.stringify({ sym: d?.sym, spot: d?.spot }));
  ok("trae UN vencimiento en forma ISO", Array.isArray(d?.expiries) && d.expiries.length >= 1 &&
     /^\d{4}-\d{2}-\d{2}$/.test(d.expiries[0]), JSON.stringify(d?.expiries));
  ok("strikes y cells alineados", Array.isArray(d?.strikes) && Array.isArray(d?.cells) &&
     d.strikes.length === d.cells.length && d.strikes.length > 0,
     `${d?.strikes?.length}/${d?.cells?.length}`);
  ok("strikes en descendente (el spot se inserta antes del cruce)",
     d.strikes.every((k, i) => i === 0 || d.strikes[i - 1] > k));
  // Doctrina: sin dato = null, JAMAS un cero plausible en la celda.
  ok("ninguna celda es 0 exacto (seria cero plausible)",
     d.cells.every(c => c === null || (c[0] !== 0)), 
     d.cells.filter(c => c && c[0] === 0).length + " ceros");
  ok("col_totals presentes y no 0-plausible", Array.isArray(d?.col_totals) &&
     d.col_totals.length === d.expiries.length && d.col_totals[0] !== 0, JSON.stringify(d?.col_totals));
  ok("declara la fuente CBOE diferida", d?.src === "cboe" && d?.oi_realtime === false);
  ok("declara la edad (ts epoch en segundos)", typeof d?.ts === "number" && d.ts > 1e9 && d.ts < 2e9);
  ok("mvc declarado con strike y expiry", d?.mvc === null ||
     (typeof d.mvc?.strike === "number" && typeof d.mvc?.gamma_volume_raw === "number"));

  const m = await get("/data/gex_heatmap_MUYNOPE.json");
  ok("símbolo sin dato da 404, no matriz vacía", m.status === 404, String(m.status));
  const t = await get("/data/otro_fichero.json");
  ok("otro /data/ no se sirve (whitelist implicita)", t.status === 404, String(t.status));
}

console.log(`\nresultado: ${pasa} pasan, ${falla} fallan`);
process.exit(falla ? 1 : 0);
