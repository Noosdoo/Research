"""
Polyphonic Sound Event and Sound Activity Detection
参考: https://github.com/arjunp17/POLYPHONIC-SOUND-EVENT-AND-SOUND-ACTIVITY-DETECTION

WASPAA 2019 論文実装
- Sound Event Detection (SED): 各フレームでどの音イベントが発生しているか検出
- Sound Activity Detection (SAD): 各フレームで何らかの音イベントがあるか検出
- 両タスクを同時に学習するジョイントモデル
"""

import os
import numpy as np
import scipy.io as sio
from scipy.io import wavfile
import librosa
import soundfile as sf

import tensorflow as tf
from tensorflow.keras.models import Model, load_model
from tensorflow.keras.layers import (
    Input, Dense, Dropout, Reshape, Permute,
    Conv2D, MaxPooling2D, BatchNormalization,
    GRU, TimeDistributed
)
from tensorflow.keras.callbacks import ModelCheckpoint
from tensorflow.keras.optimizers import Adam
from sklearn.utils import shuffle
from sklearn.model_selection import train_test_split


# ==============================================================================
# 1. 特徴量抽出 (feature_extraction/feature_extract.py)
# ==============================================================================

# データセットのパス
TRAIN_DATA_PATH = '../audio/train'
VALIDATION_DATA_PATH = '../audio/validate'
TEST_DATA_PATH = '../audio/test'


def load_filenames(train_txt='../train_wav.txt',
                   val_txt='../validation_wav.txt',
                   test_txt='../test_wav.txt'):
    """ファイル名リストをテキストファイルから読み込む"""
    train_filenames = np.loadtxt(train_txt, dtype='str')
    val_filenames = np.loadtxt(val_txt, dtype='str')
    test_filenames = np.loadtxt(test_txt, dtype='str')
    return train_filenames, val_filenames, test_filenames


def melspectrogram_feature_extract(datapath, filename, n_fft=2048,
                                   hop_length=882, win_length=1764,
                                   n_mels=40, fps=50, duration=10):
    """
    メルスペクトログラム特徴量を抽出する

    Args:
        datapath: 音声ファイルが格納されたディレクトリパス
        filename: ファイル名の配列
        n_fft: FFTウィンドウサイズ
        hop_length: ホップ長 (882 = 50fps @ 44100Hz)
        win_length: ウィンドウ長
        n_mels: メルフィルタバンク数
        fps: フレームレート
        duration: 音声の長さ（秒）

    Returns:
        特徴量のリスト (shape: [n_samples, n_mels, fps*duration, 1])
    """
    feature = []
    for i in range(len(filename)):
        [fs, x] = wavfile.read(os.path.join(datapath, filename[i]))
        x = np.array(x, dtype='float')

        # STFT → パワースペクトル → メルスペクトログラム
        D = librosa.stft(x, n_fft=n_fft, hop_length=hop_length,
                         win_length=win_length,
                         window='hamming')
        D = np.abs(D) ** 2
        S = librosa.feature.melspectrogram(S=D, n_mels=n_mels)
        S = librosa.power_to_db(S, ref=np.max)

        # 正規化: [0, 1] に変換
        normS = S - np.amin(S)
        normS = normS / float(np.amax(normS))

        # フレーム数を fps*duration に合わせる（ゼロパディングまたはトリミング）
        target_frames = fps * duration
        if int(normS.shape[1]) < target_frames:
            z_pad = np.zeros((n_mels, target_frames))
            z_pad[:, :-(target_frames - normS.shape[1])] = normS
            feature.append(z_pad)
        else:
            feat = normS[:, :target_frames]
            feature.append(feat)

    return feature


def extract_and_save_features(train_path, val_path, test_path,
                               train_filenames, val_filenames, test_filenames):
    """特徴量を抽出して .npy ファイルに保存する"""
    print("学習データの特徴量を抽出中...")
    train_feature = melspectrogram_feature_extract(
        train_path, train_filenames, 2048, 882, 882 * 2, 40, 50, 10
    )
    train_feature = np.reshape(train_feature, (len(train_feature), 40, 500, 1))
    np.save('urban_SED_train_feature', train_feature)

    print("検証データの特徴量を抽出中...")
    val_feature = melspectrogram_feature_extract(
        val_path, val_filenames, 2048, 882, 882 * 2, 40, 50, 10
    )
    val_feature = np.reshape(val_feature, (len(val_feature), 40, 500, 1))
    np.save('urban_SED_val_feature', val_feature)

    print("テストデータの特徴量を抽出中...")
    test_feature = melspectrogram_feature_extract(
        test_path, test_filenames, 2048, 882, 882 * 2, 40, 50, 10
    )
    test_feature = np.reshape(test_feature, (len(test_feature), 40, 500, 1))
    np.save('urban_SED_test_feature', test_feature)

    print("特徴量の保存完了")
    return train_feature, val_feature, test_feature


