# FLEET ANALYSIS — miércoles 2026-08-05 (premarket; mapa 07:18 ET, precios 07:05 ET)

> **Reloj de la máquina al cerrar el doc: 07:20 ET del miércoles 5-ago. El mercado NO ha abierto** (RTH 09:30). Todo lo de abajo es premarket y sigue vigente para la apertura; si se lee después de las 09:30, los niveles valen pero la "fuerza" hay que releerla.

Contexto del día: **AMD −10.6% premarket** (earnings anoche), SpaceX −8% AH (primera earnings; SPCX sin barras frescas, última 07-31 — declarado). **HOY AMC: SNDK + WDC reportan** (SNDK −1.5% pm, WDC −0.7% pm). Mañana lockup SpaceX. Viernes NFP.

Fuentes y edades (todo medido, nada inventado):
- `data/gex_snapshot.json` 06:57 ET hoy (cadena viva Polygon, edad 45-93 s; spot Intrinio/Finnhub 1-16 min).
- `data/uw_gex_expiry.json` asof 2026-08-04 EOD (gamma/charm/vanna por expiry, UW).
- Flujo: `docs/NET-PREMIUMS-2026-08-04.md` (corte 12:36 ET martes) + `data/uw_net_prem.json` (8 núcleo, 17:25 martes).
- Ballenas lunes 8/3 con ΔOI asentado: `scripts/whale_forensics.py --fecha 2026-08-03`.
- **ΔOI del flujo del MARTES 8/4** (asentado esta madrugada): calculado ad-hoc = OI del snapshot Polygon vivo de esta mañana vs `data/history/2026-08-04/chain_full_*.json`, **solo contratos presentes en ambos lados** (sin artefactos de banda).
- Fuerza premarket: `data/bars_*_ibkr.txt` (puente de proveedores, frescas a 06:41-06:46 ET; gap = último vs cierre RTH 8/4).
- Polygon aggs del mismo día: **403 en este plan** → el premarket sale de las barras del puente, no de Polygon. Declarado.

### PROCEDENCIA Y HORA DE CADA DATO (precisión, no atajo)

| dato | hora de captura | qué describe realmente | retraso |
|---|---|---|---|
| Cadena de opciones (flip, muros, POC, GEX, DEX, pin) | **snapshot Polygon tirado HOY 07:16-07:18 ET** | **el libro tal como CERRÓ ayer 8/4**: el OI del snapshot está asentado al cierre de ayer (verificado: ya contiene el flujo del martes, p.ej. INTC 108C 8/7 pasó de 659 a 19.741 OI). No es el fichero archivado de ayer, es un tiro nuevo — pero el OI que dibuja los muros es el de ayer. | OI = cierre 8/4; griegas `delayed_15m`, pobladas 72-95% según símbolo |
| Gamma/charm/vanna por expiry (UW) | asof **2026-08-04 EOD** | reparto de gamma que muere esta semana | 1 día |
| Net premium / flujo | martes 8/4 corte **12:36 ET** (doc) + widget **17:25 ET** (5 syms) | flujo del martes, **incompleto en las últimas 3,5 h** | 1 día |
| Ballenas ΔOI lunes | flujo 8/3 vs OI asentado 8/4 | posición confirmada | 2 días |
| Ballenas ΔOI martes | OI snapshot de hoy 07:16 vs archivo 8/4 | posición abierta ANOCHE | fresco |
| Barras de fuerza (`bars_*_ibkr.txt`) | 06:41-06:46 ET hoy | premarket temprano | ~30 min |
| Tick `ws_trade_*` | trade sellado 07:05 ET | precio premarket | **~15 min de retraso, medido** |
| Spot del mapa | 07:18 ET | Finnhub 7-31 s (SPY/QQQ/META/INTC) · Intrinio ~15 min (AMZN/GOOGL/MU/AAPL/SMH) | mixto, por símbolo |

**Consecuencia:** los muros/flip/pines de este doc son **la foto del cierre de ayer** — que es exactamente lo que un mapa gamma debe ser al abrir. Se usan como referencia para la apertura de HOY; el PRINT que los confirme tiene que ser del precio en vivo de la sesión, nunca de la columna delayed. `bidask_ok_pct = 0.0` en toda la cadena → **este mapa no puede validar spreads**: pasar `scripts/optgate.py` antes de cualquier boleto (regla 4).

