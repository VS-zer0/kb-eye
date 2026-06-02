#include "../include/exercise_sequencer.h"
#include <fstream>
#include <sstream>
#include <algorithm>
 
// Минимальный парсер JSON-структуры узлов.
// В production рекомендуется nlohmann/json или rapidjson.
namespace {
 
std::string read_file(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Cannot open: " + path);
    std::ostringstream ss; ss << f.rdbuf(); return ss.str();
}
 
std::string json_str_val(const std::string& obj, const std::string& key) {
    auto pos = obj.find("\"" + key + "\"");
    if (pos == std::string::npos) return {};
    pos = obj.find(':', pos) + 1;
    while (pos < obj.size() && std::isspace(obj[pos])) ++pos;
    if (obj[pos] != '"') return {};
    ++pos; auto end = obj.find('"', pos);
    return obj.substr(pos, end - pos);
}
 
float json_float_val(const std::string& obj, const std::string& key,
                     float def = 0.0f) {
    auto pos = obj.find("\"" + key + "\"");
    if (pos == std::string::npos) return def;
    pos = obj.find(':', pos) + 1;
    while (pos < obj.size() && std::isspace(obj[pos])) ++pos;
    try { return std::stof(obj.substr(pos)); } catch (...) { return def; }
}
 
} // anonymous
 
namespace tmk {
 
bool ExerciseSequencer::load_from_file(const std::string& path) {
    try { return load_from_string(read_file(path)); }
    catch (...) { return false; }
}
 
// Ожидаемый формат: JSON-массив объектов
// [{"id":"home_row","kind":0,"unlock_accuracy":0,"unlock_wpm":0,"depends_on":[]}, ...]
bool ExerciseSequencer::load_from_string(const std::string& src) {
    nodes_.clear(); index_.clear();
    size_t pos = 0;
    while (pos < src.size()) {
        auto s = src.find('{', pos);
        if (s == std::string::npos) break;
        int depth = 0; size_t e = s;
        for (size_t i = s; i < src.size(); ++i) {
            if (src[i] == '{') ++depth;
            if (src[i] == '}') { --depth; if (!depth) { e = i; break; } }
        }
        std::string obj = src.substr(s, e - s + 1);
        pos = e + 1;
 
        SequencerNode node;
        node.id             = json_str_val(obj, "id");
        node.kind           = static_cast<ExerciseKind>(
                                  static_cast<int>(json_float_val(obj, "kind")));
        node.unlock_accuracy = json_float_val(obj, "unlock_accuracy");
        node.unlock_wpm      = json_float_val(obj, "unlock_wpm");
 
        auto da = obj.find("\"depends_on\"");
        if (da != std::string::npos) {
            auto as = obj.find('[', da), ae = obj.find(']', as);
            if (as != std::string::npos) {
                std::string arr = obj.substr(as+1, ae-as-1);
                size_t p = 0;
                while (p < arr.size()) {
                    auto qs = arr.find('"', p); if (qs == std::string::npos) break;
                    auto qe = arr.find('"', qs+1);
                    node.depends_on.push_back(arr.substr(qs+1, qe-qs-1));
                    p = qe + 1;
                }
            }
        }
        node.unlocked = node.depends_on.empty();
        if (!node.id.empty()) { index_[node.id] = nodes_.size(); nodes_.push_back(node); }
    }
    return !nodes_.empty();
}
 
std::vector<const SequencerNode*> ExerciseSequencer::available() const {
    std::vector<const SequencerNode*> res;
    for (const auto& n : nodes_)
        if (n.unlocked && !n.completed) res.push_back(&n);
    return res;
}
 
std::vector<std::string> ExerciseSequencer::complete_node(
    const std::string& id, float acc, float wpm) {
    auto it = index_.find(id);
    if (it == index_.end()) return {};
    SequencerNode& node = nodes_[it->second];
    if (acc >= node.unlock_accuracy && wpm >= node.unlock_wpm)
        node.completed = true;
    std::vector<std::string> unlocked;
    for (auto& n : nodes_) {
        if (n.unlocked) continue;
        if (prerequisites_met(n)) {
            n.unlocked = true; unlocked.push_back(n.id);
            if (on_unlock_) on_unlock_(n.id);
        }
    }
    return unlocked;
}
 
void ExerciseSequencer::set_on_unlock(std::function<void(const std::string&)> cb)
    { on_unlock_ = std::move(cb); }
 
const SequencerNode* ExerciseSequencer::find(const std::string& id) const {
    auto it = index_.find(id);
    return it != index_.end() ? &nodes_[it->second] : nullptr;
}
 
bool ExerciseSequencer::prerequisites_met(const SequencerNode& node) const {
    for (const auto& dep : node.depends_on) {
        auto it = index_.find(dep);
        if (it == index_.end() || !nodes_[it->second].completed) return false;
    }
    return true;
}
 
} // namespace tmk