# ==============================================================================
# 2. ベースライン SED モデル (training/baselineSED.py)
# ==============================================================================

# 入力次元
ROWS, COLS, CHANNELS = 40, 500, 1

# モデルパラメータ
EPOCHS = 200
BATCH_SIZE = 32
NB_CLASSES = 10
LR = 0.001


def build_baseline_sed(rows=ROWS, cols=COLS, channels=CHANNELS,
                       nb_classes=NB_CLASSES, lr=LR):
    """
    ベースライン Sound Event Detection (SED) モデルを構築する

    アーキテクチャ:
        Conv2D x3 (+ BatchNorm + Dropout) → MaxPooling → Reshape → GRU → TimeDistributed Dense

    Returns:
        コンパイル済み Keras モデル
    """
    inp = Input(shape=(rows, cols, channels))

    # conv1
    x = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(inp)
    x = BatchNormalization(axis=-1)(x)
    x = Dropout(0.30)(x)
    x = MaxPooling2D(pool_size=(5, 1), strides=(5, 1))(x)

    # conv2
    x = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(x)
    x = BatchNormalization(axis=-1)(x)
    x = Dropout(0.30)(x)
    x = MaxPooling2D(pool_size=(4, 1), strides=(4, 1))(x)

    # conv3
    x = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(x)
    x = BatchNormalization(axis=-1)(x)
    x = Dropout(0.30)(x)
    x = MaxPooling2D(pool_size=(2, 1), strides=(2, 1))(x)

    # Reshape → GRU 用に時系列に変換
    x = Reshape((64, -1))(x)
    x = Permute((2, 1))(x)

    # GRU
    x = GRU(64, activation='tanh', return_sequences=True)(x)

    # 出力: 各フレームでクラスごとの確率
    sed_out = TimeDistributed(
        Dense(nb_classes, activation='sigmoid'), name='sed_out'
    )(x)

    model = Model(inp, sed_out, name='baselineSED')
    opt = Adam(learning_rate=lr)
    model.compile(loss='binary_crossentropy', optimizer=opt, metrics=['accuracy'])
    model.summary()
    return model


# ==============================================================================
# 3. ベースライン SAD モデル (training/baselineSAD.py)
# ==============================================================================

def build_baseline_sad(rows=ROWS, cols=COLS, channels=CHANNELS,
                       nb_classes=NB_CLASSES, lr=LR):
    """
    ベースライン Sound Activity Detection (SAD) モデルを構築する

    アーキテクチャ:
        Conv2D x3 (+ BatchNorm + Dropout) → MaxPooling → Reshape → GRU
        → TimeDistributed Dense(nb_classes) → TimeDistributed Dense(1)

    Returns:
        コンパイル済み Keras モデル
    """
    inp = Input(shape=(rows, cols, channels))

    # conv1
    x = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(inp)
    x = BatchNormalization(axis=-1)(x)
    x = Dropout(0.30)(x)
    x = MaxPooling2D(pool_size=(5, 1), strides=(5, 1))(x)

    # conv2
    x = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(x)
    x = BatchNormalization(axis=-1)(x)
    x = Dropout(0.30)(x)
    x = MaxPooling2D(pool_size=(4, 1), strides=(4, 1))(x)

    # conv3
    x = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(x)
    x = BatchNormalization(axis=-1)(x)
    x = Dropout(0.30)(x)
    x = MaxPooling2D(pool_size=(2, 1), strides=(2, 1))(x)

    # Reshape → GRU 用に時系列に変換
    x = Reshape((64, -1))(x)
    x = Permute((2, 1))(x)

    # GRU
    x = GRU(64, activation='tanh', return_sequences=True)(x)

    # 中間 Dense → 最終出力: 各フレームで音活動の確率 (スカラー)
    x = TimeDistributed(Dense(nb_classes, activation='sigmoid'))(x)
    sad_out = TimeDistributed(
        Dense(1, activation='sigmoid'), name='sad_out'
    )(x)

    model = Model(inp, sad_out, name='baselineSAD')
    opt = Adam(learning_rate=lr)
    model.compile(loss='binary_crossentropy', optimizer=opt, metrics=['accuracy'])
    model.summary()
    return model


# ==============================================================================
# 4. SED + SAD ジョイントモデル (training/sed_sad_joint.py)
# ==============================================================================

