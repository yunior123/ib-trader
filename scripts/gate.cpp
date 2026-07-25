// gate.cpp — EL GATE DE OPCIONES: fuente UNICA de verdad (C++23).
// Orden Yunior 2026-07-25: "python solo para test, la computacion en C++".
//
// La aritmetica vive en scripts/gate_core.hpp (ahi esta escrito el porque, con los tres bugs
// del camino del dinero y sus numeros). Este archivo es solo la CARA: lee data/opt_chain_<sym>.txt,
// llama a gate::evaluate() y escribe el veredicto en data/gate_<sym>.json (atomico tmp+rename)
// y por stdout. El mismo header lo incluye order_engine/order_engine.cpp, asi que el motor que
// SI manda ordenes a TWS y las alarmas que solo cantan usan LA MISMA cuenta. Nunca mas dos.
//
// DOS MODOS, porque hay dos preguntas distintas:
//   SONDEO   ./gate DRAM QQQ MU
//            "¿se pueden pagar opciones en este nombre AHORA?" — primer OTM liquido de la
//            cadena (criterio calcado de optgate.py para no cambiar el universo).
//   FICHA    ./gate NVDA 210 buy call
//            "este nivel, este lado, este tipo: ¿que contrato, a que limite, cuantos?" —
//            strike mas cercano al nivel, expiry mas proxima (0DTE si existe hoy).
//
// TEST     ./gate --ev-stdin < ev.json     evidencia inyectada -> JSON por stdout, sin tocar
//                                          data/. Es como lo conduce tests/test_gate.py
//                                          (Python SOLO como arnes).
//
// Umbrales por entorno (defaults = doctrina): OPT_MAX_SPREAD_PCT OPT_MIN_OI OPT_BUDGET_USD
// OPT_MAX_AGE_S OPT_CAUTION_SPREAD_PCT OPT_CAUTION_OI.
//
// RUTAS: NUNCA hardcodeadas. El repo se movio a ~/ib-trader el 2026-07-25; el raiz se deduce
// del propio binario (realpath(argv[0]) -> dirname), con IBT_REPO como override para tests.
//
// SENAL-SOLAMENTE: escribe JSON de diagnostico y texto. Jamas ordena nada.
//   compilar: ./scripts/build_gate.sh
#include <charconv>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

#include <limits.h>
#include <stdlib.h>
#include <unistd.h>

#include "gate_core.hpp"

// --------------------------- JSON minimo (idiom del repo: compass.cpp / flow_pulse.cpp) -----
static std::optional<double> jnum(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n')) ++p;
    if (p < s.size() && (s[p] == 'n' || s[p] == '"')) return std::nullopt;  // null / string
    double out{};
    auto [ptr, ec] = std::from_chars(s.data() + p, s.data() + s.size(), out);
    if (ec != std::errc{}) return std::nullopt;
    (void)ptr;
    return out;
}
static std::optional<std::string> jstr(std::string_view s, std::string_view key) {
    // OJO: no se puede exigir la comilla pegada a los dos puntos. json.dump() de Python escribe
    // ": " CON espacio y asi salen todos los data/*.json; hay que saltar los blancos o el valor
    // se lee como ausente (mismo comentario que compass.cpp — es el bug clasico de este repo).
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\t' || s[p] == '\n')) ++p;
    if (p >= s.size() || s[p] != '"') return std::nullopt;   // null / numero / objeto
    ++p;
    auto e = s.find('"', p);
    if (e == std::string_view::npos) return std::nullopt;
    return std::string(s.substr(p, e - p));
}
// (sin jbool: la evidencia de este gate no tiene ningun booleano — todo es numero o cadena,
//  y -Wall -Wextra con cero warnings es ley de la flota. Si algun dia hace falta, esta en
//  compass.cpp tal cual.)
static std::optional<std::string> jarr(std::string_view s, std::string_view key) {
    std::string pat = "\"" + std::string(key) + "\":";
    auto p = s.find(pat);
    if (p == std::string_view::npos) return std::nullopt;
    p += pat.size();
    while (p < s.size() && (s[p] == ' ' || s[p] == '\n')) ++p;
    if (p >= s.size() || s[p] != '[') return std::nullopt;
    int depth = 0;
    for (size_t i = p; i < s.size(); ++i) {
        if (s[i] == '[') ++depth;
        else if (s[i] == ']') { if (--depth == 0) return std::string(s.substr(p, i - p + 1)); }
    }
    return std::nullopt;
}
static std::vector<std::string> jobjs(const std::string& arr) {
    std::vector<std::string> out;
    int depth = 0; size_t st = 0;
    for (size_t i = 0; i < arr.size(); ++i) {
        if (arr[i] == '{') { if (depth++ == 0) st = i; }
        else if (arr[i] == '}') { if (--depth == 0) out.push_back(arr.substr(st, i - st + 1)); }
    }
    return out;
}
static std::string slurp_stdin() {
    std::ostringstream ss;
    ss << std::cin.rdbuf();
    return ss.str();
}
static std::string jesc(const std::string& s) {
    std::string o;
    o.reserve(s.size() + 8);
    for (char c : s) {
        if (c == '"' || c == '\\') { o += '\\'; o += c; }
        else if (c == '\n') o += "\\n";
        else if ((unsigned char)c < 0x20) continue;      // control -> fuera
        else o += c;
    }
    return o;
}

