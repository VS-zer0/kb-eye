#pragma once
#include "exercise_data.h"
#include <chrono>
#include <functional>
 
namespace tmk {
 
struct AdaptorConfig {
    float accuracy_upper    = 0.95f;
    float accuracy_lower    = 0.80f;
    float wpm_upper_factor  = 1.20f;
    int   stable_window_sec = 30;
    int   max_difficulty    = 5;
    int   min_difficulty    = 1;
};
 
class DifficultyAdaptor {
public:
    explicit DifficultyAdaptor(AdaptorConfig cfg = {});
 
    // Вызывается при каждом обновлении; возвращает true при смене сложности
    bool update(float current_wpm, float current_accuracy,
                float wpm_target, int& difficulty_inout);
 
    // Применяет текущий уровень сложности к ExerciseData
    void apply(int difficulty, ExerciseData& data) const;
 
    void set_on_change(std::function<void(int, int)> cb);
 
private:
    AdaptorConfig cfg_;
    std::chrono::steady_clock::time_point above_since_;
    std::chrono::steady_clock::time_point below_since_;
    bool tracking_above_ = false;
    bool tracking_below_ = false;
    std::function<void(int, int)> on_change_;
 
    float effective_wpm_upper(float wpm_target) const;
};
 
} // namespace tmk
