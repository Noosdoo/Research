# v12確定評価セット plan台帳（自動生成・事前登録の実体）

- 総数 1,800本（fold20_room1_mix0001-1800）
- core（fold2 coreの鏡像・新シード）: 1200本 = mix0001-1200
- ext（fold2 extの鏡像・新シード）: {'v12kick': 225, 'v12bike': 225, 'v12train': 150} = mix1201-1800
- SEED_BASE=12,000,000,000 step=104729（core/ext/eval全planと排他をassert済み）
- 設計フィールドはテンプレート行を完全保存（clip_id/split/seedのみ差替）
- 事前登録: md/design/v12確定評価セット_事前登録_2026-08-10.md