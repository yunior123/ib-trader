// price_alarm.cpp — watcher de alarmas de precio (M5, spec V6 §6, 2026-07-16).
//
// LEY (Yunior 2026-07-16, señal-solamente): este proceso SOLO lee archivos y
// emite audio/banner/mirror. Cero red, cero TWS/IBKR/Alpaca, cero ordenes.
//
// Loop 4 Hz (2026-07-18 "high velocity": alarma dispara <=250ms tras el dato,
// antes hasta 1s; stat+fscanf de 2 archivos chicos = coste trivial):
//   1) relee ~/Desktop/price-alerts.txt si cambio (stat mtime). Formato:
//        ticker precio [up|down|cross]     (case-insensitive; # = comentario)
//      sin direccion => modo cruce: se arma con el primer precio leido
//      (precio arriba del nivel => espera caida; abajo => espera subida).
//   2) precio actual por ticker: mid de data/nbbo_<sym>.txt (edad<=10s)
//      -> fallback close ultimo bar data/bars_<sym>_ibkr.txt (edad<=180s)
//      -> fallback data/bars_<sym>.txt (edad<=180s). Sin dato fresco => skip
//      (log 1 vez / 10 min por ticker).
//   3) disparo: SIRENA fire_alarm.wav x3 + say -v Paulina + banner/mirror via
//      fleet_notify_urgent ("SYM ALARMA PRECIO") + marca la linea como
//      [DISPARADA YYYY-MM-DD HH:MM] <original> (rewrite atomico tmp+rename).
//      Una alerta dispara UNA vez; re-armar = borrar el prefijo [DISPARADA].
//
// Pre-seed: crea el archivo con cabecera de instrucciones si no existe y
// garantiza (idempotente) la alerta activa "intc 100 down" (urgente, Yunior).
//
// Compilar desde el root del repo (canonico, spec §1):
//   clang++ -std=c++17 -O2 -o price_alarm scripts/price_alarm.cpp
#include "../fleet_notify.h"   // banner + espejo Desktop (root del repo)

#include <sys/stat.h>
#include <unistd.h>

#include <cctype>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <map>
#include <string>
#include <vector>

// ---- shell safety (mismo whitelist que los bots: dram_signal_bot.cpp) ----
// Solo alnum + " .,%+-:/()_"; el resto -> espacio. Imposible inyectar shell.
static void sh_sanitize(const char* in, char* out, size_t n) {
    size_t j = 0;
    for (size_t i = 0; in && in[i] && j + 1 < n; ++i) {
        unsigned char c = (unsigned char)in[i];
        out[j++] = (std::isalnum(c) || std::strchr(" .,%+-:/()_", c)) ? (char)c : ' ';
    }
    out[j] = 0;
}

static void logline(const char* fmt, ...) {
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    std::printf("[%02d:%02d:%02d] ", lt.tm_hour, lt.tm_min, lt.tm_sec);
    va_list ap;
    va_start(ap, fmt);
    std::vprintf(fmt, ap);
    va_end(ap);
    std::printf("\n");
    std::fflush(stdout);
}

// ---- reglas ----
enum Mode { CROSS = 0, UP = +1, DOWN = -1 };
struct Rule {
    std::string raw;   // linea original (sin \n), tal cual esta en el archivo
    std::string sym;   // minuscula, solo alnum (validado)
    double px = 0;
    int mode = CROSS;
    int armed = 0;     // solo CROSS: -1 espera caida a px, +1 espera subida; 0 sin armar
    size_t line_idx = 0;
};

static std::string alerts_path() {
    const char* home = getenv("HOME");
    std::string p = home ? home : "";
    return p + "/Desktop/price-alerts.txt";
}

static const char* HEADER =
    "# price-alerts.txt — alarmas de precio (price_alarm, ib-trader)\n"
    "# Formato: ticker precio [up|down|cross]   (una alerta por linea)\n"
    "#   nvda 215          -> cruce: dispara al TOCAR 215 desde cualquier lado\n"
    "#   intc 100 down     -> dispara cuando el precio <= 100\n"
    "#   tsla 550 up       -> dispara cuando el precio >= 550\n"
    "# Al disparar, la linea queda: [DISPARADA 2026-07-16 10:33] intc 100 down\n"
    "# Re-armar = borrar el prefijo [DISPARADA ...]. Lineas con # = comentario.\n";

