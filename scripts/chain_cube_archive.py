#!/usr/bin/env python3
"""chain_cube_archive.py — OLA 1 feature #16: indice, retencion y LECTOR REUTILIZABLE
del cubo de cadenas de opciones que ya se acumula solo.

QUE HAY HOY (medido 2026-07-25):
  data/history/<fecha>/opt_chain_<sym>_HHMM.txt   1 foto/5min/sym que deja opt_chain_cache
                                                  (25 el 21-jul, 234 el 22, 1035 el 23, 2105 el 24)
  data/history/<fecha>/chain_full_<sym>.json      cadena COMPLETA de Polygon con griegas REALES
                                                  (QQQ 854 contratos, 816 con griegas)
  data/opt_chain_<sym>.txt                        la foto viva (IBKR/TWS)

Nadie lo minaba y su unica copia son ficheros planos. Esto le pone: (1) un lector que
entiende LOS DOS formatos y dice de cual viene cada dato, (2) un indice con cobertura
honesta por sym/dia, (3) retencion con numeros medidos.

FORMATO IBKR (texto):
  # opt_chain QQQ | epoch 1784924179 | 2026-07-24 16:16:19 | spot 684.66 | exps 20260724 20260727
  # strike right exp bid ask vol oi iv delta gamma
  685.00 C 20260724 -1.00 -1.00 238672 2348 -1.0000 -1.0000 -1.0000

  El -1.00 FUERA DE RTH ES LA REALIDAD, no un error (TWS no da bid/ask/griegas con el
  mercado cerrado). REGLA: no se rellena JAMAS. El lector deja el crudo en `raw` y
  expone el campo normalizado a None + el nombre del campo en `missing`. Ningun consumidor
  puede confundir "no se" con un numero (ley anti-cero-plausible de ~/CLAUDE.md).

RETENCION (numeros MEDIDOS el 2026-07-25, no estimados):
  - contenido de fotos 5min:  2026-07-23  879 ficheros = 2,9 MB
                              2026-07-24 2105 ficheros = 7,1 MB   <- dia completo de referencia
  - el directorio del dia ocupa 14,9 MB (bloques de 4 KB: 2105 ficheros de ~3,5 KB pagan
    ~8,4 MB de relleno). Por eso NO se gzipea fichero a fichero: se AGRUPA por sym+dia.
  - agrupado y gzipeado: las 82 fotos de QQQ del 24-jul = 402 KB -> 120 KB (3,3x)
    => dia completo ~2,2 MB/dia = ~66 MB/mes = ~0,8 GB/año.
  POLITICA:
    dia 0 y dia 1  -> fotos sueltas intactas (daily_archive.py y los lectores vivos las usan)
    dia >= 2       -> bundle data/history/<fecha>/chains_<sym>_<fecha>.txt.gz, VERIFICADO
                      (paridad de filas releyendo el bundle) y solo entonces se borran las sueltas
    chain_full_*.json de dia >= 2 -> gzip en sitio (467 KB -> ~60 KB; son grandes, el bloque no importa)
    bundles        -> INDEFINIDOS. Desviacion consciente del doc (#16 decia borrar a 45 dias
                      "tras cargar a trades.db"): ese cubo en BD NO existe (trades.db ya ocupa
                      901 MB con 8 daemons leyendola), asi que borrar el bundle seria destruir
                      LA UNICA copia de la historia gamma. A 2,2 MB/dia se puede.
    GUARDA DURA    -> si data/history pasa de 3 GB, la retencion ABORTA y grita (no borra nada
                      por su cuenta: la decision de que se tira es de Yunior).

  !! --apply NO SE PUEDE ACTIVAR TODAVIA (verificado 2026-07-25). Tres consumidores leen las
     fotos SUELTAS por glob y se quedarian ciegos si se agrupan:
       scripts/local_option_scorer.py:34   glob opt_chain_*_[0-9][0-9][0-9][0-9].txt
       scripts/option_vehicle_backtest.py  primas desde data/history/<day>/
       scripts/replay.cpp:375              lee las cadenas del dia (3 convenciones de nombre)
     El paso 4 del doc ("ninguna feature lee los ficheros planos directamente") no esta hecho.
     Hasta migrarlos a este lector, la retencion se corre en DRY-RUN (que es el default) y a
     26,5 MB totales no hay ninguna urgencia de disco. La guarda de presupuesto sigue viva.

Uso:
  ./venv/bin/python scripts/chain_cube_archive.py --index                # indexa todos los dias
  ./venv/bin/python scripts/chain_cube_archive.py --index --date 2026-07-24
  ./venv/bin/python scripts/chain_cube_archive.py --du                   # cuanto ocupa cada cosa
  ./venv/bin/python scripts/chain_cube_archive.py --retention            # DRY-RUN (no toca nada)
  ./venv/bin/python scripts/chain_cube_archive.py --retention --apply    # agrupa + borra sueltas

Lector para otras features:
  snap = read_chain("data/opt_chain_qqq.txt")      -> ChainSnap(meta, rows)
  snaps = read_bundle("...chains_qqq_2026-07-24.txt.gz")
  for p in day_snapshots("2026-07-24", "QQQ"): ...

SEÑAL-SOLAMENTE: lee ficheros, escribe indice/bundles. Cero red, cero ordenes.
"""
import argparse
import glob
import gzip
import json
import os
import re
import sys
import time
from collections import namedtuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)

