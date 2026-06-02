using UnityEngine;
using TMPro;

public class WorldManager : MonoBehaviour
{
    [SerializeField] TMP_Text targetWordLabel;

    private string _currentWord = "fjdk";

    void OnEnable()
    {
        TmkAdapter.Instance.OnGameEvent += HandleEvent;
    }

    void OnDisable()
    {
        if (TmkAdapter.Instance != null)
            TmkAdapter.Instance.OnGameEvent -= HandleEvent;
    }

    void HandleEvent(string ev, string payload)
    {
        switch (ev)
        {
            case "word_complete":
                Debug.Log("Слово введено верно!");
                // спауните следующего врага, засчитайте очки и т.п.
                break;

            case "word_fail":
                Debug.Log("Ошибка — сброс слова");
                break;

            case "difficulty_change":
                Debug.Log("Смена сложности: " + payload);
                break;

            case "exercise_unlocked":
                Debug.Log("Новое упражнение: " + payload);
                break;
        }
    }
}