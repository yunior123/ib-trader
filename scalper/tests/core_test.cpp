// core_test.cpp — unit tests del nucleo del whale scalper (harness del skill
// cpp23-testing: sin frameworks, registry + EXPECT, corre release Y ASan).
#include <sys/stat.h>
#include <unistd.h>
#include <cstdio>
#include <functional>
#include <random>
#include <vector>
#include "../scalper_core.h"
#include "../ledger.h"
#include "../tail.h"

using namespace scalp;

static std::vector<std::pair<const char*, std::function<void()>>>& tests()
{ static std::vector<std::pair<const char*, std::function<void()>>> v; return v; }
static int g_fail = 0;
#define TEST(name) static void name(); \
  static const bool name##_reg = (tests().push_back({#name, name}), true); \
  static void name()
#define EXPECT(cond) do { if (!(cond)) { ++g_fail; \
  std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); } } while (0)
#define EXPECT_EQ(a,b) do { auto va=(a); auto vb=(b); if (!(va==vb)) { ++g_fail; \
  std::printf("FAIL %s:%d  %s == %s  (%lld vs %lld)\n", __FILE__, __LINE__, #a, #b, \
  (long long)va, (long long)vb); } } while (0)

// ------------------------------------------------------------ dinero
TEST(money_basico) {
    Cfg c;
    EXPECT_EQ(net_cost_c(57, c), 57 * 100 + 65);
    EXPECT_EQ(net_exit_c(60, c), 60 * 100 - 65);
    // RT = 130c: comprar y vender al MISMO precio = perdida de 130c
    EXPECT_EQ(net_exit_c(57, c) - net_cost_c(57, c), -130);
}
TEST(profit_umbral_exacto) {
    // costo 5765 (57c fill): +1% neto = 5822.65 -> se necesita exit*10000 >= 5765*10100
    int64_t cost = net_cost_c(57, Cfg{});
    EXPECT(!profit_reached(cost, cost, 100));
    EXPECT(!profit_reached(cost, cost + 57, 100));        // 57.65 requerido: 57 NO llega
    EXPECT(profit_reached(cost, cost + 58, 100));
    EXPECT(profit_reached(cost, cost * 2, 500));
}
TEST(money_prop_invariantes) {
    Cfg c;
    for (uint64_t seed : {1ull, 42ull, 0xC0FFEEull}) {
        std::mt19937_64 rng(seed);
        for (int i = 0; i < 50000; ++i) {
            int px = 1 + (int)(rng() % 99999);
            EXPECT_EQ(net_exit_c(px, c) + c.commission_side_c, (int64_t)px * 100);
            EXPECT_EQ(net_cost_c(px, c) - c.commission_side_c, (int64_t)px * 100);
            // profit_reached monotono en exit
            int64_t cost = net_cost_c(px, c);
            if (profit_reached(cost, cost + i, 100)) EXPECT(profit_reached(cost, cost + i + 1, 100));
        }
    }
}

