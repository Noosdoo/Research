// JoyconDemoPlayer.cs — 通知層の出力をJoy-con振動で体験するデモ v2（2026-09-03）
//
// v1（2026-09-01）からの追加:
//   M : 束ねモード ON/OFF — 同じ手・同じ段の再トリガが MERGE_SEC(1.0s) 以内なら「振動を延長」するだけで
//       新しい通知にしない（機器側で束ねる案。規則は無変更＝cues.csv は生の出力のまま）
//   J : 系列切替の合図 ON/OFF（連続モード時。方位が跳んだら短い2連＋弱いところから立ち上げ直す）
//   G : 連続モード ON/OFF — 車・キック・バイクは <clip>_urgency.csv（予測からの緊急度 0..1）で振動の強さを
//       毎フレーム連続に変える（安全→注意→至近で徐々に強くなる案）。警告音の単発パターンはそのまま
//   P : パンニング ON/OFF — 連続モードで方位に応じて左右の振幅を配分（正面=両手半分、真横=片手のみ）。
//       ⚠️ Joy-con 2本では前後が区別できない（首元4〜6方向デバイスでは隣接振動子の按分にする）
//   H : 画面の黒い表示（左上・凡例・判定）を全部 ON/OFF
//   R : Joy-con の役割割当（前左→前右→後左→後右 の順に、その役で持っている本のボタンを押す）  T : 役割順に1本ずつ震わせて確認
//   B : （Joy-con 4本のとき）前ペア/後ペアの入れ替え
//   4本構成: 接続順で 左1本目=前左(+45°) 右1本目=前右(−45°) 左2本目=後左(+135°) 右2本目=後右(−135°)。
//       連続モードのパンは4方向の按分（cos²の重み）になり、前後が区別できる。2本なら従来の左右按分
//
// 使い方: README_v2.md を参照。←/→ クリップ切替  Space 再生/停止  S 左右入替  M 束ね  G 連続
// 前提: JoyconLib (Looking-Glass)、シーンに JoyconManager が1つ、
//       Assets/StreamingAssets/joycon_demo_v2/<種類別フォルダ>/<日本語名>.wav / _cues.csv / _urgency.csv / _scene.csv
//       （サブフォルダは再帰的に読む。日本語のフォルダ名・ファイル名は Uri エスケープで対応）
//
// 振動の対応（本研究の「危険度=鳴り方」・v1と同じ）:
//   強   = 速い連打 ぶっぶっぶっぶっ（4発・強く・高め）
//   中   = ゆっくり ぶっ…ぶっ（2発・弱く・低め）
//   警告 = 単発の柔らかい ぶーっ

using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;

[RequireComponent(typeof(AudioSource))]
public class JoyconDemoPlayer : MonoBehaviour
{
    struct Cue { public float t; public string side, tier, cls; public float az; }
    struct Urg { public float t, u, az; }

    const float MERGE_SEC = 1.0f;          // 束ね: この時間内の同段再トリガは延長扱い
    const float EXTEND_SEC = 0.45f;        // 束ね: 1回の延長量
    const float URG_MIN = 0.15f;           // 連続: これ未満は無振動

    AudioSource src;
    List<Joycon> joycons;
    readonly List<string> clips = new List<string>();
    readonly List<Cue> cues = new List<Cue>();
    readonly List<Urg> urg = new List<Urg>();
    int clipIdx = 0, nextCue = 0, urgIdx = 0;
    bool swapSides = false, mergeMode = true, gradedMode = true, panMode = true, swapFrontBack = false;   // G は既定 ON（本人採用 2026-09-03）
    string lastFire = "";
    public bool ShowHud = true;      // H キー: 画面の黒い表示を全部 ON/OFF（振動・再生は変わらない）
    string cueSource = "";        // "正解の位置から（オラクル）" / "本物のモデルの検出から"
    static readonly Dictionary<string, string> CLS_JP2 = new Dictionary<string, string> {
        { "car", "車" }, { "siren", "救急車のサイレン" }, { "horn", "クラクション" }, { "backup_beep", "バック音" },
        { "bike_bell", "自転車のベル" }, { "crossing", "踏切" }, { "kick", "キックボード" }, { "bike", "バイク" }, { "train", "列車" } };
    static string Jp(string cls) { string v; return CLS_JP2.TryGetValue(cls, out v) ? v : cls; }
    static string TierJp(string tier) { return tier == "強" ? "強 (至近・4連打)" : (tier == "中" ? "中 (注意・2発)" : "警告 (警告音・単発)"); }
    string dataDir;
    int firedCount = 0, mergedCount = 0;

