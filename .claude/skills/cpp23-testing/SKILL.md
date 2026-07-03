---
name: cpp23-testing
description: Testing C++23 para componentes financieros de la flota — harness assert-based sin frameworks, macros EXPECT con registry, builds ASan/UBSan obligatorios, replay determinista con reloj virtual, property tests con semilla reproducible, tabla de edge cases de dinero. Usar al escribir o revisar tests de cualquier C++ del repo (scalper, bots, herramientas).
---

# Testing C++23 — flota ib-trader

## Principios
1. **Sin frameworks pesados** (no gtest/catch2): un harness header-only propio compila en <2s y corre bajo ASan sin fricción. Patrón ya probado en `tests/cpp/math_test.cpp`.
2. **Determinismo total**: cero sleeps, cero wall-clock, cero rand() sin semilla. El tiempo es una interfaz (`Clock`) y en tests se avanza a mano.
3. **Doble build SIEMPRE**: release (`-std=c++23 -O3 -march=native -Wall -Wextra`) y sanitizado (`-std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer`). Un test que solo pasa en release está roto. Un compile a la vez (Mac 8GB).
4. **La lógica pura vive en headers testeables**: FSM, dinero, parsing = funciones puras en `*.h` incluibles por el test sin linkear el binario entero.

## Harness (patrón canónico)
```cpp
// test_harness.h — registry + macros, ~40 líneas
#include <cstdio>
#include <functional>
#include <vector>
inline std::vector<std::pair<const char*, std::function<void()>>>& tests()
{ static std::vector<std::pair<const char*, std::function<void()>>> v; return v; }
inline int g_fail = 0;
#define TEST(name) static void name(); \
  static const bool name##_reg = (tests().push_back({#name, name}), true); \
  static void name()
#define EXPECT(cond) do { if (!(cond)) { ++g_fail; \
  std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); } } while (0)
#define EXPECT_EQ(a,b) do { auto va=(a); auto vb=(b); if (!(va==vb)) { ++g_fail; \
  std::printf("FAIL %s:%d  %s == %s  (%lld vs %lld)\n", __FILE__, __LINE__, #a, #b, \
  (long long)va, (long long)vb); } } while (0)
inline int run_all() { for (auto& [n, f] : tests()) f();
  std::printf(g_fail ? "\n%d FAILURES\n" : "\nALL OK (%zu tests)\n", g_fail ? g_fail : (int)tests().size());
  return g_fail ? 1 : 0; }
```
`int main() { return run_all(); }` — y el run.sh compila+ejecuta ambos builds:
```bash
set -e
clang++ -std=c++23 -O3 -march=native -Wall -Wextra -o /tmp/t_rel core_test.cpp && /tmp/t_rel
clang++ -std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -o /tmp/t_asan core_test.cpp && /tmp/t_asan
```

## Reloj virtual (para FSM con timeouts)
```cpp
struct Clock { virtual int64_t mono_ns() = 0; virtual int64_t wall_s() = 0; virtual ~Clock() = default; };
struct SimClock : Clock {
  int64_t m = 0, w = 0;
  int64_t mono_ns() override { return m; }
  int64_t wall_s()  override { return w; }
  void advance_ms(int64_t ms) { m += ms * 1'000'000; w += ms / 1000; }
};
```
Testear BORDES de timeout: t = límite−1ms (no dispara) y t = límite (dispara). Nunca "por ahí".

## Property tests ligeros (semilla reproducible)
```cpp
TEST(money_roundtrip_prop) {
  std::mt19937_64 rng(0xC0FFEE);          // semilla FIJA: fallo → reproducible siempre
  for (int i = 0; i < 100'000; ++i) {
    int64_t px = (int64_t)(rng() % 100'000);   // cents
    EXPECT(net_exit_c(px) + COMMISSION_SIDE_C == px * 100);   // invariante, no ejemplo
  }
}
```
Invariantes financieros a cazar: conmutatividad de redondeo NO asumida, mul-antes-de-div, sin overflow con precios extremos, P&L(compra,venta) == −P&L(venta,compra).

## Tabla de edge cases de dinero/mercado (checklist mínima por componente)
- Precio 0, precio negativo (bid −1.00 del chain IBKR = "sin bid"), precio gigante (overflow int32 → usar int64).
- Spread invertido (bid > ask), spread 0, NBBO congelado (mismo epoch repetido).
- Fill parcial (si qty>1), fill a mejor y peor precio que el limit.
- Comisión que convierte ganador bruto en perdedor neto (el caso que dispara kill switch).
- Timestamps: cambio de día en medio de sesión, DST, epoch en ms vs s confundidos.
- Parsing: línea truncada a mitad de write, UTF-8 multibyte (🐋 = 4 bytes), campo faltante, JSON malformado, archivo vacío, archivo inexistente.

## Replay determinista (integración)
Escenarios como JSONL de eventos con timestamps virtuales (`{"t_ms":0,"ev":"alert",...}`, `{"t_ms":2500,"ev":"nbbo","bid":...}`); el runner avanza SimClock al t de cada evento y verifica el estado/ledger esperado al final. Miles de escenarios/segundo, cero flakiness. Guardar cada bug real cazado como escenario nuevo (regresión permanente).

## Qué NO hacer
- Tests que leen la hora real, la red, o `data/` vivo del repo (usar fixtures copiadas a /tmp).
- Tolerancias flotantes en dinero: el dinero es entero (cents); si hay epsilon, el diseño está mal.
- "Pasó una vez" = pasó: correr property tests con ≥3 semillas distintas fijas antes de declarar verde.
