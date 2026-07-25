// fleet_hours.cpp — EL PORTERO DE LA FLOTA (C++23)
//
// Orden de Yunior (2026-07-25, literal): "los horarios de la flota son de domingo 8pm a
// viernes 8 pm hora de toronto, fuera de ese horario todo muerto, salvo para testing,
// backtesting, fixes, improvments, etc."
//
// Este binario decide si la flota VIVE. Por eso es C++ y no Python (ley de la casa: lo que
// calcula y vale dinero va en C++23). Un falso LIVE hace hablar a los bots con datos MUERTOS
// -> ante CUALQUIER duda devuelve DEAD y grita por stderr. Un falso DEAD solo calla.
//
//   exit 0 = LIVE   (la flota puede correr)
//   exit 1 = DEAD   (todo apagado)  <- tambien el codigo de cualquier fallo
//   exit 2 = uso incorrecto de la linea de comandos
//
// Zona horaria: America/Toronto DE VERDAD via TZ + localtime_r. NO se hardcodea el offset
// -4/-5: el 2026-01-07 Toronto esta en EST(-5) y el 2026-07-25 en EDT(-4), y la ventana
// se define en hora LOCAL, no en UTC. Medido en este Mac el 2026-07-25:
// libc++ NO tiene std::chrono::zoned_time (no member named 'zoned_time'), asi que la
// via de chrono con tzdb no compila aqui -> localtime_r es la unica opcion real.
//
// Escape de testing (lo pide Yunior explicitamente: "salvo para testing, backtesting,
// fixes"): FLEET_FORCE=1 en el entorno, o el fichero data/FLEET_FORCE. Nunca silencioso:
// la salida dice FORZADO para que nadie confunda un forzado con la ventana real.
//
// Build: ./scripts/build_fleet_hours.sh   (-std=c++23 -O3 -march=native -Wall -Wextra)

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <optional>
#include <string>
#include <string_view>

#include <libgen.h>
#include <limits.h>
#include <unistd.h>

namespace {

constexpr const char* kZone = "America/Toronto";

// La ventana, en minutos desde el domingo 00:00 hora de Toronto.
// domingo 20:00 = 0*1440 + 1200 ; viernes 20:00 = 5*1440 + 1200 = 8400.
constexpr int kOpenMinOfWeek = 1200;   // dom 20:00
constexpr int kCloseMinOfWeek = 8400;  // vie 20:00

const char* dow_es(int wday) {
  static const char* d[] = {"dom", "lun", "mar", "mie", "jue", "vie", "sab"};
  return (wday >= 0 && wday <= 6) ? d[wday] : "???";
}

// Grito de muerte: todo fallo pasa por aqui. Fail-loud, y DEAD.
[[noreturn]] void die_dead(const std::string& msg) {
  std::fprintf(stderr, "fleet_hours: FALLO (%s) -> DEAD por seguridad. "
                       "Jamas asumimos LIVE ante la duda.\n", msg.c_str());
  std::fflush(stderr);
  std::printf("DEAD fleet_hours no pudo determinar la hora: %s\n", msg.c_str());
  std::exit(1);
}

// Fija la zona del proceso a America/Toronto y COMPRUEBA que de verdad se aplico.
// Si TZ es invalida macOS cae a UTC en silencio: eso mueve la ventana 4-5 h y es
// exactamente el tipo de "valor plausible" que esta casa prohibe. Lo detectamos
// exigiendo que la abreviatura sea EST o EDT.
void pin_zone_or_die() {
  if (::setenv("TZ", kZone, 1) != 0) die_dead("setenv(TZ) fallo");
  ::tzset();

  const std::time_t probe = 0;  // 1970-01-01T00:00:00Z -> 1969-12-31 19:00 EST en Toronto
  std::tm tm_probe{};
  if (::localtime_r(&probe, &tm_probe) == nullptr) die_dead("localtime_r fallo en la sonda");
  const char* abbr = tm_probe.tm_zone;
  if (abbr == nullptr) die_dead("la zona no expone abreviatura");
  const std::string_view a{abbr};
  if (a != "EST" && a != "EDT") {
    die_dead(std::string("la zona resuelta es '") + abbr + "', no EST/EDT. "
             "Falta la base de datos de zonas (/usr/share/zoneinfo/America/Toronto)?");
  }
  if (tm_probe.tm_hour != 19 || tm_probe.tm_mday != 31) {
    die_dead("la sonda de epoch no cae en 1969-12-31 19:00 de Toronto");
  }
}

struct Local {
  std::time_t epoch{};
  std::tm tm{};
};

Local local_from_epoch_or_die(std::time_t t) {
  Local L;
  L.epoch = t;
  if (::localtime_r(&t, &L.tm) == nullptr) die_dead("localtime_r fallo");
  return L;
}

// --at "YYYY-MM-DD HH:MM[:SS]" interpretado en America/Toronto.
Local parse_at_or_die(const std::string& s) {
  std::tm tm{};
  int y = 0, mo = 0, d = 0, h = 0, mi = 0, se = 0;
  const int n = std::sscanf(s.c_str(), "%d-%d-%d %d:%d:%d", &y, &mo, &d, &h, &mi, &se);
  if (n < 5) {
    die_dead("--at no se pudo leer, formato esperado \"YYYY-MM-DD HH:MM\" (recibido: " + s + ")");
  }
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h < 0 || h > 23 || mi < 0 || mi > 59 ||
      se < 0 || se > 60) {
    die_dead("--at con campos fuera de rango: " + s);
  }
  tm.tm_year = y - 1900;
  tm.tm_mon = mo - 1;
  tm.tm_mday = d;
  tm.tm_hour = h;
  tm.tm_min = mi;
  tm.tm_sec = se;
  tm.tm_isdst = -1;  // que la libreria decida EST/EDT por la fecha
  const std::time_t t = std::mktime(&tm);
  if (t == static_cast<std::time_t>(-1)) die_dead("mktime rechazo --at: " + s);
  // mktime normaliza en sitio; releemos para tener wday/isdst/zone coherentes.
  return local_from_epoch_or_die(t);
}

