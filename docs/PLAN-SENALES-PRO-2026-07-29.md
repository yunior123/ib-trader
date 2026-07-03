# PLAN-SENALES-PRO-2026-07-29

## ANÁLISIS DE SEÑALES ACTUALES

### 1. SEÑALES IMPLEMENTADAS (mapeo fichero:línea)

#### A. **Compass (la flecha/brújula)**
- **Fichero**: `scripts/compass.cpp` (1465 líneas)
- **Qué mide**: Máquina de 5 estados que determina dirección (REVERSIÓN vs CONTINUACIÓN vs APROXIMANDO vs CAJA/PIN vs SIN_LECTURA)
- **Factores**:
  - Walls (muros OI put/call): `jnum("wall_*")` desde `charts/data/levels_<sym>.json`
  - Bollinger %B (sobreventa/sobrecompra): `PCTB_HI=0.85, PCTB_LO=0.15`
  - Flip de gamma (POS/NEG): lectura de `charts/data/levels_<sym>.json`
  - Momentum combustible (z-score EWMA de retorno 1m): satura en `FUEL_SAT=2.5`
  - Flujo del capitán (SPY/QQQ/SMH): `FLOW_MIN=0.25` umbral
  - Fleet bias (dirección consenso de los 30): `charts/data/fleet_bias.json`
  - Imán estructural (SMA20): `APPROACH_EM=0.35` para proximidad
  - Expected move residual: `em_left = em_total * (1 - EM_CONSUMED%)`
- **Print**: Exige PRINT_MIN=2 lecturas en PRINT_LOOKBACK=8 barras (regla 2)
- **Histéresis**: HYST_N=2 computos consecutivos para cambiar de estado
- **Salida**: `data/compass_<sym>.json` (JSON diagnóstico, SEÑAL-SOLAMENTE)
- **Calibración**: `data/compass_calib.json` (1379 muestras, CONTINUACION|f0|NEG n=1009 wr15=50.35%, NEG regime es el más poblado)
- **Probabilidades**: Capped a DOCTRINE_CAP=78% si fuente es "doctrina" (no "medido")
- **Problema detectado**: 
  - Veto V3 "spot bajo VT congelado" está hardcodeado pero NO se verifica si VT (Value Trap nivel) existe en `levels_<sym>.json`
  - Amplitud usa "room" del siguiente nivel pero jamás verifica si atraviesa un Muro intermedio

---

#### B. **Flow Pulse (spikes de flujo de opciones)**
- **Fichero**: `scripts/flow_pulse.cpp` (557 líneas)
- **Qué mide**: Detecta cambios DRÁSTICOS en volumen de calls/puts
- **Señales**:
  - 🚀 SPIKE CALLS: `rc >= SPIKE_X * ema_c && dc >= SPIKE_MIN` → rebote BAJA (prob=59% base)
  - 🚀 SPIKE PUTS: `rp >= SPIKE_X * ema_p && dp >= SPIKE_MIN` → rebote ALZA (prob=78% base, "la joya")
  - 🧱 EN EL MURO: spike + spot <=WALL_PCT=0.4% de muro top-3 OI → refuerzo (prob propia en calibración)
  - 🔄 GIRO: ratio P/C rota GIRO_ABS=0.08 absolute + GIRO_REL=1.30x relativo
  - 🐺 MANADA: >=MANADA_N=3 tickers en MANADA_W=720s (12 min) → extremo mercado (DANGER)
  - 🎖 CAPITAN REVIERTE: spike del capitán (SPY/QQQ/SMH) tras spikes opuestos de su tropa <=CAPT_W=1200s
- **Veto band-walk**: si BB(20,2) camina >=2 TF a favor del movimiento → el spike se veta (continuación, no fade)
- **Anti-artefacto**: spike bilateral o ratio>50x (relleno del feed) = mudo
- **Anti-crying-wolf**: cooldown 600s sym+tipo; DANGER solo manada (30 min)
- **Fuente**: `data/whale_flow_hist.jsonl` (tailing en tiempo real, 300s/símbolo)
- **Salida**: voz + banner + ledger `data/trading-signals/<fecha>.txt`
- **Calibración**: `data/flow_pulse_probs.json` (SPIKE_PUTS|normal/muro/override, SPIKE_CALLS idem — auto-calibradas cada tarde por flow_pulse_calibrate.py)
- **Problemas**:
  - Override_note usa captains_of() que es STATELESS — no memoriza si el capitán ha cambiado dirección recientemente (ej: SPY calls a 13:02, puts a 14:20)
  - Manada cuenta TODOS los spikes (vetados o no) en herd_add(), pero el banner no distingue si fue veto o no

---

