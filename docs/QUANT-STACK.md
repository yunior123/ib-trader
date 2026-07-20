# QUANT-STACK — Stack de estadística cuantitativa (ib-trader)

Investigación + instalación de lo MEJOR que ya existe (sin reinventar) para estadística
cuantitativa de trading. Dos frentes: (1) librerías Python en `./venv`, (2) plugins/marketplaces
de Claude Code.

- **Fecha**: 2026-07-19
- **Entorno**: `~/Documents/GitHub/ib-trader/venv` — Python **3.9.6**, pip 21.2.4
- **Baseline crítico**: `numpy==2.0.2` (torch 2.8, numba, sklearn compilados contra numpy 2.x).
  Regla de oro: **ninguna instalación puede downgradear numpy**. Todo lo que forzaba downgrade se revirtió.
- Verificación: cada librería pasó un import + uso funcional real (ADF, GARCH, Hurst, AutoARIMA, corr, solve convexo).

---

## (a) Librerías instaladas esta sesión

| Librería | Versión | Categoría | Uso | Ejemplo 1 línea |
|---|---|---|---|---|
| **statsmodels** | 0.14.6 | Econometría / series | ADF, Johansen (cointegración), VAR/VECM, OLS, ARIMA, ACF/PACF | `from statsmodels.tsa.stattools import adfuller; adfuller(series)` |
| **arch** | 7.2.0 | Volatilidad / riesgo | GARCH/EGARCH/HARX, VaR, bootstrap Politis-Romano (stationary/circular), unit-root | `from arch import arch_model; arch_model(r, vol="Garch", p=1, q=1).fit()` |
| **hurst** | 0.0.5 | Régimen (mean-rev vs trend) | Exponente de Hurst: H<0.5 mean-reverting, H>0.5 persistente/tendencial | `from hurst import compute_Hc; H,c,_ = compute_Hc(prices)` |
| **pingouin** | 0.5.5 | Tests estadísticos limpios | corr (con IC + BF), t-test, ANOVA, normalidad, partial corr — API pandas-friendly | `import pingouin as pg; pg.corr(x, y)` |
| **statsforecast** | 2.0.3 | Forecast rápido (Numba) | AutoARIMA, ETS, Theta, AutoCES ultrarrápidos (JIT numba), backtesting de series | `from statsforecast.models import AutoARIMA; AutoARIMA().fit(y).predict(5)` |
| **cvxpy** | 1.7.5 | Optimización convexa | Optimización de cartera / pesos con restricciones (Markowitz, min-var, risk-parity a mano) | `import cvxpy as cp; cp.Problem(cp.Minimize(cp.quad_form(w,Sigma)),[cp.sum(w)==1]).solve()` |

**Deps arrastradas (sanas, sin downgrade de numpy)**: `patsy 1.0.2`, `pandas-flavor 0.7.0`, `xarray 2024.7.0`,
`tabulate 0.9.0` (pingouin) · `numba 0.60.0`, `llvmlite 0.43.0`, `coreforecast 0.0.16`, `utilsforecast 0.2.15`,
`fugue 0.9.6`, `pyarrow 21.0.0`, `narwhals` (statsforecast) · `clarabel 0.11.1`, `osqp 1.1.3`, `scs 3.2.11`,
`pybind11`, `xlsxwriter` (cvxpy).

> **cvxpy** quedó instalado como subproducto del intento de `riskfolio-lib` (ver omitidas). Es un solver
> convexo de primera y **soporta numpy 2.0**, así que se conservó a propósito: cubre la optimización de
> cartera que iban a dar riskfolio/skfolio, sin sus conflictos de dependencias.

### Ya presentes antes de esta sesión (no reinstalados)
`numpy 2.0.2`, `pandas 2.3.3`, `scipy 1.13.1`, `scikit-learn 1.6.1`, `stockstats 0.6.8` (indicadores técnicos),
`torch 2.8.0`, `stable_baselines3 2.7.1`, `gymnasium 1.1.1`, `yfinance 1.2.0`, `matplotlib 3.9.4`, `seaborn 0.13.2`.

### Verificación funcional (todo PASA)
```
statsmodels ADF stat: -1.709
arch GARCH loglik: -1111.6
hurst H: 0.48
pingouin corr r: -0.032
statsforecast AutoARIMA fit OK
cvxpy solve OK, status: optimal
```
Reproducir: `./venv/bin/python -c "import statsmodels, arch, hurst, pingouin, statsforecast, cvxpy; print('ok')"`

---

## (b) Omitidas (y por qué)

