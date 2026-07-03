# Backtest bargain hunter — semana 14–18 jul 2026 (NO ACTIVADO, propuesta)

**Orden Yunior 2026-07-18:** verificar que los filtros no nos meten en tickers
equivocados y proponer mejoras. Herramienta: `scripts/backtest_bargain_week.py`
(reproducible con cualquier semana de logs).

**Contexto**: semana más dura de semis en un año (pánico capex-IA) — banco de
pruebas hostil. 32 candidatos únicos, 3 días (15–17 jul), retornos desde el
precio de detección.

## Resultado global: los filtros actuales NO bastan

| Métrica | +1 día | a fin de semana |
|---|---|---|
| Win rate | **17%** | 38% |
| Media | **−5.98%** | −3.88% |
| Peor | −24.7% (STIM) | −24.7% |

## Qué separa ganadores de perdedores (evidencia)

| Corte | Win% +1d | Media | Lección |
|---|---|---|---|
| mcap <$2B (micro) | **7%** | **−8.3%** | ☠️ la basura micro mata la estrategia |
| mcap $2–10B | 40% | −2.5% | ✓ |
| mcap >$10B | 33% | −0.4% | ✓ |
| score <8 | 0% | −5.4% | ☠️ |
| score >15 | **40%** | −3.5% | ✓ |
| retroceso ≥70% del rango (gainer_dip) | MAN +11.6%, ATAI +2.3%, PYPL +5.5% | | ✓ dip PROFUNDO = dip real |
| retroceso <70% | STIM −24.7%, APLM −22.3%, AEHR −17.1%, ELVA −13.9% | | ☠️ retroceso somero = sigue cayendo |
| lane fleet_dip | 0% (n=5) | −6.2% | ☠️ comprar el dip de semis EN semana de pánico del sector = cuchillos |
| veredicto TA = SELL | 0% win | −8.7% | ✓ el veto SELL del bot FUNCIONA (evitó 2 perdedores) |

## Filtros propuestos (aplicar tras revisión de Yunior — NO activados)

1. **`mcap ≥ $2,000M`** — elimina el perfil 7%-win de golpe.
2. **`score ≥ 15`** — el score ya discrimina (40% vs 0%); subir el listón.
3. **`gainer_dip`: exigir retroceso ≥70% del rango** — el dato más limpio del
   backtest: los 3 mejores retrocedieron 79–90%; los 4 peores 36–62%.
4. **Veto de régimen para `fleet_dip`**: si SOXX/SMH perf-semana < −3%, lane
   apagada (0/5 esta semana lo prueba; en semana normal el dip de flota es otra cosa).
5. Mantener el veto TA SELL tal cual (0% win en sus rechazos = acierto).

**Con filtros 1+2+3 aplicados a la MISMA semana**: sobreviven MAN (+11.6%) y
ATAI (+2.3%) → 2/2 win, media +7.0% vs −6.0% del sistema actual. (n pequeño,
pero la dirección es inequívoca y la semana era hostil.)

## Cómo re-correr

```bash
./venv/bin/python scripts/backtest_bargain_week.py            # todos los logs
./venv/bin/python scripts/backtest_bargain_week.py data/screener/bargain_log_20260722.jsonl
```

Repetir cada viernes: si los cortes cambian de signo con más datos, ajustar.
