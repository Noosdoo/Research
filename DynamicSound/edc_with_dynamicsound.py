"""
残響比較に DynamicSound(屋外) を追加。
既存 edc_compare.png は metu(実測室) と seldgen(シミュ室) の2本だけ。
ここに DynamicSound の「実IR」を加える: 屋外=自由音場なので
直接音＋地面反射1発のみ、残響テール無し(T60≈0)。
出力: DynamicSound/_out/edc_compare3.png, ir_compare3.png
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
ROOT = os.path.join(HERE, "..")
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)


def edc(h, sr):
    h = np.asarray(h, float)
    h = h / (np.max(np.abs(h)) + 1e-12)
    E = np.flip(np.cumsum(np.flip(h ** 2)))
    return 10 * np.log10(E / np.max(E) + 1e-12), np.arange(len(h)) / sr


def t60_t20(E, t):
    i1 = int(np.argmax(E <= -5)); i2 = int(np.argmax(E <= -25))
    if i2 <= i1:
        return None
    return -60 / np.polyfit(t[i1:i2], E[i1:i2], 1)[0]


# ============ 1) DynamicSound 実IR をレンダリング ============
SR = 24000
CLICK = os.path.join(OUT, "_click.wav")
click = np.zeros(int(0.05 * SR)); click[2] = 1.0          # 単一インパルス
sf.write(CLICK, click, SR)

IR_DS = os.path.join(OUT, "_ir_dynamicsound.wav")
# 静止音源(IR定義のため) / リスナーは頭の高さ z=1.5m → 地面反射が分離して見える
src_pos = (5.0, 0.0, 0.5)        # 音源(車) 高さ0.5m
mic_pos = (0.0, 0.0, 1.5)        # リスナー頭
img_pos = (5.0, 0.0, -0.5)       # 地面反射=z鏡像
T = 0.6
src_path = ds.Path([[0.0, *src_pos, 1, 0, 0, 0], [T, *src_pos, 1, 0, 0, 0]])
img_path = ds.Path([[0.0, *img_pos, 1, 0, 0, 0], [T, *img_pos, 1, 0, 0, 0]])
mic_path = ds.Path([[0.0, *mic_pos, 1, 0, 0, 0], [T, *mic_pos, 1, 0, 0, 0]])
sim = ds.Simulation(temperature=20, pressure=1, relative_humidity=50)
mic = ds.microphones.Microphone(file_path=IR_DS, sample_rate=SR)
sim.add_microphone(path=mic_path, microphone=mic)
src = ds.sources.AudioFile(filename=CLICK, gain_db=0, loop=False)  # ループ禁止(IRなので1発)
sim.add_source(path=src_path, source=src)       # 直接音
sim.add_source(path=img_path, source=src)       # 地面反射
print("rendering DynamicSound impulse response...")
sim.run()
ir_ds, _ = sf.read(IR_DS)
if ir_ds.ndim > 1:
    ir_ds = ir_ds[:, 0]
pk = int(np.argmax(np.abs(ir_ds)))
ir_ds = ir_ds[max(0, pk - 30):]
E_ds, t_ds = edc(ir_ds, SR)

# ============ 2) metu 実測室 IR（抽出済み metu_ir.wav, W ch 48k）============
a, sr_a = sf.read(os.path.join(ROOT, "seld_move_ablation", "edc", "metu_ir.wav"))
if a.ndim > 1:
    a = a[:, 0]
pk = int(np.argmax(np.abs(a))); a = a[max(0, pk - 50):]
E_a, t_a = edc(a, sr_a); T_a = t60_t20(E_a, t_a)

# ============ 3) seldgen シミュ室 IR ============
b = np.load(os.path.join(ROOT, "seld_move_ablation", "edc", "sg_ir.npy"))
pk = int(np.argmax(np.abs(b))); b = b[max(0, pk - 30):]
E_b, t_b = edc(b, 24000); T_b = t60_t20(E_b, t_b)

print("metu T60=%.2fs  seldgen T60=%.2fs  DynamicSound: ground-reflection only (T60~0)" % (T_a, T_b))

# ============ Figure 1: EDC 3本 ============
plt.figure(figsize=(8, 5), facecolor="white")
plt.plot(t_a, E_a, lw=2, color="#d1495b", label="SpatialScaper（metu 実測室） T60≈%.1f s" % T_a)
plt.plot(t_b, E_b, lw=2, color="#3a7ca5", label="SELD-Data-Generator（pra シミュ室） T60≈%.2f s" % T_b)
plt.plot(t_ds, E_ds, lw=2, color="#2a9d8f", label="DynamicSound（屋外・自由音場） T60≈0（反射1発のみ）")
plt.axhline(-60, ls="--", c="gray", lw=1); plt.text(1.05, -58, "-60 dB", color="gray", fontsize=9)
plt.xlim(0, 1.5); plt.ylim(-80, 2); plt.grid(alpha=0.3)
plt.xlabel("time [s]"); plt.ylabel("Energy Decay Curve [dB]")
plt.title("残響比較（EDC）：既存=部屋（尾が長い）／ DynamicSound=屋外（残響なし）")
plt.legend(loc="upper right", fontsize=9)
plt.tight_layout()
p1 = os.path.join(OUT, "edc_compare3.png")
plt.savefig(p1, dpi=150); print("FIG ->", p1)

# ============ Figure 2: IR 3面 ============
fig, ax = plt.subplots(3, 1, figsize=(9, 8), facecolor="white", sharex=True)
for a_, (ir, sr, ti, c) in zip(ax, [
        (a, sr_a, "SpatialScaper 実測室 (metu, T60≈%.1fs) — 反射の尾が長い" % T_a, "#d1495b"),
        (b, 24000, "SELD-Data-Generator シミュ室 (pra, T60≈%.2fs) — 短い尾" % T_b, "#3a7ca5"),
        (ir_ds, SR, "DynamicSound 屋外 — 直接音＋地面反射1発のみ、尾なし", "#2a9d8f")]):
    tt = np.arange(len(ir)) / sr
    a_.plot(tt, ir / (np.max(np.abs(ir)) + 1e-12), c=c, lw=0.7)
    a_.set_xlim(0, 0.6); a_.set_ylabel("amp"); a_.set_title(ti, fontsize=10); a_.grid(alpha=0.3)
ax[-1].set_xlabel("time [s]")
plt.suptitle("インパルス応答：既存ツールは部屋の反射の尾／DynamicSoundは屋外で尾なし", y=1.0)
plt.tight_layout()
p2 = os.path.join(OUT, "ir_compare3.png")
plt.savefig(p2, dpi=150, bbox_inches="tight"); print("FIG ->", p2)
