# -*- coding: utf-8 -*-
"""v4.2チューニングval第2版（fold31）のplan生成（2026-09-01、宣言§7.3）。

fold30（第1版）は Phase A で「両分割で同一構成」が不成立＝採用なしとなった
（原因は選定規則の設計ミス。→ 通知v4.2_選定手順の事前宣言 §7.1）。
再選定は min-max 安定規則（§7.4）で行い、そのための**未見データ**として fold31 を作る。
fold30 は勝ち構成の追加検証にのみ使う。

構成は fold30 と同一（既存val(fold2)の写し・1,800本）。違いは
clip_id/split（fold31）と seed 帯（**14G**・全既存plan＋fold30と排他assert）だけ。

使い方:
  PYTHONPATH=scripts:src python scripts/step10_v42tune2_plan.py
生成ドライバは本モジュールの v42tune2_rows() を直接使う（CSVは監査・員数用の記録）。
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

PLAN_DIR = ROOT / "out" / "dataset_outdoor_siren_v42tune2" / "plan"
SEED_BASE = 14_000_000_000      # 既存帯: v42tune=13G / core≈12.42G / conf=12G / eval=9.5G
SEED_STEP = 104_729
N_EXPECT = 1_800


def v42tune2_rows() -> list:
    """既存val(fold2)の行を写し、clip_id/split/seedだけ差し替えた1,800行（fold31）。"""
    import step11_v12_render as v12r
    m9 = v12r.m9
    core = [r for r in m9.load_plan("core") if r["split"] == "fold2"]
    ext = [r for r in v12r.load_plan_v12ext() if r["split"] == "fold2"]
    assert len(core) == 1200 and len(ext) == 600, (len(core), len(ext))
    scen_ext = Counter(r["scenario"] for r in ext)
    assert scen_ext == {"v12kick": 225, "v12bike": 225, "v12train": 150}, scen_ext
    rows = []
    for i, src in enumerate(core + ext):
        r = dict(src)
        r["clip_id"] = f"fold31_room1_mix{i + 1:04d}"
        r["split"] = "fold31"
        r["seed"] = SEED_BASE + i * SEED_STEP
        rows.append(r)
    return rows


def _all_existing_seeds() -> set:
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
    rows = v42tune2_rows()
    assert len(rows) == N_EXPECT
    dup = {r["seed"] for r in rows} & _all_existing_seeds()
    assert not dup, f"seed衝突: {sorted(dup)[:5]}"
    for p in (ROOT / "out").glob("*/plan/*.csv"):
        with open(p, newline="") as f:
            rd = csv.DictReader(f)
            if rd.fieldnames and "split" in rd.fieldnames:
                assert all(r["split"] != "fold31" for r in rd), f"fold31使用済み: {p}"

    PLAN_DIR.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for r in rows for k in r})
    out_csv = PLAN_DIR / "assignment_v42tune2.csv"
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    src_core = ROOT / "out/dataset_outdoor_siren_v11/plan/assignment_core.csv"
    src_ext = ROOT / "out/dataset_outdoor_siren_v12/plan/assignment_v12ext.csv"
    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
           for p in (src_core, src_ext)}
    cnt = Counter((r["scenario"], r["motion"]) for r in rows)
    ledger = ["# v4.2チューニングval第2版(fold31) plan台帳（自動生成）", "",
              "fold30のPhase A採用なし（宣言§7.1）を受けた再選定用。**選定1回のみに使う**。", "",
              f"- 本数: {len(rows):,} / seed: {SEED_BASE:,} + i×{SEED_STEP:,}"
              f"（max={rows[-1]['seed']:,}・全既存plan+fold30と排他assert済み）",
              f"- 由来CSV sha256/16: {sha}", "",
              "| scenario | motion | 本数 |", "|---|---|---|"]
    for (scen, mot), n in sorted(cnt.items()):
        ledger.append(f"| {scen} | {mot} | {n} |")
    (PLAN_DIR / "tune2_ledger.md").write_text("\n".join(ledger), encoding="utf-8")
    print(f"wrote {out_csv} ({len(rows)} rows) + ledger")
    print(f"source sha: {sha}")


if __name__ == "__main__":
    main()
