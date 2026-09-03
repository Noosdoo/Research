# -*- coding: utf-8 -*-
"""通知 v4.6「車の hold」の掃引（2026-09-03 事前宣言 §2〜§3）。長尺セット v1 の予測に H（方位アンカー）/ H′（系列連続）を当てる。

規則本体は v4.3＋警告音 hold のまま。hold は step12_notify_v44.apply_filters（v4.4 の実装）をそのまま使う。
指標: 再発火率（同じ車に既に同段以上が届いた後の発火）・通知/分・害（抑えた通知のうち「その車にまだ何も届いていない かつ
後で至近になる」割合）・至近の強到達・警告不変。

使い方:
  python scripts/_long_hold_sweep.py --pred out/dataset_outdoor_long_v1/pred/val_all_causal.csv --split fold40 --out out/long_v1/hold_fold40.md
  python scripts/_long_hold_sweep.py --pred ... --split fold41 --only "H 25 3"     # 候補だけ検証
"""
from __future__ import annotations

import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


LS = _load("long_score", "_long_score.py")
V44 = _load("nv44", "step12_notify_v44.py")
V42, V43, H, C43, NFR = LS.V42, LS.V43, LS.H, LS.C43, LS.NFR
RANK = {"中": 1, "強": 2}

GRID = [("なし", None)]
GRID += [(f"H {d:.0f}° {g:.0f}s", V44.Cfg44(dir_h=d, gap_h=g)) for d in (25.0, 40.0) for g in (3.0, 5.0)]
GRID += [(f"H′ {g:.0f}s", V44.Cfg44(track_hold=True, gap_h=g, jump_deg=60.0)) for g in (3.0, 5.0)]


MID_ONLY = "--mid-only" in sys.argv


def episodes_hold(frames_dist, frames_warn, C44):
    """v4.3 の発火 → hold 後の発火。返り値 [(frame, az, tier, cls, delivered)]（抑えた分も delivered=False で残す）"""
    rows = []
    for cls in LS.DIST_CLASSES:
        d_at, az_at = V42.track_series2(frames_dist, cls, NFR, C43)
        if not d_at:
            continue
        raw = V43.fires_cpa3(d_at, az_at, NFR, C43)              # [(j, az, tier, d)]
        kept = V44.apply_filters(raw, az_at, C44, d_at) if C44 is not None else list(raw)
        kept_set = {(j, round(az, 3), tier) for j, az, tier, _d in kept}
        if MID_ONLY and C44 is not None:                      # v4.6b: 強は常に通す（初回も再発火も）
            kept_set |= {(j, round(az, 3), tier) for j, az, tier, _d in raw if tier == "強"}
        for j, az, tier, _d in raw:
            rows.append((j, az, tier, cls, (j, round(az, 3), tier) in kept_set))
    for k, cls, az in H.warn_fires(frames_warn, hold=True, nframes=NFR):
        rows.append((k, az, "警告", cls, True))
    return sorted(rows)


def score_clip(rows, gt):
    """帰属して 再発火・害・至近の強到達 を数える。"""
    delivered_by_car = defaultdict(list)        # car -> [(frame, tier)] 届いたもの
    n = {"中": 0, "強": 0, "警告": 0, "supp": 0, "refire_raw": 0, "refire_after": 0, "harm": 0, "harm_b": 0, "total_raw": 0,
         "mid_raw": 0, "mid_refire_raw": 0, "mid_refire_after": 0}
    supp_unannounced = []                        # (car, frame) 何も届いていない車を抑えた
    for r in rows:
        j, az, tier, cls, deliv = r
        if tier == "警告":
            n["警告"] += 1
            continue
        n["total_raw"] += 1
        car = LS.attribute(r, gt)
        already = car is not None and any(RANK[t] >= RANK[tier] for _f, t in delivered_by_car[car])
        # 再発火（hold なしの発火列で定義。after は届いた分だけで数える）
        if already:
            n["refire_raw"] += 1
        if tier == "中":
            n["mid_raw"] += 1
            if already:
                n["mid_refire_raw"] += 1
        if deliv:
            n[tier] += 1
            if already:
                n["refire_after"] += 1
                if tier == "中":
                    n["mid_refire_after"] += 1
            if car is not None:
                delivered_by_car[car].append((j, tier))
        else:
            n["supp"] += 1
            if car is not None and not already:
                fut = [d for k, (_a, d) in gt[car].items() if k >= j]
                if fut and min(fut) <= LS.CLOSE_M:
                    n["harm"] += 1
                    supp_unannounced.append((car, j))
    for car, j in supp_unannounced:              # v4.6b: 後で強が届けば害に数えない
        if not any(t == "強" and f >= j for f, t in delivered_by_car.get(car, [])):
            n["harm_b"] += 1
    close_cars = reached = 0
    for key, fr in gt.items():
        if key[0] not in LS.DIST_CLASSES:
            continue
        ks = [k for k, (_a, d) in fr.items() if d <= LS.CLOSE_M]
        if not ks:
            continue
        close_cars += 1
        k0 = min(ks)
        if any(t == "強" and f <= k0 + LS.ATTR_FR for f, t in delivered_by_car.get(key, [])):
            reached += 1
    n["close_cars"], n["reached"] = close_cars, reached
    return n


