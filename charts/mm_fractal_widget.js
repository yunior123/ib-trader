"use strict";
// Disclosed London-only proxy for the OMM/DMM geometry in the supplied screenshot.
// It consumes the same LSE gamma×volume snapshot as the London heatmap. It is not the
// proprietary Russell Capital Group calculation and never claims dealer inventory.
(function () {
  const CSS = `
  #wgt-mmfractal .wgbody{padding:0;overflow:auto}.mmfw{padding:9px;color:#dbe4f3;font-size:11px}
  .mmftop{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:9px}.mmfp{padding:3px 7px;border-radius:5px;background:#202738;color:#aab6ca;font-weight:650}
  .mmfp.bull{background:#123b31;color:#64d6b1}.mmfp.bear{background:#442127;color:#ff7b86}.mmfp.wait{background:#2a2113;color:#e0b64a}
  .mmflevels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin:6px 0 9px}
  .mmflvl{border:1px solid #29344a;border-radius:5px;padding:6px 7px;background:#111722}.mmflvl b{display:block;font-size:9px;color:#77839a;letter-spacing:.5px}.mmflvl span{display:block;margin-top:2px;font:700 14px ui-monospace,SFMono-Regular,monospace}
  .mmflvl.gl span{color:#41d67b}.mmflvl.pml span{color:#ff6572}.mmftrack{height:13px;background:#0e1420;border:1px solid #2c374d;border-radius:8px;position:relative;margin:18px 7px 22px}
  .mmfzone{position:absolute;top:1px;bottom:1px;background:rgba(255,179,0,.18);border-left:1px solid #ffb300;border-right:1px solid #ffb300}
  .mmfmark{position:absolute;top:-7px;width:2px;height:25px;background:#e6ebf5}.mmfmark i{position:absolute;top:25px;left:50%;transform:translateX(-50%);font-style:normal;font-size:8px;color:#8793a8;white-space:nowrap}
  .mmfmark.spot{background:#4e8cff;height:28px;top:-9px}.mmfmark.spot i{top:-12px;color:#6da0ff;font-weight:700}.mmfmark.gl{background:#41d67b}.mmfmark.pml{background:#ff6572}
  .mmfquad{display:grid;grid-template-columns:1fr 1fr;gap:4px}.mmfq{background:#111722;border:1px solid #29344a;border-radius:4px;padding:6px}.mmfq b{display:block;color:#7e8ba2;font-size:9px}.mmfq span{font:700 12px ui-monospace,SFMono-Regular,monospace}.mmfq.call span{color:#64d6b1}.mmfq.put span{color:#ff7b86}
  .mmffoot{margin-top:8px;padding-top:6px;border-top:1px solid #252d3c;color:#667287;font-size:9px;line-height:1.4}.mmfempty{padding:28px 12px;text-align:center;color:#718096;line-height:1.5}
  .mmfspin{display:inline-block;width:10px;height:10px;border:2px solid #33405a;border-top-color:#5b8cff;border-radius:50%;animation:mmfsp .7s linear infinite;vertical-align:-2px;margin-right:5px}@keyframes mmfsp{to{transform:rotate(360deg)}}`;
  const style = document.createElement("style"); style.textContent = CSS; document.head.appendChild(style);
  const body = () => document.querySelector("#wgt-mmfractal .wgbody");
  const sub = () => document.querySelector("#wgt-mmfractal .wgsub");
  const POLL_MS = 10000;
  let data = null, seq = 0, lastSym = null, fetchTimer = null, clockTimer = null;
  const symNow = () => { try { return String(curSym || "").toUpperCase().replace(/USDT$/, ""); } catch(e){ return ""; } };
  const px = v => v == null ? "—" : "$" + (+v).toFixed(2);
  const vol = v => { v=+(v||0); return v>=1e6?(v/1e6).toFixed(2)+"M":v>=1e3?(v/1e3).toFixed(1)+"K":v.toFixed(0); };
  const remain = d => { const n=Math.max(0,Math.ceil((d?.next_refresh_ts||0)-Date.now()/1000)); return `↻ ${String(Math.floor(n/60)).padStart(2,"0")}:${String(n%60).padStart(2,"0")}`; };
  const age = d => { const ts=d?.active?.source_ts||d?.asof||0,n=Math.max(0,Math.round(Date.now()/1000-ts)); return n<90?n+"s":Math.round(n/60)+"m"; };
  function empty(msg,label){ const b=body();if(b)b.innerHTML=`<div class="mmfempty">${msg}</div>`;const s=sub();if(s)s.textContent=label||"sin dato";data=null; }
  function position(v, lo, hi){ return hi>lo?Math.max(0,Math.min(100,100*(v-lo)/(hi-lo))):50; }
  function draw(d){
    const b=body(); if(!b)return; const a=d.active,q=a?.quadrants||{};
    if(!a){empty("Esperando el primer snapshot OMM/DMM de London.","LSE · esperando");return;}
    const lo=Math.min(a.floor,a.green_line,a.pml,a.ceiling,a.spot),hi=Math.max(a.floor,a.green_line,a.pml,a.ceiling,a.spot);
    const bias=(d.bias||"DATA").toLowerCase(), omm=d.omm_pivot, dmm=d.dmm_magnet;
    const z0=position(a.dead_zone_low,lo,hi),z1=position(a.dead_zone_high,lo,hi);
    const mark=(v,label,cls="")=>`<span class="mmfmark ${cls}" style="left:${position(v,lo,hi)}%"><i>${label}</i></span>`;
    b.innerHTML=`<div class="mmfw"><div class="mmftop"><span class="mmfp">${a.sym}</span><span class="mmfp ${bias}">${d.bias}</span><span class="mmfp">OMM ${px(omm)}</span><span class="mmfp ${dmm==null?"wait":""}">DMM ${dmm==null?"espera 09:45":px(dmm)}</span><span class="mmfp">${remain(d)}</span></div>
      <div class="mmflevels"><div class="mmflvl"><b>CEILING</b><span>${px(a.ceiling)}</span></div><div class="mmflvl"><b>FLOOR</b><span>${px(a.floor)}</span></div><div class="mmflvl gl"><b>GREEN LINE</b><span>${px(a.green_line)}</span></div><div class="mmflvl pml"><b>PML · VOLUME PAIN</b><span>${px(a.pml)}</span></div></div>
      <div class="mmftrack"><span class="mmfzone" style="left:${z0}%;width:${Math.max(1,z1-z0)}%"></span>${mark(a.floor,"F")}${mark(a.green_line,"GL","gl")}${mark(a.pml,"PML","pml")}${mark(a.ceiling,"C")}${mark(a.spot,"SPOT","spot")}</div>
      <div class="mmfquad"><div class="mmfq put"><b>PUTS ≥ GL</b><span>${vol(q.puts_at_or_above_green)}</span></div><div class="mmfq put"><b>PUTS &lt; GL</b><span>${vol(q.puts_below_green)}</span></div><div class="mmfq call"><b>CALLS ≥ GL</b><span>${vol(q.calls_at_or_above_green)}</span></div><div class="mmfq call"><b>CALLS &lt; GL</b><span>${vol(q.calls_below_green)}</span></div></div>
      <div class="mmffoot">LSE gamma×volume q10/q50/q90 + minimizador de payout por volumen. Geometría OMM/DMM pública; proxy divulgado, no fórmula propietaria ni inventario dealer. Contexto, no gatillo.</div></div>`;
    const s=sub();if(s)s.textContent=`LSE · ${d.active_lane} · ${remain(d)} · fuente ${age(d)}`;
  }
  function clock(){ if(data&&(!window.cockpitWidgetOpen||window.cockpitWidgetOpen("mmfractal")))draw(data); }
  async function tick(){
    if(window.cockpitWidgetOpen&&!window.cockpitWidgetOpen("mmfractal"))return;
    const sym=symNow(); if(!sym){empty("Sin símbolo activo.");return;}
    if(!(window.chartIsLondonOnly&&window.chartIsLondonOnly())){empty("Disponible únicamente en London-only.","London-only");return;}
    if(sym!==lastSym){lastSym=sym;data=null;const b=body();if(b)b.innerHTML=`<div class="mmfempty"><span class="mmfspin"></span>Cargando ${sym} desde London…</div>`;}
    const mine=++seq;
    try{const r=await fetch(`/data/gex_heatmap_${sym.toLowerCase()}.json`,{cache:"no-store"});if(mine!==seq||sym!==symNow())return;const d=await r.json();
      if(!r.ok||d.src!=="lse"||!d.mm_fractal){empty(`Esperando fractal London para ${sym}.`,`LSE · esperando`);return;}data=d.mm_fractal;draw(data);
    }catch(e){if(mine===seq)empty("Error leyendo el snapshot London: "+e.message,"LSE · error");}
  }
  function start(){tick();fetchTimer=setInterval(tick,POLL_MS);clockTimer=setInterval(clock,1000);}
  window.addEventListener("cockpitWidgetsVisibility",e=>{if(e.detail?.visible&&window.cockpitWidgetOpen("mmfractal"))tick();});
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start);else start();
  window.mmFractalRefresh=tick;
})();