def build_sed_sad_joint(rows=ROWS, cols=COLS, channels=CHANNELS,
                        nb_classes=NB_CLASSES, lr=LR,
                        sed_loss_weight=0.5, sad_loss_weight=0.5):
    """
    SED と SAD を同時に学習するジョイントモデルを構築する

    アーキテクチャ:
        共有ブランチ (Conv2D x2) → SED ブランチ / SAD ブランチ に分岐

    Args:
        sed_loss_weight: SED の損失に対する重み
        sad_loss_weight: SAD の損失に対する重み

    Returns:
        コンパイル済み Keras マルチ出力モデル
    """
    inp = Input(shape=(rows, cols, channels))

    # ---- 共有ブランチ ----
    # conv1
    x = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(inp)
    x = BatchNormalization(axis=-1)(x)
    x = Dropout(0.30)(x)
    x = MaxPooling2D(pool_size=(5, 1), strides=(5, 1))(x)

    # conv2
    x = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(x)
    x = BatchNormalization(axis=-1)(x)
    x = Dropout(0.30)(x)
    shared = MaxPooling2D(pool_size=(4, 1), strides=(4, 1))(x)

    # ---- SED ブランチ ----
    sl = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(shared)
    sl = BatchNormalization(axis=-1)(sl)
    sl = Dropout(0.30)(sl)
    sl = MaxPooling2D(pool_size=(2, 1), strides=(2, 1))(sl)
    sl = Reshape((64, -1))(sl)
    sl = Permute((2, 1))(sl)
    sl = GRU(64, activation='tanh', return_sequences=True)(sl)
    sl_out = TimeDistributed(
        Dense(nb_classes, activation='sigmoid'), name='sl_out'
    )(sl)

    # ---- SAD ブランチ ----
    pa = Conv2D(64, (5, 5), strides=(1, 1), activation='relu', padding='same')(shared)
    pa = BatchNormalization(axis=-1)(pa)
    pa = Dropout(0.30)(pa)
    pa = MaxPooling2D(pool_size=(2, 1), strides=(2, 1))(pa)
    pa = Reshape((64, -1))(pa)
    pa = Permute((2, 1))(pa)
    pa = GRU(64, activation='tanh', return_sequences=True)(pa)
    pa = TimeDistributed(Dense(nb_classes, activation='sigmoid'))(pa)
    pa_out = TimeDistributed(
        Dense(1, activation='sigmoid'), name='pa_out'
    )(pa)

    model = Model(inp, outputs=[sl_out, pa_out], name='sed_sad_joint')
    opt = Adam(learning_rate=lr)
    losses = {
        'sl_out': 'binary_crossentropy',
        'pa_out': 'binary_crossentropy'
    }
    loss_weights = {
        'sl_out': sed_loss_weight,
        'pa_out': sad_loss_weight
    }
    model.compile(loss=losses, loss_weights=loss_weights,
                  optimizer=opt,
                  metrics={'sl_out': 'accuracy', 'pa_out': 'accuracy'})
    model.summary()
    return model


# ==============================================================================
# 5. 学習共通関数
# ==============================================================================

def model_train_sed(model, X_train, Y_train, X_val, Y_val,
                    epochs=EPOCHS, batch_size=BATCH_SIZE,
                    model_name='baseline_SED', output_folder='./models'):
    """
    SED (または SAD) 単一出力モデルを学習する

    Args:
        model: Keras モデル
        model_name: 保存するモデルファイルのベース名
        output_folder: モデルを保存するディレクトリ

    Returns:
        学習履歴 (History オブジェクト)
    """
    os.makedirs(output_folder, exist_ok=True)
    filepath = os.path.join(
        output_folder, model_name + '-{epoch:02d}-{val_loss:.2f}.keras'
    )
    checkpoint = ModelCheckpoint(
        filepath, monitor='val_loss', verbose=2,
        save_best_only=True, mode='min'
    )
    hist = model.fit(
        X_train, Y_train,
        validation_data=(X_val, Y_val),
        callbacks=[checkpoint],
        epochs=epochs,
        shuffle=False,
        batch_size=batch_size,
        verbose=2
    )
    return hist


