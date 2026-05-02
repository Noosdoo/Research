"""
スマホ音声による簡易 SED (Sound Event Detection) 評価スクリプト
=================================================================
スマホはモノラル/ステレオ収録のため、方向推定(DOA)はできません。
このスクリプトでは「いつ・どの音が鳴っているか」を検出します。

【使い方】
  # スマホから転送したWAVで推論
  python smartphone_eval.py --audio recording.wav

  # ディレクトリ内の全WAVをまとめて処理
  python smartphone_eval.py --audio_dir ./phone_recordings

  # ラベルCSVがある場合は評価指標も計算
  python smartphone_eval.py --audio recording.wav --label label.csv

  # デモ (合成音で動作確認)
  python smartphone_eval.py --demo

【ラベルCSVフォーマット (オプション)】
  onset_sec, offset_sec, class_name (またはclass_idx)
  0.5, 2.3, car
  3.1, 5.8, bird

【対応クラス】
  CFG["class_names"] を自分のデータに合わせて変更してください。
"""

import os
import math
import glob
import argparse
import warnings
import numpy as np
import librosa
import soundfile as sf
import torch
import torch.nn as nn
import torch.nn.functional as F
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

warnings.filterwarnings("ignore")

# =============================================================================
# 設定
# =============================================================================

CFG = {
    # --- 音クラス (自分のデータに合わせて変更) ---
    "class_names": [
        "car", "bird", "wind", "rain",
        "footstep", "voice", "dog", "insect",
    ],

    # --- 音響特徴量 ---
    "fs":          22050,   # スマホ音声に合わせた SR
    "n_fft":       1024,
    "hop_length":  512,
    "n_mels":      64,

    # --- セグメント ---
    "seg_duration": 2.0,    # 推論単位 (秒)  短いほど検出が細かい
    "overlap":      0.5,    # セグメント間オーバーラップ率

    # --- 推論 ---
    "threshold":    0.4,    # イベント検出の確率閾値
    "device":      "cuda" if torch.cuda.is_available() else "cpu",

    # --- 出力 ---
    "output_dir":  "./output_smartphone",
}
CFG["n_classes"] = len(CFG["class_names"])
CFG["n_frames"]  = int(CFG["seg_duration"] * CFG["fs"] / CFG["hop_length"]) + 1

# =============================================================================
# 特徴量抽出 (モノラル/ステレオ対応)
# =============================================================================

def load_audio(path, target_sr):
    """スマホWAV読み込み。モノラル変換とリサンプルを自動処理。"""
    audio, sr = sf.read(path, always_2d=True)
    audio = audio.mean(axis=1)          # ステレオ→モノラル
    if sr != target_sr:
        audio = librosa.resample(audio.astype(np.float32),
                                 orig_sr=sr, target_sr=target_sr)
    return audio.astype(np.float32)


def extract_mel(audio, cfg):
    """モノラル音声 → メルスペクトログラム (n_mels, T)"""
    mel = librosa.feature.melspectrogram(
        y=audio, sr=cfg["fs"],
        n_fft=cfg["n_fft"], hop_length=cfg["hop_length"],
        n_mels=cfg["n_mels"], fmax=cfg["fs"] // 2
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)
    # 正規化 [0, 1]
    mel_db = (mel_db - mel_db.min()) / (mel_db.max() - mel_db.min() + 1e-8)
    return mel_db.astype(np.float32)


def make_segments(audio, cfg):
    """
    音声をオーバーラップありのセグメントに分割。
    Returns: list of (mel, time_offset_sec)
    """
    fs        = cfg["fs"]
    seg_len   = int(cfg["seg_duration"] * fs)
    hop_len   = int(seg_len * (1 - cfg["overlap"]))
    n_frames  = cfg["n_frames"]

    segments = []
    pos = 0
    while pos < len(audio):
        chunk = audio[pos: pos + seg_len]
        if len(chunk) < seg_len:
            chunk = np.pad(chunk, (0, seg_len - len(chunk)))
        mel = extract_mel(chunk, cfg)
        # フレーム数を揃える
        if mel.shape[1] < n_frames:
            mel = np.pad(mel, ((0, 0), (0, n_frames - mel.shape[1])))
        else:
            mel = mel[:, :n_frames]
        time_offset = pos / fs
        segments.append((mel, time_offset))
        pos += hop_len

    return segments

