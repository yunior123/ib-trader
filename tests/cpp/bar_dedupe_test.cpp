// bar_dedupe_test.cpp — el warm-up del bridge NO puede cambiar lo que dice un bot.
// =============================================================================
// DEFECTO (2026-07-26): los 24 *_signal_bot.cpp leen su feed con
//     popen("tail -n +1 -F data/bars_<sym>_ibkr.txt")
// y NO deduplicaban por epoch. El bridge REESCRIBE ese fichero entero en cada
// warm-up (scripts/ibkr_bar_bridge.py:226 -> open(path,"w") con 2 dias de 1m), y
// `tail -F` reemite el fichero COMPLETO al detectar el truncado. Resultado: hasta
// 1691 barras (2 dias) reinyectadas en los indicadores de un bot EN MARCHA.
// ATR/RSI/BB/CUSUM/VWAP son acumuladores: la misma barra contada dos veces los
// envenena, y el bot canta señales sobre un movimiento que nunca ocurrio.
//
// Este test NO reimplementa nada (el pecado que confiesa math_test.cpp): conduce
// el BINARIO REAL por --stdin con barras REALES del repo, y compara.
//
// build/run:  zsh tests/cpp/run_dedupe.sh     (compila el bot y ejecuta esto)
//             o bien:  ./bar_dedupe_test <ruta_bot> [ruta_bars]
// (se ejecuta desde la RAIZ del repo)

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

// ---- harness minimo (patron de la skill cpp23-testing) ----
static int g_pass = 0, g_fail = 0;

static void check(bool cond, const std::string& name) {
    if (cond) { ++g_pass; std::printf("  [PASS] %s\n", name.c_str()); }
    else      { ++g_fail; std::printf("  [FAIL] %s\n", name.c_str()); }
}
#define EXPECT(cond, name) check((cond), (name))

static std::vector<std::string> read_lines(const fs::path& p) {
    std::vector<std::string> v;
    std::ifstream f(p);
    for (std::string ln; std::getline(f, ln); ) v.push_back(ln);
    return v;
}

static std::string read_all(const fs::path& p) {
    std::ifstream f(p);
    std::ostringstream ss; ss << f.rdbuf();
    return ss.str();
}

static void write_lines(const fs::path& p, const std::vector<std::string>& v,
                        size_t from, size_t to) {
    std::ofstream f(p, std::ios::trunc);
    for (size_t i = from; i < to && i < v.size(); ++i) f << v[i] << "\n";
}

static int run(const std::string& cmd) { return std::system(cmd.c_str()); }

// =============================================================================
// 1) LA PREMISA, medida: `tail -n +1 -F` reemite todo el fichero tras un truncado.
//    Si esto dejara de ser cierto el defecto no existiria — por eso se comprueba
//    aqui y no se da por sabido.
// =============================================================================
static void test_tail_reemite_tras_el_truncado(const fs::path& dir) {
    std::printf("tail -F tras truncado (la premisa del defecto)\n");
    fs::path bars = dir / "premisa_bars.txt";
    fs::path out  = dir / "premisa_tail.txt";
    fs::remove(out);
    {   std::ofstream f(bars, std::ios::trunc);
        for (int i = 0; i < 5; ++i) f << (1000 + i) << " 1 1 1 1 1\n"; }

    // el bot: tail -n +1 -F sobre el fichero de barras
    run("tail -n +1 -F '" + bars.string() + "' > '" + out.string() + "' 2>/dev/null & "
        "echo $! > '" + (dir / "tail.pid").string() + "'");
    run("sleep 2");
    // el bridge: warmup_sym() reescribe el fichero ENTERO (open(path,\"w\"))
    {   std::ofstream f(bars, std::ios::trunc);
        for (int i = 0; i < 7; ++i) f << (1000 + i) << " 1 1 1 1 1\n"; }
    run("sleep 3");
    run("kill $(cat '" + (dir / "tail.pid").string() + "') 2>/dev/null");

    auto emitidas = read_lines(out);
    EXPECT(emitidas.size() > 7,
           "tail reemite el fichero entero: " + std::to_string(emitidas.size()) +
           " lineas emitidas para 7 barras en disco (repeticiones reales)");
}