int min_of_week(const std::tm& tm) { return tm.tm_wday * 1440 + tm.tm_hour * 60 + tm.tm_min; }

bool in_window(const std::tm& tm) {
  const int w = min_of_week(tm);
  return w >= kOpenMinOfWeek && w < kCloseMinOfWeek;
}

// Epoch REAL del proximo borde (no aritmetica de minutos): construimos la fecha civil
// del domingo/viernes que toca y dejamos que mktime aplique el DST correspondiente.
// Asi la cuenta atras no se descuadra una hora en las semanas de cambio de horario.
std::time_t boundary_epoch_or_die(const std::tm& now_tm, int target_wday, int days_ahead) {
  std::tm t = now_tm;
  t.tm_mday += days_ahead;
  t.tm_hour = 20;
  t.tm_min = 0;
  t.tm_sec = 0;
  t.tm_isdst = -1;
  const std::time_t e = std::mktime(&t);
  if (e == static_cast<std::time_t>(-1)) die_dead("mktime fallo al construir el borde");
  std::tm chk{};
  if (::localtime_r(&e, &chk) == nullptr) die_dead("localtime_r fallo en el borde");
  if (chk.tm_wday != target_wday) die_dead("el borde calculado cae en el dia equivocado");
  return e;
}

std::string hm_span(long long seconds) {
  if (seconds < 0) seconds = 0;
  const long long total_min = seconds / 60;
  return std::to_string(total_min / 60) + "h" + std::to_string(total_min % 60) + "m";
}

std::string repo_data_path(const char* argv0, const char* name) {
  char buf[PATH_MAX];
  if (argv0 == nullptr) return std::string("data/") + name;
  char resolved[PATH_MAX];
  const char* base = (::realpath(argv0, resolved) != nullptr) ? resolved : argv0;
  std::snprintf(buf, sizeof(buf), "%s", base);
  const char* dir = ::dirname(buf);  // el binario vive en la raiz del repo, como ./compass
  return std::string(dir) + "/data/" + name;
}

bool file_exists(const std::string& p) { return ::access(p.c_str(), F_OK) == 0; }

// Detecta el escape de testing y DICE por que (nunca silencioso).
std::optional<std::string> force_reason(const char* argv0) {
  if (const char* e = std::getenv("FLEET_FORCE"); e != nullptr && e[0] != '\0' &&
      std::strcmp(e, "0") != 0) {
    return std::string("FLEET_FORCE=") + e;
  }
  const std::string f = repo_data_path(argv0, "FLEET_FORCE");
  if (file_exists(f)) return std::string("fichero ") + f;
  if (file_exists("data/FLEET_FORCE")) return std::string("fichero data/FLEET_FORCE");
  return std::nullopt;
}

void usage(const char* p) {
  std::fprintf(stderr,
      "uso: %s [--why] [--json] [--at \"YYYY-MM-DD HH:MM\"]\n"
      "  ventana LIVE: domingo 20:00 -> viernes 20:00, America/Toronto\n"
      "  exit 0 = LIVE, exit 1 = DEAD (tambien ante cualquier fallo), exit 2 = uso\n"
      "  FLEET_FORCE=1 o data/FLEET_FORCE fuerzan LIVE y lo ANUNCIAN (testing/backtesting)\n",
      p);
}

std::string json_escape(const std::string& s) {
  std::string o;
  for (char c : s) {
    if (c == '"' || c == '\\') { o += '\\'; o += c; }
    else if (c == '\n') { o += "\\n"; }
    else { o += c; }
  }
  return o;
}

}  // namespace