HIST = os.path.join("data", "history")
INDEX_PATH = os.path.join("data", "chain_cube_index.json")
HEALTH_PATH = os.path.join("data", "cube_health.json")

LOOSE_DAYS = 2                 # dias que se quedan como ficheros sueltos
HISTORY_BUDGET_GB = 3.0        # guarda dura del doc #16
SENTINEL = -1.0                # TWS fuera de RTH

# ---------------------------------------------------------------- lector

ChainRow = namedtuple("ChainRow", "sym ts exp strike right bid ask vol oi iv delta gamma src missing raw")
ChainSnap = namedtuple("ChainSnap", "meta rows")

_HDR = re.compile(
    r"^#\s*opt_chain\s+(?P<sym>\S+)\s*\|\s*epoch\s+(?P<epoch>\d+)"
    r"(?:\s*\|\s*(?P<local>[^|]*))?"
    r"(?:\s*\|\s*spot\s+(?P<spot>[-\d.]+))?"
    r"(?:\s*\|\s*exps\s+(?P<exps>[\d\s]+))?"
)

_QUOTE_FIELDS = ("bid", "ask")
_GREEK_FIELDS = ("iv", "delta", "gamma")


def _num(tok):
    """float(tok) o None si no es numero. NUNCA devuelve 0 de relleno."""
    try:
        return float(tok)
    except (TypeError, ValueError):
        return None


def _norm(v):
    """Sentinela -1 de TWS -> None (y el crudo se conserva en raw)."""
    if v is None:
        return None
    return None if v <= SENTINEL else v


