#pragma once
#include "types.h"
#include "exercise_data.h"
#include "difficulty_adaptor.h"
#include "exercise_sequencer.h"
#include <string>
#include <deque>
#include <functional>
 
namespace tmk {
 
struct TmkConfig {
    int   wpm_window_chars  = 300;
    int   accuracy_window   = 100;
    float xp_per_correct    = 1.0f;
    float xp_wpm_scale      = 0.01f;
    float xp_slowdown_exp   = 1.8f;
    bool  gaze_enabled      = false;
    float gaze_penalty_acc  = 0.005f;
    int   state_update_hz   = 10;
};
 
class Tmk {
public:
    explicit Tmk(TmkConfig cfg = {});
 
    void set_exercise(const ExerciseData& data);
    void reset_exercise();
 
    // keycode: Unicode codepoint; timestamp_ms: мс с epoch
    void submit_key(uint32_t keycode, int64_t timestamp_ms);
 
    struct GazeUpdate { float x, y, confidence; bool on_screen; };
    void update_gaze(const GazeUpdate& g);
 
    const ResourceState& state() const { return state_; }
 
    void set_on_event(std::function<void(const GameEvent&)> cb);
    void set_on_state_update(std::function<void(const ResourceState&)> cb);
 
    // Вызывается из основного цикла (~60 Гц)
    void tick(int64_t now_ms);
 
    DifficultyAdaptor& difficulty_adaptor() { return adaptor_; }
    ExerciseSequencer& exercise_sequencer() { return sequencer_; }
 
private:
    TmkConfig         cfg_;
    ResourceState     state_;
    ExerciseData      exercise_;
    DifficultyAdaptor adaptor_;
    ExerciseSequencer sequencer_;
 
    size_t      cursor_       = 0;
    std::string target_text_;
    int         error_count_  = 0;
    int         word_errors_  = 0;
 
    std::deque<bool>    accuracy_window_;
    struct KeyStamp { int64_t ts_ms; };
    std::deque<KeyStamp> wpm_window_;
 
    int64_t last_state_update_ms_   = 0;
    int64_t last_gaze_on_screen_ms_ = 0;
 
    std::function<void(const GameEvent&)>     on_event_;
    std::function<void(const ResourceState&)> on_state_update_;
 
    void        emit(EventType t, const std::string& payload = "{}");
    void        push_accuracy(bool correct);
    void        push_wpm_stamp(int64_t ts_ms);
    float       calc_wpm(int64_t now_ms) const;
    float       calc_accuracy() const;
    float       calc_xp_gain(float wpm, bool correct) const;
    std::string build_target_text() const;
    void        check_word_complete();
    void        publish_state(int64_t now_ms);
};
 
} // namespace tmk
