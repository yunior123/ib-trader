# Auditoría del compass — 2026-07-29

Alcance: inspección estática de `scripts/compass.cpp`, calibrador y pruebas. No se
tocó el motor de órdenes. Esta auditoría distingue controles ya presentes de
gaps reales; no interpreta una flecha como recomendación de compra o venta.

## Resultado

La arquitectura actual ya contiene los controles que faltaban durante las
sesiones en que aparecía una flecha verde al 50% contra una caída:

- Las confirmaciones se agrupan en cuatro familias independientes y una familia
  no puede contar dos veces; el techo duro permanece en seis
  (`scripts/compass.cpp:588-629`).
- Los vetos tienen techo duro y cubren band-walk, régimen negativo, VT,
  trampilla, agotamiento por toques y catalizador del líder
  (`scripts/compass.cpp:632-663`).
- Un Wilson inferior menor o igual a 50% produce `sin_edge`, sin porcentaje,
  en vez de una cifra maquillada a 50 (`scripts/compass.cpp:842-861`).
- La dirección candidata queda separada de la dirección operable. Pullbacks
  contra 15 minutos, transiciones y aproximaciones quedan neutrales hasta
  confirmar; una continuación solo se publica con band-walk multi-TF o edge
  medido (`scripts/compass.cpp:1056-1107`).
- Overnight es un coeficiente multiplicativo y no ocupa una familia
  (`scripts/compass.cpp:1109-1121`).
- El band-walk se calcula en el camino vivo, no solo en fixtures de prueba
  (`scripts/compass.cpp:1430-1441`).
- El spot del mapa GEX solo reemplaza las barras si el artefacto tiene menos de
  diez minutos (`scripts/compass.cpp:1453-1465`).

## Correcciones aplicadas

1. El consumidor de calibración ahora usa `n_eff` tanto en la celda exacta como
   en el pool, con fallback a `n` solo para archivos antiguos. El gate ya no
   puede tratar miles de observaciones correlacionadas como miles de ensayos
   independientes (`scripts/compass.cpp:812-839`).
2. Una opción CLI desconocida ahora escribe el error en `stderr` y termina con
   código 2. Antes era ignorada, por lo que un typo podía arrancar el daemon con
   otra configuración (`scripts/compass.cpp:1558-1571`).

## Estado estadístico real

`data/compass_calib.json` contiene 2,050 filas crudas y 365 excluidas, pero
ninguna celda alcanza el mínimo de 30 ensayos efectivos. Los mayores pools
tienen `n_eff=19`. Ejemplos:

| Celda | n_raw | n_eff | wr30 | Wilson inferior |
|---|---:|---:|---:|---:|
| CONTINUACION f0 NEG | 1,527 | 19 | 36.84% | 19.15% |
| CONTINUACION pool | 2,048 | 19 | 42.11% | 23.14% |
| CONTINUACION f0 POS | 359 | 19 | 47.37% | 27.33% |
| CONTINUACION f1 NEG | 103 | 18 | 55.56% | 33.72% |

Conclusión: hoy no existe evidencia suficiente para subir la confianza de la
flecha. Bajar el mínimo o volver a usar `n_raw` sería sobreajuste. La mejora
correcta es acumular más sesiones no solapadas y conservar neutralidad mientras
no exista edge.

## Gaps priorizados

### P0 — honestidad de amplitud

Cuando falta expected move, el cálculo de amplitud todavía puede usar un 2% del
spot como fallback doctrinal. Debe migrarse a `amplitude=null` con motivo
explícito, o a una fuente de volatilidad observada y fresca. Requiere un cambio
de contrato de salida y consumidores; no se alteró en este parche pequeño.

### P1 — procedencia estructurada del capitán

`captain_flow` depende de texto humano con TTL corto. Debe consumir un JSON con
lado agresor, strike, expiración, fuente, edad y estado `unknown/mid`. Sin esos
campos, calls o puts grandes no demuestran por sí solos dirección.

### P1 — timestamps futuros

La frescura overnight debe rechazar timestamps demasiado futuros además de
viejos. Usar diferencia absoluta, con tolerancia pequeña para skew de reloj, y
probar ambos extremos.

### P1 — persistencia atómica

La escritura temporal comprueba `fopen`, pero el resultado del `rename` final
debe verificarse y registrarse. Un fallo de rename no debe dejar al keepalive
pareciendo sano con JSON viejo.

### P2 — validación walk-forward

Mantener una división temporal por sesión, reportar Brier/calibración además de
win rate, y separar universos (índices, semis y single names). No promover una
celda por rendimiento in-sample ni combinar filas simultáneas de la flota como
ensayos independientes.

## Pruebas

- `tests/test_compass.py::test_unknown_cli_option_fails_loud`
- `tests/test_compass.py::test_calibration_consumer_prefers_effective_sample_size`
- Suite existente de estados, familias, vetos, probabilidad y calibrador.
