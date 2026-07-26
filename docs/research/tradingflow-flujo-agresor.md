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
