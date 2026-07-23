---
name: gexa-framework
description: Marco de trading por estructura de dealers (destilado de los docs de gexa.ai) — taxonomía de niveles (POC, muros, imanes/aceleradores, rug-pull, gatekeepers), régimen/flip/fragilidad, ciclo de vida de nodos, tipo de entrega, los 11 setups de alta probabilidad, las 6 condiciones de NO-operar, bias, vanna/charm, amplificación 0DTE. Usar para leer un mapa GEX, clasificar niveles, decidir setup o sit-out, o interpretar régimen/flip. Complementa [[gamma-exposure]] (nuestro cómputo). SEÑAL-SOLAMENTE.
---

# gexa-framework — leer la estructura de dealers como gexa (2026-07-23)

**Idea central**: los market makers NO eligen comprar/vender en ciertos niveles — su gamma
los OBLIGA a cubrirse mecánicamente. El mapa GEX dibuja esos flujos forzados. Se opera CON
la corriente estructural, no contra ella. Nuestro cómputo vive en [[gamma-exposure]]/`gex_core`.

## Código de color (universal)
- **DORADO = IMÁN = GEX+ (dealer largo gamma)** → cubre CONTRA el precio (vende rallies, compra dips)
  → **atrae y fija (pin)**. Oro debajo = colchón (dealers compran ahí). Oro arriba = techo imantado.
- **MORADO = ACELERADOR = GEX− (dealer corto gamma)** → cubre CON el precio (compra fuerza, vende
  debilidad) → **repele y amplifica** (el precio pasa RÁPIDO). Morado debajo = trampilla/aire.
- El signo sale del libro crudo: gamma_call (dealer-largo) − gamma_put (dealer-corto), en $/1%.
  La influencia de un nodo **decae con la distancia** (uno a ±5pt pesa muchísimo más que a ±50pt).

## Régimen y flip (el interruptor de la sesión)
- **POSITIVO** (precio ARRIBA del flip): vol baja, rango, mean-reversion. Dips comprados, rallies
  fadeados. **Operar nodo-a-nodo** entre call wall y put wall, stops definidos.
- **NEGATIVO** (precio DEBAJO del flip): vol alta, tendencia, gaps. El hedging AMPLIFICA. Selloffs
  aceleran. **Operar rupturas, NO fadear.**
- **TRANSICIÓN** (±3pt del flip): régimen inestable, un empujón lo voltea → el Pre-Trade Gate VETA
  direccionales aquí.
- **Etiqueta del flip**: `+Γ DAMPENING` (libro positivo, amortigua) vs `−Γ AMPLIFYING` (amplifica).
- **Fragilidad** (banda ámbar entre el flip estándar y el "true flip" ajustado por vanna): banda
  **<5pt = régimen estable** (un movimiento de VIX no lo mueve); **>15pt = frágil** (un pico de VIX
  puede moverlo 10-20pt y voltear el régimen) → reducir tamaño o saltar.
- **Migration trail**: polilínea del flip a lo largo del día — **horizontal=estable · inclinada=derivando
  · dentada=oscilación por vol (señal de régimen NO fiable)**. El flip NO salta tick-a-tick; es
  estructural, se recomputa ~30s. Lo que se mueve en vivo es el precio-vs-flip.

## Taxonomía de niveles
- **POC** = strike de mayor |gamma| = máxima influencia del dealer. **Oro (imán)** → operar HACIA él
  (mejor pin). **Morado (acelerador)** → evento de bifurcación: dentro de ±10pt **NO direccional**,
  esperar 2 velas de dirección y operar la ruptura.
- **Call wall** = mayor gamma+ de calls arriba = techo (dealers venden acciones al acercarse).
  **Put wall** = mayor gamma− de puts abajo = piso (dealers compran al acercarse). Juntos = rango
  esperado de la sesión.
- **Muros que ruedan = señal direccional fuerte**: call wall baja de strike = bajista (retiran defensa
  arriba); put wall sube = alcista (piso se aprieta).
- **Gatekeeper** = nodo MORADO grande entre el precio y su objetivo/POC → **no operar a través**;
  fadear en él o esperar que se debilite (gamma fading entre snapshots).
- **Rug-pull zone** = dos strikes adyacentes uno call-dominado y el siguiente put-dominado → filo de
  cuchillo (aguanta de un lado, te compran; pierde del otro, te venden a través). **Fadear desde
  afuera, jamás apostar ruptura limpia sin confirmación de flujo.**
- **Nodo contrario** = strike cuyo signo de gamma contradice su lado del flip (acelerador morado
  ARRIBA del flip, o imán oro DEBAJO) → aviso de rug-pull localizado.
- **Air pocket** = tramo sin imanes (nada frena una caída hasta el otro lado).

## Ciclo de vida del nodo (regla del primer toque)
| Etapa | Toques | Fuerza | Nota |
|---|---|---|---|
| Fresh | 0 | máxima | nunca probado, dealers defienden fuerte |
| Tested | 1 | buena | 1er toque aguantó (dobles techos/pisos) |
| Weakening | 2 | desvanece | gamma cae entre snapshots, muriendo |
| Dead | 3+ | evitar | colapsó, NO fadear — probablemente rompe |
**1er toque > retests.** Gamma CRECIENDO entre snapshots = fortaleciéndose; DECRECIENDO = perdiendo
influencia (sin importar el conteo de toques).

