# v4.2チューニングval第2版(fold32) plan台帳（自動生成）

fold30のPhase A採用なし（宣言§7.1）を受けた再選定用。**選定1回のみに使う**。

- 本数: 1,800 / seed: 15,000,000,000 + i×104,729（max=15,188,407,471・全既存plan+fold30と排他assert済み）
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