#### C. **Fleet Consensus (alarma de manada, C++)**
- **Fichero**: `scripts/fleet_consensus.cpp` (649 líneas)
- **Qué mide**: % de flota (data/fleet.txt, 30 símbolos) de acuerdo en dirección vía gamma-flip
- **Lógica**:
  - Cada símbolo vota por el lado del flip (POS/NEG) de su `charts/data/levels_<sym>.json`
  - MIN_COVER=0.90: <90% cobertura → "cobertura insuficiente", sin veredicto (degradación honesta)
  - MAX_BAR_AGE=180s: barras rancias no votan
  - Consensus: >= FLEET_CONS_PCT=78% de la flota → voz DANGER + banner
  - Ventana: FLEET_CONS_WIN_OPEN=9:25, FLEET_CONS_WIN_CLOSE=16:05
  - Capitanes SPY/QQQ/SMH deben ser UNANIMES
  - Histéresis: HYST_N=2 ciclos consecutivos para disparar
- **Salida**: voz + banner (via fleet_notify.h posix_spawn) + ledger
- **Problema crítico**:
  - Depende de `charts/data/levels_<sym>.json` que NO se refresca en bucle (chart_bridge.py solo regenera el símbolo del chart en memoria, no fichero)
  - Sin refresco <=180s frecuente, el binario dirá "cobertura insuficiente" para siempre (silencio honesto pero no operativo)
  - **FIX PENDIENTE**: poner chart_levels.py a escribir la flota en bucle (4am calibración, 8:30 refresh, 9:12 apertura, cada 5s RTH)

---

#### D. **Direction View (flecha compuesta, Python)**
- **Fichero**: `scripts/direction_view.py` (415 líneas)
- **Qué mide**: Media ponderada de factores para una flecha sobrepuesta en el chart
- **Factores** (con pesos en `scripts/direction_view.py:compute()`):
  - Gamma flip + régimen (POS/NEG)
  - Muros call/put + POC (punto de control)
  - GEX net + dealer pressure
  - Dirección flota (signal_conditioning.fleet_bias)
  - Momentum 1m
  - Inflación (inflation_score)
  - Imán estructural (narrator.structural_signal)
- **Probabilidades**: bucket "direction_view|<regime>" en `data/calibration.json` (si n>=CALIB_MIN_N=20)
- **Problema**:
  - La media ponderada DILUYÓ la reversión: el ejemplo en compass.cpp muestra -2.68/9.65=-0.278 (abajo 61%) cuando la doctrina cantaba REBOTE
  - Compass.cpp REEMPLAZA esta lógica con máquina de estados, pero direction_view.py SIGUE USÁNDOSE en chart_bridge.py
  - **Riesgo**: dos flechas compitiendo en el chart; ambas necesitan alinearse

---

#### E. **Capitulation QQQ (dip bot, Python)**
- **Fichero**: `scripts/capitulacion_qqq.py` (145 líneas)
- **Qué mide**: Capitulación en QQQ tras pánico (reversal pattern)
- **Lógica**: BB + RSI + volume arm
- **Usado en**: signal_conditioning (señales de compra dip)
- **Calibración**: ?

---

#### F. **Level React (rebote en niveles, C++)**
- **Fichero**: `bin/level_react` (compilado, ~57KB)
- **Qué mide**: Rebotes en muros/niveles OI significativos
- **Fuente**: probablemente `charts/data/levels_<sym>.json`

---

#### G. **GEX Core (exposición gamma)**
- **Fichero**: `scripts/gex_core.py` (268 líneas)
- **Qué mide**:
  - GEX per strike: `gamma * OI * 100 * spot` (convenio CASA, lineal)
  - Net GEX: suma de gamma dealer
  - Gamma flip: dónde invierten los dealers de long a short
  - Muros put/call: top-3 OI strikes por lado
- **Regimen**:
  - net_gex > 0 → POSITIVA (dealers amortiguan, mean-reversion)
  - net_gex < 0 → NEGATIVA (dealers amplifican, momentum)
