# ESTADO DEL DESPLIEGUE — ib-trader (2026-08-23, 00:38 EDT)

Generado con `bash scripts/deploy_check.sh` (reejecutable; `exit 1` si hay críticos).
El checker lo escribió el agente de despliegue; este informe es la lectura verificada de su salida.

## Los tres cubos

### SANO — verificado ahora
- **Binarios C++**: todos los de `bin/` son más nuevos que su `.cpp`. Nada que recompilar.
- **Cockpit**: 6 ventanas vivas.
- **Logs**: ningún `.log` tocado en la última hora trae error.
- **Rutas de los jobs**: 0 plists con ruta rota, 0 con `exit != 0`.
- **Único job activo**: `com.ibtrader.chartqa`, exit 0.

### PARADO A PROPÓSITO — no es una avería
- **Fuera de la ventana horaria**: la flota va de domingo 20:00 a viernes 20:00 (Toronto). Ahora es domingo 00:38:
  faltan **19 h 21 m** para el arranque. Que los bots estén parados es correcto.
- **Centinela de sueño manual activo** desde el 2026-08-14: `data/fleet_sleep` dice
  *"manual sleep: 2026-08-14 (solo software: cockpit + feed, sin bots de señal)"*.
  Mientras exista ese fichero, `fleet_keepalive_start.sh` para todo y sale.
- Encaja con la orden vigente de **no usar IBKR esta semana**.

### DECISIÓN PENDIENTE — no lo toco sin que Yunior lo diga
- **39 de los 40 jobs `com.ibtrader.*` están DESHABILITADOS en el override de launchd.**
  Comprobado con `launchctl print-disabled gui/502`: 40 entradas `=> disabled`.
  Esto **persiste al reiniciar**: no es el centinela de sueño, es una capa distinta y más pegajosa.
  - Si es intencionado (parada larga mientras no se usa IBKR), no hay nada que hacer.
  - Si no lo es, la flota **no arrancará sola** el domingo a las 20:00 aunque se borre `data/fleet_sleep`.

**Reactivar (solo cuando Yunior lo pida):**
```bash
for f in ~/Library/LaunchAgents/com.ibtrader.*.plist; do
  l=$(basename "$f" .plist)
  launchctl enable gui/502/$l
  launchctl bootstrap gui/502 "$f"
done
rm -f data/fleet_sleep     # y esto para levantar el centinela de sueño
```
No se ejecuta a ciegas: son 39 procesos que despertarían buscando TWS, que esta semana está prohibido.

## Lo que NO se ha podido verificar hoy
- Nada que dependa de **IBKR/TWS** (prohibido esta semana) ni de **mercado abierto**: puentes de barras,
  cadenas en vivo, gates de spread, alarmas de flujo. Con la flota dormida, un "ok" ahí no significaría nada.
- El comportamiento del arranque del domingo 20:00: solo se puede comprobar el domingo a las 20:00,
  y depende de la decisión de arriba.

## Cómo se vuelve a mirar
```bash
bash scripts/deploy_check.sh          # informe completo
bash scripts/deploy_check.sh --quiet  # solo CRIT y AVISO — apto para cron
```
Salida de hoy: **0 críticos · 5 avisos** (los cinco son los dos bloques de "parado a propósito" y "pendiente").