// parsea "sym precio [up|down|cross]"; devuelve false si la linea no es regla
// (comentario, vacia, disparada) o es invalida (*invalid=true en ese caso).
static bool parse_rule(const std::string& line, Rule& r, bool* invalid) {
    *invalid = false;
    std::string s = line;
    size_t h = s.find('#');
    if (h != std::string::npos) s.erase(h);          // comentario inline
    // trim
    size_t b = s.find_first_not_of(" \t\r");
    if (b == std::string::npos) return false;        // vacia
    size_t e = s.find_last_not_of(" \t\r");
    s = s.substr(b, e - b + 1);
    if (s.rfind("[DISPARADA", 0) == 0 || s.rfind("FIRED", 0) == 0) return false;
    char sym[32] = {0}, dir[32] = {0};
    double px = 0;
    int n = std::sscanf(s.c_str(), "%31s %lf %31s", sym, &px, dir);
    if (n < 2 || px <= 0) { *invalid = true; return false; }
    for (char* p = sym; *p; ++p) {
        if (!std::isalnum((unsigned char)*p)) { *invalid = true; return false; }
        *p = (char)std::tolower((unsigned char)*p);
    }
    for (char* p = dir; *p; ++p) *p = (char)std::tolower((unsigned char)*p);
    r.sym = sym;
    r.px = px;
    if (n < 3 || !std::strcmp(dir, "cross")) r.mode = CROSS;
    else if (!std::strcmp(dir, "up"))        r.mode = UP;
    else if (!std::strcmp(dir, "down"))      r.mode = DOWN;
    else { *invalid = true; return false; }
    r.raw = line;
    return true;
}

// ---- seed: crear el archivo con header si no existe (SIN reglas fijas) ----
// EXTIRPADO 2026-07-20: el pre-seed "garantizaba" intc 100 down (urgencia
// 2026-07-16) resucitandola en cada recarga — 4 dias de re-disparos falsos
// tras marcarla DISPARADA. Las urgencias van en el archivo, no en el binario.
static void ensure_seed(const std::string& path) {
    FILE* f = std::fopen(path.c_str(), "r");
    if (f) { std::fclose(f); return; }
    FILE* w = std::fopen(path.c_str(), "w");
    if (!w) { logline("ERROR: no puedo escribir %s", path.c_str()); return; }
    std::fputs(HEADER, w);
    std::fclose(w);
}

// ---- precios (solo lectura de archivos del bridge) ----
// mid del NBBO vivo si es fresco (<=10 s)
static bool px_from_nbbo(const std::string& sym, double* out) {
    char p[256];
    std::snprintf(p, sizeof(p), "data/nbbo_%s.txt", sym.c_str());
    FILE* f = std::fopen(p, "r");
    if (!f) return false;
    double ep = 0, bid = 0, ask = 0;
    int n = std::fscanf(f, "%lf %lf %lf", &ep, &bid, &ask);
    std::fclose(f);
    if (n != 3 || bid <= 0 || ask < bid) return false;
    if (time(nullptr) - (time_t)ep > 10) return false;
    *out = (bid + ask) / 2.0;
    return true;
}

// close del ultimo bar del archivo (formato EPOCH O H L C V), fresco <=180 s
static bool px_from_bars(const char* path, double* out) {
    FILE* f = std::fopen(path, "r");
    if (!f) return false;
    // leer solo la cola: ultimo bar completo
    std::fseek(f, 0, SEEK_END);
    long sz = std::ftell(f);
    long back = sz < 512 ? sz : 512;
    std::fseek(f, sz - back, SEEK_SET);
    char buf[520];
    size_t got = std::fread(buf, 1, (size_t)back, f);
    std::fclose(f);
    if (got == 0) return false;
    buf[got] = 0;
    // ultima linea no vacia
    char* last = nullptr;
    for (char* line = std::strtok(buf, "\n"); line; line = std::strtok(nullptr, "\n"))
        if (*line) last = line;
    if (!last) return false;
    double ep = 0, o = 0, h = 0, l = 0, c = 0, v = 0;
    if (std::sscanf(last, "%lf %lf %lf %lf %lf %lf", &ep, &o, &h, &l, &c, &v) < 5)
        return false;
    if (c <= 0 || time(nullptr) - (time_t)ep > 180) return false;
    *out = c;
    return true;
}

