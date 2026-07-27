#!/usr/bin/env python3
"""Las hojas HTML de data/trees/*.json. Senal-solamente: describe el libro, no ordena nada."""
import json, os, sys, sqlite3, html, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TREES = os.path.join(ROOT, "data", "trees")
SYMS = ["QQQ", "NVDA", "SMH", "MU", "AAPL", "MSFT"]
WIN = 0.055          # ventana del perfil alrededor del spot


def fleet_touch_curve():
    db = os.path.join(ROOT, "trades.db")
    if not os.path.exists(db):
        return None
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select touch_ord, sum(case when event='BREAK' then 0 else 1 end),"
            " sum(case when event='BREAK' then 1 else 0 end), count(*) "
            "from level_events where event in ('BOUNCE','BREAK','WICK_REJECT','RETEST_REJECT') "
            "group by touch_ord having count(*)>=20 order by touch_ord").fetchall()
        ses = con.execute("select count(distinct date(ts,'unixepoch','localtime')),"
                          " count(distinct sym) from level_events").fetchone()
    finally:
        con.close()
    if not rows:
        return None
    return {"sesiones": ses[0], "syms": ses[1],
            "curva": [{"toque": r[0], "aguanta": r[1], "rompe": r[2], "n": r[3],
                       "pct": round(100.0 * r[1] / r[3], 1)} for r in rows]}


def num(x, nd=2):
    return "—" if x is None else f"{x:,.{nd}f}".replace(",", " ")


def oi(x):
    return "—" if x is None else f"{int(x):,}".replace(",", " ")


def usd(x):
    if x is None:
        return "—"
    a = abs(x)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{'−' if x < 0 else ''}{a/div:.2f} {suf}"
    return f"{x:.0f}"


def pct_from(spot, lvl):
    return None if (spot in (None, 0) or lvl is None) else 100.0 * (lvl / spot - 1)


def profile_svg(d):
    spot, flip = d["spot"], d.get("flip")
    rows = [(p["strike"], p["gex"]) for p in d["profile"]
            if abs(p["strike"] / spot - 1) <= WIN and p["gex"]]
    if not rows:
        return '<p class="void">Sin perfil dentro de la ventana.</p>'
    rows.sort(key=lambda r: -r[0])
    mx = max(abs(v) for _, v in rows) or 1.0
    W, H, MID, PAD = 560, max(190, 15 * len(rows) + 30), 250, 14
    bh = (H - 2 * PAD) / len(rows)
    ks = [r[0] for r in rows]                      # descendente

    def ymap(lvl):                                 # por INDICE, igual que las barras
        for i in range(len(ks) - 1):
            hi, lo = ks[i], ks[i + 1]
            if lo <= lvl <= hi:
                f = 0.5 if hi == lo else (hi - lvl) / (hi - lo)
                return PAD + (i + 0.5 + f) * bh
        return PAD + (0.5 if lvl >= ks[0] else len(ks) - 0.5) * bh
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Perfil de gamma neta por strike" class="prof">',
           f'<line x1="{MID}" y1="{PAD-6}" x2="{MID}" y2="{H-PAD+6}" class="ax"/>']
    for i, (k, v) in enumerate(rows):
        y = PAD + i * bh
        w = abs(v) / mx * (MID - 58)
        x = MID if v > 0 else MID - w
        cls = "pos" if v > 0 else "neg"
        out.append(f'<rect x="{x:.1f}" y="{y+1:.1f}" width="{w:.1f}" height="{max(2,bh-2):.1f}" class="{cls}"/>')
        out.append(f'<text x="{MID-4:.0f}" y="{y+bh/2+3.5:.1f}" class="klab" text-anchor="end">{k:g}</text>'
                   if v > 0 else
                   f'<text x="{MID+4:.0f}" y="{y+bh/2+3.5:.1f}" class="klab" text-anchor="start">{k:g}</text>')
    for lvl, cls, lab in ((spot, "spotl", "spot"), (flip, "flipl", "flip")):
        if lvl is None or not (min(r[0] for r in rows) <= lvl <= max(r[0] for r in rows)):
            continue
        y = ymap(lvl)
        out.append(f'<line x1="{PAD}" y1="{y:.1f}" x2="{W-PAD}" y2="{y:.1f}" class="{cls}"/>'
                   f'<text x="{W-PAD:.0f}" y="{y-4:.1f}" class="lvlab {cls}t" text-anchor="end">{lab} {lvl:,.2f}</text>')
    out.append(f'<text x="{MID+8}" y="{H-2}" class="axlab">calls · gamma +</text>'
               f'<text x="{MID-8}" y="{H-2}" class="axlab" text-anchor="end">puts · gamma −</text></svg>')
    return "".join(out)


