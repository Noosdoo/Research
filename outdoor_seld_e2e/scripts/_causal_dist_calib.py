# -*- coding: utf-8 -*-
"""因果推論の距離推定を較正する（検証データのみで作り、確定評価には当てるだけ）。

## 何が起きていたか

因果推論にすると至近車への強到達が 69.9%→19.3%(v3.4) / 85.0%→50.2%(v4.1) に崩れた。
原因を測ると、**分離能はほぼ保たれている**（至近と安全を距離で分けるAUCは
0.996→0.987）のに、**推定値の位置がずれている**だけだった:

  至近の車(GT<=1.5m)に対する推定距離の中央値: 通常 1.30m → 因果 1.79m

そのため 1.5m のしきい値をまたげず、捕捉率が 73.3%→26.3% に落ちていた。
情報は失われていないので、**単調な変換で戻せる**。

## 方式（結果を見る前に宣言し、検証データだけで作る）

因果推論の距離の**分布**を、通常推論の距離の分布に合わせる分位マッピングを作る。

  corrected = 通常推論の分布の q 分位点   （q = 因果推論の分布における d の分位）

- 学習は**検証データのみ**。確定評価は当てるだけで、較正には一切使わない
- 規則もしきい値も**変えない**（知覚層側の較正であって通知層は不変）
- 窓の暖機（クリップ先頭はゼロ埋めが多い）を避けるためフレーム40以降で作る。
  実機では10秒ぶんの実音が常に埋まっており、そちらが本来の条件

使い方:
  fit  : python scripts/_causal_dist_calib.py fit <因果val.csv> <通常val.csv> <出力json>
  apply: python scripts/_causal_dist_calib.py apply <json> <入力csv> <出力csv>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DIST_CLASSES, MINFR = {4, 6, 7}, 40
QS = np.linspace(0.0, 1.0, 201)


def _dists(csv, minfr=MINFR):
    out = []
    for line in open(csv, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) < 7:
            continue
        if int(g[2]) in DIST_CLASSES and int(g[1]) >= minfr:
            out.append(float(g[6]))
    return np.array(out)


def fit(causal_csv, full_csv, outjson):
    c, f = _dists(causal_csv), _dists(full_csv)
    x = np.quantile(c, QS)                    # 因果の分位点
    y = np.quantile(f, QS)                    # 通常の同じ分位点
    x, idx = np.unique(x, return_index=True)  # 単調・重複なしに整形
    y = np.maximum.accumulate(y[idx])
    json.dump({"x": x.tolist(), "y": y.tolist(), "min_frame": MINFR,
               "n_causal": int(len(c)), "n_full": int(len(f))},
              open(outjson, "w"), indent=1)
    print(f"因果 {len(c):,}件 / 通常 {len(f):,}件（フレーム{MINFR}以降）")
    print(f"{'分位':>6} {'因果':>9} {'通常':>9} {'変換量':>9}")
    for q in (0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90):
        a, b = np.quantile(c, q), np.quantile(f, q)
        print(f"{q*100:>5.0f}% {a:>8.2f}m {b:>8.2f}m {b - a:>+8.2f}m")
    print(f"\n較正表を書きました: {outjson}（{len(x)}点）")


def apply(js, src, dst):
    t = json.load(open(js))
    x, y = np.array(t["x"]), np.array(t["y"])
    n = 0
    with open(dst, "w") as w:
        for line in open(src, encoding="utf-8"):
            g = line.strip().split(",")
            if len(g) < 7:
                continue
            if int(g[2]) in DIST_CLASSES:
                g[6] = f"{float(np.interp(float(g[6]), x, y)):.2f}"
                n += 1
            w.write(",".join(g) + "\n")
    print(f"較正を当てました: {dst}（{n:,}行の距離を書き換え）")


if __name__ == "__main__":
    (fit if sys.argv[1] == "fit" else apply)(*sys.argv[2:])
