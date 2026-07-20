// scan_server.cpp — REAL-TIME ticker scanner on localhost (Yunior 2026-07-10:
// "type any ticker and see the bids, tape... put it in localhost, real fast,
// prefer c++").
// ============================================================================
// C++ HTTP + Server-Sent-Events server on http://127.0.0.1:8765
//   GET /            -> embedded dark trading UI (bid x ask, tape, stats, chart)
//   GET /events      -> SSE stream: every IEX trade + top-of-book quote, pushed
//                       the instant it arrives (no polling)
//   GET /sym?s=XYZ   -> switch the live symbol (unsubscribes the old one)
// Data: Alpaca REST fast-poll via scripts/alpaca_tape_bridge.py child (the
//       fleet's proven popen-bridge pattern; keys in alpaca.env): full tape ~1s,
//       top-of-book quotes, day stats via snapshot. (The account's single free
//       Alpaca websocket is owned 24/5 by the NOK signal bot.) NOTE: full MPID
//       Level-2 depth (ARB/NSB...) requires paid feeds.
// Safe-close: SIGINT/SIGTERM kill the bridge child (own process group).
// Build: clang++ -std=c++17 -O2 -o scan_server scan_server.cpp -lcurl
// Run:   ./scan_server [SYM] [PORT]   then open http://localhost:8765
// ============================================================================
#include <arpa/inet.h>
#include <curl/curl.h>
#include <netinet/in.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

static int g_port = 8765;
static std::string g_sym = "NVDA";
static std::mutex g_mtx;                  // guards clients + child stdin
static std::vector<int> g_clients;        // SSE client fds
static FILE* g_child_in = nullptr;        // bridge stdin (SUB commands)
static pid_t g_child = -1;

// ---- symbol safety: only A-Z 0-9 . - up to 10 chars (goes into cmds/URLs)
static std::string sanitize_sym(const std::string& in) {
    std::string out;
    for (char c : in) {
        c = (char)std::toupper((unsigned char)c);
        if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' || c == '-')
            out += c;
        if (out.size() >= 10) break;
    }
    return out;
}

static void broadcast(const std::string& json) {
    std::string frame = "data: " + json + "\n\n";
    std::lock_guard<std::mutex> lk(g_mtx);
    for (auto it = g_clients.begin(); it != g_clients.end();) {
        ssize_t n = send(*it, frame.data(), frame.size(), MSG_NOSIGNAL);
        if (n <= 0) { close(*it); it = g_clients.erase(it); }
        else ++it;
    }
}

// ---- bridge child: fork/exec python alpaca_tape_bridge, pipes both ways ----
static FILE* spawn_bridge(const std::string& sym) {
    int inpipe[2], outpipe[2];             // in: us->child, out: child->us
    if (pipe(inpipe) || pipe(outpipe)) return nullptr;
    pid_t pid = fork();
    if (pid == 0) {
        setpgid(0, 0);
        dup2(inpipe[0], 0); dup2(outpipe[1], 1);
        close(inpipe[0]); close(inpipe[1]); close(outpipe[0]); close(outpipe[1]);
        execl("venv/bin/python", "python", "scripts/alpaca_tape_bridge.py",
              sym.c_str(), (char*)nullptr);
        _exit(127);
    }
    g_child = pid;
    close(inpipe[0]); close(outpipe[1]);
    g_child_in = fdopen(inpipe[1], "w");
    setvbuf(g_child_in, nullptr, _IOLBF, 0);
    FILE* out = fdopen(outpipe[0], "r");
    return out;
}

