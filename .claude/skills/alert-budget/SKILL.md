---
name: alert-budget
description: "Presupuesto de alarmas: registro de emisores, numero de DANGER CONGELADO (uno nuevo desplaza a uno viejo), voz solo por celda calibrada y PROVEN, cooldown de 10 minutos con histeresis, tope de 40 locuciones al dia y registro de cada supresion con su motivo. Usar al añadir cualquier alarma, sirena o voz nueva, y cuando la flota empiece a hablar demasiado."
---

# alert-budget — la fatiga de alertas es el unico fallo SIN remedio posterior

Un bug de calculo se arregla mañana. Una sirena que Yunior aprendio a ignorar **no se recupera**:
deshabilita en silencio el sistema entero, y es exactamente hacia donde camina un roster de 30
features. Ficha 12 de `docs/FEATURES-MINED-2026-07-25.md`.

## 1. El numero que define el problema

```
voice_log:  284 locuciones EN TOTAL     signals:  3233
El set de propuestas añadia ~14 emisores de voz NUEVOS × 30 syms.
```
Hoy hablamos ~28 veces por sesion. 14 emisores × 30 syms sin gobierno son cientos. **La sirena
sobrevive por escasez, no por diseño** — hasta ahora.

## 2. El registro de emisores: nadie habla sin estar inscrito

`data/voice_registry.json` lista **CADA** emisor:
```json
{"id": "flow_pulse.spike_puts", "module": "flow_pulse.cpp",
 "class": "SIGNAL", "calib_cell": "flow|puts|POS", "enabled": true}
```
Sin fila en el registro, el emisor **no habla** — ni siquiera si su codigo llama a `speak.sh`.
Un emisor sin `calib_cell` es un emisor sin evidencia: banner.

## 3. Las cinco reglas que imponen `speak.sh` / `voice_queue.sh`

| # | Regla | Detalle |
|---|---|---|
**a** | **El conteo de emisores DANGER esta CONGELADO** en el de hoy + 1 | un DANGER nuevo **debe DESPLAZAR** a uno existente. Ninguna excepcion |
**b** | Un emisor habla solo si su veredicto de `null_control` es **PROVEN** y su celda tiene `n_eff ≥` umbral | si no → **banner** ([[measured-probability]]) |
**c** | **Cooldown 10 min por sym** + **histeresis**: el gatillo debe re-entrar ±1σ antes de re-armarse | punto 3 de la doctrina: una señal marginal que titila en la frontera **no es señal** |
**d** | **Tope duro de 40 locuciones/dia** (hoy ~28/sesion) | desbordamiento → banner + **un unico digest ntfy** |
**e** | **CADA supresion se REGISTRA** en `voice_log` con `{emitter, class, reason}` | cero descartes silenciosos: si el presupuesto se come algo, se ve |

**DANGER nunca es suprimido por el presupuesto** — solo SIGNAL/INFO. El presupuesto prioriza por
clase, no por orden de llegada.

## 4. Los tres unicos DANGER autorizados

| DANGER | Por que | Skill |
|---|---|---|
**trampilla gamma en el spot** | el precio atraviesa acelerando; fadear ahi es el error caro | [[book-quality-veto]] |
**perdida del VT** | cambia la LICENCIA: fadear pasa a estar prohibido | [[flip-and-vol-trigger]] |
**reescritura material de truth-lock** | la muestra cambio bajo los pies (banner+ntfy por ahora) | [[sample-integrity]] |

Todo lo demas es **SIGNAL** o **INFO**. En particular: el cruce de flip es SIGNAL, el cruce del VT
es SIGNAL, un muro tocado es SIGNAL, un spike de flujo es SIGNAL.
**Ningun DANGER nuevo sin una retirada.**

## 5. La ley de embarque: MUDA por defecto

> **Una feature embarca MUDA y gana voz UNA CELDA CALIBRADA A LA VEZ.**

Aplicado hoy:
- `level-react` embarca con la **voz deshabilitada para TODA fuente** (~30 bots consolidados; si
  hablara, seria spam × niveles × syms).
- Todas las features en sombra (`chain-delta`, `close-drift`, `skew-lead`, `expiry-unwind`
  direccional, `gap-islands`, `kde-levels`, `wall-decay`) tienen **voz suprimida** por diseño.
- Una celda recupera voz solo con Wilson-LB ≥ null + margen del dominio y `n_eff` suficiente.

## 6. Interaccion con la jerarquia de capitanes

De la regla 12: **señal de nombre con capitan opuesto vigente = banner sin voz; la voz es del
capitan** ([[flow-captains]]). Y con `cor_fleet` ([[peer-captain-evidence]]):

| Regimen de correlacion | Efecto sobre la voz |
|---|---|
`MACRO` (ρ alta) | regla 12 a plena fuerza: el capitan opuesto **ANULA** la señal del nombre → banner |
`DISPERSION` (ρ baja) | el capitan opuesto solo **degrada DANGER a SIGNAL** |

Eso es presupuesto de alarmas hecho con fisica del mercado en vez de con un contador.

## 7. Validacion (contable, no estadistica)

1. Contar locuciones por sesion sobre **10 sesiones** antes/despues.
2. Afirmar que **ninguna sesion pasa de 40**.
3. Afirmar que el **conteo de emisores DANGER es CONSTANTE**.
4. Afirmar que **TODA** supresion tiene su fila de motivo (cero descartes silenciosos).
5. Linea de presupuesto semanal de locuciones en el email diario — el coste tiene que ser visible.

Kill-risk reconocido: **los topes duros pueden suprimir la locucion que importaba.** Mitigacion:
prioridad de clase, digest ntfy, y registrar cada supresion para que el coste se pueda auditar en
vez de discutir.

## 8. Checklist antes de añadir cualquier voz

1. ¿Esta el emisor en `voice_registry.json` con `class` y `calib_cell`?
2. ¿Su celda es **PROVEN**? Si no → banner, y punto.
3. Si es DANGER: **¿que DANGER retira?** Sin nombre, no entra.
4. ¿Tiene cooldown 10 min + histeresis ±1σ?
5. ¿Su supresion se registra con motivo?
6. ¿Cabe en 40/dia junto con los que ya hablan?
7. ¿Su voz es **preemptiva** (antes del pico) o tardia? Una voz que llega tarde gasta presupuesto y
   compra el retroceso EN EL MAXIMO (regla 10, memoria `chart-cockpit-complete`).

## 9. Al hablar (formato de la propia voz)

Corto, un numero, una accion. *"QQQ muro 690 segundo toque, regimen POS"*. Sin adjetivos, sin
"posiblemente". Si no hay probabilidad medida, **no se dice un numero** — se dice el hecho.

**SEÑAL-SOLAMENTE**: el gobernador solo silencia y registra; jamas ordena.
