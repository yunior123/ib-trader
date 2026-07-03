# V6_SPEC.md — Especificacion completa del motor v6 (flota señal-solamente)

**Fecha**: 2026-07-16. **Autor**: arquitecto v6. **Estado**: FUENTE DE VERDAD para los 5 implementadores (M1-M5).
**Ley suprema (Yunior 2026-07-16)**: la flota es SEÑAL-SOLAMENTE. PROHIBIDO cualquier `placeOrder`, exec, orden a TWS/IBKR/Alpaca. Los ejecutores retirados en `backup/execution_retired_2026-07-16/` y `backup/executors_retired_2026-07-15/` NO se reviven ni se importan. Señales = solo `BUY` / `SELL` con `prob NN%` y razones cortas. C++ para todo (Python solo donde una libreria lo exige: ib_insync/ib_async para greeks). Feeds delayed PROHIBIDOS en caminos de señal.

---

## 0. Decision de arquitectura: v6 EXTIENDE al bloque v5 (no lo reemplaza)

El bloque v5 (`scripts/v5_block.cpp.tmpl`, ya insertado en los 20 bots) contiene structs incrementales correctos y ya probados: `V5EMA`, `V5MACD` (CM 4-color), `V5BB`, `V5TF` (agregador 5m/15m), `V5TL` (trendlines LuxAlgo), `V5Ribbon`, VWAP de sesion, opening range, day_open. **v6 se inserta DESPUES del bloque v5 en el mismo archivo** y lee sus globals (`v5_tf5`, `v5_tf15`, `v5_bb1`, `v5_macd1`, `v5_tl`, `v5_rib`, `v5_vwap_pv/v5_vwap_v`, `v5_or_hi/v5_or_lo`, `v5_day_open`, `v5_bbN_dn/up_ago`). Esto evita duplicar ~200 lineas de matematica ya validada.

El disparo v5 queda **neutralizado por defecto**: `apply_v6.py` cambia el default de `V5_MIN` de `5.0` a `99.0` (regex sobre el literal `envd("<PREFIX>_V5_MIN", 5.0)` o equivalente). El bloque v5 sigue calculando (v6 lo usa como feeder); el humano puede reactivar el disparo v5 con `<SYM>_V5_MIN=5` en el keepalive si algun dia lo quiere.

Motivo: reemplazar el bloque v5 obligaria a re-testear MACD/BB/TF/TL desde cero y romperia `apply_v5.py` como referencia. Extension = riesgo minimo, diff minimo por bot.

---

## 1. Modulos, dueños y archivos (NADIE toca archivos de otro modulo)

| Mod | Alcance | Archivos que CREA/EDITA (exclusivos) | Depende de |
|-----|---------|--------------------------------------|------------|
| **M1** | Motor v6 C++ (bloque plantilla) | `scripts/v6_block.cpp.tmpl` (NUEVO, unico archivo) | nada |
| **M2** | Integracion: aplicar a la flota, recompilar, params | `scripts/apply_v6.py` (NUEVO); los 20 `*_signal_bot.cpp` (SOLO via apply_v6.py, jamas a mano); `scripts/*_keepalive.sh` (añadir exports V6); `scripts/fleet_keepalive_start.sh` (añadir lanzamiento de `price_alarm` y `options_enrich_keepalive.sh`) | M1 (template), M5 (binario price_alarm existente antes de tocar fleet_keepalive_start.sh — si no existe, dejar la linea comentada) |
| **M3** | Backtest, calibracion de prob, WFO | `scripts/v6_backtest.py` (NUEVO); `data/prob_table_<sym>.txt` (generados); `data/v6_wfo_report.txt` | M2 (bots recompilados con v6) |
| **M4** | Overlay de opciones | `scripts/options_enrich.py` (NUEVO); `scripts/options_enrich_keepalive.sh` (NUEVO) | nada (lee el mirror; formato en §6) |
| **M5** | Alarmas de precio + limpieza | `scripts/price_alarm.cpp` (NUEVO); `scripts/make_fire_alarm.py` (NUEVO); `sounds/fire_alarm.wav` (generado); `~/Desktop/price-alerts.txt` (seed); `screener/start_all.sh`; `screener/ensure_all.sh`; `screener/test_screener.py` | nada |

Orden: **M1 → M2 → M3** en serie. **M4 y M5 en paralelo** desde el minuto cero (sus contratos de formato estan cerrados en este doc). En la maquina local de 8GB: compilaciones y backtests SIEMPRE secuenciales (un `clang++` a la vez, un replay a la vez).

Compilacion canonica de bot: `clang++ -std=c++17 -O2 -o <sym>_signal_bot <sym>_signal_bot.cpp` (desde el root del repo). `price_alarm`: `clang++ -std=c++17 -O2 -o price_alarm scripts/price_alarm.cpp` (desde root, incluye `fleet_notify.h` del root).

---

## 2. M1 — `scripts/v6_block.cpp.tmpl` (motor v6)

### 2.1 Placeholders y anclas (contrato con M2)

- Placeholders identicos a v5: `@SYM@` (prefijo env mayuscula, ej `NOK`) y `@sym@` (minuscula para rutas: `data/prob_table_@sym@.txt`).
- El bloque empieza con la linea marcador exacta:
  `// ==================== MOTOR v6 MTF (2026-07-16) ====================`
  y termina con:
  `// ==================== FIN MOTOR v6 ====================`
  (`apply_v6.py` usa estos literales para idempotencia y para futuras remociones).
- El bloque define UNA funcion publica de entrada: `static void v6_on_bar(const Bar& b, bool alert_hours, int H, int M);` que M2 engancha justo despues del hook v5 existente (`v5_on_bar(b, alert_hours, H, M);`).
- El bloque asume visibles (declarados antes en el bot): `struct Bar {double t,o,h,l,c,v;}` (o el equivalente del bot — verificar nombre real en dram_signal_bot.cpp y usar ese), `notify(title,msg,urgent)`, `play()`, `speak()`, `envd()/envs()`, ATR14 1m global del motor clasico si es accesible; si no, v6 mantiene su propio `V6ATR atr1m` (Wilder 14 sobre bars 1m) — **decision: v6 mantiene el suyo propio**, cero acoplamiento con nombres internos del motor clasico.

