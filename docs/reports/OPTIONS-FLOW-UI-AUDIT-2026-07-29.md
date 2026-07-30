# Auditoría UI de flujo de opciones — 2026-07-29

Alcance: revisión de `charts/live.html` sin modificar `macapp` ni rediseñar la
interfaz compartida. La comparación usa documentación pública de
[SpotGamma Tape](https://support.spotgamma.com/hc/en-us/articles/36233401585683-What-is-SpotGamma-Tape),
[SpotGamma HIRO](https://support.spotgamma.com/hc/en-us/articles/4420646443539-What-is-the-SpotGamma-HIRO-Indicator),
sus [ejes y funciones](https://support.spotgamma.com/hc/en-us/articles/4421103606803-What-does-each-axis-on-the-HIRO-Chart-represent),
la [ventana móvil de HIRO](https://support.spotgamma.com/hc/en-us/articles/50265906309907-What-does-the-Rolling-Window-setting-do-on-the-HIRO-chart)
y [FlowAlgo](https://www.flowalgo.com/). Son referencias funcionales, no una
propuesta de copiar su identidad visual.

## Lo que ya funciona bien

- La barra superior expone fuente, modo, cuenta, timeframes, capas griegas,
  liquidez, alarmas, zonas y widgets (`charts/live.html:536-582`).
- La infobar concentra régimen, GEX, flip, walls, vanna, charm, presión, expected
  move y edad del precio (`charts/live.html:586-607`).
- El tape UW no pinta datos ficticios, bloquea artefactos rancios en RTH y
  muestra hora, símbolo, call/put, lado, strike, expiración, premium, tamaño y
  volumen/OI (`charts/live.html:2738-2792`).
- Los widgets son acoplables, colapsables y responsivos para la cuadrícula de
  seis ventanas.

## Gaps concretos y priorizados

### P0 — semántica direccional

Los textos “net call premium positivo = bullish” y “calls masivas = techo / puts
masivos = piso” son demasiado categóricos (`charts/live.html:728-757`). La
dirección depende del lado agresor, apertura/cierre, spot frente al strike,
expiración, gamma y posible multi-leg. El UI debe:

- mostrar `ask`, `bid`, `mid/unknown` como estados de primera clase;
- evitar chip bullish/bearish cuando el proveedor no lo entrega o el lado es
  indeterminado;
- describir el wall o magnet como contexto, no como conclusión automática.

### P0 — fuente, cobertura y edad por fila

La edad global es útil, pero cada print necesita timestamp/edad, fuente,
entitlement y porcentaje de tape sin lado. Un banner debe distinguir
“mercado quieto” de “feed incompleto”. El subtítulo de Net Premiums también
debe nombrar el productor real y no mezclar UW, IBKR y una vía futura.

### P0 — filtros de investigación

Faltan controles visibles para call/put, ask/bid/mid, sweep, expiración/DTE,
premium mínimo, volumen/OI y ticker. Tape, HIRO y FlowAlgo hacen de esos filtros
una parte central del análisis; sin ellos, treinta filas rápidas siguen siendo
ruido.

### P1 — agrupar contratos repetidos

Añadir una vista “Contract Data” agrupada por símbolo, strike y expiración:
número de hits, premium firmado, tamaño, volumen/OI y primera/última hora. Debe
preservar acceso a las filas crudas para auditoría.

### P1 — precio y flujo en el mismo eje temporal

Agregar, solo si existe tape firmado y fresco, una serie de premium/delta
nocional acumulado alineada con el precio, con ventanas 1m, 5m, 10m, 30m, 1h y
sesión. Sin lado fiable la serie debe quedar vacía, no aproximarse.

### P1 — vínculo a evidencia

Cada fila o grupo debe poder abrir su registro crudo: timestamp, payload
normalizado, regla, fuente y razones. Esto permite explicar una alerta tardía o
contradictoria sin depender de capturas.

### P2 — accesibilidad y consistencia multi-ventana

- Añadir `aria-label`, `aria-expanded` y foco visible a controles icon-only.
- Permitir plegar/expandir por teclado; documentar que el drag no es el único
  mecanismo.
- Respetar `prefers-reduced-motion`.
- Hacer explícito si el layout se guarda globalmente, por símbolo o por ventana,
  y ofrecer un preset reproducible para seis ventanas.

## Orden recomendado

1. Corregir semántica, fuente y estados desconocidos.
2. Incorporar filtros y agrupación contractual.
3. Añadir overlay temporal únicamente cuando el backend tenga flujo firmado.
4. Cerrar accesibilidad y persistencia de layout.

Este orden mejora confianza antes que densidad visual y evita convertir datos
incompletos en una apariencia de precisión.
