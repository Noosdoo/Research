# Joy-conデモ セットアップ手順（あなたの作業・30〜60分）

ゴール: イヤホンで街の音を聞きながらJoy-conを両手に握ると、
**車が近づくと該当する側の手が震える**（中身は採用済みv4.2＋警告音holdの本物の出力）。

## 0. このフォルダの中身

- `fold31_room1_mixXXXX.wav` … 試聴用ステレオ音声（5本。性格は manifest.md 参照）
- `fold31_room1_mixXXXX_cues.csv` … 振動キュー（何秒に・どっち側に・強/中/警告）
- `unity/JoyconDemoPlayer.cs` … Unity用スクリプト（完成品・編集不要）
- `manifest.md` … 各クリップの説明と全キュー一覧

## 1. Joy-conをWindowsにペアリング（5分）

1. Joy-con側面の**丸い小さなシンクロボタンを長押し**（ランプが流れる）
2. Windows設定 → Bluetoothとデバイス → デバイスの追加 → Bluetooth →
   「Joy-Con (L)」を選ぶ。**(R)も同様に**。2本とも「接続済み」になればOK
3. ⚠️ 一度Switch本体に挿すとペアリングが切れる。デモ期間はPC専属にする

## 2. Unityの準備（20〜30分・ほぼ待ち時間）

1. [Unity Hub](https://unity.com/download) をインストール → Unity **2022.3 LTS** を入れる
2. New project → テンプレート **3D (Built-In Render Pipeline)** → 名前 `JoyconDemo` → Create
3. [JoyconLibのReleases](https://github.com/Looking-Glass/JoyconLib/releases) から
   `JoyconLib_*.unitypackage` をダウンロード →
   Unityメニュー **Assets → Import Package → Custom Package** で取り込む（全部✓のままImport）

## 3. ファイルを置く（5分）

1. Projectウィンドウの `Assets` 内で右クリック → Create → Folder →
   `StreamingAssets` という名前で作る（**綴り厳守**）
2. その中に `joycon_demo` フォルダを作り、このフォルダの **wavとcsv全部**をドラッグして入れる
3. `unity/JoyconDemoPlayer.cs` を `Assets` 直下にドラッグ

## 4. シーンを組む（5分）

1. Hierarchyで右クリック → Create Empty → 名前 `Joycon` →
   Inspectorの **Add Component → Joycon Manager**（JoyconLib付属）
2. もう1つ Create Empty → 名前 `Demo` → **Add Component → Joycon Demo Player**
   （Audio Sourceは自動で付く）
3. 上の **▶ 再生ボタン**を押す → Gameビューに
   「クリップ [1/5] … Joy-con接続: 2本」と出れば成功

## 5. 操作

| キー | 動作 |
| --- | --- |
| ← / → | クリップ切替（5本。おすすめの順は manifest.md） |
| Space | 再生 / 停止 |
| S | 左右の入れ替え（振動が音と逆側に感じたら押す） |

## うまくいかない時

- **Joy-con接続: 0本** → ペアリングを削除して再追加（Joy-conはスリープ後に切れやすい）。
  Unityを再起動してから▶
- **音は出るが震えない** → JoyconManagerがシーンにあるか／Gameビューをクリックして
  フォーカスしてからキー操作
- **wav読み込み失敗** → StreamingAssetsの綴りと、`joycon_demo`フォルダ名を確認
- 左右が逆 → 仕様ではなく方位規約の符号の問題。**Sキー**で解決

## デモとして見せるときの一言

「振動のタイミングと強さは、発表した通知システム（v4.2）が
この音声から実際に計算した出力です。デモ用の演出ではありません」

## 別のPCで組むときの注意 — JoyconLibに当てる修正2件（2026-09-02判明）

1. **hidapi.dllの差し替え（必須）**: 同梱の2017年版はWin11でロード不能。
   公式 https://github.com/libusb/hidapi/releases の hidapi-win.zip から
   x64/hidapi.dll を `Assets/JoyconLib_plugins/win64/` に上書き
2. **Joycon.cs 370行目の書式バグ**: `{3:s}`と`{4:s}`（TimeSpanに不正な書式）を
   `{3}`と`{4}`に直す。放置しても振動は動くが、FormatExceptionがコンソールに毎秒流れる

## 俯瞰ビュー（可視化・2026-09-02追加）

1. `unity/ScenarioVisualizer.cs` を `Assets` に入れる（→済みなら不要）
2. `out/joycon_demo/` の **`*_scene.csv`（10個）** も `StreamingAssets/joycon_demo/` にコピー
3. Hierarchyの **Demo** を選び **Add Component → Scenario Visualizer**
4. ▶ → 歩行者（白カプセル・中央）を中心に、車（青）・救急車（白+赤ランプ）などが動く。
   通知の瞬間に足元のリングが光る（強=赤 / 中=オレンジ / 警告=水色）