// ------------------------------------------------------------ parsers
TEST(parse_nbbo_ok_y_basura) {
    auto n = parse_nbbo("1784664516 708.6100 708.6400");
    EXPECT(n && n->bid_c == 70861 && n->ask_c == 70864 && n->epoch_s == 1784664516);
    EXPECT(!parse_nbbo(""));
    EXPECT(!parse_nbbo("garbage"));
    EXPECT(!parse_nbbo("1784664516 708.64 708.61"));      // invertido
    EXPECT(!parse_nbbo("1784664516 0 708.64"));           // bid 0
}
TEST(parse_chain_real) {
    const char* txt =
        "# opt_chain QQQ | epoch 1784664801 | 2026-07-21 16:13:21 | spot 708.77 | exps 20260721 20260722\n"
        "# strike right exp bid ask vol oi iv delta gamma\n"
        "709.00 C 20260721 0.04 0.05 414481 1697 0.1653 0.4315 0.6328\n"
        "708.00 P 20260721 -1.00 0.02 399425 479 0.2308 -0.1533 0.2718\n"
        "linea basura que no parsea\n"
        "710.00 P 20260721 1.18 1.27 218477 1076 0.1641 -0.9634 0.1293\n";
    auto ch = parse_chain(txt);
    EXPECT(ch && ch->rows.size() == 3);
    EXPECT_EQ(ch->spot_c, 70877);
    EXPECT_EQ(ch->exp0, 20260721);
    EXPECT_EQ(ch->rows[1].bid_c, -100);                   // -1.00 preservado (el selector veta)
    EXPECT(!parse_chain(""));
    EXPECT(!parse_chain("# solo header sin filas\n"));
}
TEST(parse_alert_jsonl_variantes) {
    auto a = parse_alert_jsonl(R"({"ts":1784664700,"side":"CALLS","prev":"MID","sym":"MU","pc":0.22,"vc":29924,"vp":6583,"spot":972.4})");
    EXPECT(a && a->side == 'C' && a->sym == "MU" && a->ts == 1784664700);
    auto b = parse_alert_jsonl(R"({"sym":"QQQ","ts":5,"side":"PUTS"})");   // orden libre
    EXPECT(b && b->side == 'P');
    // json.dumps de Python: espacios tras ':' — debe parsear igual
    auto c = parse_alert_jsonl(R"({"ts": 1784664700, "side": "CALLS", "sym": "AMZN", "pc": 0.0})");
    EXPECT(c && c->side == 'C' && c->sym == "AMZN" && c->ts == 1784664700);
    EXPECT(!parse_alert_jsonl(R"({"ts":5,"side":"MID","sym":"QQQ"})"));    // MID no operable
    EXPECT(!parse_alert_jsonl(R"({"side":"CALLS"})"));                     // sin sym
    EXPECT(!parse_alert_jsonl(""));
    EXPECT(!parse_alert_jsonl(R"({"ts":0,"side":"CALLS","sym":"QQQ"})")); // ts invalido
}
TEST(parse_alert_txt_desktop) {
    auto a = parse_alert_txt("14:51:41 | \xF0\x9F\x90\x8B BALLENA CALLS | MU: flujo calls masivo, P C 0.35 (37,680 calls) — iman", 1000000);
    EXPECT(a && a->side == 'C' && a->sym == "MU");
    EXPECT_EQ(a->ts, 1000000 + 14 * 3600 + 51 * 60 + 41);
    auto b = parse_alert_txt("10:13:21 | \xF0\x9F\x90\x8B BALLENA PUTS | QQQ: flujo puts 6.1 a 1", 0);
    EXPECT(b && b->side == 'P' && b->sym == "QQQ");
    EXPECT(!parse_alert_txt("10:13:21 | V6 BUY | QQQ: otra cosa", 0));       // no ballena
    EXPECT(!parse_alert_txt("", 0));
    EXPECT(!parse_alert_txt("14:51:41 | \xF0\x9F\x90\x8B BALLENA CALLS | mu: minusculas", 0));
    EXPECT(!parse_alert_txt("basura sin hora | \xF0\x9F\x90\x8B BALLENA CALLS | MU: x", 0));
}

// ------------------------------------------------------------ seleccion de contrato
static Chain mk_chain(int64_t spot_c, int exp) {
    Chain ch; ch.epoch_s = 1000; ch.spot_c = spot_c; ch.exp0 = exp;
    auto add = [&](double k, char r, int b, int a) {
        ChainRow row; row.strike_c = (int64_t)std::llround(k * 100); row.right = r; row.exp = exp;
        row.bid_c = b; row.ask_c = a; row.iv = 0.2; row.delta = 0.3;
        ch.rows.push_back(row);
    };
    add(708, 'P', 55, 58);   // primer OTM put (spot 708.77)
    add(707, 'P', 30, 33);
    add(709, 'C', 40, 43);   // primer OTM call
    add(710, 'C', 20, 22);
    return ch;
}
TEST(seleccion_primer_otm) {
    Cfg c;
    Chain ch = mk_chain(70877, 20260721);
    auto p = select_contract(ch, 'P', 20260721, c);
    EXPECT(p && p->con.strike_c == 70800 && p->ask_c == 58);
    auto k = select_contract(ch, 'C', 20260721, c);
    EXPECT(k && k->con.strike_c == 70900);
}
TEST(seleccion_gates) {
    Cfg c;
    Chain ch = mk_chain(70877, 20260721);
    ch.rows[0].bid_c = -100;                               // sin bid -> saltar al 707
    auto p = select_contract(ch, 'P', 20260721, c);
    EXPECT(p && p->con.strike_c == 70700);
    ch.rows[0].bid_c = 55; ch.rows[0].ask_c = 250;         // >200c -> saltar
    p = select_contract(ch, 'P', 20260721, c);
    EXPECT(p && p->con.strike_c == 70700);
    ch = mk_chain(70877, 20260722);                        // no es 0DTE hoy
    EXPECT(!select_contract(ch, 'P', 20260721, c));
    Chain vacia; vacia.epoch_s = 1; vacia.spot_c = 70877; vacia.exp0 = 20260721;
    EXPECT(!select_contract(vacia, 'P', 20260721, c));
}
TEST(spread_gate) {
    Cfg c;   // max(5% del ask, 3c)
    EXPECT(spread_ok(55, 58, c));       // 3c en ask 58: 5%=2.9c -> abs 3c manda
    EXPECT(!spread_ok(50, 58, c));      // 8c: fuera
    EXPECT(spread_ok(190, 199, c));     // 9c en ask 199: 5%=9.95c -> ok
}

