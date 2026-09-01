// ScenarioVisualizer.cs — シナリオの様子を画面上で動かす俯瞰ビュー（2026-09-02）
//
// 使い方: Demoオブジェクトに Add Component でこのスクリプトを追加するだけ。
//   <clip>_scene.csv（毎フレームの方位・距離）を StreamingAssets/joycon_demo/ から
//   自動で読み、歩行者（白カプセル）を中心に物体を動かす。
//   通知が発火した瞬間、足元のリングが光る（強=赤 / 中=オレンジ / 警告=水色）。
//
// 表示は「歩行者から見た相対位置」= 装着デバイス視点。歩行者は常に中央・上向き。
// 物体の色: 車=青 / 救急車(siren)=白+赤ランプ / バイク=橙 / キック=水色 /
//           ベル自転車=緑 / バック車=灰 / 踏切=黄柱

using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;

public class ScenarioVisualizer : MonoBehaviour
{
    struct Sample { public float t, az, d; }

    JoyconDemoPlayer player;
    string loadedClip = "";
    string lastFireCache = "";
    readonly Dictionary<string, List<Sample>> tracks = new Dictionary<string, List<Sample>>();
    readonly Dictionary<string, string> objClass = new Dictionary<string, string>();
    readonly Dictionary<string, GameObject> gos = new Dictionary<string, GameObject>();
    GameObject pedestrian, flashRing;

    void Start()
    {
        player = FindFirstObjectByType<JoyconDemoPlayer>();

        var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.transform.localScale = new Vector3(8, 1, 8);           // 80m四方
        ground.GetComponent<Renderer>().material.color = new Color(0.24f, 0.27f, 0.24f);

        pedestrian = GameObject.CreatePrimitive(PrimitiveType.Capsule);
        pedestrian.transform.position = new Vector3(0, 1.0f, 0);
        pedestrian.GetComponent<Renderer>().material.color = Color.white;
        var nose = GameObject.CreatePrimitive(PrimitiveType.Cube);    // 向きマーカー
        nose.transform.SetParent(pedestrian.transform);
        nose.transform.localPosition = new Vector3(0, 0.35f, 0.55f);
        nose.transform.localScale = new Vector3(0.25f, 0.15f, 0.5f);
        nose.GetComponent<Renderer>().material.color = Color.white;

        flashRing = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        flashRing.transform.position = new Vector3(0, 0.05f, 0);
        flashRing.transform.localScale = new Vector3(3f, 0.02f, 3f);
        flashRing.SetActive(false);

        var cam = Camera.main;
        if (cam != null)
        {
            cam.transform.position = new Vector3(0, 34, -16);
            cam.transform.LookAt(new Vector3(0, 0, 4));
        }
    }

    string[] stateLines = new string[0];

    void LoadScene(string clip)
    {
        loadedClip = clip;
        foreach (var go in gos.Values) Destroy(go);
        gos.Clear(); tracks.Clear(); objClass.Clear();
        // 判定材料の表示文（<clip>_state.csv: "t|表示文"）
        stateLines = new string[0];
        string sp = Path.Combine(player.DataDir, clip + "_state.csv");
        if (File.Exists(sp))
        {
            var raw = File.ReadAllLines(sp);
            stateLines = new string[raw.Length];
            for (int i = 0; i < raw.Length; i++)
            {
                int bar = raw[i].IndexOf('|');
                stateLines[i] = bar >= 0 ? raw[i].Substring(bar + 1) : "";
            }
        }
        string path = Path.Combine(player.DataDir, clip + "_scene.csv");
        if (!File.Exists(path)) return;               // scene.csvが無いクリップは音+振動のみ
        foreach (var line in File.ReadAllLines(path))
        {
            var p = line.Trim().Split(',');
            if (p.Length < 5 || p[0] == "t_s" || p[0].StartsWith("#")) continue;
            float t, az, d;
            if (!float.TryParse(p[0], NumberStyles.Float, CultureInfo.InvariantCulture, out t)) continue;
            float.TryParse(p[3], NumberStyles.Float, CultureInfo.InvariantCulture, out az);
            float.TryParse(p[4], NumberStyles.Float, CultureInfo.InvariantCulture, out d);
            if (!tracks.ContainsKey(p[1])) { tracks[p[1]] = new List<Sample>(); objClass[p[1]] = p[2]; }
            tracks[p[1]].Add(new Sample { t = t, az = az, d = d });
        }
    }

