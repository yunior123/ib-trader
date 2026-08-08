#pragma once

// Pure C++ options-alert selector. It reads the existing realtime IBKR chain cache and
// produces signal-only contract alerts; it never connects to a broker or places orders.

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <vector>

namespace options_alert {

inline std::string normalize_symbol(std::string symbol) {
    if (symbol.empty() || symbol.size() > 12) return {};
    std::transform(symbol.begin(), symbol.end(), symbol.begin(),
                   [](unsigned char c){ return std::toupper(c); });
    if (!std::isalnum(static_cast<unsigned char>(symbol.front())) ||
        !std::isalnum(static_cast<unsigned char>(symbol.back()))) return {};
    for (unsigned char c : symbol)
        if (!std::isalnum(c) && c != '.' && c != '-') return {};
    return symbol;
}

struct Row {
    double strike = 0, bid = -1, ask = -1, volume = 0, oi = 0, iv = -1, delta = -1;
    char right = '?';
    std::string expiry;
};

struct Chain {
    long long epoch = 0;
    double spot = 0;
    std::vector<Row> rows;
};

struct Config {
    int target_dte = 5;
    long long now = std::time(nullptr);
    long long max_age_s = 900;
    double max_spread_pct = 5.0;
    double min_oi = 500;
    double max_premium = 200;
    double min_abs_delta = 0.40;
    double max_abs_delta = 0.70;
    double target_abs_delta = 0.55;
};

struct Pick {
    bool ok = false;
    Row row;
    int dte = -1;
    double spread_pct = -1;
    double premium = 0;
    std::string why;
};

inline Chain load_chain(const std::string& path) {
    Chain ch;
    std::ifstream f(path);
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        if (line[0] == '#') {
            auto ep = line.find("epoch ");
            if (ep != std::string::npos) ch.epoch = std::atoll(line.c_str() + ep + 6);
            auto sp = line.find("spot ");
            if (sp != std::string::npos) ch.spot = std::atof(line.c_str() + sp + 5);
            continue;
        }
        std::istringstream ss(line);
        Row r;
        std::string right;
        double gamma = -1;
        if (ss >> r.strike >> right >> r.expiry >> r.bid >> r.ask >> r.volume >> r.oi
               >> r.iv >> r.delta >> gamma) {
            r.right = right.empty() ? '?' : right[0];
            ch.rows.push_back(r);
        }
    }
    return ch;
}

inline int expiry_dte(const std::string& exp, long long now) {
    if (exp.size() != 8) return -1;
    const std::time_t now_t = static_cast<std::time_t>(now);
    std::tm today = *std::localtime(&now_t);
    today.tm_hour = 12; today.tm_min = 0; today.tm_sec = 0; today.tm_isdst = -1;
    std::tm end = {};
    end.tm_year = std::atoi(exp.substr(0, 4).c_str()) - 1900;
    end.tm_mon = std::atoi(exp.substr(4, 2).c_str()) - 1;
    end.tm_mday = std::atoi(exp.substr(6, 2).c_str());
    end.tm_hour = 12; end.tm_isdst = -1;
    const double seconds = std::difftime(std::mktime(&end), std::mktime(&today));
    return static_cast<int>(std::llround(seconds / 86400.0));
}

inline Pick select(const Chain& ch, char right, const Config& cfg) {
    Pick out;
    if (ch.rows.empty()) { out.why = "sin cache de cadena"; return out; }
    const long long age = cfg.now - ch.epoch;
    if (age < -5 || age > cfg.max_age_s) {
        out.why = age < -5 ? "timestamp de cadena en el futuro"
                           : "cadena vieja " + std::to_string(age) + "s";
        return out;
    }

    std::vector<std::string> expiries;
    for (const auto& r : ch.rows) {
        if (r.right == right && expiry_dte(r.expiry, cfg.now) >= 0 &&
            std::find(expiries.begin(), expiries.end(), r.expiry) == expiries.end())
            expiries.push_back(r.expiry);
    }
    if (expiries.empty()) { out.why = "sin vencimiento vigente"; return out; }
    std::sort(expiries.begin(), expiries.end(), [&](const auto& a, const auto& b) {
        const int da = expiry_dte(a, cfg.now), db = expiry_dte(b, cfg.now);
        const int aa = std::abs(da - cfg.target_dte), ab = std::abs(db - cfg.target_dte);
        return aa != ab ? aa < ab : da > db; // empate: más tiempo, no menos
    });
    const std::string expiry = expiries.front();
    const int dte = expiry_dte(expiry, cfg.now);

    const Row* best = nullptr;
    double best_score = 1e18, best_spread = -1, best_premium = 0;
    int quote_ok = 0, delta_ok = 0, liquid_ok = 0, budget_ok = 0;
    for (const auto& r : ch.rows) {
        if (r.right != right || r.expiry != expiry) continue;
        if (!(r.bid > 0 && r.ask > 0 && r.ask >= r.bid)) continue;
        quote_ok++;
        const double ad = std::fabs(r.delta);
        if (!(r.iv > 0 && ad >= cfg.min_abs_delta && ad <= cfg.max_abs_delta)) continue;
        delta_ok++;
        const double mid = (r.bid + r.ask) / 2.0;
        const double spread = 100.0 * (r.ask - r.bid) / mid;
        if (spread > cfg.max_spread_pct || !(r.oi > cfg.min_oi)) continue;
        liquid_ok++;
        const double premium = r.ask * 100.0;
        if (!(premium > 0 && premium <= cfg.max_premium)) continue;
        budget_ok++;
        const double score = std::fabs(ad - cfg.target_abs_delta) * 1000.0 + spread
                           - std::min(r.oi, 10000.0) / 100000.0;
        if (score < best_score) {
            best = &r; best_score = score; best_spread = spread; best_premium = premium;
        }
    }
    if (!best) {
        std::ostringstream why;
        why << "sin contrato APTO " << dte << "-DTE (quotes " << quote_ok
            << ", delta " << delta_ok << ", liquidez " << liquid_ok
            << ", <=$" << std::fixed << std::setprecision(0) << cfg.max_premium
            << " " << budget_ok << ")";
        out.why = why.str();
        return out;
    }
    out.ok = true; out.row = *best; out.dte = dte;
    out.spread_pct = best_spread; out.premium = best_premium;
    return out;
}

inline std::string fmt_strike(double strike) {
    std::ostringstream s;
    if (std::fabs(strike - std::round(strike)) < 1e-9) s << static_cast<long long>(std::llround(strike));
    else s << std::fixed << std::setprecision(2) << strike;
    std::string v = s.str();
    while (v.find('.') != std::string::npos && !v.empty() && v.back() == '0') v.pop_back();
    if (!v.empty() && v.back() == '.') v.pop_back();
    return v;
}

inline std::string format(const std::string& symbol, char right, const Pick& p) {
    std::string sym = symbol;
    std::transform(sym.begin(), sym.end(), sym.begin(), [](unsigned char c){ return std::tolower(c); });
    return sym + (right == 'C' ? " call " : " put ") + fmt_strike(p.row.strike)
         + " " + std::to_string(p.dte) + "-DTE";
}

} // namespace options_alert
