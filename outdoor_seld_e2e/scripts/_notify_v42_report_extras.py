# -*- coding: utf-8 -*-
"""v4.2採用構成の報告用追加集計 — 宣言§5の残り2項目（2026-09-01）。

1. **static / walk 別の内訳**（fold31・fold30）: 合成のwalkはマイク並進のみ・回転なし。
   自己回転の影響は実録で別途測る（この集計はその前段の並進影響の確認）
2. **旧val（fold2）での参考値**（w3・因果ft1の両予測）: **選定には使っていない**データでの
   同構成の成績。参考表示のみ

採用構成 = 宣言§7.5: brg5+mn4/4+rc(0.10,15)+link+cs1.3/cm1.6（安全維持版）

使い方: python scripts/_notify_v42_report_extras.py
出力: out/notify_v42_sweep2/report_extras.md
"""
from __future__ import annotations

import csv
import importlib.util
import sys
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


v4 = _load("nv4", "step12_notify_v4_ttc.py")
V42 = _load("nv42", "step12_notify_v42_bearing.py")
EV = _load("nv42ev", "_notify_v42_eval.py")

ADOPTED = V42.Cfg(route_c=True, adot_th=0.10, dn=15.0, link_pred=True,
                  cpa_strong=1.3, cpa_mid=1.6)


def motion_map(plan_csv: Path) -> dict:
    out = {}
    with open(plan_csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["clip_id"]] = r["motion"]
    return out


def score_pair(pred, meta_dir):
    """(v4.1, v4.2採用) のスコア対を返す。"""
    s_old = EV.score(pred, meta_dir, v4.run_rule(pred, "cpa"))
    s_new = EV.score(pred, meta_dir, V42.run_rule2(pred, ADOPTED))
    return s_old, s_new


def fmt_row(name, s_old, s_new):
    return (f"| {name} | {s_old['strong']:.1f}% → **{s_new['strong']:.1f}%** "
            f"({s_new['strong']-s_old['strong']:+.1f}) "
            f"| {s_old['safe']:.1f}% → **{s_new['safe']:.1f}%** "
            f"({s_new['safe']-s_old['safe']:+.1f}) "
            f"| {s_old['lead25']:.1f}% → {s_new['lead25']:.1f}% |")


def main() -> int:
    R = ["# v4.2採用構成の報告用追加集計（宣言§5の残り）", "",
         f"- 採用構成: `{ADOPTED}`",
         "- 表は「v4.1（旧規則）→ **v4.2（現行の正）**」。旧値はラベル付き参考", "",
         "## 1. static / walk 別（合成walk=並進のみ・回転なし）", "",
         "| データ・条件 | 強到達 | 安全抑制 | リード≥2.5s |",
         "| --- | --- | --- | --- |"]
    for tag, pred_p, meta_p, plan_p in [
        ("fold31", "out/predictions_v42tune2/val_all_causal.csv",
         "out/dataset_outdoor_siren_v42tune2/metadata_dist",
         "out/dataset_outdoor_siren_v42tune2/plan/assignment_v42tune2.csv"),
        ("fold30", "out/predictions_v42tune/val_all_causal.csv",
         "out/dataset_outdoor_siren_v42tune/metadata_dist",
         "out/dataset_outdoor_siren_v42tune/plan/assignment_v42tune.csv"),
    ]:
        pred = v4.load_pred(ROOT / pred_p)
        mm = motion_map(ROOT / plan_p)
        for motion in ("static", "walk"):
            sub = {c: v for c, v in pred.items() if mm.get(c) == motion}
            s_old, s_new = score_pair(sub, ROOT / meta_p)
            R.append(fmt_row(f"{tag}・{motion}（{len(sub):,}本）", s_old, s_new))
        print(f"{tag} done", flush=True)

    R += ["", "## 2. 旧val（fold2）での参考値 — **選定には未使用**", "",
          "旧valはv4.1の閾値選定・v4.2の診断/煙試験で使用済みのため、選定から除外した"
          "データ。同構成を当てた場合の参考成績。", "",
          "| 予測 | 強到達 | 安全抑制 | リード≥2.5s |",
          "| --- | --- | --- | --- |"]
    for tag, pred_p in [
        ("fold2・因果ft1（本番に近い）", "out/causal_ft_2026-08-19/val_all_causalft.csv"),
        ("fold2・w3（非因果）", "out/predictions_v12_w3/val_all.csv"),
    ]:
        pred = v4.load_pred(ROOT / pred_p)
        s_old, s_new = score_pair(pred, ROOT / "out/dataset_outdoor_siren_v12/metadata_dist")
        R.append(fmt_row(tag, s_old, s_new))
        print(f"{tag} done", flush=True)

    out_md = ROOT / "out/notify_v42_sweep2/report_extras.md"
    out_md.write_text("\n".join(R), encoding="utf-8")
    print("\n".join(R))
    print("->", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