// --------------------------- raiz del repo (NUNCA hardcodear) ---------------------------
static std::string repo_root(const char* argv0) {
    if (const char* e = std::getenv("IBT_REPO")) if (*e) return std::string(e);
    char buf[PATH_MAX];
    if (argv0 && realpath(argv0, buf)) {
        std::string p(buf);
        auto slash = p.find_last_of('/');
        if (slash != std::string::npos) return p.substr(0, slash);
    }
    if (getcwd(buf, sizeof buf)) return std::string(buf);
    return ".";
}

// ------------------------------- salida -------------------------------------
static std::string to_json(const gate::Verdict& v, const std::string& sym,
                           const char* mode, const gate::Chain& ch) {
    std::string s = "{";
    char b[640];
    s += "\"sym\":\"" + jesc(sym) + "\",\"mode\":\"" + std::string(mode) + "\",";
    s += "\"verdict\":\"" + v.verdict + "\",\"codigo\":\"" + v.codigo + "\",";
    std::snprintf(b, sizeof b, "\"verdict_known\":%s,\"go\":%s,",
                  v.known ? "true" : "false", v.go ? "true" : "false");
    s += b;
    // contrato
    if (v.have_row) {
        std::snprintf(b, sizeof b,
                      "\"contract\":{\"strike\":%.4f,\"right\":\"%s\",\"exp\":\"%s\",\"oi\":%ld,"
                      "\"oi_ok\":%s,\"delta\":%.4f,\"iv\":%.4f},",
                      v.strike, v.right.c_str(), jesc(v.exp).c_str(), v.oi,
                      v.oi_ok ? "true" : "false", v.delta, v.iv);
        s += b;
    } else {
        s += "\"contract\":null,";
    }
    // cotizacion
    const char* qs = v.qstate == gate::QState::OK ? "OK"
                   : (v.qstate == gate::QState::CROSSED ? "CRUZADO" : "SIN_DATO");
    std::snprintf(b, sizeof b, "\"quote\":{\"state\":\"%s\",\"bid\":%.4f,\"ask\":%.4f,", qs,
                  v.bid, v.ask);
    s += b;
    if (v.have_spread) {
        std::snprintf(b, sizeof b, "\"mid\":%.4f,\"spread_pct\":%.4f,\"spread_ok\":%s},",
                      v.mid, v.spread_pct, v.spread_ok ? "true" : "false");
    } else {
        // sin dato NO es spread 0: es null. Que nadie lo lea como "spread perfecto".
        std::snprintf(b, sizeof b, "\"mid\":null,\"spread_pct\":null,\"spread_ok\":false},");
    }
    s += b;
    // frescura
    if (v.have_age) {
        std::snprintf(b, sizeof b,
                      "\"freshness\":{\"epoch\":%lld,\"age_s\":%.0f,\"fresh\":%s,\"max_age_s\":%.0f},",
                      (long long)ch.epoch, v.age_s, v.fresh ? "true" : "false", v.p.max_age_s);
    } else {
        std::snprintf(b, sizeof b,
                      "\"freshness\":{\"epoch\":null,\"age_s\":null,\"fresh\":false,\"max_age_s\":%.0f},",
                      v.p.max_age_s);
    }
    s += b;
    // dinero
    std::snprintf(b, sizeof b,
                  "\"money\":{\"side\":\"%c\",\"limit\":%.4f,\"premium\":%.2f,\"size\":%d,"
                  "\"budget_usd\":%.2f,\"budget_ok\":%s},",
                  v.side, v.limit, v.premium, v.size, v.p.budget_usd,
                  v.budget_ok ? "true" : "false");
    s += b;
    std::snprintf(b, sizeof b,
                  "\"gates\":{\"max_spread_pct\":%.4f,\"min_oi\":%ld,\"budget_usd\":%.2f,"
                  "\"max_age_s\":%.0f},",
                  v.p.max_spread_pct, v.p.min_oi, v.p.budget_usd, v.p.max_age_s);
    s += b;
    if (ch.have_spot) { std::snprintf(b, sizeof b, "\"spot\":%.4f,", ch.spot); s += b; }
    else s += "\"spot\":null,";
    s += "\"why\":[";
    for (size_t i = 0; i < v.why.size(); ++i) {
        if (i) s += ",";
        s += "\"" + jesc(v.why[i]) + "\"";
    }
    s += "],";
    std::snprintf(b, sizeof b, "\"ts\":%ld}", (long)time(nullptr));
    s += b;
    return s;
}

