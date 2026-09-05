# -*- coding: utf-8 -*-
"""step20 v3 の模擬試験（2026-09-06）: 至近（左後ろ）・安全・負例・前方 F・履歴不足・多重車の 6 行で、v4.3 の発火・分母の分離・方向の比較時点を確認する。
使い方: python scripts/_mock_realsmoke_v3.py → out/realsmoke_mock_v3/score_v3.md"""
import csv, math, subprocess, sys
from pathlib import Path
ROOT = Path(r"C:\Users\satos\research\outdoor_seld_e2e"); OUT = ROOT / "out" / "realsmoke_mock_v3"; OUT.mkdir(parents=True, exist_ok=True)
PY = r"C:\Users\satos\research\DynamicSound\.venv\Scripts\python.exe"

def car_track(clip, az0, az1, d0, d1, k0, k1, rows, cls=4):
    for k in range(k0, k1 + 1):
        f = (k - k0) / max(k1 - k0, 1)
        az = az0 + (az1 - az0) * f; d = d0 + (d1 - d0) * f
        rows.append(f"{clip},{k},{cls},0,{az:.0f},-5,{d:.2f}")

pred = []
# A: 至近（左後ろから接近、CPA 8.0 s に 1.0 m、その後遠ざかる）
car_track("clipA", 165, 100, 25.0, 1.0, 20, 80, pred); car_track("clipA", 100, 40, 1.0, 12.0, 81, 99, pred)
# B: 安全（右前方 5 m を通過）
car_track("clipB", -30, -120, 20.0, 5.0, 20, 80, pred); car_track("clipB", -120, -160, 5.0, 15.0, 81, 99, pred)
# C: 負例（予測なし） / D: 前方から至近（F）/ E: 履歴不足（CPA 4.0 s）/ Fm: 多重車
car_track("clipD", 5, 40, 25.0, 1.0, 20, 80, pred)
car_track("clipE", 170, 110, 20.0, 1.0, 5, 40, pred)
car_track("clipF", 160, 100, 20.0, 1.2, 20, 80, pred)
(OUT / "pred.csv").write_text("\n".join(pred) + "\n", encoding="utf-8")
cols = ["clip_id", "event_id", "take_id", "pair_id", "trial", "class", "quadrant", "t_start", "t_cpa", "区分", "状態", "横距離m", "n_car", "scored", "session_id"]
ann = [
    dict(clip_id="clipA", event_id="1", take_id="1", pair_id="", trial="A", **{"class": "car_drive"}, quadrant="B", t_start="2.0", t_cpa="8.0", 区分="A", 状態="静止", 横距離m="1.0", n_car="1", scored="1", session_id="S1"),
    dict(clip_id="clipB", event_id="1", take_id="2", pair_id="", trial="A", **{"class": "car_drive"}, quadrant="R", t_start="2.0", t_cpa="8.0", 区分="A", 状態="静止", 横距離m="5.0", n_car="1", scored="1", session_id="S1"),
    dict(clip_id="clipC", event_id="1", take_id="3", pair_id="", trial="C", **{"class": "none"}, quadrant="", t_start="0.0", t_cpa="10.0", 区分="C", 状態="静止", 横距離m="", n_car="0", scored="1", session_id="S1"),
    dict(clip_id="clipD", event_id="1", take_id="4", pair_id="", trial="A", **{"class": "car_drive"}, quadrant="F", t_start="2.0", t_cpa="8.0", 区分="A", 状態="静止", 横距離m="1.0", n_car="1", scored="1", session_id="S1"),
    dict(clip_id="clipE", event_id="1", take_id="5", pair_id="", trial="A", **{"class": "car_drive"}, quadrant="B", t_start="0.5", t_cpa="4.0", 区分="A", 状態="静止", 横距離m="1.0", n_car="1", scored="1", session_id="S1"),
    dict(clip_id="clipF", event_id="1", take_id="6", pair_id="", trial="A", **{"class": "car_drive"}, quadrant="B", t_start="2.0", t_cpa="8.0", 区分="A", 状態="静止", 横距離m="1.2", n_car="2", scored="1", session_id="S1"),
]
with open(OUT / "ann.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(ann)
r = subprocess.run([PY, str(ROOT / "scripts/step20_realsmoke_score_v3.py"), "--pred", str(OUT / "pred.csv"), "--ann", str(OUT / "ann.csv"), "--out", str(OUT / "score_v3.md")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
print(r.stdout[-3000:]); print(r.stderr[-2000:])
print((OUT / "score_v3.md").read_text(encoding="utf-8"))
