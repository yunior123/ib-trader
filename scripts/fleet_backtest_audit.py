#!/usr/bin/env python3
"""Full-fleet C++ signal bot backtest + bag/stop audit (2026-07-11).

Uses the live keepalive env for each ticker (production params), feeds real
Alpaca IEX 1m bars via --stdin, and reports:
  closed longs/shorts: n, WR, total%, PF, avg win/loss
  open bags at end of series (unrealized)
  stop-hit rate, EOD rate, trail/target mix
  train vs OOS split (first 60% / last 40% by time)

Usage:
  venv/bin/python scripts/fleet_backtest_audit.py fetch 180
  venv/bin/python scripts/fleet_backtest_audit.py run
  venv/bin/python scripts/fleet_backtest_audit.py all 180
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "topgainer"))

SYMS = [
    "DRAM", "NOK", "SPCX", "TSLA", "NVDA", "TXN", "TSM",
    "AMD", "INTC", "ASML", "AAPL", "GLD", "QQQ",
]


def load_keepalive_env(sym: str) -> dict:
    """Parse export FOO=bar from scripts/<sym>_keepalive.sh (ignore comments/while)."""
    path = os.path.join(ROOT, "scripts", f"{sym.lower()}_keepalive.sh")
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith("export "):
                continue
            # export FOO=bar or export FOO="bar"
            body = line[len("export "):]
            if "=" not in body:
                continue
            k, v = body.split("=", 1)
            v = v.strip().strip("'").strip('"')
            # drop trailing comments
            if " #" in v:
                v = v.split(" #", 1)[0].strip()
            env[k.strip()] = v
    return env


def fetch_one(sym: str, days: int) -> str:
    from price import _load_alpaca_keys  # noqa: E402
    import json
    import urllib.request
    from datetime import timedelta

    key, sec = _load_alpaca_keys()
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    bars, tok = [], None
    while True:
        url = (
            f"https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Min"
            f"&feed=iex&limit=10000&start={start}"
            + (f"&page_token={tok}" if tok else "")
        )
        req = urllib.request.Request(
            url,
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        bars += d.get("bars") or []
        tok = d.get("next_page_token")
        if not tok:
            break
        time.sleep(0.25)
    out = os.path.join(ROOT, "data", f"bt_{sym.lower()}.txt")
    with open(out, "w") as f:
        for b in bars:
            ep = int(
                datetime.strptime(b["t"][:19], "%Y-%m-%dT%H:%M:%S")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
            f.write(f"{ep} {b['o']} {b['h']} {b['l']} {b['c']} {b['v']}\n")
    print(f"{sym}: {len(bars)} bars -> {out}")
    return out


def parse_run(stdout: str):
    """Parse COMPRAR/VENDER/SHORT/CUBRIR + reasons. Track open bags."""
    longs, shorts = [], []  # list of dicts
    open_long = None
    open_short = None
    reasons = defaultdict(int)

    # also capture epoch from bar lines if present (not always)
    for line in stdout.splitlines():
        m = re.search(
            r"\[(\d{2}):(\d{2})\] \*\*\* \w+: COMPRAR \*\*\* ~([\d.]+)", line
        )
        if m:
            open_long = {
                "entry": float(m.group(3)),
                "hh": int(m.group(1)),
                "mm": int(m.group(2)),
            }
            continue
        m = re.search(
            r"\[(\d{2}):(\d{2})\] \*\*\* \w+: VENDER \*\*\* ~([\d.]+) \(([^,]+)",
            line,
        )
        if m and open_long:
            exit_px = float(m.group(3))
            why = m.group(4).strip()
            ret = exit_px / open_long["entry"] - 1.0
            longs.append({"ret": ret, "why": why, "entry": open_long["entry"], "exit": exit_px})
            reasons["L:" + why] += 1
            open_long = None
            continue
        m = re.search(
            r"\[(\d{2}):(\d{2})\] \*\*\* \w+: PUT \*\*\* ~([\d.]+)", line
        )
        if m:
            open_short = {
                "entry": float(m.group(3)),
                "hh": int(m.group(1)),
                "mm": int(m.group(2)),
            }
            continue
        m = re.search(
            r"\[(\d{2}):(\d{2})\] \*\*\* \w+: VENDER PUT \*\*\* ~([\d.]+) \(([^,]+)",
            line,
        )
        if m and open_short:
            exit_px = float(m.group(3))
            why = m.group(4).strip()
            # short PnL: entry/exit - 1
            ret = open_short["entry"] / exit_px - 1.0
            shorts.append({"ret": ret, "why": why, "entry": open_short["entry"], "exit": exit_px})
            reasons["S:" + why] += 1
            open_short = None
            continue
    return longs, shorts, open_long, open_short, reasons


def summarize(trades, label):
    n = len(trades)
    if n == 0:
        return f"  {label:7s}  0T   —"
    rets = [t["ret"] for t in trades]
    w = sum(1 for r in rets if r > 0)
    gw = sum(r for r in rets if r > 0)
    gl = -sum(r for r in rets if r <= 0)
    pf = gw / gl if gl > 1e-12 else (99.0 if gw > 0 else 0.0)
    aw = gw / w if w else 0.0
    al = gl / (n - w) if (n - w) else 0.0
    stops = sum(1 for t in trades if "STOP" in t["why"].upper() or t["why"].startswith("HARD"))
    return (
        f"  {label:7s} {n:4d}T {w:4d}W WR {w/n:5.0%} "
        f"tot {sum(rets)*100:+7.2f}%  pf {pf:5.2f}  "
        f"avgW {aw*100:+.2f}% avgL {-al*100:+.2f}%  stops {stops}"
    )


def run_one(sym: str) -> dict:
    hist = os.path.join(ROOT, "data", f"bt_{sym.lower()}.txt")
    if not os.path.isfile(hist) or os.path.getsize(hist) < 100:
        return {"sym": sym, "error": f"missing/empty {hist}"}

    # bar count + date range
    with open(hist) as f:
        lines = [ln for ln in f if ln.strip()]
    n_bars = len(lines)
    t0 = float(lines[0].split()[0])
    t1 = float(lines[-1].split()[0])
    d0 = datetime.fromtimestamp(t0, tz=timezone.utc).strftime("%Y-%m-%d")
    d1 = datetime.fromtimestamp(t1, tz=timezone.utc).strftime("%Y-%m-%d")

    env = dict(os.environ)
    env.update(load_keepalive_env(sym))

    bin_path = os.path.join(ROOT, f"{sym.lower()}_signal_bot")
    if not os.path.isfile(bin_path):
        return {"sym": sym, "error": f"no binary {bin_path}"}

    # ISOLATED cwd (fix 2026-07-11): el bot escribe data/pos_*.txt y
    # <sym>_operations.log relativos al cwd. Correr en ROOT pisaba las
    # posiciones VIVAS de la flota y ensuciaba los ops logs con historia
    # de backtest. Cada replay corre en un tmpdir descartable.
    t_run0 = time.time()
    with tempfile.TemporaryDirectory(prefix=f"bt_{sym.lower()}_") as tmp:
        os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
        with open(hist) as stdin_f:
            proc = subprocess.run(
                [bin_path, "--stdin"],
                stdin=stdin_f,
                capture_output=True,
                text=True,
                env=env,
                cwd=tmp,
            )
    elapsed = time.time() - t_run0
    longs, shorts, bag_l, bag_s, reasons = parse_run(proc.stdout)

    # OOS split by trade index ~ last 40% of closed trades (simple)
    def oos_slice(trades, frac=0.4):
        if len(trades) < 5:
            return trades, []
        cut = int(len(trades) * (1 - frac))
        return trades[:cut], trades[cut:]

    l_tr, l_oos = oos_slice(longs)
    s_tr, s_oos = oos_slice(shorts)

    return {
        "sym": sym,
        "n_bars": n_bars,
        "d0": d0,
        "d1": d1,
        "elapsed": elapsed,
        "env_keys": sorted(k for k in env if k.startswith(sym + "_") or k.startswith(sym)),
        "params": {k: env[k] for k in sorted(env) if k.startswith(sym + "_")},
        "longs": longs,
        "shorts": shorts,
        "bag_l": bag_l,
        "bag_s": bag_s,
        "reasons": dict(reasons),
        "l_tr": l_tr,
        "l_oos": l_oos,
        "s_tr": s_tr,
        "s_oos": s_oos,
        "stderr_tail": (proc.stderr or "")[-400:],
    }


def regen_pos():
    """Reproduce el warm-up live (replay de 3 dias, igual que el reader del
    bridge) por bot en un tmpdir y REINSTALA data/pos_*.txt en ROOT.
    Uso: reparar posiciones tras un clobber o tras rebuild de binarios."""
    cutoff = time.time() - 3 * 86400
    for sym in SYMS:
        hist = os.path.join(ROOT, "data", f"bt_{sym.lower()}.txt")
        bin_path = os.path.join(ROOT, f"{sym.lower()}_signal_bot")
        if not os.path.isfile(hist) or not os.path.isfile(bin_path):
            print(f"{sym}: falta historia o binario, skip")
            continue
        env = dict(os.environ)
        env.update(load_keepalive_env(sym))
        bars = []
        with open(hist) as f:
            for ln in f:
                if ln.strip() and float(ln.split(None, 1)[0]) >= cutoff:
                    bars.append(ln)
        with tempfile.TemporaryDirectory(prefix=f"wu_{sym.lower()}_") as tmp:
            os.makedirs(os.path.join(tmp, "data"), exist_ok=True)
            subprocess.run(
                [bin_path, "--stdin"],
                input="".join(bars),
                capture_output=True,
                text=True,
                env=env,
                cwd=tmp,
            )
            state = []
            for suffix, label in (("", "LONG"), ("_s", "SHORT")):
                src = os.path.join(tmp, "data", f"pos_{sym.lower()}{suffix}.txt")
                dst = os.path.join(ROOT, "data", f"pos_{sym.lower()}{suffix}.txt")
                if os.path.isfile(src):
                    shutil.copy(src, dst)
                    state.append(f"{label} entry {open(src).read().split()[0]}")
                elif os.path.exists(dst):
                    os.remove(dst)
        print(f"{sym}: {'; '.join(state) if state else 'flat'}  ({len(bars)} bars 3d)")


def print_report(results):
    print("\n" + "=" * 88)
    print("FLEET BACKTEST — production keepalive params, Alpaca IEX 1m, C++ --stdin")
    print("=" * 88)
    for r in results:
        if r.get("error"):
            print(f"\n## {r['sym']}: ERROR {r['error']}")
            continue
        print(f"\n## {r['sym']}  bars={r['n_bars']}  {r['d0']} → {r['d1']}  "
              f"({r['elapsed']:.1f}s)")
        # key params
        p = r["params"]
        mode = p.get(f"{r['sym']}_MODE", "mr")
        shorts_on = p.get(f"{r['sym']}_SHORTS", "0")
        stop = p.get(f"{r['sym']}_STOP", "?")
        tgt = p.get(f"{r['sym']}_TARGET", "?")
        print(f"   mode={mode} shorts={shorts_on} target={tgt}% stop={stop}%  "
              f"score={p.get(r['sym']+'_SCORE_MIN','0')} eod_force={p.get(r['sym']+'_EOD_FORCE','0')}")
        print(summarize(r["longs"], "LONGS"))
        print(summarize(r["shorts"], "SHORTS"))
        if r["l_oos"]:
            print(summarize(r["l_oos"], "L-OOS40"))
        if r["s_oos"]:
            print(summarize(r["s_oos"], "S-OOS40"))
        if r["bag_l"]:
            print(f"  *** OPEN BAG LONG  entry={r['bag_l']['entry']:.4f}  "
                  f"(unrealized NOT in totals — capital stuck)")
        if r["bag_s"]:
            print(f"  *** OPEN BAG SHORT entry={r['bag_s']['entry']:.4f}  "
                  f"(unrealized NOT in totals — capital stuck)")
        # top reasons
        top = sorted(r["reasons"].items(), key=lambda x: -x[1])[:8]
        if top:
            print("   exits: " + ", ".join(f"{k}={v}" for k, v in top))

    # portfolio summary
    print("\n" + "=" * 88)
    print("PORTFOLIO SUMMARY (sum of per-ticker closed trade returns — not capital-weighted)")
    print("=" * 88)
    print(f"{'SYM':6s} {'L_T':>4s} {'L_WR':>5s} {'L_tot':>8s} {'S_T':>4s} {'S_WR':>5s} "
          f"{'S_tot':>8s} {'BAG':>5s} {'ALL':>8s}")
    grand_l = grand_s = 0.0
    n_bags = 0
    for r in results:
        if r.get("error"):
            print(f"{r['sym']:6s} ERROR")
            continue
        lr = [t["ret"] for t in r["longs"]]
        sr = [t["ret"] for t in r["shorts"]]
        lw = sum(1 for x in lr if x > 0)
        sw = sum(1 for x in sr if x > 0)
        lt = sum(lr) * 100
        st = sum(sr) * 100
        bag = ("L" if r["bag_l"] else "") + ("S" if r["bag_s"] else "") or "-"
        if r["bag_l"] or r["bag_s"]:
            n_bags += 1
        grand_l += sum(lr)
        grand_s += sum(sr)
        print(
            f"{r['sym']:6s} {len(lr):4d} {lw/len(lr) if lr else 0:5.0%} {lt:+7.1f}% "
            f"{len(sr):4d} {sw/len(sr) if sr else 0:5.0%} {st:+7.1f}% "
            f"{bag:>5s} {(sum(lr)+sum(sr))*100:+7.1f}%"
        )
    print(f"\nSum closed long R:  {grand_l*100:+.2f}%")
    print(f"Sum closed short R: {grand_s*100:+.2f}%")
    print(f"Sum closed ALL R:   {(grand_l+grand_s)*100:+.2f}%")
    print(f"Tickers ending in open bag: {n_bags}")
    print("\nNOTE: returns are uncompounded sum of trade % (full-cash assumption each trade).")
    print("NOTE: no commissions/slippage modeled in C++ signal PnL.")
    print("NOTE: IEX tape = incomplete volume/gaps vs SIP — live fills worse.")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd = args[0]
    days = int(args[1]) if len(args) > 1 else 180
    if cmd == "warmup":
        regen_pos()
        return
    if cmd in ("fetch", "all"):
        for s in SYMS:
            try:
                fetch_one(s, days)
            except Exception as e:
                print(f"{s}: FETCH FAIL {e}")
    if cmd in ("run", "all"):
        results = []
        for s in SYMS:
            print(f"... running {s}", flush=True)
            results.append(run_one(s))
        print_report(results)
        # also dump JSON-ish summary for later
        out = os.path.join(ROOT, "data", "fleet_bt_summary.txt")
        with open(out, "w") as f:
            f.write(f"generated {datetime.now().isoformat()}\n")
            for r in results:
                if r.get("error"):
                    f.write(f"{r['sym']} ERROR {r['error']}\n")
                    continue
                lt = sum(t["ret"] for t in r["longs"]) * 100
                st = sum(t["ret"] for t in r["shorts"]) * 100
                f.write(
                    f"{r['sym']} L{len(r['longs'])}T {lt:+.2f}% "
                    f"S{len(r['shorts'])}T {st:+.2f}% "
                    f"bagL={bool(r['bag_l'])} bagS={bool(r['bag_s'])}\n"
                )
        print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
