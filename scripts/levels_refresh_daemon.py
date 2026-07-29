#!/usr/bin/env python3
import sys, os, time, json, glob
from pathlib import Path

__file_abs = os.path.abspath(__file__)
REPO = os.path.dirname(os.path.dirname(__file_abs))
sys.path.insert(0, REPO)

import gex_core
import chart_levels

FLEET_FILE = os.path.join(REPO, "data", "fleet.txt")
LEVELS_DIR = os.path.join(REPO, "charts", "data")
LOG_FILE = os.path.join(REPO, "logs", "levels_refresh.log")

def log_msg(s):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{ts}] {s}"
    print(msg, flush=True)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")

def is_served_fresh(sym):
    """True si levels_<sym>.json tiene mtime <60s (margen ante el gate de 180s)."""
    path = os.path.join(LEVELS_DIR, f"levels_{sym.lower()}.json")
    if not os.path.exists(path):
        return False
    age = time.time() - os.path.getmtime(path)
    return age < 60

def refresh_one(sym):
    """Refresca levels_<sym>.json via chart_levels.gen(). Retorna True si ok, False si error."""
    try:
        result = chart_levels.gen(sym, spot=None, write=True, all_exp=False)
        if result:
            age = time.time() - os.path.getmtime(os.path.join(LEVELS_DIR, f"levels_{sym.lower()}.json"))
            log_msg(f"✓ {sym}: refrescado (age={age:.1f}s)")
            return True
        else:
            log_msg(f"✗ {sym}: gen() retorno None (sin cache?)")
            return False
    except Exception as e:
        log_msg(f"✗ {sym}: {type(e).__name__}: {e}")
        return False

def cycle_once():
    """Un ciclo de refresh: itera fleet.txt, salta los frescos, refresca los rancios."""
    if not os.path.exists(FLEET_FILE):
        log_msg(f"ERROR: {FLEET_FILE} no existe")
        return 0, 0
    
    fleet = open(FLEET_FILE).read().split()
    if not fleet:
        log_msg("ERROR: data/fleet.txt vacio")
        return 0, 0
    
    ok_count = 0
    fail_count = 0
    skipped_count = 0
    
    for sym in fleet:
        if is_served_fresh(sym):
            skipped_count += 1
            continue
        
        if refresh_one(sym):
            ok_count += 1
        else:
            fail_count += 1
        
        time.sleep(0.5)
    
    log_msg(f"CICLO: {ok_count} ok, {fail_count} fallos, {skipped_count} frescos (skipados)")
    return ok_count + fail_count, fail_count

def main():
    once = "--once" in sys.argv
    force_rth = "--force-rth" in sys.argv
    
    fail_streak = 0
    while True:
        in_rth = gex_core.in_rth() if not force_rth else True
        
        if not in_rth:
            log_msg("Fuera de RTH: durmiendo 300s")
            time.sleep(300)
            continue
        
        worked, failed = cycle_once()
        if worked > 0 and failed == worked:
            fail_streak += 1
            if fail_streak > 5:
                log_msg(f"ALERTA: {fail_streak} ciclos fallidos seguidos")
                fail_streak = 0
        else:
            fail_streak = 0
        
        if once:
            break
        
        time.sleep(60)

if __name__ == "__main__":
    main()
