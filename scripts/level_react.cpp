// level_react.cpp — CLI del primitivo de reaccion a niveles (feature minada #8, ola 2).
//
// DOS MODOS
//   1. `--ev-stdin`  : lee un JSON por stdin y devuelve los eventos por stdout. Es el modo que
//                      conduce `tests/test_level_react.py` (mismo patron que `compass --ev-stdin`
//                      y `tests/test_compass.py`): **el calculo vive entero aqui, en C++; Python
//                      es solo el arnes**.
//   2. modo ficheros : `--sym QQQ` lee `data/bars_<sym>_ibkr.txt`, `charts/data/levels_<sym>.json`
//                      y `data/nbbo_<sym>.txt`, y escupe JSONL de eventos.
//
// POR QUE NO ESCRIBE EN `trades.db`
// ---------------------------------
// La ficha pide una tabla `level_events`. Este binario escribe **JSONL** y la ingesta a sqlite es
// un paso aparte. Razon medida el 2026-07-25: `trades.db` pesa **1,53 GB** y tiene un
// `regen_signals.py` escribiendo en background; meter un writer sqlite dentro de un primitivo que
// van a incluir ~30 bots es meter 30 escritores compitiendo por el mismo lock en el camino de
// señal. JSONL append es lock-free, es rotable, y la ingesta se hace fuera de sesion.
//
// LA VOZ ESTA APAGADA. Este binario no incluye `fleet_notify.h` y no puede hablar.
// SEÑAL-SOLAMENTE.
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "level_react.h"

using namespace level_react;

// ======================================================================================
// JSON minimo (recursivo, tolerante). Solo lo que este binario necesita.
// ======================================================================================
namespace mj {

struct Val;
using PVal = std::shared_ptr<Val>;

struct Val {
    enum class T { Null, Bool, Num, Str, Arr, Obj } t = T::Null;
    bool b = false;
    double num = 0;
    std::string str;
    std::vector<PVal> arr;
    std::map<std::string, PVal> obj;
};

struct Parser {
    const char* p;
    const char* end;
    bool ok = true;

