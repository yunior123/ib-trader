// orderflow_footprint.cpp — footprint Bid x Ask REAL y patrones Trader Dale.
//
// Input normalizado (cualquier adaptador de cinta completa puede producirlo):
//   EPOCH PRICE SIZE DIR BID ASK METHOD
// DIR +1 = agresor comprador, -1 = vendedor, 0 = indeterminado. El cero permanece cero.
// METHOD N = lado nativo del venue, Q = quote rule, T = tick rule, U = desconocido.
// Input perp (`--format perp`), producido por perp_ws_bridge.py:
//   TS_MS TRADE_ID PRICE SIZE SIDE
// Output atomico: data/footprint_<sym>.json. DESCRIPTIVO / SIGNAL-ONLY; nunca ordena ni habla.
//
// Los patrones son mutables dentro de la vela: FORMING hasta el cierre; BAR_CLOSED despues.
// No se publica win probability: el score 0..100 es calidad de EVIDENCIA visual, no WR.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include <unistd.h>

namespace fs = std::filesystem;

namespace {

constexpr int kRatio = 3;
constexpr int kStack = 3;
constexpr int kKeepMinutes = 240;
constexpr int kBarsOut = 8;

struct Cell { double bid = 0, ask = 0, unknown = 0, native = 0, quote = 0, tick = 0; };
struct Minute {
    long t = 0; double o = 0, h = 0, l = 0, c = 0;
    std::map<long long, Cell> cells;
};
struct Agg {
    long t = 0; double o = 0, h = 0, l = 0, c = 0;
    std::map<long long, Cell> cells;
};
struct Source {
    std::string sym, path, carry;
    std::string feed = "normalized execution tape";
    std::string quality = "FULL_EXECUTION_TAPE";
    std::string instrument_kind = "US_EQUITY";
    std::string proxy_for;
    bool perp = false;
    std::uintmax_t offset = 0;
    std::map<long, Minute> mins;
    double tick = 0.01;
    long last_trade = 0;
};

double tick_for(double px) { return px >= 1.0 ? 0.01 : 0.0001; }
long long pkey(double px, double tick) { return std::llround(px / tick); }
double qtile(std::vector<double> v, double q, double fallback) {
    if (v.empty()) return fallback;
    std::sort(v.begin(), v.end());
    const double x = q * (v.size() - 1);
    const size_t a = static_cast<size_t>(x), b = std::min(a + 1, v.size() - 1);
    return v[a] + (v[b] - v[a]) * (x - a);
}
std::string esc(const std::string& s) {
    std::string o;
    for (char c : s) {
        if (c == '"' || c == '\\') o += '\\';
        if (c == '\n') o += "\\n"; else o += c;
    }
    return o;
}
void atomic_write(const std::string& path, const std::string& body) {
    const std::string tmp = path + ".tmp." + std::to_string(::getpid());
    { std::ofstream f(tmp, std::ios::binary); f << body; f.flush(); }
    std::rename(tmp.c_str(), path.c_str());
}

bool consume(Source& s) {
    std::error_code ec;
    const auto size = fs::file_size(s.path, ec);
    if (ec) return false;
    if (size < s.offset) { s.offset = 0; s.carry.clear(); s.mins.clear(); }
    if (size == s.offset) return false;
    std::ifstream f(s.path, std::ios::binary);
    if (!f) return false;
    f.seekg(static_cast<std::streamoff>(s.offset));
    std::string bytes((std::istreambuf_iterator<char>(f)), {});
    if (bytes.empty()) return false;
    const size_t nl = bytes.rfind('\n');
    if (nl == std::string::npos) return false;  // lote aun incompleto: no adelantar cursor
    s.offset += nl + 1;
    std::istringstream in(s.carry + bytes.substr(0, nl + 1));
    s.carry.clear();
    std::string line;
    bool changed = false;
    while (std::getline(in, line)) {
        double ep = 0, px = 0, sz = 0, bidq = 0, askq = 0; int dir = 0; char method='Q';
        int fields = 0;
        if (s.perp) {
            long long ts_ms = 0; std::string trade_id, side;
            std::istringstream row(line);
            if (row >> ts_ms >> trade_id >> px >> sz >> side) {
                ep = static_cast<double>(ts_ms) / 1000.0;
                dir = side == "buy" ? 1 : side == "sell" ? -1 : 0;
                method = dir ? 'N' : 'U'; fields = 7;
            }
        } else {
            fields=std::sscanf(line.c_str(), "%lf %lf %lf %d %lf %lf %c",
                               &ep, &px, &sz, &dir, &bidq, &askq, &method);
        }
        if (fields < 6 || ep <= 0 || px <= 0 || sz <= 0) continue;
        (void)bidq; (void)askq;
        if (s.mins.empty()) s.tick = tick_for(px);
        const long mt = static_cast<long>(ep) / 60 * 60;
        Minute& m = s.mins[mt];
        if (!m.t) { m.t = mt; m.o = m.h = m.l = m.c = px; }
        else { m.h = std::max(m.h, px); m.l = std::min(m.l, px); m.c = px; }
        Cell& c = m.cells[pkey(px, s.tick)];
        if (dir > 0) c.ask += sz; else if (dir < 0) c.bid += sz; else c.unknown += sz;
        if(dir && method=='N')c.native+=sz;
        else if(dir && method=='Q')c.quote+=sz;
        else if(dir && method=='T')c.tick+=sz;
        s.last_trade = std::max(s.last_trade, static_cast<long>(ep));
        changed = true;
    }
    const long cut = std::time(nullptr) - kKeepMinutes * 60L;
    while (!s.mins.empty() && s.mins.begin()->first < cut) s.mins.erase(s.mins.begin());
    return changed;
}

std::vector<Agg> aggregate(const Source& s, int sec) {
    std::map<long, Agg> by;
    for (const auto& [mt, m] : s.mins) {
        const long bt = mt / sec * sec;
        Agg& a = by[bt];
        if (!a.t) { a.t = bt; a.o = m.o; a.h = m.h; a.l = m.l; a.c = m.c; }
        else { a.h = std::max(a.h, m.h); a.l = std::min(a.l, m.l); a.c = m.c; }
        for (const auto& [k, x] : m.cells) {
            Cell& z = a.cells[k]; z.bid += x.bid; z.ask += x.ask; z.unknown += x.unknown;
            z.native += x.native; z.quote += x.quote; z.tick += x.tick;
        }
    }
    std::vector<Agg> out;
    for (auto& [_, a] : by) out.push_back(std::move(a));
    return out;
}

double bdelta(const Agg& a) {
    double d = 0; for (const auto& [_, c] : a.cells) d += c.ask - c.bid; return d;
}
double volume(const Agg& a) {
    double v = 0; for (const auto& [_, c] : a.cells) v += c.ask + c.bid + c.unknown; return v;
}
long long poc(const Agg& a) {
    long long best = 0; double bv = -1;
    for (const auto& [k, c] : a.cells) {
        const double v = c.bid + c.ask + c.unknown;
        if (v > bv || (v == bv && k > best)) { bv = v; best = k; }
    }
    return best;
}

struct Marks {
    std::set<long long> buy, sell;
    std::vector<std::pair<long long,long long>> buy_stacks, sell_stacks;
};
Marks imbalances(const Agg& a, double minvol) {
    Marks m;
    for (const auto& [k, c] : a.cells) {
        const auto lo = a.cells.find(k - 1), hi = a.cells.find(k + 1);
        const double diag_bid = lo == a.cells.end() ? 0 : lo->second.bid;
        const double diag_ask = hi == a.cells.end() ? 0 : hi->second.ask;
        if (c.ask >= minvol && c.ask >= kRatio * std::max(1.0, diag_bid)) m.buy.insert(k);
        if (c.bid >= minvol && c.bid >= kRatio * std::max(1.0, diag_ask)) m.sell.insert(k);
    }
    auto stacks = [](const std::set<long long>& v) {
        std::vector<std::pair<long long,long long>> out;
        if (v.empty()) return out;
        auto it = v.begin(); long long lo = *it, prev = *it;
        for (++it; it != v.end(); ++it) {
            if (*it != prev + 1) { if (prev - lo + 1 >= kStack) out.push_back({lo, prev}); lo = *it; }
            prev = *it;
        }
        if (prev - lo + 1 >= kStack) out.push_back({lo, prev});
        return out;
    };
    m.buy_stacks = stacks(m.buy); m.sell_stacks = stacks(m.sell);
    return m;
}

void pattern(std::ostringstream& o, bool& first, const char* kind, const char* side,
             const char* status, int score, const std::string& why,
             double lo = 0, double hi = 0) {
    if (!first) o << ','; first = false;
    o << "{\"kind\":\"" << kind << "\",\"side\":\"" << side
      << "\",\"status\":\"" << status << "\",\"evidence_score\":" << score
      << ",\"why\":\"" << esc(why) << "\"";
    if (lo || hi) o << ",\"zone\":[" << lo << ',' << hi << ']';
    o << '}';
}

std::string timeframe_json(const Source& s, int sec, long now) {
    auto bars = aggregate(s, sec);
    std::vector<double> bids, asks, totals, sidevals;
    for (const auto& a : bars) if (a.t + sec <= now) for (const auto& [_, c] : a.cells) {
        if (c.bid > 0) { bids.push_back(c.bid); sidevals.push_back(c.bid); }
        if (c.ask > 0) { asks.push_back(c.ask); sidevals.push_back(c.ask); }
        totals.push_back(c.bid + c.ask + c.unknown);
    }
    const double qb = qtile(bids, .95, 10), qa = qtile(asks, .95, 10),
                 qt = qtile(totals, .95, 20), minvol = std::max(3.0, qtile(sidevals, .50, 3));
    const size_t start = bars.size() > kBarsOut ? bars.size() - kBarsOut : 0;
    // Para publicar CVD por barra necesitamos el acumulado antes de `start`.
    double running = 0;
    if (!bars.empty()) {
        std::tm endtm{}; std::time_t et=bars.back().t; localtime_r(&et,&endtm);
        for (size_t i=0;i<start;i++) { std::tm tm{}; std::time_t t=bars[i].t; localtime_r(&t,&tm);
            if (tm.tm_year==endtm.tm_year && tm.tm_yday==endtm.tm_yday) running += bdelta(bars[i]); }
    }
    std::ostringstream o; o << std::fixed << std::setprecision(4);
    o << "{\"seconds\":" << sec << ",\"imbalance_ratio\":3.0,\"stack_size\":3,"
      << "\"adaptive\":{\"bid_p95\":" << qb << ",\"ask_p95\":" << qa
      << ",\"total_p95\":" << qt << ",\"min_dominant\":" << minvol << "},\"bars\":[";
    bool fb = true;
    std::vector<long long> prior_poc;
    for (size_t i=0;i<bars.size();i++) prior_poc.push_back(poc(bars[i]));
    for (size_t i=start;i<bars.size();i++) {
        const Agg& a=bars[i]; const double d=bdelta(a), v=volume(a); running += d;
        double bid_total=0, ask_total=0, unknown_total=0;
        for(const auto& [_,c]:a.cells){bid_total+=c.bid;ask_total+=c.ask;unknown_total+=c.unknown;}
        const bool closed=a.t+sec<=now; const char* status=closed?"BAR_CLOSED":"FORMING";
        const long long pk=poc(a); const Marks mk=imbalances(a,minvol);
        int cluster=1;
        if (closed) for (size_t j=i;j>0 && prior_poc[j-1]==pk && bars[j-1].t+sec<=now;j--) cluster++;
        if (!fb) o << ','; fb=false;
        o << "{\"time\":" << a.t << ",\"open\":" << a.o << ",\"high\":" << a.h
          << ",\"low\":" << a.l << ",\"close\":" << a.c << ",\"closed\":"
          << (closed?"true":"false") << ",\"bid\":" << bid_total
          << ",\"ask\":" << ask_total << ",\"unknown\":" << unknown_total
          << ",\"delta\":" << d << ",\"volume\":" << v << ",\"cvd\":" << running
          << ",\"poc\":" << pk*s.tick << ",\"poc_cluster\":" << cluster << ",\"cells\":[";
        bool fc=true;
        for (const auto& [k,c] : a.cells) {
            if (!fc) o << ','; fc=false;
            o << "{\"price\":" << k*s.tick << ",\"bid\":" << c.bid << ",\"ask\":" << c.ask
              << ",\"unknown\":" << c.unknown << ",\"buy_imb\":" << (mk.buy.count(k)?"true":"false")
              << ",\"sell_imb\":" << (mk.sell.count(k)?"true":"false")
              << ",\"poc\":" << (k==pk?"true":"false") << '}';
        }
        o << "],\"patterns\":["; bool fp=true;
        // 1) Absorción adaptativa: ambos lados enormes + extremo + fallo de continuación.
        for (const auto& [k,c] : a.cells) if (c.bid>=qb && c.ask>=qa && c.bid+c.ask>=qt) {
            const double px=k*s.tick, span=std::max(s.tick,a.h-a.l), pos=(px-a.l)/span;
            if (pos>=.72 && a.c<=px+s.tick)
                pattern(o,fp,"ABSORPTION","BEARISH",status,closed?78:62,
                        "both sides >= adaptive p95; upper extreme; price stalled — confirm at mapped resistance",px-s.tick,px+s.tick);
            else if (pos<=.28 && a.c>=px-s.tick)
                pattern(o,fp,"ABSORPTION","BULLISH",status,closed?78:62,
                        "both sides >= adaptive p95; lower extreme; price stalled — confirm at mapped support",px-s.tick,px+s.tick);
        }
        // 2) Cambio/divergencia de delta. La vela y el delta deben discrepar.
        if (a.c>a.o && d<0) pattern(o,fp,"DELTA_FLIP","BEARISH",status,closed?72:55,
            "bullish price bar with negative Ask-Bid delta");
        if (a.c<a.o && d>0) pattern(o,fp,"DELTA_FLIP","BULLISH",status,closed?72:55,
            "bearish price bar with positive Ask-Bid delta");
        if (i>=2) {
            const double dp=a.c-bars[i-2].c, dd=d-bdelta(bars[i-2]);
            if (dp>0 && dd<0) pattern(o,fp,"PRICE_DELTA_DIVERGENCE","BEARISH",status,closed?68:52,
                "price rising across 3 footprints while bar delta weakens");
            if (dp<0 && dd>0) pattern(o,fp,"PRICE_DELTA_DIVERGENCE","BULLISH",status,closed?68:52,
                "price falling across 3 footprints while bar delta strengthens");
        }
        // 3) Stacked diagonal imbalance: >=3 price rows contiguos, nunca dispersos.
        for (auto z:mk.buy_stacks) pattern(o,fp,"STACKED_IMBALANCE","BULLISH",status,closed?76:58,
            "3+ adjacent diagonal Ask >= 3x Bid rows",z.first*s.tick,z.second*s.tick);
        for (auto z:mk.sell_stacks) pattern(o,fp,"STACKED_IMBALANCE","BEARISH",status,closed?76:58,
            "3+ adjacent diagonal Bid >= 3x Ask rows",z.first*s.tick,z.second*s.tick);
        // 5) Multiple HVN: POC alineado solo cuenta en footprints CERRADOS.
        if (closed && cluster>=2) pattern(o,fp,cluster>=3?"TRIPLE_HVN":"DOUBLE_HVN","NEUTRAL",
            "BAR_CLOSED",cluster>=3?82:70,"consecutive closed footprints share the exact POC",pk*s.tick,pk*s.tick);
        o << "]}";
    }
    o << "]}";
    return o.str();
}

std::string render(const Source& s, long now) {
    double known=0, unknown=0, native=0, quote=0, tick=0;
    for (const auto& [_,m]:s.mins) for (const auto& [__,c]:m.cells) {
        known+=c.bid+c.ask; unknown+=c.unknown; native+=c.native; quote+=c.quote; tick+=c.tick;
    }
    const double pct=(known+unknown)>0?100*known/(known+unknown):0;
    const double total=known+unknown;
    const std::string side = native>0 && quote+tick>0 ? "MIXED" :
                             native>0 ? "NATIVE" : quote+tick>0 ? "INFERRED" : "UNKNOWN";
    std::ostringstream o; o << std::fixed << std::setprecision(3);
    o << "{\"schema\":1,\"sym\":\"" << esc(s.sym) << "\",\"asof\":" << s.last_trade
      << ",\"age_s\":" << (s.last_trade?std::max(0L,now-s.last_trade):0)
      << ",\"source\":\"" << esc(s.feed) << "\",\"quality\":\"" << esc(s.quality) << "\","
      << "\"instrument_kind\":\"" << esc(s.instrument_kind) << "\","
      << "\"proxy_for\":" << (s.proxy_for.empty()?"null":"\""+esc(s.proxy_for)+"\"") << ','
      << "\"side_provenance\":\"" << side << "\","
      << "\"classification_pct\":" << pct
      << ",\"native_side_pct\":" << (total?100*native/total:0)
      << ",\"quote_rule_pct\":" << (total?100*quote/total:0)
      << ",\"tick_rule_pct\":" << (total?100*tick/total:0)
      << ",\"unknown_pct\":" << (total?100*unknown/total:0)
      << ",\"tick_size\":" << s.tick
      << ",\"doctrine\":\"DESCRIPTIVE_UNPROVEN_SIGNAL_ONLY\",\"timeframes\":{";
    const int tfs[]={60,300,900,1800}; bool first=true;
    for(int sec:tfs){ if(!first)o<<','; first=false; o<<'\"'<<sec<<"\":"<<timeframe_json(s,sec,now); }
    o << "}}"; return o.str();
}

std::string sym_from(const std::string& p, bool perp) {
    const std::string n=fs::path(p).filename().string(), pre="footprint_tape_", suf=".txt";
    std::string s;
    if (perp) {
        if (fs::path(p).extension() != ".txt") return {};
        s = fs::path(p).stem().string();
    } else {
        if(n.rfind(pre,0)!=0 || n.size()<=pre.size()+suf.size()) return {};
        s=n.substr(pre.size(),n.size()-pre.size()-suf.size());
    }
    for(char& c:s)c=static_cast<char>(std::toupper(c)); return s;
}

} // namespace