def model_train_joint(model, X_train, Y_train_SED, Y_train_SAD,
                      X_val, Y_val_SED, Y_val_SAD,
                      epochs=EPOCHS, batch_size=BATCH_SIZE,
                      model_name='sed_sad_joint', output_folder='./models'):
    """
    SED + SAD ジョイントモデルを学習する

    Returns:
        学習履歴 (History オブジェクト)
    """
    os.makedirs(output_folder, exist_ok=True)
    filepath = os.path.join(
        output_folder,
        model_name + '-{epoch:02d}-{val_sl_out_loss:.2f}.keras'
    )
    checkpoint = ModelCheckpoint(
        filepath, monitor='val_loss', verbose=2,
        save_best_only=True, mode='min'
    )
    hist = model.fit(
        X_train,
        {'sl_out': Y_train_SED, 'pa_out': Y_train_SAD},
        validation_data=(X_val, {'sl_out': Y_val_SED, 'pa_out': Y_val_SAD}),
        callbacks=[checkpoint],
        epochs=epochs,
        shuffle=False,
        batch_size=batch_size,
        verbose=2
    )
    return hist


# ==============================================================================
# 6. 推論・後処理 (testing/model_output.py)
# ==============================================================================

def model_predict(model_path, sed_output_layer='sl_out', sad_output_layer='pa_out',
                  test_feature_path='../test_feature.npy'):
    """
    学習済みジョイントモデルで SED / SAD の予測を行う

    Args:
        model_path: .hdf5 モデルファイルのパス
        sed_output_layer: SED 出力レイヤー名
        sad_output_layer: SAD 出力レイヤー名
        test_feature_path: テスト特徴量 .npy ファイルのパス

    Returns:
        sed_pred: SED 予測値 (n_samples, 500, 10)
        sad_pred: SAD 予測値 (n_samples, 500)
    """
    base_model = load_model(model_path)
    base_model.summary()

    # 各タスクの出力レイヤーから個別モデルを作成
    model_sed = Model(
        inputs=base_model.input,
        outputs=base_model.get_layer(sed_output_layer).output
    )
    model_sad = Model(
        inputs=base_model.input,
        outputs=base_model.get_layer(sad_output_layer).output
    )

    test_feature = np.load(test_feature_path)

    sed_pred = []
    sad_pred = []
    for i in range(len(test_feature)):
        x = np.reshape(test_feature[i], (1, 40, 500, 1))
        sed_pred.append(model_sed.predict(x))
        sad_pred.append(model_sad.predict(x))

    sed_pred = np.array(sed_pred)
    sed_pred = np.reshape(sed_pred, (len(sed_pred), 500, 10))

    sad_pred = np.array(sad_pred)
    sad_pred = np.reshape(sad_pred, (len(sad_pred), 500))

    return sed_pred, sad_pred


def sed_sad_aggregation(sed_pred, sad_pred):
    """
    SED と SAD の予測を要素積で統合する

    各クラスの SED 確率に SAD 確率を掛け合わせることで
    偽陽性・偽陰性を抑制する。

    Args:
        sed_pred: SED 予測値 (n_samples, frames, nb_classes)
        sad_pred: SAD 予測値 (n_samples, frames)

    Returns:
        統合後の特徴量 (n_samples, frames, nb_classes)
    """
    agg_feature = []
    for i in range(len(sed_pred)):
        agg_vec = []
        present_feature_sed = sed_pred[i]   # (frames, nb_classes)
        present_feature_sad = sad_pred[i]   # (frames,)
        for j in range(present_feature_sed.shape[1]):
            agg_vec.append(present_feature_sed[:, j] * present_feature_sad)
        agg_vec = np.array(agg_vec).T       # (frames, nb_classes)
        agg_feature.append(agg_vec)

    return np.array(agg_feature)


def prob_to_onehot(model_prediction, threshold=0.2):
    """
    確率値を 0/1 の one-hot 表現に変換する

    Args:
        model_prediction: 予測確率の配列
        threshold: 閾値 (SED: 0.2, SAD: 0.5 を推奨)

    Returns:
        二値化された予測の配列
    """
    onehot_pred = []
    for i in range(len(model_prediction)):
        present_sample = model_prediction[i].copy()
        present_sample[present_sample >= threshold] = 1
        present_sample[present_sample < threshold] = 0
        onehot_pred.append(present_sample)
    return onehot_pred


# ==============================================================================
# 7. 評価 (evaluation/sed_eval.py)
# ==============================================================================