Límites declarados:
- **NOK no tiene entrada en gex_snapshot** → sin flip/muros GEX propios; se usan OI, compass y UW.
- whale_forensics 8/3→8/4 usa archivos band-limited (~±15% del spot): saltos desde/hacia OI=0 en strikes lejanos **sin volumen que los respalde** son artefactos de banda (ej.: NOK 15C ago21 "+53.7k" con volumen top del día de solo 51k en 10C; INTC 150C/160C ago21; AMZN 370C ago21 "−43.8k"). Filtrados abajo; solo cito ΔOI con ambos lados medidos o con volumen coherente.
- `uw_net_prem.json` intradía solo cubre SPY/QQQ/SMH/NVDA/MU; el resto viene del doc del martes (corte 12:36, faltan 3.5h de sesión).
- whale_forensics con per-strike UW del 8/4 solo está archivado para MU/SPY/QQQ/SMH/NVDA; usado para MU.

---

## REFRESH VIVO — precios 07:05 ET, mapa 07:18 ET

**El tick de `data/ws_trade_<SYM>.txt` llega con ~15 min de retraso** (fichero escrito 07:19-07:20, trade sellado 07:04:43-07:05:16 → edad 900-933 s en los 11 símbolos, medido). No hay IBKR esta semana; la capa de proveedores sirve Intrinio delayed. El **spot del mapa sí es fresco** (`gex_snapshot` 07:18, spot Finnhub edad 7 s). Ningún nivel de disparo debe leerse de la columna delayed: sirve para saber DÓNDE está el precio, no para imprimir el nivel.

| sym | último (07:05, +15m delay) | vs cierre 8/4 | flip 07:18 (drift vs 06:57) | call/put wall | abs wall |
|---|---:|---:|---|---|---|
| SPY | 774.50 | +0.44% | 771.23 (↑ de 770.38) | 775 / 770 | 775 pin |
| QQQ | 724.40 | −0.07% | 711.90 (↓ de 713.06) | 735 / 720 | 735 pin |
| SMH | 573.43 | −0.75% | 588.24 (=) | 600 / 530 | 530 trampilla |
| AMZN | 279.91 | +0.80% | 263.12 (↑ de 254.34) | 280 / 275 | **280 pin — precio pegado** |
| META | 596.00 | +0.62% | 581.68 (↑ de 580.19) | 600 / 580 | 600 pin |
| GOOGL | 382.79 | +0.90% | 370.77 (=) | 385 / 375 | 380 pin |
| MU | 878.80 | −1.78% | **879.26 — precio EN el flip** | 900 / 800 | 800 trampilla |
| AAPL | 310.07 | +0.05% | 303.56 (↓ de 304.63) | 315 / 300 | **310 pin — precio pegado** |
| NOK | 10.00 | +0.60% | sin mapa GEX | — | 10 pin por OI |
| INTC | 98.40 | −2.43% | 90.58 (↑ de 90.17) | 110 / 98 | **98 put wall — precio pegado** |
| AMD | 474.02 | −10.13% | 493.66 | 500 / 470 | 470 trampilla |

Lo que cambia respecto al análisis escrito a las 06:45: **AMZN subió a tocar el pin 280**, **AAPL cayó a 310.07 = exactamente el pin**, **INTC en 98.40 sobre su put wall 98**, y **MU rebotó a 878.80 = su flip 879.26** (abrió el premarket 3 puntos por debajo). Los cuatro llegan a la campana pegados a su nivel decisivo. AMD estabilizó en 474 (de −10.6% a −10.1%).

---

## CAPITANES (contexto que manda — regla 12)

### SPY — pin fortaleza en 775
- **Mapa**: gamma POS (+619M net GEX), flip 770.4 (migró 756→770 ayer), put wall 770, call wall = POC = abs wall **775 pin FORTRESS** (pin score 58.9). Imanes 770/775.
- **Flujo**: +170M semana (el mayor de la flota), martes positivo en ambos métodos UW. 34.3% de la gamma bruta muere esta semana; charm 8/5 +41.9M.
- **Fuerza**: 774.1 pm (+0.39%), %B 1m 0.55 / 15m 0.91. Compass CONTINUACION candidato up, **8 prints en 775**.
- **Día**: jaula 770-775; el pin en 775 pelea cada extensión. Sobre 775 impreso ×2 → aire a 780. Bajo 770 (flip+put wall juntos) impreso → cambia el día entero a defensivo.

