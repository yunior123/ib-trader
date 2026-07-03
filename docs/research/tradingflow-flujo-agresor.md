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

## Perpetuos 24/7: el fin de semana SÍ se mueve (medido 2026-07-26 ~23:50 ET)
Verificación decisiva antes de fiarse del gap — **la prima al cierre del viernes es cero**, así
que lo que se ve ahora es movimiento real, no premio estructural de los tokenizados:

| perp | @cierre vie | real IBKR | prima | ahora | movimiento del finde |
|---|---:|---:|---:|---:|---:|
| DRAM | 53,23 | 53,20 | +0,06% | 56,06 | **+5,32%** |
| INTC | 92,05 | 92,32 | −0,29% | 95,33 | **+3,56%** |
| MU | 919,44 | 920,95 | −0,16% | 949,84 | **+3,31%** |
| NVDA | 206,88 | 206,84 | +0,02% | 209,29 | +1,16% |
| QQQ | 685,53 | 684,23 | +0,19% | 693,32 | +1,14% |

**El orden es coherente y eso es lo que le da peso**: memoria pura (DRAM +5,3%) > semis
individuales (INTC +3,6%, MU +3,3%) > índice (QQQ +1,1%). No es ruido de un símbolo suelto: es
el complejo de memoria liderando, exactamente el engranaje que la doctrina ya describe con Corea.

**Contradice al flujo firmado del viernes**, que era bajista en MU (−140,1 M), QQQ (−37,0 M) y
SMH (−22,4 M). Las dos lecturas se publican; no se promedian. Cuando dos fuentes buenas discrepan,
el desacuerdo ES la información: el posicionamiento del viernes iba corto y el fin de semana subió.

DRAM = **Roundhill Memory ETF** (confirmado con `reqContractDetails`), no una cripto. INTC 95,51
vs Intel 92,32 descarta colisión. **STX no está listado** en Bybit para Seagate — `STXUSDT` es
Stacks (0,146 $).

## Corea confirma, en subasta de preapertura (2026-07-26 19:42 ET = lun 08:42 KST)
KRX abre 09:00 KST; la subasta de preapertura (08:30-09:00) ya publica precio indicativo:

| | subasta | cierre vie | | volumen |
|---|---:|---:|---:|---:|
| SK Hynix (000660) | 1.809.000 | 1.759.000 | **+2,84%** | 539.618 |
| Samsung (005930) | 256.500 | 250.000 | **+2,60%** | 2.344.296 |
| KODEX 200 (proxy KOSPI) | 106.365 | 106.300 | +0,06% | 3 |

**Dos fuentes independientes dicen lo mismo**: los perpetuos de Bybit (DRAM +5,32%, INTC +3,56%,
MU +3,31%) y la subasta coreana (SK Hynix +2,84%, Samsung +2,60%). En las dos, **la memoria
lidera y el índice apenas se mueve** — KODEX200 +0,06% con volumen 3 (ninguna convicción en el
índice), QQQ perp +1,14%.

Eso es lo que hace creíble la lectura: no es un símbolo suelto disparado, es el complejo de
memoria moviéndose junto en dos mercados que no se hablan entre sí.

Y las dos contradicen el flujo firmado del viernes (MU −140,1 M, QQQ −37,0 M, SMH −22,4 M).
