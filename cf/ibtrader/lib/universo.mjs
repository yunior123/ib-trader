// Los DOS universos del repo, tal cual (data/fleet.txt y data/universe_gamma.txt). No se mezclan:
// la flota es quien VOTA, el universo gamma solo se dibuja en el mapa.
export const FLOTA = ["QQQ","SPY","NVDA","TSLA","MU","SMH","AMD","AAPL","MSFT","META","AMZN","GOOGL",
  "INTC","TSM","ASML","TXN","QCOM","AVGO","NFLX","NOK","GLD","XLK","EWY","DRAM","SPCX","SKHY",
  "LRCX","SNDK","WDC","STX","HOOD","PLTR","MSTR","COIN","CRWV","RKLB"];

export const MAPA = [...FLOTA, "SPX", "XSP", "NDX", "DIA", "IWM"];

// Ventana de recoleccion 24/5 (Yunior 2026-08-23: "sunday to friday"): del domingo al viernes
// SE RECOLECTA CONTINUO, sabado reposa. El precio vivo de cada ventana lo pone /stream
// (finnhub en cash, OKX perpetuo en modo=perp); esta puerta solo decide si el cron rota la
// cadena/barras. Los festivos NO se conocen aqui: si el mercado esta cerrado la cadena no cambia
// y se ve en fuente_ts, que es justo el dato que hay que mirar antes de fiarse de un nivel.
export function ventanaAbierta(fecha = new Date()) {
  const ny = new Date(fecha.toLocaleString("en-US", { timeZone: "America/New_York" }));
  return ny.getDay() !== 6;                      // solo el sabado cierra
}

// Fase de la sesion (ET). El presupuesto de LSE son 15.000 peticiones/DIA: a 13/min 24h son
// 18.720 y la cuota muere a media tarde (medido 2026-08-24 07:20, "daily request limit reached").
// Fuera de RTH las barras de cash no se mueven, asi que la cadencia baja con la fase.
export function fase(fecha = new Date()) {
  const ny = new Date(fecha.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const d = ny.getDay(), m = ny.getHours() * 60 + ny.getMinutes();
  if (d === 0 || d === 6) return "noche";        // domingo/sabado: sin cash
  if (m >= 570 && m < 960) return "rth";         // 09:30-16:00
  if (m >= 240 && m < 1200) return "ext";        // 04:00-20:00 fuera de RTH
  return "noche";
}

// Cada cuantos minutos toca vuelta, y con que temporalidades, en cada fase.
export const CADENCIA = { rth: { cada: 1, tfs: ["15m", "1m"] },
                          ext: { cada: 3, tfs: ["15m"] },
                          noche: { cada: 15, tfs: ["15m"] } };