def main() -> int:
    a = sys.argv
    split = a[a.index("--split") + 1] if "--split" in a else "fold40"
    only = a[a.index("--only") + 1] if "--only" in a else None
    plan = {r["clip_id"]: r for r in csv.DictReader(open(LS.DS / "plan/assignment_long_v1.csv", encoding="utf-8"))}
    clips = [c for c in plan if plan[c]["split"] == split and (LS.DS / "metadata_dist" / f"{c}.csv").exists()]
    preds = LS.load_pred_long(a[a.index("--pred") + 1])
    gts = {c: LS.load_gt(c) for c in clips}
    L = [f"# v4.6{'b（中だけ hold・強は常に通す）' if MID_ONLY else ''} 車の hold 掃引 — {split}（{len(clips)} 本・モデル予測）", "",
         ("| 構成 | 幹線歩道: 通知/分 (中+強) | 減り | 中の再発火率 (前→後) | 抑えた中 | 害 (b: 後で強も届かず至近) | 至近の強到達 | 警告/本 | 住宅街: 通知/分 | 判定 |" if MID_ONLY else
          "| 構成 | 幹線歩道: 通知/分 (中+強) | 減り | 再発火率 (前→後) | 抑えた | 害 | 至近の強到達 | 警告/本 | 住宅街: 通知/分 | 判定 |"),
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    base = None
    for name, C44 in GRID:
        if only and name != "なし" and name != only:
            continue
        agg = defaultdict(lambda: defaultdict(float))
        for c in clips:
            fd, fw = preds.get(c, ({}, {}))
            s = score_clip(episodes_hold(fd, fw, C44), gts[c])
            for grp in (plan[c]["scene"], "all"):
                for k, v in s.items():
                    agg[grp][k] += v
                agg[grp]["n"] += 1
        aw, al, rs = agg["arterial_walk"], agg["all"], agg["residential"]
        per_min = (aw["中"] + aw["強"]) / max(aw["n"], 1)
        rr_raw = 100 * al["refire_raw"] / max(al["total_raw"], 1)
        rr_after = 100 * al["refire_after"] / max(al["中"] + al["強"], 1)
        if MID_ONLY:
            rr_raw = 100 * al["mid_refire_raw"] / max(al["mid_raw"], 1)
            rr_after = 100 * al["mid_refire_after"] / max(al["中"], 1)
        reach = 100 * al["reached"] / al["close_cars"] if al["close_cars"] else float("nan")
        warn = al["警告"] / max(al["n"], 1)
        harm = 100 * al["harm"] / al["supp"] if al["supp"] else 0.0
        harm_b = 100 * al["harm_b"] / al["supp"] if al["supp"] else 0.0
        if MID_ONLY:
            harm = harm_b
        res_pm = (rs["中"] + rs["強"]) / max(rs["n"], 1)
        if C44 is None:
            base = (per_min, rr_raw, reach, warn)
            L.append(f"| なし | {per_min:.2f} | — | {rr_raw:.0f}% | — | — | {reach:.1f}% | {warn:.2f} | {res_pm:.2f} | 基準 |")
            continue
        red = 100 * (base[0] - per_min) / base[0] if base[0] > 0 else 0.0
        rr_cut = 100 * (base[1] - rr_after) / base[1] if base[1] > 0 else 0.0
        ok = rr_cut >= 50 and harm <= 2 and reach >= base[2] - (0.05 if MID_ONLY else 1) and abs(warn - base[3]) < 1e-9
        L.append(f"| {name} | {per_min:.2f} | −{red:.0f}% | {rr_raw:.0f}%→{rr_after:.0f}% (−{rr_cut:.0f}%) | {al['supp']:.0f} | "
                 f"{al['harm']:.0f}/{al['supp']:.0f} ({harm:.1f}%) | {reach:.1f}% | {warn:.2f} | {res_pm:.2f} | {'候補' if ok else '×'} |")
        print(L[-1], flush=True)
    txt = "\n".join(L)
    print(txt)
    if "--out" in a:
        p = Path(a[a.index("--out") + 1]); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
