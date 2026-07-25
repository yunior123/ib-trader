// level_react.h — LA REACCION A UN NIVEL, ESCRITA UNA SOLA VEZ.
// Feature minada #8 (`level-react`), ola 2. Orden Yunior 2026-07-25.
//
// POR QUE EXISTE ESTE ARCHIVO
// ---------------------------
// ~30 `*_signal_bot.cpp` (44.379 lineas en total, medido) cargan CADA UNO su propia logica de
// nivel ad-hoc. En `qqq_signal_bot.cpp:1085` vive esta linea, y variantes suyas estan copiadas
// a mano por toda la flota:
//
//     bool touch = ib ? (b.l <= a.level + 0.25*atr && b.l >= a.level - 0.25*atr) : ...
//
// Eso es "el precio esta CERCA del nivel". La doctrina de la casa (CLAUDE.md regla 2) dice
// **PRINT O NADA**: se entra con el nivel IMPRESO — dos lecturas cruzando — jamas "esta cerca".
// Un buffer de proximidad no es un print: es un umbral que se cruza de refilon en el ruido de
// una sola vela y que cada bot afina por su cuenta.
//
// Este header es la unica definicion de que significa que un nivel REACCIONE, y es MECANICA:
// un straddle de DOS BARRAS CERRADAS. No hay sensacion, no hay "casi", no hay parametro por bot.
//
// LAS TRES COSAS QUE ESTE ARCHIVO BORRA
//   1. 30 definiciones distintas de "toque" que no coinciden entre si.
//   2. El "esta cerca" como gatillo: aqui una barra sin cerrar no produce NADA.
//   3. El `touch_idx` inventado: se incrementa solo tras una EXCURSION medida de alejamiento,
//      no cada vez que el precio roza el nivel dentro del mismo apreton.
//
// LA VOZ EMBARCA APAGADA. NO NEGOCIABLE.
// --------------------------------------
// Este header NO habla, NO notifica y NO incluye `fleet_notify.h` a proposito. Produce EVENTOS
// TIPADOS y nada mas. Una celda `(level_type x event x regimen x hora)` gana voz **solo** cuando
// `null_control` le da Wilson-LB >= tasa-de-nivel-aleatorio + 4pp con `n_eff >= 80`, y se
// recupera **de una en una**. Razon medida el 2026-07-25: **0 de 222 celdas** pasan BH-FDR hoy,
// y `cusum` tenia edge NEGATIVO con CI entero bajo cero (n=12.679) mientras seguia hablando.
// Un roster de niveles x 30 syms con voz seria una maquina de multiple testing, no una mejora.
//
// LA VARA QUE ESTE PRIMITIVO TIENE QUE SUPERAR (prior publicado, no inventado)
// Osler (2000) mide **60,8% vs 56,2%** de rebote en niveles frente a giro simple, con ~3,4pp
// atribuibles a numeros redondos. Asi que el listón es: **el nivel debe añadir >=6pp sobre el
// simple giro de vela**, o es decoracion y se borra. Ese test lo corre `null_control`, no este
// archivo — aqui solo se GENERAN los eventos que lo hacen medible.
//
// SEÑAL-SOLAMENTE: este header solo OBSERVA barras cerradas. No conecta, no ordena, no toca la
// red, no escribe en `trades.db` (ver nota de contencion en level_react.cpp).
#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace level_react {

// --------------------------------------------------------------------------------------
// Tipos
// --------------------------------------------------------------------------------------

struct Bar {
    double t = 0;   // epoch de CIERRE de la barra 1m
    double o = 0, h = 0, l = 0, c = 0, v = 0;
};

// El registro esta TOPADO DURO a 6 tipos por simbolo. `GAP_EDGE` y `KDE` no amplian el tope:
// solo pueden DESPLAZAR un slot de menor prioridad. Sin este tope, 30 syms x N niveles es un
// generador de alarmas y de p-values.
enum class LevelType : int {
    OI_CALL_WALL = 0,
    OI_PUT_WALL  = 1,
    ABS_WALL     = 2,
    FLIP_OPEN    = 3,
    POC_DOM      = 4,
    ROUND        = 5,
    GAP_EDGE     = 6,   // solo por desplazamiento
    KDE          = 7,   // solo por desplazamiento
};

