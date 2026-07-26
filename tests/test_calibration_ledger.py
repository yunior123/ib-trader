"""calibration_ledger.py — wilson() edges + calibrate()/grade() guards."""
import json
import math

import pytest


# ---------- wilson() ----------
def test_wilson_n_zero_no_division(calib):
    # CRITICAL: empty bucket must not divide by zero.
    assert calib.wilson(0, 0) == (0.0, 0.0, 0.0)


def test_wilson_all_wins_rate_one(calib):
    p, lo, hi = calib.wilson(10, 10)
    assert p == 1.0
    assert 0.0 <= lo <= 1.0
    assert hi <= 1.0 + 1e-9
    assert lo < 1.0  # Wilson lower bound never overconfident at small n


def test_wilson_zero_wins_rate_zero(calib):
    p, lo, hi = calib.wilson(0, 10)
    assert p == 0.0
    assert lo == pytest.approx(0.0, abs=1e-9)
    assert hi > 0.0  # upper bound accounts for uncertainty


def test_wilson_typical_25_of_42(calib):
    p, lo, hi = calib.wilson(25, 42)
    assert p == pytest.approx(25 / 42, abs=1e-9)
    assert 0.0 < lo < p < hi < 1.0
    # lower bound must sit meaningfully below the point estimate
    assert p - lo > 0.05


def test_wilson_lower_below_upper_always(calib):
    for w, n in [(1, 2), (3, 100), (99, 100), (50, 50)]:
        p, lo, hi = calib.wilson(w, n)
        assert lo <= p <= hi
        assert 0.0 <= lo and hi <= 1.0 + 1e-9


# ---------- calibrate() / grade() guards ----------
def test_calibrate_empty_log_returns_dict(calib, tmp_path, monkeypatch):
    # CRITICAL: no crash when the ledger file does not exist.
    monkeypatch.setattr(calib, "LOG", str(tmp_path / "nope.jsonl"))
    monkeypatch.setattr(calib, "OUT", str(tmp_path / "out.json"))
    assert calibrate_safe(calib) == {}


def calibrate_safe(calib):
    return calib.calibrate()


def test_grade_missing_log_returns_zero_no_network(calib, tmp_path, monkeypatch):
    # If the log is absent grade() must short-circuit to 0 without any yfinance call.
    monkeypatch.setattr(calib, "LOG", str(tmp_path / "absent.jsonl"))

    def _boom(*a, **k):
        raise AssertionError("grade() hit the network on an empty log")

    monkeypatch.setattr(calib.yf, "Ticker", _boom)
    assert calib.grade() == 0


