# MM Fractal OMM/DMM — implementación London-only

El widget reproduce la geometría observable de la imagen del usuario sin afirmar que
conoce la fórmula propietaria de Russell Capital Group. Runtime, selector y snapshots
usan exclusivamente London Strategic Edge.

## Líneas divulgadas

- `Floor`: percentil ponderado 10% de actividad gamma × `volume_today`.
- `Green Line`: mediana ponderada de esa actividad.
- `Ceiling`: percentil ponderado 90%.
- `PML`: strike que minimiza el payout terminal ponderado por volumen; no se etiqueta
  como max pain de OI porque London no entrega Open Interest.
- Dead zone: intervalo entre Green Line y PML; su punto medio es el pivote/imán.

El widget conserva además los cuatro cuadrantes visibles en la imagen: calls y puts
por encima/en Green Line y por debajo, usando `volume_today` de LSE.

## OMM y DMM

- OMM congela el snapshot de la sesión previa o el snapshot anterior a 09:45 ET. Su
  dead-zone mid es pivote: spot encima = bullish; debajo = bearish.
- DMM empieza a actualizar después de 09:45 ET. Su dead-zone mid se presenta como
  imán intradía.
- Si falta cadena, gamma, volumen o sesión fechable se muestra `sin dato`; no hay
  fallback a otro proveedor.

Estado de validación: `UNPROVEN_LSE_PROXY_CONTEXT_ONLY`. Sirve como contexto junto al
heatmap, walls y magnets; no es gatillo ni una medición de inventario dealer.
