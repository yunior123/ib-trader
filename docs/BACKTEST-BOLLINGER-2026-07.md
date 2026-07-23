# BACKTEST BOLLINGER 30d × FLOTA — 2026-07-22

## Metodologia (honesta, sin maquillaje)
- **Datos**: barras 1m RTH via yfinance, cache `data/backtest/bars30d_<sym>.csv`.
  Ventana REAL obtenida: **2026-06-29 → 2026-07-22 = 17 sesiones** (yfinance no
  entrega mas profundidad 1m; se pidieron 30 dias, esto es lo que hay). SKHY:
  solo **8 sesiones** (2026-07-13→22, ETF nuevo). Missing: ninguno.
- **Replica exacta** de `scripts/bollinger_alarm.py`: BB(20,2) sobre closes[-21:-1],
  ventanas 140 barras (1m/5m) y 460 (15m, bucket parcial incluido), cooldown 30min
  por simbolo+lado, expiry pierce 600s (1m)/2700s (15m), RTH 9:35-15:55, estado
  reseteado por dia. Diferencia conocida: el vigia escanea cada 30s (pierce
  intra-barra); aqui una barra que revienta y cierra dentro cuenta como
  pierce+re-entrada en la misma barra.
- **Forward = 30 barras 1m** (señales con <30 barras restantes = truncadas, NO cuentan).
- **Metricas por tesis**:
  - `elastic` / `re15` (tesis FADE): p_mid30 = P(toca la media BB en 30min);
    p_half = P(avanza ≥50% del gap a la media). Media 1m para elastic, media 15m para re15.
  - `bandwalk` (tesis CONTINUACION): p_mid30 = P(NO toca la media 1m en 30min);
    p_half = P(avanza ≥50% del gap-a-media A FAVOR del walk).
  - MFE/MAE medianos a 15/30min en la direccion de la tesis (% del spot).
- **Wilson lower bound** (95%) reportado para n chico. `enabled` en
  `data/bollinger_probs.json` = p_mid30 ≥ 0.55 **y** n ≥ 8 en la celda BASE.
- **Grid** (todas las celdas, cero cherry-pick): σ ∈ {2.0, 2.5} × cooldown ∈ {30m, 15m}.
  Produccion = σ2.0/cd30.

## Tabla principal — celda BASE (σ2.0, cooldown 30m)

p_mid30 / p_half (n). MFE/MAE medianos 30min en % del spot.

