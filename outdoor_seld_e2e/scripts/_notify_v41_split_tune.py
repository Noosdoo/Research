# -*- coding: utf-8 -*-
"""パラメータを選ぶデータと、成績を報告するデータを分ける（2分割の相互検証）。

同じ val でしきい値を選んで同じ val で成績を出すと出来レースになる。
クリップを2つに割り、A で選んだ設定を B で採点、B で選んだ設定を A で採点する。
"""
import importlib.util
import itertools
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = Path("c:/Users/satos/research/outdoor_seld_e2e")
spec = importlib.util.spec_from_file_location(
    "nv4", R / "scripts" / "step12_notify_v4_ttc.py")
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
ev = importlib.util.spec_from_file_location("ev", R / "scripts" / "_notify_v4_eval.py")
E = importlib.util.module_from_spec(ev)
ev.loader.exec_module(E)
FPS = v4.FPS

PRED = (Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].endswith(".csv")
        else R / "out/predictions_v12_w3/val_all.csv")
pred = v4.load_pred(PRED)
gts = E.gt_events(R / "out/dataset_outdoor_siren_v12/metadata_dist", sorted(pred))
CLIPS = sorted(gts)
# クリップ名の末尾番号の偶奇で分割（決め打ち・再現可能）
SPLIT = {c: (int("".join(ch for ch in c if ch.isdigit())[-4:]) % 2) for c in CLIPS}
print(f"分割A {sum(1 for c in CLIPS if SPLIT[c] == 0):,}本 / "
      f"分割B {sum(1 for c in CLIPS if SPLIT[c] == 1):,}本", flush=True)


def sl(win):
    k = np.arange(win) - (win - 1) / 2.0
    return (k / (k * k).sum() * FPS)[::-1]


def precompute(win):
    f = sl(win)
    T = {}
    for clip in CLIPS:
        nf = max(pred[clip]) + 1
        for cls in v4.DIST_CLASSES:
            d_at, az_at = v4.track_series(pred[clip], cls, nf)
            if not d_at:
                continue
            fr = np.array(sorted(d_at))
            d = np.array([d_at[j] for j in fr])
            az = np.array([az_at[j] for j in fr])
            ddot = np.full(len(fr), np.nan)
            adot = np.full(len(fr), np.nan)
            brk = np.flatnonzero(np.diff(fr) != 1) + 1
            for a, b in zip(np.r_[0, brk], np.r_[brk, len(fr)]):
                if b - a < win:
                    continue
                ddot[a + win - 1:b] = np.convolve(d[a:b], f, mode="valid")
                adot[a + win - 1:b] = np.convolve(
                    np.unwrap(np.radians(az[a:b])), f, mode="valid")
            vr, vt = ddot, d * adot
            v2 = vr * vr + vt * vt
            with np.errstate(invalid="ignore", divide="ignore"):
                tc = -(d * vr) / v2
                dc = np.abs(d * d * adot) / np.sqrt(v2)
            bad = ~np.isfinite(tc) | ~np.isfinite(dc) | (v2 < 1e-9) | (tc < 0)
            dc[bad] = np.nan
            tc[bad] = np.nan
            T[(clip, cls)] = dict(fr=fr, d=d, az=az, dc=dc, tc=tc)
    return T


def runlen(mask, need):
    out = np.zeros(len(mask), bool)
    run = 0
    for i, m in enumerate(mask):
        run = run + 1 if m else 0
        if run >= need:
            out[i] = True
    return out


def fires(T, half, cs, cm, tw, tcau, dmax, need, rule="cpa"):
    res = defaultdict(dict)
    for (clip, cls), t in T.items():
        if half is not None and SPLIT[clip] != half:
            continue
        d, dc, tc, fr, az = t["d"], t["dc"], t["tc"], t["fr"], t["az"]
        if rule == "dist":
            mS, mM = d <= v4.T3, d <= v4.SUPP
            need = v4.CONFIRM
        else:
            gate = np.isfinite(dc) & (d <= dmax)
            with np.errstate(invalid="ignore"):
                mS = (gate & (dc <= cs) & (tc <= tw)) | (d <= v4.T3)
                mM = (gate & (dc <= cm) & (tc <= tcau)) | (d <= v4.SUPP)
        hM = runlen(mM, need)
        if not hM.any():
            continue
        hS = runlen(mS, need)
        mid = [(int(fr[i]), float(az[i]), float(d[i])) for i in np.flatnonzero(hM)]
        st = [(int(fr[i]), float(az[i]), float(d[i])) for i in np.flatnonzero(hS)]
        res[clip][cls] = v4._episodes_with_upgrade(mid, st)
    return res


