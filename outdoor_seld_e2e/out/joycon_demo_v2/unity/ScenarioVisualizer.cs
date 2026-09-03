// ScenarioVisualizer.cs — 俯瞰ビュー v2（2026-09-03）: 道路の配置・8クラスの見た目・**検出層の出力**を重ねる
//
// v1（2026-09-02）からの追加:
//   - <clip>_layout.csv から 車線（横位置・進行方向）／歩道／踏切（線路・遮断機の柱）を描く
//   - <clip>_detect.csv（検出層の生出力）を「見えているもの」として重ねる:
//       距離クラス（車・キック・バイク）= 予測位置に小さな円盤（クラス色・暗め）
//       警告音クラス（サイレン等）= 方位だけなので半径15mのリング上に小さな円盤
//     → GT（実体）と検出（モデルが思っている位置）のズレがそのまま見える
//   - 8クラスの形: 車(ボディ+キャビン) / 救急車(白+赤帯+ランプ) / トラック(バック音・箱+キャブ) /
//     クラクション車(黄) / バイク(2輪+車体) / キックボード(板+人) / ベル自転車(緑・2輪+人) / 踏切(黄黒の遮断機+X標識)
//   - 物体の上にクラス名ラベル（TextMesh）
//
// 表示は「歩行者から見た相対位置」= 装着デバイス視点（FOA座標: 前=画面上, 左=画面左）。
// ⚠️ 合成世界は直線道路のみ（交差点・信号は学習データに存在しない）。
//   V キーの「街の飾り」（交差点・信号・横断歩道・建物・街路樹）は**見た目だけ**で、音にも通知にも影響しない。
//   飾りは scene_type で出し分け: arterial/daily=前方25mに交差点+信号+横断歩道+建物、residential=住宅+街路樹

using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;

public class ScenarioVisualizer : MonoBehaviour
{
    struct Sample { public float t, az, d; public int vis; }   // vis: 1=鳴っている/ラベルあり, 0=いるが無音・ラベル無し（薄く描く）
    readonly Dictionary<Renderer, Color> baseColor = new Dictionary<Renderer, Color>();
    readonly Dictionary<string, int> dimState = new Dictionary<string, int>();
    struct Det { public float t, az, d; public string cls; public bool hasD; }

    JoyconDemoPlayer player;
    string loadedClip = "";
    string lastFireCache = "";
    readonly Dictionary<string, List<Sample>> tracks = new Dictionary<string, List<Sample>>();
    readonly Dictionary<string, string> objClass = new Dictionary<string, string>();
    readonly Dictionary<string, GameObject> gos = new Dictionary<string, GameObject>();
    readonly List<Det> dets = new List<Det>();
    readonly List<GameObject> detPool = new List<GameObject>();
    readonly List<GameObject> layoutGos = new List<GameObject>();
    GameObject pedestrian, flashRing, walkArrow;
    bool showDet = true, showDeco = true;
    string sceneType = "";
    float realCrossZ = float.NaN;
    bool mapMode = false;
    // 歩行: 歩行者は画面中央に固定し、街（車線・飾り・地図）を後ろへ流す。配置図は「5 秒時点の歩行者」基準で描いてある
    float walkDir = 0f, walkSpeed = 0f;
    GameObject worldRoot;            // _layout.csv に map 行があれば実地図（OSM）を描き、合成の車線・飾りは出さない   // _layout.csv に本物の交差道路（xlane）があればその前方距離。飾りの交差点はそこに合わせる
    const float WARN_RING_M = 15f;
    readonly List<GameObject> decoGos = new List<GameObject>();
    readonly List<Renderer> signalLamps = new List<Renderer>();   // [赤,黄,青] × 灯器

    static readonly Dictionary<string, Color> CLS_COLOR = new Dictionary<string, Color> {
        {"car", new Color(0.2f, 0.45f, 1f)}, {"siren", Color.white}, {"backup_beep", Color.gray},
        {"horn", new Color(1f, 0.85f, 0.2f)}, {"bike", new Color(1f, 0.55f, 0.1f)}, {"kick", Color.cyan},
        {"bike_bell", Color.green}, {"crossing", Color.yellow} };
    static readonly Dictionary<string, string> CLS_JP = new Dictionary<string, string> {
        {"car", "車"}, {"siren", "救急車"}, {"backup_beep", "バック車"}, {"horn", "クラクション"},
        {"bike", "バイク"}, {"kick", "キック"}, {"bike_bell", "自転車ベル"}, {"crossing", "踏切"} };

    void Start()
    {
        player = FindFirstObjectByType<JoyconDemoPlayer>();

        var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
        ground.transform.localScale = new Vector3(8, 1, 8);           // 80m四方
        ground.GetComponent<Renderer>().material.color = new Color(0.30f, 0.42f, 0.28f);   // 草地

        pedestrian = GameObject.CreatePrimitive(PrimitiveType.Capsule);
        pedestrian.transform.position = new Vector3(0, 1.0f, 0);
        pedestrian.GetComponent<Renderer>().material.color = Color.white;
        var nose = GameObject.CreatePrimitive(PrimitiveType.Cube);    // 向き（デバイスの前）
        nose.transform.SetParent(pedestrian.transform);
        nose.transform.localPosition = new Vector3(0, 0.35f, 0.55f);
        nose.transform.localScale = new Vector3(0.25f, 0.15f, 0.5f);
        nose.GetComponent<Renderer>().material.color = Color.white;
        walkArrow = GameObject.CreatePrimitive(PrimitiveType.Cube);   // 歩く向き（地面の矢印）
        walkArrow.transform.localScale = new Vector3(0.3f, 0.02f, 2.0f);
        walkArrow.GetComponent<Renderer>().material.color = new Color(0.9f, 0.9f, 0.9f);
        walkArrow.SetActive(false);

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

    static bool PF(string s, out float v)
    {
        return float.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out v);
    }

