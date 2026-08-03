# Correo a Intrinio — plan Startup ($333/mo) sirviendo datos con 15 min de retraso

Listo para enviar a **success@intrinio.com**. Todo lo de abajo esta medido, con marca de tiempo,
y es reproducible con dos comandos.

---

**Asunto:** Startup plan (EquitiesEdge FMV Real-Time) delivering 15-minute delayed data — REST and WebSocket

Hi,

We are on the **Startup plan ($333/mo)**, which your pricing page lists as including
*"EquitiesEdge (FMV Real-Time)"* via **API and WebSocket**. Both the REST API and the realtime
WebSocket are serving our key **exactly 15 minutes delayed**. Measurements below, all taken on
**2026-08-03 during the US pre-market session** (06:00–06:20 ET).

**1) WebSocket, provider `EQUITIES_EDGE`** — official Python SDK `intriniorealtime` 6.3.0,
unmodified, 8 symbols (SPY QQQ NVDA AAPL MU TSLA AMD MSFT), 90 seconds, **218 trades received**:

| | value |
|---|---|
| median latency (now − trade exchange timestamp) | **900.0 s** |
| **minimum** latency | **900.0 s** |
| maximum latency | 900.1 s |
| quotes (bid/ask) received | **0** |

The minimum being 900.0 s is the point: this is not network jitter, it is a fixed 15-minute
offset applied to the feed.

**2) REST `/securities/AAPL/prices/realtime`** — every `source` we are entitled to returns the
same 15-minute-old print, and the response body reports the feed actually served:

| requested `source` | `source` in response | age of `last_time` |
|---|---|---|
| `equities_edge` | `equities_edge` | 900.9 / 902.2 / 904.1 s (three samples, 12 s apart) |
| `cboe_one` | `cboe_one_delayed` | 901.2 / 902.4 / 904.5 s |
| `iex` | `cboe_one_delayed` | 902 s, plus `"Realtime sources have been adjusted to cboe_one_delayed based on your access."` |
| `nasdaq_basic` | `cboe_one_delayed` | 902 s |
| `delayed_sip` | `delayed_sip,...` | 904 s |

Note that `source=equities_edge` is **not** downgraded — the response says `equities_edge` — but
it still arrives 15 minutes late.

**3) A second, unrelated vendor on the same machine, same minute**, for reference: median 34.1 s,
**minimum 0.6 s**. So this is not our network, our clock, or our code.

**4) `source=equities_edge` returns an unusable book.** On SPY, QQQ, NVDA, MU, GLD and NOK it
returns `bid_price: null, ask_price: null`; on AAPL it returned `bid 232.84 / ask 1.00`. The same
symbols on `cboe_one` return sane books (spreads 0.007 %–0.111 %). If EquitiesEdge is not meant
to carry NBBO, that is fine — but please confirm, because the null/garbage book is what we would
otherwise treat as a data error on our side.

**Questions**

1. Is the **realtime** entitlement actually attached to our API key, or only the delayed tier?
   The key works, authenticates on the WebSocket and streams — it simply streams 15 minutes late.
2. If it is attached, what must change on our side to receive the real-time stream? We are using
   `provider: "EQUITIES_EDGE"` with the official Python SDK and no `delayed` flag set.
3. Should `EQUITIES_EDGE` deliver quote (bid/ask) messages at all? We received 0 in 90 seconds
   while receiving 218 trades.

Account/key: the production key ending in `…c90a`. Happy to provide raw logs or a capture.

Thanks,

---

## Como reproducirlo en 30 s

```bash
# 1) REST: que feed sirve de verdad y con cuanta antiguedad
curl -s "https://api-v2.intrinio.com/securities/AAPL/prices/realtime?source=equities_edge&api_key=$INTRINIO_API_KEY" \
 | python3 -c "import json,sys,datetime as dt,time; d=json.load(sys.stdin); \
 print(d['source'], time.time()-dt.datetime.fromisoformat(d['last_time'].replace('Z','+00:00')).timestamp())"

# 2) WebSocket: latencia de los trades
python3 /private/tmp/.../prov_probe.py     # o el bloque del skill intrinio-api
```

## Mientras tanto, que hace la casa

- **PRINT en tiempo real** = `data/rt_last_<SYM>.txt` con fuente `finnhub` (0,6 s de minimo
  medido). Es lo unico realtime que hay esta semana.
- **Intrinio** = barras, contexto y **libro via `cboe_one`** (arreglado el 2026-08-03: con
  `equities_edge` el NBBO llevaba 56,7 h congelado). Etiquetado 15 min en todas partes.
- El epoch que se escribe en `data/nbbo_*.txt` es el de **bolsa**, asi que el gate de frescura
  de los bots (`now-ep <= 10 s`) sigue rechazandolo para disparar. Sirve de mapa, no de gatillo.