// =============================================================================
// 2) EL DAÑO Y EL ARREGLO: un replay en medio del stream no puede cambiar NADA
//    de lo que el bot dice. Mismo binario, mismas barras, dos ordenes de llegada.
// =============================================================================
static void test_replay_no_cambia_lo_que_dice_el_bot(const std::string& bot,
                                                     const fs::path& barfile,
                                                     const fs::path& dir) {
    std::printf("replay del warm-up vs indicadores vivos (binario REAL)\n");
    auto bars = read_lines(barfile);
    EXPECT(bars.size() > 600, "fixture: " + std::to_string(bars.size()) +
                              " barras reales de " + barfile.filename().string());
    if (bars.size() < 600) return;

    const size_t corte = bars.size() * 7 / 10;   // el bot llevaba 70% del dia visto
    fs::path limpio = dir / "limpio.txt", envenenado = dir / "envenenado.txt";
    write_lines(limpio, bars, 0, bars.size());
    {   // stream real de un warm-up: lo ya visto + la REESCRITURA completa
        std::ofstream f(envenenado, std::ios::trunc);
        for (size_t i = 0; i < corte; ++i)      f << bars[i] << "\n";
        for (size_t i = 0; i < bars.size(); ++i) f << bars[i] << "\n";
    }

    std::string sal[2], err[2];
    const char* nom[2] = {"limpio", "envenenado"};
    const fs::path fx[2] = {limpio, envenenado};
    for (int i = 0; i < 2; ++i) {
        fs::path wd = dir / nom[i];
        fs::remove_all(wd);
        fs::create_directories(wd / "data");     // el bot escribe data/pos_*.txt
        run("cd '" + wd.string() + "' && '" + bot + "' --stdin < '" +
            fx[i].string() + "' > salida.txt 2> err.txt");
        sal[i] = read_all(wd / "salida.txt");
        err[i] = read_all(wd / "err.txt");
    }

    // Sin esto, "identicos" seria trivial: hay que ver al bot HABLAR.
    size_t nlineas = 0;
    for (char c : sal[0]) if (c == '\n') ++nlineas;
    EXPECT(nlineas >= 5, "el run limpio emite señales (" + std::to_string(nlineas) +
                         " lineas): la comparacion significa algo");

    EXPECT(sal[0] == sal[1],
           "el replay de " + std::to_string(corte) +
           " barras NO cambia una sola linea de lo que dice el bot");
    if (sal[0] != sal[1]) {
        std::printf("     --- limpio ---\n%s     --- envenenado ---\n%s",
                    sal[0].c_str(), sal[1].c_str());
    }

    EXPECT(err[1].find("dedupe") != std::string::npos,
           "el bot CANTA el replay por stderr (fail-loud, no silencio)");
    EXPECT(err[0].find("dedupe") == std::string::npos,
           "un stream limpio no dispara ni un aviso de dedupe (cero falsos positivos)");
}

int main(int argc, char** argv) {
    const char* bot = argc > 1 ? argv[1] : std::getenv("BOT_BIN");
    if (!bot || !*bot) {
        std::fprintf(stderr, "uso: bar_dedupe_test <binario_del_bot> [fichero_de_bars]\n"
                             "     (o BOT_BIN=...); usa tests/cpp/run_dedupe.sh\n");
        return 2;                       // fail-loud: jamas un verde sin haber probado
    }
    fs::path barfile = argc > 2 ? argv[2] : "data/bars_nvda_ibkr.txt";
    if (!fs::exists(barfile)) {
        std::fprintf(stderr, "no encuentro %s (ejecuta desde la raiz del repo)\n",
                     barfile.string().c_str());
        return 2;
    }
    fs::path dir = fs::temp_directory_path() / "ibt_bar_dedupe";
    fs::remove_all(dir);
    fs::create_directories(dir);

    std::printf("=== bar_dedupe_test — bot: %s ===\n", bot);
    test_tail_reemite_tras_el_truncado(dir);
    test_replay_no_cambia_lo_que_dice_el_bot(fs::absolute(bot), barfile, dir);

    std::printf("\n%d pass, %d fail\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
