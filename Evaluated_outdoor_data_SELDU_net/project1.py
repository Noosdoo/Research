"""
SELD U-Net 実野外データ評価スクリプト
論文: "SELD U-Net: Joint Optimization of Sound Event Localization and Detection
       With Noise Reduction" (IEEE Access, 2023)
参考: https://github.com/sharathadavanne/seld-net

【動作モード】
  python project1.py --mode train   # Phase1(U-Net) + Phase2(SELDnet) 学習
  python project1.py --mode eval    # 学習済みモデルで評価
  python project1.py --mode infer   # ラベルなし推論（実野外データ向け）

【データ構造】
  data/
    audio/          # 4ch FOA B-format WAV (24kHz)
    labels/         # CSV アノテーション（評価時のみ必要）
      *.csv         # onset,offset,class_idx,azimuth,elevation

【ラベルCSVフォーマット】
  onset[sec], offset[sec], class_idx[0-C], azimuth[deg], elevation[deg]
  例: 0.5,2.3,0,45,-10
"""

import os
import math
import glob
import argparse
import warnings
import numpy as np
import soundfile as sf
import librosa
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
import matplotlib.pyplot as plt
from itertools import permutations

warnings.filterwarnings("ignore")

# =============================================================================
# 1. 設定
# =============================================================================

CFG = {
    # --- データ ---
    "data_dir":       "./data",          # データルートディレクトリ
    "audio_dir":      "./data/audio",    # 4ch FOA WAV ファイル
    "label_dir":      "./data/labels",   # CSV アノテーション（評価時のみ）
    "output_dir":     "./output",        # モデル・結果の保存先

    # --- 音響特徴量 ---
    "fs":             24000,    # サンプリング周波数 (Hz)
    "n_fft":          1024,     # STFT ウィンドウ長
    "hop_length":     512,      # STFT ホップ長
    "n_mels":         64,       # メルフィルタ数
    "n_channels":     7,        # 入力チャンネル数 (4mel + 3IV)

    # --- セグメント ---
    "clip_duration":  10.0,     # セグメント長 (秒)
    "label_hop_sec":  0.1,      # ラベルフレームの時間分解能 (秒)

    # --- モデル ---
    "n_classes":      14,       # 音イベントクラス数 (DCASE2020: 14クラス)
    "n_tracks":       3,        # 最大重複音源数
    "unet_base_ch":   32,       # U-Net 基本チャンネル数

    # --- 学習 ---
    "lr":             1e-3,
    "batch_size":     16,
    "epochs_phase1":  100,      # U-Net 学習エポック
    "epochs_phase2":  100,      # SELDnet 学習エポック
    "iv_loss_weight": 10.0,     # IV の L1 損失重み (論文 λ=10)
    "freq_mask_bins": 8,        # 周波数マスクするメルビン数 (最大)

    # --- デバイス ---
    "device":         "cuda" if torch.cuda.is_available() else "cpu",
}

# フレーム数を事前計算
CFG["n_frames"] = int(CFG["clip_duration"] * CFG["fs"] / CFG["hop_length"])
# ラベルフレーム数
CFG["label_frames"] = int(CFG["clip_duration"] / CFG["label_hop_sec"])

print(f"Device: {CFG['device']}")
print(f"Frames per clip: {CFG['n_frames']}, Label frames: {CFG['label_frames']}")

# =============================================================================
# 2. 特徴量抽出 (FOA B-format → mel spectrogram + Intensity Vector)
# =============================================================================

def extract_foa_features(audio_path, cfg=CFG):
    """
    4ch FOA B-format WAV から 7ch 特徴量 (mel×4 + IV×3) を抽出する。
    論文 Section III-C 式(5) に準拠。

    Returns:
        feat (np.ndarray): shape (7, T, n_mels) - float32
    """
    audio, sr = sf.read(audio_path, always_2d=True)  # (samples, ch)

    # チャンネル数チェック
    if audio.shape[1] < 4:
        # モノラル/ステレオの場合は零パディングで4ch化
        pad = np.zeros((audio.shape[0], 4 - audio.shape[1]))
        audio = np.concatenate([audio, pad], axis=1)
    audio = audio[:, :4].T  # (4, samples)

    # リサンプル
    if sr != cfg["fs"]:
        audio = np.stack([
            librosa.resample(audio[c], orig_sr=sr, target_sr=cfg["fs"])
            for c in range(4)
        ])

    n_fft, hop = cfg["n_fft"], cfg["hop_length"]

    # STFT (各チャンネル)
    stfts = [
        librosa.stft(audio[c].astype(np.float32),
                     n_fft=n_fft, hop_length=hop,
                     win_length=n_fft, window="hann")
        for c in range(4)
    ]
    W, X, Y, Z = stfts  # shape: (n_fft//2+1, T)

    mel_basis = librosa.filters.mel(sr=cfg["fs"], n_fft=n_fft,
                                    n_mels=cfg["n_mels"])  # (n_mels, freq)

    # 4ch メルスペクトログラム
    mel_feats = []
    for stft in stfts:
        power = np.abs(stft) ** 2
        mel = mel_basis @ power          # (n_mels, T)
        mel_db = librosa.power_to_db(mel, ref=np.max)
        mel_feats.append(mel_db)

    # Intensity Vector (論文 式5)
    W_conj = np.conj(W)
    iv_x = np.real(W_conj * X)          # (freq, T)
    iv_y = np.real(W_conj * Y)
    iv_z = np.real(W_conj * Z)
    iv_x = mel_basis @ iv_x             # (n_mels, T)
    iv_y = mel_basis @ iv_y
    iv_z = mel_basis @ iv_z

    # 7ch 結合: (7, T, n_mels)
    feat = np.stack(mel_feats + [iv_x, iv_y, iv_z], axis=0)  # (7, n_mels, T)
    feat = feat.transpose(0, 2, 1)                             # (7, T, n_mels)

    return feat.astype(np.float32)