// ------------------------------------------------------------ BS
TEST(bs_sanidad) {
    // ATM 1h a vencer, iv 20%: put y call casi iguales, > 0
    double c1 = bs_price(708.77, 709, 3600.0 / (365 * 24 * 3600), 0.20, 'C');
    double p1 = bs_price(708.77, 709, 3600.0 / (365 * 24 * 3600), 0.20, 'P');
    EXPECT(c1 > 0.1 && c1 < 5.0);
    EXPECT(p1 > 0.1 && p1 < 5.0);
    // expirado: intrinseco puro
    EXPECT(bs_price(700, 710, 0, 0.2, 'P') == 10.0);
    EXPECT(bs_price(700, 710, 0, 0.2, 'C') == 0.0);
    // theta: menos tiempo = menos valor extrinseco
    double far = bs_price(708, 709, 7200.0 / (365 * 24 * 3600), 0.20, 'C');
    double near = bs_price(708, 709, 600.0 / (365 * 24 * 3600), 0.20, 'C');
    EXPECT(far > near);
}

// ------------------------------------------------------------ FSM
struct World {
    Cfg cfg; SimClock clk; Fsm fsm{cfg, clk};
    Inputs in{}; Chain chain = mk_chain(70877, 20260721);
    std::vector<Action> acts;
    World() {
        clk.hhmm = 1005; clk.w = 1784660000;
        in.today_yyyymmdd = 20260721;
        in.und = {clk.w, 70875, 70878};
        chain.epoch_s = clk.w;
        in.chain = &chain;
    }
    void fresh() { in.und.epoch_s = clk.w; chain.epoch_s = clk.w; }
    std::vector<Action> step() {
        acts.clear();
        fsm.step(in, acts);
        in.alert.reset(); in.ev = Inputs::NONE;
        return acts;
    }
    void send_alert(char side, const char* sym) {
        Alert a; a.ts = clk.w; a.side = side; a.sym = sym;
        in.alert = a;
    }
    bool has(std::vector<Action>& v, Action::K k) {
        for (auto& a : v) if (a.k == k) return true;
        return false;
    }
    // avanza y da FILL a la ultima orden enviada
    int last_oid(std::vector<Action>& v) {
        for (auto& a : v) if (a.k == Action::SEND_BUY || a.k == Action::SEND_SELL) return a.order_id;
        return 0;
    }
};

TEST(fsm_camino_feliz_profit) {
    World w;
    w.send_alert('C', "QQQ");                        // CALLS -> comprar PUT
    auto a1 = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::ARMED_WAIT);
    w.clk.advance_ms(2499); w.fresh();
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::ARMED_WAIT);   // borde: 2499 < 2500
    w.clk.advance_ms(1); w.fresh();
    auto a2 = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::ENTRY_PENDING);
    EXPECT(w.has(a2, Action::SEND_BUY));
    int oid = w.last_oid(a2);
    w.clk.advance_ms(200); w.fresh();
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 58;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);
    // profit: bid que da +5% neto -> venta inmediata
    // costo neto = 5865; +5% = 6158.25 -> bid >= (6158.25+65)/100 = 62.24 -> 63c
    w.clk.advance_ms(5000); w.fresh();
    w.in.opt = {63, 66};
    auto a3 = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
    EXPECT(w.has(a3, Action::SEND_SELL));
    int soid = w.last_oid(a3);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = soid; w.in.ev_px_c = 63;
    auto a4 = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);         // verde -> IDLE con cooldown
    EXPECT_EQ(w.fsm.trades_today(), 1);
    EXPECT(!w.has(a4, Action::HALT_WRITE));
}

TEST(fsm_60s_sin_profit_halt) {
    World w;
    w.send_alert('P', "NVDA");                       // PUTS -> comprar CALL
    w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 43;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);
    // 60s sin profit (bid plano = perdedor por comisiones)
    w.in.opt = {43, 46};
    w.clk.advance_ms(59999); w.fresh(); w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);      // borde: 59999
    w.clk.advance_ms(1); w.fresh();
    auto b = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
    int soid = w.last_oid(b);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = soid; w.in.ev_px_c = 43;
    auto c = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HALTED);       // rojo neto (-130c) = HALT
    EXPECT(w.has(c, Action::HALT_WRITE));
    // alerta post-halt: muerta
    w.send_alert('C', "QQQ");
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HALTED);
}

