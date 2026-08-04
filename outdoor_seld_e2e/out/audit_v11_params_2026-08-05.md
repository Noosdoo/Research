# v11パラメータ精査（学習系7,200本、実測 7200本）

## B1 車の台数分布（公称 0/1/2/3台 = 18/47/23/12%）
- 0台: 1296本 (18.0%)
- 1台: 3384本 (47.0%)
- 2台: 1656本 (23.0%)
- 3台: 864本 (12.0%)

## B2 警告音の個数（公称 0/1/2個 = 45/40/15%）
- 0個: 3240本 (45.0%)
- 1個: 2880本 (40.0%)
- 2個: 1080本 (15.0%)

## B3 マイク（公称 静止50%/歩行50%）
- walk: 3600本 (50.0%)
- static: 3600本 (50.0%)
- 歩行速度: 1.00〜1.40 (中央1.20) m/s

## B4 主要車の危険層（公称 近/中/遠 均等）
- caution: 1968本
- safe: 1968本
- critical: 1968本

## B5 背景騒音 dB(A)（公称 40〜65）
- 実測: 40.0〜65.0 (中央52.4)

## B6 最低本数保証
- 車なし＋警告音あり: 714本（公称≥400）
- 対象音なし＋背景のみ: 582本（公称≥300）
- 車2台以上: 2520本（公称≥1,500）

## B7 fold間シード独立
- fold1: 4800種
- fold2: 1200種
- fold3: 1200種
- fold間で共有されるseed: 0個 (独立)

## B8 空メタデータの員数
- 空メタ: 589本 / 音源ゼロ(背景のみ): 582本 / 差分（音源はあるがラベル0行）: 7本
  - fold1_room1_mix0474: [('car_drive', 0.0)]
  - fold1_room1_mix1121: [('car_drive', 0.0)]
  - fold1_room1_mix2177: [('car_drive', 0.0)]
  - fold1_room1_mix2773: [('car_drive', 0.0)]
  - fold1_room1_mix2917: [('car_drive', 0.0)]
  - fold3_room1_mix0534: [('car_drive', 0.0)]
  - fold3_room1_mix0984: [('car_drive', 0.0)]

# A3 音源パラメータ実測（P15公称との突合）

## backup_beep  (n=1008)
- 規定音量 law_db: 60.0〜95.0 (中央74.9)
- 速度: 1.0〜3.0 (中央2.0) m/s

## bike_bell  (n=1008)
- 規定音量 law_db: 80.0〜95.0 (中央87.3)
- 速度: 3.0〜7.0 (中央5.0) m/s

## car_drive  (n=9288)
- 規定音量 law_db: 60.0〜67.0 (中央63.5)
- 速度: 3.0〜10.0 (中央6.6) m/s
- 車f0: 33.60〜50.40 (中央42.02) Hz

## crossing  (n=1008)
- 規定音量 law_db: 75.0〜85.0 (中央80.1)

## horn  (n=1008)
- 規定音量 law_db: 87.0〜111.9 (中央99.5)
- 速度: 5.0〜15.0 (中央10.1) m/s

## siren  (n=1008)
- 規定音量 law_db: 90.0〜119.9 (中央104.3)
- 速度: 5.0〜15.0 (中央10.1) m/s

## サブタイプ取り分
- backup:R165_60-75: 511
- backup:実勢85-95: 497
- bell:ring: 502
- bell:single: 506
- siren:fire: 269
- siren:peepo: 489
- siren:wail: 250

# C1 評価専用セットの員数
評価クリップ総数: 3246（公称3,342）
- backup_reverse: 100本
- bell_overtake: 100本
- carfree_siren: 600本
- crossing_wait: 200本
- intersection_siren: 100本
- n1_blind: 150本
- n2_ev: 150本
- n3_parking: 150本
- n4_fast_siren: 150本
- n5_downtown: 150本
- n6_overtake: 150本
- n7_pullout: 150本
- probe_backup_beep: 16本
- probe_bike_bell: 16本
- probe_car_drive: 16本
- probe_crossing: 16本
- probe_horn: 16本
- probe_siren: 16本
- siren_worstnoise: 200本
- traffic2: 100本
- traffic3: 100本
- v11core: 600本