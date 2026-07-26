#!/bin/zsh
# Lo que toda sesion nueva debe saber, UNA vez (hook SessionStart matcher=startup).
# CLAUDE.md ya lo carga el harness; lo que se pierde entre sesiones es TODOS.md.
REPO="${CLAUDE_PROJECT_DIR:-${0:A:h:h}}"
cd "$REPO" || exit 0
echo "=== ib-trader | $(git branch --show-current 2>/dev/null) | $(git log --oneline -1 2>/dev/null | cut -c1-60)"
echo "=== LEE: CLAUDE.md (6 reglas) · AGENTS.md (ordenes permanentes) · TODOS.md"
echo "=== TODOS.md: $(grep -c '^- \[ \]' TODOS.md 2>/dev/null) abiertas. Las 8 primeras:"
grep '^- \[ \]' TODOS.md 2>/dev/null | head -8 | sed 's/\*\*//g; s/\[pendiente[^]]*\]//g; s/^- \[ \]/  ·/' | cut -c1-105
./fleet_hours --why 2>/dev/null | head -1
echo "=== APUNTA cada peticion nueva en TODOS.md AL MOMENTO, con las palabras de Yunior."