def ladder(d):
    spot = d["spot"]
    lv = []
    for key, lab in (("call_wall", "muro de calls"), ("abs_wall", "muro dominante"),
                     ("put_wall", "muro de puts"), ("oi_call_wall", "muro OI calls"),
                     ("oi_put_wall", "muro OI puts")):
        k = d.get(key)
        if k is None:
            continue
        kind = d.get(key + "_kind")
        lv.append({"k": k, "lab": lab, "kind": kind})
    if d.get("flip") is not None:
        lv.append({"k": d["flip"], "lab": "gamma-flip", "kind": "flip"})
    lv.append({"k": spot, "lab": "SPOT (cierre viernes)", "kind": "spot"})
    seen, uni = set(), []
    for x in sorted(lv, key=lambda z: -z["k"]):
        key = (round(x["k"], 2), x["lab"])
        if key in seen:
            continue
        seen.add(key)
        uni.append(x)
    rows = []
    for x in uni:
        dist = pct_from(spot, x["k"])
        kd = x["kind"]
        chip = {"pin": '<span class="chip pin">pin · aguanta</span>',
                "trampilla": '<span class="chip trap">trampilla · atraviesa</span>',
                "flip": '<span class="chip flip">gamma cero</span>',
                "spot": ""}.get(kd, '<span class="chip none">sin régimen</span>')
        cls = "row spot" if kd == "spot" else "row"
        rows.append(
            f'<div class="{cls}"><b class="k">{x["k"]:,.2f}</b>'
            f'<span class="lab">{html.escape(x["lab"])}</span>{chip}'
            f'<span class="d">{"" if dist is None else f"{dist:+.2f}%"}</span></div>')
    return '<div class="ladder">' + "".join(rows) + "</div>"


def branch_text(kind, lab):
    if kind == "pin":
        return f"{lab} en régimen POS: los dealers amortiguan. El nivel aguanta — se cobra ahí, no se persigue a través."
    if kind == "trampilla":
        return f"{lab} en régimen NEG: los dealers amplifican. El precio lo ATRAVIESA — prohibido fadear en el aire."
    return f"{lab} sin régimen calculable: no se afirma nada del nivel."


def tree(d):
    spot, cw, pw = d["spot"], d.get("call_wall"), d.get("put_wall")
    flip, reg = d.get("flip"), d.get("regime")
    up, dn = [], []
    if cw is not None:
        up.append((cw, d.get("call_wall_kind"), "muro de calls"))
    if flip is not None and flip > spot:
        up.append((flip, "flip", "gamma-flip"))
    if pw is not None:
        dn.append((pw, d.get("put_wall_kind"), "muro de puts"))
    if flip is not None and flip < spot:
        dn.append((flip, "flip", "gamma-flip"))
    up.sort(key=lambda x: x[0])
    dn.sort(key=lambda x: -x[0])

    def leg(items, arrow, cls):
        if not items:
            return f'<li class="{cls}"><span class="arw">{arrow}</span><span class="void">sin nivel calculado por ese lado</span></li>'
        out = []
        for k, kind, lab in items:
            dist = pct_from(spot, k)
            txt = ("Cruzar el flip cambia el régimen: por encima los dealers amortiguan, por debajo amplifican."
                   if kind == "flip" else branch_text(kind, lab))
            out.append(f'<li class="{cls}"><span class="arw">{arrow}</span>'
                       f'<b>{k:,.2f}</b><span class="dd">{dist:+.2f}%</span>'
                       f'<span class="why">{html.escape(txt)}</span></li>')
        return "".join(out)

    caja = ""
    if reg == "NEG" and cw is not None and pw is not None:
        caja = (f'<p class="verdict neg">Régimen NEG entre {pw:,.2f} y {cw:,.2f}: es una CAJA, no una dirección. '
                f'La gamma negativa amplifica los dos lados — sin lado limpio hasta que un muro se toque '
                f'y sea RECHAZADO con print de IBKR.</p>')
    elif reg == "POS":
        caja = (f'<p class="verdict pos">Régimen POS: los dealers amortiguan. Los niveles tienden a aguantar '
                f'y el rango se comprime hacia el imán dominante ({num(d.get("abs_wall"))}).</p>')
    return (f'<ul class="tree">{leg(up, "▲", "up")}'
            f'<li class="node"><span class="arw">◆</span><b>{spot:,.2f}</b>'
            f'<span class="dd">spot</span><span class="why">cierre del viernes — el print que confirme '
            f'cualquiera de estas ramas tiene que venir de IBKR en tiempo real, no de aquí.</span></li>'
            f'{leg(dn, "▼", "dn")}</ul>{caja}')