### QQQ — caja 720-735, put-carga al viernes
- **Mapa**: POS (+276M), flip 713.1, put wall 720 (compass lo marca trampilla local), call wall = POC = 735 pin fortress. Imanes 720/735.
- **Flujo**: viernes 8/7 carga **−48.5M en puts** (cobertura de semana); dirección del martes INDETERMINADA entre métodos UW (gotcha documentado).
- **Fuerza**: 723.4 pm (−0.20%), %B 1m 0.58 / 15m 0.76.
- **Día**: 720 es el nivel del día. Aguanta 720 → deriva a 725-730. Pierde 720 impreso → trampilla, aire hasta 713 (flip). NFP viernes + esa put-carga = el mercado ya pagó protección.

### SMH — el capitán en gamma NEGATIVA con AMD −10.6%
- **Mapa**: **NEG (−20.5M)**, flip 587.9 un **+2.6% ARRIBA** del spot 573. Call wall 600, put wall 530 = abs wall **TRAMPILLA**, POC 530. Caja NEG 530-600 = whipsaw/aceleración, no dirección.
- **Flujo**: +13.8M semana (modesto). AMD (tropa pesada) −10.6% pm; MU −2.2%; SNDK/WDC reportan hoy AMC.
- **Fuerza**: 573.2 pm (−0.80%), %B 1m 0.43 / 15m 0.56. Compass SIN LECTURA (hueco de feed) — declarado.
- **Día**: capitán semis bajo el flip = **toda señal alcista de la tropa (MU incluido) queda degradada** mientras SMH no recupere 588. Bajo 570 impreso acelera (gamma NEG); 530 es trampilla, no piso. Este es el riesgo central del día.

---

## AMZN — día de pin en 280 (fortaleza)
- **Mapa**: POS fuerte (+234M), flip 254.3 (−5.9% debajo, lejos). Put wall 275, call wall = POC = abs wall **280 pin FORTRESS** (pin score 102, el 2º más alto). Imanes 275/280.
- **Flujo**: semana +25.3M (lun +41.8 / mar −16.5 = toma de beneficios); hacia 8/5 +6.8M, viernes −4.6M. 31.2% de la gamma bruta muere esta semana; charm 8/5 −2.6M, 8/7 +2.0M.
- **Ballenas** (lun, ΔOI asentado): aperturas 300C 8/7 +10.2k, 305C 8/7 +7.1k, 315C ago21 +6.8k. **ΔOI martes→hoy**: 300C ago21 **+9.1k** (37.3k OI: techo de mes creciendo), racimo 0DTE 275-287.5C +4.6-6.2k cada uno, 275P 8/5 +3.9k, y **250P 8/7 CIERRE −4.2k** (protección profunda retirada = menos miedo).
- **Fuerza**: 279.4 pm (+0.61%), %B 1m 0.28 / 15m 0.90, r6 −0.14%. Compass: **ya 3 prints en 280** premarket.
- **Escenario**: jaula 275-282.5 con imán en 280 — el OI 0DTE recién abierto a ambos lados de 280 lo refuerza. Sobre 282.5 impreso ×2 → 285-287.5 (estantería call). Bajo 275 impreso → 270 (270P 8/7 +2.6k) y ahí para; el flip en 254 no es objetivo del día.
- **Invalida**: QQQ perdiendo 720 impreso (capitán manda) o print doble fuera de 275/282.5.