def test_calibrate_excludes_no_entry_rows(calib, tmp_path, monkeypatch):
    # no_entry rows must NOT count toward win-rate (they never triggered).
    log = tmp_path / "calib_log.jsonl"
    out = tmp_path / "calibration.json"
    rows = [
        dict(date="2026-07-01", sym="NVDA", setup_type="reclaim_wall",
             regime="POSITIVO", direction="bull", result="win"),
        dict(date="2026-07-01", sym="MU", setup_type="reclaim_wall",
             regime="POSITIVO", direction="bull", result="loss"),
        dict(date="2026-07-01", sym="AMD", setup_type="reclaim_wall",
             regime="POSITIVO", direction="bull", result="no_entry"),
        dict(date="2026-07-01", sym="SMH", setup_type="reclaim_wall",
             regime="POSITIVO", direction="bull", result=None),
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(calib, "LOG", str(log))
    monkeypatch.setattr(calib, "OUT", str(out))

    res = calib.calibrate()
    k = "reclaim_wall|POSITIVO"
    assert k in res
    # only the win + loss count; no_entry and ungraded(None) excluded.
    assert res[k]["n"] == 2
    assert res[k]["wins"] == 1
    assert 0.0 <= res[k]["rate"] <= 1.0
    assert res[k]["trust"] is False  # n < MIN_N
    # file was written and is valid json
    assert json.load(open(out)) == res


def test_calibrate_bad_date_does_not_crash(calib, tmp_path, monkeypatch):
    # A malformed date must fall back (age=0) instead of raising.
    log = tmp_path / "calib_log.jsonl"
    log.write_text(json.dumps(dict(
        date="not-a-date", sym="QQQ", setup_type="breakdown",
        regime="NEGATIVO", direction="bear", result="win")) + "\n")
    monkeypatch.setattr(calib, "LOG", str(log))
    monkeypatch.setattr(calib, "OUT", str(tmp_path / "o.json"))
    res = calib.calibrate()
    assert res["breakdown|NEGATIVO"]["n"] == 1


# ============================================================================
# grade(): el corte tras la entrada tiene que ser TEMPORAL, no una mascara
# ============================================================================
# DEFECTO A (hunt 2026-07-24, `calibration_ledger.py:110`):
#
#     after = d[d.High >= s["entry"]] if bull else d[d.Low <= s["entry"]]
#
# Eso NO es "las barras despues de la entrada": es "las barras cuyo High supera
# el precio de entrada". Justo las barras del retroceso —donde VIVE el stop—
# tienen High por debajo de la entrada, asi que la mascara las BORRA y el
# recorrido secuencial nunca ve el stop. Resultado: la operacion se registra
# como GANADA. Este fichero es el motor de la calibracion "empirica" de la casa
# (escribe data/calibration.json), asi que la mentira entra en cada probabilidad
# por bucket setup x regimen que cantan los PDF.
#
# Caso real que lo motiva: 2026-07-21, ledger vivo de 56 filas con 24 win / 3
# loss (WR 88.9% publicado en data/calibration.json). Replayando esas mismas
# filas contra poly_bars con corte temporal, tres "victorias" eran stops.


class _FakeBars(object):
    """DataFrame minimo con lo que grade() usa: .index.strftime, .High, .Low,
    .Close, len(), indexacion booleana e .iloc. Se construye a mano para que el
    caso sea legible y no dependa de pandas ni de la red."""

    def __init__(self, rows, date="2026-07-21"):
        # rows: [(hh_mm, high, low, close), ...]
        self._rows = list(rows)
        self._date = date

    # --- lo que el codigo de grade() toca ---
    def __len__(self):
        return len(self._rows)

    @property
    def index(self):
        outer = self

        class _Idx(object):
            def strftime(self, _fmt):
                return _Series([outer._date] * len(outer._rows))
        return _Idx()

    @property
    def High(self):
        return _Series([r[1] for r in self._rows])

    @property
    def Low(self):
        return _Series([r[2] for r in self._rows])

    @property
    def Close(self):
        return _Series([r[3] for r in self._rows])

    def __getitem__(self, key):
        if isinstance(key, _Series):          # mascara booleana
            return _FakeBars([r for r, k in zip(self._rows, list(key.values)) if k],
                             self._date)
        raise KeyError(key)

    @property
    def iloc(self):
        outer = self

        class _ILoc(object):
            def __getitem__(self, k):
                if isinstance(k, slice):
                    return _FakeBars(outer._rows[k], outer._date)
                return _Bar(outer._rows[k])
        return _ILoc()

    def iterrows(self):
        for i, r in enumerate(self._rows):
            yield i, _Bar(r)


class _Bar(object):
    def __init__(self, r):
        self.High, self.Low, self.Close = r[1], r[2], r[3]


class _Series(object):
    """Imita lo justo de pandas.Series, incluido `.values` como ndarray: el
    arreglo usa `printed.values.argmax()` (primera barra True) igual que
    haria sobre un DataFrame real."""

    def __init__(self, values):
        import numpy as np
        self.values = np.asarray(list(values))

    def __eq__(self, other):
        return _Series([v == other for v in self.values])

    def __ge__(self, other):
        return _Series([v >= other for v in self.values])

    def __le__(self, other):
        return _Series([v <= other for v in self.values])

    def any(self):
        return bool(self.values.any())

    def max(self):
        return self.values.max()

    def min(self):
        return self.values.min()

    @property
    def iloc(self):
        vals = self.values

        class _I(object):
            def __getitem__(self, k):
                return vals[k]
        return _I()

    def __len__(self):
        return len(self.values)


def _graded(calib, tmp_path, monkeypatch, row, bars):
    """Corre grade() sobre UNA fila con `bars` inyectadas (sin red) y devuelve
    el `result` escrito."""
    log = tmp_path / "calib_log.jsonl"
    log.write_text(json.dumps(row) + "\n")
    monkeypatch.setattr(calib, "LOG", str(log))

    class _T(object):
        def __init__(self, _sym):
            pass

        def history(self, **_k):
            return bars

    monkeypatch.setattr(calib.yf, "Ticker", _T)
    assert calib.grade() == 1
    return json.loads(log.read_text().strip())["result"]


def test_grade_bull_stop_en_el_retroceso_es_loss(calib, tmp_path, monkeypatch):
    """EL TEST DEL DEFECTO A. Bull entry=100, target=102, stop=99.

    Camino real: imprime la entrada, RETROCEDE tocando el stop, y solo despues
    sube al target. Es una PERDIDA: el bracket ya estaba fuera cuando llego el
    target.

    La barra del stop tiene High=99.8 < entry=100, asi que `d[d.High >= entry]`
    la BORRA y el bucle salta directo a la barra del target -> "win".
    Con corte temporal (d.iloc[i0:]) el stop se ve y sale "loss".
    """
    bars = _FakeBars([
        ("09:30", 100.5, 99.9, 100.2),   # imprime la entrada (High >= 100)
        ("09:45", 99.80, 98.5, 98.80),   # STOP: Low 98.5 <= 99. High<entry -> la mascara la borraba
        ("10:00", 102.5, 100.5, 102.3),  # target, pero ya estabamos fuera
    ])
    row = dict(date="2026-07-21", sym="NVDA", setup_type="reclaim_wall",
               regime="POSITIVO", direction="bull", entry=100.0, target=102.0,
               stop=99.0, pred_prob=0.55, result=None)
    assert _graded(calib, tmp_path, monkeypatch, row, bars) == "loss"


def test_grade_bear_stop_en_el_rebote_es_loss(calib, tmp_path, monkeypatch):
    """Simetrico para bear: la mascara era `d[d.Low <= entry]`, y borra las
    barras del REBOTE, que son las que tocan el stop de un corto."""
    bars = _FakeBars([
        ("09:30", 100.2, 99.50, 99.80),   # imprime la entrada (Low <= 100)
        ("09:45", 101.60, 100.20, 101.4),  # STOP: High 101.6 >= 101. Low>entry -> borrada
        ("10:00", 100.0, 97.50, 97.80),    # target 98, pero ya estabamos fuera
    ])
    row = dict(date="2026-07-21", sym="NVDA", setup_type="breakdown",
               regime="POSITIVO", direction="bear", entry=100.0, target=98.0,
               stop=101.0, pred_prob=0.45, result=None)
    assert _graded(calib, tmp_path, monkeypatch, row, bars) == "loss"


def test_grade_ganadora_limpia_sigue_siendo_win(calib, tmp_path, monkeypatch):
    """El arreglo no puede convertir en perdida lo que si gano: sin retroceso al
    stop, target primero -> win."""
    bars = _FakeBars([
        ("09:30", 100.5, 99.90, 100.2),
        ("09:45", 101.4, 100.10, 101.3),
        ("10:00", 102.5, 101.00, 102.3),
    ])
    row = dict(date="2026-07-21", sym="NVDA", setup_type="reclaim_wall",
               regime="POSITIVO", direction="bull", entry=100.0, target=102.0,
               stop=99.0, pred_prob=0.55, result=None)
    assert _graded(calib, tmp_path, monkeypatch, row, bars) == "win"


def test_grade_barra_de_entrada_ambigua_resuelve_stop_primero(calib, tmp_path,
                                                              monkeypatch):
    """La barra que imprime la entrada tambien toca el stop. Sin ruta sub-barra
    no se puede saber el orden: la casa resuelve SL PRIMERO (misma regla
    conservadora que barrier_labels.triple_barrier), y se declara."""
    bars = _FakeBars([
        ("09:30", 100.6, 98.40, 98.90),   # entrada Y stop en la misma barra
        ("09:45", 101.4, 99.50, 101.3),
        ("10:00", 102.5, 100.9, 102.3),
    ])
    row = dict(date="2026-07-21", sym="NVDA", setup_type="reclaim_wall",
               regime="POSITIVO", direction="bull", entry=100.0, target=102.0,
               stop=99.0, pred_prob=0.55, result=None)
    assert _graded(calib, tmp_path, monkeypatch, row, bars) == "loss"


def test_grade_sin_entrada_es_no_entry(calib, tmp_path, monkeypatch):
    """Nunca imprime la entrada -> no_entry (no cuenta en el denominador)."""
    bars = _FakeBars([
        ("09:30", 99.5, 98.9, 99.2),
        ("09:45", 99.8, 99.0, 99.4),
        ("10:00", 99.9, 99.1, 99.5),
    ])
    row = dict(date="2026-07-21", sym="NVDA", setup_type="reclaim_wall",
               regime="POSITIVO", direction="bull", entry=100.0, target=102.0,
               stop=99.0, pred_prob=0.55, result=None)
    assert _graded(calib, tmp_path, monkeypatch, row, bars) == "no_entry"