| Ticker | elastic | wLB | mfe/mae30 | bandwalk | wLB | mfe/mae30 | re15 | wLB | mfe/mae30 |
|---|---|---|---|---|---|---|---|---|---|
| QQQ | 70%/83% (n=190) | 0.63 | +0.14/-0.13 | 52%/76% (n=25) | 0.34 | +0.13/-0.12 | 0%/25% (n=4) | 0.00 | +0.18/-0.14 |
| SPY | 72%/85% (n=213) | 0.66 | +0.08/-0.06 | 47%/82% (n=17) | 0.26 | +0.07/-0.08 | 0%/38% (n=8) | 0.00 | +0.10/-0.10 |
| NVDA | 69%/86% (n=196) | 0.63 | +0.25/-0.27 | 55%/70% (n=20) | 0.34 | +0.35/-0.29 | 0%/33% (n=9) | 0.00 | +0.39/-0.18 |
| TSLA | 70%/86% (n=200) | 0.64 | +0.27/-0.29 | 53%/47% (n=15) | 0.30 | +0.15/-0.38 | 0%/22% (n=9) | 0.00 | +0.17/-0.37 |
| MU | 65%/79% (n=202) | 0.58 | +0.53/-0.56 | 44%/62% (n=16) | 0.23 | +0.50/-0.75 | 0%/33% (n=3) | 0.00 | +0.38/-0.49 |
| SMH | 66%/81% (n=188) | 0.59 | +0.29/-0.27 | 44%/75% (n=16) | 0.23 | +0.41/-0.35 | 0%/0% (n=4) | 0.00 | +0.11/-0.37 |
| AMD | 69%/88% (n=195) | 0.62 | +0.47/-0.47 | 38%/62% (n=16) | 0.18 | +0.38/-0.78 | 40%/40% (n=5) | 0.12 | +0.49/-0.26 |
| AAPL | 65%/82% (n=196) | 0.58 | +0.16/-0.20 | 20%/60% (n=15) | 0.07 | +0.12/-0.26 | 20%/40% (n=5) | 0.04 | +0.04/-0.32 |
| MSFT | 70%/86% (n=203) | 0.63 | +0.19/-0.22 | 50%/67% (n=12) | 0.25 | +0.13/-0.18 | 0%/50% (n=2) | 0.00 | +0.16/-0.33 |
| META | 74%/86% (n=212) | 0.67 | +0.27/-0.23 | 56%/50% (n=16) | 0.33 | +0.19/-0.25 | 38%/50% (n=8) | 0.14 | +0.46/-0.24 |
| AMZN | 68%/84% (n=193) | 0.61 | +0.22/-0.23 | 38%/62% (n=16) | 0.18 | +0.19/-0.24 | 14%/43% (n=7) | 0.03 | +0.29/-0.17 |
| GOOGL | 68%/81% (n=197) | 0.61 | +0.20/-0.22 | 63%/79% (n=19) | 0.41 | +0.20/-0.13 | 0%/14% (n=7) | 0.00 | +0.15/-0.23 |
| INTC | 68%/82% (n=211) | 0.62 | +0.47/-0.50 | 31%/54% (n=13) | 0.13 | +0.31/-0.75 | 0%/80% (n=5) | -0.00 | +0.69/-0.30 |
| TSM | 68%/81% (n=203) | 0.61 | +0.29/-0.29 | 44%/67% (n=18) | 0.25 | +0.25/-0.27 | 0%/33% (n=6) | 0.00 | +0.18/-0.37 |
| ASML | 68%/87% (n=189) | 0.61 | +0.32/-0.34 | 43%/76% (n=21) | 0.24 | +0.33/-0.34 | 50%/50% (n=2) | 0.10 | +0.45/-0.40 |
| TXN | 67%/83% (n=187) | 0.60 | +0.32/-0.31 | 47%/67% (n=15) | 0.25 | +0.27/-0.42 | 25%/38% (n=8) | 0.07 | +0.34/-0.31 |
| QCOM | 69%/89% (n=182) | 0.62 | +0.44/-0.39 | 53%/80% (n=15) | 0.30 | +0.31/-0.23 | 0%/0% (n=2) | 0.00 | +0.31/-0.77 |
| AVGO | 68%/86% (n=197) | 0.62 | +0.31/-0.28 | 46%/73% (n=22) | 0.27 | +0.25/-0.26 | 0%/25% (n=4) | 0.00 | +0.18/-0.24 |
| NFLX | 77%/87% (n=202) | 0.71 | +0.25/-0.22 | 56%/72% (n=18) | 0.34 | +0.24/-0.19 | 0%/14% (n=7) | 0.00 | +0.19/-0.15 |
| NOK | 72%/87% (n=205) | 0.66 | +0.35/-0.30 | 50%/88% (n=16) | 0.28 | +0.40/-0.25 | 0%/50% (n=4) | 0.00 | +0.37/-0.26 |
| GLD | 64%/80% (n=194) | 0.57 | +0.09/-0.11 | 40%/73% (n=15) | 0.20 | +0.11/-0.11 | 0%/22% (n=9) | 0.00 | +0.08/-0.05 |
| XLK | 69%/85% (n=183) | 0.62 | +0.20/-0.15 | 52%/95% (n=21) | 0.32 | +0.25/-0.16 | 0%/50% (n=4) | 0.00 | +0.23/-0.12 |
| EWY | 63%/80% (n=185) | 0.56 | +0.29/-0.36 | 41%/76% (n=17) | 0.22 | +0.31/-0.29 | 0%/100% (n=3) | 0.00 | +0.40/-0.08 |
| DRAM | 61%/79% (n=186) | 0.54 | +0.40/-0.56 | 24%/71% (n=21) | 0.11 | +0.36/-0.56 | 0%/25% (n=4) | 0.00 | +0.30/-0.54 |
| SPCX | 69%/84% (n=205) | 0.63 | +0.51/-0.48 | 71%/93% (n=14) | 0.45 | +0.69/-0.26 | 7%/7% (n=14) | 0.01 | +0.24/-0.54 |
| SKHY | 69%/86% (n=86) | 0.58 | +0.75/-1.03 | 30%/80% (n=10) | 0.11 | +0.79/-1.17 | 0%/33% (n=3) | 0.00 | +1.11/-0.71 |
| LRCX | 68%/83% (n=193) | 0.61 | +0.44/-0.45 | 25%/83% (n=12) | 0.09 | +0.73/-0.77 | 0%/0% (n=1) | 0.00 | +0.07/-0.58 |
| SNDK | 73%/86% (n=194) | 0.66 | +0.77/-0.86 | 46%/73% (n=22) | 0.27 | +0.54/-0.99 | 14%/43% (n=7) | 0.03 | +1.31/-0.28 |
| WDC | 72%/84% (n=204) | 0.65 | +0.49/-0.53 | 46%/54% (n=13) | 0.23 | +0.48/-0.42 | 0%/33% (n=3) | 0.00 | +0.35/-0.51 |
| STX | 72%/82% (n=209) | 0.66 | +0.53/-0.51 | 50%/93% (n=14) | 0.27 | +0.61/-0.39 | 33%/67% (n=3) | 0.06 | +0.60/-0.44 |

