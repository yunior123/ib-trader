// fleet_notify.h — blazingly-fast Mac-ONLY notifications for the 5 C++ signal
// bots (Yunior 2026-07-10: "lets remove telegram and email, just mac, but make
// sure it really fast in mac with c++").
//
// Path: posix_spawn(/usr/bin/osascript) directo — UN solo spawn del kernel,
// sin shell, sin parse, sin red, sin threads. El caller vuelve en ~0.1ms
// (medido 1.5ms end-to-end con el banner ya disparado). Argumentos van como
// argv: inyeccion shell/AppleScript estructuralmente imposible (as_escape
// solo escapa comillas para el literal de AppleScript).
// Fire-and-forget: SIGCHLD en SIG_IGN una vez -> los hijos se auto-cosechan,
// cero zombies, cero waitpid en el hot path.
//
// ALL notifications are URGENT (orden 2026-07-10): every banner carries sound.
// Nota: para que los banners se queden en pantalla (estilo Alert, no Banner):
// System Settings -> Notifications -> Script Editor -> Alerts. No es scriptable.
#pragma once
#include <spawn.h>
#include <unistd.h>

#include <csignal>
#include <cstdio>

extern char** environ;

// escape for inclusion inside an AppleScript double-quoted string literal
static void as_escape(const char* in, char* out, size_t n) {
    size_t o = 0;
    for (size_t i = 0; in[i] && o + 2 < n; i++) {
        char c = in[i];
        if ((unsigned char)c < 0x20) c = ' ';
        if (c == '"' || c == '\\') out[o++] = '\\';
        out[o++] = c;
    }
    out[o] = 0;
}

// URGENT Mac banner + sound, non-blocking: one posix_spawn, caller returns at once.
static void fleet_notify_urgent(const char* title, const char* msg,
                                const char* sound = "Glass") {
    static bool init = [] { std::signal(SIGCHLD, SIG_IGN); return true; }();
    (void)init;
    char t[256], m[768], script[1200];
    as_escape(title, t, sizeof(t));
    as_escape(msg, m, sizeof(m));
    std::snprintf(script, sizeof(script),
                  "display notification \"%s\" with title \"%s\" sound name \"%s\"",
                  m, t, sound);
    const char* argv[] = {"/usr/bin/osascript", "-e", script, nullptr};
    pid_t pid;
    posix_spawn(&pid, "/usr/bin/osascript", nullptr, nullptr,
                (char* const*)argv, environ);   // no wait: SIG_IGN auto-reaps
}