    void ws() { while (p < end && (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t')) ++p; }

    PVal parse() {
        ws();
        if (p >= end) { ok = false; return nullptr; }
        switch (*p) {
            case '{': return object();
            case '[': return array();
            case '"': return string();
            case 't': case 'f': return boolean();
            case 'n': return null_();
            default: return number();
        }
    }

    PVal object() {
        auto v = std::make_shared<Val>();
        v->t = Val::T::Obj;
        ++p;  // {
        ws();
        if (p < end && *p == '}') { ++p; return v; }
        while (p < end && ok) {
            ws();
            if (p >= end || *p != '"') { ok = false; break; }
            PVal k = string();
            ws();
            if (p >= end || *p != ':') { ok = false; break; }
            ++p;
            PVal val = parse();
            if (!ok) break;
            v->obj[k->str] = val;
            ws();
            if (p < end && *p == ',') { ++p; continue; }
            if (p < end && *p == '}') { ++p; break; }
            ok = false;
            break;
        }
        return v;
    }

    PVal array() {
        auto v = std::make_shared<Val>();
        v->t = Val::T::Arr;
        ++p;  // [
        ws();
        if (p < end && *p == ']') { ++p; return v; }
        while (p < end && ok) {
            PVal e = parse();
            if (!ok) break;
            v->arr.push_back(e);
            ws();
            if (p < end && *p == ',') { ++p; continue; }
            if (p < end && *p == ']') { ++p; break; }
            ok = false;
            break;
        }
        return v;
    }

    PVal string() {
        auto v = std::make_shared<Val>();
        v->t = Val::T::Str;
        ++p;  // "
        while (p < end && *p != '"') {
            if (*p == '\\' && p + 1 < end) {
                ++p;
                switch (*p) {
                    case 'n': v->str += '\n'; break;
                    case 't': v->str += '\t'; break;
                    case 'r': v->str += '\r'; break;
                    default:  v->str += *p;   break;
                }
            } else {
                v->str += *p;
            }
            ++p;
        }
        if (p < end) ++p;  // "
        return v;
    }

    PVal boolean() {
        auto v = std::make_shared<Val>();
        v->t = Val::T::Bool;
        if (end - p >= 4 && strncmp(p, "true", 4) == 0) { v->b = true;  p += 4; }
        else if (end - p >= 5 && strncmp(p, "false", 5) == 0) { v->b = false; p += 5; }
        else ok = false;
        return v;
    }

    PVal null_() {
        auto v = std::make_shared<Val>();
        v->t = Val::T::Null;
        if (end - p >= 4 && strncmp(p, "null", 4) == 0) p += 4; else ok = false;
        return v;
    }

    PVal number() {
        auto v = std::make_shared<Val>();
        v->t = Val::T::Num;
        char* e = nullptr;
        v->num = strtod(p, &e);
        if (e == p) { ok = false; return v; }
        p = e;
        return v;
    }
};

inline PVal parse(const std::string& s, bool* ok = nullptr) {
    Parser pr{s.c_str(), s.c_str() + s.size()};
    PVal v = pr.parse();
    if (ok) *ok = pr.ok;
    return v;
}

// Getters que NO inventan valores: si la clave falta o no es del tipo pedido, devuelven el
// `fallback` que el llamante eligio conscientemente, o senalan ausencia via `found`.
inline PVal get(const PVal& o, const char* k) {
    if (!o || o->t != Val::T::Obj) return nullptr;
    auto it = o->obj.find(k);
    return it == o->obj.end() ? nullptr : it->second;
}
inline bool num(const PVal& o, const char* k, double* out) {
    PVal v = get(o, k);
    if (!v || v->t != Val::T::Num) return false;
    *out = v->num;
    return true;
}
inline std::string str(const PVal& o, const char* k, const char* dflt = "") {
    PVal v = get(o, k);
    return (v && v->t == Val::T::Str) ? v->str : std::string(dflt);
}
inline bool boolean_of(const PVal& o, const char* k, bool dflt) {
    PVal v = get(o, k);
    return (v && v->t == Val::T::Bool) ? v->b : dflt;
}

}  // namespace mj

// ======================================================================================
// Utilidades
// ======================================================================================

static bool type_of_name(const std::string& s, LevelType* out) {
    if (s == "OI_CALL_WALL") { *out = LevelType::OI_CALL_WALL; return true; }
    if (s == "OI_PUT_WALL")  { *out = LevelType::OI_PUT_WALL;  return true; }
    if (s == "ABS_WALL")     { *out = LevelType::ABS_WALL;     return true; }
    if (s == "FLIP_OPEN")    { *out = LevelType::FLIP_OPEN;    return true; }
    if (s == "POC_DOM")      { *out = LevelType::POC_DOM;      return true; }
    if (s == "ROUND")        { *out = LevelType::ROUND;        return true; }
    if (s == "GAP_EDGE")     { *out = LevelType::GAP_EDGE;     return true; }
    if (s == "KDE")          { *out = LevelType::KDE;          return true; }
    return false;
}

static std::string read_all(FILE* f) {
    std::string s;
    char buf[65536];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) s.append(buf, n);
    return s;
}

static void print_events(const std::vector<Emitted>& evs, const Engine& eng,
                         const Registry& reg, const char* sym) {
    printf("{\"sym\":\"%s\",\"atr\":%.6f,\"buffer\":%.6f,\"voice\":\"OFF\",\"registry\":[",
           sym, eng.atr(), eng.buf());
    bool first = true;
    for (const auto& L : reg.levels()) {
        printf("%s{\"type\":\"%s\",\"px\":%.4f}", first ? "" : ",", type_name(L.type), L.px);
        first = false;
    }
    printf("],\"registry_max\":%zu,\"events\":[", REGISTRY_MAX);
    first = true;
    for (const auto& e : evs) {
        printf("%s{\"ts\":%.0f,\"level_type\":\"%s\",\"level_px\":%.4f,\"event\":\"%s\","
               "\"is_round\":%s,\"touch_ord\":%d,\"dist_atr\":%.4f,\"printed\":%s,"
               "\"tradeable\":%s}",
               first ? "" : ",", e.ts, type_name(e.level_type), e.level_px, event_name(e.event),
               e.is_round ? "true" : "false", e.touch_ord, e.dist_atr,
               e.printed ? "true" : "false", e.tradeable ? "true" : "false");
        first = false;
    }
    printf("]}\n");
}

// ======================================================================================
// Modo 1 — `--ev-stdin`
// ======================================================================================

static int run_stdin() {
    std::string in = read_all(stdin);
    bool ok = false;
    mj::PVal root = mj::parse(in, &ok);
    if (!ok || !root) {
        fprintf(stderr, "level_react: JSON de entrada invalido\n");
        return 2;
    }

    const std::string sym = mj::str(root, "sym", "?");

    std::vector<Bar> bars;
    mj::PVal jb = mj::get(root, "bars");
    if (jb && jb->t == mj::Val::T::Arr) {
        for (const auto& row : jb->arr) {
            if (row->t != mj::Val::T::Arr || row->arr.size() < 5) continue;
            Bar b;
            b.t = row->arr[0]->num;
            b.o = row->arr[1]->num;
            b.h = row->arr[2]->num;
            b.l = row->arr[3]->num;
            b.c = row->arr[4]->num;
            b.v = row->arr.size() > 5 ? row->arr[5]->num : 0.0;
            bars.push_back(b);
        }
    }

    // ATR: si el arnes no lo da, se calcula de las barras. Si no hay muestra, **se falla
    // ruidosamente**: un ATR inventado convierte "no se" en un buffer concreto.
    double atr = 0;
    if (!mj::num(root, "atr", &atr)) {
        atr = atr14_wilder(bars);
        if (atr <= 0) {
            fprintf(stderr, "level_react: sin ATR y sin muestra para calcularlo "
                            "(hacen falta >=15 barras); no hay veredicto\n");
            return 3;
        }
    }
    double half_spread = 0, tick = 0.01;
    mj::num(root, "half_spread", &half_spread);
    mj::num(root, "tick", &tick);

    Registry reg;
    mj::PVal jl = mj::get(root, "levels");
    if (jl && jl->t == mj::Val::T::Arr) {
        for (const auto& e : jl->arr) {
            Level L;
            LevelType t;
            if (!type_of_name(mj::str(e, "type", ""), &t)) continue;
            L.type = t;
            if (!mj::num(e, "px", &L.px)) continue;
            L.is_round = mj::boolean_of(e, "is_round", false);
            reg.add(L);
        }
    }

    Engine eng(reg, atr, half_spread, tick);
    std::vector<Emitted> all;
    for (const auto& b : bars) {
        auto ev = eng.on_bar(b);
        all.insert(all.end(), ev.begin(), ev.end());
    }
    print_events(all, eng, reg, sym.c_str());
    return 0;
}

// ======================================================================================
// Modo 2 — ficheros de la flota
// ======================================================================================

static bool load_bars(const std::string& path, std::vector<Bar>* out) {
    FILE* f = fopen(path.c_str(), "r");
    if (!f) return false;
    char line[512];
    while (fgets(line, sizeof line, f)) {
        Bar b;
        if (sscanf(line, "%lf %lf %lf %lf %lf %lf", &b.t, &b.o, &b.h, &b.l, &b.c, &b.v) >= 5)
            out->push_back(b);
    }
    fclose(f);
    return true;
}

// Medio spread de la ultima linea de `data/nbbo_<sym>.txt` (`epoch bid ask`).
// Si el fichero no existe o la linea no es parseable devuelve `false`: el llamante usa 0 y el
// `max()` del buffer se queda con el termino de ATR. Nunca se inventa un spread.
static bool last_half_spread(const std::string& path, double* out) {
    FILE* f = fopen(path.c_str(), "r");
    if (!f) return false;
    char line[512], last[512] = {0};
    while (fgets(line, sizeof line, f)) memcpy(last, line, sizeof last - 1);
    fclose(f);
    double ts, bid, ask;
    if (sscanf(last, "%lf %lf %lf", &ts, &bid, &ask) != 3) return false;
    if (bid <= 0 || ask <= 0 || ask < bid) return false;   // IBKR escribe -1 cuando no cotiza
    *out = (ask - bid) / 2.0;
    return true;
}

static std::string lower(std::string s) {
    for (auto& c : s) c = (char)tolower((unsigned char)c);
    return s;
}

static int run_files(const std::string& sym, const std::string& root_dir) {
    const std::string lo = lower(sym);
    const std::string bars_p = root_dir + "/data/bars_" + lo + "_ibkr.txt";
    const std::string lvl_p  = root_dir + "/charts/data/levels_" + lo + ".json";
    const std::string nbbo_p = root_dir + "/data/nbbo_" + lo + ".txt";

    std::vector<Bar> bars;
    if (!load_bars(bars_p, &bars) || bars.size() < 16) {
        fprintf(stderr, "level_react: sin barras suficientes en %s\n", bars_p.c_str());
        return 3;
    }
    const double atr = atr14_wilder(bars);
    if (atr <= 0) {
        fprintf(stderr, "level_react: ATR indeterminado; no hay veredicto\n");
        return 3;
    }

    FILE* lf = fopen(lvl_p.c_str(), "r");
    if (!lf) {
        fprintf(stderr, "level_react: falta %s\n", lvl_p.c_str());
        return 3;
    }
    std::string ls = read_all(lf);
    fclose(lf);
    bool ok = false;
    mj::PVal lv = mj::parse(ls, &ok);
    if (!ok) {
        fprintf(stderr, "level_react: %s no es JSON valido\n", lvl_p.c_str());
        return 3;
    }

    Registry reg;
    double x = 0;
    if (mj::num(lv, "oi_call_wall", &x)) reg.add({LevelType::OI_CALL_WALL, x, false});
    if (mj::num(lv, "oi_put_wall",  &x)) reg.add({LevelType::OI_PUT_WALL,  x, false});
    if (mj::num(lv, "abs_wall",     &x)) reg.add({LevelType::ABS_WALL,     x, false});
    // FLIP_OPEN es el flip CONGELADO a la apertura. Si no esta congelado todavia, se usa el
    // flip vivo y se DECLARA en la meta — nunca en silencio (la congelacion es media feature).
    const char* flip_src = "frozen";
    if (mj::num(lv, "flip_open", &x)) {
        reg.add({LevelType::FLIP_OPEN, x, false});
    } else if (mj::num(lv, "flip", &x)) {
        reg.add({LevelType::FLIP_OPEN, x, false});
        flip_src = "live_fallback";
    } else {
        flip_src = "ausente";
    }
    // `poc_dom` en `levels_<sym>.json` es un STRING de etiqueta ("97%P"), no un precio: no se
    // fuerza a numero. Si algun dia es numerico, entra solo.
    if (mj::num(lv, "poc_dom", &x)) reg.add({LevelType::POC_DOM, x, false});

    // ROUND: el numero redondo mas cercano al spot. Osler atribuye ~3,4pp del efecto de nivel
    // justo a los redondos, asi que va al registro como su propio tipo y se mide aparte.
    double spot = 0;
    if (mj::num(lv, "spot", &spot) && spot > 0) {
        const double step = (spot >= 100.0) ? 5.0 : 1.0;
        const double r = step * std::round(spot / step);
        reg.add({LevelType::ROUND, r, true});
    }

    double hs = 0;
    const bool hs_ok = last_half_spread(nbbo_p, &hs);

    Engine eng(reg, atr, hs, 0.01);
    std::vector<Emitted> all;
    for (const auto& b : bars) {
        auto ev = eng.on_bar(b);
        all.insert(all.end(), ev.begin(), ev.end());
    }
    fprintf(stderr, "level_react %s: %zu barras, ATR14=%.4f, buffer=%.4f, half_spread=%s, "
                    "flip_src=%s, niveles=%zu/%zu, eventos=%zu (VOZ APAGADA)\n",
            sym.c_str(), bars.size(), atr, eng.buf(), hs_ok ? "nbbo" : "ausente",
            flip_src, reg.size(), REGISTRY_MAX, all.size());
    print_events(all, eng, reg, sym.c_str());
    return 0;
}

// ======================================================================================

int main(int argc, char** argv) {
    std::string sym, root = ".";
    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--ev-stdin") == 0) return run_stdin();
        if (strcmp(argv[i], "--sym") == 0 && i + 1 < argc) sym = argv[++i];
        else if (strcmp(argv[i], "--root") == 0 && i + 1 < argc) root = argv[++i];
        else if (strcmp(argv[i], "--help") == 0) {
            printf("uso: level_react --ev-stdin            (arnes de test, JSON por stdin)\n"
                   "     level_react --sym QQQ [--root .]  (ficheros de la flota)\n"
                   "SEÑAL-SOLAMENTE. La voz embarca APAGADA.\n");
            return 0;
        }
    }
    if (sym.empty()) {
        fprintf(stderr, "level_react: falta --sym o --ev-stdin (ver --help)\n");
        return 1;
    }
    return run_files(sym, root);
}