    // 束ね用: 手ごとの実行中パターン
    class Runner { public string tier; public float endTime, lastFireTime; public Coroutine co; }
    readonly Dictionary<Joycon, Runner> runners = new Dictionary<Joycon, Runner>();
    // 役割（角度）: 前左 +45 / 前右 −45 / 後左 +135 / 後右 −135。R で割当モード（持っている Joy-con のボタンを 前左→前右→後左→後右 の順に押す）
    readonly Dictionary<Joycon, float> roleOf = new Dictionary<Joycon, float>();
    static readonly float[] ROLE_ORDER = { 45f, -45f, 135f, -135f };
    int assignStep = -1;            // -1=割当モードでない, 0..3=次に押すべき役割の番号
    string RoleName(float ang) { return (Mathf.Abs(ang) < 90f ? "前" : "後") + (ang > 0 ? "左" : "右"); }

    // 可視化(ScenarioVisualizer)から読むための公開プロパティ（v1 と同じ名前）
    public string CurrentClip { get { return clips.Count > 0 ? clips[clipIdx] : null; } }
    public float PlayTime { get { return (src != null && src.clip != null) ? src.time : 0f; } }
    public bool IsPlaying { get { return src != null && src.isPlaying; } }
    public string DataDir { get { return dataDir; } }
    public string LastFire { get { return lastFire; } }

    void Start()
    {
        src = GetComponent<AudioSource>();
        joycons = JoyconManager.Instance != null ? JoyconManager.Instance.j : new List<Joycon>();
        dataDir = Path.Combine(Application.streamingAssetsPath, "joycon_demo_v2");
        if (!Directory.Exists(dataDir)) dataDir = Path.Combine(Application.streamingAssetsPath, "joycon_demo");
        // サブフォルダ（種類別・日本語名）も再帰的に拾う。clip = dataDir からの相対パス（区切りは /）
        foreach (var f in Directory.GetFiles(dataDir, "*_cues.csv", SearchOption.AllDirectories))
        {
            string rel = f.Substring(dataDir.Length).TrimStart(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar).Replace(Path.DirectorySeparatorChar, '/');
            clips.Add(rel.Substring(0, rel.Length - "_cues.csv".Length));
        }
        clips.Sort(System.StringComparer.Ordinal);
        if (clips.Count > 0) StartCoroutine(LoadClip(0));
    }

    static bool ParseF(string s, out float v)
    {
        return float.TryParse(s, System.Globalization.NumberStyles.Float,
                              System.Globalization.CultureInfo.InvariantCulture, out v);
    }

    IEnumerator LoadClip(int idx)
    {
        clipIdx = idx; nextCue = 0; urgIdx = 0; src.Stop(); lastFire = ""; firedCount = 0; mergedCount = 0; cueSource = "検出層→通知層";
        cues.Clear(); urg.Clear();
        foreach (var line in File.ReadAllLines(Path.Combine(dataDir, clips[idx] + "_cues.csv")))
        {
            var p = line.Trim().Split(',');
            if (p.Length > 0 && p[0].StartsWith("#"))
            {
                if (line.Contains("本物")) cueSource = "検出層→通知層";
                else if (line.Contains("オラクル")) cueSource = "正解の位置→通知層 (モデル不使用)";
                continue;
            }
            if (p.Length < 5 || p[0] == "t_s") continue;
            float tv, azv;
            if (!ParseF(p[0], out tv)) continue;
            ParseF(p[4], out azv);
            cues.Add(new Cue { t = tv, side = p[1], tier = p[2], cls = p[3], az = azv });
        }
        string upath = Path.Combine(dataDir, clips[idx] + "_urgency.csv");
        if (File.Exists(upath))
            foreach (var line in File.ReadAllLines(upath))
            {
                var p = line.Trim().Split(',');
                float tv, uv, azv;
                if (p.Length < 3 || !ParseF(p[0], out tv) || !ParseF(p[1], out uv)) continue;
                ParseF(p[2], out azv);
                urg.Add(new Urg { t = tv, u = uv, az = azv });
            }
        // 日本語・空白を含むパスでも読めるよう Uri でエスケープする
        string url = new System.Uri(Path.Combine(dataDir, clips[idx] + ".wav")).AbsoluteUri;
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
        if (Input.GetKeyDown(KeyCode.M)) mergeMode = !mergeMode;
        if (Input.GetKeyDown(KeyCode.G)) gradedMode = !gradedMode;
        if (Input.GetKeyDown(KeyCode.P)) panMode = !panMode;
        if (Input.GetKeyDown(KeyCode.B)) swapFrontBack = !swapFrontBack;
        if (Input.GetKeyDown(KeyCode.J)) switchCue = !switchCue;
        if (Input.GetKeyDown(KeyCode.H)) ShowHud = !ShowHud;
        if (Input.GetKeyDown(KeyCode.R)) { roleOf.Clear(); assignStep = joycons.Count > 0 ? 0 : -1; lastFire = joycons.Count > 0 ? "割当: 前左で持っている Joy-con のボタンを押してください" : "Joy-con が接続されていません"; }
        if (Input.GetKeyDown(KeyCode.T)) StartCoroutine(RoleTest());
        AssignTick();
        if (Input.GetKeyDown(KeyCode.Space))
        {
            if (src.isPlaying) { src.Stop(); StopAllRunners(); }
            else if (src.clip != null) { nextCue = 0; urgIdx = 0; lastFire = ""; firedCount = 0; mergedCount = 0; switchCount = 0; switchRampT0 = -10f; lastGradedT = -1f; src.Play(); }
        }
        while (src.isPlaying && nextCue < cues.Count && src.time >= cues[nextCue].t)
            Fire(cues[nextCue++]);
        if (gradedMode && src.isPlaying) GradedTick();
    }