### 2.2 Structs nuevos (todo incremental, O(1)/bar, cero mallocs en hot path)

```cpp
// ATR Wilder generico
struct V6ATR { double atr=0, prev_c=0; int n=0, period=14;
  void add(double h,double l,double c){ double tr = n? std::max({h-l,fabs(h-prev_c),fabs(l-prev_c)}) : h-l;
    atr = (n<period)? (atr*n+tr)/(n+1) : (atr*(period-1)+tr)/period; prev_c=c; n++; } };

// ADX(14) Wilder — se alimenta con bars 15m CERRADOS (v5_tf15.closed)
struct V6ADX { double pdm=0,ndm=0,tr=0,adx=0,prev_h=0,prev_l=0,prev_c=0; int n=0;
  void add(double h,double l,double c); // Wilder smoothing 14; adx valido con n>=28
  bool trending(){ return n>=28 && adx>25.0; }
  bool ranging(){  return n>=28 && adx<20.0; } };  // 20-25 = zona muerta: ni breakout ni reversion

// BB extendida: %B + BandWidth + percentil de bandwidth (ring 125)
struct V6BBX { // envuelve una BB(20,2.0) propia sobre el TF que se le de
  double ring_close[20]; int rn=0, ri=0; double mid=0, up=0, dn=0;
  double bw_ring[125]; int bn=0, bi=0;
  void add(double c);                       // recalcula mid/up/dn (std poblacional, igual que V5BB)
  double pctB(double c){ return (up>dn)? (c-dn)/(up-dn) : 0.5; }
  double bandwidth(){ return (mid>0)? (up-dn)/mid : 0; }
  double bw_pctile();                       // % de valores del ring <= bandwidth actual (0-100)
  bool squeeze(){ return bn>=100 && bw_pctile()<=10.0; } };  // BB-4 research: bottom 10th pct de 100+ barras

// Supertrend(10, 3.0xATR) sobre bars 5m cerrados (v5_tf5) — filtro de regimen, JAMAS señal sola (COMBO-2)
struct V6ST { V6ATR atr{.period=10}; double st_up=0, st_dn=0; int dir=0; bool flip_up=false, flip_dn=false;
  void add(double h,double l,double c); };

// Swings 1m para pullback/reversal: pivots N=8 (fractal: high mayor que 8 a cada lado)
struct V6Swing {
  double hbuf[17], lbuf[17]; int n=0;       // ventana deslizante 2*8+1
  double swing_hi=0, swing_lo=0; double last_confirmed_low=0, last_confirmed_high=0;
  void add(double h,double l);              // confirma pivote con lag de 8 bars (anti-repaint, CALIB-3)
  // retroceso desde el ultimo swing_hi hacia abajo (para longs):
  double retr_dn(double c){ return (swing_hi>swing_lo)? (swing_hi-c)/(swing_hi-swing_lo) : 0; }
  double retr_up(double c){ return (swing_hi>swing_lo)? (c-swing_lo)/(swing_hi-swing_lo) : 0; }
  bool broke_last_low(double c){ return last_confirmed_low>0 && c<last_confirmed_low; }
  bool broke_last_high(double c){ return last_confirmed_high>0 && c>last_confirmed_high; } };

// Clasificador de fase de la sesion (evaluado en 10:00, re-evaluado 10:30; congelado despues)
struct V6Session {
  enum Phase { UNKNOWN=0, SPIKE_FADE, DIP_CLIMB, TREND_UP, TREND_DOWN, LATERAL };
  Phase phase=UNKNOWN;
  double prev_rth_close=0, open930=0, hi_0945=0, lo_0945=0;
  int bars_above_vwap=0, bars_below_vwap=0, bars_total=0;   // solo 9:30-10:30
  bool dipped_below_vwap=false, reclaimed_vwap=false; double reclaim_vol_ratio=0;
  double vwap_at_1000=0;
  void on_session_roll(double last_rth_close);              // 15:59 -> guarda prev_rth_close, resetea
  void on_bar(const Bar& b, int H,int M, double vwap, double volMA);
  Phase classify(double c, double vwap, double atr15, double or_hi, double or_lo); };

// Tabla de probabilidades por clase (calibrada por M3)
struct V6Prob {
  struct Row { char cls[40]; int n; int w; double wr; };
  Row rows[40]; int nrows=0; time_t last_load=0, last_mtime=0;
  void maybe_reload(const char* path);      // stat() cada 3600 s; formato en §4.2
  // prob final con shrinkage bayesiano hacia el prior (k=20): evita WR=100% con n=3
  double prob(const char* cls, double prior_pct){
    for(...) if(match) return 100.0*( (rows[i].w + (prior_pct/100.0)*20.0) / (rows[i].n + 20.0) );
    return prior_pct; } };
```

Globals nuevos: `V6ATR v6_atr1; V6ADX v6_adx15; V6BBX v6_bb5, v6_bb15; V6ST v6_st5; V6Swing v6_sw; V6Session v6_sess; V6Prob v6_prob;` + `time_t v6_last_fire_buy=0, v6_last_fire_sell=0; int v6_fires_today[N_CLASSES]={0};` + MACD 1m/15m: reutiliza `v5_macd1` y agrega `V5MACD v6_macd15;` alimentado con closes de `v5_tf15` (v5 ya tiene MACD15? — si el template v5 ya mantiene un MACD 15m, reusarlo; si solo tiene `v5_macd1`, v6 crea `v6_macd15`). Trendline 15m: `V5TL v6_tl15;` (pivots N=10, slope=ATR14_15m/14) alimentada con bars 15m cerrados.

### 2.3 Parametros env (todos via `envd("@SYM@_...")`, defaults entre parentesis)

`V6` (1 = activo), `V6_MIN` (6.0 — score minimo), `V6_COOL` (1800 s por lado), `V6_PROB_MIN` (55.0 — no se emite señal con prob < 55%), `V6_MAX_CLASS_DAY` (2 — señales max por clase y dia), `V6_RVOL` (1.5), `V6_RVOL_RECLAIM` (2.0), `V6_RETR_CONT` (0.50), `V6_RETR_REV` (0.62), `V6_SQUEEZE_PCT` (10.0), `V6_ADX_TREND` (25.0), `V6_ADX_RANGE` (20.0), `V6_OR_LATERAL` (1.2 — OR_height <= 1.2*ATR15 ⇒ candidato lateral), `V6_GAP_BREAKAWAY` (1.0 — gap/ATR15_prev>1.0 = breakaway, no fade).

