# -*- coding: utf-8 -*-
"""因果推論の予測 csv（clip,frame,class,track,az,el,dist）の距離を 3D → 水平（dist × cos(el)）に変換する（2026-09-04・v15c 用）。
モデルは 3D 距離と仰角を出し、通知の判定は水平距離で行う、という v15c の設計の後段。
使い方: python scripts/_pred_to_horizontal.py in.csv out.csv
"""
import math
import sys

src, dst = sys.argv[1], sys.argv[2]
n = 0
with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8", newline="\n") as w:
    for line in f:
        q = line.rstrip("\n").split(",")
        if len(q) >= 7 and q[6] not in ("", "nan"):
            try:
                el = float(q[5]); d = float(q[6])
                q[6] = f"{d * math.cos(math.radians(el)):.2f}"
                n += 1
            except ValueError:
                pass
        w.write(",".join(q) + "\n")
print(f"converted {n} rows -> {dst}")
