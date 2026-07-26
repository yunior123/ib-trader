#!/usr/bin/env python3
"""Hoja diaria de apertura: gráfico 15m + árbol + muros + flujo firmado, por ticker."""
import json, os, sys, html, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TREES = os.path.join(ROOT, "data", "trees")
ORDER = ["QQQ", "NVDA", "SMH", "MU", "AAPL", "MSFT"]


def n(x, d=2):
    return "—" if x is None else f"{x:,.{d}f}".replace(",", " ")


def usd(x):
    if x is None:
        return "—"
    a = abs(x)
    for div, s in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{'−' if x < 0 else '+'}{a/div:.1f} {s}"
    return f"{x:+.0f}"


def oi(x):
    return "—" if x is None else f"{int(x):,}".replace(",", " ")


def candles_svg(d):
    """Velas 15m + BB + muros + flip. Eje por VELAS; los niveles se dibujan, no mandan."""
    bars = d.get("bars15") or []
    if len(bars) < 5:
        return '<p class="void">Sin barras de 15m.</p>'
    t = d["arbol"]
    W, H, PL, PR, PT, PB = 720, 300, 6, 62, 10, 20
    lo = min(b[3] for b in bars)
    hi = max(b[2] for b in bars)
    pad = (hi - lo) * 0.06 or 1.0
    lo, hi = lo - pad, hi + pad
    y = lambda p: PT + (hi - p) / (hi - lo) * (H - PT - PB)
    bw = (W - PL - PR) / len(bars)
    o = [f'<svg viewBox="0 0 {W} {H}" class="cnd" role="img" aria-label="Velas de 15 minutos">']
    for i, b in enumerate(bars):
        x = PL + i * bw + bw / 2
        up = b[4] >= b[1]
        c = "cu" if up else "cd"
        o.append(f'<line x1="{x:.1f}" y1="{y(b[2]):.1f}" x2="{x:.1f}" y2="{y(b[3]):.1f}" class="wk {c}"/>')
        y1, y2 = y(max(b[1], b[4])), y(min(b[1], b[4]))
        o.append(f'<rect x="{x-bw*0.34:.1f}" y="{y1:.1f}" width="{max(1,bw*0.68):.1f}" '
                 f'height="{max(1,y2-y1):.1f}" class="bd {c}"/>')
    bbv = d.get("bb15")
    if bbv:
        for k, cls in (("up", "bbl"), ("mid", "bbm"), ("lo", "bbl")):
            if lo <= bbv[k] <= hi:
                o.append(f'<line x1="{PL}" y1="{y(bbv[k]):.1f}" x2="{W-PR}" y2="{y(bbv[k]):.1f}" class="{cls}"/>')
    for key, cls, lab in (("call_wall", "lvc", "CW"), ("put_wall", "lvp", "PW"),
                          ("flip", "lvf", "flip"), ("abs_wall", "lva", "POC")):
        v = t.get(key)
        if v is None or not (lo <= v <= hi):
            continue
        kind = t.get(key + "_kind")
        tag = " PIN" if kind == "pin" else " TRAMP" if kind == "trampilla" else ""
        o.append(f'<line x1="{PL}" y1="{y(v):.1f}" x2="{W-PR}" y2="{y(v):.1f}" class="{cls}"/>'
                 f'<text x="{W-PR+3}" y="{y(v)+3:.1f}" class="lvt {cls}t">{lab} {v:g}{tag}</text>')
    px = d.get("px_ultimo")
    if px and lo <= px <= hi:
        o.append(f'<line x1="{PL}" y1="{y(px):.1f}" x2="{W-PR}" y2="{y(px):.1f}" class="pxl"/>'
                 f'<text x="{W-PR+3}" y="{y(px)+3:.1f}" class="lvt pxt">{px:,.2f}</text>')
    t0 = dt.datetime.fromtimestamp(bars[0][0]).strftime("%d-%m %H:%M")
    t1 = dt.datetime.fromtimestamp(bars[-1][0]).strftime("%d-%m %H:%M")
    o.append(f'<text x="{PL}" y="{H-5}" class="ax">{t0}</text>'
             f'<text x="{W-PR}" y="{H-5}" class="ax" text-anchor="end">{t1} · 15m</text></svg>')
    return "".join(o)


