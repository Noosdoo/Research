# -*- coding: utf-8 -*-
"""⑥ 雨音の試作を試聴用に書き出す（2026-09-02）。本人の耳で確認してもらうための音。

作るもの（out/rain_proto/）:
  1. rain_<light|moderate|heavy>.wav — 雨音だけ（モノ・6秒・ピーク正規化）。質感の確認用
  2. mix_<clip>_norain.wav / mix_<clip>_rain<XX>dBA.wav — v12 valの実クリップ
     （車2台＋サイレン、暗騒音41dBA）に雨を XX dB(A) で足したもの。ステレオ・べき圧縮
     （Joy-conデモと同じ試聴用加工。較正は捨てている）。「車の走行音がどれだけ埋まるか」の確認用
  3. README.md — 何を聴いてほしいか・仮置きの数値
  4. rain_spectrum.png — 3強度のA特性オクターブ帯スペクトル（数字の確認用）

⚠️ これは学習データではない。学習用に入れるかは10月末の④の束で判断する。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from outdoor_seld import rain as R  # noqa: E402
from outdoor_seld.calibration import gain_for_spl_a, spl_a, a_weight_amplitude  # noqa: E402

FS = 24000
OUT = ROOT / "out/rain_proto"
CLIPS = {"fold2_room1_mix0777": "車1台のみ（最接近2.0m・7.6s・受聴69.6dBA）・暗騒音40.6dBA",
         "fold2_room1_mix0001": "車2台(1.0m/2.4m)＋サイレン2.9-8.4s(115dBA!)・暗騒音41.2dBA"}
RAIN_DBA = [50.0, 58.0, 65.0]         # 中程度〜強い雨の仮置き（README参照）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def stereo_listen(foa: np.ndarray) -> np.ndarray:
    """(4,n) FOA → 試聴用ステレオ（L=W+0.5Y / R=W−0.5Y・ピーク正規化・べき圧縮0.5・0.7倍）。"""
    L = foa[0] + 0.5 * foa[1]
    Rr = foa[0] - 0.5 * foa[1]
    st = np.stack([L, Rr], axis=1)
    st = st / (np.max(np.abs(st)) + 1e-12)
    st = np.sign(st) * np.abs(st) ** 0.5
    return (st * 0.7).astype(np.float32)


def octave_levels(x: np.ndarray, fs: int):
    X = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / fs)
    X = X * a_weight_amplitude(f) ** 2
    fcs = [63, 125, 250, 500, 1000, 2000, 4000, 8000]
    return fcs, [10 * np.log10(X[(f >= fc / np.sqrt(2)) & (f < fc * np.sqrt(2))].sum() + 1e-30)
                 for fc in fcs]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260902)
    n = 6 * FS
    spec_rows = []
    for name, rate in R.INTENSITY.items():
        x = R.rain_mono(n, FS, rng, rate)
        y = 0.9 * x / np.max(np.abs(x))
        sf.write(OUT / f"rain_{name}.wav", y.astype(np.float32), FS, subtype="PCM_16")
        fcs, lv = octave_levels(x, FS)
        lv = np.array(lv) - max(lv)
        spec_rows.append((name, rate, fcs, lv))
        print(f"rain_{name}: rate={rate:.0f}/s  A特性オクターブ帯(最大=0dB): "
              + " ".join(f"{fc}Hz:{l:+.0f}" for fc, l in zip(fcs, lv)))

    # 実クリップに足す
    # v12コアの音声は v11 core とビット同一（v12生成物はサーバ側。ローカルは v11 の同名flacを使う）
    lines = []
    for clip, desc in CLIPS.items():
        foa, sr = sf.read(str(ROOT / "out/dataset_outdoor_siren_v11/foa" / f"{clip}.flac"),
                          dtype="float64", always_2d=True)
        foa = foa.T
        assert sr == FS and foa.shape[0] == 4
        base_dba = spl_a(foa[0], FS)
        sf.write(OUT / f"mix_{clip}_norain.wav", stereo_listen(foa), FS, subtype="PCM_16")
        lines.append(f"| {clip} | {desc} | なし | {base_dba:.1f} dB(A) |")
        print(lines[-1])
        for dba in RAIN_DBA:
            rate = R.INTENSITY["moderate"] if dba < 60 else R.INTENSITY["heavy"]
            rf = R.diffuse_foa_rain(foa.shape[1], FS, rng, rate)
            rf = rf * gain_for_spl_a(rf[0], FS, dba)
            mix = foa + rf
            sf.write(OUT / f"mix_{clip}_rain{dba:.0f}dBA.wav", stereo_listen(mix), FS,
                     subtype="PCM_16")
            lines.append(f"| {clip} | 同上 | {dba:.0f} dB(A)・{rate:.0f}/s "
                         f"| {spl_a(mix[0], FS):.1f} dB(A) |")
            print(lines[-1])

    # スペクトル図
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6, 3.5))
        for name, rate, fcs, lv in spec_rows:
            ax.plot(fcs, lv, marker="o", label=f"{name} ({rate:.0f}/s)")
        ax.set_xscale("log")
        ax.set_xticks(fcs)
        ax.set_xticklabels([str(f) for f in fcs])
        ax.set_xlabel("octave band [Hz]")
        ax.set_ylabel("A-weighted level rel. max [dB]")
        ax.set_title("synthetic rain prototype: A-weighted octave spectrum")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(OUT / "rain_spectrum.png", dpi=130)
    except Exception as e:  # matplotlib が無くても音は出す
        print("figure skipped:", e)

    md = ["# ⑥ 雨音 試作の試聴セット（2026-09-02・自動生成: _rain_proto_listen.py）", "",
          "⚠️ 学習データではない。**本人の耳で確認してもらうための音**。",
          "モデル= `src/outdoor_seld/rain.py`（雨滴バーストのポアソン重ね合わせ＋2〜6kHzの地）。",
          "雨の3要素のうち①背景雑音としての雨音だけ（②マイクへの雨滴・③濡れた路面のタイヤ音は含まない）。", "",
          "## 聴いてほしい点", "",
          "1. `rain_light/moderate/heavy.wav`（雨だけ・6秒）: **雨に聞こえるか**。",
          "   気になる方向を教えてほしい: 「粒が立ちすぎ／地が多すぎ」「高すぎ・シャリシャリ」",
          "   「低音が足りない」「傘に当たる音に近い／遠くの雨に近い」など",
          "2. `mix_<clip>_norain.wav` → `_rain50dBA` → `_rain58dBA` → `_rain65dBA`: ",
          "   実クリップ（下表の2本）に雨を足したもの。",
          "   **車の走行音がどの雨量で聞き取れなくなるか**（mix0777=車だけ・静かな背景が本命。"
          "mix0001はサイレン115dBAが支配的なので参考）",
          "3. 音の作り自体が違うと思ったら、それが一番の情報（実録の雨とAB比較する前の仮説になる）", "",
          "## 仮置きの数値（⚠️ 要出典・10月の実録で検証）", "",
          "| 強さ | 雨滴発生率 | 想定レベル（舗装路・屋外・傘なし） |", "| --- | --- | --- |",
          "| light | 150/s | 45〜50 dB(A) |", "| moderate | 600/s | 50〜58 dB(A) |",
          "| heavy | 2,500/s | 60〜68 dB(A) |", "",
          "## 混合結果（W ch のA特性レベル・クリップ全体）", "",
          "| クリップ | 内容 | 雨 | 混合後の全体レベル |", "| --- | --- | --- | --- |"] + lines + [
          "", "## 学習データに入れる場合の設計（案・未決）", "",
          "- 雨あり/なし・強さ（発生率・dB(A)）を **plan の列として記録**し層別採点できるようにする",
          "  （todo⑥の注意2。「雨で何pt落ちたか」を言えるように）",
          "- 空間は等方拡散（暗騒音と同じ規約）。実録で下方（路面）に偏ると分かれば Z を弱める",
          "- ③濡れた路面のタイヤ音は音源側の差し替えが要る（別項目。ここでは扱わない）",
          "- 車が最も落ちる見込み（広帯域どうし）。警告音（トーン性）は相対的に強いはず"]
    (OUT / "README.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
