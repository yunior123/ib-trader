#!/usr/bin/env python3
"""premarket_unconsolidated.py — PUENTE TONTO: archiva el premarket NO CONSOLIDADO
(feed directo de la bolsa PRIMARIA del simbolo, via Databento historico) de una fecha.

CERO COMPUTO DE SEÑAL. Mueve bytes de Databento a disco y clasifica la cinta con
Lee-Ready usando el quote del PROPIO tbbo. Quien mide la probabilidad es
scripts/premarket_calibrate.py (lote fuera de sesion).

Databento LIVE no esta licenciado en esta cuenta (medido: "a live data license is
required"). Solo historico, y el historico va a T-1: la sesion de HOY no existe.

Salida por simbolo:  data/history/<fecha>/premkt_unconsolidated_<sym>.json
Uso:
  ./venv-mit/bin/python scripts/premarket_unconsolidated.py --date 2026-08-05
  ./venv-mit/bin/python scripts/premarket_unconsolidated.py --date 2026-08-05 --syms SPY QQQ
  ./venv-mit/bin/python scripts/premarket_unconsolidated.py --date 2026-08-05 --max-cost 0.10
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(REPO, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import em_envelope  # noqa: E402  (tabla de festivos: LEVANTA fuera de tabla, no asume)

ROUTE_PATH = os.path.join(REPO, "data", "premarket_route.json")
HISTDIR = os.path.join(REPO, "data", "history")

# Feeds directos de bolsa PRIMARIA. El desequilibrio de subasta solo lo publica la
# bolsa donde el simbolo COTIZA -> es la medicion que decide el enrutado.
PRIMARY_CANDIDATES = [
    ("XNAS.ITCH", "Nasdaq"),
    ("ARCX.PILLAR", "NYSE Arca"),
    ("XNYS.PILLAR", "NYSE"),
    ("XASE.PILLAR", "NYSE American"),
    ("BATS.PITCH", "Cboe BZX"),
    ("IEXG.TOPS", "IEX"),
    ("EPRL.DOM", "MIAX Pearl"),
    ("MEMX.MEMOIR", "MEMX"),
    ("XCHI.PILLAR", "NYSE Texas"),
]

PREMKT_OPEN_MIN = 4 * 60        # 04:00 ET
RTH_OPEN_MIN = 9 * 60 + 30      # 09:30 ET
TRAMO_MIN = 5
MAX_COST_DEFAULT = float(os.environ.get("PREMKT_MAX_COST_USD", "0.50"))


class PremarketError(RuntimeError):
    pass


# ------------------------------------------------------------------ utilidades

def atomic_write(path, text):
    """tmp + os.replace: nadie lee un fichero a medio escribir."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def feeds_env():
    out = {}
    path = os.path.join(REPO, "config", "feeds.env")
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError as exc:
        raise PremarketError("no se pudo leer config/feeds.env: %s" % exc)
    return out


def api_key():
    k = os.environ.get("DATABENTO_API_KEY") or feeds_env().get("DATABENTO_API_KEY")
    if not k:
        raise PremarketError("sin DATABENTO_API_KEY (entorno ni config/feeds.env)")
    return k


