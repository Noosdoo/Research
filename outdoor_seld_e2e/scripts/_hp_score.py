# -*- coding: utf-8 -*-
"""④ハイパラ感度測定の採点表（2026-09-02）。

val 1,800（fold2）の予測 val_all(.csv / _causal.csv) を並べて、
  1. 通知v4.2採用構成（brg5+mn4/4+rc(0.10,15)+link+cs1.3/cm1.6）の
     至近到達・強到達・注意到達・安全抑制・リード中央・≥2.5s・発火数
  2. ft2選定と同じ至近捕捉率／誤捕捉率／至近推定距離中央（_causalft_select.py と同一定義）
  3. 距離誤差（車・キック・バイク、方位20°以内で対応付いたペアの相対誤差中央値）
を1行ずつ出す。宣言= md/design/再学習④_ハイパラ感度_方針宣言_2026-09-02.md

使い方:
  python scripts/_hp_score.py <出力md> <ラベル>=<csv> [<ラベル>=<csv> ...]
  例: python scripts/_hp_score.py out/hp_sweep/stageB.md w3=out/predictions_v12_w3/val_all.csv \
        seed2=out/hp_sweep/ref/w3_seed2_val.csv lr1e-4=out/hp_sweep/B/lr1e-4_val.csv
"""
from __future__ import annotations

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


v4 = _load("nv4", "step12_notify_v4_ttc.py")
V42 = _load("nv42", "step12_notify_v42_bearing.py")
EV = _load("nv42ev", "_notify_v42_eval.py")
SEL = _load("nvsel", "_causalft_select.py")

META = ROOT / "out/dataset_outdoor_siren_v12/metadata_dist"
ADOPTED = V42.Cfg(route_c=True, adot_th=0.10, dn=15.0, link_pred=True,
                  cpa_strong=1.3, cpa_mid=1.6)


def dist_err(csv):
    """方位20°以内で対応付いた (推定, GT) ペアの相対誤差中央値（全フレーム・距離クラス）。"""
    P = SEL.pairs(csv, META)          # 列0=推定距離, 列1=GT距離（フレーム40以降のみ）
    if len(P) == 0:
        return float("nan"), 0
    rel = np.abs(P[:, 0] - P[:, 1]) / np.maximum(P[:, 1], 0.1)
    return float(100 * np.median(rel)), len(P)


def row(label, csv):
    pred = v4.load_pred(csv)
    s = EV.score(pred, META, V42.run_rule2(pred, ADOPTED))
    P = SEL.pairs(csv, META)
    close, safe = P[P[:, 1] <= 1.5, 0], P[P[:, 1] > 3.2, 0]
    cap = 100 * np.mean(close <= SEL.TH) if len(close) else float("nan")
    fp = 100 * np.mean(safe <= SEL.TH) if len(safe) else float("nan")
    med = float(np.median(close)) if len(close) else float("nan")
    rel, npair = dist_err(csv)
    return (f"| {label} | {s['crit']:.1f}% | **{s['strong']:.1f}%** | {s['caut']:.1f}% "
            f"| {s['safe']:.1f}% | {s['lead']:.2f}s | {s['lead25']:.1f}% | {s['n_fire']:,} "
            f"| {cap:.1f}% | {fp:.2f}% | {med:.2f}m | {rel:.1f}% ({npair:,}) |")


def main() -> int:
    out_md = Path(sys.argv[1])
    items = [a.split("=", 1) for a in sys.argv[2:]]
    R = [f"# ④ハイパラ感度 採点表 — {out_md.stem}", "",
         "val 1,800（fold2）。通知= v4.2採用構成。捕捉率/誤捕捉/推定距離= ft2選定と同一定義"
         "（GT≤1.5m を 1.5m しきい値で捕まえる率 / GT>3.2m を ≤1.5m と出す率 / フレーム40以降）。"
         "距離誤差= 方位20°以内ペアの相対誤差中央値(ペア数)。", "",
         "| 予測 | 至近到達 | **強到達** | 注意到達 | 安全抑制 | リード中央 | ≥2.5s | 発火数 "
         "| 至近捕捉 | 誤捕捉 | 至近推定距離 | 距離誤差 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for label, csv in items:
        p = Path(csv)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            R.append(f"| {label} | （未着: {p.name}） |")
            print(R[-1], flush=True)
            continue
        R.append(row(label, p))
        print(R[-1], flush=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(R) + "\n", encoding="utf-8")
    print("->", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