inline const char* type_name(LevelType t) {
    switch (t) {
        case LevelType::OI_CALL_WALL: return "OI_CALL_WALL";
        case LevelType::OI_PUT_WALL:  return "OI_PUT_WALL";
        case LevelType::ABS_WALL:     return "ABS_WALL";
        case LevelType::FLIP_OPEN:    return "FLIP_OPEN";
        case LevelType::POC_DOM:      return "POC_DOM";
        case LevelType::ROUND:        return "ROUND";
        case LevelType::GAP_EDGE:     return "GAP_EDGE";
        case LevelType::KDE:          return "KDE";
    }
    return "?";
}

// Prioridad: numero MAS BAJO = mas prioritario. Es el orden de la ficha: los muros de OI son
// campos de fuerza medidos; un nivel KDE es una segunda opinion estadistica y cede siempre.
inline int priority(LevelType t) { return static_cast<int>(t); }

enum class Event : int {
    TOUCH,          // llego y respeto el lado — CONSOLIDACION, jamas una entrada
    BREAK,          // abrio a un lado y cerro al otro
    BOUNCE,         // TOUCH en t y NO BREAK en t+1  -> OPERABLE
    RETEST_REJECT,  // BREAK, vuelta desde el lado lejano sin re-ruptura -> OPERABLE
    WICK_REJECT,    // mecha a traves, cuerpo rechazado
};

inline const char* event_name(Event e) {
    switch (e) {
        case Event::TOUCH:         return "TOUCH";
        case Event::BREAK:         return "BREAK";
        case Event::BOUNCE:        return "BOUNCE";
        case Event::RETEST_REJECT: return "RETEST_REJECT";
        case Event::WICK_REJECT:   return "WICK_REJECT";
    }
    return "?";
}

// Los UNICOS dos eventos operables (ficha #8 + skill print-o-nada-levels).
// `TOUCH` es consolidacion y una primera `BREAK` sin retest es la trampa clasica.
inline bool is_tradeable(Event e) {
    return e == Event::BOUNCE || e == Event::RETEST_REJECT;
}

struct Level {
    LevelType type = LevelType::ROUND;
    double px = 0;
    bool is_round = false;
};

struct Emitted {
    double ts = 0;              // epoch de cierre de la barra que lo produjo
    LevelType level_type = LevelType::ROUND;
    double level_px = 0;
    Event event = Event::TOUCH;
    bool is_round = false;
    int touch_ord = 0;          // 1 = primer toque tras excursion
    double dist_atr = 0;        // (close - nivel) / ATR, con signo
    bool printed = false;       // straddle de 2 barras cerradas satisfecho
    bool tradeable = false;     // BOUNCE / RETEST_REJECT **y** printed
};

// --------------------------------------------------------------------------------------
// Registro topado
// --------------------------------------------------------------------------------------

inline constexpr size_t REGISTRY_MAX = 6;   // TOPE DURO. No se sube "solo esta vez".

class Registry {
  public:
    // Devuelve true si el nivel entro. Con el registro lleno, un nivel solo entra si es
    // ESTRICTAMENTE mas prioritario que el peor que hay dentro — y entonces lo DESPLAZA.
    bool add(const Level& L) {
        for (auto& e : v_)                        // mismo tipo: se actualiza el precio del dia
            if (e.type == L.type) { e = L; return true; }
        if (v_.size() < REGISTRY_MAX) { v_.push_back(L); return true; }
        size_t worst = 0;
        for (size_t i = 1; i < v_.size(); ++i)
            if (priority(v_[i].type) > priority(v_[worst].type)) worst = i;
        if (priority(L.type) < priority(v_[worst].type)) { v_[worst] = L; return true; }
        return false;                              // no desplaza a nadie: se descarta
    }
    const std::vector<Level>& levels() const { return v_; }
    size_t size() const { return v_.size(); }
    void clear() { v_.clear(); }

