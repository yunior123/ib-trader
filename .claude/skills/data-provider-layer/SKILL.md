---
name: data-provider-layer
description: Capa genérica de proveedores de datos en mit/ (Market/Options/Depth/Flow por capacidad, registro por decorador, selección por nombre, puente TONTO a los ficheros de la flota). Usar para AÑADIR o CAMBIAR un proveedor (intrinio/polygon/databento/unusual_whales/IBKR-futuro), entender el toggle data/market_source.txt, o cablear el provider_bridge. SEÑAL-SOLAMENTE.
---

# data-provider-layer — un fichero por proveedor, servicio genérico intacto (2026-08-01)

Capa en `mit/backend/app/providers/`. **Idea MVVM: el adaptador de la API es lo ÚNICO que
cambia; el servicio genérico (registry + build_providers + provider_bridge) queda intacto.**
Existentes: `polygon` (market+options), `intrinio` (market+options), `databento` (market+depth)
+ `databento_live`, `unusual_whales` (flow), `mock` (las 4, fallback). SEÑAL-SOLAMENTE.

## 1. Contrato por CAPACIDAD (`base.py`)
Cuatro ABCs async, cada una una capacidad independiente:
- **`MarketDataProvider`** — `get_quote(symbol)->Quote`, `get_bars(symbol,interval,limit)->list[Bar]`,
  `get_daily_bars` (default llama a `get_bars` 1d), `close()`.
- **`OptionsDataProvider`** — `get_option_chain(symbol,expiration=None)->list[OptionContract]`.
- **`DepthDataProvider`** — `get_order_book(symbol,depth)->OrderBook`.
- **`FlowDataProvider`** — `get_option_flow(symbol,limit)->list[OptionFlow]`.
Un proveedor implementa SOLO las que soporta (herencia múltiple: `class X(MarketDataProvider,
OptionsDataProvider)`). Dominios en `backend.app.domain`.

- **`ProviderError`** (`base.py:9`) — RuntimeError con contexto estructurado opcional
  (`provider`/`capability`/`error_code`, todos default `None` → los `raise ProviderError("msg")`
  desnudos siguen valiendo). En camino de señal un error levanta o devuelve `None`; **jamás un
  cero/valor plausible**.
- **`UnavailableProvider`** (`base.py:90`) — implementa las 4 ABCs y cada método hace `_raise()`.
  Es el placeholder que **preserva el arranque del proceso** y dispara el fallback local por
  capacidad cuando un proveedor no existe / falla al construirse / no declara la capacidad pedida.

## 2. Registro por decorador (`base.py:30`)
```python
PROVIDER_REGISTRY: dict[str, type] = {}
@register("polygon")                      # el nombre = valor de MIT_<CAP>_PROVIDER
class PolygonProvider(MarketDataProvider, OptionsDataProvider):
    name = "polygon"
    __capabilities__: set[str] = {"market", "options"}   # capacidades DECLARADAS
    def __init__(self, settings: Settings) -> None: ...   # lee sus keys aquí
```
- **`__capabilities__`** es load-bearing: `registry.py:83-93` **rechaza una capacidad no declarada
  SIN instanciar la clase** — evita `__init__` con efectos secundarios (p.ej. `unusual_whales`
  lanzando tasks) cuando se pide una capacidad que el proveedor no da. Hay además fallback
  `isinstance` por seguridad. **Declara siempre `__capabilities__`.**
- `mock` NO usa `@register`: `registry.py` lo importa directo como `fallback` de `ProviderSet`.

## 3. Auto-descubrimiento + build por capacidad (`registry.py`)
- **`_discover()`** (`registry.py:25`): `pkgutil.iter_modules` importa cada `providers/<x>.py`
  (orden determinista; salta `_*`, `base`, `registry`) para que sus `@register(...)` llenen el
  registro. Un import que falla (dep opcional ausente O bug) → **WARNING, no silencio** → ese
  nombre queda desconocido → `UnavailableProvider` al pedirlo.
