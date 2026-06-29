"""
seldgen/SpatialScaper と同一音源(car_dry_mono.wav)で DynamicSound をレンダリングし、
「dry / metu(実測室SRIR) / seldgen(シミュ室SRIR) / DynamicSound(屋外物理)」を4面比較。
- 図 : 同一音源を各レンダラに通したスペクトログラム比較
- 音 : listen_dynamicsound_mono.wav（同一音源の屋外物理版）
出力 : DynamicSound/_out/
"""
import os
import numpy as np
import soundfile as sf
import dynamic_sound as ds
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import spectrogram

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "SELD-Data-Generator", "srir",
                   "ambisonics_dependencies", "car_demos", "car_dry_mono.wav")
EDC = os.path.join(HERE, "..", "seld_move_ablation", "edc")
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)

SR = 24000          # seldgen/metu と同じ
DUR = 6.5           # 〃 と同じ長さ
REN = os.path.join(OUT, "car_dynamicsound.wav")

# ---- DynamicSound レンダリング（同一音源・原点に無指向マイク1個）----
X = 5.0
src_path = ds.Path([[0.0, X,  40, 1, 1, 0, 0, 0],
                    [DUR, X, -40, 1, 1, 0, 0, 0]])
refl_path = ds.Path([[0.0, X,  40, -1, 1, 0, 0, 0],   # 地面反射(z鏡像)
                     [DUR, X, -40, -1, 1, 0, 0, 0]])
mic_path = ds.Path([[0.0, 0, 0, 1, 1, 0, 0, 0],
                    [DUR, 0, 0, 1, 1, 0, 0, 0]])

sim = ds.Simulation(temperature=20, pressure=1, relative_humidity=50)
mic = ds.microphones.Microphone(file_path=REN, sample_rate=SR)   # 無指向1ch @原点
sim.add_microphone(path=mic_path, microphone=mic)
src = ds.sources.AudioFile(filename=SRC, gain_db=10)
sim.add_source(path=src_path, source=src)        # 直接音
sim.add_source(path=refl_path, source=src)       # 地面反射
print("rendering DynamicSound (same source, 6.5s @24k)...")
sim.run()
print("rendered ->", REN)

# ---- 読み込み（4種・同一音源）----
def load(p):
    y, sr = sf.read(p)
    if y.ndim > 1:
        y = y[:, 0]
    return y, sr

clips = {
    "dry (no physics)":            os.path.join(EDC, "car_dry.wav"),
    "metu  (real room SRIR)":      os.path.join(EDC, "car_metu.wav"),
    "seldgen (sim room SRIR)":     os.path.join(EDC, "car_seldgen.wav"),
    "DynamicSound (outdoor phys)": REN,
}

# ================= 4面スペクトログラム比較 =================
fig, axes = plt.subplots(4, 1, figsize=(9, 12), sharex=True)
for ax, (title, path) in zip(axes, clips.items()):
    y, sr = load(path)
    y = y / (np.max(np.abs(y)) + 1e-9)
    f, tt, Sxx = spectrogram(y, fs=sr, nperseg=1024, noverlap=768)
    m = f <= 4000
    ax.pcolormesh(tt, f[m], 10 * np.log10(Sxx[m] + 1e-12),
                  shading="auto", cmap="magma", vmin=-100, vmax=-20)
    ax.set_ylabel("Hz")
    ax.set_title(f"{title}   (same source: car_dry_mono.wav)", fontsize=10)
axes[-1].set_xlabel("time [s]")
fig.suptitle("Same source, different renderers — room reverb vs outdoor physics",
             fontsize=12)
fig.tight_layout()
png = os.path.join(OUT, "car_compare.png")
fig.savefig(png, dpi=130)
print("FIG ->", png)

# ================= 試聴 =================
y, sr = load(REN)
y = y - np.mean(y)
y = y / (np.max(np.abs(y)) + 1e-9) * 0.95
sf.write(os.path.join(OUT, "listen_dynamicsound_mono.wav"), y, sr)
print("WAV -> listen_dynamicsound_mono.wav (same source, outdoor physics)")
print("比較用既存: seld_move_ablation/edc/car_dry.wav / car_metu.wav / car_seldgen.wav")
