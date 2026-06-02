using UnityEngine;

public class InputHandler : MonoBehaviour
{
    void OnGUI()
    {
        Event e = Event.current;
        if (e.type == EventType.KeyDown && e.keyCode != KeyCode.None)
        {
            char c = e.character;
            if (c != '\0')
                TmkAdapter.Instance?.SendKeyEvent(c);
        }
    }
}