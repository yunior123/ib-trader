"""vclock.py — RELOJ VIRTUAL + FEEDER DE BARRAS para la regeneracion de señales.

Vive DENTRO del proceso hijo (el generador de señales real, sin modificar). Su unico
trabajo: que el generador crea que estamos en el instante virtual V, y que el sandbox
contenga EXACTAMENTE las barras que existian en V.

INVARIANTE DE NO-LOOK-AHEAD (el que hace que los 540 dias valgan algo)
----------------------------------------------------------------------
Una barra 1m con timestamp T cubre [T, T+60) y SOLO se conoce en T+60. Por eso
`materialize(V)` escribe unicamente las barras con `ts + 60 <= V` — identico a
scripts/replay.cpp (K::BAR_S) e identico a ibkr_bar_bridge (que jamas emite la vela en
curso). El sandbox es un PREFIJO monotono: nunca se reescribe una linea, solo se añade.

No hay aleatoriedad aqui: mismo (fecha, simbolos, warm) -> mismos ficheros, byte a byte.
Verificado contra `./replay --end HH:MM` en tests/test_regen_signals.py.
"""
import os

BAR_S = 60


class VClock:
    def __init__(self, sandbox, t0, t_end, bars_by_sym):
        """bars_by_sym: {sym_lower: [(ts,o,h,l,c,v), ...]} ORDENADO por ts, warm incluido."""
        if not sandbox:
            raise ValueError("vclock: sandbox vacio")
        self.sandbox = sandbox
        self.t = float(t0)
        self.t_end = float(t_end)
        self.bars = bars_by_sym
        self.cursor = {s: 0 for s in bars_by_sym}
        self.fh = {}
        d = os.path.join(sandbox, "data")
        os.makedirs(d, exist_ok=True)
        for s in bars_by_sym:
            p = os.path.join(d, "bars_%s_ibkr.txt" % s)
            # 'w': el sandbox arranca VACIO de barras (nunca heredamos un dia anterior)
            self.fh[s] = open(p, "w", buffering=1)
        self.materialize()

    def clock_path(self):
        return os.path.join(self.sandbox, "clock.txt")

    def materialize(self):
        """Añade al sandbox las barras CERRADAS en el instante virtual actual."""
        v = self.t
        for s, rows in self.bars.items():
            i = self.cursor[s]
            fh = self.fh[s]
            n = len(rows)
            while i < n and rows[i][0] + BAR_S <= v:
                ts, o, h, l, c, vol = rows[i]
                # mismo formato que ibkr_bar_bridge/replay: "EPOCH O H L C V"
                fh.write("%d %.4f %.4f %.4f %.4f %.0f\n" % (ts, o, h, l, c, vol))
                i += 1
            self.cursor[s] = i
        # reloj virtual visible desde fuera (paridad con replay: clock.txt en la raiz)
        tmp = self.clock_path() + ".tmp"
        with open(tmp, "w") as f:
            f.write("%.3f\n" % v)
        os.replace(tmp, self.clock_path())

    def advance(self, secs):
        if secs is None or secs < 0:
            raise ValueError("vclock.advance: segundos invalidos %r" % (secs,))
        self.t += float(secs)
        self.materialize()
        return self.t

    def close(self):
        for fh in self.fh.values():
            fh.close()
        self.fh = {}
