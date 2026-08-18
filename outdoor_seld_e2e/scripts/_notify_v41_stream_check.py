# -*- coding: utf-8 -*-
"""通知v4.1をリアルタイムと同じ「逐次1フレームずつ」で回し、
オフライン採点との差を測る。

オフラインの `_episodes_with_upgrade` は、エピソード内に強があると
**エピソード全体を1件の強**として報告する。実機はそうはできない:
中が成立した瞬間に中を鳴らし、あとで強になったら鳴らし直す。
その差（通知回数・最初に鳴る時刻）を定量化する。
"""
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = Path("c:/Users/satos/research/outdoor_seld_e2e")
sp = importlib.util.spec_from_file_location("nv4", R / "scripts" / "step12_notify_v4_ttc.py")
v4 = importlib.util.module_from_spec(sp)
sp.loader.exec_module(v4)
ev = importlib.util.spec_from_file_location("ev", R / "scripts" / "_notify_v4_eval.py")
E = importlib.util.module_from_spec(ev)
ev.loader.exec_module(E)
FPS = v4.FPS

pred = v4.load_pred(R / "out/predictions_v12_w3/val_all.csv")
gts = E.gt_events(R / "out/dataset_outdoor_siren_v12/metadata_dist", sorted(pred))


def stream_fires(d_at, az_at, nframes):
    """逐次実行。フレームjの判定にj以降の情報を一切使わない。

    返り値: [(発火フレーム, 方位, tier, 距離)] — 実機が実際に鳴らす列
    （中→強の格上げは**2件**として出る）
    """
    runs = {"cS": 0, "cM": 0, "fS": 0, "fM": 0}
    out = []
    ep_open = False           # 中エピソードが開いているか
    ep_last_j, ep_last_az = -99, None
    ep_strong_done = False
    for j in range(nframes):
        d = d_at.get(j)
        if d is None:
            for k in runs:
                runs[k] = 0
            continue
        # --- ここまでの過去だけで予測を作る ---
        vel = v4.closing_speed(d_at, j)
        adot = v4.azimuth_rate(az_at, j)
        dc, tc = v4.cpa_of(d, None if vel is None else -vel, adot)
        okS = dc is not None and dc <= v4.CPA_STRONG_M and tc <= v4.TTC_WARN
        okM = dc is not None and dc <= v4.CPA_MID_M and tc <= v4.TTC_CAUTION
        runs["cS"] = runs["cS"] + 1 if okS else 0
        runs["cM"] = runs["cM"] + 1 if okM else 0
        runs["fS"] = runs["fS"] + 1 if d <= v4.T3 else 0
        runs["fM"] = runs["fM"] + 1 if d <= v4.SUPP else 0
        hitS = runs["cS"] >= v4.CONFIRM_CPA or runs["fS"] >= v4.CONFIRM
        hitM = runs["cM"] >= v4.CONFIRM_CPA or runs["fM"] >= v4.CONFIRM
        if not hitM:
            continue
        # エピソードの継続判定（v3.4と同一: フレーム差<=1 かつ 方位差<=25度）
        cont = (ep_open and j - ep_last_j <= 1
                and v4.cdiff(az_at[j], ep_last_az) <= v4.AZ_MATCH)
        if not cont:
            ep_open, ep_strong_done = True, False
            out.append((j, az_at[j], "中", d))       # まず中を鳴らす
        if hitS and not ep_strong_done:
            ep_strong_done = True
            out.append((j, az_at[j], "強", d))       # 強になった時点で鳴らし直す
        ep_last_j, ep_last_az = j, az_at[j]
    return out


off_n = stream_n = 0
first_off, first_str = {}, {}
gap = []
for clip, evs in gts.items():
    nf = max(pred[clip]) + 1
    for cls in v4.DIST_CLASSES:
        d_at, az_at = v4.track_series(pred[clip], cls, nf)
        if not d_at:
            continue
        off = v4.fires_cpa(d_at, az_at, nf)
        stm = stream_fires(d_at, az_at, nf)
        off_n += len(off)
        stream_n += len(stm)
        for f in off:
            first_off.setdefault((clip, cls), []).append(f)
        for f in stm:
            first_str.setdefault((clip, cls), []).append(f)

print(f"通知の総数: オフライン採点 {off_n:,} / 実機（逐次） {stream_n:,} "
      f"（+{stream_n - off_n:,} = +{100*(stream_n-off_n)/off_n:.0f}%）")
print("  差の正体: オフラインは「中→強」を1件に畳むが、実機は中と強を別々に鳴らす\n")

# GTイベントごとに「最初に何か鳴った時刻」を比べる
lead_off, lead_str, tier_at_first = [], [], defaultdict(int)
for clip, evs in gts.items():
    for e in evs:
        if e["tier"] == "safe":
            continue
        a, b = e["f0"] - E.WIN_PRE * FPS, e["cpa"] + E.WIN_POST * FPS
        for src, acc in ((first_off, lead_off), (first_str, lead_str)):
            fl = sorted(src.get((clip, e["cls"]), []))
            hit = next((f for f in fl if a <= f[0] <= b), None)
            if hit is not None:
                acc.append((e["cpa"] - hit[0]) / FPS)
                if src is first_str:
                    tier_at_first[hit[2]] += 1
print(f"最初に鳴るまでの余裕（危険イベント）")
print(f"  オフライン採点: 中央値 {np.median(lead_off):.2f}s (n={len(lead_off):,})")
print(f"  実機（逐次）  : 中央値 {np.median(lead_str):.2f}s (n={len(lead_str):,})")
print(f"  → 実機のほうが先に鳴る差 {np.median(lead_str) - np.median(lead_off):+.2f}s "
      f"（中を先に出すぶん）")
print(f"  最初の通知の段階: 中 {tier_at_first['中']:,}件 / 強 {tier_at_first['強']:,}件")

print("\n規則そのものの遅れ（未来を一切見ないので、これは純粋な待ち時間）")
print(f"  最接近の予測: 速度窓 {v4.VEL_WIN}fr({v4.VEL_WIN/FPS:.1f}s) "
      f"+ 確認 {v4.CONFIRM_CPA}fr({v4.CONFIRM_CPA/FPS:.1f}s) = "
      f"{(v4.VEL_WIN + v4.CONFIRM_CPA)/FPS:.1f}s")
print(f"  距離の保険  : 確認 {v4.CONFIRM}fr({v4.CONFIRM/FPS:.1f}s) のみ = "
      f"{v4.CONFIRM/FPS:.1f}s")
