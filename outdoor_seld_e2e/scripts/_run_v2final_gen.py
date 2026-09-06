# -*- coding: utf-8 -*-
"""確定評価 v2 の最終学習データの生成ドライバ（2026-09-07）。描画は v16 と同一（step11_v16_render）。
違いは (1) plan = out/dataset_outdoor_siren_v2final/plan/assignment_v2final.csv、(2) D1 SIREN_MIX を md/design/v2final_params.json から、
(3) 出力先 = out/dataset_outdoor_siren_v2final/ のみ（v16 以前には書かない）。

使い方:
  python scripts/_run_v2final_gen.py --list
  python scripts/_run_v2final_gen.py --rows 0-749     # シャード生成（サーバ）
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import step11_v16_render as v16r  # noqa: E402

m9 = v16r.m9
v13 = v16r.v13
PARAMS = ROOT / "md/design/v2final_params.json"
P = json.loads(PARAMS.read_text(encoding="utf-8"))
DS = ROOT / "out/dataset_outdoor_siren_v2final"
m9.DS = DS
m9.WORK = DS / "work"
v16r.PLAN_V15 = DS / "plan"
v13.SIREN_MIX = {k: float(v) for k, v in P["D1_SIREN_MIX"].items()}      # D1（描画時に読まれる module-global）
assert abs(sum(v13.SIREN_MIX.values()) - 1.0) < 1e-6, v13.SIREN_MIX


def load_plan() -> list:
    rows = []
    with open(DS / "plan" / "assignment_v2final.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["n_warnings"] = int(r["n_warnings"]); r["seed"] = int(r["seed"])
            rows.append(r)
    return rows


def main() -> None:
    rows = load_plan()
    assert len(rows) == int(P["N_ROWS_EXPECTED"]), len(rows)
    assert m9.DS.name == "dataset_outdoor_siren_v2final", m9.DS
    if "--list" in sys.argv:
        print(f"total rows: {len(rows)} -> {m9.DS} | SIREN_MIX={v13.SIREN_MIX} | params status={P.get('status')}")
        return
    if P.get("status") != "fixed":
        print(f"❌ params の status が fixed ではない（{P.get('status')}）。10 月末に数値を確定してから生成する")
        sys.exit(2)
    lo, hi = 0, len(rows) - 1
    if "--rows" in sys.argv:
        a, b = sys.argv[sys.argv.index("--rows") + 1].split("-")
        lo, hi = int(a), int(b)
    part = rows[lo:hi + 1]
    t0 = time.time(); done = skip = 0
    for i, row in enumerate(part):
        if (m9.DS / "foa" / f"{row['clip_id']}.flac").exists():
            skip += 1; continue
        v16r.generate_clip(row)
        done += 1
        if done % 50 == 0:
            print(f"[{lo}-{hi}] {i+1}/{len(part)} done={done} skip={skip} {(time.time()-t0)/max(done,1):.1f}s/clip", flush=True)
    print(f"[{lo}-{hi}] FINISHED done={done} skip={skip} {time.time()-t0:.0f}s -> {m9.DS}", flush=True)


if __name__ == "__main__":
    main()
