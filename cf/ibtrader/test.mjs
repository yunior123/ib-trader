// Pruebas de las funciones puras. `node test.mjs` — sin dependencias.
import { flipRaices, gammaFlip, maxPain, bollinger, agregar } from "./lib/calculo.mjs";
import { ventanaAbierta } from "./lib/universo.mjs";
import { turno } from "./lib/recolecta.mjs";

let pasa = 0, falla = 0;
const ok = (n, c, extra = "") => c ? (pasa++, console.log("  ✓ " + n))
                                   : (falla++, console.log("  ✗ " + n + "  " + extra));
const cerca = (a, b, tol = 1e-6) => a !== null && Math.abs(a - b) <= tol;
const perfil = pares => pares.map(([strike, gex]) => ({ strike, gex }));

console.log("\n[flip]");
// acumulado: -10, -4, +6 -> cruza entre 110 y 120, en 110 + (4/10)*10 = 114
ok("interpola el cruce", cerca(gammaFlip(perfil([[100,-10],[110,6],[120,10]]), 115), 114),
   String(gammaFlip(perfil([[100,-10],[110,6],[120,10]]), 115)));
ok("sin cruce devuelve null", gammaFlip(perfil([[100,5],[110,5]]), 105) === null);
ok("perfil vacio devuelve null", gammaFlip([], 100) === null);
{
  // dos cruces: uno en 114 y otro arriba. Con spot 200 gana el mas cercano al spot.
  const p = perfil([[100,-10],[110,6],[120,10],[130,-20],[140,1]]);
  const raices = flipRaices(p, 200);
  ok("devuelve TODAS las raices", raices.length === 2, JSON.stringify(raices));
  ok("ordena por cercania al spot", raices[0] > raices[1], JSON.stringify(raices));
  ok("el flip publicado es el mas cercano", cerca(gammaFlip(p, 200), raices[0]));
}

console.log("\n[max pain]");
{
  // OI solo en calls de 100: el dolor minimo esta en el strike mas bajo
  const filas = [{ strike: 90, call_oi: 0, put_oi: 0 }, { strike: 100, call_oi: 500, put_oi: 0 },
                 { strike: 110, call_oi: 0, put_oi: 0 }];
  ok("con solo calls arriba, el minimo esta abajo", maxPain(filas) === 90, String(maxPain(filas)));
}

console.log("\n[bollinger]");
ok("menos de 20 cierres devuelve null (no un numero plausible)", bollinger([1,2,3]) === null);
{
  const planos = Array(20).fill(100);
  const b = bollinger(planos);
  ok("serie plana: sd 0 y %B null, no 0.5", b.sd === 0 && b.pctB === null, JSON.stringify(b));
  const sube = Array.from({ length: 20 }, (_, i) => 100 + i);
  const b2 = bollinger(sube);
  ok("serie creciente: %B alto", b2.pctB > 0.9, String(b2.pctB));
}

console.log("\n[agregar]");
{
  const cadena = { data: { current_price: 100, last_trade_time: "x", options: [
    { option: "TST260828C00100000", open_interest: 10, volume: 1, gamma: 0.05 },
    { option: "TST260828P00100000", open_interest: 20, volume: 2, gamma: 0.04 },
    { option: "basura", open_interest: 99, gamma: 9 },
  ] } };
  const m = agregar(cadena);
  ok("ignora contratos ilegibles", m.contratos === 2, String(m.contratos));
  ok("call wall y put wall en el unico strike", m.call_wall === 100 && m.put_wall === 100);
  // (0.05*10 - 0.04*20) * 100 * 100^2 * 0.01 = -0.3 * 10000 = -3000
  ok("GEX con la convencion declarada", cerca(m.gex_total, -3000, 1e-6), String(m.gex_total));
  let tiro = false;
  try { agregar({ data: { current_price: 0, options: [] } }); } catch { tiro = true; }
  ok("spot invalido LANZA en vez de devolver cero", tiro);
  let tiro2 = false;
  try { agregar({}); } catch { tiro2 = true; }
  ok("cadena sin data LANZA", tiro2);
}

console.log("\n[ventana y turno]");
ok("sabado cerrado", ventanaAbierta(new Date("2026-08-22T18:00:00Z")) === false);
ok("domingo cerrado", ventanaAbierta(new Date("2026-08-23T18:00:00Z")) === false);
ok("lunes 14:00 UTC (10:00 ET) abierto", ventanaAbierta(new Date("2026-08-24T14:00:00Z")) === true);
ok("lunes 02:00 UTC (22:00 ET domingo) cerrado", ventanaAbierta(new Date("2026-08-24T02:00:00Z")) === false);
{
  const lista = ["A", "B", "C"];
  const t0 = turno(lista, 0), t1 = turno(lista, 5 * 60 * 1000), t3 = turno(lista, 15 * 60 * 1000);
  ok("el turno avanza cada 5 min", t0 !== t1, `${t0} ${t1}`);
  ok("el turno da la vuelta", t0 === t3, `${t0} ${t3}`);
}

console.log(`\n${pasa} pasan · ${falla} fallan\n`);
process.exit(falla ? 1 : 0);