def surv_table(d):
    rows = [x for x in d["supervivientes"]]
    if not rows:
        return '<p class="void">Sin muros registrados la semana pasada.</p>'
    tr = []
    for x in rows:
        est = x["estado"]
        cls = {"SOBREVIVE": "ok", "DECAIDO": "warn", "SIN RASTRO": "bad"}[est]
        tr.append(f'<tr><td class="{"c" if x["lado"]=="C" else "p"}">{"CALL" if x["lado"]=="C" else "PUT"}</td>'
                  f'<td class="n">{x["strike"]:g}</td><td class="n">{x["dias_semana_pasada"]}</td>'
                  f'<td class="n">{oi(x["oi_entonces"])}</td><td class="n">{oi(x["oi_ahora"])}</td>'
                  f'<td class="n">{"—" if x["rank_ahora"] is None else "#"+str(x["rank_ahora"])}</td>'
                  f'<td class="n">{oi(x["oi_viernes"])}</td>'
                  f'<td><span class="st {cls}">{est}</span></td></tr>')
    return ('<div class="scroll"><table class="tbl"><thead><tr><th>lado</th><th>strike</th>'
            '<th>días</th><th>OI entonces</th><th>OI ahora</th><th>rango</th><th>OI viernes</th>'
            '<th>estado</th></tr></thead><tbody>' + "".join(tr) + "</tbody></table></div>")


def friday_table(d):
    cs, ps = d.get("viernes_top_calls") or [], d.get("viernes_top_puts") or []
    n = max(len(cs), len(ps))
    if not n:
        return '<p class="void">La cadena no tiene contratos para ese viernes.</p>'
    tr = []
    for i in range(n):
        c = cs[i] if i < len(cs) else None
        p = ps[i] if i < len(ps) else None
        tr.append(f'<tr><td class="n c">{c["strike"]:g}' if c else '<tr><td class="n">—')
        tr.append(f'</td><td class="n">{oi(c["oi"]) if c else "—"}</td>')
        tr.append(f'<td class="n p">{p["strike"]:g}</td><td class="n">{oi(p["oi"])}</td></tr>'
                  if p else '<td class="n">—</td><td class="n">—</td></tr>')
    return ('<div class="scroll"><table class="tbl"><thead><tr><th colspan="2">CALLS</th>'
            '<th colspan="2">PUTS</th></tr><tr><th>strike</th><th>OI</th><th>strike</th><th>OI</th>'
            '</tr></thead><tbody>' + "".join(tr) + "</tbody></table></div>")