## Agregado flota (celda BASE)

| tipo | señales (n) | truncadas | p_mid30 pooled | p_half pooled |
|---|---|---|---|---|
| elastic | 5800 | 465 | 68.9% | 83.9% |
| bandwalk | 500 | 79 | 45.6% | 72.4% |
| re15 | 160 | 121 | 8.1% | 33.1% |

## Grid completo por tipo — ¿mejora 2.5σ? ¿cooldown 15m?

p_mid30 pooled de la flota (n total) por configuracion — TODAS las celdas:

| tipo | σ2.0/cd30 (BASE) | σ2.0/cd15 | σ2.5/cd30 | σ2.5/cd15 |
|---|---|---|---|---|
| elastic | 68.9% (n=5800) | 69.0% (n=7835) | 63.3% (n=4729) | 63.3% (n=5891) |
| bandwalk | 45.6% (n=500) | 47.4% (n=856) | 56.1% (n=173) | 56.6% (n=286) |
| re15 | 8.1% (n=160) | 8.1% (n=209) | 8.1% (n=74) | 6.7% (n=90) |

### σ2.5 por ticker (cd30) vs BASE — elastic p_mid30

| Ticker | σ2.0 | σ2.5 |
|---|---|---|
| QQQ | 70%/83% (n=190) | 62%/77% (n=156) |
| SPY | 72%/85% (n=213) | 66%/80% (n=177) |
| NVDA | 69%/86% (n=196) | 61%/80% (n=163) |
| TSLA | 70%/86% (n=200) | 66%/80% (n=177) |
| MU | 65%/79% (n=202) | 62%/79% (n=155) |
| SMH | 66%/81% (n=188) | 62%/79% (n=149) |
| AMD | 69%/88% (n=195) | 63%/83% (n=170) |
| AAPL | 65%/82% (n=196) | 61%/80% (n=168) |
| MSFT | 70%/86% (n=203) | 65%/81% (n=166) |
| META | 74%/86% (n=212) | 69%/86% (n=170) |
| AMZN | 68%/84% (n=193) | 62%/83% (n=162) |
| GOOGL | 68%/81% (n=197) | 67%/82% (n=163) |
| INTC | 68%/82% (n=211) | 64%/81% (n=175) |
| TSM | 68%/81% (n=203) | 58%/78% (n=153) |
| ASML | 68%/87% (n=189) | 69%/87% (n=158) |
| TXN | 67%/83% (n=187) | 62%/82% (n=130) |
| QCOM | 69%/89% (n=182) | 64%/82% (n=157) |
| AVGO | 68%/86% (n=197) | 64%/84% (n=153) |
| NFLX | 77%/87% (n=202) | 75%/86% (n=171) |
| NOK | 72%/87% (n=205) | 68%/88% (n=169) |
| GLD | 64%/80% (n=194) | 59%/81% (n=157) |
| XLK | 69%/85% (n=183) | 59%/78% (n=130) |
| EWY | 63%/80% (n=185) | 58%/77% (n=163) |
| DRAM | 61%/79% (n=186) | 53%/74% (n=139) |
| SPCX | 69%/84% (n=205) | 62%/80% (n=168) |
| SKHY | 69%/86% (n=86) | 61%/82% (n=72) |
| LRCX | 68%/83% (n=193) | 62%/78% (n=160) |
| SNDK | 73%/86% (n=194) | 56%/79% (n=155) |
| WDC | 72%/84% (n=204) | 69%/87% (n=172) |
| STX | 72%/82% (n=209) | 63%/78% (n=171) |

