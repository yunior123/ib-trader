// korea_watch.cpp — vigilante C++23 de la noche KRX (orden Yunior 2026-07-19
// "usa c++23 como tool, python too slow"). Reemplaza el loop bash/awk: lee
// nbbo_{kospi,skhynix,samsung,koru,soxs}.txt cada 5s, maquina de estados del
// playbook, y en CADA CAMBIO: banner+sonido (fleet_notify, posix_spawn ~0.1ms)
// + voz espanol (speak.sh serializado) + linea a stdout (Monitor -> Claude).
// Niveles y cierres previos son DATO (data/korea_levels.txt + bars), no constantes.
// Estados: PRINT, RECLAIM, NADIE, BAJISTA, V_ROTA, VETO,
// READTHRU_BEAR (Hynix<=-2% Y Samsung<=-2% -> SOXS), FEED_MUERTO.
// Compilar: clang++ -std=c++2c -O3 -march=native -o korea_watch scripts/korea_watch.cpp
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <sys/stat.h>
#include <thread>
#include "../fleet_notify.h"

// Cierre previo MEDIDO de data/bars_<sym>.txt: ultimo close de un dia KST anterior
// al de hoy. Antes eran 4 constantes del 19-jul (CLAUDE.md #7). <=0 = no medible.
static double prev_close(const char* n) {
    char p[128]; std::snprintf(p, sizeof(p), "data/bars_%s.txt", n);
    FILE* f = std::fopen(p, "r"); if (!f) return -1;
    long hoy = (long)((time(nullptr) + 9 * 3600) / 86400);   // dia KST de hoy
    double ep, o, h, l, c, v, out = -1;
    while (std::fscanf(f, "%lf %lf %lf %lf %lf %lf", &ep, &o, &h, &l, &c, &v) == 6)
        if (c > 0 && (long)((ep + 9 * 3600) / 86400) < hoy) out = c;
    std::fclose(f); return out;
}

// Niveles del playbook KODEX: DATO, no constantes. Sin fichero fresco no se opera.
struct Niveles { double veto, vrota, baj, reclaim, print_; long age = -1; bool ok = false; };

static Niveles rd_niveles() {
    Niveles n;
    FILE* f = std::fopen("data/korea_levels.txt", "r"); if (!f) return n;
    char k[64]; double v; int got = 0;
    while (std::fscanf(f, "%63s %lf", k, &v) == 2) {
        if (k[0] == '#') { int ch; while ((ch = fgetc(f)) != '\n' && ch != EOF) {} continue; }
        if (!std::strcmp(k, "veto")) { n.veto = v; got++; }
        else if (!std::strcmp(k, "vrota")) { n.vrota = v; got++; }
        else if (!std::strcmp(k, "baj")) { n.baj = v; got++; }
        else if (!std::strcmp(k, "reclaim")) { n.reclaim = v; got++; }
        else if (!std::strcmp(k, "print")) { n.print_ = v; got++; }
    }
    std::fclose(f);
    struct stat st;
    if (::stat("data/korea_levels.txt", &st) == 0) n.age = (long)(time(nullptr) - st.st_mtime);
    n.ok = (got == 5 && n.age >= 0 && n.age <= 86400);
    return n;
}

struct Q { double mid = 0; long age = 999999; };

static Q rd(const char* n) {
    char p[128]; std::snprintf(p, sizeof(p), "data/nbbo_%s.txt", n);
    FILE* f = std::fopen(p, "r"); Q q; if (!f) return q;
    double ep, b, a;
    if (std::fscanf(f, "%lf %lf %lf", &ep, &b, &a) == 3 && b > 0) {
        q.mid = (b + a) / 2.0; q.age = (long)(time(nullptr) - (time_t)ep);
    }
    std::fclose(f); return q;
}

static void speak(const char* prio, const char* msg) {
    char a1[16], a2[512];
    std::snprintf(a1, sizeof(a1), "%s", prio);
    std::snprintf(a2, sizeof(a2), "%s", msg);
    const char* argv[] = {"/bin/bash", "scripts/speak.sh", a1, a2, nullptr};
    pid_t pid;
    posix_spawn(&pid, "/bin/bash", nullptr, nullptr, (char* const*)argv, environ);
}

enum St { BOOT, PRINT109, RECLAIM, NADIE, BAJ107, VROTA, VETO, RTBEAR, RTBULL, MUERTO };