TEST(fsm_entrada_no_llena_3_intentos) {
    World w;
    w.send_alert('C', "QQQ");
    w.step();
    w.clk.advance_ms(2500); w.fresh();
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::ENTRY_PENDING);
    w.in.opt = {55, 58};                                  // quote viva para re-price
    for (int i = 0; i < 3; ++i) { w.clk.advance_ms(1500); w.fresh(); w.step(); }
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);         // 3 intentos y fuera, sin dinero
    EXPECT_EQ(w.fsm.trades_today(), 0);
}

TEST(fsm_gates_entrada) {
    World w;
    // fuera de ventana
    w.clk.hhmm = 1135;
    w.send_alert('C', "QQQ"); w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    // simbolo fuera de IMPACT
    w.clk.hhmm = 1010;
    w.send_alert('C', "NOK"); w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    // halt file
    w.in.halt_file = true;
    w.send_alert('C', "QQQ"); w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    w.in.halt_file = false;
    // NBBO stale al disparo
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500);
    w.in.und.epoch_s = w.clk.w - 10; w.chain.epoch_s = w.clk.w;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    // chain stale al disparo
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.in.und.epoch_s = w.clk.w; w.chain.epoch_s = w.clk.w - 700;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
}

TEST(fsm_alertas_ignoradas_en_posicion) {
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.send_alert('P', "QQQ");                             // opuesta en ARMED_WAIT
    auto a = w.step();
    bool ignored = false;
    for (auto& x : a) if (x.ev == "ALERT_IGNORED") ignored = true;
    EXPECT(ignored);
    EXPECT_EQ((int)w.fsm.state(), (int)St::ARMED_WAIT);
}

TEST(fsm_trailing_1_a_5) {
    // premium 150c: banda verde 153..158 (min +1% = bid 153, +5% = bid 159)
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 150;  // costo neto 15065
    w.step();
    w.clk.advance_ms(5000); w.fresh();
    w.in.opt = {153, 157};                                 // arma el trail (+1.1% neto)
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);
    w.clk.advance_ms(1000); w.fresh();
    w.in.opt = {157, 161};                                 // pico 157, aun < +5%
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);
    w.clk.advance_ms(1000); w.fresh();
    w.in.opt = {154, 158};                                 // retro 3c desde pico -> vende VERDE
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
}

TEST(fsm_trailing_5pct_inmediato) {
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 150;
    w.step();
    w.clk.advance_ms(5000); w.fresh();
    w.in.opt = {159, 163};                                 // +5% neto directo -> vende YA
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
}

TEST(fsm_trail_jamas_vende_rojo) {
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 150;  // costo neto 15065
    w.step();
    w.clk.advance_ms(5000); w.fresh();
    w.in.opt = {153, 157};                                 // arma
    w.step();
    w.clk.advance_ms(1000); w.fresh();
    w.in.opt = {148, 152};                                 // cae BAJO breakeven: NO vender rojo
    auto b = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);        // desarmado, aguantando
    bool disarm = false;
    for (auto& x : b) if (x.ev == "TRAIL_DISARM") disarm = true;
    EXPECT(disarm);
    // evapora pero VERDE: bid 152 -> exit 15135 > 15065 -> cobrar
    w.clk.advance_ms(1000); w.fresh();
    w.in.opt = {153, 157};                                 // re-arma
    w.step();
    w.clk.advance_ms(1000); w.fresh();
    w.in.opt = {152, 156};                                 // < min pero verde -> cobrar
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
}

TEST(fsm_force_flat) {
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 58;
    w.step();
    w.clk.hhmm = 1555;                                     // 15:55
    w.clk.advance_ms(1000); w.fresh();
    w.in.opt = {58, 61};
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
}

TEST(fsm_recovery) {
    World w;
    OptContract c{70800, 'P', 20260721};
    w.acts.clear();
    w.fsm.recover_holding(c, 58, 999999, w.acts);          // vieja: salida directa
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
    World w2;
    w2.acts.clear();
    w2.fsm.recover_holding(c, 58, 5000, w2.acts);          // joven: gestionar
    EXPECT_EQ((int)w2.fsm.state(), (int)St::HOLDING);
}

