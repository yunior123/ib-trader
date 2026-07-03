// safety.h — candados de seguridad del order_engine (dinero real).
//   1) Doble llave: --arm-live (flag) Y archivo order_engine/ARM_LIVE con la
//      fecha de HOY. Falta una -> DRY (registra la orden que colocaría, no la
//      manda). PAPER (7497) es el default de puerto; LIVE (7496) opt-in.
//   2) Disarm-on-exit: SIGINT/SIGTERM/crash/atexit -> cancel_all_own() + flush
//      ANTES de morir el proceso. Handler instalado ANTES de la 1ª orden.
// Header-only. La protección REAL ante crash son los stops NATIVOS (server-side);
// esto es la red de las órdenes en vuelo + entries (que jamás descansan).
#pragma once
#include <atomic>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <cstring>
#include <exception>
#include <fstream>
#include <functional>
#include <string>
#include <unistd.h>

namespace oe {

// Fecha local YYYY-MM-DD (para casar contra ARM_LIVE y armed_date de zonas).
inline std::string today_date() {
    time_t t = time(nullptr);
    struct tm lt{};
    localtime_r(&t, &lt);
    char buf[16];
    std::snprintf(buf, sizeof buf, "%04d-%02d-%02d", lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday);
    return buf;
}

inline std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    size_t b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

// Doble llave. arm_flag = se pasó --arm-live. arm_file = order_engine/ARM_LIVE.
enum class ArmFail { NONE, NO_FLAG, FILE_MISSING, FILE_STALE };

// Veredicto de la doble llave CON motivo accionable: un cierre que no se manda es
// dinero en riesgo, y "DRY" a secas no dice qué llave falta ni cómo renovarla.
struct ArmStatus {
    bool ok = false;
    ArmFail fail = ArmFail::NONE;
    std::string file_date;      // lo que había en ARM_LIVE ("" si ausente/vacío)
    std::string reason;         // listo para stderr + ledger
};

inline ArmStatus arm_status(bool arm_flag, const std::string& arm_file,
                            const std::string& today) {
    ArmStatus s;
    std::ifstream f(arm_file);
    if (!f.is_open()) {
        s.fail = ArmFail::FILE_MISSING;
        s.reason = "falta el fichero " + arm_file + " -> arma con order_engine/arm.sh";
    } else {
        std::string content((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
        s.file_date = trim(content);
        if (s.file_date != today) {
            s.fail = ArmFail::FILE_STALE;
            s.reason = "ARM_LIVE tiene fecha " + (s.file_date.empty() ? std::string("VACIA") : s.file_date) +
                       " pero hoy es " + today + " -> renueva con order_engine/arm.sh";
        }
    }
    if (!arm_flag) {
        const std::string m = "falta el flag --arm-live (relanza el motor con --arm-live)";
        if (s.fail == ArmFail::NONE) { s.fail = ArmFail::NO_FLAG; s.reason = m; }
        else s.reason += "; ademas " + m;
    }
    s.ok = (s.fail == ArmFail::NONE);
    return s;
}

inline ArmStatus arm_status(bool arm_flag, const std::string& arm_file) {
    return arm_status(arm_flag, arm_file, today_date());
}

inline bool armed_live(bool arm_flag, const std::string& arm_file) {
    return arm_status(arm_flag, arm_file, today_date()).ok;
}

// ---- guardias de proceso (singleton simple para señales/atexit) ----------
class Guard {
public:
    // Instala handlers + atexit con la función de desarme (cancel_all + flush).
    // Llamar ANTES de la primera orden.
    static void install(std::function<void()> disarm) {
        inst().disarm_ = std::move(disarm);
        std::signal(SIGINT,  &Guard::on_signal);
        std::signal(SIGTERM, &Guard::on_signal);
        std::signal(SIGHUP,  &Guard::on_signal);
        // Fatales: mejor-esfuerzo de cancelar antes de morir (los stops nativos
        // son la red real; entries nunca descansan). Documentado como best-effort.
        std::signal(SIGSEGV, &Guard::on_fatal);
        std::signal(SIGABRT, &Guard::on_fatal);
        std::signal(SIGBUS,  &Guard::on_fatal);
        std::signal(SIGFPE,  &Guard::on_fatal);
        std::atexit(&Guard::on_atexit);
        // Excepción no capturada -> terminate: contexto NORMAL (no señal), así que
        // aquí SÍ es seguro desarmar limpio (socket/mutex) antes de abortar.
        std::set_terminate(&Guard::on_terminate);
    }

    // El main loop consulta esto y sale limpio (ruta preferida de SIGINT/TERM).
    static bool stop_requested() { return inst().stop_.load(); }

    // Ejecuta el desarme UNA sola vez (idempotente).
    static void run_disarm_once() {
        if (inst().disarmed_.exchange(true)) return;
        if (inst().disarm_) inst().disarm_();
    }

private:
    Guard() = default;
    static Guard& inst() { static Guard g; return g; }

    static void on_signal(int sig) {
        inst().stop_.store(true);           // el main loop rompe y desarma limpio
        static const char m[] = "\n[safety] senal recibida -> desarme y salida limpia\n";
        (void)!write(2, m, sizeof(m) - 1);
        (void)sig;
    }
    static void on_fatal(int sig) {
        // Contexto de SEÑAL: SOLO async-signal-safe. NADA de socket/mutex/iostream
        // (deadlock/UB justo cuando importa). La red REAL ante crash son los stops
        // NATIVOS server-side + el reconcile de arranque (cancela huérfanas OE:).
        static const char m[] = "\n[safety] senal FATAL: stops nativos protegen; reconcile al reiniciar\n";
        (void)!write(2, m, sizeof(m) - 1);
        std::signal(sig, SIG_DFL);          // restaurar y re-lanzar para core/estado real
        std::raise(sig);
    }
    static void on_terminate() {
        run_disarm_once();                  // seguro aquí: contexto normal, no señal
        std::abort();
    }
    static void on_atexit() { run_disarm_once(); }

    std::function<void()> disarm_;
    std::atomic<bool> stop_{false};
    std::atomic<bool> disarmed_{false};
};

} // namespace oe
