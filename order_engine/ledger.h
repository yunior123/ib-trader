// ledger.h — libro append-only JSONL del order_engine (dinero real).
// Cada evento del ciclo de vida de una orden se persiste UNA vez, en cuanto
// ocurre, y se flushea a disco: intent/ack/fill/cancel/reject/commission.
// El P&L NETO manda el broker: se casa execId -> commission (comisiones reales),
// NUNCA nuestro reloj (regla skill ibkr-tws). Header-only, sin dependencias.
#pragma once
#include <cstdio>
#include <ctime>
#include <fstream>
#include <mutex>
#include <string>
#include <sys/stat.h>
#include <unordered_map>

namespace oe {

// Escapa una cadena para incrustarla en JSON (comillas, backslash, control).
inline std::string json_escape(const std::string& s) {
    std::string o;
    o.reserve(s.size() + 8);
    for (char c : s) {
        switch (c) {
            case '"':  o += "\\\""; break;
            case '\\': o += "\\\\"; break;
            case '\n': o += "\\n";  break;
            case '\r': o += "\\r";  break;
            case '\t': o += "\\t";  break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof buf, "\\u%04x", c);
                    o += buf;
                } else {
                    o += c;
                }
        }
    }
    return o;
}

// Epoch ms (reloj local; SOLO para ordenar/auditar — el P&L usa commission).
inline long long now_ms() {
    struct timespec ts{};
    clock_gettime(CLOCK_REALTIME, &ts);
    return static_cast<long long>(ts.tv_sec) * 1000 + ts.tv_nsec / 1000000;
}

// Descripción compacta de un contrato de opción para el ledger.
struct LedgerContract {
    std::string symbol;
    std::string exp;      // YYYYMMDD
    double      strike = 0;
    std::string right;    // C | P
    std::string to_json() const {
        char buf[256];
        std::snprintf(buf, sizeof buf,
                      "{\"sym\":\"%s\",\"exp\":\"%s\",\"strike\":%.4g,\"right\":\"%s\"}",
                      json_escape(symbol).c_str(), json_escape(exp).c_str(),
                      strike, json_escape(right).c_str());
        return buf;
    }
};

class Ledger {
public:
    // path = order_engine/ledger/orders.jsonl (se crea el dir si falta).
    explicit Ledger(const std::string& path) : path_(path) {
        make_parent_dir(path);
        out_.open(path, std::ios::app);
    }

    bool ok() const { return out_.is_open(); }

    // --- eventos ---------------------------------------------------------
    // intent: lo que el motor VA a colocar (incluye el modo DRY/LIVE/PAPER).
    void intent(int orderId, const LedgerContract& c, char side, int qty,
                double limit, const std::string& orderRef, const std::string& mode) {
        char extra[512];
        std::snprintf(extra, sizeof extra,
                      "\"side\":\"%c\",\"qty\":%d,\"px\":%.4f,\"ref\":\"%s\",\"mode\":\"%s\"",
                      side, qty, limit, json_escape(orderRef).c_str(),
                      json_escape(mode).c_str());
        write("intent", orderId, "", &c, extra);
    }

    void ack(int orderId, const std::string& status) {
        std::string extra = "\"status\":\"" + json_escape(status) + "\"";
        write("ack", orderId, "", nullptr, extra.c_str());
    }

    // fill real: viene de execDetails (execId + precio + qty del broker).
    void fill(int orderId, const std::string& execId, const LedgerContract& c,
              double px, double qty, const std::string& tws_time) {
        char extra[512];
        std::snprintf(extra, sizeof extra,
                      "\"px\":%.4f,\"qty\":%.4f,\"tws_time\":\"%s\"",
                      px, qty, json_escape(tws_time).c_str());
        write("fill", orderId, execId, &c, extra);
        Fill f{orderId, px, qty, 0.0, false};
        fills_[execId] = f;
    }

    void cancel(int orderId, const std::string& orderRef) {
        std::string extra = "\"ref\":\"" + json_escape(orderRef) + "\"";
        write("cancel", orderId, "", nullptr, extra.c_str());
    }

    void reject(int orderId, int code, const std::string& msg) {
        char extra[512];
        std::snprintf(extra, sizeof extra, "\"code\":%d,\"msg\":\"%s\"",
                      code, json_escape(msg).c_str());
        write("reject", orderId, "", nullptr, extra);
    }

    // commission real por execId: cierra el P&L NETO de ese fill.
    void commission(const std::string& execId, double commission, double realizedPnl) {
        // IBKR manda UNSET_DOUBLE (~1.8e308) cuando no aplica (p.ej. trade de apertura
        // sin P&L realizado). Sanear para no corromper el ledger ni el acumulado.
        if (!(realizedPnl > -1e300 && realizedPnl < 1e300)) realizedPnl = 0.0;
        if (!(commission  > -1e300 && commission  < 1e300)) commission  = 0.0;
        char extra[256];
        std::snprintf(extra, sizeof extra,
                      "\"commission\":%.4f,\"realizedPnl\":%.4f",
                      commission, realizedPnl);
        write("commission", 0, execId, nullptr, extra);
        auto it = fills_.find(execId);
        if (it != fills_.end()) { it->second.commission = commission; it->second.has_comm = true; }
        realized_pnl_ += realizedPnl;
        total_commission_ += commission;
    }

    void note(const std::string& msg) {
        std::string extra = "\"msg\":\"" + json_escape(msg) + "\"";
        write("note", 0, "", nullptr, extra.c_str());
    }

    void flush() { std::lock_guard<std::mutex> g(mu_); if (out_.is_open()) out_.flush(); }

    // P&L NETO acumulado según el broker (realizedPnl - comisiones ya vienen
    // netas en realizedPNL de IBKR; exponemos ambos para auditoría).
    double net_realized_pnl() const { return realized_pnl_; }
    double total_commission() const { return total_commission_; }

private:
    struct Fill { int orderId; double px; double qty; double commission; bool has_comm; };

    static void make_parent_dir(const std::string& path) {
        auto pos = path.find_last_of('/');
        if (pos == std::string::npos) return;
        std::string dir = path.substr(0, pos);
        // mkdir -p superficial (un nivel; el caller crea order_engine/ledger).
        mkdir(dir.c_str(), 0755);
    }

    void write(const char* ev, int orderId, const std::string& execId,
               const LedgerContract* c, const char* extra) {
        std::lock_guard<std::mutex> g(mu_);
        if (!out_.is_open()) return;
        out_ << "{\"ts\":" << now_ms()
             << ",\"ev\":\"" << ev << "\""
             << ",\"orderId\":" << orderId;
        if (!execId.empty()) out_ << ",\"execId\":\"" << json_escape(execId) << "\"";
        if (c) out_ << ",\"contract\":" << c->to_json();
        if (extra && *extra) out_ << ',' << extra;
        out_ << "}\n";
        out_.flush();  // dinero real: nunca dejar un evento sólo en buffer.
    }

    std::string path_;
    std::ofstream out_;
    std::mutex mu_;
    std::unordered_map<std::string, Fill> fills_;
    double realized_pnl_ = 0.0;
    double total_commission_ = 0.0;
};

} // namespace oe
