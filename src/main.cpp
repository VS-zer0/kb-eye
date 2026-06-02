#include "../include/tmk.h"
#include "../include/json_server.h"
#include <iostream>
#include <fstream>
#include <chrono>
#include <thread>
#include <csignal>
 
#ifndef _WIN32
  #include <unistd.h>
#endif
 
struct AppConfig {
    uint16_t    tmk_port       = 5760;
    uint16_t    gtm_port       = 5765;
    std::string sequencer_path = "exercises.json";
    bool        launch_gtm     = false;
    std::string gtm_executable = "./gaze_service";
};
 
AppConfig load_config(const std::string& path) {
    AppConfig cfg;
    std::ifstream f(path); if (!f) return cfg;
    std::string line;
    while (std::getline(f, line)) {
        auto parse_u16 = [&](const std::string& key, uint16_t& out) {
            auto p = line.find("\"" + key + "\"");
            if (p == std::string::npos) return;
            p = line.find(':', p) + 1;
            while (p < line.size() && std::isspace(line[p])) ++p;
            out = static_cast<uint16_t>(std::stoul(line.substr(p)));
        };
        parse_u16("tmk_port", cfg.tmk_port);
        parse_u16("gtm_port", cfg.gtm_port);
        if (line.find("launch_gtm") != std::string::npos)
            cfg.launch_gtm = line.find("true") != std::string::npos;
    }
    return cfg;
}
 
static volatile bool g_running = true;
static void sig_handler(int) { g_running = false; }
 
int main(int argc, char* argv[]) {
    std::string cfg_path = (argc > 1) ? argv[1] : "config.json";
    auto app_cfg = load_config(cfg_path);
 
    std::signal(SIGINT,  sig_handler);
    std::signal(SIGTERM, sig_handler);
 
    tmk::TmkConfig tmk_cfg;
    tmk_cfg.gaze_enabled = (app_cfg.gtm_port != 0);
 
    tmk::Tmk       engine(tmk_cfg);
    tmk::JsonServer server(engine, app_cfg.tmk_port);
 
    if (!engine.exercise_sequencer().load_from_file(app_cfg.sequencer_path))
        std::cerr << "[TMK] Warning: sequencer file not found\n";
 
    engine.exercise_sequencer().set_on_unlock([&](const std::string& id) {
        server.broadcast("{\"type\":\"exercise_unlocked\",\"id\":\"" + id + "\"}\n");
        std::cout << "[TMK] Unlocked: " << id << "\n";
    });
 
    // Топология 2: запуск GTM как дочернего процесса
    if (app_cfg.launch_gtm) {
#ifdef _WIN32
        std::string cmd = app_cfg.gtm_executable
                        + " --port " + std::to_string(app_cfg.gtm_port);
        STARTUPINFOA si{}; PROCESS_INFORMATION pi{};
        CreateProcessA(nullptr, const_cast<char*>(cmd.c_str()),
                       nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi);
        std::cout << "[TMK] GTM started (pid=" << pi.dwProcessId << ")\n";
#else
        pid_t pid = fork();
        if (pid == 0) {
            execlp(app_cfg.gtm_executable.c_str(),
                   app_cfg.gtm_executable.c_str(),
                   "--port", std::to_string(app_cfg.gtm_port).c_str(), nullptr);
            _exit(1);
        } else if (pid > 0) {
            std::cout << "[TMK] GTM started (pid=" << pid << ")\n";
        }
#endif
    }
 
    if (!server.start()) {
        std::cerr << "[TMK] Failed to start server on port " << app_cfg.tmk_port << "\n";
        return 1;
    }
 
    std::cout << "[TMK] Running. Press Ctrl+C to stop.\n";
 
    while (g_running) {
        auto now_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
        engine.tick(now_ms);
        std::this_thread::sleep_for(std::chrono::milliseconds(16)); // ~60 Hz
    }
 
    std::cout << "[TMK] Shutting down.\n";
    server.stop();
    return 0;
}