def _open_text(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", errors="replace")
    return open(path, errors="replace")


def parse_ibkr_text(lines, path=""):
    """Parsea UNA foto en formato texto IBKR. Devuelve ChainSnap.
    Levanta ValueError si no hay cabecera valida (fail-loud: un fichero a medias
    NO se convierte en una cadena vacia con spot 0)."""
    meta = {"fmt": "ibkr_txt", "src": "ibkr_tws", "path": path,
            "sym": None, "ts": None, "spot": None, "exps": [],
            "bad_rows": 0, "n_rows": 0, "n_with_quotes": 0, "n_with_greeks": 0}
    rows = []
    cols = None
    for ln in lines:
        ln = ln.rstrip("\n")
        if not ln.strip():
            continue
        if ln.startswith("#"):
            m = _HDR.match(ln)
            if m:
                meta["sym"] = m.group("sym").upper()
                meta["ts"] = int(m.group("epoch"))
                meta["spot"] = _num(m.group("spot"))
                meta["exps"] = (m.group("exps") or "").split()
                continue
            toks = ln.lstrip("#").split()
            if toks and toks[0] == "strike":
                cols = toks
            continue
        if meta["sym"] is None:
            raise ValueError("fila de datos antes de la cabecera en %s" % path)
        t = ln.split()
        if len(t) < 7:
            meta["bad_rows"] += 1
            continue
        names = cols if (cols and len(cols) == len(t)) else \
            ["strike", "right", "exp", "bid", "ask", "vol", "oi", "iv", "delta", "gamma"][:len(t)]
        raw = {}
        for name, tok in zip(names, t):
            raw[name] = tok
        strike = _num(raw.get("strike"))
        right = (raw.get("right") or "").upper()[:1]
        exp = raw.get("exp")
        if strike is None or right not in ("C", "P") or not (exp or "").isdigit():
            meta["bad_rows"] += 1
            continue
        vals = {}
        missing = []
        for name in ("bid", "ask", "vol", "oi", "iv", "delta", "gamma"):
            v = _num(raw.get(name))
            nv = _norm(v) if name in _QUOTE_FIELDS + _GREEK_FIELDS else v
            if nv is None:
                missing.append(name)
            vals[name] = nv
        rows.append(ChainRow(meta["sym"], meta["ts"], int(exp), strike, right,
                             vals["bid"], vals["ask"], vals["vol"], vals["oi"],
                             vals["iv"], vals["delta"], vals["gamma"],
                             "ibkr_tws", tuple(missing), raw))
    meta["n_rows"] = len(rows)
    meta["n_with_quotes"] = sum(1 for r in rows if r.bid is not None and r.ask is not None)
    meta["n_with_greeks"] = sum(1 for r in rows if r.gamma is not None)
    if meta["sym"] is None:
        raise ValueError("sin cabecera opt_chain: %s" % path)
    return ChainSnap(meta, rows)


def parse_polygon_json(obj, path=""):
    """Parsea el chain_full_<sym>.json de Polygon (griegas/IV/OI REALES, sin bid/ask:
    la key no tiene entitlement de cotizaciones -> bid/ask = None SIEMPRE, jamas 0)."""
    pm = obj.get("meta") or {}
    meta = {"fmt": "polygon_json", "src": "polygon_snapshot", "path": path,
            "sym": (pm.get("sym") or "").upper() or None,
            "ts": int(float(pm.get("snapshot_epoch") or 0)) or None,
            "spot": _num(pm.get("spot")), "exps": [],
            "bad_rows": 0, "n_rows": 0, "n_with_quotes": 0, "n_with_greeks": 0,
            "polygon_meta": pm}
    rows = []
    exps = set()
    for c in (obj.get("results") or []):
        d = c.get("details") or {}
        strike = _num(d.get("strike_price"))
        ed = (d.get("expiration_date") or "").replace("-", "")
        ct = (d.get("contract_type") or "")
        right = "C" if ct.startswith("c") else ("P" if ct.startswith("p") else "")
        if strike is None or not ed.isdigit() or right not in ("C", "P"):
            meta["bad_rows"] += 1
            continue
        g = c.get("greeks") or {}
        day = c.get("day") or {}
        iv = _num(c.get("implied_volatility"))
        delta = _num(g.get("delta"))
        gamma = _num(g.get("gamma"))
        oi = _num(c.get("open_interest"))
        vol = _num(day.get("volume"))
        missing = ["bid", "ask"]     # NO_ENTITLED en este plan de Polygon
        for name, v in (("iv", iv), ("delta", delta), ("gamma", gamma),
                        ("oi", oi), ("vol", vol)):
            if v is None:
                missing.append(name)
        exps.add(int(ed))
        rows.append(ChainRow(meta["sym"], meta["ts"], int(ed), strike, right,
                             None, None, vol, oi, iv, delta, gamma,
                             "polygon_snapshot", tuple(missing), c))
    meta["exps"] = [str(e) for e in sorted(exps)]
    meta["n_rows"] = len(rows)
    meta["n_with_quotes"] = 0
    meta["n_with_greeks"] = sum(1 for r in rows if r.gamma is not None)
    if meta["sym"] is None:
        raise ValueError("chain_full sin meta.sym: %s" % path)
    return ChainSnap(meta, rows)


def read_chain(path):
    """Lector UNICO de los dos formatos (.txt/.txt.gz IBKR, .json/.json.gz Polygon).
    meta['src'] dice de donde viene cada dato. Levanta si el fichero no se entiende."""
    base = os.path.basename(path)
    if base.endswith(".json") or base.endswith(".json.gz"):
        with _open_text(path) as f:
            return parse_polygon_json(json.load(f), path)
    with _open_text(path) as f:
        return parse_ibkr_text(f, path)


def read_bundle(path):
    """Lee un bundle chains_<sym>_<fecha>.txt.gz (N fotos concatenadas) -> [ChainSnap]."""
    out = []
    buf = []
    with _open_text(path) as f:
        for ln in f:
            if _HDR.match(ln) and buf:
                out.append(parse_ibkr_text(buf, path))
                buf = []
            buf.append(ln)
    if buf:
        out.append(parse_ibkr_text(buf, path))
    return out


def day_snapshot_paths(date, sym=None):
    """Rutas de las fotos 5min de un dia (sueltas y/o bundle), ordenadas."""
    d = os.path.join(HIST, date)
    # dos convenciones reales: _HHMM.txt (21-jul en adelante) y _HH.txt (las primeras
    # fotos horarias del 21/22-jul). Las dos entran; opt_chain_<sym>.txt (foto del dia
    # que copia daily_archive) NO, porque no lleva sufijo numerico.
    sl = sym.lower() if sym else "*"
    loose = sorted(set(glob.glob(os.path.join(d, "opt_chain_%s_[0-9][0-9].txt" % sl)) +
                       glob.glob(os.path.join(d, "opt_chain_%s_[0-9][0-9][0-9][0-9].txt" % sl))))
    bpat = "chains_%s_%s.txt.gz" % (sym.lower() if sym else "*", date)
    bundles = sorted(glob.glob(os.path.join(d, bpat)))
    return loose, bundles


def day_snapshots(date, sym=None):
    """Generador de ChainSnap de un dia, venga de sueltas o de bundle."""
    loose, bundles = day_snapshot_paths(date, sym)
    for p in loose:
        try:
            yield read_chain(p)
        except (ValueError, OSError) as e:
            print("  AVISO foto ilegible %s: %s" % (p, e), file=sys.stderr)
    for p in bundles:
        try:
            for s in read_bundle(p):
                yield s
        except (ValueError, OSError) as e:
            print("  AVISO bundle ilegible %s: %s" % (p, e), file=sys.stderr)


def full_chain_path(sym, date=None):
    """chain_full_<sym>.json[.gz] del dia pedido (o el mas reciente que exista). None si no hay."""
    sl = sym.lower()
    dates = [date] if date else sorted(os.listdir(HIST), reverse=True)
    for d in dates:
        for ext in (".json", ".json.gz"):
            p = os.path.join(HIST, d, "chain_full_%s%s" % (sl, ext))
            if os.path.exists(p) and os.path.getsize(p) > 0:
                return p
    return None


def latest_chain(sym):
    """La foto IBKR viva (data/opt_chain_<sym>.txt). None si no existe."""
    p = os.path.join("data", "opt_chain_%s.txt" % sym.lower())
    return p if os.path.exists(p) and os.path.getsize(p) > 0 else None


# ---------------------------------------------------------------- escritura atomica

def atomic_write_json(path, obj):
    tmp = path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------- indice

def dates_available():
    if not os.path.isdir(HIST):
        return []
    return sorted(d for d in os.listdir(HIST)
                  if re.match(r"^\d{4}-\d{2}-\d{2}$", d) and os.path.isdir(os.path.join(HIST, d)))


def index_day(date):
    """Cobertura HONESTA de un dia: fotos, filas, cuantas con cotizacion y cuantas con griegas."""
    syms = {}
    n_files = 0
    for snap in day_snapshots(date):
        m = snap.meta
        s = syms.setdefault(m["sym"], {"snaps": 0, "rows": 0, "rows_with_quotes": 0,
                                       "rows_with_greeks": 0, "bad_rows": 0,
                                       "first_ts": None, "last_ts": None, "exps": []})
        s["snaps"] += 1
        s["rows"] += m["n_rows"]
        s["rows_with_quotes"] += m["n_with_quotes"]
        s["rows_with_greeks"] += m["n_with_greeks"]
        s["bad_rows"] += m["bad_rows"]
        if m["ts"]:
            s["first_ts"] = m["ts"] if s["first_ts"] is None else min(s["first_ts"], m["ts"])
            s["last_ts"] = m["ts"] if s["last_ts"] is None else max(s["last_ts"], m["ts"])
        for e in m["exps"]:
            if e not in s["exps"]:
                s["exps"].append(e)
        n_files += 1
    fulls = {}
    for p in sorted(glob.glob(os.path.join(HIST, date, "chain_full_*.json*"))):
        try:
            snap = read_chain(p)
        except (ValueError, OSError) as e:
            print("  AVISO chain_full ilegible %s: %s" % (p, e), file=sys.stderr)
            continue
        fulls[snap.meta["sym"]] = {
            "contracts": snap.meta["n_rows"],
            "with_greeks": snap.meta["n_with_greeks"],
            "with_quotes": snap.meta["n_with_quotes"],
            "bytes": os.path.getsize(p),
            "path": p,
            "greeks_src": (snap.meta.get("polygon_meta") or {}).get("greeks"),
        }
    loose, bundles = day_snapshot_paths(date)
    return {
        "snapshots": n_files,
        "loose_files": len(loose),
        "bundles": len(bundles),
        "storage": "bundle" if (bundles and not loose) else ("mixed" if bundles else "loose"),
        "bytes_dir": dir_bytes(os.path.join(HIST, date)),
        "syms": syms,
        "full_chains": fulls,
    }


def dir_bytes(path):
    tot = 0
    for root, _dirs, files in os.walk(path):
        for fn in files:
            try:
                tot += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return tot


def build_index(dates=None):
    idx = {"updated": int(time.time()), "days": {}, "totals": {}}
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH) as f:
                old = json.load(f)
            idx["days"] = old.get("days", {})
        except (ValueError, OSError):
            pass                                   # indice corrupto: se reconstruye entero
    for d in (dates or dates_available()):
        idx["days"][d] = index_day(d)
        print("  %s: %d fotos, %d syms, %.1f MB" % (
            d, idx["days"][d]["snapshots"], len(idx["days"][d]["syms"]),
            idx["days"][d]["bytes_dir"] / 1e6))
    tot_rows = sum(s["rows"] for d in idx["days"].values() for s in d["syms"].values())
    idx["totals"] = {
        "days": len(idx["days"]),
        "snapshots": sum(d["snapshots"] for d in idx["days"].values()),
        "rows": tot_rows,
        "history_bytes": dir_bytes(HIST),
    }
    atomic_write_json(INDEX_PATH, idx)
    return idx


