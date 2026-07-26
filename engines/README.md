# engines/ — MOTOR 2: bb_engine (B7, SOLO Bollinger) + MOTOR 3: combo_engine (B8, BB + FLUJO)

C++23, aislado, **SEÑAL-SOLAMENTE** (jamas toca broker, sin voz por ahora).
Formato de señales compartido + scorer unico: `docs/ENGINE-SCORING-SPEC.md`.

## Archivos

| archivo | que es |
|---|---|
| `bb_core.h` | Nucleo header-only puro: BB(20,2) **poblacional /N** incremental O(1) (patron V5BB de `scripts/v5_block.cpp.tmpl`, mejorado a sumas rodantes), %B, bandwidth + percentil rodante 125, ATR14 Wilder, agregador TF (1m→5m/15m, cierre sin look-ahead), elastic pierce+re-entrada, band-walk, squeeze-break, parser de barras robusto. |
| `bb_engine.cpp` | main MOTOR 2: modos `--backtest` y `--live`. |
| `tests/bb_test.cpp` | 75 checks: BB vs valores a mano, %B bordes, sd=0 sin dividir, pierce/re-entrada/wick, parser malformado no crashea, TFAgg, ATR, BWPct, BandWalk, engine end-to-end + gating + RTH. Pasa normal y con ASan/UBSan. |
| `combo_core.h` | Nucleo MOTOR 3 (B8) header-only: `FlowBook` (replay del MISMO nucleo de spikes de flow_pulse v3/v4: ritmo ≥3x EMA 0.40, delta ≥2000, dominancia 2x, anti-artefacto bilateral/>50x con EMA intacta), jerarquia de capitanes (regla 12), `ComboEngine` = elastic de `bb_core.h` gated por contexto de flujo, parser jsonl robusto. |
| `combo_engine.cpp` | main MOTOR 3: `--backtest ... --flow <jsonl>` y `--live` (fusion temporal barras+flujo, cero look-ahead). |
| `tests/combo_test.cpp` | 57 checks: spikes/EMA/anti-artefacto, parser jsonl malformado no crashea, capitanes (memoria y mercado), matriz de gating en los 4 cuadrantes, veto propio, ventana 20 min expira, sin flujo = sin señal, capitan-contra > capitan-favor. Pasa normal y con ASan/UBSan. |

## Compilar (con lock — Mac 8GB)

```bash
while [ -f /tmp/cc.lock ]; do sleep 5; done; touch /tmp/cc.lock
cd engines
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o bb_engine bb_engine.cpp
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o tests/bb_test tests/bb_test.cpp && ./tests/bb_test
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -o tests/bb_test_asan tests/bb_test.cpp && ./tests/bb_test_asan
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o combo_engine combo_engine.cpp
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -I. -o tests/combo_test tests/combo_test.cpp && ./tests/combo_test
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -I. -o tests/combo_test_asan tests/combo_test.cpp && ./tests/combo_test_asan
rm -f /tmp/cc.lock
```

## Uso

```bash
# backtest (emite CSV formato compartido: epoch,sym,side,kind,ref_px,target_px,stop_px)
./bb_engine --backtest data/backtest/bars3mo5m_qqq.csv --sym QQQ \
    [--csv1m data/backtest/bars30d_qqq.csv] --out señales.csv --data-dir data
# live (tail de data/bars_<sym>_ibkr.txt 1m -> data/engine_signals_bb.jsonl; --once = sin daemon)
./bb_engine --live QQQ --once --data-dir data
```

## Señales

- **ELASTIC** — pierce (CIERRE fuera de banda, wick solo no cuenta) + re-entrada
  (cierre de vuelta dentro). LONG: target = media BB, stop = min del pierce − 0.5·ATR14(5m).
  SHORT espejo. TF base: 1m si hay (`--csv1m` / live), 5m si no (declarado por stderr).
  Veto doctrina: band-walk EN CONTRA en 5m+15m (banda reventada 2-3 TF a favor = continuacion, no rebote).
- **SQZ_BRK** — bandwidth 5m en pctile ≤20 (ventana 125) y cierre rompe banda:
  target 2·ATR, stop 1·ATR.
- **BWALK** — racha ≥3 cierres 5m fuera + burst 15m mismo lado (solo si `enabled` en probs).
- RTH 9:45–15:55 ET (9:30-9:45 jamas — subasta), DST correcto (TZ=America/New_York).
  Cooldowns: elastic 900s, squeeze 1800s, bwalk 3600s por lado.

