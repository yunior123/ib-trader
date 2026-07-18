---
name: finviz-picaro
description: Recetas pícaras de Finviz Elite — gappers, squeezes, swing, PEAD, insider, opciones, leverage. Usar cuando Yunior pida candidatos para operar (premarket, intradía, swing) o ideas nuevas. El ejecutor es ./scripts/picaro.sh.
---

# finviz-picaro — el arte de encontrar el trade antes que el resto (2026-07-17)

**Ejecutor**: `./scripts/picaro.sh <receta> [filas]` · `./scripts/picaro.sh list`
**Recetas** (editables en caliente): `data/picaro_recipes.txt` — 20 recetas en 7 familias, sintaxis validada en vivo.
Mecánica de la API: skill `finviz-elite`. Token: feeds.env.

## La rutina pícara del día
- **7:00-9:25**: `gappers` (o `gappers-calidad` para nuestro estilo con opciones) cada 10-15 min + `unusual-vol`. Candidato → noticia (v=320) → finviz_scout ya trae su short float/float → print de precio decide (playbook regla 1).
- **RTH**: `momo-extremo` y `squeeze` cuando el tape está direccional; `gap-down-fade` en nombres sanos.
- **Noche/finde**: `squeeze-radar`, `swing-pullback`, `breakout-52w`, `canslim`, `momo-burst`, `pead`, `insider` → watchlist del día siguiente.
- **Opciones**: `pre-earnings` (radar de IV → debit spreads, regla 6), `options-liquid`, `wheel`.

## Los trucos que valen dinero (del research 2026-07-17)
1. **`ta_perf_*`: la `o` es GANANCIA, la `u` es PÉRDIDA** (`ta_perf_d10o` = +10% hoy) — medio internet lo tiene al revés.
2. **Rangos custom Elite**: cualquier filtro numérico acepta `2to20` (`sh_price_2to20`); decimales OK (`sh_relvol_o1.5`).
3. **Elite ve el premarket REAL** (4:00-9:30) y after-hours (16:00-20:00) — col 71 = AH Close. Free es delayed = inútil para gappers.
4. **El catalizador no se filtra**: la 5ª pila de Ross (noticia) se verifica con `v=320` sobre el resultado, o el finviz_scout avisa ratings/targets.
5. Patrones (`ta_pattern_channelup`, `doublebottom`, `headandshoulders`... + sufijo `2` = estricto) y velas (`ta_candlestick_h` hammer...) — todos sobre DIARIO.
6. **Backtest casero**: guardar el CSV del export con timestamp cada día y medir forward returns = validar cualquier receta sin pagar nada.
7. Rotación sectorial: `groups.ashx?g=industry&v=210&o=-perf1w` → luego `f=sec_<ganador>` con momentum.

## Las trampas (respetarlas = sobrevivir)
- **Short interest de Finviz = FINRA bimensual, hasta 2+ semanas viejo** — el squeeze-radar da la lista, no el timing; cross-check Fintel/iBorrowDesk para borrow rate.
- Low float: cuidado reverse-splits (float bajo falso) y diluidoras seriales (SEC filings antes de tocar).
- PEAD: el gap-and-crap del día 1 — exigir cierre>apertura; entrar tras el cierre del día 1.
- Insider `sh_insidertrans` = neto 6 meses, NO detecta clusters — openinsider.com/latest-cluster-buys para el cluster real.
- `sh_opt_option` ≠ cadena líquida — SIEMPRE `./opt_quick SYM` (gates spread<5%/OI>500) antes del contrato.
- Momentum extremo (`momo-extremo`, `ipo-momo`) vive en zona de halts LULD — tamaño chico.
- **Ley de la casa**: la receta ENCUENTRA; el print + retest confirma (playbook reglas 1-2); las opciones pasan por opt_quick; señal-solamente.

## Encadenar con la flota
Candidato pícaro → añadir a `data/focus_ticker` (bot con prob% en 30s) → sirenas en `price-alerts.txt` → `./opt_quick SYM` para el contrato → finviz_scout vigila su short float/ratings solo.
