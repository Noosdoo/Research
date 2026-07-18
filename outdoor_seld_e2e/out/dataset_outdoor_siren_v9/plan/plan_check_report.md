# v9 割当表 検算レポート（step10_v9_plan.py 自動生成）

- GLOBAL_SEED=20260717 / core md5=b177a00906a3b5d043b6246f3c583f2e
- core=1120 scenario=20 probe=48
- 決定論: 2回構築でmd5一致 / ID・seed一意 / 2音源の同一クラス重複ゼロ

- fold1/static: clips=320 n_warn={0: 96, 1: 176, 2: 48} class_ev={'siren': 54, 'horn': 54, 'backup_beep': 55, 'bike_bell': 54, 'crossing': 55} tier={'critical': 106, 'caution': 107, 'safe': 107}
- fold1/walk: clips=320 n_warn={0: 96, 1: 176, 2: 48} class_ev={'siren': 55, 'horn': 55, 'backup_beep': 54, 'bike_bell': 54, 'crossing': 54} tier={'critical': 107, 'caution': 107, 'safe': 106}
- fold1: cross-spread class_x_wside=1 class_x_tier=2 class_x_carside=3 tier_x_carside=1 tier_x_motion=1 (all within tol)
- fold2/static: clips=120 n_warn={0: 36, 1: 66, 2: 18} class_ev={'siren': 21, 'horn': 20, 'backup_beep': 20, 'bike_bell': 20, 'crossing': 21} tier={'critical': 40, 'caution': 40, 'safe': 40}
- fold2/walk: clips=120 n_warn={0: 36, 1: 66, 2: 18} class_ev={'siren': 20, 'horn': 21, 'backup_beep': 20, 'bike_bell': 21, 'crossing': 20} tier={'critical': 40, 'caution': 40, 'safe': 40}
- fold2: cross-spread class_x_wside=1 class_x_tier=2 class_x_carside=1 tier_x_carside=0 tier_x_motion=0 (all within tol)
- fold3/static: clips=120 n_warn={0: 36, 1: 66, 2: 18} class_ev={'siren': 20, 'horn': 20, 'backup_beep': 21, 'bike_bell': 21, 'crossing': 20} tier={'critical': 40, 'caution': 40, 'safe': 40}
- fold3/walk: clips=120 n_warn={0: 36, 1: 66, 2: 18} class_ev={'siren': 21, 'horn': 21, 'backup_beep': 20, 'bike_bell': 20, 'crossing': 20} tier={'critical': 40, 'caution': 40, 'safe': 40}
- fold3: cross-spread class_x_wside=1 class_x_tier=3 class_x_carside=2 tier_x_carside=0 tier_x_motion=0 (all within tol)
