# -*- coding: utf-8 -*-
"""因果学習のチェックポイントを**検証データだけ**で選ぶ（2026-08-20）。

## なぜ必要か

学習中の checkpoint 選択は `val/macro/SELD_scr` を見ているが、
検証は通常推論（未来も見る）のままなので、**目的と違う条件で選んでいる**
（監査①）。そこで20エポックごとに全部保存しておき、
**因果推論での成績**で選び直す。確定評価セットには選んだ1つだけを当てる。

## 選ぶ基準（結果を見る前に決める）

通知の至近警告は「推定距離が近いか」で決まるので、
**GTが至近(≤1.5m)の車を、1.5mのしきい値でどれだけ捕まえられるか**を主基準にする。
誤って捕まえる率（GTが>3.2mなのに1.5m以下と出す率）が
基準の2倍を超える候補は、捕捉率が高くても採らない。

窓の暖機を避けフレーム40以降のみ。方位が20度以内で対応が付いた検出だけを使う。

使い方: python scripts/_causalft_select.py <GTdir> <csv1> <csv2> ...
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CLS, MINFR, TH = {4, 6, 7}, 40, 1.5


def pairs(csv, meta):
    pr = defaultdict(lambda: defaultdict(list))
    for line in open(csv, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) >= 7 and int(g[2]) in CLS and int(g[1]) >= MINFR:
            pr[g[0]][int(g[1])].append((int(g[2]), float(g[4]), float(g[6])))
    out = []
    for clip, fr in pr.items():
        f = Path(meta) / f"{clip}.csv"
        if not f.exists():
            continue
        gt = defaultdict(list)
        for line in open(f, encoding="utf-8"):
            g = line.strip().split(",")
            if len(g) == 6 and int(g[1]) in CLS:
                gt[int(g[0])].append((int(g[1]), float(g[3]), float(g[5])))
        for j, items in fr.items():
            for c, az, d in items:
                cand = [(abs((az - a + 180) % 360 - 180), dg)
                        for cc, a, dg in gt.get(j, []) if cc == c]
                if cand:
                    e, dg = min(cand)
                    if e <= 20.0:
                        out.append((d, dg))
    return np.array(out)


def main() -> int:
    meta, csvs = sys.argv[1], sys.argv[2:]
    print(f"{'モデル':>28} {'至近を捕まえる率':>16} {'誤って捕まえる率':>16} "
          f"{'至近への推定距離':>16}")
    rows = []
    for c in csvs:
        P = pairs(c, meta)
        close, safe = P[P[:, 1] <= 1.5, 0], P[P[:, 1] > 3.2, 0]
        cap = 100 * np.mean(close <= TH)
        fp = 100 * np.mean(safe <= TH)
        rows.append((Path(c).parent.name, cap, fp, float(np.median(close))))
        print(f"{rows[-1][0]:>28} {cap:>15.1f}% {fp:>15.2f}% "
              f"{rows[-1][3]:>15.2f}m")
    base = min(r[2] for r in rows)
    ok = [r for r in rows if r[2] <= base * 2]
    ok.sort(key=lambda r: -r[1])
    print(f"\n誤捕捉が最小値({base:.2f}%)の2倍以内の候補: {len(ok)}件")
    print(f"→ 選択: **{ok[0][0]}**（捕捉率 {ok[0][1]:.1f}% / 誤捕捉 {ok[0][2]:.2f}%）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