def sheet(d, i):
    t, f = d["arbol"], d.get("flujo")
    px, bbv = d["px_ultimo"], d.get("bb15")
    reg = t.get("regime")
    lado = None if not (px and t.get("flip")) else ("POS" if px >= t["flip"] else "NEG")
    stats = [
        ("precio", n(px), "último cierre de 15m"),
        ("régimen vivo", f'<span class="rg {(lado or "").lower()}">{lado or "—"}</span>',
         f'flip {n(t.get("flip"))}'),
        ("muro calls", n(t.get("call_wall")), t.get("call_wall_kind") or "sin régimen"),
        ("muro puts", n(t.get("put_wall")), t.get("put_wall_kind") or "sin régimen"),
        ("%B 15m", "—" if not bbv else f'{bbv["pctb"]:.2f}',
         "—" if not bbv else f'{n(bbv["lo"])} – {n(bbv["up"])}'),
        ("ATR 15m", "—" if d.get("atr15_pct") is None else f'{d["atr15_pct"]:.2f}%', "por vela"),
        ("flujo firmado", usd(None if not f else f["signed_premium"]),
         "viernes · agresor (ask−bid)"),
        ("P/C del viernes", n(t.get("viernes_pc_oi")),
         f'{oi(t.get("viernes_puts_oi"))}p / {oi(t.get("viernes_calls_oi"))}c'),
        ("perp 24/7", "—" if not d.get("perp") else n(d["perp"]["px"]),
         "sin perp" if not d.get("perp") else
         f'gap {d["perp"]["gap_pct"]:+.2f}% · vol {d["perp"]["vol24h_usd"]/1e6:.1f}M'),
    ]
    cards = "".join(f'<div class="st"><span class="sl">{html.escape(l)}</span>'
                    f'<span class="sv">{v}</span><span class="sn">{html.escape(str(x))}</span></div>'
                    for l, v, x in stats)
    ram = "".join(
        f'<li><b>{html.escape(r["gatillo"])}</b>'
        f'<span class="lee">{html.escape(r["lee"])}</span>'
        f'<span class="inv">lo invalida: {html.escape(r["invalida"])}</span></li>'
        for r in d.get("ramas") or [])
    surv = [x for x in t.get("supervivientes") or [] if x["estado"] == "SOBREVIVE"][:5]
    srows = "".join(
        f'<tr><td class="{"c" if x["lado"]=="C" else "p"}">{"CALL" if x["lado"]=="C" else "PUT"}</td>'
        f'<td class="nn">{x["strike"]:g}</td><td class="nn">{oi(x["oi_ahora"])}</td>'
        f'<td class="nn">#{x["rank_ahora"]}</td><td class="nn">{oi(x["oi_viernes"])}</td></tr>'
        for x in surv) or '<tr><td colspan="5" class="void">ninguno sobrevive en el top 6</td></tr>'
    tops = "".join(
        f'<tr><td class="nn c">{c["strike"]:g}</td><td class="nn">{oi(c["oi"])}</td>'
        f'<td class="nn p">{p["strike"]:g}</td><td class="nn">{oi(p["oi"])}</td></tr>'
        for c, p in zip((t.get("viernes_top_calls") or [])[:5], (t.get("viernes_top_puts") or [])[:5]))
    return f'''<section class="sh" id="{d["sym"].lower()}">
<header class="hd"><span class="ord">{i} / 6</span><h2>{d["sym"]}</h2>
<p class="sub">{d["n_barras_15m"]} velas de 15m · cadena al viernes {t["viernes"]} ·
{t["n_solo_viernes"]} contratos ese día</p></header>
<div class="stats">{cards}</div>
<div class="chart">{candles_svg(d)}</div>
<div class="two">
<div><h3>Ramas de la apertura</h3><ul class="ram">{ram}</ul>
<p class="warn"><b>Sin probabilidad de apertura.</b> {html.escape(d["apertura_medida"]["detalle"])}</p></div>
<div><h3>Muros que sobreviven</h3>
<div class="sc"><table><thead><tr><th>lado</th><th>strike</th><th>OI hoy</th><th>rango</th><th>OI vie</th></tr></thead>
<tbody>{srows}</tbody></table></div>
<h3>Cadena del viernes {t["viernes"]}</h3>
<div class="sc"><table><thead><tr><th colspan="2">CALLS</th><th colspan="2">PUTS</th></tr>
<tr><th>strike</th><th>OI</th><th>strike</th><th>OI</th></tr></thead><tbody>{tops}</tbody></table></div>
</div></div></section>'''


