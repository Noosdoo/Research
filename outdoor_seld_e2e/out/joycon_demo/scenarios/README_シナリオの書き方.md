# シナリオ自作の書き方（Joy-conデモ）

1. この фолダのJSON例をコピーして数字を書き換える
2. 実行:
   `python scripts/_make_custom_demo_scenario.py out/joycon_demo/scenarios/自分の.json`
3. できた `custom_*.wav` と `custom_*_cues.csv` の2つを
   Unityの `Assets/StreamingAssets/joycon_demo/` へドラッグ → ▶し直すと一覧に出る

## 書けるもの

| キー | 意味 |
| --- | --- |
| class | car / siren / horn / bike_bell / backup_beep / crossing / kick / bike |
| from | front（前から来る）/ behind（後ろから来る） |
| side | left / right（どちら側を通るか） |
| lateral_m | 横距離[m]。1.0=かすめる、4.5=安全に通過（→鳴らない） |
| speed_kmh | 速度 |
| cpa_s | 最接近の時刻[秒]。**10より大きくすると「近づき続けたまま終わる」** |
| level_db / t_on / t_off / siren_type | 任意（音量・短鳴らし・サイレン種peepo/wail/fire） |
| crossing だけ | side / lateral_m / x_m（静止した踏切警報器） |

## 遊び方のヒント

- 対向1.0m と すり抜け4.5m を並べる → 片方だけ震える（=Q2の実演）→ rei1
- サイレンを cpa_s=14 で置く → 遠くから鳴りながら迫って終わる（自然な接近）→ rei2
- lateral_m を 1.0→2.0→4.0 と変えて「どこから鳴らなくなるか」を体で探す
- noise_dba を 60 にして騒がしい街でも同じか試す

## 注意（正直に）

- 振動は**GT系列＋本物の規則(v4.2+hold)のオラクル動作**。知覚モデルは通していない
  （fold31の5本は本物のモデル出力。発表で使うときはこの区別を言うこと）
- 音量の既定値は概算。学習・評価には使わない

## 歩行（2026-09-02追加）

トップレベルに以下を書くと歩行者が歩く（合成規約どおり直進・回転なし）:

```json
"motion": "walk", "walk_speed_kmh": 4.3
```

例 = hodou_30km.json（車道の左側の歩道を歩行中、後ろから30km/hの車が右側2.0mを追い越す）
