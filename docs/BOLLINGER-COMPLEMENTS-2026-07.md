# BOLLINGER COMPLEMENTS — Mision B6 (2026-07-22)

Complementos de la señal **elastic-1m** de `scripts/bollinger_alarm.py`, medidos
ticker por ticker sobre 30 dias de barras 1m (17 sesiones RTH; SKHY solo 8).
Grid COMPLETO — celdas nulas y negativas incluidas. Numeros honestos, Wilson 95%.

- Motor: `scripts/bollinger_complements.py` (detector + `--analyze`).
- Señales crudas: `data/backtest/bcomp_results.json` (4,619 señales elastic).
- Grid procesado: `data/backtest/bcomp_grid.json`.
- Consumo por el alarm: `data/bollinger_plus.json` (n>=15 y |uplift|>=5pts).

## 1. Metodologia

Replica de la deteccion del alarm, bar a bar cerrado:

- **BB(20,2) 1m, std POBLACIONAL** (/N), banda sobre los 20 cierres ANTERIORES
  a la vela actual (identico a `bars[-21:-1]` del alarm).
- **PIERCE**: `high > banda_sup` o `low < banda_inf`. Cierre fuera → arma el lado.
- **RE-ENTRADA (fire)**: vela posterior (≤10 min de armado, = expiry del alarm)
  que sigue perforando pero CIERRA dentro. Cooldown 30 min por simbolo+lado.
- **Exclusion band-walk**: si el cierre 5m actual esta fuera de su BB(20,2) 5m
  en el mismo lado, el alarm canta BAND-WALK, no elastico → fuera de la base
  (≈24 walks/ticker en 17 dias).
- **RTH only**, señal valida 9:50–15:30 ET (≥20 barras de sesion para BB 100%
  intradia; ≤15:30 para tener los 30 min de outcome completos, sin cruzar cierre).
- **Outcome principal `hit_mid30`**: toca la media BB20-1m CONGELADA al fire
  dentro de 30 barras 1m (dn: high≥mid; up: low≤mid). Conservador: la media
  real camina hacia el precio. Secundarios: `hit_half30` (≥50% del gap),
  MFE/MAE 15/30 min en % (a favor de la reversion).
- Diferencia vs live: el alarm escanea cada 30s INTRABAR; aqui todo es bar 1m
  cerrado (anti-lookahead). El conteo de señales live sera ligeramente mayor.

Filtros como el alarm los veria en el momento del fire (cero lookahead):
F1 RVOL≥1.5 (vol vela fire vs SMA20 vol) · F2 RSI(2) 1m extremo (dn<10 / up>90)
· F3 profundidad del pierce >0.05 / >0.15 del ancho de banda · F4 z-VWAP sesion
≥|1.5| contra el lado · F5 bandwidth 1m percentil ≤20 de 125 barras (contexto
squeeze) · F6 buckets horarios · F7 cierre 15m dentro de su banda · F8 ADX(14)
5m <20 / ≥25.

## 2. Base flota (sin filtro)

| metrica | valor |
|---|---|
| n señales | 4,619 (30 tickers, 17 sesiones) |
| P(toca media 30min) | **65.8%** [64.4, 67.1] |
| P(≥50% del gap) | 82.7% |
| gap medio a la media | 0.268% |
| MFE30 / MAE30 medios | 0.455% / 0.478% → **edge30 = −0.023%** |
| lado dn (fade long) | 67.3% [65.3, 69.1], n=2376 |
| lado up (fade short) | 64.2% [62.2, 66.2], n=2243 |

**Honestidad**: 65.8% de tocar la media NO es dinero gratis. El target medio es
chico (0.27%) y el MAE medio SUPERA al MFE — el elastico crudo, aguantado 30 min
sin gestion, tiene expectativa ≈ 0. El edge esta en (a) filtrar (abajo), y
(b) cobrar EN la media, rapido, con stop — exactamente la doctrina espada:
chico y seguro. La regla cero de la skill ("banda sola = coin flip") aplica al
toque; el pierce+re-entrada ya lleva confirmacion dentro y por eso parte de 66%,
no de 50%.

## 3. EL GRID COMPLETO

