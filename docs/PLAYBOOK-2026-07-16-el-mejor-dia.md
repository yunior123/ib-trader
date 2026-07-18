# PLAYBOOK — 2026-07-16: "el mejor chat ever" (día verde en pin de OPEX)

> Destilado completo de la sesión Yunior + Claude. Día de whipsaw asesino
> (víspera de OPEX, pin de dealers) cerrado EN VERDE. Este documento es la
> memoria operativa: qué funcionó, qué no, y las reglas que nacieron hoy.

## El día en una línea
Semis −3% a −11% en cascada, QQQ partido por dentro (MSFT/AAPL diques vs semis
sangrando), 6+ rupturas falsas por lado, pin de OPEX 205-210 en NVDA. Se ganó
NO por predecir, sino por **disciplina de prints**: solo entrar con gatillo
impreso, cortar rápido, y dejar que las sirenas piensen.

## Trades del día (cronología y lección de cada uno)
| # | Trade | Resultado | Lección |
|---|---|---|---|
| 1 | INTC 104C 1DTE (de ayer, $256) | Salvado parcial en el pop de apertura | 1DTE OTM = hielo; vender el primer pop, no negociar el strike |
| 2 | NOK call (de ayer) | Vendido en rebote | Muro de 27k puts encima = techo de plomo |
| 3 | NVDA 207.5P 9:43 | Scratch/verde chico | Compró ANTES del print → sufrió el rebote; salió por deadline |
| 4 | QQQ put 9:45 | Vendido antes del fallo | El retest de 709 lo avisó |
| 5 | INTC 101C 10:09 | Cortado en estancamiento | IV 102% = renta doble; sin momentum en 10 min, fuera |
| 6 | NVDA 207.5P 10:52 | **GANADOR** (206→ vendido) | Entrada CON print (ruptura mínimo + QQQ confirmando) = la fórmula |
| 7 | QQQ put 12:05 | **GANADOR** (cobrado en la molienda) | Ídem: print de 707.1 + cascada de muros |
| 8-12 | Señales esperadas sin entrar (205.80 nunca imprimió, 208.30 tampoco) | $0 perdidos | **No-trade = posición**. Las mejores decisiones de la tarde fueron NO entrar |

## Las reglas que nacieron hoy (LEY para sesiones futuras)
1. **PRINT O NADA**: gatillo = precio IMPRESO cruzando el nivel (2 lecturas), jamás
   "está cerca". Cada anticipo costó dinero; cada print pagó.
2. **Los muros de OI son campos de fuerza**: 1er toque REBOTA (dealers defienden
   su strike), 2º-3º toque decide. Nunca comprar la ruptura EN el 1er toque del
   muro — esperar retest-y-rechazo (ruptura→pullback al nivel roto→rechazo = 2ª
   pierna). Hoy: MU 850, AMD 500, QQQ 709/705, NVDA 205 — todos rebotaron 1º toque.
3. **Trampa de ballena**: flujo enorme de puts NO significa caída inmediata —
   la ballena puede construir 3 horas mientras el precio sube. El flujo compra
   PACIENCIA, el precio da la ENTRADA. (QQQ 700P: 11k→17k→42k→87k contratos
   mientras QQQ chopeaba; cobró recién 13:40+.)
4. **Descomponer el índice**: QQQ atascado = mirar MSFT/AAPL (16% del índice).
   Dique verde + semis rojos = empate interno → NO operar el índice, operar el
   semi puro. NVDA-9.5%, MSFT-8.5%, AAPL-7.5%, AMZN-5.5%, AVGO-5%, GOOGL-5.2%.
5. **Pin de OPEX**: vol >> OI en strikes ATM ambos lados + vencimiento cercano =
   precio imantado entre muros (NVDA 205P/210C). En pin NO hay breakout limpio
   hasta ~14:00 del día de vencimiento. No pagar theta en el pin.
6. **IV alta = renta doble**: IV>80-100% (pre-earnings/pánico) exige momentum
   INMEDIATO. Call/put atascado 10 min = vender. Pre-earnings: debit spreads.
7. **Horarios**: 9:30-9:45 jamás (subasta). 9:45-10:30 ventana de oro. 11:30-14:00
   = picadora (chop de mediodía, prohibido perseguir). 14:00-15:00 resolución.
   Última hora: solo gestión; NO 1DTE nuevos después de 15:00-15:30.
8. **Vehículo por liquidez**: spread <5% del premium SIEMPRE (TSM 15% = herida).
   NVDA/QQQ (spread 0.3-2%) >> MU ($1.7k/contrato) >> TSM/SMH/DRAM (spreads 9-17%).