int main(int argc,char** argv){
    std::string input, sym, out="-", dir="data", out_dir, feed="normalized execution tape",
                quality="FULL_EXECUTION_TAPE", format="normalized", suffix,
                instrument_kind="US_EQUITY"; int loop_ms=0;
    for(int i=1;i<argc;i++){
        std::string a=argv[i];
        if(a=="--input"&&i+1<argc)input=argv[++i]; else if(a=="--sym"&&i+1<argc)sym=argv[++i];
        else if(a=="--out"&&i+1<argc)out=argv[++i]; else if(a=="--dir"&&i+1<argc)dir=argv[++i];
        else if(a=="--source"&&i+1<argc)feed=argv[++i];
        else if(a=="--quality"&&i+1<argc)quality=argv[++i];
        else if(a=="--format"&&i+1<argc)format=argv[++i];
        else if(a=="--out-dir"&&i+1<argc)out_dir=argv[++i];
        else if(a=="--sym-suffix"&&i+1<argc)suffix=argv[++i];
        else if(a=="--instrument-kind"&&i+1<argc)instrument_kind=argv[++i];
        else if(a=="--loop"&&i+1<argc)loop_ms=std::max(100,std::atoi(argv[++i]));
    }
    const bool perp=format=="perp";
    if(out_dir.empty())out_dir=dir;
    if(!input.empty()){
        Source s; s.sym=(sym.empty()?sym_from(input,perp):sym); s.path=input; s.feed=feed;
        s.quality=quality; s.perp=perp; s.instrument_kind=instrument_kind;
        if(perp){s.proxy_for=s.sym;s.sym+=suffix;} consume(s);
        const std::string body=render(s,std::time(nullptr));
        if(out=="-")std::cout<<body<<'\n';else atomic_write(out,body); return s.last_trade?0:2;
    }
    std::map<std::string,Source> src;
    do{
        std::error_code ec;
        std::map<std::string,std::string> found;
        if(perp){
            for(const auto& e:fs::recursive_directory_iterator(dir,ec)){
                if(ec||!e.is_regular_file())continue; const std::string p=e.path().string(), base=sym_from(p,true);
                if(!base.empty() && (!found.count(base)||p>found[base]))found[base]=p;
            }
        } else {
            for(const auto& e:fs::directory_iterator(dir,ec)){
                if(ec||!e.is_regular_file())continue; const std::string p=e.path().string(), base=sym_from(p,false);
                if(!base.empty())found[base]=p;
            }
        }
        for(const auto& [base,p]:found){
            const std::string key=base+suffix;
            if(!src.count(key)){ Source x; x.sym=key; x.path=p; x.feed=feed; x.quality=quality;
                x.perp=perp; x.instrument_kind=instrument_kind; if(perp)x.proxy_for=base;
                src[key]=std::move(x); }
            else if(src[key].path!=p){src[key].path=p;src[key].offset=0;src[key].carry.clear();}
        }
        const long now=std::time(nullptr);
        for(auto& [s,x]:src) if(consume(x)) {
            std::string lower=s; for(char& c:lower)c=static_cast<char>(std::tolower(c));
            atomic_write(out_dir+"/footprint_"+lower+".json",render(x,now));
        }
        if(!loop_ms)break; std::this_thread::sleep_for(std::chrono::milliseconds(loop_ms));
    }while(true);
    return 0;
}
