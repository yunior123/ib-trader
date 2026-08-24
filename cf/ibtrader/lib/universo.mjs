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