static std::string human(const gate::Verdict& v, const std::string& sym) {
    const char* icon = v.verdict == "GO" ? "🟢" : (v.verdict == "CAUTION" ? "🟡" : "🔴");
    char b[512];
    if (!v.have_row) {
        std::snprintf(b, sizeof b, "%s %s %s (%s) — %s", icon, sym.c_str(), v.verdict.c_str(),
                      v.codigo.c_str(), v.why.empty() ? "sin motivo" : v.why[0].c_str());
        return b;
    }
    std::string head;
    if (v.have_spread) {
        std::snprintf(b, sizeof b,
                      "%s %s %g%s %s %s (%s) — límite $%.2f, prima $%.0f, size %d, "
                      "spread %.2f%%, OI %ld, edad %.0fs",
                      icon, sym.c_str(), v.strike, v.right.c_str(), v.exp.c_str(),
                      v.verdict.c_str(), v.codigo.c_str(), v.limit, v.premium, v.size,
                      v.spread_pct, v.oi, v.age_s);
    } else {
        std::snprintf(b, sizeof b,
                      "%s %s %g%s %s %s (%s) — SIN DATO de bid/ask, OI %ld",
                      icon, sym.c_str(), v.strike, v.right.c_str(), v.exp.c_str(),
                      v.verdict.c_str(), v.codigo.c_str(), v.oi);
    }
    head = b;
    if (!v.known) head += " [SIN VEREDICTO: no hay con que juzgar]";
    return head;
}

static bool write_atomic(const std::string& repo, const std::string& sym_lo,
                         const std::string& js) {
    std::string tmp = repo + "/data/.gate_" + sym_lo + ".tmp";
    std::string dst = repo + "/data/gate_" + sym_lo + ".json";
    FILE* f = std::fopen(tmp.c_str(), "w");
    if (!f) return false;
    std::fprintf(f, "%s\n", js.c_str());
    std::fclose(f);
    return std::rename(tmp.c_str(), dst.c_str()) == 0;
}

// ------------------------- evidencia inyectada (TEST) -----------------------
struct Ev {
    std::string sym = "TEST", mode = "ticket", side = "buy", kind = "call", exp;
    gate::Chain ch;
    double level = 0;
    long long now = 0;
    gate::Params p;
};