def sheet(d, i, ntot):
    spot, flip = d["spot"], d.get("flip")
    fd = pct_from(spot, flip)
    reg = d.get("regime")
    surv_ok = sum(1 for x in d["supervivientes"] if x["estado"] == "SOBREVIVE")
    stats = [
        ("spot", f'{num(spot)}', "cierre del viernes"),
        ("régimen", f'<span class="reg {"" if reg is None else reg.lower()}">{reg or "—"}</span>',
         "POS amortigua · NEG amplifica"),
        ("gamma-flip", num(flip), "—" if fd is None else f"{fd:+.2f}% del spot"),
        ("net GEX", usd(d.get("net_gex")), "convención de la casa (×spot)"),
        ("muro de calls", num(d.get("call_wall")), d.get("call_wall_kind") or "sin régimen"),
        ("muro de puts", num(d.get("put_wall")), d.get("put_wall_kind") or "sin régimen"),
        ("P/C del viernes", num(d.get("viernes_pc_oi"), 2),
         f'{oi(d.get("viernes_puts_oi"))} puts / {oi(d.get("viernes_calls_oi"))} calls'),
        ("supervivientes", f'{surv_ok}<span class="of">/{len(d["supervivientes"])}</span>',
         "muros de la semana pasada aún en el top 6"),
    ]
    cards = "".join(f'<div class="stat"><span class="sl">{html.escape(l)}</span>'
                    f'<span class="sv">{v}</span><span class="sn">{html.escape(str(n))}</span></div>'
                    for l, v, n in stats)
    cav = "".join(f"<li>{html.escape(c)}</li>" for c in d.get("caveats") or [])
    return f'''<section class="sheet" id="{d['sym'].lower()}">
<header class="sh">
 <span class="ord">hoja {i} de {ntot}</span>
 <h2>{d['sym']}</h2>
 <p class="sub">{d['n_solo_viernes']} contratos al viernes {d['viernes']} · {d['n_hasta_viernes']} hasta esa fecha · banda {d.get('band')} · griegas {html.escape(str(d.get('greeks_src')))}</p>
</header>
<div class="stats">{cards}</div>
<div class="two">
 <div class="col">
  <h3>El árbol</h3>
  {tree(d)}
  <h3>La escalera</h3>
  {ladder(d)}
 </div>
 <div class="col">
  <h3>Gamma neta por strike <span class="hint">±{WIN*100:.1f}% del spot</span></h3>
  {profile_svg(d)}
  <h3>La cadena que expira el viernes {d['viernes']}</h3>
  {friday_table(d)}
 </div>
</div>
<h3>Muros de la semana pasada ({d['semana_pasada_fechas'][0]} → {d['semana_pasada_fechas'][-1]})</h3>
<p class="declara"><b>Dos ventanas distintas, no se comparan a ciegas:</b> los muros de la semana
pasada salen de cadenas IBKR/TWS archivadas con banda <b>±4,5%</b> y del vencimiento más cercano
de cada día — contratos <b>ya expirados</b>. El libro de hoy es Polygon con banda adaptativa
<b>{d.get('band')}</b> y todos los vencimientos hasta el viernes. Por eso la supervivencia se
decide por <b>RANGO del strike</b> en el libro de hoy, nunca por el cociente de OI.</p>
{surv_table(d)}
<details class="cav"><summary>Lo que este mapa NO dice ({len(d.get('caveats') or [])})</summary><ul>{cav}</ul></details>
</section>'''


def curve_block(tc):
    if not tc:
        return ""
    bars = "".join(
        f'<div class="cb"><span class="ct">{r["toque"]}</span>'
        f'<div class="cbar"><div style="width:{r["pct"]:.1f}%"></div></div>'
        f'<span class="cp">{r["pct"]:.0f}%</span><span class="cn">n={r["n"]}</span></div>'
        for r in tc["curva"][:8])
    return f'''<section class="sheet doct" id="decay">
<header class="sh"><span class="ord">control de doctrina</span>
<h2>¿De verdad el primer toque rebota al 70%?</h2>
<p class="sub">La casa opera con esa constante y con <code>TOUCH_EXHAUST = 3</code>. Nunca se midió. Esto es lo que dicen los datos que hay.</p></header>
<div class="curve">{bars}</div>
<p class="verdict warn">Veredicto: <b>DATOS INSUFICIENTES</b> — {tc['sesiones']} sesiones y {tc['syms']} símbolos correlacionados
(ρ̄ de la flota = 0,41, así que la muestra efectiva es una fracción de la nominal). Con lo que hay, la tasa de aguante
<b>no decae</b> con el número de toque, que es lo contrario de lo que dice la doctrina. No se cambia la doctrina con esto,
y tampoco se afirma que sea cierta: hace falta ~40 sesiones. El reloj ya corre.</p>
</section>'''


