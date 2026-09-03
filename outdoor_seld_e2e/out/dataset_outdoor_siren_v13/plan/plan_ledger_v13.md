# v13 plan台帳（自動生成: step10_v13_plan.py）

土台= v11 core + v12ext の fold1/fold2（clip_id・seed・クラス・危険層・n_car・場面は不変）。
再割当= motion（歩行70%）・雨（20%）を seed×20260913 で決定論的に。

## fold1（7,200本）

- motion: {'static': 2143, 'walk': 5057}
- rain: {'none': 5792, 'light': 710, 'heavy': 191, 'moderate': 507}
- scenario: {'v11core': 4800, 'v12kick': 900, 'v12bike': 900, 'v12train': 600}
- n_car: {'0': 3264, '1': 2256, '2': 1104, '3': 576}
- 警告クラス: {'bike_bell': 672, 'crossing': 672, 'horn': 672, 'siren': 672, 'backup_beep': 672}

## fold2（1,800本）

- motion: {'walk': 1267, 'static': 533}
- rain: {'none': 1394, 'moderate': 136, 'light': 216, 'heavy': 54}
- scenario: {'v11core': 1200, 'v12kick': 225, 'v12bike': 225, 'v12train': 150}
- n_car: {'0': 816, '1': 564, '2': 276, '3': 144}
- 警告クラス: {'siren': 168, 'bike_bell': 168, 'horn': 168, 'crossing': 168, 'backup_beep': 168}

