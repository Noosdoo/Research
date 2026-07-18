# v9 生成前チェック（step11 precheck、レンダなしの解析計算）

- 行数: 1188（core+scenario+probe）
- 相対CPAの検算: 設計値との最大差 0.072 m（0.05s格子の離散化誤差の範囲であること）
- ピーク上限（クレスト率×反射同相の保守的バウンド）上位5:
    fold3_room1_mix212: 0.919
    fold1_room1_mix399: 0.763
    fold2_room9_mix015: 0.741
    fold2_room9_mix005: 0.696
    fold1_room1_mix385: 0.671
  -> 最大 0.919（1.0未満なら本番assertも確実。超える行はスモークで実測ピークを確認する）
- クラス別の可聴フレーム率の予測（発音窓内、吸収・反射無視の点近似）:
    backup_beep: mean=1.00 p10=1.00 完全不可聴率=0.00%
    bike_bell: mean=0.91 p10=0.66 完全不可聴率=4.04%
    car_drive: mean=0.60 p10=0.18 完全不可聴率=1.86%
    crossing: mean=0.80 p10=0.00 完全不可聴率=17.17%
    horn: mean=1.00 p10=1.00 完全不可聴率=0.00%
    siren: mean=1.00 p10=1.00 完全不可聴率=0.00%
- 車のオラクル・リードタイム予測（可聴開始→相対CPA): median=3.3s  >=2.5s: 61.3%  >=2.0s: 69.3%  クリップ内不可聴: 1.7%
- 音量AUCの事前予測（受音レベルのみでのクラス対判別、案A''の事前登録値）:
    backup_beep vs bike_bell: AUC=0.970
    backup_beep vs car_drive: AUC=0.987
    backup_beep vs crossing: AUC=0.989
    backup_beep vs horn: AUC=0.891
    backup_beep vs siren: AUC=0.983
    bike_bell vs car_drive: AUC=0.567
    bike_bell vs crossing: AUC=0.733
    bike_bell vs horn: AUC=1.000
    bike_bell vs siren: AUC=1.000
    car_drive vs crossing: AUC=0.677
    car_drive vs horn: AUC=1.000
    car_drive vs siren: AUC=1.000
    crossing vs horn: AUC=1.000
    crossing vs siren: AUC=1.000
    horn vs siren: AUC=0.843
