---
name: low-iv-hunter
description: Cazar PRIMA BARATA a 10-15 DTE saltandose el bulto de IV de earnings — los tres filtros (vencimiento limpio de evento, IV ATM contra HV20/HV60 realizada, gate de spread de la casa), el bump de term-structure que localiza donde esta el evento, y por que IV/HV es la unica medida de "cara o barata" calculable sin archivo historico de IV. Usar cuando Yunior pida contratos baratos, prima barata, "low vix", opciones a 2 semanas, o antes de comprar cualquier opcion con un earnings cerca.
---

# low-iv-hunter — comprar volatilidad solo cuando esta barata de verdad

Orden Yunior 2026-08-12: *"find contracts with low vix up to 10-15 dte to skip earnings high vix"*.

Ejecutor: `scripts/low_iv_hunter.py`.

## El problema, medido el 2026-08-12

| nombre | evento | IV ATM | HV20 realizada | IV/HV |
|---|---|---|---|---|
| CSCO | earnings esa tarde | **127%** (2d) / 69% (9d) | 32% | **3.97x** |
| AMAT | earnings al dia siguiente | **122%** (2d) | 34% | 3.59x |
| KLAR | earnings en 6 dias | **118%** (9d) | — | — |
| AVGO | earnings en 21 dias | **40%** (9d) | 40% | **1.00x** |

El crush se lleva **42-100%** del boleto con el move MEDIANO (simulado sobre CSCO ese dia). La
prima barata no estaba en el nombre con noticia: estaba en el vencimiento que **no contiene** el
evento. El escaner existe para encontrar ese vencimiento sin mirarlo a ojo.

## Los tres filtros, en orden

**1. VENCIMIENTO LIMPIO.** Si la fecha de earnings cae entre hoy y el vencimiento, ese
vencimiento se descarta ENTERO. Es el filtro que mas prima ahorra. Se ve inmediatamente en la
term structure: AVGO 2026-08-12 tenia IV 37-42% hasta el 28-ago y **saltaba a 51%** el 4-sep,
el primer vencimiento despues del print del 2-sep.

**2. IV / HV.** Sin archivo historico de IV no hay IV-rank honesto (Polygon `?as_of=` es una
trampa: responde `status OK` y sirve el presente — ver [[chain-data-contract]]). La medida que
si se puede calcular es la implicita contra la **realizada**: HV20 y HV60 close-to-close
anualizadas. `IV/HV20 <= 1.15` por defecto.
Las dos se publican a proposito: **IV/HV20 bajo con IV/HV60 alto es una calma reciente, no una
ganga** — el nombre se movia mucho hace dos meses y puede volver.

**3. GATE DE SPREAD** canonico de `gate_core.hpp`: spread <= 5% del **MID** (no del ask), o
peaje `(ask-bid)/(|delta|*spot)` <= 0.60%, y `mid < $0.20` = veto directo (medido: 0/821
pasaron). Ver [[option-liquidity-gate]].

## El bump de term-structure

`bump = IV(vencimiento) / IV(vencimiento 20+ dias mas lejano)`.

- **bump > 1.25 en el corto** → el evento esta DENTRO de ese vencimiento corto.
- **bump < 1.0 con vencimiento limpio** → ya estas al otro lado del crush. Es donde se compra.

## Uso

```bash
python3 scripts/low_iv_hunter.py                          # flota, 10-15 DTE, $200, IV/HV<=1.15
python3 scripts/low_iv_hunter.py NET AVGO MRVL            # simbolos sueltos
python3 scripts/low_iv_hunter.py --dte 8 20 --budget 400  # ventana ancha (captura los viernes)
python3 scripts/low_iv_hunter.py --max-iv-hv 1.0 --json
```

**La ventana estrecha [10,15] se salta los viernes.** Muchos nombres solo tienen vencimientos
semanales: con 10-15 DTE un miercoles caen fuera tanto el viernes de +9d como el de +16d. Si
sale "SIN CANDIDATOS", mirar primero la linea de `descartes` y luego ampliar a `--dte 8 20`.

## Como se lee la salida

```
  AVGO  spot 419.57  HV20 40.4%  HV60 54.4%  earnings 2026-09-02 amc
       → 20260821   9d  IV  40.2%  IV/HV20 1.00  bump 0.82x  ✅ limpio
         20260904  23d  IV  51.4%  IV/HV20 1.27  bump 1.05x  🚫 earnings dentro
         descartes: fuera_ventana=8  oi=547  presupuesto=73  spread=3  delta=91
```

`→` = dentro de la ventana pedida. Los demas se muestran solo como contexto de term structure.
Los `descartes` dicen POR QUE no hay candidatos — sin ellos, "sin candidatos" no es un resultado,
es un silencio.

## Reglas que NO relaja este escaner

- **SIN CANDIDATOS es un resultado valido.** NO-TRADE es posicion (regla 6). Nunca bajar
  `--max-iv-hv` para que salga algo.
- IV barata **no es direccion**. El escaner dice *cuanto cuesta*, no *hacia donde va*. La
  direccion sigue viniendo del mapa ([[gamma-exposure]]), del print ([[print-o-nada-levels]]) y
  de Bollinger ([[bollinger-mastery]]).
- El **spot y el NBBO son delayed** (CBOE + Finnhub). Esto SELECCIONA candidatos; el print que
  confirma es de IBKR. Cadenas CBOE mas viejas de 3h se marcan `⚠CADENA RANCIA` — con una cadena
  rancia el spread NO es medible y el gate no significa nada.
- `earnings: sin dato` **no significa "no hay earnings"**: significa que Finnhub no lo dio. Se
  verifica a mano antes de comprar.

## Relacionadas

[[event-premium-discipline]] (el gate de EM vs move historico, que es el paso SIGUIENTE a este),
[[expected-move-envelope]], [[option-liquidity-gate]], [[chain-data-contract]],
[[strangle-scanner]].
