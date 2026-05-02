"""
sound.py の動作確認デモ
合成データを使って特徴量抽出・モデル構築・学習・推論を実際に実行する
"""

import os
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import numpy as np
import tempfile
import wave

# sound.py のすべての関数を読み込む
from sound import (
    melspectrogram_feature_extract,
    build_baseline_sed,
    build_baseline_sad,
    build_sed_sad_joint,
    model_train_sed,
    model_train_joint,
    sed_sad_aggregation,
    prob_to_onehot,
)

print("=" * 60)
print("STEP 1: 合成音声ファイルの生成")
print("=" * 60)

# WAV ファイルを一時ディレクトリに作成
tmpdir = tempfile.mkdtemp()
wav_paths = []
n_samples_audio = 5
fs = 44100
duration_sec = 10

for i in range(n_samples_audio):
    wav_path = os.path.join(tmpdir, f'sample_{i:03d}.wav')
    # ランダムノイズ + 正弦波ミックス（多重音響のシミュレーション）
    t = np.linspace(0, duration_sec, fs * duration_sec)
    signal = (
        0.3 * np.sin(2 * np.pi * 440 * t) +   # 440 Hz
        0.2 * np.sin(2 * np.pi * 880 * t) +   # 880 Hz
        0.1 * np.random.randn(len(t))          # ノイズ
    )
    signal = (signal * 32767).astype(np.int16)
    with wave.open(wav_path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(fs)
        wf.writeframes(signal.tobytes())
    wav_paths.append(f'sample_{i:03d}.wav')

print(f"  {n_samples_audio} 個の WAV ファイルを生成: {tmpdir}")

print()
print("=" * 60)
print("STEP 2: メルスペクトログラム特徴量の抽出")
print("=" * 60)

features = melspectrogram_feature_extract(
    datapath=tmpdir,
    filename=wav_paths,
    n_fft=2048,
    hop_length=882,
    win_length=1764,
    n_mels=40,
    fps=50,
    duration=10
)
features = np.reshape(features, (len(features), 40, 500, 1))
print(f"  特徴量 shape: {features.shape}")
print(f"  値の範囲: [{features.min():.3f}, {features.max():.3f}]")

# ダミーラベルを生成（NB_CLASSES=10 のマルチラベル、500 フレーム）
NB_CLASSES = 10
FRAMES = 500

def make_sed_label(n_samples):
    """各フレームで各クラスが 0/1 のランダムラベル"""
    return np.random.randint(0, 2, (n_samples, FRAMES, NB_CLASSES)).astype(np.float32)

def make_sad_label(n_samples):
    """各フレームで音活動が 0/1 のランダムラベル"""
    return np.random.randint(0, 2, (n_samples, FRAMES, 1)).astype(np.float32)

# 学習 / 検証 データを用意（合成）
n_train = 4
n_val   = 1
X_train     = features[:n_train]
X_val       = features[n_train:]
Y_train_SED = make_sed_label(n_train)
Y_val_SED   = make_sed_label(n_val)
Y_train_SAD = make_sad_label(n_train)
Y_val_SAD   = make_sad_label(n_val)

print(f"  学習: X={X_train.shape}, Y_SED={Y_train_SED.shape}, Y_SAD={Y_train_SAD.shape}")
print(f"  検証: X={X_val.shape}, Y_SED={Y_val_SED.shape}")

print()
print("=" * 60)
print("STEP 3: ベースライン SED モデルの構築と学習 (3 epoch)")
print("=" * 60)

sed_model = build_baseline_sed()
model_train_sed(
    sed_model, X_train, Y_train_SED, X_val, Y_val_SED,
    epochs=3, batch_size=2,
    model_name='demo_baseline_SED', output_folder='./demo_models'
)
print("  SED モデルの学習完了")

print()
print("=" * 60)
print("STEP 4: ベースライン SAD モデルの構築と学習 (3 epoch)")
print("=" * 60)

sad_model = build_baseline_sad()
model_train_sed(
    sad_model, X_train, Y_train_SAD, X_val, Y_val_SAD,
    epochs=3, batch_size=2,
    model_name='demo_baseline_SAD', output_folder='./demo_models'
)
print("  SAD モデルの学習完了")

print()
print("=" * 60)
print("STEP 5: SED+SAD ジョイントモデルの構築と学習 (3 epoch)")
print("=" * 60)

joint_model = build_sed_sad_joint()
model_train_joint(
    joint_model,
    X_train, Y_train_SED, Y_train_SAD,
    X_val, Y_val_SED, Y_val_SAD,
    epochs=3, batch_size=2,
    model_name='demo_sed_sad_joint', output_folder='./demo_models'
)
print("  ジョイントモデルの学習完了")

print()
print("=" * 60)
print("STEP 6: 推論と後処理")
print("=" * 60)

# ジョイントモデルで SED / SAD を個別に推論
from tensorflow.keras.models import Model

model_sed_infer = Model(
    inputs=joint_model.input,
    outputs=joint_model.get_layer('sl_out').output
)
model_sad_infer = Model(
    inputs=joint_model.input,
    outputs=joint_model.get_layer('pa_out').output
)

sed_preds = []
sad_preds = []
for i in range(len(X_val)):
    x = np.reshape(X_val[i], (1, 40, 500, 1))
    sed_preds.append(model_sed_infer.predict(x, verbose=0))
    sad_preds.append(model_sad_infer.predict(x, verbose=0))

sed_preds = np.reshape(np.array(sed_preds), (len(sed_preds), 500, 10))
sad_preds = np.reshape(np.array(sad_preds), (len(sad_preds), 500))

print(f"  SED 予測 shape: {sed_preds.shape}")
print(f"  SAD 予測 shape: {sad_preds.shape}")

# SED × SAD の要素積で統合
final_pred = sed_sad_aggregation(sed_preds, sad_preds)
print(f"  統合後 shape: {final_pred.shape}")

# 確率 → 0/1 変換
sed_onehot = prob_to_onehot(final_pred, threshold=0.2)
sad_onehot = prob_to_onehot(list(sad_preds), threshold=0.5)
print(f"  SED one-hot サンプル[0][0]: {sed_onehot[0][0]}")
print(f"  SAD one-hot サンプル[0][0]: {sad_onehot[0][0]}")

print()
print("=" * 60)
print("全ステップ完了!")
print("=" * 60)

# クリーンアップ
import shutil
shutil.rmtree(tmpdir)
