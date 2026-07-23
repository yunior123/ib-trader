// ledger.h — libro append-only del whale scalper (JSONL, O_APPEND+fsync).
// Cada evento con timestamp wall(us)+mono(ms). Recovery: al arrancar se
// parsea el dia y un FILL de BUY sin TRADE_CLOSE = posicion viva.
#pragma once
#include <fcntl.h>
#include <unistd.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <optional>
#include <string>
#include "scalper_core.h"

namespace scalp {

inline std::string today_str(time_t t = 0) {
    if (!t) t = ::time(nullptr);
    struct tm lt{}; localtime_r(&t, &lt);
    char b[16]; std::snprintf(b, sizeof b, "%04d-%02d-%02d", lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday);
    return b;
}
inline int today_yyyymmdd(time_t t = 0) {
    if (!t) t = ::time(nullptr);
    struct tm lt{}; localtime_r(&t, &lt);
    return (lt.tm_year + 1900) * 10000 + (lt.tm_mon + 1) * 100 + lt.tm_mday;
}

class Ledger {
public:
    explicit Ledger(std::string dir) : dir_(std::move(dir)) {}

    // escapa comillas/backslash para JSON valido siempre
    static std::string jesc(const std::string& s) {
        std::string o; o.reserve(s.size());
        for (char c : s) {
            if (c == '"' || c == '\\') { o += '\\'; o += c; }
            else if ((unsigned char)c < 0x20) o += ' ';
            else o += c;
        }
        return o;
    }

    void write(const char* ev, const char* state, const OptContract& con,
               int px_c, int order_id, const std::string& reason, int64_t mono_ms) {
        struct timespec ts{}; clock_gettime(CLOCK_REALTIME, &ts);
        // reason acotado ANTES de formatear: un reason gigante truncaria el
        // snprintf y se COMERIA el '\n' final -> dos eventos pegados en una
        // linea = ledger corrupto para el recovery. Jamas.
        std::string r = jesc(reason);
        if (r.size() > 900) { r.resize(900); r += "...(trunc)"; }
        char line[2048];
        int n = std::snprintf(line, sizeof line,
            "{\"tw\":%lld,\"tm\":%lld,\"ev\":\"%s\",\"state\":\"%s\","
            "\"strike_c\":%lld,\"right\":\"%c\",\"exp\":%d,"
            "\"px_c\":%d,\"oid\":%d,\"reason\":\"%s\"}\n",
            (long long)(ts.tv_sec * 1000000LL + ts.tv_nsec / 1000), (long long)mono_ms,
            ev, state, (long long)con.strike_c, con.right ? con.right : '-', con.yyyymmdd,
            px_c, order_id, r.c_str());
        if (n < 0) return;
        if (n >= (int)sizeof line) {           // cinturon: la linea SIEMPRE termina en '\n'
            line[sizeof line - 2] = '\n'; line[sizeof line - 1] = 0;
        }
        int fd = ::open(path().c_str(), O_WRONLY | O_APPEND | O_CREAT, 0644);
        if (fd < 0) { std::fprintf(stderr, "ledger: no puedo abrir %s\n", path().c_str()); return; }
        ssize_t wr = ::write(fd, line, std::strlen(line));
        if (wr < 0) std::fprintf(stderr, "ledger: write fallo en %s\n", path().c_str());
        ::fsync(fd);            // el libro JAMAS miente ni pierde eventos
        ::close(fd);
    }

    // recovery: BUY FILL de hoy sin TRADE_CLOSE posterior -> posicion viva
    struct Open { OptContract con; int fill_c; int64_t tw_us; };
    std::optional<Open> find_open_position() {
        FILE* f = std::fopen(path().c_str(), "r");
        if (!f) return std::nullopt;
        std::optional<Open> open;
        char line[2048];   // = tamaño max de linea del writer (una linea larga
                           // partida en dos chunks jamas debe confundir el parseo)
        while (std::fgets(line, sizeof line, f)) {
            std::string_view sv(line);
            auto has = [&](const char* pat) { return sv.find(pat) != std::string_view::npos; };
            auto num = [&](const char* key) -> long long {
                std::string p = std::string("\"") + key + "\":";
                size_t q = sv.find(p);
                return q == std::string_view::npos ? 0 : std::atoll(line + q + p.size());
            };
            if ((has("\"ev\":\"FILL\"") || has("\"ev\":\"FILL_ADOPT\"")) && has("BUY")) {
                Open o; o.fill_c = (int)num("px_c"); o.tw_us = num("tw");
                if (o.fill_c <= 0) {                  // ledgers pre-fix: precio solo en reason "BUY @ 146c"
                    size_t at = sv.find("@ ");
                    if (at != std::string_view::npos) o.fill_c = std::atoi(line + at + 2);
                }
                o.con.strike_c = num("strike_c"); o.con.yyyymmdd = (int)num("exp");
                size_t r = sv.find("\"right\":\"");
                o.con.right = r == std::string_view::npos ? 'P' : line[r + 9];
                open = o;
            } else if (has("\"ev\":\"TRADE_CLOSE\"") || has("\"ev\":\"NO_FILL\"")) {
                open.reset();
            }
        }
        std::fclose(f);
        return open;
    }

    // estado del dia para recovery de contadores (kill -9 tras un cierre):
    // cierres del dia, si alguno fue rojo neto, y el tw (us) del ultimo cierre.
    struct DayState { int closes = 0; bool red = false; int64_t last_close_us = 0; };
    DayState day_state() {
        DayState ds;
        FILE* f = std::fopen(path().c_str(), "r");
        if (!f) return ds;
        char line[2048];
        while (std::fgets(line, sizeof line, f)) {
            std::string_view sv(line);
            if (sv.find("\"ev\":\"TRADE_CLOSE\"") == std::string_view::npos) continue;
            ++ds.closes;
            std::string p = "\"tw\":";
            size_t q = sv.find(p);
            if (q != std::string_view::npos) ds.last_close_us = std::atoll(line + q + p.size());
            size_t r = sv.find("net ");            // reason: "net -530c (buy .. sell ..)"
            if (r != std::string_view::npos && std::atoll(line + r + 4) <= 0) ds.red = true;
        }
        std::fclose(f);
        return ds;
    }

    std::string path() const { return dir_ + "/trades_" + today_str() + ".jsonl"; }
    std::string pm_path() const { return dir_ + "/postmortem_" + today_str() + ".md"; }

    // post-mortem: cadena completa del dia + veredicto, para revision humana
    void postmortem(const std::string& why) {
        FILE* src = std::fopen(path().c_str(), "r");
        FILE* out = std::fopen(pm_path().c_str(), "a");
        if (!out) return;
        std::fprintf(out, "\n# POST-MORTEM %s\n\n**Motivo del HALT:** %s\n\n"
                          "Regla: un trade rojo neto = parada total hasta revision humana.\n"
                          "Revisar: ¿era band-walk de continuacion (dia de catalizador del lider)?"
                          " ¿spread se comio el edge? ¿entrada tarde vs la alerta?\n\n"
                          "## Cadena de eventos del dia\n```\n", today_str().c_str(), why.c_str());
        if (src) { char b[1024]; while (std::fgets(b, sizeof b, src)) std::fputs(b, out); std::fclose(src); }
        std::fputs("```\n", out);
        std::fclose(out);
    }

private:
    std::string dir_;
};

} // namespace scalp
