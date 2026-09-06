# -*- coding: utf-8 -*-
"""長尺セット v1 の採点結果 md（_long_score.py の出力）を 2 つ並べて差を出す（2026-09-07・v1 ft2 vs v17b）。

使い方: python scripts/_long_compare.py <A.md> <B.md> [--labels A,B] [--out md]
表の列（_long_score.py）: 場面 | 交通量 | 本数 | 中/分 | 抑えた中/分 | 害 | 強/分 | 至近の車 | 至近の強到達 | 警告/本
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def rows_of(p: Path) -> dict:
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| 場面") or line.startswith("| ---"):
            continue
        c = [x.strip() for x in line.strip("|").split("|")]
        if len(c) < 10:
            continue
        out[(c[0], c[1])] = c
    return out


def num(s: str):
    m = re.match(r"^-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


def main() -> int:
    a = sys.argv
    A, B = Path(a[1]), Path(a[2])
    labels = (a[a.index("--labels") + 1].split(",") if "--labels" in a else [A.stem, B.stem])
    ra, rb = rows_of(A), rows_of(B)
    L = [f"# 長尺セット v1 — {labels[0]} vs {labels[1]}", "",
         "| 場面 | 交通量 | 本数 | 中/分 A→B | 強/分 A→B | 至近の強到達 A→B | 警告/本 A→B |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for k in ra:
        if k not in rb:
            continue
        x, y = ra[k], rb[k]
        def d(i, unit=""):
            va, vb = num(x[i]), num(y[i])
            if va is None or vb is None:
                return f"{x[i]} → {y[i]}"
            return f"{x[i]} → {y[i]}（{vb - va:+.2f}{unit}）"
        L.append(f"| {k[0]} | {k[1]} | {x[2]} | {d(3)} | {d(6)} | {d(8, 'pt')} | {d(9)} |")
    txt = "\n".join(L)
    print(txt)
    if "--out" in a:
        Path(a[a.index("--out") + 1]).write_text(txt + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
