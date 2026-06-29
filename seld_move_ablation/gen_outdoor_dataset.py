"""
seld_move_ablation / gen_outdoor_dataset.py
-------------------------------------------
自由音場の屋外SELD教師データ生成（MVP：屋外物理はまだ入れない）。
複数音源を「方向（静止 or 移動）」で FOA(ACN/SN3D) に符号化し、DOAラベルを自動付与。

含むもの:  多音源シーン / 静止・移動の軌跡 / FOA 4ch / DCASEラベル(frame,class,track,az,el)
含まない: 室内残響(=自由音場) / 屋外物理(1/r・ドップラー・大気吸収) ← これは次段で足す

使い方（SpatialScaper の venv で実行＝librosa/soundfile が要る）:
  python gen_outdoor_dataset.py <static|moving> <train|test> [NSCAPES]
出力:
  data/<split>_<mode>_outdoor/foa/mixNNN.wav   (FOA 4ch, 24kHz)
  data/<split>_<mode>_outdoor/labels/mixNNN.csv (frame,class,track,az,el  10fps)
"""
import os
import sys
import glob
import random
import numpy as np
import soundfile as sf
import librosa

SR = 24000
FPS = 10
DURATION = 30.0
N_EVENTS_RANGE = (3, 6)          # 1シーンのイベント数
EVENT_DUR_RANGE = (2.0, 6.0)     # 各イベントの長さ[s]
EL_RANGE = (-30.0, 0.0)          # 仰角[deg]：車両は耳より下

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES_DIR = os.path.join(HERE, "sources")   # class サブフォルダ/*.wav
OUT_ROOT = os.path.join(HERE, "data")
BG_DIR = os.path.join(HERE, "background")      # 背景音（非定位＝omni W に加算）
BG_LEVEL = 0.3                                 # 背景の大きさ（イベントRMSに対する比）


def load_sources():
    classes = sorted(d for d in os.listdir(SOURCES_DIR)
                     if os.path.isdir(os.path.join(SOURCES_DIR, d)))
    pool = {c: sorted(glob.glob(os.path.join(SOURCES_DIR, c, "*.wav"))) for c in classes}
    cls_id = {c: i for i, c in enumerate(classes)}
    return classes, pool, cls_id


def load_background():
    return sorted(glob.glob(os.path.join(BG_DIR, "*", "*.wav")))


def trajectory(n, moving):
    """各サンプルの az/el[deg]。moving=Trueは直線に方向が変化、Falseは一定。"""
    if moving:
        a0, a1 = np.random.uniform(-180, 180, 2)
        e0, e1 = np.random.uniform(EL_RANGE[0], EL_RANGE[1], 2)
        return np.linspace(a0, a1, n), np.linspace(e0, e1, n)
    az = np.full(n, np.random.uniform(-180, 180))
    el = np.full(n, np.random.uniform(EL_RANGE[0], EL_RANGE[1]))
    return az, el


def encode_foa(s, az_deg, el_deg):
    """自由音場 FOA(ACN/SN3D)。方向は時変。物理(1/r等)は無し。"""
    a = np.deg2rad(az_deg)
    e = np.deg2rad(el_deg)
    return np.stack([s,                       # W
                     s * np.sin(a) * np.cos(e),  # Y
                     s * np.sin(e),              # Z
                     s * np.cos(a) * np.cos(e)], axis=1)  # X


def generate_one(classes, pool, cls_id, bg_pool, mode, out_dir, idx, seed):
    random.seed(seed)
    np.random.seed(seed)
    N = int(DURATION * SR)
    foa = np.zeros((N, 4), dtype=np.float32)
    rows = []   # (frame, class, track, az, el)

    n_events = random.randint(*N_EVENTS_RANGE)
    for track in range(n_events):
        cls = random.choice(classes)
        clip = random.choice(pool[cls])
        full = librosa.load(clip, sr=SR, mono=True)[0]
        ev_dur = min(np.random.uniform(*EVENT_DUR_RANGE), len(full) / SR)
        ev_n = max(1, int(ev_dur * SR))
        st = random.randint(0, max(0, len(full) - ev_n))
        s = full[st:st + ev_n]
        onset = np.random.uniform(0, max(0.01, DURATION - ev_dur))
        i0 = int(onset * SR)
        az, el = trajectory(len(s), moving=(mode == "moving"))
        foa[i0:i0 + len(s)] += encode_foa(s, az, el)
        # 10fps ラベル（軌跡に追従）
        f0 = int(round(onset * FPS))
        f1 = int(round((onset + ev_dur) * FPS))
        for f in range(f0, f1):
            k = min(len(s) - 1, int((f / FPS - onset) * SR))
            rows.append((f, cls_id[cls], track, int(round(az[k])), int(round(el[k]))))

    # 背景音（非定位＝omni W のみに加算。DOAラベルは付けない）
    if bg_pool:
        bg = librosa.load(random.choice(bg_pool), sr=SR, mono=True)[0]
        if len(bg) < N:
            bg = np.tile(bg, int(np.ceil(N / len(bg))))
        bg = bg[:N]
        ev_rms = np.sqrt(np.mean(foa[:, 0] ** 2)) + 1e-9
        bg_rms = np.sqrt(np.mean(bg ** 2)) + 1e-9
        foa[:, 0] += bg * (ev_rms * BG_LEVEL / bg_rms)
    foa /= (np.max(np.abs(foa)) + 1e-9)
    name = f"mix{idx:03d}"
    sf.write(os.path.join(out_dir, "foa", name + ".wav"), foa, SR)
    rows.sort()
    with open(os.path.join(out_dir, "labels", name + ".csv"), "w") as fp:
        for r in rows:
            fp.write("%d,%d,%d,%d,%d\n" % r)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: python gen_outdoor_dataset.py <static|moving> <train|test> [NSCAPES]")
    mode, split = sys.argv[1], sys.argv[2]
    nscapes = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    classes, pool, cls_id = load_sources()
    bg_pool = load_background()
    out_dir = os.path.join(OUT_ROOT, f"{split}_{mode}_outdoor")
    os.makedirs(os.path.join(out_dir, "foa"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "labels"), exist_ok=True)
    base = 1000 if split == "train" else 9000

    print(f"[outdoor MVP] mode={mode} split={split} N={nscapes} "
          f"classes={classes} bg={len(bg_pool)} dur={DURATION}s (自由音場・物理なし) -> {out_dir}")
    for i in range(nscapes):
        generate_one(classes, pool, cls_id, bg_pool, mode, out_dir, i, base + i)
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{nscapes}")
    print("DONE:", out_dir)


if __name__ == "__main__":
    main()
