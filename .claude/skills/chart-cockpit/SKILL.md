---
name: chart-cockpit
description: Manual de operación del cockpit de trading en vivo (charts/live.html + scripts/chart_bridge.py) — chart TradingView-like con GEX/flip/muros de gexa, combo_tl, narrador de mercado (DeepSeek), señales estructurales (imán/flip), marcadores de TODAS las señales/notificaciones, operaciones de los engines, y alarmas manuales estilo TradingView. Usar para arrancar/operar/extender el chart, entender los frames WS y comandos, o consultar la BD de señales para el backtest EOD. SEÑAL-SOLAMENTE.
---

# chart-cockpit — el cockpit de trading en vivo (2026-07-23)

Chart web tipo TradingView conectado a IBKR TWS, con el mapa GEX de gexa + nuestras
señales. Doctrina del mapa: [[gexa-framework]]. Cómputo GEX: [[gamma-exposure]].

## Arranque
```bash
venv-chart/bin/python scripts/chart_bridge.py --sym nvda --port 7496 --http-port 8080
# -> http://127.0.0.1:8080/    (--mock para demo sin TWS)
```
Deps (venv-chart py3.12): `ib_async fastapi uvicorn websockets`. TWS 7496 (live), clientId 60.
GOTCHAS: (1) el bridge SIRVE el .js de lightweight-charts (ruta estática) o queda undefined;
(2) uvicorn necesita `websockets`; (3) ib_async dentro del loop → `reqHistoricalDataAsync`
(await), nunca el síncrono. Hora del chart = **America/Toronto** (Intl, DST auto).

## Arquitectura: frames WebSocket (server → cliente)
| type | cadencia | contenido |
|---|---|---|
| `history` | al conectar / cambio tf-sym | barras + indicadores + levels + signals + engineOps |
| `bar` | por tick | última barra + indicadores |
| `levels` | 15s (`levels_loop`) | GEX/flip/muros/VEX/pressure/EM al SPOT VIVO |
| `narrator` | 15s / bajo demanda | lectura del narrador (⚡det / 🤖DeepSeek) |
| `structural` | 15s | señal imán/flip {text,prob,dir,kind,price} |
| `signals` | 15s | marcadores de señales + engineOps (refresco visual) |
| `alarms` | al pedir/cambiar | alarmas manuales del símbolo |

## Comandos (cliente → server, JSON por /stream)
- `{cmd:"tf", tf:"1m|5m|15m|1h|1d"}` — cambia timeframe (re-pide barras nativas).
- `{cmd:"sym", sym:"NVDA"}` — re-cualifica contrato en TWS + recarga.
- `{cmd:"scope", scope:"0DTE|ALL"}` — 0DTE puro vs toda la cadena (flip apenas se mueve, Vanna salta).
- `{cmd:"narrate", on:bool, force:bool}` — enciende narrador / fuerza pulido DeepSeek.
- `{cmd:"alarm", act:"add|del|list", price:N}` — alarma manual (escribe ~/Desktop/price-alerts.txt).

## Capas del chart
- **combo_tl**: Supertrend (ATR10×3 Wilder, Buy/Sell), Madrid Ribbon (18 EMAs coloreadas),
  BB(20,2), SMA20/40/100/200, VWAP, MACD, trendlines-con-breaks.
- **GEX (gexa)**: muros call/put + flip + perfil GEX/VEX por strike, escala $/1% (=gexa).
  IMÁN oro (gamma+) / ACELERADOR morado (gamma−). Info: chips con ⓘ + botón "ℹ Guía".
- **Marcadores** (todos desde `trades.db`, tooltip por evento):
  🐋P/🐋C ballena · 🚀 spike flujo · 🩸 dip · 🎈 bollinger · 🌋 cusum · ⏰ alarma · 🧲 estructural ·
  ⚙▲/⚙▼ operaciones de engines (verde BUY / rojo SELL) · Buy/Sell del Supertrend.
- **Píldora estructural** (#structpill, oro/rojo): "🧲 NVDA se dirige a su imán 210 ↑ · 75%".
- **Narrador** (🗣, barra inferior): lectura breve tipo gexa. ⚡ determinista (gratis) / 🤖 DeepSeek (↻).
- **Alarmas manuales** (🔔): botón → clic en el precio → línea dorada punteada con campana.
  Panel arriba-derecha lista cada alarma con 🗑 para borrarla.

## Señal ESTRUCTURAL (narrator.structural_signal)
Desde el mapa GEX, en régimen POSITIVO:
- **pin** (dist ≤0.30% del imán): "en su imán X — pin".
- **approaching** (momentum o pressure≥75 hacia el imán, dist ≤1.6·EM): "se dirige a su imán X ↑".
- **flip** (|precio−flip| <0.12%): "pegado al flip — TRANSICIÓN, no direccional".
- `prob` = CONVICCIÓN estructural transparente `50 + 0.30·|pressure| − dist/EM·10` (cap 52–85).
  **NO es un win-rate medido** — se etiqueta así en el tip y en la BD (respeta la ley de probs medidas).

## Narrador (thrift de tokens)
`scripts/narrator.py`: (1) `deterministic(lv)` = lectura desde niveles, CERO tokens, cada 15s;
(2) `deepseek(lv)` = pule en ≤2 frases (llm.env DEEPSEEK_API_KEY, deepseek-chat, urllib, max_tokens 120).
AI solo BAJO DEMANDA (botón ↻ / primer encendido / cambio material con throttle 90s). OFF por defecto.
Key NUNCA impresa. Señal-solamente (el system prompt prohíbe ordenar comprar/vender).

## BD de señales (para el backtest EOD)
`trades.db` (tablas nuevas 2026-07-23): `signals` (todas las señales/alarmas/notificaciones,
clasificadas por `source`) + `voice_log` (qué se HABLÓ/preemptió/descartó). Poblado por
`scripts/signals_db.py --daemon` (tail del HUD Desktop). Opciones: snapshots 5min en
`data/history/YYYY-MM-DD/`. Consulta para backtest:
```bash
python3 scripts/signals_db.py --stats
sqlite3 trades.db "SELECT ts_txt,symbol,source,msg FROM signals WHERE date='YYYY-MM-DD' ORDER BY ts_txt"
```

## Operaciones de los engines en el chart
`load_engine_ops(sym, bars)` lee `bot_trades` + `etf_operations` filtradas al símbolo+día →
marcadores ⚙. Hoy los engines están en señal/paper (no operan); cuando el mejor algoritmo
esté listo y opere solo, sus fills aparecen aquí en tiempo real. Voz de la voz-cola: [[voice-alerts]].

## Reglas
Aditivo, degradación limpia. Backup a `backup/` antes de tocar el bridge/generador. Escribir
config de alarma ≠ orden broker (guard `assert_signal_only` intacto). SEÑAL-SOLAMENTE. Todo
tiempo real salvo VIX (falta suscripción CBOE). No es consejo financiero.