def main():
    p = os.path.join(TREES, "opening_plan.json")
    data = json.load(open(p))
    ds = [data[s] for s in ORDER if s in data]
    if not ds:
        raise RuntimeError("opening_plan.json vacío")
    nav = "".join(f'<a href="#{d["sym"].lower()}">{d["sym"]}</a>' for d in ds)
    body = "".join(sheet(d, i + 1) for i, d in enumerate(ds))
    gen = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = HEAD + f'''<div class="wrap">
<header class="top"><p class="kick">ib-trader · plan de apertura · señal-solamente</p>
<h1>Seis mapas para mañana</h1>
<p class="lede">Marco de 15 minutos, muros de la semana que entra, GEX y gamma-flip.
Cada hoja lleva las ramas con su gatillo y lo que las invalida — no una predicción.</p>
<nav>{nav}</nav>
<p class="stamp">generado {gen} · estructura de Polygon (15 min de retraso) ·
flujo firmado de Unusual Whales · <b>el print que confirma cualquier rama es de IBKR</b></p></header>
{body}
<footer><p>No es consejo financiero. Describe el libro de opciones; no predice el precio.
Sin print de IBKR no hay entrada.</p></footer></div>'''
    dest = os.path.join(TREES, "plan-apertura.html")
    open(dest, "w").write(out)
    print(dest, f"({os.path.getsize(dest)/1024:.0f} KB, {len(ds)} hojas)")


