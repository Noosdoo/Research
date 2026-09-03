# -*- coding: utf-8 -*-
"""v13（合成データ修正の束）の全量生成ドライバ（fold1 7,200 + fold2 1,800 = 9,000本、シャード・再開可）。

出力先は **out/dataset_outdoor_siren_v13/** のみ（v11/v12 には書かない。ドライバ側でも assert）。

使い方:
  PYTHONPATH=scripts:src python scripts/_run_v13_gen.py --rows 0-749   # シャード（サーバ12並列）
  PYTHONPATH=scripts:src python scripts/_run_v13_gen.py --list
決定論なので中断・再実行は同一ビットに収束（既存foaはスキップ）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import step11_v13_render as v13  # noqa: E402

m9 = v13.m9


def main() -> None:
    rows = v13.load_plan_v13()
    assert len(rows) == 9000, len(rows)
    assert m9.DS.name == "dataset_outdoor_siren_v13", m9.DS
    if "--list" in sys.argv:
        print(f"total rows: {len(rows)} -> {m9.DS}")
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
        v13.generate_clip(row)
        done += 1
        if done % 50 == 0:
            el = time.time() - t0
            print(f"[{lo}-{hi}] {i+1}/{len(part)} done={done} skip={skip} "
                  f"{el/max(done,1):.1f}s/clip", flush=True)
    print(f"[{lo}-{hi}] FINISHED done={done} skip={skip} {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
