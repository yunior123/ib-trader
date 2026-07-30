# IBKR live + UI + order readiness QA — 2026-07-29

## Resultado

- `data/ib_mode.txt=live`; `scripts/ib_mode.py` resolvió dinámicamente Gateway `4001`.
- Gateway `4001` escuchando; conexión IBKR `readonly=True`, `marketDataType=1`.
- Prueba sobre mercado abierto: Samsung KRX `conId=17382528`, barra 1m de 6.4 s.
- `order_engine/ARM_LIVE`, `data/order_engine/ARM_LIVE` y `scalper/ARM_LIVE`: ausentes.
- Ningún `order_engine`, scalper ni executor estaba corriendo. No se colocó, modificó,
  canceló ni transmitió ninguna orden, tampoco paper.
- BUY/SELL de acciones y opciones verificados con funciones puras/fixtures locales.
- Doble llave, desarme idempotente y ownership de cancelación tienen pruebas explícitas.
- Clic normal en la app abre seis ventanas independientes; `--windows` y `--ports` mandan.
- Puertos 8080–8085 sanos, sin blanco, `signal_only:true`, versión pública `v1`.

## Evidencia

- Modo/puerto: `scripts/ib_mode.py:18-32,89-112`.
- Data bridge solo lectura/realtime: `scripts/ibkr_bar_bridge.py:477-482`.
- Seis ventanas/overrides: `macapp/main.swift:24-26,252-266,306-312`.
- Doble llave: `order_engine/safety.h:41-48`.
- Ownership puro: `order_engine/guards.h:115-120`; consumidor:
  `order_engine/tws_adapter.cpp:134-156`.
- Pruebas nuevas: `order_engine/tests/test_guards.cpp:85-113`;
  `tests/test_macos_startup_windows.py:8-18`.

## QA ejecutado

```text
zsh order_engine/tests/run_tests.sh
  120 guards + 39 chain + 499 stock/options = 658 OK
  ASan/UBSan limpio

bash order_engine/build.sh
  order_engine C++23 compilado OK

swiftc -typecheck macapp/main.swift macapp/Settings.swift
  OK

pytest test_macos_startup_windows + chart_bridge mock/isolation/liquidity
  11 passed

HTTP 8080..8085
  HTML 207014 B; JS 196203 B; 1.8–29.3 ms; /version=v1

WebSocket E2E
  8080 QQQ→GOOGL→QQQ; 8081 permaneció NVDA
```

## Límite honesto

La cinta US estaba cerrada al ejecutar QA. QQQ terminaba a las 20:00 ET; no se etiquetó
esa barra como rancia. La prueba de frescura se hizo en KRX abierto. NQ devolvió una barra
10 minutos vieja, compatible con falta de entitlement CME realtime; no se usa como prueba
de realtime. No se hizo el bundle final: otras lanes modifican archivos empaquetados.