Celdas: `P% (n) [uplift vs base del ticker]` — outcome = toca la media BB20-1m en 30 min.

| ticker | base n | base P% | F1_rvol15 | F2_rsi2_ext | F3a_depth05 | F3b_depth15 | F4_zvwap15 | F5_squeeze | F6_0945 | F6_1030 | F6_1130 | F6_1400 | F7_15m_in | F8a_adx_lt20 | F8b_adx_ge25 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| AAPL | 157 | 58.6 | 38.5 (13) [-20] | 30.0 (10) [-29] | 58.1 (155) [-0] | 60.3 (131) [+2] | 30.8 (13) [-28] | 68.9 (45) [+10] | 35.3 (17) [-23] | 60.7 (28) [+2] | 61.1 (72) [+2] | 62.5 (40) [+4] | 61.1 (126) [+2] | 54.2 (48) [-4] | 59.3 (81) [+1] |
| AMD | 161 | 72.7 | 81.0 (21) [+8] | 30.0 (10) [-43] | 73.6 (159) [+1] | 71.7 (138) [-1] | 52.4 (21) [-20] | 87.8 (49) [+15] | 52.6 (19) [-20] | 76.7 (30) [+4] | 71.0 (69) [-2] | 81.4 (43) [+9] | 75.9 (137) [+3] | 73.3 (60) [+1] | 70.4 (71) [-2] |
| AMZN | 165 | 61.2 | 82.4 (17) [+21] | 18.2 (11) [-43] | 61.1 (162) [-0] | 61.9 (134) [+1] | 43.5 (23) [-18] | 73.3 (45) [+12] | 61.9 (21) [+1] | 65.4 (26) [+4] | 57.7 (78) [-4] | 65.0 (40) [+4] | 64.6 (144) [+3] | 66.0 (53) [+5] | 59.7 (72) [-2] |
| ASML | 151 | 68.2 | 72.2 (36) [+4] | 45.5 (11) [-23] | 69.4 (147) [+1] | 70.5 (122) [+2] | 64.3 (14) [-4] | 68.1 (47) [-0] | 52.9 (17) [-15] | 79.3 (29) [+11] | 57.8 (64) [-10] | 82.9 (41) [+15] | 69.9 (123) [+2] | 74.4 (39) [+6] | 65.0 (80) [-3] |
| AVGO | 157 | 70.7 | 75.0 (24) [+4] | 88.9 (9) [+18] | 71.0 (155) [+0] | 70.2 (131) [-0] | 50.0 (24) [-21] | 74.4 (43) [+4] | 55.6 (18) [-15] | 66.7 (30) [-4] | 70.0 (70) [-1] | 82.1 (39) [+11] | 73.7 (133) [+3] | 70.6 (51) [-0] | 66.2 (74) [-4] |
| DRAM | 153 | 58.8 | 57.7 (26) [-1] | 57.1 (14) [-2] | 60.1 (148) [+1] | 57.9 (121) [-1] | 55.6 (18) [-3] | 70.2 (47) [+11] | 56.2 (16) [-3] | 62.1 (29) [+3] | 47.0 (66) [-12] | 76.2 (42) [+17] | 59.1 (132) [+0] | 52.9 (34) [-6] | 59.1 (93) [+0] |
| EWY | 140 | 62.1 | 62.5 (24) [+0] | 42.9 (14) [-19] | 61.8 (136) [-0] | 64.9 (114) [+3] | 66.7 (21) [+5] | 70.3 (37) [+8] | 70.8 (24) [+9] | 56.5 (23) [-6] | 57.1 (56) [-5] | 67.6 (37) [+6] | 59.0 (117) [-3] | 58.3 (36) [-4] | 60.8 (79) [-1] |
| GLD | 158 | 62.7 | 68.4 (38) [+6] | 50.0 (8) [-13] | 62.7 (153) [+0] | 62.2 (127) [-0] | 66.7 (27) [+4] | 76.0 (50) [+13] | 50.0 (20) [-13] | 59.3 (27) [-3] | 63.0 (73) [+0] | 71.1 (38) [+8] | 62.6 (131) [-0] | 65.9 (41) [+3] | 61.6 (86) [-1] |
| GOOGL | 163 | 67.5 | 71.4 (21) [+4] | 83.3 (6) [+16] | 67.3 (159) [-0] | 68.8 (125) [+1] | 64.7 (17) [-3] | 88.5 (52) [+21] | 61.1 (18) [-6] | 65.5 (29) [-2] | 66.2 (74) [-1] | 73.8 (42) [+6] | 68.8 (138) [+1] | 83.6 (55) [+16] | 52.6 (78) [-15] |
| INTC | 166 | 61.4 | 57.1 (14) [-4] | 33.3 (6) [-28] | 61.0 (164) [-0] | 59.7 (134) [-2] | 36.8 (19) [-25] | 76.7 (60) [+15] | 47.1 (17) [-14] | 67.7 (31) [+6] | 59.7 (72) [-2] | 65.2 (46) [+4] | 61.9 (139) [+0] | 68.5 (54) [+7] | 60.0 (85) [-1] |
| LRCX | 151 | 64.2 | 60.6 (33) [-4] | 60.0 (10) [-4] | 64.4 (149) [+0] | 64.1 (117) [-0] | 46.7 (15) [-18] | 79.5 (44) [+15] | 54.5 (11) [-10] | 64.3 (28) [+0] | 58.0 (69) [-6] | 76.7 (43) [+12] | 63.8 (130) [-0] | 72.5 (40) [+8] | 59.0 (83) [-5] |
| META | 158 | 69.6 | 66.7 (33) [-3] | 80.0 (5) [+10] | 69.2 (156) [-0] | 64.8 (122) [-5] | 50.0 (18) [-20] | 72.9 (59) [+3] | 76.5 (17) [+7] | 56.5 (23) [-13] | 62.9 (70) [-7] | 83.3 (48) [+14] | 72.4 (134) [+3] | 70.8 (48) [+1] | 65.9 (85) [-4] |
| MSFT | 167 | 66.5 | 66.7 (21) [+0] | 61.5 (13) [-5] | 66.7 (162) [+0] | 67.2 (131) [+1] | 25.0 (16) [-42] | 84.0 (50) [+18] | 61.1 (18) [-5] | 48.4 (31) [-18] | 70.8 (65) [+4] | 73.6 (53) [+7] | 71.9 (135) [+5] | 78.2 (55) [+12] | 63.6 (77) [-3] |
| MU | 167 | 61.7 | 44.4 (9) [-17] | 30.0 (10) [-32] | 62.5 (160) [+1] | 62.2 (127) [+0] | 54.5 (22) [-7] | 72.0 (50) [+10] | 47.6 (21) [-14] | 62.5 (32) [+1] | 58.1 (74) [-4] | 75.0 (40) [+13] | 62.4 (141) [+1] | 62.5 (48) [+1] | 56.1 (82) [-6] |
| NFLX | 160 | 78.1 | 70.0 (20) [-8] | 66.7 (9) [-11] | 79.0 (157) [+1] | 78.8 (132) [+1] | 66.7 (21) [-11] | 83.3 (54) [+5] | 68.8 (16) [-9] | 70.0 (30) [-8] | 77.5 (71) [-1] | 88.4 (43) [+10] | 79.7 (138) [+2] | 72.9 (48) [-5] | 82.4 (85) [+4] |
| NOK | 160 | 68.8 | 81.5 (27) [+13] | 68.8 (16) [+0] | 69.0 (158) [+0] | 67.2 (131) [-2] | 47.4 (19) [-21] | 80.7 (57) [+12] | 68.2 (22) [-1] | 55.2 (29) [-14] | 71.0 (69) [+2] | 75.0 (40) [+6] | 68.6 (121) [-0] | 76.8 (56) [+8] | 65.0 (80) [-4] |
| NVDA | 156 | 66.0 | 87.5 (16) [+22] | 20.0 (5) [-46] | 66.5 (155) [+0] | 62.6 (123) [-3] | 57.1 (21) [-9] | 79.2 (48) [+13] | 42.9 (14) [-23] | 53.6 (28) [-12] | 69.0 (71) [+3] | 76.7 (43) [+11] | 69.5 (131) [+4] | 69.0 (42) [+3] | 66.3 (86) [+0] |
| QCOM | 147 | 70.1 | 83.9 (31) [+14] | 75.0 (4) [+5] | 69.9 (143) [-0] | 72.0 (118) [+2] | 86.7 (15) [+17] | 81.4 (43) [+11] | 60.0 (15) [-10] | 76.7 (30) [+7] | 65.1 (63) [-5] | 76.9 (39) [+7] | 69.9 (123) [-0] | 64.8 (54) [-5] | 76.7 (60) [+7] |
| QQQ | 145 | 66.9 | 60.0 (20) [-7] | 33.3 (9) [-34] | 66.0 (141) [-1] | 67.9 (112) [+1] | 66.7 (21) [-0] | 84.4 (45) [+18] | 52.9 (17) [-14] | 60.7 (28) [-6] | 65.6 (64) [-1] | 80.6 (36) [+14] | 69.2 (120) [+2] | 72.7 (33) [+6] | 65.9 (91) [-1] |
| SKHY | 71 | 57.7 | 78.6 (14) [+21] | 40.0 (5) [-18] | 56.5 (69) [-1] | 55.4 (56) [-2] | 42.9 (7) [-15] | 83.3 (18) [+26] | 58.3 (12) [+1] | 58.3 (12) [+1] | 62.1 (29) [+4] | 50.0 (18) [-8] | 54.4 (57) [-3] | 66.7 (21) [+9] | 55.6 (36) [-2] |
| SMH | 154 | 62.3 | 65.4 (26) [+3] | 46.2 (13) [-16] | 60.8 (148) [-2] | 61.1 (113) [-1] | 30.8 (13) [-32] | 71.1 (38) [+9] | 45.0 (20) [-17] | 77.8 (27) [+16] | 52.9 (70) [-9] | 78.4 (37) [+16] | 64.6 (127) [+2] | 48.6 (37) [-14] | 62.4 (93) [+0] |
| SNDK | 158 | 65.8 | 57.1 (21) [-9] | 61.5 (13) [-4] | 66.0 (153) [+0] | 66.4 (128) [+1] | 50.0 (20) [-16] | 75.6 (45) [+10] | 50.0 (18) [-16] | 60.0 (30) [-6] | 60.6 (66) [-5] | 84.1 (44) [+18] | 66.4 (137) [+1] | 58.3 (36) [-8] | 70.2 (104) [+4] |
| SPCX | 153 | 66.0 | 70.8 (24) [+5] | 69.2 (13) [+3] | 66.0 (153) [+0] | 65.9 (129) [-0] | 67.9 (28) [+2] | 76.9 (39) [+11] | 68.8 (16) [+3] | 53.8 (26) [-12] | 68.7 (67) [+3] | 68.2 (44) [+2] | 67.9 (131) [+2] | 61.0 (41) [-5] | 72.5 (80) [+6] |
| SPY | 167 | 64.1 | 66.7 (30) [+3] | 66.7 (9) [+3] | 64.6 (164) [+0] | 62.4 (133) [-2] | 50.0 (24) [-14] | 72.2 (54) [+8] | 63.2 (19) [-1] | 70.6 (34) [+6] | 63.8 (69) [-0] | 60.0 (45) [-4] | 64.3 (143) [+0] | 66.7 (48) [+3] | 64.3 (84) [+0] |
| STX | 164 | 64.0 | 69.0 (29) [+5] | 63.6 (11) [-0] | 64.0 (161) [+0] | 64.7 (139) [+1] | 50.0 (20) [-14] | 78.0 (59) [+14] | 38.9 (18) [-25] | 60.6 (33) [-3] | 60.8 (74) [-3] | 84.6 (39) [+21] | 68.1 (141) [+4] | 70.0 (50) [+6] | 58.6 (87) [-5] |
| TSLA | 161 | 68.9 | 52.0 (25) [-17] | 77.8 (9) [+9] | 68.9 (161) [+0] | 71.0 (131) [+2] | 60.0 (15) [-9] | 76.1 (46) [+7] | 72.2 (18) [+3] | 71.4 (28) [+2] | 65.2 (69) [-4] | 71.7 (46) [+3] | 70.1 (134) [+1] | 69.8 (43) [+1] | 71.6 (81) [+3] |
| TSM | 164 | 66.5 | 75.0 (20) [+8] | 33.3 (12) [-33] | 66.5 (164) [+0] | 67.5 (126) [+1] | 62.5 (24) [-4] | 76.6 (47) [+10] | 61.9 (21) [-5] | 64.3 (28) [-2] | 58.9 (73) [-8] | 83.3 (42) [+17] | 67.4 (141) [+1] | 66.1 (56) [-0] | 71.1 (76) [+5] |
| TXN | 144 | 66.0 | 84.8 (33) [+19] | 50.0 (4) [-16] | 65.5 (139) [-0] | 65.1 (109) [-1] | 65.0 (20) [-1] | 72.9 (48) [+7] | 64.7 (17) [-1] | 60.7 (28) [-5] | 61.9 (63) [-4] | 77.8 (36) [+12] | 68.0 (122) [+2] | 67.4 (43) [+1] | 66.7 (75) [+1] |
| WDC | 162 | 67.3 | 72.0 (25) [+5] | 25.0 (4) [-42] | 67.7 (158) [+0] | 65.1 (129) [-2] | 31.8 (22) [-36] | 72.9 (59) [+6] | 65.0 (20) [-2] | 62.1 (29) [-5] | 69.7 (76) [+2] | 67.6 (37) [+0] | 69.6 (138) [+2] | 69.6 (56) [+2] | 62.0 (79) [-5] |
| XLK | 139 | 64.7 | 51.9 (27) [-13] | 75.0 (8) [+10] | 64.5 (138) [-0] | 61.9 (105) [-3] | 75.0 (20) [+10] | 76.1 (46) [+11] | 72.2 (18) [+8] | 50.0 (22) [-15] | 59.6 (57) [-5] | 76.2 (42) [+12] | 65.8 (117) [+1] | 60.5 (38) [-4] | 68.5 (73) [+4] |
| **FLOTA** | 4619 | 65.8 | 68.5 (718) [+2.7] | 53.0 (281) [-12.8] | 65.9 (4527) [+0.1] | 65.6 (3688) [-0.2] | 54.8 (578) [-11.0] | 76.8 (1424) [+11.0] | 58.1 (535) [-7.7] | 63.6 (838) [-2.2] | 63.2 (2023) [-2.6] | 75.0 (1223) [+9.2] | 67.3 (3881) [+1.5] | 67.7 (1364) [+1.9] | 64.7 (2396) [-1.1] |

