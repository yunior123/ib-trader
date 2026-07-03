---
name: flip-and-vol-trigger
description: "Regimen gamma honesto: flip repreciado vs estatico con flip_src, TODAS las raices (la segunda raiz debajo del spot es trampilla y veta 0DTE comprado), congelacion del flip y del Volatility Trigger a las 09:35, y la licencia que da cada lado (arriba se fadea, abajo fadear esta PROHIBIDO). Usar en cada lectura de regimen, en cada cruce de flip y antes de fadear una banda estirada."
---

# flip-and-vol-trigger — dos lineas congeladas que reparten LICENCIAS

El flip y el VT no son señales: son **interruptores de licencia**. Dicen que CLASE de jugada esta
permitida hoy, y por eso deben ser **estables**. Un nivel que oscila no puede hacer crying-wolf
porque ya lo esta haciendo todo el rato.
Motor: `scripts/gex_core.py` (`_flip`, `flip_recompute`, `from_ibkr_cache`) +
`scripts/chart_levels.py` + `scripts/vol_trigger.py`. Fichas 6 y 20.

## 1. Los tres bugs vivos del flip

| Bug | Consecuencia |
|---|---|
| Pagamos `flip_recompute` y **luego lo descartamos** — `from_ibkr_cache` deja ganar a `flip_static` | el nivel de regimen que se canta no es el que se calculo bien |
| `_flip` devuelve **UNA** raiz | la **segunda raiz debajo del spot** es la trampilla, y no se ve |
| El flip **re-oscila intradia** | el cruce dispara y se desdispara; histeresis imposible |

`flip_recompute` es el correcto (SqueezeMetrics/Perfiliev): **recomputa la gamma BS a cada spot
hipotetico** del grid ±15% (120 pasos) porque **la gamma DEPENDE de S**, y halla la raiz por
interpolacion. `_flip` interpola el perfil estatico — mas barato, menos fiel.

## 2. Contrato de salida

```json
{"flip_open": 703.2, "flip_live": 705.9, "flip_src": "repriced|static_no_iv|none",
 "roots": [703.2, 691.4], "trapdoor_root": 691.4, "frozen_at": "09:35:04"}
```
- `flip_recompute` **GANA durante RTH**; si no hay IV → `flip_src='static_no_iv'`.
- `roots[]` = **TODOS** los cambios de signo de la GEX neta acumulada sobre la rejilla ±15%, cada
  cruce refinado por biseccion a `1e-4` del spot, ordenados por `|K − spot|`.
- `trapdoor_root` = la raiz mas cercana **DEBAJO** del spot dentro de 1× `em`.
- **`roots[]` se SUPRIME** salvo `n_strikes_populated ≥ 12` o snapshot completo de Polygon: sobre
  una banda de ±1.45% las raices extra pueden ser **bordes de ventana**, no cruces reales.
- Spot vivo de `data/nbbo_<sym>.txt`, **nunca** el spot rancio de la cabecera del fichero.

## 3. CONGELAR a las 09:35 — y quien usa cada version

| Campo | Uso |
|---|---|
**`flip_open`** (congelado 09:35) | **la etiqueta de regimen y el factor `flip` de la flecha usan ESTE, y solo este** |
`flip_live` | diagnostico. Se dibuja fino, no manda |
**`vt_open`** (congelado 09:35) | la licencia de fadear |
`vt_live` | diagnostico |

`flip_src='static_no_iv'` → **peso del factor flip ×0.5** y `why[]` imprime *"flip sin griegas"*
(insercion multiplicativa, ver [[direction-view-architecture]]).

## 4. Volatility Trigger: la ULTIMA ESTANTERIA DENSA, no el cruce por cero

Solo desde `chain_full_snap` y solo para syms con **≥40 strikes poblados** (ver
[[chain-data-contract]]).

```
VT = max{ K ≤ spot :  net_gex(K) > 0
                      y net_gex(K) ≥ 0.05·Σ|net_gex|
                      y ambos strikes vecinos poblados }
```
**NO es el gamma-cero.** Es la ultima estanteria densa de gamma positiva debajo del spot.
Fallback: el strike listado mas cercano a la raiz continua. `dist_vt = (spot − vt_open)/em`.
Pre-armado cuando `dist_vt < 0.35` **Y** fase de fuerza ∈ {GIRO, AGOTAMIENTO} **Y** el put wall
cercano **no** esta BUILDING.

