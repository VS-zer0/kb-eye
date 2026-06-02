#pragma once
#include "exercise_data.h"
#include <string>
#include <vector>
#include <unordered_map>
#include <functional>
 
namespace tmk {
 
struct SequencerNode {
    std::string              id;
    ExerciseKind             kind;
    float                    unlock_accuracy = 0.0f;
    float                    unlock_wpm      = 0.0f;
    std::vector<std::string> depends_on;
    bool                     unlocked  = false;
    bool                     completed = false;
};
 
class ExerciseSequencer {
public:
    bool load_from_file(const std::string& path);
    bool load_from_string(const std::string& json_str);
 
    std::vector<const SequencerNode*> available() const;
 
    // Помечает узел пройденным; возвращает вновь разблокированные id
    std::vector<std::string> complete_node(const std::string& id,
                                           float achieved_accuracy,
                                           float achieved_wpm);
 
    void set_on_unlock(std::function<void(const std::string&)> cb);
    const SequencerNode* find(const std::string& id) const;
 
private:
    std::vector<SequencerNode>              nodes_;
    std::unordered_map<std::string, size_t> index_;
    std::function<void(const std::string&)> on_unlock_;
 
    bool prerequisites_met(const SequencerNode& node) const;
};
 
} // namespace tmk