# =============================================================================
# モデル: 軽量 CNN + Transformer (スマホ音声向け)
# =============================================================================

class SmartphoneSED(nn.Module):
    """
    軽量 SED モデル。
    入力: (B, 1, n_mels, T)
    出力: (B, T, n_classes)  各フレームの音イベント確率
    """

    def __init__(self, n_mels, n_frames, n_classes, dropout=0.3):
        super().__init__()

        # CNN ブロック (周波数方向の特徴抽出)
        self.cnn = nn.Sequential(
            nn.Conv2d(1, 32, (3, 3), padding=1), nn.BatchNorm2d(32), nn.ReLU(),
            nn.MaxPool2d((2, 1)),                 # n_mels/2

            nn.Conv2d(32, 64, (3, 3), padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool2d((2, 1)),                 # n_mels/4

            nn.Conv2d(64, 128, (3, 3), padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            nn.MaxPool2d((2, 1)),                 # n_mels/8

            nn.Dropout2d(dropout),
        )

        # CNN出力の周波数次元
        freq_out = n_mels // 8
        self.proj = nn.Linear(128 * freq_out, 128)

        # Transformer (時間方向の依存関係)
        enc_layer = nn.TransformerEncoderLayer(
            d_model=128, nhead=4, dim_feedforward=256,
            dropout=dropout, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(enc_layer, num_layers=2)

        # 出力
        self.fc = nn.Linear(128, n_classes)

    def forward(self, x):
        # x: (B, 1, n_mels, T)
        x = self.cnn(x)                   # (B, 128, n_mels/8, T)
        B, C, Fq, T = x.shape
        x = x.permute(0, 3, 1, 2)         # (B, T, C, Fq)
        x = x.reshape(B, T, C * Fq)       # (B, T, C*Fq)
        x = F.relu(self.proj(x))          # (B, T, 128)
        x = self.transformer(x)           # (B, T, 128)
        x = torch.sigmoid(self.fc(x))     # (B, T, n_classes)
        return x


# =============================================================================
# 学習
# =============================================================================

class SimpleAudioDataset(torch.utils.data.Dataset):
    def __init__(self, audio_dir, label_dir, cfg, augment=False):
        self.cfg = cfg
        self.augment = augment
        self.samples = []  # (mel, label_vec, fname)

        audio_paths = sorted(
            glob.glob(os.path.join(audio_dir, "*.wav")) +
            glob.glob(os.path.join(audio_dir, "*.WAV")) +
            glob.glob(os.path.join(audio_dir, "*.m4a"))
        )
        print(f"[Dataset] {len(audio_paths)} ファイルを処理中...")

        for ap in audio_paths:
            audio = load_audio(ap, cfg["fs"])
            segs  = make_segments(audio, cfg)
            base  = os.path.splitext(os.path.basename(ap))[0]

            # ラベル読み込み
            csv_p = os.path.join(label_dir, base + ".csv") if label_dir else None
            events = _load_label(csv_p, cfg["class_names"]) if csv_p else []

            total_dur = len(audio) / cfg["fs"]
            for mel, t_off in segs:
                label = _events_to_label(events, t_off,
                                         t_off + cfg["seg_duration"],
                                         cfg["n_classes"])
                self.samples.append((mel, label, base))

        print(f"[Dataset] セグメント数: {len(self.samples)}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        mel, label, fname = self.samples[idx]
        if self.augment:
            mel = _augment(mel)
        x = torch.from_numpy(mel).unsqueeze(0)    # (1, n_mels, T)
        y = torch.tensor(label, dtype=torch.float32)
        return x, y, fname


def _load_label(csv_path, class_names):
    """CSV → [(onset, offset, class_idx), ...]"""
    if not os.path.exists(csv_path):
        return []
    events = []
    name2idx = {n: i for i, n in enumerate(class_names)}
    with open(csv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            onset, offset = float(parts[0]), float(parts[1])
            cls_raw = parts[2]
            try:
                cls = int(cls_raw)
            except ValueError:
                cls = name2idx.get(cls_raw, -1)
            if cls >= 0:
                events.append((onset, offset, cls))
    return events


def _events_to_label(events, seg_start, seg_end, n_classes):
    """セグメント内でアクティブなクラスを multi-hot ベクトルに変換"""
    label = np.zeros(n_classes, dtype=np.float32)
    for onset, offset, cls in events:
        if cls < n_classes and onset < seg_end and offset > seg_start:
            label[cls] = 1.0
    return label


def _augment(mel):
    """簡易データ拡張: 周波数マスク + 時間マスク"""
    mel = mel.copy()
    # 周波数マスク
    f = np.random.randint(0, 8)
    f0 = np.random.randint(0, mel.shape[0] - f + 1)
    mel[f0:f0 + f, :] = 0.0
    # 時間マスク
    t = np.random.randint(0, 10)
    t0 = np.random.randint(0, mel.shape[1] - t + 1)
    mel[:, t0:t0 + t] = 0.0
    return mel


def train_model(audio_dir, label_dir, cfg, epochs=50, lr=1e-3):
    os.makedirs(cfg["output_dir"], exist_ok=True)

    dataset = SimpleAudioDataset(audio_dir, label_dir, cfg, augment=True)
    loader  = torch.utils.data.DataLoader(
        dataset, batch_size=16, shuffle=True, num_workers=0
    )

    model = SmartphoneSED(cfg["n_mels"], cfg["n_frames"],
                          cfg["n_classes"]).to(cfg["device"])
    opt   = torch.optim.Adam(model.parameters(), lr=lr)

    print(f"\n[Train] エポック数: {epochs}, デバイス: {cfg['device']}")
    history = []
    for ep in range(epochs):
        model.train()
        ep_loss = 0.0
        for x, y, _ in loader:
            x, y = x.to(cfg["device"]), y.to(cfg["device"])
            pred = model(x)                       # (B, T, C)
            # セグメントレベルラベル: フレームに broadcast
            y_exp = y.unsqueeze(1).expand_as(pred)
            loss = F.binary_cross_entropy(pred, y_exp)
            opt.zero_grad(); loss.backward(); opt.step()
            ep_loss += loss.item()
        ep_loss /= len(loader)
        history.append(ep_loss)
        if (ep + 1) % 10 == 0:
            print(f"  Epoch {ep+1:3d}/{epochs} | loss={ep_loss:.4f}")

    model_path = os.path.join(cfg["output_dir"], "sed_smartphone.pt")
    torch.save(model.state_dict(), model_path)
    print(f"\n  モデル保存: {model_path}")

    # 学習曲線
    plt.figure(figsize=(6, 3))
    plt.plot(history); plt.title("Training Loss")
    plt.xlabel("Epoch"); plt.ylabel("BCE Loss"); plt.tight_layout()
    plt.savefig(os.path.join(cfg["output_dir"], "train_loss.png"))
    plt.close()

    return model


# =============================================================================
# 推論
# =============================================================================

@torch.no_grad()
def infer_audio(audio_path, model, cfg, label_path=None):
    """
    1つの音声ファイルを推論し、イベントリストと可視化を返す。

    Returns:
        events: [(onset_sec, offset_sec, class_name, prob), ...]
    """
    audio    = load_audio(audio_path, cfg["fs"])
    segments = make_segments(audio, cfg)
    total_dur = len(audio) / cfg["fs"]

    model.eval()
    all_probs = []   # [(t_offset, probs[T, C]), ...]

    for mel, t_off in segments:
        x = torch.from_numpy(mel).unsqueeze(0).unsqueeze(0)  # (1,1,M,T)
        x = x.to(cfg["device"])
        probs = model(x)[0].cpu().numpy()   # (T, C)
        all_probs.append((t_off, probs))

    # 時間軸に沿った確率マップを構成 (オーバーラップは平均)
    frame_dur   = cfg["hop_length"] / cfg["fs"]
    n_total_fr  = int(total_dur / frame_dur) + 1
    prob_map    = np.zeros((n_total_fr, cfg["n_classes"]), dtype=np.float32)
    count_map   = np.zeros(n_total_fr, dtype=np.float32)

    for t_off, probs in all_probs:
        fr_start = int(t_off / frame_dur)
        T = probs.shape[0]
        fr_end = min(fr_start + T, n_total_fr)
        L = fr_end - fr_start
        prob_map[fr_start:fr_end] += probs[:L]
        count_map[fr_start:fr_end] += 1.0

    valid = count_map > 0
    prob_map[valid] /= count_map[valid, None]

    # 確率マップ → イベントリスト (閾値処理 + ランレングス圧縮)
    events = _prob_to_events(prob_map, frame_dur,
                              cfg["threshold"], cfg["class_names"])

    # ラベル読み込み (評価用)
    ref_events = []
    if label_path and os.path.exists(label_path):
        raw = _load_label(label_path, cfg["class_names"])
        ref_events = [(o, f, cfg["class_names"][c])
                      for o, f, c in raw if c < cfg["n_classes"]]

    return prob_map, events, ref_events, total_dur


def _prob_to_events(prob_map, frame_dur, threshold, class_names):
    """確率マップ → [(onset, offset, class_name, avg_prob)]"""
    events = []
    for c, name in enumerate(class_names):
        active = prob_map[:, c] >= threshold
        in_event = False
        onset = 0.0
        probs_buf = []
        for fr, a in enumerate(active):
            t = fr * frame_dur
            if a and not in_event:
                in_event = True; onset = t; probs_buf = [prob_map[fr, c]]
            elif a and in_event:
                probs_buf.append(prob_map[fr, c])
            elif not a and in_event:
                in_event = False
                events.append((onset, t, name, float(np.mean(probs_buf))))
                probs_buf = []
        if in_event:
            events.append((onset, len(active) * frame_dur, name,
                           float(np.mean(probs_buf))))
    events.sort(key=lambda e: e[0])
    return events


# =============================================================================
# 評価指標 (ラベルありの場合)
# =============================================================================

def compute_sed_metrics(pred_events, ref_events, total_dur,
                        class_names, collar=0.25):
    """
    イベントベース F1-score と Error Rate を計算。
    collar: onset/offset の許容誤差 (秒)
    """
    n_cls = len(class_names)
    TP = FP = FN = 0

    for cls in class_names:
        preds = [(o, f) for o, f, c, *_ in pred_events if c == cls]
        refs  = [(o, f) for o, f, c      in ref_events  if c == cls]

        matched = [False] * len(refs)
        for p_on, p_off in preds:
            hit = False
            for j, (r_on, r_off) in enumerate(refs):
                if not matched[j]:
                    if (abs(p_on - r_on) <= collar and
                            abs(p_off - r_off) <= collar):
                        matched[j] = True; hit = True; break
            if hit:
                TP += 1
            else:
                FP += 1
        FN += sum(1 for m in matched if not m)

    precision = TP / (TP + FP + 1e-8)
    recall    = TP / (TP + FN + 1e-8)
    F1        = 2 * precision * recall / (precision + recall + 1e-8)
    ER        = (FP + FN) / (TP + FN + 1e-8)

    return {"F1": F1, "ER": ER, "TP": TP, "FP": FP, "FN": FN}


# =============================================================================
# 可視化
# =============================================================================

def visualize(prob_map, pred_events, ref_events,
              total_dur, class_names, out_path, fname=""):
    """
    上段: メルスペクトログラム風確率マップ
    中段: 予測イベント (青)
    下段: 正解イベント (赤, ある場合)
    """
    has_ref  = len(ref_events) > 0
    n_rows   = 2 + has_ref
    fig, axes = plt.subplots(n_rows, 1,
                             figsize=(14, 3 * n_rows),
                             gridspec_kw={"height_ratios": [2] + [1] * (n_rows - 1)})

    frame_dur = total_dur / prob_map.shape[0]
    t_axis    = np.linspace(0, total_dur, prob_map.shape[0])

    # ① 確率マップ
    ax = axes[0]
    im = ax.imshow(prob_map.T, aspect="auto", origin="lower",
                   extent=[0, total_dur, -0.5, len(class_names) - 0.5],
                   cmap="YlOrRd", vmin=0, vmax=1)
    ax.set_yticks(range(len(class_names)))
    ax.set_yticklabels(class_names, fontsize=8)
    ax.set_title(f"SED 確率マップ: {fname}", fontsize=10)
    ax.set_xlabel("時間 (秒)")
    plt.colorbar(im, ax=ax, fraction=0.02)

    # ② 予測イベント
    _draw_events(axes[1], pred_events, class_names, total_dur,
                 color="steelblue", title="予測イベント")

    # ③ 正解イベント
    if has_ref:
        ref_fmt = [(o, f, c, 1.0) for o, f, c in ref_events]
        _draw_events(axes[2], ref_fmt, class_names, total_dur,
                     color="firebrick", title="正解イベント")

    plt.tight_layout()
    plt.savefig(out_path, dpi=110)
    plt.close()
    print(f"  可視化保存: {out_path}")


def _draw_events(ax, events, class_names, total_dur, color, title):
    n = len(class_names)
    ax.set_xlim(0, total_dur)
    ax.set_ylim(-0.5, n - 0.5)
    ax.set_yticks(range(n))
    ax.set_yticklabels(class_names, fontsize=8)
    ax.set_title(title, fontsize=9)
    ax.set_xlabel("時間 (秒)")
    ax.grid(axis="x", alpha=0.3)
    for ev in events:
        onset, offset, cls_name = ev[0], ev[1], ev[2]
        cls_idx = class_names.index(cls_name) if cls_name in class_names else -1
        if cls_idx >= 0:
            ax.barh(cls_idx, offset - onset, left=onset,
                    height=0.6, color=color, alpha=0.7)


# =============================================================================
# エントリポイント
# =============================================================================

def run_single(audio_path, label_path, cfg, model=None):
    """1ファイル推論・評価・可視化"""
    os.makedirs(cfg["output_dir"], exist_ok=True)

    if model is None:
        model_path = os.path.join(cfg["output_dir"], "sed_smartphone.pt")
        model = SmartphoneSED(cfg["n_mels"], cfg["n_frames"],
                              cfg["n_classes"])
        if os.path.exists(model_path):
            model.load_state_dict(
                torch.load(model_path, map_location=cfg["device"])
            )
            print(f"  モデル読み込み: {model_path}")
        else:
            print("  [警告] 学習済みモデルなし → ランダム重みで推論します")
        model = model.to(cfg["device"])

    prob_map, pred_events, ref_events, total_dur = \
        infer_audio(audio_path, model, cfg, label_path)

    base     = os.path.splitext(os.path.basename(audio_path))[0]
    out_fig  = os.path.join(cfg["output_dir"], base + "_result.png")
    out_csv  = os.path.join(cfg["output_dir"], base + "_events.csv")

    # CSV 出力
    with open(out_csv, "w") as f:
        f.write("onset_sec,offset_sec,class_name,probability\n")
        for onset, offset, cls, prob in pred_events:
            f.write(f"{onset:.3f},{offset:.3f},{cls},{prob:.3f}\n")
    print(f"  イベントCSV: {out_csv}")

    # コンソール出力
    print(f"\n  --- 検出イベント ({os.path.basename(audio_path)}) ---")
    if pred_events:
        for onset, offset, cls, prob in pred_events:
            print(f"  {onset:6.2f}s ~ {offset:6.2f}s  [{cls:<12}] prob={prob:.2f}")
    else:
        print("  (なし)")

    # 評価指標
    if ref_events:
        metrics = compute_sed_metrics(pred_events, ref_events,
                                      total_dur, cfg["class_names"])
        print(f"\n  --- 評価指標 ---")
        print(f"  F1-score   : {metrics['F1']:.4f}")
        print(f"  Error Rate : {metrics['ER']:.4f}")
        print(f"  TP/FP/FN   : {metrics['TP']} / {metrics['FP']} / {metrics['FN']}")

    # 可視化
    visualize(prob_map, pred_events, ref_events,
              total_dur, cfg["class_names"], out_fig,
              fname=os.path.basename(audio_path))

    return pred_events


def demo(cfg):
    """合成音で動作確認"""
    import tempfile

    print("=== デモモード: 合成音声で動作確認 ===")
    os.makedirs(cfg["output_dir"], exist_ok=True)
    os.makedirs(os.path.join(cfg["output_dir"], "demo_audio"), exist_ok=True)
    os.makedirs(os.path.join(cfg["output_dir"], "demo_labels"), exist_ok=True)

    fs = cfg["fs"]
    dur = 10.0
    t   = np.linspace(0, dur, int(dur * fs), endpoint=False)
    n_train = 3

    # 合成データ生成
    for i in range(n_train + 1):
        audio = np.random.randn(len(t)).astype(np.float32) * 0.05
        events_csv = []
        for _ in range(np.random.randint(2, 4)):
            onset  = np.random.uniform(0.5, dur * 0.7)
            offset = min(onset + np.random.uniform(1.0, 3.0), dur - 0.3)
            cls    = np.random.randint(0, cfg["n_classes"])
            freq   = 300 + cls * 150
            mask   = (t >= onset) & (t <= offset)
            audio[mask] += 0.4 * np.sin(2 * np.pi * freq * t[mask])
            events_csv.append(f"{onset:.3f},{offset:.3f},{cfg['class_names'][cls]}")

        tag = "test" if i == n_train else f"train_{i:02d}"
        wav_p = os.path.join(cfg["output_dir"], "demo_audio", f"{tag}.wav")
        csv_p = os.path.join(cfg["output_dir"], "demo_labels", f"{tag}.csv")
        sf.write(wav_p, audio, fs)
        with open(csv_p, "w") as f:
            f.write("\n".join(events_csv))

    # 学習
    cfg_demo = dict(cfg)
    model = train_model(
        os.path.join(cfg["output_dir"], "demo_audio"),
        os.path.join(cfg["output_dir"], "demo_labels"),
        cfg_demo, epochs=20
    )

    # テスト推論
    test_wav = os.path.join(cfg["output_dir"], "demo_audio", "test.wav")
    test_csv = os.path.join(cfg["output_dir"], "demo_labels", "test.csv")
    run_single(test_wav, test_csv, cfg, model)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="スマホ音声 簡易SED評価")
    parser.add_argument("--audio",      default=None, help="推論する音声ファイル")
    parser.add_argument("--audio_dir",  default=None, help="音声ディレクトリ (一括処理)")
    parser.add_argument("--label",      default=None, help="ラベルCSV (1ファイル)")
    parser.add_argument("--label_dir",  default=None, help="ラベルディレクトリ")
    parser.add_argument("--train",      action="store_true", help="学習モード")
    parser.add_argument("--epochs",     type=int, default=50)
    parser.add_argument("--threshold",  type=float, default=None)
    parser.add_argument("--demo",       action="store_true", help="デモ実行")
    args = parser.parse_args()

    if args.threshold:
        CFG["threshold"] = args.threshold

    os.makedirs(CFG["output_dir"], exist_ok=True)

    if args.demo:
        demo(CFG)

    elif args.train:
        if not args.audio_dir:
            print("--train 時は --audio_dir が必要です")
        else:
            train_model(args.audio_dir, args.label_dir, CFG, args.epochs)

    elif args.audio:
        run_single(args.audio, args.label, CFG)

    elif args.audio_dir:
        # ディレクトリ内の全 WAV を処理
        model_path = os.path.join(CFG["output_dir"], "sed_smartphone.pt")
        model = SmartphoneSED(CFG["n_mels"], CFG["n_frames"], CFG["n_classes"])
        if os.path.exists(model_path):
            model.load_state_dict(
                torch.load(model_path, map_location=CFG["device"])
            )
        model = model.to(CFG["device"])

        wav_files = sorted(
            glob.glob(os.path.join(args.audio_dir, "*.wav")) +
            glob.glob(os.path.join(args.audio_dir, "*.WAV"))
        )
        print(f"{len(wav_files)} ファイルを処理します")
        for wav_p in wav_files:
            base    = os.path.splitext(os.path.basename(wav_p))[0]
            csv_p   = None
            if args.label_dir:
                csv_p = os.path.join(args.label_dir, base + ".csv")
            print(f"\n[{base}]")
            run_single(wav_p, csv_p, CFG, model)
    else:
        print("引数が必要です。--demo で動作確認できます。")
        parser.print_help()
