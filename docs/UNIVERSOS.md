# Los DOS universos, y por qué no son el mismo

> Escrito el 2026-07-26 al añadir los índices (Yunior: *"SPX/SPXW/XSP… feel free to add them to
> fleet"*, y luego *"for now focus on qqq, spy, spx, fleet, priority to those, smh too"*).
> Confundirlos es la forma más fácil de romper MANADA. Ya pasó una vez.

---

## `data/fleet.txt` — la flota de SEÑALES (30 símbolos)

**Quién la lee: 36 ficheros.** Entre ellos `fleet_consensus.py:23` (`FLEET = open("data/fleet.txt")`),
que es **el denominador de MANADA**.

Para estar aquí, un símbolo necesita **barras de 1 minuto**. Sin barras no hay bot, ni brújula, ni
Bollinger, ni voto — es un símbolo mudo que solo sirve para agrandar el denominador.

> ⚠️ **El precedente que justifica esta regla**: el 2026-07-25 `fleet_consensus` hacía
> `except: continue` y el símbolo desaparecía del denominador → **21/26 = 80,8% disparó voz DANGER
> "comprar PUTS" cuando 21/30 = 70% no debía**. Sonó tres veces, una con barras de 11 horas.
> Un símbolo que no puede votar **no puede estar en la lista de votantes**.

## `data/universe_gamma.txt` — el universo del MAPA (35)

Los 30 de la flota **+ SPX, XSP, NDX, DIA, IWM**.

Para estar aquí basta con tener **cadena de opciones con griegas y OI**. Da mapa gamma: flip,
muros, POC, régimen, pin vs trampilla. **No vota, no habla, no dispara.**

---

## Por qué los índices entran aquí y NO en la flota — MEDIDO el 2026-07-26

| símbolo | cadena de opciones | barras 1m | ⇒ dónde va |
|---|---|---|---|
| **SPX** | ✅ Polygon `I:SPX` 250 contratos, 248 con gamma · CBOE `_SPX` 28.784 | ❌ **`NOT_AUTHORIZED`** | **solo mapa** |
| **XSP** | ✅ CBOE `_XSP` 16.704, 14.381 con gamma | ❌ | **solo mapa** |
| **NDX** | ✅ Polygon `I:NDX` 250, todos con gamma · CBOE 15.498 | ❌ (200 pero vacío) | **solo mapa** |
| **DIA** | ✅ CBOE 4.200, 3.715 con gamma | ✅ (es ETF) | mapa; flota **posible** |
| **IWM** | ✅ CBOE 5.594, 4.905 con gamma | ✅ (es ETF) | mapa; flota **posible** |

**SPX tiene el mapa pero no la cinta.** No es un defecto nuestro: Polygon no autoriza barras de
índice con esta clave. Se desbloquearía con la suscripción IBKR **CBOE Global Indexes** (~$1,50/mes)
— la misma que hace falta para el VIX, así que un solo pago cae dos casillas.

**DIA e IWM sí podrían entrar en `fleet.txt`** (son ETFs con barras), pero **no entran todavía**:
antes hay que darles bot, keepalive y `book_quality` medido, y comprobar que su presencia no diluye
la amplitud. Entran al mapa hoy; a la flota cuando tengan con qué votar.

---

## Lo que NO se añade, y por qué

- **`SPXW`** — **no es un símbolo**. La cadena `_SPX` trae 28.784 contratos = **9.626 raíz `SPX`**
  (mensuales, AM-settled) **+ 19.158 raíz `SPXW`** (weeklies, PM-settled). Mismo subyacente, mismo
  spot. Añadirlo sería contar el índice dos veces.
- **`XSP` en `fleet.txt`** — es **SPX/10 exacto** (741,20 vs 7.411,98). Mismo subyacente. En el
  denominador sería un voto duplicado: la regla 4 de la casa, *una tesis = un boleto*.

---

## Por qué SPX aporta aunque ya tengamos SPY

No es redundante, y la prueba no es teórica: son titulares del propio Market Recap de TradingFlow.

- **22-jul**: *"Dealer gamma split between a still-positive SPX and a newly short SPY"*
- **15-jul**: *"QQQ flips short gamma while SPX and SPY stayed long"*

**El índice y su ETF tienen regímenes distintos el mismo día**, porque su OI vive en sitios
distintos. Leer solo el ETF es leer el proxy.

## Y por qué XSP es el que se puede OPERAR

Contrato ATM del vencimiento vivo (27-jul), medido:

| | call | put | ¿cabe en el presupuesto de $200? |
|---|---:|---:|---|
| SPX | $4.280 | $1.710 | **no** |
| XSP | $396 | **$187** | **sí, el put** |

**XSP es el único vehículo de índice operable con la regla de ≤$200.** SPX sirve para leer el mapa;
XSP para tomar la posición. No es el motivo por el que se pidió añadirlo, pero es el bueno.

---

## Modo OBSERVACIÓN (cómo entran)

Los cinco nuevos entran con **mapa sí, voz no**: se les calcula gamma y se archiva su cadena, pero
**no cantan** hasta tener una semana de datos y `book_quality` medido. Es la misma cautela que ya
está escrita para SPX en `TODOS.md`: *un símbolo muerto encoge denominadores*.
