#!/usr/bin/env python3
"""nvda_options_engine.py — engine de opciones NVDA SEÑAL-SOLAMENTE (orden Yunior 2026-07-24).
Tiempo real: GEX + flip + muros + IMANES (gex_core) + PRESIÓN DE PARES medida (peer_influence)
+ STOP-LOSS. Doctrina + lecciones de hoy:
  - POS + se dirige a IMÁN oro + pares alineados -> CALL/PUT hacia el imán. Target=imán, stop=flip.
  - NEG todo-acelerador (sin oro) = WHIPSAW -> SIT OUT (lección 2026-07-24).
  - %B 1m extremo = timing corto; muro+rechazo IMPRESO para fadear (nunca en el aire).
  - imán con gamma DECAYENDO = fadeable; creciendo = pin fuerte.
Auto-consciente: relee niveles + presión de pares en cada tick. NUNCA ejecuta órdenes.

Modos:  python3 scripts/nvda_options_engine.py --live      (loop señal en vivo)
        python3 scripts/nvda_options_engine.py --backtest  (sobre poly_bars, 1 mes)
"""
import os, sys, time, math, sqlite3, statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO); sys.path.insert(0, os.path.join(REPO, "scripts"))
from ib_mode import get_port  # fuente unica: scripts/ib_mode.py (CLAUDE.md #7)
DB = os.path.join(REPO, "trades.db")
SYM = "NVDA"

# ---------- parámetros del engine (stop/target) ----------
STOP_PCT = 0.006     # stop del subyacente: 0.6% en contra (equivale a ~stop de premium)
TGT_FRAC_EM = 0.9    # target = imán, capado a 0.9·EM
PEER_MIN = 15        # |presión de pares| mínima para confirmar dirección

def _mom(c, n=6):
    return 100 * (c[-1] - c[-1 - n]) / c[-1 - n] if len(c) > n else 0
def _pb(c, n=20):
    if len(c) < n: return 0.5
    w = c[-n:]; m = st.mean(w); sd = st.pstdev(w); up = m + 2*sd; lo = m - 2*sd
    return (c[-1] - lo) / (up - lo) if up > lo else 0.5

# ================= TIEMPO REAL =================
def live_decide():
    import chart_levels, peer_influence, candles
    r = [l.split() for l in open(f"data/bars_{SYM.lower()}_ibkr.txt") if l.strip()]
    c1 = [float(x[4]) for x in r]; spot = c1[-1]
    lv = chart_levels.gen(SYM, spot=spot, write=False)
    if not lv: return None
    peer = peer_influence.load_weights(SYM)
    # presión de pares (momentum peer × peso)
    tot = 0.0; nrm = 0.0
    for w in peer[:12]:
        p = f"data/bars_{w['peer'].lower()}_ibkr.txt"
        if not os.path.exists(p): continue
        cc = [float(l.split()[4]) for l in open(p) if l.strip()]
        if len(cc) < 7: continue
        tot += _mom(cc) * w["weight"]; nrm += abs(w["weight"])
    peer_score = round(tot / (nrm or 1) * 100, 1)
    # imán oro dominante
    gold = [(pp["strike"], pp["gex"]) for pp in lv["profile"] if pp["gex"] > 0]
    mag = max(gold, key=lambda x: x[1])[0] if gold else None
    all_accel = not gold
    flip = lv["flip"]; reg = lv["regime"]; em = lv.get("em") or spot*0.02
    pb1 = _pb(c1); mom = _mom(c1)
    cand = candles.read(SYM, 1)["patterns"]
    d = dict(spot=spot, flip=flip, reg=reg, mag=mag, em=em, peer=peer_score,
             pb1=round(pb1,2), mom=round(mom,2), pressure=lv["pressure"],
             cw=lv["call_wall"], pw=lv["put_wall"], all_accel=all_accel,
             cand=[c["name"]+"["+c["bias"][0]+"]" for c in cand])
    # ---- lógica ----
    sig = None
    if all_accel or reg == "NEG":
        sig = ("SIT_OUT", "todo-acelerador/NEG = whipsaw, sin lado (lección 07-24)")
    elif mag and spot < flip * 1.0015 and spot > flip:   # POS, sobre flip
        # dirección al imán, confirmada por pares
        if mag > spot and peer_score > PEER_MIN:
            sig = ("BUY_CALL", f"POS -> imán {mag} arriba + pares +{peer_score}", mag, spot*(1-STOP_PCT))
        elif mag < spot and peer_score < -PEER_MIN:
            sig = ("BUY_PUT", f"POS -> imán {mag} abajo + pares {peer_score}", mag, spot*(1+STOP_PCT))
    if not sig and mag and reg == "POS":
        # pinned: dirección al imán dominante si pares confirman
        if mag > spot and peer_score > PEER_MIN:
            sig = ("BUY_CALL", f"pin -> imán {mag} + pares +{peer_score}", mag, spot*(1-STOP_PCT))
        elif mag < spot and peer_score < -PEER_MIN:
            sig = ("BUY_PUT", f"pin -> imán {mag} + pares {peer_score}", mag, spot*(1+STOP_PCT))
    d["signal"] = sig or ("NO_TRADE", "sin confluencia (imán+pares+régimen)")
    return d

