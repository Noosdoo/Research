# -*- coding: utf-8 -*-
"""v13試作（S1サイレン遠方スポーン・S2クラクション短発）の試聴AB用書き出し（2026-09-02）。

out/dataset_outdoor_siren_v13_proto/ にある試作クリップと、同じclip_idの v11 原本
（= v12コアと同一音）を並べて、ステレオ・べき圧縮の試聴wavにする。
サイレンのフレームSNR（masks）の時系列図も出す（「徐々に」が数字で見えるように）。

出力: out/v13_proto_listen/<clip>_A_v11.wav / <clip>_B_v13.wav / siren_snr.png / README.md
使い方: python scripts/_v13_proto_listen.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "out/dataset_outdoor_siren_v11"
V13 = ROOT / "out/dataset_outdoor_siren_v13_proto"
OUT = ROOT / "out/v13_proto_listen"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def stereo_listen(foa: np.ndarray) -> np.ndarray:
    L, R = foa[0] + 0.5 * foa[1], foa[0] - 0.5 * foa[1]
    st = np.stack([L, R], axis=1)
    st = st / (np.max(np.abs(st)) + 1e-12)
    st = np.sign(st) * np.abs(st) ** 0.5
    return (st * 0.7).astype(np.float32)


def snr_series(mask_csv: Path, cls_idx: int) -> np.ndarray:
    out = {}
    with open(mask_csv, newline="") as f:
        for r in csv.DictReader(f):
            if int(r["class"]) == cls_idx:
                out[int(r["frame"])] = float(r["snr_a_db"])
    return np.array([out.get(k, np.nan) for k in range(100)])


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    clips = sorted(p.stem for p in (V13 / "foa").glob("*.flac"))
    R = ["# v13試作の試聴AB（自動生成: _v13_proto_listen.py）", "",
         "A = v11原本（=v12コアと同一音・現行の学習データ） / B = v13試作（S1・S2）。",
         "同じseed・同じ車・同じ暗騒音で、**サイレン/クラクションの鳴り方だけ**が違う。",
         "ステレオ・べき圧縮（Joy-conデモと同じ試聴用加工。較正は捨てている）。", "",
         "| clip | クラス | A(v11): 鳴り方 | B(v13): 鳴り方 | 図 |", "| --- | --- | --- | --- | --- |"]
    series = []
    for clip in clips:
        sa = json.loads((V11 / "work" / clip / "scene.json").read_text(encoding="utf-8"))
        sb = json.loads((V13 / "work" / clip / "scene.json").read_text(encoding="utf-8"))
        for tag, ds in (("A_v11", V11), ("B_v13", V13)):
            x, sr = sf.read(str(ds / "foa" / f"{clip}.flac"), dtype="float64", always_2d=True)
            sf.write(OUT / f"{clip}_{tag}.wav", stereo_listen(x.T), sr, subtype="PCM_16")
        wa = [s for s in sa["sources"] if s["class"] in ("siren", "horn")][0]
        wb = [s for s in sb["sources"] if s["class"] in ("siren", "horn")][0]
        cls = wa["class"]
        da = (f"{wa['t_on']:.1f}〜{wa['t_off']:.1f}s だけ鳴る（最接近{wa['min_dist_m']:.0f}m）")
        if cls == "siren":
            db = (f"全体で鳴動・開始{wb['start_dist_m']:.0f}m先→最接近{wb['min_dist_m']:.0f}m"
                  f"（t_cpa={wb['t_cpa_s']:.0f}s{'=クリップ外' if wb['t_cpa_s'] > 10 else ''}）")
            series.append((clip, snr_series(V11 / "masks" / f"{clip}.csv", 0),
                           snr_series(V13 / "masks" / f"{clip}.csv", 0)))
        else:
            db = (f"{wb['n_honk']}回・{wb['t_on']:.1f}〜{wb['t_off']:.1f}s"
                  f"（最接近{wb['min_dist_m']:.0f}m の直前）")
        R.append(f"| {clip} | {cls} | {da} | {db} | {'siren_snr.png' if cls == 'siren' else ''} |")
        print(R[-1])

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(len(series), 1, figsize=(7, 2.2 * len(series)), sharex=True)
        for ax, (clip, a, b) in zip(np.atleast_1d(axes), series):
            t = np.arange(100) * 0.1
            ax.plot(t, a, label="A: v11 (window)", color="tab:gray")
            ax.plot(t, b, label="B: v13 (continuous, far spawn)", color="tab:red")
            ax.axhline(0, color="k", lw=0.5)
            ax.set_ylim(-30, 80)                      # 無音の床(−500dB)で潰れないように
            ax.set_ylabel("siren SNR_A [dB]")
            ax.set_title(clip, fontsize=9)
            ax.grid(alpha=0.3)
        np.atleast_1d(axes)[0].legend(fontsize=8)
        np.atleast_1d(axes)[-1].set_xlabel("time [s]")
        fig.tight_layout()
        fig.savefig(OUT / "siren_snr.png", dpi=120)
    except Exception as e:
        print("figure skipped:", e)

    R += ["", "## 聴いてほしい点", "",
          "1. サイレン: Bは「遠くで鳴っていて近づいてくる／通り過ぎて遠ざかる」に聞こえるか。",
          "   A（現行）の「途中で突然鳴り出して4秒で消える」との違い",
          "2. クラクション: Bの「近づいた車が1〜2回プッと鳴らす」は自然か（長さ・回数・タイミング）",
          "3. 図 siren_snr.png: Bはサイレンの受聴SNRがなだらかに上がる/下がる（Aは矩形）", "",
          "## 設計メモ（本採用時に決めること）", "",
          "- サイレンの開始距離は対数一様 30m〜2km。実物の可聴限界はkm単位なので、",
          "  10秒窓の中で「鳴り始め」は原理的に起きない。例外（車庫出発）を少数混ぜるかは未決",
          "- ⚠️ **試作の冒頭無音は伝播遅延の artifact**（放射がt=0から始まるため、925m先なら2.7秒は",
          "  音が届かない）。本採用時はレンダラにプリロール（t<0からの放射）を足して消す。",
          "  聴くときは冒頭の無音を「鳴り始め」と取らないでほしい",
          "- **警告音のラベルにも可聴ゲート（SNR_A ≥ 0 dB）を適用**した。トーン性の音は広帯域SNRが",
          "  0dB未満でも聞こえるので、閾値を下げる（例 −6〜−10dB）かは要検討",
          "- クラクションを鳴らす車の走行音は現行どおり付いていない（別項目S2b）"]
    (OUT / "README.md").write_text("\n".join(R) + "\n", encoding="utf-8")
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