static bool current_price(const std::string& sym, double* out) {
    if (px_from_nbbo(sym, out)) {
        // ANTI-FANTASMA (2026-07-20): nbbo_<sym>.txt tiene DOS escritores
        // (daemon IBKR sano 1/s + reader alpaca_ws_bridge con quotes viejas
        // — NVDA 203.725 fantasma vs real 206.3 disparo 5 alarmas falsas).
        // Cross-check: si el nbbo diverge >1% del close del bar IBKR fresco
        // (<180s), el bar manda (fuente unica confiable).
        char pb[256];
        std::snprintf(pb, sizeof(pb), "data/bars_%s_ibkr.txt", sym.c_str());
        double bar = 0;
        if (px_from_bars(pb, &bar) && bar > 0 &&
            std::fabs(*out - bar) / bar > 0.01) {
            *out = bar;
        }
        return true;
    }
    char p[256];
    std::snprintf(p, sizeof(p), "data/bars_%s_ibkr.txt", sym.c_str());
    if (px_from_bars(p, out)) return true;
    std::snprintf(p, sizeof(p), "data/bars_%s.txt", sym.c_str());
    return px_from_bars(p, out);
}

// ---- disparo: sirena x3 + voz + banner + mirror ----
static void fire(const Rule& r, double px) {
    char SYM[32];
    std::snprintf(SYM, sizeof(SYM), "%s", r.sym.c_str());
    for (char* p = SYM; *p; ++p) *p = (char)std::toupper((unsigned char)*p);

    // (a) SIRENA ultra-pro: ProAlarm (tono AAC calidad iPhone, eleccion Yunior
    // 2026-07-18 para CRITICOS con dinero en juego) x3 en background. Fallback
    // al viejo fire_alarm.wav si el aiff no existe (nunca mudo).
    std::system("s=\"$HOME/Library/Sounds/ProAlarm.aiff\"; "
                "[ -r \"$s\" ] || s=sounds/fire_alarm.wav; "
                "( for i in 1 2 3; do afplay \"$s\"; done ) >/dev/null 2>&1 &");
    // voz: cola serializada (Yunior 2026-07-18: antes killall say + say& se
    // CORTABAN entre alarmas). speak.sh ENCOLA (instantáneo); voice_queue.sh
    // reproduce entero sin pisarse. Prioridad DANGER (alarma de precio). Si el
    // daemon está caído, speak.sh habla en fallback con mutex. sp ya sanitizado.
    char phrase[200], sp[200], cmd[400];
    std::snprintf(phrase, sizeof(phrase), "ALARMA DE PRECIO: %s toco %.2f",
                  SYM, r.px);
    sh_sanitize(phrase, sp, sizeof(sp));
    std::snprintf(cmd, sizeof(cmd),
                  "scripts/speak.sh DANGER '%s' >/dev/null 2>&1 &", sp);
    std::system(cmd);

    // (b) banner urgente + linea en el espejo ~/Desktop/trading-signals/
    char title[64], msg[320], raw_s[160];
    sh_sanitize(r.raw.c_str(), raw_s, sizeof(raw_s));
    std::snprintf(title, sizeof(title), "%s ALARMA PRECIO", SYM);
    std::snprintf(msg, sizeof(msg), "%s toco %.2f (regla: %s) px=%.4f",
                  SYM, r.px, raw_s, px);
    fleet_notify_urgent(title, msg, "ProAlarm");
    logline("*** DISPARADA *** %s", msg);
}

// (c) marcar la linea como [DISPARADA ...] — rewrite atomico tmp+rename
static bool mark_fired(const std::string& path, const Rule& r) {
    FILE* f = std::fopen(path.c_str(), "r");
    if (!f) return false;
    std::vector<std::string> lines;
    char buf[1024];
    while (std::fgets(buf, sizeof(buf), f)) {
        std::string l = buf;
        if (!l.empty() && l.back() == '\n') l.pop_back();
        lines.push_back(l);
    }
    std::fclose(f);
    // localizar la linea: por indice si sigue igual, si no por contenido
    // (tolera ediciones a mano entre la lectura y el disparo)
    size_t idx = lines.size();
    if (r.line_idx < lines.size() && lines[r.line_idx] == r.raw) idx = r.line_idx;
    else
        for (size_t i = 0; i < lines.size(); ++i)
            if (lines[i] == r.raw) { idx = i; break; }
    if (idx >= lines.size()) return false;
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    char stamp[64];
    std::snprintf(stamp, sizeof(stamp), "[DISPARADA %04d-%02d-%02d %02d:%02d] ",
                  lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday,
                  lt.tm_hour, lt.tm_min);
    lines[idx] = stamp + r.raw;
    std::string tmp = path + ".tmp";
    FILE* w = std::fopen(tmp.c_str(), "w");
    if (!w) return false;
    for (auto& l : lines) { std::fputs(l.c_str(), w); std::fputc('\n', w); }
    std::fclose(w);
    return std::rename(tmp.c_str(), path.c_str()) == 0;
}