    void LoadScene(string clip)
    {
        loadedClip = clip;
        foreach (var go in gos.Values) Destroy(go);
        foreach (var go in layoutGos) Destroy(go);
        foreach (var go in decoGos) Destroy(go);
        gos.Clear(); tracks.Clear(); objClass.Clear(); layoutGos.Clear(); dets.Clear(); decoGos.Clear(); signalLamps.Clear(); baseColor.Clear(); dimState.Clear();

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
        if (File.Exists(path))
            foreach (var line in File.ReadAllLines(path))
            {
                var p = line.Trim().Split(',');
                if (p.Length < 5 || p[0] == "t_s" || p[0].StartsWith("#")) continue;
                float t, az, d, vv = 1f;
                if (!PF(p[0], out t)) continue;
                PF(p[3], out az); PF(p[4], out d);
                if (p.Length >= 6 && p[5] != "") PF(p[5], out vv);
                if (!tracks.ContainsKey(p[1])) { tracks[p[1]] = new List<Sample>(); objClass[p[1]] = p[2]; }
                tracks[p[1]].Add(new Sample { t = t, az = az, d = d, vis = vv >= 0.5f ? 1 : 0 });
            }
        string dp = Path.Combine(player.DataDir, clip + "_detect.csv");
        if (File.Exists(dp))
            foreach (var line in File.ReadAllLines(dp))
            {
                var p = line.Trim().Split(',');
                if (p.Length < 3 || p[0] == "t_s") continue;
                float t, az, d = 0f;
                if (!PF(p[0], out t)) continue;
                PF(p[2], out az);
                bool hasD = p.Length >= 4 && p[3] != "" && PF(p[3], out d);
                dets.Add(new Det { t = t, az = az, d = d, cls = p[1], hasD = hasD });
            }
        BuildLayout(Path.Combine(player.DataDir, clip + "_layout.csv"));
        if (worldRoot == null) worldRoot = new GameObject("WorldRoot");
        worldRoot.transform.position = Vector3.zero;
        foreach (var g in layoutGos) if (g != null) g.transform.SetParent(worldRoot.transform, true);
        foreach (var g in decoGos) if (g != null) g.transform.SetParent(worldRoot.transform, true);
    }

