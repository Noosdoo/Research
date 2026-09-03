# -*- coding: utf-8 -*-
"""⑫(b) シナリオ文法の診断 — 学習コアの警告音は「どこで・どれだけ急に」鳴り始めるか（2026-09-02）。

本人の指摘（2026-09-02 2時・Joy-conデモ試聴）: 「サイレンが中距離で突然オン→4秒で消えるのは
現実にない」。学習コア（v11core = v12の本体）の scene.json を全数読み、移動警告音
（siren / horn / backup_beep / bike_bell）について
  - 鳴り始め t_on の時刻・その瞬間のマイク距離・受聴レベル（l1m − 20log10 d）と暗騒音の差(SNR)
  - 鳴り終わり t_off の同上
  - 発音の長さ、最接近(CPA)が発音中に入っているか
を集計する。「突然オン」= 鳴り始めの瞬間に SNR ≥ 10 dB（十分聞こえる大きさで
いきなり始まる）と定義して数える。

出力: out/scenario_grammar_diag/<split>.md ＋ 明細 csv
使い方: python scripts/_scenario_grammar_diag.py [fold1|fold2|all]
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "out/dataset_outdoor_siren_v11/work"
OUT = ROOT / "out/scenario_grammar_diag"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WARN = ("siren", "horn", "backup_beep", "bike_bell")
CLIP = 10.0
SUDDEN_SNR = 10.0     # 「突然オン」の定義: 鳴り始め時点の推定SNR(dB)がこれ以上


def mic_pos(mic: dict, t: float) -> np.ndarray:
    if "waypoints" in mic:
        wp = np.array(mic["waypoints"])
        return np.array([np.interp(t, wp[:, 0], wp[:, k]) for k in (1, 2, 3)])
    return np.array([0.0, 0.0, 1.5])


def src_pos(src: dict, t: float) -> np.ndarray:
    wp = np.array(src["wp"])
    return np.array([np.interp(t, wp[:, 0], wp[:, k]) for k in (1, 2, 3)])


def dist(scene: dict, src: dict, t: float) -> float:
    return float(np.linalg.norm(src_pos(src, t) - mic_pos(scene["mic"], t)))


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "fold1"
    prefixes = ["fold1_", "fold2_", "fold3_"] if which == "all" else [which + "_"]
    rows = []
    n_clip = 0
    for d in sorted(WORK.iterdir()):
        if not any(d.name.startswith(p) for p in prefixes):
            continue
        f = d / "scene.json"
        if not f.exists():
            continue
        n_clip += 1
        sc = json.load(open(f, encoding="utf-8"))
        noise = float(sc["noise"]["dba"])
        for src in sc["sources"]:
            if src["class"] not in WARN or src["kind"] != "vehicle":
                continue
            t_on, t_off = float(src["t_on"]), float(src["t_off"])
            d_on, d_off = dist(sc, src, t_on), dist(sc, src, t_off)
            l1m = float(src["l1m_db"])
            snr_on = l1m - 20 * np.log10(max(d_on, 1.0)) - noise
            snr_off = l1m - 20 * np.log10(max(d_off, 1.0)) - noise
            # 軌道上の最接近（鳴っているかに関係なく）
            ts = np.linspace(0, CLIP, 101)
            dd = np.array([dist(sc, src, t) for t in ts])
            k = int(np.argmin(dd))
            t_cpa, d_cpa = float(ts[k]), float(dd[k])
            rows.append(dict(clip=d.name, cls=src["class"], t_on=t_on, t_off=t_off,
                             dur=t_off - t_on, d_on=d_on, d_off=d_off,
                             snr_on=snr_on, snr_off=snr_off, t_cpa=t_cpa, d_cpa=d_cpa,
                             cpa_in_window=int(t_on <= t_cpa <= t_off),
                             sudden_on=int(snr_on >= SUDDEN_SNR),
                             sudden_off=int(snr_off >= SUDDEN_SNR),
                             noise=noise, speed=float(src["speed_mps"])))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"{which}_sources.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    R = [f"# シナリオ文法の診断（{which}・{n_clip:,}クリップ・移動警告音 {len(rows):,}本）", "",
         f"「突然オン/オフ」= その瞬間の推定SNR（l1m − 20log10 d − 暗騒音）≥ {SUDDEN_SNR:.0f} dB。",
         "距離は直線軌道と歩行者位置から再計算（scene.json）。", "",
         "| クラス | 本数 | 発音長 中央(s) | 鳴り始め距離 中央/最大(m) | 鳴り始めSNR 中央(dB) "
         "| **突然オン** | **突然オフ** | 最接近が発音中 | 最接近距離 中央(m) |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    by = defaultdict(list)
    for r in rows:
        by[r["cls"]].append(r)
    for cls in WARN:
        rs = by.get(cls, [])
        if not rs:
            continue
        g = lambda k: np.array([r[k] for r in rs])
        R.append(f"| {cls} | {len(rs):,} | {np.median(g('dur')):.1f} "
                 f"| {np.median(g('d_on')):.1f} / {g('d_on').max():.0f} "
                 f"| {np.median(g('snr_on')):.1f} "
                 f"| **{100*g('sudden_on').mean():.0f}%** | **{100*g('sudden_off').mean():.0f}%** "
                 f"| {100*g('cpa_in_window').mean():.0f}% | {np.median(g('d_cpa')):.1f} |")
    # サイレンの鳴り始め距離の分布
    sr = by.get("siren", [])
    if sr:
        d_on = np.array([r["d_on"] for r in sr])
        R += ["", "## サイレンの鳴り始め距離の分布", "",
              "| 帯 | 本数 | 割合 |", "| --- | --- | --- |"]
        for lo, hi in [(0, 10), (10, 20), (20, 40), (40, 80), (80, 1e9)]:
            m = (d_on >= lo) & (d_on < hi)
            R.append(f"| {lo}〜{hi if hi < 1e8 else '∞'} m | {m.sum():,} | {100*m.mean():.1f}% |")
        R += ["", f"参考: 現実のサイレンは連続鳴動で接近する（鳴り始めは可聴限界の外）。"
              f"学習コアでは発音窓 t_on〜t_off（{np.median([r['dur'] for r in sr]):.1f}s中央）だけ鳴り、"
              f"窓の位置は軌道と無関係に一様乱数で決まる（step11_v11_render.py:123）。"]
    (OUT / f"{which}.md").write_text("\n".join(R) + "\n", encoding="utf-8")
    print("\n".join(R))
    print("->", OUT / f"{which}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
