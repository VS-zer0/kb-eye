#pragma once
#include <string>
#include <vector>
 
namespace tmk {
 
enum class ExerciseKind {
    SingleKeys,       // отдельные клавиши
    SpecialChars,     // специальные символы и пунктуация
    FrequentWords,    // частотные слова
    SpeedDrilling,    // тренировка скорости
    AccuracyDrilling, // тренировка точности
    GazeHold          // удержание взгляда (требует GTM)
};
 
struct ExerciseData {
    ExerciseKind kind = ExerciseKind::FrequentWords;
 
    // содержимое упражнения
    std::vector<std::string> word_list;
    std::vector<char>        target_keys;
    bool                     layout_shift = false;
 
    // ограничения производительности
    float wpm_target      = 0.0f;  // 0 = не ограничено
    float accuracy_target = 0.0f;  // 0 = не ограничено
    int   error_budget    = -1;    // -1 = неограниченный
    int   time_limit_sec  = 0;     // 0 = без лимита
 
    // параметры GazeHold
    int   gaze_penalty_ms = 800;
    float gaze_bonus_xp   = 2.0f;
 
    // мета
    int repeat_count    = 1;
    int min_word_length = 2;
    int max_word_length = 12;
};
 
} // namespace tmk
