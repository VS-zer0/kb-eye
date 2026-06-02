#pragma once
#include <string>
#include <vector>
#include <cstdint>
 
namespace tmk {
 
// ─── Игровые события, публикуемые TMK движку-хосту ───────────────────────
enum class EventType {
    KeyHit,           // верное нажатие
    KeyMiss,          // ошибочное нажатие
    KeyHint,          // подсказка целевой клавиши
    ModifierCue,      // подсказка клавиши-модификатора (Shift и т.п.)
    WordComplete,     // слово введено верно
    WordFail,         // слово введено с ошибками, сброс
    ExerciseComplete, // задание завершено
    WpmUpdate,        // плановое обновление WPM
    AccuracyUpdate,   // плановое обновление точности
    OverBudget,       // превышен бюджет ошибок
    SpeedFail,        // скорость ниже целевой по истечении времени
    DifficultyChange, // адаптер изменил уровень сложности
    GazeOffScreen,    // взгляд покинул экран (только при подкл. GTM)
    GazeRestored,     // взгляд вернулся на экран
    XpGained,         // начислены очки опыта
    ExerciseUnlocked  // открыт новый тип упражнения
};
 
struct GameEvent {
    EventType   type;
    std::string payload_json; // дополнительные данные в JSON-строке
};
 
// ─── Состояние ресурсов, передаваемое в state_update ─────────────────────
struct ResourceState {
    float wpm            = 0.0f;
    float accuracy       = 1.0f;  // [0, 1]
    int   xp             = 0;
    int   skill_level    = 1;
    int   difficulty     = 1;     // 1..5
    bool  gaze_on_screen = true;
    float gaze_x         = 0.5f;
    float gaze_y         = 0.5f;
    float gaze_conf      = 0.0f;
};
 
} // namespace tmk