    Joycon HandFor(bool wantLeft)
    {
        foreach (var j in joycons) if (j.isLeft == wantLeft) return j;
        return joycons.Count > 0 ? joycons[0] : null;
    }

    // 方位 az（DCASE: 0°=前, +=左）に一番近い役割の Joy-con を返す。4本なら前左/前右/後左/後右、2本なら左右
    Joycon HandForAz(float az, out string roleName)
    {
        if (joycons.Count >= 4)
        {
            var roles = Roles4();
            Joycon best = null; float bestD = 999f, bestAng = 0f;
            foreach (var kv in roles)
            {
                float d = Mathf.Abs(Mathf.DeltaAngle(az, kv.Value));
                if (d < bestD) { bestD = d; best = kv.Key; bestAng = kv.Value; }
            }
            float a = swapSides ? -bestAng : bestAng;
            roleName = (Mathf.Abs(a) < 90f ? "前" : "後") + (a > 0 ? "左" : "右");
            return best;
        }
        bool wantLeft = (az > 0) ^ swapSides;
        roleName = wantLeft ? "左手" : "右手";
        return HandFor(wantLeft);
    }

    void Fire(Cue c)
    {
        bool isDist = (c.tier == "強" || c.tier == "中");
        // 連続モードでは距離クラスの離散通知は出さない（緊急度で連続に振動する）。警告音は従来どおり
        if (gradedMode && isDist) { lastFire = $"{c.t:F1} 秒 {TierJp(c.tier)} {Jp(c.cls)} → 連続モード中なので段階の振動は出さず、緊急度で震えます"; return; }

        // 通知の方位で担当の Joy-con を決める（4本: 前左/前右/後左/後右、2本: 左右）
        string role;
        Joycon jc = HandForAz(c.az, out role);
        // 束ね: 同じ段の再トリガが MERGE_SEC 以内 → 新しい連打を出さず延長だけ。担当が別の Joy-con に移った場合は
        // 振動をそちらへ移す（方向は更新するが「ぶっぶっ」の頭出しはしない）
        Runner r;
        if (mergeMode && isDist && jc != null)
        {
            Joycon prevJc = null; Runner prev = null;
            foreach (var kv in runners)
                if (kv.Value.tier == c.tier && (src.time - kv.Value.lastFireTime) < MERGE_SEC && (prev == null || kv.Value.lastFireTime > prev.lastFireTime))
                { prevJc = kv.Key; prev = kv.Value; }
            if (prev != null)
            {
                mergedCount++;
                if (prevJc == jc)
                {
                    prev.endTime = Mathf.Max(prev.endTime, src.time) + EXTEND_SEC;
                    prev.lastFireTime = src.time;
                    lastFire = $"{c.t:F1} 秒 {role} {TierJp(c.tier)} {Jp(c.cls)} → 束ねた (同じ通知が続いたので +{EXTEND_SEC:F1} 秒伸ばしただけ)";
                }
                else
                {
                    if (prev.co != null) StopCoroutine(prev.co);
                    runners.Remove(prevJc);
                    var mv = new Runner { tier = c.tier, lastFireTime = src.time,
                                          endTime = Mathf.Max(prev.endTime, src.time) + EXTEND_SEC, };
                    runners[jc] = mv;
                    mv.co = StartCoroutine(PatternUntil(jc, mv, true));
                    lastFire = $"{c.t:F1} 秒 {role} {TierJp(c.tier)} {Jp(c.cls)} → 束ねた (担当の Joy-con を移して伸ばした)";
                }
                return;
            }
        }
        firedCount++;
        lastFire = $"{c.t:F1} 秒 {role} {TierJp(c.tier)} {Jp(c.cls)} (方位 {c.az:F0}°、0=前 +=左)";
        if (jc == null) return;                       // Joy-con未接続でも画面表示だけ動く
        if (!isDist) { jc.SetRumble(120f, 240f, 0.5f, 300); return; }   // 警告 = 単発
        if (runners.TryGetValue(jc, out r) && r.co != null) StopCoroutine(r.co);
        r = new Runner { tier = c.tier, lastFireTime = src.time,
                         endTime = src.time + (c.tier == "強" ? 0.72f : 0.78f) };
        runners[jc] = r;
        r.co = StartCoroutine(PatternUntil(jc, r));
    }