# ---------------------------------------------------------------- retencion

def bundle_day(date, apply_=False):
    """Agrupa las fotos sueltas de un dia en un .txt.gz por sym. Verifica paridad de
    filas releyendo el bundle ANTES de borrar nada. Idempotente."""
    acts = []
    loose, _ = day_snapshot_paths(date)
    if not loose:
        return acts
    by_sym = {}
    for p in loose:
        m = re.match(r"^opt_chain_([a-z0-9.]+)_(\d{2}|\d{4})\.txt$", os.path.basename(p))
        if not m:
            continue
        hhmm = m.group(2)
        minute = int(hhmm) * 100 if len(hhmm) == 2 else int(hhmm)   # _HH y _HHMM en el mismo orden
        by_sym.setdefault(m.group(1), []).append((minute, p))
    for sl, items in sorted(by_sym.items()):
        items.sort()
        out = os.path.join(HIST, date, "chains_%s_%s.txt.gz" % (sl, date))
        src_rows = 0
        for _hhmm, p in items:
            try:
                src_rows += read_chain(p).meta["n_rows"]
            except (ValueError, OSError) as e:
                acts.append({"action": "skip_sym", "sym": sl, "date": date,
                             "reason": "foto ilegible %s: %s" % (p, e)})
                src_rows = None
                break
        if src_rows is None:
            continue
        act = {"action": "bundle", "sym": sl.upper(), "date": date,
               "files": len(items), "rows": src_rows,
               "bytes_loose": sum(os.path.getsize(p) for _h, p in items),
               "out": out, "applied": False}
        if not apply_:
            acts.append(act)
            continue
        existing = []
        if os.path.exists(out):
            try:
                existing = read_bundle(out)
            except (ValueError, OSError):
                existing = []
        tmp = out + ".tmp.%d" % os.getpid()
        with gzip.open(tmp, "wt") as g:
            for snap in existing:                       # idempotente: conserva lo ya agrupado
                _rewrite(g, snap)
            for _hhmm, p in items:
                with open(p, errors="replace") as f:
                    g.write(f.read())
        os.replace(tmp, out)
        got = sum(s.meta["n_rows"] for s in read_bundle(out))
        want = src_rows + sum(s.meta["n_rows"] for s in existing)
        if got != want:
            act["error"] = "paridad FALLA (bundle %d filas vs fuente %d) -> NO se borra nada" % (got, want)
            acts.append(act)
            continue
        for _hhmm, p in items:
            os.unlink(p)
        act["applied"] = True
        act["bytes_bundle"] = os.path.getsize(out)
        acts.append(act)
    return acts


