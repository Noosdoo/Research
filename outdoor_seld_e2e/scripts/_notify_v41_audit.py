# -*- coding: utf-8 -*-
"""通知v4.1の自己監査（2026-08-18）。報告済みの主張を疑ってかかる。

検査項目:
  A 有意性     — 改善量は運の範囲か（対応のあるMcNemar検定）
  B リードの公平性 — 中央値の伸びは「届いたイベントが増えた」ことの副産物ではないか
  C 時刻ずれ   — 距離は j 時点、傾きは窓の中心時点。この不整合の影響は
  D 仰角の無視 — 方位だけの角速度で足りるか（3Dの角速度と比較）
  E 誤発火の中身 — 「紐づかない発火」は幽霊か、最接近を過ぎた鳴り続けか
  F 分割の妥当性 — 偶奇分割で2群の中身が偏っていないか
  G 採点の順序依存 — 貪欲マッチングはイベントの並び順に依存しないか

使い方: python scripts/_notify_v41_audit.py [pred.csv] [metadata_dist]
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "nv4", ROOT / "scripts" / "step12_notify_v4_ttc.py")
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)
ev = importlib.util.spec_from_file_location("ev", ROOT / "scripts" / "_notify_v4_eval.py")
E = importlib.util.module_from_spec(ev)
ev.loader.exec_module(E)
FPS = v4.FPS

PRED = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out/predictions_v12_w3/val_all.csv"
META = Path(sys.argv[2]) if len(sys.argv) > 2 else \
    ROOT / "out/dataset_outdoor_siren_v12/metadata_dist"

# 仰角つきで読み直す（本体の load_pred は方位と距離しか持たない）
pred3d = defaultdict(lambda: defaultdict(list))
for line in open(PRED, encoding="utf-8"):
    p = line.strip().split(",")
    if len(p) < 7:
        continue
    pred3d[p[0]][int(p[1])].append((int(p[2]), float(p[4]), float(p[5]), float(p[6])))
pred3d = dict(pred3d)
pred = v4.load_pred(PRED)
gts = E.gt_events(META, sorted(pred))
print(f"クリップ {len(gts):,} / GTイベント {sum(len(v) for v in gts.values()):,}\n")


def sl(win):
    k = np.arange(win) - (win - 1) / 2.0
    return (k / (k * k).sum() * FPS)[::-1]


def track3d(frames, cls, nframes, link=v4.LINK_DEG):
    """v4.1と同じ連結規則で (frame, az, el, dist) 系列を作る。"""
    d_at, az_at, el_at, prev = {}, {}, {}, None
    for j in range(nframes):
        cand = [(a, e, d) for (c, a, e, d) in frames.get(j, []) if c == cls]
        if not cand:
            prev = None
            continue
        if prev is not None:
            lk = [x for x in cand if v4.cdiff(x[0], prev) <= link]
            if lk:
                cand = lk
        a, e, d = min(cand, key=lambda x: x[2])
        d_at[j], az_at[j], el_at[j], prev = d, a, e, a
    return d_at, az_at, el_at


def derive(fr, d, az, el, win, mode):
    """mode: base=方位のみ・j時点の生d / align=傾きと同じ直線上のd / el3d=3D角速度"""
    f = sl(win)
    ddot = np.full(len(fr), np.nan)
    om = np.full(len(fr), np.nan)
    dfit = d.astype(float).copy()
    brk = np.flatnonzero(np.diff(fr) != 1) + 1
    for a, b in zip(np.r_[0, brk], np.r_[brk, len(fr)]):
        if b - a < win:
            continue
        s = slice(a + win - 1, b)
        ddot[s] = np.convolve(d[a:b], f, mode="valid")
        if mode == "el3d":
            # 3Dの単位方向ベクトルの変化率＝真の角速度
            aa, ee = np.radians(az[a:b]), np.radians(el[a:b])
            u = np.stack([np.cos(ee) * np.cos(aa), np.cos(ee) * np.sin(aa),
                          np.sin(ee)], axis=1)
            du = np.stack([np.convolve(u[:, k], f, mode="valid") for k in range(3)],
                          axis=1)
            om[s] = np.linalg.norm(du, axis=1)
        else:
            om[s] = np.abs(np.convolve(np.unwrap(np.radians(az[a:b])), f, "valid"))
        if mode == "align":
            # 最小二乗直線を窓の端(j)で評価した値＝傾きと時刻の整合が取れたd
            w = np.ones(win) / win
            mean_d = np.convolve(d[a:b], w, mode="valid")
            dfit[s] = mean_d + ddot[s] * ((win - 1) / 2.0) / FPS
    vr, vt = ddot, dfit * om
    v2 = vr * vr + vt * vt
    with np.errstate(invalid="ignore", divide="ignore"):
        tc = -(dfit * vr) / v2
        dc = np.abs(dfit * dfit * om) / np.sqrt(v2)
    bad = ~np.isfinite(tc) | ~np.isfinite(dc) | (v2 < 1e-9) | (tc < 0)
    dc[bad] = np.nan
    tc[bad] = np.nan
    return dfit, dc, tc


def runlen(mask, need):
    out = np.zeros(len(mask), bool)
    run = 0
    for i, m in enumerate(mask):
        run = run + 1 if m else 0
        if run >= need:
            out[i] = True
    return out


def fires_all(mode="base", win=v4.VEL_WIN, rule="cpa"):
    res = defaultdict(dict)
    for clip in gts:
        nf = max(pred[clip]) + 1
        for cls in v4.DIST_CLASSES:
            d_at, az_at, el_at = track3d(pred3d[clip], cls, nf)
            if not d_at:
                continue
            fr = np.array(sorted(d_at))
            d = np.array([d_at[j] for j in fr])
            az = np.array([az_at[j] for j in fr])
            el = np.array([el_at[j] for j in fr])
            if rule == "dist":
                dd = d
                hS = runlen(d <= v4.T3, v4.CONFIRM)
                hM = runlen(d <= v4.SUPP, v4.CONFIRM)
            else:
                dd, dc, tc = derive(fr, d, az, el, win, mode)
                gate = np.isfinite(dc) & (dd <= v4.D_MAX_TTC)
                with np.errstate(invalid="ignore"):
                    cS = gate & (dc <= v4.CPA_STRONG_M) & (tc <= v4.TTC_WARN)
                    cM = gate & (dc <= v4.CPA_MID_M) & (tc <= v4.TTC_CAUTION)
                # 本体と同じく、距離保険はCONFIRM・最接近予測はCONFIRM_CPAで別々に数える
                hS = runlen(cS, v4.CONFIRM_CPA) | runlen(dd <= v4.T3, v4.CONFIRM)
                hM = runlen(cM, v4.CONFIRM_CPA) | runlen(dd <= v4.SUPP, v4.CONFIRM)
            if not hM.any():
                continue
            mk = [(int(fr[i]), float(az[i]), float(dd[i])) for i in np.flatnonzero(hM)]
            st = [(int(fr[i]), float(az[i]), float(dd[i])) for i in np.flatnonzero(hS)]
            res[clip][cls] = v4._episodes_with_upgrade(mk, st)
    return res


def score(res, order="asis"):
    """order='time' でイベントを時刻順に処理（貪欲マッチングの順序依存の検査）。"""
    per, leads, fa = {}, {}, []
    n_late = n_fa = 0
    for clip, evs in gts.items():
        fl = [(f[0], f[1], f[2], f[3], cls)
              for cls, eps in res.get(clip, {}).items() for f in eps]
        fl.sort(key=lambda x: x[0])
        used = [False] * len(fl)
        order_evs = sorted(evs, key=lambda e: e["f0"]) if order == "time" else evs
        for e in order_evs:
            a, b = e["f0"] - E.WIN_PRE * FPS, e["cpa"] + E.WIN_POST * FPS
            hit = None
            for i, f in enumerate(fl):
                if used[i] or f[4] != e["cls"]:
                    continue
                if a <= f[0] <= b:
                    hit = i
                    break
            key = (clip, e["cls"], e["track"], e["f0"])
            per[key] = (e["tier"], hit is not None)
            if hit is not None:
                used[hit] = True
                if e["tier"] != "safe":
                    leads[key] = (e["cpa"] - fl[hit][0]) / FPS
        # 紐づかない発火の中身: どれかのイベントの最接近より後か
        for i, u in enumerate(used):
            if u:
                continue
            n_fa += 1
            same = [e for e in evs if e["cls"] == fl[i][4]]
            if same and any(fl[i][0] > e["cpa"] + E.WIN_POST * FPS for e in same):
                n_late += 1
    return per, leads, n_fa, n_late


def mcnemar(pairs):
    """対応のある2値比較。b=旧のみ成功, c=新のみ成功。両側p（正規近似）。"""
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if y and not x)
    if b + c == 0:
        return b, c, 1.0
    z = (abs(b - c) - 1) / np.sqrt(b + c)          # 連続修正つき
    from math import erfc
    return b, c, float(erfc(z / np.sqrt(2)))


print("=" * 72)
print("A. 改善量は運の範囲か（対応のあるMcNemar検定・同じイベントで新旧を比較）")
print("=" * 72)
P_d, L_d, fa_d, late_d = score(fires_all(rule="dist"))
P_c, L_c, fa_c, late_c = score(fires_all())
keys = sorted(set(P_d) & set(P_c))
for tier, jp in (("critical", "至近到達"), ("caution", "注意到達"), ("safe", "安全抑制")):
    ks = [k for k in keys if P_d[k][0] == tier]
    # safeは「鳴らない」が成功なので反転
    inv = tier == "safe"
    pairs = [((not P_d[k][1]) if inv else P_d[k][1],
              (not P_c[k][1]) if inv else P_c[k][1]) for k in ks]
    od = 100 * np.mean([p[0] for p in pairs])
    nw = 100 * np.mean([p[1] for p in pairs])
    b, c, p = mcnemar(pairs)
    sig = "有意" if p < 0.05 else "**有意でない**"
    print(f"  {jp} n={len(ks):>4}: {od:>5.1f}% → {nw:>5.1f}% ({nw-od:+.1f}pt) "
          f"旧だけ成功{b:>3} / 新だけ成功{c:>3}  p={p:.4f} {sig}")

print()
print("=" * 72)
print("B. リードの伸びは「届くイベントが増えた」副産物ではないか")
print("=" * 72)
both = sorted(set(L_d) & set(L_c))
a = np.array([L_d[k] for k in both])
b_ = np.array([L_c[k] for k in both])
print(f"  両方が届いたイベントだけ n={len(both):,}")
print(f"    中央値 {np.median(a):.2f}s → {np.median(b_):.2f}s ({np.median(b_)-np.median(a):+.2f}s)")
print(f"    1件ごとの差の中央値 {np.median(b_-a):+.2f}s / 改善した割合 "
      f"{100*np.mean(b_>a):.1f}% / 悪化した割合 {100*np.mean(b_<a):.1f}%")
print(f"    >=2.5s の割合 {100*np.mean(a>=2.5):.1f}% → {100*np.mean(b_>=2.5):.1f}%")
only_c = sorted(set(L_c) - set(L_d))
if only_c:
    print(f"  新規に届いたイベント n={len(only_c)}: リード中央値 "
          f"{np.median([L_c[k] for k in only_c]):.2f}s（全体中央値を押し上げる分）")
print(f"  参考（全体・母集団が違う）: {np.median(list(L_d.values())):.2f}s → "
      f"{np.median(list(L_c.values())):.2f}s")

print()
print("=" * 72)
print("C/D. 未検証の近似2つ — 時刻ずれ と 仰角の無視")
print("=" * 72)


def summarize(res, tag):
    per, leads, fa, late = score(res)
    st = defaultdict(lambda: [0, 0])
    for (tier, hit) in per.values():
        st[tier][1] += 1
        st[tier][0] += int((not hit) if tier == "safe" else hit)
    L = np.array(list(leads.values()))
    print(f"  {tag:<28} 至近{100*st['critical'][0]/st['critical'][1]:>5.1f} "
          f"注意{100*st['caution'][0]/st['caution'][1]:>5.1f} "
          f"安全{100*st['safe'][0]/st['safe'][1]:>5.1f} "
          f"リード{np.median(L):>5.2f}s 誤発火{fa:>5}")


summarize(fires_all(rule="dist"), "v3.4 距離規則")
summarize(fires_all("base"), "v4.1 採用版（方位のみ・生d）")
summarize(fires_all("align"), "C 傾きと時刻を揃えたd")
summarize(fires_all("el3d"), "D 仰角も入れた3D角速度")

print()
print("=" * 72)
print("E. 「紐づかない発火」の中身")
print("=" * 72)
for tag, (fa, late) in (("v3.4", (fa_d, late_d)), ("v4.1", (fa_c, late_c))):
    print(f"  {tag}: 計{fa:,} — うち同クラスの最接近を過ぎてからの発火 {late:,} "
          f"({100*late/max(fa,1):.1f}%)、それ以外（真に紐づかない）{fa-late:,}")

print()
print("=" * 72)
print("F. 偶奇分割で2群の中身が偏っていないか / G. 採点の順序依存")
print("=" * 72)
SPLIT = {c: int("".join(ch for ch in c if ch.isdigit())[-4:]) % 2 for c in gts}
for h in (0, 1):
    ks = [k for k in P_c if SPLIT[k[0]] == h]
    tiers = defaultdict(int)
    for k in ks:
        tiers[P_c[k][0]] += 1
    n = len(ks)
    print(f"  分割{'AB'[h]}: イベント{n:,} / 重大{100*tiers['critical']/n:.1f}% "
          f"注意{100*tiers['caution']/n:.1f}% 安全{100*tiers['safe']/n:.1f}%")
P_t, L_t, fa_t, _ = score(fires_all(), order="time")
diff = sum(1 for k in P_c if P_c[k][1] != P_t.get(k, (None, None))[1])
print(f"  イベントを時刻順に処理し直すと判定が変わる件数: {diff} / {len(P_c):,} "
      f"（誤発火 {fa_c:,} → {fa_t:,}）")