### Flota con Wilson, P(half) y expectativa MFE−MAE 30min

| filtro | n | P(mid) [Wilson95] | P(half) | gap% | edge30 (MFE−MAE) |
|---|---|---|---|---|---|
| BASE | 4619 | 65.8 [64.4, 67.1] | 82.7 | 0.268 | −0.023 |
| F1_rvol15 | 718 | 68.5 [65.0, 71.8] | 85.0 | 0.233 | −0.022 |
| F2_rsi2_ext | 281 | 53.0 [47.2, 58.8] | 77.2 | 0.433 | +0.040 |
| F3a_depth05 | 4527 | 65.9 [64.5, 67.2] | 82.6 | 0.267 | −0.024 |
| F3b_depth15 | 3688 | 65.6 [64.1, 67.1] | 82.5 | 0.268 | −0.036 |
| F4_zvwap15 | 578 | 54.8 [50.8, 58.9] | 74.0 | 0.476 | −0.035 |
| F5_squeeze | 1424 | **76.8 [74.5, 78.9]** | 88.9 | 0.137 | −0.019 |
| F6_0945 | 535 | 58.1 [53.9, 62.2] | 77.2 | 0.518 | **−0.215** |
| F6_1030 | 838 | 63.6 [60.3, 66.8] | 81.6 | 0.364 | +0.051 |
| F6_1130 | 2023 | 63.2 [61.0, 65.2] | 81.4 | 0.219 | −0.042 |
| F6_1400 | 1223 | **75.0 [72.5, 77.3]** | 87.9 | 0.174 | **+0.042** |
| F7_15m_in | 3881 | 67.3 [65.8, 68.8] | 83.8 | 0.242 | −0.005 |
| F8a_adx_lt20 | 1364 | 67.7 [65.2, 70.2] | 84.2 | 0.195 | −0.051 |
| F8b_adx_ge25 | 2396 | 64.7 [62.8, 66.6] | 81.6 | 0.298 | −0.004 |

