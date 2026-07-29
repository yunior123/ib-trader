# CLAUDE.md — ib-trader (flota de detección de movimientos, C++23+Python)

## Sistema (1 línea)
Flota de 21 signal bots C++ (barras 1m; prob. solo 'medido' con n>=30, si no doctrina etiquetada) + order_engine (doble llave) = anticipar movimientos antes del pico. **SEÑAL-SOLAMENTE POR DEFECTO** (no ejecuta órdenes salvo --arm-live). Tiempo real: IBKR>Polygon>CBOE.

## Estructura del repo

```
bin/                16 binarios C++23: compass, fleet_consensus, flow_pulse, 
                    fleet_hours (portero horario), gate, opt_quick, etc.
bots/               21 signal bots C++ (aapl_signal_bot, nvda_signal_bot, ... 
                    + fleet_notify.h: broadcast interno)
scripts/            daemons Python: ibkr_bar_bridge.py (TWS vivo), 
                    opt_chain_cache.py, calibration_ledger.py, chart_bridge.py, 
                    fleet_up.sh (un comando), ib_mode.py (puertos no hardcodeados)
config/             feeds.env (Polygon key), llm.env, x.env
data/               fleet.txt (30 tickers), universe_gamma.txt (35), 
                    ib_mode.txt ("paper"|"live"), trades.db (read-only), 
                    bars_*.txt (vivos), pos_*.txt (estado)
logs/               136 .log rotatorios por bot/operación (e.g. aapl_signals.log)
charts/             live.html (cockpit JS, lightweight-charts, 10 widgets), históricos
docs/               62 docs: ARCHITECTURE.md (sistema), OPERATIONS.md (runbook), 
                    DAILY-SYSTEM.md (planes 4am), LATENCIA-FUENTES.md (medido)
order_engine/       motor C++23: order_engine (binario), arm.sh + disarm.sh 
                    (doble llave), tests/, ledger/
scalper/            whale_scalper C++23 (0DTE QQQ sim/shadow)
engines/            bb_engine, combo_engine (experimentales)
screener/           escaneres Finviz + picks
tests/              975 tests: conftest.py, test_*.py (69 archivos), cpp/ (GTest)
.git/               solo rama main (no branches)
```

## Reglas duras evidentes en código

