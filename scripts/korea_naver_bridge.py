#!/usr/bin/env python3
"""korea_naver_bridge.py — respaldo de barras KRX cuando IB Gateway no esta.

MOTIVO (2026-08-03 09:0x KST, medido): el Gateway llevaba caido y `korea_bar_bridge`
acumulo 126 reintentos gritando "ningun puerto IBKR escucha" mientras KRX estaba ABIERTO
y cayendo -8%. Un indicador LIDER mudo justo el dia que lidera no vale nada.

FUENTE: polling.finance.naver.com/api/realtime/domestic/stock/<codigos>. Medido con los 10
simbolos de `data/korea_contracts.txt`: `delayTime: 0`, `marketStatus: OPEN`, `localTradedAt`
con reloj de Seul. Es precio REAL, no diferido — pero NO trae libro (bid/ask): el endpoint
`askingPrice` responde 404. Por eso este puente NO escribe `data/nbbo_<name>.txt`: un
`bid=ask=last` daria spread 0,00% y colaria el gate de los bots (regla de la casa: prohibido
el cero plausible). Los bots quedan fail-closed en el confirm de compra, que es lo correcto.

IBKR MANDA. Si un puerto de Gateway escucha, este puente se aparta: IBKR es tiempo real con
libro y es la fuente de disparo. Este solo cubre el hueco.

Escribe (mismo contrato que korea_bar_bridge, para que los bots C++ no cambien):
  data/bars_<name>.txt     "EPOCH O H L C V"  (1m, agregado de los sondeos)
  data/korea_source.json   procedencia declarada (fuente, retraso, nbbo, ultimo sondeo)

Uso: korea_naver_bridge.py [--once] [--poll 3.0]
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

URL = "https://polling.finance.naver.com/api/realtime/domestic/stock/{codes}"
HDRS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}
GATEWAY_PORTS = (4001, 4002)
POLL_S = float(os.environ.get("KOREA_NAVER_POLL_S", "3.0"))
IDLE_S = 60.0            # mercado cerrado: sondeo lento, solo para ver cuando abre
FAILS_LOUD = 5           # 5 fallos seguidos con KRX abierto = voz, nunca silencio
SRC_FILE = os.path.join(ROOT, "data", "korea_source.json")


def contratos():
    """NAME -> codigo KRX desde data/korea_contracts.txt (fuente unica, jamas hardcodeado)."""
    path = os.path.join(ROOT, "data", "korea_contracts.txt")
    out = {}
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) >= 3:
                out[p[0].lower()] = p[2]
    if not out:
        raise RuntimeError(f"{path} vacio: sin universo coreano no hay puente")
    return out


def gateway_vivo():
    for p in GATEWAY_PORTS:
        s = socket.socket()
        s.settimeout(0.4)
        try:
            s.connect(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return None


def _num(txt):
    """'1,589,000' -> 1589000.0. None si no es un numero (jamas 0: un 0 es un precio)."""
    if txt is None:
        return None
    t = str(txt).replace(",", "").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return v


def sondeo(codes):
    """Lista de dicts crudos de Naver. Levanta si la red o el JSON fallan (fail-loud)."""
    req = urllib.request.Request(URL.format(codes=",".join(codes)), headers=HDRS)
    with urllib.request.urlopen(req, timeout=10) as r:
        payload = json.loads(r.read().decode())
    datas = payload.get("datas")
    if not datas:
        raise RuntimeError("Naver respondio sin 'datas'")
    return datas


def epoch_de(row):
    """Reloj de BOLSA (localTradedAt, KST con offset). Nunca la hora de llegada: marcar con
    hora local un dato retrasado lo disfrazaria de vivo."""
    ts = row.get("localTradedAt")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return None


class Agg:
    """Agrega sondeos en barras de 1 minuto por simbolo."""

    def __init__(self, name):
        self.name = name
        self.minuto = None
        self.o = self.h = self.l = self.c = None
        self.vol_ini = None        # volumen acumulado del dia al abrir la barra
        self.vol_last = None
        self.last_emitted = self._ultimo_epoch()

    def _ultimo_epoch(self):
        try:
            with open(f"data/bars_{self.name}.txt") as f:
                ult = None
                for ln in f:
                    if ln.strip():
                        ult = ln
            return float(ult.split()[0]) if ult else 0.0
        except (OSError, ValueError, IndexError):
            return 0.0

    def tick(self, ep, price, vol_acum):
        """Devuelve la barra cerrada (str) si este tick abre un minuto nuevo, o None."""
        m = ep - ep % 60
        cerrada = None
        if self.minuto is not None and m > self.minuto:
            cerrada = self._cerrar()
        if self.minuto is None or m > self.minuto:
            self.minuto = m
            self.o = self.h = self.l = self.c = price
            self.vol_ini = vol_acum
            self.vol_last = vol_acum
        elif m == self.minuto:
            self.h = max(self.h, price)
            self.l = min(self.l, price)
            self.c = price
            if vol_acum is not None:
                if self.vol_ini is None or vol_acum < self.vol_ini:
                    self.vol_ini = vol_acum      # rollover de dia: el acumulado se reinicia
                self.vol_last = vol_acum
        return cerrada

    def _cerrar(self):
        if self.minuto is None or self.c is None or self.c <= 0:
            return None
        if self.minuto <= self.last_emitted:
            return None
        v = 0.0
        if self.vol_last is not None and self.vol_ini is not None:
            v = max(0.0, self.vol_last - self.vol_ini)
        self.last_emitted = self.minuto
        return (f"{self.minuto:.0f} {self.o:.4f} {self.h:.4f} "
                f"{self.l:.4f} {self.c:.4f} {v:.0f}\n")


def escribe_procedencia(estado):
    tmp = SRC_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SRC_FILE)


def grita(msg):
    print(msg, file=sys.stderr, flush=True)
    try:
        subprocess.Popen(["/bin/bash", os.path.join(ROOT, "scripts", "speak.sh"), "DANGER", msg],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def main():
    once = "--once" in sys.argv
    if "--poll" in sys.argv:
        globals()["POLL_S"] = float(sys.argv[sys.argv.index("--poll") + 1])
    mapa = contratos()                       # name -> codigo
    por_codigo = {c: n for n, c in mapa.items()}
    aggs = {n: Agg(n) for n in mapa}
    fallos = 0
    print(f"[korea-naver] {len(mapa)} simbolos, sondeo {POLL_S}s: {' '.join(sorted(mapa))}",
          flush=True)

    while True:
        gw = gateway_vivo()
        if gw:
            # IBKR manda: tiene libro y es la fuente de disparo. Este puente se aparta.
            escribe_procedencia({"fuente": "ibkr", "motivo": f"Gateway vivo en {gw}",
                                 "ts": int(time.time())})
            print(f"[korea-naver] Gateway vivo en {gw} — me aparto (IBKR es la fuente)",
                  flush=True)
            if once:
                return 0
            time.sleep(30)
            continue

        try:
            filas = sondeo(list(mapa.values()))
            fallos = 0
        except (urllib.error.URLError, OSError, ValueError, RuntimeError) as e:
            fallos += 1
            print(f"[korea-naver] sondeo fallo ({fallos}): {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            if fallos == FAILS_LOUD:
                grita(f"Puente Corea de respaldo caido: {fallos} sondeos fallidos seguidos.")
            if once:
                return 1
            time.sleep(POLL_S * 2)
            continue

        abierto = False
        escritas = 0
        for row in filas:
            name = por_codigo.get(str(row.get("itemCode")))
            if name is None:
                continue
            if str(row.get("marketStatus")) == "OPEN":
                abierto = True
            price = _num(row.get("closePrice"))
            ep = epoch_de(row)
            if price is None or price <= 0 or ep is None:
                continue        # sin precio o sin reloj de bolsa no se inventa nada
            vol = _num(row.get("accumulatedTradingVolume"))
            linea = aggs[name].tick(ep, price, vol)
            if linea:
                with open(f"data/bars_{name}.txt", "a") as f:
                    f.write(linea)
                escritas += 1

        escribe_procedencia({
            "fuente": "naver_polling",
            "delay_declarado_s": 0,
            "nbbo": None,
            "nbbo_motivo": "Naver no publica libro (askingPrice -> 404): no se escribe nbbo_*",
            "simbolos": sorted(mapa),
            "ultimo_sondeo": int(time.time()),
            "mercado_abierto": abierto,
            "barras_cerradas_este_ciclo": escritas,
        })
        if escritas:
            print(f"[korea-naver] {time.strftime('%H:%M:%S')} {escritas} barras cerradas",
                  flush=True)
        if once:
            return 0
        time.sleep(POLL_S if abierto else IDLE_S)


if __name__ == "__main__":
    raise SystemExit(main())
