# -*- coding: utf-8 -*-
"""きれいな上限実験（トラック単位）。

前回の上限実験は「毎フレーム一番近い音源」を拾っていたため、同じクラスの車が
2台いるクリップで系列が別の車へ飛び移り、速度も角速度も壊れていた。
ここでは **GTの1トラックだけ** を追った系列に規則を当て、
規則そのものの実力（＝入力が完璧なときの天井）を測る。

段階:
  A) GT距離・GT方位（完璧な入力）
  B) GT方位 + 推定距離（距離だけが誤差）
  C) GT距離 + 推定方位（方位だけが誤差）
  D) 推定距離・推定方位だが**対応付けは正解**（追跡だけが完璧）
"""
import importlib.util
import itertools
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = Path("c:/Users/satos/research/outdoor_seld_e2e")
spec = importlib.util.spec_from_file_location(
    "nv4", R / "scripts" / "step12_notify_v4_ttc.py")
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
FPS = v4.FPS
META = R / "out/dataset_outdoor_siren_v12/metadata_dist"
PRED = (Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].endswith(".csv")
        else R / "out/predictions_v12_w3/val_all.csv")
pred = v4.load_pred(PRED)


def gt_tracks(clip):
    """[(cls, trk, {frame:(az,dist)})] を連続ラン単位で返す（1ラン=1イベント）。"""
    f = META / f"{clip}.csv"
    if not f.exists():
        return []
    per = defaultdict(dict)
    for line in open(f, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) < 6:
            continue
        c = int(g[1])
        if c not in v4.DIST_CLASSES:
            continue
        per[(c, int(g[2]))][int(g[0])] = (float(g[3]), float(g[5]))
    out = []
    for (c, t), fr in per.items():
        js = sorted(fr)
        run = [js[0]]
        for j in js[1:]:
            if j == run[-1] + 1:
                run.append(j)
            else:
                out.append((c, t, {k: fr[k] for k in run}))
                run = [j]
        out.append((c, t, {k: fr[k] for k in run}))
    return out


def sl(win):
    k = np.arange(win) - (win - 1) / 2.0
    return (k / (k * k).sum() * FPS)[::-1]


def match_pred(clip, cls, frames, az_gt):
    """GTトラックに対応する推定値を拾う（同フレームで方位が最も近い検出）。"""
    d_p, a_p = {}, {}
    for j in frames:
        cand = [(a, d) for (c, a, d) in pred.get(clip, {}).get(j, [])
                if c == cls and d is not None]
        if not cand:
            continue
        a, d = min(cand, key=lambda x: v4.cdiff(x[0], az_gt[j]))
        if v4.cdiff(a, az_gt[j]) <= 60.0:      # 明らかに別物は拾わない
            d_p[j], a_p[j] = d, a
    return d_p, a_p


def series(clip, cls, fr, mode, win):
    """mode に応じた (frames, d, az) を作る。無ければ None。"""
    js = sorted(fr)
    az_gt = {j: fr[j][0] for j in js}
    d_gt = {j: fr[j][1] for j in js}
    if mode == "A":
        d_at, az_at = d_gt, az_gt
    else:
        d_p, a_p = match_pred(clip, cls, js, az_gt)
        if not d_p:
            return None
        keys = sorted(d_p)
        d_at = {j: (d_gt[j] if mode == "C" else d_p[j]) for j in keys}
        az_at = {j: (az_gt[j] if mode == "B" else a_p[j]) for j in keys}
    ks = np.array(sorted(d_at))
    return ks, np.array([d_at[j] for j in ks]), np.array([az_at[j] for j in ks])


def derive(ks, d, az, win):
    f = sl(win)
    ddot = np.full(len(ks), np.nan)
    adot = np.full(len(ks), np.nan)
    brk = np.flatnonzero(np.diff(ks) != 1) + 1
    for a, b in zip(np.r_[0, brk], np.r_[brk, len(ks)]):
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
    return dc, tc


def first_fire(ks, d, dc, tc, cs, cm, tw, tcau, dmax, need, rule):
    """最初に鳴ったフレーム（強でも中でも）を返す。鳴らなければ None。"""
    if rule == "dist":
        m = d <= v4.SUPP
    else:
        gate = np.isfinite(dc) & (d <= dmax)
        with np.errstate(invalid="ignore"):
            m = (gate & (dc <= cm) & (tc <= tcau)) | (d <= v4.SUPP)
    run = 0
    for i, x in enumerate(m):
        run = run + 1 if x else 0
        if run >= need:
            return int(ks[i])
    return None