def normalize_feature(feat):
    """チャンネルごとに min-max 正規化 (0〜1)"""
    out = np.zeros_like(feat)
    for c in range(feat.shape[0]):
        mn, mx = feat[c].min(), feat[c].max()
        if mx - mn > 1e-8:
            out[c] = (feat[c] - mn) / (mx - mn)
        else:
            out[c] = feat[c] - mn
    return out


def freq_mask(feat, max_bins=8):
    """周波数マスキング (data augmentation)"""
    f = np.random.randint(0, max_bins + 1)
    f0 = np.random.randint(0, feat.shape[-1] - f + 1)
    feat = feat.copy()
    feat[:, :, f0:f0 + f] = 0.0
    return feat


def segment_feature(feat, n_frames):
    """
    長い特徴量を n_frames のセグメントに分割 (最後はゼロパディング)。
    Returns: list of (7, n_frames, n_mels)
    """
    T = feat.shape[1]
    segments = []
    for start in range(0, T, n_frames):
        seg = feat[:, start:start + n_frames, :]
        if seg.shape[1] < n_frames:
            pad = np.zeros((feat.shape[0], n_frames - seg.shape[1], feat.shape[2]),
                           dtype=np.float32)
            seg = np.concatenate([seg, pad], axis=1)
        segments.append(seg)
    return segments


# =============================================================================
# 3. ラベル処理 (CSV → multi-ACCDOA ターゲット)
# =============================================================================