### 2.4 Clasificador de fase (componente a) — criterios cuantitativos

Evaluado al cierre del bar de 10:00 ET; re-evaluado (puede cambiar) al cierre de 10:30; congelado despues. Antes de 10:00: `UNKNOWN` (solo clases que no dependen de fase). KRX: misma logica con su reloj KST (el bot ya pasa H,M correctos; ventana OR = 09:00-09:30 KST, evaluacion 09:30/10:00 KST — el template usa offsets relativos al primer bar de sesion, no horas literales US: `mins_since_open = (H*60+M) - session_open_min` donde `session_open_min` = 570 US / 540 KRX detectado por `@SYM@_KRX` env que `apply_v6.py` fija en 1 para kospi/samsung/skhynix).

Orden de decision (primero que matchea gana):
1. **DIP_CLIMB** (dip-and-rip, OPEN-6): `open930 > prev_rth_close` (gap-up, cualquier tamaño) Y `dipped_below_vwap` entre min 5-45 Y `reclaimed_vwap` (cierre 1m > VWAP tras el dip) con `reclaim_vol_ratio >= 2.0` (vol del bar de reclaim / volMA20).
2. **SPIKE_FADE** (OPEN-7): `hi_0945 > open930 + 0.5*ATR15` (spike inicial) Y luego >=3 bars 1m consecutivos con cierre < VWAP antes del min 45, sin reclaim.
3. **TREND_UP / TREND_DOWN** (OPEN-8, VWAP como regimen): >=80% de los bars 9:30-10:30 del mismo lado del VWAP Y `|c_1030 - vwap| > 0.5*ATR15`. Lado arriba ⇒ TREND_UP.
4. **LATERAL** (OPEN-7): `(or_hi - or_lo) <= V6_OR_LATERAL * ATR15` Y `|vwap_1030 - vwap_at_1000| < 0.25*ATR15` (VWAP plano) Y ADX15 no trending.
5. Si nada matchea: `UNKNOWN` (sin restriccion extra).

Gap context (OPEN-1): `gap_ratio = |open930 - prev_rth_close| / ATR15_prev_close`. Si `gap_ratio > V6_GAP_BREAKAWAY` ⇒ flag `no_fade=true` para el dia: se vetan las clases mean-reversion CONTRA la direccion del gap (los gaps >1.2xATR solo llenan ~8%).

Efecto de la fase sobre clases permitidas:
- `LATERAL`: veta SQUEEZE_BREAK, ORB, TLINE_BREAK (breakouts pierden en chop); permite MTF_BB_REV.
- `TREND_UP`: veta clases SHORT excepto TREND_REVERSAL; `TREND_DOWN` simetrico.
- `SPIKE_FADE`: veta longs hasta que haya reclaim de VWAP (si luego reclama ⇒ se re-clasifica DIP_CLIMB en la ventana 10:30).
- `DIP_CLIMB`: habilita VWAP_RECLAIM_LONG.

### 2.5 Detector pullback vs cambio de tendencia (componente b)

Contexto: hay "tendencia activa larga" si `v6_macd15` en {a_up, b_up} Y (`v6_st5.dir==+1` O fase TREND_UP). Simetrico para corta.

**PULLBACK (continuacion)** — en tendencia larga activa (PULLBACK-1/2):
- `retr = v6_sw.retr_dn(c)` desde ultimo swing_hi confirmado: `retr <= V6_RETR_CONT (0.50)`;
- HOLD: low del pullback `>= max(VWAP, BB15.mid) - 0.10*ATR15` (tolerancia una decima de ATR);
- gatillo 1m: `v5_macd1` transiciona a {b_up o a_up} (histograma girando) Y bar verde que supera el high del bar previo Y `vol >= 1.2*volMA20`.

**REVERSAL (cambio de tendencia)** — dispara cuando se cumplen **>=2 de estas 3** (PULLBACK-3), estando en tendencia larga:
1. `retr > V6_RETR_REV (0.62)` — estructura Fib rota; O `v6_sw.broke_last_low(c)` — higher-low de Dow roto;
2. flip del histograma MACD15: transicion a {a_dn} o cruce de cero del histograma contra la tendencia;
3. cierre 1m al otro lado de `BB15.mid` (SMA20 de 15m) tras band-walk (band-walk := `v6_bb15.pctB` estuvo >=0.9 durante >=3 bars 15m en los ultimos 10 bars 15m).

Reversal en tendencia larga ⇒ clase `TREND_REVERSAL_SHORT` (señal SELL); en corta ⇒ `TREND_REVERSAL_LONG` (BUY).

### 2.6 Trendlines (componente c)

- 1m: reutiliza `v5_tl` (LuxAlgo, pivots N=14, slope ATR14/14) — flags `up_break/dn_break`.
- 15m: nueva instancia `v6_tl15` (misma struct V5TL, pivots N=10, slope = ATR14_15m/14) alimentada con cada bar 15m cerrado.
- Clase TLINE_BREAK exige break 1m Y que la trendline 15m no este intacta EN CONTRA (es decir: para LONG, `!` (existe trendline bajista 15m por encima no rota a <0.5*ATR15 del precio)). Implementacion concreta: LONG permitido si `v6_tl15.up_break` reciente (<=3 bars 15m) O no hay linea bajista 15m activa.

### 2.7 BB multi-TF + squeeze + %B (componente d)

- Reutiliza la logica v5 de "BB reventada en >=2 TF" (`v5_bbN_dn/up_ago`: 1m <=3 bars, 5m <=2, 15m <=1) como componente de la clase MTF_BB_REV.
- Nuevo: `v6_bb5`/`v6_bb15` con %B y bandwidth-percentile. Regimen (BB-2/BB-3):
  - `v6_adx15.trending()` (ADX>25) ⇒ modo band-walk: `pctB>=0.9` sostenido = mantener sesgo largo, PROHIBIDO señal SELL por toque de banda superior;
  - `v6_adx15.ranging()` (ADX<20) ⇒ modo mean-reversion: `pctB<=0.1` + RSI>30 girando = candidato MTF_BB_REV_LONG. Si RSI<30 y cayendo: NO comprar (breakdown de momentum);
  - ADX 20-25: zona muerta, ninguna señal de origen BB.