  private:
    std::vector<Level> v_;
};

// --------------------------------------------------------------------------------------
// El buffer: `s = max(0.15*ATR14_1m, medio-spread, 1 tick)`
// --------------------------------------------------------------------------------------
//
// Los tres terminos existen por una razon distinta y por eso es un `max`, no una eleccion:
//   0.15*ATR  -> ruido de la barra. Sin el, cada vela toca cada nivel.
//   medio-spread -> el nivel no se puede resolver mas fino que el propio libro. Un "toque"
//                   dentro del spread es una cotizacion, no una decision de nadie.
//   1 tick    -> suelo duro: un buffer 0 hace que `>=` y `>` decidan la señal.
inline double buffer(double atr14_1m, double half_spread, double tick) {
    double s = 0.15 * atr14_1m;
    if (half_spread > s) s = half_spread;
    if (tick > s) s = tick;
    return s;
}

// ATR14 de Wilder sobre barras 1m. Devuelve <0 si no hay muestra suficiente: **jamas 0.0**.
// Un ATR de 0 haria el buffer 0 y convertiria "no se" en "el nivel es exacto al centavo".
inline double atr14_wilder(const std::vector<Bar>& bars, int period = 14) {
    if ((int)bars.size() < period + 1) return -1.0;
    double sum = 0;
    for (int i = 1; i <= period; ++i) {
        const Bar& b = bars[(size_t)i];
        const double pc = bars[(size_t)i - 1].c;
        const double tr = std::max(b.h - b.l, std::max(std::fabs(b.h - pc), std::fabs(b.l - pc)));
        sum += tr;
    }
    double atr = sum / period;
    for (size_t i = (size_t)period + 1; i < bars.size(); ++i) {
        const Bar& b = bars[i];
        const double pc = bars[i - 1].c;
        const double tr = std::max(b.h - b.l, std::max(std::fabs(b.h - pc), std::fabs(b.l - pc)));
        atr = (atr * (period - 1) + tr) / period;
    }
    return atr;
}

// --------------------------------------------------------------------------------------
// La maquina de estados de UN nivel
// --------------------------------------------------------------------------------------

class Tracker {
  public:
    Tracker(Level L, double atr, double buf)
        : L_(L), atr_(atr), s_(buf) {}