int main() {
    const double PCK = prev_close("kospi"), PCH = prev_close("skhynix"),
                 PCS = prev_close("samsung");
    if (PCK <= 0 || PCH <= 0 || PCS <= 0) {
        std::fprintf(stderr, "korea_watch: cierre previo NO medible en data/bars_*.txt "
                     "(kospi %.0f hynix %.0f samsung %.0f) — no arranco\n", PCK, PCH, PCS);
        return 1;
    }
    const Niveles N = rd_niveles();
    if (!N.ok) {
        std::fprintf(stderr, "korea_watch: data/korea_levels.txt ausente/incompleto/rancio "
                     "(edad %lds, max 86400) — no arranco. Los niveles del playbook son DATO, "
                     "no constantes: escribelo con veto/vrota/baj/reclaim/print de HOY.\n", N.age);
        speak("DANGER", "Vigilante de Corea sin niveles de hoy. No arranco.");
        return 1;
    }
    std::printf("korea_watch: cierres previos MEDIDOS kospi %.0f hynix %.0f samsung %.0f | "
                "niveles de hace %lds\n", PCK, PCH, PCS, N.age);
    St st = BOOT; int above = 0;
    for (;;) {
        Q k = rd("kospi"), h = rd("skhynix"), s = rd("samsung"), u = rd("koru");
        double hp = 100 * (h.mid / PCH - 1), sp = 100 * (s.mid / PCS - 1);
        St ns;
        // KORU es un ETF US: durante la sesion KRX SIEMPRE esta rancio (medido: 7,1 dias).
        // Exigirle frescura mandaba a MUERTO siempre; el feed de Corea son los KRX.
        if (k.age > 120 || h.age > 120 || s.age > 120) ns = MUERTO;
        else if (k.mid <= N.veto) ns = VETO;
        else if (k.mid <= N.vrota || (st == VROTA && k.mid < N.vrota + 250)) ns = VROTA;  // histeresis 250: no flapear VROTA<->RTBEAR en el pin
        // read-through con histeresis 0.5% (2026-07-19: Hynix oscilaba EXACTO
        // en -2% -> RTBEAR<->BAJ107 cada 5s = voz repetida y crying-wolf).
        // Entra al cruzar +/-2%; sale solo si una pata se recupera a +/-1.5%.
        else if ((hp <= -2.0 && sp <= -2.0) ||
                 (st == RTBEAR && hp <= -1.5 && sp <= -1.5)) ns = RTBEAR;
        else if ((hp >= 2.0 && sp >= 2.0) ||
                 (st == RTBULL && hp >= 1.5 && sp >= 1.5)) ns = RTBULL;   // alcista -> SOXL
        // histeresis 250 pts (2026-07-19: flap NADIE<->RECLAIM cada 5s en la
        // frontera exacta = voz repetida): entrar a un estado pide cruzar el
        // nivel; salir pide alejarse 250 del nivel.
        else if (k.mid <= N.baj || (st == BAJ107 && k.mid < N.baj + 250)) ns = BAJ107;
        else if (k.mid >= N.print_) { if (++above >= 2) ns = PRINT109; else ns = st; }
        else if (k.mid >= N.reclaim || (st == RECLAIM && k.mid > N.reclaim - 250)) ns = RECLAIM;
        else ns = NADIE;
        if (k.mid < N.print_) above = 0;
        char koru[32];
        if (u.age > 3600) std::snprintf(koru, sizeof(koru), "n/d");
        else std::snprintf(koru, sizeof(koru), "$%.2f", u.mid);
        if (ns != st) {
            st = ns;
            char m[256], t[128];
            std::snprintf(m, sizeof(m), "KODEX %.0f (%+.2f%%) Hynix %+.2f%% Samsung %+.2f%% KORU %s",
                          k.mid, 100 * (k.mid / PCK - 1), hp, sp, koru);
            switch (st) {
            case PRINT109: std::snprintf(t, sizeof(t), "🟢 PRINT %.0f — COMPRA KORU", N.print_);
                           fleet_notify_urgent(t, m, "ProAlarm");
                           speak("DANGER", "Print confirmado. Compra Koru activa, mitad de tamaño.");
                           std::printf("PRINT109 %s\n", m); break;
            case RECLAIM:  std::snprintf(t, sizeof(t), "🟡 KODEX reclaim %.0f", N.reclaim);
                           fleet_notify_urgent(t, m, "ProChord");
                           speak("SIGNAL", "Kodex recupero el nivel de reclaim. Atento al print.");
                           std::printf("RECLAIM %s\n", m); break;
            case NADIE:    std::printf("NADIE %s\n", m); break;
            case BAJ107:   std::snprintf(t, sizeof(t), "🔻 KODEX <%.0f — bajista", N.baj);
                           fleet_notify_urgent(t, m, "ProAlert");
                           speak("SIGNAL", "Kodex perdio el nivel bajista. Tesis bajista.");
                           std::printf("BAJ107 %s\n", m); break;
            case VROTA:    std::snprintf(t, sizeof(t), "🔻🔻 V ROTA <%.0f — EWY puts", N.vrota);
                           fleet_notify_urgent(t, m, "ProAlarm");
                           speak("DANGER", "Ve rota. Corea perdio el nivel de la ve. Puts de e doble u ai mañana.");
                           std::printf("VROTA %s\n", m); break;
            case VETO:     fleet_notify_urgent("🔪 VETO — minimo del panico roto", m, "ProAlarm");
                           speak("DANGER", "Veto total. Minimo del panico roto. Jamas long.");
                           std::printf("VETO %s\n", m); break;
            case RTBEAR:   fleet_notify_urgent("🐻 READ-THROUGH: Hynix y Samsung -2% — SOXS", m, "ProAlarm");
                           speak("DANGER", "Read tru bajista. Hynix y Samsung menos dos por ciento. Soxs es el trade.");
                           std::printf("RTBEAR %s\n", m); break;
            case RTBULL:   fleet_notify_urgent("🐂 READ-THROUGH: Hynix y Samsung +2% — SOXL / KORU", m, "ProAlarm");
                           speak("DANGER", "Read tru alcista. Hynix y Samsung mas dos por ciento. Soxl o Koru es el trade.");
                           std::printf("RTBULL %s\n", m); break;
            case MUERTO:   fleet_notify_urgent("⚠️ FEED COREA CONGELADO", m, "ProAlarm");
                           speak("DANGER", "Feed de Corea congelado.");
                           std::printf("MUERTO %s\n", m); break;
            default: break;
            }
            std::fflush(stdout);
        }
        // fin de sesion 02:35 ET
        time_t now = time(nullptr); struct tm lt; localtime_r(&now, &lt);
        if (lt.tm_hour == 2 && lt.tm_min >= 35) {
            speak("SIGNAL", "Corea cerro. Vigilante fuera.");
            std::printf("CIERRE KRX — korea_watch fin\n"); return 0;
        }
        std::this_thread::sleep_for(std::chrono::seconds(5));
    }
}