- Squeeze (BB-4/BB-5): `v6_bb15.squeeze()` (bandwidth en percentil <=10 de 125 bars 15m). Fire = primer cierre 1m FUERA de la banda 15m tras squeeze, con `RVOL>=1.5`. Sin volumen no hay señal (58% WR con volumen vs 31% sin el).

### 2.8 MACD 4-color CM (componente e)

- `v6_macd15` (15m) = CONTEXTO: estados a_up/b_up = solo BUY permitido por clases trend; a_dn/b_dn = solo SELL. (reusa struct V5MACD.)
- `v5_macd1` (1m) = GATILLO: la transicion de estado (ej b_dn→b_up o cruce señal) es el timing de entrada de las clases TREND_PULLBACK y VWAP_RECLAIM.
- **Regla dura "15m manda"**: `v6_veto_buy = (v6_macd15 en a_dn) || (c < VWAP && v6_st5.dir==-1)`. Ninguna clase BUY dispara con veto activo, EXCEPTO `MTF_BB_REV_LONG` que solo exige `v6_adx15.ranging()` (reversion pura en rango). Simetrico para SELL.

### 2.9 Clases de señal (enum cerrado — el contrato con M3 y la tabla de prob)

```cpp
enum V6Class { TREND_PULLBACK_LONG, TREND_PULLBACK_SHORT,
               VWAP_RECLAIM_LONG,  VWAP_LOSS_SHORT,
               SQUEEZE_BREAK_LONG, SQUEEZE_BREAK_SHORT,
               ORB_LONG,           ORB_SHORT,
               MTF_BB_REV_LONG,    MTF_BB_REV_SHORT,
               TLINE_BREAK_LONG,   TLINE_BREAK_SHORT,
               TREND_REVERSAL_LONG, TREND_REVERSAL_SHORT, V6_N_CLASSES };
static const char* V6_CLS[] = {"TREND_PULLBACK_LONG", ...};   // nombres EXACTOS, parseados por M3/M4
```

Priors (fallback si no hay tabla; de la evidencia web, conservadores):

| Clase | Prior % | Base research |
|---|---|---|
| TREND_PULLBACK_* | 62 | PULLBACK-2: 64% con alineacion multi-TF |
| VWAP_RECLAIM_LONG / VWAP_LOSS_SHORT | 60 | OPEN-6/OPEN-8 |
| SQUEEZE_BREAK_* | 56 | BB-4: 58% con RVOL; recortado por TF intradia (BB-6) |
| ORB_* | 53 | OPEN-5: 52-53% (edge en filtros) |
| MTF_BB_REV_* | 55 | BB-7 + COMBO-1 |
| TLINE_BREAK_* | 55 | COMBO-4 |
| TREND_REVERSAL_* | 55 | PULLBACK-3 |

Condiciones completas por clase (todas exigen `alert_hours` y bar 1m cerrado; ventana de entradas: `mins_since_open` entre 5 y 330 — SIN ningun flatten/cierre programado, ver §7):

1. **TREND_PULLBACK_LONG**: tendencia larga activa (§2.5) + ADX15>25 + pullback valido (retr<=0.50, hold VWAP/BB15mid) + gatillo MACD1 + RVOL>=1.2. SHORT espejo.
2. **VWAP_RECLAIM_LONG**: fase DIP_CLIMB + cruce 1m sobre VWAP con vol>=2.0*volMA20 + antes del min 120 de sesion. **VWAP_LOSS_SHORT**: fase SPIKE_FADE + 3er cierre consecutivo bajo VWAP con vol>=1.5*volMA20 + MACD15 no alcista.
3. **SQUEEZE_BREAK_LONG**: `v6_bb15.squeeze()` activo en los ultimos 5 bars 15m + primer cierre 1m > BB15.up + RVOL>=1.5 + MACD15 no en a_dn. SHORT espejo (cierre < BB15.dn, MACD15 no a_up).
4. **ORB_LONG**: min 30-120 de sesion + cierre 1m > `v5_or_hi` + RVOL>=1.5 + c>VWAP + fase != LATERAL + (gap a favor o sin gap breakaway en contra). SHORT espejo bajo `v5_or_lo` y c<VWAP.
5. **MTF_BB_REV_LONG**: BB reventadas abajo en >=2 TF (logica v5) + bar verde de confirmacion + RSI14_1m>30 y subiendo + ADX15<20 + no `no_fade` contra el gap. SHORT espejo (RSI<70 y bajando, reventadas arriba).
6. **TLINE_BREAK_LONG**: `v5_tl.up_break` (1m) + condicion 15m (§2.6) + RVOL>=1.5 + c>VWAP. SHORT espejo.
7. **TREND_REVERSAL_SHORT/LONG**: detector §2.5 (>=2 de 3). No requiere RVOL (es aviso de estructura), pero exige prob>=V6_PROB_MIN como todas.

### 2.10 Score de calidad (gate secundario) y disparo

`score` (max 10) suma sobre la clase candidata: +2 condicion nuclear de la clase (siempre presente), +1 MACD15 alineado, +1 supertrend5 alineado, +1 `v5_rib` (ribbon 15m) alineado (|score|>0.2), +1 lado correcto del VWAP, +1 RVOL>=2.0 (extra sobre el minimo), +1 whale a favor (`whale_score>0.3`, solo live), +1 fase de sesion favorable, +1 trendline a favor. Dispara si `score >= V6_MIN (6.0)`.

Anti-lookahead (CALIB-3): TODO se decide con el bar 1m **cerrado**; la señal se emite al cierre del bar, nunca intrabar.

Cooldown y limites: `now - v6_last_fire_<lado> >= V6_COOL` Y `v6_fires_today[cls] < V6_MAX_CLASS_DAY`. Si BUY y SELL califican en el mismo bar: gana el de mayor `prob`; empate ⇒ silencio.