    // ---- 道路配置 ---------------------------------------------------------------
    void BuildLayout(string lp)
    {
        walkArrow.SetActive(false);
        mapMode = false;
        if (!File.Exists(lp)) return;
        var laneYs = new List<float>();
        var laneDirs = new List<float>();
        var xl = new List<float[]>(); var xlKind = new List<string>();   // 横切る道路・線路（v3: xlane,x,dir,kind,height）
        foreach (var line in File.ReadAllLines(lp))
        {
            var p = line.Trim().Split(',');
            if (p.Length < 4 || p[0] == "type") continue;
            if (p[0] == "scene")
            {
                sceneType = p[1];
                float wd;
                walkDir = 0f; walkSpeed = 0f;
                if (p[2] == "walk" && PF(p[3], out wd) && wd != 0f)
                {
                    walkArrow.SetActive(true);
                    walkArrow.transform.position = new Vector3(0, 0.03f, wd > 0 ? 1.6f : -1.6f);
                    walkDir = wd > 0 ? 1f : -1f;
                    float sp;
                    walkSpeed = (p.Length > 4 && p[4] != "" && PF(p[4], out sp) && sp > 0f) ? sp : 4.3f / 3.6f;
                }
            }
            else if (p[0] == "lane")
            {
                float y, dir; PF(p[1], out y); PF(p[2], out dir);
                laneYs.Add(y); laneDirs.Add(dir);
            }
            else if (p[0] == "map") { mapMode = true; }
            else if (p[0] == "road" || p[0] == "water" || p[0] == "rail")
            {
                float x1, y1, x2, y2, wd = 3f; PF(p[1], out x1); PF(p[2], out y1); PF(p[3], out x2); PF(p[4], out y2);
                if (p.Length > 5 && p[5] != "") PF(p[5], out wd);
                string kind = p.Length > 6 ? p[6] : "";
                AddSegment(p[0], x1, y1, x2, y2, wd, kind);
            }
            else if (p[0] == "bldg")
            {
                float cx, cy, bw, bd, ang, bh = 6f; PF(p[1], out cx); PF(p[2], out cy); PF(p[3], out bw); PF(p[4], out bd); PF(p[5], out ang);
                if (p.Length > 6 && p[6] != "") PF(p[6], out bh);
                AddBuilding(cx, cy, bw, bd, ang, bh, p.Length > 7 ? p[7] : "");
            }
            else if (p[0] == "poi")
            {
                float px, py; PF(p[1], out px); PF(p[2], out py);
                AddPoi(px, py, p[3], p.Length > 4 ? p[4] : "");
            }
            else if (p[0] == "xlane")
            {
                float x, dir, h = 0f; PF(p[1], out x); PF(p[2], out dir); if (p.Length > 4) PF(p[4], out h);
                xl.Add(new float[] { x, dir, h }); xlKind.Add(p[3]);
            }
            else if (p[0] == "static" && p[3] == "crossing")
            {
                float x, y; PF(p[1], out x); PF(p[2], out y);
                BuildCrossing(x, y);
            }
        }
        if (mapMode) return;   // 実地図: 合成の歩道帯・車線・飾りは描かない（道路は road 行で描いてある）
        // 歩道（歩行者の足元・幅1.2m）
        var sw = Band(0f, 1.2f, new Color(0.62f, 0.62f, 0.58f), 0.01f);
        layoutGos.Add(sw);
        // 車線: 横位置 y ごとに幅3mのアスファルト帯＋中央の破線＋進行方向の矢印
        var used = new List<float>();
        for (int i = 0; i < laneYs.Count; i++)
        {
            float y = laneYs[i];
            bool near = false;
            foreach (var u in used) if (Mathf.Abs(u - y) < 1.6f) near = true;
            if (near) continue;
            used.Add(y);
            layoutGos.Add(Band(y, 3.0f, new Color(0.22f, 0.22f, 0.24f), 0.005f));
            for (int k = -12; k <= 12; k++)               // 破線
            {
                var dash = GameObject.CreatePrimitive(PrimitiveType.Cube);
                dash.transform.localScale = new Vector3(0.12f, 0.01f, 1.5f);
                dash.transform.position = new Vector3(-(y + (y > 0 ? 1.5f : -1.5f)), 0.012f, k * 3.2f);
                dash.GetComponent<Renderer>().material.color = new Color(0.9f, 0.9f, 0.85f);
                layoutGos.Add(dash);
            }
            var arrow = GameObject.CreatePrimitive(PrimitiveType.Cube);   // 進行方向
            arrow.transform.localScale = new Vector3(0.25f, 0.012f, 2.4f);
            arrow.transform.position = new Vector3(-y, 0.013f, laneDirs[i] > 0 ? 6f : -6f);
            arrow.GetComponent<Renderer>().material.color = laneDirs[i] > 0 ? new Color(0.6f, 0.9f, 1f) : new Color(1f, 0.7f, 0.6f);
            layoutGos.Add(arrow);
        }
        // 横切る道路・線路（v3 の場面: 交差点を横切る車・横断歩道・左折・高架）。Unity z = 前方距離 x
        realCrossZ = float.NaN;
        for (int i = 0; i < xl.Count; i++)
        {
            float x = xl[i][0], dir = xl[i][1], h = xl[i][2]; string kind = xlKind[i];
            if (h > 2f)
            {   // 高架（頭上）: 2本のレールと橋脚だけ描き、下の道路や車が隠れないようにする
                for (int sgn = -1; sgn <= 1; sgn += 2)
                {
                    var rail = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    rail.transform.localScale = new Vector3(80f, 0.15f, 0.2f);
                    rail.transform.position = new Vector3(0, h, x + sgn * 0.75f);
                    rail.GetComponent<Renderer>().material.color = new Color(0.35f, 0.35f, 0.4f);
                    layoutGos.Add(rail);
                }
                for (int k = -3; k <= 3; k++)
                {
                    var pier = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    pier.transform.localScale = new Vector3(0.8f, h, 2.4f);
                    pier.transform.position = new Vector3(k * 12f + 6f, h / 2f, x);
                    pier.GetComponent<Renderer>().material.color = new Color(0.5f, 0.5f, 0.52f);
                    layoutGos.Add(pier);
                }
                continue;
            }
            if (float.IsNaN(realCrossZ)) realCrossZ = x;
            var band = GameObject.CreatePrimitive(PrimitiveType.Cube);
            band.transform.localScale = new Vector3(80f, 0.01f, kind == "train" ? 4f : 6.5f);
            band.transform.position = new Vector3(0, 0.006f, x);
            band.GetComponent<Renderer>().material.color = kind == "train" ? new Color(0.3f, 0.28f, 0.25f) : new Color(0.22f, 0.22f, 0.24f);
            layoutGos.Add(band);
            if (kind == "train")
            {
                for (int sgn = -1; sgn <= 1; sgn += 2)
                {
                    var r = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    r.transform.localScale = new Vector3(80f, 0.012f, 0.12f);
                    r.transform.position = new Vector3(0, 0.014f, x + sgn * 0.72f);
                    r.GetComponent<Renderer>().material.color = new Color(0.6f, 0.6f, 0.62f);
                    layoutGos.Add(r);
                }
            }
            else
            {
                for (int k = -12; k <= 12; k++)
                {
                    var dash = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    dash.transform.localScale = new Vector3(1.5f, 0.01f, 0.12f);
                    dash.transform.position = new Vector3(k * 3.2f, 0.012f, x);
                    dash.GetComponent<Renderer>().material.color = new Color(0.9f, 0.9f, 0.85f);
                    layoutGos.Add(dash);
                }
                var arrow = GameObject.CreatePrimitive(PrimitiveType.Cube);   // 進行方向（+y=歩行者の左へ → Unity −x）
                arrow.transform.localScale = new Vector3(2.4f, 0.012f, 0.25f);
                arrow.transform.position = new Vector3(dir > 0 ? -6f : 6f, 0.013f, x + (dir > 0 ? 1.5f : -1.5f));
                arrow.GetComponent<Renderer>().material.color = dir > 0 ? new Color(0.6f, 0.9f, 1f) : new Color(1f, 0.7f, 0.6f);
                layoutGos.Add(arrow);
            }
        }
        BuildDecoration(used);
    }