## Veredicto por ticker (celda BASE; enabled = p_mid30≥55% y n≥8)

| Ticker | elastic | bandwalk | re15 |
|---|---|---|---|
| QQQ | ✅ CANTA 70% (n=190) | 🔇 MUTED 52% (n=25) | 🔇 MUTED 0% (n=4) |
| SPY | ✅ CANTA 72% (n=213) | 🔇 MUTED 47% (n=17) | 🔇 MUTED 0% (n=8) |
| NVDA | ✅ CANTA 69% (n=196) | ✅ CANTA 55% (n=20) | 🔇 MUTED 0% (n=9) |
| TSLA | ✅ CANTA 70% (n=200) | 🔇 MUTED 53% (n=15) | 🔇 MUTED 0% (n=9) |
| MU | ✅ CANTA 65% (n=202) | 🔇 MUTED 44% (n=16) | 🔇 MUTED 0% (n=3) |
| SMH | ✅ CANTA 66% (n=188) | 🔇 MUTED 44% (n=16) | 🔇 MUTED 0% (n=4) |
| AMD | ✅ CANTA 69% (n=195) | 🔇 MUTED 38% (n=16) | 🔇 MUTED 40% (n=5) |
| AAPL | ✅ CANTA 65% (n=196) | 🔇 MUTED 20% (n=15) | 🔇 MUTED 20% (n=5) |
| MSFT | ✅ CANTA 70% (n=203) | 🔇 MUTED 50% (n=12) | 🔇 MUTED 0% (n=2) |
| META | ✅ CANTA 74% (n=212) | ✅ CANTA 56% (n=16) | 🔇 MUTED 38% (n=8) |
| AMZN | ✅ CANTA 68% (n=193) | 🔇 MUTED 38% (n=16) | 🔇 MUTED 14% (n=7) |
| GOOGL | ✅ CANTA 68% (n=197) | ✅ CANTA 63% (n=19) | 🔇 MUTED 0% (n=7) |
| INTC | ✅ CANTA 68% (n=211) | 🔇 MUTED 31% (n=13) | 🔇 MUTED 0% (n=5) |
| TSM | ✅ CANTA 68% (n=203) | 🔇 MUTED 44% (n=18) | 🔇 MUTED 0% (n=6) |
| ASML | ✅ CANTA 68% (n=189) | 🔇 MUTED 43% (n=21) | 🔇 MUTED 50% (n=2) |
| TXN | ✅ CANTA 67% (n=187) | 🔇 MUTED 47% (n=15) | 🔇 MUTED 25% (n=8) |
| QCOM | ✅ CANTA 69% (n=182) | 🔇 MUTED 53% (n=15) | 🔇 MUTED 0% (n=2) |
| AVGO | ✅ CANTA 68% (n=197) | 🔇 MUTED 46% (n=22) | 🔇 MUTED 0% (n=4) |
| NFLX | ✅ CANTA 77% (n=202) | ✅ CANTA 56% (n=18) | 🔇 MUTED 0% (n=7) |
| NOK | ✅ CANTA 72% (n=205) | 🔇 MUTED 50% (n=16) | 🔇 MUTED 0% (n=4) |
| GLD | ✅ CANTA 64% (n=194) | 🔇 MUTED 40% (n=15) | 🔇 MUTED 0% (n=9) |
| XLK | ✅ CANTA 69% (n=183) | 🔇 MUTED 52% (n=21) | 🔇 MUTED 0% (n=4) |
| EWY | ✅ CANTA 63% (n=185) | 🔇 MUTED 41% (n=17) | 🔇 MUTED 0% (n=3) |
| DRAM | ✅ CANTA 61% (n=186) | 🔇 MUTED 24% (n=21) | 🔇 MUTED 0% (n=4) |
| SPCX | ✅ CANTA 69% (n=205) | ✅ CANTA 71% (n=14) | 🔇 MUTED 7% (n=14) |
| SKHY | ✅ CANTA 69% (n=86) | 🔇 MUTED 30% (n=10) | 🔇 MUTED 0% (n=3) |
| LRCX | ✅ CANTA 68% (n=193) | 🔇 MUTED 25% (n=12) | 🔇 MUTED 0% (n=1) |
| SNDK | ✅ CANTA 73% (n=194) | 🔇 MUTED 46% (n=22) | 🔇 MUTED 14% (n=7) |
| WDC | ✅ CANTA 72% (n=204) | 🔇 MUTED 46% (n=13) | 🔇 MUTED 0% (n=3) |
| STX | ✅ CANTA 72% (n=209) | 🔇 MUTED 50% (n=14) | 🔇 MUTED 33% (n=3) |

