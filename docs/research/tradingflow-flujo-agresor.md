# TradingFlow: el agresor manda (capturado 2026-07-26, cuenta de Yunior, trial 7 días)

## La escalera de agresor, confirmada en datos reales
`Side` tiene 5 peldaños: **AAsk · Ask · Mid · Bid · BBid**.

## Su `Sentiment` NO sale del tipo de contrato, sale del AGRESOR
| fila capturada | Side | Sentiment |
|---|---|---|
| SPXW PUT 7350 26-07-31, $996,6K | **BBid** | BULLISH |
| SPX CALL 7445 26-09-18, $455,0K | **AAsk** | BULLISH |
| SPXW CALL 7475 26-07-27, $510 | **Bid** | BEARISH |
| SPXW CALL 7425 26-07-27, $1,8K | **Mid** | NEUTRAL |

Un PUT en BBid = **venta agresiva de puts** = alcista. Un CALL en Bid = **venta de calls** = bajista.

## Lo que esto dice de lo nuestro
`opt_whale_watch.py:157` usa `pc = vp/max(vc,1)` — ratio de VOLUMEN puro. No distingue
comprador de vendedor, así que **cuenta igual** un diluvio de puts comprados (bajista) que uno
de puts vendidos (alcista). Son tesis opuestas con el mismo número.

Evidencia del cierre del viernes 24-jul: el flujo grande fue **PUT BBid** (venta de puts) y
**CALL AAsk** (compra de calls) → posicionamiento ALCISTA. Nuestro mapa del mismo día da SPY/QQQ
en NEG con P/C de OI 2,80 al viernes. No se contradicen: el **OI** es estructura acumulada, el
**flujo** es quién agrede ahora. Nos falta la segunda mitad.

## Bug del referee, para no fiarse a ciegas
`XSP CALL strike 743,0` con `Spot $7411,98` etiquetado **ITM**. XSP = SPX/10 = 741,198, así que
un call de 743 está **OTM**. Sirven el spot de SPX en la fila de XSP. Su moneyness de XSP no es
de fiar; el resto de columnas sí cuadran.

## Verificación cruzada que SÍ cuadra
SPX spot 7408,30 el 24-jul contra nuestro SPY 738,31 del mismo día → ratio 10,03. Consistente.

## Serie de régimen: 17 sesiones fechadas (`data/history/tradingflow_regime_hist.jsonl`)
Su recap público da el régimen gamma por índice con fecha desde el 26-jun. Es el único
referee histórico de régimen que tenemos: nuestro `gexa_hist.jsonl` tiene **2 filas**, y en
`data/history/<fecha>/levels.json` el campo `gexa.regime` viene **null** para SPY y QQQ (solo
NVDA lo trae). Por eso el régimen histórico propio hay que derivarlo de `spot vs flip`.

**Cruce medido (solo donde TF da el veredicto DEL MISMO símbolo, sin sustituir por el de SPX):**

| fecha | sym | spot | flip | dist | nuestro | TF |
|---|---|---:|---:|---:|---|---|
| 22-jul | SPY | 747,49 | 747,00 | **+0,07%** | POS | NEG |

**n=1: no se concluye nada.** Y el único caso cae a 0,07% del flip — la frontera, donde un flip
diario congelado no puede resolver el signo. Con `spot vs flip` sobre las 4 sesiones en que TF
solo habla de SPX, coincidiríamos en 4 de 7, pero comparar QQQ contra un veredicto de SPX no es
un cruce, es una suposición.

Para que esto sirva de verdad hacen falta dos cosas: (1) poblar `gexa.regime` para SPY/QQQ en el
archivo diario, no dejarlo null; (2) acumular sesiones. El reloj corre.

## Cruce independiente con Unusual Whales (24-jul) — las dos fuentes coinciden en el signo
UW `net-prem-ticks` firma el agresor por su cuenta (ask-side − bid-side). Sobre el mismo día:

| | net_call_premium | net_put_premium | neto firmado |
|---|---:|---:|---:|
| SPY | **−82,2 M** (venta de calls = bajista) | **−47,5 M** (venta de puts = alcista) | **−34,7 M** |
| QQQ | −2,4 M | **+34,5 M** (compra de puts = bajista) | **−37,0 M** |

**Lo que confirma el cruce**: TradingFlow enseñaba SPXW **PUT BBid** (venta agresiva de puts) el
viernes por la tarde; UW da `net_put_premium` **negativo** en SPY el mismo día. Dos fuentes
independientes, mismo signo en el componente de puts. No se contradicen: en SPY la venta de
calls (−82,2 M) es mayor que la de puts (−47,5 M), y por eso el neto sale bajista.

**Lo que el ratio de volumen se comía**: SPY P/C 1,26 y QQQ 1,18 — los dos en zona muda. El
premium firmado dice −34,7 M y −37,0 M. Es la misma clase de ballena silenciosa que el tide de
−53 M del 21-jul.

⚠️ **La latencia de UW sigue SIN MEDIR en sesión** (domingo, mercado cerrado; el último bucket
venía con 43,8 h). Por eso el overlay es **banner sin voz**: no dispara nada hasta medirla el lunes.
