# -*- coding: utf-8 -*-
"""v4.3 の設計診断 — 「安全×すり抜け型」に v4.2 が出す誤った強警告の機序（2026-09-03）。

引き継ぎ（md/design/引き継ぎ_通知層v4.3_検討依頼_2026-09-03.md）: fold31 の型別表で
安全(>3.2m)×すり抜け型 n=501 の強が v4.1 61 → v4.2 114 に倍増。
部品別の帰属（同表を部品OFFで再計算・fold31）: cs1.3→1.0 で 114→91、routeC OFF で 114→90、
link OFF で 116 → **cs と routeC が半分ずつ**、どちらも重大×対向型の強を約16件ずつ減らす代償つき。

ここでは v4.2 採用構成のまま、**誤った強の「最初の強フレーム」で何が成立していたか**を個票にする:
  - 発火経路: rc（定方位接近）／cpa（d_cpa≤cs & t_cpa≤2.5）／ins（距離保険 d≤1.5）
  - その瞬間の 推定距離 d・GT距離・d_cpa・t_cpa・測定adot・GT adot（同フレーム前後）・ddot
  - 対照として 重大×対向型 の正しい強（最初の強フレーム）も同じ列で出す
⚠️ fold31 は v4.2 の選定に使ったデータ。ここでは**設計診断のみ**（v4.3の選定は新val fold32 で行う）。

使い方: python scripts/_notify_v43_diag.py  → out/notify_v43_diag/casebook.csv / summary.md
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


v4 = _load("nv4", "step12_notify_v4_ttc.py")
V42 = _load("nv42", "step12_notify_v42_bearing.py")
DG = _load("nv42diag", "_notify_v42_diag.py")
Q2 = _load("nv42q2", "_notify_v42_q2_table.py")

PRED = ROOT / "out/predictions_v42tune2/val_all_causal.csv"
META = ROOT / "out/dataset_outdoor_siren_v42tune2/metadata_dist"
OUT = ROOT / "out/notify_v43_diag"
C = V42.Cfg(route_c=True, adot_th=0.10, dn=15.0, link_pred=True, cpa_strong=1.3, cpa_mid=1.6)
FPS = v4.FPS


def frame_state(d_at, az_at, j):
    """v4.2 fires_cpa2 と同じ量をフレーム j で再計算（経路判定用）。"""
    d = d_at.get(j)
    if d is None:
        return None
    v = v4.closing_speed(d_at, j, win=C.vel_win)
    ddot = None if v is None else -v
    adot = v4.azimuth_rate(az_at, j, win=C.brg_win)
    dc, tc = v4.cpa_of(d, ddot, adot)
    rc = (adot is not None and abs(adot) <= C.adot_th and ddot is not None
          and ddot < -C.v_close and d <= C.dn)
    cpa_ok = dc is not None and dc <= C.cpa_strong and tc <= v4.TTC_WARN
    ins = d <= v4.T3
    return dict(d=d, ddot=ddot, adot=adot, dc=dc, tc=tc, rc=rc, cpa_ok=cpa_ok, ins=ins)


def gt_adot_at(fr, j, half=2):
    js = [k for k in sorted(fr) if j - half <= k <= j + half]
    if len(js) < 3:
        return None
    unw = np.unwrap(np.radians([fr[k][0] for k in js]))
    return float(np.median(np.abs(np.diff(unw)) * FPS / np.diff(js)))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pred = v4.load_pred(PRED)
    res = V42.run_rule2(pred, C)
    rows = []
    for clip in sorted(pred):
        evs = [DG.mk_event(c, t, fr) for c, t, fr in DG.gt_tracks(META, clip)]
        eps = {cls: e for cls, e in res.get(clip, {}).items()}
        for ev in evs:
            ad = Q2.gt_adot_before_cpa(ev["fr"], ev["cpa"])
            if ad is None:
                continue
            typ = "対向型" if ad < Q2.ADOT_SPLIT else "すり抜け型"
            if (ev["tier"], typ) not in (("safe", "すり抜け型"), ("critical", "対向型")):
                continue
            a, b = ev["f0"] - FPS, ev["cpa"] + FPS
            strong = [f for f in eps.get(ev["cls"], []) if f[2] == "強" and a <= f[0] <= b]
            if not strong:
                continue
            j = int(min(f[0] for f in strong))
            d_at, az_at = V42.track_series2(pred[clip], ev["cls"], 100, C)
            st = frame_state(d_at, az_at, j)
            if st is None:
                continue
            gt_d = ev["fr"][j][1] if j in ev["fr"] else None
            route = "rc" if st["rc"] and not st["cpa_ok"] else ("cpa" if st["cpa_ok"] else
                                                                 ("ins" if st["ins"] else "?"))
            rows.append(dict(clip=clip, cls=ev["cls"], tier=ev["tier"], typ=typ, j=j,
                             t_to_cpa=round((ev["cpa"] - j) / FPS, 1), route=route,
                             rc=int(st["rc"]), cpa_ok=int(st["cpa_ok"]), ins=int(st["ins"]),
                             d_pred=round(st["d"], 2), d_gt=gt_d,
                             dc=None if st["dc"] is None else round(st["dc"], 2),
                             tc=None if st["tc"] is None else round(st["tc"], 2),
                             adot=None if st["adot"] is None else round(st["adot"], 3),
                             gt_adot=gt_adot_at(ev["fr"], j),
                             ddot=None if st["ddot"] is None else round(st["ddot"], 2),
                             gt_cpa_d=round(ev["dmin"], 2) if "dmin" in ev else None))
    with open(OUT / "casebook.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    R = ["# v4.3 設計診断 — 強警告の「最初の強フレーム」で成立していた経路（fold31・v4.2採用構成）", "",
         "経路: rc=定方位接近のみ / cpa=最接近予測（d_cpa≤1.3 & t_cpa≤2.5） / ins=距離保険（d≤1.5）", ""]
    for key, name in ((("safe", "すり抜け型"), "安全×すり抜け型（誤った強）"),
                      (("critical", "対向型"), "重大×対向型（正しい強）")):
        rs = [r for r in rows if (r["tier"], r["typ"]) == key]
        if not rs:
            continue
        cnt = Counter(r["route"] for r in rs)
        g = lambda k: np.array([r[k] for r in rs if r[k] is not None], dtype=float)
        R += [f"## {name} n={len(rs)}", "",
              f"- 経路: {dict(cnt)}",
              f"- 推定距離 中央 {np.median(g('d_pred')):.2f} m（GT同時刻 {np.median(g('d_gt')):.2f} m）",
              f"- d_cpa 中央 {np.median(g('dc')):.2f} m / t_cpa 中央 {np.median(g('tc')):.2f} s",
              f"- 測定|adot| 中央 {np.median(np.abs(g('adot'))):.3f} rad/s（GT同時刻 {np.median(g('gt_adot')):.3f}）",
              f"- ddot 中央 {np.median(g('ddot')):.2f} m/s",
              f"- 最初の強はCPAの {np.median(g('t_to_cpa')):.1f} s 前（中央）", ""]
        for route in ("rc", "cpa", "ins"):
            sub = [r for r in rs if r["route"] == route]
            if not sub:
                continue
            gg = lambda k: np.array([r[k] for r in sub if r[k] is not None], dtype=float)
            R.append(f"  - {route} n={len(sub)}: d_pred {np.median(gg('d_pred')):.2f} / d_gt {np.median(gg('d_gt')):.2f}"
                     f" / |adot| {np.median(np.abs(gg('adot'))):.3f} (GT {np.median(gg('gt_adot')):.3f})"
                     f" / dc {np.median(gg('dc')) if len(gg('dc')) else float('nan'):.2f}"
                     f" / t_to_cpa {np.median(gg('t_to_cpa')):.1f}s")
        R.append("")
    (OUT / "summary.md").write_text("\n".join(R) + "\n", encoding="utf-8")
    print("\n".join(R))
    return 0


if __name__ == "__main__":
    sys.exit(main())