## 4. Combos (pares de filtros con uplift flota ≥5 y n≥15)

Solo DOS filtros calificaron a nivel flota (F5 +11.0, F6_1400 +9.2) → 1 combo
legal. Se listan ademas 2 exploratorios (con F8a, que quedo en +1.9 — NO
califico; se reportan por transparencia, no como señal):

| combo | n | P(mid) [Wilson95] | uplift | edge30 |
|---|---|---|---|---|
| **F5_squeeze + F6_1400** | 389 | **85.1 [81.2, 88.3]** | **+19.3** | **+0.041** |
| (exploratorio) F5 + F8a_adx<20 | 512 | 77.1 [73.3, 80.6] | +11.3 | −0.038 |
| (exploratorio) F6_1400 + F8a_adx<20 | 508 | 73.8 [69.8, 77.5] | +8.0 | +0.019 |

**El hallazgo estrella**: pierce+re-entrada con bandas comprimidas (bw pctile
≤20) en la ventana 14:00–15:30 toca la media el 85% de las veces con
expectativa cruda POSITIVA. n=389 en 17 dias ≈ 23/dia en la flota — señal
frecuente, no una rareza.

## 5. Control anti-mecanico de F5 (¿el squeeze solo acerca el target?)

Con bandas comprimidas la media esta mas cerca — el uplift podria ser
"mecanico". Control por cuartiles de gap% (distancia a la media al fire):

