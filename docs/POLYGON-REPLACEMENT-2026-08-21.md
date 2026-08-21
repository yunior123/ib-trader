# Reemplazo gratuito de Polygon OI — 2026-08-21

## Decisión implementada para la semana próxima

Polygon queda **OFF por defecto**. El cockpit no consulta su API ni acepta su caché.
El adaptador `scripts/free_oi.py` usa ahora la cadena pública de Nasdaq, sin clave,
cuenta, tarjeta ni pago. Descarga sólo el rango de expiraciones activo y normaliza OI por
contrato; London conserva spot, IV/Greeks y actividad intradía. El 21-ago se verificó el
camino completo en QQQ, NVDA, SMH, SPY, TSLA y SPCX: los seis publicaron
`oi_source=nasdaq_public_option_chain`, `oi_available=true`, Net GEX y flip.

La ruta falla cerrada: OI ausente se conserva como desconocido, una expiración sin calls y
puts suficientes invalida la captura, la caché vence a las 36 h, y se exige IV London del
mismo vencimiento/strike/lado antes de calcular gamma. Polygon sólo conserva un rollback
manual con `IBT_ENABLE_POLYGON_OI=1`; no participa en el arranque normal.

Tradier Lite y Alpaca Basic siguen siendo alternativas gratuitas sin mínimo publicado, pero
ambas necesitan que el usuario cree una cuenta/token. No se fingió que estaban conectadas sin
credenciales. Optionwatch y OptionCharts son interfaces, no feeds públicos documentados.

Corrección importante: se probó el CSV keyless de OCC y contiene totales agregados de mercado
por categoría, no OI por símbolo/strike. Sirve como control de totales del mercado, pero **no**
puede alimentar paredes ni flip y queda fuera del camino del cockpit.

## Lo que encontré al revisar las alternativas mencionadas

| Servicio | ¿API gratuita utilizable? | OI por contrato | Veredicto |
|---|---:|---:|---|
| [Nasdaq Option Chain](https://www.nasdaq.com/market-activity/stocks/nvda/option-chain) | Sí, endpoint público keyless | Sí | **Conectado y verificado en los seis símbolos.** Sin SLA/API pública documentada: caché y fail-closed obligatorios. |
| [Optionwatch.io](https://optionwatch.io/) | No API pública documentada | Visible en UI | Buena interfaz gratuita; no construir un daemon contra HTML privado. |
| [option.watch](https://www.option.watch/) | Es frontend BYOD | Según proveedor | Confirma la ruta: para acciones recomienda conectar Tradier; no es un feed independiente. |
| [OptionCharts](https://optioncharts.io/docs) | No API pública documentada | Visible con 15 min de retraso | UI gratis; su propia página reserva descargas para planes de pago. No usar scraping. |
| [OptionWhales API](https://www.optionwhales.io/developers) | Sólo health en Free | OI es Pro+ | Excelente esquema de snapshots AM/PM, pero no reemplazo gratuito. |
| [HF Market Data](https://www.hfmarketdata.io/) | Sí, keyless | Sí, EOD | Prometedor para historia, no para la semana próxima: la sonda del 21-ago devolvió 07-ago como último día para los seis símbolos. |
| [MarketData.app](https://www.marketdata.app/docs/api/options/chain/) | 100 créditos/día | Sí | Free es 24 h retrasado y las cadenas actuales cobran por contrato; insuficiente para seis libros completos. |
| [ThetaData](https://docs.thetadata.us/Articles/Getting-Started/Subscriptions.html) | EOD limitado | OI no está en Free | Rechazado para OI gratuito; la tabla oficial reserva el endpoint OI a Value+. |
| [FlashAlpha](https://flashalpha.com/pricing) | 5 llamadas/día | Cotización completa es Growth | Free sirve para probar GEX/metadata, no para seis cadenas diarias. |
| [OptionData](https://www.optiondata.io/option_chain) | Prueba de 14 días | Sí | Beta y luego $599/mes de lista; no es solución gratuita permanente. |
| [Cboe delayed quotes](https://www.cboe.com/delayed_quotes/API/quote_table/) | No automatizable | Visible | Cboe prohíbe expresamente autoextracción; descartado. |
| [OCC Daily Open Interest](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/daily-open-interest) | Sí, CSV keyless | **No; sólo agregados** | Verificado y descartado para paredes/flip. |

## Contrato mínimo del adaptador

El proveedor nuevo debe normalizar cada fila a:

```json
{
  "expiry": "YYYY-MM-DD",
  "strike": 0.0,
  "right": "call|put",
  "open_interest": 0,
  "oi_date": "YYYY-MM-DD|null",
  "source": "nasdaq_public_option_chain|tradier|alpaca"
}
```

La gamma se reprecifica con spot/IV London; jamás se aceptará un GEX agregado opaco del
proveedor como sustituto de la cadena. El adaptador debe cachear OI una vez por sesión,
publicar edad/cobertura/proveedor y fallar a `DATA`, no a cero.

## Fuentes oficiales

- Tradier: [cadena](https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains),
  [campos de quote](https://docs.tradier.com/docs/quotes),
  [tiempo real vs. retrasado](https://docs.tradier.com/docs/market-data),
  [límites](https://docs.tradier.com/docs/rate-limiting) y
  [precio Lite/API](https://production.tradier.com/individuals/pricing).
- Alpaca: [contratos y `open_interest_date`](https://docs.alpaca.markets/us/docs/options-trading)
  y [plan Basic](https://docs.alpaca.markets/us/docs/about-market-data-api).
- OCC: [descarga diaria de OI](https://www.theocc.com/market-data/market-data-reports/other-market-data-info/batch-processing/daily-open-interest).
