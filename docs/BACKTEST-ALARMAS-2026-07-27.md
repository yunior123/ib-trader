# BACKTEST ALARMAS — sesión 2026-07-27 (selloff)

Solo lectura, medido 2026-07-28. Fuentes: `data/trading-signals/2026-07-27.txt` (2.048 líneas),
`trades.db` `voice_log` (288 filas del día) y `signals`, `notify_relay.log` (segmento 1511139–1512004),
precios `data/bars_<sym>_ibkr.txt` (390 barras RTH × 30 símbolos, completo).
Entrada = close de la barra 1m de la señal; retorno en la dirección cantada; Wilson 95% al cierre.
Contexto intradía medido (open→close): MU −3,40% (low 854,79) · DRAM −4,53% · SMH −3,12% ·
QQQ −1,39% · SPY −0,79% · SNDK −12,56% · WDC −4,80% · STX −4,52%. Los −8,6%/−10,4% del titular
incluyen el gap desde el viernes; el intradía es lo de arriba.

## 1. Inventario de señales (feed del día)

| grupo | n | nota |
|---|---|---|
| direccionales backtesteadas (RTH) | 570 | tabla §2 |
| 🧲 flip/pin "TRANSICIÓN, no direccional" | 435 | spam: NVDA flip 208.4x repetido 286 veces (21 veces el mismo texto) |
| WARMUP (replay premarket 00:39–00:46) | 315 | no son señales vivas |
| FLUJO OPCIONES volC 0 volP 0 | 174 | sentinel CIEGO todo el día |
| TRUTH-LOCK / info / arranques | ~554 | 99 arranques FLOW PULSE + 97 despedidas (§5) |

## 2. WR por fuente (RTH 9:30–16:00, retorno % en la dirección cantada)

| fuente | n | WR30m | mean30m | WR60m | mean60m | WRclose | meanclose | Wilson95 close |
|---|---|---|---|---|---|---|---|---|
| sell_now (voz "sell X now") | 2 | 100% | +2,48 | 100% | +3,11 | 50% | +1,42 | — |
| price_alarm (NVDA 203 / SMH 550,50) | 2 | 100% | +1,52 | 100% | +1,82 | 100% | +1,70 | — |
| cusum_terremoto | 12 | 67% | +1,11 | 82% | +2,94 | 58% | +1,06 | [32,81] |
| bot_v6_sell (SMH/INTC/NOK/GLD/SKHY/SPCX) | 6 | 67% | +1,45 | 67% | +1,47 | 17% | −0,20 | [3,56] |
| dip_buy 🩸 | 17 | 47% | −0,19 | 24% | −0,73 | 59% | +1,01 | [36,78] |
| bb_bandwalk (hablada) | 9 | 57% | +0,09 | 57% | +0,47 | 56% | +0,55 | [27,81] |
| bb_bandwalk_MUTED p<55 | 62 | 65% | +0,82 | 70% | +1,52 | 58% | +0,38 | [46,70] |
| bb_rebote (notify_only) | 198 | 42% | −0,07 | 49% | +0,12 | 51% | −0,04 | [44,57] |
| bb_rebote [VETO medido] | 60 | 40% | −0,14 | 48% | −0,19 | 57% | +0,38 | [44,68] |
| bb15_reentrada MUTED | 94 | 33% | −0,43 | 27% | −0,88 | 54% | +0,17 | [44,64] |
| apertura_fuera_banda | 10 | 50% | +0,07 | 50% | +0,17 | 70% | −0,13 | [40,89] |
| apertura_reentrada +VOL | 6 | 83% | +0,71 | 67% | +1,09 | 83% | +0,46 | [44,97] |
| structural_magnet 🧲 | 67 | **27%** | −0,18 | 34% | −0,39 | 49% | −0,19 | [38,61] |
| bot_v6_buy (TXN/AAPL) | 2 | 50% | −0,44 | 50% | −0,54 | 50% | −0,65 | — |

Caveat de muestra: las BB disparan en ráfaga multi-símbolo el mismo minuto (correlación ≈1);
la muestra EFECTIVA es mucho menor que n. No publicar estos WR como calibración.

**Lo mejor del día** (Yunior tenía razón: "some were good, like maybe many"):
- **CUSUM TERREMOTO CAIDA de apertura**: AMD 09:31 short → **+7,33% a 60m**; SKHY 09:32 → +9,05%;
  DRAM 09:32 → +5,67%; QQQ/TSM/TSLA todos verdes. Las 7 de 09:31–09:47 clavaron la continuación.
  Las de después de 10:30 ya no (0/4 al cierre) — el terremoto es señal de APERTURA.
- **"sell S M H now" 09:31:06** (565,95 → 553,21 a 30m, +2,25% short) y **"sell Intel now" 09:56:03**
  (+2,71% a 30m). Las dos voces V6 más tempranas fueron las dos mejores órdenes del día.
- **ALARMA DE PRECIO** NVDA tocó 203,00 (09:42) y SMH 550,50 (10:11): continuación bajista real
  (+1,52% medio a 30m si se leía como short).
- **bb_bandwalk NO-fade**: correcta (57–70% WR) — y las 62 MUTED p<55 eran BUENAS
  (WR60 70%, +1,52%): el mute p<55 está calibrado en otro régimen y calló la continuación del selloff.
- Correctamente calladas: bb15_reentrada MUTED (WR60 27%) y bb_rebote [VETO medido] (WR30 40%) —
  los vetos medidos funcionaron.
