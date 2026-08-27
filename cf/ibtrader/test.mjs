// Pruebas de las funciones puras. `node test.mjs` — sin dependencias.
import { flipRaices, gammaFlip, maxPain, bollinger, agregar } from "./lib/calculo.mjs";
import { ventanaAbierta, fase, CADENCIA } from "./lib/universo.mjs";
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
  // dos cruces: uno en ~114 y otro arriba. Con el spot en 130 los dos caen dentro del 25%.
  const p = perfil([[100,-10],[110,6],[120,10],[130,-20],[140,1]]);
  const raices = flipRaices(p, 130);
  ok("devuelve TODAS las raices cercanas", raices.length === 2, JSON.stringify(raices));
  ok("ordena por cercania al spot", Math.abs(raices[0] - 130) <= Math.abs(raices[1] - 130),
     JSON.stringify(raices));
  ok("el flip publicado es el mas cercano", cerca(gammaFlip(p, 130), raices[0]));
  // Una raiz al 40% del spot no es un nivel que el precio pueda cruzar: MU publicaba flip
  // 276 con el spot en 914 (2026-08-24) y el chart lo pintaba como si fuera operable.
  ok("descarta las raices lejanas al spot", flipRaices(p, 200).length === 0,
     JSON.stringify(flipRaices(p, 200)));
  ok("sin raiz cercana el flip es null", gammaFlip(p, 200) === null);
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
  // Cadena SIN griegas: un 0 aqui se lee igual que un libro neutro de verdad (paso con AAPL
  // el 2026-08-24: greeks_ok_pct 0 y gex_total 0 guardados como dato).
  const sinG = agregar({ data: { current_price: 100, last_trade_time: "x", options: [
    { option: "TST260828C00100000", open_interest: 10, volume: 1 },
    { option: "TST260828P00100000", open_interest: 20, volume: 2 },
  ] } });
  ok("sin gamma el GEX es null, no 0", sinG.gex_total === null && sinG.gross_gex === null,
     String(sinG.gex_total));
  ok("sin gamma los MUROS siguen (son OI)", sinG.call_wall === 100 && sinG.put_wall === 100);
  ok("sin IV vex/charm son null", sinG.net_vex === null && sinG.net_charm === null);

    // Un muro fuera de alcance no es un muro: QQQ tenia 53.167 puts en el 530 a <=8 dias
  // (-25,3%) contra 52.434 en el 700 (-1,3%). El grande gana solo si esta en la banda.
  const lejos = agregar({ data: { current_price: 100, last_trade_time: "x", options: [
    { option: "TST260828P00070000", open_interest: 9000, volume: 1, gamma: 0.01, iv: 0.2 },
    { option: "TST260828P00099000", open_interest: 8000, volume: 1, gamma: 0.01, iv: 0.2 },
    { option: "TST260828C00130000", open_interest: 9000, volume: 1, gamma: 0.01, iv: 0.2 },
    { option: "TST260828C00102000", open_interest: 8000, volume: 1, gamma: 0.01, iv: 0.2 },
  ] } });
  ok("el put wall es el alcanzable, no el mayor", lejos.put_wall === 99, String(lejos.put_wall));
  ok("el call wall es el alcanzable, no el mayor", lejos.call_wall === 102, String(lejos.call_wall));

  // Convencion de la casa (gex_core.py): call wall = techo (>= spot), put wall = piso
  // (<= spot). XSP 2026-08-26 publico put wall 770 con call wall 765 y spot 767,57: un
  // "piso" por ENCIMA del "techo". El mayor OI de cada lado no puede cruzarse de lado.
  const cruzado = agregar({ data: { current_price: 100, last_trade_time: "x", options: [
    { option: "TST260828C00099000", open_interest: 9000, volume: 1, gamma: 0.01, iv: 0.2 },
    { option: "TST260828C00101000", open_interest: 100, volume: 1, gamma: 0.01, iv: 0.2 },
    { option: "TST260828P00099000", open_interest: 100, volume: 1, gamma: 0.01, iv: 0.2 },
    { option: "TST260828P00101000", open_interest: 9000, volume: 1, gamma: 0.01, iv: 0.2 },
  ] } });
  ok("el call wall no baja del spot aunque el mayor OI este abajo",
     cruzado.call_wall === 101, String(cruzado.call_wall));
  ok("el put wall no sube del spot aunque el mayor OI este arriba",
     cruzado.put_wall === 99, String(cruzado.put_wall));
  ok("piso <= techo por construccion", cruzado.put_wall <= cruzado.call_wall);
  ok("declara la banda usada", typeof lejos.muros_banda === "number", String(lejos.muros_banda));
  ok("la banda no pasa del 10% del spot", lejos.muros_banda <= 10.0001, String(lejos.muros_banda));

    ok("spot invalido LANZA en vez de devolver cero", tiro);
  let tiro2 = false;
  try { agregar({}); } catch { tiro2 = true; }
  ok("cadena sin data LANZA", tiro2);
}

