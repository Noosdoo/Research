# -*- coding: utf-8 -*-
"""v4.2チューニング専用valのplan生成（2026-08-30、⑦Stage 2）。

## なぜ作るか

⑦（通知層の方位主体化 v4.2）は閾値・構成の再選定を伴う。既存val(fold2)は
v4.1の閾値選定で使用済みのため、**3回目の選定に使うと過適合が入る**。
そこで**チューニング専用のval**を新しい乱数で合成する
（→ md/seminar/中間発表_質疑と宿題_2026-08-30.md §4 / project_post_seminar_todo ⑦）。

## 構成

**既存val(fold2)と完全同構成**: core 1,200行 + v12ext 600行（kick225/bike225/train150）
= 1,800行。scenario・motion（static/walk 混合）・その他の列は**元の行をそのまま写し**、
clip_id（fold30_）・split（fold30）・seed（13G帯・全既存planと排他をassert）だけ差し替える。
同構成にするのは、ここで選んだ閾値が既存val・確定評価の分布へそのまま持ち運べるように
するため（層の比率が違うと最適点がずれる）。

## 使い方

  PYTHONPATH=scripts:src python scripts/step10_v42tune_plan.py
  → out/dataset_outdoor_siren_v42tune/plan/assignment_v42tune.csv + 台帳

生成ドライバ（scripts/_run_v42tune_gen.py）はCSVではなく本モジュールの
v42tune_rows() を直接使う（CSV再シリアライズによる型ズレを避ける）。
CSVは監査・員数用の記録。
"""
from __future__ import annotations

import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLAN_DIR = ROOT / "out" / "dataset_outdoor_siren_v42tune" / "plan"
SEED_BASE = 13_000_000_000      # 既存帯: core≈12.42G / conf=12G / eval=9.5G / ext=9.1G
SEED_STEP = 104_729
N_EXPECT = 1_800                # core fold2 1,200 + ext fold2 600


def v42tune_rows() -> list:
    """既存val(fold2)の行を写し、clip_id/split/seedだけ差し替えた1,800行を返す。

    ⚠️ 呼ぶ側は m9.DS を付け替える**前**に呼ぶこと（load_planはm9.PLAN=v11固定なので
    実際には影響しないが、順序を守れば仮に実装が変わっても安全）。
    """
    import step11_v12_render as v12r
    m9 = v12r.m9
    core = [r for r in m9.load_plan("core") if r["split"] == "fold2"]
    ext = [r for r in v12r.load_plan_v12ext() if r["split"] == "fold2"]
    assert len(core) == 1200, f"core fold2 = {len(core)}"
    assert len(ext) == 600, f"ext fold2 = {len(ext)}"
    scen_ext = Counter(r["scenario"] for r in ext)
    assert scen_ext == {"v12kick": 225, "v12bike": 225, "v12train": 150}, scen_ext

    rows = []
    for i, src in enumerate(core + ext):
        r = dict(src)
        r["clip_id"] = f"fold30_room1_mix{i + 1:04d}"
        r["split"] = "fold30"
        r["seed"] = SEED_BASE + i * SEED_STEP
        rows.append(r)
    return rows


def _all_existing_seeds() -> set:
    """out/*/plan/*.csv 全部から seed 列を集める（帯の記憶に頼らない排他検証）。"""
    seeds = set()
    for p in (ROOT / "out").glob("*/plan/*.csv"):
        with open(p, newline="") as f:
            rd = csv.DictReader(f)
            if not rd.fieldnames or "seed" not in rd.fieldnames:
                continue
            for r in rd:
                try:
                    seeds.add(int(r["seed"]))
                except (TypeError, ValueError):
                    pass
    return seeds


def main() -> None:
    rows = v42tune_rows()
    assert len(rows) == N_EXPECT

    existing = _all_existing_seeds()
    dup = {r["seed"] for r in rows} & existing
    assert not dup, f"seed衝突: {sorted(dup)[:5]}"
    # fold30 が他planで未使用なことも確認（clip_id衝突の予防）
    for p in (ROOT / "out").glob("*/plan/*.csv"):
        with open(p, newline="") as f:
            rd = csv.DictReader(f)
            if rd.fieldnames and "split" in rd.fieldnames:
                assert all(r["split"] != "fold30" for r in rd), f"fold30使用済み: {p}"

    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for r in rows for k in r})
    out_csv = PLAN_DIR / "assignment_v42tune.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # 由来CSVの指紋（ローカルとサーバーで同じ元データから作られたことの照合用）
    src_core = ROOT / "out/dataset_outdoor_siren_v11/plan/assignment_core.csv"
    src_ext = ROOT / "out/dataset_outdoor_siren_v12/plan/assignment_v12ext.csv"
    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
           for p in (src_core, src_ext)}

    cnt = Counter((r["scenario"], r["motion"]) for r in rows)
    ledger = ["# v4.2チューニング専用val plan台帳（自動生成: step10_v42tune_plan.py）", "",
              "既存val(fold2)と同構成・新seed帯。**選定専用**（学習・確定評価に混ぜない）。", "",
              f"- 本数: {len(rows):,}（core写し1,200 + ext写し600）",
              f"- seed: {SEED_BASE:,} + i×{SEED_STEP:,}"
              f"（min={rows[0]['seed']:,} max={rows[-1]['seed']:,}・全既存planと排他assert済み）",
              f"- 由来CSV sha256/16: {sha}", "",
              "| scenario | motion | 本数 |", "|---|---|---|"]
    for (scen, mot), n in sorted(cnt.items()):
        ledger.append(f"| {scen} | {mot} | {n} |")
    (PLAN_DIR / "tune_ledger_v42.md").write_text("\n".join(ledger), encoding="utf-8")
    print(f"wrote {out_csv} ({len(rows)} rows) + ledger")
    print(f"source sha: {sha}")


if __name__ == "__main__":
    main()
