---
name: flow-captains
description: Jerarquía de capitanes de flujo de opciones (REGLA 12) + interpretación de spikes de flow_pulse. Usar cuando se hable de "flujo de opciones", "capitanes", "spike de puts/calls", "quién manda SPY o el nombre", conflicto capitán-vs-tropa, MANADA, o cualquier señal de flow_pulse/ballenas de la flota. SEÑAL-SOLAMENTE — jamás órdenes al broker.
---

# flow-captains — quién manda cuando habla el flujo (doctrina 2026-07-22)

Motor: `scripts/flow_pulse.cpp` (C++23). Spike = ritmo ≥3x su EMA propia (α=0.40) + ≥2000
contratos + dominancia 2x del lado + filtros anti-artefacto (relleno de feed, bilateral, ratio>50x = mudo).
Cooldown 600s por sym+tipo. Táctica madre: espada-ballena (CLAUDE.md regla 11) — el flujo extremo
marca EXTREMOS locales y se opera la REVERSIÓN chica y segura.

## 1. La jerarquía y sus dos leyes (REGLA 12, ~/CLAUDE.md)

**Capitanes**: SPY/QQQ = capitanes del MERCADO (mandan sobre toda la flota).
SMH = capitán de SEMIS/memoria — tropa: MU SKHY DRAM SNDK WDC STX LRCX NVDA AMD TSM.
Orden de mando: **mercado (SPY/QQQ) > sector (SMH) > nombre**.

- **Ley (a) — Puts-flow masivo del capitán = rebote del grupo SIEMPRE.**
  Evidencia: viernes 2026-07-18, cada SMH puts-flow → rebound de semis;
  2026-07-22 SPY puts 14:21 → piso del mercado, NVDA rebotó +0.35%.
- **Ley (b) — Conflicto capitán-vs-nombre: el capitán PREVALECE; la señal del nombre queda
  prácticamente ANULADA.** Evidencia 2026-07-22: NVDA calls-flow + SPY puts-flow → la de NVDA
  sin efecto; MU calls + SMH puts → manda SMH.
- En código: señal de nombre con capitán opuesto vigente = **banner sin voz; la voz es del capitán**.

## 2. Señal de flow_pulse → acción

| Señal | Prob. medida | Acción (señal-only, scalp chico y seguro) |
|---|---|---|
| 🐋 SPIKE PUTS | rebote al ALZA **88%** (n=8) | Call/long EN el fondo impreso (2 lecturas); vender en el rebote corto, no pedir más |
| 🐋 SPIKE CALLS | rebote a la BAJA **60%** (n=10) | Fade con put EN el pico; edge más débil → stop apretado, tamaño mínimo |
| 🚫 VETO band-walk | — | BB 1m+5m reventadas A FAVOR del flujo = continuación, no extremo. Señal muda, no operar la reversión |
| 🧱 EN EL MURO | rebote REFORZADO | Spot a ≤0.4% de muro top-3 OI de su lado → subir convicción (muro = campo de fuerza, regla 5) |
| 🐺 MANADA | extremo de MERCADO (DANGER) | ≥3 tickers misma dirección en 12 min → tratar como señal de capitán aunque SPY/QQQ no haya cantado; cooldown 30 min |

Gates SIEMPRE antes de sugerir vehículo: BB 1m+15m (regla 1), print o nada (regla 2),
`optgate.py` spread ≤5% (regla 4), presupuesto ≤$200, ventanas horarias (regla 7).

## 3. Matriz de conflictos capitán × tropa (4 cuadrantes)

| | **Tropa: SPIKE PUTS** | **Tropa: SPIKE CALLS** |
|---|---|---|
| **Capitán: SPIKE PUTS** | ✅ **ALINEADOS ALCISTA** — doble extremo vendedor → rebote del grupo, máxima convicción (88% + refuerzo). Si son ≥3 = MANADA. Vehículo: el más líquido de la tesis (regla 4) | ⚔️ **CAPITÁN MANDA** — piso del grupo viene; el calls-flow del nombre queda ANULADO (NVDA calls + SPY puts, 7/22). NO fade bajista del nombre; esperar el rebote del capitán |
| **Capitán: SPIKE CALLS** | ⚔️ **CAPITÁN MANDA** — techo local del grupo probable (60%); el rebote que sugiere el puts-flow del nombre queda anulado. No comprar el rebote del nombre contra techo del capitán | ⚠️ **ALINEADOS BAJISTA** — clímax comprador de grupo → fade a la baja (60%), pero es el cuadrante más traicionero: día de catalizador del LÍDER puede ser band-walk/continuación (regla 11). Verificar fuerza/z antes; stop más apretado de todos |

Regla práctica: nunca cantar una señal de tropa sin mirar primero si su capitán (SMH para semis,
SPY/QQQ para todo) tiene spike vigente dentro de la ventana de cooldown.

## 4. Lo que el research público confirma o añade (destilado, 2026-07-22)

1. **Sweeps vs blocks** — sweep (ISO multi-exchange) = urgencia direccional; block negociado = a
   menudo hedge institucional, menos direccional. La MAYORÍA de sweeps son inventario de market
   makers, no convicción: filtrar por volumen ≥5-10x OI y premium grande antes de creer.
   Refuerza nuestros filtros de ≥2000 contratos + dominancia 2x.
   → https://www.tradealgo.com/trading-guides/options/understanding-block-trades-and-sweep-orders-what-they-signal-about-smart-money
2. **P/C ratio contrarian solo en EXTREMOS relativos** — el extremo se define contra el propio
   histórico (1-2 desviaciones vs 20-50 días), nunca con número fijo. Exactamente lo que hace
   flow_pulse con su EMA propia por ticker (≥3x). Equity-only P/C >0.80-0.85 = miedo retail
   (alcista contrarian); <0.55-0.60 = codicia (bajista).
   → https://chartschool.stockcharts.com/table-of-contents/market-indicators/put-call-ratio
3. **Puts de ÍNDICE corren estructuralmente altos** (hedging institucional permanente) — juzgar el
   puts-flow de SPY/QQQ contra SU baseline, no contra 1.0. El spike EXTREMO de hedging marca
   capitulación, no inicio de caída → coherente con "puts del capitán = piso" (ley a).
   → https://apexvol.com/learn/put-call-ratio
4. **Amplitud del sector valida al capitán** — ETF sectorial subiendo con pocos nombres
   participando = movimiento frágil que precede reversión; participación amplia = institucional y
   durable. Complementa MANADA: capitán + tropa confirmando = señal de grupo real; capitán solo
   con tropa divergente = más frágil, tamaño menor.
   → https://traderlion.com/technical-analysis/strength-stock-industry-group/

Asimetría honesta que el research respalda: el miedo (puts) es mejor señal contrarian que la
codicia (calls) — cuadra con nuestro 88% vs 60%.

## 5. Límites honestos

- **n chico**: 88% viene de n=8, 60% de n=10 — intervalos Wilson anchos. Son direccionales, no ley.
- **Re-calibración obligatoria ~2026-08-22** con el histórico real (`calibration_ledger.py`,
  buckets setup×régimen, jamás hardcodear).
- **Excepción band-walk / día de catalizador del líder**: la ballena call puede ser continuación,
  no techo (regla 11) — verificar fuerza/z (momentum_calc) antes de fade.
- Conflicto SPY-vs-SMH entre sí: doctrina dice mercado > sector, pero SIN evidencia medida aún —
  tratar con prob. explícita baja y anotar el caso en el ledger cuando ocurra.
- Todo esto es SEÑAL-SOLAMENTE (ley 2026-07-16): banners, sirenas y voz — jamás ejecución.
