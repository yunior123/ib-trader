// korea_watch.cpp — vigilante C++23 de la noche KRX (orden Yunior 2026-07-19
// "usa c++23 como tool, python too slow"). Reemplaza el loop bash/awk: lee
// nbbo_{kospi,skhynix,samsung,koru,soxs}.txt cada 5s, maquina de estados del
// playbook, y en CADA CAMBIO: banner+sonido (fleet_notify, posix_spawn ~0.1ms)
// + voz espanol (speak.sh serializado) + linea a stdout (Monitor -> Claude).
// Estados: PRINT_109K, RECLAIM, NADIE, BAJISTA_107K5, V_ROTA, VETO,
// READTHRU_BEAR (Hynix<=-2% Y Samsung<=-2% -> SOXS), FEED_MUERTO.
// Compilar: clang++ -std=c++2c -O3 -march=native -o korea_watch scripts/korea_watch.cpp
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <thread>
#include "../fleet_notify.h"

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
    constexpr double PCK = 109000, PCH = 1842000, PCS = 255000, PCU = 18.26;
    St st = BOOT; int above = 0;
    for (;;) {
        Q k = rd("kospi"), h = rd("skhynix"), s = rd("samsung"), u = rd("koru");
        double hp = 100 * (h.mid / PCH - 1), sp = 100 * (s.mid / PCS - 1);
        St ns;
        if (k.age > 120 || u.age > 120) ns = MUERTO;
        else if (k.mid <= 103550) ns = VETO;
        else if (k.mid <= 105000 || (st == VROTA && k.mid < 105250)) ns = VROTA;  // histeresis 250: no flapear VROTA<->RTBEAR en el pin de 105000
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
        else if (k.mid <= 107500 || (st == BAJ107 && k.mid < 107750)) ns = BAJ107;
        else if (k.mid >= 109000) { if (++above >= 2) ns = PRINT109; else ns = st; }
        else if (k.mid >= 108400 || (st == RECLAIM && k.mid > 108150)) ns = RECLAIM;
        else ns = NADIE;
        if (k.mid < 109000) above = 0;
        if (ns != st) {
            st = ns;
            char m[256];
            std::snprintf(m, sizeof(m), "KODEX %.0f (%+.2f%%) Hynix %+.2f%% Samsung %+.2f%% KORU $%.2f",
                          k.mid, 100 * (k.mid / PCK - 1), hp, sp, u.mid);
            switch (st) {
            case PRINT109: fleet_notify_urgent("🟢 PRINT 109000 — COMPRA KORU", m, "ProAlarm");
                           speak("DANGER", "Print confirmado. Compra Koru activa, mitad de tamaño.");
                           std::printf("PRINT109 %s\n", m); break;
            case RECLAIM:  fleet_notify_urgent("🟡 KODEX reclaim 108400", m, "ProChord");
                           speak("SIGNAL", "Kodex recupero ciento ocho cuatrocientos. Atento al print.");
                           std::printf("RECLAIM %s\n", m); break;
            case NADIE:    std::printf("NADIE %s\n", m); break;
            case BAJ107:   fleet_notify_urgent("🔻 KODEX <107500 — bajista", m, "ProAlert");
                           speak("SIGNAL", "Kodex perdio ciento siete quinientos. Tesis bajista.");
                           std::printf("BAJ107 %s\n", m); break;
            case VROTA:    fleet_notify_urgent("🔻🔻 V ROTA <105000 — EWY puts", m, "ProAlarm");
                           speak("DANGER", "Ve rota. Corea perdio ciento cinco mil. Puts de e doble u ai mañana.");
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
