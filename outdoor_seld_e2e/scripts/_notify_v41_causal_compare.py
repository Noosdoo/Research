# -*- coding: utf-8 -*-
"""因果推論（未来を見ない）での通知v4.1の成績を、通常推論と同じ土俵で比べる。

## 何を測るのか

これまでの通知の数字はすべて**通常推論**の予測に対するものだった。通常推論は
10秒クリップを丸ごとモデルに入れるので、判定時刻より後の音を見ている＝実機では成立しない。
因果推論（各時刻までの音だけで判定）に替えたとき、通知性能がどれだけ落ちるかを測る。

v4.1 は距離の**傾き**（接近速度）と方位の**傾き**を使うので、
1フレームあたりの推定が粗くなる影響を、距離しきい値だけの v3.4 より強く受けうる。
その大小がここで分かる。

## 読むときの注意（この実験の構造的な弱み）

因果窓は「その時刻までの音を右詰めし、残りをゼロ埋めした10秒」である。
クリップ先頭では窓のほとんどがゼロなので、モデルにとって学習時と違う入力になる。
**実機では10秒ぶんの実音がつねに埋まっている**ので、先頭付近の成績は実機より悪いはず。
そこで「全フレーム」と「発火が後半（窓の実音が多い領域）に来たイベントだけ」を並べる。

使い方:
  python scripts/_notify_v41_causal_compare.py <通常推論csv> <因果推論csv> <GTdir> <出力dir>
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sp = importlib.util.spec_from_file_location(
    "nv4", ROOT / "scripts" / "step12_notify_v4_ttc.py")
v4 = importlib.util.module_from_spec(sp)
sp.loader.exec_module(v4)
ev = importlib.util.spec_from_file_location("ev", ROOT / "scripts" / "_notify_v4_eval.py")
E = importlib.util.module_from_spec(ev)
ev.loader.exec_module(E)
FPS = v4.FPS
WARM = 50          # このフレーム以降＝因果窓の半分以上が実音


def score(pred, gts, rule, clips, min_cpa=0):
    """min_cpa 以降に最接近するイベントだけを対象にする（先頭の暖機を除くため）。"""
    res = v4.run_rule(pred, rule)
    stat = defaultdict(lambda: [0, 0])
    leads, n_fa = [], 0
    for clip in clips:
        evs = [e for e in gts.get(clip, []) if e["cpa"] >= min_cpa]
        fl = [(f[0], f[1], f[2], f[3], cls)
              for cls, eps in res.get(clip, {}).items() for f in eps]
        fl.sort(key=lambda x: x[0])
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
    return dict(crit=100 * stat["critical"][0] / max(stat["critical"][1], 1),
                caut=100 * stat["caution"][0] / max(stat["caution"][1], 1),
                safe=100 * stat["safe"][0] / max(stat["safe"][1], 1),
                lead=float(np.median(L)), lead25=float(100 * np.mean(L >= 2.5)),
                fa=n_fa, n=stat["critical"][1] + stat["caution"][1] + stat["safe"][1])


def main() -> int:
    full_p, causal_p, meta, outdir = (Path(sys.argv[1]), Path(sys.argv[2]),
                                      Path(sys.argv[3]), Path(sys.argv[4]))
    outdir.mkdir(parents=True, exist_ok=True)
    full, causal = v4.load_pred(full_p), v4.load_pred(causal_p)
    # クリップ集合はGT側から取る。予測の積集合にすると「因果側が何も検出しなかった
    # クリップ」が分母から落ちて因果に有利になる（検出ゼロは失敗として数えるべき）。
    pre = sorted(set(full) | set(causal))
    stem = pre[0].split("_")[0] if pre else "fold2"
    clips = sorted(p.stem for p in meta.glob(f"{stem}_*.csv"))
    if not clips:
        clips = pre
    gts = E.gt_events(meta, clips)
    n_ev = sum(len(v) for v in gts.values())

    R = ["# 因果推論での通知v4.1（未来を見ない実装での成績）", "",
         f"- 通常推論 {full_p.name} / 因果推論 {causal_p.name}",
         f"- 共通クリップ {len(clips):,} / GTイベント {n_ev:,}",
         "- 因果推論＝各時刻までの音を右詰めしゼロ埋めした10秒窓で、"
         "モデル出力の最終フレームだけ採用", ""]

    for tag, mc in (("全イベント", 0), (f"最接近が{WARM/FPS:.0f}秒以降のイベントのみ", WARM)):
        rows = {}
        for rule in ("dist", "cpa"):
            rows[("通常", rule)] = score(full, gts, rule, clips, mc)
            rows[("因果", rule)] = score(causal, gts, rule, clips, mc)
        n = rows[("通常", "cpa")]["n"]
        R += [f"## {tag}（n={n:,}）", "",
              "| 推論 | 規則 | 至近到達 | 注意到達 | 安全抑制 | リード中央値 | ≥2.5s | 誤発火 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for (inf, rule), r in rows.items():
            nm = "v3.4(距離)" if rule == "dist" else "**v4.1(最接近予測)**"
            R.append(f"| {inf} | {nm} | {r['crit']:.1f}% | {r['caut']:.1f}% | "
                     f"{r['safe']:.1f}% | {r['lead']:.2f}s | {r['lead25']:.1f}% | "
                     f"{r['fa']:,} |")
        R.append("")
        for rule, nm in (("dist", "v3.4(距離)"), ("cpa", "v4.1(最接近予測)")):
            a, b = rows[("通常", rule)], rows[("因果", rule)]
            R.append(f"- **{nm} の因果化による変化**: 至近{b['crit']-a['crit']:+.1f}pt / "
                     f"注意{b['caut']-a['caut']:+.1f}pt / 抑制{b['safe']-a['safe']:+.1f}pt / "
                     f"リード{b['lead']-a['lead']:+.2f}s / 誤発火{b['fa']-a['fa']:+,}")
        R.append("")

    (outdir / "causal_compare.md").write_text("\n".join(R), encoding="utf-8")
    print("\n".join(R))
    return 0


if __name__ == "__main__":
    sys.exit(main())