def load_label_csv(csv_path, n_frames, n_classes, n_tracks, label_hop_sec):
    """
    CSV アノテーション → multi-ACCDOA ターゲット

    Returns:
        target (np.ndarray): shape (n_frames, n_tracks, n_classes, 3)
                             3 = (x, y, z) Cartesian DOA
                             アクティブな場合は単位ベクトル、非アクティブは(0,0,0)
    """
    target = np.zeros((n_frames, n_tracks, n_classes, 3), dtype=np.float32)

    if not os.path.exists(csv_path):
        return target

    events = []
    with open(csv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 5:
                continue
            onset, offset = float(parts[0]), float(parts[1])
            cls = int(parts[2])
            az = math.radians(float(parts[3]))   # azimuth → rad
            el = math.radians(float(parts[4]))   # elevation → rad
            # Cartesian DOA
            x = math.cos(el) * math.cos(az)
            y = math.cos(el) * math.sin(az)
            z = math.sin(el)
            events.append((onset, offset, cls, x, y, z))

    # フレームごとにイベントを割り当て
    for onset, offset, cls, x, y, z in events:
        if cls >= n_classes:
            continue
        fr_start = int(onset / label_hop_sec)
        fr_end   = int(offset / label_hop_sec)
        for fr in range(fr_start, min(fr_end, n_frames)):
            # 空きトラックを探す
            for tr in range(n_tracks):
                if np.sum(np.abs(target[fr, tr, cls])) == 0.0:
                    target[fr, tr, cls] = [x, y, z]
                    break

    return target


# =============================================================================
# 4. Dataset
# =============================================================================

class SELDOutdoorDataset(Dataset):
    """
    実野外データ用 Dataset。
    音声ファイル一覧と（オプションで）ラベルCSVを読み込む。
    """

    def __init__(self, audio_dir, label_dir=None, cfg=CFG,
                 augment=False, mode="train"):
        self.cfg = cfg
        self.augment = augment
        self.mode = mode
        self.label_dir = label_dir

        # WAV ファイル収集
        self.audio_paths = sorted(
            glob.glob(os.path.join(audio_dir, "**", "*.wav"), recursive=True) +
            glob.glob(os.path.join(audio_dir, "**", "*.WAV"), recursive=True)
        )
        if not self.audio_paths:
            raise FileNotFoundError(f"WAV ファイルが見つかりません: {audio_dir}")

        # 特徴量 + ラベルをセグメント単位でキャッシュ
        self.segments = []   # (feat, target_or_None, file_name, seg_idx)
        print(f"[Dataset] {len(self.audio_paths)} ファイルを処理中...")
        for ap in self.audio_paths:
            feat = extract_foa_features(ap, cfg)
            feat = normalize_feature(feat)
            segs = segment_feature(feat, cfg["n_frames"])

            # ラベル読み込み
            if label_dir is not None:
                base = os.path.splitext(os.path.basename(ap))[0]
                csv_path = os.path.join(label_dir, base + ".csv")
                # 音声全体のラベル
                n_total_frames = cfg["label_frames"] * len(segs)
                full_target = load_label_csv(
                    csv_path, n_total_frames,
                    cfg["n_classes"], cfg["n_tracks"], cfg["label_hop_sec"]
                )
                # セグメントごとに切り出し
                lf_per_seg = cfg["label_frames"]
                for i, seg_feat in enumerate(segs):
                    seg_target = full_target[
                        i * lf_per_seg:(i + 1) * lf_per_seg
                    ]
                    if seg_target.shape[0] < lf_per_seg:
                        pad = np.zeros(
                            (lf_per_seg - seg_target.shape[0],
                             cfg["n_tracks"], cfg["n_classes"], 3),
                            dtype=np.float32
                        )
                        seg_target = np.concatenate([seg_target, pad], axis=0)
                    self.segments.append(
                        (seg_feat, seg_target,
                         os.path.basename(ap), i)
                    )
            else:
                for i, seg_feat in enumerate(segs):
                    self.segments.append(
                        (seg_feat, None, os.path.basename(ap), i)
                    )

        print(f"[Dataset] セグメント総数: {len(self.segments)}")

    def __len__(self):
        return len(self.segments)

    def __getitem__(self, idx):
        feat, target, fname, seg_idx = self.segments[idx]

        if self.augment:
            feat = freq_mask(feat, self.cfg["freq_mask_bins"])

        feat_t = torch.from_numpy(feat)   # (7, T, n_mels)

        if target is not None:
            target_t = torch.from_numpy(target)  # (label_frames, n_tracks, n_classes, 3)
            return feat_t, target_t, fname, seg_idx
        else:
            return feat_t, fname, seg_idx


# =============================================================================
# 5. アーキテクチャ: U-Net (Phase 1 - 論文 Figure 3)
# =============================================================================

class UNetConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class UNet(nn.Module):
    """
    論文 Figure 3 の U-Net。
    入力: (B, 7, T, n_mels)  → 出力: (B, 7, T, n_mels)  [デノイズ済み特徴量]
    エンコーダの各レベルの特徴マップも返す (SELDnet の入力に使用)。

    チャンネル数: 7 → base → base*2 → base*4 → base*8 → base*16 → ...
    """

    def __init__(self, in_ch=7, base_ch=32):
        super().__init__()
        b = base_ch

        # Encoder
        self.enc1 = UNetConvBlock(in_ch, b)       # 250×64
        self.enc2 = UNetConvBlock(b,   b*2)       # 125×32
        self.enc3 = UNetConvBlock(b*2, b*4)       # 62×16
        self.enc4 = UNetConvBlock(b*4, b*8)       # 31×8
        self.pool  = nn.MaxPool2d(2, 2)

        # Bottleneck
        self.bottleneck = UNetConvBlock(b*8, b*16)  # 15×4

        # Decoder
        self.up4 = nn.ConvTranspose2d(b*16, b*8, 2, stride=2)
        self.dec4 = UNetConvBlock(b*16, b*8)

        self.up3 = nn.ConvTranspose2d(b*8, b*4, 2, stride=2)
        self.dec3 = UNetConvBlock(b*8, b*4)

        self.up2 = nn.ConvTranspose2d(b*4, b*2, 2, stride=2)
        self.dec2 = UNetConvBlock(b*4, b*2)

        self.up1 = nn.ConvTranspose2d(b*2, b, 2, stride=2)
        self.dec1 = UNetConvBlock(b*2, b)

        # 出力
        self.out_conv = nn.Conv2d(b, in_ch, 1)

    def forward(self, x):
        # Encoder
        e1 = self.enc1(x)                    # (B, b,    T,   M)
        e2 = self.enc2(self.pool(e1))        # (B, b*2,  T/2, M/2)
        e3 = self.enc3(self.pool(e2))        # (B, b*4,  T/4, M/4)
        e4 = self.enc4(self.pool(e3))        # (B, b*8,  T/8, M/8)
        bn = self.bottleneck(self.pool(e4))  # (B, b*16, T/16,M/16)

        # Decoder: ConvTranspose の出力をエンコーダのサイズに合わせて補間
        def _up_cat(up_layer, dec_feat, enc_feat):
            up = up_layer(dec_feat)
            if up.shape != enc_feat.shape:
                up = F.interpolate(up, size=enc_feat.shape[2:],
                                   mode="bilinear", align_corners=False)
            return torch.cat([up, enc_feat], dim=1)

        d4 = self.dec4(_up_cat(self.up4, bn, e4))  # (B, b*8, ...)
        d3 = self.dec3(_up_cat(self.up3, d4, e3))  # (B, b*4, ...)
        d2 = self.dec2(_up_cat(self.up2, d3, e2))  # (B, b*2, ...)
        d1 = self.dec1(_up_cat(self.up1, d2, e1))  # (B, b,   ...)

        out = self.out_conv(d1)  # (B, 7, T, M)

        # SELDnet へ渡すデコーダ特徴マップ (3つ)
        decoder_feats = [d1, d2, d3]

        return out, decoder_feats


# =============================================================================
# 6. アーキテクチャ: SELDnet (Phase 2 - 論文 Figure 6)
# =============================================================================

class ResidualConvBlock(nn.Module):
    """論文の Residual Convolutional Block (RCB)"""

    def __init__(self, in_ch, out_ch, dropout=0.3):
        super().__init__()
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1)
        self.bn1   = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1)
        self.bn2   = nn.BatchNorm2d(out_ch)
        self.skip  = nn.Conv2d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()
        self.pool  = nn.AdaptiveAvgPool2d((None, 1))  # 周波数軸を1に圧縮
        self.drop  = nn.Dropout(dropout)
        self.act   = nn.ReLU(inplace=True)

    def forward(self, x):
        residual = self.skip(x)
        out = self.act(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = self.act(out + residual)
        out = self.pool(out)     # (B, C, T, 1)
        out = self.drop(out)
        return out


class SELDnet(nn.Module):
    """
    論文 Figure 6 の SELDnet。
    入力: U-Net デコーダ特徴マップ (3つ) を結合・調整したもの
    出力: multi-ACCDOA (B, T, n_tracks × n_classes × 3)
    """

    def __init__(self, decoder_channels, n_classes, n_tracks=3,
                 n_heads=4, ff_dim=512, dropout=0.3):
        super().__init__()
        self.n_classes = n_classes
        self.n_tracks  = n_tracks

        # デコーダ特徴マップを同一チャンネル数に揃える ConvTranspose
        # d1: base_ch, d2: base_ch*2, d3: base_ch*4 → すべて base_ch に統一
        base = decoder_channels[0]
        self.align = nn.ModuleList([
            nn.Sequential(
                nn.ConvTranspose2d(decoder_channels[i], base, 1),
                nn.ReLU(inplace=True)
            )
            for i in range(len(decoder_channels))
        ])

        stem_in = base * len(decoder_channels)

        # Stem Block
        self.stem = nn.Sequential(
            nn.Conv2d(stem_in, stem_in, 5, padding=2),
            nn.ReLU(inplace=True),
            nn.Conv2d(stem_in, stem_in * 2, 1),
            nn.ReLU(inplace=True),
        )
        rcb_in = stem_in * 2

        # 3 Residual Convolutional Blocks
        self.rcb1 = ResidualConvBlock(rcb_in,  128, dropout)
        self.rcb2 = ResidualConvBlock(128,      128, dropout)
        self.rcb3 = ResidualConvBlock(128,      128, dropout)

        # Transformer Encoder (1 layer, 4 heads)
        self.pos_enc = PositionalEncoding(128)
        enc_layer = nn.TransformerEncoderLayer(
            d_model=128, nhead=n_heads,
            dim_feedforward=ff_dim,
            dropout=dropout, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(enc_layer, num_layers=1)

        # 予測ブロック
        self.fc1 = nn.Linear(128, 128)
        self.fc2 = nn.Linear(128, n_tracks * n_classes * 3)

    def forward(self, decoder_feats):
        """
        decoder_feats: list of tensors [(B,c1,T,M), (B,c2,T,M), (B,c3,T,M)]
        Returns: (B, T, n_tracks, n_classes, 3)
        """
        # 全デコーダ特徴を同じ空間サイズに揃えてから結合
        target_size = decoder_feats[0].shape[2:]  # T, M of d1
        aligned = []
        for i, feat in enumerate(decoder_feats):
            a = self.align[i](feat)
            if a.shape[2:] != target_size:
                a = F.interpolate(a, size=target_size, mode="bilinear",
                                  align_corners=False)
            aligned.append(a)
        x = torch.cat(aligned, dim=1)  # (B, sum_ch, T, M)

        x = self.stem(x)               # (B, stem_ch*2, T, M)
        x = self.rcb1(x)               # (B, 128, T, 1)
        x = self.rcb2(x)               # (B, 128, T, 1)
        x = self.rcb3(x)               # (B, 128, T, 1)

        x = x.squeeze(-1).permute(0, 2, 1)  # (B, T, 128)
        x = self.pos_enc(x)
        x = self.transformer(x)              # (B, T, 128)

        x = F.relu(self.fc1(x))
        x = self.fc2(x)                      # (B, T, n_tracks*n_classes*3)

        B, T, _ = x.shape
        x = x.view(B, T, self.n_tracks, self.n_classes, 3)
        x = torch.tanh(x)  # [-1, 1] → 方向余弦表現
        return x


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=2000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len).unsqueeze(1).float()
        div = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))  # (1, max_len, d_model)

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]