| cuartil gap% | todos P | F5 P | no-F5 P | uplift F5 dentro del cuartil |
|---|---|---|---|---|
| Q1 (≤0.098%) | 80.6 (1167) | 84.0 (655) | 75.9 (503) | **+8.1** |
| Q2 (≤0.189%) | 70.3 (1147) | 74.5 (432) | 67.3 (704) | **+7.2** |
| Q3 (≤0.344%) | 60.9 (1155) | 69.4 (245) | 58.3 (893) | **+11.1** |
| Q4 (>0.344%) | 51.2 (1150) | 55.4 (92) | 52.1 (998) | +3.3 (n chico) |

El uplift SOBREVIVE el control en Q1–Q3: parte del efecto es target-cercano,
pero hay señal real. Interpretacion: nuestra señal exige RE-ENTRADA — el
breakout genuino de squeeze NO re-entra (se va en band-walk y el gate 5m lo
excluye). Condicionado a re-entrar, el pierce post-squeeze es un breakout
FALLIDO, y un breakout fallido es de los mejores combustibles de reversion.

## 6. SORPRESAS (lo que contradice la skill o la intuicion)

1. **F5 squeeze REFUTA la hipotesis semilla** ("pierce post-squeeze = breakout,
   deberia empeorar el fade"). Es el MEJOR filtro de la flota (+11.0, 30/30
   tickers en positivo o neutro salvo ASML −0). La re-entrada cambia el signo:
   squeeze + re-entrada = head-fake confirmado, no breakout. La skill ya
   documentaba el head-fake (§2) — esto lo cuantifica del lado fade.
