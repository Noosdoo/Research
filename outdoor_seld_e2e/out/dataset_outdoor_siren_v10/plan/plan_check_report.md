# v10 割当表 検算レポート（step10_v10_plan.py 自動生成）

- GLOBAL_SEED=20260721 / core md5=fd471c09864501e5c6b9e121e53fb612
- core=3600（train2400/val600/test600、TAU-NIGENS train:val:test=4:1:1比・v9.1比 3.75倍）
- scenario=20 probe=48 scenario2=100 v10a=60（評価専用枠、v9.1本数のまま据え置き）
- 決定論: 2回構築でmd5一致 / ID・seed一意 / 2音源の同一クラス重複ゼロ

- fold1/static: clips=1200 n_warn={0: 360, 1: 660, 2: 180} class_ev={'siren': 204, 'horn': 204, 'backup_beep': 204, 'bike_bell': 204, 'crossing': 204} tier={'critical': 400, 'caution': 400, 'safe': 400}
- fold1/walk: clips=1200 n_warn={0: 360, 1: 660, 2: 180} class_ev={'siren': 204, 'horn': 204, 'backup_beep': 204, 'bike_bell': 204, 'crossing': 204} tier={'critical': 400, 'caution': 400, 'safe': 400}
- fold1: cross-spread class_x_wside=0 class_x_tier=0 class_x_carside=0 tier_x_carside=0 tier_x_motion=0 (all within tol)
- fold2/static: clips=300 n_warn={0: 90, 1: 165, 2: 45} class_ev={'siren': 51, 'horn': 51, 'backup_beep': 51, 'bike_bell': 51, 'crossing': 51} tier={'critical': 100, 'caution': 100, 'safe': 100}
- fold2/walk: clips=300 n_warn={0: 90, 1: 165, 2: 45} class_ev={'siren': 51, 'horn': 51, 'backup_beep': 51, 'bike_bell': 51, 'crossing': 51} tier={'critical': 100, 'caution': 100, 'safe': 100}
- fold2: cross-spread class_x_wside=2 class_x_tier=4 class_x_carside=1 tier_x_carside=0 tier_x_motion=0 (all within tol)
- fold3/static: clips=300 n_warn={0: 90, 1: 165, 2: 45} class_ev={'siren': 51, 'horn': 51, 'backup_beep': 51, 'bike_bell': 51, 'crossing': 51} tier={'critical': 100, 'caution': 100, 'safe': 100}
- fold3/walk: clips=300 n_warn={0: 90, 1: 165, 2: 45} class_ev={'siren': 51, 'horn': 51, 'backup_beep': 51, 'bike_bell': 51, 'crossing': 51} tier={'critical': 100, 'caution': 100, 'safe': 100}
- fold3: cross-spread class_x_wside=2 class_x_tier=2 class_x_carside=2 tier_x_carside=0 tier_x_motion=0 (all within tol)