def _px(v):
    """DBN fixed-point x1e9. to_df() suele escalar; si llega crudo, se divide."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f / 1e9 if abs(f) > 1e7 else f


def _int(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return int(f)


def prev_market_day(d):
    p = d - dt.timedelta(days=1)
    while not em_envelope.is_market_day(p):
        p = p - dt.timedelta(days=1)
    return p


def _et_zone():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except Exception as exc:                      # noqa: BLE001
        raise PremarketError("sin tzdata para America/New_York: %s" % exc)


def et_window_utc(d, start_min, end_min):
    """[start,end) de minutos ET del dia d -> instantes UTC ISO (Z)."""
    tz = _et_zone()
    base = dt.datetime(d.year, d.month, d.day, tzinfo=tz)
    a = (base + dt.timedelta(minutes=start_min)).astimezone(dt.timezone.utc)
    b = (base + dt.timedelta(minutes=end_min)).astimezone(dt.timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%S.%f"
    return a.strftime(fmt)[:-3] + "Z", b.strftime(fmt)[:-3] + "Z"


def et_minute_of_day(epoch_s):
    tz = _et_zone()
    t = dt.datetime.fromtimestamp(epoch_s, tz)
    return t.hour * 60 + t.minute


def hhmm(minute_of_day):
    return "%02d:%02d" % (minute_of_day // 60, minute_of_day % 60)


# ------------------------------------------------------- Lee-Ready (puro, testable)

def _valid_quote(bid, ask):
    if bid is None or ask is None:
        return False
    if not (math.isfinite(bid) and math.isfinite(ask)):
        return False
    return bid > 0 and ask > 0 and ask >= bid


def classify_lee_ready(rows):
    """rows: [{price,bid,ask}, ...] en orden temporal. -> [+1 | -1 | None].

    None = NO clasificado (sin quote valida, o tick test sin referencia previa).
    Jamas se reparte 50/50 ni se cuenta como 0.
    """
    signs = []
    last_px = None       # precio del trade inmediatamente anterior
    last_diff_px = None  # ultimo precio DISTINTO del anterior (zero-tick de Lee-Ready)
    for r in rows:
        px = r.get("price")
        bid, ask = r.get("bid"), r.get("ask")
        s = None
        if px is not None and math.isfinite(px) and _valid_quote(bid, ask):
            mid = (bid + ask) / 2.0
            if px > mid:
                s = 1
            elif px < mid:
                s = -1
            else:
                ref = last_px if (last_px is not None and last_px != px) else last_diff_px
                if ref is not None:
                    s = 1 if px > ref else (-1 if px < ref else None)
        signs.append(s)
        if px is not None and math.isfinite(px):
            if last_px is not None and px != last_px:
                last_diff_px = last_px
            last_px = px
    return signs


def build_tape(rows):
    """rows: [{ts,price,size,bid,ask}] -> (tramos de 5 min ET, total). Puro."""
    signs = classify_lee_ready(rows)
    acc = {}
    last_px = None
    last_ts = None
    for r, s in zip(rows, signs):
        mod = et_minute_of_day(r["ts"])
        if mod < PREMKT_OPEN_MIN or mod >= RTH_OPEN_MIN:
            continue
        last_px, last_ts = r["price"], r["ts"]
        key = (mod // TRAMO_MIN) * TRAMO_MIN
        b = acc.setdefault(key, {"t": hhmm(key), "n_trades": 0, "vol": 0, "_pv": 0.0,
                                 "buy_vol": 0, "sell_vol": 0,
                                 "n_sin_clasificar": 0, "vol_sin_clasificar": 0})
        sz = int(r.get("size") or 0)
        b["n_trades"] += 1
        b["vol"] += sz
        b["_pv"] += float(r["price"]) * sz
        if s == 1:
            b["buy_vol"] += sz
        elif s == -1:
            b["sell_vol"] += sz
        else:
            b["n_sin_clasificar"] += 1
            b["vol_sin_clasificar"] += sz

    tramos = []
    for key in sorted(acc):
        b = acc[key]
        pv = b.pop("_pv")
        b["vwap"] = round(pv / b["vol"], 6) if b["vol"] > 0 else None
        b["signed_vol"] = b["buy_vol"] - b["sell_vol"]
        tramos.append(b)

    total = {"n_trades": 0, "vol": 0, "buy_vol": 0, "sell_vol": 0,
             "n_sin_clasificar": 0, "vol_sin_clasificar": 0}
    pv = 0.0
    for b in tramos:
        for k in total:
            total[k] += b[k]
        if b["vwap"] is not None:
            pv += b["vwap"] * b["vol"]
    total["vwap"] = round(pv / total["vol"], 6) if total["vol"] > 0 else None
    total["signed_vol"] = total["buy_vol"] - total["sell_vol"]
    total["last_px"] = last_px            # ultimo print del premarket (feature GAP)
    total["last_ts"] = int(last_ts) if last_ts is not None else None
    return tramos, total


def imbalance_ratio(paired_qty, total_imbalance_qty):
    """None si el denominador es 0. JAMAS 0.0 (un 0 plausible es una mentira)."""
    if paired_qty is None or total_imbalance_qty is None:
        return None
    den = paired_qty + total_imbalance_qty
    if den == 0:
        return None
    return total_imbalance_qty / float(den)


def reduce_imbalance(rows):
    """rows: [{ts,ref_price,paired_qty,total_imbalance_qty,side}] -> 1 punto por minuto ET
    (el ULTIMO de cada minuto). Puro."""
    per_min = {}
    for r in rows:
        mod = et_minute_of_day(r["ts"])
        per_min[mod] = r          # el ultimo de cada minuto gana
    out = []
    for mod in sorted(per_min):
        r = per_min[mod]
        out.append({
            "ts": int(r["ts"]),
            "hhmm": hhmm(mod),
            "ref_price": r.get("ref_price"),
            "paired_qty": r.get("paired_qty"),
            "total_imbalance_qty": r.get("total_imbalance_qty"),
            "side": r.get("side"),
            "imbalance_ratio": imbalance_ratio(r.get("paired_qty"),
                                               r.get("total_imbalance_qty")),
        })
    return out


# ------------------------------------------------------------------- Databento

def _hist(key):
    try:
        import databento as db          # import PEREZOSO: el modulo se testea sin el paquete
    except ImportError as exc:
        raise PremarketError(
            "el paquete 'databento' no esta en este interprete (%s): usa ./venv-mit/bin/python — %s"
            % (sys.executable, exc))
    return db.Historical(key)


class CostGate:
    """metadata.get_cost ANTES de cada descarga. Un rango mal puesto factura años."""

    def __init__(self, hist, max_cost):
        self.hist = hist
        self.max_cost = float(max_cost)
        self.spent = 0.0
        self.detail = []

    def check(self, etiqueta, **kw):
        try:
            c = float(self.hist.metadata.get_cost(**kw))
        except Exception as exc:                  # noqa: BLE001  fail-loud, sin coste inventado
            raise PremarketError("get_cost(%s) fallo: %s: %s" % (etiqueta, type(exc).__name__, exc))
        if self.spent + c > self.max_cost:
            raise PremarketError(
                "ABORTADO ANTES DE DESCARGAR: %s costaria $%.5f y el acumulado ($%.5f) "
                "superaria --max-cost $%.5f" % (etiqueta, c, self.spent, self.max_cost))
        self.spent += c
        self.detail.append((etiqueta, round(c, 6)))
        return c


def _get_range(hist, etiqueta, **kw):
    try:
        return hist.timeseries.get_range(**kw)
    except Exception as exc:                      # noqa: BLE001  fail-loud con el mensaje real
        raise PremarketError("get_range(%s) fallo: %s: %s" % (etiqueta, type(exc).__name__, exc))


def _rows(store):
    """DBN store -> lista de dicts planos (sin pandas fuera de aqui)."""
    df = store.to_df()
    if df is None or len(df) == 0:
        return []
    df = df.reset_index()
    return df.to_dict("records")


def _ts_epoch(rec):
    v = rec.get("ts_event")
    if v is None:
        v = rec.get("ts_recv")
    if v is None:
        raise PremarketError("registro sin ts_event ni ts_recv")
    if hasattr(v, "timestamp"):                   # pandas.Timestamp (to_df ya decodifico)
        return v.timestamp()
    f = float(v)
    return f / 1e9 if f > 1e12 else f             # ts_event en NANOsegundos


# --------------------------------------------------------------------- enrutado

def load_route():
    try:
        with open(ROUTE_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_route(route):
    atomic_write(ROUTE_PATH, json.dumps(route, indent=1, sort_keys=True) + "\n")


def measure_primary(hist, sym, d):
    """La bolsa PRIMARIA se MIDE: solo ella publica el desequilibrio de la subasta.
    Ventana estrecha 09:28-09:30 (todas las primarias publican ahi; 6 h tardan 4 min/llamada).
    Devuelve (dataset, bolsa, evidencia) o (None, None, evidencia) = dataset_desconocido."""
    start, end = et_window_utc(d, RTH_OPEN_MIN - 2, RTH_OPEN_MIN)
    evid = {}
    best = None
    for ds, bolsa in PRIMARY_CANDIDATES:
        try:
            n = int(hist.metadata.get_record_count(dataset=ds, symbols=[sym],
                                                   schema="imbalance", start=start, end=end))
        except Exception as exc:                  # noqa: BLE001  simbolo ausente del feed
            evid[ds] = "ERR:%s" % type(exc).__name__
            continue
        evid[ds] = n
        if ds == "XNAS.ITCH":
            continue                  # se decide al final: ver nota de abajo
        if n > 0 and (best is None or n > best[2]):
            best = (ds, bolsa, n)
    # MEDIDO 2026-08-05: XNAS.ITCH publica NOII (138 msgs en 09:28-09:30) tambien para
    # simbolos que NO lista (SPY, TSM); las demas primarias publican 0 salvo en SUS
    # listados. Por eso Nasdaq solo gana si ninguna otra primaria tiene mensajes.
    if best is None and isinstance(evid.get("XNAS.ITCH"), int) and evid["XNAS.ITCH"] > 0:
        best = ("XNAS.ITCH", "Nasdaq", evid["XNAS.ITCH"])
    if best is None:
        return None, None, evid
    return best[0], best[1], evid


def resolve_dataset(hist, sym, d, route, remeasure=False):
    ent = route.get(sym)
    if ent and not remeasure:
        return ent
    ds, bolsa, evid = measure_primary(hist, sym, d)
    ent = {"dataset": ds, "bolsa_primaria": bolsa,
           "metodo": "record_count(imbalance) por feed directo; la subasta solo la publica "
                     "la bolsa donde el simbolo cotiza",
           "medido_en": d.isoformat(), "evidencia": evid}
    if ds is None:
        ent["dataset"] = "dataset_desconocido"
        ent["bolsa_primaria"] = "dataset_desconocido"
    route[sym] = ent
    return ent


# -------------------------------------------------------------------- descarga

def jobs_for(sym, d, dataset):
    """Las 4 peticiones de un sym-dia. Misma lista para el gate de coste y la descarga."""
    t_start, t_end = et_window_utc(d, PREMKT_OPEN_MIN, RTH_OPEN_MIN)
    i_start, i_end = et_window_utc(d, PREMKT_OPEN_MIN, RTH_OPEN_MIN + 5)
    o_start, o_end = et_window_utc(d, RTH_OPEN_MIN, RTH_OPEN_MIN + 35)
    prev = prev_market_day(d)
    p_start, p_end = et_window_utc(prev, 15 * 60 + 30, 16 * 60)

    jobs = [
        ("tbbo", dict(dataset=dataset, schema="tbbo", symbols=[sym],
                      stype_in="raw_symbol", start=t_start, end=t_end)),
        ("imbalance", dict(dataset=dataset, schema="imbalance", symbols=[sym],
                           stype_in="raw_symbol", start=i_start, end=i_end)),
        ("ohlcv-1m-open", dict(dataset=dataset, schema="ohlcv-1m", symbols=[sym],
                               stype_in="raw_symbol", start=o_start, end=o_end)),
        ("ohlcv-1m-prev", dict(dataset=dataset, schema="ohlcv-1m", symbols=[sym],
                               stype_in="raw_symbol", start=p_start, end=p_end)),
    ]
    return jobs


def cost_symbol(gate, sym, d, dataset):
    """get_cost de las 4 peticiones SIN descargar nada."""
    coste = {}
    for etiqueta, kw in jobs_for(sym, d, dataset):
        coste[etiqueta] = round(gate.check(etiqueta + " " + sym, **kw), 6)
    return coste


def fetch_symbol(hist, gate, sym, d, dataset):
    """Descarga tbbo + imbalance + ohlcv-1m (apertura y cierre previo). FAIL-LOUD."""
    jobs = jobs_for(sym, d, dataset)
    coste = cost_symbol(gate, sym, d, dataset)   # el gate corre ANTES de pedir un byte
    out = {}
    for etiqueta, kw in jobs:
        out[etiqueta] = _rows(_get_range(hist, etiqueta + " " + sym, **kw))
    return out, coste


def shape_trades(recs):
    rows = []
    for r in recs:
        px = _px(r.get("price"))
        if px is None:
            continue
        rows.append({"ts": _ts_epoch(r), "price": px, "size": _int(r.get("size")) or 0,
                     "bid": _px(r.get("bid_px_00")), "ask": _px(r.get("ask_px_00"))})
    rows.sort(key=lambda x: x["ts"])
    return rows


def shape_imbalance(recs):
    rows = []
    for r in recs:
        side = r.get("side")
        if hasattr(side, "decode"):
            side = side.decode()
        rows.append({"ts": _ts_epoch(r),
                     "ref_price": _px(r.get("ref_price")),
                     "paired_qty": _int(r.get("paired_qty")),
                     "total_imbalance_qty": _int(r.get("total_imbalance_qty")),
                     "side": str(side) if side is not None else None})
    rows.sort(key=lambda x: x["ts"])
    return rows


def shape_resultado(open_recs, prev_recs, dataset):
    """open oficial de RTH y precio a +30 min, del MISMO dataset (mismo reloj que la feature)."""
    res = {"open": None, "px_30m": None, "prev_close": None,
           "fuente": "%s ohlcv-1m" % dataset, "nota": None}
    bars = []
    for r in open_recs:
        bars.append((_ts_epoch(r), _px(r.get("open")), _px(r.get("close"))))
    bars.sort(key=lambda x: x[0])
    by_min = {}
    for ts, op, cl in bars:
        by_min[et_minute_of_day(ts)] = (op, cl)
    if RTH_OPEN_MIN in by_min and by_min[RTH_OPEN_MIN][0] is not None:
        res["open"] = by_min[RTH_OPEN_MIN][0]
    else:
        res["nota"] = "sin barra 1m de 09:30 en %s" % dataset
    m30 = RTH_OPEN_MIN + 29                       # cierre de la barra 09:59 = open+30min
    if m30 in by_min and by_min[m30][1] is not None:
        res["px_30m"] = by_min[m30][1]
    elif res["nota"] is None:
        res["nota"] = "sin barra 1m de %s en %s" % (hhmm(m30), dataset)

    prevs = sorted(((_ts_epoch(r), _px(r.get("close"))) for r in prev_recs), key=lambda x: x[0])
    prevs = [c for _t, c in prevs if c is not None]
    if prevs:
        res["prev_close"] = prevs[-1]
    return res


def archive_symbol(hist, gate, sym, d, route, remeasure=False, cost_only=False):
    ent = resolve_dataset(hist, sym, d, route, remeasure=remeasure)
    dataset = ent.get("dataset")
    if not dataset or dataset == "dataset_desconocido":
        return {"sym": sym, "estado": "dataset_desconocido", "evidencia": ent.get("evidencia")}

    if cost_only:
        antes = gate.spent
        cost_symbol(gate, sym, d, dataset)
        return {"sym": sym, "estado": "cost_only", "dataset": dataset,
                "coste": round(gate.spent - antes, 6)}

    raw, coste = fetch_symbol(hist, gate, sym, d, dataset)
    trades = shape_trades(raw["tbbo"])
    imb = shape_imbalance(raw["imbalance"])
    tramos, total = build_tape(trades)
    resultado = shape_resultado(raw["ohlcv-1m-open"], raw["ohlcv-1m-prev"], dataset)

    doc = {
        "meta": {
            "sym": sym,
            "fecha": d.isoformat(),
            "dataset": dataset,
            "bolsa_primaria": ent.get("bolsa_primaria"),
            "clase_dato": "unconsolidated_direct",
            "schemas": {"tape": "tbbo", "imbalance": "imbalance",
                        "resultado": "ohlcv-1m", "prev_close": "ohlcv-1m"},
            "ventana_premkt_et": "04:00-09:30",
            "tramo_min": TRAMO_MIN,
            "coste_usd_medido": round(sum(coste.values()), 6),
            "coste_desglose": coste,
            "ts_descarga": int(time.time()),
            "generador": "scripts/premarket_unconsolidated.py",
            "clasificacion_cinta": "lee-ready con bid_px_00/ask_px_00 del propio tbbo; "
                                   "sin quote valida = NO clasificado (jamas repartido)",
            "n_trades_crudos": len(trades),
            "n_imbalance_crudos": len(imb),
        },
        "tape": tramos,
        "tape_total": total,
        "imbalance": reduce_imbalance(imb),
        "resultado": resultado,
    }
    path = os.path.join(HISTDIR, d.isoformat(), "premkt_unconsolidated_%s.json" % sym)
    atomic_write(path, json.dumps(doc, indent=1) + "\n")
    return {"sym": sym, "estado": "ok", "path": path, "dataset": dataset,
            "coste": doc["meta"]["coste_usd_medido"], "n_trades": len(trades),
            "n_imb": len(doc["imbalance"]),
            "sin_clasificar": total["n_sin_clasificar"],
            "resultado_ok": resultado["open"] is not None and resultado["px_30m"] is not None}


# ------------------------------------------------------------------------ main

def read_syms(path):
    with open(path) as fh:
        txt = fh.read()
    return [s.strip().upper() for s in txt.replace(",", " ").split() if s.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="archiva el premarket no consolidado (Databento)")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (T-1: hoy no existe)")
    ap.add_argument("--syms-file", default=os.path.join(REPO, "data", "fleet.txt"))
    ap.add_argument("--syms", nargs="+", help="anula --syms-file")
    ap.add_argument("--max-cost", type=float, default=MAX_COST_DEFAULT,
                    help="tope de coste de la corrida en USD (defecto %.2f)" % MAX_COST_DEFAULT)
    ap.add_argument("--remeasure-route", action="store_true",
                    help="vuelve a medir la bolsa primaria aunque este cacheada")
    ap.add_argument("--cost-only", action="store_true",
                    help="solo get_cost: no descarga ni escribe nada")
    args = ap.parse_args(argv)

    d = dt.date.fromisoformat(args.date)
    if not em_envelope.is_market_day(d):
        print("%s no es dia de mercado: no se escribe nada" % d)
        return 0

    syms = [s.upper() for s in args.syms] if args.syms else read_syms(args.syms_file)
    hist = _hist(api_key())
    gate = CostGate(hist, args.max_cost)
    route = load_route()

    resultados = []
    try:
        for sym in syms:
            r = archive_symbol(hist, gate, sym, d, route, remeasure=args.remeasure_route,
                               cost_only=args.cost_only)
            resultados.append(r)
            print(json.dumps(r))
    finally:
        save_route(route)

    ok = [r for r in resultados if r.get("estado") == "ok"]
    print("RESUMEN %s: %d/%d %s, coste medido $%.6f (tope $%.2f)"
          % (d, len(ok), len(syms),
             "presupuestados (COST-ONLY, sin descarga)" if args.cost_only else "archivados",
             gate.spent, args.max_cost))
    for etiqueta, c in gate.detail:
        if c > 0:
            print("  coste %-22s $%.6f" % (etiqueta, c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