# ================= BACKTEST (poly_bars) =================
def _load_bars_duck():
    import duckdb
    d = duckdb.connect(); d.execute("INSTALL sqlite; LOAD sqlite;")
    d.execute(f"CREATE TABLE pb AS SELECT sym,ts,o,h,l,c FROM sqlite_scan('{DB}','poly_bars')")
    return d

def backtest():
    """Honesto: sin GEX intradía histórico -> IMÁN = strike $2.5 más cercano (pin real 0DTE),
    RÉGIMEN = precio vs VWAP-sesión (proxy del flip), PRESIÓN DE PARES = SPY/QQQ medida.
    Mide el edge de 'ir al imán con pares alineados + stop' sobre 1 mes de precio real 1min.
    P&L en subyacente (proxy del direccional de la opción; la opción amplifica)."""
    import peer_influence
    d = _load_bars_duck()
    W = {w["peer"]: w["weight"] for w in peer_influence.load_weights(SYM)}
    rows = d.execute("SELECT ts,o,h,l,c FROM pb WHERE sym=? ORDER BY ts", [SYM]).fetchall()
    # cargar peers en memoria por ts para presión
    peers = ["SPY", "QQQ", "XLK", "SMH"]
    pmap = {}
    for p in peers:
        pmap[p] = {ts: c for ts, c in d.execute("SELECT ts,c FROM pb WHERE sym=? ORDER BY ts", [p]).fetchall()}
    d.close()
    import datetime
    ET = datetime.timezone(datetime.timedelta(hours=-4))
    # agrupar por día
    days = {}
    for ts,o,h,l,c in rows:
        dd = datetime.datetime.fromtimestamp(ts/1000, ET).date()
        days.setdefault(dd, []).append((ts,o,h,l,c))
    trades = []
    for dd, bars in days.items():
        if len(bars) < 40: continue
        closes = [b[4] for b in bars]
        vwap_acc = 0; vol = 0
        for i in range(30, len(bars)-15):
            ts,o,h,l,c = bars[i]
            win = closes[max(0,i-20):i+1]
            vwap = sum(win)/len(win)                    # proxy flip = SMA20
            mag = round(c/2.5)*2.5                       # imán = strike $2.5 más cercano
            if abs(mag - c) < 0.15 or abs(mag - c) > 2.0: continue   # ni encima ni lejos
            mom = 100*(c-closes[i-6])/closes[i-6]
            # presión de pares en este ts
            ps = 0.0; nn = 0.0
            for p in peers:
                pc = pmap[p]; pt = ts
                # peer return ~6min
                keys = [pt-k*60000 for k in range(6,0,-1)]
                if pt in pc and (pt-6*60000) in pc:
                    pm = 100*(pc[pt]-pc.get(pt-6*60000,pc[pt]))/pc.get(pt-6*60000,pc[pt])
                    ps += pm * W.get(p,0); nn += abs(W.get(p,0))
            peer_score = ps/(nn or 1)*100
            reg_pos = c > vwap
            # SEÑAL: POS + imán arriba + pares alcistas (o al revés)
            direction = 0
            if reg_pos and mag > c and peer_score > PEER_MIN and mom > 0.03: direction = 1
            elif (not reg_pos) and mag < c and peer_score < -PEER_MIN and mom < -0.03: direction = -1
            if direction == 0: continue
            # simular: target=imán, stop=STOP_PCT en contra, ventana 15min
            entry = c; tgt = mag; stop = entry*(1 - STOP_PCT*direction*-1) if False else entry*(1 - STOP_PCT) if direction>0 else entry*(1+STOP_PCT)
            stop = entry*(1-STOP_PCT) if direction>0 else entry*(1+STOP_PCT)
            out = None
            for j in range(i+1, min(i+16, len(bars))):
                hj, lj = bars[j][2], bars[j][3]
                if direction>0:
                    if lj <= stop: out=("stop", stop); break
                    if hj >= tgt:  out=("target", tgt); break
                else:
                    if hj >= stop: out=("stop", stop); break
                    if lj <= tgt:  out=("target", tgt); break
            if out is None: out=("time", bars[min(i+15,len(bars)-1)][4])
            ret = (out[1]-entry)/entry*100*direction
            trades.append((dd, direction, entry, out[0], round(ret,3), peer_score))
    # reporte
    if not trades:
        print("sin trades (proxy demasiado estricto)"); return
    wins = [t for t in trades if t[4] > 0]
    wr = 100*len(wins)/len(trades)
    avg = sum(t[4] for t in trades)/len(trades)
    tgt_hits = sum(1 for t in trades if t[3]=="target")
    stops = sum(1 for t in trades if t[3]=="stop")
    def wilson(k,n):
        p=k/n;z=1.96;dn=1+z*z/n;c=(p+z*z/(2*n))/dn;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/dn;return round(100*(c-h)),round(100*(c+h))
    lo,hi=wilson(len(wins),len(trades))
    print(f"\n=== BACKTEST NVDA OPTIONS ENGINE (1 mes, {len(trades)} trades) ===")
    print(f"  WR {wr:.0f}% [{lo},{hi}] | ret medio subyacente {avg:+.3f}%/trade | target {tgt_hits} stop {stops} time {len(trades)-tgt_hits-stops}")
    print(f"  (opción AMPLIFICA: un ±0.5% de subyacente 0DTE ~ ±15-40% de premium)")
    print(f"  CAVEAT HONESTO: imán=strike$2.5 (proxy, no GEX intradía histórico), flip=SMA20 proxy,")
    print(f"  pares=SPY/QQQ/XLK/SMH MEDIDOS. Mide el edge de la LÓGICA precio+pares+stop, no el GEX exacto.")
    # guardar
    c=sqlite3.connect(DB); c.execute("""CREATE TABLE IF NOT EXISTS engine_backtest(
        run_ts REAL, date TEXT, direction INTEGER, entry REAL, outcome TEXT, ret REAL, peer REAL)""")
    rt=time.time()
    for t in trades: c.execute("INSERT INTO engine_backtest VALUES(?,?,?,?,?,?,?)",(rt,str(t[0]),t[1],t[2],t[3],t[4],t[5]))
    c.commit(); c.close()