# =============================================================================
# 7. SELD U-Net 統合モデル
# =============================================================================

class SELDUNet(nn.Module):
    """
    Phase 1 の U-Net + Phase 2 の SELDnet を結合した統合モデル。
    論文 Figure 2 に対応。
    """

    def __init__(self, cfg=CFG):
        super().__init__()
        b = cfg["unet_base_ch"]

        self.unet = UNet(in_ch=cfg["n_channels"], base_ch=b)

        # デコーダの各レベルのチャンネル数 (d1, d2, d3)
        decoder_channels = [b, b*2, b*4]

        self.seldnet = SELDnet(
            decoder_channels=decoder_channels,
            n_classes=cfg["n_classes"],
            n_tracks=cfg["n_tracks"],
        )

    def forward(self, x):
        """
        x: (B, 7, T, n_mels)
        Returns:
            enhanced: (B, 7, T, n_mels)   Phase1 出力
            seld_out: (B, T_label, n_tracks, n_classes, 3)  Phase2 出力
        """
        enhanced, decoder_feats = self.unet(x)
        seld_out = self.seldnet(decoder_feats)
        return enhanced, seld_out


# =============================================================================
# 8. 損失関数
# =============================================================================

def unet_loss(pred, target, iv_weight=10.0, n_mel_ch=4):
    """
    論文 式(1): mel spectrogram の L1 + IV の L1 × λ
    pred, target: (B, 7, T, n_mels)
    """
    mel_pred   = pred[:, :n_mel_ch]
    mel_target = target[:, :n_mel_ch]
    iv_pred    = pred[:, n_mel_ch:]
    iv_target  = target[:, n_mel_ch:]

    loss_mel = F.l1_loss(mel_pred, mel_target)
    loss_iv  = F.l1_loss(iv_pred, iv_target)
    return loss_mel + iv_weight * loss_iv


def adpit_loss(pred, target):
    """
    論文 式(3)(4): ADPIT (Auxiliary Duplicating Permutation Invariant Training)
    pred:   (B, T, n_tracks, n_classes, 3)
    target: (B, T_label, n_tracks, n_classes, 3)
    """
    B, T_pred, N, C, _ = pred.shape
    T_lbl = target.shape[1]
    T = min(T_pred, T_lbl)

    pred   = pred[:, :T]    # (B, T, N, C, 3)
    target = target[:, :T]  # (B, T, N, C, 3)

    # クラスごと、フレームごとに最良のトラック割り当てを探す
    # シンプル化: 各クラスについて N トラック間の最小 MSE を使用
    total_loss = 0.0
    for c in range(C):
        t_c = target[:, :, :, c, :]  # (B, T, N, 3)
        p_c = pred[:,   :, :, c, :]  # (B, T, N, 3)

        # 全順列の中で最小 MSE を選択
        best_loss = None
        for perm in permutations(range(N)):
            p_c_perm = p_c[:, :, list(perm), :]
            mse = ((p_c_perm - t_c) ** 2).mean(dim=(2, 3))  # (B, T)
            if best_loss is None:
                best_loss = mse
            else:
                best_loss = torch.minimum(best_loss, mse)

        total_loss += best_loss.mean()

    return total_loss / C