def _rewrite(fh, snap):
    """Re-serializa una foto ya parseada (para reconstruir bundles idempotentes)."""
    m = snap.meta
    fh.write("# opt_chain %s | epoch %d | %s | spot %s | exps %s\n" % (
        m["sym"], m["ts"] or 0, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m["ts"] or 0)),
        ("%.2f" % m["spot"]) if m["spot"] is not None else "nan", " ".join(m["exps"])))
    fh.write("# strike right exp bid ask vol oi iv delta gamma\n")
    for r in snap.rows:
        raw = r.raw if isinstance(r.raw, dict) else {}
        fh.write("%s %s %s %s %s %s %s %s %s %s\n" % (
            raw.get("strike", "%.2f" % r.strike), r.right, r.exp,
            raw.get("bid", "-1.00"), raw.get("ask", "-1.00"),
            raw.get("vol", "-1"), raw.get("oi", "-1"),
            raw.get("iv", "-1.0000"), raw.get("delta", "-1.0000"), raw.get("gamma", "-1.0000")))


def gzip_full_chains(date, apply_=False):
    acts = []
    for p in sorted(glob.glob(os.path.join(HIST, date, "chain_full_*.json"))):
        act = {"action": "gzip_full", "date": date, "path": p,
               "bytes": os.path.getsize(p), "applied": False}
        if apply_:
            out = p + ".gz"
            tmp = out + ".tmp.%d" % os.getpid()
            with open(p, "rb") as f, gzip.open(tmp, "wb") as g:
                g.write(f.read())
            os.replace(tmp, out)
            try:
                read_chain(out)                     # verifica antes de borrar el crudo
            except (ValueError, OSError) as e:
                act["error"] = "gz ilegible (%s) -> se conserva el .json" % e
                os.unlink(out)
                acts.append(act)
                continue
            os.unlink(p)
            act["applied"] = True
            act["bytes_gz"] = os.path.getsize(out)
        acts.append(act)
    return acts


