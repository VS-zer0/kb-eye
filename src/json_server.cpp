#include "../include/json_server.h"
#include <iostream>
#include <sstream>
#include <algorithm>
#include <cstring>
 
#ifdef _WIN32
  #pragma comment(lib, "Ws2_32.lib")
  #define CLOSE_SOCK(s) closesocket(s)
#else
  #define CLOSE_SOCK(s) ::close(s)
#endif
 
namespace tmk {
 
// ─── Транспортные вспомогательные функции ────────────────────────────────
 
static std::string recv_line(socket_t sock) {
    std::string line; char ch = 0;
    while (true) {
        int n = recv(sock, &ch, 1, 0);
        if (n <= 0) return {};
        if (ch == '\n') break;
        line += ch;
    }
    return line;
}
 
static bool send_all(socket_t sock, const std::string& msg) {
    const char* ptr = msg.c_str(); size_t left = msg.size();
    while (left > 0) {
        int sent = send(sock, ptr, static_cast<int>(left), 0);
        if (sent <= 0) return false;
        ptr += sent; left -= sent;
    }
    return true;
}
 
// ─── Сборка исходящих JSON-сообщений ─────────────────────────────────────
 
std::string JsonServer::event_to_json(const GameEvent& e) {
    static const char* names[] = {
        "key_hit","key_miss","key_hint","modifier_cue",
        "word_complete","word_fail","exercise_complete",
        "wpm_update","accuracy_update","over_budget","speed_fail",
        "difficulty_change","gaze_off_screen","gaze_restored",
        "xp_gained","exercise_unlocked"
    };
    int idx = static_cast<int>(e.type);
    std::string t = (idx >= 0 && idx < 16) ? names[idx] : "unknown";
    return "{\"type\":\"game_event\",\"event\":\"" + t
         + "\",\"data\":" + e.payload_json + "}\n";
}
 
std::string JsonServer::state_to_json(const ResourceState& s) {
    std::ostringstream ss;
    ss << "{\"type\":\"state_update\""
       << ",\"wpm\":"          << s.wpm
       << ",\"accuracy\":"     << s.accuracy
       << ",\"xp\":"           << s.xp
       << ",\"skill_level\":"  << s.skill_level
       << ",\"difficulty\":"   << s.difficulty
       << ",\"gaze_on_screen\":" << (s.gaze_on_screen ? "true":"false")
       << ",\"gaze_x\":"       << s.gaze_x
       << ",\"gaze_y\":"       << s.gaze_y
       << ",\"gaze_conf\":"    << s.gaze_conf
       << "}\n";
    return ss.str();
}
 
// ─── Конструктор / деструктор ─────────────────────────────────────────────
 
JsonServer::JsonServer(Tmk& engine, uint16_t port)
    : engine_(engine), port_(port) {
#ifdef _WIN32
    WSADATA wsa; WSAStartup(MAKEWORD(2,2), &wsa);
#endif
    engine_.set_on_event([this](const GameEvent& e){
        broadcast(event_to_json(e)); });
    engine_.set_on_state_update([this](const ResourceState& s){
        broadcast(state_to_json(s)); });
}
 
JsonServer::~JsonServer() { stop(); }
 
bool JsonServer::start() {
    listen_sock_ = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_sock_ == INVALID_SOCKET) return false;
    int opt = 1;
    setsockopt(listen_sock_, SOL_SOCKET, SO_REUSEADDR,
               reinterpret_cast<const char*>(&opt), sizeof(opt));
    sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(port_);
    if (bind(listen_sock_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0
        || listen(listen_sock_, 8) != 0) return false;
    running_ = true;
    accept_thread_ = std::thread(&JsonServer::accept_loop, this);
    recv_thread_   = std::thread(&JsonServer::recv_loop,   this);
    std::cout << "[TMK] JSON server on port " << port_ << "\n";
    return true;
}
 
void JsonServer::stop() {
    running_ = false;
    if (listen_sock_ != INVALID_SOCKET) { CLOSE_SOCK(listen_sock_); listen_sock_ = INVALID_SOCKET; }
    { std::lock_guard<std::mutex> lk(clients_mtx_);
      for (auto& c : clients_) CLOSE_SOCK(c.sock); clients_.clear(); }
    if (accept_thread_.joinable()) accept_thread_.join();
    if (recv_thread_.joinable())   recv_thread_.join();
#ifdef _WIN32
    WSACleanup();
#endif
}
 
void JsonServer::broadcast(const std::string& msg) {
    std::lock_guard<std::mutex> lk(clients_mtx_);
    for (auto& c : clients_) send_all(c.sock, msg);
}
 
void JsonServer::close_socket(socket_t s) { CLOSE_SOCK(s); }
 
// ─── Цикл приёма подключений ──────────────────────────────────────────────
 
void JsonServer::accept_loop() {
    while (running_) {
        socket_t cli = accept(listen_sock_, nullptr, nullptr);
        if (cli == INVALID_SOCKET) break;
        std::lock_guard<std::mutex> lk(clients_mtx_);
        clients_.push_back({cli, false});
        std::cout << "[TMK] Client connected\n";
    }
}
 
// ─── Цикл чтения входящих сообщений ──────────────────────────────────────
 
void JsonServer::recv_loop() {
    while (running_) {
        std::vector<Client> snap;
        { std::lock_guard<std::mutex> lk(clients_mtx_); snap = clients_; }
        for (auto& c : snap) {
            fd_set fds; FD_ZERO(&fds); FD_SET(c.sock, &fds);
            timeval tv{0, 1000};
            if (select(static_cast<int>(c.sock)+1, &fds, nullptr, nullptr, &tv) <= 0) continue;
            std::string line = recv_line(c.sock);
            if (line.empty()) {
                std::lock_guard<std::mutex> lk(clients_mtx_);
                clients_.erase(std::remove_if(clients_.begin(), clients_.end(),
                    [&](const Client& x){ return x.sock == c.sock; }), clients_.end());
                CLOSE_SOCK(c.sock); continue;
            }
            handle_message(line, c);
        }
    }
}
 
// ─── Обработка входящих сообщений ────────────────────────────────────────
 
void JsonServer::handle_message(const std::string& json, Client& src) {
    auto extract = [&](const std::string& key) -> std::string {
        auto pos = json.find("\"" + key + "\"");
        if (pos == std::string::npos) return {};
        pos = json.find(':', pos) + 1;
        while (pos < json.size() && std::isspace(json[pos])) ++pos;
        if (json[pos] == '"') { ++pos; auto e = json.find('"', pos); return json.substr(pos, e-pos); }
        auto end = json.find_first_of(",}\n", pos); return json.substr(pos, end-pos);
    };
 
    std::string type = extract("type");
 
    if (type == "key_event") {
        uint32_t kc = static_cast<uint32_t>(std::stoul(extract("keycode")));
        int64_t  ts = std::stoll(extract("timestamp_ms"));
        engine_.submit_key(kc, ts);
 
    } else if (type == "gaze_update") {
        src.is_gtm = true;
        Tmk::GazeUpdate g;
        g.x          = std::stof(extract("x"));
        g.y          = std::stof(extract("y"));
        g.confidence = std::stof(extract("confidence"));
        g.on_screen  = (extract("on_screen") == "true");
        engine_.update_gaze(g);
 
    } else if (type == "set_exercise") {
        // В production: распаковать ExerciseData из JSON
        // Здесь: заглушка для демонстрации протокола
        ExerciseData data;
        engine_.set_exercise(data);
    }
}
 
} // namespace tmk
