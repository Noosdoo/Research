# -*- coding: utf-8 -*-
"""ablation arm の **SELDスコア**採点（2026-08-17、事前登録§9.3の主要評価）。

§9.3 は「主要評価はフル物理val上の ΔSELDスコア」と登録しているが、単体で回せる
採点入口が無かったため、これまで tier再現率で代用していた。本スクリプトは
PSELDNets の `SELDMetrics` と `to_metrics_format` を直接呼んで
**ER / F / LE_CD / LR_CD / SELDスコア** を出す。

- 予測: 推論が出した val_all.csv（`clip,frame,class[,track],az,el[,dist]`）
- 正解: 採点対象の世界の metadata（`--gt full` なら基準、`--gt self` なら arm）
- 学習ログの val SELD は**自条件val**（その世界で学習しその世界で採点）なので、
  転移ギャップの比較には使えない。本スクリプトは正解の世界を明示的に選べる。

使い方:
  python scripts/_abl_seld_score.py <pred_val_all.csv> <GT metadataディレクトリ> [--nb-classes 8]
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

PS = Path.home() / "research" / "PSELDNet" / "PSELDNets"
sys.path.insert(0, str(PS / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from utils.SELD_metrics import SELDMetrics          # noqa: E402
from utils.data_utilities import to_metrics_format  # noqa: E402

NB_CLASSES = 8
LABEL_RES = 0.1


def _arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


def load_pred(path: Path):
    """clip -> {frame: [[class, track, az, el], ...]} （DCASE形式）"""
    out = defaultdict(lambda: defaultdict(list))
    for line in open(path, encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) >= 7:      # clip,frame,class,track,az,el,dist
            clip, fr, cls, trk, az, el = p[0], int(p[1]), int(p[2]), int(p[3]), float(p[4]), float(p[5])
        elif len(p) == 6:    # clip,frame,class,az,el,dist
            clip, fr, cls, trk, az, el = p[0], int(p[1]), int(p[2]), 0, float(p[3]), float(p[4])
        else:
            continue
        out[clip][fr].append([cls, trk, az, el])
    return out


def load_gt(meta_dir: Path, clip: str):
    """metadata/<clip>.csv -> {frame: [[class, track, az, el], ...]}"""
    f = meta_dir / f"{clip}.csv"
    if not f.exists():
        return None
    d = defaultdict(list)
    for line in open(f, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) >= 5:
            d[int(g[0])].append([int(g[1]), int(g[2]), float(g[3]), float(g[4])])
    return d


def main() -> int:
    pred_path = Path(sys.argv[1])
    meta_dir = Path(sys.argv[2])
    nb = int(_arg("--nb-classes", str(NB_CLASSES)))
    pred = load_pred(pred_path)

    # 分母は「予測に現れた fold と同じ fold の GT クリップ全部」。
    # _score_sde_dist.py と同じ manifest 規約（予測ゼロのクリップも分母に含めるが、
    # 評価対象外の fold=学習分は含めない）。GT全部を分母にすると学習分が
    # 巨大な見逃しとして混入し、SELDスコアが破綻する（2026-08-17に実際に0.61が出た）。
    prefixes = {k.rsplit("_mix", 1)[0] for k in pred.keys()}
    clips = sorted({p.stem for p in meta_dir.glob("*.csv")
                    if p.stem.rsplit("_mix", 1)[0] in prefixes} | set(pred.keys()))
    m = SELDMetrics(doa_threshold=20, nb_classes=nb)
    n_used = n_skip = 0
    for clip in clips:
        gt = load_gt(meta_dir, clip)
        if gt is None:
            n_skip += 1
            continue
        n_frames = max(max(gt, default=0),
                       max(pred.get(clip, {}), default=0)) + 1
        n_frames = max(n_frames, int(round(10.0 / LABEL_RES)))   # 10秒クリップ
        m.update_seld_scores(
            pred=to_metrics_format(dict(pred.get(clip, {})), n_frames, LABEL_RES),
            gt=to_metrics_format(dict(gt), n_frames, LABEL_RES))
        n_used += 1

    md, _classwise = m.compute_seld_scores(average="macro")
    er, f1, le, lr, seld = (md["ER"], md["F"], md["LE"], md["LR"], md["SELD_scr"])
    print(f"# SELDスコア採点  pred={pred_path.parent.name}  GT={meta_dir.parent.name}")
    print(f"- クリップ {n_used:,}本（GT無しでスキップ {n_skip}）  クラス数 {nb}")
    print(f"- ER      {er:.4f}")
    print(f"- F       {f1:.4f}")
    print(f"- LE_CD   {le:.2f}°")
    print(f"- LR_CD   {lr:.4f}")
    print(f"- **SELDスコア {seld:.4f}**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
