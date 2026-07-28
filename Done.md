
- [x] **hecho (agente UW)** — `docs/research/designs-{tradytics,optioncharts,quanted}.md` + pasada HTTP a tradingflow. Ninguno con API usable (fuente de IDEAS). Features aceptadas con test de colinealidad por delante; rechazadas citando anti-overfit-killlist. Hallazgo: CBOE Open-Close Volume Summary = version MEDIDA de nuestro DeltaOI.
      *(era)* **[pendiente] Minar 4 vendedores más** como se hizo con TrendSpider/MenthorQ/SpotGamma
- [x] **hecho/verificado** — los 3 escritores usan `IBT_DESKTOP_HOY` (default `~/Desktop/ib-trader/hoy`): `print_mon_plans.sh:8`, `daily_archive.py`, `price_alarm.cpp:82-85`. MEDIDO: no hay `price-alerts.txt` en la raiz del Desktop, si en `hoy/`. Residuo benigno: `daily_archive.py:40` LEE el formato viejo como fallback.
      *(era)* **[pendiente] Los folder de planes van DENTRO de `~/Desktop/ib-trader/`, no en la raíz del
