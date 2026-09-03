# -*- coding: utf-8 -*-
"""v14（v13 ＋ D10 至近・低速）の生成ドライバ。出力先は out/dataset_outdoor_siren_v14/ のみ。

使い方:
  python scripts/_run_v14_gen.py --stats            # 描画せず、至近フレームの分布を v13 と v14 で比較（全 9,000 行）
  python scripts/_run_v14_gen.py --proto 30         # close_slow 行の先頭 30 本を描画（試聴用）
  python scripts/_run_v14_gen.py --rows 0-749       # シャード生成（サーバ）
  python scripts/_run_v14_gen.py --list
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

import step11_v14_render as v14  # noqa: E402

m9 = v14.m9


def stats(rows: list) -> None:
    """v13（close_slow を無視）と v14 で、車がいるクリップの至近フレーム数を比べる。"""
    tot = {"v13": {"le1.0": 0, "le1.5": 0, "frames": 0, "clips": 0}, "v14": dict.fromkeys(["le1.0", "le1.5", "frames", "clips"], 0)}
    per_cs = []
    t0 = time.time()
    for i, row in enumerate(rows):
        r13 = dict(row); r13["close_slow"] = ""
        a = v14.close_frames(r13)
        b = v14.close_frames(row)
        for key, res in (("v13", a), ("v14", b)):
            if res["has_car"]:
                tot[key]["clips"] += 1
                tot[key]["frames"] += 100
                tot[key]["le1.0"] += res["le1.0"]
                tot[key]["le1.5"] += res["le1.5"]
        if row["close_slow"] == "1":
            per_cs.append((a["le1.5"], b["le1.5"]))
        if (i + 1) % 1500 == 0:
            print(f"  {i+1}/{len(rows)} {time.time()-t0:.0f}s", flush=True)
    print("| 版 | 車ありクリップ | ≤1.0m のフレーム（割合） | ≤1.5m のフレーム（割合） |")
    print("| --- | --- | --- | --- |")
    for key in ("v13", "v14"):
        t = tot[key]
        print(f"| {key} | {t['clips']:,} | {t['le1.0']:,}（{100*t['le1.0']/max(t['frames'],1):.2f}%） "
              f"| {t['le1.5']:,}（{100*t['le1.5']/max(t['frames'],1):.2f}%） |")
    if per_cs:
        p = np.array(per_cs)
        print(f"置換した {len(p)} 本: ≤1.5m のフレーム数 平均 {p[:,0].mean():.1f} → {p[:,1].mean():.1f} / 本")


def main() -> None:
    rows = v14.load_plan_v14()
    assert len(rows) == 9000, len(rows)
    assert m9.DS.name == "dataset_outdoor_siren_v14", m9.DS
    if "--list" in sys.argv:
        print(f"total rows: {len(rows)} -> {m9.DS}")
        return
    if "--stats" in sys.argv:
        stats(rows)
        return
    if "--proto" in sys.argv:
        n = int(sys.argv[sys.argv.index("--proto") + 1])
        part = [r for r in rows if r["close_slow"] == "1"][:n]
    else:
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
        v14.generate_clip(row)
        done += 1
        if done % 10 == 0:
            el = time.time() - t0
            print(f"{i+1}/{len(part)} done={done} skip={skip} {el/max(done,1):.1f}s/clip", flush=True)
    print(f"FINISHED done={done} skip={skip} {time.time()-t0:.0f}s -> {m9.DS}", flush=True)


if __name__ == "__main__":
    main()
