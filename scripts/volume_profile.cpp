// volume_profile.cpp — EL POC QUE NOS FALTABA: el de VOLUMEN.
//
// EL HUECO (confirmado 2026-07-25). Todo nuestro mapa de niveles es de GAMMA:
// `gex_snapshot.json` publica `poc`, `abs_wall`, `flip`, `magnets` — todos derivados de la
// cadena de opciones. No teniamos NADA derivado del PRECIO NEGOCIADO. Son dos cosas de
// naturaleza distinta y por eso el cruce vale:
//
//   POC de GAMMA   = donde el DEALER ESTA OBLIGADO a cubrirse (mecanica de inventario).
//   POC de VOLUMEN = donde el MERCADO ACEPTO valor (subasta: ahi se cruzo mas papel).
//
// Un nivel donde coinciden las dos es un nivel al que llegan dos poblaciones distintas por
// caminos distintos. Un nivel que solo tiene una de las dos es mas debil. Eso es lo unico
// que este binario afirma, y lo afirma como DESCRIPCION, no como probabilidad.
//
// LO QUE ESTE FICHERO NO HACE (a proposito)
// -----------------------------------------
//   - NO publica probabilidad, win-rate ni edge. Ninguna. La ley de la casa: no se afirma
//     una probabilidad que no se ha medido, y la confluencia POC-vol / POC-gamma NO esta
//     medida todavia (haria falta el arnes de barrera sobre >=N sesiones con ambos POC
//     archivados; hoy `levels_5m.jsonl` tiene 1 sesion). Cuando se mida, se mide aparte.
//   - NO habla: cero voz, cero banner, cero sirena. Escribe un JSON y calla.
//   - NO ordena nada (ley #0, señal-solamente).
//   - Las etiquetas CONFLUENCE/NEAR/APART son una CONVENCION DECLARADA de distancia, no un
//     veredicto estadistico. Van con `thresholds_are_convention_not_measured: true` DENTRO
//     del propio fichero para que ningun consumidor futuro pueda confundirse.
//
// APROXIMACION HONESTA. Una barra de 1 minuto no dice DONDE dentro de [low,high] se negocio
// su volumen. Se reparte UNIFORMEMENTE entre los buckets que cubre. Es la convencion estandar
// de VPVR y se declara en `_meta.method`: no es la distribucion intra-barra real. Con 1m sobre
// 20 sesiones (~7.800 barras) el sesgo de esa aproximacion se promedia; con pocas barras NO,
// y por eso hay un minimo duro (`--min-bars`) por debajo del cual el simbolo sale con motivo
// y sin numeros — jamas con un POC inventado.
//
// FUENTE: trades.db tabla `poly_bars` (1m, 30 simbolos, ts en MILISEGUNDOS), abierta
// SQLITE_OPEN_READONLY: este binario no escribe una sola pagina de esa base (hay jobs de
// etiquetado corriendo sobre ella).
//
//   compilar: ./scripts/build_volume_profile.sh
//   uso:
//     ./volume_profile                          # flota entera -> data/vpvr.json
//     ./volume_profile --sym QQQ --print        # tabla legible por consola
//     ./volume_profile --sessions 60 --bins 400
//     ./volume_profile --stdin --out -          # arnes de test (barras por stdin)

#include <algorithm>
#include <cctype>
#include <charconv>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

#include <sqlite3.h>

