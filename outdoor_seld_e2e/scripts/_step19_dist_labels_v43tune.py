# -*- coding: utf-8 -*-
"""fold32（v43tune）の距離付きラベル生成 — step19_dist_labels_v12 の出力先差替。

使い方: PYTHONPATH=scripts:src python scripts/_step19_dist_labels_v43tune.py [--limit N]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import step19_dist_labels_v12 as s19  # noqa: E402

DS = ROOT / "out" / "dataset_outdoor_siren_v43tune"
s19.DS = DS
s19.OUT = DS / "metadata_dist"

if __name__ == "__main__":
    s19.main()
