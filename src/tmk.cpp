#include "../include/tmk.h"
#include <algorithm>
#include <sstream>
#include <cmath>
 
namespace tmk {
 
Tmk::Tmk(TmkConfig cfg) : cfg_(std::move(cfg)) {}
 
// ─── Управление упражнением ───────────────────────────────────────────────
 
void Tmk::set_exercise(const ExerciseData& data) {
    exercise_    = data;
    target_text_ = build_target_text();
    cursor_      = 0;
    error_count_ = 0;
    word_errors_ = 0;
    accuracy_window_.clear();
    wpm_window_.clear();
    state_.wpm      = 0.0f;
    state_.accuracy = 1.0f;
}
 
void Tmk::reset_exercise() { set_exercise(exercise_); }
 
// ─── Ввод клавиши ─────────────────────────────────────────────────────────
 
void Tmk::submit_key(uint32_t keycode, int64_t timestamp_ms) {
    if (target_text_.empty() || cursor_ >= target_text_.size()) return;
 
    const char expected = target_text_[cursor_];
    const bool correct  = (static_cast<char>(keycode) == expected);
 
    push_accuracy(correct);
 
    if (correct) {
        push_wpm_stamp(timestamp_ms);
        ++cursor_;
        state_.xp += static_cast<int>(calc_xp_gain(state_.wpm, true));
        emit(EventType::KeyHit);
        check_word_complete();
    } else {
        ++error_count_;
        ++word_errors_;
        emit(EventType::KeyMiss);
 
        if (exercise_.error_budget >= 0 &&
            error_count_ > exercise_.error_budget)
            emit(EventType::OverBudget);
 
        emit(EventType::KeyHint,
             std::string("{\"key\":\"") + expected + "\"}");
 
        if (exercise_.layout_shift && std::isupper(expected))
            emit(EventType::ModifierCue, "{\"modifier\":\"Shift\"}");
    }
 
    state_.wpm      = calc_wpm(timestamp_ms);
    state_.accuracy = calc_accuracy();
    last_state_update_ms_ = timestamp_ms;
}
 
// ─── Данные взгляда ───────────────────────────────────────────────────────
 
void Tmk::update_gaze(const GazeUpdate& g) {
    if (!cfg_.gaze_enabled) return;
 
    state_.gaze_x    = g.x;
    state_.gaze_y    = g.y;
    state_.gaze_conf = g.confidence;
 
    bool was_on = state_.gaze_on_screen;
    state_.gaze_on_screen = g.on_screen;
 
    if (!g.on_screen && was_on) {
        emit(EventType::GazeOffScreen);
        last_gaze_on_screen_ms_ = 0;
    } else if (g.on_screen && !was_on) {
        emit(EventType::GazeRestored);
    }
}
 
// ─── Периодический тик ───────────────────────────────────────────────────
 
void Tmk::tick(int64_t now_ms) {
    const int64_t interval_ms = 1000 / cfg_.state_update_hz;
    if (now_ms - last_state_update_ms_ >= interval_ms) {
        publish_state(now_ms);
        last_state_update_ms_ = now_ms;
    }
 
    // Штраф за взгляд на клавиатуру
    if (cfg_.gaze_enabled && !state_.gaze_on_screen
        && last_gaze_on_screen_ms_ > 0) {
        int64_t off_ms = now_ms - last_gaze_on_screen_ms_;
        if (off_ms >= exercise_.gaze_penalty_ms) {
            float seconds = static_cast<float>(off_ms) / 1000.0f;
            state_.accuracy = std::max(0.0f,
                state_.accuracy - cfg_.gaze_penalty_acc * seconds);
            last_gaze_on_screen_ms_ = now_ms;
        }
    }
 
    // Адаптер сложности
    int diff = state_.difficulty;
    if (adaptor_.update(state_.wpm, state_.accuracy,
                        exercise_.wpm_target, diff)) {
        int old = state_.difficulty;
        state_.difficulty = diff;
        adaptor_.apply(diff, exercise_);
        target_text_ = build_target_text();
        emit(EventType::DifficultyChange,
             "{\"from\":" + std::to_string(old)
             + ",\"to\":"  + std::to_string(diff) + "}");
    }
}
 
// ─── Callbacks ────────────────────────────────────────────────────────────
 
void Tmk::set_on_event(std::function<void(const GameEvent&)> cb)
    { on_event_ = std::move(cb); }
 
void Tmk::set_on_state_update(std::function<void(const ResourceState&)> cb)
    { on_state_update_ = std::move(cb); }
 
// ─── Приватные методы ─────────────────────────────────────────────────────
 
void Tmk::emit(EventType t, const std::string& payload) {
    if (on_event_) on_event_({t, payload});
}
 
void Tmk::push_accuracy(bool correct) {
    accuracy_window_.push_back(correct);
    if (static_cast<int>(accuracy_window_.size()) > cfg_.accuracy_window)
        accuracy_window_.pop_front();
}
 
void Tmk::push_wpm_stamp(int64_t ts_ms) {
    wpm_window_.push_back({ts_ms});
    while (!wpm_window_.empty() &&
           ts_ms - wpm_window_.front().ts_ms > 60'000)
        wpm_window_.pop_front();
}
 
float Tmk::calc_wpm(int64_t now_ms) const {
    if (wpm_window_.size() < 2) return 0.0f;
    int64_t span_ms = now_ms - wpm_window_.front().ts_ms;
    if (span_ms <= 0) return 0.0f;
    return (static_cast<float>(wpm_window_.size()) / 5.0f)
           / (static_cast<float>(span_ms) / 60'000.0f);
}
 
float Tmk::calc_accuracy() const {
    if (accuracy_window_.empty()) return 1.0f;
    int ok = static_cast<int>(
        std::count(accuracy_window_.begin(), accuracy_window_.end(), true));
    return static_cast<float>(ok) / accuracy_window_.size();
}
 
float Tmk::calc_xp_gain(float wpm, bool correct) const {
    if (!correct) return 0.0f;
    float base    = cfg_.xp_per_correct;
    float bonus   = std::max(0.0f, wpm - 30.0f) * cfg_.xp_wpm_scale;
    float diminish = 1.0f / std::pow(1.0f + wpm / 100.0f, cfg_.xp_slowdown_exp);
    return (base + bonus) * diminish;
}
 
std::string Tmk::build_target_text() const {
    std::string result;
    for (int r = 0; r < exercise_.repeat_count; ++r)
        for (const auto& w : exercise_.word_list)
            result += w + ' ';
    if (!result.empty() && result.back() == ' ')
        result.pop_back();
    return result;
}
 
void Tmk::check_word_complete() {
    bool at_space = (cursor_ < target_text_.size()
                     && target_text_[cursor_] == ' ');
    bool at_end   = (cursor_ >= target_text_.size());
 
    if (at_space || at_end) {
        if (word_errors_ == 0) {
            emit(EventType::WordComplete);
            state_.xp += static_cast<int>(calc_xp_gain(state_.wpm, true) * 5.0f);
        } else {
            emit(EventType::WordFail);
            if (exercise_.error_budget < 0)
                while (cursor_ > 0 && target_text_[cursor_ - 1] != ' ')
                    --cursor_;
        }
        word_errors_ = 0;
        if (at_space) ++cursor_;
        if (cursor_ >= target_text_.size())
            emit(EventType::ExerciseComplete);
    }
}
 
void Tmk::publish_state(int64_t) {
    emit(EventType::WpmUpdate,
         "{\"wpm\":"      + std::to_string(state_.wpm) + "}");
    emit(EventType::AccuracyUpdate,
         "{\"accuracy\":" + std::to_string(state_.accuracy) + "}");
    if (on_state_update_) on_state_update_(state_);
}
 
} // namespace tmk
