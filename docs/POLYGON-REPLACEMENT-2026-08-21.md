# Reemplazo gratuito de Polygon OI — 2026-08-21

## Decisión para la semana próxima

Polygon queda **OFF por defecto**. El cockpit no consulta su API ni acepta su caché.
Hasta validar un sustituto con datos reales, `flip`, `net_gex` y `regime` permanecen
`DATA`; London sigue entregando paredes, imán y perfil descriptivo `gamma × volume_today`.

La ruta recomendada es:

1. **Tradier como OI primario.** Su plan Lite es gratuito, el mínimo de cuenta publicado
   es $0, la API está incluida, y la cadena por vencimiento entrega `open_interest`, IV y
   Greeks de ORATS. Producción ofrece opciones en tiempo real; sandbox es 15 minutos
   retrasado. El límite publicado es 120 solicitudes/minuto, muy por encima de una captura
   diaria para seis símbolos.
2. **Alpaca como segundo proveedor diario.** El plan Basic es gratuito y el endpoint de
   contratos de opciones expone `open_interest` junto con `open_interest_date`. Su feed
   gratuito de precios es indicativo, pero eso no bloquea este diseño: London conserva spot,
   IV/Greeks y actividad intradía; Alpaca sólo aporta OI start-of-day.
3. **OCC como control/fallback autoritativo.** OCC publica una descarga CSV diaria de OI y
   documenta el URL para automatización. Requiere parser de símbolo OCC y unión con la
   superficie London, pero no requiere clave y sirve para reconciliar Tradier/Alpaca.

No se cambia automáticamente a un proveedor sin una captura paralela y estas puertas:
fecha de OI explícita, cobertura call/put de ambos lados, al menos 50% de contratos positivos
con IV London utilizable, expiraciones solicitadas completas y diferencia de muros/flip
explicada frente al control OCC.

## Lo que encontré al revisar las alternativas mencionadas

| Servicio | ¿API gratuita utilizable? | OI por contrato | Veredicto |
|---|---:|---:|---|
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

## Contrato mínimo del adaptador

El proveedor nuevo debe normalizar cada fila a:

```json
{
  "expiry": "YYYY-MM-DD",
  "strike": 0.0,
  "right": "call|put",
  "open_interest": 0,
  "oi_date": "YYYY-MM-DD",
  "source": "tradier|alpaca|occ"
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