## META — band-walk hacia el imán 600; prohibido fadear
- **Mapa**: POS (+59M), flip 580.2 = put wall 580 (mismo nivel: piso estructural). Call wall = abs wall **600 pin**, POC 600. Imanes 580/600.
- **Flujo**: semana +36.1M pero martes −18.9M (cobraron); 8/5 −1.0M, viernes −2.5M. **48.4% del net GEX muere el viernes** (ojo: net total pequeño, 35.7k). Charm −3.5M/−5.7M (8/5/8/7) = drift-DOWN doctrinal al decaer.
- **Ballenas** (lun): **637.5C y 647.5C 8/7 aperturas +5.5k/+5.0k** (apuestas upside a +7-9%), 560P 8/5 +7.2k (hedge), 465P ago21 +3.5k. **ΔOI martes**: aperturas call 600-625C en 8/5 y 8/7 (+1.2 a +2.0k c/u), 617.5C 8/5 +2.0k; hedge 570P/580P 8/5 abiertos; 560P 8/5 cerrado −1.2k.
- **Fuerza**: 593-596 pm (+0.17%), **band-walk en 3 TF** (%B 1m 1.42 / 15m 1.32) — veto compass: continuación, NO fadear.
- **Escenario**: el imán es 600. Band-walk + OI call fresco 600-625 → toca 600. Primer toque del muro/pin 600 = rebote/pin (~70% doctrina); solo retest-y-rechazo convierte 600 en soporte para 610/617.5/620 (donde está el ΔOI abierto). Sin ruptura, tarde de pin 595-600 con charm empujando abajo al decaer.
- **Invalida**: pérdida de 580 (flip + put wall juntos) impreso ×2 = cambia a NEG territory; y capitanes rojos anulan la extensión.

## GOOGL — caja 380-385 con piso comprado en 375
- **Mapa**: POS (+88M), flip 370.6. Put wall 375, abs wall **380 pin** (86), call wall 385, POC 380. Imanes 375/380/385.
- **Flujo**: semana +33.8M constante (lun +27.1 / mar +6.7); martes dirigido a 8/5 +6.6M. Charm 8/5 +3.9M y 8/7 +2.8M = **drift-UP** al decaer (el único de los 7 con charm a favor en ambos vencimientos cortos).
- **Ballenas** (lun): 400C ago21 +5.9k, aperturas weeklies masivas de calls (375C 8/7 +4.1k, 430C 8/7 +3.7k, 390C/400C 8/7 +2.7k c/u). **ΔOI martes**: **375P 8/5 +9.0k y 377.5P 8/5 +4.0k** — protección enorme justo bajo el spot PARA HOY (piso defendido); arriba 380C 8/7 +3.8k, 385C 8/7 +2.2k, 405C 8/5 +2.0k.
- **Fuerza**: 382.5 pm (**+0.84%, el mejor gap de los 7**), %B 1m 1.04 / 15m 0.90 (extremo alto — compass families).
- **Escenario**: sostiene sobre 380 → pelea 385; impreso sobre 385 ×2 → 390 y aire a 400 (OI abierto). El 375 es hoy el piso mejor comprado de los 7 (put wall + 13k puts 0DTE abiertos anoche). Pullback a 380 con rebote = entrada con la corriente del charm.
- **Invalida**: bajo 375 impreso ×2 → 370.6 (flip) y ahí se decide el régimen; capitanes rojos convierten 385 en techo del día.

## MU — el flujo más alcista de la flota ABRIENDO DEBAJO DE SU FLIP
- **Mapa**: score −2.6 ≈ **gamma CERO/NEG local**: flip 880.8 está ARRIBA del spot pm 875.2. Call wall 900, put wall 800 = abs wall **TRAMPILLA**, POC 800. Compass marca además muro put 850 trampilla ("no piso"). Imanes 800/900. **38.3% de la gamma bruta muere esta semana — la mayor de los 7** → el mapa se vacía el viernes.
- **Flujo**: **+124M semana, +104M solo el martes, +37.3M dirigidos al viernes** — la convicción alcista nº1 de la flota. Per-strike martes (UW archivado): **1000C 47k vol COMPRA ($74.5M prem)**, 885C COMPRA, 900C 59k vol $213M mixto, 800P/850P $42M/$29M mixto.
- **Ballenas**: lunes 635P 8/5 +15.0k (put profundo, hedge institucional; ambos lados medidos), 1190C ago21 +6.0k. **ΔOI martes**: dos caras — upside 950C 8/7 +1.7k, 1400C 8/7 +1.7k, 1100C 8/7 +1.3k, 1000C 8/5+8/7 +2.3k; y protección fresca **675P 8/5 +6.0k, 800P 8/5 +2.2k, 850P +1.3k, 790P +1.3k, 505P 8/14 +3.2k**. Compran el sueño y aseguran la caída a la vez = perfil de volatilidad, no de dirección limpia.
- **Fuerza**: 875.2 pm (**−2.18%**, contagio AMD), %B 1m 0.08 / 15m 0.22, r6 −0.22% — débil.
- **Escenario**: la batalla es el **flip 881**. (a) Reclaim 881 impreso ×2 con SMH recuperando → 900 imán y el flujo del viernes (+37.3M) empuja. (b) Rechazo en 881 = tierra sin piso: 850 es trampilla, después 800 trampilla — en gamma NEG los muros put no aguantan, aceleran. Regla 12: **SMH en NEG manda sobre el flujo bullish del nombre** — sin SMH verde, el +124M no se opera largo.
- **Invalida bull**: rechazo impreso en 881 o SMH bajo 570. **Invalida bear**: reclaim 881 + SMH sobre 588.