# =============================================================================
# 9. 評価指標 (DCASE SELD metrics)
# =============================================================================

def cart2sph(x, y, z):
    """直交座標 → 球座標 (方位角[deg], 仰角[deg])"""
    r = math.sqrt(x**2 + y**2 + z**2)
    if r < 1e-8:
        return 0.0, 0.0
    az = math.degrees(math.atan2(y, x))
    el = math.degrees(math.asin(max(-1, min(1, z / r))))
    return az, el


def angular_distance(az1, el1, az2, el2):
    """2点間の大圏距離 (度)"""
    az1, el1 = math.radians(az1), math.radians(el1)
    az2, el2 = math.radians(az2), math.radians(el2)
    dist = math.acos(max(-1.0, min(1.0,
        math.sin(el1)*math.sin(el2) +
        math.cos(el1)*math.cos(el2)*math.cos(az1 - az2)
    )))
    return math.degrees(dist)


def decode_accdoa(seld_out, threshold=0.5):
    """
    multi-ACCDOA → イベントリスト [(frame, class, az, el), ...]
    seld_out: (T, n_tracks, n_classes, 3)
    """
    events = []
    T, N, C, _ = seld_out.shape
    for t in range(T):
        for n in range(N):
            for c in range(C):
                vec = seld_out[t, n, c]
                r = float(np.linalg.norm(vec))
                if r > threshold:
                    az, el = cart2sph(*vec.tolist())
                    events.append((t, c, az, el))
    return events


class SELDMetrics:
    """
    フレームレベル SELD 評価指標。
    論文 式(9)〜(20) に対応。
    """

    def __init__(self, n_classes, doa_threshold=20.0):
        self.C = n_classes
        self.doa_th = doa_threshold
        self.reset()

    def reset(self):
        self.TP = self.FP = self.FN = 0
        self.loc_error_sum = 0.0
        self.loc_recall_num = self.loc_recall_den = 0

    def update(self, pred_events, ref_events, n_frames):
        """
        pred_events, ref_events: list of (frame, class, az, el)
        """
        # フレーム×クラス → イベントリスト のマッピング
        def to_dict(events):
            d = {}
            for fr, cls, az, el in events:
                d.setdefault((fr, cls), []).append((az, el))
            return d

        pred_d = to_dict(pred_events)
        ref_d  = to_dict(ref_events)

        all_keys = set(pred_d.keys()) | set(ref_d.keys())

        for key in all_keys:
            preds = pred_d.get(key, [])
            refs  = ref_d.get(key, [])

            # TP / FP / FN (論文 式9〜11)
            tp = min(len(preds), len(refs))
            fp = max(0, len(preds) - len(refs))
            fn = max(0, len(refs) - len(preds))

            # DOA 条件付き TP
            doa_tp = 0
            used = [False] * len(refs)
            for p_az, p_el in preds:
                for j, (r_az, r_el) in enumerate(refs):
                    if not used[j]:
                        d = angular_distance(p_az, p_el, r_az, r_el)
                        if d <= self.doa_th:
                            doa_tp += 1
                            used[j] = True
                            self.loc_error_sum += d
                            break

            self.TP += doa_tp
            self.FP += fp + (tp - doa_tp)
            self.FN += fn + (tp - doa_tp)
            self.loc_recall_num += doa_tp
            self.loc_recall_den += len(refs)

    def compute(self):
        # F1-score
        precision = self.TP / (self.TP + self.FP + 1e-8)
        recall    = self.TP / (self.TP + self.FN + 1e-8)
        F1 = 2 * precision * recall / (precision + recall + 1e-8)

        # Error Rate
        ER = (self.FP + self.FN) / (self.TP + self.FN + 1e-8)
        ER = min(ER, 1.0)

        # Localization Error (LE)
        LE = self.loc_error_sum / (self.loc_recall_num + 1e-8)

        # Localization Recall (LR)
        LR = self.loc_recall_num / (self.loc_recall_den + 1e-8)

        # SELD Score (論文 式20)
        SELD = (ER + (1 - F1) + LE / 180.0 + (1 - LR)) / 4.0

        return {
            "ER": ER, "F1": F1,
            "LE": LE, "LR": LR,
            "SELD": SELD
        }


# =============================================================================
# 10. 学習ループ
# =============================================================================

def train_phase1(model, loader, optimizer, cfg):
    """Phase 1: U-Net 学習 (ノイズ除去)"""
    model.train()
    total_loss = 0.0
    for batch in loader:
        # ラベルなしの場合もあるので対応
        if len(batch) == 4:
            feat, _, _, _ = batch
        else:
            feat, _, _ = batch

        feat = feat.to(cfg["device"])  # (B, 7, T, n_mels) - これが「ノイズあり」
        # Phase1 では自己再構成 (identity) で U-Net を学習
        # 実データでは clean と noisy のペアが理想だが、
        # ここでは入力を教師信号として学習（自己教師あり）
        optimizer.zero_grad()
        enhanced, _ = model(feat)
        loss = unet_loss(enhanced, feat, cfg["iv_loss_weight"])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(loader)


