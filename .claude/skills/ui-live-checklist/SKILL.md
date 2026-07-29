---
name: ui-live-checklist
description: Non-vibecoded UI design checklist for live.html — accessibility, responsive zoom, marker rendering, performance (<300ms data load), WebSocket lag, legend clarity, dark mode, mobile fallback. Use for QA before pushing UI updates.
---

# UI Checklist — Diseño pro sin vibes

Verificar `charts/live.html` (2766 líneas) antes de desplegar.

## Checklist técnico
```bash
cd ~/ib-trader

# 1. Performance: <300ms data load
time curl -s http://localhost:8080/history?sym=NVDA | wc -l

# 2. WebSocket lag (simulate 100ms latency)
# Modificar scripts/chart_bridge.py: add sleep(0.1) en onbar()
# Medir diferencia timestamp_server vs timestamp_rendered_js

# 3. Markers render correctamente
# Check console.log: cada BUY/SELL marker emite "MARKER sym=NVDA @ 119.45"

# 4. Zoom responsive (scroll wheel)
# Manual: abrir live.html, scroll en chart, verificar que no hay jigging

# 5. Legend legible (contrast ratio >= 4.5:1)
# Usar WCAG contrast checker en cada color de leyenda

# 6. Mobile fallback (viewport meta)
# Abrir en iPhone: ¿chart legible o desbordado?

# 7. Dark mode (css @media prefers-color-scheme)
# Chrome DevTools: Rendering > Emulate CSS media > prefers-color-scheme: dark
```

## Checklist de UX
- Que el countdown (TF seconds) no "congele" >5s
- Que los stops arrastrables no salten a precio roto
- Que el refresh de watchlist no cause "blinking"
- Que las alarmas audibles (voz) se queden muted si el volume está bajo
- Que el account badge (paper/live) sea bien visible

## Archivo
`charts/live.html` (fuente única, <3KB js inline + lightweight-charts v5)

## Fuente propia
Propio diseño + reglas de Yunior trading-cockpit 2026-07
