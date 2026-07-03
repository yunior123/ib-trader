"""sitecustomize.py — ARNES DE RELOJ VIRTUAL (solo activo con IBT_REGEN_SANDBOX).

Se carga automaticamente por `site` cuando este directorio esta en PYTHONPATH. NO se
importa nunca en produccion: el directorio scripts/regen_shim/ solo entra al PYTHONPATH
del subproceso que lanza scripts/regen_signals.py.

POR QUE UN SHIM Y NO UN PARCHE AL GENERADOR
-------------------------------------------
`scripts/bollinger_alarm.py` no se toca ni una linea: si tocaramos su logica de deteccion,
lo que midieramos no seria nuestra alarma. Lo unico que cambia es el RELOJ y el AUDIO:
  · time.time / localtime / gmtime  -> instante VIRTUAL (leido del reloj del sandbox)
  · time.sleep(n)                   -> avanza el reloj virtual n segundos Y materializa
                                       las barras que existirian en ese instante
  · subprocess.Popen de voz/banner  -> no-op (540 sesiones hablando serian horas de audio)
El resto (./gate, la escritura del fichero de señales) pasa TAL CUAL.

El generador escribe sus señales en <sandbox>/data/trading-signals/<fecha>.txt con el
timestamp VIRTUAL, que es exactamente el formato que scripts/signals_db.py ya parsea.
"""
import os
import sys

_SB = os.environ.get("IBT_REGEN_SANDBOX", "")
if _SB:
    import time as _time
    import subprocess as _sp

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from vclock import VClock, BAR_S                              # noqa: E402

    def _die(msg):
        # fail-loud: sin reloj no hay medicion; jamas un instante inventado
        sys.stderr.write("[regen-shim] FATAL %s\n" % msg)
        raise SystemExit(3)

    try:
        _T0 = float(os.environ["IBT_REGEN_T0"])
        _TEND = float(os.environ["IBT_REGEN_TEND"])
    except (KeyError, ValueError) as e:
        _die("IBT_REGEN_T0/IBT_REGEN_TEND ausentes o invalidos (%s)" % e)

    _bars = {}
    _feeddir = os.path.join(_SB, "_regen")
    if not os.path.isdir(_feeddir):
        _die("falta %s (el padre no volco las barras)" % _feeddir)
    for _fn in sorted(os.listdir(_feeddir)):
        if not _fn.startswith("allbars_") or not _fn.endswith(".txt"):
            continue
        _sym = _fn[len("allbars_"):-len(".txt")]
        _rows = []
        with open(os.path.join(_feeddir, _fn)) as _f:
            for _ln in _f:
                _p = _ln.split()
                if len(_p) != 6:
                    _die("linea invalida en %s: %r" % (_fn, _ln))
                _rows.append((int(_p[0]), float(_p[1]), float(_p[2]),
                              float(_p[3]), float(_p[4]), float(_p[5])))
        _bars[_sym] = _rows
    if not _bars:
        _die("cero simbolos en %s" % _feeddir)

    _VC = VClock(_SB, _T0, _TEND, _bars)
    # margen: si el generador no termina solo, lo cortamos en seco (nunca colgado)
    _SLACK = float(os.environ.get("IBT_REGEN_SLACK", 3600))

    _orig_sleep = _time.sleep
    _orig_time = _time.time
    _orig_localtime = _time.localtime
    _orig_gmtime = _time.gmtime

    def _now():
        return _VC.t

    def _sleep(n):
        if _VC.t > _VC.t_end + _SLACK:
            sys.stderr.write("[regen-shim] fin de sesion virtual alcanzado, saliendo\n")
            raise SystemExit(0)
        _VC.advance(n)

    def _localtime(t=None):
        return _orig_localtime(_VC.t if t is None else t)

    def _gmtime(t=None):
        return _orig_gmtime(_VC.t if t is None else t)

    _time.sleep = _sleep
    _time.time = _now
    _time.localtime = _localtime
    _time.gmtime = _gmtime

    # --- audio / banners: mudos. La señal SI se escribe al fichero (es la medicion). ---
    _MUTE = ("speak.sh", "osascript", "afplay", "/usr/bin/say", "terminal-notifier")

    def _muted(args):
        try:
            blob = " ".join(args) if isinstance(args, (list, tuple)) else str(args)
        except Exception:                                    # noqa: BLE001
            return False
        return any(m in blob for m in _MUTE)

    class _NullPopen:
        returncode = 0
        pid = -1
        stdout = None
        stderr = None
        stdin = None

        def __init__(self, *a, **k):
            pass

        def wait(self, timeout=None):
            return 0

        def communicate(self, input=None, timeout=None):
            return (b"", b"")

        def poll(self):
            return 0

        def kill(self):
            pass

        terminate = kill

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    _orig_popen = _sp.Popen

    def _popen(args, *a, **k):
        if _muted(args):
            return _NullPopen()
        return _orig_popen(args, *a, **k)

    _sp.Popen = _popen