def train_phase2(model, loader, optimizer, cfg, freeze_unet=True):
    """Phase 2: SELDnet 学習 (U-Net 重みは固定)"""
    model.train()
    if freeze_unet:
        for p in model.unet.parameters():
            p.requires_grad = False
    else:
        for p in model.unet.parameters():
            p.requires_grad = True

    total_loss = 0.0
    skipped = 0
    for batch in loader:
        if len(batch) != 4:
            skipped += 1
            continue
        feat, target, _, _ = batch
        feat   = feat.to(cfg["device"])    # (B, 7, T, n_mels)
        target = target.to(cfg["device"])  # (B, T_lbl, N, C, 3)

        optimizer.zero_grad()
        _, seld_out = model(feat)
        loss = adpit_loss(seld_out, target)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        total_loss += loss.item()

    if freeze_unet:
        for p in model.unet.parameters():
            p.requires_grad = True

    n = len(loader) - skipped
    return total_loss / max(n, 1)


def train(cfg=CFG):
    """Phase1 → Phase2 の 2段階学習"""
    os.makedirs(cfg["output_dir"], exist_ok=True)

    # --- データセット ---
    has_labels = os.path.isdir(cfg["label_dir"])
    label_dir = cfg["label_dir"] if has_labels else None

    train_dataset = SELDOutdoorDataset(
        cfg["audio_dir"], label_dir, cfg, augment=True, mode="train"
    )
    train_loader = DataLoader(
        train_dataset, batch_size=cfg["batch_size"],
        shuffle=True, num_workers=0, drop_last=False
    )

    # --- モデル ---
    model = SELDUNet(cfg).to(cfg["device"])
    total_params = sum(p.numel() for p in model.parameters()) / 1e6
    print(f"[Model] パラメータ数: {total_params:.2f}M")

    # --- Phase 1 ---
    print("\n=== Phase 1: U-Net 学習 ===")
    opt1 = torch.optim.Adam(model.unet.parameters(), lr=cfg["lr"])
    best_loss1 = float("inf")
    history1 = []
    for ep in range(cfg["epochs_phase1"]):
        loss = train_phase1(model, train_loader, opt1, cfg)
        history1.append(loss)
        if loss < best_loss1:
            best_loss1 = loss
            torch.save(model.unet.state_dict(),
                       os.path.join(cfg["output_dir"], "unet_best.pt"))
        if (ep + 1) % 10 == 0:
            print(f"  Epoch {ep+1:3d}/{cfg['epochs_phase1']} | loss={loss:.4f}")

    # --- Phase 2 (ラベルがある場合のみ) ---
    if has_labels:
        print("\n=== Phase 2: SELDnet 学習 ===")
        # U-Net の最良重みを読み込み
        model.unet.load_state_dict(
            torch.load(os.path.join(cfg["output_dir"], "unet_best.pt"),
                       map_location=cfg["device"])
        )

        opt2 = torch.optim.Adam(model.seldnet.parameters(), lr=cfg["lr"])
        best_loss2 = float("inf")
        history2 = []
        for ep in range(cfg["epochs_phase2"]):
            loss = train_phase2(model, train_loader, opt2, cfg, freeze_unet=True)
            history2.append(loss)
            if loss < best_loss2:
                best_loss2 = loss
                torch.save(model.state_dict(),
                           os.path.join(cfg["output_dir"], "seld_unet_best.pt"))
            if (ep + 1) % 10 == 0:
                print(f"  Epoch {ep+1:3d}/{cfg['epochs_phase2']} | loss={loss:.4f}")

        _plot_history(history1, history2, cfg["output_dir"])
    else:
        print("\n[警告] ラベルディレクトリが見つかりません。Phase2 をスキップします。")
        torch.save(model.state_dict(),
                   os.path.join(cfg["output_dir"], "seld_unet_best.pt"))
        _plot_history(history1, [], cfg["output_dir"])

    print(f"\n学習完了。モデル保存先: {cfg['output_dir']}")


def _plot_history(h1, h2, out_dir):
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    plt.plot(h1)
    plt.title("Phase1: U-Net Loss (L1)")
    plt.xlabel("Epoch"); plt.ylabel("Loss")

    plt.subplot(1, 2, 2)
    if h2:
        plt.plot(h2)
        plt.title("Phase2: SELDnet Loss (ADPIT)")
        plt.xlabel("Epoch"); plt.ylabel("Loss")
    else:
        plt.text(0.5, 0.5, "Phase2 skipped\n(no labels)", ha="center")

    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "training_curves.png"))
    plt.close()
    print(f"  学習曲線: {os.path.join(out_dir, 'training_curves.png')}")


# =============================================================================
# 11. 評価 / 推論
# =============================================================================