def retention(apply_=False, today=None):
    """Aplica la politica. Con apply_=False no toca NADA (dry-run por defecto)."""
    hb = dir_bytes(HIST)
    if hb > HISTORY_BUDGET_GB * 1e9:
        raise RuntimeError("data/history = %.2f GB > presupuesto %.1f GB: retencion ABORTADA, "
                           "que se tira lo decide Yunior" % (hb / 1e9, HISTORY_BUDGET_GB))
    today = today or time.strftime("%Y-%m-%d")
    acts = []
    for d in dates_available():
        if d >= today:
            continue
        age = _age_days(d, today)
        if age < LOOSE_DAYS:
            continue
        acts += bundle_day(d, apply_)
        acts += gzip_full_chains(d, apply_)
    health = {
        "date": today,
        "updated": int(time.time()),
        "history_bytes": dir_bytes(HIST),
        "history_gb": round(dir_bytes(HIST) / 1e9, 4),
        "budget_gb": HISTORY_BUDGET_GB,
        "loose_days_kept": LOOSE_DAYS,
        "applied": bool(apply_),
        "actions": acts,
    }
    atomic_write_json(HEALTH_PATH, health)
    return health


def _age_days(date, today):
    a = time.mktime(time.strptime(date, "%Y-%m-%d"))
    b = time.mktime(time.strptime(today, "%Y-%m-%d"))
    return int(round((b - a) / 86400.0))