## 5. TABLA DE LICENCIAS — lo que se puede hacer a cada lado

| Posicion | Licencia | Permitido | **PROHIBIDO** |
|---|---|---|---|
**spot > `vt_open`** | reversion a la media | fadear hacia el call wall, mariposas, venta de premium, trades de pin | perseguir extensiones fuera de la valla |
**spot < `vt_open`** | **MOMENTUM** | ampliar stops, operar rupturas con print a favor | **FADEAR ESTA PROHIBIDO**; sin trades de pin; sin venta de premium |
**spot ≥ `flip_open`** | POS: dealers amortiguan | muros son muros, imanes fijan | — |
**spot < `flip_open`** | NEG: dealers amplifican | rupturas con print | fadear %B extremo en el aire |
**`trapdoor_root` presente** | — | — | **VETO DURO sobre calls 0DTE compradas** |

> **Refinamiento de la REGLA 1 de la casa:** una banda de Bollinger estirada **en contra tuya por
> debajo del VT es CONTINUACION, no rebote elastico.** Arriba del VT la misma banda estirada SI es
> el rebote elastico. La misma lectura, dos veredictos opuestos, y el discriminador es el VT.

En la brujula: veto **V3** = *"bajo el VT <precio> congelado: fadear prohibido"* → estado
CONTINUACION, la flecha no gira. Veto **V2** = regimen NEG sin pin impreso.

## 6. Lo que se ELIMINO explicitamente (y no vuelve)

- **`eta_min`**, la pendiente Theil-Sen `dflip/dt`, `converge='dealer-driven'` y su **voz DANGER
  preventiva**. Razon: con **OI estatico de cierre previo** durante todo el intradia, `dflip/dt`
  mide **el spot moviendose bajo un libro congelado** — es un artefacto de spot/IV y **no puede
  medir posicionamiento llegando**. Misma tautologia que mato el "iman movil" de CoM.
- La narrativa de "velocidad del flip". No existe con estos datos.

## 7. Clase de voz

| Evento | Clase |
|---|---|
cruce de flip (2 prints) | **SIGNAL** — nunca DANGER |
cruce del VT (2 prints) | **SIGNAL** — nunca DANGER, hasta que el split de RV este medido |
trampilla gamma en el spot | **DANGER** (uno de los tres unicos autorizados, ver [[alert-budget]]) |
perdida del VT | **DANGER** (idem) |

## 8. Validacion (determinista primero, probabilidad despues)

1. **Test unitario**: la salida en RTH **iguala `flip_recompute`** (hoy iguala silenciosamente
   `flip_static`).
2. Contar sobre 20 sesiones cuantas veces `|flip_repriced − flip_static| > 0.3%·S`. **Ese numero
   ES el tamaño del bug.** Y cuantas veces una segunda raiz cae dentro de 1× `em` por debajo.
3. VT, post-backfill: clasificar cada sesion por apertura-vs-`vt_open` y comparar **vol realizada
   de 5 min y rango de Parkinson** a cada lado (SpotGamma publica **13% vs 18%** de RV a 5 dias);
   test de dos muestras con block bootstrap y correccion `n_eff`.
   **KEEP COMO VETO** si el acierto de los fades por debajo del VT es **<45%** (Wilson upper) con
   `n ≥ 60` sesiones; **kill** si los dos lados son indistinguibles.

Kill-risk honesto: si la estanteria es un artefacto de la escasez de la cadena, el nivel congelado
es arbitrario y la regla de prohibir-fadear **hace daño real**. Las guardas son la puerta de ≥40
strikes y el umbral de estanteria del 5%.

## 9. Al hablar

> *"QQQ 692.4, flip_open 703.2 congelado (repriced) → NEG: dealers amplifican. VT 698.1 →
> **fadear PROHIBIDO**. Segunda raiz 691.4 = trampilla dentro de 1 em: calls 0DTE VETADAS.
> Rupturas con print a favor, stops anchos."*

**SEÑAL-SOLAMENTE.**
