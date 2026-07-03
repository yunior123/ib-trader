// Cockpit: seis graficos, como las seis ventanas de la .app. Sin prosa.
export const COCKPIT = ["QQQ", "SPY", "NVDA", "TSLA", "SMH", "SPCX"];

export function pagina({ datos, cuota }) {
  const gb = x => (x / 1073741824).toFixed(1);
  const pie = cuota ? `LSE ${gb(cuota.bytes_used_month)}/${gb(cuota.bytes_cap_month)} GB` : "LSE —";
  return `<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ib-trader</title>
<style>
:root{--bg:#0a0c0f;--panel:#101318;--line:#1e232c;--fg:#e6e9ef;--fg2:#8b93a3;
      --up:#26a69a;--down:#ef5350;--call:#ef5350;--put:#26a69a;--flip:#f5a623;--pain:#7c8496}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font:13px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow:hidden}
#rejilla{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(2,1fr);
         gap:1px;background:var(--line);height:100vh;padding-bottom:22px}
.v{background:var(--panel);position:relative;display:flex;flex-direction:column;min-width:0;min-height:0}
.cab{display:flex;align-items:baseline;gap:8px;padding:6px 9px;border-bottom:1px solid var(--line);flex:0 0 auto}
.sym{font:700 14px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.04em}
.px{font:600 13px/1 ui-monospace,Menlo,monospace}
.ch{font:600 11px/1 ui-monospace,Menlo,monospace}
.reg{margin-left:auto;font:700 9px/1.7 ui-monospace,Menlo,monospace;letter-spacing:.08em;
     padding:0 6px;border-radius:3px;border:1px solid currentColor}
.up{color:var(--up)}.down{color:var(--down)}
canvas{flex:1;width:100%;display:block;min-height:0}
.niv{display:flex;gap:10px;padding:4px 9px 6px;font:600 10px/1.4 ui-monospace,Menlo,monospace;
     color:var(--fg2);border-top:1px solid var(--line);flex:0 0 auto;flex-wrap:wrap}
.niv b{font-weight:700}
.vacio{display:flex;align-items:center;justify-content:center;height:100%;color:var(--fg2);
       font:600 11px/1 ui-monospace,Menlo,monospace}
#pie{position:fixed;bottom:0;left:0;right:0;height:22px;background:var(--panel);
     border-top:1px solid var(--line);display:flex;align-items:center;gap:14px;padding:0 10px;
     font:500 10px/1 ui-monospace,Menlo,monospace;color:var(--fg2)}
#pie a{color:var(--fg2)}
#sw button{background:transparent;border:1px solid var(--line);color:var(--fg2);cursor:pointer;
  font:600 10px/1 ui-monospace,Menlo,monospace;padding:3px 8px;border-radius:3px;margin-right:3px}
#sw button.on{color:var(--fg);border-color:var(--fg2);background:#1a1f28}
.sp{font:600 10px/1 ui-monospace,Menlo,monospace;color:var(--fg2)}
@media(max-width:900px){#rejilla{grid-template-columns:repeat(2,1fr);grid-template-rows:repeat(3,1fr)}}
@media(max-width:620px){#rejilla{grid-template-columns:1fr;grid-template-rows:repeat(6,minmax(180px,1fr));
  height:auto;overflow-y:auto}body{overflow:auto}}
</style></head><body>
<div id="rejilla"></div>
<div id="pie"><span id="reloj"></span>
  <span id="sw"><button id="b-cash" class="on">acciones</button><button id="b-perp">perp 24/7</button></span>
  <span id="estado" class="mut"></span><span>${pie}</span>
  <span><b style="color:var(--call)">━</b> call wall &nbsp;<b style="color:var(--put)">━</b> put wall
  &nbsp;<b style="color:var(--flip)">┄</b> flip &nbsp;<b style="color:var(--pain)">┄</b> max pain</span>
  <span style="margin-left:auto"><a href="/api/niveles">niveles</a> · <a href="/api/flujo">flujo</a> · <a href="/api/estado">estado</a></span>
</div>
<script>
const DATOS = ${JSON.stringify(datos)};

function dibujar(cv, d) {
  const dpr = Math.min(devicePixelRatio || 1, 2);
  const w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return;
  cv.width = w * dpr; cv.height = h * dpr;
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const velas = d.barras || [];
  if (!velas.length) return;

  const ML = 0, MR = 52, MT = 6, MB = 6;           // el eje va a la derecha, como en el chart
  const gw = w - ML - MR, gh = h - MT - MB;

  // El rango lo mandan LAS VELAS. Un nivel solo entra si cabe sin aplastarlas: si el muro esta
  // lejos, meterlo dejaria el precio como una raya en el borde y el grafico no diria nada. Los
  // niveles que no caben siguen escritos bajo el grafico, que es donde se leen igual de bien.
  const bajo = Math.min(...velas.map(v => v.l)), alto = Math.max(...velas.map(v => v.h));
  const rango = Math.max(alto - bajo, alto * 0.0008);      // suelo: en after-hours el rango es casi 0
  let lo = bajo - rango * 0.35, hi = alto + rango * 0.35;
  for (const n of [d.call_wall, d.put_wall, d.flip, d.max_pain]) {
    if (n && n > bajo - rango * 2 && n < alto + rango * 2) { lo = Math.min(lo, n); hi = Math.max(hi, n); }
  }
  const margen = (hi - lo) * 0.04;
  lo -= margen; hi += margen;
  const y = p => MT + gh - ((p - lo) / (hi - lo)) * gh;

  // rejilla + eje de precios
  // Los decimales los manda el RANGO, no el precio: con 0 decimales un rango de 2 $ en QQQ
  // repetia "714, 714, 713" y el eje no decia nada.
  const amplitud = hi - lo;
  const dec = amplitud < 1 ? 3 : amplitud < 10 ? 2 : amplitud < 100 ? 1 : 0;
  g.font = "10px ui-monospace,Menlo,monospace";
  g.textAlign = "left"; g.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {
    const p = lo + (hi - lo) * (i / 4), yy = y(p);
    g.strokeStyle = "#171b22"; g.lineWidth = 1;
    g.beginPath(); g.moveTo(ML, yy + .5); g.lineTo(ML + gw, yy + .5); g.stroke();
    g.fillStyle = "#8b93a3"; g.fillText(p.toFixed(dec), ML + gw + 6, yy);
  }

  // velas
  const paso = gw / velas.length, cuerpo = Math.max(1, Math.min(paso * 0.7, 7));
  velas.forEach((v, i) => {
    const x = ML + i * paso + paso / 2, sube = v.c >= v.o;
    g.strokeStyle = g.fillStyle = sube ? "#26a69a" : "#ef5350";
    g.beginPath(); g.moveTo(x, y(v.h)); g.lineTo(x, y(v.l)); g.stroke();
    const yo = y(v.o), yc = y(v.c);
    g.fillRect(x - cuerpo / 2, Math.min(yo, yc), cuerpo, Math.max(1, Math.abs(yc - yo)));
  });

  // niveles
  const linea = (p, color, punteada, etiqueta) => {
    if (!p || p < lo || p > hi) return;
    const yy = y(p);
    g.save();
    g.strokeStyle = color; g.lineWidth = 1;
    if (punteada) g.setLineDash([4, 3]);
    g.beginPath(); g.moveTo(ML, yy + .5); g.lineTo(ML + gw, yy + .5); g.stroke();
    g.restore();
    g.fillStyle = color; g.textAlign = "left";
    g.fillText(etiqueta, ML + 4, yy - 6);
  };
  linea(d.put_wall, "#26a69a", false, "PW " + d.put_wall);
  linea(d.call_wall, "#ef5350", false, "CW " + d.call_wall);
  linea(d.flip, "#f5a623", true, "flip " + (d.flip ? d.flip.toFixed(1) : ""));
  linea(d.max_pain, "#7c8496", true, "pain " + d.max_pain);

  // ultimo precio, marcado en el eje
  const ult = velas[velas.length - 1].c, yu = y(ult);
  g.fillStyle = "#e6e9ef";
  g.fillRect(ML + gw, yu - 8, MR, 16);
  g.fillStyle = "#0a0c0f"; g.textAlign = "left";
  g.fillText(ult.toFixed(Math.max(dec, 2)), ML + gw + 5, yu);
}

function pintar() {
  const r = document.getElementById("rejilla");
  r.innerHTML = "";
  for (const d of DATOS) {
    const cambio = d.barras && d.barras.length > 1
      ? (d.barras[d.barras.length - 1].c / d.barras[0].c - 1) * 100 : null;
    const sube = (cambio ?? 0) >= 0;
    const neg = (d.gex_total ?? 0) < 0;
    const el = document.createElement("div");
    el.className = "v";
    el.innerHTML =
      '<div class="cab"><span class="sym">' + d.sym + '</span>' +
      '<span class="px">' + (d.spot != null ? d.spot.toFixed(2) : "—") + '</span>' +
      (cambio == null ? "" : '<span class="ch ' + (sube ? "up" : "down") + '">' +
        (sube ? "+" : "") + cambio.toFixed(2) + '%</span>') +
      '<span class="reg ' + (neg ? "down" : "up") + '">' + (neg ? "NEG" : "POS") + '</span></div>' +
      '<canvas></canvas>' +
      '<div class="niv"><span>PW <b>' + (d.put_wall ?? "—") + '</b></span>' +
      '<span>CW <b>' + (d.call_wall ?? "—") + '</b></span>' +
      '<span>flip <b>' + (d.flip ? d.flip.toFixed(1) : "sin cruce") + '</b></span>' +
      '<span>pain <b>' + (d.max_pain ?? "—") + '</b></span>' +
      '<span>GEX <b>' + (d.gex_total == null ? "—" :
        (Math.abs(d.gex_total) >= 1e9 ? (d.gex_total / 1e9).toFixed(2) + "B"
                                      : (d.gex_total / 1e6).toFixed(0) + "M")) + '</b></span>' +
      '<span class="sp">' + (d.spread_pct != null ? "spread " + d.spread_pct.toFixed(3) + "%" : "") + '</span>' +
      '<span style="margin-left:auto">' + (d.fuente_ts ? String(d.fuente_ts).slice(11, 19) : "—") + '</span></div>';
    r.appendChild(el);
    const cv = el.querySelector("canvas");
    if (!d.barras || !d.barras.length) {
      cv.remove();
      const v = document.createElement("div");
      v.className = "vacio"; v.textContent = "sin barras";
      el.insertBefore(v, el.querySelector(".niv"));
    } else {
      requestAnimationFrame(() => dibujar(cv, d));
    }
  }
}

function reloj() {
  document.getElementById("reloj").textContent =
    new Date().toLocaleTimeString("es-ES", { timeZone: "America/New_York", hour12: false }) + " ET";
}
let DATOS_VIVOS = DATOS;
// acciones = LSE+CBOE (cierra con la bolsa) · perp = OKX (24/7, con libro). El modo se recuerda.
let MODO = (() => { try { return localStorage.getItem("ibt_modo") || "cash"; } catch { return "cash"; } })();
pintar(); reloj();
setInterval(reloj, 1000);

// Refresco EN CALIENTE: se traen los datos y se redibuja solo el lienzo. Sin recargar la pagina,
// que perdia el scroll y parpadeaba. Si una vuelta falla no se toca nada: se queda lo ultimo bueno.
async function refrescar() {
  try {
    const r = await fetch("/api/panel" + (MODO === "perp" ? "?modo=perp" : ""), { cache: "no-store" });
    if (!r.ok) return;
    const nuevos = await r.json();
    if (!Array.isArray(nuevos) || nuevos.length !== DATOS_VIVOS.length) return;
    DATOS_VIVOS = nuevos;
    const cajas = document.querySelectorAll("#rejilla .v");
    nuevos.forEach((d, i) => {
      const el = cajas[i]; if (!el) return;
      const px = el.querySelector(".px"), ch = el.querySelector(".ch");
      if (px && d.spot != null) px.textContent = d.spot.toFixed(2);
      if (ch && d.barras && d.barras.length > 1) {
        const c = (d.barras[d.barras.length - 1].c / d.barras[0].c - 1) * 100;
        ch.textContent = (c >= 0 ? "+" : "") + c.toFixed(2) + "%";
        ch.className = "ch " + (c >= 0 ? "up" : "down");
      }
      const sp = el.querySelector(".sp");
      if (sp) sp.textContent = d.spread_pct != null ? "spread " + d.spread_pct.toFixed(3) + "%" : "";
      const cv = el.querySelector("canvas");
      if (cv && d.barras && d.barras.length) dibujar(cv, d);
    });
    const p = document.getElementById("estado");
    if (p) p.textContent = "· actualizado " + new Date().toLocaleTimeString("es-ES", { hour12: false });
  } catch { /* un fallo de red no borra el grafico */ }
}
function pintarModo() {
  const bc = document.getElementById("b-cash"), bp = document.getElementById("b-perp");
  bc.className = MODO === "cash" ? "on" : "";
  bp.className = MODO === "perp" ? "on" : "";
}
function cambiar(m) {
  MODO = m;
  try { localStorage.setItem("ibt_modo", m); } catch { /* modo privado: no se recuerda, da igual */ }
  pintarModo(); refrescar();
}
document.getElementById("b-cash").onclick = () => cambiar("cash");
document.getElementById("b-perp").onclick = () => cambiar("perp");
pintarModo();
if (MODO === "perp") refrescar();
setInterval(refrescar, 5000);
addEventListener("visibilitychange", () => { if (!document.hidden) refrescar(); });
addEventListener("resize", () => {
  document.querySelectorAll("#rejilla .v").forEach((el, i) => {
    const cv = el.querySelector("canvas");
    if (cv) dibujar(cv, DATOS_VIVOS[i]);
  });
});

</script></body></html>`;
}
