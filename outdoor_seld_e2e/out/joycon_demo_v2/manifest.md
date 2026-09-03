# Joy-conデモ v2 データ（自動生成: _make_joycon_demo_v43.py）

- 通知= **v4.3**（`sa∞+dn12+ath0.07+rcw13`）＋警告音hold の本物の出力。クリップは fold32・ft2 因果推論
- cues.csv は規則の生の出力（束ね無し）。Unity 側で M=束ね(1秒以内の同段再トリガは延長) / G=連続振動(urgency) を切替
- urgency.csv は予測からの毎フレーム緊急度（0..1）。実発火は cues.csv（4/4確認つき）
- detect.csv は検出層の生出力（class/方位/距離）。layout.csv は道路の配置（車線・歩道・踏切）

## fold32_room1_mix0007 — A 1台の車に強が0.8秒おきに再発火（束ねON/OFFを M キーで比較）
- 0.3s L 警告 (crossing, az=22°)
- 5.4s L 中 (car, az=179°)
- 6.6s L 強 (car, az=178°)
- 7.4s L 強 (car, az=176°)
- 8.8s L 強 (car, az=79°)
- 8.9s L 強 (car, az=31°)

## fold32_room1_mix0067 — B 同じ車が 中→強 と昇格（段階/連続を G キーで比較）
- 0.3s L 中 (car, az=177°)
- 3.6s R 強 (car, az=-176°)
- 4.6s R 強 (car, az=-173°)
- 6.4s R 強 (car, az=-55°)

## fold32_room1_mix0120 — D 安全な車だけ→中止まり・強は出ない（抑制）
- 0.3s L 中 (car, az=175°)

## fold32_room1_mix0128 — C 幹線・歩行・車3台の連続通知（本当の交通量）
- 2.3s R 強 (car, az=-5°)
- 2.9s R 強 (car, az=-6°)
- 4.1s R 強 (car, az=-76°)
- 4.2s R 強 (car, az=-120°)
- 4.3s R 中 (car, az=-148°)
- 7.0s L 中 (car, az=93°)
- 8.9s R 強 (car, az=-85°)