static Ev ev_from_json(const std::string& j, const std::string& repo) {
    Ev e;
    e.p = gate::params_from_env();
    if (auto s = jstr(j, "sym")) e.sym = *s;
    if (auto s = jstr(j, "mode")) e.mode = *s;
    if (auto s = jstr(j, "side")) e.side = *s;
    if (auto s = jstr(j, "kind")) e.kind = *s;
    if (auto s = jstr(j, "exp")) e.exp = *s;
    if (auto v = jnum(j, "level")) e.level = *v;
    if (auto v = jnum(j, "now")) e.now = (long long)*v;
    if (auto v = jnum(j, "budget")) e.p.budget_usd = *v;
    if (auto v = jnum(j, "max_spread_pct")) e.p.max_spread_pct = *v;
    if (auto v = jnum(j, "min_oi")) e.p.min_oi = (long)*v;
    if (auto v = jnum(j, "max_age_s")) e.p.max_age_s = *v;
    if (auto v = jnum(j, "caution_spread_pct")) e.p.caution_spread_pct = *v;
    if (auto v = jnum(j, "caution_oi")) e.p.caution_oi = (long)*v;

    // (a) cadena REAL desde archivo -> ejercita el parser de verdad (cabecera incluida)
    if (auto f = jstr(j, "chain_file")) {
        std::string path = *f;
        if (!path.empty() && path[0] != '/') path = repo + "/" + path;
        e.ch = gate::load_chain(path, e.sym);
        return e;
    }
    // (b) filas inline: la cabecera se declara por campos. "epoch" ausente o <=0 => SIN epoch
    //     (que es exactamente el fail-open que estamos cerrando).
    e.ch.sym = e.sym;
    if (auto v = jnum(j, "epoch")) if (*v > 0) { e.ch.epoch = (long long)*v; e.ch.have_epoch = true; }
    if (auto v = jnum(j, "spot")) if (*v > 0) { e.ch.spot = *v; e.ch.have_spot = true; }
    if (auto a = jarr(j, "exps")) {
        std::string_view sv(*a);
        size_t p = 0;
        while (true) {
            auto q1 = sv.find('"', p);
            if (q1 == std::string_view::npos) break;
            auto q2 = sv.find('"', q1 + 1);
            if (q2 == std::string_view::npos) break;
            e.ch.exps.emplace_back(sv.substr(q1 + 1, q2 - q1 - 1));
            p = q2 + 1;
        }
    }
    if (auto a = jarr(j, "rows")) {
        for (const auto& ob : jobjs(*a)) {
            gate::Row r;
            r.strike = jnum(ob, "strike").value_or(0);
            r.right = jstr(ob, "right").value_or("C");
            r.exp = jstr(ob, "exp").value_or(e.ch.exps.empty() ? "" : e.ch.exps.front());
            r.bid = jnum(ob, "bid").value_or(-1);
            r.ask = jnum(ob, "ask").value_or(-1);
            r.vol = (long)jnum(ob, "vol").value_or(0);
            r.oi = (long)jnum(ob, "oi").value_or(0);
            r.iv = jnum(ob, "iv").value_or(-1);
            r.delta = jnum(ob, "delta").value_or(-1);
            r.gamma = jnum(ob, "gamma").value_or(-1);
            if (r.right != "C" && r.right != "P") continue;
            e.ch.rows.push_back(r);
        }
    }
    e.ch.file_ok = !e.ch.rows.empty();
    return e;
}

// ------------------------------- main ---------------------------------------
static void usage() {
    std::fprintf(stderr,
        "uso: gate [--json] SYM...                       (sondeo: ¿se pagan opciones?)\n"
        "     gate [--json] SYM LEVEL buy|sell call|put   (ficha: contrato+limite+size)\n"
        "     gate --ev-stdin < ev.json                   (TEST: evidencia inyectada)\n"
        "opciones: --budget N  --exp YYYYMMDD  --now EPOCH  --no-write\n");
}