2. **RSI(2) extremo es VETO, no confirmacion** (−12.8 flota; NVDA −46, AMD/AMZN
   −43, WDC −42). La literatura de mean-reversion (Connors RSI2) es DIARIA; en
   1m un RSI(2) <10/>90 en el pierce significa impulso violento en curso →
   continuacion, no elastico. Solo AVGO/GOOGL/META/XLK/TSLA lo tienen en
   positivo (n≤13 — ruido). Coincide con la doctrina "señal marginal ≠
   decisiva": el elastico bueno es el estirado TRANQUILO.
3. **z-VWAP estirado (F4) es VETO** (−11.0; MSFT −42, WDC −36, SMH −32,
   AAPL −28). La hipotesis era "mas estirado del ancla = mejor elastico"; la
   realidad: lejos de VWAP = dia de tendencia → el pierce 1m es pausa de
   band-walk, no extremo. Excepcion honesta: QCOM +17 y XLK +10 (n=15-20, CI
   anchisimo). Regla: NO fade con |z-VWAP|≥1.5 en contra.
4. **La "ventana de oro" 9:45–10:30 es la PEOR hora del elastico** (58.1%,
   edge30 −0.215% — el unico bucket con MAE brutal; lado dn 55.6% y
   edge −0.396%). La ventana de oro de la doctrina es para MOMENTUM/breakouts;
   para fade es la picadora real. La tarde 14:00–15:30 es la hora elastica
   (+9.2, edge positivo). AAPL 9:45–10:30 = 35.3%: fade de apertura en AAPL es
   regalar dinero. Excepciones de mañana: EWY +9, XLK +8, META +7 (n 16-24).
