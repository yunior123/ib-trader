# UW — latencia medida en sesion (2026-08-05)

Generado por `scripts/uw_latency_probe.py --rth-measure`. TODOS 8a (latencia) + 8b (websocket).

- Corrida: 2026-08-05T13:35:05.682505+00:00 UTC · en_rth=True · peticiones UW=9 (tope 10) · cupo 3704/30000

- sin IBKR esta semana: el proxy del disparador es el print de finnhub (data/rt_last_<SYM>.txt); TODOS 8f sigue pendiente


## 8a — edad del feed y desfase contra el disparador

| medida | min | mediana | max |
|---|---|---|---|
| `stock-state.tape_time` vs reloj (s) | -1.30 | 1.50 | 1.70 |
| `net-prem-ticks.tape_time` vs reloj (s) | 5.70 | 8.50 | 8.50 |
| UW − print finnhub (s, >0 = UW detras) | -224.23 | 0.20 | 0.67 |

**Veredicto** (umbral de la casa: <60 s = candidato a tiempo real):
- `stock-state`: **CANDIDATO A TIEMPO-REAL**
- `net-prem-ticks`: **CANDIDATO A TIEMPO-REAL**

Prediccion registrada de antemano en TODOS 8a: **30-90 s**.


## 8b — websocket en RTH

| caso | status | handshake s | cierre s | bytes | close-frame |
|---|---|---|---|---|---|
| sin enviar nada | HTTP/1.1 101 Switching Protocols | 0.2622 | 0.2626 | 0 | False |
| join lista | HTTP/1.1 101 Switching Protocols | 0.366 | 0.3685 | 0 | False |
| join objeto | HTTP/1.1 101 Switching Protocols | 0.1902 | 0.1907 | 0 | False |

`GET /api/socket` canales declarados: `[]`

**El socket entrega datos en RTH: NO — se mantiene el veredicto: no se construye consumidor**

## 8c — colinealidades (killlist test 1: |rho|>0,9 = muere ya)

**(1) `dir_vega_flow` vs `signed_premium`** — rho_pooled=**0.0706** (n=1013120 minutos, 92 dias, 30 syms); per-sym min/mediana/max = -0.2416 / 0.1929 / 0.5442
- control `dir_delta_flow` vs `net_delta` (precedente rho=1,0): rho=**1.0000**, byte-identicos 1013079/1013120

**(2) `senal_capitan` vs `fleet_consensus` (manada sobre BARRAS)** — 9 dias:

| capitan | rho | n | acuerdo de signo |
|---|---|---|---|
| SPY | 0.4198 | 678 | 68.1% |
| QQQ | 0.5065 | 678 | 72.2% |
| SMH | 0.1229 | 678 | 56.6% |

**(3) `max_pain` (UW/OI) vs `abs_wall` (gex)** — rho=**-0.0196** (n=185 sym-dias, 7 dias); strike identico en **8.6%**; mediana |max_pain−abs_wall|/spot = **5.14%**

Avisos que NO se pueden omitir al leer estos numeros: la muestra de (2) son buckets SOLAPADOS de pocas sesiones (n_eff mucho menor que n) y el signo de (1) cambia entre dias. Sobrevivir la colinealidad NO es tener edge: publicar probabilidad sigue bloqueado en TODOS 8e.

---

## Lectura honesta de 8a — la prediccion FALLO, y por que no se celebra

**Predije 30-90 s y salio 1,5-8,5 s.** La regla que yo mismo registre de antemano dice: *"si sale
< 30 s, sospechar de la medicion antes de celebrarla"*. Sospechas concretas, no retoricas:

1. **Hay desfase de reloj entre este Mac y los servidores de UW.** Una de las edades salio
   **−1,3 s** (negativa): el `tape_time` de UW venia por delante de nuestro reloj. Con un offset
   de ese orden, **cualquier afirmacion por debajo de ~2 s no esta justificada**. Lo defendible
   es "unidades de segundo", no "1,5 s".
2. **El −224,23 s del minimo de `UW − finnhub` NO significa que UW se adelante 224 s.** Significa
   que el print de finnhub de SPY estaba **rancio** (102 s en la 1ª pasada) y UW venia mas
   fresco. Mide la ranciedad de finnhub, no la de UW.
3. **Ventana estrecha**: 2 pasadas, 2 simbolos, 09:35-09:37 ET — la ventana de mas volumen del
   dia. **La latencia en la apertura no es la latencia de la picadora de las 11:30-14:00.**
   Repetir a mediodia antes de generalizar.
4. **`cube_lag = 0`** en `net-prem-ticks`: el cubo del minuto en curso ya estaba publicado. Eso
   es consistente con un feed que consolida por minuto y lo publica rapido.

**Lo que SI queda establecido**: UW no es un feed de 15 minutos. En la apertura entrega en
unidades de segundo, con `stock-state` mas fresco que `net-prem-ticks` (1,5 s vs 8,5 s de
mediana), y con `market_time: "regular"` confirmando sesion viva.

**Lo que NO cambia**: la regla dura de la casa sigue intacta — **ningun nivel que dispare una
orden viene de UW**. El nivel se calcula; el PRINT que lo confirma es de IBKR. Que UW sea rapido
lo asciende a *candidato*, no a disparador, y el contraste que de verdad decide (contra
`data/bars_<SYM>.txt`) sigue pendiente en **TODOS 8f** porque no hay IBKR esta semana.

## Lectura honesta de 8b — el veredicto de madrugada SE MANTIENE

Los 3 casos en RTH dan **exactamente la misma firma** que de madrugada: **101 Switching
Protocols** y cierre en **0,19-0,37 s con 0 bytes y sin close-frame**, insensible a lo que se
envie. `GET /api/socket` sigue declarando **`[]` = cero canales**.

**La hipotesis falsable ("UW apaga el socket fuera de horario") queda REFUTADA con el mercado
abierto.** Es una puerta de plan, no un horario. **No se construye ningun consumidor de
websocket**; el motor de flujo va por REST con sondeo, cuya latencia es la de arriba.

**No se pudo medir si el 101 consume cupo**: el contador salto 3.651 → 3.704 (+53) entre las dos
lecturas, pero en esa ventana tambien pedian `uw_flow_tape` y demas procesos de la flota — el
contador es **global del token, no de este proceso**. Se declara no medible por esta via en vez
de atribuir el salto al websocket.
