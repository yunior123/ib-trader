# Qué fuente es TIEMPO REAL y cuál es DELAYED — medido, no supuesto

> Escrito el 2026-07-26 por orden de Yunior: *"verifica cual data is delayed y cual no, con
> evidencia, search, priority goes to realtime not delayed data, ibkr i think is not delayed right?"*
>
> **Respuesta corta: sí, tenías razón. IBKR es el único tiempo real que tenemos.**
> Polygon y CBOE son los dos delayed, y cada uno por un motivo distinto.

---

## El veredicto

| fuente | latencia | evidencia (medida hoy) | para qué sirve |
|---|---|---|---|
| **IBKR / TWS** | 🟢 **TIEMPO REAL** | `reqMarketDataType(1)` en los 4 puentes; `ibkr_bar_bridge.py:352` lo declara *"1 = REALTIME. Delayed PROHIBIDO"* | **DISPARO**: spot, NBBO, la cinta, el gate de spread |
| **Polygon** | 🔴 **15 min** | `/v3/trades` y `/v3/quotes` → **401 NOT_AUTHORIZED**; el snapshot de acciones también. Su tabla de precios: Starter $29/mes = *15-minute delayed*; Advanced $199/mes = *real-time* | **HISTORIA**: 2 años de barras 1m, archivo de cadenas |
| **CBOE CDN** | 🔴 **delayed, y desigual** | El endpoint se llama literalmente `delayed_quotes`. Medido a la vez: `QQQ` 1,8 h · `_SPX` 4,2 h · `SPY` y `SMH` **21,5 h** | **ESTRUCTURA**: cadena completa, SPX/XSP/NDX, bid/ask de respaldo |
| **Unusual Whales** | 🟢 **segundos** (MEDIDO en RTH 2026-08-05 09:35-09:37) | `stock-state` mediana **1,5 s** · `net-prem-ticks` mediana **8,5 s** con `cube_lag=0` · `market_time:"regular"`. Detalle y avisos en `docs/UW-LATENCIA-RTH-2026-08-05.md`. **Ojo**: hay desfase de reloj con UW (una edad salió −1,3 s) → afirmar por debajo de ~2 s no está justificado; medido solo en la apertura, falta la picadora. `market-tide` sigue en cubos de 5 min **por construcción** (su resolución la descalifica para disparar), `greek-exposure` diario | **HISTORIA**: 1 año de griegas de dealer, DEX por strike. **Candidato**, NO disparador: la regla dura no cambia — ningún nivel que dispare una orden viene de UW; el contraste contra `data/bars_<SYM>.txt` sigue pendiente (TODOS 8f, sin IBKR esta semana) |

---

## La prueba que importa: Polygon NO adultera el dato, solo lo entrega tarde

Comparé la misma barra de QQQ del viernes 24-jul en las dos fuentes:

| minuto | IBKR (`bars_qqq_ibkr.txt`) | Polygon |
|---|---:|---:|
| 16:23 | 685,0900 | 685,09 |
| 16:24 | 687,7200 | 687,7263 |
| 16:25 | 685,0600 | 685,06 |

**Idénticos.** Es un dato importante y conviene no confundirse: Polygon es *correcto*, solo llega
15 minutos tarde. Por eso vale para medir el pasado y **no vale para disparar**.

⚠️ **Cuidado con medir latencia en fin de semana**: hoy es domingo y "la última barra tiene 33 h"
no significa nada — el mercado cerró el viernes a las 16:00. La latencia solo se mide **en sesión**.
Por eso aquí la evidencia es estructural (entitlements, `reqMarketDataType`, timestamps propios del
feed), no un reloj de pared.

---

## Consecuencia operativa: quién manda en cada capa

Esto ya estaba implícito en el diseño; ahora está medido y escrito.

```
DISPARO (el precio que decide)     IBKR/TWS   TIEMPO REAL   <- aqui NUNCA otra fuente
  spot, NBBO, cinta firmada, gate de spread, print-o-nada

ESTRUCTURA (el mapa del dia)       CBOE       delayed       <- vale: se CONGELA a las 09:35
  muros lejanos, flip, SPX/XSP/NDX, bid/ask de respaldo

HISTORIA (lo que se mide)          Polygon    15 min        <- vale: el pasado no cambia
  2 anos de barras 1m, archivo diario de cadenas

REFEREE (que no nos mintamos)      las tres + UW, comparadas cada sesion
```

**Por qué un feed delayed SÍ vale para la estructura**: el flip y los muros **se congelan a las
09:35** (`chart_levels.py:72`) y solo cambian cuando cambia la cadena. Un mapa con 1,8 h de retraso
describe el mismo libro de opciones. El retraso solo mata en el **disparo**, y ahí manda IBKR.

**Regla dura que se deriva**: ningún nivel que dispare una orden puede venir de una fuente delayed.
El nivel se puede *calcular* con CBOE; el **print que lo confirma** tiene que ser de IBKR.

---

## Lo que NO tenemos en tiempo real, y cuánto costaría

| hueco | vía | coste |
|---|---|---|
| Barras 1m de **SPX / NDX** (índices) | suscripción IBKR **CBOE Global Indexes** | **~$1,50/mes** — y desbloquea el **VIX** de paso |
| Cinta de opciones firmada (HIRO propio) | ya la tenemos: `ibkr_bar_bridge.py:250` `reqTickByTickData(..., "AllLast", ...)` | **$0**, falta apuntarla a contratos de opción |
| Tiempo real en Polygon | plan Advanced | $199/mes — **no hace falta**: IBKR ya lo da y Polygon es para historia |
| Cadena completa en tiempo real | IBKR da ±6% ATM (`opt_chain_cache.py:50`) | el resto de la curva por CBOE, delayed, congelado a 09:35 |

**La compra que sí tiene sentido son los $1,50/mes de CBOE Global Indexes**: cae SPX en vivo (hoy
solo tenemos su cadena, no sus barras — Polygon da `NOT_AUTHORIZED` para `I:SPX`) y cae el VIX, que
desbloquea la banda de fragilidad. Los $199 de Polygon serían pagar por algo que IBKR ya nos da.

---

## Cómo se declara esto en el dato (obligatorio)

Todo fichero que cruce fuentes lleva la procedencia **dentro**, no en un comentario:
`chain_src`, `greeks_src`, `spot_source`, `feed_age_s`. Y **jamás se mezcla una griega de CBOE con
una de Polygon sin decirlo en la cabecera** (`~/CLAUDE.md`). Si un consumidor no puede saber si su
nivel vino de tiempo real o de un feed de 21 horas, el nivel no vale.

Sources:
- [Polygon.io Pricing](https://polygon.io/pricing)
- [Polygon.io Stocks](https://polygon.io/stocks)
