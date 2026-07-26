// test_fleet_notify_write.cpp — fleet_notify.h:54 (Yunior 2026-07-26).
// write(fd, line, (size_t)n) usaba el "n" de snprintf: si el mensaje trunca, snprintf
// devuelve la longitud que HABRIA necesitado, no lo realmente escrito -> write() lee
// fuera de "line" (1200 bytes). Bajo ASan esto es un stack-buffer-overflow de LECTURA
// en el syscall write(). Este binario no debe abortar bajo -fsanitize=address.
#include "../fleet_notify.h"
#include <cstdio>
#include <string>
#include <unistd.h>

int main() {
    // mensaje >> 1200 bytes fuerza a snprintf a truncar dentro de line[].
    std::string longmsg(4000, 'A');
    fleet_notify_desktop_mirror("TEST-LARGO", longmsg.c_str());
    fleet_notify_desktop_mirror("TEST-CORTO", "ok");
    std::printf("SIN CRASH\n");
    return 0;
}
