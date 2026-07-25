# v9 生成前チェック（step11 precheck、レンダなしの解析計算）

- 行数: 3828（core+scenario+probe）
- 相対CPAの検算: 設計値との最大差 0.042 m（0.05s格子の離散化誤差の範囲であること）
- ピーク上限（クレスト率×反射同相の保守的バウンド）上位5:
    fold3_room1_mix380: 0.966
    fold2_room1_mix202: 0.926
    fold1_room1_mix1522: 0.879
    fold1_room1_mix1104: 0.873
    fold1_room1_mix408: 0.862
  -> 最大 0.966（1.0未満なら本番assertも確実。超える行はスモークで実測ピークを確認する）
- クラス別の可聴フレーム率の予測（発音窓内、吸収・反射無視の点近似）:
    backup_beep: mean=0.64 p10=0.00 完全不可聴率=33.44%
    bike_bell: mean=0.91 p10=0.63 完全不可聴率=4.95%
    car_drive: mean=0.73 p10=0.28 完全不可聴率=2.37%
    crossing: mean=0.79 p10=0.00 完全不可聴率=17.03%
    horn: mean=1.00 p10=1.00 完全不可聴率=0.00%
    siren: mean=1.00 p10=1.00 完全不可聴率=0.00%
- 車のオラクル・リードタイム予測（可聴開始→相対CPA): median=5.7s  >=2.5s: 77.0%  >=2.0s: 82.6%  クリップ内不可聴: 2.3%
- 音量AUCの事前予測（受音レベルのみでのクラス対判別、案A''の事前登録値）:
    backup_beep vs bike_bell: AUC=0.768
    backup_beep vs car_drive: AUC=0.772
    backup_beep vs crossing: AUC=0.617
    backup_beep vs horn: AUC=0.999
    backup_beep vs siren: AUC=1.000
    bike_bell vs car_drive: AUC=0.509
    bike_bell vs crossing: AUC=0.745
    bike_bell vs horn: AUC=0.999
    bike_bell vs siren: AUC=1.000
    car_drive vs crossing: AUC=0.752
    car_drive vs horn: AUC=0.999
    car_drive vs siren: AUC=1.000
    crossing vs horn: AUC=1.000
    crossing vs siren: AUC=1.000
    horn vs siren: AUC=0.870
