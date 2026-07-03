// Los DOS universos del repo, tal cual (data/fleet.txt y data/universe_gamma.txt). No se mezclan:
// la flota es quien VOTA, el universo gamma solo se dibuja en el mapa.
export const FLOTA = ["QQQ","SPY","NVDA","TSLA","MU","SMH","AMD","AAPL","MSFT","META","AMZN","GOOGL",
  "INTC","TSM","ASML","TXN","QCOM","AVGO","NFLX","NOK","GLD","XLK","EWY","DRAM","SPCX","SKHY",
  "LRCX","SNDK","WDC","STX","HOOD","PLTR","MSTR","COIN","CRWV","RKLB"];

export const MAPA = [...FLOTA, "SPX", "XSP", "NDX", "DIA", "IWM"];

// Ventana de mercado US en Nueva York, incluida la sesion extendida que sirven las fuentes.
// Los festivos NO se conocen aqui: si el mercado esta cerrado la cadena no cambia y se ve en
// fuente_ts, que es justo el dato que hay que mirar antes de fiarse de un nivel.
export function ventanaAbierta(fecha = new Date()) {
  const ny = new Date(fecha.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const dia = ny.getDay();
  if (dia === 0 || dia === 6) return false;
  const min = ny.getHours() * 60 + ny.getMinutes();
  return min >= 4 * 60 && min <= 20 * 60;        // 04:00-20:00 ET
}
