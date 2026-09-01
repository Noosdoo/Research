# -*- coding: utf-8 -*-
"""v4.2チューニング専用val（1,800本）の生成ドライバ（_run_v12_gen.py と同型）。

出力先は **out/dataset_outdoor_siren_v42tune/**（新規ディレクトリ）。
既存の v12/v12_conf/v12_eval データセットには一切書かない。

使い方:
  PYTHONPATH=scripts:src python scripts/_run_v42tune_gen.py --rows 0-149   # シャード
  PYTHONPATH=scripts:src python scripts/_run_v42tune_gen.py --list         # 行数確認
決定論なので中断・再実行は同一ビットに収束（既存foaはスキップ）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import step10_v42tune_plan as plan  # noqa: E402
import step11_v12_render as v12  # noqa: E402

m9 = v12.m9


def main() -> None:
    rows = plan.v42tune_rows()          # m9.DS 付け替え前に呼ぶ（planの注意書き参照）
    assert len(rows) == 1800, len(rows)

    # 出力先を v42tune に切替（v12本体は不変更）
    m9.DS = ROOT / "out" / "dataset_outdoor_siren_v42tune"
    m9.WORK = m9.DS / "work"

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
        v12.generate_clip_v12(row)
        done += 1
        if done % 50 == 0:
            el = time.time() - t0
            print(f"[{lo}-{hi}] {i+1}/{len(part)} done={done} skip={skip} "
                  f"{el/max(done,1):.1f}s/clip", flush=True)
    print(f"[{lo}-{hi}] FINISHED done={done} skip={skip} {time.time()-t0:.0f}s",
          flush=True)


if __name__ == "__main__":
    main()