# ================= SHADOW (TWS vivo, papel, LOG — SIN operar) =================
def _assert_no_orders():
    import ast as _a
    banned = {"placeOrder","bracketOrder","marketOrder","limitOrder","stopOrder"}
    t=_a.parse(open(os.path.abspath(__file__)).read())
    hits={n.func.attr for n in _a.walk(t) if isinstance(n,_a.Call) and isinstance(n.func,_a.Attribute) and n.func.attr in banned}
    assert not hits, f"SEÑAL-SOLAMENTE VIOLADO: {hits}"

def _nearest_exp():
    p="data/opt_chain_nvda.txt"
    try:
        h=open(p).readline().split()
        exps=[h[i+1] for i in range(len(h)) if h[i]=="exps"][0] if "exps" in h else None
        # header trae 'exps YYYYMMDD YYYYMMDD'
        import datetime; today=datetime.date.today().strftime("%Y%m%d")
        cand=[x for x in h if x.isdigit() and len(x)==8 and x>=today]
        return min(cand) if cand else None
    except Exception: return None

def shadow(client_id=62):
    """Conecta TWS en vivo, opera en PAPEL sobre imanes (calls/puts), loguea a paper_trades.
    NUNCA envía órdenes. Precio de opción real via reqMktData; degradación limpia si falla."""
    _assert_no_orders()
    from ib_async import IB, Stock, Option
    import chart_levels, peer_influence
    c=sqlite3.connect(DB); c.execute("""CREATE TABLE IF NOT EXISTS paper_trades(
        ts_open REAL, ts_close REAL, side TEXT, strike REAL, exp TEXT, u_entry REAL, u_exit REAL,
        opt_entry REAL, opt_exit REAL, opt_pnl_pct REAL, u_pnl_pct REAL, reason TEXT, mag REAL, peer REAL)""")
    c.commit()
    ib=IB(); ib.connect("127.0.0.1",get_port(),clientId=client_id,readonly=True,timeout=15)
    ib.RequestTimeout = 15   # causa raiz 2026-07-28 (opt_whale_watch.py): sin esto, qualifyContracts cuelga para siempre si TWS no responde
    print(f"[shadow] TWS conectado clientId {client_id} — PAPEL, sin operar")
    stk=Stock("NVDA","SMART","USD"); ib.qualifyContracts(stk); tk=ib.reqMktData(stk,"",False,False)
    W={w["peer"]:w["weight"] for w in peer_influence.load_weights("NVDA")}
    pos=None; last_open=0
    def opt_mid(strike,right,exp):
        try:
            o=Option("NVDA",exp,strike,right,"SMART"); ib.qualifyContracts(o)
            t=ib.reqMktData(o,"",False,False); ib.sleep(1.5)
            m=t.marketPrice()
            return round(m,2) if m and m==m and m>0 else None
        except Exception: return None
    while True:
        ib.sleep(20)
        spot=tk.marketPrice()
        if not spot or spot!=spot or spot<=0: continue
        lv=chart_levels.gen("NVDA",spot=spot,write=False)
        if not lv or not lv.get("flip"): continue
        gold=[(p["strike"],p["gex"]) for p in lv["profile"] if p["gex"]>0]
        mag=max(gold,key=lambda x:x[1])[0] if gold else None
        em=lv.get("em") or spot*0.02; flip=lv["flip"]; reg=lv["regime"]
        # presión de pares
        tot=nn=0.0
        for pr,wt in W.items():
            f=f"data/bars_{pr.lower()}_ibkr.txt"
            if not os.path.exists(f): continue
            cc=[float(l.split()[4]) for l in open(f) if l.strip()]
            if len(cc)>7: tot+=(100*(cc[-1]-cc[-7])/cc[-7])*wt; nn+=abs(wt)
        peer=round(tot/(nn or 1)*100,1)
        # ---- gestión de posición abierta (VENDER) ----
        if pos:
            hit=None
            if pos["side"]=="CALL":
                if spot>=pos["target"]: hit="target"
                elif spot<=pos["stop"]: hit="stop"
            else:
                if spot<=pos["target"]: hit="target"
                elif spot>=pos["stop"]: hit="stop"
            if not hit and time.time()-pos["ts"]>3600: hit="time"   # 60min máx
            if hit:
                oe=opt_mid(pos["strike"],pos["right"],pos["exp"]) or pos["opt_entry"]
                upnl=(spot-pos["u_entry"])/pos["u_entry"]*100*(1 if pos["side"]=="CALL" else -1)
                opnl=(oe-pos["opt_entry"])/pos["opt_entry"]*100 if pos["opt_entry"] else 0
                c.execute("INSERT INTO paper_trades VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pos["ts"],time.time(),pos["side"],pos["strike"],pos["exp"],pos["u_entry"],spot,
                     pos["opt_entry"],oe,round(opnl,1),round(upnl,2),hit,pos["mag"],pos["peer"]))
                c.commit()
                print(f"[shadow] CIERRA {pos['side']} {pos['strike']} {hit}: opt {opnl:+.0f}% (subyacente {upnl:+.2f}%)")
                pos=None
            continue
        # ---- buscar oportunidad JUGOSA (COMPRAR) ----
        if time.time()-last_open<120: continue
        if not mag or not gold: continue        # NEG todo-acelerador -> no
        if reg!="POS": continue
        dist=abs(mag-spot); stopd=spot*STOP_PCT
        if dist<0.1 or dist>1.5*em: continue     # ni encima ni lejos
        rr=dist/stopd
        side=right=None
        if mag>spot and peer>PEER_MIN: side,right="CALL","C"
        elif mag<spot and peer<-PEER_MIN: side,right="PUT","P"
        if not side or rr<1.2: continue           # JUICE: R:R>=1.2 + pares confirman
        exp=_nearest_exp()
        if not exp: continue
        strike=round(spot/2.5)*2.5 if abs(round(spot/2.5)*2.5-spot)<1.3 else round(mag/2.5)*2.5
        oe=opt_mid(strike,right,exp)
        if not oe or oe>2.0*100: continue         # premium sano (<=$200, regla casa)
        pos=dict(side=side,right=right,strike=strike,exp=exp,u_entry=spot,opt_entry=oe,
                 target=mag,stop=spot*(1-STOP_PCT) if side=="CALL" else spot*(1+STOP_PCT),
                 ts=time.time(),mag=mag,peer=peer); last_open=time.time()
        print(f"[shadow] ABRE {side} {strike} exp {exp} @ opt ${oe} | u {spot} -> imán {mag} R:R {rr:.1f} pares {peer:+}")

def main():
    if "--shadow" in sys.argv:
        i=sys.argv.index("--client")+1 if "--client" in sys.argv else None
        shadow(int(sys.argv[i]) if i else 62)
    elif "--backtest" in sys.argv:
        backtest()
    elif "--live" in sys.argv:
        while True:
            d = live_decide()
            if d:
                s = d["signal"]
                print(f"{time.strftime('%H:%M:%S')} NVDA {d['spot']} {d['reg']} imán {d['mag']} pares {d['peer']:+} %B {d['pb1']} | {s[0]}: {s[1]}")
            time.sleep(30)
    else:
        d = live_decide()
        if d:
            import json; print(json.dumps(d, indent=1, default=str))

if __name__ == "__main__":
    main()