    // Alimenta UNA barra CERRADA. Devuelve los eventos que esa barra produjo (puede ser 0, 1
    // o 2: p.ej. un BOUNCE del toque anterior mas un TOUCH nuevo).
    std::vector<Emitted> on_bar(const Bar& b) {
        std::vector<Emitted> out;
        ++idx_;

        const bool straddle = (b.h > L_.px && b.l < L_.px);
        const bool printed  = straddle && prev_straddle_;   // PRINT O NADA: dos barras cerradas

        const int s_open  = side(b.o);
        const int s_close = side(b.c);

        // --- excursion: habilita que el PROXIMO toque cuente como un toque nuevo -----------
        // Sin esto, un precio pegado al nivel produce `touch_ord` 1,2,3,4... dentro del mismo
        // apreton y el "3er toque = muro exhausto" se dispara en un solo minuto de chop.
        if (std::fabs(b.c - L_.px) >= 0.5 * atr_) excursed_ = true;

        // --- BOUNCE: TOUCH en t-1 y NO hay BREAK en t --------------------------------------
        const bool break_now = (s_open != 0 && s_close != 0 && s_open != s_close);
        if (pending_touch_ && !break_now) {
            out.push_back(make(b, Event::BOUNCE, printed));
            pending_touch_ = false;
        } else if (pending_touch_) {
            pending_touch_ = false;   // hubo ruptura: el toque no era un rebote
        }

        // --- RETEST_REJECT: BREAK previo, vuelta desde el lado LEJANO, sin re-ruptura -------
        if (break_pending_ && (idx_ - break_idx_) <= RETEST_BARS && (idx_ != break_idx_)) {
            const bool touched_band = (b.l <= L_.px + s_ && b.h >= L_.px - s_);
            if (break_now) {
                break_pending_ = false;                 // re-rompio: no hay rechazo
            } else if (touched_band && s_close == break_side_ * -1 && s_close != 0) {
                // volvio al lado de origen = la ruptura fue rechazada
                out.push_back(make(b, Event::RETEST_REJECT, printed));
                break_pending_ = false;
            }
        } else if (break_pending_ && (idx_ - break_idx_) > RETEST_BARS) {
            break_pending_ = false;                     // la ventana de retest expiro
        }

        // --- BREAK -------------------------------------------------------------------------
        if (break_now) {
            out.push_back(make(b, Event::BREAK, printed));
            break_pending_ = true;
            break_idx_ = idx_;
            break_side_ = s_close;
            last_side_ = s_close;
        }

        // --- TOUCH: llego a la banda y CERRO del lado del que venia -------------------------
        const bool in_band = (b.l <= L_.px + s_ && b.h >= L_.px - s_);
        if (!break_now && in_band && s_close != 0 && s_close == last_side_) {
            if (excursed_) { ++touch_ord_; excursed_ = false; }
            out.push_back(make(b, Event::TOUCH, printed));
            pending_touch_ = true;
        }

        // --- WICK_REJECT: mecha a traves, cuerpo rechazado ----------------------------------
        const double body = std::fabs(b.o - b.c);
        if (b.h > L_.px && b.c < L_.px && (b.h - b.c) > body)
            out.push_back(make(b, Event::WICK_REJECT, printed));
        else if (b.l < L_.px && b.c > L_.px && (b.c - b.l) > body)
            out.push_back(make(b, Event::WICK_REJECT, printed));

        if (s_close != 0) last_side_ = s_close;
        prev_straddle_ = straddle;
        return out;
    }

    int touch_ord() const { return touch_ord_; }

  private:
    static constexpr int RETEST_BARS = 5;

    // +1 por encima de la banda, -1 por debajo, 0 DENTRO de la banda (indeterminado).
    // Que "dentro" sea 0 y no un lado es deliberado: dentro del buffer nadie ha decidido nada.
    int side(double px) const {
        if (px > L_.px + s_) return 1;
        if (px < L_.px - s_) return -1;
        return 0;
    }

    Emitted make(const Bar& b, Event e, bool printed) const {
        Emitted em;
        em.ts = b.t;
        em.level_type = L_.type;
        em.level_px = L_.px;
        em.event = e;
        em.is_round = L_.is_round;
        em.touch_ord = touch_ord_;
        em.dist_atr = (atr_ > 0) ? (b.c - L_.px) / atr_ : 0.0;
        em.printed = printed;
        em.tradeable = is_tradeable(e) && printed;
        return em;
    }

    Level L_;
    double atr_ = 0, s_ = 0;
    int idx_ = -1;
    bool prev_straddle_ = false;
    bool pending_touch_ = false;
    bool break_pending_ = false;
    int break_idx_ = -1;
    int break_side_ = 0;
    int last_side_ = 0;
    int touch_ord_ = 0;
    bool excursed_ = true;   // el primer toque de la sesion cuenta
};

// --------------------------------------------------------------------------------------
// El motor: registro topado + un Tracker por nivel
// --------------------------------------------------------------------------------------

class Engine {
  public:
    Engine(const Registry& reg, double atr, double half_spread, double tick)
        : atr_(atr), s_(buffer(atr, half_spread, tick)) {
        for (const auto& L : reg.levels()) tr_.emplace_back(L, atr, s_);
    }

    std::vector<Emitted> on_bar(const Bar& b) {
        std::vector<Emitted> all;
        for (auto& t : tr_) {
            auto ev = t.on_bar(b);
            all.insert(all.end(), ev.begin(), ev.end());
        }
        return all;
    }

    double buf() const { return s_; }
    double atr() const { return atr_; }

  private:
    double atr_, s_;
    std::vector<Tracker> tr_;
};

}  // namespace level_react