static void bridge_reader(FILE* out) {
    char line[512];
    while (fgets(line, sizeof(line), out)) {
        char sym[16]; double p, s2, bp, bs, ap, as2; long long ms;
        if (sscanf(line, "T %15s %lf %lf %lld", sym, &p, &s2, &ms) == 4) {
            char j[256];
            snprintf(j, sizeof(j),
                     "{\"t\":\"tr\",\"sym\":\"%s\",\"p\":%.4f,\"s\":%.0f,\"ms\":%lld}",
                     sym, p, s2, ms);
            broadcast(j);
        } else if (sscanf(line, "Q %15s %lf %lf %lf %lf %lld",
                          sym, &bp, &bs, &ap, &as2, &ms) == 6) {
            char j[320];
            snprintf(j, sizeof(j),
                     "{\"t\":\"q\",\"sym\":\"%s\",\"bp\":%.4f,\"bs\":%.0f,"
                     "\"ap\":%.4f,\"as\":%.0f,\"ms\":%lld}",
                     sym, bp, bs, ap, as2, ms);
            broadcast(j);
        } else if (sscanf(line, "D %15s %lf %lf %lf %lf %lf",
                          sym, &p, &bp, &bs, &ap, &as2) == 6) {
            char j[320];
            snprintf(j, sizeof(j),
                     "{\"t\":\"st\",\"sym\":\"%s\",\"o\":%.4f,\"h\":%.4f,"
                     "\"l\":%.4f,\"pc\":%.4f,\"v\":%.0f}",
                     sym, p, bp, bs, ap, as2);
            broadcast(j);
        } else if (line[0] == 'S') {
            fprintf(stderr, "[bridge] %s", line);
        }
    }
    fprintf(stderr, "[scan] bridge exited\n");
}

