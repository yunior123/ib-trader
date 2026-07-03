# ENGINE-SCORING-SPEC — formato de señales compartido + scorer unico (E1H)

**Fuente de verdad** para los 3 motores (flujo, y los otros builders). Toda engine
emite señales en ESTE formato y se puntua SOLO con `scripts/scorer.py`.
Comparaciones entre motores solo valen si ambos pasaron por este scorer.

## 1. Formato de señal (CSV)

```
epoch,sym,side,kind,ref_px,target_px,stop_px
```

| campo | tipo | significado |
|---|---|---|
| `epoch` | int (s, UTC) | instante del disparo de la señal |
| `sym` | str | ticker (mayusculas) |
| `side` | `LONG` \| `SHORT` | direccion de la tesis |
| `kind` | str corto | etiqueta de la señal (p.ej. `SPIKE_PUTS`) |
| `ref_px` | float | precio del subyacente al disparar |
| `target_px` | float | objetivo |
| `stop_px` | float | stop |

Header opcional (linea que empieza por `epoch` se ignora). Una señal por linea.

## 2. Reglas del scorer (`scripts/scorer.py`)

1. **Entrada** = `OPEN` de la **siguiente barra 5m tras `epoch`** (primera barra
   con `start > epoch`). Cero look-ahead: nada anterior o simultaneo al disparo.
2. Recorre las barras 5m desde la barra de entrada **inclusive**:
   - `LONG`: stop si `low <= stop_px`; target si `high >= target_px`.
   - `SHORT`: stop si `high >= stop_px`; target si `low <= target_px`.
3. **Stop y target en la MISMA barra -> cuenta STOP** (conservador; protege de
   sobreestimar el WR).
4. **Horizonte = 24 barras 5m** (2 h). Ni target ni stop dentro -> bucket
   **TIMEOUT**: se reporta aparte (no entra en el WR) con PnL al `close` de la
   ultima barra disponible del horizonte.
5. **WR estricto = wins / (wins + losses)**. Wilson 95% inferior (`wilson_lo`)
   sobre esa misma proporcion.
6. PnL en bps sobre la entrada, con signo por lado:
   `LONG = (exit-entry)/entry*1e4`, `SHORT = (entry-exit)/entry*1e4`.
   Exit: target o stop segun toque; close del horizonte si TIMEOUT.
   Nota honesta: los niveles son fijos al `ref_px` del disparo y la entrada es
   el open siguiente — con gap, un "LOSS" (stop) puede tener PnL positivo y
   viceversa. Se reporta tal cual.
7. Señal sin barras posteriores a su epoch (o sin fichero de barras) ->
   **SKIPPED**, contada aparte, fuera de `n`.
8. Todo por motor y **por ticker** + agregado global.

### Barras

`--bars-dir` (default `data/backtest/`), formato `epoch,o,h,l,c,v`:
- `bars3mo5m_<sym>.csv` (5m nativo, prioridad) — hoy: aapl amd meta msft mu
  nvda qqq smh spy tsla, hasta 2026-07-22 15:55.
- `bars30d_<sym>.csv` (1m, 30 dias, toda la flota) — se agrega a 5m:
  bucket `epoch - epoch%300`, `o`=primera, `h`=max, `l`=min, `c`=ultima, `v`=suma.

### Uso

```
venv/bin/python scripts/scorer.py <señales.csv> [mas.csv ...] \
    --name <nombre> [--bars-dir data/backtest] [--horizon 24] [--engine "etiqueta"]
```

Salida: `data/backtest/scores_<nombre>.json` + tabla por stdout.

```json
{"engine": "...", "horizon_bars_5m": 24, "skipped_sin_barras": 0,
 "por_ticker": {"NVDA": {"n":6,"wins":4,"losses":2,"timeouts":0,
                          "wr":0.6667,"wilson_lo":0.30,
                          "pnl_bps_median":33.7,"timeout_pnl_bps_median":null}},
 "global": { ...misma forma... }}
```

**Auto-test** (obligatorio tras tocar el scorer): CSV sintetico con 4 casos —
win claro, loss claro, timeout, y stop+target en la misma barra (debe contar
STOP). Verificado 2026-07-22 con PnLs calculados a mano.

## 3. Motor de flujo — replay (`scripts/flow_signals_export.py`)

Replica exacta del nucleo de spikes de `scripts/flow_pulse.cpp` (v3/v4) sobre
`data/whale_flow_hist.jsonl`:
ritmo por lado sobre `mins∈[1,30]`; EMA alfa 0.40; spike = ritmo ≥3x EMA y
delta ≥2000 contratos; dominancia 2x; anti-artefacto (bilateral o >50x = mudo,
EMA intacta); cooldown 600 s por sym+lado (se consume aunque haya veto);
RTH 09:35–15:54 ET; veto band-walk BB(20,2) 1m+5m con barras historicas
cerradas (`epoch+60 <= ts`), sin barras -> sin veto (degradacion limpia).

Señales (tesis de reversion espada-ballena): `SPIKE_PUTS -> LONG`,
`SPIKE_CALLS -> SHORT`, `ref_px` = spot del registro, target/stop = ±0.35%.

## 4. Resultado motor de flujo — 2026-07-22 (DECLARACION DE DATOS)

**`data/whale_flow_hist.jsonl` existe SOLO desde 2026-07-21; en disco hay
UN dia de flujo (2026-07-22 09:32–16:00, 1500 registros). 3 meses de flujo NO
EXISTEN. n minusculo por diseño — esto NO es un backtest de 3 meses.**

Replay: 26 spikes emitidos (17 calls-fade SHORT, 9 puts-rebote LONG),
0 vetados por band-walk, 28 artefactos silenciados, 2 fuera de RTH.

`scores_flow.json` (horizonte 24x5m, target/stop ±0.35%):

| bucket | n | wins | losses | timeouts | WR | Wilson lo | PnL med (bps) |
|---|---|---|---|---|---|---|---|
| **GLOBAL** | 26 | 15 | 9 | 2 | **62.5%** | **42.7%** | +17.7 |

Por ticker (n≥3): NVDA 4/2 (66.7%), AVGO 2/2 (50%), GOOGL 1/2 (33.3%).
QQQ: 2 timeouts (rango estrecho — 0.35% no se alcanzo en 2 h).

Lectura honesta: 62.5% con Wilson inferior 42.7% en UN solo dia — la cota
inferior no separa de la moneda al aire. Sirve como linea base del harness,
no como prueba del edge. Se recalibra cada dia que `whale_flow_hist.jsonl`
acumule historia (el archivo crece en vivo desde 2026-07-21).

## 5. Regla de oro

Aditivo y con degradacion limpia. El scorer jamas ejecuta ordenes
(SEÑAL-SOLAMENTE). Numeros reales aunque duelan; jamas look-ahead.
