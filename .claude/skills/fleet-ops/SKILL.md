---
name: fleet-ops
description: Operar la flota ib-trader RÁPIDO — foco de tickers, reinicios, sirenas, escaneo de opciones, estado. Usar cuando Yunior pida activar/apagar bots, armar alarmas, verificar flujo de opciones o estado de la flota. Todo señal-only (ley #0).
---

# fleet-ops — operación rápida de la flota (nacido 2026-07-16: "it took too long today")

Repo: `~/Documents/GitHub/ib-trader`. TODO es señal-only — jamás órdenes al broker.

## 1. Modo foco (solo estos tickers hoy)
```bash
printf "tsm\nintc\nnvda\n" > data/focus_ticker   # lista deseada, uno por línea
zsh scripts/fleet_keepalive_start.sh              # aplica YA (mata el resto)
rm data/focus_ticker && zsh scripts/fleet_keepalive_start.sh  # flota completa
```
Verificar: `ps aux | grep -E '[a-z]+_signal_bot$' | grep -v grep`

## 2. Sirenas de precio (C++ `price_alarm`, chequeo 1s, ya corre 24/5)
Editar `~/Desktop/price-alerts.txt`: `ticker precio up|down` (+ comentario).
Dispara: sirena + voz + línea en `~/Desktop/trading-signals/YYYY-MM-DD.txt`,
y marca `[DISPARADA hh:mm]` (re-armar = borrar ese prefijo). El binario relee
el archivo cada segundo — no hay que reiniciar nada.

## 3. Escaneo de opciones RÁPIDO
- **Instantáneo (C++)**: `./opt_quick SYM` — lee el cache `data/opt_chain_*.txt`
  (muros OI/vol, P/C, max pain). Si no existe aún, ver scripts/opt_chain_cache
  (21 syms: flota + MSFT/AVGO/AMZN/META para el xray).
- Flujo vivo cada 5 min: `cat data/opt_flow.txt` (opt_sentinel, 17 tickers).
- Escaneo puntual profundo (python, ~30s): usar clientIds LIBRES 40-49
  (85-99 están tomados por los daemons). Patrón en el playbook.

## 4. Estado de la flota en un comando
```bash
./qqq_xray        # radiografía QQQ: top-10, DIQUE MSFT+AAPL, semis, veredicto (<50ms)
                  # ./qqq_xray --watch = loop 60s, avisa SOLO al cambiar dique/veredicto
for s in $(cat data/focus_ticker 2>/dev/null || echo nvda qqq intc); do
  printf "%s: %s\n" $s "$(cat data/nbbo_$s.txt | awk '{printf "%.2f",($2+$3)/2}')"; done
pgrep -fl 'price_alarm|opt_sentinel|options_enrich|ibkr_bar_bridge' | head
tail -20 ~/Desktop/trading-signals/$(date +%F).txt
```

## 5. Recarga de bots tras recompilar (secuencial, 8GB)
`pkill -x {sym}_signal_bot` — el keepalive lo resucita con el binario nuevo en ~30s.
Los 3 KRX (kospi/samsung/skhynix) tienen sesión 20:00-02:30 ET.

## 6. Loop copiloto minuto-a-minuto
Tick = leer NBBOs + última barra (`tail -1 data/bars_{sym}_ibkr.txt`), dar orden
de UN número, y `sleep 60` con run_in_background como timer. Voz:
`(say -v Paulina "mensaje" &)`. Doctrina completa: docs/PLAYBOOK-2026-07-16-el-mejor-dia.md

## Reglas fijas
- clientIds TWS: 85-99 reservados a daemons; escaneos puntuales usar 40-49.
- Compilar: `clang++ -std=c++17 -O2 -o X X.cpp` — UNO a la vez (8GB).
- Todo evento visible en el Desktop; señales solo BUY/SELL + prob%.
