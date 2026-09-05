// Layout-driven Japanese streets; GT, detections and notification timing are unchanged.
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
    JapaneseStreetscape streets;
    int cameraMode;
    float cameraZoom = 1f;
    Vector2 legendScroll, stateScroll;
    float observerGround;
    // 歩行: 歩行者は画面中央に固定し、街（車線・飾り・地図）を後ろへ流す。配置図は「5 秒時点の歩行者」基準で描いてある
    float walkDir = 0f, walkSpeed = 0f;
    GameObject worldRoot;            // _layout.csv に map 行があれば実地図（OSM）を描き、合成の車線・飾りは出さない   // _layout.csv に本物の交差道路（xlane）があればその前方距離。飾りの交差点はそこに合わせる
    const float WARN_RING_M = 15f;
    readonly List<GameObject> decoGos = new List<GameObject>();

    static readonly Dictionary<string, Color> CLS_COLOR = new Dictionary<string, Color> {
        {"car", new Color(0.2f, 0.45f, 1f)}, {"siren", Color.white}, {"backup_beep", Color.gray},
        {"horn", new Color(1f, 0.85f, 0.2f)}, {"bike", new Color(1f, 0.55f, 0.1f)}, {"kick", Color.cyan},
        {"bike_bell", Color.green}, {"crossing", Color.yellow}, {"train", new Color(.70f,.73f,.72f)} };
    static readonly Dictionary<string, string> CLS_JP = new Dictionary<string, string> {
        {"car", "車"}, {"siren", "救急車"}, {"backup_beep", "バック車"}, {"horn", "クラクション"},
        {"bike", "バイク"}, {"kick", "キック"}, {"bike_bell", "自転車ベル"}, {"crossing", "踏切"}, {"train", "列車"} };

    void Start()
    {
        player = FindAnyObjectByType<JoyconDemoPlayer>();

        JapaneseStreetscape.ConfigureLighting();

        pedestrian = GameObject.CreatePrimitive(PrimitiveType.Capsule);
        pedestrian.transform.localScale = new Vector3(.44f,.85f,.44f);
        pedestrian.transform.position = new Vector3(0, .99f, 0);
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
        flashRing.transform.position = new Vector3(0, 0.20f, 0);
        flashRing.transform.localScale = new Vector3(3f, 0.02f, 3f);
        flashRing.SetActive(false);

        var cam = Camera.main;
        if (cam != null)
        {
            cam.nearClipPlane = .10f; cam.farClipPlane = 350;
            cam.backgroundColor = new Color(.73f, .78f, .80f);
            cam.clearFlags = CameraClearFlags.SolidColor;
            UpdateCamera();
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
        gos.Clear(); tracks.Clear(); objClass.Clear(); layoutGos.Clear(); dets.Clear(); decoGos.Clear(); baseColor.Clear(); dimState.Clear();

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

    void BuildLayout(string path)
    {
        streets = JapaneseStreetscape.Build(path);
        layoutGos.Add(streets.gameObject);
        walkDir = streets.WalkDirection; walkSpeed = streets.WalkSpeed;
        streets.SetDecorations(showDeco);
        walkArrow.SetActive(walkDir != 0f && walkSpeed > 0f);
        walkArrow.transform.position = new Vector3(0, .20f, walkDir * 2f);
    }

    void UpdateCamera()
    {
        var cam = Camera.main; if (cam == null) return;
        cam.orthographic = cameraMode == 2;
        if (cameraMode == 1)
        {
            cam.transform.position = new Vector3(0, 1.68f + observerGround, -.25f);
            cam.transform.rotation = Quaternion.Euler(3, 0, 0); cam.fieldOfView = 72;
        }
        else
        {
            cam.transform.position = cameraMode == 2 ? new Vector3(0, 48 * cameraZoom, -1) : new Vector3(0, 25 * cameraZoom, -29 * cameraZoom);
            cam.transform.LookAt(new Vector3(0, 0, cameraMode == 2 ? 0 : 7));
            cam.fieldOfView = 52; cam.orthographicSize = 30 * cameraZoom;
        }
        if (pedestrian != null) foreach (var renderer in pedestrian.GetComponentsInChildren<Renderer>()) renderer.enabled = cameraMode != 1;
    }

    // ---- 毎フレーム ---------------------------------------------------------------
    // 無音・ラベル無しの間は色を落として「そこにいるが聞こえていない」ことを示す（消さない）
    void ApplyDim(string key, GameObject go, int vis)
    {
        int cur; if (dimState.TryGetValue(key, out cur) && cur == vis) return;
        dimState[key] = vis;
        foreach (var r in go.GetComponentsInChildren<Renderer>())
        {
            if (r.GetComponent<TextMesh>() != null) continue;
            Color c0;
            if (!baseColor.TryGetValue(r, out c0)) { c0 = r.material.color; baseColor[r] = c0; }
            r.material.color = vis == 1 ? c0 : new Color(c0.r * 0.45f, c0.g * 0.45f, c0.b * 0.45f, c0.a);
        }
    }

    void Update()
    {
        if (player == null) return;
        if (Input.GetKeyDown(KeyCode.D)) showDet = !showDet;
        if (Input.GetKeyDown(KeyCode.V)) { showDeco = !showDeco; if (streets != null) streets.SetDecorations(showDeco); }
        if (Input.GetKeyDown(KeyCode.C)) { cameraMode = (cameraMode + 1) % 3; UpdateCamera(); }
        float scroll = Input.mouseScrollDelta.y;
        if (Mathf.Abs(scroll) > .01f && (!player.ShowHud || !DemoHudLayout.MouseOverPanel())) { cameraZoom = Mathf.Clamp(cameraZoom - scroll * .08f, .45f, 1.8f); UpdateCamera(); }
        var clip = player.CurrentClip;
        if (clip != null && clip != loadedClip) LoadScene(clip);

        float now = player.PlayTime;
        bool playing = player.IsPlaying;
        if (worldRoot != null)
            worldRoot.transform.position = (walkDir != 0f && walkSpeed > 0f)
                ? new Vector3(0f, 0f, -walkDir * walkSpeed * (now - 5f)) : Vector3.zero;
        if (streets != null)
        {
            float routeZ = walkDir * walkSpeed * (now - 5f);
            observerGround = streets.ObserverGroundHeight(routeZ);
            pedestrian.transform.position = new Vector3(0, observerGround + .85f, 0);
            walkArrow.transform.position = new Vector3(0, observerGround + .025f, walkDir * 2f);
            if (cameraMode == 1) UpdateCamera();
        }
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
                g.transform.position = new Vector3(-r * Mathf.Sin(rad), 0.20f, r * Mathf.Cos(rad));
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
        if (player == null || !player.ShowHud) return;
        var style = new GUIStyle(GUI.skin.label) { fontSize = 14, wordWrap = true };
        style.normal.textColor = Color.white;
        var panels = DemoHudLayout.Current;
        string legend = "立体：実体 (GT)　円盤：検出 (D)\n薄い色：無音・ラベルなし\n通知リング：赤=強 / 橙=中 / 水色=警告\nC：視点　V：街の表示　H：情報表示\nホイール：街を拡縮 / パネル内をスクロール";
        DemoHudLayout.TextPanel(panels.legend, legend, style, ref legendScroll);
        string state = "← / →：場面切替　Space：再生 / 停止";
        if (stateLines.Length > 0)
        {
            int idx = Mathf.Clamp(Mathf.FloorToInt(player.PlayTime * 10f), 0, stateLines.Length - 1);
            state = player.IsPlaying ? "いまの判定：" + stateLines[idx] : state;
        }
        DemoHudLayout.TextPanel(panels.state, state, style, ref stateScroll);
    }

    // ---- 8クラスの見た目 --------------------------------------------------------------
    static GameObject Part(GameObject parent, PrimitiveType t, Vector3 pos, Vector3 size, Color c)
    {
        var g = GameObject.CreatePrimitive(t);
        g.transform.SetParent(parent.transform, false);
        g.transform.localPosition = pos; g.transform.localScale = size;
        var material = new Material(Shader.Find("Standard")) { color = c };
        material.SetFloat("_Glossiness", .28f);
        g.GetComponent<Renderer>().sharedMaterial = material;
        var owner = parent.GetComponent<StreetVehicleMaterials>();
        if (owner == null) owner = parent.AddComponent<StreetVehicleMaterials>();
        owner.Own(material);
        var collider = g.GetComponent<Collider>();
        if (collider != null) { if (Application.isPlaying) Destroy(collider); else DestroyImmediate(collider); }
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
        if (cls == "car_drive") cls = "car";
        Color col; if (!CLS_COLOR.TryGetValue(cls, out col)) col = Color.magenta;
        if (cls == "car" && streets != null && streets.LayoutPath.Contains("バス停")) cls = "bus";
        switch (cls)
        {
            case "car":
            case "horn":
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.5f, 0), new Vector3(1.8f, 0.7f, 4.4f), col);
                Part(go, PrimitiveType.Cube, new Vector3(0, 1.15f, -0.2f), new Vector3(1.6f, 0.6f, 2.2f), new Color(.18f, .28f, .33f));
                Part(go, PrimitiveType.Cube, new Vector3(0, 1.48f, -.2f), new Vector3(1.62f, .08f, 2.05f), col);
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
            case "bus":
                Part(go, PrimitiveType.Cube, new Vector3(0,1.65f,0), new Vector3(2.45f,2.6f,10.2f), new Color(.79f,.81f,.75f));
                Part(go, PrimitiveType.Cube, new Vector3(0,1.12f,0), new Vector3(2.47f,.32f,10.22f), new Color(.22f,.40f,.39f));
                Part(go, PrimitiveType.Cube, new Vector3(0,2.15f,5.115f), new Vector3(2.12f,1.12f,.025f), new Color(.16f,.26f,.31f));
                Part(go, PrimitiveType.Cube, new Vector3(0,2.86f,5.115f), new Vector3(1.6f,.22f,.025f), new Color(.12f,.15f,.15f));
                for (int side=-1;side<=1;side+=2)
                {
                    for(float z=-4;z<=4;z+=1.45f)
                        Part(go,PrimitiveType.Cube,new Vector3(side*1.238f,2.12f,z),new Vector3(.025f,1.05f,1.18f),new Color(.16f,.26f,.31f));
                    foreach(float z in new[]{-3.25f,3.0f})
                    {
                        Part(go,PrimitiveType.Cylinder,new Vector3(side*1.14f,.49f,z),new Vector3(.96f,.16f,.96f),Color.black).transform.localRotation=Quaternion.Euler(0,0,90);
                        Part(go,PrimitiveType.Cylinder,new Vector3(side*1.31f,.49f,z),new Vector3(.58f,.025f,.58f),Color.gray).transform.localRotation=Quaternion.Euler(0,0,90);
                    }
                    Part(go,PrimitiveType.Cube,new Vector3(side*.86f,.83f,5.13f),new Vector3(.33f,.21f,.025f),new Color(.93f,.93f,.80f));
                }
                Part(go,PrimitiveType.Cube,new Vector3(-1.248f,1.40f,3.8f),new Vector3(.027f,2.15f,.95f),new Color(.25f,.28f,.28f));
                break;
            case "train":
                go.transform.position = Vector3.up * (streets != null ? streets.TrainHeight : 0f);
                for (int coach = -1; coach <= 1; coach++)
                {
                    float z = coach * 19.5f;
                    Part(go, PrimitiveType.Cube, new Vector3(0, 1.85f, z), new Vector3(2.8f, 2.85f, 19f), new Color(.72f,.75f,.73f));
                    Part(go, PrimitiveType.Cube, new Vector3(0, 1.27f, z), new Vector3(2.82f, .24f, 19.02f), new Color(.18f,.39f,.37f));
                    Part(go, PrimitiveType.Cube, new Vector3(0, .45f, z), new Vector3(2.3f,.55f,17f), new Color(.19f,.20f,.20f));
                    for (int side = -1; side <= 1; side += 2)
                    {
                        for (float wz = -8; wz <= 8; wz += 2)
                            Part(go, PrimitiveType.Cube, new Vector3(side*1.411f,2.30f,z+wz), new Vector3(.025f,.95f,1.25f), new Color(.16f,.26f,.30f));
                        for (int end = -1; end <= 1; end += 2)
                            Part(go, PrimitiveType.Cylinder, new Vector3(side*1.12f,.42f,z+end*6), new Vector3(.75f,.13f,.75f), Color.black).transform.localRotation=Quaternion.Euler(0,0,90);
                    }
                    Part(go, PrimitiveType.Cube, new Vector3(0,3.42f,z), new Vector3(1.6f,.30f,2.4f), Color.gray);
                }
                for (int end = -1; end <= 1; end += 2)
                    Part(go, PrimitiveType.Cube, new Vector3(0,2.3f,end*29.01f), new Vector3(2.5f,.95f,.025f), new Color(.16f,.26f,.30f));
                break;
            case "crossing":
                Part(go, PrimitiveType.Cylinder, new Vector3(0, 1.4f, 0), new Vector3(0.3f, 1.4f, 0.3f), Color.yellow);
                break;
            default:
                Part(go, PrimitiveType.Cube, new Vector3(0, 0.5f, 0), Vector3.one, col);
                break;
        }
        if (cls == "car" || cls == "horn" || cls == "siren" || cls == "backup_beep")
        {
            float width = cls == "backup_beep" ? 2.3f : cls == "siren" ? 2f : 1.8f;
            float front = cls == "backup_beep" ? 3.21f : cls == "siren" ? 2.61f : 2.21f;
            float back = cls == "backup_beep" ? -3.31f : -front;
            Color glass = new Color(.16f,.26f,.31f), metal = new Color(.55f,.59f,.60f);
            for (int side = -1; side <= 1; side += 2)
            {
                foreach (float axle in new [] {front - .85f, back + .9f})
                {
                    Part(go, PrimitiveType.Cylinder, new Vector3(side*width*.48f,.35f,axle), new Vector3(.68f,.14f,.68f), new Color(.07f,.08f,.08f)).transform.localRotation=Quaternion.Euler(0,0,90);
                    Part(go, PrimitiveType.Cylinder, new Vector3(side*(width*.48f+.15f),.35f,axle), new Vector3(.39f,.022f,.39f), metal).transform.localRotation=Quaternion.Euler(0,0,90);
                }
                Part(go, PrimitiveType.Cube, new Vector3(side*width*.36f,.72f,front), new Vector3(.38f,.18f,.035f), new Color(.94f,.94f,.78f));
                Part(go, PrimitiveType.Cube, new Vector3(side*width*.36f,.75f,back), new Vector3(.26f,.19f,.035f), new Color(.72f,.12f,.09f));
                Part(go, PrimitiveType.Cube, new Vector3(side*(width*.5f+.12f),1.19f,front-1.5f), new Vector3(.24f,.14f,.28f), col);
                Part(go, PrimitiveType.Cube, new Vector3(side*(width*.5f+.012f),.90f,-.25f), new Vector3(.025f,.045f,.20f), metal);
                if (cls == "car" || cls == "horn")
                    Part(go, PrimitiveType.Cube, new Vector3(side*.81f,1.15f,-.15f), new Vector3(.05f,.62f,.10f), col);
                else
                    Part(go, PrimitiveType.Cube, new Vector3(side*(width*.5f+.014f),1.45f,front-.75f), new Vector3(.025f,.60f,1.05f), glass);
            }
            Part(go, PrimitiveType.Cube, new Vector3(0,.41f,front), new Vector3(width*.9f,.14f,.07f), metal);
            Part(go, PrimitiveType.Cube, new Vector3(0,.59f,front+.04f), new Vector3(.42f,.18f,.025f), Color.white);
            if (cls == "siren" || cls == "backup_beep")
                Part(go, PrimitiveType.Cube, new Vector3(0,1.44f,front+.005f), new Vector3(width*.85f,.60f,.025f), glass);
        }
        string jp; if (!CLS_JP.TryGetValue(cls, out jp)) jp = cls == "bus" ? "バス" : cls;
        AddLabel(go, jp, cls == "train" ? 4.2f : 2.6f);
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

// Each moving object owns its colour instances; scene switching releases them.
public sealed class StreetVehicleMaterials : MonoBehaviour
{
    readonly List<Material> owned = new List<Material>();
    public void Own(Material material) { owned.Add(material); }
    void OnDestroy()
    {
        foreach (var material in owned) if (material != null)
        { if (Application.isPlaying) Destroy(material); else DestroyImmediate(material); }
    }
}
