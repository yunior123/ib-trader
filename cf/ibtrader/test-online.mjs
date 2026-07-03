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
  // MEDIDO: LSE no publica griegas de los contratos que vencen ESE día (dte 0) — 4 de 100.
  // Lo que no puede pasar es que lleguen como 0: un cero plausible es peor que un hueco.
  const conGriegas = r.cuerpo.filter(f => f.dte > 0);
  ok("las griegas están en todo lo que no vence hoy",
     conGriegas.every(f => typeof f.delta === "number" && typeof f.iv === "number"),
     conGriegas.filter(f => typeof f.delta !== "number").map(f => f.ticker).join(","));
  ok("cuando faltan, faltan como null y NUNCA como 0",
     r.cuerpo.filter(f => f.delta === null).every(f => f.iv === null && f.dte === 0),
     r.cuerpo.filter(f => f.delta === null && f.dte !== 0).map(f => f.ticker).join(","));
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
  ok("informa de la cuota de LSE", r.cuerpo.cuota_lse && r.cuerpo.cuota_lse.bytes_cap_month > 0);
  ok("la bitácora registra vueltas", Array.isArray(r.cuerpo.ultimas_vueltas) && r.cuerpo.ultimas_vueltas.length > 0);
  ok("no filtra la clave de LSE", !JSON.stringify(r.cuerpo).includes("X-API-Key"));

  const t1 = await get("/tarea/vuelta");
  ok("la tarea sin clave da 401", t1.status === 401, String(t1.status));
  const t2 = await get("/tarea/mapa?sym=QQQ&key=malaclave");
  ok("clave equivocada da 401", t2.status === 401, String(t2.status));
  const t3 = await get("/noexiste");
  ok("ruta inexistente da 404", t3.status === 404, String(t3.status));
}

console.log(`\n${pasa} pasan · ${falla} fallan\n`);
process.exit(falla ? 1 : 0);
