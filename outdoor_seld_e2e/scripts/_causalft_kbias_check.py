# -*- coding: utf-8 -*-
"""監査③: 乱数がワーカー間で複製され、各クリップが毎エポック同じ終端フレームkを
見ていた可能性の検査。もしそうなら、学習が特定のkに偏り、フレーム位置ごとの
精度に構造（凸凹）が出るはずである。"""
import sys
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = Path("c:/Users/satos/research/outdoor_seld_e2e")
META = R/"out/dataset_outdoor_siren_v12/metadata_dist"
CLS = {4,6,7}
def pairs(csv):
    pr = defaultdict(lambda: defaultdict(list))
    for line in open(csv, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) >= 7 and int(g[2]) in CLS:
            pr[g[0]][int(g[1])].append((int(g[2]), float(g[4]), float(g[6])))
    out=[]
    for clip, fr in pr.items():
        f = META/f"{clip}.csv"
        if not f.exists(): continue
        gt = defaultdict(list)
        for line in open(f, encoding="utf-8"):
            g = line.strip().split(",")
            if len(g)==6 and int(g[1]) in CLS:
                gt[int(g[0])].append((int(g[1]), float(g[3]), float(g[5])))
        for j, items in fr.items():
            for c,az,d in items:
                cand=[(abs((az-a+180)%360-180),dg) for cc,a,dg in gt.get(j,[]) if cc==c]
                if cand:
                    e,dg=min(cand)
                    if e<=20.0: out.append((j,d,dg))
    return np.array(out)
P = pairs(R/"out/causal_ft_2026-08-19/val_all_causalft.csv")
print(f"対にできた検出 {len(P):,}\n")
print("フレーム位置ごとの距離の相対誤差中央値（学習がkに偏っていれば凸凹が出る）")
print(f"{'フレーム':>10}{'n':>9}{'相対誤差中央':>13}")
prev=[]
for lo in range(40, 100, 5):
    m=(P[:,0]>=lo)&(P[:,0]<lo+5)
    if m.sum()<50: continue
    v=100*np.median(np.abs(P[m,1]-P[m,2])/P[m,2])
    prev.append(v)
    print(f"{lo:>4}-{lo+5:>3}{m.sum():>9,}{v:>12.1f}%")
a=np.array(prev)
print(f"\n  帯ごとのばらつき: 標準偏差 {a.std():.2f}pt / 範囲 {a.max()-a.min():.2f}pt")
print("  → 大きく凸凹していなければ、kの偏りは実害として現れていない")
