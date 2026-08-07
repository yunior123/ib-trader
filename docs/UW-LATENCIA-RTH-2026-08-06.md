# UW — latencia medida en sesion (2026-08-06)

Generado por `scripts/uw_latency_probe.py --rth-measure`. TODOS 8a (latencia) + 8b (websocket).

- Corrida: 2026-08-06T13:35:03.623719+00:00 UTC · en_rth=True · peticiones UW=0 (tope 10) · cupo None/None

- sin IBKR esta semana: el proxy del disparador es el print de finnhub (data/rt_last_<SYM>.txt); TODOS 8f sigue pendiente


## 8a — edad del feed y desfase contra el disparador

| medida | min | mediana | max |
|---|---|---|---|

**Veredicto** (umbral de la casa: <60 s = candidato a tiempo real):
- `stock-state`: **None**
- `net-prem-ticks`: **None**

Prediccion registrada de antemano en TODOS 8a: **30-90 s**.


## 8b — websocket en RTH

| caso | status | handshake s | cierre s | bytes | close-frame |
|---|---|---|---|---|---|
| sin enviar nada | HTTP/1.1 429 Too Many Requests | 0.1012 | 8.1025 | 809 | False |
| join lista | HTTP/1.1 429 Too Many Requests | 0.1021 | 8.1039 | 809 | False |
| join objeto | HTTP/1.1 429 Too Many Requests | 0.0898 | 8.091 | 809 | False |

`GET /api/socket` canales declarados: `None`

**El socket entrega datos en RTH: SI — el veredicto de madrugada QUEDA REVOCADO**

## 8c — colinealidades (killlist test 1: |rho|>0,9 = muere ya)

**(1) `dir_vega_flow` vs `signed_premium`** — rho_pooled=**0.0706** (n=1013120 minutos, 92 dias, 30 syms); per-sym min/mediana/max = -0.2416 / 0.1929 / 0.5442
- control `dir_delta_flow` vs `net_delta` (precedente rho=1,0): rho=**1.0000**, byte-identicos 1013079/1013120

**(2) `senal_capitan` vs `fleet_consensus` (manada sobre BARRAS)** — 9 dias:

| capitan | rho | n | acuerdo de signo |
|---|---|---|---|
| SPY | 0.4198 | 678 | 68.1% |
| QQQ | 0.5065 | 678 | 72.2% |
| SMH | 0.1229 | 678 | 56.6% |

**(3) `max_pain` (UW/OI) vs `abs_wall` (gex)** — rho=**-0.0196** (n=185 sym-dias, 7 dias); strike identico en **8.6%**; mediana |max_pain−abs_wall|/spot = **5.14%**

Avisos que NO se pueden omitir al leer estos numeros: la muestra de (2) son buckets SOLAPADOS de pocas sesiones (n_eff mucho menor que n) y el signo de (1) cambia entre dias. Sobrevivir la colinealidad NO es tener edge: publicar probabilidad sigue bloqueado en TODOS 8e.
