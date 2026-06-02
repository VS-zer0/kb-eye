using System;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Collections.Concurrent;
using UnityEngine;

public class TmkAdapter : MonoBehaviour
{
    public static TmkAdapter Instance { get; private set; }

    [Header("Events")]
    public event Action<string, string> OnGameEvent;   // (event, payload)
    public event Action<TmkState>       OnStateUpdate;

    private Process       _tmkProcess;
    private TcpClient     _client;
    private NetworkStream _stream;
    private Thread        _readThread;
    private bool          _running;

    private readonly ConcurrentQueue<string> _inbox = new();

    void Awake() { Instance = this; }

    void Start()
    {
        StartTmkProcess();
        ConnectWithRetry();
        SendSetExercise();

        _running    = true;
        _readThread = new Thread(ReceiveLoop) { IsBackground = true };
        _readThread.Start();
    }

    void Update()
    {
        while (_inbox.TryDequeue(out var json))
            HandleMessage(json);
    }

    // ── Запуск TMK ────────────────────────────────────────────────────────

    void StartTmkProcess()
    {
        string exe = Path.Combine(Application.streamingAssetsPath,
#if UNITY_EDITOR_WIN || UNITY_STANDALONE_WIN
            "tmk_service.exe");
#else
            "tmk_service");
#endif
        string cfg = Path.Combine(Application.streamingAssetsPath, "config.json");

        _tmkProcess = new Process();
        _tmkProcess.StartInfo.FileName        = exe;
        _tmkProcess.StartInfo.Arguments       = $"\"{cfg}\"";
        _tmkProcess.StartInfo.UseShellExecute = false;
        _tmkProcess.StartInfo.CreateNoWindow  = true;
        _tmkProcess.Start();
        UnityEngine.Debug.Log("[TMK] Process started, pid=" + _tmkProcess.Id);
    }

    void ConnectWithRetry()
    {
        for (int i = 0; i < 10; i++)
        {
            try
            {
                _client = new TcpClient("127.0.0.1", 5760);
                _stream = _client.GetStream();
                UnityEngine.Debug.Log("[TMK] Connected");
                return;
            }
            catch { Thread.Sleep(300); }
        }
        UnityEngine.Debug.LogError("[TMK] Cannot connect");
    }

    // ── Отправка сообщений ────────────────────────────────────────────────

    public void SendKeyEvent(char key)
    {
        long ts   = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        string msg = $"{{\"type\":\"key_event\","
                   + $"\"keycode\":{(int)key},"
                   + $"\"timestamp_ms\":{ts}}}\n";
        Send(msg);
    }

    void SendSetExercise()
    {
        // Минимальная конфигурация первого упражнения
        string msg = "{\"type\":\"set_exercise\","
                   + "\"word_list\":[\"аsd\",\"фjk\",\"ыl\"]}\n";
        Send(msg);
    }

    void Send(string json)
    {
        if (_stream == null) return;
        var data = Encoding.UTF8.GetBytes(json);
        try { _stream.Write(data, 0, data.Length); }
        catch (Exception e) { UnityEngine.Debug.LogWarning("[TMK] Send: " + e.Message); }
    }

    // ── Фоновый поток чтения ──────────────────────────────────────────────

    void ReceiveLoop()
    {
        var sb = new StringBuilder();
        while (_running)
        {
            try
            {
                int b = _stream.ReadByte();
                if (b < 0) break;
                if ((char)b == '\n')
                {
                    _inbox.Enqueue(sb.ToString());
                    sb.Clear();
                }
                else sb.Append((char)b);
            }
            catch { break; }
        }
    }

    // ── Разбор входящих сообщений (main thread) ───────────────────────────

    void HandleMessage(string json)
    {
        if (json.Contains("\"game_event\""))
        {
            string ev = Extract(json, "event");
            OnGameEvent?.Invoke(ev, json);
        }
        else if (json.Contains("\"state_update\""))
        {
            var state = new TmkState
            {
                wpm      = float.Parse(Extract(json, "wpm")),
                accuracy = float.Parse(Extract(json, "accuracy")),
                xp       = int.Parse(Extract(json, "xp")),
            };
            OnStateUpdate?.Invoke(state);
        }
    }

    static string Extract(string json, string key)
    {
        int p = json.IndexOf($"\"{key}\":", StringComparison.Ordinal);
        if (p < 0) return "0";
        p = json.IndexOf(':', p) + 1;
        while (p < json.Length && char.IsWhiteSpace(json[p])) p++;
        if (json[p] == '"')
        {
            p++; int e = json.IndexOf('"', p);
            return json.Substring(p, e - p);
        }
        int end = json.IndexOfAny(new[]{',','}','\n'}, p);
        return json.Substring(p, end - p).Trim();
    }

    void OnApplicationQuit()
    {
        _running = false;
        try { Send("{\"type\":\"quit\"}\n"); } catch { }
        _stream?.Close();
        _client?.Close();
        try { _tmkProcess?.Kill(); } catch { }
    }
}

[Serializable]
public struct TmkState
{
    public float wpm;
    public float accuracy;
    public int   xp;
}