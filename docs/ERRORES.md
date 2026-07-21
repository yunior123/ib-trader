# ERRORES.md — libro de errores (append-only; NO repetir ninguno)

Regla de uso (obligatoria para el copiloto): (1) cada error nuevo se APUNTA aquí el mismo
día con causa + fix + regla; (2) ANTES de operaciones propensas (postear a X, enviar email,
tocar launchd, scrapear Yahoo, imprimir, dropdowns de gexa) — grep rápido de esta lista;
(3) si un error se repite = fallo del sistema, no del azar: arreglar el CÓDIGO, no la memoria.

| Fecha | Error | Causa raíz | Fix aplicado | Regla anti-repetición |
|---|---|---|---|---|
| 2026-07-21 | "Ballenas mudas" reportado 13:5x — falsa alarma | diseño anti-spam: solo suena al CAMBIAR estado; QQQ 0.86 / SPY 0.79 P/C = mid (umbral 2.0/0.35), sin cruce = sin sirena; MU sí sonó 12:45 y 13:54 | ninguno (silencio correcto; audio verificado end-to-end con "prueba ballenas") | Antes de declarar watcher muerto: ver ~/Desktop/trading-signals/HOY.txt + opt_flow.txt mtime; tide $ ≠ ratio P/C por volumen |
| 2026-07-21 ×2 | X rechaza post (403/401 confuso) con 2+ cashtags | X limita a UN $SYMBOL por post | sanitizador en x_post_common (solo 1er $ se conserva) | Máx 1 cashtag; los demás tickers SIN $ |
| 2026-07-21 | x_plan_poster/xpost con imagen fallan silencioso | upload v1.1 media falla (tier API) y el flujo moría | posts van texto-solo con fallback limpio | Media es opcional SIEMPRE; jamás bloquear el post por la imagen |
| 2026-07-21 | 16/26 tickers FALLO "unexpected character" | ráfaga yfinance → Yahoo rate-limit devuelve HTML | reintentos espaciados 10s uno-a-uno | Nunca 26 tickers en ráfaga; IBKR cache primero; espaciar 4-10s |
| 2026-07-21 | sed a x_plan_poster sin verificar si aplicó | edición ciega sin grep de confirmación | — | Tras editar con sed/replace: SIEMPRE grep para confirmar el cambio |
| 2026-07-21 | Veredicto DRAM sin mirar gráfico (fuerza muerta) | opinión con datos viejos | regla gráfico-primero + momentum_calc | NUNCA veredicto sin NBBO+gráfico+calculadora (CLAUDE.md regla 9) |
| 2026-07-21 | Put SPY sugerido con KOSPI +fuerte | ignoré filtro macro overnight | regla KOSPI grabada | Macro overnight PRIMERO, flujo/gexa después |
| 2026-07-20 | Compra a través de muro intermedio (META 660C) | operar contra el mapa de imanes | protocolo imanes OI | Hacia el imán sí, a través del muro no |
| 2026-07-20/21 | launchd com.ibtrader.* exit 78 recurrente | EX_CONFIG no diagnosticado | healthcheck relanza (workaround) | Pendiente: cazar root cause post-cierre; no crear plists nuevos copiando esos |
| 2026-07-21 | opt_whale_watch duplicado (2 procesos, días distintos) | keepalive sin dedup | whale_watch_keepalive.sh idempotente | Todo daemon nuevo lleva keepalive con dedup por diseño |
| 2026-07-21 | Spam Error 200 QQQ strike 712.5 inexistente | pedir contratos sin security definition | pendiente (TODOS.md) | Cachear contratos inválidos y saltarlos |
| 2026-07-20 | Impresora: jobs a cola ajena (Brother) | asumí impresora sin confirmar dueño | cola eliminada | Jamás imprimir a una cola no confirmada del usuario |
| 2026-07-21 | gexa dropdown: primer resultado ≠ ticker (TOWN por TSM) | fuzzy match del buscador | verificar header post-carga | SIEMPRE screenshot del dropdown y verificar header |
| 2026-07-21 | x_post_common post_text da 401 pero OAuth1 directo da 201 | auth interna del modulo mal construida (pendiente diagnosticar) | workaround: OAuth1 directo + ledger manual | arreglar auth() del modulo post-cierre |
| 2026-07-21 | Ballenas de PREMIUM (-53M tide) sin sirena | watcher solo mide ratio de VOLUMEN (P/C 2.0), no dolares pagados | copiloto cubrio a mano via gexa | v2 con alarma de premium neto (TODOS.md) — dos metricas, dos sirenas |
| 2026-07-21 | Media upload X fallaba silencioso todo el dia | flujo interno x_post_common; el endpoint correcto es upload.twitter.com/1.1 multipart directo | RESUELTO 15:32: media_id 200 + tweet con imagen 201 | usar multipart directo a upload.twitter.com; portar a x_post_common post-cierre |
