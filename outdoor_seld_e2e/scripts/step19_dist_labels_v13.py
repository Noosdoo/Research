# -*- coding: utf-8 -*-
"""v13 の距離付き6列ラベル生成（step19_dist_labels_v12 の出力先差替＋プリロール対応）。

v12版との差分は1点: S1 のサイレン（scene.json に preroll_s>0）は放射が t=−preroll から
始まるので、軌道を t=−pre まで直線外挿し source_active_from=−pre で frame_label_rows を呼ぶ
（step11_v13_render.generate_clip_v13 のラベル生成と同一規約）。検証ゲート（az/el 全行一致）は同じ。

使い方: PYTHONPATH=scripts:src python scripts/step19_dist_labels_v13.py [--limit N]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import step19_dist_labels_v12 as s19  # noqa: E402
import step11_v13_render as v13  # noqa: E402  (m9.DS が v13 に切替わる)
from outdoor_seld.labels import frame_label_rows  # noqa: E402

DS = ROOT / "out" / "dataset_outdoor_siren_v13"
s19.DS = DS
s19.OUT = DS / "metadata_dist"
m9 = v13.m9


def regen_clip_v13(clip: str, c: float) -> int:
    scene = json.loads((DS / "work" / clip / "scene.json").read_text())
    mic = s19.rebuild_mic(scene["mic"])
    per_src = {}
    for src in scene["sources"]:
        if src.get("no_label"):
            continue
        cls_idx = v13.v12.CLASS_IDX_V12[src["class"]]
        wp = np.array(src["wp"], float)
        pre = float(src.get("preroll_s", 0.0))
        if pre > 0:
            wp, act_from = v13._extend_back(wp, pre), -pre
        else:
            act_from = src["t_on"]
        _, dbg = frame_label_rows(wp, mic, clip_len_sec=m9.CLIP, class_idx=cls_idx,
                                  track_idx=src.get("track", 0),
                                  source_active_from=act_from,
                                  source_active_until=src["t_off"], c=c)
        key = (cls_idx, src.get("track", 0))
        assert key not in per_src, f"{clip}: (class,track)重複 {key}"
        per_src[key] = dbg

    out_lines = []
    for line in (DS / "metadata" / f"{clip}.csv").read_text().splitlines():
        k, ci, tr, az, el = (int(v) for v in line.split(","))
        dbg = per_src[(ci, tr)]
        az_i = int(np.rint(dbg["az"][k]))
        if az_i == 180:
            az_i = -180
        el_i = int(np.rint(dbg["el"][k]))
        assert (az_i, el_i) == (az, el), f"{clip}: az/el不一致 (frame={k},cls={ci},tr={tr})"
        d = float(dbg["dist"][k])
        assert np.isfinite(d), f"{clip}: dist非有限 frame={k}"
        out_lines.append(f"{line},{d:.2f}")
    with open(s19.OUT / f"{clip}.csv", "w", newline="\n") as f:
        f.write("".join(s + "\n" for s in out_lines))
    return len(out_lines)


s19.regen_clip = regen_clip_v13

if __name__ == "__main__":
    s19.main()
