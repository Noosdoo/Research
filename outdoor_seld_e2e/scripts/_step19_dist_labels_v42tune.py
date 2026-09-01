# -*- coding: utf-8 -*-
"""v42tune の距離付きラベル（metadata_dist）生成 — step19_dist_labels_v12 の出力先差替。

step19_dist_labels_v12 のロジック（scene.jsonから距離を再計算し、既存metadataの
az/el と整数一致することを検証しながら6列目に距離を足す）をそのまま使い、
対象データセットだけ out/dataset_outdoor_siren_v42tune/ に向ける。

使い方: PYTHONPATH=scripts:src python scripts/_step19_dist_labels_v42tune.py [--limit N]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import step19_dist_labels_v12 as s19  # noqa: E402  (import時点ではDS=v12を指す)

DS = ROOT / "out" / "dataset_outdoor_siren_v42tune"
s19.DS = DS
s19.OUT = DS / "metadata_dist"

if __name__ == "__main__":
    s19.main()
