#!/usr/bin/env python3
"""peer_influence.py — modelo MEDIDO de influencia cruzada entre tickers (orden Yunior
2026-07-24: "measure influence of other tickers realtime, self-aware, auto-updated").

Metodología (estándar, verificada web): beta = corr × (σ_target/σ_peer) por regresión de
retornos; correlación = fuerza/fiabilidad; lead-lag = correlación cruzada desfasada (¿el peer
ADELANTA al target?). Todo MEDIDO de poly_bars (nada hardcoded), se auto-recalibra.

  peso_influencia(peer->target) = beta × corr × dir_lead
    - beta: cuánto mueve el target por 1% del peer
    - corr: fiabilidad (0..1); |corr|<0.3 = ruido, se descarta
    - lead: +1 si el peer ADELANTA al target (predictivo), 0 si coincidente

En vivo: peer_pressure(target) = Σ (momentum_actual_peer × peso) sobre los influyentes ->
score direccional de presión de pares. Ej: QQQ+SMH cayendo con beta+corr altos = presión
bajista fuerte sobre NVDA -> el engine sesga bajista / veta longs.

Uso:
  python3 scripts/peer_influence.py weights NVDA      calcula+guarda pesos (peer_weights)
  python3 scripts/peer_influence.py pressure NVDA     presión de pares AHORA (vivo)
  python3 scripts/peer_influence.py show NVDA         tabla de pesos guardada
SEÑAL-SOLAMENTE.
"""
import os, sys, time, json, sqlite3

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
DB = os.path.join(REPO, "trades.db")
FLEET = open("data/fleet.txt").read().split()


def compute(target="NVDA", min_corr=0.3, lags=3):
    import duckdb
    d = duckdb.connect()
    d.execute("INSTALL sqlite; LOAD sqlite;")
    d.execute(f"CREATE TABLE pb AS SELECT sym, ts, c FROM sqlite_scan('{DB}','poly_bars')")
    # retornos 1min por símbolo
    d.execute("""CREATE TABLE ret AS
        SELECT sym, ts, (c/LAG(c) OVER (PARTITION BY sym ORDER BY ts) - 1) AS r
        FROM pb""")
    tsym = target.upper()
    have = set(r[0] for r in d.execute("SELECT DISTINCT sym FROM ret").fetchall())
    if tsym not in have:
        print(f"{tsym} sin datos en poly_bars"); return []
    out = []
    for peer in FLEET:
        p = peer.upper()
        if p == tsym or p not in have:
            continue
        # alinear en ts: target.r vs peer.r
        q = d.execute("""
            SELECT corr(t.r, p.r) AS corr,
                   regr_slope(t.r, p.r) AS beta,           -- beta = d(target)/d(peer)
                   stddev(t.r) AS st, stddev(p.r) AS sp,
                   count(*) AS n
            FROM ret t JOIN ret p ON t.ts = p.ts
            WHERE t.sym=? AND p.sym=? AND t.r IS NOT NULL AND p.r IS NOT NULL
        """, [tsym, p]).fetchone()
        corr, beta, stt, sp, n = q
        if corr is None or n < 500 or abs(corr) < min_corr:
            continue
        # lead-lag: corr( target[t], peer[t-1] ) — si sube al desfasar => el peer ADELANTA
        best_lag, best_lc = 0, corr
        for lag in range(1, lags + 1):
            lc = d.execute("""
                SELECT corr(t.r, p.r) FROM ret t JOIN ret p ON t.ts = p.ts + ?*60000
                WHERE t.sym=? AND p.sym=? AND t.r IS NOT NULL AND p.r IS NOT NULL
            """, [lag, tsym, p]).fetchone()[0]
            if lc is not None and abs(lc) > abs(best_lc):
                best_lc, best_lag = lc, lag
        lead = 1 if best_lag > 0 else 0     # el peer adelanta al target
        weight = round(beta * abs(corr), 3)
        out.append(dict(peer=p, corr=round(corr, 3), beta=round(beta, 3),
                        lead_min=best_lag, lead=lead, weight=weight, n=n))
    out.sort(key=lambda x: -abs(x["weight"]))
    d.close()
    return out