    // 段ごとのパルスを endTime まで繰り返す（束ねで endTime が伸びれば続く）
    IEnumerator PatternUntil(Joycon jc, Runner r, bool continued = false)
    {
        if (continued) yield return new WaitForSeconds(0.05f);      // 移動時は頭出しを避けて滑らかにつなぐ
        while (src.isPlaying && src.time < r.endTime)
        {
            if (r.tier == "強") { jc.SetRumble(320f, 640f, 1.0f, 110); yield return new WaitForSeconds(0.18f); }
            else { jc.SetRumble(80f, 160f, 0.4f, 90); yield return new WaitForSeconds(0.39f); }
        }
        r.co = null;
    }

    void StopAllRunners()
    {
        foreach (var kv in runners) if (kv.Value.co != null) StopCoroutine(kv.Value.co);
        runners.Clear();
    }

    // 連続モード: 緊急度 0..1 で振幅・周波数を毎フレーム更新（安全→注意→至近で徐々に強く）
    float lastGradedU = 0f;
    // 系列切替の合図（J キー・既定ON）: 緊急度が続いているのに方位が 0.3 秒以内に 60° 以上跳んだ＝追跡が別の車に乗り移った
    // → 新しい側で短い2連の合図を出し、連続振動を弱いところから立ち上げ直す（「別の車が来た」と伝える）
    bool switchCue = true; int switchCount = 0; float switchRampT0 = -10f; float lastGradedAz = 0f, lastGradedT = -1f;
    void GradedTick()
    {
        while (urgIdx + 1 < urg.Count && urg[urgIdx + 1].t <= src.time) urgIdx++;
        if (urg.Count == 0) return;
        var g = urg[urgIdx];
        bool jumped = g.u >= URG_MIN && lastGradedU >= URG_MIN && lastGradedT >= 0f && src.time - lastGradedT < 0.3f
                      && Mathf.Abs(Mathf.DeltaAngle(g.az, lastGradedAz)) > 60f;
        lastGradedU = g.u; lastGradedAz = g.az; lastGradedT = src.time;
        if (jumped && switchCue)
        {
            switchCount++; switchRampT0 = src.time;
            string roleN;
            Joycon jn = HandForAz(g.az, out roleN);
            if (jn != null) StartCoroutine(SwitchPulse(jn));   // 0.2 秒の合図。束ねの Runner とは別管理
        }
        if (g.u < URG_MIN) return;
        if (src.time - switchRampT0 < 0.25f) return;           // 合図の間は連続振動を止める
        float ramp = Mathf.Clamp01((src.time - switchRampT0 - 0.25f) / 0.6f);   // 切替後 0.6 秒で立ち上げ直す
        float amp = (0.25f + 0.75f * g.u) * Mathf.Lerp(0.3f, 1f, ramp);   // 0.25(注意の入口)〜1.0(至近)
        float lo = Mathf.Lerp(80f, 320f, g.u), hi = Mathf.Lerp(160f, 640f, g.u);
        if (!panMode)
        {
            string roleC;
            Joycon jc = HandForAz(g.az, out roleC);
            if (jc != null) jc.SetRumble(lo, hi, amp, 120);   // 毎フレーム上書き＝連続振動
            return;
        }
        if (joycons.Count >= 4)
        {
            // 4方向按分: 各振動子の角度 θk（前左+45/前右−45/後左+135/後右−135）に cos²(az−θk) の重み
            var roles = Roles4();
            float sum = 0f; var w = new float[roles.Count];
            for (int k = 0; k < roles.Count; k++)
            {
                float c = Mathf.Cos((g.az - roles[k].Value) * Mathf.Deg2Rad);
                w[k] = c > 0 ? c * c : 0f; sum += w[k];
            }
            for (int k = 0; k < roles.Count; k++)
            {
                float a = sum > 0 ? amp * w[k] / sum * 1.6f : 0f;
                if (a >= 0.08f) roles[k].Key.SetRumble(lo, hi, Mathf.Clamp01(a), 120);
            }
            return;
        }
        // 2本: 方位 az（DCASE規約: +=左）を sin で左右に配分。正面/背後は両手半分ずつ（前後は2本では区別不可）
        float sL = 0.5f * (1f + Mathf.Sin(g.az * Mathf.Deg2Rad));
        float sR = 1f - sL;
        if (swapSides) { float t = sL; sL = sR; sR = t; }
        foreach (var j in joycons)
        {
            float wj = j.isLeft ? sL : sR;
            if (wj * amp >= 0.08f) j.SetRumble(lo, hi, Mathf.Clamp01(wj * amp * 1.4f), 120);
        }
    }