namespace {

[[noreturn]] void die(const std::string& msg) {
    std::fprintf(stderr, "volume_profile: %s\n", msg.c_str());
    std::exit(2);
}

// ---------------------------------------------------------------- barras
struct Bar {
    long long ts_ms;
    double h, l, v;
};

// Sesion = dia con el corte desplazado -5 h respecto a UTC. El corte cae entonces entre las
// 00:00 (EST) y las 01:00 (EDT) hora de Nueva York, que en AMBOS regimenes de horario esta
// fuera de cualquier sesion — ni RTH (09:30-16:00) ni extendida (04:00-20:00). Asi no hace
// falta la base de datos de zonas horarias para no partir una sesion por la mitad.
constexpr long long kSessionShiftSec = 5 * 3600;

long long session_day(long long ts_ms) {
    long long s = ts_ms / 1000 - kSessionShiftSec;
    return s >= 0 ? s / 86400 : (s - 86399) / 86400;
}

std::string session_iso(long long day) {
    std::time_t t = static_cast<std::time_t>(day * 86400 + kSessionShiftSec);
    std::tm g{};
    gmtime_r(&t, &g);
    char buf[16];
    std::snprintf(buf, sizeof buf, "%04d-%02d-%02d", g.tm_year + 1900, g.tm_mon + 1, g.tm_mday);
    return buf;
}

// ---------------------------------------------------------------- perfil
struct Profile {
    // identidad de la muestra
    long long n_bars = 0;
    int n_sessions = 0;
    std::string first_session, last_session;
    // rejilla
    double lo = 0, hi = 0, bucket = 0;
    int bins = 0;
    // resultado
    double poc = 0;
    double vah = 0, val = 0;
    double total_volume = 0;
    double va_volume = 0;
    std::vector<double> hvn, lvn;
    // por que no hay resultado
    std::string skip_reason;
    bool ok() const { return skip_reason.empty(); }
};

Profile build_profile(std::vector<Bar>& bars, int bins, double va_frac, long long min_bars) {
    Profile p;
    p.bins = bins;
    p.n_bars = static_cast<long long>(bars.size());
    if (bars.empty()) {
        p.skip_reason = "sin barras en la ventana";
        return p;
    }
    std::set<long long> days;
    for (const auto& b : bars) days.insert(session_day(b.ts_ms));
    p.n_sessions = static_cast<int>(days.size());
    p.first_session = session_iso(*days.begin());
    p.last_session = session_iso(*days.rbegin());

    if (p.n_bars < min_bars) {
        p.skip_reason = "muestra insuficiente: " + std::to_string(p.n_bars) + " barras < min " +
                        std::to_string(min_bars);
        return p;
    }

    p.lo = bars.front().l;
    p.hi = bars.front().h;
    for (const auto& b : bars) {
        p.lo = std::min(p.lo, b.l);
        p.hi = std::max(p.hi, b.h);
    }
    if (!(p.hi > p.lo)) {
        p.skip_reason = "rango degenerado (hi <= lo): precio plano o dato corrupto";
        return p;
    }
    p.bucket = (p.hi - p.lo) / bins;

    // Reparto uniforme del volumen de cada barra entre los buckets que cubre [l,h].
    std::vector<double> vol(static_cast<size_t>(bins), 0.0);
    auto idx = [&](double px) {
        int i = static_cast<int>((px - p.lo) / p.bucket);
        return std::clamp(i, 0, bins - 1);
    };
    for (const auto& b : bars) {
        if (!(b.v > 0)) continue;   // volumen 0 o NaN no aporta; no se inventa nada
        int a = idx(b.l), z = idx(b.h);
        if (z < a) std::swap(a, z);
        double share = b.v / static_cast<double>(z - a + 1);
        for (int i = a; i <= z; ++i) vol[static_cast<size_t>(i)] += share;
        p.total_volume += b.v;
    }
    if (!(p.total_volume > 0)) {
        p.skip_reason = "volumen total 0 en la ventana";
        return p;
    }

    auto center = [&](int i) { return p.lo + (static_cast<double>(i) + 0.5) * p.bucket; };

    // POC = CENTRO de la meseta del maximo, no su primer bucket. `max_element` devuelve el
    // primer empate, asi que un maximo plano de k buckets (habitual: una barra de 1m cubre
    // varios buckets y reparte lo mismo en cada uno) empujaba el POC a su borde IZQUIERDO,
    // un sesgo sistematico a la baja. Se toma la mediana de los indices empatados.
    const double vmax = *std::max_element(vol.begin(), vol.end());
    std::vector<int> tied;
    for (int i = 0; i < bins; ++i)
        if (vol[static_cast<size_t>(i)] >= vmax * (1.0 - 1e-12)) tied.push_back(i);
    int poc_i = tied[tied.size() / 2];
    p.poc = center(poc_i);

    // Area de valor: desde el POC se anexa el vecino (arriba o abajo) con mas volumen hasta
    // cubrir `va_frac` del total. Variante 1-a-1 del metodo de Steidlmayer.
    double acc = vol[static_cast<size_t>(poc_i)];
    int up = poc_i, dn = poc_i;
    const double target = p.total_volume * va_frac;
    while (acc < target && (up < bins - 1 || dn > 0)) {
        double vu = (up < bins - 1) ? vol[static_cast<size_t>(up + 1)] : -1.0;
        double vd = (dn > 0) ? vol[static_cast<size_t>(dn - 1)] : -1.0;
        if (vu < 0 && vd < 0) break;
        if (vu >= vd) { ++up; acc += vu; }
        else          { --dn; acc += vd; }
    }
    p.vah = center(up);
    p.val = center(dn);
    p.va_volume = acc;

    // HVN = maximos locales con >=150% del volumen medio por bucket.
    // LVN = minimos locales con <=40%. Umbrales de FORMA, descriptivos.
    // `>=` a la izquierda y `>` a la derecha (y su espejo): con la comparacion ESTRICTA por
    // los dos lados una MESETA plana no produce ningun pico y el propio POC se quedaba fuera
    // de la lista (cazado con datos sinteticos: 500 barras clavadas en 105 daban hvn=[]).
    // Asi cada meseta aporta exactamente un punto: su borde derecho.
    // Los buckets del BORDE tambien cuentan: se les da un vecino exterior de -inf (para HVN)
    // y +inf (para LVN). Con el bucle empezando en 1 y acabando en bins-2, un POC que cae en
    // el ultimo bucket del rango no aparecia en hvn (cazado por el test: el maximo de la
    // muestra ES el borde superior por construccion).
    const double mean = p.total_volume / bins;
    const double kInf = std::numeric_limits<double>::infinity();
    for (int i = 0; i < bins; ++i) {
        double v = vol[static_cast<size_t>(i)];
        double a_hi = (i > 0) ? vol[static_cast<size_t>(i - 1)] : -kInf;
        double b_hi = (i < bins - 1) ? vol[static_cast<size_t>(i + 1)] : -kInf;
        double a_lo = (i > 0) ? vol[static_cast<size_t>(i - 1)] : kInf;
        double b_lo = (i < bins - 1) ? vol[static_cast<size_t>(i + 1)] : kInf;
        if (v >= a_hi && v > b_hi && v >= 1.5 * mean) p.hvn.push_back(center(i));
        if (v <= a_lo && v < b_lo && v <= 0.4 * mean && center(i) > p.val && center(i) < p.vah)
            p.lvn.push_back(center(i));
    }
    // los 5 mas cargados / mas huecos, no la lista entera
    auto trim = [](std::vector<double>& v) { if (v.size() > 5) v.resize(5); };
    std::sort(p.hvn.begin(), p.hvn.end(),
              [&](double a, double b) { return std::abs(a - p.poc) < std::abs(b - p.poc); });
    trim(p.hvn);
    std::sort(p.hvn.begin(), p.hvn.end());
    trim(p.lvn);
    return p;
}

// ---------------------------------------------------------------- JSON minimo
// Solo hace falta leer `data/gex_snapshot.json`: {"QQQ": {..., "poc": 695.0, "spot": 685.06}}.
// Escanea campos de un objeto respetando anidamiento y cadenas con escapes.
std::map<std::string, std::string> json_fields(std::string_view s) {
    std::map<std::string, std::string> out;
    size_t i = s.find('{');
    if (i == std::string_view::npos) return out;
    ++i;
    auto skip_ws = [&] { while (i < s.size() && std::isspace(static_cast<unsigned char>(s[i]))) ++i; };
    auto read_string = [&]() -> std::string {
        std::string r;
        ++i;                                    // comilla de apertura
        while (i < s.size() && s[i] != '"') {
            if (s[i] == '\\' && i + 1 < s.size()) { r += s[i + 1]; i += 2; continue; }
            r += s[i++];
        }
        ++i;
        return r;
    };
    while (true) {
        skip_ws();
        if (i >= s.size() || s[i] == '}') break;
        if (s[i] != '"') break;
        std::string key = read_string();
        skip_ws();
        if (i >= s.size() || s[i] != ':') break;
        ++i;
        skip_ws();
        size_t start = i;
        int depth = 0;
        bool in_str = false;
        for (; i < s.size(); ++i) {
            char c = s[i];
            if (in_str) {
                if (c == '\\') { ++i; continue; }
                if (c == '"') in_str = false;
                continue;
            }
            if (c == '"') { in_str = true; continue; }
            if (c == '{' || c == '[') { ++depth; continue; }
            if (c == '}' || c == ']') {
                if (depth == 0) break;
                --depth;
                continue;
            }
            if (c == ',' && depth == 0) break;
        }
        out[key] = std::string(s.substr(start, i - start));
        if (i < s.size() && s[i] == ',') ++i;
    }
    return out;
}

std::optional<double> as_number(const std::string& raw) {
    std::string t = raw;
    while (!t.empty() && std::isspace(static_cast<unsigned char>(t.back()))) t.pop_back();
    if (t.empty() || t == "null") return std::nullopt;
    try {
        size_t used = 0;
        double d = std::stod(t, &used);
        if (used == 0 || !std::isfinite(d)) return std::nullopt;
        return d;
    } catch (...) {
        return std::nullopt;   // NUNCA 0.0 por defecto: "no se" no es "es cero"
    }
}

struct GammaRef {
    std::optional<double> poc, spot;
};

std::map<std::string, GammaRef> load_gamma(const std::string& path, std::string& note) {
    std::map<std::string, GammaRef> out;
    std::ifstream f(path);
    if (!f) {
        note = "ausente: " + path;
        return out;
    }
    std::stringstream ss;
    ss << f.rdbuf();
    const std::string text = ss.str();
    for (auto& [sym, body] : json_fields(text)) {
        if (!sym.empty() && sym[0] == '_') continue;   // _meta
        auto inner = json_fields(body);
        GammaRef g;
        if (auto it = inner.find("poc"); it != inner.end()) g.poc = as_number(it->second);
        if (auto it = inner.find("spot"); it != inner.end()) g.spot = as_number(it->second);
        out[sym] = g;
    }
    note = out.empty() ? ("sin simbolos utiles en " + path) : path;
    return out;
}

// ---------------------------------------------------------------- salida
std::string num(double v, int dec = 4) {
    char buf[64];
    std::snprintf(buf, sizeof buf, "%.*f", dec, v);
    std::string s = buf;
    if (s.find('.') != std::string::npos) {
        while (s.back() == '0') s.pop_back();
        if (s.back() == '.') s.pop_back();
    }
    return s;
}

std::string arr(const std::vector<double>& v) {
    std::string s = "[";
    for (size_t i = 0; i < v.size(); ++i) {
        if (i) s += ", ";
        s += num(v[i]);
    }
    return s + "]";
}

// Umbrales de DISTANCIA, no de probabilidad. Declarados aqui y marcados en el JSON.
constexpr double kConfluencePct = 0.15;
constexpr double kNearPct = 0.50;

void write_atomic(const std::string& path, const std::string& body) {
    if (path == "-") {
        std::cout << body;
        return;
    }
    const std::string tmp = path + ".tmp";
    {
        std::ofstream f(tmp, std::ios::trunc);
        if (!f) die("no puedo escribir " + tmp);
        f << body;
        if (!f) die("fallo al escribir " + tmp);
    }
    if (std::rename(tmp.c_str(), path.c_str()) != 0) die("fallo el rename a " + path);
}

}  // namespace

