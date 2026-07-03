# LOTTOS SEMANA — martes 2026-08-04 ~11:50 ET

Método: confluencia GAMMA (gex_snapshot 11:42, chains vivas <4min) × NET OPTIONS (UW net-prem-ticks hoy, signed = net_call − net_put) × BALLENAS (uw_fleet_flow hoy + flow-alerts, solo ask-side, expiry ≤08-07). Gates: strike OTM hacia el imán SIN cruzar muro, prima ≤$200, spread ≤5%, OI>500 (Polygon 11:33), sin earnings dentro del vencimiento. Se publica la confluencia, no un %.

## MAÑANA 08-05

`AAPL 307.5c 8/5 @ 1.65 · $165 · spread 2.5% · OI 5,608` (variante barata: `310c 8/5 @ .91 · $91 · OI 9,533`)
- GAMMA: spot 306.38 → imán/call-wall 310 (pin), lado cercano, sin muro intermedio, régimen POS, flip 301.26 debajo.
- NET: +$4.3M signed hoy, +$1.6M últimos 30 min.
- BALLENAS: alertas mudas (0 en flota hoy ≤08-07) — PERO flow-per-strike: 310p VENDIDAS bid-side ($4.6M bid vs $1.4M ask) = soporte dealer hacia 310. Confluencia 2.5/3.

`AMZN 275p 8/5 @ 1.57 · $157 · spread 1.3% · OI 2,842`
- GAMMA: spot 277.50 → put-wall/imán 275 debajo, sin muro intermedio, régimen POS.
- NET: −$17.0M signed hoy (−$2.8M últimos 30 min) — el más bajista de la flota sin veto.
- BALLENAS: alertas mudas — PERO flow-per-strike: 280c VENDIDAS bid-side ($13.7M bid vs $10.1M ask) = techo en 280. Confluencia 2.5/3.

## VIERNES 08-07

**NINGUNA idea pasa los 4 gates.** El más cercano: AAPL 310c 8/7 @ 2.08 = $208, falla prima por $8 (y 307.5c 8/7 spread 6.3%). NOK 10c 8/7 @ .28 ($28, OI 14,319) falla spread 7.4% — regla 4, vetada.

## CONFLUENCIA PLENA 3/3 QUE NO CABE EN $200 (info, no lotto)

| sym | 3 evidencias | contrato legal más barato (strike ≤ imán) |
|---|---|---|
| MU | net +$95.8M (+$38.6M últ. 30m) · ballenas $12.1M calls ask ≤08-07 · spot 896.74 → imán 900 | 900c 8/5 $2,435 (OI 2,363) / 8/7 $3,935 (OI 6,282). Flow-per-strike 900: $59.6M call ask vs $44.8M bid = +$14.8M comprado. EL flujo del día. |
| MSFT | net +$72.9M · ballena $1.9M call ask · spot 497.38 → imán/cw 500 | 500c 8/5 $425 (OI 2,698) |
| INTC | net +$25.7M · ballenas $3.1M calls ask · spot 99.70 → imán/cw 100 | 100c 8/5 $263 (OI 8,173); 102c 8/5 sí cuesta $183 pero cruza el muro 100 = PROHIBIDO |
| SMH | net +$16.3M · ballena $0.7M call ask · spot 572.14 → imán/cw 580 | 580c 8/5 $590 y spread 13.6% — doble fallo |

## DESCARTADOS (motivo dominante)

- **PIN (spot pegado al abs-wall, prohibido lotto comprado)**: QQQ (719 a 0.03%), SPY (767 a 0.15%), NVDA (210 a 0.22%), TXN (280 a 0.19%), GLD (375 a 0.08%), DRAM (50 a 0.04%).
- **EARNINGS dentro del vencimiento**: AMD (hoy AH), SPCX (hoy AH), SNDK (08-05 AH), WDC (08-05 AH).
- **GAMMA NEG whipsaw**: SPCX, SKHY.
- **CONFLICTO de fuentes**: TSLA (net −$10.1M vs ballena $1.0M call 325 8/7), GOOGL (net +$5.5M vs gamma abajo), NFLX (net −$3.5M vs gamma arriba), EWY (net + vs gamma abajo, spot bajo flip 168.79), META (net −$13.8M vs gamma arriba; régimen sin resolver), SNDK (net −$3.7M vs +$13.7M últ. 30m, earnings además).
- **SIN CONFLUENCIA (ballenas y/o net mudos)**: TSM, ASML (además $1,697 de spot, nada ≤$200 legal), XLK (sin quote en sidecar para 186), AVGO (net +$30.4M pero spot 414.82 pegado al cw 415 = comprar EN el muro), LRCX (spread 7-12%), STX, AAPL 8/7, QCOM (155p spread 9.2%), NOK (net +$0.05M, spread 7.4%).

## Fuentes y cuota
gex_snapshot 11:42 ET · chain_full Polygon 11:33 (OI medido) · NBBO CBOE sidecars 3-5 min · UW: 35 requests (25 net-prem-ticks + 1 flow-alerts + 7 earnings + 2 flow-per-strike; MU/NVDA/QQQ/SMH/SPY reutilizados del archivo del día). Presupuesto 800 → gastado 35.

Lotto = riesgo a cero, prima = stop. No es consejo financiero.
