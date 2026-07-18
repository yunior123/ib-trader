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
#include <fcntl.h>
#include <spawn.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cctype>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

extern char** environ;

// ---- espejo Desktop (orden Yunior 2026-07-15: "make sure that we see the
// notifications in desktop notes files as well") — cada banner se APPENDEA a
// ~/Desktop/trading-signals/YYYY-MM-DD.txt con timestamp de pared al segundo,
// para que el humano compare hora-de-notificacion vs grafico real.
// open(O_APPEND)+write+close directo: sin shell, sin buffers compartidos,
// append atomico (<PIPE_BUF). Si Desktop no es escribible, falla en silencio
// (el banner + ops log siguen siendo canonicos).
static void fleet_notify_desktop_mirror(const char* title, const char* msg) {
    const char* home = getenv("HOME");
    if (!home || !*home) return;
    time_t now = time(nullptr);
    struct tm lt;
    localtime_r(&now, &lt);
    char dir[512], path[600], line[1200];
    snprintf(dir, sizeof(dir), "%s/Desktop/trading-signals", home);
    mkdir(dir, 0755);  // idempotente
    snprintf(path, sizeof(path), "%s/%04d-%02d-%02d.txt", dir,
             lt.tm_year + 1900, lt.tm_mon + 1, lt.tm_mday);
    int n = snprintf(line, sizeof(line), "%02d:%02d:%02d | %s | %s\n",
                     lt.tm_hour, lt.tm_min, lt.tm_sec, title, msg);
    if (n <= 0) return;
    int fd = open(path, O_WRONLY | O_APPEND | O_CREAT, 0644);
    if (fd >= 0) {
        write(fd, line, (size_t)n);
        close(fd);
    }
}

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
                                // ProChord: tono AAC calidad iPhone (~/Library/Sounds,
                                // eleccion Yunior 2026-07-18) para señales BUY/SELL.
                                // Ballenas/muros pasan "ProAlert"; criticos "ProAlarm".
                                const char* sound = "ProChord") {
    static bool init = [] { std::signal(SIGCHLD, SIG_IGN); return true; }();
    (void)init;
    char t[256], m[768], script[1300];
    as_escape(title, t, sizeof(t));
    as_escape(msg, m, sizeof(m));
    // ANTI-DESCARTE (empirico 2026-07-18): macOS descarta banners que llegan en
    // el MISMO instante desde la misma app (3 simultaneos → el de en medio se
    // perdia siempre; separados 0.4s llegan los 3). El HIJO osascript duerme un
    // jitter aleatorio 0–0.45s antes de publicar — el caller sigue volviendo en
    // ~0.1ms (el delay vive en el hijo). El delay 0.6 final mantiene vivo al
    // hijo hasta completar la entrega (proceso que muere al publicar pierde
    // banners a veces).
    std::snprintf(script, sizeof(script),
                  "delay (random number from 0.0 to 0.45)\n"
                  "display notification \"%s\" with title \"%s\" sound name \"%s\"\n"
                  "delay 0.6",
                  m, t, sound);
    const char* argv[] = {"/usr/bin/osascript", "-e", script, nullptr};
    pid_t pid;
    posix_spawn(&pid, "/usr/bin/osascript", nullptr, nullptr,
                (char* const*)argv, environ);   // no wait: SIG_IGN auto-reaps
    fleet_notify_desktop_mirror(title, msg);    // espejo Desktop 2026-07-15
}