## Config por ticker (degradacion limpia)

- `data/bollinger_probs.json` → `elastic/bandwalk.enabled` (disabled = no emite).
- `data/bollinger_plus.json` → `veto_filters` implementables solo-BB:
  `F5_squeeze`, `F6_0945/1030/1130/1400` (ventanas ET), `F7_15m_in` — un veto SOLO se aplica con `fdr_ok:true` (BH-FDR, ver bb_engine.cpp).
  F1/F2/F3/F4/F8 (RVOL/RSI/depth/zVWAP/ADX) se IGNORAN con aviso por stderr.
- Sin .json → elastic basico con defaults. Nada crashea por archivo ausente.

## Resultados preliminares 2026-07-23 (scorer unico, horizonte 24×5m, stop gana en barra empatada)

**DECLARACION DE DATOS**: barras 5m de 3 meses (`bars3mo5m_*`, yfinance) y 1m de
30 dias (`bars30d_*`). `data/whale_flow_hist.jsonl` existe SOLO desde 2026-07-21 —
**3 meses de flujo NO EXISTEN** (no aplica a este motor, pero se declara).
El run de 3 meses corre elastic en 5m (no hay 1m de 3 meses); el run 1m (30d)
es el diseño real del modo live.

### Run A — 3 meses, base 5m (`data/backtest/scores_bb.json`)

| ticker | n | WR | Wilson lo | PnL med (bps) |
|---|---|---|---|---|
| QQQ | 205 | 40.6% | 34.1% | −7.7 |
| NVDA | 279 | 41.0% | 35.3% | −19.7 |
| MU | 214 | 39.6% | 33.2% | −36.7 |
| SMH | 158 | 37.4% | 30.2% | −17.1 |
| NOK | 230 | 35.8% | 29.7% | −31.4 |
| **GLOBAL** | **1086** | **39.1%** | **36.1%** | **−14.6** |

Por kind (global): ELASTIC-5m n=684 WR 45.9% (Wilson 42.1%, −9.5 bps);
SQZ_BRK n=376 WR **27.8%** (breakeven de su R:R 2:1 = 33.3% → **pierde**);
BWALK n=26 WR 26.9%.

### Run B — 30 dias, base 1m = diseño live (scratchpad `scores_bb1m.json`)

| ticker | n | WR | Wilson lo | PnL med (bps) |
|---|---|---|---|---|
| NOK | 223 | 59.5% | 52.9% | +4.8 |
| SMH | 140 | 58.3% | 50.0% | +4.0 |
| QQQ | 190 | 55.8% | 48.7% | +0.2 |
| MU | 234 | 52.1% | 45.8% | −2.4 |
| NVDA | 232 | 50.0% | 43.6% | −7.1 |
| **GLOBAL** | **1019** | **54.8%** | **51.7%** | **+0.1** |

Por kind: **ELASTIC-1m n=910 WR 58.0% (Wilson lo 54.8%, +1.8 bps)** —
la cota inferior separa de la moneda; SQZ_BRK n=100 WR 27.6% (sigue perdiendo).

### Lectura honesta

1. **Elastic vive en el 1m** (58.0% con Wilson 54.8%); en 5m se degrada a 45.9%.
   El modo live (1m) es el bueno. PnL en bps es minusculo porque el target es la
   media BB (recorrido corto) — WR alto ≠ edge grande; el tamaño del target manda.
2. **SQZ_BRK pierde tal cual esta** (27.6–27.8% vs 33.3% de breakeven) en ambas
   bases. Candidato a `enabled:false` por defecto o a re-diseño (retest en vez de
   primer break). NO se toco: numeros primero, cirugia despues.
3. Ambos runs son ventanas cortas (3mo/30d) de un solo regimen de mercado.
   Preliminar, no prueba de edge.

---

# MOTOR 3 — combo_engine (B8): BOLLINGER + FLUJO DE OPCIONES

La señal BB **elastic** (nucleo B7) SOLO se emite si el **contexto de flujo**
esta de acuerdo, con la **jerarquia de capitanes** (regla 12 de `~/CLAUDE.md`,
2026-07-22): SPY/QQQ capitanes del mercado para todos; SMH capitan de la tropa
memoria {MU SKHY DRAM SNDK WDC STX LRCX NVDA AMD TSM}; nadie es capitan de si
mismo (SPY↔QQQ se cubren entre ellos).

