# CLAUDE.md — ib-trader (se lee automáticamente al abrir sesión en este repo)

Índice de punteros, no copia. La doctrina larga vive en `AGENTS.md` (83 KB) y en `docs/`.

## Lee esto antes de tocar nada
- **`AGENTS.md`** — órdenes permanentes. Empieza por "ORDENES PERMANENTES DE YUNIOR".
- **`TODOS.md`** — lo que queda. **Apunta cada petición nueva AL MOMENTO**, con las palabras de Yunior.
- **`~/CLAUDE.md`** — reglas globales (ya cargado por el harness).

## Las 6 que más rompen cosas
1. **SEÑAL-SOLAMENTE.** Nada ordena al bróker. Única excepción: `order_engine/` (doble llave, paper-first, disarm-on-exit).
2. **Prosa PROHIBIDA** (2026-07-26). Comentarios 1 línea solo si el porqué no es obvio; la historia va al mensaje del commit. *Focus on shit done.*
3. **Ningún `except` devuelve `0`, `0.0`, `0.5`, `50` ni `{}`** en camino de señal → `None` o levanta. Un número plausible convierte "no sé" en "sé, y es cero".
4. **Tiempo real es prioridad.** IBKR = tiempo real (el DISPARO). Polygon = 15 min (HISTORIA). CBOE = delayed y desigual (ESTRUCTURA). Ningún nivel que dispare una orden viene de fuente delayed. → `docs/LATENCIA-FUENTES.md`
5. **Dos universos, no uno.** `data/fleet.txt` (30, exige barras 1m, **denominador de MANADA**, 36 lectores) vs `data/universe_gamma.txt` (35, solo exige cadena, no vota). Mezclarlos rompió MANADA. → `docs/UNIVERSOS.md`
6. **Una sola rama: `main`.** Commit directo, sin feature branches. Verifica con `git branch -a`.

## Mac de 8 GB
Un solo `clang++` a la vez: `ps aux | grep -c "[c]lang++"` antes de compilar. Los bots/alarmas ligeros sí van en paralelo.

## Flags C++
`-std=c++2c -O3 -mcpu=native -Wall -Wextra`, cero warnings.

## Verificar antes de creer
Lo que devuelve un agente se comprueba con fichero:línea. Un informe no es evidencia hasta que se mide. `trades.db` siempre en solo lectura: `sqlite3 "file:trades.db?mode=ro"`.

## Ventana horaria
Portero: `./fleet_hours --why`. Flota viva dom 20:00 → vie 20:00 Toronto. Fuera de ahí, muerta a propósito.

## Tests
`./venv/bin/python -m pytest tests/ -q` (~4 min). Referencia actual: **~690 passed**, 1 fallo preexistente y ajeno en `test_voice_budget.py::test_gate_devuelve_42_solo_al_suprimir`.