- **Honestidad de cadena** (feature #5 2026-07-25):
  - MIN_GREEKS_OK=0.5: <50% de filas con griegas → sin voz gamma
  - STALE_S=45min: cadena vieja descartada
  - ROLL_HOUR_ET=16:00: contrato que vence HOY no se cuenta
- **Validación BS**:
  - implied_vol(price, S, K, T) por bisección, tol=1e-6
  - devuelve None jamás un 0.3 plausible si falla
- **Problema**:
  - La cadena actual (chain_full_*.json archivada) SOLO tiene OI/griegas del momento del snapshot (~16:20 cierre)
  - NO hay historia intraday de cómo evoluciona el GEX (ej: vega rotation, charm decay)
  - Para features como "DEX intradía" se necesaría "captura cada 30min" no "1 snapshot/día"

---

#### H. **Bollinger Complement**
- **Fichero**: `scripts/bollinger_complements.py` (217 líneas)
- **Qué mide**: BB(20,2) + %B + extremos
- **Usado en**: veto de band-walk en compass y flow_pulse
- **Problema**: Solo análisis, no genera señales independientes

---

#### I. **Overnight Structure**
- **Fichero**: `scripts/overnight_structure.py` (268 líneas)
- **Qué mide**: Preocupaciones overnight (overnight gaps, futuros, Asia/Europa)
- **Entrada**: Barras overnight (Asia/Europa), correlación de futuros

---

#### J. **Peer Structure**
- **Fichero**: `scripts/peer_structure.py` (213 líneas)
- **Qué mide**: Influencia de pares (QQQ→NVDA, SMH→MU, etc.)
- **Entrada**: Correlación intraday de componentes

---

#### K. **Momentum Decay**
- **Fichero**: `bin/momentum_calc` (compilado)
- **Qué mide**: Decaimiento de momentum intradía (modelo de media-reversion)

---

#### L. **Inflation Score**
- **Fichero**: `scripts/inflation_score.py` (120 líneas)
- **Qué mide**: Viento de cola/frente (inflación, tasa libre de riesgo, etc.)

---

#### M. **Signal Conditioning**
- **Fichero**: `scripts/signal_conditioning.py` (234 líneas)
- **Qué mide**: Filtro que combina señales crudas con contexto (hora, régimen, flood, etc.)
- **Entrada**: Compass, flow_pulse, fleet_consensus, momentum, etc.
- **Salida**: "Señales condicionadas" (que sí están calibradas)

---

### 2. DATOS DISPONIBLES (histórico y vivo)

| Fuente | Período | Granularidad | Qué Contiene | Ruta |
|---|---|---|---|---|
| Barras IBKR 1m | 2 años | 1 minuto | OHLCV | `data/bars_<sym>_ibkr.txt` |
| Barras Polygon 1m | 21 días | 1 minuto | OHLCV | `data/poly_bars` BD (493k filas, 30 syms) |
| Cadenas opciones | diaria (snapshot ~16:20) | 1 snapshot/día | Strike, IV, delta, gamma, theta, vega, OI, bid/ask | `data/history/<fecha>/chain_full_<sym>.json` |
| Flujo UW | intraday (300s/sym) | 1 dato/5min | Volumen calls, puts, P/C ratio, spot | `data/whale_flow_hist.jsonl` |
| NBBO | vivo (cada trade o 1s max) | bid/ask | Spread de entrada | `data/nbbo_<sym>.txt` |
| Correlación flota | diaria | 1 computo/día | Matriz de correlación Pearson | `data/cor_fleet.json` |
| Calidad libro | diaria | 1 computo/día | Coef[0,1] de confiabilidad gamma por símbolo | `data/book_quality.json` |
| GEX/flip | (depende gex_core.py) | (necesita refresco) | GEX net, flip, muros | Dentro de compass y daily_fleet_plans |

### 3. GAPS vs ESTÁNDARES PRO

**Benchmark nivel desk pro**: GEX + DEX + vanna + charm + IV term structure + put/call skew + expected move + unusual flow + OI changes + dealer positioning + regime + event-driven + gestión de riesgo.

#### **Tenemos ya**:
- ✅ GEX (gex_core.py, lo consume compass)
- ✅ Gamma flip (dentro de GEX)
- ✅ Muros OI (dentro de GEX)
- ✅ Unusual flow (flow_pulse.cpp, spikes de calls/puts)
- ✅ Regime gamma (NEG/POS de flip)
- ✅ Bollinger + %B (momentum extremo)
- ✅ Momentum intradía (barras 1m)
- ✅ Capitanes/jerarquía (flow_pulse v4)
- ✅ Manada consenso (fleet_consensus.cpp)
- ✅ Expected move residual (compass.cpp)

#### **Falta (medible con datos que YA archivamos)**:

1. **IV Term Structure (IV *slope* / carry)**
   - **Dato**: `chain_full_<sym>.json` archiva IV por expiry/strike (9 expiries típicamente)
   - **Cálculo**: IV_next - IV_today (forward carry), IV_ATM by expiry (slope)
   - **Aplicación**: Carry positivo → mean-reversion bias; negativo → momentum bias
   - **Esfuerzo**: S (15 líneas Python, aritmética)
   - **Calibración**: Auto-medible vs realized move (15 días → RV-IV cross)

2. **Put/Call Skew 25-Delta**
   - **Dato**: `chain_full_<sym>.json` archiva IV por strike + delta
   - **Cálculo**: IV_P(delta=-0.25) - IV_C(delta=+0.25)
   - **Aplicación**: Skew positivo (put IV > call IV) → pánico comprador o hedge; negativo → call overprice/crash concern
   - **Esfuerzo**: S (busca por delta, resta)
   - **Calibración**: Correlación con extremos de %B a la baja (pánico), reversiones post-pico

3. **DEX — Dealer Exposure (Vanna + Charm)**
   - **Dato**: `chain_full_<sym>.json` archiva vanna (∂²precio/∂S∂σ) y charm (Θ de gamma)
   - **Cálculo**:
     - Vanna net: `Σ vanna * OI * 100` (dealers short vanna en crash market)
     - Charm net: `Σ charm * OI * 100` (theta de gamma, decay diurno)
   - **Aplicación**: 
     - Vanna >0 durante sube → vender si sube mucho (vanna flux up = dealers hedge shorting more)
     - Charm >0 daily → gamma decay, mejor para shorters si no estan long vega
   - **Esfuerzo**: M (necesita aritmética por strike, similar a GEX)
   - **Calibración**: vs reversiones post-spike de IV (30-60s lag, dealers hedging)

4. **Expected Move (EM) — descomposición futura**
   - **Dato**: IV ATM de hoy, días hasta expiry
   - **Cálculo**: `EM = S * IV_ATM * sqrt(T) * 0.4` (36-40% de σ√T es empirical expected move)
   - **Aplicación**: 
     - Puedo rebote hoy: amplitud máxima ~50% del EM diario
     - EM residual: cuánto queda por recorrer (compass ya lo usa, pero NO se publica)
   - **Esfuerzo**: S (3 líneas, ya lo hace compass.cpp)
   - **Calibración**: vs realized daily range (RTL/H), desagregado por IV regime (CALM <16, ELEVADO 16-24, ALTO >24 VIX)

5. **Realized Vol vs Implied Vol (RV-IV Cross)**
   - **Dato**: Barras 1m (493k filas en BD), IV vivo de opciones
   - **Cálculo**: 
     - RV = std(retornos 1m) * sqrt(252 * 24 * 60) (anualizando)
     - Cross = RV / IV_ATM (IV puff si crash/spike o deflate si calma)
   - **Aplicación**: RV>IV → volatility crush coming (mean-reversion); RV<IV → upside explosive
   - **Esfuerzo**: M (necesita rolling window de RV, auto-update cada 5s)
   - **Calibración**: Auto-predictor: RV<IV hoy → mejor prob de movimiento el doble (backtesting 30 días)

6. **Charm Decay Intradía (Theta de Gamma)**
   - **Dato**: `chain_full_*.json` snapshot diario
   - **Problema**: Solo 1 snapshot/día (~16:20) → sin visión intraday del charm decay
   - **Solución**: Capturar snapshots cada 30-60min (durante RTH) → 6-12 muestras/día
   - **Aplicación**: Charm >0 morning → gamma decay acelera conforme pasan minutos → mejor probabilidad de mean-reversion conforme tarde
   - **Esfuerzo**: L (requiere pipeline nueva: fetch_chain_intraday → archiva + gex_core.charm_net)
   - **Calibración**: vs reversiones en tarde (12:00-15:00) donde charm decay es pico

7. **OI Term Structure Change Detection**
   - **Dato**: `chain_full_<sym>.json` OI por expiry
   - **Cálculo**: OI_today - OI_yesterday por expiry, concentración (fwd vs back)
   - **Aplicación**: 
     - OI collapse en frontal → roll action o liquidación incoming
     - OI concentration en 2-3 strikes → pin pin probable (opción perdedora)
   - **Esfuerzo**: S (resta diaria, archivo histórico pequeño)
   - **Calibración**: vs re-rolls (earnings weeks, expirations)

8. **Gamma Distribution by Delta (heatmap)**
   - **Dato**: `chain_full_<sym>.json` gamma * OI por strike (delta bucket)
   - **Cálculo**: Suma gamma por bucketas: delta [-0.25..-0.05], [-0.05..0.05], [0.05..0.25] (ATM, 10-delta, 25-delta)
   - **Aplicación**: Donde está la mayor concentración de gamma dealer = zona de máxima fricción/pin
   - **Esfuerzo**: S (groupby delta)
   - **Calibración**: vs realized spot distribution ese día (KS test: ¿la distribución de precios evita la gamma máxima?)

9. **Momentum Decay Model (intradía, predictor)**
   - **Dato**: Barras 1m, volatilidad intradía
   - **Cálculo**: 
     - Impulso puro (returns 1m, EWMA 6-bar)
     - Decaimiento: media-reversion exponencial ~3-8min (medido por calibration_ledger)
     - Previsión: si z-score momentum actual = +2.3 @ 10:30, prob de reversión a 10:45 = X% (measured)
   - **Esfuerzo**: M (ARIMA/exponential decay fitting)
   - **Calibración**: Ledger histórico vs compass_ledger.jsonl (muestras de computo + resultado 15-30min después)

10. **Vega Exposure by Delta Bucket (IV rotation risk)**
    - **Dato**: `chain_full_<sym>.json` vega * OI por delta
    - **Cálculo**: Suma vega por bucket ATM vs wings
    - **Aplicación**: Vega concentrada en wings + IV spike → dealers rush to de-hedge → momentum en el delta principal
    - **Esfuerzo**: S (groupby delta)
    - **Calibración**: vs IV level changes (spike put IV → vega wing long → algo unwind)

---

### 4. CALIBRACIÓN — Estado actual vs lo que falta

| Señal | Actual | n | Medido? | Falta | Prioridad |
|---|---|---|---|---|
| Compass:REVERSION | CP decision tree | 1379 | **Sí** (n>=30/celda) | Más regímenes (volatilidad, hora del día, IV regime) | M |
| Compass:CONTINUACION | CP decision tree | 1379 | Sí | idem | M |
| Flow:SPIKE_PUTS | EMA threshold + arbitrio | ? | Parcial (prob=78% base) | Bucket fino por: capitán opuesto, en muro, sobreventa %B | M |
| Flow:SPIKE_CALLS | EMA threshold + arbitrio | ? | Parcial (prob=59% base) | idem | M |
| Flow:MANADA | >=3 tickers 12min | ? | **Sí** (decisión binaria) | Requerir consenso de dirección (no solo spikes) | S |
| Fleet:CONSENSUS | >=78% flip agreement | ? | Parcial (n=flota) | Refresco de levels_*.json cada 5s RTH | BLOCKER |
| Capitulation | BB+RSI+volume | ? | Dudoso | Datos históricos de calibración | M |
| Level_React | Muros OI | ? | Desconocido | Backtest vs realized rebounds | L |
| GEX Net | Suma gamma dealer | Continua | **Sí** (BS math) | Captura intraday (30-60min snapshots) | L |
| RV-IV Cross | Propuesto | ? | No existe | Scripts + calibración | M |
| Charm Decay | Propuesto | ? | No existe | Pipeline intraday snapshots + BS decay | L |
| DEX (Vanna) | Propuesto | ? | No existe | Scripts + calibración vs IV spikes | M |
| IV Term Structure | Propuesto | ? | No existe | Scripts (carry slope) + calibración | S |
| Put/Call Skew | Propuesto | ? | No existe | Scripts (delta matching) + calibración | S |

---

## 5. PROBLEMAS CRÍTICOS A RESOLVER YA (fixes de calibración)

### **Fix #1: fleet_consensus.cpp depende de charts/data/levels_<sym>.json que NO se refresca**
- **Estado**: Binario compilado espera JSON frescos <=180s pero chart_levels.py NO refresca en bucle
- **Impacto**: fleet_consensus dice "cobertura insuficiente" todo el tiempo = SILENCIO total
- **Fix**: 
  1. Modificar `scripts/daily_fleet_plans.py:schedule()` → agregar **bucle cada 5s RTH** que refresca 30 símbolos
  2. O crear `scripts/chart_levels_daemon.py` que hace lo mismo (importa `gex_core`, genera JSON por cada símbolo)
  3. **Esfuerzo**: S (copiar lógica, agregar loop)
  4. **Validación**: `ls -la charts/data/levels_*.json | tail -5` debe mostrar timestamps frescos (<5s viejo)

### **Fix #2: Compass.cpp veto V3 no verifica si VT (Value Trap) existe**
- **Estado**: Código dice `// V3 spot bajo el VT congelado` pero NO valida `"vt": <number>` en levels_<sym>.json
- **Impacto**: Veto puede no ejecutarse silenciosamente
- **Fix**:
  1. Leer "vt" de levels_<sym>.json (ya está del chart_levels.py)
  2. Comparar spot < vt * (1 + NEAR_PCT)
  3. **Esfuerzo**: S (5 líneas adicionales)
  4. **Validación**: Log "V3 veto activo" cuando aplique

### **Fix #3: GEX Net no tiene captura intraday — solo 1 snapshot/día**
- **Estado**: `chain_full_<sym>.json` archivado a ~16:20 cierre
- **Impacto**: DEX (vanna + charm) no se puede medir intraday; no se detecta "vanna rotation" ni "charm decay"
- **Fix**:
  1. **chart_levels_daemon.py** (fix #1) también archivo snapshots JSON cada 30min con timestamp
  2. Crear `scripts/gex_archive_snapshot.py` → lee chain_full → calcula GEX/DEX/vanna/charm → archiva a `data/history/$(date +%Y-%m-%d)/gex_<sym>_<HH:MM>.json`
  3. **Esfuerzo**: M (15-20 líneas Python, reutiliza gex_core)
  4. **Validación**: Al EOD, 6-8 snapshots de GEX por símbolo con tiempo

### **Fix #4: Compass amplitud ("room") no verifica si atraviesa muro intermedio**
- **Estado**: Calcula distancia al siguiente nivel pero no valida si hay Muro en el camino (post-mortem 2026-07-20: META 660C tras muro 650 = premium muerto)
- **Fix**:
  1. Leer "walls_call" / "walls_put" de levels_<sym>.json → array ordenado de strikes
  2. Verificar si hay wall entre spot y "next_level"
  3. Si yes: amplitud = distancia a wall, no a next_level
  4. **Esfuerzo**: S (binary search + cond)
  5. **Validación**: Log "amplitud recortada por muro intermedio"

### **Fix #5: Direction_view.py sigue usando media ponderada que diluyó reversiones**
- **Estado**: Compass.cpp es máquina de estados (correcto), direction_view.py es media ponderada (diluidora), ambas coexisten
- **Fix**:
  1. Deprecar direction_view.py compute() en chart_bridge.py
  2. Reemplazar con lectura de `data/compass_<sym>.json` → leer "direction" + "prob"
  3. **Esfuerzo**: S (3-5 líneas, cambiar fuente de datos)
  4. **Validación**: Chart muestra 1 flecha, no dos compitiendo

### **Fix #6: Flow_pulse v4 captain_revierte sin memoria de cambios de dirección recientes**
- **Estado**: Detecta "capitan dispara opuesto a su tropa" pero si el capitán MISMO acaba de cambiar dirección, no lo sabe
- **Ejemplo**: SPY calls 13:02, puts 14:21 → a 14:35 MU spike calls → "capitan revierte" pero SPY está EN TRANSICION
- **Fix**:
  1. Agregar `cap_transition_ts` para cada capitán → registrar cuándo cambió dirección
  2. Verificar `now - cap_transition_ts < 180s` → si yes, NO disparar capitan_revierte (captán en transición)
  3. **Esfuerzo**: S (std::map + 3 líneas)
  4. **Validación**: Log "capitán en transición, esperando confirmación"

---

## 6. PLAN PRIORIZADO (10 items máximo, S/M/L esfuerzo)

### **TOP 5 (impacto máximo, esfuerzo S)**

**#1. IV Term Structure Slope (anticipador de carry)**
- **Qué**: Calcular IV_futuro - IV_hoy por expiry; detectar si el mercado espera crush o expansion
- **Entrada**: `chain_full_<sym>.json` IV por expiry (ya tenemos)
- **Salida**: `data/iv_term_structure_<sym>.json` con carry by expiry + slope signo
- **Ficheros**:
  - Script nuevo: `scripts/iv_term_structure.py` (~40 líneas, consume gex_core cadena reader)
  - Integrarlo en: compass.cpp como factor "IV_carry" (peso 0.3 si positivo = mean-reversion bias)
- **Calibración**: 15 días de histórico → Wilson CI de reversión 15min post-spike, condicionada en "IV_carry > 0"
- **Impacto**: +5-7% en prob de reversiones cuando carry es claro (medible vs compass_ledger)
- **Esfuerzo**: S
- **Validación**: `./compass qqq | jq .factors.iv_carry`

**#2. Put/Call Skew 25-Delta (pánico detector)**
- **Qué**: IV_put(delta=-0.25) - IV_call(delta=+0.25); alerta temprana a pánico/hedge demand
- **Entrada**: `chain_full_<sym>.json` IV + delta
- **Salida**: `data/skew_25d_<sym>.json` con skew value + trend (up/down)
- **Ficheros**:
  - Script nuevo: `scripts/skew_25d.py` (~35 líneas, busca strike por delta con interpolación lineal)
  - Integrarlo en: compass.cpp como veto V7 "skew negativo extremo" (crash protection)
- **Calibración**: Correlación skew spike vs %B < 0.15 (pánico bottomming)
- **Impacto**: +3-4% detección temprana de pánicos (15-30s anticipación vs mercado)
- **Esfuerzo**: S
- **Validación**: `./compass qqq | jq .factors.skew_25d`

**#3. FIX BLOCKER: Chart_levels daemon (refresco 5s RTH)**
- **Qué**: Crear `scripts/chart_levels_daemon.py` que refresca `charts/data/levels_<sym>.json` cada 5s RTH
- **Entrada**: IBKR spot + options API (ya funciona en daily_fleet_plans.py)
- **Salida**: 30 ficheros JSON frescos (<5s old)
- **Ficheros**:
  - Reutilizar lógica de daily_fleet_plans.py:chain_stats() → wrapper daemon
  - Launchd: `com.ibtrader.chart_levels_daemon` (priority HIGH, antes que fleet_consensus)
- **Impacto**: **DESBLOQUEADOR para fleet_consensus.cpp** (sin esto = silencio total)
- **Esfuerzo**: S
- **Validación**: `ps aux | grep chart_levels_daemon` + `ls -la charts/data/levels_qqq.json` <5s

**#4. RV-IV Cross (volatility crush anticipator)**
- **Qué**: Real vol / Implied vol → si <1.0 y bajando = crush incoming; si >1.0 = upside explosive
- **Entrada**: Barras 1m (BD poly_bars), IV ATM vivo
- **Salida**: `data/rviv_cross_<sym>.json` con ratio + trend + centiles históricos (percentil 10/50/90)
- **Ficheros**:
  - Script nuevo: `scripts/rv_iv_cross.py` (~45 líneas, rolling std de returns 1m)
  - Integrarlo en: compass.cpp factor "volatility_regime" (peso 0.5 si RV<IV=mean-reversion bias)
  - Auto-calibración: ledger histórico → buckets por RV/IV regime
- **Calibración**: 60 días de histórico → prob de reversión a la alza (15min exit) si RV/IV < 0.6
- **Impacto**: +4-6% en prob de reversiones cuando IV puffed (alta volatility implied)
- **Esfuerzo**: S
- **Validación**: `./compass qqq | jq .factors.rviv_cross`

**#5. Captura intraday de GEX snapshots (pipeline 30-60min)**
- **Qué**: Guardar `chain_full_<sym>.json` cada 30-60min RTH → 6-12 muestras/día vs 1 actual
- **Entrada**: IBKR options (ya subscrito) → chain_full generado por chart_levels_daemon.py
- **Salida**: `data/history/$(date +%Y-%m-%d)/gex_<sym>_<HH:MM>.json` con GEX/vanna/charm
- **Ficheros**:
  - Script nuevo: `scripts/gex_archive_snapshot.py` (~25 líneas, consume gex_core)
  - Scheduled: cron cada 30-60min o trigger en chart_levels_daemon.py
- **Impacto**: Desbloqueador para DEX (vanna + charm) y charm decay detection
- **Esfuerzo**: S
- **Validación**: `ls data/history/$(date +%Y-%m-%d)/gex_qqq_*.json | wc -l` debe ser 6-12

---

### **ITEMS 6-10 (impacto M/L, esfuerzo M/L)**

**#6. DEX — Dealer Exposure (Vanna + Charm)**
- **Qué**: Suma vanna * OI + charm * OI por símbolo → detector de dealer hedging gaps
- **Entrada**: `data/history/*/gex_<sym>_*.json` (vanna/charm de snapshots intraday)
- **Salida**: `data/dex_<sym>.json` con vanna_net + charm_net + interpretation
- **Ficheros**:
  - Extender `scripts/gex_core.py`: funciones `vanna_net()` y `charm_net()` (~20 líneas)
  - Script nuevo: `scripts/dex_realtime.py` (~50 líneas, consume snapshots, calcula DEX cada 15-30min)
  - Integrarlo en: daily_fleet_plans.py charting (heatmap vanna/charm rotation)
- **Calibración**: Vanna flux durante IV spikes (30s después del spike, medir cuánto se revierte)
- **Impacto**: +3-5% en prob de reversiones cuando vanna es "long" (dealers hedging short vega = market reverses)
- **Esfuerzo**: M
- **Validación**: Daily PDF con "vanna rotation 9:30-16:00" heatmap

**#7. Charm Decay Intradía (Theta de Gamma)**
- **Qué**: Charm = -Γ * σ * S / 365 (decrece durante el día); modela cómo gamma se convierte en theta
- **Entrada**: `data/history/*/gex_<sym>_*.json` snapshots, time between snapshots
- **Salida**: `data/charm_decay_<sym>.json` con decay rate + expected reversal timing
- **Ficheros**:
  - Extender `scripts/gex_core.py`: función `charm_decay_rate()` (~15 líneas)
  - Script nuevo: `scripts/charm_decay_model.py` (~40 líneas, ajusta decaimiento exponencial)
  - Integrarlo en: compass.cpp amplitude "timing_charm" (esperar a 14:00+ si charm_decay_positive = prob de reversión aumento conforme pasan minutos)
- **Calibración**: Midday reversals (11:00-14:00) vs early morning (9:30-11:00)
- **Impacto**: +2-3% en timing de reversales (saber *cuándo* esperar más que *si*)
- **Esfuerzo**: M
- **Validación**: `./compass qqq --loop 60 | grep charm_decay | head -10`

**#8. OI Term Structure Change (roll detection)**
- **Qué**: Detectar rolling masivo (traslado de OI de frontal a back) → liquidación incoming
- **Entrada**: `data/history/*/chain_full_<sym>_*.json` OI por expiry (diario)
- **Salida**: `data/oi_term_change_<sym>.json` con concentration shift + predicted roll date
- **Ficheros**:
  - Script nuevo: `scripts/oi_roll_detector.py` (~50 líneas, diferencia OI día-a-día)
  - Integrarlo en: daily_fleet_plans.py para earnings weeks, expirations alerts
- **Calibración**: Correlation con liquidity squeeze (spreads expanding 48h pre-roll)
- **Impacto**: +2-3% en anticipating whip-saws durante roll weeks (earnings)
- **Esfuerzo**: M
- **Validación**: Manual inspection of historical roll weeks vs predicted dates

**#9. Gamma Distribution by Delta Bucket (pin zone mapping)**
- **Qué**: Concentración de gamma por delta bucket [-0.25, -0.05, 0, +0.05, +0.25] → zona de máxima fricción
- **Entrada**: `data/history/*/chain_full_<sym>.json` gamma * OI por strike
- **Salida**: `data/gamma_distribution_<sym>.json` heatmap + predicted pin zone
- **Ficheros**:
  - Script nuevo: `scripts/gamma_distribution.py` (~35 líneas, groupby delta ranges)
  - Integrarlo en: daily_fleet_plans.py charting (overlay gamma bucket colores)
- **Calibración**: KS test vs realized spot distribution: ¿evita la gamma máxima?
- **Impacto**: +1-2% en pin probability (bajo cuando gamma concentrado = higher pin prob)
- **Esfuerzo**: M
- **Validación**: "Muro del 0-delta = 450k contracts → pin zona [684-686]" in daily PDF

**#10. Momentum Decay Model (intradía, predictor)**
- **Qué**: Ajustar modelo de decaimiento exponencial de momentum (z-score) → previsión "en qué min revienta la reversión"
- **Entrada**: Barras 1m, compass_ledger.jsonl (computos históricos)
- **Salida**: `data/momentum_decay_model.json` con λ (decay rate) by sym + vega scaling (alto VIX = slower decay)
- **Ficheros**:
  - Script nuevo: `scripts/momentum_decay_calibrate.py` (~60 líneas, ARIMA fitting + cross-validation)
  - Integrarlo en: compass.cpp timing de reversión (si momentum z-score actual = +2.3 @ 10:30, esperar reversal @ 10:45±5min)
- **Calibración**: 90 días de histórico → ledger de impulsos vs tiempo-a-reversión real
- **Impacto**: +2-4% en timing accuracy (55% early exits, 35% perfect exit, 10% late)
- **Esfuerzo**: L (necesita stats fitting, cross-validation)
- **Validación**: Backtest harness: compare predicted timing vs actual (MAE <5min = OK)

---

## 7. RESUMEN EJECUTIVO

### Tres frentes simultáneamente (parallelizable):

**URGENTE (bloqueador)**:
1. **Chart_levels daemon** (#3) — sin esto fleet_consensus es mudo

**CORE (máximo impacto con mínimo esfuerzo)**:
2. IV term structure slope (#1)
3. Put/call skew 25-delta (#2)
4. RV-IV cross (#4)
5. GEX snapshots intraday (#5)

**EXTENSION (timing + regime)**:
6. DEX vanna/charm (#6)
7. Charm decay model (#7)
8. OI roll detection (#8)
9. Gamma pin zones (#9)
10. Momentum decay predictor (#10)

### Calibración mínima viable:
- Todas excepto #7, #10 se calibran con 15-30 días histórico ya archivado (Wilson CI, buckets por regime)
- #7 y #10 necesitan 60-90 días para fitting (disponibles: compass_ledger 1379 muestras, barras 2 años)

### Medidas de éxito:
- Compass prob medido (no doctrina) sube de ~10% actual a ~60%+ de muestras
- Fleet_consensus vuelve a hablar (FIX #3)
- Daily PDF charting muestra 5+ factores independientes (hoy: solo GEX + BB)
- Signal conditioning calibración passa FDR <0.1 (hoy: desconocido)

