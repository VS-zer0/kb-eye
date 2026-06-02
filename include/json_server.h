#pragma once
#include "tmk.h"
#include <string>
#include <thread>
#include <atomic>
#include <vector>
#include <mutex>
 
#ifdef _WIN32
  #include <winsock2.h>
  #include <ws2tcpip.h>
  using socket_t = SOCKET;
#else
  #include <sys/socket.h>
  #include <netinet/in.h>
  #include <unistd.h>
  using socket_t = int;
  constexpr socket_t INVALID_SOCKET = -1;
#endif
 
namespace tmk {
 
// TCP-сервер: принимает key_event / set_exercise / gaze_update,
// рассылает game_event и state_update всем подключённым клиентам.
class JsonServer {
public:
    explicit JsonServer(Tmk& engine, uint16_t port = 5760);
    ~JsonServer();
 
    bool start();
    void stop();
    bool running() const { return running_; }
 
    void broadcast(const std::string& json_msg);
 
private:
    Tmk&      engine_;
    uint16_t  port_;
    socket_t  listen_sock_ = INVALID_SOCKET;
    std::atomic<bool> running_{false};
 
    struct Client { socket_t sock; bool is_gtm = false; };
    std::vector<Client> clients_;
    std::mutex          clients_mtx_;
 
    std::thread accept_thread_;
    std::thread recv_thread_;
 
    void accept_loop();
    void recv_loop();
    void handle_message(const std::string& json, Client& src);
 
    static std::string event_to_json(const GameEvent& e);
    static std::string state_to_json(const ResourceState& s);
    void close_socket(socket_t s);
};
 
} // namespace tmk
