// Backtest the fleet BUY/SELL -> options-alert policy on the repository's 1-minute history.
// Chronological 60/40 split; triple barrier; explicit option-ATM friction approximation.
#include <sqlite3.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <map>
#include <regex>
#include <set>
#include <sstream>
#include <string>
#include <vector>

struct Bar { long long ts; double h, l, c; };
struct Event {
    std::string date, time, sym, side, raw;
    long long epoch = 0;
    int probability = 0, label = -1; // 1=TP first, 0=SL first, -1=timeout/no data
    double net_atr = 0;
};
struct Stats { int n=0, wins=0, days=0; double sum=0; };

static void check(int rc, sqlite3* db, const char* what) {
    if (rc != SQLITE_OK && rc != SQLITE_DONE && rc != SQLITE_ROW) {
        std::cerr << what << ": " << sqlite3_errmsg(db) << "\n"; std::exit(2);
    }
}
static int declared_probability(const std::string& text) {
    static const std::regex p1(R"(prob(?:abilidad)?\s+([0-9]{2,3})\s*(?:%|por ciento))",
                               std::regex::icase);
    std::smatch m;
    if (!std::regex_search(text, m, p1)) return 0;
    return std::clamp(std::atoi(m[1].str().c_str()), 0, 100);
}
static std::vector<Bar> bars(sqlite3* db, const std::string& sym, long long epoch) {
    sqlite3_stmt* st = nullptr;
    const char* sql = "SELECT ts,h,l,c FROM poly_bars WHERE sym=? AND ts>=? AND ts<=? ORDER BY ts";
    check(sqlite3_prepare_v2(db, sql, -1, &st, nullptr), db, "prepare bars");
    sqlite3_bind_text(st, 1, sym.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(st, 2, (epoch - 30*60) * 1000);
    sqlite3_bind_int64(st, 3, (epoch + 31*60) * 1000);
    std::vector<Bar> out;
    while (sqlite3_step(st) == SQLITE_ROW)
        out.push_back({sqlite3_column_int64(st,0), sqlite3_column_double(st,1),
                       sqlite3_column_double(st,2), sqlite3_column_double(st,3)});
    sqlite3_finalize(st); return out;
}
static bool label(sqlite3* db, Event& e) {
    auto bs = bars(db, e.sym, e.epoch);
    const long long tms = e.epoch * 1000;
    int entry_i=-1;
    for (int i=0;i<(int)bs.size();++i) if (bs[i].ts<=tms) entry_i=i;
    if (entry_i < 14 || entry_i+1 >= (int)bs.size() || tms-bs[entry_i].ts > 15*60*1000) return false;
    double atr=0;
    for (int i=entry_i-13;i<=entry_i;++i) {
        double tr=bs[i].h-bs[i].l;
        if (i>0) tr=std::max(tr,std::max(std::fabs(bs[i].h-bs[i-1].c),std::fabs(bs[i].l-bs[i-1].c)));
        atr += tr;
    }
    atr /= 14.0;
    if (!(atr>0)) return false;
    const double entry=bs[entry_i].c, dir=e.side=="BUY"?1.0:-1.0;
    const double tp=entry+dir*atr, sl=entry-dir*atr;
    e.label=-1;
    for (int i=entry_i+1;i<(int)bs.size() && bs[i].ts<=tms+30*60*1000;++i) {
        bool hit_tp=dir>0?bs[i].h>=tp:bs[i].l<=tp;
        bool hit_sl=dir>0?bs[i].l<=sl:bs[i].h>=sl;
        if (hit_tp||hit_sl) { e.label=hit_sl?0:1; break; } // same bar: SL first
    }
    if (e.label<0) return true;
    // House benchmark: 0.069% of underlying round-trip for a liquid ATM option.
    const double cost_atr=(0.00069*entry)/atr;
    e.net_atr=(e.label?1.0:-1.0)-cost_atr;
    return true;
}
static Stats policy(const std::vector<Event>& ev, const std::set<std::string>& dates,
                    int min_prob, int top_n) {
    std::map<std::string,std::vector<const Event*>> byday;
    for (const auto& e:ev) if (dates.count(e.date) && e.probability>=min_prob && e.label>=0)
        byday[e.date].push_back(&e);
    Stats s; s.days=(int)dates.size();
    for (auto& [day,v]:byday) {
        std::stable_sort(v.begin(),v.end(),[](auto a,auto b){
            return a->probability != b->probability ? a->probability>b->probability : a->time<b->time;
        });
        if ((int)v.size()>top_n) v.resize(top_n);
        for (auto e:v) { s.n++; s.wins+=e->label; s.sum+=e->net_atr; }
    }
    return s;
}
static void show(const char* set, int p, int top, const Stats& s) {
    std::cout<<std::left<<std::setw(5)<<set<<" p>="<<std::setw(2)<<p<<" top"<<top
             <<" n="<<std::setw(3)<<s.n;
    if (!s.n) { std::cout<<" DATA-INSUFFICIENT\n"; return; }
    std::cout<<" WR="<<std::fixed<<std::setprecision(1)<<100.0*s.wins/s.n<<"%"
             <<" net="<<std::showpos<<std::setprecision(3)<<s.sum/s.n<<std::noshowpos
             <<" ATR/alert\n";
}

int main(int argc,char**argv) {
    const char* path=argc>1?argv[1]:"data/trades.db";
    sqlite3* db=nullptr; check(sqlite3_open_v2(path,&db,SQLITE_OPEN_READONLY,nullptr),db,"open");
    sqlite3_stmt* st=nullptr;
    const char* sql="SELECT date,ts_txt,ts_epoch,raw FROM signals WHERE ts_epoch IS NOT NULL ORDER BY ts_epoch";
    check(sqlite3_prepare_v2(db,sql,-1,&st,nullptr),db,"prepare signals");
    static const std::regex re(R"(^\d\d:\d\d:\d\d \| ([A-Z0-9]{1,8}): (BUY|SELL) \|)");
    std::vector<Event> ev; std::set<std::string> dates_all; int skipped=0;
    while(sqlite3_step(st)==SQLITE_ROW) {
        std::string raw=(const char*)sqlite3_column_text(st,3); std::smatch m;
        if(!std::regex_search(raw,m,re)) continue;
        Event e; e.date=(const char*)sqlite3_column_text(st,0); e.time=(const char*)sqlite3_column_text(st,1);
        e.epoch=(long long)sqlite3_column_double(st,2); e.raw=raw; e.sym=m[1]; e.side=m[2];
        e.probability=declared_probability(raw);
        if(label(db,e)){ev.push_back(e);dates_all.insert(e.date);}else skipped++;
    }
    sqlite3_finalize(st); sqlite3_close(db);
    std::vector<std::string> ds(dates_all.begin(),dates_all.end());
    const size_t cut=std::max<size_t>(1,std::lround(ds.size()*0.60));
    std::set<std::string> train(ds.begin(),ds.begin()+std::min(cut,ds.size()));
    std::set<std::string> test(ds.begin()+std::min(cut,ds.size()),ds.end());
    std::cout<<"events="<<ev.size()<<" skipped="<<skipped<<" days="<<ds.size()
             <<" train="<<train.size()<<" test="<<test.size()<<"\n";
    std::cout<<"label=TP/SL 1ATR, 30min, SL-first ambiguous; net includes 0.069% option-ATM friction\n\n";
    double best=-1e18; int bestp=0,bestn=0;
    for(int p:{55,60,65,70}) for(int n:{1,2,3}) {
        Stats s=policy(ev,train,p,n); show("train",p,n,s);
        show("test",p,n,policy(ev,test,p,n));
        if(s.n>=10 && s.sum/s.n>best){best=s.sum/s.n;bestp=p;bestn=n;}
    }
    std::cout<<"\nCHOSEN ON TRAIN: p>="<<bestp<<" top"<<bestn<<"\n";
    show("test",bestp,bestn,policy(ev,test,bestp,bestn));
    show("all",bestp,bestn,policy(ev,dates_all,bestp,bestn));
    return bestp?0:1;
}