@torch.no_grad()
def evaluate(cfg=CFG):
    """学習済みモデルで SELD メトリクスを計算"""
    model_path = os.path.join(cfg["output_dir"], "seld_unet_best.pt")
    if not os.path.exists(model_path):
        print(f"[Error] モデルが見つかりません: {model_path}")
        return

    model = SELDUNet(cfg).to(cfg["device"])
    model.load_state_dict(
        torch.load(model_path, map_location=cfg["device"])
    )
    model.eval()

    has_labels = os.path.isdir(cfg["label_dir"])
    dataset = SELDOutdoorDataset(
        cfg["audio_dir"],
        cfg["label_dir"] if has_labels else None,
        cfg, augment=False, mode="eval"
    )
    loader = DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0)

    metrics = SELDMetrics(cfg["n_classes"])
    results_per_file = {}  # fname → [(pred_events, ref_events)]

    for batch in loader:
        if has_labels and len(batch) == 4:
            feat, target, fnames, seg_idxs = batch
            target = target.to(cfg["device"])
        elif len(batch) == 3:
            feat, fnames, seg_idxs = batch
            target = None
        else:
            continue

        feat = feat.to(cfg["device"])
        fname = fnames[0]
        seg_idx = int(seg_idxs[0])

        _, seld_out = model(feat)  # (1, T, N, C, 3)
        seld_np = seld_out[0].cpu().numpy()

        pred_events = decode_accdoa(seld_np, threshold=0.5)
        ref_events  = []

        if target is not None:
            ref_np = target[0].cpu().numpy()
            ref_events = decode_accdoa(ref_np, threshold=0.1)
            metrics.update(pred_events, ref_events,
                           n_frames=cfg["label_frames"])

        results_per_file.setdefault(fname, []).append(
            (seg_idx, pred_events, ref_events)
        )

    # --- メトリクス出力 ---
    print("\n=== SELD 評価結果 ===")
    if has_labels:
        res = metrics.compute()
        print(f"  Error Rate (ER):       {res['ER']:.4f}  (↓ 低いほど良い)")
        print(f"  F1-score:              {res['F1']:.4f}  (↑ 高いほど良い)")
        print(f"  Localization Error:    {res['LE']:.2f} deg  (↓ 低いほど良い)")
        print(f"  Localization Recall:   {res['LR']:.4f}  (↑ 高いほど良い)")
        print(f"  SELD Score:            {res['SELD']:.4f}  (↓ 低いほど良い)")
    else:
        print("  ラベルなし → メトリクス計算スキップ")

    # --- 結果の可視化 ---
    _visualize_results(results_per_file, cfg)
    return results_per_file


@torch.no_grad()
def infer(cfg=CFG):
    """ラベルなし実野外データへの推論"""
    model_path = os.path.join(cfg["output_dir"], "seld_unet_best.pt")
    if not os.path.exists(model_path):
        print(f"[Error] モデルが見つかりません: {model_path}")
        return

    model = SELDUNet(cfg).to(cfg["device"])
    model.load_state_dict(
        torch.load(model_path, map_location=cfg["device"])
    )
    model.eval()

    dataset = SELDOutdoorDataset(
        cfg["audio_dir"], None, cfg, augment=False, mode="infer"
    )
    loader = DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0)

    os.makedirs(os.path.join(cfg["output_dir"], "predictions"), exist_ok=True)
    all_results = {}

    for batch in loader:
        feat, fnames, seg_idxs = batch
        feat  = feat.to(cfg["device"])
        fname = fnames[0]
        seg_i = int(seg_idxs[0])

        _, seld_out = model(feat)
        seld_np = seld_out[0].cpu().numpy()  # (T, N, C, 3)
        pred_events = decode_accdoa(seld_np, threshold=0.5)

        all_results.setdefault(fname, []).append((seg_i, pred_events))

    # --- CSV 出力 ---
    for fname, segs in all_results.items():
        segs.sort(key=lambda x: x[0])
        base = os.path.splitext(fname)[0]
        out_csv = os.path.join(cfg["output_dir"], "predictions", base + ".csv")
        with open(out_csv, "w") as f:
            f.write("onset_sec,offset_sec,class_idx,azimuth_deg,elevation_deg\n")
            for seg_i, events in segs:
                time_offset = seg_i * cfg["clip_duration"]
                for (fr, cls, az, el) in events:
                    onset  = time_offset + fr * cfg["label_hop_sec"]
                    offset = onset + cfg["label_hop_sec"]
                    f.write(f"{onset:.3f},{offset:.3f},{cls},{az:.1f},{el:.1f}\n")
        print(f"  予測 CSV 保存: {out_csv}")

    _visualize_results(
        {k: [(s, ev, []) for s, ev in v] for k, v in all_results.items()},
        cfg
    )


def _visualize_results(results_per_file, cfg):
    """
    各ファイルの予測イベントを time×class のヒートマップで可視化。
    """
    os.makedirs(os.path.join(cfg["output_dir"], "figures"), exist_ok=True)

    for fname, seg_list in results_per_file.items():
        seg_list = sorted(seg_list, key=lambda x: x[0])
        total_frames = len(seg_list) * cfg["label_frames"]

        pred_map = np.zeros((cfg["n_classes"], total_frames))
        ref_map  = np.zeros((cfg["n_classes"], total_frames))

        for i, item in enumerate(seg_list):
            seg_i = item[0]
            pred_events = item[1]
            ref_events  = item[2] if len(item) > 2 else []
            offset = i * cfg["label_frames"]
            for (fr, cls, az, el) in pred_events:
                if fr + offset < total_frames and cls < cfg["n_classes"]:
                    pred_map[cls, fr + offset] = 1
            for (fr, cls, az, el) in ref_events:
                if fr + offset < total_frames and cls < cfg["n_classes"]:
                    ref_map[cls, fr + offset] = 1

        has_ref = ref_map.sum() > 0
        fig, axes = plt.subplots(1 + has_ref, 1,
                                 figsize=(14, 4 * (1 + has_ref)))
        if not has_ref:
            axes = [axes]

        axes[0].imshow(pred_map, aspect="auto", origin="lower",
                       cmap="Blues", vmin=0, vmax=1)
        axes[0].set_title(f"予測: {fname}")
        axes[0].set_xlabel("フレーム"); axes[0].set_ylabel("クラスID")

        if has_ref:
            axes[1].imshow(ref_map, aspect="auto", origin="lower",
                           cmap="Reds", vmin=0, vmax=1)
            axes[1].set_title(f"正解: {fname}")
            axes[1].set_xlabel("フレーム"); axes[1].set_ylabel("クラスID")

        plt.tight_layout()
        fig_path = os.path.join(
            cfg["output_dir"], "figures",
            os.path.splitext(fname)[0] + "_seld.png"
        )
        plt.savefig(fig_path, dpi=100)
        plt.close()
        print(f"  可視化: {fig_path}")