// ---- embedded UI ----
static const char* HTML = R"HTML(<!doctype html><html><head><meta charset="utf-8">
<title>scan — live tape</title>
<style>
 body{background:#0b0e14;color:#cfd8e3;font:14px -apple-system,Menlo,monospace;margin:0}
 #top{display:flex;gap:14px;align-items:center;padding:10px 14px;background:#11151f;border-bottom:1px solid #1e2635;flex-wrap:wrap}
 #symbox{background:#0b0e14;border:1px solid #2b3750;color:#fff;font:700 20px Menlo;padding:6px 10px;width:110px;text-transform:uppercase;border-radius:6px}
 .big{font:700 26px Menlo}
 .grn{color:#2ecc71}.red{color:#ff5252}.dim{color:#7a8699;font-size:12px}
 .stat{text-align:center}.stat .v{font:700 16px Menlo}
 #bidask{display:flex;gap:8px;align-items:center}
 .box{padding:6px 14px;border-radius:6px;text-align:center}
 #bidbox{background:#0e2b1c;border:1px solid #1d5c3b}
 #askbox{background:#2b0e12;border:1px solid #5c1d26}
 #main{display:grid;grid-template-columns:340px 1fr;gap:0;height:calc(100vh - 64px)}
 #tape{overflow-y:auto;border-right:1px solid #1e2635}
 #tape table{width:100%;border-collapse:collapse}
 #tape td{padding:2px 10px;font:13px Menlo;border-bottom:1px solid #131826}
 #tape tr.up td{color:#2ecc71}#tape tr.dn td{color:#ff5252}
 #tape tr.big td{background:#1a2130;font-weight:700}
 #chartwrap{position:relative}
 canvas{width:100%;height:100%;display:block}
 #right{display:flex;flex-direction:column}
 #qhist{height:120px;overflow-y:auto;border-top:1px solid #1e2635;font:12px Menlo;padding:4px 10px;color:#7a8699}
 h4{margin:6px 10px;color:#7a8699;font-weight:600;font-size:11px;letter-spacing:1px}
</style></head><body>
<div id="top">
 <input id="symbox" value="NVDA" maxlength="10" spellcheck="false">
 <div class="big" id="last">—</div><div class="big" id="chg">—</div>
 <div id="bidask">
   <div class="box" id="bidbox"><div class="dim">BID × sz</div><div class="v big grn" id="bid">—</div></div>
   <div class="box" id="askbox"><div class="dim">ASK × sz</div><div class="v big red" id="ask">—</div></div>
   <div class="stat"><div class="dim">SPREAD</div><div class="v" id="spr">—</div></div>
 </div>
 <div class="stat"><div class="dim">OPEN</div><div class="v" id="o">—</div></div>
 <div class="stat"><div class="dim">HIGH</div><div class="v" id="h">—</div></div>
 <div class="stat"><div class="dim">LOW</div><div class="v" id="l">—</div></div>
 <div class="stat"><div class="dim">PREV</div><div class="v" id="pc">—</div></div>
 <div class="stat"><div class="dim">IEX VOL</div><div class="v" id="vol">0</div></div>
 <div class="dim" id="status">connecting…</div>
</div>
<div id="main">
 <div id="tape"><h4>TIME &amp; SALES (IEX real-time)</h4><table id="tt"></table></div>
 <div id="right">
   <div id="chartwrap"><canvas id="cv"></canvas></div>
   <div id="qhist"><h4>QUOTE HISTORY</h4><div id="qh"></div></div>
 </div>
</div>
<script>
let SYM='NVDA', lastPx=0, vol=0, px=[], maxRows=250;
const $=id=>document.getElementById(id);
function setSym(s){
  SYM=s.toUpperCase(); vol=0; px=[]; lastPx=0;
  $('tt').innerHTML=''; $('qh').innerHTML=''; $('vol').textContent='0';
  fetch('/sym?s='+SYM); document.title=SYM+' — live tape';
}
$('symbox').addEventListener('keydown',e=>{if(e.key==='Enter')setSym(e.target.value)});
const es=new EventSource('/events');
es.onopen=()=>$('status').textContent='live';
es.onerror=()=>$('status').textContent='reconnecting…';
es.onmessage=ev=>{
  const m=JSON.parse(ev.data);
  if(m.sym && m.sym!==SYM) return;
  if(m.t==='tr'){
    const d=new Date(m.ms), ts=d.toTimeString().slice(0,8)+'.'+String(m.ms%1000).padStart(3,'0');
    const tr=document.createElement('tr');
    tr.className=(lastPx&&m.p<lastPx)?'dn':'up'; if(m.s>=1000)tr.className+=' big';
    tr.innerHTML=`<td>${ts}</td><td>${m.p.toFixed(m.p<1?4:2)}</td><td style="text-align:right">${m.s}</td>`;
    const tt=$('tt'); tt.insertBefore(tr,tt.firstChild);
    while(tt.rows.length>maxRows)tt.deleteRow(-1);
    $('last').textContent=m.p.toFixed(m.p<1?4:2);
    $('last').className='big '+((lastPx&&m.p<lastPx)?'red':'grn');
    lastPx=m.p; vol+=m.s; $('vol').textContent=vol.toLocaleString();
    px.push(m.p); if(px.length>600)px.shift(); draw();
  }else if(m.t==='q'){
    $('bid').textContent=m.bp.toFixed(m.bp<1?4:2)+' × '+m.bs;
    $('ask').textContent=m.ap.toFixed(m.ap<1?4:2)+' × '+m.as;
    $('spr').textContent=(m.ap-m.bp).toFixed(m.bp<1?4:2);
    const d=new Date(m.ms);
    const row=document.createElement('div');
    row.textContent=`${d.toTimeString().slice(0,8)}  ${m.bp.toFixed(2)}×${m.bs}  |  ${m.ap.toFixed(2)}×${m.as}`;
    const qh=$('qh'); qh.insertBefore(row,qh.firstChild);
    while(qh.childNodes.length>40)qh.removeChild(qh.lastChild);
  }else if(m.t==='st'){
    if(m.c){$('o').textContent=(m.o||0).toFixed(2);$('h').textContent=(m.h||0).toFixed(2);
      $('l').textContent=(m.l||0).toFixed(2);$('pc').textContent=(m.pc||0).toFixed(2);
      const dp=m.dp||0; $('chg').textContent=(dp>=0?'+':'')+dp.toFixed(2)+'%';
      $('chg').className='big '+(dp>=0?'grn':'red');
      if(!lastPx){$('last').textContent=m.c.toFixed(2);}}
  }
};
function draw(){
  const cv=$('cv'), ctx=cv.getContext('2d');
  cv.width=cv.clientWidth; cv.height=cv.clientHeight;
  if(px.length<2)return;
  const mn=Math.min(...px), mx=Math.max(...px), pad=(mx-mn)*0.1||0.01;
  const X=i=>i/(px.length-1)*(cv.width-20)+10;
  const Y=p=>cv.height-((p-mn+pad)/(mx-mn+2*pad))*cv.height;
  ctx.strokeStyle=px[px.length-1]>=px[0]?'#2ecc71':'#ff5252';
  ctx.lineWidth=1.6; ctx.beginPath(); ctx.moveTo(X(0),Y(px[0]));
  for(let i=1;i<px.length;i++)ctx.lineTo(X(i),Y(px[i]));
  ctx.stroke();
  ctx.fillStyle='#7a8699'; ctx.font='11px Menlo';
  ctx.fillText(mx.toFixed(2),4,10); ctx.fillText(mn.toFixed(2),4,cv.height-4);
}
window.addEventListener('resize',draw);
</script></body></html>)HTML";

// ---- tiny HTTP ----
static void http_send(int fd, const char* status, const char* ctype,
                      const std::string& body) {
    char hdr[256];
    snprintf(hdr, sizeof(hdr),
             "HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %zu\r\n"
             "Cache-Control: no-cache\r\nConnection: close\r\n\r\n",
             status, ctype, body.size());
    send(fd, hdr, strlen(hdr), MSG_NOSIGNAL);
    send(fd, body.data(), body.size(), MSG_NOSIGNAL);
}

static void handle_client(int fd) {
    char buf[2048];
    ssize_t n = recv(fd, buf, sizeof(buf) - 1, 0);
    if (n <= 0) { close(fd); return; }
    buf[n] = 0;
    if (!strncmp(buf, "GET /events", 11)) {
        const char* h = "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                        "Cache-Control: no-cache\r\nConnection: keep-alive\r\n\r\n"
                        "retry: 1500\n\n";
        send(fd, h, strlen(h), MSG_NOSIGNAL);
        std::lock_guard<std::mutex> lk(g_mtx);
        g_clients.push_back(fd);          // stays open; broadcast() owns it now
        return;
    }
    if (!strncmp(buf, "GET /sym?s=", 11)) {
        std::string raw(buf + 11);
        raw = raw.substr(0, raw.find_first_of(" &\r\n"));
        std::string sym = sanitize_sym(raw);
        if (!sym.empty()) {
            std::lock_guard<std::mutex> lk(g_mtx);
            g_sym = sym;
            if (g_child_in) fprintf(g_child_in, "SUB %s\n", sym.c_str());
        }
        http_send(fd, "200 OK", "application/json",
                  "{\"ok\":true,\"sym\":\"" + sym + "\"}");
        close(fd); return;
    }
    if (!strncmp(buf, "GET / ", 6) || !strncmp(buf, "GET /HTTP", 9)) {
        http_send(fd, "200 OK", "text/html; charset=utf-8", HTML);
        close(fd); return;
    }
    http_send(fd, "404 Not Found", "text/plain", "not found");
    close(fd);
}

static void on_term(int) {
    if (g_child > 0) kill(-g_child, SIGTERM);
    _exit(0);
}

int main(int argc, char** argv) {
    if (argc > 1) g_sym = sanitize_sym(argv[1]);
    if (argc > 2) g_port = atoi(argv[2]);
    if (g_sym.empty()) g_sym = "NVDA";
    signal(SIGPIPE, SIG_IGN);
    signal(SIGINT, on_term); signal(SIGTERM, on_term);
    curl_global_init(CURL_GLOBAL_DEFAULT);

    FILE* bridge_out = spawn_bridge(g_sym);
    if (!bridge_out) { fprintf(stderr, "no bridge\n"); return 1; }
    std::thread(bridge_reader, bridge_out).detach();

    int srv = socket(AF_INET, SOCK_STREAM, 0);
    int yes = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    sockaddr_in a{}; a.sin_family = AF_INET; a.sin_port = htons((uint16_t)g_port);
    inet_pton(AF_INET, "127.0.0.1", &a.sin_addr);       // localhost ONLY
    if (bind(srv, (sockaddr*)&a, sizeof(a)) || listen(srv, 32)) {
        fprintf(stderr, "bind/listen failed on %d (already running?)\n", g_port);
        return 1;
    }
    printf("scan_server: http://localhost:%d  (sym %s, IEX real-time)\n",
           g_port, g_sym.c_str());
    fflush(stdout);
    while (true) {
        int fd = accept(srv, nullptr, nullptr);
        if (fd < 0) continue;
        std::thread(handle_client, fd).detach();
    }
}