| Librería | Motivo |
|---|---|
| **riskfolio-lib** (7.0.1) | Instala, pero su dependencia `astropy 6.0.1` **fija `numpy<2`** y downgradeó `numpy 2.0.2 → 1.26.4`, rompiendo el baseline (torch/numba/sklearn compilados contra numpy 2.x). **Revertido** y numpy restaurado a 2.0.2 (regla: no forzar). Alternativa si se necesita: venv separado con numpy 1.26. Su nicho (optimización de cartera) queda cubierto por **cvxpy**, ya instalado. |
| **skfolio** | **No hay distribución para Python 3.9** (requiere >=3.10). Omitido: el venv es 3.9.6. Reevaluar si se migra a py3.10+. |
| **pandas-ta** | Sin distribución instalable en este py3.9/pip (`No matching distribution`); además la build de PyPI usa `numpy.NaN` (eliminado en numpy 2.0) → rompería en import. **stockstats 0.6.8** ya cubre indicadores técnicos. |
| **TA-Lib** | Requiere la librería C nativa del sistema (`brew install ta-lib`) + compilación del wrapper. Se evitó el build pesado (regla RAM 8GB / no compilaciones grandes). Redundante con stockstats. Instalable manualmente si hace falta: `brew install ta-lib && ./venv/bin/pip install TA-Lib`. |
| **mlfinlab** | Pins legacy incompatibles con py3.9 + numpy 2.0; el proyecto quedó mayormente comercial/gated. No aporta sin romper deps. Omitido. |

---

## (c) Plugins / marketplaces de Claude Code (quant / trading)

**Hallazgo honesto: Yunior YA tiene añadidos los marketplaces reputados y la mayoría de los buenos
plugins instalados.** No hace falta añadir casi nada; abajo está el inventario real + el único gap accionable.

### Ya INSTALADOS (verificado en `~/.claude/plugins/installed_plugins.json`)
| Plugin@marketplace | Qué aporta |
|---|---|
| `trading-market-analysis@claude-trading-skills` | Régimen de mercado, breadth, tendencias (tradermonty, 2.5k★) |
| `trading-stock-screeners@claude-trading-skills` | VCP, CANSLIM, breakout, pares |
| `trading-portfolio-risk@claude-trading-skills` | Position sizing, escenarios, opciones |
| `trading-strategy-tools@claude-trading-skills` | Backtesting, edge detection, hipótesis |
| `trading-earnings-timing@claude-trading-skills` | Calendarios earnings/macro, FTD |
| `trading-ideas@quant-sentiment-ai-claude-equity-research` | Research institucional BUY/SELL con price targets (643★) |
| `equity-research@anthropics-financial-services-plugins` | Research oficial Anthropic (financial-services) |
| `trading-indicators@local-plugins` | Pine/NinjaScript/Tradovate (indicadores) |

### Marketplaces AÑADIDOS pero con plugin SIN instalar (gap accionable)
- **agiprolabs/claude-trading-skills** (233★, MIT) — 67 skills de trading/DeFi/quant-finance (market data,
  on-chain, ML for trading, backtesting, execution). Marketplace ya añadido; el plugin `trading-skills` **no está instalado**.
  Fuerte para el lado cripto (**bitunix-bot**). Para instalarlo (correr tú en la UI):
  ```
  /plugin install trading-skills@agiprolabs-claude-trading-skills
  ```

### Otros marketplaces reputados YA conocidos por tu instalación (por si quieres explorar)
Añadidos en `known_marketplaces.json`: `K-Dense-AI/claude-scientific-skills` (140 skills científicas: series
ARIMA/GARCH), `lgbarn/trading-indicator-plugins`, `pasie15/claude-trading-skills-marketplace`,
`obra/superpowers-marketplace`, `trailofbits/skills-curated`.

### Comandos de referencia (por si hay que re-añadir alguno)
```
/plugin marketplace add agiprolabs/claude-trading-skills
/plugin marketplace add tradermonty/claude-trading-skills        # (repo: claude-trading-skills)
/plugin marketplace add quant-sentiment-ai/claude-equity-research
/plugin marketplace add anthropics/financial-services-plugins
/plugin marketplace add K-Dense-AI/claude-scientific-skills
```
> Nota: la instalación de plugins es interactiva (UI del usuario). Este doc deja los comandos listos;
> no se ejecutó ninguna instalación de plugin desde el agente.

---

## Resumen ejecutivo
- **Instaladas y verificadas (6)**: statsmodels, arch, hurst, pingouin, statsforecast, cvxpy — cubren
  econometría, GARCH/VaR, régimen (Hurst), forecast rápido, tests limpios y optimización de cartera.
- **numpy 2.0.2 intacto** (se revirtió el downgrade que metía riskfolio-lib/astropy).
- **Omitidas (5)** por incompatibilidad py3.9 / numpy 2.0 / build pesado — todas con sustituto ya presente.
- **Plugins CC**: el stack quant/trading reputado ya está instalado; único gap = instalar `trading-skills@agiprolabs`.