def main():
    ds = []
    for s in (sys.argv[1:] or SYMS):
        p = os.path.join(TREES, f"{s.lower()}.json")
        if not os.path.exists(p):
            print(f"{s}: sin data/trees/{s.lower()}.json", file=sys.stderr)
            continue
        ds.append(json.load(open(p)))
    if not ds:
        raise RuntimeError("no hay ninguna hoja en data/trees/")
    nav = "".join(f'<a href="#{d["sym"].lower()}">{d["sym"]}</a>' for d in ds)
    body = "".join(sheet(d, i + 1, len(ds)) for i, d in enumerate(ds))
    gen = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    titulo = NOMBRE.get(len(ds), f"Los {len(ds)} árboles")
    out = HEAD.replace("@@TITULO@@", f"{titulo} — " + " · ".join(d["sym"] for d in ds)) + f'''<div class="wrap">
<header class="top">
 <p class="kicker">ib-trader · mapa de posicionamiento · señal-solamente</p>
 <h1>{titulo}</h1>
 <p class="lede">Qué muros de la semana pasada siguen en pie, qué libro hay hasta el viernes
 {ds[0]['viernes']}, y qué expira ese día. Una hoja de papel por ticker.</p>
 <nav class="nav">{nav}<a href="#decay">doctrina</a></nav>
 <p class="stamp">generado {gen} · cadena {ds[0]['chain_dir']} · Polygon (15 min de retraso) para la estructura ·
 el disparo es de IBKR en tiempo real, nunca de aquí</p>
</header>
{body}
{curve_block(fleet_touch_curve())}
<footer class="foot"><p>Nada de esto es una orden ni un consejo financiero. Describe el libro de opciones;
no predice el precio. Sin print de IBKR no hay entrada.</p></footer>
</div>'''
    dest = os.path.join(ROOT, "data", "trees", "arboles.html")
    with open(dest, "w") as f:
        f.write(out)
    print(dest, f"({os.path.getsize(dest)/1024:.0f} KB, {len(ds)} hojas)")


NOMBRE = {4: "Los cuatro árboles", 5: "Los cinco árboles", 6: "Los seis árboles",
          7: "Los siete árboles"}

