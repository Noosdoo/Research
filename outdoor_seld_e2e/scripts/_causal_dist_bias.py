# -*- coding: utf-8 -*-
"""因果推論の距離推定が、窓の実音の割合（＝フレーム位置）でどう変わるかを見る。
先頭ほど窓がゼロ埋めで埋まっているので、そこだけ悪いなら「暖機の人工物」。"""
import sys
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = Path("c:/Users/satos/research/outdoor_seld_e2e")
META = R/"out/dataset_outdoor_siren_v12_conf/metadata_dist"
CAR = 4

def load(p):
    d = defaultdict(lambda: defaultdict(list))
    for line in open(p, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) < 7: continue
        if int(g[2]) != CAR: continue
        d[g[0]][int(g[1])].append((float(g[4]), float(g[6])))
    return d

full = load(R/"out/predictions_v12_conf/conf_all.csv")
caus = load(R/"out/causal_v12_w3_2026-08-18/conf_all_causal.csv")
clips = [f"fold20_room1_mix{i:04d}" for i in range(1, 1201)]

rows = []
for c in clips:
    f = META/f"{c}.csv"
    if not f.exists(): continue
    gt = defaultdict(list)
    for line in open(f, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) == 6 and int(g[1]) == CAR:
            gt[int(g[0])].append((float(g[3]), float(g[5])))
    for j, items in gt.items():
        for az_g, d_g in items:
            for tag, src in (("full", full), ("caus", caus)):
                cand = src.get(c, {}).get(j, [])
                if not cand: continue
                a, d = min(cand, key=lambda x: abs((x[0]-az_g+180)%360-180))
                if abs((a-az_g+180)%360-180) <= 20:
                    rows.append((tag, j, d_g, d))
A = np.array([(1 if t=="caus" else 0, j, g, p) for t,j,g,p in rows], dtype=float)
print(f"GTと対応が付いた検出: 通常 {int((A[:,0]==0).sum()):,} / 因果 {int((A[:,0]==1).sum()):,}\n")
print("フレーム帯ごとの距離推定（窓に含まれる実音の割合＝フレーム/100）")
print(f"{'フレーム':>10} {'実音%':>6} | {'通常 誤差中央':>13} {'因果 誤差中央':>13} | {'通常 n':>7} {'因果 n':>7}")
for lo, hi in ((0,20),(20,40),(40,60),(60,80),(80,100)):
    out = []
    for k in (0, 1):
        m = (A[:,0]==k) & (A[:,1]>=lo) & (A[:,1]<hi)
        out.append((np.median(A[m,3]-A[m,2]) if m.sum() else np.nan, int(m.sum())))
    print(f"{lo:>4}-{hi:>3}   {(lo+hi)/2:>5.0f}% | {out[0][0]:>12.2f}m {out[1][0]:>12.2f}m "
          f"| {out[0][1]:>7,} {out[1][1]:>7,}")
print("\n至近帯(GT<=1.5m)だけで見る")
print(f"{'フレーム':>10} | {'通常 誤差中央':>13} {'因果 誤差中央':>13} | {'通常が1.5m以下と出す率':>20} {'因果':>8}")
for lo, hi in ((0,20),(20,40),(40,60),(60,80),(80,100)):
    r = []
    for k in (0, 1):
        m = (A[:,0]==k)&(A[:,1]>=lo)&(A[:,1]<hi)&(A[:,2]<=1.5)
        r.append((np.median(A[m,3]-A[m,2]) if m.sum() else np.nan,
                  100*np.mean(A[m,3]<=1.5) if m.sum() else np.nan, int(m.sum())))
    print(f"{lo:>4}-{hi:>3}   | {r[0][0]:>12.2f}m {r[1][0]:>12.2f}m | "
          f"{r[0][1]:>19.1f}% {r[1][1]:>7.1f}%  (n={r[0][2]}/{r[1][2]})")