## AAPL — pin más fuerte de la flota en 310-312.5; el mapa GIRÓ overnight
- **Mapa**: **régimen pasó de NEG (flip 326 el lunes) a POS (flip 304.6 hoy)** — migración real del libro, declarada. Put wall 300, abs wall **310 pin con pin_score 120 (el más alto de la flota)**, call wall 315, POC 310. Imanes 300/310/315.
- **Flujo**: semana −12.8M (el único negativo de los 7) PERO martes +11.3M (giró); 8/5 +1.9M, viernes +2.6M. **Charm el más negativo: −12.6M (8/5) y −16.3M (8/7)** + net_delta semanal negativo = lastre vespertino.
- **Ballenas** (lun): aperturas call 305C/310C 8/5 +8.9k/+6.8k, 310C 8/7 +8.3k, escalera 320-327.5C 8/7 +4.2-4.5k; hedge 300P 8/5+8/7 +4.4k c/u. **ΔOI martes**: **312.5C y 315C 8/5 +6.2k/+6.1k**, 325C 8/5 +3.5k, 305C/307.5C 8/10 +3.0k c/u, 330C ago21 +2.7k; contrapeso 300P 8/5 +4.5k, 305P 8/7 +4.3k, 315P 8/7 +2.7k.
- **Fuerza**: 311.4 pm (+0.48%), %B 1m 0.27 / 15m 0.53 — neutral.
- **Escenario**: jaula 310-315 con el pin más pesado de la flota en 310-312.5. Sobre 315 impreso ×2 → 320 (escalera call abierta). Bajo 310 → 305 y el put wall 300. Con ese charm, si a las 14:00 no rompió 315, la deriva doctrinal es hacia 310 al cierre. Prohibido 0DTE comprado pegado al pin (regla 5 post-mortem).
- **Invalida**: print doble fuera de la caja o SPY perdiendo 770.

## NOK — sin mapa GEX propio (declarado); acumulación de calls cortas
- **Mapa**: **NOK no está en gex_snapshot** → sin flip/muros GEX. Compass: nivel 9.0-10.0 pin por OI, estado SIN LECTURA (feed con huecos — declarado). UW: net GEX total 4.56M (enorme para el nombre), 8/7 concentra 29.7% y ago21 24.7%; charm 8/7 −5.2M.
- **Flujo**: +1.9M semana (chico en dólares — contratos de centavos; el volumen es la señal aquí).
- **Ballenas**: lunes COMPRA clara 10C (51k vol), 9.5C, 12C; venta de 8.5P. ΔOI asentado: **8.5P ago21 +17.6k** (venta de puts = piso pagado), 10C 8/7 +6.1k, 9.5C 8/7 +5.5k, 10C 8/14 +8.2k. El "+53.7k del 15C ago21" es **artefacto de banda** (sin volumen que lo respalde) — descartado. **ΔOI martes**: **12C ago21 +10.3k**, escalera 8/7 abierta 10C +3.2k / 10.5C +3.4k / 11C +3.8k / 11.5C +3.1k; rotación 8/14→8/7 (10C 8/14 −7.1k, 9.5C 8/7 −2.7k). Alguien construye upside 10.5-12 para YA.
- **Fuerza**: 10.00 pm (+0.65%), %B 1m 0.00 (banda baja del premarket), r6 −0.20%.
- **Escenario**: pin en 10.00 (OI 10C masivo = imán). Sobre 10.25-10.30 con volumen → la escalera 10.5-11-11.5-12 recién abierta alimenta squeeze hacia 10.74 (techo del 7/21). Sin catalizador, jaula 9.90-10.10. Niveles de OI, no de GEX — menos fiables, dicho.
- **Invalida**: bajo 9.90 impreso el squeeze muere; spread de opciones NOK suele ser ancho → **optgate antes de cualquier boleto** (regla 4).