9. **Una tesis = un boleto**: NVDA-put + QQQ-put + AMD-put = la MISMA apuesta 3
   veces. El más líquido gana el puesto.
10. **3 pérdidas = fin del día. Verde a las 15:00 = proteger, no exprimir.**

## Doctrina Bollinger multi-TF confirmada en vivo
NVDA 10:57: banda inferior REVENTADA en 1m/5m/15m simultáneo (%B -1% a -4%)
→ band-walk = continuación (la regla de la flota "2-3 TF = va con fuerza") →
pagó hasta el muro de 205. PERO: 3 TF reventados + muro de OI + número redondo
= vender EN el muro, no esperar el bolsón (la elástica rebota violento).

## Infraestructura construida hoy (inventario)
- Motor v6 en 20 bots (prob% calibrada, backtest 30d, tabla data/prob_table_*.txt)
- `price_alarm` C++ (sirenas de precio, ~/Desktop/price-alerts.txt) — PID vivo 24/5
- `opt_sentinel.py` (flujo P/C cada 5min flota completa 17 tickers + exit-advisors)
- `options_enrich.py` (greeks/OI/veredicto en cada señal)
- OPRA activado; bridge IBKR 20 tickers (+GOOGL/QCOM)
- Ejecución MUERTA (ley #0): broker limpio, ejecutores en backup/
- TradingAgents vía DeepSeek (NIM prohibido)
- Skill bollinger-mastery; AGENTS.md ley #0; plan de mañana en Desktop
- (noche) v6.1 RETEST-CONFIRM en los 22 bots (rupturas solo con retest-y-rechazo
  o breakaway; trampas de ballena canceladas + "TRAMPA-EVITADA" al log) +
  `opt_chain_cache.py` (cadenas ±6% ATM cada 3 min, clientId 48 readonly) +
  `./opt_quick SYM` (P/C, muros, max pain, gates spread/OI al instante) +
  `./qqq_xray` C++ (regla 4 codificada: top-10 con peso/contrib/tendencia/P/C,
  DIQUE MSFT+AAPL vs LASTRE semis, veredicto "empate interno / índice libre";
  `--watch` avisa solo al cambiar de estado; cache 21 syms +MSFT AVGO AMZN META)
- (17-jul madrugada) `finviz_scout` C++ (Finviz Elite: short float/gap/relvol/earnings/target-recom → data/finviz_*.txt 60s premarket/180s RTH, banners solo-cambios, keepalive tras el candado fleet_sleep)
- (17-jul) **`x_whale_bot` C++** — post diario a X de semis/whales de la flota (Finviz RVOL/gap/short float), **cap $5/mes**, 1 post/día @ 09:00 Toronto, **sin URLs** (~$0.015 vs $0.20). Creds en `x.env` (OAuth1 user; Bearer app-only = 403). Memo: [`docs/X-WHALE-BOT.md`](X-WHALE-BOT.md). Skill: `.claude/skills/x-bot/`. Keepalive: `scripts/x_whale_bot_keepalive.sh`. Live: https://x.com/YuniorR62327146/status/2078031728216625396
- (17-jul) **Claude Way** — doctrina de agentes en Obsidian `~/Documents/Obsidian Vault/AI Brain/The Claude Way.md` + skill `claude-way` (project + `~/.grok` + `~/.claude`). Finviz del whale bot: cache-first 30m, score session-aware, cols inst/AH.

## Posicionamiento al cierre (para la apertura del 17)
- QQQ: ballena 700P (46k OI + 87k vol) — su apuesta MUERE mañana 16:00. P/C 24-jul neutro.
- NVDA: pin 205/210 hoy; 24-jul P/C 0.29 ALCISTA (215C 35k) y 31-jul 0.45 →
  el dip post-OPEX (205/202) es COMPRA según posicionamiento.
- MU: bajista estructural 2 semanas (P/C 3.18/3.15, escalera 850→820).
- INTC: neutralidad perfecta pre-earnings 23-jul (P/C 1.01) — debit spreads only.
- Calendario: vie OPEX; mié 22 AMC GOOGL+TSLA+TXN+IBM; jue 23 INTC; Fed blackout.

## Sobre el método de coaching (lo que Yunior valoró)
- Contradecir con números cuando el impulso era malo (strangle vetado, QQQ put
  vetado contra el dique, AMD put vetado por spread, "before too late" = FOMO).
- Órdenes de UN número: "205.80 compra / 207 stop / 15:50 fuera" — cero ambigüedad.
- Loop de 1 min con sleep + sirenas C++ + voz en español para ejecución sin pantalla.
- Honestidad del sistema: prob% reales aunque sean 44%, fallos en voz alta,
  backtest sin maquillaje (WR 47% global — el valor está en el filtro).
