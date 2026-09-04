# -*- coding: utf-8 -*-
"""v15（v14 ＋ D13 マイク高さ）の生成ドライバ。出力先は out/dataset_outdoor_siren_v15b/ のみ。

使い方:
  python scripts/_run_v15_gen.py --stats          # 描画せず、critical 層の車の 3D 最接近が 1.5 m → mic_z でどう変わるか
  python scripts/_run_v15_gen.py --rows 0-749     # シャード生成（サーバ）
  python scripts/_run_v15_gen.py --list
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import step11_v15b_render as v15  # noqa: E402

m9 = v15.m9


def stats(rows: list) -> None:
    by_tier = {}
    t0 = time.time()
    for i, row in enumerate(rows):
        if row.get("scenario") != "v11core" or row.get("car_side") not in ("L", "R"):
            continue
        st = v15.cpa_stats(row)
        if "1.5" not in st or "v15" not in st:
            continue
        tier = row["danger_tier"] or "na"
        by_tier.setdefault(tier, []).append((st["1.5"][0], st["v15"][0], st["v15"][1], float(row["mic_z"])))
        if (i + 1) % 2000 == 0:
            print(f"  {i+1}/{len(rows)} {time.time()-t0:.0f}s", flush=True)
    print("| 危険層 | 本数 | 3D最接近 中央値 (1.5 m) | 3D最接近 中央値 (v15) | 横距離 中央値 | 3D≤1.5m の割合 (1.5 m → v15) | マイク高さ 平均 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for tier in ("critical", "caution", "safe", "na"):
        if tier not in by_tier:
            continue
        a = np.array(by_tier[tier])
        print(f"| {tier} | {len(a):,} | {np.median(a[:,0]):.2f} m | {np.median(a[:,1]):.2f} m | {np.median(a[:,2]):.2f} m | "
              f"{100*np.mean(a[:,0] <= 1.5):.0f}% → {100*np.mean(a[:,1] <= 1.5):.0f}% | {a[:,3].mean():.2f} m |")


def main() -> None:
    rows = v15.load_plan_v15()
    assert len(rows) == 9000, len(rows)
    assert m9.DS.name == "dataset_outdoor_siren_v15b", m9.DS
    if "--list" in sys.argv:
        print(f"total rows: {len(rows)} -> {m9.DS}")
        return
    if "--stats" in sys.argv:
        stats(rows)
        return
    lo, hi = 0, len(rows) - 1
    if "--rows" in sys.argv:
        a, b = sys.argv[sys.argv.index("--rows") + 1].split("-")
        lo, hi = int(a), int(b)
    part = rows[lo:hi + 1]
    t0 = time.time()
    done = skip = 0
    for i, row in enumerate(part):
        if (m9.DS / "foa" / f"{row['clip_id']}.flac").exists():
            skip += 1
            continue
        v15.generate_clip(row)
        done += 1
        if done % 50 == 0:
            print(f"[{lo}-{hi}] {i+1}/{len(part)} done={done} skip={skip} {(time.time()-t0)/max(done,1):.1f}s/clip", flush=True)
    print(f"[{lo}-{hi}] FINISHED done={done} skip={skip} {time.time()-t0:.0f}s -> {m9.DS}", flush=True)


if __name__ == "__main__":
    main()
