# -*- coding: utf-8 -*-
"""発表で刺されやすい3点を確定評価セットの実データで確認する。
 ① 検出率と対になる誤検出（適合率）  ② 方向誤差の外れ値と量子化  ③ 距離誤差の距離帯別"""
import sys
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = Path("c:/Users/satos/research/outdoor_seld_e2e")
META = R/"out/dataset_outdoor_siren_v12_conf/metadata_dist"
JP = {0:"サイレン",1:"クラクション",2:"バック音",3:"自転車ベル",4:"車",5:"踏切・列車",6:"キックボード",7:"バイク"}
TOL = 20.0
def cd(a,b): return abs((a-b+180)%360-180)

pred = defaultdict(lambda: defaultdict(list))
for line in open(R/"out/predictions_v12_conf/conf_all.csv", encoding="utf-8"):
    g = line.strip().split(",")
    if len(g) >= 7:
        pred[g[0]][int(g[1])].append((int(g[2]), float(g[4]), float(g[5]), float(g[6])))
clips = [f"fold20_room1_mix{i:04d}" for i in range(1,1801)]

tp=defaultdict(int); fp=defaultdict(int); fn=defaultdict(int)
errs=defaultdict(list); dpairs=[]; azvals=[]
for c in clips:
    f = META/f"{c}.csv"
    if not f.exists(): continue
    gt = defaultdict(list)
    for line in open(f, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g)==6: gt[int(g[0])].append((int(g[1]), float(g[3]), float(g[4]), float(g[5])))
    frames = set(gt) | set(pred.get(c,{}))
    for j in frames:
        G = gt.get(j,[]); P = pred.get(c,{}).get(j,[])
        usedP=[False]*len(P)
        for cls,az,el,d in G:
            best,bi=None,None
            for i,(pc,pa,pe,pd_) in enumerate(P):
                if usedP[i] or pc!=cls: continue
                e = cd(pa,az)
                if best is None or e<best: best,bi=e,i
            if best is not None and best<=TOL:
                usedP[bi]=True; tp[cls]+=1; errs[cls].append(best); azvals.append(P[bi][1])
                if cls==4: dpairs.append((d, P[bi][3]))
            else: fn[cls]+=1
        for i,(pc,pa,pe,pd_) in enumerate(P):
            if not usedP[i]: fp[pc]+=1

print("① 検出率と対になる誤検出（フレーム単位・方位20度以内で一致とみなす）\n")
print(f"{'クラス':<12}{'再現率':>8}{'適合率':>8}{'F値':>8}{'誤検出数':>10}")
for k in sorted(JP):
    t,f_,n = tp[k], fp[k], fn[k]
    if t+n==0: continue
    r = t/(t+n); p = t/max(t+f_,1)
    print(f"{JP[k]:<12}{100*r:>7.1f}%{100*p:>7.1f}%{100*2*r*p/max(r+p,1e-9):>7.1f}%{f_:>10,}")

print("\n② 方向誤差の分布（中央値だけでは足りないという指摘）\n")
print(f"{'クラス':<12}{'中央':>7}{'p90':>7}{'p95':>7}{'最大':>8}{'0度の割合':>10}")
for k in sorted(JP):
    e = np.array(errs[k])
    if len(e)<50: continue
    print(f"{JP[k]:<12}{np.median(e):>6.1f}°{np.percentile(e,90):>6.1f}°"
          f"{np.percentile(e,95):>6.1f}°{e.max():>7.1f}°{100*np.mean(e==0):>9.1f}%")
A = np.array(azvals)
print(f"\n  方位の値が整数の割合: {100*np.mean(A==np.round(A)):.1f}%"
      f"  → 出力もGTも1度刻みで書かれている（LE=1.0°は分解能の下限に張り付いている）")

print("\n③ 距離誤差の距離帯別（車・通知が使うのは3〜30m）\n")
D = np.array(dpairs)
print(f"{'GT距離帯':>12}{'n':>9}{'中央絶対誤差':>12}{'相対誤差中央':>12}{'p90絶対':>10}")
for lo,hi in ((0,1.5),(1.5,3.2),(3.2,5),(5,10),(10,20),(20,30),(30,1e9)):
    m = (D[:,0]>=lo)&(D[:,0]<hi)
    if m.sum()<30: continue
    ae = np.abs(D[m,1]-D[m,0])
    print(f"{lo:>5.1f}-{hi if hi<1e8 else 999:>5.0f}m{m.sum():>9,}{np.median(ae):>11.2f}m"
          f"{100*np.median(ae/D[m,0]):>11.1f}%{np.percentile(ae,90):>9.2f}m")