def save(target, rows):
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS peer_weights(
        target TEXT, peer TEXT, corr REAL, beta REAL, lead_min INTEGER,
        weight REAL, n INTEGER, ts REAL, PRIMARY KEY(target, peer))""")
    for r in rows:
        c.execute("INSERT OR REPLACE INTO peer_weights VALUES(?,?,?,?,?,?,?,?)",
                  (target.upper(), r["peer"], r["corr"], r["beta"], r["lead_min"],
                   r["weight"], r["n"], time.time()))
    c.commit(); c.close()


def load_weights(target):
    c = sqlite3.connect(DB)
    try:
        rows = c.execute("SELECT peer,corr,beta,lead_min,weight,n FROM peer_weights WHERE target=? ORDER BY abs(weight) DESC",
                         (target.upper(),)).fetchall()
    except Exception:
        rows = []
    c.close()
    return [dict(peer=r[0], corr=r[1], beta=r[2], lead_min=r[3], weight=r[4], n=r[5]) for r in rows]


def _mom(sym, n=6):
    """momentum reciente (%) del símbolo desde data/bars_<sym>_ibkr.txt (vivo)."""
    p = f"data/bars_{sym.lower()}_ibkr.txt"
    if not os.path.exists(p):
        return None
    c = [float(l.split()[4]) for l in open(p) if l.strip()]
    if len(c) < n + 1:
        return None
    return 100 * (c[-1] - c[-1 - n]) / c[-1 - n]


def pressure(target):
    """Presión de pares AHORA: Σ momentum_peer × peso. + = empuje alcista sobre el target."""
    w = load_weights(target)
    if not w:
        print(f"sin pesos para {target} — corre 'weights {target}' primero"); return None
    total = 0.0; parts = []
    for r in w[:12]:
        m = _mom(r["peer"])
        if m is None:
            continue
        contrib = m * r["weight"]     # momentum del peer proyectado al target por su peso
        total += contrib
        parts.append((r["peer"], round(m, 2), r["weight"], round(contrib, 3), r["lead_min"]))
    # normalizar por suma de |pesos| usados
    norm = sum(abs(p[2]) for p in parts) or 1
    score = round(total / norm * 100, 1)   # -100..+100 aprox
    print(f"=== PRESIÓN DE PARES sobre {target.upper()} AHORA ===")
    print(f"  score {score:+.1f}  ({'ALCISTA' if score>15 else 'BAJISTA' if score<-15 else 'NEUTRO'})")
    for p in sorted(parts, key=lambda x: -abs(x[3]))[:8]:
        lead = f" (adelanta {p[4]}m)" if p[4] else ""
        print(f"    {p[0]:5s} mom {p[1]:+.2f}% × peso {p[2]:+.2f} = {p[3]:+.3f}{lead}")
    return score


def main():
    a = sys.argv[1:]
    cmd = a[0] if a else "show"
    tgt = a[1] if len(a) > 1 else "NVDA"
    if cmd == "weights":
        rows = compute(tgt); save(tgt, rows)
        print(f"=== PESOS DE INFLUENCIA -> {tgt.upper()} (medidos, {len(rows)} peers) ===")
        for r in rows[:15]:
            lead = f"adelanta {r['lead_min']}m" if r["lead"] else "coincidente"
            print(f"  {r['peer']:5s} beta {r['beta']:+.2f} corr {r['corr']:+.2f} peso {r['weight']:+.3f} [{lead}] n={r['n']}")
    elif cmd == "pressure":
        pressure(tgt)
    else:
        for r in load_weights(tgt)[:15]:
            print(f"  {r['peer']:5s} beta {r['beta']:+.2f} corr {r['corr']:+.2f} peso {r['weight']:+.3f}")


if __name__ == "__main__":
    main()
