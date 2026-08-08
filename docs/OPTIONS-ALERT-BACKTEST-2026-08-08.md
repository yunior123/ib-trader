# Motor de alertas de opciones — backtest 2026-08-08

## Resultado

El motor C++ está desplegado en **modo automático** por orden explícita del 2026-08-08.
Produce el top diario local en `data/options-alerts/YYYY-MM-DD.txt` y publica como máximo
**dos** alertas automáticas diarias a Discord. Un ticker custom también puede probarse y
publicarse explícitamente con:

```sh
bin/options_alert_engine NVDA CALL --dte 5
bin/options_alert_engine NVDA CALL --dte 5 --emit
```

La salida/payload es exactamente una línea:

```text
nvda call 230 5-DTE
```

Los símbolos no están limitados a una watchlist fija. Cada ticker válido visto en una señal
se registra dinámicamente en `data/options_alert_tickers.txt`; IBKR o el proveedor configurado
añade su cadena sin reiniciar. Si la cadena todavía no existe o está vieja, la señal queda
pendiente y se reintenta cada 30 segundos durante 20 minutos. Se admiten tickers alfanuméricos
y acciones de clase con punto/guion (por ejemplo `BRK.B`), siempre bajo los mismos gates de
frescura, delta, spread, OI y presupuesto.

## Política probada

- Población: títulos exactos `SYM: BUY` / `SYM: SELL` de `trades.db signals`.
- Precio: `poly_bars` 1 minuto, únicamente hasta donde existe historia local.
- Split cronológico: 60% de sesiones train / 40% test.
- Resultado: triple barrera TP/SL de 1 ATR, horizonte 30 minutos; si TP y SL aparecen en la
  misma vela se cuenta SL primero.
- Fricción: 0,069% del subyacente, benchmark de la casa para opción ATM líquida.
- Ranking: probabilidad declarada por la señal; barrido train de `prob >= 55/60/65/70` y
  `top 1/2/3` por día.
- El selector vivo añade gates que este estudio no relaja: cache <=15 min, delta 0,40–0,70
  (objetivo 0,55), spread <=5%, OI >500 y prima <=$200.

Reproducir:

```sh
clang++ -std=c++17 -O2 -Wall -Wextra \
  -o bin/options_alert_backtest scripts/options_alert_backtest.cpp -lsqlite3
bin/options_alert_backtest
```

## Resultado cronológico

La cobertura honesta fue pequeña: 54 eventos etiquetables, 56 sin camino completo, siete
sesiones (cuatro train, tres test). La mejor política train con al menos diez observaciones
fue `prob >=55, top 3/día`:

| bloque | n | WR | expectativa neta |
|---|---:|---:|---:|
| train | 12 | 75,0% | +0,212 ATR/alerta |
| test | 8 | 62,5% | **-0,405 ATR/alerta** |
| total | 20 | 70,0% | -0,035 ATR/alerta |

Top 1 fue peor fuera de muestra: 33,3% y -1,435 ATR/alerta. Subir el umbral a 60 tampoco
arregló el test (top 2/3: 50%, -0,929 ATR/alerta). Los umbrales 65/70 no tuvieron muestra
suficiente.

## Contrato real disponible

`data/option_vehicle_2026-07-24.json` permite una comprobación ask→bid con primas reales,
pero solo dos señales exactas pasaron simultáneamente spread/OI/presupuesto ese día: una ganó
y una perdió. La media fue positiva por una única ganadora grande; `n=2` no valida nada.

## Decisión y override explícito

La decisión estadística original fue mantener shadow porque el OOS fue negativo. El usuario
ordenó después hacerlo automático; `options_alert_engine_keepalive.sh` fija explícitamente
`OPTIONS_ALERT_AUTO=1`, `OPTIONS_ALERT_MIN_PROB=55` y `OPTIONS_ALERT_TOP_N=2`. No se cambió ni
se maquilló el resultado del backtest. Se conservaron estas barreras:

1. máximo dos alertas automáticas por sesión;
2. probabilidad declarada >=55;
3. delta 0,40–0,70, spread <=5%, OI >500 y prima <=$200;
4. ningún uso de cadena con más de 15 minutos;
5. los rechazos quedan locales y nunca se convierten en alertas plausibles.

Esto es señal-solamente: ningún binario de esta ruta contiene API de órdenes.
