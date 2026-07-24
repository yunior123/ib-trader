#!/usr/bin/env python3
"""prob_profit_test.py — smoke + doctrina para el overlay de probabilidad.
Sin red y sin depender de caches vivos: stubbea chart_levels/narrator/direction_view/
signal_conditioning en sys.modules para forzar escenarios y verificar la lógica de composición
y los VETOS de doctrina (whipsaw honesto, capitán en contra, imán a favor).

Uso: python3 order_engine/prob_profit_test.py   (exit 0 = todo verde)
"""
import os, sys, types, importlib

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "order_engine"))
sys.path.insert(0, os.path.join(REPO, "scripts"))

FAILS = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        FAILS.append(name)


def _stub(lv=None, sig=None, dv=None, cond=None):
    """Inyecta módulos falsos. lv=None -> chart_levels devuelve None (gamma missing)."""
    cl = types.ModuleType("chart_levels")
    cl.gen = lambda sym, spot=None, write=True, all_exp=False: lv
    sys.modules["chart_levels"] = cl

    nr = types.ModuleType("narrator")
    nr.structural_signal = lambda lv, bars=None: sig
    sys.modules["narrator"] = nr

    dvm = types.ModuleType("direction_view")
    dvm.compute = lambda sym, lv=None: (dv or {"dir": "flat", "prob": 50, "score": 0.0})
    sys.modules["direction_view"] = dvm

    scm = types.ModuleType("signal_conditioning")
    scm.conditioned_prob = lambda source, sym, d, base, now_min=None: (
        cond or {"prob": 60, "veto": False, "speak": True, "why": []})
    sys.modules["signal_conditioning"] = scm

    for m in ("prob_profit",):
        sys.modules.pop(m, None)
    return importlib.import_module("prob_profit")


# --- 1) helpers puros ---
P = _stub()
check("dfav buy call = alcista", P._dfav("buy", "call") == 1)
check("dfav buy put = bajista", P._dfav("buy", "put") == -1)
check("dfav sell call = bajista", P._dfav("sell", "call") == -1)
check("dfav sell put = alcista", P._dfav("sell", "put") == 1)
check("days_to_exp None = 0DTE", P._days_to_exp(None) == 0)
check("days_to_exp futuro > 0", P._days_to_exp("20991231") > 100)

# --- 2) degradación limpia: sin ningún insumo, no crashea y da forma completa ---
P = _stub(lv=None, sig=None,
          dv=None, cond={"prob": 60, "veto": False, "speak": True, "why": []})
# forzar flow/tech missing lanzando excepción -> usar módulos que revientan
sys.modules["direction_view"].compute = lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
sys.modules["signal_conditioning"].conditioned_prob = lambda *a, **k: (_ for _ in ()).throw(RuntimeError())
r = P.prob_profit("ZZZZ", 100, "buy", "call")
for key in ("prob", "verdict", "why", "regime", "magnet", "walls", "components"):
    check(f"clave presente: {key}", key in r)
check("verdict válido", r["verdict"] in ("GO", "CAUTION", "NO-GO"))
check("prob en [0,100]", 0 <= r["prob"] <= 100)
check("missing_core = 3 (todo ausente)", r["flags"]["missing_core"] == 3)
check("componentes núcleo None", r["components"]["gamma"] is None
      and r["components"]["flow"] is None and r["components"]["technical"] is None)

# --- 3) HONESTIDAD whipsaw: NEG sin imán oro + flujo flat -> NO-GO "whipsaw sin lado limpio" ---
lv_neg = {"sym": "QQQ", "spot": 500.0, "flip": 505.0, "regime": "NEG",
          "call_wall": 510.0, "put_wall": 495.0, "em": 6.0, "pressure": -50}
P = _stub(lv=lv_neg, sig=None,           # sig None = sin imán oro
          dv={"dir": "flat", "prob": 50, "score": 0.05},
          cond={"prob": 60, "veto": False, "speak": True, "why": []})
r = P.prob_profit("QQQ", 500, "buy", "call")
check("whipsaw flag activo", r["flags"]["whipsaw"] is True)
check("whipsaw -> NO-GO", r["verdict"] == "NO-GO")
check("whipsaw en el why", any("whipsaw sin lado" in w for w in r["why"]))

# --- 3b) band-walk: mismo NEG pero flujo FUERTE a favor -> no es whipsaw ciego ---
P = _stub(lv=lv_neg, sig=None,
          dv={"dir": "up", "prob": 78, "score": 0.7},   # flujo fuerte a favor del call
          cond={"prob": 66, "veto": False, "speak": True, "why": []})
r = P.prob_profit("QQQ", 500, "buy", "call")
check("band-walk rescata (no NO-GO por whipsaw)", r["flags"]["band_walk"] is True)
check("band-walk nota presente", any("band-walk" in w for w in r["why"]))

# --- 4) VETO de capitán en contra -> NO-GO siempre ---
lv_pos = {"sym": "NVDA", "spot": 200.0, "flip": 195.0, "regime": "POS",
          "call_wall": 205.0, "put_wall": 190.0, "abs_wall": 205.0, "em": 4.0, "pressure": 60,
          "call_wall_gex": 100.0, "abs_wall_gex": 120.0, "put_wall_gex": -80.0}
sig_up = {"sym": "NVDA", "dir": "up", "kind": "magnet", "price": 205.0, "prob": 72}
P = _stub(lv=lv_pos, sig=sig_up,
          dv={"dir": "up", "prob": 70, "score": 0.6},
          cond={"prob": 40, "veto": True, "speak": False, "why": ["capitán EN CONTRA"]})
r = P.prob_profit("NVDA", 200, "buy", "call")
check("veto -> NO-GO", r["verdict"] == "NO-GO")
check("veto flag", r["flags"]["veto"] is True)

# --- 5) escenario LIMPIO alcista: POS + imán oro a favor + flujo a favor + sin veto -> GO ---
P = _stub(lv=lv_pos, sig=sig_up,
          dv={"dir": "up", "prob": 74, "score": 0.65},
          cond={"prob": 72, "veto": False, "speak": True, "why": []})
r = P.prob_profit("NVDA", 200, "buy", "call")
check("imán oro a favor detectado", r["magnet"] and r["magnet"]["dir"] == "up")
check("magnet_toward flag", r["flags"]["magnet_toward"] is True)
check("prob alta (>60)", r["prob"] > 60)
check("veredicto GO", r["verdict"] == "GO")

# --- 5b) mismo imán pero trade BAJISTA (put) -> imán en contra -> no GO ---
r = P.prob_profit("NVDA", 200, "buy", "put")
check("imán en contra para put", r["flags"]["magnet_against"] is True)
check("put contra imán -> no GO", r["verdict"] in ("CAUTION", "NO-GO"))

print()
if FAILS:
    print(f"{len(FAILS)} FALLO(S): " + "; ".join(FAILS))
    sys.exit(1)
print("TODO VERDE")
