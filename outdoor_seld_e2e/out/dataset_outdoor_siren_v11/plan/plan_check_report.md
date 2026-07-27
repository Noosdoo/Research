# v11 core 割当表 検算レポート（step10_v11_plan.py 自動生成）

- GLOBAL_SEED=20260727 / CORE_OFFSET=200000 / core md5=3169fd7f027d614045442536042c1f77
- core=7200（fold1 4800/fold2 1200/fold3 1200 = 20h、DCASE2022 Task3公式合成相当・v10比2.0倍）
- 分布: シーン種別 住宅40/生活40/幹線20 → n_car周辺分布 18/47/23/12% (厳密) / n_warn 45/40/15%
- シード帯域: 12420025651..12420032850（既存7970シード[26ファイル]との衝突ゼロを機械検証済み）
- 決定論: 2回構築でmd5一致 / ID・seed一意
- レンダラ仕様（step11_v11_render.py への申し送り）: scenario='v11core'、乱数消費順 ①マイク ②車n_car台 ③w1 ④w2 ⑤暗騒音、車t_cpa: n_car==1はCAR_TCPA / n_car>=2はU(4,9)

- fold1/static: clips=2400 n_warn={0: 1080, 1: 960, 2: 360} class_ev={siren:336, horn:336, backup_beep:336, bike_bell:336, crossing:336} warnレベル層内偏差max=0.8 クラス×n_car偏差max=2.8 tier×warn差=5(許容9)
- fold1/walk: clips=2400 n_warn={0: 1080, 1: 960, 2: 360} class_ev={siren:336, horn:336, backup_beep:336, bike_bell:336, crossing:336} warnレベル層内偏差max=0.8 クラス×n_car偏差max=2.8 tier×warn差=5(許容9)
- fold1: n_car={0: 864, 1: 2256, 2: 1104, 3: 576} (18%/47%/23%/12%) | フロア実測: 警告のみ474(>=400) 純静穏390(>=300) 複数車1680(>=1500) ✓
- fold2/static: clips=600 n_warn={0: 270, 1: 240, 2: 90} class_ev={siren:84, horn:84, backup_beep:84, bike_bell:84, crossing:84} warnレベル層内偏差max=0.6 クラス×n_car偏差max=3.0 tier×warn差=7(許容7)
- fold2/walk: clips=600 n_warn={0: 270, 1: 240, 2: 90} class_ev={siren:84, horn:84, backup_beep:84, bike_bell:84, crossing:84} warnレベル層内偏差max=0.6 クラス×n_car偏差max=3.0 tier×warn差=7(許容7)
- fold2: n_car={0: 216, 1: 564, 2: 276, 3: 144} (18%/47%/23%/12%) | フロア実測: 警告のみ120(>=100) 純静穏96(>=75) 複数車420(>=375) ✓
- fold3/static: clips=600 n_warn={0: 270, 1: 240, 2: 90} class_ev={siren:84, horn:84, backup_beep:84, bike_bell:84, crossing:84} warnレベル層内偏差max=0.6 クラス×n_car偏差max=3.0 tier×warn差=7(許容7)
- fold3/walk: clips=600 n_warn={0: 270, 1: 240, 2: 90} class_ev={siren:84, horn:84, backup_beep:84, bike_bell:84, crossing:84} warnレベル層内偏差max=0.6 クラス×n_car偏差max=3.0 tier×warn差=7(許容7)
- fold3: n_car={0: 216, 1: 564, 2: 276, 3: 144} (18%/47%/23%/12%) | フロア実測: 警告のみ120(>=100) 純静穏96(>=75) 複数車420(>=375) ✓
- 同一クラス警告×2: {'bike_bell': 78, 'backup_beep': 82, 'siren': 82}（計242本、v10.2 C枠112本の役割をcoreに吸収）
