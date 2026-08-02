---
name: whale-flow-reading
description: Cómo leer ballenas (flujo grande de opciones) y muros/imán/gamma-flip correctamente vía UW+IBKR+Polygon — distinguir apuesta direccional fresca de roll/hedge, y muros vivos de OI rancio pre-gap. Usar al analizar flujo de opciones, ballenas, o antes de operar una tesis basada en flujo.
---

# Lectura de ballenas y muros (destilado 2026-07-31)

## Fuentes (medido)
- **IBKR Gateway 4001** = spot/OI/griegas TIEMPO REAL (tick 100=volumen, 101=OI). Es el disparo.
- **UW** (`api.unusualwhales.com`, header `User-Agent: curl/*` o 403): `greek-exposure/strike?expiry=`, `max-pain`, `flow-alerts`. Da GEX/muros/flujo.
- **Polygon** `snapshot/options/{SYM}`: OI+griegas medidas (autoriza); pero `last-trade` da 403 (plan). Confirma OI de IBKR.

## Ballenas: direccional vs roll/hedge (LO MÁS IMPORTANTE)
El P/C premium bruto ENGAÑA. Para saber si una ballena es señal:
1. **Lado del agresor:** ASK-side = comprador (pagó el ask). BID-side = vendedor. Si UW no da bid/ask, usar AscendingFill=compra / DescendingFill=venta.
2. **Opening vs closing:** `vol > OI` (VOI>1) Y OI creciendo = APERTURA (posición nueva, direccional). `vol << OI` o OI plana = churn/roll/cierre.
3. **Comprar puts ask-side + opening = BAJISTA.** VENDER puts (bid-side) = ALCISTA/neutral (NO es ballena bajista — descartar). Comprar calls ask = alcista.
4. **Deep-ITM = trampa.** Un bloque enorme de puts/calls muy ITM (precio ≈ intrínseco) sobre OI ya gigante = **ROLL/CIERRE de hedge, NO convicción fresca.** Ej. medido: AAPL 325P "$12M" parecía apocalíptico = era roll del hedge de earnings; lo fresco real eran ~$2M near-money.
5. **VOI>1 solo NO discrimina** — hace falta lado + OI-previo (ver [[options-flow-in-analysis]]).
6. **Ballena "en posición" ≠ creciendo.** OI intacta + sin adds nuevos = posición sostenida pero enfriada (menos combustible). Validar con OI viva, no solo el premium de ayer.
7. **La convicción es POR VENCIMIENTO.** Medido: AAPL bajista Aug-7 (puts) pero ALCISTA Aug-14 (calls 310/312.5). El dinero grande puede ser bear una semana y bull la siguiente — mirar cada expiry, no agregar.

## Muros / imán / gamma tras un GAP
- **Después de un gap grande (−10% earnings), el max pain y los muros OI lejanos son RANCIOS (pre-gap).** Ej: AAPL max pain 327.5 con spot 300 = OI de cuando valía 333, no imán real. **Usar solo near-money.** (A veces el max pain se resetea el mismo día — verificar que el close ≈ spot.)
- **Muro real = mayor OI/GEX cercano al spot.** Ej AAPL: put wall 300/295, resistencia call 305/310 (ignorar 325/350 pre-gap).
- **Régimen = SIGNO del net GEX**, no el flip por strike (se distorsiona con OTM profundo). Neg = acelerante/whipsaw (trampilla: 1er toque del muro defiende ~70%, ruptura IMPRESA acelera). Pos = pin/estable. Ver [[gamma-regime-walls]].
- **Amplitud de muros cayendo:** contar cuántos de la flota tienen spot bajo su put wall (muro cayendo) = medida de la ruptura/selloff. Ej medido: 8/30 cayendo = liderado por semis/tech, no broad.
- **Capitán:** SMH puts grandes ask-side suelen marcar PISO local (rebote de la tropa), no continuación — no fadear sin print. Ver [[peer-captain-evidence]].

## Regla operativa
La ballena da la DIRECCIÓN; el PRINT del nivel da el timing. Una tesis basada en ballena sin el print del nivel (ej. AAPL bajista pero 300 no rompe) sangra theta. Print-o-nada: 2 lecturas cruzando el nivel, no "está cerca".