HEAD = '''<meta charset="utf-8">
<title>@@TITULO@@</title>
<style>
:root{
 --ground:#0d1014; --panel:#141920; --panel2:#1b212a; --line:#28303b;
 --ink:#e8e6e0; --ink2:#a7a49c; --ink3:#6f6d67;
 --gold:#d7a12c; --violet:#8b6bff; --call:#3f9d6b; --put:#c9543f; --warn:#d78b2c;
 --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,monospace;
 --disp:"Avenir Next Condensed","HelveticaNeue-CondensedBold","Arial Narrow",system-ui,sans-serif;
 --body:system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme:light){
 :root{--ground:#f6f5f1;--panel:#fffefb;--panel2:#efeee8;--line:#dad7cd;
 --ink:#1a1c1f;--ink2:#5a5852;--ink3:#8b8880;--gold:#9a6f10;--violet:#5a3fd6;
 --call:#2f7d52;--put:#a63c2a;--warn:#9a6410;}
}
:root[data-theme="dark"]{--ground:#0d1014;--panel:#141920;--panel2:#1b212a;--line:#28303b;
 --ink:#e8e6e0;--ink2:#a7a49c;--ink3:#6f6d67;--gold:#d7a12c;--violet:#8b6bff;
 --call:#3f9d6b;--put:#c9543f;--warn:#d78b2c;}
:root[data-theme="light"]{--ground:#f6f5f1;--panel:#fffefb;--panel2:#efeee8;--line:#dad7cd;
 --ink:#1a1c1f;--ink2:#5a5852;--ink3:#8b8880;--gold:#9a6f10;--violet:#5a3fd6;
 --call:#2f7d52;--put:#a63c2a;--warn:#9a6410;}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--body);
 font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:clamp(20px,4vw,52px) clamp(14px,3vw,28px) 64px}
.top{border-bottom:2px solid var(--line);padding-bottom:22px;margin-bottom:34px}
.kicker{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;
 color:var(--gold);margin:0 0 10px}
h1{font-family:var(--disp);font-size:clamp(38px,7vw,68px);line-height:.95;letter-spacing:-.01em;
 margin:0 0 12px;text-wrap:balance;font-weight:600}
.lede{max-width:62ch;color:var(--ink2);margin:0 0 18px;font-size:17px}
.nav{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.nav a{font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-decoration:none;
 color:var(--ink2);border:1px solid var(--line);border-radius:2px;padding:5px 11px;background:var(--panel)}
.nav a:hover,.nav a:focus-visible{color:var(--ground);background:var(--gold);border-color:var(--gold);outline:none}
.stamp{font-family:var(--mono);font-size:11.5px;color:var(--ink3);margin:0;max-width:82ch}
.sheet{border:1px solid var(--line);background:var(--panel);padding:clamp(16px,2.4vw,28px);
 margin-bottom:30px;scroll-margin-top:16px}
.sh{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:18px}
.ord{font-family:var(--mono);font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink3)}
h2{font-family:var(--disp);font-size:clamp(30px,5vw,46px);margin:2px 0 6px;letter-spacing:.01em;font-weight:600}
.sub{font-family:var(--mono);font-size:12px;color:var(--ink2);margin:0}
h3{font-family:var(--mono);font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;
 color:var(--gold);margin:26px 0 10px;font-weight:600}
h3:first-child{margin-top:0}
.hint{color:var(--ink3);letter-spacing:.04em;text-transform:none}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:1px;
 background:var(--line);border:1px solid var(--line);margin-bottom:6px}
.stat{background:var(--panel2);padding:11px 13px;display:flex;flex-direction:column;gap:2px}
.sl{font-family:var(--mono);font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3)}
.sv{font-family:var(--mono);font-size:20px;font-variant-numeric:tabular-nums;color:var(--ink)}
.sv .of{font-size:13px;color:var(--ink3)}
.sn{font-family:var(--mono);font-size:10.5px;color:var(--ink2)}
.reg.neg{color:var(--violet)}.reg.pos{color:var(--gold)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:8px}
@media(max-width:860px){.two{grid-template-columns:1fr}}
.tree{list-style:none;margin:0;padding:0;font-family:var(--mono);font-size:12.5px}
.tree li{display:grid;grid-template-columns:22px 74px 62px 1fr;gap:6px;align-items:baseline;
 padding:7px 0;border-bottom:1px dotted var(--line)}
.tree li:last-child{border-bottom:none}
.tree .arw{color:var(--ink3)}
.tree .up .arw{color:var(--call)}.tree .dn .arw{color:var(--put)}
.tree .node{background:var(--panel2);margin:4px -8px;padding:9px 8px;border-left:2px solid var(--gold)}
.tree b{font-variant-numeric:tabular-nums;font-size:14px}
.tree .dd{color:var(--ink3);font-size:11px}
.tree .why{color:var(--ink2);line-height:1.5;grid-column:1/-1}
@media(min-width:600px){.tree .why{grid-column:4}}
.ladder{font-family:var(--mono);font-size:12.5px;border:1px solid var(--line)}
.ladder .row{display:flex;align-items:center;gap:9px;padding:8px 11px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.ladder .row:last-child{border-bottom:none}
.ladder .row.spot{background:var(--panel2);border-left:2px solid var(--gold)}
.ladder .k{font-variant-numeric:tabular-nums;min-width:74px}
.ladder .lab{color:var(--ink2);flex:1;min-width:110px}
.ladder .d{color:var(--ink3);font-variant-numeric:tabular-nums}
.chip{font-size:10px;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;border:1px solid}
.chip.pin{color:var(--gold);border-color:var(--gold)}
.chip.trap{color:var(--violet);border-color:var(--violet)}
.chip.flip{color:var(--ink2);border-color:var(--line)}
.chip.none{color:var(--ink3);border-color:var(--line)}
.prof{width:100%;height:auto;display:block;background:var(--panel2);border:1px solid var(--line)}
.prof .pos{fill:var(--call)}.prof .neg{fill:var(--put)}
.prof .ax{stroke:var(--line);stroke-width:1}
.prof .klab{font-family:var(--mono);font-size:8.5px;fill:var(--ink3)}
.prof .axlab{font-family:var(--mono);font-size:8.5px;fill:var(--ink3);letter-spacing:.06em}
.prof .spotl{stroke:var(--gold);stroke-width:1;stroke-dasharray:4 3}
.prof .flipl{stroke:var(--violet);stroke-width:1;stroke-dasharray:2 3}
.prof .spotlt{fill:var(--gold)}.prof .fliplt{fill:var(--violet)}
.prof .lvlab{font-family:var(--mono);font-size:9px;letter-spacing:.04em}
.scroll{overflow-x:auto;border:1px solid var(--line)}
.tbl{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}
.tbl th{background:var(--panel2);text-align:left;padding:7px 10px;font-size:10px;letter-spacing:.1em;
 text-transform:uppercase;color:var(--ink3);font-weight:600;border-bottom:1px solid var(--line);white-space:nowrap}
.tbl td{padding:6px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
.tbl tr:last-child td{border-bottom:none}
.tbl .n{font-variant-numeric:tabular-nums;text-align:right}
.tbl .c{color:var(--call)}.tbl .p{color:var(--put)}
.st{font-size:10px;letter-spacing:.06em;padding:2px 7px;border:1px solid}
.st.ok{color:var(--call);border-color:var(--call)}
.st.warn{color:var(--warn);border-color:var(--warn)}
.st.bad{color:var(--ink3);border-color:var(--line)}
.verdict{font-size:13.5px;line-height:1.6;padding:12px 15px;margin:14px 0 0;
 border-left:2px solid var(--line);background:var(--panel2);color:var(--ink2);max-width:78ch}
.verdict.neg{border-color:var(--violet)}
.verdict.pos{border-color:var(--gold)}
.verdict.warn{border-color:var(--warn)}
.verdict b{color:var(--ink)}
.void{color:var(--ink3);font-family:var(--mono);font-size:12px;margin:6px 0}
.declara{font-size:12px;line-height:1.5;color:var(--ink2);margin:0 0 9px;max-width:96ch;
 border-left:2px solid var(--warn);padding:7px 11px;background:var(--panel2)}
.declara b{color:var(--ink)}
.cav{margin-top:22px;border-top:1px solid var(--line);padding-top:12px}
.cav summary{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;
 color:var(--ink3);cursor:pointer}
.cav summary:focus-visible{outline:1px solid var(--gold);outline-offset:3px}
.cav ul{margin:10px 0 0;padding-left:20px;color:var(--ink2);font-size:13px;max-width:82ch}
.cav li{margin-bottom:6px}
.doct h2{font-size:clamp(24px,4vw,36px)}
.curve{display:flex;flex-direction:column;gap:5px;font-family:var(--mono);font-size:11.5px;margin:6px 0 4px}
.cb{display:grid;grid-template-columns:26px 1fr 44px 62px;gap:9px;align-items:center}
.cb .ct{color:var(--ink3);text-align:right}
.cbar{background:var(--panel2);border:1px solid var(--line);height:15px}
.cbar div{height:100%;background:var(--gold);opacity:.75}
.cb .cp{font-variant-numeric:tabular-nums;text-align:right}
.cb .cn{color:var(--ink3);font-variant-numeric:tabular-nums}
.foot{border-top:1px solid var(--line);margin-top:34px;padding-top:16px}
.foot p{font-family:var(--mono);font-size:11.5px;color:var(--ink3);margin:0;max-width:76ch}
code{font-family:var(--mono);font-size:.92em;color:var(--ink)}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
@media print{
 :root{--ground:#fff;--panel:#fff;--panel2:#fff;--line:#999;--ink:#000;--ink2:#000;
   --ink3:#333;--gold:#000;--violet:#000;--call:#000;--put:#000;--warn:#000;}
 body{background:#fff;color:#000;font-size:6.9pt;line-height:1.28}
 .wrap{max-width:100%;padding:0}
 .nav,.stamp,.cav,.foot{display:none}
 .top{border-bottom:1pt solid #000;padding-bottom:2.5pt;margin-bottom:4pt}
 .kicker{font-size:6.4pt;margin:0;color:#000;display:inline}
 h1{font-size:12pt;margin:0;display:inline;margin-left:6pt}
 .lede{font-size:6.6pt;margin:1pt 0 0;max-width:none;color:#000}
 /* una hoja de papel por ticker: el arbol jamas se parte */
 .sheet{border:.75pt solid #000;padding:4pt;margin:0;background:#fff;
   break-inside:avoid;page-break-inside:avoid}
 .sheet+.sheet{break-before:page;page-break-before:always}
 .sh{padding-bottom:2pt;margin-bottom:4pt;border-bottom:.5pt solid #999}
 .ord{font-size:6.2pt;color:#333}
h2{font-size:11.5pt;margin:0 0 1pt}.sub{font-size:6.4pt;color:#000}
h3{font-size:6.8pt;color:#000;border-bottom:.5pt solid #999;margin:4.5pt 0 2.5pt;padding-bottom:1pt}
 .hint{color:#333}
 .stats{grid-template-columns:repeat(4,1fr);gap:0;border:.5pt solid #999;background:#fff;margin-bottom:3pt}
 .stat{background:#fff;border-right:.5pt solid #999;border-bottom:.5pt solid #999;padding:1.8pt 4pt;gap:0}
.sv{font-size:8.6pt}.sl,.sn{font-size:6.1pt;color:#333}
 .reg.neg,.reg.pos{color:#000;font-weight:700}
 .two{grid-template-columns:1fr 1fr;gap:6pt;margin-top:2pt}
 .tree{font-size:6.7pt}
 .tree .why{font-size:6.3pt;color:#000}.tree li{padding:1.1pt 0}
 .tree li{grid-template-columns:13px 50px 42px 1fr}
 .tree b{font-size:7.6pt}.tree .dd{font-size:6.1pt}
 .ladder{font-size:6.5pt}.ladder .row{padding:1.1pt 4pt;gap:5px}
 .ladder .k{min-width:52px}.ladder .lab{min-width:78px}
 .chip{border-color:#000;color:#000;font-size:6pt;padding:0 3pt}
 .ladder .row.spot{background:#eee;border-left:1pt solid #000}
 .tree .node{background:#eee;border-left:1pt solid #000;margin:2pt -5pt;padding:3pt 5pt}
 .tree li,.ladder .row{break-inside:avoid;page-break-inside:avoid}
 /* el perfil escala POR ANCHO: con height fija el viewBox se encoge a una tira ilegible */
 .prof{background:#fff;border:.5pt solid #999;width:100%;height:auto;max-height:82mm}
 /* gris = nada: calls HUECAS, puts MACIZAS. La forma distingue, no el color */
 .prof .pos{fill:#fff;stroke:#000;stroke-width:.6}.prof .neg{fill:#000;stroke:none}
 /* el viewBox mide 560u en ~88mm: 8.5u seria 3.8pt en papel, ilegible */
 .prof .klab{font-size:12px}.prof .axlab{font-size:11px}.prof .lvlab{font-size:12px}
 .prof .klab,.prof .axlab,.prof .lvlab{fill:#000}
 .prof .ax{stroke:#000}
 .prof .spotl{stroke:#000;stroke-dasharray:5 2}
 .prof .flipl{stroke:#000;stroke-dasharray:1 2}
 .prof .spotlt,.prof .fliplt{fill:#000}
 .verdict{background:#fff;border-left:1pt solid #000;font-size:6.4pt;padding:2.5pt 4pt;margin:3pt 0 0;
   max-width:none;break-inside:avoid}
 .void{font-size:6.3pt;color:#333}
 .declara{font-size:6pt;background:#fff;border-left:1pt solid #000;padding:2pt 4pt;
   margin:0 0 2.5pt;max-width:none;color:#000;break-inside:avoid}
 .scroll{overflow:visible;border:.5pt solid #999;break-inside:avoid}
 .tbl{font-size:6.3pt}
 .tbl th{background:#eee;color:#000;padding:1.4pt 4pt;font-size:5.8pt}
 .tbl td{padding:1.1pt 4pt;border-bottom:.25pt solid #ccc}
 /* CALL/PUT se leen por la ETIQUETA de texto y el grosor, jamas por el color */
 .tbl .c,.tbl .p{color:#000}.tbl .c{font-weight:700}
 .st{font-size:5.8pt;padding:0 3pt}
 .st.ok,.st.warn,.st.bad{color:#000;border-color:#000}
 .st.ok{font-weight:700}.st.bad{border-style:dotted}
 .doct{break-before:page;page-break-before:always}
 .doct h2{font-size:12pt}
 /* trama en vez de macizo: la barra se lee igual y gasta un tercio de tinta */
 .cbar{border:.5pt solid #999;height:9pt}
 .cbar div{background:repeating-linear-gradient(90deg,#000 0 .5pt,#fff .5pt 2.5pt);opacity:1}
 .curve{font-size:6.8pt}
 @page{margin:11mm 9mm}
}

</style>
'''

if __name__ == "__main__":
    main()