`prob = v6_prob.prob(V6_CLS[cls], prior[cls])` con reload de `data/prob_table_@sym@.txt` (§4.2). Si `prob < V6_PROB_MIN (55)` ⇒ NO se emite.

### 2.11 Formato de salida (contrato con mirror, M3 y M4 — NO desviarse ni un caracter)

stdout (siempre, tambien en replay `--stdin`; parseado por `v6_backtest.py`):
```
[HH:MM] *** @SYM@ V6 BUY *** prob 68% clase TREND_PULLBACK_LONG score 7.0 <razones> t=1784201400
[HH:MM] *** @SYM@ V6 SELL *** prob 61% clase SQUEEZE_BREAK_SHORT score 6.5 <razones> t=1784205000
```
`<razones>` = 2-5 tokens unidos por `+`, sin espacios, whitelist sh_sanitize: ej `pullback-38%+MACD15-verde+sobre-VWAP+RVOL-2.1x`, `squeeze-p7+cierre-fuera-BB15+vol-1.8x`.

notify (solo live, gated por edad de bar como v5): titulo EXACTO `@SYM@: BUY` o `@SYM@: SELL` (nada de CALL/PUT — ley). Mensaje:
```
@SYM@ @ 123.45 | prob 68% | pullback-38%+MACD15-verde+sobre-VWAP | fase=TREND_UP
```
Audio: `play()` con dram_buy.wav/dram_sell.wav + `speak("buy @HUMANNAME@ now, probability 68 percent")` (nombre humano lo inyecta apply_v6.py como en v5). Con esto la linea del mirror queda:
```
10:41:03 | NVDA: BUY | NVDA @ 123.45 | prob 68% | pullback-38%+MACD15-verde+sobre-VWAP | fase=TREND_UP
```

### 2.12 Presupuesto de rendimiento

Replay: <=10 us/bar añadidos por v6 (v5 esta en ~5 us/bar). Cero heap en hot path (buffers fijos). Un bot live = mismo footprint actual + ~40 KB.

---

## 3. M2 — `scripts/apply_v6.py` + despliegue a los 20 bots

Lista BOTS = identica a `apply_v5.py` (20: aapl amd asml cper dram gld intc kospi nok nvda qqq samsung skhy skhynix slv spcx tsla tsm txn uso).

Pasos por bot (idempotente — salta si `MOTOR v6` ya presente):
1. Detectar prefijo env con la regex de apply_v5 (`envd\("([A-Z]+)_BB_STD`) y nombre humano de voz desde `speak("buy X now")`.
2. Insertar el bloque v6 (con @SYM@/@sym@ sustituidos) INMEDIATAMENTE DESPUES de la linea `// ==================== FIN MOTOR v5` si existe; si el template v5 no tiene marcador de cierre, insertar ANTES del ancla `// ---- cierre seguro: SIGTERM/SIGINT` (misma ancla que apply_v5 — el bloque v6 queda despues del v5 automaticamente porque apply_v5 ya corrio).
3. Insertar el hook `        v6_on_bar(b, alert_hours, H, M);   // motor v6 (2026-07-16)` en la linea siguiente al hook v5 existente (`v5_on_bar(b, alert_hours, H, M);`).
4. Neutralizar disparo v5: reemplazar el default `5.0` de `V5_MIN` por `99.0` (regex `envd\("([A-Z]+)_V5_MIN",\s*5\.0\)` → `envd("\1_V5_MIN", 99.0)`).
5. **Eliminar flatten programado** (requisito 6): localizar el branch EOD del motor clasico (flatten 15:45, y cualquier venta forzada 15:30/15:50) y envolverlo en `if (envd("@SYM@_EOD_FLATTEN", 0) > 0.5) { ... }` — default 0 = NUNCA venta programada por reloj. Idem para el lado corto. El time-stop (TIME_STOP_MIN) se conserva (es por duracion de posicion virtual, no por hora de reloj).
6. Renames residuales de titulos (si quedara alguno que apply_v5 no cubrio): `BUY CALL`→`BUY`, `BUY PUT`→`SELL`, `PUT-STOP`→`BUY (STOP)`, `SELL-STOP`→`SELL (STOP)`, `BUY NOW`→`BUY`, `SELL NOW`→`SELL`. (El mirror de 2026-07-15 aun muestra `BUY CALL`/`PUT-STOP` ⇒ hay bots corriendo binarios viejos: recompilar TODOS es obligatorio.)
7. Marcar bots KRX: para kospi/samsung/skhynix, el bloque insertado lleva `#define V6_KRX 1` (o env `@SYM@_KRX=1` exportado en sus keepalives) para `session_open_min=540`.
8. Compilar SECUENCIAL: `clang++ -std=c++17 -O2 -o <sym>_signal_bot <sym>_signal_bot.cpp`; abortar todo al primer error.
9. Smoke replay: `printf` 500 bars sinteticos por `--stdin` y verificar exit 0 y cero señales malformadas.

Keepalives: añadir a cada `scripts/<sym>_keepalive.sh` los exports v6 que difieran del default (minimo: nada — defaults del template valen; el WFO de M3 escribira overrides). NO tocar parametros clasicos existentes.

`scripts/fleet_keepalive_start.sh`: añadir (idempotente via pgrep) el lanzamiento de `bin/price_alarm >> price_alarm.log 2>&1 &` y `scripts/options_enrich_keepalive.sh &`. Si los binarios/scripts aun no existen (M4/M5 en curso), dejar las 2 lineas añadidas pero protegidas con `[ -x bin/price_alarm ] &&` / `[ -f scripts/options_enrich.py ] &&`.

---

## 4. M3 — Backtest, calibracion de prob y walk-forward (`scripts/v6_backtest.py`)

### 4.1 Motor de evaluacion

