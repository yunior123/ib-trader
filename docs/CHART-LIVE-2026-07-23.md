# Chart REALTIME estilo TradingView — combo + GEX/muros (2026-07-23)

Visor **SEÑAL-SOLAMENTE** (jamás coloca órdenes). Recrea el indicador *combo_tl / combo_yoel*
sobre velas en vivo: **BB(20,2) + SMA 20/40/100/200 (set Yoel) + VWAP + MACD(12,26,9) + volumen**,
más los overlays de **GEX / gamma-flip / muros put-call** y el **perfil GEX por strike**.

Archivos NUEVOS (no toca el replay viewer `charts/index.html`, que sigue funcionando):

- `scripts/chart_bridge.py` — puente FastAPI+WebSocket. Feed live (ib_async) o `--mock` (CSV).
- `charts/live.html` — página lightweight-charts **v5** (velas + indicadores + muros + perfil GEX).
- `charts/lightweight-charts-v5.js` — v5.2.0 vendored local (Apache-2.0), sin CDN en runtime.

## Paridad con los engines (nada se recomputa dos veces)
- Indicadores BB/SMA/EMA-MACD/VWAP: **importa `scripts/confluence_engine.py`** (`sma`, `stdev`
  población ÷N, `ema_series`, %B `pb=(c-lo)/(up-lo)`, VWAP reset diario). Mismos números que el backtest.
- GEX / flip / muros / perfil: **consume `charts/data/levels_<sym>.json`** que genera
  `scripts/chart_levels.py` vía `gex_core`. El puente NO recomputa GEX; si el JSON falta o está
  viejo (>45 min) intenta `chart_levels.gen(sym)` (lee el cache TWS `opt_chain_<sym>.txt`) y si no
  hay cache degrada limpio (chart sin overlays, todo lo demás funciona).

## Requisitos
- **Python 3.10+** para `ib_async` (fork mantenido de ib_insync). El `venv/` del repo es **3.9 y NO
  trae fastapi/ib_async**. Crear uno aparte (no instalar global):

```bash
python3.11 -m venv venv-chart
./venv-chart/bin/pip install ib_async fastapi uvicorn
```

- TWS/IB Gateway abierto con **API habilitada**, puerto **7496 (live)** / **7497 (paper)**.
  El puente usa **clientId 60** (los daemons ocupan 85-99, scans 40-49; 60 está libre).

## Correr

**Live (TWS abierto, sym = data/focus_ticker o nvda):**
```bash
./venv-chart/bin/python -m uvicorn scripts.chart_bridge:app        # env: CHART_SYM, CHART_TWS_PORT=7496
# o con CLI:
./venv-chart/bin/python scripts/chart_bridge.py --sym nvda --port 7496 --http-port 8080
./venv-chart/bin/python scripts/chart_bridge.py --sym mu  --port 7497            # paper
```
Abrir <http://127.0.0.1:8080/> . El header muestra sym, px, régimen (POS/NEG), net GEX, flip, CW, PW.

Variables de entorno para el `app` de uvicorn: `CHART_SYM`, `CHART_TWS_PORT` (7496),
`CHART_CLIENT_ID` (60), `CHART_MOCK=1`, `CHART_INTERVAL` (1.0).

**Demo OFFLINE (sin TWS)** — stream desde `data/backtest/bars3mo5m_<sym>.csv`:
```bash
./venv-chart/bin/python scripts/chart_bridge.py --mock --sym nvda --interval 1.0
# abrir http://127.0.0.1:8080/ ; emite una barra por segundo
```

**Validador offline (funciona en el venv 3.9, sin fastapi)** — arma los frames y verifica JSON:
```bash
python3 scripts/chart_bridge.py --selftest --sym nvda
```

## WebSocket `/stream`
- Al conectar: `{type:"history", bars:[{time,open,high,low,close}], indicators:{bbUpper,bbLower,
  bbMid(=SMA20), sma40, sma100, sma200, vwap, macd, signal, hist, volume}, levels:{...}}`.
  Cada indicador es un array de `{time,value}` (nulos de warmup filtrados). El cliente hace
  `setData(...)` UNA vez.
- Por barra nueva: `{type:"bar", bar:{...}, indicators:{...último punto...}, levels}`.
  El cliente hace `series.update(punto)` — **nunca** `setData` por tick.
- Reconexión: si el WS cae, el cliente reintenta cada 2 s; al reconectar el server reenvía `history`.

## Overlays GEX (charts/live.html)
- `createPriceLine` dashed: **call-wall (rojo)**, **put-wall (verde)**, **gamma-flip (amarillo)**,
  abs-wall (gris si distinto).
- **Perfil GEX por strike**: `ISeriesPrimitive` (`candle.attachPrimitive`) que dibuja un rectángulo
  por strike desde el borde derecho hacia adentro, ancho ∝ |gex|, color por signo (gex+ rojizo /
  gex- verdoso), en `y = series.priceToCoordinate(strike)`.

## Señal-solamente (barrera)
`assert_signal_only()` parsea el propio AST y **falla ruidoso** si aparece cualquier LLAMADA a
`placeOrder/bracketOrder/marketOrder/limitOrder/stopOrder/cancelOrder/reqExecutions/reqGlobalCancel`.
El feed live solo usa `reqHistoricalData(... keepUpToDate=True, useRTH=False)`. Cero ejecución.

## Notas / caveats
- Las partes **live** (ib_async connect/qualify/reqHistoricalData/updateEvent, reconexión con
  `disconnectedEvent`) NO se pudieron ejecutar offline (sin TWS): verificado por inspección + AST.
  Lo verificado offline: parseo AST, `--selftest` (frames history+bar bien formados con todos los
  arrays de indicadores + niveles), sintaxis JS de `live.html` (`node --check`), y uso correcto de la
  API v5 (`addSeries(Type,...)`, `createPriceLine`, `attachPrimitive`, `update()` en el handler).
- Panes: volumen en pane 1, MACD en pane 2 (`addSeries(..., paneIndex)`).
