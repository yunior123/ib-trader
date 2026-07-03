---
name: premarket-brief
description: Assemble premarket brief (overnight context, Korea/Europe moves, spot NBBO, TA 15m/1m, fleet direction, compass, plan ficha) in <30 sec. Use for 9:12 APERTURA job or manual prep.
---

# Premarket Brief — Ficha de apertura

Preparar resumen para las 9:12 APERTURA: context overnight + TA + compass + plan.

## Comando (todo en 1 pasada)
```bash
cd ~/ib-trader

# 1. Context nocturno (Korea, futuros, VIX)
python3 scripts/korea_watch.cpp  # si compilado
cat data/nbbo_kodex200.txt 2>/dev/null | tail -1 | cut -d, -f2,3,4

# 2. Spot + TA rápido (QQQ/SPY)
for sym in QQQ SPY; do
  tail -10 data/bars_${sym}_ibkr.txt | cut -d, -f2,3,4,5,6 | python3 -c "
    import sys; lines=sys.stdin.readlines()
    if len(lines)>1: 
      c1,o2,c2=[float(lines[i].split(',')[j]) for i,j in [(0,1),(1,0),(1,4)]]
      print(f'${sym}: spot {c2:.2f}, change {100*(c2-c1)/c1:+.2f}%, TA: {c1<c2 and \"GREEN\" or \"RED\"}')"
done

# 3. Compass flecha
python3 -c "import json; d=json.load(open('data/compass_out.json')); print(f'Compass: {d.get(\"direction\",\"UNKNOWN\")} (prob {d.get(\"prob\",0):.1%})')" 2>/dev/null

# 4. Fleet consensus (¿manada decide?)
./bin/fleet_consensus 2>&1 | head -1 || echo "INIT"

# 5. Daily plan ficha (si existe)
ls -t logs/opening_plan_*.log 2>/dev/null | head -1 | xargs tail -5
```

## Salida esperada
```
Korea: KOSPI 2426.50 -0.3%
Futures: ES +28, NQ +85
QQQ: spot 429.10, change +0.8%, TA: GREEN
SPY: spot 558.25, change +0.4%, TA: GREEN
Compass: UP (prob 62%)
Fleet: 18/30 bullish, 7/30 bearish, 5 neutral
Plan: Breakout targets 432C, support 427.5P
```

## Fuente propia
Agregación de daemons + compass + plan
