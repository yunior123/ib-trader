# BACKFILL DE BARRAS DE OPCIONES — 2026-07-25

**Encargo**: *"solve data insufficient issues"*. El cuello de botella medido era
`poly_opt_bars`: **114.337 filas, 8 símbolos, 940 contratos, 10-22 sesiones** (NVDA 22, el
resto 10). Varias features piden **60 sesiones** de superficie de IV y todas salían
DATA-INSUFFICIENT por el mismo motivo: no había materia prima, no faltaba código.

La IV del pasado **no se descarga** — Polygon no sirve griegas históricas en este plan — pero
**sí se reconstruye** invirtiéndola por bisección desde el precio del contrato
(`gex_core.implied_vol`). Lo que faltaba era el precio del contrato con historia. Eso es lo
que trae `scripts/poly_backfill_opts.py`.

---

## Lo que se midió contra la API con la key real (no recordado)

| Endpoint | Resultado | Evidencia |
|---|---|---|
| `/v2/aggs/ticker/O:<contrato>/range/1/day/{from}/{to}` | **MEDIDO OK** — devuelve la **vida entera del contrato en UNA petición** | `O:QQQ260515C00500000` → 73 barras diarias, 2026-01-05 → 2026-05-14, campos `v vw o c h l t n` |
| `/v3/reference/options/contracts?underlying_ticker=X&expired=true&expiration_date=<exacta>` | **MEDIDO OK** — 200, 1000/página, contratos vencidos reales | QQQ mayo-2026: 1000 resultados, 247 strikes, expiries 05-01/05-04/05-05, con `next_url` |
| `?as_of=<fecha>` en `/v3/reference/options/contracts` | **MEDIDO — SE IGNORA** | `as_of=2026-03-16` y `as_of=2025-09-15` devolvieron la **misma** primera página (expiries de **2011-03-25**). Es la misma trampa que el `as_of` del snapshot: `status OK` y el parámetro a la basura. **No se usa.** En su lugar se acota por `expiration_date`. |
| `/v2/aggs/grouped/locale/us/market/options/{fecha}` | **MEDIDO — HTTP 400**, no existe | habría sido 1 petición por fecha para toda la superficie; no está |
| `/v3/trades/O:` y `/v3/quotes/O:` | **403 NOT_AUTHORIZED** (ya conocido, no se reintentó) | `~/CLAUDE.md` |
| OI histórico | **NO EXISTE a ningún precio en este plan** | no se aproxima, no se afirma, no se escribe |

**Griegas y OI siguen sin existir para el pasado.** Este backfill trae `o h l c v` y nada
más. Quien necesite gamma/vanna del pasado invierte IV por bisección y calcula por
Black-Scholes (`gex_core.bs_gamma/bs_vanna/bs_charm`); quien necesite OI del pasado **no lo
tiene** y debe marcarlo `oi_source='proxy'` dentro del propio dato o callarse.

---

## La decisión de diseño: el orden, no el volumen

El presupuesto es **5 peticiones / 60 s** (ventana medida, `poly_client.py`): cada petición
cuesta 12 segundos de reloj. Pero como **una petición devuelve la vida entera de un
contrato**, la palanca no es pedir más sino pedir en el orden correcto.

Por eso el descargador trabaja por **rondas de moneyness**:

| Ronda | Qué pide | Peticiones | Qué desbloquea |
|---|---|---|---|
| 0 | ATM (`m=0`) de cada símbolo × expiry | 56 (+56 de catálogo) | la **estructura temporal ATM** de los 8 símbolos sobre la ventana completa |
| 1 | ±5% | 112 | primer par de la sonrisa |
| 2 | ±10% | 112 | sonrisa media |
| 3 | ±15% | 112 | borde de la banda pedida |
| 4 | ATM put + ±2,5/7,5/12,5% | 392 | densidad |

Cortarlo en cualquier ronda deja un resultado **útil**, no uno a medias. Esa es toda la
gracia del orden: la ronda 0 es el mejor cuarto de hora del backfill.

**Expiries**: los **mensuales** (3er viernes) de 2026-03 a 2026-09. Son los que viven meses,
así que un solo contrato cubre decenas de sesiones. Los semanales habrían costado lo mismo
por petición y habrían cubierto cinco días.

**Strikes**: rejilla de moneyness de **±15%** sobre el **spot mediano** de la ventana que
cada expiry cubre, leído de `poly_bars` (**0 peticiones** — 501 sesiones locales por
símbolo). Se toma el **OTM de cada lado** (put por debajo del spot, call por encima): es la
superficie que de verdad se usa, y cuesta la mitad que pedir ambos lados en todos los
strikes.

---

## Contención y leyes de la casa

- **Esquema de `poly_opt_bars` intacto**: mismas 11 columnas, misma `PRIMARY KEY(otk, ts)`,
  `INSERT OR IGNORE`. **Ni un `ALTER`, ni un `DROP`, ni un `DELETE`, ni un `VACUUM`** — hay
  features leyendo esa tabla. Un test audita el código fuente (sin comentarios) para que siga
  siendo verdad.
- Las barras nuevas son **diarias**, con `ts` a medianoche ET. Las **114.337 filas de 5
  minutos preexistentes no colisionan** con ellas y siguen ahí; hay un test que lo fija.
- `trades.db` pesa 1,5 GB y tiene otros lectores: `busy_timeout=60000` y **un commit por
  contrato** (transacción de milisegundos, nunca de minutos).
- **Fail-loud**: un contrato que falla queda `state='failed'` con el motivo y **se reintenta**
  al relanzar. `'empty'` (el contrato existe en el catálogo pero no cotizó en la ventana) es
  un **estado propio**, ni éxito ni fallo. Lo que jamás ocurre es *"done, 0 filas, todo bien"*
  — ese es el cero plausible que arruina un backtest sin que nadie se entere.
- Ningún `except` devuelve `0`, `0.0`, `0.5`, `{}` ni `[]`. Un test lo audita sobre la fuente.
- **SEÑAL-SOLAMENTE**: no pone órdenes. Lote fuera de sesión → Python legítimo.
- Rutas derivadas de `__file__`; informe y catálogos con escritura atómica (tmp + `os.replace`).

---

## Estado

<!-- RESULTADOS -->

---

## Uso

```
./venv/bin/python scripts/poly_backfill_opts.py plan     # qué se va a pedir y cuánto cuesta (0 peticiones)
./venv/bin/python scripts/poly_backfill_opts.py run --rounds 4 --max-req 500
./venv/bin/python scripts/poly_backfill_opts.py status
./venv/bin/python scripts/poly_backfill_opts.py report   # reescribe data/opt_backfill_report.json
```

Es **reanudable**: matarlo y relanzarlo retoma donde iba sin repetir peticiones (catálogos en
`data/opt_contracts/`, estado por contrato en `poly_opt_bf_progress`) ni duplicar filas
(`PRIMARY KEY(otk, ts)`).

Tests: `./venv/bin/python -m pytest tests/test_poly_backfill_opts.py -q` — sin red, todas las
respuestas HTTP mockeadas.
