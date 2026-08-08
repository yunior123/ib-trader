// C++ options alert engine: fleet BUY/SELL -> one liquid contract alert.
// SIGNAL-ONLY: reads files and appends text; no broker/order API exists in this binary.
#include "options_alert_engine_core.h"

#include <chrono>
#include <filesystem>
#include <iostream>
#include <map>
#include <regex>
#include <set>
#include <thread>

namespace fs = std::filesystem;
using namespace options_alert;

static std::string lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c){ return std::tolower(c); });
    return s;
}
static std::string upper(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c){ return std::toupper(c); });
    return s;
}
static std::string hhmmss() {
    std::time_t t = std::time(nullptr); char b[16];
    std::strftime(b, sizeof b, "%H:%M:%S", std::localtime(&t)); return b;
}
static std::string ymd() {
    std::time_t t = std::time(nullptr); char b[16];
    std::strftime(b, sizeof b, "%Y-%m-%d", std::localtime(&t)); return b;
}
static void append_line(const std::string& path, const std::string& line) {
    std::ofstream f(path, std::ios::app);
    if (!f) throw std::runtime_error("no se puede escribir " + path);
    f << line << '\n';
}
static void register_custom(const std::string& sym) {
    const std::string path = "data/options_alert_tickers.txt";
    std::ifstream f(path); std::string x;
    while (f >> x) if (upper(x) == upper(sym)) return;
    append_line(path, upper(sym));
}

static int produce(const std::string& raw_sym, char right, Config cfg, bool emit,
                   std::string* alert_out = nullptr, bool quiet = false) {
    const std::string sym = normalize_symbol(raw_sym);
    if (sym.empty()) {
        if (!quiet) std::cerr << raw_sym << ": ticker inválido\n";
        return 2;
    }
    const std::string path = "data/opt_chain_" + lower(sym) + ".txt";
    if (!fs::exists(path)) {
        register_custom(sym);
        if (!quiet)
            std::cerr << sym << ": sin cache; registrado en data/options_alert_tickers.txt "
                      << "para el adaptador de cadena\n";
        return 3;
    }
    const Pick p = select(load_chain(path), right, cfg);
    if (!p.ok) {
        if (!quiet) {
            append_line("logs/options_alert_engine.log", hhmmss() + " RECHAZADA " + sym + " " + p.why);
            std::cerr << sym << ": " << p.why << '\n';
        }
        return 1;
    }
    const std::string alert = format(sym, right, p);
    if (alert_out) *alert_out = alert;
    std::cout << alert << '\n';
    append_line("logs/options_alert_engine.log", hhmmss() + " APTA " + alert);
    if (emit) append_line("data/notify_push.txt", hhmmss() + " | OPTIONS ALERT | " + alert);
    return 0;
}

static int declared_probability(const std::string& line) {
    static const std::regex re(R"(prob(?:abilidad)?\s+([0-9]{2,3})\s*(?:%|por ciento))",
                               std::regex::icase);
    std::smatch m;
    return std::regex_search(line, m, re) ? std::clamp(std::atoi(m[1].str().c_str()), 0, 100) : 0;
}

static bool parse_signal(const std::string& line, std::string& sym, char& right, int& probability) {
    static const std::regex re(
        R"(^\d\d:\d\d:\d\d \| ([A-Z0-9][A-Z0-9.-]{0,11}): (BUY|SELL) \|)");
    std::smatch m;
    if (!std::regex_search(line, m, re)) return false;
    sym = normalize_symbol(m[1].str());
    if (sym.empty()) return false;
    right = m[2].str() == "BUY" ? 'C' : 'P';
    probability = declared_probability(line); return true;
}

struct Candidate { std::string key, alert; int probability=0; long long ts=0; };
struct Pending { std::string sym; char right='?'; int probability=0; long long first=0, next=0; };

static void write_daily_top(const std::string& day, std::vector<Candidate> candidates, int top_n) {
    fs::create_directories("data/options-alerts");
    std::stable_sort(candidates.begin(), candidates.end(), [](const auto& a, const auto& b) {
        return a.probability != b.probability ? a.probability > b.probability : a.ts < b.ts;
    });
    std::set<std::string> seen; std::vector<Candidate> unique;
    for (const auto& c : candidates) if (seen.insert(c.key).second) unique.push_back(c);
    if ((int)unique.size() > top_n) unique.resize(top_n);
    const std::string path = "data/options-alerts/" + day + ".txt", tmp = path + ".tmp";
    std::ofstream f(tmp);
    for (const auto& c : unique) f << c.alert << '\n';
    f.close(); fs::rename(tmp, path);
}

