---
name: fleet-health
description: Comprehensive fleet status check — all 30 tickers, fresh bars/NBBO, daemon health, calibration freshness, active positions, compass state. Use for morning wake-up or debugging silent failures.
---

# Fleet Health — Chequeo integral

Verificar estado operativo de la flota (30 tickers).

## Chequeo rápido (1 min)
```bash
cd ~/ib-trader

# ¿Barras frescas? (última actualización <2min)
ls -lah data/bars_*_ibkr.txt | awk '{print $6,$7,$8,$9,$10}' | sort

# ¿NBBO fresco? (último NBBO <30s)
ls -lah data/nbbo_*.txt | awk '{print $10; system("stat -f %Sm -t %H:%M:%S " $10)}' 2>/dev/null

# ¿Daemons vivos?
ps aux | grep -E "[i]bkr_bar_bridge|[k]orea_bar_bridge|[o]pt_whale_watch|[f]low_pulse" | wc -l

# ¿Último compass refresh? (estado flecha)
stat -f %Sm -t "%Y-%m-%d %H:%M:%S" data/compass_out.json 2>/dev/null || echo "NO COMPASS"

# ¿Cadena de opciones fresca? (opt_chain_*.txt <1h)
find data -name "opt_chain_*.txt" -type f -mmin -60 2>/dev/null | wc -l

# ¿Calibración calibrada? (compass_calib.json)
cat data/compass_calib.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Cells: {len(d)}, Median n: {sorted([v['n'] for v in d.values()])[-1]}\")" || echo "NO CALIB"
```

## Chequeo profundo (3 min)
```bash
# Posiciones activas (order_engine)
./bin/fleet_hours && cat logs/order_engine.log | tail -10 || echo "NO ORDERS"

# Fleet consensus (30/30 votaron?)
./bin/fleet_consensus 2>&1 | grep -E "(DANGER|GREEN|DIRECTION)" || echo "MUERTO"

# Dramas específicos
for sym in NVDA QQQ SMH MU TSLA; do
  echo "$sym: $(tail -1 data/bars_${sym}_ibkr.txt 2>/dev/null | cut -d, -f2-3 || echo 'SIN DATOS')"
done
```

## Alarmas amarillas
- Barras stale >5min: bridge caído
- NBBO stale >2min: TWS lento o gateway off
- Daemons <3 vivos: cluster fault
- Calibration.n<30 en alguna celda: setup poco medido
- Compass stale >1h: recalc roto

## Fuente propia
Scripts + config status