    // ---- 実地図（OpenStreetMap → _osm_map_layout.py）の描画。FOA座標 x=前 y=左 → Unity (−y, 0, x) ----
    static readonly HashSet<string> CAR_ROADS = new HashSet<string> { "tertiary", "secondary", "primary", "unclassified", "residential", "living_street", "service", "car" };
    void AddSegment(string type, float x1, float y1, float x2, float y2, float wd, string kind)
    {
        var a = new Vector3(-y1, 0f, x1); var b = new Vector3(-y2, 0f, x2);
        var dvec = b - a; float len = dvec.magnitude; if (len < 0.05f) return;
        float h = type == "water" ? 0.002f : (type == "rail" ? 0.006f : (CAR_ROADS.Contains(kind) ? 0.004f : 0.005f));
        var g = GameObject.CreatePrimitive(PrimitiveType.Cube);
        g.transform.position = (a + b) * 0.5f + new Vector3(0, h, 0);
        g.transform.rotation = Quaternion.LookRotation(dvec.normalized, Vector3.up);
        g.transform.localScale = new Vector3(wd, 0.01f, len + wd * 0.9f);
        Color c;
        if (type == "water") c = new Color(0.45f, 0.65f, 0.95f);
        else if (type == "rail") { c = new Color(0.3f, 0.28f, 0.25f); g.transform.localScale = new Vector3(3.2f, 0.01f, len + 1f); }
        else if (CAR_ROADS.Contains(kind)) c = new Color(0.22f, 0.22f, 0.24f);
        else if (kind == "steps") c = new Color(0.7f, 0.68f, 0.62f);
        else c = new Color(0.62f, 0.62f, 0.58f);       // 歩道・小道
        g.GetComponent<Renderer>().material.color = c;
        layoutGos.Add(g);
        if (type == "rail")
        {
            for (int sgn = -1; sgn <= 1; sgn += 2)
            {
                var r = GameObject.CreatePrimitive(PrimitiveType.Cube);
                r.transform.position = g.transform.position + g.transform.right * (sgn * 0.72f) + new Vector3(0, 0.008f, 0);
                r.transform.rotation = g.transform.rotation;
                r.transform.localScale = new Vector3(0.12f, 0.012f, len + 1f);
                r.GetComponent<Renderer>().material.color = new Color(0.6f, 0.6f, 0.62f);
                layoutGos.Add(r);
            }
        }
    }

    void AddBuilding(float cx, float cy, float bw, float bd, float angDeg, float bh, string name)
    {
        var g = GameObject.CreatePrimitive(PrimitiveType.Cube);
        float rad = angDeg * Mathf.Deg2Rad;
        var axis = new Vector3(-Mathf.Sin(rad), 0f, Mathf.Cos(rad));      // 長軸（FOA (cos,sin) → Unity (−sin, 0, cos)）
        g.transform.position = new Vector3(-cy, bh * 0.5f, cx);
        g.transform.rotation = Quaternion.LookRotation(axis, Vector3.up);
        g.transform.localScale = new Vector3(Mathf.Max(bd, 1f), bh, Mathf.Max(bw, 1f));
        g.GetComponent<Renderer>().material.color = name != "" ? new Color(0.72f, 0.62f, 0.55f) : new Color(0.6f, 0.58f, 0.6f);
        layoutGos.Add(g);
        if (name != "") AddLabel(g, name, bh + 1.5f);
    }

    void AddPoi(float px, float py, string kind, string name)
    {
        var pos = new Vector3(-py, 0f, px);
        if (kind == "crossing")
        {
            for (int k = -2; k <= 2; k++)
            {
                var z = GameObject.CreatePrimitive(PrimitiveType.Cube);
                z.transform.position = pos + new Vector3(k * 0.9f, 0.011f, 0);
                z.transform.localScale = new Vector3(0.45f, 0.01f, 3.0f);
                z.GetComponent<Renderer>().material.color = new Color(0.92f, 0.92f, 0.9f);
                layoutGos.Add(z);
            }
        }
        else if (kind == "signal")
        {
            var pole = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            pole.transform.position = pos + new Vector3(0, 2.5f, 0); pole.transform.localScale = new Vector3(0.18f, 2.5f, 0.18f);
            pole.GetComponent<Renderer>().material.color = new Color(0.35f, 0.35f, 0.38f); layoutGos.Add(pole);
            var lamp = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            lamp.transform.position = pos + new Vector3(0, 5.2f, 0); lamp.transform.localScale = Vector3.one * 0.9f;
            lamp.GetComponent<Renderer>().material.color = new Color(1f, 0.25f, 0.2f); layoutGos.Add(lamp);
        }
        else if (kind == "gate")
        {
            GameObject last = null;
            for (int sgn = -1; sgn <= 1; sgn += 2)
            {
                var post = GameObject.CreatePrimitive(PrimitiveType.Cube);
                post.transform.position = pos + new Vector3(sgn * 1.6f, 1.2f, 0); post.transform.localScale = new Vector3(0.4f, 2.4f, 0.4f);
                post.GetComponent<Renderer>().material.color = new Color(0.95f, 0.6f, 0.2f); layoutGos.Add(post); last = post;
            }
            if (name != "" && last != null) AddLabel(last, name, 3.5f);
        }
        else if (kind == "bus_stop")
        {
            var pole = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            pole.transform.position = pos + new Vector3(0, 1.4f, 0); pole.transform.localScale = new Vector3(0.12f, 1.4f, 0.12f);
            pole.GetComponent<Renderer>().material.color = new Color(0.2f, 0.4f, 0.9f); layoutGos.Add(pole);
            var sign = GameObject.CreatePrimitive(PrimitiveType.Cube);
            sign.transform.position = pos + new Vector3(0, 2.9f, 0); sign.transform.localScale = new Vector3(0.9f, 0.6f, 0.08f);
            sign.GetComponent<Renderer>().material.color = new Color(0.2f, 0.4f, 0.9f); layoutGos.Add(sign);
            if (name != "") AddLabel(sign, name, 1.0f);
        }
    }