int main() {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    const std::string path = alerts_path();
    ensure_seed(path);
    logline("price_alarm arriba — vigilando %s (loop 1 Hz, señal-solamente)",
            path.c_str());

    std::vector<Rule> rules;
    std::map<std::string, int> armed_state;      // raw line -> armed (cross)
    std::map<std::string, time_t> stale_log;     // sym -> ultimo log "sin dato"
    std::map<std::string, bool> bad_logged;      // raw line invalida -> ya logueada
    std::map<std::string, time_t> pending;       // raw line -> 1a lectura hit (confirmacion)
    time_t last_mtime = 0;

    while (true) {
        struct stat st;
        if (stat(path.c_str(), &st) != 0) {
            ensure_seed(path);                    // borrado a mano: re-sembrar
            sleep(1);
            continue;
        }
        if (st.st_mtime != last_mtime) {
            last_mtime = st.st_mtime;
            // preservar el armado cross de reglas que siguen presentes
            for (const auto& r : rules)
                if (r.mode == CROSS && r.armed) armed_state[r.raw] = r.armed;
            rules.clear();
            FILE* f = std::fopen(path.c_str(), "r");
            if (f) {
                char buf[1024];
                size_t idx = 0;
                while (std::fgets(buf, sizeof(buf), f)) {
                    std::string line = buf;
                    if (!line.empty() && line.back() == '\n') line.pop_back();
                    Rule r;
                    bool bad = false;
                    if (parse_rule(line, r, &bad)) {
                        r.line_idx = idx;
                        auto it = armed_state.find(r.raw);
                        if (r.mode == CROSS && it != armed_state.end())
                            r.armed = it->second;
                        rules.push_back(r);
                    } else if (bad && !bad_logged[line]) {
                        bad_logged[line] = true;
                        logline("linea invalida ignorada: '%s'", line.c_str());
                    }
                    idx++;
                }
                std::fclose(f);
                logline("alertas recargadas: %zu activas", rules.size());
            }
        }

        bool any_fired = false;
        for (auto& r : rules) {
            double px = 0;
            if (!current_price(r.sym, &px)) {
                time_t now = time(nullptr);
                if (now - stale_log[r.sym] >= 600) {
                    stale_log[r.sym] = now;
                    logline("%s: sin dato fresco (nbbo<=10s / bars<=180s) — skip",
                            r.sym.c_str());
                }
                continue;
            }
            bool hit = false;
            if (r.mode == DOWN)      hit = px <= r.px;
            else if (r.mode == UP)   hit = px >= r.px;
            else {                                  // CROSS: armar con 1er precio
                if (!r.armed) {
                    r.armed = px > r.px ? -1 : +1;  // arriba => espera caida
                    logline("%s %.2f cross armada (%s, px=%.4f)", r.sym.c_str(),
                            r.px, r.armed < 0 ? "espera caida" : "espera subida",
                            px);
                    continue;                        // nunca disparar al armar
                }
                hit = (r.armed < 0) ? px <= r.px : px >= r.px;
            }
            if (hit) {
                // CONFIRMACION 2 LECTURAS >=1s (2026-07-20: un tick NBBO malo
                // — NVDA 203.70 fantasma con px real 206.3 — disparo 2 alarmas
                // en falso). El bridge escribe NBBO 1/s: la 2a lectura ve el
                // tick siguiente ya sano. Print-o-nada, tambien en sirenas.
                time_t now = time(nullptr);
                auto pit = pending.find(r.raw);
                if (pit == pending.end()) { pending[r.raw] = now; continue; }
                if (now - pit->second < 1) continue;
                pending.erase(pit);
                fire(r, px);
                if (!mark_fired(path, r))
                    logline("WARN: no pude marcar DISPARADA: '%s'", r.raw.c_str());
                armed_state.erase(r.raw);
                any_fired = true;
            } else {
                pending.erase(r.raw);   // dejo de cumplirse -> descartar
            }
        }
        if (any_fired) {
            // el rewrite cambio mtime: forzar recarga limpia en el proximo tick
            struct stat st2;
            if (stat(path.c_str(), &st2) == 0) last_mtime = 0;
        }
        usleep(250000);   // 4 Hz
    }
    return 0;
}
