---
name: ibkr-tws
description: Experto en conectar a IBKR TWS y colocar/gestionar órdenes — API C++ oficial (EClient/EWrapper, build macOS con Intel Decimal lib) como camino principal del scalper, ib_async Python como referencia secundaria. Usar al implementar TwsAdapter, el sidecar, o cualquier código que hable con TWS.
---

# IBKR TWS — conexión y órdenes (C++ primero)

## Reglas de la casa (NUNCA romper)
- La flota es SEÑAL-SOLAMENTE (ley 2026-07-16). El ÚNICO módulo autorizado a ordenar es `scalper/` con doble llave: flag `--arm-live` + archivo `scalper/ARM_LIVE` conteniendo la fecha de hoy. Sin ambas → SIM.
- Paper SIEMPRE primero: puerto **7497** (paper DUR197573) antes que **7496** (live TFSA U26942420).
- clientIds ya ocupados: 48 (opt_chain_cache), 82 (opt_whale_watch), 83/84 (bar bridge), 87 (walls/cancel). **El scalper usa 90.** Jamás reusar un id vivo: TWS mata la conexión vieja.
- Toda conexión que no ordene: `readonly=True` (Python) / no llamar placeOrder (C++).

## Camino C++ (API oficial vendoreada)

### Obtener y vendorear
1. Descargar TWS API estable de https://interactivebrokers.github.io (aceptar licencia). Versión ≥10.30.
2. Vendorear en `scalper/vendor/IBJts/` (solo `source/cppclient/client/` + `Intel_lib_build.txt`). No commitear binarios.

### Build macOS (una vez) — el peaje es la Intel Decimal FP lib
La API usa `Decimal` (IEEE 754-2008) para precios/cantidades → depende de IntelRDFPMathLib (agnóstica de arquitectura, funciona en Apple Silicon).
```bash
# 1. Intel lib: https://www.intel.com/content/www/us/en/developer/articles/tool/intel-decimal-floating-point-math-library.html
tar xvzf IntelRDFPMathLib20U2.tar.gz && cd IntelRDFPMathLib20U2/LIBRARY
# makefile: L370 BID_LIB=$(LIB_DIR)/libbid.dylib ; L377 "gcc -o $@ $^ -shared" ; L112 añadir -fPIC -Wno-implicit-function-declaration
make CC=gcc CALL_BY_REF=0 GLOBAL_RND=0 GLOBAL_FLAGS=0 UNCHANGED_BINARY_FLAGS=0   # -> libbid.dylib
# 2. Cliente TWS (en IBJts/source/cppclient/client): compilar todos los .cpp como lib
clang++ -std=c++17 -O2 -pthread -Wall -Wno-switch -Wno-unused-function -shared -fPIC -I. *.cpp -Llib -lbid -o libTwsSocketClient.dylib
# La engine linkea: -Lscalper/vendor/lib -lTwsSocketClient -lbid (+ DYLD_LIBRARY_PATH o rpath)
```
OJO: versiones nuevas añaden dependencia protobuf — si el build pide protobuf, `brew install protobuf` y añadir `-I$(brew --prefix protobuf)/include -L... -lprotobuf`. El cliente TWS se compila c++17 (su código no es c++23-limpio); la engine sí va en c++23 y linkea contra la lib.

### Patrón EWrapper/EClient (arquitectura obligada)
```cpp
class TwsAdapter : public EWrapper {          // callbacks de TWS (≈100 virtuales; stub los no usados)
  EReaderOSSignal m_signal{2000};             // timeout ms
  std::unique_ptr<EClientSocket> m_client;    // comandos HACIA TWS
  std::unique_ptr<EReader> m_reader;          // hilo lector
public:
  TwsAdapter() : m_client(new EClientSocket(this, &m_signal)) {}
  bool connect(const char* host, int port, int clientId) {
    if (!m_client->eConnect(host, port, clientId)) return false;
    m_reader = std::make_unique<EReader>(m_client.get(), &m_signal);
    m_reader->start();                        // hilo que encola mensajes
    return true;
  }
  void pump() {                               // llamar en el loop propio (o hilo dedicado):
    m_signal.waitForSignal();                 // bloquea hasta timeout o mensaje
    m_reader->processMsgs();                  // dispara los callbacks EWrapper EN ESTE hilo
  }
};
```
Secuencia de arranque: `eConnect` → TWS manda `nextValidId(orderId)` (callback) → **ese** es el primer orderId usable; incrementar localmente por orden. Sin nextValidId no se ordena.