- **`build_providers(settings)->ProviderSet`** (`registry.py:66`): resuelve las 4 capacidades por
  nombre, con caché; cualquier excepción al construir → `UnavailableProvider(name, msg)`. Devuelve
  `market/options/depth/flow` + `fallback` (Mock). `ProviderSet.close()` cierra todo con timeout,
  una `close` mala no aborta el resto.

## 4. Selección por nombre (`config.py`)
- **`ProviderName = str`** (str LIBRE, no `Literal` cerrado) → añadir proveedor = 1 fichero
  auto-registrado, **sin tocar `config.py` ni `registry.py`**. Nombre desconocido → Unavailable →
  el bridge aborta fail-loud.
- Selectores: `MIT_MARKET_PROVIDER` / `MIT_OPTIONS_PROVIDER` / `MIT_DEPTH_PROVIDER` /
  `MIT_FLOW_PROVIDER` (default `mock`).
- **`_export_to_environ()`** (`config.py:21`) vuelca `config/feeds.env` a `os.environ` con
  `setdefault` (no pisa lo ya presente) → un proveedor NUEVO lee su key con
  `os.environ.get("MIPROV_KEY")` en su `__init__`, sin añadir campos a la clase `Settings`
  (aunque los proveedores existentes SÍ tienen sus campos tipados en `Settings`).

## 5. CÓMO AÑADIR UN PROVEEDOR (el flujo entero)
1. Crear **UN** fichero `mit/backend/app/providers/<x>.py`:
   ```python
   from backend.app.providers.base import MarketDataProvider, ProviderError, register
   @register("<x>")
   class XProvider(MarketDataProvider):
       name = "<x>"
       __capabilities__: set[str] = {"market"}
       def __init__(self, settings):
           key = settings.<x>_key or os.environ.get("<X>_KEY")
           if not key: raise ProviderError("<X>_KEY required")   # fail-loud, no arranca sin key
       async def get_quote(self, symbol): ...   # Quote real o levanta; nunca cero plausible
       async def get_bars(self, symbol, *, interval="5m", limit=1200): ...
   ```
2. Poner su key en `config/feeds.env` (`<X>_KEY=...`). **No** hardcodear keys en el skill ni en código.
3. Apuntarlo: `MIT_MARKET_PROVIDER=<x>` en `feeds.env`, o `data/market_source.txt` = `<x>` (ver §6).
   `_discover()` lo registra solo; **registry y config no se tocan**.
4. Verificar: `./venv-mit/bin/python scripts/provider_bridge.py --once SPY QQQ`.

## 6. Toggle en vivo: `data/market_source.txt`  (`ibkr` | `<provider>`)
Un archivo, una palabra. Lo leen `fleet_up.sh`, `fleet_keepalive_start.sh`, `fleet_consensus.py`.
- **`ibkr`** (default): feed por los puentes IBKR dedicados (`ibkr_bar_bridge.py` +
  `opt_chain_cache.py`), realtime, exige Gateway/TWS.
- **cualquier otro nombre** (`intrinio`, `polygon`…): `fleet_keepalive_start.sh:209` hace
  `export MIT_MARKET_PROVIDER="$MARKET_SOURCE"`, MATA los escritores IBKR de los mismos ficheros
  (para no duplicar) y arranca `provider_bridge.py --daemon`. Gateway ya no hace falta para market
  data (solo para órdenes). `fleet_consensus.py:29` ajusta el denominador de MANADA según el source.

## 7. El puente TONTO: `scripts/provider_bridge.py` (venv-mit, py3.12)
Mueve bytes de la capa genérica a los MISMOS ficheros que ya lee la flota C++. **Cero cómputo de
señal** (doctrina: los puentes mueven bytes). Escribe por símbolo de `data/provider_syms.txt`
(o `fleet.txt`):
- `data/bars_<sym>_ibkr.txt` — `EPOCH O H L C V` (min-alineado, epoch estrictamente creciente).
- `data/nbbo_<sym>.txt` — `EPOCH BID ASK`, atómico.
- `data/opt_chain_<sym>.txt` — 3 cabeceras + filas, mismo contrato que `opt_quick.cpp`.

