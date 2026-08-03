#!/usr/bin/env python3
"""korea_naver_bridge.py — respaldo de barras KRX cuando IB Gateway no esta.

MOTIVO (2026-08-03 09:0x KST, medido): el Gateway llevaba caido y `korea_bar_bridge`
acumulo 126 reintentos gritando "ningun puerto IBKR escucha" mientras KRX estaba ABIERTO
y cayendo -8%. Un indicador LIDER mudo justo el dia que lidera no vale nada.

FUENTE: polling.finance.naver.com/api/realtime/domestic/{index|stock}/<codigos>. Medido:
`delayTime: 0`, `marketStatus`, `localTradedAt` con reloj de Seul. Es precio REAL, no diferido
— pero NO trae libro (bid/ask): el endpoint `askingPrice` responde 404. Por eso este puente NO
escribe `data/nbbo_<name>.txt`: un `bid=ask=last` daria spread 0,00% y colaria el gate de los
bots (regla de la casa: prohibido el cero plausible). Los bots quedan fail-closed en el confirm
de compra, que es lo correcto.

INDICE != ETF (medido 2026-08-03, cierre KRX): KODEX 200 (ETF 069500) -8,93% contra KOSPI
-5,12% y KOSPI 200 -5,74%. Durante meses `kospi` fue el ETF y exageraba el indice 1,8x. Ahora
`kospi`/`kospi200` son los INDICES y el ETF vive aparte como `kodex200`. El tipo de endpoint
es DATO (`data/korea_endpoints.txt`), no una lista dentro de este fichero.

CIERRE DE SUBASTA: al cerrar KRX `localTradedAt` se congela en 15:30 y ya no llega ningun
minuto nuevo -> la barra del cierre no se escribia JAMAS (medido: fichero 98.625 contra cierre
oficial 99.105, medio punto porcentual inventado). `Agg.cierre_oficial` la vuelca una vez,
idempotente contra reinicios, y persiste el cierre OFICIAL en data/korea_prevclose.json.

IBKR MANDA. Si un puerto de Gateway escucha, este puente se aparta: IBKR es tiempo real con
libro y es la fuente de disparo. Este solo cubre el hueco.

Escribe (mismo contrato que korea_bar_bridge, para que los bots C++ no cambien):
  data/bars_<name>.txt        "EPOCH O H L C V"  (1m, agregado de los sondeos)
  data/korea_prevclose.json   cierre OFICIAL de la sesion KRX anterior (oficial=true)
  data/korea_source.json      procedencia declarada (fuente, retraso, nbbo, ultimo sondeo)

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
import overnight_feed as ovf  # noqa: E402   calendario KRX (festivos/sesion previa): 1 definicion

URL = "https://polling.finance.naver.com/api/realtime/domestic/{tipo}/{codes}"
HDRS = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}
GATEWAY_PORTS = (4001, 4002)
POLL_S = float(os.environ.get("KOREA_NAVER_POLL_S", "3.0"))
IDLE_S = 60.0            # mercado cerrado: sondeo lento, solo para ver cuando abre
FAILS_LOUD = 5           # 5 fallos seguidos con KRX abierto = voz, nunca silencio
SRC_FILE = os.path.join(ROOT, "data", "korea_source.json")
PREVCLOSE_FILE = os.path.join(ROOT, "data", ovf.PREVCLOSE_NAME)
TIPOS_OK = ("index", "stock")


def _filas_fichero(path):
    try:
        with open(path) as f:
            for ln in f:
                ln = ln.split("#")[0].split()
                if len(ln) >= 3:
                    yield ln
    except OSError:
        return


def universo():
    """NAME -> (tipo_endpoint, codigo). `data/korea_endpoints.txt` declara el TIPO y manda;
    lo que solo esta en `korea_contracts.txt` entra como accion (asi un satelite nuevo del
    puente IBKR no queda mudo aqui). Jamas una lista hardcodeada en este fichero."""
    ends = os.path.join(ROOT, "data", "korea_endpoints.txt")
    out = {}
    for p in _filas_fichero(ends):
        if p[1].lower() not in TIPOS_OK:
            raise RuntimeError(f"{ends}: tipo '{p[1]}' desconocido (index|stock)")
        out[p[0].lower()] = (p[1].lower(), p[2])
    for p in _filas_fichero(os.path.join(ROOT, "data", "korea_contracts.txt")):
        out.setdefault(p[0].lower(), ("stock", p[2]))
    if not out:
        raise RuntimeError(f"{ends} y korea_contracts.txt vacios: sin universo no hay puente")
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
    """'1,589,000' -> 1589000.0; '6,257.45' -> 6257.45 (los indices traen coma de miles Y punto
    decimal). None si no es un numero (jamas 0: un 0 es un precio)."""
    if txt is None:
        return None
    t = str(txt).replace(",", "").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return v


def campo(row, k):
    """Numero de `k` prefiriendo el campo `<k>Raw`: en indices `accumulatedTradingVolume` viene
    como '272,959천주' (miles de acciones) y solo el Raw es un numero."""
    v = _num(row.get(k + "Raw"))
    return v if v is not None else _num(row.get(k))


def sondeo(por_tipo):
    """Lista de dicts crudos de Naver, un GET por tipo de endpoint. Levanta si red/JSON fallan."""
    filas = []
    for tipo in sorted(por_tipo):
        codes = por_tipo[tipo]
        if not codes:
            continue
        req = urllib.request.Request(URL.format(tipo=tipo, codes=",".join(codes)), headers=HDRS)
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = json.loads(r.read().decode())
        datas = payload.get("datas")
        if not datas:
            raise RuntimeError(f"Naver respondio sin 'datas' en /{tipo}")
        filas.extend(datas)
    return filas


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


def epoch_cierre(row):
    """Epoch de la subasta de cierre = fecha de localTradedAt + `endTime` del propio payload.
    No se usa localTradedAt directo: en los INDICES sigue avanzando tras el cierre (medido
    18:59 con KRX cerrado a las 15:30) y fabricaria barras de una sesion que no existe."""
    ts = row.get("localTradedAt")
    fin = str((row.get("stockExchangeType") or {}).get("endTime") or "")
    if not ts or len(fin) != 4 or not fin.isdigit():
        return None
    try:
        d = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return d.replace(hour=int(fin[:2]), minute=int(fin[2:]),
                     second=0, microsecond=0).timestamp()


def sesion_anterior(ep_cierre, row):
    """(fecha_ISO, epoch) del cierre de la sesion KRX ANTERIOR a la que cerro en `ep_cierre`.
    Calendario (fin de semana + festivos) de overnight_feed: una sola definicion en el repo.
    None si `ep_cierre` cae en un dia sin sesion (la fuente esta rellenando, no se persiste)."""
    fin = str((row.get("stockExchangeType") or {}).get("endTime") or "")
    if len(fin) != 4 or not fin.isdigit():
        return None
    d = datetime.fromtimestamp(ep_cierre, ovf.KST)
    if d.weekday() >= 5 or d.date().isoformat() in ovf.krx_holidays():
        return None
    b = d.replace(hour=ovf.KRX_OPEN_H, minute=ovf.KRX_OPEN_M,
                  second=0, microsecond=0).timestamp()
    ses = ovf.prev_krx_session_date(b)
    ep = datetime.fromisoformat(f"{ses}T{fin[:2]}:{fin[2:]}:00").replace(
        tzinfo=ovf.KST).timestamp()
    return ses, ep


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

    def cierre_oficial(self, ep_cierre, price, vol_acum):
        """Lista de barras a escribir al cerrar KRX. La subasta de cierre nunca abre un minuto
        NUEVO (localTradedAt se congela en 15:30), asi que sin este volcado la barra del cierre
        oficial no se escribe jamas. IDEMPOTENTE: `last_emitted` (releido del fichero al
        arrancar) impide reescribirla en los ~1000 sondeos que quedan con el mercado cerrado."""
        m = ep_cierre - ep_cierre % 60
        if m <= self.last_emitted:
            return []
        salida = []
        previa = self.tick(ep_cierre, price, vol_acum)
        if previa:
            salida.append(previa)
        fin = self._cerrar()
        if fin:
            salida.append(fin)
        return salida

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


def prevclose_oficial(row):
    """(close, epoch, sesion) del cierre OFICIAL de la sesion KRX anterior, tal como lo publica
    la fuente: closePrice - compareToPreviousClosePrice. Jamas inferido de la ultima barra
    intradia (el 2026-08-03 daba 108.900 contra 108.820 reales del KODEX). None si falta algo."""
    c, delta = campo(row, "closePrice"), campo(row, "compareToPreviousClosePrice")
    if c is None or c <= 0 or delta is None:
        return None
    prev = c - delta
    if prev <= 0:
        return None
    ep_c = epoch_cierre(row)
    if ep_c is None:
        return None
    ses = sesion_anterior(ep_c, row)
    if ses is None:
        return None
    return prev, ses[1], ses[0]


def persistir_prevclose(entradas, path=None):
    """data/korea_prevclose.json con el cierre OFICIAL (mismo esquema que
    korea_bar_bridge.update_prev_close + `oficial: true`). Atomico y monotono: nunca retrocede
    a una sesion mas vieja ni pisa las entradas de otros nombres."""
    p = path or PREVCLOSE_FILE
    try:
        with open(p) as f:
            cur = json.load(f)
        if not isinstance(cur, dict):
            cur = {}
    except (OSError, ValueError):
        cur = {}
    cambios = 0
    for name, (close, ep, ses) in entradas.items():
        old = cur.get(name)
        if isinstance(old, dict) and float(old.get("epoch") or 0) >= ep:
            continue
        cur[name] = {"close": round(float(close), 4), "epoch": int(ep),
                     "session": ses, "oficial": True}
        cambios += 1
    if not cambios:
        return 0
    tmp = p + f".tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(cur, f)
    os.replace(tmp, p)
    return cambios


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
    mapa = universo()                        # name -> (tipo, codigo)
    por_codigo = {c.upper(): n for n, (_t, c) in mapa.items()}
    por_tipo = {}
    for _n, (t, c) in mapa.items():
        por_tipo.setdefault(t, []).append(c)
    aggs = {n: Agg(n) for n in mapa}
    fallos = 0
    print(f"[korea-naver] {len(mapa)} simbolos, sondeo {POLL_S}s: "
          + " ".join(f"{n}/{t}" for n, (t, _c) in sorted(mapa.items())), flush=True)

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
            filas = sondeo(por_tipo)
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
        cierres = 0
        prevcloses = {}
        ahora = time.time()
        for row in filas:
            name = por_codigo.get(str(row.get("itemCode")).upper())
            if name is None:
                continue
            en_curso = str(row.get("marketStatus")) == "OPEN"
            abierto = abierto or en_curso
            price = campo(row, "closePrice")
            if price is None or price <= 0:
                continue        # sin precio no se inventa nada
            vol = campo(row, "accumulatedTradingVolume")
            if en_curso:
                ep = epoch_de(row)
                if ep is None:
                    continue    # sin reloj de bolsa la barra iria con hora de llegada
                lineas = [l for l in (aggs[name].tick(ep, price, vol),) if l]
            else:
                ep_c = epoch_cierre(row)
                if ep_c is None or ep_c > ahora + 60:
                    continue    # cierre en el futuro = la fuente aun no tiene la sesion
                lineas = aggs[name].cierre_oficial(ep_c, price, vol)
                cierres += len(lineas)
                pc = prevclose_oficial(row)
                if pc:
                    prevcloses[name] = pc
            if lineas:
                with open(f"data/bars_{name}.txt", "a") as f:
                    f.writelines(lineas)
                escritas += len(lineas)

        persistidos = persistir_prevclose(prevcloses) if prevcloses else 0

        escribe_procedencia({
            "fuente": "naver_polling",
            "delay_declarado_s": 0,
            "nbbo": None,
            "nbbo_motivo": "Naver no publica libro (askingPrice -> 404): no se escribe nbbo_*",
            "simbolos": sorted(mapa),
            "tipos": {n: t for n, (t, _c) in sorted(mapa.items())},
            "ultimo_sondeo": int(time.time()),
            "mercado_abierto": abierto,
            "barras_cerradas_este_ciclo": escritas,
            "barras_de_subasta_este_ciclo": cierres,
            "prevclose_oficiales_persistidos": persistidos,
        })
        if escritas or persistidos:
            print(f"[korea-naver] {time.strftime('%H:%M:%S')} {escritas} barras "
                  f"({cierres} de subasta), {persistidos} prev_close oficiales", flush=True)
        if once:
            return 0
        time.sleep(POLL_S if abierto else IDLE_S)


if __name__ == "__main__":
    raise SystemExit(main())