## Gating (espejo exacto LONG/SHORT)

- **elastic LONG** requiere: sin `SPIKE_CALLS` vigente (≤20 min) del **propio**
  ticker Y capitan(es) **sin** `SPIKE_CALLS` vigente. `SPIKE_PUTS` vigente del
  capitan = **refuerzo** → `kind=combo_captain`; contexto neutro →
  `kind=combo_elastic`. SHORT es el espejo.
- **Capitan-contra > capitan-favor** (conflicto QQQ-favor + SPY-contra = veto):
  "el capitan prevalece y la señal del nombre queda anulada".
- **Sin flujo = sin señal** (diseño, no fallo): se exige registro de flujo
  ≤30 min del propio ticker Y de cada capitan; si falta, el candidato cae en
  `sin_contexto` y NO se emite.
- Estado de flujo: replay del MISMO algoritmo de spikes de `flow_pulse` v3/v4
  (== `scripts/flow_signals_export.py`): ritmo ≥3x EMA α0.40, delta ≥2000,
  dominancia 2x, anti-artefacto (bilateral o >50x = mudo, EMA intacta). Aqui
  el spike solo arma el reloj de vigencia (20 min); sin cooldown.
- Cero look-ahead: solo registros de flujo con `ts <=` cierre de la barra que
  decide; los 28 artefactos del replay coinciden 1:1 con los del export Python.

## Uso

```bash
# backtest (CSV formato compartido; --flow obligatorio)
./combo_engine --backtest data/backtest/bars3mo5m_qqq.csv --sym QQQ \
    --flow data/whale_flow_hist.jsonl [--csv1m data/backtest/bars30d_qqq.csv] --out señales.csv
# live (tail bars_<sym>_ibkr.txt 1m + whale_flow_hist.jsonl -> data/engine_signals_combo.jsonl; sin voz)
./combo_engine --live QQQ --once --data-dir data
```

## Resultado preliminar 2026-07-23 (scorer unico, horizonte 24×5m)

**DECLARACION DE DATOS — clave**: `data/whale_flow_hist.jsonl` existe SOLO
desde 2026-07-21; en disco hay **UN dia de flujo** (2026-07-22 09:32–16:00,
1500 registros). **3 meses de flujo NO EXISTEN.** El combo en dias sin flujo NO
emite — eso ES el diseño (sin contexto no hay señal). Barras: 1m×30d (elastic
en 1m, el diseño live).

Cobertura (candidatos elastic → que paso): QQQ 225 cand / 208 sin_contexto /
1 veto_propio / 16 emitidas; NVDA 237 / 223 / 1+1 veto / 12 emitidas;
MU 236 / 221 / 1 veto / 14 emitidas. Es decir: ~93% de los candidatos caen en
dias/horas sin flujo y no se emiten (declarado, por diseño).

`data/backtest/scores_combo.json`:

| ticker | n | wins | losses | timeouts | WR | Wilson lo | PnL med (bps) |
|---|---|---|---|---|---|---|---|
| QQQ | 16 | 13 | 3 | 0 | 81.2% | 57.0% | +3.5 |
| MU | 14 | 9 | 5 | 0 | 64.3% | 38.8% | −0.2 |
| NVDA | 12 | 7 | 5 | 0 | 58.3% | 31.9% | +11.9 |
| **GLOBAL** | **42** | **29** | **13** | **0** | **69.0%** | **54.0%** | **+3.5** |

### Lectura honesta

1. 69.0% con Wilson inferior 54.0% **sobre UN solo dia de mercado** (n=42):
   la cota separa de la moneda por poco, pero un dia no es un regimen — es una
   linea base del harness, no prueba de edge. Se recalibra cada dia que
   `whale_flow_hist.jsonl` acumule historia.
2. Referencia: el mismo elastic-1m SIN gating de flujo dio 58.0% (Run B,
   30 dias, n=910). 69.0% del combo **parece** sumar, pero compara 1 dia vs
   30 y n=42 vs n=910 — sugestivo, no concluyente.
3. `combo_captain` (refuerzo) aparecio 1 sola vez (MU) — sin n para juzgarlo.
4. Vetos reales del dia: 3 veto_propio + 1 veto_capitan — el flujo del 7/22 fue
   tranquilo en los capitanes durante las señales elastic.