def du_report():
    rows = []
    for d in dates_available():
        loose, bundles = day_snapshot_paths(d)
        lb = sum(os.path.getsize(p) for p in loose)
        bb = sum(os.path.getsize(p) for p in bundles)
        fb = sum(os.path.getsize(p) for p in glob.glob(os.path.join(HIST, d, "chain_full_*.json*")))
        rows.append((d, len(loose), lb, len(bundles), bb, fb, dir_bytes(os.path.join(HIST, d))))
    print("fecha       sueltas   MB    bundles   MB   chain_full MB   dir MB")
    for d, nl, lb, nb, bb, fb, tot in rows:
        print("%s %7d %6.2f %8d %5.2f %10.2f %10.2f" %
              (d, nl, lb / 1e6, nb, bb / 1e6, fb / 1e6, tot / 1e6))
    print("data/history total: %.2f MB (presupuesto %.0f GB)" % (dir_bytes(HIST) / 1e6, HISTORY_BUDGET_GB))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--date")
    ap.add_argument("--du", action="store_true")
    ap.add_argument("--retention", action="store_true")
    ap.add_argument("--apply", action="store_true",
                    help="con --retention: agrupa y borra sueltas DE VERDAD. Ojo: hay 3 "
                         "consumidores de las sueltas (ver cabecera) -> no usar aun")
    a = ap.parse_args()
    did = False
    if a.du:
        du_report()
        did = True
    if a.index:
        idx = build_index([a.date] if a.date else None)
        print("indice: %d dias, %d fotos, %d filas -> %s" %
              (idx["totals"]["days"], idx["totals"]["snapshots"], idx["totals"]["rows"], INDEX_PATH))
        did = True
    if a.retention:
        h = retention(apply_=a.apply)
        nb = sum(1 for x in h["actions"] if x["action"] == "bundle")
        print("%s: %d bundles, %d gzip de chain_full, history %.2f MB" %
              ("APLICADO" if a.apply else "DRY-RUN", nb,
               sum(1 for x in h["actions"] if x["action"] == "gzip_full"), h["history_bytes"] / 1e6))
        for x in h["actions"]:
            if x.get("error"):
                print("  ERROR %s" % x["error"], file=sys.stderr)
        if a.apply:
            print("  AVISO: local_option_scorer.py, option_vehicle_backtest.py y replay.cpp "
                  "leen las fotos SUELTAS por glob; si acabas de agruparlas, migralos a "
                  "chain_cube_archive.day_snapshots() antes de confiar en ellos.", file=sys.stderr)
        did = True
    if not did:
        ap.print_help()


if __name__ == "__main__":
    main()
