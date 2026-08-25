# -*- coding: utf-8 -*-
"""LINK_DEG（同一物体の連結幅）の角度掃引。

背景: 2026-08-26、本人「角度試す実験を行ってください」。
これまで比べたのは **±25°(v3.4以前) と ±60°(v3.4) の2点だけ**で、
`md/design/通知v4.1_最接近予測_2026-08-18.md` §247 でも LINK_DEG は「工学的選択」と
記録されている。「なぜ60度か」に答えられるよう、他の角度も同じ土俵で採点する。

**val（検証データ）で回す。** 確定評価セット(1,800)は「1回だけ採点」と事前登録済みで、
そこでパラメータを掃引するとテストセットでのチューニングになるため触らない。
val は設計上「モデル選択・通知しきい値の決定」に使う枠。

LINK_DEG は後処理（`track_series` の同一物体連結）のパラメータなので、
**再学習は不要**。保存済み推論 CSV に対して採点し直すだけ。

使い方:
  python scripts/_sweep_link_deg.py [pred_csv] [meta_dir]
  既定 = out/predictions_v12_w3/val_all.csv / out/dataset_outdoor_siren_v12/metadata_dist
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


E = _load("ev", "scripts/_notify_v4_eval.py")
# 注意: _notify_v4_eval.py は **自分用に別の v4 を読み込む**（importlib で毎回新しい
# モジュールオブジェクトになり sys.modules にも載らない）。掃引は必ず E が持っている
# ほうの v4 を書き換えること。別に _load した v4 を patch しても効かない（2026-08-26 実測）。
v4 = E.v4

PRED = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    ROOT / "out/predictions_v12_w3/val_all.csv"
META = Path(sys.argv[2]) if len(sys.argv) > 2 else \
    ROOT / "out/dataset_outdoor_siren_v12/metadata_dist"

ANGLES = [15, 20, 25, 30, 40, 45, 50, 60, 75, 90, 120, 180]
RULE = "cpa"                      # v4.1（本番の規則）

pred = v4.load_pred(PRED)
gts = E.gt_events(META, sorted(pred))
n_ev = sum(len(v) for v in gts.values())
print(f"pred = {PRED.name} / クリップ {len(gts):,} / GTイベント {n_ev:,}")
print(f"規則 = v4.1({RULE})  AZ_MATCH={v4.AZ_MATCH}°（固定）  "
      f"現行 LINK_DEG={v4.LINK_DEG}°\n")

hdr = (f"{'±deg':>5} | {'至近到達':>16} | {'注意到達':>16} | "
       f"{'安全抑制':>16} | {'誤発火':>6} | {'発火計':>6} | {'リード中央':>9}")
print(hdr)
print("-" * len(hdr))

import numpy as np                                             # noqa: E402

rows = []
for deg in ANGLES:
    v4.track_series.__defaults__ = (float(deg),)   # 既定引数を差し替える
    assert v4.track_series.__defaults__[0] == float(deg)
    r = E.evaluate(pred, gts, RULE)
    st = r["stat"]

    def pct(tier):
        ok, n = st[tier]
        return (100.0 * ok / n if n else float("nan")), ok, n

    c, c_ok, c_n = pct("critical")
    a, a_ok, a_n = pct("caution")
    s, s_ok, s_n = pct("safe")
    lead = float(np.median(r["leads"])) if r["leads"] else float("nan")
    mark = "  ← 現行" if deg == int(v4.LINK_DEG) else ""
    print(f"{deg:>5} | {c:>6.1f}% ({c_ok:>3}/{c_n:>3}) | "
          f"{a:>6.1f}% ({a_ok:>3}/{a_n:>3}) | "
          f"{s:>6.1f}% ({s_ok:>4}/{s_n:>4}) | "
          f"{r['n_fa']:>6,} | {r['n_fire']:>6,} | {lead:>8.2f}s{mark}")
    rows.append((deg, c, a, s, r["n_fa"], r["n_fire"], lead))

v4.track_series.__defaults__ = (60.0,)             # 後片付け（既定へ戻す）

out = ROOT / "out" / "link_deg_sweep_val.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "w", encoding="utf-8", newline="") as f:
    f.write("link_deg,critical_pct,caution_pct,safe_suppress_pct,"
            "false_fire,total_fire,lead_median_s\n")
    for r in rows:
        f.write(",".join(f"{x:.4f}" if isinstance(x, float) else str(x)
                         for x in r) + "\n")
print(f"\nsaved: {out}")