int main(int argc, char** argv) {
    std::string repo = repo_root(argc > 0 ? argv[0] : nullptr);
    gate::Params P = gate::params_from_env();
    bool ev_stdin = false, want_json = false, no_write = false;
    std::string exp_arg;
    long long now_arg = 0;
    std::vector<std::string> pos;

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--ev-stdin") ev_stdin = true;
        else if (a == "--json") want_json = true;
        else if (a == "--no-write") no_write = true;
        else if (a == "--budget" && i + 1 < argc) P.budget_usd = atof(argv[++i]);
        else if (a == "--exp" && i + 1 < argc) exp_arg = argv[++i];
        else if (a == "--now" && i + 1 < argc) now_arg = atoll(argv[++i]);
        else if (a == "--repo" && i + 1 < argc) repo = argv[++i];
        else if (a.rfind("--", 0) == 0) { usage(); return 2; }
        else pos.push_back(a);
    }

    // ---------- modo TEST: evidencia por stdin, sin tocar data/ ----------
    if (ev_stdin) {
        std::string j = slurp_stdin();
        Ev e = ev_from_json(j, repo);
        long long now = e.now ? e.now : (long long)time(nullptr);
        char side = (e.side.size() && (e.side[0] == 's' || e.side[0] == 'S')) ? 'S' : 'B';
        const gate::Row* r = nullptr;
        const char* mode = "ticket";
        if (e.mode == "survey") {
            mode = "survey";
            r = gate::first_otm_row(e.ch);
        } else {
            std::string right = (e.kind.size() && (e.kind[0] == 'p' || e.kind[0] == 'P')) ? "P" : "C";
            std::string exp = !e.exp.empty() ? e.exp
                            : (e.ch.exps.empty() ? std::string() : e.ch.exps.front());
            r = gate::nearest_row(e.ch, right, exp, e.level);
        }
        gate::Verdict v = gate::evaluate(e.ch, r, side, e.p, now);
        std::printf("%s\n", to_json(v, e.sym, mode, e.ch).c_str());
        return 0;
    }

    if (pos.empty()) { usage(); return 2; }

    // FICHA vs SONDEO sin ambigüedad. `gate DRAM QQQ MU SKHY` son CUATRO simbolos (asi lo
    // llamaba optgate.py), no una ficha; y `gate NVDA 210 buy call` es una ficha. Se decide
    // por la FORMA de los argumentos, jamas por contarlos.
    auto is_num = [](const std::string& s) {
        if (s.empty()) return false;
        char* e = nullptr;
        double v = std::strtod(s.c_str(), &e);
        return e && *e == '\0' && v > 0;
    };
    auto lower_of = [](std::string s) {
        for (auto& c : s) c = (char)tolower(c);
        return s;
    };
    bool ficha = pos.size() == 4 && is_num(pos[1]) &&
                 (lower_of(pos[2]) == "buy" || lower_of(pos[2]) == "sell") &&
                 (lower_of(pos[3]) == "call" || lower_of(pos[3]) == "put");
    if (!ficha) {
        for (size_t i = 1; i < pos.size(); ++i) {
            std::string l = lower_of(pos[i]);
            if (is_num(l) || l == "buy" || l == "sell" || l == "call" || l == "put") {
                std::fprintf(stderr, "[gate] ficha incompleta ('%s'): hacen falta "
                                     "SYM LEVEL buy|sell call|put\n", pos[i].c_str());
                usage();
                return 2;
            }
        }
    }

    // ---------- modo FICHA: SYM LEVEL side kind ----------
    if (ficha) {
        std::string sym = pos[0];
        for (auto& c : sym) c = (char)toupper(c);
        std::string lo = sym;
        for (auto& c : lo) c = (char)tolower(c);
        double level = atof(pos[1].c_str());
        char side = (pos[2].size() && (pos[2][0] == 's' || pos[2][0] == 'S')) ? 'S' : 'B';
        std::string right = (pos[3].size() && (pos[3][0] == 'p' || pos[3][0] == 'P')) ? "P" : "C";
        gate::Chain ch = gate::load_chain(repo + "/data/opt_chain_" + lo + ".txt", sym);
        std::string exp = !exp_arg.empty() ? exp_arg
                        : (ch.exps.empty() ? std::string() : ch.exps.front());
        const gate::Row* r = gate::nearest_row(ch, right, exp, level);
        long long now = now_arg ? now_arg : (long long)time(nullptr);
        gate::Verdict v = gate::evaluate(ch, r, side, P, now);
        std::string js = to_json(v, sym, "ticket", ch);
        if (!no_write && !write_atomic(repo, lo, js))
            std::fprintf(stderr, "[gate] no puedo escribir data/gate_%s.json\n", lo.c_str());
        if (want_json) std::printf("%s\n", js.c_str());
        else {
            std::printf("%s\n", human(v, sym).c_str());
            for (const auto& w : v.why) std::printf("    · %s\n", w.c_str());
        }
        return v.go ? 0 : 1;
    }

    // ---------- modo SONDEO: uno o varios simbolos ----------
    int rc = 0;
    for (const auto& raw : pos) {
        std::string sym = raw, lo = raw;
        for (auto& c : sym) c = (char)toupper(c);
        for (auto& c : lo) c = (char)tolower(c);
        gate::Chain ch = gate::load_chain(repo + "/data/opt_chain_" + lo + ".txt", sym);
        const gate::Row* r = gate::first_otm_row(ch);
        long long now = now_arg ? now_arg : (long long)time(nullptr);
        gate::Verdict v = gate::evaluate(ch, r, 'B', P, now);
        std::string js = to_json(v, sym, "survey", ch);
        if (!no_write && !write_atomic(repo, lo, js))
            std::fprintf(stderr, "[gate] no puedo escribir data/gate_%s.json\n", lo.c_str());
        if (want_json) std::printf("%s\n", js.c_str());
        else {
            std::printf("%s\n", human(v, sym).c_str());
            for (const auto& w : v.why) std::printf("    · %s\n", w.c_str());
        }
        if (!v.go) rc = 1;
    }
    return rc;
}
