# BARGAIN WATCH FLEET — 2026-08-05 (patrón NOK: C/P alto + calls líquidas + retail)

Orden de Yunior: 20 tickers "como Nokia la semana pasada" (C/P ~7, dealers bien puestos,
calls compradas con antelación). Banda $1–$25, opciones líquidas, comunidad retail viva.
**SEÑAL-SOLAMENTE. `data/bargain_fleet.txt` NO vota en MANADA** (fleet.txt intacto).

## Método (todo MEDIDO, EOD 2026-08-04 de Unusual Whales)
1. `/api/screener/stocks` banda $1–25, orden por `call_volume` y por `net_call_premium` (2 pasadas, ~55 candidatos).
2. Retail: apewisdom.io + tradestie (menciones WSB 24h) + Stocktwits/WebSearch.
3. Por candidato `/api/stock/{sym}/option-contracts`: contrato call ATM→+25% OTM, 1–50 DTE,
   **OI≥500 y spread NBBO ≤~6.5% del mid** (regla 4; NBBO de cierre — en RTH suele apretar).
4. `/api/stock/{sym}/greek-exposure`: en los 20, `call_gamma` domina 2–5x a `|put_gamma|`
   (libro cargado de calls). OJO convención UW: no distingue quién es dueño; con el flujo
   ask-side medido, el dealer está corto esas calls = combustible arriba si imprime.

## Los 20 (C/P = call/put volume 08-04; ΔOI = OI hoy − ayer del contrato objetivo)

| # | Sym | Prev | C/P | Net call prem | Contrato objetivo | OI | ΔOI | Spread | Catalizador / retail |
|---|-----|------|-----|--------------|-------------------|-----|-----|--------|----------------------|
| 1 | OPEN | 3.94 | 5.4 | +$1.22M | 08/07 4.5C @$0.18 | 27,299 | **+12,624** | 5.4% | Stocktwits "next GameStop"; ER pasó 08/04 |
| 2 | POET | 7.36 | 8.0 | +$1.15M | 08/21 9C @$0.79 | 4,367 | +153 | 6.4% | fotónica; WSB #52; ER 08/10 |
| 3 | BBAI | 2.86 | **15.3** | +$153k | 09/18 3C @$0.45 | 6,503 | +188 | 6.7% | AI defensa, lotto retail clásico |
| 4 | ZETA | 22.56 | 6.8 | +$2.21M | 08/07 25C @$1.69 | 4,040 | +818 | 4.7% | ER reportado 08/04; vol calls 12,880 |
| 5 | RGTI | 16.02 | 2.5 | +$1.70M | 08/07 17C @$1.26 | 4,261 | +2,226 | **3.2%** | quantum; ER 08/06 |
| 6 | SOFI | 18.03 | 2.1 | +$452k | 08/21 20C @$0.36 | **49,668** | +1,879 | 5.6% | retail perenne; masa de OI enorme |
| 7 | SOUN | 6.10 | 3.8 | +$369k | 08/21 7.5C @$0.33 | 19,555 | +259 | **3.1%** | AI voz; ER 08/05 |
| 8 | ONDS | 8.37 | 4.3 | +$143k | 08/21 9C @$0.83 | 27,688 | −505 | 4.8% | drones; WSB #55; ER 08/13 |
| 9 | ACHR | 4.84 | 6.8 | +$177k | 08/07 5C @$0.38 | 10,922 | +1,815 | 5.3% | eVTOL; ER 08/10 |
| 10 | USAR | 15.86 | 5.3 | +$917k | 09/18 20C @$1.62 | 8,326 | +235 | **3.1%** | tierras raras (onda MP); ER 08/10 |
| 11 | RUN | 10.43 | **10.5** | −$257k | 08/21 12C @$0.73 | 3,843 | +2,719 | **2.7%** | solar; ER 08/05 |
| 12 | PATH | 13.05 | 7.2 | −$325k | 08/07 14C @$0.47 | 10,549 | **+6,979** | 4.3% | RPA/AI; OI nuevo masivo |
| 13 | NVTS | 11.52 | 4.4 | +$856k | 08/21 12C @$1.64 | 5,143 | +661 | 4.9% | GaN / lazo NVDA |
| 14 | CLSK | 14.65 | 3.2 | +$1.56M | 08/21 17C @$0.52 | 3,812 | +126 | 5.8% | BTC miner; ER 08/06 |
| 15 | RDW | 9.64 | 4.9 | +$963k | 08/07 10.5C @$0.82 | 1,963 | +703 | 6.1% | space; ER 08/05 |
| 16 | QBTS | 19.98 | 3.1 | +$515k | 08/21 22C @$1.95 | 3,952 | +63 | 5.1% | quantum; ER 08/06 |
| 17 | DJT | 10.01 | **13.0** | +$316k | 08/21 10C @$0.98 | 2,391 | +164 | 5.1% | meme político |
| 18 | LUNR | 13.10 | 2.9 | +$957k | 09/18 15C @$1.95 | 762 | +96 | 5.1% | space retail; ER 08/13 |
| 19 | GME | 19.06 | 3.1 | −$1.11M | 08/07 19C @$0.45 | 5,010 | **+4,986** | 6.6% | el meme rey; OI del 19C se dobló |
| 20 | SNAP | 5.04 | 5.5 | −$330k | 08/21 5C @$0.84 | 13,458 | +483 | 5.9% | retail masivo; ER 11/04 |

