# -*- coding: utf-8 -*-
"""step10_v2final_plan.py — 確定評価 v2 の最終学習データの割当表（2026-09-07）。

v13 → v14 → v15 → v16 の plan 生成器をそのまま鎖にして、つまみだけ md/design/v2final_params.json から差し替える
（D3 雨の比率・D2 雨のレベル・D4 歩行比率・D10 至近低速の割合・D13 高さの幅・高さ増強）。
seed の塩（SALT）は v13/v16 と同じなので、つまみが v16 と同じ値なら **assignment_v16.csv と 1 バイト違わず一致**する
（--check-v16 で確認。これが「鎖を壊していない」証拠）。D1 SIREN_MIX は描画側（_run_v2final_gen.py）で効く。

出力: out/dataset_outdoor_siren_v2final/plan/assignment_v2final.csv ＋ README_plan_v2final.md（params の SHA256・件数）
      中間の v13/v14/v15/v16 形式は plan/chain/ に残す。v13〜v16 の既存出力には書かない。

使い方: python scripts/step10_v2final_plan.py [--check-v16] [--params <json>]
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PARAMS_DEFAULT = ROOT / "md/design/v2final_params.json"
OUT = ROOT / "out/dataset_outdoor_siren_v2final/plan"
CHAIN = OUT / "chain"
V16_PLAN = ROOT / "out/dataset_outdoor_siren_v16/plan/assignment_v16.csv"


def _arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    params_path = Path(_arg("--params", str(PARAMS_DEFAULT)))
    P = json.loads(params_path.read_text(encoding="utf-8"))
    import step10_v13_plan as p13
    import step10_v14_plan as p14
    import step10_v15_plan as p15
    import step10_v16_plan as p16

    CHAIN.mkdir(parents=True, exist_ok=True)
    # v13: 歩行比率・雨
    p13.WALK_FRAC = float(P["D4_WALK_FRAC"])
    p13.RAIN_FRAC = float(P["D3_RAIN_FRAC"])
    p13.RAIN_KIND_P = {k: float(v) for k, v in P["RAIN_KIND_P"].items()}
    p13.RAIN_DBA = {k: (float(v[0]), float(v[1])) for k, v in P["D2_RAIN_DBA"].items()}
    p13.SALT = int(P["SALTS"]["v13"])
    p13.OUT_DIR = CHAIN
    p13.main()
    # v14: 至近低速
    p14.SRC_V13 = CHAIN / "assignment_v13.csv"
    p14.OUT_DIR = CHAIN
    p14.CLOSE_SLOW_FRAC = float(P["D10_CLOSE_SLOW_FRAC"])
    p14.main()
    # v15: 高さの幅
    p15.SRC_V14 = CHAIN / "assignment_v14.csv"
    p15.OUT_DIR = CHAIN
    p15.MIC_Z_RANGE = tuple(float(x) for x in P["D13_MIC_Z_RANGE"])
    p15.main()
    # v16: 高さ増強（×2）
    assert int(P["HEIGHT_AUG_COPIES"]) == 2, "高さ増強は ×2 だけ実装（v16 と同じ）"
    p16.SRC_V15 = CHAIN / "assignment_v15.csv"
    p16.OUT_DIR = CHAIN
    p16.MIC_Z_RANGE = tuple(float(x) for x in P["D13_MIC_Z_RANGE"])
    p16.SALT16 = int(P["SALTS"]["v16"])
    p16.main()

    src = CHAIN / "assignment_v16.csv"
    dst = OUT / "assignment_v2final.csv"
    shutil.copyfile(src, dst)
    with open(dst, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    n_exp = int(P["N_ROWS_EXPECTED"])
    assert len(rows) == n_exp, f"行数 {len(rows)} ≠ 期待 {n_exp}"
    folds = Counter(r["split"] for r in rows) if "split" in rows[0] else Counter()
    L = [f"# v2final plan（{len(rows):,} 行）— {params_path.name} sha256 {sha256(params_path)[:16]}… / status={P.get('status')}", "",
         f"- つまみ: 歩行 {p13.WALK_FRAC:.0%} / 雨 {p13.RAIN_FRAC:.0%} dB(A) {p13.RAIN_DBA} / 至近低速 {p14.CLOSE_SLOW_FRAC:.0%} / 高さ {p15.MIC_Z_RANGE} m ×{P['HEIGHT_AUG_COPIES']} / SALT {P['SALTS']}",
         f"- D1 SIREN_MIX {P['D1_SIREN_MIX']} は描画側（_run_v2final_gen.py）", f"- 内訳 split: {dict(folds)}",
         f"- assignment_v2final.csv sha256 {sha256(dst)}", ""]
    if "--check-v16" in sys.argv:
        same = V16_PLAN.exists() and sha256(V16_PLAN) == sha256(dst)
        L.append(f"- v16 との一致（つまみが v16 と同じなら一致するはず）: {'一致' if same else '不一致'}")
        print("v16 との一致:", "一致" if same else "不一致")
    (OUT / "README_plan_v2final.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:4]))
    print("->", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