    IEnumerator SwitchPulse(Joycon jc)
    {
        for (int i = 0; i < 2; i++)
        {
            jc.SetRumble(400f, 800f, 1.0f, 70);
            yield return new WaitForSeconds(0.11f);
        }
    }

    // 4本の役割割当（接続順・isLeft から）。B で前後ペアを入れ替え
    List<KeyValuePair<Joycon, float>> Roles4()
    {
        var roles = new List<KeyValuePair<Joycon, float>>();
        if (roleOf.Count >= 4)
        {
            // R で本人が決めた割当を使う（B/S の入替もその上に掛かる）
            foreach (var kv in roleOf)
            {
                float a = kv.Value;
                if (swapFrontBack) a = (a > 0 ? 180f - a : -180f - a);
                if (swapSides) a = -a;
                roles.Add(new KeyValuePair<Joycon, float>(kv.Key, a));
            }
            return roles;
        }
        // 未割当: 接続順（HID の列挙順なので持ち方と合わないことがある → R で割り当て直す）
        var lefts = new List<Joycon>(); var rights = new List<Joycon>();
        foreach (var j in joycons) (j.isLeft ? lefts : rights).Add(j);
        float fl = 45f, fr = -45f, bl = 135f, br = -135f;
        if (swapFrontBack) { fl = 135f; fr = -135f; bl = 45f; br = -45f; }
        if (swapSides) { fl = -fl; fr = -fr; bl = -bl; br = -br; }
        if (lefts.Count > 0) roles.Add(new KeyValuePair<Joycon, float>(lefts[0], fl));
        if (rights.Count > 0) roles.Add(new KeyValuePair<Joycon, float>(rights[0], fr));
        if (lefts.Count > 1) roles.Add(new KeyValuePair<Joycon, float>(lefts[1], bl));
        if (rights.Count > 1) roles.Add(new KeyValuePair<Joycon, float>(rights[1], br));
        return roles;
    }

    static readonly Joycon.Button[] ANY_BUTTONS = {
        Joycon.Button.SHOULDER_1, Joycon.Button.SHOULDER_2, Joycon.Button.SL, Joycon.Button.SR,
        Joycon.Button.DPAD_UP, Joycon.Button.DPAD_DOWN, Joycon.Button.DPAD_LEFT, Joycon.Button.DPAD_RIGHT,
        Joycon.Button.STICK, Joycon.Button.PLUS, Joycon.Button.MINUS };
    bool AnyButtonDown(Joycon j)
    {
        foreach (var b in ANY_BUTTONS) if (j.GetButtonDown(b)) return true;
        return false;
    }

