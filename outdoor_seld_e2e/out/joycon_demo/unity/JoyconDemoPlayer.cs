// JoyconDemoPlayer.cs — 通知層の出力をJoy-con振動で体験するデモ（2026-09-01）
//
// 使い方: README_セットアップ手順.md を参照。
//   ←/→ : クリップ切替   Space : 再生/停止   S : 左右入れ替え
//
// 前提: JoyconLib (Looking-Glass) がプロジェクトに入っていて、
//       シーンに JoyconManager コンポーネントが1つあること。
//       Assets/StreamingAssets/joycon_demo/ に <clip>.wav と <clip>_cues.csv を置く。
//
// 振動の対応（本研究の「危険度=鳴り方」）:
//   強   = 高周波・強く長め 600ms （至近の車）
//   中   = 弱め・短く 250ms       （注意の車）
//   警告 = 短いダブルパルス       （サイレン・踏切などの警告音クラス）

using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;

[RequireComponent(typeof(AudioSource))]
public class JoyconDemoPlayer : MonoBehaviour
{
    struct Cue { public float t; public string side, tier, cls; public float az; }

    AudioSource src;
    List<Joycon> joycons;
    readonly List<string> clips = new List<string>();
    readonly List<Cue> cues = new List<Cue>();
    int clipIdx = 0, nextCue = 0;
    bool swapSides = false;
    string lastFire = "";
    string dataDir;

    // 可視化(ScenarioVisualizer)から読むための公開プロパティ
    public string CurrentClip { get { return clips.Count > 0 ? clips[clipIdx] : null; } }
    public float PlayTime { get { return src != null ? src.time : 0f; } }
    public bool IsPlaying { get { return src != null && src.isPlaying; } }
    public string DataDir { get { return dataDir; } }
    public string LastFire { get { return lastFire; } }

    void Start()
    {
        src = GetComponent<AudioSource>();
        joycons = JoyconManager.Instance != null ? JoyconManager.Instance.j : new List<Joycon>();
        dataDir = Path.Combine(Application.streamingAssetsPath, "joycon_demo");
        foreach (var f in Directory.GetFiles(dataDir, "*_cues.csv"))
            clips.Add(Path.GetFileName(f).Replace("_cues.csv", ""));
        clips.Sort();
        if (clips.Count > 0) StartCoroutine(LoadClip(0));
    }

    IEnumerator LoadClip(int idx)
    {
        clipIdx = idx; nextCue = 0; src.Stop(); lastFire = "";
        cues.Clear();
        foreach (var line in File.ReadAllLines(Path.Combine(dataDir, clips[idx] + "_cues.csv")))
        {
            var p = line.Trim().Split(',');
            if (p.Length < 5 || p[0] == "t_s" || p[0].StartsWith("#")) continue;
            float tv, azv;
            if (!float.TryParse(p[0], System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out tv)) continue;
            float.TryParse(p[4], System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out azv);
            cues.Add(new Cue { t = tv, side = p[1], tier = p[2], cls = p[3], az = azv });
        }
        string url = "file:///" + Path.Combine(dataDir, clips[idx] + ".wav").Replace("\\", "/");
        using (var req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.WAV))
        {
            yield return req.SendWebRequest();
            if (req.result == UnityWebRequest.Result.Success)
                src.clip = DownloadHandlerAudioClip.GetContent(req);
            else
                Debug.LogError("wav読み込み失敗: " + url + " / " + req.error);
        }
    }

    void Update()
    {
        if (Input.GetKeyDown(KeyCode.RightArrow) && clips.Count > 0)
            StartCoroutine(LoadClip((clipIdx + 1) % clips.Count));
        if (Input.GetKeyDown(KeyCode.LeftArrow) && clips.Count > 0)
            StartCoroutine(LoadClip((clipIdx - 1 + clips.Count) % clips.Count));
        if (Input.GetKeyDown(KeyCode.S)) swapSides = !swapSides;
        if (Input.GetKeyDown(KeyCode.Space))
        {
            if (src.isPlaying) { src.Stop(); }
            else if (src.clip != null) { nextCue = 0; lastFire = ""; src.Play(); }
        }
        while (src.isPlaying && nextCue < cues.Count && src.time >= cues[nextCue].t)
            Fire(cues[nextCue++]);
    }

    void Fire(Cue c)
    {
        bool wantLeft = (c.side == "L") ^ swapSides;
        Joycon jc = null;
        foreach (var j in joycons) if (j.isLeft == wantLeft) { jc = j; break; }
        if (jc == null && joycons.Count > 0) jc = joycons[0];
        lastFire = $"{c.t:F1}s {(wantLeft ? "左手" : "右手")} {c.tier} ({c.cls} az={c.az:F0}°)";
        if (jc == null) return;                       // Joy-con未接続でも画面表示だけ動く
        // 中間発表の設計どおり「危険度=鳴り方（パルスのパターン）」で区別する（2026-09-02）:
        //   強   = 速い連打 ぶっぶっぶっぶっ（4発・強く・高め）
        //   中   = ゆっくり ぶっ…ぶっ（2発・弱く・低め）
        //   警告 = 単発の柔らかい ぶーっ（音種の通知。危険度パルスとは別物と分かる形）
        switch (c.tier)
        {
            case "強": StartCoroutine(Pulses(jc, 4, 110, 70, 320f, 640f, 1.0f)); break;
            case "中": StartCoroutine(Pulses(jc, 2, 90, 300, 80f, 160f, 0.4f)); break;
            default: jc.SetRumble(120f, 240f, 0.5f, 300); break;   // 警告
        }
    }

    IEnumerator Pulses(Joycon jc, int n, int onMs, int gapMs,
                       float lo, float hi, float amp)
    {
        for (int i = 0; i < n; i++)
        {
            jc.SetRumble(lo, hi, amp, onMs);
            yield return new WaitForSeconds((onMs + gapMs) / 1000f);
        }
    }

    void OnGUI()
    {
        GUI.Label(new Rect(10, 10, 900, 30),
            $"クリップ [{clipIdx + 1}/{clips.Count}] {(clips.Count > 0 ? clips[clipIdx] : "なし")}  " +
            $"Joy-con接続: {joycons.Count}本  左右入替: {(swapSides ? "ON" : "OFF")}");
        GUI.Label(new Rect(10, 35, 900, 30),
            $"←/→=切替  Space=再生/停止  S=左右入替   再生位置 {src.time:F1}s");
        GUI.Label(new Rect(10, 60, 900, 30), "最後の通知: " + lastFire);
        for (int i = 0; i < cues.Count; i++)
            GUI.Label(new Rect(10, 90 + i * 22, 900, 22),
                $"{(i < nextCue && src.isPlaying ? "✓" : "  ")} {cues[i].t:F1}s " +
                $"{cues[i].side} {cues[i].tier} ({cues[i].cls})");
    }
}
