// korea_tape.cpp — veredicto KORU/Corea INSTANTANEO (orden Yunior 2026-07-19
// "rapido, te demoras mucho, usa c++23"). Lee nbbo_{kospi,skhynix,samsung,
// koru}.txt + reglas del playbook y responde en microsegundos: estado + orden
// de UN numero. Uso: ./korea_tape   (compilar: clang++ -std=c++2c -O3
// -march=native -o korea_tape scripts/korea_tape.cpp)
#include <cstdio>
#include <ctime>
#include <string_view>

struct Q { double mid = 0; long age = 999999; };

static Q read_nbbo(const char* name) {
    char p[128]; std::snprintf(p, sizeof(p), "data/nbbo_%s.txt", name);
    FILE* f = std::fopen(p, "r");
    Q q;
    if (!f) return q;
    double ep, bid, ask;
    if (std::fscanf(f, "%lf %lf %lf", &ep, &bid, &ask) == 3 && bid > 0) {
        q.mid = (bid + ask) / 2.0;
        q.age = (long)(time(nullptr) - (time_t)ep);
    }
    std::fclose(f);
    return q;
}

int main() {
    constexpr double PC_KODEX = 109000, PC_HYNIX = 1842000, PC_SAMS = 255000,
                     PC_KORU = 18.26;
    Q k = read_nbbo("kospi"), h = read_nbbo("skhynix"), s = read_nbbo("samsung"),
      u = read_nbbo("koru");
    auto pct = [](double x, double pc) { return 100.0 * (x / pc - 1.0); };
    std::printf("KODEX %.0f (%+.2f%%)  Hynix %+.2f%%  Samsung %+.2f%%  KORU $%.2f (%+.1f%%)\n",
                k.mid, pct(k.mid, PC_KODEX), pct(h.mid, PC_HYNIX),
                pct(s.mid, PC_SAMS), u.mid, pct(u.mid, PC_KORU));
    if (k.age > 120 || u.age > 120) {
        std::printf("⚠️  FEED VIEJO (kospi %lds, koru %lds) — no operar a ciegas\n", k.age, u.age);
        return 1;
    }
    std::string_view v;
    if      (k.mid <= 103550) v = "🔪 VETO: minimo del panico ROTO — jamas long; bajista full (EWY puts manana)";
    else if (k.mid <= 105000) v = "🔻 V ROTA <105000 — NO KORU; tesis EWY puts CONFIRMADA para la apertura US";
    else if (k.mid <= 107500) v = "🔻 BAJISTA <107500 (rechazo del gap-fill) — NO KORU; EWY puts manana si cierra debil. Decide 105000";
    else if (k.mid >= 109000) v = "🟢 PRINT 109000 — si aguanta 2 lecturas: COMPRA KORU (mitad de tamano), TP 20.60";
    else if (k.mid >= 108400) v = "🟡 Reclaim 108400+ — compra KORU se reactiva SOLO con print 109000 x2";
    else                      v = "⏸  Tierra de nadie 105000-108400 — NO operar; esperar print o quiebre";
    std::printf("%.*s\n", (int)v.size(), v.data());
    return 0;
}
