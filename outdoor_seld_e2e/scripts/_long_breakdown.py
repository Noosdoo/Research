# -*- coding: utf-8 -*-
"""長尺セット v1: 通知（強・中）を「帰属した車の最接近距離」で分類し、同じ車への再発火を数える（v4.5 結果 §2 の表を任意の予測で再現・2026-09-07）。

  段 | 合計（/分） | 至近の車（≤1.5 m） | 注意の車（1.5〜3.2 m） | 安全な車（>3.2 m） | 帰属なし | 同じ車への再発火
帰属 = _long_score.attribute（±0.5 s・≤30°・最も近い方位）。車の区分 = その車のクリップ内の最接近（水平距離）。
再発火 = 同じ車に、同段以上の通知が既に届いた後の通知。

使い方: python scripts/_long_breakdown.py --pred <val_all_causal.csv> [--split fold40] [--scene arterial_walk] [--out md]
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
spec = importlib.util.spec_from_file_location("_ls", ROOT / "scripts" / "_long_score.py")
LS = importlib.util.module_from_spec(spec); sys.modules["_ls"] = LS; spec.loader.exec_module(LS)

RANK = {"中": 1, "強": 2}


def tier_of_car(fr):
    d = min(v[1] for v in fr.values())
    return "至近" if d <= 1.5 else ("注意" if d <= 3.2 else "安全")


def main() -> int:
    a = sys.argv
    pred = LS.load_pred_long(a[a.index("--pred") + 1])
    split = a[a.index("--split") + 1] if "--split" in a else None
    scene = a[a.index("--scene") + 1] if "--scene" in a else None
    plan = {r["clip_id"]: r for r in csv.DictReader(open(LS.DS / "plan/assignment_long_v1.csv", encoding="utf-8"))}
    clips = [c for c, r in plan.items() if (split is None or r.get("split") == split) and (scene is None or r.get("scene", r.get("場面", "")) == scene)]
    cnt = {t: defaultdict(int) for t in ("強", "中")}
    total_min = 0.0
    for clip in clips:
        gt = LS.load_gt(clip)
        fd, fw = pred.get(clip, (dict(), dict()))
        eps = LS.episodes(fd, fw) if fd or fw else []
        total_min += LS.NFR / 10.0 / 60.0
        best = {}                                    # car -> 届いた最高段
        for j, az, tier, cls in eps:
            if tier not in RANK:
                continue
            key = LS.attribute((j, az), gt)
            cnt[tier]["合計"] += 1
            if key is None:
                cnt[tier]["帰属なし"] += 1
                continue
            cnt[tier][tier_of_car(gt[key])] += 1
            if best.get(key, 0) >= RANK[tier]:
                cnt[tier]["再発火"] += 1
            best[key] = max(best.get(key, 0), RANK[tier])
    L = [f"# 長尺 v1 の通知の内訳（{Path(a[a.index('--pred') + 1]).name}・{split or 'all'}・{scene or '全場面'}・{len(clips)} 本）", "",
         "| 段 | 合計 | /分 | 至近の車（≤1.5 m） | 注意の車（1.5〜3.2 m） | 安全な車（>3.2 m） | 帰属なし | 同じ車への再発火 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for t in ("強", "中"):
        n = cnt[t]["合計"] or 1
        pct = lambda k: f"{100 * cnt[t][k] / n:.0f}%"
        L.append(f"| {t} | {cnt[t]['合計']} | {cnt[t]['合計'] / max(total_min, 1e-9):.2f} | {pct('至近')} | {pct('注意')} | **{pct('安全')}** | {pct('帰属なし')} | {pct('再発火')} |")
    txt = "\n".join(L)
    print(txt)
    if "--out" in a:
        Path(a[a.index("--out") + 1]).write_text(txt + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