- Datos: `data/bt_<sym>.txt` (formato bot `EPOCH O H L C V`, ~90 dias disponibles para 16 US). Ventana de calibracion: **ultimos 30 dias de sesiones** por ticker (recorte por epoch). PROHIBIDO Alpaca fetch nuevo (guardia NO-ALPACA vigente) y PROHIBIDO Yahoo. Si un ticker no tiene bt_*.txt (kospi/samsung/skhynix/slv?): usar `data/bars_<sym>*.txt` acumulado si cubre >=15 sesiones; si no, el ticker queda con priors (tabla ausente = fallback, es un estado valido).
- Replay: correr `<sym>_signal_bot --stdin < recorte` en **tmpdir aislado** (como backtest_replay.py, para no pisar `data/pos_*.txt` ni `data/prob_table_*.txt` vivos) con env identico al keepalive de produccion (`load_keepalive_env` de fleet_backtest_audit.py) + los V6 por defecto. SECUENCIAL, un ticker a la vez.
- Parseo: regex sobre stdout `\*\*\* (\w+) V6 (BUY|SELL) \*\*\* prob (\d+)% clase (\w+) score ([\d.]+) (\S+) t=(\d+)`.
- **Outcome (triple-barrier simplificado, identico para todas las clases y para train/OOS — CALIB-2 exige procedimiento fijado ex-ante)**: desde el open del bar siguiente a la señal: WIN si el precio toca `entry + 0.75*ATR14_1m` (BUY) antes de tocar `entry - 0.75*ATR14_1m`; LOSS al reves; si en `V6_HORIZON_MIN=60` minutos no toca ninguna: WIN si el close a horizonte > entry (BUY), si no LOSS. Barras ambiguas (toca ambas en el mismo bar 1m): LOSS (pesimista). SELL espejo. ATR14_1m lo recalcula el harness sobre el mismo stream (misma formula Wilder).

### 4.2 Tabla de probabilidades — formato de `data/prob_table_<sym>.txt` (contrato con M1)

```
# v6 prob table nvda | generado 2026-07-16 por v6_backtest.py | train 2026-06-01..2026-06-24 (60%)
TREND_PULLBACK_LONG 41 28 68.3
SQUEEZE_BREAK_SHORT 12 7 58.3
...
```
Una linea por clase observada: `CLASE n wins wr_pct` separados por UN espacio. Lineas `#` = comentario. El bot aplica shrinkage k=20 hacia el prior (§2.2) — la tabla guarda datos crudos, el bot calcula la prob mostrada. **Solo las clases con n>=20 en TRAIN dominan de facto** (el shrinkage se encarga del resto; CALIB-2: 50-100 trades para WR util).

### 4.3 Walk-forward simple 60/40

- Split temporal por ticker: primeras 60% de sesiones = TRAIN, ultimas 40% = OOS (mismo prefijo deterministico que fleet_wfo.py).
- La tabla se construye SOLO con TRAIN. Luego se evalua OOS con la tabla congelada.
- Gates de aceptacion por clase-ticker (para que la clase quede "calibrada" y no en prior): `n_train>=20` Y `WR_train>=55%` Y en OOS `n_oos>=5` Y `WR_oos >= 0.5*WR_train` (analogo WFE>=0.5, CALIB-1). Clase que falla OOS ⇒ se escribe en la tabla con un `#FAIL_OOS` al final de la linea y el bot la ignora (trata como prior) — regla de parseo: si la linea contiene `#FAIL_OOS`, skip.
- Parametros libres a explorar: MAXIMO 3 (CALIB-1): `V6_MIN ∈ {5.5, 6.0, 6.5}`, `V6_RVOL ∈ {1.3, 1.5, 1.8}`, `V6_RETR_CONT ∈ {0.45, 0.50, 0.55}` — grid 27 combos, seleccion en TRAIN por expectancy, test de meseta (vecinos ±1 conservan >=40% del edge, como fleet_wfo), validacion OOS. Overrides ganadores se escriben a `data/v6_wfo_report.txt` en formato `SYM export NVDA_V6_MIN=6.0` (mismo estilo fleet_wfo_ship) — Yunior decide si se copian a keepalives.
- Reporte final `data/v6_wfo_report.txt`: por ticker y clase: n/WR/PF train y OOS, veredicto CALIBRADA/PRIOR/FAIL_OOS; resumen de flota al final.
- Regenerar tablas: cadencia semanal (manual o cron), siempre regenerando desde cero con la ventana movil de 30d.

---

## 5. M4 — Overlay de opciones: `scripts/options_enrich.py`

**SOLO LECTURA. `IB.connect(..., readonly=True)`. El script NO importa ni llama NADA de ordenes. Cero `placeOrder`.** Python permitido porque ib_insync lo exige (nota: ib_insync archivado 2024-03; si `import ib_insync` falla, usar `ib_async` — API identica).

- Conexion: `127.0.0.1:7496` (TWS live, datos reales — jamas delayed: `reqMarketDataType(1)`), `clientId=87` (84/83 ocupados por ibkr_bar_bridge), `readonly=True`.
- Input: tail -F del mirror del dia `~/Desktop/trading-signals/YYYY-MM-DD.txt` (rota a medianoche). Trigger: linea cuyo campo titulo sea exactamente `<SYM>: BUY` o `<SYM>: SELL` (split por ` | `, campo 2). Ignorar `(STOP)`, `WARMUP`, `OPT`, `ALARMA`, `TERREMOTO`, `SIN DATOS`. Dedupe: 1 enriquecimiento por (SYM, lado) por 30 min.
- Solo tickers US con opciones (mapear `dram`→`MU`? NO: el simbolo del mirror ya es el ticker del bot; tabla interna SYM_MAP = {DRAM: MU, SKHY: opcion no-US ⇒ skip, KOSPI/SAMSUNG/SKHYNIX: skip, GLD/SLV/QQQ/USO/CPER: ok, resto: literal}). Ventana horaria: 9:35-15:00 ET; fuera de ella el veredicto es `NO-APTO-HORA` (los ultimos 30-60 min son el peor periodo risk-adjusted en 0DTE).
- Pipeline por señal (tecnica verificada, notebook oficial option_chain.ipynb):
  1. `qualifyContracts(Stock(sym,'SMART','USD'))`; spot via `reqTickers`.
  2. `reqSecDefOptParams(sym,'',secType,conId)` → chain SMART tradingClass==sym; `expiry = min(expirations)` con DTE 0-2 (si el mas cercano es >2 DTE, usarlo igual y anotarlo).
  3. Strikes en ±5% del spot; right = 'C' si BUY, 'P' si SELL.
  4. `reqMktData(opt, genericTickList='100,101,106')`, `ib.sleep(4)`; elegir el strike con `|modelGreeks.delta|` mas cercano a **0.55** dentro de [0.40, 0.70].
  5. Gates (research §webOptions): `0.40<=|delta|<=0.70`; `spread_pct=(ask-bid)/mid <= 3.0%` (relajar a 5% si sym no es QQQ/SPY-like — configurable `OPT_SPREAD_MAX`); `volume >= 500` contratos hoy en el strike; `OI >= 1000` (si OI<100 ⇒ NO-APTO duro); IV del contrato anotada (IV rank no computable sin historial ⇒ solo warning si `impliedVol > 0.90`).
  6. Veredicto: `APTO same-day` si TODOS los gates pasan; si no `NO-APTO (razon-principal)`.