    // 割当モード: 画面の指示どおりに、その役割で持っている Joy-con のボタンを押す。押した本を 0.3 秒震わせて確認
    void AssignTick()
    {
        if (assignStep < 0) return;
        foreach (var j in joycons)
        {
            if (roleOf.ContainsKey(j) || !AnyButtonDown(j)) continue;
            roleOf[j] = ROLE_ORDER[assignStep];
            j.SetRumble(160f, 320f, 0.8f, 300);
            assignStep++;
            if (assignStep >= Mathf.Min(4, joycons.Count)) { assignStep = -1; lastFire = "割当完了: " + RoleSummary(); }
            break;
        }
    }

    string RoleSummary()
    {
        var parts = new List<string>();
        foreach (var kv in Roles4()) parts.Add($"{RoleName(kv.Value)}={(kv.Key.isLeft ? "L" : "R")}");
        return string.Join(" ", parts);
    }

    // T: 役割の順に 1 本ずつ震わせる（前左→前右→後左→後右）。どれがどれか手で確かめる
    IEnumerator RoleTest()
    {
        var roles = Roles4();
        roles.Sort((a, b) => System.Array.IndexOf(ROLE_ORDER, Mathf.Round(a.Value)).CompareTo(System.Array.IndexOf(ROLE_ORDER, Mathf.Round(b.Value))));
        foreach (var kv in roles)
        {
            lastFire = $"テスト: {RoleName(kv.Value)} が震えます";
            kv.Key.SetRumble(200f, 400f, 1.0f, 500);
            yield return new WaitForSeconds(0.9f);
        }
        lastFire = "テスト終了: " + RoleSummary();
    }

    // 画面の文字: 左上に半透明の箱をひとつ（幅は画面の 55% まで・折り返し）。右上は ScenarioVisualizer の凡例が使う
    float T { get { return (src != null && src.clip != null) ? src.time : 0f; } }
    void OnGUI()
    {
        if (!ShowHud)
        {
            var tiny = new GUIStyle(GUI.skin.label) { fontSize = 12 };
            tiny.normal.textColor = new Color(1f, 1f, 1f, 0.6f);
            GUI.Label(new Rect(8, 6, 400, 20), $"H: 表示を戻す   場面 {clipIdx + 1}/{clips.Count}   再生 {T:F1} 秒", tiny);
            return;
        }
        // 左上の操作パネル: 行ごとに高さを計算して折り返す（画面幅の 52% まで。右上の凡例と重ならない）
        int fs = 14;
        GUIStyle st = null, hd = null;
        float w = Mathf.Min(900f, Screen.width * 0.60f);
        float tw = w - 20f;
        List<KeyValuePair<string, GUIStyle>> items = null;
        float[] hs = null; float total = 0f;
        int nCue = 0;
        for (int attempt = 0; attempt < 4; attempt++)
        {
            st = new GUIStyle(GUI.skin.label) { fontSize = fs, wordWrap = true, richText = true };
            st.normal.textColor = Color.white;
            hd = new GUIStyle(st) { fontSize = fs + 2, fontStyle = FontStyle.Bold };
            items = BuildPanelItems(st, hd, out nCue);
            total = 12f;
            hs = new float[items.Count];
            for (int i = 0; i < items.Count; i++) { hs[i] = items[i].Value.CalcHeight(new GUIContent(items[i].Key), tw) + 3f; total += hs[i]; }
            if (gradedMode) total += 30f;
            if (total + 12f <= Screen.height - 70f) break;   // 下の「いまの判定」パネルの分を空けて収める
            fs -= 1;                                          // 収まらなければ 1 段小さく（14→13→12→11）
        }
        {
        }
        DrawPanel(items, hs, total, w, tw, st);
    }