1. **Señal-solamente**: bin/*_signal_bot solo grabar alertas; no ordenan. 
   `order_engine` ejecuta órdenes SOLO si:
   - `data/ib_mode.txt` = "live" Y
   - `order_engine/ARM_LIVE` existe (fecha de hoy) Y
   - se invoca con `--arm-live` flag (doble llave verificada antes de CADA envío)
   - Por defecto: `--paper` (sin ARM_LIVE no ordena en vivo)

2. **Ningún except devuelve 0 / 0.0 / 0.5 / 50 / {} en camino de señal**:
   - Devuelven `None` o levantan excepción (fail-loud)
   - Ejemplo: `calibration_ledger.py` conecta read-only a trades.db; si falla, no inventa probabilidades

3. **Nada hardcodeado de puertos / rutas**:
   - Puertos IBKR: resueltos dinámicamente vía `scripts/ib_mode.py` 
     (lee `data/ib_mode.txt` + env `IBT_PAPER_PORTS`/`IBT_LIVE_PORTS`) — JAMAS un puerto clavado en un consumidor (precedente: default 4002 copiado x4 = flota entera desconectada)
   - Rutas derivadas de `__file__` o `BASH_SOURCE`, no rutas hardcodeadas
   - Universos (`fleet.txt` 30, `universe_gamma.txt` 35) son data/, no código

4. **Escritura atómica**: tmp + `os.replace()` para ficheros leídos en vivo 
   (ej: `calibration_ledger.py`, `barrier_labels.py`, `book_quality.py`)

5. **trades.db read-only excepto escritores designados**:
   - Lectores: `sqlite3.connect("file:data/trades.db?mode=ro", uri=True)`
   - Escritores: `barrier_labels.py`, cron del order_engine ledger

6. **Una sola rama**: `git branch -a` = `main` + `remotes/origin/main`

7. **Comentarios**: 1 línea si el "por qué" no es obvio. Cabecera del archivo OK (multiline). 
   Nada de docstrings-ensayo.

8. **Verificación antes de creerlo**: `fichero:línea` en hallazgos, nunca afirmaciones sin rendorizar.

## Cómo correr

### Tests (975 tests)
```bash
cd ~/ib-trader
./venv/bin/python -m pytest tests/ -q    # salida compacta
./venv/bin/python -m pytest tests/ -v    # detalle
# Subconjunto: pytest tests/test_compass.py -q
```

### Compilación C++23
```bash
# Binarios individuales (seleccionados tienen build_*.sh):
cd ~/ib-trader
zsh scripts/build_compass.sh        # compass
zsh scripts/build_fleet_hours.sh    # portero horario
zsh scripts/build_fleet_consensus.sh

# order_engine (complejo, requiere TWS libs vendoreadas):
cd order_engine && zsh build.sh     # genera order_engine (c++23 -O3 -march=native)

# whale_scalper:
cd scalper && zsh build.sh
```
**Flags C++**: `-std=c++23 -O3 -march=native` (Intel) / `-mcpu=native` (Apple Silicon), 
`-pthread -Wall -Wextra`, sin warnings.

**Mac 8GB**: compila SECUENCIAL (un solo clang++ a la vez). Verifica con `ps aux | grep -c "[c]lang++"`.

### Portero horario (ib_trader solo dom 20:00→vie 20:00 Toronto)
```bash
./bin/fleet_hours          # exit 0 = LIVE, exit 1 = DEAD
./bin/fleet_hours --why    # explica por qué está muerto/vivo
./bin/fleet_hours --json   # JSON para scripts
```
Override testing: `export FLEET_FORCE=1` o crear `data/FLEET_FORCE`.

### Levantar flota (señal-solamente)
```bash
zsh scripts/fleet_up.sh             # todos los bots + puentes + alarmas
zsh scripts/fleet_up.sh --chart     # + cockpit gráfico (browser)
zsh scripts/fleet_up.sh --status    # solo informa, no arranca nada

# Pasar a LIVE (lo único manual):
zsh scripts/ib_mode.sh live         # cambia data/ib_mode.txt
zsh scripts/fleet_up.sh              # relanza con puerto 4001 (Gateway live)
```

### Ejecutar órdenes (doble llave: order_engine + ARM_LIVE)
```bash
order_engine/arm.sh                         # llave 1: crea data/order_engine/ARM_LIVE
order_engine/run.sh --arm-live --sym QQQ   # llave 2: requiere ARM_LIVE presente
order_engine/disarm.sh                      # remover ARM_LIVE
```

## Datos críticos

| Archivo | Qué es | Ejemplo |
|---|---|---|
| `data/fleet.txt` | 30 tickers (vota en alertas) | QQQ SPY NVDA ... STX |
| `data/universe_gamma.txt` | 35 (mapa + 5 índices) | fleet.txt + SPX XSP NDX DIA IWM |
| `data/ib_mode.txt` | "paper" \| "live" (resuelve puerto) | paper |
| `data/trades.db` | SQLite: operaciones realizadas (read-only) | queries en backtest_harness.py |
| `data/pos_*.txt` | Estado virtual de cada bot | EPOCH ENTRY TRAIL FLOOR TARGET |

## Documentación clave

- **ARCHITECTURE.md**: diseño completo (plano de datos, motores, contratos de fichero, latencias medidas)
- **OPERATIONS.md**: runbook de arranque/parada, matanza, health checks, troubleshooting
- **DAILY-SYSTEM.md**: cron autónomo (04:00 full, 08:30 refresh, 09:12 apertura) → 26 PDFs/ticker + email + X
- **LATENCIA-FUENTES.md**: IBKR realtime, Polygon 15min (401 /v3/trades), CBOE delayed (SPY 21h)

## Cambios de Yunior: APUNTA EN TODOS.md

Cada nueva petición durante sesión → `TODOS.md` al momento con sus palabras exactas + fecha + estado:
```
- [ ] [descripción exacta del pedido] (2026-07-29, pendiente)
- [x] [descripción] (2026-07-28, hecho commit_hash)
```
Al cerrar: TODOS.md es la única fuente de lo que queda; lo CERRADO se mueve a `Done.md`.

## Versiones de la app macOS

- La versión visible es secuencial: `v1`, `v2`, ...; jamás se muestra el hash de git al usuario.
- Fuente única: `macapp/VERSION` (entero). Subirla exactamente una vez por release visible antes
  del rebuild final. El commit permanece en `Info.plist` solo para diagnóstico interno.

## NUNCA revertir trabajo de codex ni de Yunior (orden 2026-07-29)
Yunior manda tareas a codex directamente en paralelo: lo que parezca "trabajo no pedido" puede
ser orden suya. Si algo rompe consumidores: ADAPTAR hacia delante o reportar con números —
jamás `git revert/checkout`. Y en briefs a agentes: prohibido git destructivo (un checkout de
scripts/ destruyó fixes ajenos el 2026-07-29).

---
**Actualizado**: 2026-07-29 | **Rama**: main | **Sistemas**: 21 bots, 975 tests, 1 orden_engine doble-llave
