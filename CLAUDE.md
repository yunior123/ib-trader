# CLAUDE.md — ib-trader (se lee automáticamente al abrir sesión en este repo)

Índice de punteros, no copia. La doctrina larga vive en `AGENTS.md` (83 KB) y en `docs/`.

## Lee esto antes de tocar nada
- **`AGENTS.md`** — órdenes permanentes. Empieza por "ORDENES PERMANENTES DE YUNIOR".
- **`TODOS.md`** — lo que queda. **Apunta cada petición nueva AL MOMENTO**, con las palabras de Yunior. Lo CERRADO se mueve a `Done.md`.
- **`~/CLAUDE.md`** — reglas globales (ya cargado por el harness).

## Las 6 que más rompen cosas
1. **SEÑAL-SOLAMENTE.** Nada ordena al bróker. Única excepción: `order_engine/` (doble llave, paper-first, disarm-on-exit).
2. **Prosa PROHIBIDA** (2026-07-26). Comentarios 1 línea solo si el porqué no es obvio; la historia va al mensaje del commit. *Focus on shit done.*
3. **Ningún `except` devuelve `0`, `0.0`, `0.5`, `50` ni `{}`** en camino de señal → `None` o levanta. Un número plausible convierte "no sé" en "sé, y es cero".
4. **Tiempo real es prioridad.** IBKR = tiempo real (el DISPARO). Polygon = 15 min (HISTORIA). CBOE = delayed y desigual (ESTRUCTURA). Ningún nivel que dispare una orden viene de fuente delayed. → `docs/LATENCIA-FUENTES.md`
5. **Dos universos, no uno.** `data/fleet.txt` (30, exige barras 1m, **denominador de MANADA**, 36 lectores) vs `data/universe_gamma.txt` (35, solo exige cadena, no vota). Mezclarlos rompió MANADA. → `docs/UNIVERSOS.md`
6. **Una sola rama: `main`.** Commit directo, sin feature branches. Verifica con `git branch -a`.

## 7. NADA HARDCODEADO (Yunior 2026-07-27: "evita poner hardcoded shit, it should be dynamic")
Un valor clavado en el código es un bug esperando su turno. Medido ese día: `IBKR_PORT` con
default `"4002"` copiado en 4 daemons mientras el Gateway estaba en 4001 → `ibkr_bar_bridge`
(los 30 símbolos) y `korea_bar_bridge` **100% desconectados en crash-loop**, y `opt_sentinel` +
`sox_index_feed` reventando cada 20-30 s. Cuatro copias del mismo número, cuatro averías.
- **Puertos/cuentas/modo** → `scripts/ib_mode.py` y NADA más. Gateway-only por orden; lista
  configurable por env (`IBT_PAPER_PORTS`/`IBT_LIVE_PORTS`), jamás reescrita en el consumidor.
- **Rutas** → derivadas de `__file__`. Cero rutas absolutas (la mudanza a `~/ib-trader` mató 3 scripts).
- **Universos** → `data/fleet.txt` (30, vota MANADA) y `data/universe_gamma.txt` (35, mapa). Jamás
  una lista de símbolos copiada dentro de un script.
- **Horarios** → el portero (`./fleet_hours`, `scripts/fleet_window.py`); para KRX, `krx_market()`.
  Llegó a haber 4 definiciones del horario peleándose. No crees la 5ª.
- **Cierres previos / niveles de referencia** → SE CALCULAN del dato. Precedente vivo:
  `scripts/korea_watch.cpp:39` lleva `PCH/PCS/PCK` clavados de hace una semana → calcula Hynix
  −3,56% y Samsung −1,47% falsos y está a 1350 KRW de cantar un `READTHRU_BEAR` inventado.
- Si de verdad hace falta una constante: **una sola definición**, con el porqué en 1 línea, y el
  consumidor la IMPORTA. Duplicarla es el bug.

## Mac de 8 GB
Un solo `clang++` a la vez: `ps aux | grep -c "[c]lang++"` antes de compilar. Los bots/alarmas ligeros sí van en paralelo.

## Flags C++
`-std=c++2c -O3 -mcpu=native -Wall -Wextra`, cero warnings.

## Verificar antes de creer
Lo que devuelve un agente se comprueba con fichero:línea. Un informe no es evidencia hasta que se mide. `trades.db` siempre en solo lectura: `sqlite3 "file:trades.db?mode=ro"`.

## Ventana horaria
Portero: `./fleet_hours --why`. Flota viva dom 20:00 → vie 20:00 Toronto. Fuera de ahí, muerta a propósito, salvo los perpetuos 24/7 y sus notificaciones/alarmas.

## Tests
`./venv/bin/python -m pytest tests/ -q` (~4 min). Referencia actual: **~690 passed**, 1 fallo preexistente y ajeno en `test_voice_budget.py::test_gate_devuelve_42_solo_al_suprimir`.