    List<KeyValuePair<string, GUIStyle>> BuildPanelItems(GUIStyle st, GUIStyle hd, out int nCue)
    {
        var items = new List<KeyValuePair<string, GUIStyle>>();
        items.Add(new KeyValuePair<string, GUIStyle>($"場面 {clipIdx + 1}/{clips.Count}: {(clips.Count > 0 ? clips[clipIdx].Replace("/", " › ") : "なし")}", hd));
        items.Add(new KeyValuePair<string, GUIStyle>("通知の元: " + (cueSource == "" ? "(読込中)" : cueSource), st));
        items.Add(new KeyValuePair<string, GUIStyle>(
            $"Joy-con: {joycons.Count}本" + (joycons.Count >= 4 ? $"  役割 [{RoleSummary()}]   R=役割を決め直す  T=順に震わせて確認" : (joycons.Count > 0 ? " (左=左手・右=右手)" : " (未接続。画面だけ動きます)")), st));
        if (assignStep >= 0)
            items.Add(new KeyValuePair<string, GUIStyle>($"★ 割当中: 「{RoleName(ROLE_ORDER[assignStep])}」で持っている Joy-con のボタン (ZL/ZR/SL/SR/十字/スティック押込) を押してください ({assignStep + 1}/{Mathf.Min(4, joycons.Count)})", hd));
        items.Add(new KeyValuePair<string, GUIStyle>("設定:", st));
        items.Add(new KeyValuePair<string, GUIStyle>($"  M 束ね={(mergeMode ? "ON" : "OFF")} (1秒以内の同じ通知は伸ばすだけ)", st));
        items.Add(new KeyValuePair<string, GUIStyle>($"  G 連続={(gradedMode ? "ON" : "OFF")} (近づくほど強く震える)", st));
        items.Add(new KeyValuePair<string, GUIStyle>($"  P 方向按分={(panMode ? "ON" : "OFF")} (方位に応じて複数の本に振り分ける)", st));
        items.Add(new KeyValuePair<string, GUIStyle>($"  J 切替の合図={(switchCue ? "ON" : "OFF")} (追跡が別の車に乗り移ったら短い2連)", st));
        items.Add(new KeyValuePair<string, GUIStyle>($"  S 左右入替={(swapSides ? "ON" : "OFF")}" + (joycons.Count >= 4 ? $"   B 前後入替={(swapFrontBack ? "ON" : "OFF")}" : ""), st));
        items.Add(new KeyValuePair<string, GUIStyle>("操作: ←/→ 場面を変える   Space 再生/停止", st));
        items.Add(new KeyValuePair<string, GUIStyle>($"再生 {T:F1} 秒   振動した回数 {firedCount}   束ねた回数 {mergedCount}", st));
        items.Add(new KeyValuePair<string, GUIStyle>($"切替の合図 {switchCount} 回" + (gradedMode ? $"   緊急度 {lastGradedU:F2} (0=安全 1=至近)" : ""), st));
        items.Add(new KeyValuePair<string, GUIStyle>("最後の通知: " + (lastFire == "" ? "—" : lastFire), st));
        items.Add(new KeyValuePair<string, GUIStyle>("この場面の通知一覧 (✓=済)  強=至近・4連打", st));
        items.Add(new KeyValuePair<string, GUIStyle>("中=注意・2発  警告=警告音・単発", st));
        nCue = Mathf.Min(cues.Count, 8);
        for (int i = 0; i < nCue; i++)
            items.Add(new KeyValuePair<string, GUIStyle>(
                $"{(i < nextCue && src.isPlaying ? "✓" : "　")} {cues[i].t:F1} 秒  {(cues[i].side == "L" ? "左" : "右")}  {cues[i].tier}  {Jp(cues[i].cls)}", st));
        if (cues.Count > 8) items.Add(new KeyValuePair<string, GUIStyle>($"… 他 {cues.Count - 8} 件", st));
        return items;
    }

    void DrawPanel(List<KeyValuePair<string, GUIStyle>> items, float[] hs, float total, float w, float tw, GUIStyle st)
    {
        var old = GUI.color;
        GUI.color = new Color(0f, 0f, 0f, 0.55f);
        GUI.DrawTexture(new Rect(6, 6, w, total + 6f), Texture2D.whiteTexture);
        GUI.color = old;
        float x = 14f, y = 12f;
        for (int i = 0; i < items.Count; i++)
        {
            GUI.Label(new Rect(x, y, tw, hs[i]), items[i].Key, items[i].Value);
            y += hs[i];
        }
        if (gradedMode)
        {
            GUI.Label(new Rect(x, y, 200, 22), "緊急度 (連続モードの振動の強さ)", st);
            GUI.color = new Color(1f, 1f, 1f, 0.25f);
            GUI.DrawTexture(new Rect(x + 190, y + 4, 204, 14), Texture2D.whiteTexture);
            GUI.color = new Color(1f, 0.45f, 0.2f, 0.95f);
            GUI.DrawTexture(new Rect(x + 192, y + 6, 200f * Mathf.Clamp01(lastGradedU), 10), Texture2D.whiteTexture);
            GUI.color = old;
        }
    }
}