- **structural_magnet fue la peor fuente** (WR30 27%, n=67): flechas ↑ hacia imanes de arriba
  (MSFT 390, AAPL 340) en pleno selloff. El propio msg dice "no WR medido" — confirmado que no lo tiene.

## 3. DIP-BUY de la mañana — veredicto: DOS OLAS

| ola | n | positivos al cierre | mean close | mean MAE (drawdown post-señal) |
|---|---|---|---|---|
| 09:47–10:20 (AMZN NOK GOOGL ASML SPCX QQQ SNDK AMD) | 8 | **2/8** | **−0,35%** | **−2,98%** |
| 10:32–11:38 (SMH LRCX TSM NVDA MU XLK WDC STX EWY) | 9 | **8/9** | **+2,22%** | −0,99% |

El low del día fue ~10:43 en casi toda la flota. **Los dips de antes de 10:30 llegaron temprano y
cayeron más** (NOK MAE −4,31%, ASML −4,38%, SNDK −6,48% y "prob 100% n=10" en el msg — esa prob es
a 3 días, no intradía, pero el drawdown fue brutal). **Los de después de 10:30 fueron entradas de
libro**: WDC +5,06% al cierre (MAE −0,34%), MU +4,74% (MAE −0,63%), STX +3,54%, EWY +2,07%.
Detalle completo por señal: salida de `bt727.py` (scratchpad), reproducible con las fuentes citadas.
A 60m el dip pierde (WR 24%) — es señal de cierre/3 días, no de scalp.

## 4. Lo que NO sonó (el hueco grande del día)

- **Opciones CIEGAS toda la sesión**: `CINTA CIEGA: 25 de la flota sin tape` a las 09:26
  (feed 09:26:01), y las 174 líneas `FLUJO OPCIONES ... volC 0 volP 0 P/C 0.00` cada 5 min.
  Resultado: **cero BALLENA, cero FLUJO CALLS/PUTS, cero MANADA en todo el selloff** — la espada
  de Napoleón estuvo envainada el día que más hacía falta. `opt_whale.log` del día: solo errores
  `Unknown contract` (strikes 20260731 inexistentes en INTC/NFLX/GLD).
- **flow_pulse corrió pero mudo** (arranque 00:46, sin una sola señal de flujo hasta el cierre).

## 5. Notificaciones (verificado contra notify_relay.log y voice_log)

- Voz del día: 46 `spoke` (10 DANGER + 36 SIGNAL), 8 `coalesced`, 234 `notify_only`. Los 17 DIP
  REAL fueron HABLADOS todos. OK.
- Relay RTH: 221 líneas elegibles → **195 ENVIADA + 24 CAP 1/5s + 0 perdidas** (cobertura completa,
  sin caída del relay en sesión; DESCARTADA por vieja: 0).
- **Las 2 mejores señales del día NO llegaron al teléfono**: `SMH: SELL` 09:31:00 y `INTC: SELL`
  09:56:00 cayeron en `CAP 1/5s` (relay_727 líneas con "CAP 1/5s: 09:31:00 | SMH: SELL"). La voz sí
  las dijo ("sell S M H now" 09:31:06). El cap de 1/5s mata justo la ráfaga de apertura.
- Dips sin push (CAP): GOOGL, ASML, SNDK, XLK. Los otros 13 sí ENVIADA.
- **Spam nocturno**: 236 líneas WARMUP entraron al relay (9 ENVIADAS al teléfono, 227 CAP) — el
  filtro excluye MUTED pero no WARMUP (`scripts/notify_relay.sh:29-32`).
- **Boot-loop post-cierre**: flow_pulse arrancó/salió ~cada 5 min de 16:00 a 24:00 (190 pares
  "arriba"/"fuera hasta manana" en el feed) — keepalive relanzando fuera de ventana.
- **BD `signals` coja**: para el 27 solo ingirió structural (539 filas). bollinger/whale/flow/cusum
  tienen `max(date)` 2026-07-24/25 en la tabla — el ingester de esas fuentes murió el 25;
  el registro completo del 27 vive solo en el feed txt y voice_log.
- Duplicados: flip NVDA/QQQ repetidos hasta 21 veces el mismo texto (cooldown del structural no
  aplica al estado "pegado al flip"); 128 repeticiones de FLUJO OPCIONES vol0.

## 6. Señales sospechosas de DATOS VIEJOS

Chequeo: precio cantado vs rango O-H-L de la barra del minuto (±0,5%). En RTH solo 2, y menores:

| hora | fuente | sym | cantado | barra | desvío |
|---|---|---|---|---|---|
| 10:10 | dip_buy | SPCX | 110,14 (zona técnica) | close 110,85 | 0,6% |
| 09:31 | apertura_fuera_banda | AMZN | 235,75 | close 233,41 | 0,54% |

Los precios cantados el 27 estaban FRESCOS (el fix de datos viejos que se está trabajando aparte
no tuvo víctimas nuevas este día en el camino de voz/feed). Lo viejo del día fue otra cosa: la
cadena de opciones (strikes inexistentes 20260731) y la cinta tick-by-tick ausente (§4).

## Método y límites
Entrada al close de la barra del minuto de la señal (hasta 60 s de adelanto — sesgo pequeño y
uniforme). Horizontes fijos, sin triple barrera; n de un solo día correlacionado → estos números
describen EL DÍA, no calibran probabilidades (regla `measured-probability`).
