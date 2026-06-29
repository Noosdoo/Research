"""
DynamicSound出力を「図」と「音」で体感する。
- 図: ①ジオメトリ(俯瞰) ②距離(t)と1/r予測 vs 実測RMS包絡 ③スペクトログラム(ドップラー)
- 音: dry(生音) / rendered(物理付き mono) / rendered stereo(空間差は微小・確認用)
入力 : DynamicSound/_out/car_5s.wav (run_car_5s.py で生成済み)
出力 : DynamicSound/_out/ に png と listen_*.wav
"""
import os
import numpy as np
import soundfile as sf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import spectrogram, resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
DRY = os.path.join(HERE, "..", "dynamic-sound", "examples",
                   "resources", "sounds", "suv_dirt_road.wav")
REN = os.path.join(HERE, "_out", "car_5s.wav")
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)

# --- ジオメトリ（run_car_5s.py と同じ）---
DUR = 5.0
X = 5.0                       # 車の横位置 [m]
Y0, Y1 = 40.0, -40.0         # y: +40 -> -40
def car_y(t): return Y0 + (Y1 - Y0) * (t / DUR)
def car_dist(t):             # マイク原点からの距離
    return np.sqrt(X**2 + car_y(t)**2 + 1.0**2)   # z=1m

# --- 読み込み ---
ren, sr = sf.read(REN)        # (40960, 4)
if ren.ndim == 1:
    ren = ren[:, None]
ch0 = ren[:, 0]
t = np.arange(len(ch0)) / sr

# --- 実測RMS包絡 ---
hop = 512
rms_t, rms_v = [], []
for i in range(0, len(ch0) - hop, hop):
    seg = ch0[i:i + hop]
    rms_t.append((i + hop / 2) / sr)
    rms_v.append(np.sqrt(np.mean(seg**2)))
rms_t, rms_v = np.array(rms_t), np.array(rms_v)

# 1/r 予測（距離減衰のみ。空気吸収・地面反射は含まずの理論線）
pred = 1.0 / car_dist(rms_t)
pred = pred / pred.max() * rms_v.max()   # スケール合わせ

# ================= 図 =================
fig, axes = plt.subplots(3, 1, figsize=(9, 11))

# ① 俯瞰ジオメトリ
ax = axes[0]
ts = np.linspace(0, DUR, 200)
ax.plot([X, X], [Y0, Y1], "-", color="tab:blue", lw=2, label="car path")
ax.scatter([X], [car_y(2.5)], color="tab:blue", zorder=5)
ax.annotate("car @t=2.5s\n(closest)", (X, car_y(2.5)),
            textcoords="offset points", xytext=(8, 0))
ax.scatter([0], [0], color="tab:red", marker="*", s=200, zorder=5, label="mic (head)")
ax.plot([0, X], [0, 0], "--", color="gray", lw=1)
ax.annotate(f"{X:.0f} m", (X / 2, 1.5), color="gray")
ax.set_xlabel("x [m] (lateral)"); ax.set_ylabel("y [m] (along walk dir)")
ax.set_title("(1) Geometry: car passing the listener (top view)")
ax.set_aspect("equal"); ax.grid(alpha=0.3); ax.legend(loc="upper right")

# ② 距離と包絡
ax = axes[1]
ax2 = ax.twinx()
l1, = ax.plot(rms_t, car_dist(rms_t), color="gray", lw=2, label="distance(t) [m]")
l2, = ax2.plot(rms_t, rms_v, color="tab:green", lw=2, label="measured RMS (rendered)")
l3, = ax2.plot(rms_t, pred, "--", color="tab:orange", lw=2, label="1/r prediction (scaled)")
ax.set_xlabel("time [s]"); ax.set_ylabel("distance [m]", color="gray")
ax2.set_ylabel("level (RMS)", color="tab:green")
ax.set_title("(2) Pass-by loudness swell = distance attenuation (1/r)")
ax.grid(alpha=0.3)
ax.legend(handles=[l1, l2, l3], loc="upper right")

# ③ スペクトログラム（ドップラー）
ax = axes[2]
f, tt, Sxx = spectrogram(ch0, fs=sr, nperseg=1024, noverlap=768)
Sxx_db = 10 * np.log10(Sxx + 1e-12)
m = f <= 2000
pcm = ax.pcolormesh(tt, f[m], Sxx_db[m], shading="auto", cmap="magma")
ax.axvline(2.5, color="cyan", ls="--", lw=1)
ax.annotate("closest approach\n(Doppler: high->low)", (2.55, 1600),
            color="cyan", fontsize=9)
ax.set_xlabel("time [s]"); ax.set_ylabel("freq [Hz]")
ax.set_title("(3) Spectrogram of rendered ch0 — Doppler shift across pass-by")
fig.colorbar(pcm, ax=ax, label="dB")

fig.tight_layout()
png = os.path.join(OUT, "car_physics.png")
fig.savefig(png, dpi=130)
print("FIG ->", png)

# ================= 音 =================
def norm(x):
    x = x - np.mean(x)
    p = np.max(np.abs(x))
    return x / p * 0.95 if p > 0 else x

# dry: 60sの定常エンジン音から先頭5sを切り出して試聴用に
dry, sr_dry = sf.read(DRY)
if dry.ndim > 1:
    dry = dry[:, 0]
dry5 = dry[:int(sr_dry * DUR)]
sf.write(os.path.join(OUT, "listen_dry.wav"), norm(dry5), sr_dry)

# rendered mono（物理付き）
sf.write(os.path.join(OUT, "listen_rendered_mono.wav"), norm(ch0), sr)

# rendered stereo（ch0=+x を L, ch2=-x を R。空間差は微小だが確認用）
if ren.shape[1] >= 3:
    st = np.stack([norm(ren[:, 0]), norm(ren[:, 2])], axis=1)
    sf.write(os.path.join(OUT, "listen_rendered_stereo.wav"), st, sr)

print("WAV -> listen_dry.wav / listen_rendered_mono.wav / listen_rendered_stereo.wav  (in _out/)")
print("\n聴き比べ: dry=生音(物理なし) → rendered=ドップラー＋通過ラウドネス山が乗る")