console.log("\n[ventana y turno]");
ok("sabado cerrado", ventanaAbierta(new Date("2026-08-22T18:00:00Z")) === false);
ok("domingo 14:00 ET abierto (24/5)", ventanaAbierta(new Date("2026-08-23T18:00:00Z")) === true);
ok("lunes 14:00 UTC (10:00 ET) abierto", ventanaAbierta(new Date("2026-08-24T14:00:00Z")) === true);
ok("lunes 02:00 UTC (22:00 ET domingo) abierto (24/5)", ventanaAbierta(new Date("2026-08-24T02:00:00Z")) === true);
{
  const lista = ["A", "B", "C"];
  const t0 = turno(lista, 0), t1 = turno(lista, 5 * 60 * 1000), t3 = turno(lista, 15 * 60 * 1000);
  ok("el turno avanza cada 5 min", t0 !== t1, `${t0} ${t1}`);
  ok("el turno da la vuelta", t0 === t3, `${t0} ${t3}`);
}

console.log("\n[fase y presupuesto LSE]");
// 2026-08-24 es lunes. ET = UTC-4 en agosto.
ok("09:00 ET (13:00 UTC) es extendida", fase(new Date("2026-08-24T13:00:00Z")) === "ext",
   fase(new Date("2026-08-24T13:00:00Z")));
ok("09:30 ET (13:30 UTC) es RTH", fase(new Date("2026-08-24T13:30:00Z")) === "rth",
   fase(new Date("2026-08-24T13:30:00Z")));
ok("16:00 ET (20:00 UTC) ya no es RTH", fase(new Date("2026-08-24T20:00:00Z")) === "ext",
   fase(new Date("2026-08-24T20:00:00Z")));
ok("02:00 ET (06:00 UTC) es noche", fase(new Date("2026-08-24T06:00:00Z")) === "noche",
   fase(new Date("2026-08-24T06:00:00Z")));
ok("sabado es noche aunque sean las 11:00 ET", fase(new Date("2026-08-22T15:00:00Z")) === "noche",
   fase(new Date("2026-08-22T15:00:00Z")));
// El vault ignora `interval`: pedir 15m devolvia las MISMAS barras de 1m (medido en D1,
// 200 filas identicas). Ninguna fase puede pedir mas de una temporalidad o son duplicados.
ok("ninguna fase pide temporalidades duplicadas",
   Object.values(CADENCIA).every(c => c.tfs.length === 1 && c.tfs[0] === "1m"),
   JSON.stringify(CADENCIA));
{
  // El techo son 15.000/dia. Con 6 simbolos del cockpit: RTH 12 barras + 1 flujo por vuelta.
  const dia = 390 / CADENCIA.rth.cada * (6 * CADENCIA.rth.tfs.length + 1)
            + 570 / CADENCIA.ext.cada * (6 * CADENCIA.ext.tfs.length + 1)
            + 480 / CADENCIA.noche.cada * (6 * CADENCIA.noche.tfs.length + 1);
  ok("el dia entero cabe en 15.000 peticiones LSE", dia < 15000, `estimado ${Math.round(dia)}`);
  ok("y deja al menos 40% de margen", dia < 9000, `estimado ${Math.round(dia)}`);
}

console.log(`\n${pasa} pasan · ${falla} fallan\n`);
process.exit(falla ? 1 : 0);
