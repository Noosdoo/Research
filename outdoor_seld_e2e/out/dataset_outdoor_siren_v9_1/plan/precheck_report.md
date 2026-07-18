# v9 生成前チェック（step11 precheck、レンダなしの解析計算）

- 行数: 1288（core+scenario+probe）
- 相対CPAの検算: 設計値との最大差 0.072 m（0.05s格子の離散化誤差の範囲であること）
- ピーク上限（クレスト率×反射同相の保守的バウンド）上位5:
    fold1_room1_mix346: 0.795
    fold2_room9_mix005: 0.744
    fold2_room9_mix015: 0.741
    fold1_room1_mix172: 0.570
    fold2_room9_mix004: 0.559
  -> 最大 0.795（1.0未満なら本番assertも確実。超える行はスモークで実測ピークを確認する）
- クラス別の可聴フレーム率の予測（発音窓内、吸収・反射無視の点近似）:
    backup_beep: mean=1.00 p10=1.00 完全不可聴率=0.00%
    bike_bell: mean=0.96 p10=0.96 完全不可聴率=1.38%
    car_drive: mean=0.61 p10=0.19 完全不可聴率=1.88%
    crossing: mean=0.80 p10=0.00 完全不可聴率=17.43%
    horn: mean=1.00 p10=1.00 完全不可聴率=0.00%
    siren: mean=1.00 p10=1.00 完全不可聴率=0.00%
- 車のオラクル・リードタイム予測（可聴開始→相対CPA): median=3.4s  >=2.5s: 61.5%  >=2.0s: 69.3%  クリップ内不可聴: 1.9%
- 音量AUCの事前予測（受音レベルのみでのクラス対判別、案A''の事前登録値）:
    backup_beep vs bike_bell: AUC=0.964
    backup_beep vs car_drive: AUC=0.986
    backup_beep vs crossing: AUC=0.990
    backup_beep vs horn: AUC=0.889
    backup_beep vs siren: AUC=0.984
    bike_bell vs car_drive: AUC=0.581
    bike_bell vs crossing: AUC=0.746
    bike_bell vs horn: AUC=1.000
    bike_bell vs siren: AUC=1.000
    car_drive vs crossing: AUC=0.681
    car_drive vs horn: AUC=1.000
    car_drive vs siren: AUC=1.000
    crossing vs horn: AUC=1.000
    crossing vs siren: AUC=1.000
    horn vs siren: AUC=0.845