    // ---- 街の飾り（見た目だけ・音や通知には無関係） ------------------------------------
    GameObject Deco(PrimitiveType t, Vector3 pos, Vector3 size, Color c)
    {
        var g = GameObject.CreatePrimitive(t);
        g.transform.position = pos; g.transform.localScale = size;
        g.GetComponent<Renderer>().material.color = c;
        decoGos.Add(g);
        return g;
    }

    void BuildDecoration(List<float> laneYs)
    {
        // 道路の外側の端（車線の最も遠い側）を求め、その外側に建物・街路樹を置く
        float roadMinX = -0.6f, roadMaxX = 0.6f;           // Unity x = −y
        foreach (var y in laneYs) { float x = -y; roadMinX = Mathf.Min(roadMinX, x - 1.5f); roadMaxX = Mathf.Max(roadMaxX, x + 1.5f); }
        bool urban = sceneType == "arterial" || sceneType == "daily";
        if (sceneType == "parking")
        {
            // 駐車場: 広いアスファルト・両側に駐車枠（白線）と停めてある車・周りは低いフェンス。車線（通路）は lane 行のまま
            Deco(PrimitiveType.Cube, new Vector3(0, 0.002f, 0), new Vector3(46f, 0.01f, 80f), new Color(0.3f, 0.3f, 0.32f));
            for (int side = -1; side <= 1; side += 2)
            {
                float xBay = side * (Mathf.Max(roadMaxX, -roadMinX) + 4.5f);     // 通路の外側に駐車枠の列
                for (int k = -7; k <= 7; k++)
                {
                    float z = k * 5.2f;
                    Deco(PrimitiveType.Cube, new Vector3(xBay, 0.012f, z + 2.6f), new Vector3(5.0f, 0.01f, 0.12f), new Color(0.92f, 0.92f, 0.9f));   // 枠線
                    if ((k * 7 + side * 3 + 11) % 3 != 0)                                                                                        // 3台に2台は駐車中
                    {
                        var body = Deco(PrimitiveType.Cube, new Vector3(xBay, 0.7f, z), new Vector3(1.8f, 1.4f, 4.4f), new Color(0.55f + 0.1f * (k % 3), 0.55f, 0.6f + 0.1f * ((k + side) % 2)));
                        Deco(PrimitiveType.Cube, new Vector3(xBay, 1.55f, z - 0.3f), new Vector3(1.6f, 0.5f, 2.4f), new Color(0.3f, 0.35f, 0.4f));
                    }
                }
                Deco(PrimitiveType.Cube, new Vector3(xBay, 0.012f, 0), new Vector3(0.12f, 0.01f, 80f), new Color(0.92f, 0.92f, 0.9f));   // 枠の背中側の線
                Deco(PrimitiveType.Cube, new Vector3(side * 23f, 0.6f, 0), new Vector3(0.1f, 1.2f, 80f), new Color(0.5f, 0.5f, 0.52f));  // フェンス
            }
            for (int k = -3; k <= 3; k++)
                Deco(PrimitiveType.Cylinder, new Vector3(-24.5f, 2.5f, k * 12f), new Vector3(0.2f, 2.5f, 0.2f), new Color(0.35f, 0.35f, 0.38f));   // 照明柱
            foreach (var g in decoGos) g.SetActive(showDeco);
            return;
        }
        bool realCross = !float.IsNaN(realCrossZ);
        float zX = realCross ? realCrossZ : 25f;           // 交差点の位置（本物の横切る道路があればそこ。無ければ前方25m・飾り）
        if (urban)
        {
            // 交差道路（画面横方向の帯）＋横断歩道＋停止線
            if (!realCross)
                Deco(PrimitiveType.Cube, new Vector3(0, 0.004f, zX), new Vector3(80f, 0.01f, 6.5f), new Color(0.22f, 0.22f, 0.24f));
            for (int k = -9; k <= 9; k++)
                Deco(PrimitiveType.Cube, new Vector3(k * 0.9f, 0.011f, zX - 4.4f), new Vector3(0.45f, 0.01f, 2.0f), new Color(0.92f, 0.92f, 0.9f));
            Deco(PrimitiveType.Cube, new Vector3(0, 0.011f, zX - 5.8f), new Vector3(12f, 0.01f, 0.25f), new Color(0.92f, 0.92f, 0.9f));
            // 信号機（横断歩道の手前の角・歩行者側と反対側）
            BuildSignal(new Vector3(roadMaxX + 1.0f, 0, zX - 6.5f), true);
            BuildSignal(new Vector3(roadMinX - 1.0f, 0, zX + 6.5f), false);
            // 建物（道路の両側の区画。交差点の帯は空ける）
            var col = new Color(0.55f, 0.55f, 0.6f);
            for (int k = 0; k < 5; k++)
            {
                float z = -30f + k * 11f; if (Mathf.Abs(z - zX) < 8f) continue;
                Deco(PrimitiveType.Cube, new Vector3(roadMaxX + 8f, 3.5f, z), new Vector3(9f, 7f + 2f * (k % 3), 8f), col * (0.85f + 0.05f * k));
                Deco(PrimitiveType.Cube, new Vector3(roadMinX - 9f, 2.5f, z + 4f), new Vector3(9f, 5f + 1.5f * (k % 2), 8f), col * (0.8f + 0.06f * k));
            }
        }
        else
        {
            // 住宅街: 家と街路樹
            for (int k = 0; k < 6; k++)
            {
                float z = -32f + k * 12f;
                Deco(PrimitiveType.Cube, new Vector3(roadMaxX + 6f, 1.8f, z), new Vector3(7f, 3.6f, 7f), new Color(0.75f, 0.68f, 0.6f));
                Deco(PrimitiveType.Cube, new Vector3(roadMaxX + 6f, 4.0f, z), new Vector3(7.4f, 0.8f, 7.4f), new Color(0.45f, 0.3f, 0.3f));   // 屋根
                Deco(PrimitiveType.Cube, new Vector3(roadMinX - 7f, 1.8f, z + 6f), new Vector3(7f, 3.6f, 7f), new Color(0.8f, 0.78f, 0.7f));
            }
            for (int k = -3; k <= 3; k++)
            {
                Deco(PrimitiveType.Cylinder, new Vector3(roadMinX - 1.2f, 1.2f, k * 10f + 5f), new Vector3(0.3f, 1.2f, 0.3f), new Color(0.4f, 0.3f, 0.2f));
                Deco(PrimitiveType.Sphere, new Vector3(roadMinX - 1.2f, 3.2f, k * 10f + 5f), Vector3.one * 2.6f, new Color(0.2f, 0.5f, 0.2f));
            }
        }
        foreach (var g in decoGos) g.SetActive(showDeco);
    }