int main(int argc, char** argv) {
  bool want_why = false, want_json = false;
  // OJO: `at_given` es imprescindible. Con `--at ""` la cadena queda vacia y un
  // `at.empty()` la confundiria con "no me pasaron --at" -> el binario usaria el reloj
  // real y devolveria un veredicto EN SILENCIO sobre un instante que no es el pedido.
  // Eso es exactamente el "valor plausible" que esta casa prohibe: quien pregunta por un
  // instante ilegible tiene que oir un FALLO, no una respuesta creible de otro instante.
  bool at_given = false;
  std::string at;

  for (int i = 1; i < argc; ++i) {
    const std::string_view a{argv[i]};
    if (a == "--why") { want_why = true; }
    else if (a == "--json") { want_json = true; }
    else if (a == "--at") {
      if (i + 1 >= argc) { std::fprintf(stderr, "fleet_hours: --at necesita argumento\n"); return 2; }
      at = argv[++i];
      at_given = true;
    } else if (a.starts_with("--at=")) {
      at = std::string(a.substr(5));
      at_given = true;
    } else if (a == "-h" || a == "--help") { usage(argv[0]); return 2; }
    else { std::fprintf(stderr, "fleet_hours: flag desconocida '%s'\n", argv[i]); usage(argv[0]); return 2; }
  }

  pin_zone_or_die();

  Local now;
  if (at_given) {
    // Cualquier --at ilegible (vacio, blanco o basura) muere aqui GRITANDO. Nunca cae
    // al reloj real: un DEAD callado de sabado parece correcto y esconde el fallo.
    now = parse_at_or_die(at);
  } else {
    const std::time_t t = std::time(nullptr);
    if (t == static_cast<std::time_t>(-1)) die_dead("time() fallo");
    now = local_from_epoch_or_die(t);
  }

  const bool real_live = in_window(now.tm);
  const std::optional<std::string> forced = force_reason(argv[0]);
  const bool live = real_live || forced.has_value();

  char stamp[64];
  std::snprintf(stamp, sizeof(stamp), "%s %04d-%02d-%02d %02d:%02d %s", dow_es(now.tm.tm_wday),
                now.tm.tm_year + 1900, now.tm.tm_mon + 1, now.tm.tm_mday, now.tm.tm_hour,
                now.tm.tm_min, now.tm.tm_zone ? now.tm.tm_zone : "??");

  // Cuenta atras al borde que toca.
  std::string detail;
  long long secs = 0;
  if (real_live) {
    const int days = (5 - now.tm.tm_wday + 7) % 7;  // hasta el proximo viernes
    secs = static_cast<long long>(boundary_epoch_or_die(now.tm, 5, days)) - now.epoch;
    detail = "quedan " + hm_span(secs) + " de ventana (cierra vie 20:00)";
  } else {
    int days = (7 - now.tm.tm_wday) % 7;  // hasta el proximo domingo
    if (now.tm.tm_wday == 0 && min_of_week(now.tm) < kOpenMinOfWeek) days = 0;
    secs = static_cast<long long>(boundary_epoch_or_die(now.tm, 0, days)) - now.epoch;
    detail = "faltan " + hm_span(secs) + " para el arranque (dom 20:00)";
  }

  const char* state = live ? "LIVE" : "DEAD";
  std::string forced_tag;
  if (forced.has_value()) {
    forced_tag = " (FORZADO por " + *forced + " — no es la ventana real: la ventana dice " +
                 std::string(real_live ? "LIVE" : "DEAD") + ")";
  }

  if (want_json) {
    std::printf("{\"state\":\"%s\",\"live\":%s,\"window_live\":%s,\"forced\":%s,"
                "\"forced_reason\":%s,\"zone\":\"%s\",\"now\":\"%s\",\"tz_abbr\":\"%s\","
                "\"utc_offset_sec\":%ld,\"min_of_week\":%d,\"seconds_to_boundary\":%lld,"
                "\"window\":\"dom20:00-vie20:00\",\"detail\":\"%s\"}\n",
                state, live ? "true" : "false", real_live ? "true" : "false",
                forced.has_value() ? "true" : "false",
                forced.has_value() ? ("\"" + json_escape(*forced) + "\"").c_str() : "null",
                kZone, json_escape(stamp).c_str(), now.tm.tm_zone ? now.tm.tm_zone : "??",
                static_cast<long>(now.tm.tm_gmtoff), min_of_week(now.tm), secs,
                json_escape(detail).c_str());
  } else {
    std::printf("%s%s ventana dom20:00-vie20:00 %s | ahora %s | %s\n", state, forced_tag.c_str(),
                kZone, stamp, detail.c_str());
    if (want_why) {
      std::printf("  motivo: la flota vive de domingo 20:00 a viernes 20:00 hora de Toronto "
                  "(sabado entero muerto, domingo hasta 19:59 muerto, viernes desde 20:00 "
                  "muerto).\n"
                  "  ahora son las %02d:%02d del %s en %s (%s, offset UTC %+.1f h) -> "
                  "minuto de la semana %d, ventana [%d, %d).\n",
                  now.tm.tm_hour, now.tm.tm_min, dow_es(now.tm.tm_wday), kZone,
                  now.tm.tm_zone ? now.tm.tm_zone : "??",
                  static_cast<double>(now.tm.tm_gmtoff) / 3600.0, min_of_week(now.tm),
                  kOpenMinOfWeek, kCloseMinOfWeek);
      if (forced.has_value()) {
        std::printf("  ATENCION: LIVE FORZADO (%s). Esto es el escape de testing/backtesting; "
                    "en produccion la ventana manda.\n", forced->c_str());
      }
    }
  }

  return live ? 0 : 1;
}
