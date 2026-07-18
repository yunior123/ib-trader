---
name: cpp23-fleet
description: C++23 para la flota ib-trader — flags canónicos (c++23 -O3 -march=native), builds con sanitizers, patrones de hot-path (posix_spawn, O_APPEND atómico, sin locks), warning-cero, y cómo compilar/verificar los 22 bots + price_alarm + qqq_xray. Usar al compilar, tocar C++ de la flota, cazar bugs de memoria, o al crear componentes nuevos.
---

# C++23 Fleet — rápido Y de alta calidad (emblema Yunior)

## Flags canónicos (Apple clang 21, macOS Tahoe)

```bash
# Producción (SIEMPRE):
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o <bin> <src>.cpp

# Verificación (antes de dar por bueno un cambio):
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -o <bin>_asan <src>.cpp
```

- `c++23` es el estándar completo más nuevo del clang instalado; `c++2c` existe pero
  no añade velocidad — la velocidad viene de `-O3 -march=native`, no del estándar.
- NO hace falta actualizar la Mac para "el último C++": clang 21 ya es el más nuevo.
- Warnings = 0 SIEMPRE (2026-07-18: se eliminó `a5o` muerta de los 22 bots → 0 warnings).

## Compilar la flota (paralelo OK — regla secuencial NO aplica a ib-trader)

```bash
cd ~/Documents/GitHub/ib-trader
# 22 bots en paralelo, 6 hilos:
ls *_signal_bot.cpp | xargs -P 6 -I{} sh -c 'b="{}"; clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o "${b%.cpp}" "$b"'
clang++ -std=c++23 -O3 -march=native -o price_alarm scripts/price_alarm.cpp
clang++ -std=c++23 -O3 -march=native -o qqq_xray  scripts/qqq_xray.cpp
```

`scripts/apply_v6.py` ya emite estos flags. Los 4 bridges de infra
(alpaca_ws_bridge/scan_server/x_whale_bot/screener_alert) necesitan sus libs
(curl/openssl/Network) — pendientes, data-plane, no path de señal.

## Patrones de hot-path de la flota

- **Banner**: `fleet_notify.h` → `posix_spawn` directo de osascript (~150–180μs
  caller, medido 2026-07-18), SIGCHLD SIG_IGN (auto-cosecha, cero zombies),
  jitter AppleScript 0–0.45s en el HIJO (anti-descarte de banners simultáneos).
- **Logs**: `open(O_APPEND)+write` de UNA línea <PIPE_BUF = append atómico sin locks.
- **Voz**: NUNCA `say` directo desde C++ — siempre `scripts/speak.sh <PRIO> 'msg'`
  (cola serializada). Sanitizar SIEMPRE con `sh_sanitize` (whitelist alnum + ` .,%+-:/()_`).
- **Rewrite de archivos compartidos**: tmp + `rename()` (atómico) — ver `mark_fired`.

## Verificación mínima antes de "está listo" (sistema financiero)

1. Compila con `-Wall -Wextra` → 0 warnings.
2. Build ASan+UBSan y córrele el replay real: `./<bot>_asan --stdin < data/bars_<sym>_ibkr.txt` → 0 informes.
3. Unit tests del scratch: patrón `#define main <x>_main` + `#include` del .cpp real
   (prueba las funciones EXACTAS de producción, no copias).
4. Si tocaste notificación/voz: dispara una de verdad y confírmala con el humano.