5. **La profundidad del pierce NO importa** (F3a +0.1 / F3b −0.2). "Mas
   estirado = mejor rebote" es falsa a 1m dentro del rango medido (>0.05 vs
   >0.15 del ancho). Nada que optimizar aqui.
6. **ADX 5m apenas mueve la aguja** (F8a +1.9, F8b −1.1). El mantra
   "mean-reversion solo con ADX<20" NO se gana el pan a horizonte 30min-1m —
   el gate 5m band-walk del alarm ya filtra la tendencia dura, y ADX llega
   tarde a 5m. Matiz por ticker real: GOOGL adora el rango (F8a +16, F8b −15)
   y SMH lo odia (F8a −14). Sorpresa dentro de la sorpresa: QCOM y SPCX
   revierten MEJOR en tendencia (F8b +7/+6).
7. **RVOL≥1.5 es idiosincratico, no universal** (+2.7 flota, dispersion
   −17…+22): NVDA +22, AMZN +21, TXN +19, QCOM +14, NOK +13 (volumen en el
   pierce = clímax → rebota) contra TSLA −17, XLK −13, SNDK −9, QQQ −7
   (volumen = combustible → sigue). En TSLA el volumen valida la CONTINUACION;
   en NVDA valida el CLIMAX. Usarlo solo por ticker, jamas como regla flota.
8. **El elastico funciona en TODOS los tickers** (peor base: SKHY 57.7 con
   n=71 y 8 dias, AAPL 58.6, DRAM 58.8) — ninguno baja del coin flip, pero en
   AAPL/DRAM/SKHY el Wilson inferior roza 50%: ahi el elastico SIN filtro no
   se opera. NFLX es el rey (78.1 base; 88.4 en la tarde).
9. **F7 (15m dentro de banda) confirma la skill pero flojito** (+1.5). Es
   filtro de sentido comun, no de edge: su valor es que su COMPLEMENTO
   (15m fuera = band-walk 15m) cae a ~57% — vale como veto, no como boost.
10. **Fade long (dn) > fade short (up)**: 67.3% vs 64.2%. El mercado de estos
    30 dias fue alcista (rally memoria) — sesgo de regimen a favor del rebote.

## 7. Contraste con literatura publica