## Tipo de entrega (cómo llega el precio importa tanto como el nivel)
- **Node walk** (nivel-a-nivel ordenado) = la más fiable, alta prob de reacción al siguiente.
- **Bounce** (rechazó y se aleja) = buen setup hacia el siguiente soporte.
- **Flush** (caída rápida por un air pocket) = reacción DÉBIL, el momentum puede seguir.
- **Squeeze** (short-cover/gamma squeeze) = volátil, menos fiable.

## Los 11 setups de alta probabilidad
1. **Clean Path** — sin gatekeepers precio→POC, régimen +: calls en dips, target POC, stop bajo soporte.
2. **Continuation** — colchones oro debajo + imanes oro arriba = el long de mayor prob.
3. **Support/Resistance** — precio en imán fuerte (1er toque fresco = mayor prob de aguantar).
4. **Air Pocket** — régimen −, sin piso oro, aceleradores morados debajo: puts en cualquier ruptura.
5. **Range Bound** — call wall arriba + put wall abajo: fadear los bordes, stops más allá de los muros.
6. **Gatekeeper Fade** — el nodo morado que bloquea se debilita → operar la ruptura al colapsar.
7. **Momentum Day** — nodos asimétricos (imanes de un lado, aceleradores detrás): operar pullbacks a favor.
8. **Trap** — colchón imán fino que oculta acelerador debajo (piso sin profundidad).
9. **Exhaustion** — estanca en call wall con gamma fading (techo) / rebota en put wall con menos fuerza (piso).
10. **Gamma Cluster Pin** — imanes apilados en rango estrecho → pin, sin edge direccional, esperar ruptura.
11. **Scattered** — imanes/aceleradores alternando sin patrón = ruido, sentarse.

## Las 6 condiciones de NO-operar (sit-out)
**Reshuffle** (3+ nodos cambiaron de signo → niveles inválidos) · **Fortress Pin** (todo positivo cerca,
tarde → sin edge) · **Midpoint Trap** (precio en mitad del rango call/put, R:R ~1:1) · **Air Pocket**
(negativo sin soporte, no atrapes el cuchillo) · **Power Hour** (tras 15:30 sin patrón, dominan flujos
mecánicos) · **Purple POC Bifurcation** (±10pt de POC morado, binario, esperar dirección).

## Bias (flujo + estructura; estricto)
- **BULLISH**: calls > 1.5× puts **Y** precio > max pain **Y** existe call wall.
- **BEARISH**: puts > 1.5× calls **Y** precio < max pain.
- **CALL FLOW / PUT FLOW**: el flujo se inclina pero la estructura NO confirma.
- **NEUTRAL**: nada paga — respuesta honesta de "sin edge aún".

## Vanna, charm, 0DTE
- **Vanna (VEX)**: cómo cambia el delta del dealer con la IV. IV cae (post-apertura) → re-hedge SIN
  que el precio se mueva → rallies en IV crush. **GEX y VEX alineados en el mismo strike = zona de
  confluencia** (doble refuerzo, mayor prob de aguantar/revertir). Vanna+ = combustible melt-up
  (dealers compran al caer IV); vanna− = combustible de caída.
- **Charm**: decaimiento del delta con el tiempo → flujo intradía predecible que **acelera al cierre**
  (el "afternoon drift"/pinning tardío del SPX).
- **0DTE**: gamma altísima (poco tiempo) → hedging agresivo, el perfil se reorganiza en minutos, pin
  extremo al expiry, rupturas violentas. Exige data en tiempo real (el mapa cambia todo el día).

## Checklist para leer el mapa
1. Régimen (¿arriba/abajo del flip?) → expectativa de vol. 2. POC (¿oro imán u morado bifurcación?).
3. Muros (call=techo, put=piso = rango). 4. Path (¿limpio de gatekeepers precio→POC?). 5. Nodos cercanos
(oro abajo=colchón, morado abajo=aire). 6. Salud del nodo (fresh/muriendo, creciendo/cayendo). 7. Síntesis.

## Qué tenemos vs qué es sustituto honesto
- **Tenemos** (OI+griegas, `gex_core`/chart): GEX por strike $/1%, net, régimen, flip, muros, imán/
  acelerador, POC/abs, perfil, tiempo real. **Buildeable**: vanna/charm/VEX, toggle 0DTE/all-exp,
  dealer-pressure −100..100, expected-move cone, pin-risk, %C/%P dominance, nuestras señales como marcadores.
- **NO tenemos** (necesitan tape firmado + dark-pool licenciado): True Dealer Book (TAPE), Dark Pool
  Nodes, DIX, Market Tide firmado, GEX direccional, sweep/golden-sweep. **Sustituto casero**: nuestros
  daemons whale/flow/bollinger (partial, honesto — no tape-grade). Ver [[whale-alarm-napoleon-sword]] [[flow-captains]].

## Ley
Nada de esto es consejo financiero — es un mapa educativo de flujos mecánicos. Entradas/tamaño/riesgo
son del trader. El print manda la entrada; la estructura da la paciencia. SEÑAL-SOLAMENTE.