def evaluate_sed(ref_path, est_path, pair_file,
                 time_resolution=1.0, t_collar=0.250):
    """
    SED の評価指標を計算する (sed_eval ライブラリを使用)

    Args:
        ref_path: 正解アノテーションディレクトリ
        est_path: 予測アノテーションディレクトリ
        pair_file: ファイルペアリスト (タブ区切り)
        time_resolution: セグメントベース評価の時間分解能 (秒)
        t_collar: イベントベース評価の時間許容誤差 (秒)
    """
    try:
        import sed_eval
        import dcase_util
    except ImportError:
        print("sed_eval または dcase_util がインストールされていません。")
        print("pip install sed_eval dcase_util でインストールしてください。")
        return

    # ファイルペアの読み込み
    file_list = []
    with open(pair_file, 'r') as pf:
        for line in pf.readlines():
            parts = line.strip().split('\t')
            file_list.append({
                'reference_file': os.path.join(ref_path, parts[0]),
                'estimated_file': os.path.join(est_path, parts[1])
            })

    data = []
    all_data = dcase_util.containers.MetaDataContainer()
    for file_pair in file_list:
        reference_event_list = sed_eval.io.load_event_list(
            filename=file_pair['reference_file']
        )
        estimated_event_list = sed_eval.io.load_event_list(
            filename=file_pair['estimated_file']
        )
        data.append({
            'reference_event_list': reference_event_list,
            'estimated_event_list': estimated_event_list
        })
        all_data += reference_event_list

    print(f"評価ファイル数: {len(data)}")
    event_labels = all_data.unique_event_labels
    print(f"イベントラベル: {event_labels}")

    # セグメントベース評価
    seg_metrics = sed_eval.sound_event.SegmentBasedMetrics(
        event_label_list=event_labels,
        time_resolution=time_resolution
    )
    for file_pair in data:
        seg_metrics.evaluate(
            reference_event_list=file_pair['reference_event_list'],
            estimated_event_list=file_pair['estimated_event_list']
        )
    print("\n=== セグメントベース評価 ===")
    print(seg_metrics)

    # イベントベース評価
    evt_metrics = sed_eval.sound_event.EventBasedMetrics(
        event_label_list=event_labels,
        t_collar=t_collar,
        evaluate_onset=True,
        evaluate_offset=False
    )
    for file_pair in data:
        evt_metrics.evaluate(
            reference_event_list=file_pair['reference_event_list'],
            estimated_event_list=file_pair['estimated_event_list']
        )
    print("\n=== イベントベース評価 ===")
    print(evt_metrics)


# ==============================================================================
# 8. メイン処理
# ==============================================================================

if __name__ == '__main__':

    OUTPUT_FOLDER = './models'

    # ---- (A) 特徴量抽出 ----
    # 事前に音声ファイルと txt リストを用意してから実行する
    # train_fns, val_fns, test_fns = load_filenames()
    # extract_and_save_features(
    #     TRAIN_DATA_PATH, VALIDATION_DATA_PATH, TEST_DATA_PATH,
    #     train_fns, val_fns, test_fns
    # )

    # ---- (B) データ読み込み ----
    X_train     = np.load('../train_feature.npy')
    X_val       = np.load('../val_feature.npy')
    Y_train_SED = np.load('../train_label_SED.npy')
    Y_val_SED   = np.load('../val_label_SED.npy')
    Y_train_SAD = np.load('../train_label_SAD.npy')
    Y_val_SAD   = np.load('../val_label_SAD.npy')

    # ---- (C) ベースライン SED の学習 ----
    baseline_sed = build_baseline_sed()
    model_train_sed(
        baseline_sed, X_train, Y_train_SED, X_val, Y_val_SED,
        model_name='baseline_SED', output_folder=OUTPUT_FOLDER
    )

    # ---- (D) ベースライン SAD の学習 ----
    baseline_sad = build_baseline_sad()
    model_train_sed(
        baseline_sad, X_train, Y_train_SAD, X_val, Y_val_SAD,
        model_name='baseline_SAD', output_folder=OUTPUT_FOLDER
    )

    # ---- (E) ジョイントモデルの学習 ----
    joint_model = build_sed_sad_joint()
    model_train_joint(
        joint_model, X_train, Y_train_SED, Y_train_SAD,
        X_val, Y_val_SED, Y_val_SAD,
        model_name='sed_sad_joint', output_folder=OUTPUT_FOLDER
    )

    # ---- (F) 推論・後処理 ----
    sed_pred, sad_pred = model_predict(
        model_path='sed_sad_joint_model.keras',
        sed_output_layer='sl_out',
        sad_output_layer='pa_out',
        test_feature_path='../test_feature.npy'
    )

    # SED × SAD の要素積で統合
    final_sed_pred = sed_sad_aggregation(sed_pred, sad_pred)

    # 確率 → 0/1 変換 (SED 閾値: 0.2, SAD 閾値: 0.5 が推奨値)
    final_sed_onehot = prob_to_onehot(final_sed_pred, threshold=0.2)
    sad_onehot       = prob_to_onehot(list(sad_pred), threshold=0.5)

    # ---- (G) 評価 ----
    evaluate_sed(
        ref_path='../annotations/test',
        est_path='../annotations/predict',
        pair_file='../file_list_sed_eval'
    )