- Guias publicas de BB mean-reversion intradia reportan ~60% de win rate con
  ~1:1 y **58–65% con filtros (ADX, trigger de rechazo, time-stop) vs ~45% sin
  filtros porque los dias de tendencia producen rachas catastroficas**
  ([crosstrade.io](https://crosstrade.io/learn/trading-strategies/bollinger-mean-reversion)) —
  nuestra base 65.8% con el gate band-walk 5m incorporado cae exactamente en esa
  banda alta, y nuestro F6_0945/F4 son la version medida de "trending kills".
- La recomendacion publica de time-stop ("si no revirtio en ~15 barras, es
  tendencia — fuera") ([luxalgo.com](https://www.luxalgo.com/blog/mean-reversion-trading-fading-extremes-with-precision/))
  cuadra con nuestro P(half)=82.7% a 30min: lo que va a revertir, revierte rapido.
- NO encontramos literatura publica que documente el hallazgo F5 (squeeze
  mejora el fade condicionado a re-entrada) ni el veto RSI(2) a 1m — ambos son
  hallazgos propios de este dataset. Tratarlos con la humildad de n=30d.

## 8. Propuesta de diff para `bollinger_alarm.py` (NO aplicado — archivo tomado por otro agente)

Aditivo, degradacion limpia (sin `bollinger_plus.json` todo sigue igual).
Idea: el alarm ya carga `bollinger_probs.json`; añadir contexto de filtros
medidos al mensaje y mutear las celdas veto.

```python
# --- añadir tras la carga de PROBS ---
try:
    BPLUS = json.load(open("data/bollinger_plus.json"))
except Exception:
    BPLUS = {}

def bb_context(sym, mins_now, bw_pct, zvwap, rsi2):
    """Etiqueta de calidad medida para el canto elastico. '' si no hay datos."""
    d = BPLUS.get(sym.upper())
    if not d:
        return "", True
    tags, ok = [], True
    # F6_1400 + F5: la celda estrella 85% flota
    tarde = 840 <= mins_now <= 930
    squeeze = bw_pct is not None and bw_pct <= 20
    if tarde and squeeze:
        tags.append("celda estrella tarde+squeeze 85 por ciento flota")
    elif squeeze:
        tags.append("post-squeeze: re-entrada favorece el fade")
    # vetos flota medidos (n>=278): apertura, rsi2 extremo, z-vwap estirado
    if 585 <= mins_now < 630:
        tags.append("OJO apertura: peor hora del elastico 58 por ciento"); ok = False
    if rsi2 is not None and (rsi2 < 10 or rsi2 > 90):
        tags.append("VETO RSI2 extremo: impulso en curso 53 por ciento"); ok = False
    if zvwap is not None and abs(zvwap) >= 1.5:
        tags.append("VETO z-VWAP estirado: dia tendencia 55 por ciento"); ok = False
    # vetos por ticker medidos (n>=15, uplift<=-5)
    for v in d.get("veto_filters", []):
        ...  # mapear filtro->condicion actual si se computa en vivo
    return (" " + "; ".join(tags) if tags else ""), ok
```

Y en el canto elastico (rama `else` de `walk`): computar `bw_pct` (percentil
del bandwidth 1m sobre 125 barras), `rsi2` y `z-VWAP` de la sesion con los
mismos calculos de `bollinger_complements.py` (copiar `Wilder(2)` y el
acumulador VWAP — O(1)/bar), llamar `bb_context`, y:
- si `ok=False` → `log_only("🎈 BB REBOTE [VETO medido]", ...)` en vez de sirena;
- si celda estrella → `prio="SIGNAL"` y añadir el tag al mensaje.

Nota anti-doble-conteo: el mute actual por `bollinger_probs.json` (p<55) se
mantiene; `bollinger_plus.json` refina, no reemplaza.

## 9. Caveats (sin maquillaje)

- **17 sesiones** (SKHY: 8). Un solo regimen de mercado (rally memoria, VIX
  bajo). Los uplifts de hora y RVOL pueden rotar con el regimen — recalibrar
  mensual (`--force` + `--analyze`, ~2 min).
- **390 celdas per-ticker** → multiplicidad: celdas individuales con n=15-50
  tienen CI de ±15-20 pts; las conclusiones firmes son las de FLOTA (n>500) y
  las per-ticker solo donde el patron se repite entre tickers hermanos.
- `hit_mid30` usa la media CONGELADA al fire (conservador) y barras 1m cerradas
  (el alarm live escanea intrabar cada 30s — contara algo mas de señales).
- edge30 es MFE−MAE crudo sin gestion: mide simetria del movimiento, no P&L de
  una tactica con stop/target reales.
- SKHY: yfinance solo entrego 8 sesiones (ETF nuevo/iliquido) — sus celdas son
  orientativas.

*Generado por Mision B6, 2026-07-22. Datos: `data/backtest/bars30d_*.csv`
(yfinance 1m, RTH). Reproducir: `venv/bin/python scripts/bollinger_complements.py
--force && ... --analyze`.*
