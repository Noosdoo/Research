# -*- coding: utf-8 -*-
"""⑤交通量モード: duty分布の v12 再測定（2026-08-30、第10回監査 論点4の条件）。

監査の指摘: duty中央値54% vs 89〜91%・しきい値60%は **v10a=v9.1時代**のモデルと合成の
測定値であり、v12世代にそのまま持ち込む根拠がない。→ v12 val で再測定する。

duty の定義（v10aと同一）: クリップ100フレーム中、車（クラス4）が1台以上
報告されているフレームの割合。交通量グループはGTの車トラック数（metadata_dist）。

使い方:
  python scripts/_duty_v12_measure.py <pred_csv> <metadata_distディレクトリ> <出力md>
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CAR = 4


def main() -> int:
    pred_path, meta_dir, out_md = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    out_md.parent.mkdir(parents=True, exist_ok=True)

    frames_with_car = defaultdict(set)          # clip -> {frame}
    all_clips = set()                           # 車予測ゼロのクリップも分母に残す
    for line in open(pred_path, encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) >= 6:
            all_clips.add(p[0])
            if int(p[2]) == CAR:
                frames_with_car[p[0]].add(int(p[1]))

    duty_by_n = defaultdict(list)
    for clip in sorted(all_clips):
        f = meta_dir / f"{clip}.csv"
        if not f.exists():
            continue
        tracks = set()
        for line in open(f, encoding="utf-8"):
            g = line.strip().split(",")
            if len(g) >= 6 and int(g[1]) == CAR:
                tracks.add(int(g[2]))
        duty_by_n[len(tracks)].append(len(frames_with_car[clip]) / 100.0)

    R = [f"# duty分布のv12再測定 pred={pred_path.name}", "",
         "duty = 車が1台以上報告されているフレーム割合（クリップ全体=10秒窓）。", "",
         "| GT車台数 | n(クリップ) | duty中央値 | 四分位 | ≥60%の割合 |",
         "| --- | --- | --- | --- | --- |"]
    for n in sorted(duty_by_n):
        d = np.array(duty_by_n[n])
        R.append(f"| {n}台 | {len(d):,} | {100*np.median(d):.0f}% "
                 f"| {100*np.percentile(d,25):.0f}–{100*np.percentile(d,75):.0f}% "
                 f"| {100*np.mean(d >= 0.6):.0f}% |")
    one = np.array(duty_by_n.get(1, []))
    multi = np.array(duty_by_n.get(2, []) + duty_by_n.get(3, []))
    if len(one) and len(multi):
        R += ["", f"## 60%しきい値の分離性能（v10aの候補値の検算）", "",
              f"- 1台クリップで duty≥60%（誤って「多」判定）: {100*np.mean(one>=0.6):.1f}%",
              f"- 2〜3台クリップで duty<60%（誤って「少」判定）: {100*np.mean(multi<0.6):.1f}%",
              "", "v10a（v9.1時代）の中央値54% vs 89〜91%と比べて分離が保たれているかを見る。",
              "⚠️ これは分布の記述であり、しきい値の**選定**ではない。⑤を実装する際は",
              "⑦と同型の手続き（目的関数と方針の事前宣言→チューニング専用データで選定）を踏む。"]
    out_md.write_text("\n".join(R), encoding="utf-8")
    print("\n".join(R))
    print("->", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