- Output: append (O_APPEND, una linea) al MISMO mirror del dia + a `data/options_enrich.log`:
```
10:41:09 | NVDA: OPT | C 2026-07-17 124 | delta 0.56 gamma 0.041 theta -0.32 IV 43% | OI 5210 vol 2140 spread 1.8% | APTO same-day
10:41:09 | GLD: OPT | P 2026-07-17 224 | delta -0.51 gamma 0.09 theta -0.15 IV 18% | OI 340 vol 120 spread 6.2% | NO-APTO (spread 6.2% > 3%)
```
- Robustez: si TWS caido ⇒ log y reintento 60 s (no crashear); timeouts 10 s por request; `ib.disconnect()` limpio. `scripts/options_enrich_keepalive.sh` = patron estandar (pgrep, relaunch cada 30 s, log `options_enrich.log`).

---

## 6. M5 — Alarmas de precio (`scripts/price_alarm.cpp`) + sirena + limpieza

### 6.1 Formato de `~/Desktop/price-alerts.txt` (el humano escribe a mano)

```
nvda 215            # dispara al TOCAR 215 desde cualquier lado (cruce)
intc 100 down       # dispara cuando precio <= 100
tsla 550 up         # dispara cuando precio >= 550
# lineas con # = comentario; lineas ya disparadas quedan prefijadas: FIRED 2026-07-16 10:33 | intc 100 down
```
Parser tolerante: `sym precio [up|down]`, case-insensitive, espacios multiples ok, lineas invalidas se ignoran con log. Sin direccion ⇒ modo cruce: se arma con el primer precio leido (si arranca por encima ⇒ down, por debajo ⇒ up).

**Pre-seed obligatorio**: si el archivo no existe, crearlo; garantizar (idempotente) que contiene la linea activa `intc 100 down` (alerta urgente de Yunior).

### 6.2 Watcher `scripts/price_alarm.cpp`

- Compilar desde el root: `clang++ -std=c++17 -O2 -o price_alarm scripts/price_alarm.cpp`. `#include "fleet_notify.h"` (root) para banner + mirror.
- Loop 1 Hz: releer `~/Desktop/price-alerts.txt` (stat mtime, re-parse si cambio); por cada alerta armada, precio actual = mid de `data/nbbo_<sym>.txt` (`EPOCH BID ASK`, valido si edad<=10 s) → fallback close del ultimo bar de `data/bars_<sym>_ibkr.txt` (edad<=180 s) → fallback `data/bars_<sym>.txt`. Sin dato fresco ⇒ skip silencioso (log 1 vez/10 min).
- Disparo: (a) **SIRENA**: `system("for i in 1 2 3; do afplay sounds/fire_alarm.wav; done &")` + `say -v Daniel -r 170 'ALARMA DE PRECIO: <sym> toco <precio>'` (frase sh_sanitized); (b) mirror + banner via `fleet_notify_urgent("<SYM> ALARMA PRECIO", "<SYM> toco 100.00 (regla: intc 100 down) px=99.97")` → linea mirror `10:33:07 | INTC ALARMA PRECIO | INTC toco 100.00 (regla: intc 100 down) px=99.97`; (c) marcar la linea en el archivo como `FIRED YYYY-MM-DD HH:MM | <linea original>` (rewrite atomico: tmp + rename) — re-armar = el humano borra el prefijo. Anti-rafaga: una alerta dispara UNA vez.
- Ley: el watcher SOLO lee archivos y emite audio/banner/mirror. Cero red, cero TWS, cero ordenes.

### 6.3 `sounds/fire_alarm.wav` — `scripts/make_fire_alarm.py`

Python stdlib (`wave`, `math`, sin deps): 44100 Hz, 16-bit mono, 2.5 s, sirena barrido 600→1200→600 Hz (onda cuadrada suavizada o senoidal con vibrato 6 Hz), amplitud 0.85. Correr una vez: `python3 scripts/make_fire_alarm.py` ⇒ escribe `sounds/fire_alarm.wav`. Verificar con `afplay sounds/fire_alarm.wav`.

### 6.4 Limpieza (requisito 6) — cambios exactos

- `screener/start_all.sh`: borrar lineas 4-10 (comentarios de watchdog/claude_trader_loop/exec_trade), 21-26 (pkill de watchdog_keepalive/screener_watchdog/claude_trader_loop), 29-30 (nohup watchdog_keepalive.sh), 39-44 (lanzamiento claude_trader_loop.sh), 56-59 (executor_keepalive.sh). Dejar solo: screener_alert + fastscan/rescan si aplican. Unificar lista IBKR daemon a la de fleet_keepalive_start.sh (17 syms CON SKHY).
- `screener/ensure_all.sh`: borrar lineas 22-25 (watchdog_keepalive), 36-45 (logica claude_trader_loop), 59-63 (executor_keepalive). Linea 17: eliminar `SCREENER_LIVE=1` por defecto — el modo es SIEMPRE señal-only, sin flags de armado. Unificar lista a 17 syms.
- `screener/test_screener.py`: eliminar el bloque que importa/usa `exec_trade` (lineas 44-75); el resto de tests debe pasar.
- Verificacion global (gate G6, §8): `grep -RniE 'watchdog_keepalive|claude_trader_loop|exec_trade|executor_keepalive|fleet_executor|screener_watchdog' screener/*.sh scripts/*.sh` ⇒ 0 hits (fuera de backup/). Y `grep -RniE 'placeOrder|\.placeOrder|order\(' scripts/price_alarm.cpp scripts/options_enrich.py` ⇒ 0 hits de ordenes.
- Flatten: tras `apply_v6.py` (M2 paso 5), `grep -n "15:45\|EOD" *_signal_bot.cpp` debe mostrar el branch gated por `EOD_FLATTEN` default 0. Ninguna venta programada 15:30/15:45/15:50 activa por defecto en NINGUN archivo vivo.
- Nota (no bloqueante, dejar TODO en el reporte): plist roto `scripts/com.ibtrader.dram` (referencia run_dram_bot.sh inexistente) — candidato a `launchctl unload` + borrar.

