# -*- coding: utf-8 -*-
"""通知 v4.5「流れモード」の掃引（2026-09-03 事前宣言 §3〜§4）。長尺セット v1 の予測に 9 構成を当てて 1 枚の表にする。

使い方:
  python scripts/_long_sweep.py --pred out/dataset_outdoor_long_v1/pred/val_all_causal.csv --split fold40 --out out/long_v1/sweep_fold40.md
  python scripts/_long_sweep.py --oracle --split fold40                      # 自己検査（GT→規則）
判断基準は宣言 §4（幹線歩道の注意/分 −30% 以上・害 ≤ 2%・至近の強到達 −1pt 以内・警告変化 0）。
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


LS = _load("long_score", "_long_score.py")
GRID = [None] + [(K, W, C) for K in (2, 3) for W in (10.0, 20.0) for C in (10.0, 20.0)]


def run_config(clips, plan, preds, flow):
    agg = defaultdict(lambda: defaultdict(float))
    for clip in clips:
        gt = LS.load_gt(clip)
        fd, fw = LS.gt_as_pred(gt) if preds is None else preds.get(clip, ({}, {}))
        s = LS.score_clip(clip, fd, fw, gt, flow)
        for grp in ((plan[clip]["scene"],), ("all",)):
            for k, v in s.items():
                agg[grp[0]][k] += v
            agg[grp[0]]["n"] += 1
    return agg


def main() -> int:
    a = sys.argv
    split = a[a.index("--split") + 1] if "--split" in a else "fold40"
    plan = {r["clip_id"]: r for r in csv.DictReader(open(LS.DS / "plan/assignment_long_v1.csv", encoding="utf-8"))}
    clips = [c for c in plan if plan[c]["split"] == split and (LS.DS / "metadata_dist" / f"{c}.csv").exists()]
    preds = None if "--oracle" in a else LS.load_pred_long(a[a.index("--pred") + 1])
    base = None
    L = [f"# v4.5 流れモード 掃引 — {split}（{len(clips)} 本）" + ("・オラクル" if preds is None else "・モデル予測"), "",
         "| 構成 | 幹線歩道: 中/分 | 減り | 抑えた中 | 害 | 至近の強到達（全体） | 警告/本（全体） | 住宅街: 中/分 | 判定 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for flow in GRID:
        agg = run_config(clips, plan, preds, flow)
        aw = agg.get("arterial_walk", defaultdict(float)); al = agg["all"]; rs = agg.get("residential", defaultdict(float))
        n_aw = max(aw["n"], 1)
        mid_pm = aw["mid"] / n_aw
        reach = 100 * al["reached"] / al["close_cars"] if al["close_cars"] else float("nan")
        warn = al["warn"] / max(al["n"], 1)
        if flow is None:
            base = (mid_pm, reach, warn)
            L.append(f"| なし | {mid_pm:.2f} | — | — | — | {reach:.1f}% | {warn:.2f} | {rs['mid']/max(rs['n'],1):.2f} | 基準 |")
            continue
        red = 100 * (base[0] - mid_pm) / base[0] if base[0] > 0 else 0.0
        harm = 100 * aw["harm"] / aw["mid_supp"] if aw["mid_supp"] else 0.0
        ok = red >= 30 and harm <= 2 and reach >= base[1] - 1 and abs(warn - base[2]) < 1e-9
        L.append(f"| K={flow[0]} W={flow[1]:.0f} C={flow[2]:.0f} | {mid_pm:.2f} | −{red:.0f}% | {aw['mid_supp']:.0f} | "
                 f"{aw['harm']:.0f}/{aw['mid_supp']:.0f}（{harm:.1f}%） | {reach:.1f}% | {warn:.2f} | {rs['mid']/max(rs['n'],1):.2f} | {'候補' if ok else '×'} |")
    txt = "\n".join(L)
    print(txt)
    if "--out" in a:
        p = Path(a[a.index("--out") + 1]); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
