# GEXA SNAPSHOTS FINALES — 2026-07-23 (última noche antes de que gexa.ai cierre)

Capturados autónomamente vía navegador (cuenta de Yunior) para CALIBRAR nuestro reemplazo
mañana antes de que gexa muera. Todos Exp 2026-07-24, VIX 18.7, cierre 16:2x ET.

| sym | spot | flip | régimen | Vanna | Bias |
|---|---|---|---|---|---|
| NVDA | 209.25 | 203 (+5.7pt) | POSITIVE | +1.8B | CALL FLOW |
| QQQ | 695.50 | 709 (−14pt) | NEGATIVE | +3.6B | BEARISH |
| SPY | 739.52 | 748 (−8.2pt) | NEGATIVE | +7.7B | BEARISH |

## HALLAZGO CLAVE (respuesta a "por qué −319M vs 2.4B")
La cifra de "billones" que Yunior veía en gexa NO es el net GEX — es la **Vanna** (header
"Vanna +1.8B") y/o cifras de **NODO** en el panel DARK POOL/GEX PROFILE (ej nodo ATM NVDA
209 = $2.4B). Nuestro net GEX (−319M/+262M) es la gamma NETA con signo. Nuestra Vanna
(3.69–4.5B) coincide en orden con la de gexa. Son métricas distintas. Per-strike GEX SÍ
matcheamos gexa (verificado SPY 736 −371M vs −369M).

## CALIBRACIÓN PENDIENTE (mañana, ampliar cache primero)
- flip gap: NVDA gexa 203 vs nuestro ~206 · QQQ 709 · SPY 748 → comparar tras ampliar strikes.
- Imanes gexa (INSTITUTIONAL FOOTPRINT, de QQQ): 700 ACELERADOR 90/100, 685/690 MAGNET 80/77.
- gexa DEEP ANALYSIS del día: fortress-pin 7400 (QQQ), gatekeeper_fade fue el edge, pin de expiry ganó.

## LO QUE NO PODEMOS REPLICAR (necesita feeds pagados)
Dark Pool nodes, Market Tide firmado, DIX, GEX direccional, Institutional Footprint (sweeps/DP prints).
Sustituto honesto = nuestros daemons whale/flow. El resto (GEX/flip/muros/Vanna/charm/régimen) SÍ lo tenemos.
