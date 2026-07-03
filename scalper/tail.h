// tail.h — tail incremental por offset para el whale scalper (2026-07-22,
// extraido de whale_scalper.cpp para poder testearlo).
// Reglas: arranca en EOF (alertas viejas NO se operan); archivo rotado/encogido
// -> saltar a EOF; linea a medio escribir -> esperar; linea GIGANTE (> buffer)
// -> descartarla entera y seguir (antes bloqueaba el tail para siempre).
#pragma once
#include <sys/stat.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace scalp {

inline int64_t tail_fsize(const std::string& p) {
    struct stat st{}; return ::stat(p.c_str(), &st) == 0 ? (int64_t)st.st_size : -1;
}

struct Tail {
    std::string path;
    int64_t off = -1;
    bool skipping_ = false;   // dentro de una linea gigante que se descarta

    std::vector<std::string> read_new() {
        std::vector<std::string> out;
        int64_t sz = tail_fsize(path);
        if (sz < 0) { off = -1; skipping_ = false; return out; }
        if (off < 0 || off > sz) { off = sz; skipping_ = false; }   // primer contacto o rotacion
        if (sz == off) return out;
        FILE* f = std::fopen(path.c_str(), "r");
        if (!f) return out;
        std::fseek(f, (long)off, SEEK_SET);
        char line[2048];
        while (std::fgets(line, sizeof line, f)) {
            size_t n = std::strlen(line);
            if (n == 0) break;
            bool complete = line[n - 1] == '\n';
            if (skipping_) {                       // consumiendo el resto de una gigante
                off += (int64_t)n;
                if (complete) skipping_ = false;
                continue;
            }
            if (complete) { line[n - 1] = 0; out.emplace_back(line); off += (int64_t)n; continue; }
            if (n == sizeof line - 1) {            // buffer lleno sin '\n': linea gigante -> descartar
                off += (int64_t)n;
                skipping_ = true;
                continue;
            }
            break;                                 // linea corta a medio escribir: esperar al writer
        }
        std::fclose(f);
        return out;
    }
};

} // namespace scalp
