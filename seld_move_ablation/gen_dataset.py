"""
seld_move_ablation / gen_dataset.py
-----------------------------------
SpatialScaper で SELD合成データを "static版 / moving版" でバッチ生成する。
移動 on/off の ablation 用：唯一の違いは event_position（静止 vs 移動）。
他（音源・クラス・シーン数・polyphony・背景・乱数シード範囲）は完全に同条件。

使い方（SpatialScaper の venv で実行）:
  python gen_dataset.py <mode> <split> [NSCAPES]
    mode  : static | moving
    split : train | test
  例:
    python gen_dataset.py static train 100
    python gen_dataset.py moving train 100
    python gen_dataset.py moving test  30

出力:
  data/<split>_<mode>/foa/mixNNN.wav      (FOA 4ch, 24kHz)
  data/<split>_<mode>/labels/mixNNN.csv   (DCASE形式 frame,class,track,az,el,(dist))

設計メモ:
- static: event_position=("static", None)
- moving: event_position=("moving", ("uniform", None, None))   ← SpatialScaper のネイティブ移動
  （core.py: "moving"指定で define_trajectory が speed_limit を使い軌跡を自動生成）
- まずは seld_match の9クラス(既存音源)を流用。危険音クラスは後で foreground を差し替えるだけ。
- 速度は SpatialScaper の speed_limit[m/s]（論文TAU-NIGENSは角速度10/20/40°/s。厳密一致はせず、speed sweepは後段）。
"""
import os
import sys
import random
import numpy as np

import spatialscaper as ss
import spatialscaper.core as ss_core

# ---- パス（SpatialScaper の datasets を絶対パスで参照＝どこから実行してもOK）----
SS_ROOT = r"C:\Users\satos\research\SpatialScaper"
FOREGROUND_DIR = os.path.join(SS_ROOT, "datasets", "sound_event_datasets", "seld_match")
RIR_DIR        = os.path.join(SS_ROOT, "datasets", "rir_datasets")
OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ---- クラス（seld_match の9クラス。SpatialScaperはDCASE13固定なので辞書差し替え）----
CLASSES = ["Bird", "BirdVocalization", "Car", "Gunshot", "Rain",
           "Subway", "Thunder", "Train", "Walk"]
ss_core.__DCASE_SOUND_EVENT_CLASSES__ = {c: i for i, c in enumerate(CLASSES)}

# ---- 条件（static/moving で完全に揃える）----
ROOM = "metu"
FMT = "foa"
DURATION = 30.0        # PoC用。TAU-NIGENS標準は60s（最終は60に上げる）
SR = 24000
MAX_OVERLAP = 2        # TAU-NIGENS標準 = 最大polyphony 2
N_EVENTS = 6           # 1シーンあたりのイベント数
REF_DB = -65
SPEED_LIMIT = 1.5      # moving時の移動速度[m/s]（後でsweep）


def event_position_for(mode):
    if mode == "static":
        return ("static", None)
    if mode == "moving":
        return ("moving", ("uniform", None, None))
    raise ValueError("mode must be 'static' or 'moving'")


def generate_one(mode, out_dir, index, seed):
    random.seed(seed)
    np.random.seed(seed)
    ssc = ss.Scaper(duration=DURATION, foreground_dir=FOREGROUND_DIR, rir_dir=RIR_DIR,
                    fmt=FMT, room=ROOM, use_room_ambient_noise=False,
                    max_event_overlap=MAX_OVERLAP, sr=SR, speed_limit=SPEED_LIMIT)
    ssc.ref_db = REF_DB
    ssc.add_background()
    pos = event_position_for(mode)
    for _ in range(N_EVENTS):
        ssc.add_event(event_position=pos)        # ★ ここだけが static / moving の違い
    name = f"mix{index:03d}"
    ssc.generate(os.path.join(out_dir, "foa", name),
                 os.path.join(out_dir, "labels", name))


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: python gen_dataset.py <static|moving> <train|test> [NSCAPES]")
    mode = sys.argv[1]
    split = sys.argv[2]
    nscapes = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    out_dir = os.path.join(OUT_ROOT, f"{split}_{mode}")
    os.makedirs(os.path.join(out_dir, "foa"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "labels"), exist_ok=True)

    # train と test で乱数レンジを分ける（独立シーン）
    base_seed = 1000 if split == "train" else 9000

    print(f"[gen] mode={mode} split={split} N={nscapes} dur={DURATION}s "
          f"overlap={MAX_OVERLAP} -> {out_dir}")
    for i in range(nscapes):
        generate_one(mode, out_dir, i, seed=base_seed + i)
        if (i + 1) % 5 == 0:
            print(f"  {i+1}/{nscapes}")
    print("DONE:", out_dir)


if __name__ == "__main__":
    main()