    void Update()
    {
        if (player == null) return;
        var clip = player.CurrentClip;
        if (clip != null && clip != loadedClip) LoadScene(clip);

        float now = player.PlayTime;
        bool playing = player.IsPlaying;
        foreach (var kv in tracks)
        {
            Sample s = default; bool found = false;
            var L = kv.Value;
            for (int i = 0; i < L.Count; i++)
            {
                if (L[i].t <= now + 0.05f) { s = L[i]; found = true; } else break;
            }
            bool show = playing && found && (now - s.t) <= 0.3f;
            var go = GetOrCreate(kv.Key);
            go.SetActive(show);
            if (!show) continue;
            float rad = s.az * Mathf.Deg2Rad;             // DCASE: 0°=前, +=左
            var pos = new Vector3(-s.d * Mathf.Sin(rad), go.transform.position.y,
                                  s.d * Mathf.Cos(rad));
            var prev = go.transform.position;
            go.transform.position = Vector3.Lerp(prev, pos, 12f * Time.deltaTime);
            var move = go.transform.position - prev;      // 進行方向へ向ける
            move.y = 0;
            if (move.sqrMagnitude > 1e-4f)
                go.transform.rotation = Quaternion.Slerp(go.transform.rotation,
                    Quaternion.LookRotation(move), 8f * Time.deltaTime);
        }

        if (player.LastFire != lastFireCache)
        {
            lastFireCache = player.LastFire;
            if (lastFireCache != "") { StopCoroutine("Flash"); StartCoroutine("Flash"); }
        }
    }

    IEnumerator Flash()
    {
        var c = lastFireCache.Contains("強") ? Color.red
              : lastFireCache.Contains("中") ? new Color(1f, 0.6f, 0f) : Color.cyan;
        flashRing.GetComponent<Renderer>().material.color = c;
        flashRing.SetActive(true);
        yield return new WaitForSeconds(0.6f);
        flashRing.SetActive(false);
    }

    void OnGUI()
    {
        if (player == null || stateLines.Length == 0) return;
        int idx = Mathf.Clamp(Mathf.FloorToInt(player.PlayTime * 10f), 0, stateLines.Length - 1);
        string txt = player.IsPlaying ? stateLines[idx] : "（Spaceで再生すると判定が流れます）";
        var style = new GUIStyle(GUI.skin.label) { fontSize = 16, wordWrap = true };
        style.normal.textColor = Color.white;
        GUI.Box(new Rect(5, Screen.height - 78, Screen.width - 10, 72), "");
        GUI.Label(new Rect(12, Screen.height - 74, Screen.width - 24, 66),
                  "いまの判定: " + txt, style);
    }

    GameObject GetOrCreate(string key)
    {
        if (gos.ContainsKey(key)) return gos[key];
        string cls = objClass[key];
        GameObject go;
        if (cls == "siren")                               // 救急車: 白い車体+赤ランプ
        {
            go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.transform.localScale = new Vector3(1.9f, 1.7f, 4.8f);
            go.GetComponent<Renderer>().material.color = Color.white;
            var lamp = GameObject.CreatePrimitive(PrimitiveType.Cube);
            lamp.transform.SetParent(go.transform);
            lamp.transform.localPosition = new Vector3(0, 0.6f, 0.1f);
            lamp.transform.localScale = new Vector3(0.5f, 0.15f, 0.25f);
            lamp.GetComponent<Renderer>().material.color = Color.red;
        }
        else if (cls == "crossing")                       // 踏切警報器: 黄色い柱
        {
            go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            go.transform.localScale = new Vector3(0.5f, 1.6f, 0.5f);
            go.GetComponent<Renderer>().material.color = Color.yellow;
        }
        else if (cls == "bike_bell")                      // ベル自転車: 緑の球
        {
            go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            go.transform.localScale = Vector3.one * 1.0f;
            go.GetComponent<Renderer>().material.color = Color.green;
        }
        else
        {
            go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            Color col; Vector3 size;
            switch (cls)
            {
                case "car":  col = new Color(0.2f, 0.45f, 1f); size = new Vector3(1.7f, 1.3f, 4.2f); break;
                case "bike": col = new Color(1f, 0.55f, 0.1f); size = new Vector3(0.8f, 1.3f, 2.2f); break;
                case "kick": col = Color.cyan;                 size = new Vector3(0.5f, 1.3f, 1.4f); break;
                case "backup_beep": col = Color.gray;          size = new Vector3(2.2f, 2.4f, 6f); break;
                case "horn": col = new Color(0.6f, 0.3f, 1f);  size = new Vector3(1.7f, 1.3f, 4.2f); break;
                default:     col = Color.magenta;              size = Vector3.one; break;
            }
            go.transform.localScale = size;
            go.GetComponent<Renderer>().material.color = col;
        }
        var p0 = go.transform.position; p0.y = go.transform.localScale.y * 0.5f;
        go.transform.position = p0;
        gos[key] = go;
        return go;
    }
}
