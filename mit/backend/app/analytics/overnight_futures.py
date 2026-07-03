"""Mapa de HUECO de la noche: lee lo que escribe scripts/futures_feed.py y lo deja listo
para el widget. No pide nada a la red: el puente ya lo hizo (patron de la casa — el puente
mueve bytes, el terminal pinta).

Por que es el widget esencial de futuros: entre el cierre del viernes y las 09:30 del lunes
las acciones US no imprimen NADA (medido 2026-08-02 21:18 ET: ultimo print de SPY/QQQ/NVDA
del viernes 19:59, y el WebSocket de Finnhub con 26 suscripciones llevaba 0 trades). Lo unico
que cotiza es CME. El hueco que dejan los futuros ES la unica informacion de apertura que
existe, y la casa se dedica a anticipar movimientos antes del pico.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

FUTURES_DIR_ENV = "MIT_FUTURES_DIR"
STALE_S = float(os.environ.get("MIT_FUTURES_STALE_S", "900"))   # 15 min: el feed corre cada 60 s


def futures_dir() -> Path:
    override = os.environ.get(FUTURES_DIR_ENV)
    return Path(override) if override else Path(__file__).resolve().parents[4] / "data"


def read_overnight(*, base_dir: str | Path | None = None, now: float | None = None) -> dict:
    """Mapa de hueco listo para pintar. `disponible=False` + `motivo` si no hay dato utilizable:
    nunca ceros ni un mapa vacio con pinta de bueno."""
    root = Path(base_dir) if base_dir is not None else futures_dir()
    path = root / "futures_overnight.json"
    if not path.is_file():
        return {"disponible": False, "motivo": "futures_overnight.json no existe "
                                               "(¿corre scripts/futures_feed.py?)"}
    try:
        d = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        return {"disponible": False, "motivo": f"futures_overnight.json ilegible: {type(e).__name__}"}

    ahora = time.time() if now is None else now
    edad = ahora - float(d.get("ts") or 0)
    filas = [f for f in (d.get("futuros") or []) if f.get("pct") is not None]
    if not filas:
        return {"disponible": False, "motivo": "ningun futuro con dato",
                "avisos": d.get("avisos") or []}
    if edad > STALE_S:
        return {"disponible": False,
                "motivo": f"mapa rancio ({edad/60:.0f} min > {STALE_S/60:.0f})",
                "edad_s": round(edad, 1), "avisos": d.get("avisos") or []}

    capitanes = [f for f in filas if f.get("cash_proxy")]
    return {
        "disponible": True,
        "edad_s": round(edad, 1),
        "generado_et": d.get("et"),
        "futuros": filas,
        "corea": d.get("corea") or {},
        "avisos": d.get("avisos") or [],
        "nota": d.get("nota"),
        "divergencia": _divergencia(capitanes, d.get("corea") or {}),
    }


def _divergencia(capitanes: list[dict], corea: dict) -> dict | None:
    """Futuros US contra el liderazgo coreano. Corea abre ~13 h antes: cuando los dos apuntan
    a lados distintos, la apertura US suele ser la que cede (doctrina de la casa, NO medida —
    va etiquetada como doctrina hasta que haya n>=30 en el ledger).
    """
    us = [f["pct"] for f in capitanes if f.get("pct") is not None]
    kr = [v["pct"] for v in corea.values() if isinstance(v, dict) and v.get("pct") is not None]
    if not us or not kr:
        return None
    mus, mkr = sum(us) / len(us), sum(kr) / len(kr)
    if mus * mkr >= 0:
        return {"hay": False, "us_pct": round(mus, 3), "korea_pct": round(mkr, 3)}
    return {
        "hay": True, "us_pct": round(mus, 3), "korea_pct": round(mkr, 3),
        "brecha_pp": round(abs(mus - mkr), 2),
        "lectura": ("futuros US arriba con Corea abajo" if mus > 0 else
                    "futuros US abajo con Corea arriba"),
        "base": "doctrina",   # no medida: sin n>=30 no se llama probabilidad
    }