    void BuildSignal(Vector3 basePos, bool faceUs)
    {
        Deco(PrimitiveType.Cylinder, basePos + new Vector3(0, 2.5f, 0), new Vector3(0.18f, 2.5f, 0.18f), new Color(0.35f, 0.35f, 0.38f));
        var box = Deco(PrimitiveType.Cube, basePos + new Vector3(faceUs ? -0.9f : 0.9f, 4.8f, 0), new Vector3(1.8f, 0.55f, 0.35f), new Color(0.1f, 0.1f, 0.1f));
        Color[] cols = { Color.red, Color.yellow, new Color(0.1f, 0.6f, 1f) };
        for (int i = 0; i < 3; i++)
        {
            var lamp = Deco(PrimitiveType.Sphere, box.transform.position + new Vector3((i - 1) * 0.55f, 0, faceUs ? -0.2f : 0.2f), Vector3.one * 0.4f, cols[i] * 0.3f);
            signalLamps.Add(lamp.GetComponent<Renderer>());
        }
    }

    // 信号の点灯を時間で回す（青→黄→赤・飾り）
    void UpdateSignals(float now)
    {
        if (signalLamps.Count == 0) return;
        float ph = Mathf.Repeat(now, 12f);
        int lit = ph < 6f ? 2 : ph < 8f ? 1 : 0;      // 青6s・黄2s・赤4s
        Color[] cols = { Color.red, Color.yellow, new Color(0.1f, 0.6f, 1f) };
        for (int i = 0; i < signalLamps.Count; i++)
        {
            int lampIdx = i % 3;
            signalLamps[i].material.color = lampIdx == lit ? cols[lampIdx] : cols[lampIdx] * 0.25f;
        }
    }

    GameObject Band(float y, float width, Color c, float h)
    {
        var b = GameObject.CreatePrimitive(PrimitiveType.Cube);
        b.transform.localScale = new Vector3(width, 0.01f, 80f);
        b.transform.position = new Vector3(-y, h, 0);
        b.GetComponent<Renderer>().material.color = c;
        return b;
    }

    void BuildCrossing(float x, float y)
    {
        // 線路: 警報機の位置 x を横切る2本のレール（画面横方向）＋黄黒の遮断機の柱
        for (int r = -1; r <= 1; r += 2)
        {
            var rail = GameObject.CreatePrimitive(PrimitiveType.Cube);
            rail.transform.localScale = new Vector3(40f, 0.02f, 0.12f);
            rail.transform.position = new Vector3(0, 0.02f, x + r * 0.7f);
            rail.GetComponent<Renderer>().material.color = new Color(0.5f, 0.45f, 0.4f);
            layoutGos.Add(rail);
        }
        var post = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
        post.transform.localScale = new Vector3(0.3f, 1.4f, 0.3f);
        post.transform.position = new Vector3(-y, 1.4f, x);
        post.GetComponent<Renderer>().material.color = Color.yellow;
        layoutGos.Add(post);
        var bar = GameObject.CreatePrimitive(PrimitiveType.Cube);         // 遮断かん（黄黒）
        bar.transform.localScale = new Vector3(3.0f, 0.12f, 0.12f);
        bar.transform.position = new Vector3(-y + 1.5f, 2.4f, x);
        bar.GetComponent<Renderer>().material.color = new Color(1f, 0.85f, 0f);
        layoutGos.Add(bar);
        var sign = GameObject.CreatePrimitive(PrimitiveType.Cube);        // X標識
        sign.transform.localScale = new Vector3(0.9f, 0.9f, 0.05f);
        sign.transform.position = new Vector3(-y, 3.2f, x);
        sign.transform.rotation = Quaternion.Euler(0, 0, 45);
        sign.GetComponent<Renderer>().material.color = Color.yellow;
        layoutGos.Add(sign);
        AddLabel(post, "踏切", 2.2f);
    }