---

## 7. Reglas transversales (aplican a TODOS los modulos)

1. **Señal-only**: ningun modulo escribe a sockets de ordenes. options_enrich es readonly=True. Los unicos escritores de red permitidos son los bridges existentes (lectura de datos).
2. **Titulos de notify**: solo `SYM: BUY`, `SYM: SELL`, `SYM: BUY (STOP)`, `SYM: SELL (STOP)`, `SYM: OPT`, `SYM ALARMA PRECIO`, `SYM TERREMOTO ...`, `SYM: SIN DATOS IBKR`. Nada de CALL/PUT en titulos.
3. **Mirror**: todo evento visible al humano pasa por `fleet_notify_urgent` (o append O_APPEND con el mismo formato `HH:MM:SS | TITULO | MSG`) a `~/Desktop/trading-signals/YYYY-MM-DD.txt`.
4. **Sin flatten por reloj**: ninguna señal de venta generada por hora del dia. Las salidas del motor clasico (stop/target/trail/time-stop por duracion) se mantienen; el EOD queda apagado por defecto.
5. **stdout de backtest**: los literales `COMPRAR/VENDER/PUT/VENDER PUT` del motor clasico NO se tocan (los parsers viejos dependen de ellos). v6 añade sus propias lineas `V6 BUY/SELL`.
6. **8GB RAM**: compilar y backtestear en serie. Jamas 2 clang++ o 2 replays simultaneos.
7. **Determinismo**: mismo input `--stdin` + mismo env ⇒ stdout byte-identico (v6 no usa reloj de pared en replay: `now` = epoch del bar, como v5).

---

## 8. Criterios de aceptacion (gates de cierre — todos deben pasar)

- **G1 (compila)**: los 20 bots compilan sin warnings nuevos con el comando canonico; `price_alarm` compila; `options_enrich.py` pasa `python3 -m py_compile`.
- **G2 (determinismo)**: `md5` del stdout de 2 replays identicos de `dram_signal_bot --stdin < data/bt_dram.txt` coincide; y coincide con el pre-v6 en las lineas clasicas (v6 solo AÑADE lineas).
- **G3 (contexto manda)**: en replay de 30d, CERO señales `V6 BUY` emitidas con MACD15 en a_dn, y CERO `V6 SELL` con MACD15 en a_up (excepto clases MTF_BB_REV con ADX15<20 y TREND_REVERSAL). Verificable con un flag debug `V6_DEBUG=1` que imprime el estado 15m junto a cada señal.
- **G4 (prob)**: toda señal emitida lleva `prob NN%` con NN>=V6_PROB_MIN; con tabla presente, la prob impresa = shrinkage(tabla, prior) a ±1%; sin tabla, prob = prior de la clase.
- **G5 (calibracion)**: `v6_backtest.py all` corre los 16 US secuencialmente sin errores, genera `data/prob_table_*.txt` + `data/v6_wfo_report.txt`; >=1 clase CALIBRADA (n_train>=20, OOS gate) en >=6 tickers; ninguna clase calibrada con WR_oos < 0.5*WR_train sin marca `#FAIL_OOS`.
- **G6 (ley/limpieza)**: greps de §6.4 en cero; `grep -RniE 'placeOrder|reqIds|whatIf' *_signal_bot.cpp scripts/v6_block.cpp.tmpl scripts/price_alarm.cpp scripts/options_enrich.py` ⇒ 0.
- **G7 (mirror end-to-end)**: en paper/live con TWS arriba: una señal v6 real o inyectada (bar sintetico) produce en el mirror la linea `SYM: BUY | ... prob ...` y, <=60 s despues, la linea `SYM: OPT | ...` del enriquecedor.
- **G8 (alarma)**: test sintetico — escribir `data/nbbo_test.txt` con precio que cruza una alerta `test 100 down` ⇒ sirena suena (3x afplay), linea `TEST ALARMA PRECIO` en el mirror, y la linea del archivo queda `FIRED ...`. La alerta pre-sembrada `intc 100 down` esta presente y armada.
- **G9 (no regresion live)**: tras redeploy, 1 sesion completa sin crash de ningun bot (keepalives no reinician en loop), CPU/RAM del fleet dentro del rango previo (±15%).
- **G10 (sin flatten)**: replay de un dia completo con posicion virtual abierta a las 15:44 ⇒ NINGUNA linea de venta a las 15:45 con defaults.

---

## 9. Plan de ejecucion (secuencia)

1. **M5** y **M4** arrancan ya (contratos cerrados). M5 entrega sirena+watcher+limpieza; M4 entrega enrichment (testeable contra el mirror de hoy aunque v6 no exista: reacciona a titulos `SYM: BUY` actuales).
2. **M1** entrega `v6_block.cpp.tmpl` + un mini `main` de prueba unitaria propio (archivo temporal en scratchpad, no en el repo) que alimenta bars sinteticos y verifica clasificador/pullback/squeeze.
3. **M2** aplica a dram primero (bot de referencia), compila, G2/G3 sobre dram; luego rollout a los otros 19, compilacion secuencial, hook en fleet_keepalive_start.sh.
4. **M3** corre calibracion 30d + WFO 60/40 secuencial (16 US), genera tablas y reporte; Yunior revisa `data/v6_wfo_report.txt` y decide overrides de keepalive.
5. Gates G1-G10; redeploy de flota (pkill via keepalives, que ya relanzan solos).
