# v4.2チューニング専用val plan台帳（自動生成: step10_v42tune_plan.py）

既存val(fold2)と同構成・新seed帯。**選定専用**（学習・確定評価に混ぜない）。

- 本数: 1,800（core写し1,200 + ext写し600）
- seed: 13,000,000,000 + i×104,729（min=13,000,000,000 max=13,188,407,471・全既存planと排他assert済み）
- 由来CSV sha256/16: {'assignment_core.csv': '1335e884aa2e90ab', 'assignment_v12ext.csv': '2565f3d1cb23752e'}

| scenario | motion | 本数 |
|---|---|---|
| v11core | static | 600 |
| v11core | walk | 600 |
| v12bike | static | 112 |
| v12bike | walk | 113 |
| v12kick | static | 113 |
| v12kick | walk | 112 |
| v12train | static | 75 |
| v12train | walk | 75 |