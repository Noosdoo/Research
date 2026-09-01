# -*- coding: utf-8 -*-
"""①多重車: 落ちているのは遠い車か近い車か（2026-08-30、todo①の先行測定）。

**目的**: 多重車の未報告（GT3台で3台とも報告34.8%）に投資すべきかの判断材料。
todo①: 「遠い車なら通知に効かないので投資しない」。

**測り方**: GTに同一フレーム2台以上の車がいるフレームで、予測の車を方位±30°の
貪欲マッチでGT車に対応付け、対応の付かなかったGT車（=落ちた車）と付いた車の
- GT距離の分布
- フレーム内の距離順位（1=最も近い車）
- 危険域との関係（≤1.5m / ≤3.2m / >3.2m）
を比べる。±30°は step16 の方向つきカバー率と同じ幅。

使い方:
  python scripts/_multicar_miss_anatomy.py <pred_csv> <metadata_distディレクトリ> <出力dir>
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
T3, SUPP = 1.5, 3.2


def cdiff(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def load_pred_cars(path: Path):
    """{clip: {frame: [az, ...]}}（クラス4のみ・複数トラック保持）"""
    out = defaultdict(lambda: defaultdict(list))
    for line in open(path, encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) >= 7 and int(p[2]) == CAR:
            out[p[0]][int(p[1])].append(float(p[4]))
        elif len(p) == 6 and int(p[2]) == CAR:
            out[p[0]][int(p[1])].append(float(p[3]))
    return dict(out)


def load_gt_cars(meta_dir: Path, clip: str):
    """{frame: [(az, dist), ...]}（クラス4のみ）"""
    f = meta_dir / f"{clip}.csv"
    if not f.exists():
        return {}
    out = defaultdict(list)
    for line in open(f, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) >= 6 and int(g[1]) == CAR:
            out[int(g[0])].append((float(g[3]), float(g[5])))
    return out


def main() -> int:
    pred_path, meta_dir, outdir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    pred = load_pred_cars(pred_path)

    rep, miss = [], []                  # (dist, rank, n_gt)
    n_frames = defaultdict(int)         # n_gt -> フレーム数
    n_allrep = defaultdict(int)         # n_gt -> 全台報告できたフレーム数
    miss_rank_by_n = defaultdict(lambda: defaultdict(int))   # n_gt -> rank -> 件数
    for clip in sorted(pred):
        gt = load_gt_cars(meta_dir, clip)
        for k, cars in gt.items():
            if len(cars) < 2:
                continue
            n = len(cars)
            n_frames[n] += 1
            order = sorted(range(n), key=lambda i: cars[i][1])
            rank_of = {i: order.index(i) + 1 for i in range(n)}
            paz = list(pred.get(clip, {}).get(k, []))
            matched = [False] * n
            for a in paz:                       # 貪欲: 各予測を最も近い未対応GTへ
                cand = [(cdiff(a, cars[i][0]), i) for i in range(n)
                        if not matched[i] and cdiff(a, cars[i][0]) <= 30.0]
                if cand:
                    matched[min(cand)[1]] = True
            if all(matched):
                n_allrep[n] += 1
            for i in range(n):
                (rep if matched[i] else miss).append(
                    (cars[i][1], rank_of[i], n))
                if not matched[i]:
                    miss_rank_by_n[n][rank_of[i]] += 1

    def q(v):
        a = np.array([x[0] for x in v])
        return (f"中央 {np.median(a):.2f}m / 四分位 {np.percentile(a,25):.2f}–"
                f"{np.percentile(a,75):.2f}m") if len(a) else "n/a"

    md = np.array([x[0] for x in miss]) if miss else np.array([])
    R = [f"# 多重車: 落ちた車の距離解剖 pred={pred_path.name}", "",
         f"- 対象: GT2台以上のフレーム（2台 {n_frames[2]:,} / 3台 {n_frames[3]:,}）",
         f"- 全台報告: 2台 {100*n_allrep[2]/max(n_frames[2],1):.1f}% / "
         f"3台 {100*n_allrep[3]/max(n_frames[3],1):.1f}%（±30°方位マッチ基準）", "",
         f"## 報告できた車 {len(rep):,}台分 vs 落ちた車 {len(miss):,}台分（フレーム×車）", "",
         f"- 報告: {q(rep)}",
         f"- **落ち: {q(miss)}**", ""]
    if len(md):
        R += [f"- 落ちた車のうち **>3.2m（そもそも抑制域）: {100*np.mean(md>SUPP):.1f}%** / "
              f"1.5–3.2m: {100*np.mean((md>T3)&(md<=SUPP)):.1f}% / "
              f"**≤1.5m（重大域）: {100*np.mean(md<=T3):.1f}%**", ""]
    R.append("## 落ちた車の距離順位（1=フレーム内で最も近い車）")
    R.append("")
    for n in sorted(miss_rank_by_n):
        tot = sum(miss_rank_by_n[n].values())
        row = " / ".join(f"順位{r}: {c:,} ({100*c/tot:.0f}%)"
                         for r, c in sorted(miss_rank_by_n[n].items()))
        R.append(f"- GT{n}台のフレーム: {row}")
    R += ["", "## 判断（todo①-1）", "",
          "todo①の基準=「遠い車なら通知に効かないので投資しない」。",
          "上の「落ちた車の≤1.5m比率」と「順位1（最近接）の落ち」が小さければ投資しない。"]
    out_md = outdir / "multicar_miss.md"
    out_md.write_text("\n".join(R), encoding="utf-8")
    print("\n".join(R))
    print("->", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
