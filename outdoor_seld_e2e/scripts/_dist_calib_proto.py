# -*- coding: utf-8 -*-
"""至近帯の距離バイアスの「補正表」試作（2026-09-03・v2 束の未決1＝本人判断 B）。

補正表 = 「モデルが言った距離 → 実際の距離の中央値」の単調な対応表（0〜5m を 0.25m 刻み、5m 超はそのまま）。
fold32（選定用）の因果推論と GT の対応ペア（方位20°以内・フレーム40以降＝_causalft_select.pairs と同じ）で作り、
別のデータ（fold2 val）に当てて 至近捕捉／誤捕捉／推定距離中央値／距離誤差 の前後を出す。
v2 では **v2 のモデル**で同じ手順を踏む（数値は使い回さない。手順だけを事前登録する）。

使い方: python scripts/_dist_calib_proto.py [fit_csv fit_meta eval_csv eval_meta]
"""
from __future__ import annotations

import importlib.util
import json
import sys
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


SEL = _load("nvsel", "_causalft_select.py")
EDGES = np.arange(0.0, 5.0 + 1e-9, 0.25)


def pava(y, w):
    """単調非減少になるよう隣接ビンを平均で併合（pool-adjacent-violators）。"""
    y = list(map(float, y)); w = list(map(float, w))
    blocks = [[y[i], w[i], 1] for i in range(len(y))]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0] + 1e-12:
            a, b = blocks[i], blocks[i + 1]
            m = (a[0] * a[1] + b[0] * b[1]) / (a[1] + b[1])
            blocks[i] = [m, a[1] + b[1], a[2] + b[2]]
            del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    out = []
    for m, _, n in blocks:
        out += [m] * n
    return np.array(out)


def fit_table(P):
    """P[:,0]=推定, P[:,1]=GT。ビンごとの GT 中央値を単調化した表を返す（centers, values, counts）。"""
    centers = 0.5 * (EDGES[:-1] + EDGES[1:])
    med, cnt = [], []
    for lo, hi in zip(EDGES[:-1], EDGES[1:]):
        sel = (P[:, 0] >= lo) & (P[:, 0] < hi)
        cnt.append(int(sel.sum()))
        med.append(float(np.median(P[sel, 1])) if sel.sum() >= 30 else float("nan"))
    med = np.array(med); cnt = np.array(cnt)
    ok = np.isfinite(med)
    vals = med.copy()
    vals[ok] = pava(med[ok], cnt[ok])
    vals[~ok] = centers[~ok]          # ペアが少ないビンは恒等
    return centers, vals, cnt


def apply_table(d, centers, vals):
    d = np.asarray(d, dtype=float)
    out = np.interp(d, centers, vals)
    return np.where(d >= 5.0, d, out)


def metrics(P, corr=None):
    pred = P[:, 0] if corr is None else corr
    close, safe = pred[P[:, 1] <= 1.5], pred[P[:, 1] > 3.2]
    cap = 100 * np.mean(close <= SEL.TH)
    fp = 100 * np.mean(safe <= SEL.TH)
    med = float(np.median(close))
    rel = 100 * np.median(np.abs(pred - P[:, 1]) / np.maximum(P[:, 1], 0.1))
    band = {}
    for lo, hi in [(0, 0.5), (0.5, 1.0), (1.0, 1.5), (1.5, 2.5), (2.5, 4.0)]:
        s = (P[:, 1] >= lo) & (P[:, 1] < hi)
        band[f"{lo}-{hi}"] = 100 * np.median((pred[s] - P[s, 1]) / np.maximum(P[s, 1], 0.1)) if s.sum() else float("nan")
    return cap, fp, med, rel, band


def main() -> int:
    a = sys.argv[1:]
    fit_csv = a[0] if a else "out/predictions_v43tune/val_all_causal.csv"
    fit_meta = a[1] if len(a) > 1 else "out/dataset_outdoor_siren_v43tune/metadata_dist"
    ev_csv = a[2] if len(a) > 2 else "out/hp_sweep/C/ft2_e079_causal.csv"
    ev_meta = a[3] if len(a) > 3 else "out/dataset_outdoor_siren_v12/metadata_dist"
    Pf = SEL.pairs(ROOT / fit_csv, ROOT / fit_meta)
    Pe = SEL.pairs(ROOT / ev_csv, ROOT / ev_meta)
    centers, vals, cnt = fit_table(Pf)
    print(f"作成: {fit_csv}  ペア {len(Pf):,}   評価: {ev_csv}  ペア {len(Pe):,}")
    print("| 推定距離のビン | ペア数 | 実距離の中央値（補正後の値） | 補正量 |")
    print("| --- | --- | --- | --- |")
    for lo, hi, c, v, n in zip(EDGES[:-1], EDGES[1:], centers, vals, cnt):
        if hi <= 3.0:
            print(f"| {lo:.2f}–{hi:.2f} m | {n:,} | {v:.2f} m | {v - c:+.2f} m |")
    out = {"edges": EDGES.tolist(), "centers": centers.tolist(), "values": vals.tolist(), "counts": cnt.tolist(),
           "fit": fit_csv, "note": "試作。v2 では v2 モデルで作り直す"}
    (ROOT / "out/hp_sweep/dist_calib_proto.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for label, P in [("作成データ(fold32)", Pf), ("別データ(fold2 val)", Pe)]:
        b = metrics(P)
        c = metrics(P, apply_table(P[:, 0], centers, vals))
        print(f"\n{label}: 至近捕捉 {b[0]:.1f}→{c[0]:.1f}%  誤捕捉 {b[1]:.2f}→{c[1]:.2f}%  至近推定中央値 {b[2]:.2f}→{c[2]:.2f}m  距離誤差 {b[3]:.1f}→{c[3]:.1f}%")
        print("  帯別の相対バイアス中央値(%) 前→後: " + "  ".join(f"{k}m {b[4][k]:+.0f}→{c[4][k]:+.0f}" for k in b[4]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
