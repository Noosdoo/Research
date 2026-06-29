"""
残響尾の比較に DynamicSound(屋外) パネルを追加。
既存の car_dry/metu/seldgen（同一音源・静止）に、同じ乾き音源を
DynamicSoundで静止レンダリング(直接音＋地面反射, loop=False)したものを並べる。
予想: 屋外=自由音場なので鳴り止み後の残響テールが無い。
出力: DynamicSound/_out/reverb_tail_compare.png
"""
import os
import numpy as np
import soundfile as sf
import dynamic_sound as ds
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
for fp in [r"C:/Windows/Fonts/meiryo.ttc", r"C:/Windows/Fonts/YuGothM.ttc"]:
    try:
        fm.fontManager.addfont(fp)
        plt.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
        break
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
EDC = os.path.join(HERE, "..", "seld_move_ablation", "edc")
OUT = os.path.join(HERE, "_out")
SR = 24000
C = 343.0
TCUT = 2.5  # 既存図と同じ鳴り止み時刻


def nrm(x):
    return 0.97 * x / (np.max(np.abs(x)) + 1e-9)


# --- 既存3種（同一音源・静止）を読む ---
dry, _ = sf.read(os.path.join(EDC, "car_dry.wav"))
met, _ = sf.read(os.path.join(EDC, "car_metu.wav"))
sgn, _ = sf.read(os.path.join(EDC, "car_seldgen.wav"))

# --- DynamicSound: 同じ乾き音源を静止音源として屋外レンダリング ---
DRYWAV = os.path.join(EDC, "car_dry.wav")
IRD = os.path.join(OUT, "_car_dry_dynamicsound.wav")
dur = len(dry) / SR
src_pos = (2.0, 0.0, 0.5)     # 静止音源
mic_pos = (0.0, 0.0, 1.5)     # リスナー頭
img_pos = (2.0, 0.0, -0.5)    # 地面反射(z鏡像)
sp = ds.Path([[0.0, *src_pos, 1, 0, 0, 0], [dur, *src_pos, 1, 0, 0, 0]])
ip = ds.Path([[0.0, *img_pos, 1, 0, 0, 0], [dur, *img_pos, 1, 0, 0, 0]])
mp = ds.Path([[0.0, *mic_pos, 1, 0, 0, 0], [dur, *mic_pos, 1, 0, 0, 0]])
sim = ds.Simulation(temperature=20, pressure=1, relative_humidity=50)
mic = ds.microphones.Microphone(file_path=IRD, sample_rate=SR)
sim.add_microphone(path=mp, microphone=mic)
src = ds.sources.AudioFile(filename=DRYWAV, gain_db=0, loop=False)   # ループ禁止=鳴り止む
sim.add_source(path=sp, source=src)      # 直接音
sim.add_source(path=ip, source=src)      # 地面反射
print("rendering DynamicSound (static source, outdoor)...")
sim.run()
dsnd, _ = sf.read(IRD)
if dsnd.ndim > 1:
    dsnd = dsnd[:, 0]
# 直接音の伝搬遅延ぶん先頭をトリムして鳴り止み時刻を既存と揃える
dist = np.linalg.norm(np.array(src_pos) - np.array(mic_pos))
shift = int(round(dist / C * SR))
dsnd = dsnd[shift:]

# --- 図（ダーク, 4面）---
plt.style.use("dark_background")
t = np.arange(len(dry)) / SR
fig, ax = plt.subplots(4, 1, figsize=(9, 8), sharex=True)
panels = [
    (dry,  "元音源（室内残響なし）", "#bbbbbb"),
    (met,  "SpatialScaper 実測室（metu）", "#e0566c"),
    (sgn,  "SELD-Data-Generator シミュ室（pra）", "#4a9fd0"),
    (nrm(dsnd), "DynamicSound 屋外（自由音場・直接音＋地面反射のみ）", "#39c0a8"),
]
for a, (y, ti, c) in zip(ax, panels):
    tt = np.arange(len(y)) / SR
    a.plot(tt, y, c=c, lw=0.6)
    a.axvline(TCUT, color="white", ls=":", lw=1)
    a.set_xlim(2.2, 4.0); a.set_ylim(-1, 1)
    a.grid(alpha=0.25)
    a.set_title(ti, fontsize=10, loc="center")
    a.set_ylabel("amp")
ax[-1].set_xlabel("time [s]   （点線＝音が鳴り止む瞬間。以降の尾＝残響）")
fig.tight_layout()
p = os.path.join(OUT, "reverb_tail_compare.png")
fig.savefig(p, dpi=140)
print("FIG ->", p)

# 鳴り止み後(2.6s以降)の残量を数値で
def post_rms(y):
    seg = y[int(2.6 * SR): int(4.0 * SR)]
    return float(np.sqrt(np.mean(seg ** 2)))
print("post-2.6s RMS  metu=%.4f seldgen=%.4f DynamicSound=%.5f" %
      (post_rms(met), post_rms(sgn), post_rms(nrm(dsnd))))