def score(res, half):
    stat = defaultdict(lambda: [0, 0])
    leads, n_fa = [], 0
    for clip, evs in gts.items():
        if SPLIT[clip] != half:
            continue
        fl = [(f[0], f[1], f[2], f[3], cls)
              for cls, eps in res.get(clip, {}).items() for f in eps]
        used = [False] * len(fl)
        for e in evs:
            a, b = e["f0"] - E.WIN_PRE * FPS, e["cpa"] + E.WIN_POST * FPS
            hit = None
            for i, f in enumerate(fl):
                if used[i] or f[4] != e["cls"]:
                    continue
                if a <= f[0] <= b:
                    hit = i
                    break
            if e["tier"] == "safe":
                stat["safe"][1] += 1
                stat["safe"][0] += int(hit is None)
                if hit is not None:
                    used[hit] = True
                continue
            stat[e["tier"]][1] += 1
            if hit is not None:
                used[hit] = True
                stat[e["tier"]][0] += 1
                leads.append((e["cpa"] - fl[hit][0]) / FPS)
        n_fa += sum(1 for u in used if not u)
    L = np.array(leads) if leads else np.array([0.0])
    return dict(crit=100 * stat["critical"][0] / stat["critical"][1],
                caut=100 * stat["caution"][0] / stat["caution"][1],
                safe=100 * stat["safe"][0] / stat["safe"][1],
                lead=float(np.median(L)), lead25=float(100 * np.mean(L >= 2.5)),
                fa=n_fa, n=stat["critical"][1] + stat["caution"][1] + stat["safe"][1])


t0 = time.time()
PRE = {w: precompute(w) for w in (5, 9)}
GRID = list(itertools.product(
    (5, 9), ((1.5, 3.2), (1.0, 2.0), (0.7, 1.5), (0.5, 1.0)),
    ((2.5, 4.0), (1.5, 2.5), (1.0, 1.5)), (30.0, 15.0, 10.0), (2, 3, 4)))
print(f"前計算 {time.time() - t0:.0f}s / {len(GRID)}通り", flush=True)


def run_half(h, cfg=None, rule="cpa"):
    if rule == "dist":
        return score(fires(PRE[5], h, 0, 0, 0, 0, 0, 0, rule="dist"), h)
    vw, cs, cm, tw, tcau, dm, cf = cfg
    return score(fires(PRE[vw], h, cs, cm, tw, tcau, dm, cf), h)


BASE = {h: run_half(h, rule="dist") for h in (0, 1)}
for h in (0, 1):
    b = BASE[h]
    print(f"分割{'AB'[h]} v3.4(距離): 重大{b['crit']:.1f} 注意{b['caut']:.1f} "
          f"安全{b['safe']:.1f} リード{b['lead']:.2f}s >=2.5s{b['lead25']:.1f}% 誤{b['fa']}")

ALL = {h: [] for h in (0, 1)}
for h in (0, 1):
    for vw, (cs, cm), (tw, tcau), dm, cf in GRID:
        r = run_half(h, (vw, cs, cm, tw, tcau, dm, cf))
        r["cfg"] = (vw, cs, cm, tw, tcau, dm, cf)
        ALL[h].append(r)
print(f"探索 {time.time() - t0:.0f}s", flush=True)

# 選び方は2通りを事前に決めておく（後出しでいじらない）
POLICIES = {
    "安全重視": lambda rows, b: sorted(
        [r for r in rows if r["safe"] >= b["safe"] and r["crit"] >= b["crit"] - 1.0],
        key=lambda r: -r["lead"]),
    "リード重視": lambda rows, b: sorted(
        [r for r in rows if r["safe"] >= b["safe"] - 5.0 and r["crit"] >= b["crit"]],
        key=lambda r: -r["lead"]),
}
OUT = {}
for pol, pick in POLICIES.items():
    print(f"\n===== 方針: {pol} =====")
    for tune, rep in ((0, 1), (1, 0)):
        cand = pick(ALL[tune], BASE[tune])
        if not cand:
            print(f"  {'AB'[tune]}で選ぶ → 候補なし")
            continue
        cfg = cand[0]["cfg"]
        held = run_half(rep, cfg)
        b = BASE[rep]
        print(f"  {'AB'[tune]}で選び {'AB'[rep]}で採点  設定={cfg}")
        print(f"    v3.4 : 重大{b['crit']:>5.1f} 注意{b['caut']:>5.1f} 安全{b['safe']:>5.1f} "
              f"リード{b['lead']:.2f}s >=2.5s{b['lead25']:>4.1f}% 誤{b['fa']}")
        print(f"    v4.1 : 重大{held['crit']:>5.1f} 注意{held['caut']:>5.1f} "
              f"安全{held['safe']:>5.1f} リード{held['lead']:.2f}s "
              f"cannot>=2.5s{held['lead25']:>4.1f}% 誤{held['fa']}".replace("cannot", ""))
        print(f"    差   : 重大{held['crit']-b['crit']:+5.1f} 注意{held['caut']-b['caut']:+5.1f} "
              f"安全{held['safe']-b['safe']:+5.1f} リード{held['lead']-b['lead']:+.2f}s "
              f">=2.5s{held['lead25']-b['lead25']:+5.1f}pt 誤{held['fa']-b['fa']:+d}")
        OUT.setdefault(pol, []).append(dict(tune="AB"[tune], report="AB"[rep],
                                            cfg=list(cfg), held=held, base=b))
json.dump(OUT, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
print(f"\n{time.time() - t0:.0f}s")
