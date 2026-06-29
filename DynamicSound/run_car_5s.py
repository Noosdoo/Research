"""
car例の最小確認版（5s）。
目的: DynamicSoundが実際に出力を出せるか + 4ch生波形の中身を見る。
出力: DynamicSound/_out/car_5s.wav
"""
import os
import numpy as np
import dynamic_sound as ds
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
# 音源は dynamic-sound 同梱のものを流用
RES = os.path.join(HERE, "..", "dynamic-sound", "examples",
                   "resources", "sounds", "suv_dirt_road.wav")
OUT = os.path.join(HERE, "_out", "car_5s.wav")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

DUR = 5.0  # 20s -> 5s に短縮

# 車: x=5m横, z=1m高さ, y=+40 -> -40 を5秒で通過（マイク前を横切る）
source_path = ds.Path([[0.0, 5,  40, 1, 1, 0, 0, 0],
                       [DUR, 5, -40, 1, 1, 0, 0, 0]])
# 地面反射（z=-1の鏡像）
reflection_path = ds.Path([[0.0, 5,  40, -1, 1, 0, 0, 0],
                           [DUR, 5, -40, -1, 1, 0, 0, 0]])
# 4chマイク（原点・±2cm）
microphone_path = ds.Path([[0.0, 0, 0, 1, 1, 0, 0, 0],
                           [DUR, 0, 0, 1, 1, 0, 0, 0]])

sim = ds.Simulation(temperature=20, pressure=1, relative_humidity=50)
mic = ds.microphones.MicrophoneArray(file_path=OUT, sample_rate=8192, positions=[
    (0.02, 0, 0, 1, 0, 0, 0),
    (0, 0.02, 0, 1, 0, 0, 0),
    (-0.02, 0, 0, 1, 0, 0, 0),
    (0, -0.02, 0, 1, 0, 0, 0)])
sim.add_microphone(path=microphone_path, microphone=mic)
src = ds.sources.AudioFile(filename=RES, gain_db=20)
sim.add_source(path=source_path, source=src)      # 直接音
sim.add_source(path=reflection_path, source=src)  # 地面反射
print("running simulation (5s)...")
sim.run()

y, sr = sf.read(OUT)
print(f"\nDONE -> {OUT}")
print(f"shape={y.shape}  sr={sr}  dur={len(y)/sr:.2f}s")
if y.ndim == 1:
    y = y[:, None]
print(f"nchan={y.shape[1]}")
print(f"global: min={y.min():+.4f} max={y.max():+.4f}  any_nan={np.isnan(y).any()}")
for c in range(y.shape[1]):
    ch = y[:, c]
    print(f"  ch{c}: rms={np.sqrt(np.mean(ch**2)):.5f}  peak={np.max(np.abs(ch)):.5f}")

# ch間の差を見る（FOA化に必要なレベル差/位相差が出ているか）
print("\n--- inter-channel correlation (lag=0) & best lag (samples) ---")
def best_lag(a, b, maxlag=20):
    cc = np.correlate(a - a.mean(), b - b.mean(), mode="full")
    mid = len(a) - 1
    win = cc[mid - maxlag: mid + maxlag + 1]
    return np.argmax(win) - maxlag
if y.shape[1] >= 4:
    pairs = [(0, 2), (1, 3), (0, 1)]  # +x/-x, +y/-y, +x/+y
    for a, b in pairs:
        r = np.corrcoef(y[:, a], y[:, b])[0, 1]
        lag = best_lag(y[:, a], y[:, b])
        print(f"  ch{a}-ch{b}: corr={r:+.4f}  best_lag={lag:+d} samp")
print("\n(差が出ていれば空間情報あり=FOA化の見込みあり)")