// ------------------------------------------------------------ review 2026-07-22
TEST(parse_alert_jsonl_escalada) {
    // BALLENA CRECE (prev=ESCALADA): parsea, pero marcada esc — NO es flip
    auto a = parse_alert_jsonl(R"({"ts":1784740000,"side":"CALLS","prev":"ESCALADA","sym":"NVDA","pc":0.2,"vc":248000,"vp":40000,"spot":170.1})");
    EXPECT(a && a->side == 'C' && a->esc);
    auto b = parse_alert_jsonl(R"({"ts":1784740000,"side":"CALLS","prev":"MID","sym":"NVDA","pc":0.2})");
    EXPECT(b && !b->esc);                                  // flip normal: esc false
}
TEST(parse_nbbo_nan_inf_absurdo) {
    EXPECT(!parse_nbbo("1784664516 nan nan"));             // NaN parsea en %lf: veneno para llround
    EXPECT(!parse_nbbo("1784664516 inf inf"));
    EXPECT(!parse_nbbo("nan 708.61 708.64"));
    EXPECT(!parse_nbbo("1784664516 708.61 999999999"));    // $1e9: fisicamente absurdo
    EXPECT(!parse_nbbo("99999999999 708.61 708.64"));      // epoch > año 2100
    EXPECT(parse_nbbo("1784664516 708.6100 708.6400"));    // el bueno sigue pasando
}
TEST(parse_chain_absurdos) {
    const char* txt =
        "# opt_chain QQQ | epoch 1784664801 | fecha | spot 708.77 | exps 20260721\n"
        "709.00 C 20260721 0.04 0.05 1 1 0.1653 0.4315 0.6\n"
        "710.00 C 20260721 nan 0.05 1 1 0.16 0.43 0.6\n"          // bid NaN: fila fuera
        "711.00 C 20260721 0.04 99999999 1 1 0.16 0.43 0.6\n"     // ask absurdo (overflow int): fuera
        "-5.00 C 20260721 0.04 0.05 1 1 0.16 0.43 0.6\n"          // strike negativo: fuera
        "708.00 P 20260721 -1.00 0.02 1 1 0.23 -0.15 0.2\n";      // sentinel -1.00: se PRESERVA
    auto ch = parse_chain(txt);
    EXPECT(ch && ch->rows.size() == 2);
    EXPECT_EQ(ch->rows[1].bid_c, -100);
    // header con spot nan -> chain invalida (jamas llround(NaN))
    EXPECT(!parse_chain("# opt_chain QQQ | epoch 1784664801 | f | spot nan | exps 20260721\n"
                        "709.00 C 20260721 0.04 0.05 1 1 0.16 0.43 0.6\n"));
}
TEST(parse_alert_lines_todas) {
    std::vector<std::string> lines = {
        R"({"ts":100,"side":"MID","prev":"CALLS","sym":"QQQ"})",     // MID: fuera
        R"({"ts":101,"side":"CALLS","prev":"MID","sym":"NOK"})",     // valida (impact se filtra despues)
        "basura no json",
        R"({"ts":102,"side":"PUTS","prev":"MID","sym":"QQQ"})",      // valida
    };
    auto v = parse_alert_lines(lines);
    EXPECT_EQ(v.size(), 2u);
    EXPECT(v[0].sym == "NOK" && v[1].sym == "QQQ" && v[1].side == 'P');  // orden preservado
}
TEST(age_ms_helper) {
    EXPECT_EQ(age_ms_from_us(2000000, 1000000), 1000);
    EXPECT_EQ(age_ms_from_us(1000000, 2000000), 0);        // futuro/garbage -> 0 (gestionar)
    EXPECT_EQ(age_ms_from_us(1000000, 0), 0);
    EXPECT_EQ(age_ms_from_us(1000000, -5), 0);
}
TEST(cfg_nbbo_grace) {
    Cfg c;
    EXPECT_EQ(c.nbbo_hold_grace_ms, 2000);                 // default = comportamiento previo
    cfg_set(c, "NBBO_HOLD_GRACE_MS", "3500");
    EXPECT_EQ(c.nbbo_hold_grace_ms, 3500);
}
TEST(fsm_escalada_veto) {
    World w;
    // escalada en IDLE: no es flip -> jamas arma
    w.send_alert('C', "QQQ"); w.in.alert->esc = true;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    // flip arma; escalada del MISMO lado durante wait -> aborta (marea sigue)
    w.send_alert('C', "QQQ"); w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::ARMED_WAIT);
    w.clk.advance_ms(1000); w.fresh();
    w.send_alert('C', "QQQ"); w.in.alert->esc = true;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    // re-arma; escalada del OTRO lado: solo ignorada, sigue armado
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(1000); w.fresh();
    w.send_alert('P', "QQQ"); w.in.alert->esc = true;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::ARMED_WAIT);
}
TEST(fsm_stale_fill_adopta_en_entry) {
    // el BUY del intento 1 (cancelado) llena DESPUES del re-price: adoptar,
    // matar la orden viva, jamas ignorar dinero real
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid1 = w.last_oid(a);
    EXPECT_EQ((int)w.fsm.state(), (int)St::ENTRY_PENDING);
    w.in.opt = {55, 58};                                   // quote viva: re-price posible
    w.clk.advance_ms(1500); w.fresh();
    auto b = w.step();                                     // cancel oid1 + BUY intento 2
    EXPECT(w.has(b, Action::CANCEL) && w.has(b, Action::SEND_BUY));
    w.clk.advance_ms(100); w.fresh();
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid1; w.in.ev_px_c = 58;   // fill del CANCELADO
    auto c = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);
    EXPECT(w.has(c, Action::CANCEL));                      // la orden viva (intento 2) se mata
    bool adopt = false;
    for (auto& x : c) if (x.ev == "FILL_ADOPT") adopt = true;
    EXPECT(adopt);
}
TEST(fsm_stale_fill_adopta_en_idle) {
    // NO_FILL rindio (sin quote) -> IDLE; el fill del cancelado llega tarde
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid1 = w.last_oid(a);
    w.in.opt = {};                                         // sin quote: rendirse al timeout
    w.clk.advance_ms(1500); w.fresh();
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    w.clk.advance_ms(200); w.fresh();
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid1; w.in.ev_px_c = 58;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);       // posicion real adoptada
}
TEST(fsm_stale_sell_fill_cierra) {
    // el SELL cancelado (re-price) llena igual: ESE es el cierre; trade contado
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 58;
    w.step();
    w.clk.advance_ms(5000); w.fresh();
    w.in.opt = {63, 66};                                   // +5% neto -> EXIT_PENDING
    auto b = w.step();
    int sell1 = w.last_oid(b);
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
    w.clk.advance_ms(2000); w.fresh();
    auto c = w.step();                                     // re-price: cancel sell1, envia sell2
    EXPECT(w.has(c, Action::CANCEL));
    w.clk.advance_ms(100); w.fresh();
    w.in.ev = Inputs::FILL; w.in.ev_order_id = sell1; w.in.ev_px_c = 63;  // fill del CANCELADO
    auto d = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);          // verde cerrado
    EXPECT_EQ(w.fsm.trades_today(), 1);
    EXPECT(w.has(d, Action::CANCEL));                      // sell2 vivo se mata
}
TEST(fsm_orphan_fill_notifica) {
    World w;
    w.in.ev = Inputs::FILL; w.in.ev_order_id = 777; w.in.ev_px_c = 50;
    auto a = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);          // sin estado nuevo
    bool orphan = false, notified = false;
    for (auto& x : a) { if (x.ev == "ORPHAN_FILL") orphan = true; if (x.k == Action::NOTIFY) notified = true; }
    EXPECT(orphan && notified);                            // jamas en silencio
}
TEST(fsm_recover_day) {
    World w;                                               // dia con 2 cierres verdes
    w.acts.clear();
    w.fsm.recover_day(2, false, 999999999, w.acts);
    EXPECT_EQ(w.fsm.trades_today(), 2);
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    World w2;                                              // dia ROJO: HALT restaurado
    w2.acts.clear();
    w2.fsm.recover_day(1, true, 5000, w2.acts);
    EXPECT_EQ((int)w2.fsm.state(), (int)St::HALTED);
    w2.send_alert('C', "QQQ"); w2.step();
    EXPECT_EQ((int)w2.fsm.state(), (int)St::HALTED);       // muerto sigue muerto
    World w3;                                              // cierre hace 1s: cooldown activo
    w3.acts.clear();
    w3.fsm.recover_day(1, false, 1000, w3.acts);
    w3.send_alert('C', "QQQ");
    auto a = w3.step();
    EXPECT_EQ((int)w3.fsm.state(), (int)St::IDLE);         // GATE_SKIP cooldown
    bool skip = false;
    for (auto& x : a) if (x.ev == "GATE_SKIP") skip = true;
    EXPECT(skip);
}
// ------------------------------------------------------------ review 2026-07-22 (ronda B)
TEST(fsm_entry_abort_halt_y_forceflat) {
    // BUY vivo + HALT file -> cancelar YA, IDLE, cero dinero
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::ENTRY_PENDING);
    w.in.halt_file = true;
    w.clk.advance_ms(100); w.fresh();
    auto a = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    EXPECT(w.has(a, Action::CANCEL));
    EXPECT_EQ(w.fsm.trades_today(), 0);
    // BUY vivo + force-flat (15:55) -> igual: cancelar y fuera
    World w2;
    w2.send_alert('C', "QQQ"); w2.step();
    w2.clk.advance_ms(2500); w2.fresh();
    w2.step();
    EXPECT_EQ((int)w2.fsm.state(), (int)St::ENTRY_PENDING);
    w2.clk.hhmm = 1556;
    w2.clk.advance_ms(100); w2.fresh();
    auto b = w2.step();
    EXPECT_EQ((int)w2.fsm.state(), (int)St::IDLE);
    EXPECT(w2.has(b, Action::CANCEL));
}
TEST(fsm_halt_cancel_fill_gana_y_se_gestiona) {
    // verificador 2026-07-22: HALT durante entrada -> cancel; el fill GANA al
    // cancel con halt_file AUN puesto -> adopcion obligatoria (dinero real) y
    // salida forzada inmediata por HALT en mano. Jamas posicion huerfana.
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.halt_file = true;
    w.clk.advance_ms(100); w.fresh();
    auto b = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    EXPECT(w.has(b, Action::CANCEL));
    // el fill del BUY cancelado llega con el HALT aun activo
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 58;
    auto c = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);       // adoptada, no ignorada
    bool adopted = false;
    for (auto& x : c) if (x.k == Action::LEDGER && x.ev == "FILL_ADOPT") adopted = true;
    EXPECT(adopted);
    // siguiente tick: HALT en mano -> salida forzada YA
    w.clk.advance_ms(100); w.fresh();
    auto d = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
    EXPECT(w.has(d, Action::SEND_SELL));
}
TEST(fsm_nbbo_invalido_en_mano) {
    // NBBO JAMAS visto (ok()=false) con posicion: misma gracia que stale -> salida
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 58;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);
    w.in.und = {};                                         // NBBO muere del todo
    w.clk.advance_ms(2000); w.chain.epoch_s = w.clk.w;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::HOLDING);       // borde: 2000 = gracia, aun no
    w.clk.advance_ms(1);
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);  // 2001 > gracia: fuera
}
TEST(fsm_last_bid_reset_entre_trades) {
    // el bid memorizado del trade 1 JAMAS pone precio a la salida del trade 2
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto a = w.step();
    int oid = w.last_oid(a);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid; w.in.ev_px_c = 58;
    w.step();
    w.clk.advance_ms(5000); w.fresh();
    w.in.opt = {63, 66};                                   // +5% -> EXIT (bid 63 memorizado)
    auto b = w.step();
    int soid = w.last_oid(b);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = soid; w.in.ev_px_c = 63;
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);          // verde, cooldown
    w.in.opt = {};                                         // trade 2: sin quote nunca
    w.clk.advance_ms(120000); w.fresh();
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto c = w.step();
    int oid2 = w.last_oid(c);
    EXPECT_EQ((int)w.fsm.state(), (int)St::ENTRY_PENDING);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid2; w.in.ev_px_c = 58;
    w.step();
    w.in.und = {};                                         // NBBO muere: salida a ciegas
    w.clk.advance_ms(2100); w.chain.epoch_s = w.clk.w;
    auto d = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
    int sell_px = -1;
    for (auto& x : d) if (x.k == Action::SEND_SELL) sell_px = x.limit_c;
    EXPECT_EQ(sell_px, 1);                                 // fallback 1c, NO el 63 del trade 1
}
TEST(fsm_last_bid_no_contamina_tras_no_fill) {
    // hueco del verificador 2026-07-22: una entrada ABANDONADA (NO_FILL) no
    // limpia con_, el driver sigue cotizando el contrato abandonado en IDLE y
    // last_opt_bid_c_ se re-contamina; la salida a ciegas del trade siguiente
    // debe ser el fallback honesto 1c, JAMAS el bid del contrato abandonado.
    World w;
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::ENTRY_PENDING);
    // sin fill y sin quote -> NO_FILL abandona en el primer timeout
    w.in.opt = {};
    w.clk.advance_ms(1500); w.fresh();
    w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::IDLE);
    // driver: held() sigue valido tras el abandono -> cotiza el contrato viejo
    w.in.opt = {63, 66};
    w.clk.advance_ms(1000); w.fresh();
    w.step();                                              // last_opt_bid_c_ <- 63 (contaminado)
    // trade 2: quote del contrato nuevo rota (jamas ok)
    w.in.opt = {};
    w.send_alert('C', "QQQ"); w.step();
    w.clk.advance_ms(2500); w.fresh();
    auto c = w.step();
    int oid2 = w.last_oid(c);
    EXPECT_EQ((int)w.fsm.state(), (int)St::ENTRY_PENDING);
    w.in.ev = Inputs::FILL; w.in.ev_order_id = oid2; w.in.ev_px_c = 58;
    w.step();
    w.in.und = {};                                         // NBBO muere: salida a ciegas
    w.clk.advance_ms(2100); w.chain.epoch_s = w.clk.w;
    auto d = w.step();
    EXPECT_EQ((int)w.fsm.state(), (int)St::EXIT_PENDING);
    int sell_px = -1;
    for (auto& x : d) if (x.k == Action::SEND_SELL) sell_px = x.limit_c;
    EXPECT_EQ(sell_px, 1);                                 // 1c honesto, NO el 63 del abandonado
}
static void append_file(const char* p, const std::string& s) {
    FILE* f = std::fopen(p, "a"); if (f) { std::fputs(s.c_str(), f); std::fclose(f); }
}
TEST(ledger_trunc_y_daystate) {
    const char* dir = "/tmp/scalper_ledger_test";
    ::mkdir(dir, 0755);
    Ledger led(dir);
    ::unlink(led.path().c_str());
    OptContract con{70400, 'P', 20260722};
    // reason gigante: la linea DEBE seguir terminando en '\n' (ledger legible)
    led.write("GATE_SKIP", "IDLE", con, 0, 0, std::string(3000, 'x'), 1);
    led.write("FILL", "HOLDING", con, 146, 1, "BUY @ 146c", 2);
    {
        FILE* f = std::fopen(led.path().c_str(), "r");
        EXPECT(f != nullptr);
        int nl = 0, lines = 0; int ch; int last = 0;
        while ((ch = std::fgetc(f)) != EOF) { if (ch == '\n') ++nl; last = ch; }
        std::fclose(f);
        lines = nl;
        EXPECT_EQ(lines, 2);                               // 2 eventos = 2 lineas exactas
        EXPECT_EQ(last, (int)'\n');
    }
    auto open = led.find_open_position();
    EXPECT(open && open->fill_c == 146 && open->con.strike_c == 70400 && open->con.right == 'P');
    // cierre ROJO -> sin posicion abierta + day_state rojo
    led.write("TRADE_CLOSE", "IDLE", con, 0, 2, "net -530c (buy 146 sell 142)", 3);
    EXPECT(!led.find_open_position());
    auto ds = led.day_state();
    EXPECT(ds.closes == 1 && ds.red && ds.last_close_us > 0);
    // cierre verde adicional: closes 2, red se mantiene
    led.write("TRADE_CLOSE", "IDLE", con, 0, 3, "net 70c (buy 146 sell 148)", 4);
    ds = led.day_state();
    EXPECT(ds.closes == 2 && ds.red);
}
TEST(ledger_fill_px_fallback) {
    // ledgers de HOY (pre-fix) tienen px_c:0 y el precio SOLO en el reason
    const char* dir = "/tmp/scalper_ledger_test2";
    ::mkdir(dir, 0755);
    Ledger led(dir);
    ::unlink(led.path().c_str());
    append_file(led.path().c_str(),
        "{\"tw\":1784727968313618,\"tm\":1,\"ev\":\"FILL\",\"state\":\"HOLDING\","
        "\"strike_c\":70400,\"right\":\"P\",\"exp\":20260722,\"px_c\":0,\"oid\":1,\"reason\":\"BUY @ 146c\"}\n");
    auto open = led.find_open_position();
    EXPECT(open && open->fill_c == 146);                   // rescatado del reason
    EXPECT(open && open->tw_us == 1784727968313618LL);
}
TEST(tail_gigante_y_rotacion) {
    const char* p = "/tmp/scalper_tail_test.txt";
    ::unlink(p);
    append_file(p, "vieja\n");
    Tail t; t.path = p;
    EXPECT(t.read_new().empty());                          // primer contacto = EOF: viejas NO
    append_file(p, "b\n");
    auto v = t.read_new();
    EXPECT(v.size() == 1 && v[0] == "b");
    // linea gigante (5000 chars > buffer 2048): descartada, el tail NO se bloquea
    append_file(p, std::string(5000, 'X') + "\nc\n");
    v = t.read_new();
    EXPECT(v.size() == 1 && v[0] == "c");
    // rotacion (archivo encoge): saltar a EOF y seguir vivo
    { FILE* f = std::fopen(p, "w"); if (f) { std::fputs("d\n", f); std::fclose(f); } }
    v = t.read_new();
    EXPECT(v.empty());                                     // conservador: no re-lee tras rotar
    append_file(p, "e\n");
    v = t.read_new();
    EXPECT(v.size() == 1 && v[0] == "e");
    // linea a medio escribir: esperar; completa: entregar
    append_file(p, "parcial");
    EXPECT(t.read_new().empty());
    append_file(p, "_fin\n");
    v = t.read_new();
    EXPECT(v.size() == 1 && v[0] == "parcial_fin");
}

int main() {
    for (auto& [n, f] : tests()) f();
    if (g_fail) { std::printf("\n%d FAILURES\n", g_fail); return 1; }
    std::printf("\nALL OK (%zu tests)\n", tests().size());
    return 0;
}