### Colocar/gestionar órdenes
```cpp
Contract c; c.symbol="QQQ"; c.secType="OPT"; c.exchange="SMART"; c.currency="USD";
c.lastTradeDateOrContractMonth="20260722"; c.strike=708; c.right="P"; c.multiplier="100";
Order o; o.action="BUY"; o.orderType="LMT"; o.totalQuantity=DecimalFunctions::stringToDecimal("1");
o.lmtPrice=0.57; o.tif="DAY"; o.transmit=true; o.outsideRth=false;
m_client->placeOrder(orderId, c, o);
m_client->cancelOrder(orderId, OrderCancel());          // cancelar
// modificar = placeOrder MISMO id con el campo cambiado (cancel/replace nativo)
```
Callbacks que importan (implementar de verdad):
- `orderStatus(id, status, filled, remaining, avgFillPrice, ...)` — status: PreSubmitted→Submitted→Filled | Cancelled | Inactive. `Filled` + remaining 0 = lleno.
- `execDetails(reqId, contract, execution)` — precio/hora reales de cada fill (execution.price, .time, .execId).
- `commissionReport(cr)` — comisión real por execId (`cr.commission`). Casar execId→orden para el P&L neto EXACTO.
- `error(id, time, code, msg, json)` — ver tabla abajo.
- `connectionClosed()` — TWS se fue: cancelar estado local, bloquear entradas, reconectar con backoff.

### Códigos de error clave
| Code | Significado | Acción |
|---|---|---|
| 201 | Orden rechazada (margen/permiso) | ledger REJECT, no reintentar ciego |
| 202 | Orden cancelada (confirmación de nuestro cancel) | normal |
| 103 | orderId duplicado | resincronizar con reqIds(-1) |
| 10147/10148 | orderId a cancelar no existe / ya cancelada | tratar como cancelada |
| 354 | Sin suscripción market data | usar NBBO de archivos de la flota |
| 1100/1102 | Conectividad TWS↔IB perdida/restaurada | congelar entradas hasta 1102 |
| 502 | No conecta (API off o puerto mal) | verificar TWS config API |
- Pacing: máx **50 msg/s** por conexión; violación = desconexión. El scalper (1 orden + reprices) jamás se acerca — no meter polling de market data por esta conexión.
- Reloj: timestamps de TWS son del servidor IB; el P&L manda el `execDetails`/`commissionReport`, no nuestro reloj.

## Camino Python (referencia/verificación rápida)
`pip install ib_async` (fork mantenido de ib_insync, drop-in, sin ibapi):
```python
from ib_async import IB, Option, LimitOrder
ib = IB(); ib.connect('127.0.0.1', 7497, clientId=91, readonly=False)  # paper
c = Option('QQQ', '20260722', 708, 'P', 'SMART', tradingClass='QQQ')
ib.qualifyContracts(c)
tr = ib.placeOrder(c, LimitOrder('BUY', 1, 0.57))
ib.sleep(2); print(tr.orderStatus.status, tr.fills)      # commissionReport en fill.commissionReport
ib.cancelOrder(tr.order)
```
Usar para: verificar contratos/permisos en paper, inspeccionar respuestas de TWS, probar escenarios antes de codificarlos en C++. NO para el camino caliente del scalper.

## Fuentes
- https://interactivebrokers.github.io/tws-api/ (docs oficiales: client_wrapper, order_submission, order_management)
- https://dlewis.io/ibkr-cpp-api/ (receta build macOS + Intel lib)
- https://github.com/ib-api-reloaded/ib_async (Python mantenido)
