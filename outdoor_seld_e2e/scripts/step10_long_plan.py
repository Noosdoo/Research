# -*- coding: utf-8 -*-
"""長尺セット v1（60 秒 × 400 本）の計画表と場面仕様を作る（2026-09-03・本人判断「流れモードを v2 規則に入れる＝A」）。

目的: 幹線の歩道で車が次々通るときの「注意（中）の鳴らしすぎ」と、それを抑える流れモードの効きと害を測る。
      10 秒のクリップでは「続けて鳴る」状況が入らないので、60 秒の長い場面を新設する。
構成（束の設計案 §6.1 で宣言。交通量は本人指摘で 3 層に）:
  - 本数: fold40（選定用）200 本 ＋ fold41（検証用）200 本 ＝ 400 本、各 60 秒、晴れ・雨なし
  - 交通量: low 2〜4 / mid 4〜8 / high 8〜12 台/分 を等分（幹線）。住宅街は 0.5〜1 台/分
  - 場面: 幹線の歩道を歩く 70%、幹線で静止（信号待ち・バス停）15%、住宅街 15%
  - 至近を含む本: 幹線の 25%（左折巻き込み or 至近の徐行通過）、住宅街の 50%（至近の徐行通過）
  - 警告音: 後ろから自転車ベル 15%、クラクション 5%（規則の警告経路が流れモードの影響を受けないことの確認用）
幾何: 日本の左側通行。歩行者は左の歩道、右手の近い車線（横 3.0〜4.5 m）は後ろから来る車、遠い対向車線（横 6.5〜8.5 m）は前から。
音量・暗騒音は学習データと同じ規約（m9 の _draw_level / NOISE_DBA）。描画は step11_long_render.py。

使い方: python scripts/step10_long_plan.py   → out/dataset_outdoor_long_v1/plan/{assignment_long_v1.csv, specs/<clip>.json}
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import step11_v9_render as m9  # noqa: E402  (音量・暗騒音の規約だけ借りる。データセットには書かない)

OUT = ROOT / "out/dataset_outdoor_long_v1"
PLAN = OUT / "plan"
SALT = 20260940
CLIP_S = 60.0
N_PER_FOLD = 200
STRATA = {"low": (2.0, 4.0), "mid": (4.0, 8.0), "high": (8.0, 12.0)}   # 台/分（幹線・両車線の合計）
SCENE_P = {"arterial_walk": 0.70, "arterial_static": 0.15, "residential": 0.15}
NEAR_LAT = (3.0, 4.5)      # 近い車線（後ろから）
FAR_LAT = (6.5, 8.5)       # 対向車線（前から）
ART_SPEED = (30.0, 50.0)   # km/h
RES_LAT = (1.5, 3.0)
RES_SPEED = (15.0, 30.0)
RES_LAM = (0.5, 1.0)
P_CLOSE_ART, P_CLOSE_RES = 0.25, 0.50
P_BELL, P_HORN = 0.15, 0.05
NOISE_ART, NOISE_RES = (52.0, 65.0), (40.0, 50.0)


def car_event(rng, frm, side, lat, v_kmh, cpa_s):
    lv, l1m = m9._draw_level("car_drive", rng)
    return {"class": "car", "from": frm, "side": side, "lateral_m": round(lat, 2), "speed_kmh": round(v_kmh, 1),
            "cpa_s": round(cpa_s, 2), "level_db": round(l1m, 1), "f0": round(42.0 * rng.uniform(0.8, 1.2), 2)}


def make_spec(i: int, split: str, stratum: str, rng: np.random.Generator) -> tuple:
    scene = str(rng.choice(list(SCENE_P), p=list(SCENE_P.values())))
    motion = "walk" if scene == "arterial_walk" else ("static" if scene == "arterial_static" else ("walk" if rng.random() < 0.7 else "static"))
    v_walk = float(rng.uniform(*m9.WALK_SPEED))
    events, tags = [], {}
    if scene.startswith("arterial"):
        lam = float(rng.uniform(*STRATA[stratum]))
        near, far = float(rng.uniform(*NEAR_LAT)), float(rng.uniform(*FAR_LAT))
        n = int(rng.poisson(lam * (CLIP_S + 20.0) / 60.0))          # −10 s〜+70 s に到着（端の車も入れる）
        for _ in range(n):
            t = float(rng.uniform(-10.0, CLIP_S + 10.0))
            if rng.random() < 0.5:
                events.append(car_event(rng, "behind", "right", near, rng.uniform(*ART_SPEED), t))
            else:
                events.append(car_event(rng, "front", "right", far, rng.uniform(*ART_SPEED), t))
        noise = float(rng.uniform(*NOISE_ART))
        if rng.random() < P_CLOSE_ART:
            if rng.random() < 0.5:
                t_turn = float(rng.uniform(8.0, CLIP_S - 8.0))
                ev = car_event(rng, "behind", "right", near, 35.0, t_turn)
                ev.update({"geom": "turn", "turn": "left", "radius_m": 4.0, "ahead_m": 1.0, "t_turn": round(t_turn, 2),
                           "speed_knots": [[0, 35], [round(t_turn - 2.5, 2), 35], [round(t_turn, 2), 15], [CLIP_S, 15]]})
                ev.pop("cpa_s", None)
                events.append(ev); tags["close_type"] = "turn_left_across"
            else:
                ev = car_event(rng, "behind", "right", rng.uniform(0.8, 1.2), rng.uniform(10.0, 20.0), rng.uniform(5.0, CLIP_S - 5.0))
                events.append(ev); tags["close_type"] = "close_slow_pass"
    else:
        lam = float(rng.uniform(*RES_LAM))
        lat = float(rng.uniform(*RES_LAT))
        n = max(1, int(rng.poisson(lam * (CLIP_S + 20.0) / 60.0)))
        for _ in range(n):
            t = float(rng.uniform(-10.0, CLIP_S + 10.0))
            events.append(car_event(rng, "behind" if rng.random() < 0.5 else "front", "right", lat, rng.uniform(*RES_SPEED), t))
        noise = float(rng.uniform(*NOISE_RES))
        if rng.random() < P_CLOSE_RES:
            ev = car_event(rng, "behind", "right", rng.uniform(0.8, 1.5), rng.uniform(10.0, 25.0), rng.uniform(5.0, CLIP_S - 5.0))
            events.append(ev); tags["close_type"] = "close_slow_pass"
    if rng.random() < P_BELL:
        t = float(rng.uniform(6.0, CLIP_S - 3.0))
        lv, l1m = m9._draw_level("bike_bell", rng)
        events.append({"class": "bike_bell", "from": "behind", "side": "right", "lateral_m": 1.0, "speed_kmh": 15.0,
                       "cpa_s": round(t, 2), "t_on": round(t - 2.0, 2), "t_off": round(t, 2), "level_db": round(l1m, 1)})
        tags["has_bell"] = 1
    if rng.random() < P_HORN and scene.startswith("arterial"):
        t = float(rng.uniform(6.0, CLIP_S - 3.0))
        lv, l1m = m9._draw_level("horn", rng)
        events.append({"class": "horn", "from": "behind", "side": "right", "lateral_m": float(rng.uniform(*NEAR_LAT)), "speed_kmh": 35.0,
                       "cpa_s": round(t, 2), "t_on": round(t - 1.5, 2), "t_off": round(t - 0.7, 2), "level_db": round(l1m, 1)})
        tags["has_horn"] = 1
    clip_id = f"long_{split}_{i:04d}"
    spec = {"name": clip_id, "clip_s": CLIP_S, "scene_type": "arterial" if scene.startswith("arterial") else "residential",
            "scene": scene, "motion": motion, "walk_speed_kmh": round(v_walk * 3.6, 2), "noise_dba": round(noise, 1),
            "seed": int(rng.integers(1, 2**31 - 1)), "stratum": stratum, "lam_per_min": round(lam, 2), "events": events}
    row = {"clip_id": clip_id, "split": split, "stratum": stratum, "scene": scene, "motion": motion,
           "walk_speed_mps": round(v_walk, 3), "lam_per_min": round(lam, 2),
           "n_cars": sum(1 for e in events if e["class"] == "car"), "has_close": 1 if "close_type" in tags else 0,
           "close_type": tags.get("close_type", ""), "has_bell": tags.get("has_bell", 0), "has_horn": tags.get("has_horn", 0),
           "noise_dba": round(noise, 1), "seed": spec["seed"]}
    return row, spec


def main() -> int:
    (PLAN / "specs").mkdir(parents=True, exist_ok=True)
    rows = []
    strata = list(STRATA)
    for split, base in (("fold40", 0), ("fold41", 1000)):
        for i in range(N_PER_FOLD):
            rng = np.random.default_rng([SALT, base + i])
            row, spec = make_spec(i, split, strata[i % 3], rng)
            rows.append(row)
            (PLAN / "specs" / f"{row['clip_id']}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(PLAN / "assignment_long_v1.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    import collections
    L = ["# 長尺セット v1 計画台帳（自動生成: step10_long_plan.py）", "",
         f"60 秒 × {len(rows)} 本（fold40 選定用 {N_PER_FOLD} / fold41 検証用 {N_PER_FOLD}）。seed×{SALT} で決定論的。", ""]
    for key in ("stratum", "scene", "motion", "close_type", "has_bell", "has_horn"):
        L.append(f"- {key}: " + ", ".join(f"{k or '（なし）'}={v}" for k, v in sorted(collections.Counter(str(r[key]) for r in rows).items())))
    n_cars = [r["n_cars"] for r in rows]
    L.append(f"- 車の台数/本: 平均 {np.mean(n_cars):.1f}（最小 {min(n_cars)} 最大 {max(n_cars)}）")
    (PLAN / "README_plan_long_v1.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print("->", PLAN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
