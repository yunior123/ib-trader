# SEMANA → VIERNES 2026-08-07 — C/P altos, net premium, ballenas (martes 2026-08-04, 10:35-10:45 ET)

**Encargo (Yunior)**: "search high call/put ratio for this week till friday, calculate net premium
from today tuesday 10:35 till friday, search whales, darkpool, sentiment."

**Aclaración obligada sobre "net premium from 10:35 till friday"**: el futuro no se calcula. Lo que
SÍ se midió y se entrega: **(a)** el net premium ACUMULADO de HOY desde las 10:35 ET en adelante
(serie por minuto de UW `net-prem-ticks`, recortada a `tape_time ≥ 14:35 UTC`; a la hora del corte
son solo **8-9 minutos** de serie — crece durante el día), y **(b)** el premium YA APILADO hoy en
contratos que **expiran ≤ 2026-08-07** (posicionamiento hacia viernes: `flow-per-expiry` +
ballenas `flow-alerts` filtradas por expiry). `signed = net_call − net_put` (vender put es
alcista: el put RESTA).

**Fuentes y latencia**: screener UW (EOD-live, fecha 2026-08-04), net-prem-ticks (1 min),
flow-alerts/flow-per-expiry/flow-per-strike (evento/día). Spreads: **CBOE delayed** (sin IBKR esta
semana — orden 2026-08-02; el gate definitivo lo daría NBBO IBKR). Dark pool y headlines:
**SOLO DESCRIPTIVO** (killlist #3: dark pool no es señal ni entra en el ranking).
**CERO probabilidades inventadas**; percentiles descriptivos permitidos. Señal-solamente.

---

## 1. Universo

Screener con liquidez `call_volume + put_volume ≥ 20.000` contratos hoy → **109 tickers**.
C/P = 1/put_call_ratio (volumen). Detalle profundo: top-15 C/P alto + top-5 C/P bajo.

## 2. TOP ALCISTA (C/P alto) — el dato decide, no el ratio

| # | Ticker | C/P | net ≥10:35 ET | net día completo | % prem HOY → ≤vie | Ballenas ≤vie (lado) | Strike dominante (% del día) | Spread ATM 8/7 (CBOE delayed) | ¿Cabe $200? |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **NOK** | 9,4 | **+71.244 (p68 de 91 días, misma ventana)** | −438.963 | 11% | 0 ≥$10k | 10 C (32%, $2,1M calls) | 10C 0,25/0,26 = **3,9% ✅** | **SÍ: mid $26, OI 14.319** |
| 2 | **ONDS** | 8,0 | **+88.781** | +392.957 | 16% | 10C 8/7 ask $14,4k BULL | 10 (23%) | 8.5C 0,49/0,52 = **5,9% ⚠️** (>5% al print CBOE) | SÍ: mid $50, OI 16.043 |
| 3 | **GRAB** | 17,2 | +8.731 | +169.313 | **32%** | 2× 4C 8/7 ask $42,9k BULL | 4 (33%) | 4C 0,03/0,04 = **28,6% ❌ VETADAS** | (contrato $4 — irrelevante, vetado) → acciones |
| 4 | **BBAI** | 20,2 | +34.373 | +175.493 | 18% | 0 | 3 (38%) | 3C 0,07/0,09 = **25% ❌ VETADAS** | → acciones |
| 5 | **RGTI** | 8,0 | +13.985 | +489.985 | 23% | 16C 8/7 ask $58,8k BULL | 27 (16%) | 17C 0,84/0,90 = **6,9% ⚠️** | SÍ: mid $87 — **pero earnings 2026-08-06** |

- **NOK** (flota, Corea-indirecta no): único con spread limpio ≤5% Y premium ≤$200. Ojo honesto:
  el día completo va **−439k** (venta de calls temprano); el tramo ≥10:35 es el positivo. p68 =
  descriptivo, no probabilidad.
- **ONDS/RGTI**: spread 5,9%/6,9% al print CBOE delayed — regla 4 dice <5%: **vetadas a este
  print**; re-medir con print vivo antes de pagar. RGTI reporta el 8/6: premium comprado a través
  de earnings = prohibido aguantar el print.
- **GRAB/BBAI**: el flujo acompaña (GRAB 32% del premium de hoy apunta ≤ viernes) pero sus
  opciones son ilíquidas → vehículo = **acciones**, no opciones.

## 3. TOP BAJISTA (contraste)

| Ticker | C/P | net ≥10:35 | net día | Qué dice el dato |
|---|---|---|---|---|
| **VIXW** | 0,43* | **−4.320.443** | −4.208.851 | Venta masiva de calls de VIX **semanales** (73% del premium de hoy expira ≤8/7). Apuesta a CALMA — coherente con la marea alcista de mercado (§5). *No operable aquí.* |
| **HUT** | 8,3 (¡alto!) | −255.667 | **−1.566.779** | El C/P engaña: el premium firmado VENDE calls todo el día. Ballenas mixtas (112C ask $188k vs bid-side y 99P). Spread 46% + mid $572 → no cabe. **Contraste de libro: ratio alcista, dólares bajistas.** |
| **CVX** | 0,49 | +150.712 | −38.747 | Ballena clara ≤vie: **190P 8/7 ask-side $204.750 BEAR** (13:32 UTC). Spread ATM 14-22% y mid ~$235 → no cabe en $200. |
| **WBD** | **0,05** | +5.152 | **+514.134** | El C/P más bajo del universo, pero el signed del día es POSITIVO: los puts (25P, $545k) se están **vendiendo** = alcista en dólares. Earnings 8/6. El ratio solo, sin el lado, miente. |
| **HPE** | 6,3 (alto) | **−256.211** | −70.228 | Igual que HUT: C/P alto, flujo reciente vende. Descartado del lado alcista con este motivo. |

## 4. Ballenas hacia viernes que pesan (todas con lado medido ask/bid)

1. **CVX 190P exp 8/7 — $204.750 ask-side (BEAR)**, vol 654 vs OI 1.833.
2. **HUT 112C exp 8/7 — $188.140 ask-side (BULL)**, vol 488 vs OI 51 (vol≫OI: probable apertura) — pero el net del día la contradice.
3. **RGTI 16C exp 8/7 — $58.770 ask-side (BULL)**, OI 4.600.
4. **GRAB 4C exp 8/7 — $42.895 ask-side (BULL)** en 2 prints.
5. **ARKK**: mixto ≤vie (bull $72k ask en 75.5C/73C/80C vs bear $42,7k bid en 72.5C).
6. **CIFR**: ballenas ≤vie VENDEN calls (21C/21.5C bid-side $75k) pese a ≥10:35 +138k → mixto, earnings HOY.
Nada en el top-20 supera $250k hacia ≤8/7 salvo CVX — semana de ballenas chicas en estos nombres.

## 5. Contexto ROTULADO (no señal, no ranking)

- **Market tide (UW, 5 min, acumulado)**: a las 10:40 ET net_call **+$361,9M**, net_put +$38,2M →
  signed **+$323,7M** = mañana compradora de calls a nivel mercado.
- **Dark pool (descriptivo, killlist #3 — jamás gatillo)**: últimos 20 prints — NOK $5,8M (mayor:
  $1,39M a 9,825 @14:39 UTC), POET $6,0M (print $1,55M a 8,46), OPEN $5,3M (bloque $1,03M a
  4,02), GRAB $2,9M, BBAI $0,78M.
- **Headlines (UW news, búsqueda por texto = RUIDOSA para tickers cortos; sin score compuesto)**:
  POET: nombramientos al board 8/3 (neutral). GRAB: expansión EV Vietnam 7/10 (neutral). NOK/OPEN:
  resultados de búsqueda contaminados (krona noruega / "open" genérico) — **sin dato limpio**.
  Macro de la mañana: JOLTS junio 7.359k vs 7.454k est.

## 6. Descartados del lado alcista, con motivo

- **GPK** (C/P 1.660): ratio fabricado por 28k calls vs 17 puts, pero bear$ $1,23M > bull$ $0,19M,
  día −$1,04M, 81% en 12.5C, earnings HOY → perfil de overwriting, no tesis alcista.
- **MTUM**: un solo bloque 305C = 55% del día; semana 0%; bear$ > bull$.
- **EEM**: signed ≥10:35 +766k (venta de puts) y bloque 68C de $19,4M (84% del día) — pero **0%
  del premium expira ≤ viernes**: posicionamiento a plazo, no de esta semana. Spread 35%.
- **HYG / PCG**: ≤1% del premium hacia ≤vie → fuera del horizonte.
- **OPEN**: ≥10:35 −23.917 y earnings HOY.
- **POET**: ≥10:35 −10.771 y día −132k: el flujo no acompaña al ratio.
- **HUT, HPE**: movidos al lado bajista (flujo firmado vende; ver §3).
- **CIFR**: mixto + earnings HOY.
- **VIX/VIXW/XSP/SPXW**: índices/raíces — no candidatos de boleto aquí (XSP=SPX/10, SPXW no es símbolo).
- Resto del top-40 C/P (NFLX, ORCL, TSM, SNAP, AAPL, PLTR…): fuera del corte top-15 de detalle;
  ranking completo en `scratchpad` del agente si se quiere segunda pasada.

## 7. Gate de liquidez (regla 4) — resumen

Con CBOE **delayed** (sin IBKR esta semana): **solo NOK pasa ≤5% y cabe en $200** (10C 8/7,
3,9%, mid $26). ONDS (5,9%) y RGTI (6,9%) quedan a un print vivo de pasar. GRAB, BBAI, EEM, CIFR,
HUT, WBD, CVX: **opciones vetadas** por spread y/o premium >$200 → acciones o nada.

## 8. Cuota UW

125 requests gastadas por este agente (screener 6, detalle 20×4, contexto 17, refresco 20+1,
sondas 2). Contador del token al cierre: 12.457/30.000.

---
*Generado 2026-08-04 ~10:45 ET por agente semana. Señal-solamente. No es consejo financiero.*
