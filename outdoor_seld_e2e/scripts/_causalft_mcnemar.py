# -*- coding: utf-8 -*-
"""同じ508台の車について、条件間で「至近警告が届いたか」を対で比べる（McNemar）。"""
import sys, math
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
D = Path("c:/Users/satos/research/outdoor_seld_e2e/out/causal_ft_2026-08-19")
def fails(n):
    s = set()
    for i, line in enumerate(open(D/f"casebook_{n}.csv", encoding="utf-8")):
        if i == 0: continue
        g = line.strip().split(",")
        if len(g) >= 2: s.add((g[0], g[1]))
    return s
F = {n: fails(n) for n in ("future","causal","causal_calib","causal_ft")}
allc = set().union(*F.values())
N = 508
JP = {"future":"未来参照","causal":"因果・素","causal_calib":"因果+較正","causal_ft":"因果学習"}
print(f"至近到達（分母508台・casebookは未到達の台）")
for n, s in F.items():
    print(f"  {JP[n]:<10} 到達 {N-len(s):>3}/508 = {100*(N-len(s))/N:>5.1f}%  （未到達 {len(s)}）")
def mcnemar(a, b):
    # a,b は未到達集合。到達 = 補集合。b(旧のみ到達)=aで到達&bで未到達
    only_a = len(b - a); only_b = len(a - b)   # only_a: aで到達しbで未到達
    n = only_a + only_b
    if n == 0: return only_a, only_b, 1.0
    z = (abs(only_a-only_b)-1)/math.sqrt(n)
    return only_a, only_b, math.erfc(z/math.sqrt(2))
print("\n対応のある比較（同じ車で見る）")
pairs = [("causal","causal_calib"),("causal","causal_ft"),
         ("causal_calib","causal_ft"),("causal_ft","future")]
for x, y in pairs:
    a, b, p = mcnemar(F[x], F[y])
    print(f"  {JP[x]:<10} → {JP[y]:<10}: {JP[x]}だけ到達 {a:>3} / {JP[y]}だけ到達 {b:>3}  "
          f"p={p:.2e} {'有意' if p<0.05 else '有意でない'}")
print("\n因果学習が取りこぼした127台のうち、未来参照版も取りこぼしていた台:",
      len(F['causal_ft'] & F['future']), "/", len(F['causal_ft']))
print("因果学習が新たに取りこぼした（未来参照版は到達できていた）台:",
      len(F['causal_ft'] - F['future']))