# =============================================================================
# 12. サンプルデータ生成 (動作確認用)
# =============================================================================

def generate_sample_data(cfg=CFG, n_files=3, duration=10.0):
    """
    動作確認用の合成 4ch FOA 音声と CSV ラベルを生成する。
    実野外データがある場合はこの関数を呼ばずに data/ ディレクトリを用意してください。
    """
    import soundfile as sf

    audio_dir = cfg["audio_dir"]
    label_dir = cfg["label_dir"]
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(label_dir, exist_ok=True)

    fs = cfg["fs"]
    n_samples = int(duration * fs)
    t = np.linspace(0, duration, n_samples, endpoint=False)

    freqs = [440, 880, 1320, 660, 550]
    class_names = list(range(cfg["n_classes"]))

    for i in range(n_files):
        # 4ch FOA: W=omni, X=cos(az)cos(el), Y=sin(az)cos(el), Z=sin(el)
        audio = np.zeros((n_samples, 4), dtype=np.float32)
        events = []

        for ev_i in range(3):
            onset  = np.random.uniform(0.5, duration * 0.3)
            offset = onset + np.random.uniform(1.0, 3.0)
            offset = min(offset, duration - 0.5)
            cls    = np.random.randint(0, cfg["n_classes"])
            az     = np.random.uniform(-180, 180)
            el     = np.random.uniform(-30, 30)
            freq   = freqs[ev_i % len(freqs)]

            az_r = math.radians(az); el_r = math.radians(el)
            x = math.cos(el_r) * math.cos(az_r)
            y = math.cos(el_r) * math.sin(az_r)
            z = math.sin(el_r)
            amp = 0.3

            mask = (t >= onset) & (t <= offset)
            sig = amp * np.sin(2 * np.pi * freq * t)
            audio[mask, 0] += sig[mask]           # W
            audio[mask, 1] += x * sig[mask]       # X
            audio[mask, 2] += y * sig[mask]       # Y
            audio[mask, 3] += z * sig[mask]       # Z
            events.append((onset, offset, cls, az, el))

        # ノイズを追加 (実野外を模倣)
        noise_level = np.random.uniform(0.02, 0.1)
        audio += noise_level * np.random.randn(*audio.shape).astype(np.float32)
        audio = np.clip(audio, -1.0, 1.0)

        wav_path = os.path.join(audio_dir, f"outdoor_sample_{i:03d}.wav")
        sf.write(wav_path, audio, fs, subtype="PCM_16")

        csv_path = os.path.join(label_dir, f"outdoor_sample_{i:03d}.csv")
        with open(csv_path, "w") as f:
            for onset, offset, cls, az, el in events:
                f.write(f"{onset:.3f},{offset:.3f},{cls},{az:.1f},{el:.1f}\n")

    print(f"サンプルデータ生成完了: audio={n_files}ファイル, labels={n_files}ファイル")


# =============================================================================
# 13. エントリポイント
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SELD U-Net 実野外データ評価")
    parser.add_argument("--mode", choices=["train", "eval", "infer", "demo"],
                        default="demo",
                        help="動作モード (demo=サンプル生成して学習+評価)")
    parser.add_argument("--audio_dir",  default=None, help="音声ディレクトリ")
    parser.add_argument("--label_dir",  default=None, help="ラベルディレクトリ")
    parser.add_argument("--output_dir", default=None, help="出力ディレクトリ")
    parser.add_argument("--n_classes",  type=int, default=None, help="音イベントクラス数")
    parser.add_argument("--epochs_p1",  type=int, default=None, help="Phase1 エポック数")
    parser.add_argument("--epochs_p2",  type=int, default=None, help="Phase2 エポック数")
    args = parser.parse_args()

    # コマンドライン引数で CFG を上書き
    if args.audio_dir:  CFG["audio_dir"]  = args.audio_dir
    if args.label_dir:  CFG["label_dir"]  = args.label_dir
    if args.output_dir: CFG["output_dir"] = args.output_dir
    if args.n_classes:  CFG["n_classes"]  = args.n_classes
    if args.epochs_p1:  CFG["epochs_phase1"] = args.epochs_p1
    if args.epochs_p2:  CFG["epochs_phase2"] = args.epochs_p2

    os.makedirs(CFG["output_dir"], exist_ok=True)

    if args.mode == "demo":
        print("=" * 60)
        print("DEMO モード: サンプルデータを生成して学習・評価を実行します")
        print("=" * 60)
        ep1 = args.epochs_p1 if args.epochs_p1 else 100
        ep2 = args.epochs_p2 if args.epochs_p2 else 100
        CFG["epochs_phase1"] = ep1
        CFG["epochs_phase2"] = ep2
        CFG["batch_size"] = 2
        generate_sample_data(CFG, n_files=10, duration=10.0)
        train(CFG)
        evaluate(CFG)

    elif args.mode == "train":
        print("=" * 60)
        print(f"学習モード | audio: {CFG['audio_dir']}")
        print("=" * 60)
        train(CFG)

    elif args.mode == "eval":
        print("=" * 60)
        print(f"評価モード | audio: {CFG['audio_dir']}")
        print("=" * 60)
        evaluate(CFG)

    elif args.mode == "infer":
        print("=" * 60)
        print(f"推論モード (ラベルなし) | audio: {CFG['audio_dir']}")
        print("=" * 60)
        infer(CFG)
