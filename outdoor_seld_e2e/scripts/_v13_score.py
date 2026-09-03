# -*- coding: utf-8 -*-
"""v13 の採点表（2026-09-03）。

2つの見方:
  A. v12 fold2 val（旧文法・雨なし）で 旧モデル(ft2/w3) と v13モデル を同じ土俵で比較 → データ変更の効果
  B. v13 fold2 val（新文法・雨20%）で plan 列（rain / motion）別に層別 → in-distribution の成績
     ＋ サイレンの距離帯別フレーム再現率（S1 の効果を直接見る。GTは可聴ゲート済み）

各行= 通知v4.2採用構成の 至近到達/強到達/注意/安全抑制/リード ＋ 至近捕捉/誤捕捉/距離誤差（_hp_score と同一定義）。

使い方:
  python scripts/_v13_score.py <出力md> --meta v12|v13 <ラベル>=<csv> ...
  例: python scripts/_v13_score.py out/v13_score/A_v12val.md --meta v12 ft2=... v13ft=...
      python scripts/_v13_score.py out/v13_score/B_v13val.md --meta v13 --strata v13ft=... ft2=...
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


HP = _load("hpscore", "_hp_score.py")
v4, V42, EV, SEL = HP.v4, HP.V42, HP.EV, HP.SEL
META_DIRS = {"v12": ROOT / "out/dataset_outdoor_siren_v12/metadata_dist",
             "v13": ROOT / "out/dataset_outdoor_siren_v13/metadata_dist"}
PLAN_V13 = ROOT / "out/dataset_outdoor_siren_v13/plan/assignment_v13.csv"
SIREN_BINS = [(0, 50), (50, 100), (100, 200), (200, 500), (500, 1e9)]


def load_plan_cols():
    out = {}
    with open(PLAN_V13, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["clip_id"]] = r
    return out


def filter_csv(csv_path: Path, keep: set, dst: Path) -> Path:
    """予測CSVをクリップ集合で絞った一時ファイルを作る（採点器はファイル入力のため）。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, encoding="utf-8") as f, open(dst, "w", encoding="utf-8", newline="\n") as w:
        for line in f:
            if line.split(",", 1)[0] in keep:
                w.write(line)
    return dst


def siren_recall_by_dist(csv_path: Path, meta_dir: Path, clips: set):
    """サイレン(class0)のGTフレーム（可聴ゲート済み）に対し、同フレーム・同クラス・方位20°以内の
    予測があった率を GT距離帯別に返す。"""
    pred = defaultdict(list)
    with open(csv_path, encoding="utf-8") as f:
        for line in f:
            g = line.strip().split(",")
            if len(g) >= 7 and int(g[2]) == 0 and g[0] in clips:
                pred[(g[0], int(g[1]))].append(float(g[4]))
    hit = defaultdict(int)
    tot = defaultdict(int)
    for clip in clips:
        p = meta_dir / f"{clip}.csv"
        if not p.exists():
            continue
        for line in open(p, encoding="utf-8"):
            g = line.strip().split(",")
            if len(g) != 6 or int(g[1]) != 0:
                continue
            k, az, d = int(g[0]), float(g[3]), float(g[5])
            b = next(i for i, (lo, hi) in enumerate(SIREN_BINS) if lo <= d < hi)
            tot[b] += 1
            if any(abs((az - a + 180) % 360 - 180) <= 20.0 for a in pred.get((clip, k), [])):
                hit[b] += 1
    return [(SIREN_BINS[b], hit[b], tot[b]) for b in range(len(SIREN_BINS))]


def main() -> int:
    args = sys.argv[1:]
    out_md = Path(args.pop(0))
    meta_key = "v12"
    strata = False
    items = []
    while args:
        a = args.pop(0)
        if a == "--meta":
            meta_key = args.pop(0)
        elif a == "--strata":
            strata = True
        else:
            items.append(a.split("=", 1))
    HP.META = META_DIRS[meta_key]
    meta_dir = HP.META
    plan = load_plan_cols() if meta_key == "v13" else {}
    tmpdir = ROOT / "out/v13_score/_tmp"

    R = [f"# v13 採点表 — {out_md.stem}（val= {meta_key} fold2・通知v4.2採用構成）", "",
         "| 予測 | 至近到達 | **強到達** | 注意到達 | 安全抑制 | リード中央 | ≥2.5s | 発火数 "
         "| 至近捕捉 | 誤捕捉 | 至近推定距離 | 距離誤差 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for label, csv_path in items:
        p = Path(csv_path)
        p = p if p.is_absolute() else ROOT / p
        if not p.exists():
            R.append(f"| {label} | （未着: {p.name}） |")
            print(R[-1], flush=True)
            continue
        R.append(HP.row(label, p))
        print(R[-1], flush=True)
        if strata and plan:
            for col, vals in (("rain", ["", "light", "moderate", "heavy"]),
                              ("motion", ["static", "walk"])):
                for v in vals:
                    keep = {c for c, r in plan.items() if r["split"] == "fold2" and r[col] == v}
                    sub = filter_csv(p, keep, tmpdir / f"{label}_{col}_{v or 'none'}.csv")
                    R.append(HP.row(f"{label}・{col}={v or 'none'}（{len(keep)}本）", sub))
                    print(R[-1], flush=True)
    if strata and plan:
        R += ["", "## サイレンの距離帯別フレーム再現率（GT=可聴ゲート済みラベル・方位20°以内）", "",
              "| 予測 | " + " | ".join(f"{lo:.0f}〜{hi:.0f}m" if hi < 1e8 else f"{lo:.0f}m〜"
                                      for lo, hi in SIREN_BINS) + " |",
              "| --- | " + " | ".join("---" for _ in SIREN_BINS) + " |"]
        clips = {c for c, r in plan.items() if r["split"] == "fold2"}
        for label, csv_path in items:
            p = Path(csv_path)
            p = p if p.is_absolute() else ROOT / p
            if not p.exists():
                continue
            rec = siren_recall_by_dist(p, meta_dir, clips)
            R.append(f"| {label} | " + " | ".join(
                f"{100*h/t:.1f}% ({t:,})" if t else "—" for _, h, t in rec) + " |")
            print(R[-1], flush=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(R) + "\n", encoding="utf-8")
    print("->", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
