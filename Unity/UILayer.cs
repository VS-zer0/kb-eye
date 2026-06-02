using UnityEngine;
using TMPro;

public class UILayer : MonoBehaviour
{
    [SerializeField] TMP_Text wpmLabel;
    [SerializeField] TMP_Text accuracyLabel;
    [SerializeField] TMP_Text xpLabel;

    void OnEnable()
    {
        TmkAdapter.Instance.OnStateUpdate += Refresh;
    }

    void OnDisable()
    {
        if (TmkAdapter.Instance != null)
            TmkAdapter.Instance.OnStateUpdate -= Refresh;
    }

    void Refresh(TmkState s)
    {
        if (wpmLabel)      wpmLabel.text      = $"WPM: {s.wpm:F0}";
        if (accuracyLabel) accuracyLabel.text = $"Точность: {s.accuracy*100:F0}%";
        if (xpLabel)       xpLabel.text       = $"XP: {s.xp}";
    }
}