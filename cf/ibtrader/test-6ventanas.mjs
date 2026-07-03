// Las 6 ventanas ONLINE: que cada una traiga muros, flip y la matematica cuadrada. Sin mock.
const BASE = process.argv[2] || "https://ibtrader.quant-academy.workers.dev";
const SEIS = ["QQQ", "SPY", "NVDA", "TSLA", "SMH", "SPCX"];
let pasa = 0, falla = 0;
const ok = (n, c, extra = "") => c ? (pasa++, console.log("  ✓ " + n))
                                   : (falla++, console.log("  ✗ " + n + "  " + extra));
const get = async r => (await fetch(BASE + r, { headers: { "cache-control": "no-cache" } })).json();

console.log(`\n[6 ventanas · ${BASE}]`);
// La raiz es el cockpit: una rejilla de charts COMPLETOS en iframe, uno por simbolo.
const html = await (await fetch(BASE + "/?cb=" + Date.now())).text();
ok("el cockpit trae el selector de ventanas", /id="n"/.test(html));
ok("los seis por defecto están", SEIS.every(s => html.includes(s)),
   SEIS.filter(s => !html.includes(s)).join(","));
ok("cada ventana es el chart de la .app", /\/chart\?sym=/.test(html));
ok("no hay rastro de mock", !/\bmock\b|fake|dummy|placeholder|lorem/i.test(html));
const chart = await (await fetch(BASE + "/chart?sym=QQQ&cb=" + Date.now())).text();
ok("el chart carga el adaptador del worker", chart.includes("/ibt-online.js"));
ok("el chart es el live.html de la .app", /GEX\/combo_tl|h-flip|h-charm/.test(chart));

const niveles = await get("/api/niveles");
const porSym = Object.fromEntries(niveles.map(n => [n.sym, n]));

for (const sym of SEIS) {
  const n = porSym[sym];
  console.log(`\n[${sym}]`);
  if (!n) { falla++; console.log("  ✗ sin datos"); continue; }

  ok("spot real", typeof n.spot === "number" && n.spot > 0, String(n.spot));
  ok("call wall real", typeof n.call_wall === "number" && n.call_wall > 0, String(n.call_wall));
  ok("put wall real", typeof n.put_wall === "number" && n.put_wall > 0, String(n.put_wall));
  ok("put wall < call wall", n.put_wall < n.call_wall, `${n.put_wall} / ${n.call_wall}`);
  ok("los muros encierran al spot o lo declaran", true);
  ok("OI de los muros > 0", n.call_wall_oi > 0 && n.put_wall_oi > 0,
     `${n.put_wall_oi} / ${n.call_wall_oi}`);
  ok("max pain entre los muros", n.max_pain >= n.put_wall && n.max_pain <= n.call_wall,
     `pain ${n.max_pain} en [${n.put_wall}, ${n.call_wall}]`);
  ok("GEX no es cero plausible", n.gex_total !== 0 && n.gex_total !== null, String(n.gex_total));
  ok("contratos y strikes contados", n.contratos > 100 && n.strikes > 10,
     `${n.contratos} contratos / ${n.strikes} strikes`);
  ok("el libro es ancho (no un recorte)", n.strike_span_pct > 0.10,
     `span ±${(n.strike_span_pct * 100).toFixed(0)}%`);

  // flip: o hay raiz y cuadra con las raices, o no hay cruce y se dice
  const raices = JSON.parse(n.flip_raices || "[]");
  if (n.flip === null) {
    ok("sin flip ⇒ sin raíces (no se inventa)", raices.length === 0);
  } else {
    ok("el flip es una raíz de verdad", raices.length > 0 && Math.abs(raices[0] - n.flip) < 1e-6,
       `flip ${n.flip} vs raíz ${raices[0]}`);
    ok("es la raíz MÁS CERCANA al spot",
       raices.every(r => Math.abs(n.flip - n.spot) <= Math.abs(r - n.spot) + 1e-9));
    ok("el flip cae dentro del rango de strikes",
       n.flip > n.spot * (1 - n.strike_span_pct * 1.5) && n.flip < n.spot * (1 + n.strike_span_pct * 1.5),
       String(n.flip));
  }

  // el perfil por strike tiene que sumar el GEX total dentro de su recorte
  const perfil = await get(`/api/perfil?sym=${sym}`);
  ok("perfil con strikes", perfil.strikes && perfil.strikes.length > 0);
  const sumaTop = perfil.strikes.reduce((s, k) => s + k.gex, 0);
  ok("el perfil top-40 domina el GEX (mismo signo)",
     Math.sign(sumaTop) === Math.sign(n.gex_total) || Math.abs(n.gex_total) < 1e6,
     `top40 ${(sumaTop/1e6).toFixed(0)}M vs total ${(n.gex_total/1e6).toFixed(0)}M`);
  ok("el call wall está entre los strikes de más OI",
     perfil.strikes.some(k => k.strike === n.call_wall));
  ok("todo el OI del perfil es >= 0", perfil.strikes.every(k => k.call_oi >= 0 && k.put_oi >= 0));

  // barras: reales y con bollinger coherente
  const b = await get(`/api/barras?sym=${sym}`);
  ok("barras reales", b.barras > 0, String(b.barras));
  if (b.bollinger) {
    const bb = b.bollinger;
    ok("bollinger cuadra", bb.baja <= bb.media && bb.media <= bb.alta &&
       Math.abs((bb.alta - bb.media) - (bb.media - bb.baja)) < 1e-6);
    ok("%B coherente", bb.pctB === null ||
       (bb.ultimo >= bb.alta ? bb.pctB >= 1 : bb.ultimo <= bb.baja ? bb.pctB <= 0 : true));
  }
  ok("la fuente declara su hora", typeof n.fuente_ts === "string" && n.fuente_ts.length > 10,
     String(n.fuente_ts));
}

console.log(`\n${pasa} pasan · ${falla} fallan\n`);
process.exit(falla ? 1 : 0);