HEAD = '''<title>Plan de apertura — QQQ · NVDA · SMH · MU · AAPL · MSFT</title>
<style>
:root{--bg:#0b0e13;--pn:#121720;--pn2:#182030;--ln:#26303f;--ink:#e6e8ec;--ink2:#9aa5b8;
 --ink3:#657085;--au:#d9a441;--vi:#8d76ff;--up:#3fa87a;--dn:#cf5346;--wr:#d98b2b;
 --mo:ui-monospace,"SF Mono",Menlo,monospace;--dp:"Avenir Next Condensed","Arial Narrow",system-ui,sans-serif;}
@media (prefers-color-scheme:light){:root{--bg:#f7f6f2;--pn:#fffefc;--pn2:#eeece6;--ln:#dcd8cf;
 --ink:#171a1f;--ink2:#57606e;--ink3:#8a8f99;--au:#96690c;--vi:#5a41cf;--up:#26714f;--dn:#a63a2c;--wr:#95610f;}}
:root[data-theme="dark"]{--bg:#0b0e13;--pn:#121720;--pn2:#182030;--ln:#26303f;--ink:#e6e8ec;
 --ink2:#9aa5b8;--ink3:#657085;--au:#d9a441;--vi:#8d76ff;--up:#3fa87a;--dn:#cf5346;--wr:#d98b2b;}
:root[data-theme="light"]{--bg:#f7f6f2;--pn:#fffefc;--pn2:#eeece6;--ln:#dcd8cf;--ink:#171a1f;
 --ink2:#57606e;--ink3:#8a8f99;--au:#96690c;--vi:#5a41cf;--up:#26714f;--dn:#a63a2c;--wr:#95610f;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1140px;margin:0 auto;padding:clamp(18px,4vw,48px) clamp(13px,3vw,26px) 56px}
.top{border-bottom:2px solid var(--ln);padding-bottom:20px;margin-bottom:30px}
.kick{font-family:var(--mo);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--au);margin:0 0 9px}
h1{font-family:var(--dp);font-size:clamp(34px,6.5vw,60px);line-height:.96;margin:0 0 11px;font-weight:600;text-wrap:balance}
.lede{max-width:60ch;color:var(--ink2);margin:0 0 16px;font-size:16.5px}
nav{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:13px}
nav a{font-family:var(--mo);font-size:12px;text-decoration:none;color:var(--ink2);
 border:1px solid var(--ln);padding:5px 11px;background:var(--pn)}
nav a:hover,nav a:focus-visible{background:var(--au);color:var(--bg);border-color:var(--au);outline:none}
.stamp{font-family:var(--mo);font-size:11.5px;color:var(--ink3);margin:0;max-width:84ch}
.stamp b{color:var(--ink2)}
.sh{border:1px solid var(--ln);background:var(--pn);padding:clamp(15px,2.3vw,26px);margin-bottom:28px;scroll-margin-top:14px}
.hd{border-bottom:1px solid var(--ln);padding-bottom:12px;margin-bottom:16px}
.ord{font-family:var(--mo);font-size:10.5px;letter-spacing:.16em;color:var(--ink3)}
h2{font-family:var(--dp);font-size:clamp(28px,5vw,42px);margin:2px 0 5px;font-weight:600}
.sub{font-family:var(--mo);font-size:12px;color:var(--ink2);margin:0}
h3{font-family:var(--mo);font-size:11.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--au);margin:22px 0 9px;font-weight:600}
h3:first-child{margin-top:0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(142px,1fr));gap:1px;background:var(--ln);border:1px solid var(--ln);margin-bottom:16px}
.st{background:var(--pn2);padding:10px 12px;display:flex;flex-direction:column;gap:2px}
.sl{font-family:var(--mo);font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3)}
.sv{font-family:var(--mo);font-size:19px;font-variant-numeric:tabular-nums}
.sn{font-family:var(--mo);font-size:10.5px;color:var(--ink2)}
.rg.neg{color:var(--vi)}.rg.pos{color:var(--au)}
.chart{overflow-x:auto;border:1px solid var(--ln);background:var(--pn2);margin-bottom:6px}
.cnd{width:100%;min-width:560px;height:auto;display:block}
.cnd .cu{fill:var(--up);stroke:var(--up)}.cnd .cd{fill:var(--dn);stroke:var(--dn)}
.cnd .wk{stroke-width:1}.cnd .bd{stroke-width:.5}
.cnd .bbl{stroke:var(--ink3);stroke-width:.8;stroke-dasharray:2 3;opacity:.7}
.cnd .bbm{stroke:var(--ink3);stroke-width:.8;opacity:.45}
.cnd .lvc{stroke:var(--dn);stroke-width:1;stroke-dasharray:5 3}
.cnd .lvp{stroke:var(--up);stroke-width:1;stroke-dasharray:5 3}
.cnd .lvf{stroke:var(--vi);stroke-width:1;stroke-dasharray:3 3}
.cnd .lva{stroke:var(--au);stroke-width:1;stroke-dasharray:5 3}
.cnd .pxl{stroke:var(--ink);stroke-width:1}
.cnd .lvt{font-family:var(--mo);font-size:8.5px}
.cnd .lvct{fill:var(--dn)}.cnd .lvpt{fill:var(--up)}.cnd .lvft{fill:var(--vi)}
.cnd .lvat{fill:var(--au)}.cnd .pxt{fill:var(--ink)}
.cnd .ax{font-family:var(--mo);font-size:8.5px;fill:var(--ink3)}
.two{display:grid;grid-template-columns:1.15fr 1fr;gap:24px;margin-top:6px}
@media(max-width:900px){.two{grid-template-columns:1fr}}
.ram{list-style:none;margin:0;padding:0}
.ram li{border-left:2px solid var(--ln);padding:8px 0 8px 11px;margin-bottom:10px}
.ram b{font-family:var(--mo);font-size:12.5px;display:block;margin-bottom:3px}
.ram .lee{display:block;color:var(--ink2);font-size:13.5px;line-height:1.5}
.ram .inv{display:block;color:var(--ink3);font-size:11.5px;font-style:italic;margin-top:4px}
.warn{font-size:13px;line-height:1.55;padding:11px 14px;margin:14px 0 0;border-left:2px solid var(--wr);
 background:var(--pn2);color:var(--ink2);max-width:74ch}
.warn b{color:var(--ink)}
.sc{overflow-x:auto;border:1px solid var(--ln);margin-bottom:4px}
table{width:100%;border-collapse:collapse;font-family:var(--mo);font-size:11.5px}
th{background:var(--pn2);text-align:left;padding:6px 9px;font-size:10px;letter-spacing:.1em;
 text-transform:uppercase;color:var(--ink3);border-bottom:1px solid var(--ln);white-space:nowrap}
td{padding:5px 9px;border-bottom:1px solid var(--ln);white-space:nowrap}
tr:last-child td{border-bottom:none}
.nn{font-variant-numeric:tabular-nums;text-align:right}
.c{color:var(--up)}.p{color:var(--dn)}
.void{color:var(--ink3);font-style:italic;text-align:center}
footer{border-top:1px solid var(--ln);margin-top:30px;padding-top:15px}
footer p{font-family:var(--mo);font-size:11.5px;color:var(--ink3);margin:0;max-width:74ch}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
'''

if __name__ == "__main__":
    main()