int main(int argc, char** argv) {
    std::string db_path = "data/trades.db";   // la BD vive en data/; "trades.db" abria el vacio de la raiz
    std::string gex_path = "data/gex_snapshot.json";
    std::string out_path = "data/vpvr.json";
    std::string only_sym;
    int sessions = 20, bins = 240;
    double va_frac = 0.70;
    long long min_bars = 500;
    bool from_stdin = false, do_print = false;

    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) die("falta el valor de " + a);
            return argv[++i];
        };
        if (a == "--db") db_path = next();
        else if (a == "--gex") gex_path = next();
        else if (a == "--out") out_path = next();
        else if (a == "--sym") only_sym = next();
        else if (a == "--sessions") sessions = std::atoi(next().c_str());
        else if (a == "--bins") bins = std::atoi(next().c_str());
        else if (a == "--va") va_frac = std::atof(next().c_str());
        else if (a == "--min-bars") min_bars = std::atoll(next().c_str());
        else if (a == "--stdin") from_stdin = true;
        else if (a == "--print") do_print = true;
        else if (a == "--help" || a == "-h") {
            std::puts("volume_profile [--db trades.db] [--gex data/gex_snapshot.json]");
            std::puts("               [--out data/vpvr.json|-] [--sym SYM] [--sessions 20]");
            std::puts("               [--bins 240] [--va 0.70] [--min-bars 500] [--stdin] [--print]");
            std::puts("");
            std::puts("POC de VOLUMEN desde poly_bars + confluencia con el POC de GAMMA.");
            std::puts("DESCRIPTIVO: no publica ninguna probabilidad. No habla. No ordena.");
            return 0;
        } else die("opcion desconocida: " + a);
    }
    if (bins < 8) die("--bins demasiado pequeño (min 8)");
    if (!(va_frac > 0 && va_frac < 1)) die("--va debe estar en (0,1)");

    std::map<std::string, std::vector<Bar>> bars;

    if (from_stdin) {
        // arnes de test: `sym ts_ms open high low close volume` por linea
        std::string sym;
        long long ts;
        double o, h, l, c, v;
        while (std::cin >> sym >> ts >> o >> h >> l >> c >> v) bars[sym].push_back({ts, h, l, v});
    } else {
        sqlite3* db = nullptr;
        const std::string uri = "file:" + db_path + "?mode=ro";
        if (sqlite3_open_v2(uri.c_str(), &db, SQLITE_OPEN_READONLY | SQLITE_OPEN_URI, nullptr) != SQLITE_OK)
            die("no puedo abrir (solo lectura) " + db_path + ": " + (db ? sqlite3_errmsg(db) : "?"));
        sqlite3_busy_timeout(db, 5000);

        // El corte de la ventana se calcula por SIMBOLO (no todos tienen el mismo ultimo dia).
        std::vector<std::string> syms;
        {
            const char* q = only_sym.empty()
                                ? "SELECT DISTINCT sym FROM poly_bars ORDER BY sym"
                                : "SELECT DISTINCT sym FROM poly_bars WHERE sym = ?1";
            sqlite3_stmt* st = nullptr;
            if (sqlite3_prepare_v2(db, q, -1, &st, nullptr) != SQLITE_OK)
                die(std::string("prepare syms: ") + sqlite3_errmsg(db));
            if (!only_sym.empty()) sqlite3_bind_text(st, 1, only_sym.c_str(), -1, SQLITE_STATIC);
            while (sqlite3_step(st) == SQLITE_ROW)
                syms.emplace_back(reinterpret_cast<const char*>(sqlite3_column_text(st, 0)));
            sqlite3_finalize(st);
        }
        if (syms.empty()) die("poly_bars no tiene el simbolo pedido" + (only_sym.empty() ? "" : ": " + only_sym));

        for (const auto& s : syms) {
            long long last_ms = 0;
            {
                sqlite3_stmt* st = nullptr;
                sqlite3_prepare_v2(db, "SELECT MAX(ts) FROM poly_bars WHERE sym = ?1", -1, &st, nullptr);
                sqlite3_bind_text(st, 1, s.c_str(), -1, SQLITE_STATIC);
                if (sqlite3_step(st) == SQLITE_ROW) last_ms = sqlite3_column_int64(st, 0);
                sqlite3_finalize(st);
            }
            if (last_ms <= 0) continue;
            // (sessions-1) dias de calendario hacia atras y luego se cuentan las sesiones
            // REALES presentes: fines de semana y festivos no roban ventana.
            long long cut_day = session_day(last_ms) - static_cast<long long>(sessions) * 2 - 5;
            long long cut_ms = (cut_day * 86400 + kSessionShiftSec) * 1000;

            std::vector<Bar> tmp;
            sqlite3_stmt* st = nullptr;
            if (sqlite3_prepare_v2(db,
                                   "SELECT ts, h, l, v FROM poly_bars WHERE sym = ?1 AND ts >= ?2 "
                                   "ORDER BY ts",
                                   -1, &st, nullptr) != SQLITE_OK)
                die(std::string("prepare bars: ") + sqlite3_errmsg(db));
            sqlite3_bind_text(st, 1, s.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_int64(st, 2, cut_ms);
            while (sqlite3_step(st) == SQLITE_ROW) {
                Bar b{sqlite3_column_int64(st, 0), sqlite3_column_double(st, 1),
                      sqlite3_column_double(st, 2), sqlite3_column_double(st, 3)};
                if (!std::isfinite(b.h) || !std::isfinite(b.l) || b.h < b.l) continue;
                tmp.push_back(b);
            }
            sqlite3_finalize(st);
            if (tmp.empty()) continue;

            // recortar a las ULTIMAS `sessions` sesiones realmente presentes
            std::set<long long> days;
            for (const auto& b : tmp) days.insert(session_day(b.ts_ms));
            long long keep_from = *days.begin();
            if (static_cast<int>(days.size()) > sessions) {
                auto it = days.end();
                std::advance(it, -sessions);
                keep_from = *it;
            }
            std::vector<Bar> kept;
            kept.reserve(tmp.size());
            for (const auto& b : tmp)
                if (session_day(b.ts_ms) >= keep_from) kept.push_back(b);
            bars[s] = std::move(kept);
        }
        sqlite3_close(db);
    }

    std::string gex_note;
    auto gamma = load_gamma(gex_path, gex_note);

    // -------------------------------------------------------------- render
    // Marca de tiempo: sin ella nadie puede juzgar si este fichero esta rancio, y en esta casa
    // TODO dato se juzga por frescura (`age_s`/`stale` en los archivadores). `generated_utc` es
    // cuando se calculo; `last_session` por simbolo dice hasta donde llegan los datos — no son
    // lo mismo y por eso van los dos.
    char stamp[32] = "?";
    {
        std::time_t now = std::time(nullptr);
        std::tm g{};
        gmtime_r(&now, &g);
        std::strftime(stamp, sizeof stamp, "%Y-%m-%dT%H:%M:%SZ", &g);
    }

    std::string j = "{\n";
    j += "  \"_meta\": {\n";
    j += "    \"generated_utc\": \"" + std::string(stamp) + "\",\n";
    j += "    \"generated_epoch\": " + std::to_string(static_cast<long long>(std::time(nullptr))) + ",\n";
    j += "    \"what\": \"POC de VOLUMEN (donde el mercado acepto valor) desde barras 1m, y su "
         "distancia al POC de GAMMA (donde el dealer debe cubrirse). Son dos cosas distintas: "
         "ahi esta el valor del cruce.\",\n";
    j += "    \"source_bars\": \"poly_bars (" + db_path + ", SQLITE_OPEN_READONLY)\",\n";
    j += "    \"source_gamma\": \"" + gex_note + "\",\n";
    j += "    \"sessions_requested\": " + std::to_string(sessions) + ",\n";
    j += "    \"bins\": " + std::to_string(bins) + ",\n";
    j += "    \"value_area\": " + num(va_frac) + ",\n";
    j += "    \"min_bars\": " + std::to_string(min_bars) + ",\n";
    j += "    \"method\": \"el volumen de cada barra 1m se reparte UNIFORMEMENTE entre los "
         "buckets que cubre [low,high]; es la convencion estandar de VPVR y NO es la "
         "distribucion intra-barra real\",\n";
    j += "    \"session_cut\": \"dia con corte UTC-5h (cae entre 00:00 EST y 01:00 EDT: fuera "
         "de RTH y de la sesion extendida en ambos regimenes de horario)\",\n";
    j += "    \"thresholds_are_convention_not_measured\": true,\n";
    j += "    \"confluence_pct\": " + num(kConfluencePct) + ",\n";
    j += "    \"near_pct\": " + num(kNearPct) + ",\n";
    j += "    \"no_probability\": \"fichero DESCRIPTIVO: no publica probabilidad, win-rate ni "
         "edge. La confluencia POC-volumen / POC-gamma NO esta medida todavia.\",\n";
    j += "    \"signal_only\": true\n";
    j += "  }";

    int n_ok = 0, n_conf = 0;
    for (auto& [sym, bs] : bars) {
        Profile p = build_profile(bs, bins, va_frac, min_bars);
        j += ",\n  \"" + sym + "\": {\n";
        j += "    \"n_bars\": " + std::to_string(p.n_bars) + ",\n";
        j += "    \"n_sessions\": " + std::to_string(p.n_sessions) + ",\n";
        if (!p.first_session.empty()) {
            j += "    \"first_session\": \"" + p.first_session + "\",\n";
            j += "    \"last_session\": \"" + p.last_session + "\",\n";
        }
        if (!p.ok()) {
            // fail-loud: sin numeros y con el motivo DENTRO del dato. Jamas un POC de 0.
            j += "    \"poc_volume\": null,\n";
            j += "    \"vah\": null,\n    \"val\": null,\n";
            j += "    \"confluence\": null,\n";
            j += "    \"skip_reason\": \"" + p.skip_reason + "\"\n  }";
            continue;
        }
        ++n_ok;
        j += "    \"lo\": " + num(p.lo) + ",\n";
        j += "    \"hi\": " + num(p.hi) + ",\n";
        j += "    \"bucket\": " + num(p.bucket, 6) + ",\n";
        j += "    \"poc_volume\": " + num(p.poc) + ",\n";
        j += "    \"vah\": " + num(p.vah) + ",\n";
        j += "    \"val\": " + num(p.val) + ",\n";
        j += "    \"hvn\": " + arr(p.hvn) + ",\n";
        j += "    \"lvn\": " + arr(p.lvn) + ",\n";
        j += "    \"total_volume\": " + num(p.total_volume, 2) + ",\n";
        j += "    \"va_volume_frac\": " + num(p.va_volume / p.total_volume, 4) + ",\n";

        auto it = gamma.find(sym);
        std::optional<double> pg = (it != gamma.end()) ? it->second.poc : std::nullopt;
        std::optional<double> spot = (it != gamma.end()) ? it->second.spot : std::nullopt;
        if (pg && spot && *spot > 0) {
            double dist = std::abs(p.poc - *pg) / *spot * 100.0;
            const char* label = dist <= kConfluencePct ? "CONFLUENCE"
                                : dist <= kNearPct     ? "NEAR"
                                                       : "APART";
            if (dist <= kConfluencePct) ++n_conf;
            j += "    \"poc_gamma\": " + num(*pg) + ",\n";
            j += "    \"spot\": " + num(*spot) + ",\n";
            j += "    \"dist_pct\": " + num(dist, 4) + ",\n";
            j += "    \"confluence\": \"" + std::string(label) + "\"\n";
        } else {
            // el POC de gamma no existe hoy para este simbolo -> se DICE, no se rellena
            j += "    \"poc_gamma\": null,\n";
            j += "    \"dist_pct\": null,\n";
            j += "    \"confluence\": null,\n";
            j += "    \"confluence_why\": \"sin POC de gamma para este simbolo en el mapa\"\n";
        }
        j += "  }";
    }
    j += "\n}\n";

    write_atomic(out_path, j);

    if (do_print) {
        std::printf("%-6s %8s %8s %8s %10s %8s %s\n", "SYM", "VAL", "POC-vol", "VAH", "POC-gam",
                    "dist%", "confluencia");
        for (auto& [sym, bs] : bars) {
            Profile p = build_profile(bs, bins, va_frac, min_bars);
            if (!p.ok()) {
                std::printf("%-6s  --  %s\n", sym.c_str(), p.skip_reason.c_str());
                continue;
            }
            auto it = gamma.find(sym);
            std::optional<double> pg = (it != gamma.end()) ? it->second.poc : std::nullopt;
            std::optional<double> spot = (it != gamma.end()) ? it->second.spot : std::nullopt;
            std::printf("%-6s %8s %8s %8s ", sym.c_str(), num(p.val, 2).c_str(),
                        num(p.poc, 2).c_str(), num(p.vah, 2).c_str());
            if (pg && spot && *spot > 0) {
                double d = std::abs(p.poc - *pg) / *spot * 100.0;
                std::printf("%10s %7.2f%% %s\n", num(*pg, 2).c_str(), d,
                            d <= kConfluencePct ? "CONFLUENCE" : d <= kNearPct ? "NEAR" : "APART");
            } else {
                std::printf("%10s %8s %s\n", "n/d", "n/d", "sin POC de gamma");
            }
        }
        std::printf("\n%d simbolos con perfil, %d en CONFLUENCE (<=%.2f%%). "
                    "DESCRIPTIVO: sin probabilidad.\n", n_ok, n_conf, kConfluencePct);
    }
    return 0;
}