El **sufijo `_ibkr` se conserva** porque 21 bots lo tienen cableado — la procedencia REAL va en el
header + `data/provider_status.json`, **nada miente**. Reglas duras:
- **GUARD anti-mock** (`run()`): si `market`/`options` resuelven a `Mock`/`Unavailable`, **ABORTA**
  (`SystemExit`) — jamás inyectar sintético en los ficheros de la flota (`IBT_ALLOW_MOCK=1` SOLO
  tests offline).
- **Fail-loud por capacidad/símbolo**: un error de un símbolo se registra y sigue; NBBO/spot
  inválidos NO se escriben (nada de cero plausible).
- **epoch = tiempo REAL de bolsa** (`q.timestamp`), NO wall-clock → el gate de frescura de los
  bots (`now-ep<=10s`) **falla-cerrado** con dato delayed en vez de tratar un spread de hace 15 min
  como vivo. `provider_status.json.epoch` + `last_exchange_ts` = para medir latencia.
- **Keys redactadas** en logs (`_scrub`, `api_?key=` → `***`).

## 8. IBKR como proveedor FUTURO (deshabilitado temporalmente)
Hoy el toggle `ibkr` usa los puentes dedicados legados (`ibkr_bar_bridge.py`/`opt_chain_cache.py`),
NO un proveedor de esta capa. IBKR encaja como `providers/ibkr.py` con `@register("ibkr")` +
`__capabilities__={"market","options","depth"}` (adaptador `ib_async`, realtime, prioridad en todo
el camino vivo). Al existir, `market_source.txt=ibkr` podría unificarse a esta capa. Está pendiente,
no roto — la capa ya lo contempla (base.py:26-29). Latencia de fuentes: ver skill `gamma-exposure`
§6 y `docs/LATENCIA-FUENTES.md` (IBKR realtime, Polygon 15min, CBOE delayed).

## 9. Un fallo TRANSITORIO deja un ticker mudo — reintentar (medido 2026-08-02)
`provider_bridge` no reintentaba la cadena: **un solo `ReadTimeout` dejaba al símbolo sin
`data/opt_chain_<sym>.txt` toda la sesión**. Cazado por `scripts/e2e_smoke.sh`: NFLX, GLD y XLK
—los tres en `fleet.txt`, `provider_syms.txt` y `universe_gamma.txt`— sin mapa de opciones, mientras
Polygon **sí los servía** (`/v3/snapshot/options/<sym>` → 250 resultados). No era del vendor: era
nuestro. Ahora: 2 intentos con 2 s de espera y, si falla de verdad, `SIN MAPA DE OPCIONES` en el log
— nunca un hueco callado. Verificado en vivo: 329/315/184 filas y `opt_quick` leyéndolas con el spot
correcto del cierre del viernes.

**El mismo patrón, en el terminal**: `orchestrator._multi_expiry_chain` usaba
`return_exceptions=True` y descartaba en silencio los vencimientos caídos → los muros se calculaban
sobre la cadena superviviente. Con SPY al MISMO spot 744.27: `call_wall` 775 → 700 y `flip` 729.98 →
647.68 entre dos refrescos. Ahora reintenta, **LEVANTA si la cobertura baja de la mitad** (que
`_with_fallback` lo declare `connected=False`) y grita si sirve con huecos.

**Regla que se deriva:** en esta capa un `except` que sigue adelante sin reintentar produce un
DENOMINADOR FABRICADO — el mapa parcial tiene exactamente la misma pinta que el completo. O se
reintenta, o se levanta, o se declara el hueco. Nunca las tres cosas en silencio.
