#!/usr/bin/env python3
"""Correlación temporal, simétrica y honesta entre flujo y reentradas Bollinger.

No genera señales ni cambia umbrales. Conserva hechos ya emitidos para que:
  * flujo PUTS + BB al alza, o CALLS + BB a la baja, se enriquezcan si ambos existen;
  * una BB posterior produzca una única actualización ligada al flujo;
  * nunca se presente como existente una BB futura ni se afirme causalidad.
"""
import json
import os
import tempfile
import fcntl

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO, "data")
WINDOW_S = int(os.environ.get("FLOW_BB_WINDOW_S", "180"))


def compatible(flow_side, bb_direction):
    return ((flow_side.upper() == "PUTS" and bb_direction.upper() == "UP") or
            (flow_side.upper() == "CALLS" and bb_direction.upper() == "DOWN"))


class Correlator:
    def __init__(self, data_dir=DATA_DIR, window_s=WINDOW_S):
        self.data_dir = data_dir
        self.window_s = window_s
        self.flow_path = os.path.join(data_dir, "flow_bb_events.jsonl")
        self.bb_path = os.path.join(data_dir, "flow_bb_latest.json")
        self.dedup_path = os.path.join(data_dir, "flow_bb_dedup.json")
        os.makedirs(data_dir, exist_ok=True)

    @staticmethod
    def _load(path, default):
        try:
            with open(path) as f:
                value = json.load(f)
            return value
        except (OSError, ValueError):
            return default

    @staticmethod
    def _atomic_json(path, value):
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(value, f, separators=(",", ":"), sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass

    def _append_flow(self, event):
        line = (json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n").encode()
        fd = os.open(self.flow_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)

    def _flows(self):
        out = []
        try:
            # Hot path de una BB: nunca recorrer historia ilimitada. 512 KiB cubre holgadamente
            # la ventana de 180s incluso en una avalancha; si se entra a mitad de línea, se tira.
            with open(self.flow_path, "rb") as f:
                size = os.fstat(f.fileno()).st_size
                start = max(0, size - 512 * 1024)
                f.seek(start)
                if start:
                    f.readline()
                for raw in f:
                    try:
                        out.append(json.loads(raw.decode("utf-8")))
                    except (UnicodeDecodeError, ValueError):
                        continue
        except OSError:
            pass
        return out[-2000:]

    def _mark_once(self, flow_id, bb_id):
        lock_path = self.dedup_path + ".lock"
        with open(lock_path, "a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            state = self._load(self.dedup_path, {})
            if flow_id in state:
                return False
            state[flow_id] = bb_id
            # El fichero sólo cubre la ventana viva; limitar crecimiento sin depender del reloj real.
            if len(state) > 2000:
                state = dict(list(state.items())[-1000:])
            self._atomic_json(self.dedup_path, state)
            return True

    def record_flow(self, *, ts, sym, side, source, volume_scope,
                    aggregate_volume=None, dominant_strike=None, premium=None,
                    event_id=None):
        """Registra flujo real y devuelve la BB previa fresca compatible, si existe."""
        side, sym = side.upper(), sym.upper()
        event = {
            "id": event_id or f"{source}:{sym}:{side}:{int(ts)}",
            "ts": float(ts), "sym": sym, "side": side, "source": source,
            "volume_scope": volume_scope,
            "aggregate_volume": aggregate_volume,
            "dominant_strike": dominant_strike,
            "premium": premium,
        }
        self._append_flow(event)
        bb = self._load(self.bb_path, {}).get(sym)
        if not bb:
            return None
        age = float(ts) - float(bb.get("ts", 0))
        if age < 0 or age > self.window_s or not compatible(side, bb.get("direction", "")):
            return None
        if not self._mark_once(event["id"], bb["id"]):
            return None
        return {"flow": event, "bb": bb, "age_s": round(age)}

    def record_bb(self, *, ts, sym, direction, timeframe, price=None, target=None,
                  source="bollinger_alarm", event_id=None):
        """Registra BB y devuelve un único flujo anterior fresco compatible."""
        sym, direction = sym.upper(), direction.upper()
        bb = {
            "id": event_id or f"{source}:{sym}:{direction}:{timeframe}:{int(ts)}",
            "ts": float(ts), "sym": sym, "direction": direction,
            "timeframe": timeframe, "price": price, "target": target, "source": source,
        }
        latest = self._load(self.bb_path, {})
        latest[sym] = bb
        self._atomic_json(self.bb_path, latest)
        candidates = [
            f for f in self._flows()
            if f.get("sym") == sym and compatible(f.get("side", ""), direction)
            and 0 <= float(ts) - float(f.get("ts", 0)) <= self.window_s
        ]
        if not candidates:
            return None
        flow = max(candidates, key=lambda f: float(f["ts"]))
        if not self._mark_once(flow["id"], bb["id"]):
            return None
        return {"flow": flow, "bb": bb, "age_s": round(float(ts) - float(flow["ts"]))}


def flow_detail(flow):
    """Texto que separa volumen agregado, strike dominante y premium."""
    scope = flow.get("volume_scope")
    if scope == "aggregate_delta":
        n = flow.get("aggregate_volume")
        return f"volumen agregado incremental ({n:,.0f} contratos)" if n is not None else "volumen agregado incremental"
    if scope == "aggregate_class":
        return "volumen agregado de la clase (sin strike medido)"
    if scope == "aggregate_strikes":
        text = "volumen agregado de los strikes escaneados"
        if flow.get("dominant_strike") is not None:
            text += f"; strike dominante ${flow['dominant_strike']:g}"
        return text
    if scope == "signed_premium":
        p = flow.get("premium")
        return f"premium neto firmado (${p:,.0f})" if p is not None else "premium neto firmado"
    return "flujo agregado"


def bb_phrase(direction):
    return "rebote BB al alza" if direction == "UP" else "retroceso BB a la baja"


def prior_bb_suffix(match):
    bb, age = match["bb"], match["age_s"]
    return (f" BB fresca ya existente ({bb['timeframe']}, hace {age}s): "
            f"{bb_phrase(bb['direction'])}. Compatibilidad técnica; no prueba causalidad.")


def linked_update(match):
    flow, bb, age = match["flow"], match["bb"], match["age_s"]
    side = flow["side"].lower()
    detail = flow_detail(flow)
    short = (f"Actualización {flow['sym']}: {age}s después del alto volumen de {side}, "
             f"aparece {bb_phrase(bb['direction'])}. Señales compatibles; no prueba causalidad.")
    levels = ""
    if bb.get("price") is not None:
        levels = f", reentrada {bb['price']:.2f}"
        if bb.get("target") is not None:
            levels += f", media {bb['target']:.2f}"
    full = (f"{short} Flujo: {detail}; fuente {flow['source']}. "
            f"Bollinger: {bb['timeframe']}{levels}, fuente {bb['source']}.")
    return {"title": f"🔗 FLUJO + BB {flow['sym']}", "short": short, "full": full}


DEFAULT = Correlator()