## INTC — sentado EXACTAMENTE en su put wall 98 con flujo bull detrás
- **Mapa**: POS (+21M), flip 90.2 (lejos abajo). **Put wall 98 = el spot premarket (98.6)**, call wall = abs wall = POC **110 pin**. Imanes 98/110. 30.7% de la gamma muere esta semana; charm −6.9M (8/5) y −5.2M (8/7).
- **Flujo**: martes **+30.1M** y viernes +11.2M — bulls con horizonte (tras lunes −23.5M: giro completo).
- **Ballenas**: lunes aperturas 104C 8/5 +11.1k, 100C 8/5 +6.9k, 95C +6.0k, 105C +5.4k (los "150C/160C ago21 +22k/+11k" = artefacto de banda, descartados). **ΔOI martes — el más activo de los 7**: **108C 8/7 +19.1k**, 99C 8/5 +14.6k, 110C 8/5 +13.3k, 110C 8/7 +9.0k, 106C/104C 8/7 +5.4k c/u, 125C 8/14 +6.9k; y protección pegada al precio **98P 8/5 +10.1k, 97P 8/7 +9.7k, 88P 8/5 +5.7k**; cierre 104C 8/5 −5.5k (roll a 8/7). Apuesta masiva a 100-110 esta semana con el suelo asegurado en 97-98.
- **Fuerza**: 98.6 pm (**−2.27%**), %B 1m 0.22 / 15m 0.58. Compass: 1 print ya en 98.
- **Escenario**: el 98 decide. (a) Aguanta 98 (put wall + 10k puts frescos defendiendo) → rebote a 100 y la escalera 104-108-110 tira hacia arriba; imán semanal 110 si el mercado ayuda. (b) Pierde 98 impreso ×2 → 95-97 (97P abierto) y vacío técnico — el flip está en 90. Primer toque de 98 debería rebotar (doctrina muros).
- **Invalida bull**: 98 impreso roto con SMH rojo. **Invalida bear**: print doble sobre 100.

---

## FICHA DE APERTURA 09:30 — niveles de ayer, gap de hoy

Niveles = cierre del libro 8/4. Gap = tick 07:05 (delayed 15 min) vs cierre RTH 8/4. **Nada se opera sin print de 2 velas cerradas en el nivel** (print-o-nada). 09:30-09:45 no se toca: subasta.