    // ---- 毎フレーム ---------------------------------------------------------------
    // 無音・ラベル無しの間は色を落として「そこにいるが聞こえていない」ことを示す（消さない）
    void ApplyDim(string key, GameObject go, int vis)
    {
        int cur; if (dimState.TryGetValue(key, out cur) && cur == vis) return;
        dimState[key] = vis;
        foreach (var r in go.GetComponentsInChildren<Renderer>())
        {
            Color c0;
            if (!baseColor.TryGetValue(r, out c0)) { c0 = r.material.color; baseColor[r] = c0; }
            r.material.color = vis == 1 ? c0 : new Color(c0.r * 0.45f, c0.g * 0.45f, c0.b * 0.45f, c0.a);
        }
    }

    void Update()
    {
        if (player == null) return;
        if (Input.GetKeyDown(KeyCode.D)) showDet = !showDet;
        if (Input.GetKeyDown(KeyCode.V)) { showDeco = !showDeco; foreach (var g in decoGos) g.SetActive(showDeco); }
        var clip = player.CurrentClip;
        if (clip != null && clip != loadedClip) LoadScene(clip);

        float now = player.PlayTime;
        bool playing = player.IsPlaying;
        if (worldRoot != null)
            worldRoot.transform.position = (walkDir != 0f && walkSpeed > 0f)
                ? new Vector3(0f, 0f, -walkDir * walkSpeed * (now - 5f)) : Vector3.zero;
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
            ApplyDim(kv.Key, go, s.vis);
            float rad = s.az * Mathf.Deg2Rad;             // DCASE: 0°=前, +=左
            var pos = new Vector3(-s.d * Mathf.Sin(rad), go.transform.position.y, s.d * Mathf.Cos(rad));
            var prev = go.transform.position;
            go.transform.position = Vector3.Lerp(prev, pos, 12f * Time.deltaTime);
            var move = go.transform.position - prev;
            move.y = 0;
            if (move.sqrMagnitude > 1e-4f && objClass[kv.Key] != "crossing")
                go.transform.rotation = Quaternion.Slerp(go.transform.rotation,
                    Quaternion.LookRotation(move), 8f * Time.deltaTime);
        }
        UpdateDetections(now, playing);
        UpdateSignals(Time.time);