## Conclusiones del grid (sin cherry-pick)

1. **elastic ES el filo del vigia**: 68.9% pooled (n=5800), TODOS los 30 tickers
   ≥55% con n grande → los 30 quedan enabled. Mejores: NFLX 77%, META 74%,
   SNDK 73%, SPY/NOK/WDC/STX 72%. Peores (aun asi >55%): DRAM 61%, EWY 63%.
2. **σ2.5 EMPEORA elastic** (63.3% vs 68.9%, y en 29/30 tickers): el pierce mas
   profundo se parece mas a band-walk que a elastico. **Quedarse con 2.0σ.**
3. **σ2.5 SI mejora bandwalk** (56.1% vs 45.6%) pero n cae de 500 a 173 — señal
   de que el band-walk "de verdad" necesita el pierce profundo. Candidato a
   v2 (usar 2.5σ SOLO para el canto de band-walk), no se cambia hoy.
4. **cooldown 15m ≈ mismo hit-rate** (elastic 69.0% vs 68.9%) con +35% señales →
   mas ruido sin mas filo por señal. **Quedarse con 30m** (anti crying-wolf).
5. **re15 esta MUERTO como fade**: 8.1% pooled (n=160), 0 tickers enabled. Tras
   re-entrada 15m el precio NO va a la media 15m en 30min. El vigia ahora lo
   deja en solo-log para toda la flota (degradacion, no borrado).
6. **bandwalk queda enabled solo en 5**: NVDA 55%, META 56%, GOOGL 63%,
   NFLX 56%, SPCX 71% — el resto muted (44% pooled = el "NO hacer fade"
   generico NO estaba aguantando 30min en la mayoria de la flota).
7. Neto en produccion: **35 celdas cantan, 55 muted** (solo log).

## Notas honestas
- 17 sesiones ≠ 30 dias: es TODO lo que yfinance da en 1m. n chico en muchos
  buckets — el Wilson LB es la cifra prudente, no el punto.
- Un solo regimen de mercado (rally memoria jul-2026); las probs pueden no
  viajar a otro regimen. Re-correr el backtest mensualmente.
- `bandwalk` mide si la continuacion aguanta (NO tocar la media 1m en 30min);
  es la validacion de 'NO hacer fade', no un edge de entrada por si mismo.
- SKHY: 8 sesiones -> n minusculo; celdas casi todas MUTED por n, no por filo.
- El gating del vigia degrada limpio: sin `bollinger_probs.json` canta como antes.