| sym | gap pm | nivel decisivo | escenario A (sobre el nivel) | escenario B (bajo el nivel) | invalida el plan |
|---|---:|---|---|---|---|
| **SPY** | +0.44% | **775** (call wall = POC = pin fortaleza, 8 prints) | 775 impreso ×2 → 780 | pierde **770** (flip 771 + put wall juntos) → día defensivo | print doble fuera de 770/775 |
| **QQQ** | −0.07% | **720** (put wall) | aguanta 720 → deriva 725-730, techo 735 | pierde 720 → trampilla, aire a 712 (flip) | — |
| **SMH** | −0.75% | **588** (flip) / **570** abajo | recupera 588 → desbloquea largos de semis | bajo 570 acelera (gamma NEG); 530 es trampilla, no piso | mientras <588, todo largo de semis va a media ficha |
| **AMZN** | +0.80% | **280** (pin fortaleza, ya pegado, 3 prints) | 282,5 impreso ×2 → 285-287,5 | bajo 275 → 270 y para | QQQ perdiendo 720 |
| **META** | +0.62% | **600** (pin/imán, band-walk 3 TF: NO fadear) | primer toque de 600 rebota (~70%); solo retest-y-rechazo abre 610-620 | pierde **580** (flip+put wall) ×2 → cambia el régimen | capitanes rojos anulan la extensión |
| **GOOGL** | +0.90% | **380** (pin) con piso comprado en **375** | pullback a 380 con rebote = la entrada del día (charm drift-UP); sobre 385 ×2 → 390-400 | bajo 375 ×2 → 370,8 (flip) decide | capitanes rojos hacen de 385 el techo |
| **MU** | −1.78% | **879** (flip, precio EXACTAMENTE encima) | reclaim 879 ×2 **+ SMH sobre 588** → 900 (imán, +37,3M de flujo al viernes) | rechazo en 879 → sin piso: 850 y 800 son trampillas, aceleran | regla 12: sin SMH verde no se opera el +124M largo |
| **AAPL** | +0.05% | **310-312,5** (pin más pesado de la flota, precio pegado) | 315 impreso ×2 → 320 (escalera call abierta) | bajo 310 → 305, luego put wall 300 | charm −12,6M/−16,3M: si a las 14:00 no rompió 315, deriva al pin |
| **NOK** | +0.60% | **10,00** (imán de OI; sin mapa GEX) | sobre 10,25-10,30 con volumen → escalera 10,5-11-11,5-12 recién abierta, objetivo 10,74 | bajo 9,90 el squeeze muere | spread ancho: optgate obligatorio |
| **INTC** | −2.43% | **98** (put wall, precio encima, 1 print) | aguanta 98 (10k puts frescos defendiendo) → 100, escalera 104-108-110 | pierde 98 ×2 → 95-97 y vacío hasta el flip 90,6 | SMH rojo convierte A en trampa |

## SÍNTESIS DE FLOTA — 2026-08-05

1. **El conflicto del día**: capitanes de mercado en gamma POS con pins fortaleza (SPY 775, QQQ 735) = mercado enjaulado; pero el **capitán de semis SMH está en gamma NEGATIVA bajo su flip (588) con AMD −10.6%**. Dos mercados en uno: mega-caps pinneados, semis en caja de whipsaw 530-600.
2. **Jerarquía operable**: mientras SMH < 588, ninguna señal larga de la tropa semi (MU, INTC vía asociación) se opera a tamaño completo — regla 12. MU es el caso extremo: +124M de flujo alcista pero abriendo bajo su flip 881 con AMD en contra.
3. **Pines del día** (fortress, prohibido 0DTE comprado pegado): AMZN 280 (3 prints ya), AAPL 310-312.5 (pin 120), SPY 775 (8 prints), META 600 como imán-techo. Día de vencimiento 8/5 con mucha gamma muriendo (AMZN 31%, AAPL 35%, MU 38% de la semana) → los pines pesan HOY y el mapa se afloja mañana-viernes.
4. **Mejor estructura larga de los 7**: **GOOGL** — charm drift-UP en ambos vencimientos, piso comprado anoche (375P +13k), gap +0.84%, escalera call abierta a 385-405. Entrada doctrinal: pullback a 380 impreso con rebote.
5. **Mejor asimetría de evento**: **INTC en 98** — primer toque de put wall con +41M de flujo bull en dos días y 19k calls 108 abiertas anoche. Print o nada en 98.
6. **Peligros**: (a) SNDK/WDC reportan HOY AMC — nada de premium comprado en memoria aguantando el print (SNDK viernes ya cargó −16.3M el martes); (b) QQQ lleva −48.5M de puts al viernes + NFP = la protección ya está pagada, un dato benigno el viernes la convierte en combustible alcista; (c) lockup SpaceX mañana con SPCX en gamma NEG (flip 134 vs spot 108, trampilla 100) y sin barras frescas — sin lectura intradía, solo mapa.
7. **Honestidad**: SMH y NOK sin lectura compass (huecos de feed); NOK sin mapa GEX; flujo fleet-wide del martes cortado a las 12:36; Polygon no da aggs del mismo día en este plan (premarket = puente de proveedores, fresco a 06:42-06:46 ET); ΔOI martes limitado a la banda archivada del 8/4 (±15% aprox) — movimientos en LEAPS/strikes lejanos no medidos.
