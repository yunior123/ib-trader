// account_cfg.h — de dónde sale la cuenta ESPERADA. Nada de credenciales en el código.
//
// POR QUE EXISTE: el motor tenía la cuenta a fuego (`U26942420`/`DUR197573`), así que
// abortaba para cualquier otra persona. Ahora se configura, pero **sin perder la
// protección**: el check sigue siendo obligatorio y FALLA CERRADO — sin cuenta
// configurada el motor NO opera. Eso es deliberado: si nadie declaró qué cuenta
// espera, no hay forma de saber que el Gateway está logueado donde crees.
//
// Orden de búsqueda (gana el primero que exista):
//   1. env IBTRADER_ACCOUNT_LIVE / IBTRADER_ACCOUNT_PAPER   (para tests y CI)
//   2. ~/Library/Application Support/ib-trader/config.json  (panel de la .app)
//   3. <repo>/data/account.txt   ->  "live=U1234567" / "paper=DU1234567"
#pragma once
#include <cstdlib>
#include <fstream>
#include <string>

namespace oe {

inline std::string cfg_trim(const std::string& s) {
    const auto a = s.find_first_not_of(" \t\r\n\"");
    if (a == std::string::npos) return "";
    const auto b = s.find_last_not_of(" \t\r\n\",");
    return s.substr(a, b - a + 1);
}

// Extrae "clave": "valor" de un JSON plano, sin dependencias.
inline std::string json_str_field(const std::string& blob, const std::string& key) {
    const auto k = blob.find("\"" + key + "\"");
    if (k == std::string::npos) return "";
    const auto c = blob.find(':', k);
    if (c == std::string::npos) return "";
    const auto q1 = blob.find('"', c);
    if (q1 == std::string::npos) return "";
    const auto q2 = blob.find('"', q1 + 1);
    if (q2 == std::string::npos) return "";
    return blob.substr(q1 + 1, q2 - q1 - 1);
}

// Cuenta esperada para el modo. Devuelve "" si NADIE la configuró -> el llamante ABORTA.
inline std::string expected_account(bool live, const std::string& repo) {
    if (const char* e = std::getenv(live ? "IBTRADER_ACCOUNT_LIVE" : "IBTRADER_ACCOUNT_PAPER"))
        if (*e) return cfg_trim(e);

    if (const char* home = std::getenv("HOME")) {
        const std::string p = std::string(home) +
            "/Library/Application Support/ib-trader/config.json";
        std::ifstream f(p);
        if (f) {
            const std::string blob((std::istreambuf_iterator<char>(f)),
                                    std::istreambuf_iterator<char>());
            // El panel guarda UNA cuenta; el prefijo dice si es live (U) o paper (DU).
            const std::string acct = cfg_trim(json_str_field(blob, "account"));
            if (!acct.empty()) {
                const bool is_paper = acct.rfind("DU", 0) == 0;
                if (live != is_paper) return acct;   // coincide con el modo pedido
            }
        }
    }

    std::ifstream f(repo + "/data/account.txt");
    if (f) {
        std::string line;
        const std::string want = live ? "live=" : "paper=";
        while (std::getline(f, line)) {
            line = cfg_trim(line);
            if (line.empty() || line[0] == '#') continue;
            if (line.rfind(want, 0) == 0) return cfg_trim(line.substr(want.size()));
        }
    }
    return "";
}

}  // namespace oe
