# 自作場面 × 本物の検出層（ft2 e099 因果推論 → v4.3＋hold）

| 場面 | オラクル（正解→規則） | モデル（検出→規則） |
| --- | --- | --- |
| 01_roji_ushiro_kuruma | 4.3 R 強(car) | 4.4 R 強(car) / 6.5 R 強(car) / 6.6 R 中(car) |
| 02_roji_taikou_kuruma | 4.0 L 強(car) / 6.1 L 強(car) / 6.2 L 中(car) | 5.3 L 強(car) / 6.1 L 中(car) |
| 03_kansen_hodou_renzoku | 6.0 R 強(car) | 3.1 R 中(car) / 5.3 R 強(car) |
| 04_fumikiri_matsu_ressha | 0.4 L 警告(crossing) | 0.3 L 警告(siren) / 0.4 L 警告(crossing) / 2.3 L 強(car) / 2.9 L 強(car) / 3.2 L 中(car) / 4.5 L 中(car) / 5.2 L 強(car) / 6.7 L 警告(crossing) |
| 05_fumikiri_keihou_dake | 0.4 L 警告(crossing) | 0.3 L 警告(siren) / 0.4 L 警告(crossing) |
| 06_chushajo_backup | 0.4 R 警告(backup_beep) / 1.7 R 強(car) / 6.7 R 警告(backup_beep) / 7.3 R 警告(backup_beep) / 8.3 R 警告(backup_beep) | 0.3 R 警告(backup_beep) / 2.7 R 強(car) / 4.2 R 強(car) / 6.9 R 中(car) / 7.1 R 警告(backup_beep) / 8.5 R 警告(backup_beep) |
| 07_jitensha_bell_ushiro | 4.8 R 警告(bike_bell) | 4.8 R 警告(bike_bell) |
| 08_kick_ushiro | 3.7 L 強(kick) / 6.1 L 強(kick) / 6.2 L 強(kick) | 5.6 L 強(kick) / 6.1 L 強(kick) / 7.6 L 中(kick) |
| 09_bike_ushiro | 4.0 R 強(bike) / 6.1 R 強(bike) / 6.2 R 中(bike) | 4.6 R 強(bike) / 6.0 R 強(bike) / 6.1 R 強(bike) / 6.2 R 中(bike) |
| 10_kyukyusha_tsuuka | 0.6 L 警告(siren) / 6.9 L 警告(siren) / 7.2 L 警告(siren) / 7.7 L 警告(siren) | 0.6 L 警告(siren) / 6.8 L 警告(siren) / 7.2 L 警告(siren) / 7.8 L 警告(siren) |
| 11_kyukyusha_sekkin_nomi | 1.0 R 警告(siren) | 1.0 R 警告(siren) |
| 12_horn_narasareru | 5.0 R 強(car) / 5.3 R 警告(horn) / 7.1 R 強(car) / 7.2 R 中(car) | 5.3 R 警告(horn) / 5.9 R 強(car) / 6.8 R 強(car) / 7.0 R 強(car) |
| 13_shizuka_nanimonai | なし | なし |
| 14_fukugo_mae_kuruma_ushiro_jitensha | 4.8 L 中(car) / 6.3 R 警告(bike_bell) | 4.2 L 強(car) / 5.1 L 中(car) / 6.3 R 警告(bike_bell) / 8.8 L 強(car) |
| 15_kansen_shingo_machi | 5.5 L 強(car) / 8.0 L 中(car) | 2.5 L 中(car) / 5.1 L 中(car) / 5.5 L 中(car) / 8.6 L 中(car) |
| 16_ushiro_kuruma_yukkuri_tsuika | 4.2 L 強(car) | 4.4 L 強(car) / 6.1 L 強(car) / 6.9 L 中(car) |
| 17_teisha_kuruma_hasshin | なし | なし |
| 18_oudan_migi_kara_kuruma | 6.1 R 中(car) | 6.7 L 中(car) / 8.8 L 強(car) / 9.5 L 中(car) |
| 19_koukashita_zujou_ressha | 0.5 R 警告(crossing) / 6.8 R 中(car) / 9.9 R 警告(crossing) | 0.9 R 強(bike) / 3.5 R 強(bike) / 3.8 R 警告(crossing) / 7.2 R 強(car) / 9.4 R 警告(crossing) |
| 20_basutei_basu_teisha_hasshin | 3.3 R 中(car) | 0.3 R 中(car) / 3.4 R 中(car) / 4.2 R 中(car) |
| 21_takuhai_bike_teishi_hasshin | 0.9 R 強(bike) / 8.4 R 強(bike) | 1.8 R 強(bike) / 5.3 R 警告(crossing) / 5.8 R 中(bike) / 8.4 R 強(bike) |
| 22_kousaten_yokogiru_kuruma | なし | なし |
| 23_sasetsu_makikomi | 4.5 R 中(car) | 9.4 L 強(car) |
| 24_rikadai_seimon_matsu_sasetsu | 4.5 L 強(car) | 8.6 L 中(car) / 8.7 L 中(car) |
| 25_rikadai_seimon_deru_wataru | なし | なし |
| 26_rikadai_seimon_nansei_kara | 5.8 R 警告(bike_bell) / 7.4 R 警告(bike_bell) | 5.8 L 警告(bike_bell) / 6.1 R 警告(bike_bell) / 7.5 R 警告(bike_bell) |
| 27_rikadai_seimon_aruite_sasetsu_mae | 0.9 L 強(car) / 3.0 R 中(car) | 2.2 L 強(car) / 3.1 R 中(car) / 5.7 R 強(car) |
| 28_rikadai_seimon_aruite_usetsu_ushiro | 3.9 R 強(car) / 6.0 R 中(car) | 0.5 R 警告(bike_bell) |
| 29_taikou_to_toorisugi | 3.0 L 強(car) / 5.1 L 強(car) / 5.2 L 中(car) | 4.2 L 強(car) / 5.0 L 中(car) / 5.1 L 中(car) |
