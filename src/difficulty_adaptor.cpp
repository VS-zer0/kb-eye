#include "../include/difficulty_adaptor.h"
#include <algorithm>
 
namespace tmk {
 
DifficultyAdaptor::DifficultyAdaptor(AdaptorConfig cfg)
    : cfg_(std::move(cfg)) {}
 
void DifficultyAdaptor::set_on_change(std::function<void(int,int)> cb)
    { on_change_ = std::move(cb); }
 
float DifficultyAdaptor::effective_wpm_upper(float wpm_target) const {
    return wpm_target > 0.0f ? wpm_target * cfg_.wpm_upper_factor : 1e9f;
}
 
bool DifficultyAdaptor::update(float wpm, float accuracy,
                                float wpm_target, int& diff) {
    using Clock = std::chrono::steady_clock;
    auto now    = Clock::now();
 
    const bool above = accuracy >= cfg_.accuracy_upper &&
                       wpm      >= effective_wpm_upper(wpm_target);
    const bool below = accuracy <  cfg_.accuracy_lower;
 
    // ── Слишком легко → повысить сложность ───────────────────────────────
    if (above) {
        if (!tracking_above_) { tracking_above_ = true; above_since_ = now; }
        else {
            auto s = std::chrono::duration_cast<std::chrono::seconds>(
                         now - above_since_).count();
            if (s >= cfg_.stable_window_sec && diff < cfg_.max_difficulty) {
                int old = diff; ++diff;
                tracking_above_ = false;
                if (on_change_) on_change_(old, diff);
                return true;
            }
        }
    } else { tracking_above_ = false; }
 
    // ── Слишком сложно → снизить сложность ───────────────────────────────
    if (below) {
        if (!tracking_below_) { tracking_below_ = true; below_since_ = now; }
        else {
            auto s = std::chrono::duration_cast<std::chrono::seconds>(
                         now - below_since_).count();
            if (s >= cfg_.stable_window_sec / 2 && diff > cfg_.min_difficulty) {
                int old = diff; --diff;
                tracking_below_ = false;
                if (on_change_) on_change_(old, diff);
                return true;
            }
        }
    } else { tracking_below_ = false; }
 
    return false;
}
 
void DifficultyAdaptor::apply(int difficulty, ExerciseData& data) const {
    data.min_word_length = 2 + difficulty - 1;
    data.max_word_length = std::min(5 + (difficulty - 1) * 2, 14);
    if (data.wpm_target > 0.0f)
        data.wpm_target = 20.0f + difficulty * 12.0f;
    if (data.error_budget >= 0)
        data.error_budget = std::max(0, 10 - difficulty * 2);
}
 
} // namespace tmk