static int daemon(Config cfg, bool auto_emit, int min_prob, int top_n, int retry_s) {
    std::map<std::string, long long> last;
    std::map<std::string, Pending> pending;
    std::vector<Candidate> candidates;
    int sent_today = 0;
    std::string current, line;
    std::uintmax_t offset = 0;
    while (true) {
        const std::string path = "data/trading-signals/" + ymd() + ".txt";
        if (path != current) {
            current = path; candidates.clear(); sent_today = 0;
            pending.clear();
            std::error_code ec;
            offset = fs::exists(path, ec) ? fs::file_size(path, ec) : 0;
        }
        auto accept = [&](const std::string& sym, char right, int probability,
                          long long now, const std::string& alert) {
            const std::string key = sym + right;
            last[key] = now;
            candidates.push_back({key, alert, probability, now});
            write_daily_top(ymd(), candidates, top_n);
            append_line("logs/options_alert_engine.log", hhmmss() + " TOP-CANDIDATE p="
                        + std::to_string(probability) + " " + alert);
            if (auto_emit && sent_today < top_n) {
                append_line("data/notify_push.txt", hhmmss() + " | OPTIONS ALERT | " + alert);
                sent_today++;
                append_line("logs/options_alert_engine.log", hhmmss() + " AUTO-SENT "
                            + std::to_string(sent_today) + "/" + std::to_string(top_n)
                            + " " + alert);
            }
        };
        std::ifstream input(path, std::ios::binary);
        std::string chunk;
        if (input) {
            input.seekg(static_cast<std::streamoff>(offset));
            chunk.assign(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
        }
        const std::uintmax_t base_offset = offset;
        std::size_t begin = 0, newline = 0;
        while ((newline = chunk.find('\n', begin)) != std::string::npos) {
            line = chunk.substr(begin, newline - begin);
            offset = base_offset + newline + 1;  // incomplete trailing lines remain pending.
            begin = newline + 1;
            std::string sym; char right; int probability=0;
            if (!parse_signal(line, sym, right, probability) || probability < min_prob) continue;
            const long long now = std::time(nullptr);
            const std::string key = sym + right;
            if (now - last[key] < 1800 || pending.count(key)) continue;
            register_custom(sym);  // dynamic discovery: ask the active provider for this chain.
            cfg.now = now;
            std::string alert;
            if (produce(sym, right, cfg, false, &alert) == 0) accept(sym, right, probability, now, alert);
            else pending[key] = {sym, right, probability, now, now + retry_s};
        }
        const long long now = std::time(nullptr);
        for (auto it = pending.begin(); it != pending.end(); ) {
            auto& p = it->second;
            if (now - p.first > 20 * 60) {
                append_line("logs/options_alert_engine.log", hhmmss() + " PENDING-EXPIRED "
                            + p.sym + p.right);
                it = pending.erase(it);
            } else if (now < p.next) {
                ++it;
            } else {
                cfg.now = now;
                std::string alert;
                if (produce(p.sym, p.right, cfg, false, &alert, true) == 0) {
                    accept(p.sym, p.right, p.probability, now, alert);
                    it = pending.erase(it);
                } else {
                    p.next = now + retry_s;
                    ++it;
                }
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
    }
}

int main(int argc, char** argv) {
    Config cfg;
    if (const char* v = std::getenv("OPTIONS_ALERT_DTE")) cfg.target_dte = std::atoi(v);
    if (const char* v = std::getenv("OPTIONS_ALERT_BUDGET")) cfg.max_premium = std::atof(v);
    bool emit = false, run_daemon = false;
    bool auto_emit = std::getenv("OPTIONS_ALERT_AUTO") && std::string(std::getenv("OPTIONS_ALERT_AUTO")) == "1";
    int min_prob = std::getenv("OPTIONS_ALERT_MIN_PROB") ? std::atoi(std::getenv("OPTIONS_ALERT_MIN_PROB")) : 55;
    int top_n = std::getenv("OPTIONS_ALERT_TOP_N") ? std::atoi(std::getenv("OPTIONS_ALERT_TOP_N")) : 3;
    int retry_s = std::getenv("OPTIONS_ALERT_RETRY_S") ? std::atoi(std::getenv("OPTIONS_ALERT_RETRY_S")) : 30;
    std::vector<std::string> pos;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--daemon") run_daemon = true;
        else if (a == "--emit") emit = true;
        else if (a == "--dte" && i + 1 < argc) cfg.target_dte = std::atoi(argv[++i]);
        else if (a == "--budget" && i + 1 < argc) cfg.max_premium = std::atof(argv[++i]);
        else pos.push_back(a);
    }
    if (run_daemon) return daemon(cfg, auto_emit, min_prob, std::max(1, top_n), std::max(1, retry_s));
    if (pos.size() < 2) {
        std::cerr << "uso: options_alert_engine --daemon | SYM CALL|PUT|BUY|SELL [--dte N] [--emit]\n";
        return 2;
    }
    const std::string side = upper(pos[1]);
    if (side != "CALL" && side != "PUT" && side != "BUY" && side != "SELL") return 2;
    return produce(pos[0], (side == "CALL" || side == "BUY") ? 'C' : 'P', cfg, emit);
}
