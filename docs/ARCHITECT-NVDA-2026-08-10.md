# Architect / NVDA — revisión estructural del 10 de agosto de 2026

## Estado de la evidencia

La predicción bajista de The Architect para NVDA está aceptada como real por
confirmación directa del usuario. Su texto exacto todavía no está en el archivo
local: el corpus de X termina el 7 de agosto y la consulta adicional quedó sin
créditos. Por eso este documento evalúa el resultado y la estructura London sin
inventar palabras, hora o niveles que no se hayan recuperado del post.

Los ejemplos del VIX pivot y RKLB del 10–11 de agosto también quedan clasificados
como `USER_CONFIRMED_REAL_NOT_YET_LOCAL_ARCHIVE`, no como ejemplos dudosos.

## Resultado observado

Datos London de un minuto, sesión regular de NVDA del 10 de agosto:

- Apertura: **223.44**.
- Máximo: **224.13** a las 09:31 ET.
- Mínimo: **216.76** a las 12:38 ET.
- Cierre: **217.56** a las 15:59 ET.
- Apertura a cierre: **-2.63%**.
- Máximo a mínimo: **-3.29%**.

La predicción bajista acertó la dirección y ocurrió una expansión clara hacia
abajo. Esta revisión no atribuye al post un precio objetivo exacto porque su texto
no está archivado localmente.

## Lectura de la cadena y niveles London

La instantánea de las 09:25 ET mostraba spot 223.80, Call Wall 225, Put Wall 220,
magnet 225, flip archivado 217.55, expected move 4.65 y POC 92% calls. La secuencia
observable fue:

1. NVDA no recuperó 225 y rechazó la zona superior.
2. El Call Wall migró de 225 a 222.50 alrededor de las 10:10 ET.
3. El precio perdió el Put Wall 220.
4. La caída alcanzó la zona del flip archivado, aproximadamente 217.66, a las
   12:35 ET; el mínimo llegó tres minutos después.

La lección Architect no es que “muchas calls” sean alcistas. Calls concentradas
por encima del spot pueden formar techo; la migración descendente del Call Wall,
seguida por pérdida del Put Wall, es una secuencia estructural bajista más útil
que el porcentaje de calls aislado.

## Delta, absorción, value e imbalance

El video y el libro de Order Flow definen tres patrones de giro:

1. **Absorción:** volumen ejecutado inusualmente alto en Bid y Ask cerca de una
   zona importante, mientras el precio deja de progresar.
2. **Cambio de Delta:** Delta de footprint = volumen ejecutado al Ask menos
   volumen ejecutado al Bid; un cambio/divergencia contra el precio puede advertir
   agotamiento.
3. **Bid/Ask imbalance:** comparación diagonal; referencia inicial 3:1 (300%) y
   mayor fuerza cuando hay tres o más niveles apilados.

`Value` es la ubicación que da sentido a esas señales — Call/Put Wall, magnet,
máximo/mínimo anterior, POC o VWAP — y no una cuarta señal independiente. El
contrato nuevo sólo declara `REVERSAL` cuando hay rechazo en value y coinciden al
menos dos de los tres patrones.

## Qué puede y qué no puede afirmar London

London entrega precio, IV, Greeks, volumen y premium de opciones. La respuesta
actual no incluye Open Interest ni la cinta ejecutada Bid×Ask con aggressor side.
Por eso:

- CW, PW y magnet London se calculan como concentraciones **gamma × volumen**.
- El score Architect compara actividad gamma, delta y premium; es descriptivo y
  su umbral ±20 aún no está validado fuera de muestra.
- La actividad de opciones puede servir de contexto, pero no sustituye Delta de
  footprint, absorción ni imbalance ejecutado.
- `REV 3` muestra `DATA` cuando faltan esas ejecuciones, en vez de fabricar una
  confirmación.

## Refinamiento incorporado

El algoritmo conserva los colores anteriores y añade estas defensas:

- Call Wall sólo puede quedar en/por encima del spot; Put Wall en/por debajo.
- La migración del wall se archiva por `option_source_ts` real.
- No se comparan acumulados si cambió la cobertura de contratos o la sesión.
- Se separa `ARCH_OPTIONS_CONTEXT_PROXY` de las tres señales de footprint y nunca
  cuenta para el 2-de-3.
- Se exige cierre de rechazo en una zona de value antes de armar un giro.
- Todo umbral nuevo permanece `UNPROVEN_FORWARD_AUDIT_ONLY` hasta reunir muestra
  cronológica suficiente y aprobar un test fuera de muestra.

## Auditoría footprint terminada

El caso NVDA sigue siendo un estudio de evento, no un backtest del post. Sí se cerró
la auditoría separada de footprint con 66 sesiones-símbolo (NVDA, QQQ y SPY), 25,740
barras RTH y 243 celdas cronológicas con entrada en la siguiente apertura, matched
nulls, Wilson y BH-FDR. Ninguna celda sobrevivió; absorción aportó 412 candidatos pero
ningún umbral promocionable. El verificador independiente pasó 18/18 controles.

Esto prueba Delta de ejecuciones de acciones en XNAS, no el Delta/skew de opciones de
Architect. La consecuencia correcta es mantener Architect como doctrina principal de
opciones y usar footprint sólo como confirmación contemporánea en value. Los resultados
y limitaciones están en `data/research/delta_setups_backtest.md`.
