# -*- coding: utf-8 -*-
"""通知規則の新旧比較（2026-08-18）— v3.4(距離) vs v4(TTC)。

「遠くで鳴るようになった」だけでは改善と言えない。早く鳴らせば誤警告も増えるので、
**到達率・リードタイム・誤警告**を同じ土俵で並べて初めて判断できる。

GT（metadata_dist: frame,class,track,az,el,dist）から
  - イベント = (clip, class, track) の連続フレーム
  - 最接近(CPA) = そのイベントで GT距離が最小のフレーム
  - GT区分 = 最小GT距離から critical(≤1.5) / caution(≤3.2) / safe(>3.2)
を作り、規則ごとに次を測る:
  - 到達率: イベント窓 [開始−1s, CPA+1s] に発火があったか
            （safe区分は「鳴らないこと」が成功＝既存の抑制の定義と同じ）
  - リード: (CPA − 発火) / FPS 秒
  - 誤警告: どのイベント窓にも入らない発火の数

使い方:
  python scripts/_notify_v4_eval.py <pred_val_all.csv> <GT metadata_distディレクトリ> <出力dir>
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

spec = importlib.util.spec_from_file_location(
    "nv4", ROOT / "scripts" / "step12_notify_v4_ttc.py")
v4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v4)

FPS = v4.FPS
WIN_PRE, WIN_POST = 1.0, 1.0       # step20と同じイベント窓
CLS_JP = {4: "車", 6: "キックボード", 7: "バイク"}


def gt_events(meta_dir: Path, clips):
    """(clip -> [ {cls, track, f0, f1, cpa, dmin, tier} ])"""
    out = defaultdict(list)
    for clip in clips:
        f = meta_dir / f"{clip}.csv"
        if not f.exists():
            continue
        per = defaultdict(list)          # (cls,track) -> [(frame, dist)]
        for line in open(f, encoding="utf-8"):
            g = line.strip().split(",")
            if len(g) < 6:
                continue
            cls, trk = int(g[1]), int(g[2])
            if cls not in v4.DIST_CLASSES:
                continue
            per[(cls, trk)].append((int(g[0]), float(g[5])))
        for (cls, trk), rows in per.items():
            rows.sort()
            # 連続フレームのランごとに1イベント
            run = [rows[0]]
            for r in rows[1:]:
                if r[0] == run[-1][0] + 1:
                    run.append(r)
                else:
                    out[clip].append(_mk(cls, trk, run))
                    run = [r]
            out[clip].append(_mk(cls, trk, run))
    return out


def _mk(cls, trk, run):
    d = np.array([x[1] for x in run])
    i = int(np.argmin(d))
    dmin = float(d[i])
    tier = ("critical" if dmin <= v4.T3
            else ("caution" if dmin <= v4.SUPP else "safe"))
    return dict(cls=cls, track=trk, f0=run[0][0], f1=run[-1][0],
                cpa=run[i][0], dmin=dmin, tier=tier)


def evaluate(pred, gts, rule):
    res = v4.run_rule(pred, rule)
    stat = defaultdict(lambda: [0, 0])        # tier -> [成功, 母数]
    leads, n_fa, n_fire = [], 0, 0
    lead_by_cls = defaultdict(list)
    for clip, evs in gts.items():
        fires = [(f[0], f[1], f[2], f[3], cls)
                 for cls, eps in res.get(clip, {}).items() for f in eps]
        n_fire += len(fires)
        used = [False] * len(fires)
        for ev in evs:
            a = ev["f0"] - WIN_PRE * FPS
            b = ev["cpa"] + WIN_POST * FPS
            hit = None
            for i, fr in enumerate(fires):
                if used[i] or fr[4] != ev["cls"]:
                    continue
                if a <= fr[0] <= b:
                    hit = i
                    break
            if ev["tier"] == "safe":
                # 安全: 鳴らないことが成功（既存の抑制の定義と同一）
                stat["safe"][1] += 1
                stat["safe"][0] += int(hit is None)
                if hit is not None:
                    used[hit] = True
                continue
            stat[ev["tier"]][1] += 1
            if hit is not None:
                used[hit] = True
                stat[ev["tier"]][0] += 1
                lead = (ev["cpa"] - fires[hit][0]) / FPS
                leads.append(lead)
                lead_by_cls[ev["cls"]].append(lead)
        n_fa += sum(1 for i, u in enumerate(used) if not u)
    return dict(stat=stat, leads=leads, n_fa=n_fa, n_fire=n_fire,
                lead_by_cls=lead_by_cls)


def main() -> int:
    pred_path, meta_dir, outdir = (Path(sys.argv[1]), Path(sys.argv[2]),
                                   Path(sys.argv[3]))
    outdir.mkdir(parents=True, exist_ok=True)
    pred = v4.load_pred(pred_path)
    gts = gt_events(meta_dir, sorted(pred.keys()))
    n_ev = sum(len(v) for v in gts.values())

    R = [f"# 通知規則の新旧比較 pred={pred_path.name}", "",
         f"- クリップ {len(gts):,} / GTイベント {n_ev:,}",
         f"- 窓=[開始−{WIN_PRE}s, CPA+{WIN_POST}s]、safe区分は「鳴らない」が成功", ""]
    out = {}
    for rule in ("dist", "ttc", "cpa"):
        out[rule] = evaluate(pred, gts, rule)
    R += ["| 指標 | v3.4(距離) | v4(TTC) | **v4.1(最接近予測)** | 距離→v4.1 |",
         "| --- | --- | --- | --- | --- |"]

    def pct(s, t):
        return f"{100*s[t][0]/s[t][1]:.1f}%" if s[t][1] else "n/a"

    for t, jp in [("critical", "至近到達（重大）"), ("caution", "注意到達"),
                  ("safe", "安全抑制")]:
        a, b, c = (out["dist"]["stat"], out["ttc"]["stat"], out["cpa"]["stat"])
        if a[t][1]:
            d = 100 * (c[t][0] / c[t][1] - a[t][0] / a[t][1])
            R.append(f"| {jp} (n={a[t][1]:,}) | {pct(a,t)} | {pct(b,t)} "
                     f"| **{pct(c,t)}** | {d:+.1f}pt |")
    la, lb, lc = (out["dist"]["leads"], out["ttc"]["leads"], out["cpa"]["leads"])
    if la and lc:
        R.append(f"| リード中央値 | {np.median(la):.2f}s | {np.median(lb):.2f}s "
                 f"| **{np.median(lc):.2f}s** | {np.median(lc)-np.median(la):+.2f}s |")
        f = lambda x: 100*np.mean(np.array(x) >= 2.5)
        R.append(f"| リード≥2.5s の割合 | {f(la):.1f}% | {f(lb):.1f}% "
                 f"| **{f(lc):.1f}%** | {f(lc)-f(la):+.1f}pt |")
    R.append(f"| 発火総数 | {out['dist']['n_fire']:,} | {out['ttc']['n_fire']:,} "
             f"| **{out['cpa']['n_fire']:,}** | "
             f"{out['cpa']['n_fire']-out['dist']['n_fire']:+,} |")
    R.append(f"| **紐づかない発火** | {out['dist']['n_fa']:,} | {out['ttc']['n_fa']:,} "
             f"| **{out['cpa']['n_fa']:,}** | "
             f"{out['cpa']['n_fa']-out['dist']['n_fa']:+,} |")

    R += ["", "## クラス別リード中央値（速い相手ほど効くはず）", "",
          "| クラス | v3.4 | v4.1 | 変化 |", "| --- | --- | --- | --- |"]
    for cls in sorted(CLS_JP):
        a = out["dist"]["lead_by_cls"].get(cls, [])
        c = out["cpa"]["lead_by_cls"].get(cls, [])
        if a and c:
            R.append(f"| {CLS_JP[cls]} | {np.median(a):.2f}s | "
                     f"**{np.median(c):.2f}s** | {np.median(c)-np.median(a):+.2f}s |")
    (outdir / "notify_compare.md").write_text("\n".join(R), encoding="utf-8")
    print("\n".join(R))
    return 0


if __name__ == "__main__":
    sys.exit(main())