        if (player.LastFire != lastFireCache)
        {
            lastFireCache = player.LastFire;
            if (lastFireCache != "") { StopCoroutine("Flash"); StartCoroutine("Flash"); }
        }
    }

    // 検出層の出力: 直近0.15秒の検出を円盤で描く（GT実体との差＝知覚層の誤差）
    void UpdateDetections(float now, bool playing)
    {
        int used = 0;
        if (showDet && playing)
        {
            foreach (var d in dets)
            {
                if (d.t > now + 0.05f || now - d.t > 0.15f) continue;
                if (used >= detPool.Count)
                {
                    var disc = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                    disc.transform.localScale = new Vector3(1.0f, 0.03f, 1.0f);
                    detPool.Add(disc);
                }
                var g = detPool[used++];
                Color c; if (!CLS_COLOR.TryGetValue(d.cls, out c)) c = Color.magenta;
                g.GetComponent<Renderer>().material.color = c * 0.6f;
                float r = d.hasD ? d.d : WARN_RING_M;
                float rad = d.az * Mathf.Deg2Rad;
                g.transform.position = new Vector3(-r * Mathf.Sin(rad), 0.06f, r * Mathf.Cos(rad));
                g.transform.localScale = d.hasD ? new Vector3(1.0f, 0.03f, 1.0f) : new Vector3(1.6f, 0.03f, 1.6f);
                g.SetActive(true);
            }
        }
        for (int i = used; i < detPool.Count; i++) detPool[i].SetActive(false);
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
        if (player == null) return;
        var style = new GUIStyle(GUI.skin.label) { fontSize = 14, wordWrap = true };
        style.normal.textColor = Color.white;
        // 右上: 凡例（画面幅の 44% まで・行ごとに高さを計算して折り返す）
        float w = Mathf.Min(440f, Screen.width * 0.44f);
        float tw = w - 16f;
        string[] legend = {
            "凡例  立体=実体(GT)  暗い円盤=検出層の出力(D)",
            "薄い色=いるが聞こえていない（無音・ラベル無し）",
            "リング=通知（赤=強 / 橙=中 / 水色=警告）",
            "地面の矢印=歩く向き   街の飾り(V)は見た目だけ" };
        float total = 10f;
        var hs = new float[legend.Length];
        for (int i = 0; i < legend.Length; i++) { hs[i] = style.CalcHeight(new GUIContent(legend[i]), tw) + 2f; total += hs[i]; }
        var old = GUI.color;
        GUI.color = new Color(0f, 0f, 0f, 0.55f);
        GUI.DrawTexture(new Rect(Screen.width - w - 6, 6, w, total + 4f), Texture2D.whiteTexture);
        GUI.color = old;
        float y = 10f;
        for (int i = 0; i < legend.Length; i++) { GUI.Label(new Rect(Screen.width - w + 2, y, tw, hs[i]), legend[i], style); y += hs[i]; }
        if (stateLines.Length == 0) return;
        int idx = Mathf.Clamp(Mathf.FloorToInt(player.PlayTime * 10f), 0, stateLines.Length - 1);
        string txt = player.IsPlaying ? stateLines[idx] : "（Space で再生すると判定が流れます）";
        float bh = style.CalcHeight(new GUIContent("いまの判定: " + txt), Screen.width - 28) + 8f;
        GUI.color = new Color(0f, 0f, 0f, 0.55f);
        GUI.DrawTexture(new Rect(6, Screen.height - bh - 6, Screen.width - 12, bh), Texture2D.whiteTexture);
        GUI.color = old;
        GUI.Label(new Rect(14, Screen.height - bh - 2, Screen.width - 28, bh - 4), "いまの判定: " + txt, style);
    }

    // ---- 8クラスの見た目 --------------------------------------------------------------
    static GameObject Part(GameObject parent, PrimitiveType t, Vector3 pos, Vector3 size, Color c)
    {
        var g = GameObject.CreatePrimitive(t);
        g.transform.SetParent(parent.transform, false);
        g.transform.localPosition = pos; g.transform.localScale = size;
        g.GetComponent<Renderer>().material.color = c;
        return g;
    }

    static void AddLabel(GameObject parent, string text, float height)
    {
        var lab = new GameObject("label");
        lab.transform.SetParent(parent.transform, false);
        lab.transform.localPosition = new Vector3(0, height, 0);
        var tm = lab.AddComponent<TextMesh>();
        tm.text = text; tm.fontSize = 48; tm.characterSize = 0.08f;
        tm.anchor = TextAnchor.MiddleCenter; tm.color = Color.white;
        lab.AddComponent<FaceCamera>();
    }

    GameObject GetOrCreate(string key)
    {
        if (gos.ContainsKey(key)) return gos[key];
        string cls = objClass[key];
        var go = new GameObject(cls);
        Color col; if (!CLS_COLOR.TryGetValue(cls, out col)) col = Color.magenta;
        switch (cls)
        {
            case "car":
            case "horn":
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.5f, 0), new Vector3(1.8f, 0.7f, 4.4f), col);
                Part(go, PrimitiveType.Cube, new Vector3(0, 1.15f, -0.2f), new Vector3(1.6f, 0.6f, 2.2f), col * 0.8f);
                if (cls == "horn") Part(go, PrimitiveType.Sphere, new Vector3(0, 1.9f, 0.6f), Vector3.one * 0.5f, Color.yellow);
                break;
            case "siren":
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.9f, 0), new Vector3(2.0f, 1.8f, 5.2f), Color.white);
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.9f, 0), new Vector3(2.02f, 0.25f, 5.22f), Color.red);   // 赤帯
                Part(go, PrimitiveType.Cube, new Vector3(0, 1.95f, 0.5f), new Vector3(0.8f, 0.2f, 0.3f), Color.red);  // 赤ランプ
                break;
            case "backup_beep":
                Part(go, PrimitiveType.Cube, new Vector3(0, 1.4f, -0.8f), new Vector3(2.3f, 2.6f, 5.0f), Color.gray);   // 荷台
                Part(go, PrimitiveType.Cube, new Vector3(0, 1.0f, 2.4f), new Vector3(2.3f, 1.8f, 1.6f), new Color(0.35f, 0.35f, 0.4f)); // キャブ
                Part(go, PrimitiveType.Sphere, new Vector3(0, 1.0f, -3.4f), Vector3.one * 0.35f, Color.yellow);          // 後退灯
                break;
            case "bike":
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.6f, 0), new Vector3(0.5f, 0.5f, 1.8f), col);
                Part(go, PrimitiveType.Cylinder, new Vector3(0, 0.35f, 0.8f), new Vector3(0.7f, 0.08f, 0.7f), Color.black).transform.localRotation = Quaternion.Euler(0, 0, 90);
                Part(go, PrimitiveType.Cylinder, new Vector3(0, 0.35f, -0.8f), new Vector3(0.7f, 0.08f, 0.7f), Color.black).transform.localRotation = Quaternion.Euler(0, 0, 90);
                Part(go, PrimitiveType.Capsule, new Vector3(0, 1.4f, -0.2f), new Vector3(0.5f, 0.6f, 0.5f), new Color(0.3f, 0.3f, 0.3f));
                break;
            case "kick":
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.15f, 0), new Vector3(0.25f, 0.06f, 1.1f), col);
                Part(go, PrimitiveType.Cylinder, new Vector3(0, 0.9f, 0.5f), new Vector3(0.05f, 0.5f, 0.05f), Color.gray);
                Part(go, PrimitiveType.Capsule, new Vector3(0, 1.2f, 0), new Vector3(0.45f, 0.55f, 0.45f), new Color(0.3f, 0.3f, 0.3f));
                break;
            case "bike_bell":
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.55f, 0), new Vector3(0.15f, 0.1f, 1.4f), col);
                Part(go, PrimitiveType.Cylinder, new Vector3(0, 0.35f, 0.7f), new Vector3(0.7f, 0.05f, 0.7f), Color.black).transform.localRotation = Quaternion.Euler(0, 0, 90);
                Part(go, PrimitiveType.Cylinder, new Vector3(0, 0.35f, -0.7f), new Vector3(0.7f, 0.05f, 0.7f), Color.black).transform.localRotation = Quaternion.Euler(0, 0, 90);
                Part(go, PrimitiveType.Capsule, new Vector3(0, 1.3f, -0.1f), new Vector3(0.45f, 0.55f, 0.45f), new Color(0.3f, 0.3f, 0.3f));
                break;
            case "crossing":
                Part(go, PrimitiveType.Cylinder, new Vector3(0, 1.4f, 0), new Vector3(0.3f, 1.4f, 0.3f), Color.yellow);
                break;
            default:
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.5f, 0), Vector3.one, col);
                break;
        }
        string jp; if (!CLS_JP.TryGetValue(cls, out jp)) jp = cls;
        AddLabel(go, jp, 2.6f);
        gos[key] = go;
        return go;
    }
}

// ラベルを常にカメラへ向ける
public class FaceCamera : MonoBehaviour
{
    void LateUpdate()
    {
        if (Camera.main == null) return;
        transform.rotation = Quaternion.LookRotation(transform.position - Camera.main.transform.position);
    }
}