Premiums objetivo $8–$195/contrato: **todos caben en el presupuesto ≤$200**.

## Manual watch override
- **SHOP** added 2026-08-05 after its Q2 earnings gap. It is outside the original
  $1–$25 NOK-style bargain screen and is watched specifically for post-earnings
  continuation versus gap-fade; it does not inherit the original basket thesis.

## Descartados con números (los que la comunidad ama pero la liquidez veta)
- **PCG** C/P 17.0 pero spread 20.5% (17C 08/28) y cero retail → institucional, fuera.
- **GRAB** C/P 13.6, spread 22% (mid $0.09). **IE** C/P 96 = un bloque único, spread 13%.
- **BRBR** spread 54%. **CCXI** 36%. **AMC** netC −$414k y ΔOI −2,765 en su 3C (calls vendidas).
- **MARA/WULF/BTDR** C/P ≤1.5. **SMR** C/P 1.9. **EOSE** netC −$1.0M + spread 9%.
- **CORZ/FSLY/FLNC/HTZ/NIO/SPCE/HL/UEC/QXO/FCEL/CRML/RIOT/AG** spread >6.5–15% en su mejor contrato.
- **AAOI $110 / ASTS $63.5 / RKLB $70** — top WSB (ranks 19/12/13) pero fuera de banda $1–25.

## Notas duras
- Datos EOD 08-04 (screener UW publica t−1). El spread NBBO es de cierre: **re-verificar
  spread vivo con `scripts/optgate.py` antes de pagar cualquier premium** (regla 4).
- 8 de los 20 reportan earnings esta semana (05–06/08): catalizador Y riesgo — jamás
  aguantar premium comprado a través del print de earnings (regla de la casa).
- RUN/PATH/GME/SNAP llevan net call premium negativo: el ratio y el ΔOI mandan ahí; vigilar
  que el flujo del día confirme antes de entrar.
- Cupo UW usado: ~1.5k/30k req. Endpoints nuevos validados: `screener/stocks` acepta
  `min/max_underlying_price`, `min_call_volume`, `order`, `ticker`.

## Infra bargain previa (NO tocada)
- `scripts/bargain_keepalive.sh` → `screener/bargain_scan.py` cada 10 min RTH →
  `data/screener/bargain_log_*.jsonl` (lanes Finviz `gainer_dip` etc.). Es OTRO animal:
  caza retrocesos de gainers por precio/volumen, **sin filtro de opciones**.
- Conexión natural (futuro, si se pide): pasar sus candidatos por esta misma medición UW
  (C/P + spread + OI) antes de cantar; `bargain_fleet.txt` es la lista semanal estática.