EVENTS = []
for clip in sorted(pred):
    for cls, trk, fr in gt_tracks(clip):
        if len(fr) < 20:
            continue
        d = np.array([v[1] for v in fr.values()])
        js = sorted(fr)
        cpa = js[int(np.argmin([fr[j][1] for j in js]))]
        dmin = float(d.min())
        EVENTS.append(dict(clip=clip, cls=cls, fr=fr, cpa=cpa, dmin=dmin,
                           tier=("critical" if dmin <= v4.T3
                                 else "caution" if dmin <= v4.SUPP else "safe")))
print(f"評価イベント {len(EVENTS):,}（1トラック=1イベント）", flush=True)

CACHE = {}


def evaluate(mode, win, cs, cm, tw, tcau, dmax, need, rule="cpa"):
    stat = defaultdict(lambda: [0, 0])
    leads = []
    for e in EVENTS:
        key = (id(e), mode, win)
        if key not in CACHE:
            s = series(e["clip"], e["cls"], e["fr"], mode, win)
            CACHE[key] = None if s is None else (s, derive(*s, win))
        got = CACHE[key]
        if got is None:
            stat[e["tier"]][1] += 1
            stat[e["tier"]][0] += int(e["tier"] == "safe")
            continue
        (ks, d, az), (dc, tc) = got
        j = first_fire(ks, d, dc, tc, cs, cm, tw, tcau, dmax, need, rule)
        j = None if (j is not None and j > e["cpa"] + FPS) else j
        stat[e["tier"]][1] += 1
        if e["tier"] == "safe":
            stat["safe"][0] += int(j is None)
        elif j is not None:
            stat[e["tier"]][0] += 1
            leads.append((e["cpa"] - j) / FPS)
    L = np.array(leads) if leads else np.array([0.0])
    return dict(crit=100 * stat["critical"][0] / stat["critical"][1],
                caut=100 * stat["caution"][0] / stat["caution"][1],
                safe=100 * stat["safe"][0] / stat["safe"][1],
                lead=float(np.median(L)), lead25=float(100 * np.mean(L >= 2.5)))


GRID = list(itertools.product(
    (5, 9), ((1.5, 3.2), (1.0, 2.0), (0.7, 1.5)),
    ((2.5, 4.0), (4.0, 6.0)), (30.0, 15.0), (2, 3, 4)))
NAMES = {"A": "GT距離 + GT方位（完璧）", "B": "推定距離 + GT方位",
         "C": "GT距離 + 推定方位", "D": "推定距離 + 推定方位（対応付けのみ正解）"}
BARS = (100.0, 98.0, 95.0, 90.0, 85.0)
print()
print("各段階で「安全抑制をこの水準に保ったまま出せるリード中央値」")
print()
print(f"{'入力の条件':<34}{'距離規則':>9} " + " ".join(f"{b:>5.0f}%" for b in BARS))
for mode in ("A", "C", "B", "D"):
    b = evaluate(mode, 5, 0, 0, 0, 0, 0, v4.CONFIRM, rule="dist")
    rows = []
    for win, (cs, cm), (tw, tcau), dm, cf in GRID:
        r = evaluate(mode, win, cs, cm, tw, tcau, dm, cf)
        r.update(win=win, cs=cs, cm=cm, tw=tw, tc=tcau, dm=dm, cf=cf)
        rows.append(r)
    cells = []
    for bar in BARS:
        ok = sorted([r for r in rows if r["safe"] >= bar], key=lambda r: -r["lead"])
        cells.append(f"{ok[0]['lead']:>5.2f}" if ok else "    -")
    print(f"{NAMES[mode]:<28}{b['lead']:>8.2f}s " + " ".join(cells)
          + f"   [距離規則の抑制 {b['safe']:.1f}%]")
print()
print("（- はその抑制率を満たす設定が無い。単位は秒＝リード中央値）")

print()
print("重大イベントの到達率（同じ列の設定で）")
print(f"{'入力の条件':<34}{'距離規則':>9} " + " ".join(f"{b:>5.0f}%" for b in BARS))
for mode in ("A", "C", "B", "D"):
    b = evaluate(mode, 5, 0, 0, 0, 0, 0, v4.CONFIRM, rule="dist")
    rows = [dict(evaluate(mode, win, cs, cm, tw, tcau, dm, cf),
                 win=win, cs=cs, cm=cm, tw=tw, tc=tcau, dm=dm, cf=cf)
            for win, (cs, cm), (tw, tcau), dm, cf in GRID]
    cells = []
    for bar in BARS:
        ok = sorted([r for r in rows if r["safe"] >= bar], key=lambda r: -r["lead"])
        cells.append(f"{ok[0]['crit']:>5.1f}" if ok else "    -")
    print(f"{NAMES[mode]:<28}{b['crit']:>8.1f}% " + " ".join(cells))
