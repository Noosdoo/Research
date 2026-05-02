"""
UNS-ESSE2023 SELD U-Net 評価スクリプト
データセット: UNS-Exterior Spatial Sound Events 2023 (DOI: 10.5281/zenodo.10792703)
論文モデル: "SELD U-Net: Joint Optimization of Sound Event Localization and Detection
             With Noise Reduction" (IEEE Access, 2023)

【クラス定義】
  0: boom            (爆発音)
  1: gunshot/gunfire (銃声)
  2: shatter         (破砕音)

【データセット仕様】
  - 音声: 8ch マイクアレイ (Infineon Audiohub Nano, 48kHz)
  - 特徴量: 8ch メルスペクトログラム (FOA でないため IV は使用しない)
  - アノテーション: metafiles/meta.events.csv (onset/offset 形式)
  - 仰角: 常に 0 (水平面配置)

【ディレクトリ構造 (Zenodo から解凍後)】
  data/
    audio/
      mix_0/ ... mix_5/
        chunked/dev/
          train/ val/ → 学習・検証
        chunked/eval/ → テスト評価
    metafiles/
      meta.events.csv
      evaluation setup/
        fold1_train.csv / fold1_val.csv / fold1_evaluate.csv

【動作モード】
  python uns_esse2023_seld.py --mode demo    # 合成データで動作確認
  python uns_esse2023_seld.py --mode train   # 学習 (実データ)
  python uns_esse2023_seld.py --mode eval    # 評価
  python uns_esse2023_seld.py --mode infer   # ラベルなし推論
"""

import os
import csv
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

CLASS_NAMES = ["boom", "gunshot_gunfire", "shatter"]

# meta.events.csv の event_label → クラス番号
CLASS_MAP = {
    "boom": 0,
    "gunshot": 1, "gunfire": 1, "gunshot_gunfire": 1,
    "shatter": 2,
}

CFG = {
    # --- データ ---
    "data_root":      "./data",
    "audio_root":     "./data/audio",
    "meta_csv":       "./data/meta.events.csv",   # data/ 直下に存在
    "output_dir":     "./output",
    "train_split":    "train",   # meta.events.csv の "set" 列
    "eval_split":     "eval",

    # --- 音響特徴量 ---
    # 8ch MIC @ 48kHz → 24kHz にリサンプルして処理
    "fs":             24000,
    "n_fft":          1024,
    "hop_length":     512,
    "n_mels":         64,
    "n_channels":     8,         # 8ch mel スペクトログラム

    # --- セグメント ---
    "clip_duration":  10.0,
    "label_hop_sec":  0.1,       # meta.events.csv の時間精度

    # --- モデル ---
    "n_classes":      3,
    "n_tracks":       3,
    "unet_base_ch":   32,

    # --- 学習 ---
    "lr":             1e-3,
    "batch_size":     8,         # 8ch でメモリ増加するため小さめ
    "epochs_phase1":  100,
    "epochs_phase2":  100,
    "freq_mask_bins": 8,

    # --- デバイス ---
    "device":         "cuda" if torch.cuda.is_available() else "cpu",
}

CFG["n_frames"]     = int(CFG["clip_duration"] * CFG["fs"] / CFG["hop_length"])
CFG["label_frames"] = int(CFG["clip_duration"] / CFG["label_hop_sec"])

print(f"Device: {CFG['device']}")
print(f"Classes: {CLASS_NAMES}")
print(f"n_frames={CFG['n_frames']}, label_frames={CFG['label_frames']}")

# =============================================================================
# 2. 特徴量抽出 (8ch MIC → 8 mel スペクトログラム)
# =============================================================================

def extract_mic_features(audio_path, cfg=CFG):
    """
    8ch マイクアレイ WAV から 8ch メルスペクトログラムを抽出する。
    FOA でないため Intensity Vector は使用しない。

    Returns:
        feat (np.ndarray): shape (8, T, n_mels) - float32
    """
    audio, sr = sf.read(audio_path, always_2d=True)  # (samples, ch)

    n_ch = min(audio.shape[1], 8)
    audio = audio[:, :n_ch].T  # (n_ch, samples)
    if n_ch < 8:
        pad = np.zeros((8 - n_ch, audio.shape[1]))
        audio = np.concatenate([audio, pad], axis=0)

    if sr != cfg["fs"]:
        audio = np.stack([
            librosa.resample(audio[c], orig_sr=sr, target_sr=cfg["fs"])
            for c in range(8)
        ])

    mel_basis = librosa.filters.mel(sr=cfg["fs"], n_fft=cfg["n_fft"],
                                    n_mels=cfg["n_mels"])

    mel_feats = []
    for c in range(8):
        stft  = librosa.stft(audio[c].astype(np.float32),
                              n_fft=cfg["n_fft"], hop_length=cfg["hop_length"],
                              win_length=cfg["n_fft"], window="hann")
        power = np.abs(stft) ** 2
        mel   = librosa.power_to_db(mel_basis @ power, ref=np.max)
        mel_feats.append(mel)

    feat = np.stack(mel_feats, axis=0)   # (8, n_mels, T)
    feat = feat.transpose(0, 2, 1)       # (8, T, n_mels)
    return feat.astype(np.float32)


def normalize_feature(feat):
    out = np.zeros_like(feat)
    for c in range(feat.shape[0]):
        mn, mx = feat[c].min(), feat[c].max()
        out[c] = (feat[c] - mn) / (mx - mn) if mx - mn > 1e-8 else feat[c] - mn
    return out


def freq_mask(feat, max_bins=8):
    f  = np.random.randint(0, max_bins + 1)
    f0 = np.random.randint(0, feat.shape[-1] - f + 1)
    feat = feat.copy()
    feat[:, :, f0:f0 + f] = 0.0
    return feat


def segment_feature(feat, n_frames):
    T, segs = feat.shape[1], []
    for start in range(0, T, n_frames):
        seg = feat[:, start:start + n_frames, :]
        if seg.shape[1] < n_frames:
            pad = np.zeros((feat.shape[0], n_frames - seg.shape[1], feat.shape[2]),
                           dtype=np.float32)
            seg = np.concatenate([seg, pad], axis=1)
        segs.append(seg)
    return segs


# =============================================================================
# 3. アノテーション処理 (meta.events.csv → multi-ACCDOA ターゲット)
# =============================================================================

def load_meta_events_csv(meta_csv, split=None, data_root="./data"):
    """
    meta.events.csv を読み込んで {audio_path: [(onset,offset,cls,az,el), ...]} を返す。

    meta.events.csv の列:
      filename, event_onset, event_offset, event_label,
      azimuth, event_elevation, event_distance, set, snr, spl_before, spl_after, identifier
    """
    file_events = {}
    if not os.path.exists(meta_csv):
        return file_events

    with open(meta_csv, newline="", encoding="utf-8-sig") as f:
        # TSV 形式 (タブ区切り、\r\n 改行)
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            s = row.get("set", "").strip()
            if split and s != split:
                continue
            fname = row["filename"].strip().replace("\\", "/")
            label = row["event_label"].strip().lower()
            cls   = CLASS_MAP.get(label)
            if cls is None:
                continue
            onset  = float(row["event_onset"])
            offset = float(row["event_offset"])
            # 列名は "event_azimuth" (ReadMe の "azimuth" と異なる実際の列名)
            az     = float(row.get("event_azimuth", row.get("azimuth", "0")))
            el     = float(row.get("event_elevation", "0"))
            audio_path = os.path.normpath(os.path.join(data_root, fname))
            file_events.setdefault(audio_path, []).append((onset, offset, cls, az, el))

    return file_events


def events_to_target(events, n_frames, n_classes, n_tracks, label_hop_sec):
    """
    イベントリスト → multi-ACCDOA ターゲット (n_frames, n_tracks, n_classes, 3)
    """
    target = np.zeros((n_frames, n_tracks, n_classes, 3), dtype=np.float32)
    for onset, offset, cls, az, el in events:
        if cls >= n_classes:
            continue
        az_r, el_r = math.radians(az), math.radians(el)
        x = math.cos(el_r) * math.cos(az_r)
        y = math.cos(el_r) * math.sin(az_r)
        z = math.sin(el_r)
        fr_start = int(onset / label_hop_sec)
        fr_end   = int(offset / label_hop_sec)
        for fr in range(fr_start, min(fr_end, n_frames)):
            for tr in range(n_tracks):
                if np.sum(np.abs(target[fr, tr, cls])) == 0.0:
                    target[fr, tr, cls] = [x, y, z]
                    break
    return target


# =============================================================================
# 4. Dataset
# =============================================================================

class UNSESSEDataset(Dataset):
    """
    UNS-ESSE2023 用 Dataset。
    meta.events.csv から音声パスとイベントを取得する。
    split が None の場合はすべてのファイルをロード (推論用)。
    """

    def __init__(self, cfg=CFG, split="train", augment=False,
                 audio_paths_override=None):
        self.cfg     = cfg
        self.augment = augment

        if audio_paths_override is not None:
            # meta CSV なし: ディレクトリスキャン (infer モード)
            file_events = {p: [] for p in audio_paths_override}
        else:
            file_events = load_meta_events_csv(
                cfg["meta_csv"], split=split, data_root=cfg["data_root"]
            )

        if not file_events:
            # meta CSV が存在しない場合は audio_root をスキャン
            audio_paths = sorted(
                glob.glob(os.path.join(cfg["audio_root"], "**", "*.wav"), recursive=True) +
                glob.glob(os.path.join(cfg["audio_root"], "**", "*.WAV"), recursive=True)
            )
            file_events = {p: [] for p in audio_paths}

        self.segments = []
        print(f"[Dataset:{split}] {len(file_events)} ファイルを処理中...")

        for audio_path, events in file_events.items():
            if not os.path.exists(audio_path):
                print(f"  [skip] 見つかりません: {audio_path}")
                continue
            feat = normalize_feature(extract_mic_features(audio_path, cfg))
            segs = segment_feature(feat, cfg["n_frames"])
            has_label = len(events) > 0

            if has_label:
                n_total = cfg["label_frames"] * len(segs)
                full_target = events_to_target(
                    events, n_total, cfg["n_classes"], cfg["n_tracks"],
                    cfg["label_hop_sec"]
                )
                lf = cfg["label_frames"]
                for i, seg_feat in enumerate(segs):
                    seg_tgt = full_target[i * lf:(i + 1) * lf]
                    if seg_tgt.shape[0] < lf:
                        pad = np.zeros((lf - seg_tgt.shape[0], cfg["n_tracks"],
                                        cfg["n_classes"], 3), dtype=np.float32)
                        seg_tgt = np.concatenate([seg_tgt, pad], axis=0)
                    self.segments.append(
                        (seg_feat, seg_tgt, os.path.basename(audio_path), i)
                    )
            else:
                for i, seg_feat in enumerate(segs):
                    self.segments.append(
                        (seg_feat, None, os.path.basename(audio_path), i)
                    )

        print(f"[Dataset:{split}] セグメント総数: {len(self.segments)}")

    def __len__(self):
        return len(self.segments)

    def __getitem__(self, idx):
        feat, target, fname, seg_idx = self.segments[idx]
        if self.augment:
            feat = freq_mask(feat, self.cfg["freq_mask_bins"])
        feat_t = torch.from_numpy(feat)
        if target is not None:
            return feat_t, torch.from_numpy(target), fname, seg_idx
        return feat_t, fname, seg_idx


# =============================================================================
# 5. アーキテクチャ: U-Net (Phase 1)
# =============================================================================

class UNetConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class UNet(nn.Module):
    """
    入力: (B, 8, T, n_mels)  → 出力: (B, 8, T, n_mels) [デノイズ済み]
    """
    def __init__(self, in_ch=8, base_ch=32):
        super().__init__()
        b = base_ch
        self.enc1 = UNetConvBlock(in_ch, b)
        self.enc2 = UNetConvBlock(b,    b*2)
        self.enc3 = UNetConvBlock(b*2,  b*4)
        self.enc4 = UNetConvBlock(b*4,  b*8)
        self.pool = nn.MaxPool2d(2, 2)
        self.bottleneck = UNetConvBlock(b*8, b*16)
        self.up4 = nn.ConvTranspose2d(b*16, b*8, 2, stride=2)
        self.dec4 = UNetConvBlock(b*16, b*8)
        self.up3 = nn.ConvTranspose2d(b*8,  b*4, 2, stride=2)
        self.dec3 = UNetConvBlock(b*8,  b*4)
        self.up2 = nn.ConvTranspose2d(b*4,  b*2, 2, stride=2)
        self.dec2 = UNetConvBlock(b*4,  b*2)
        self.up1 = nn.ConvTranspose2d(b*2,  b,   2, stride=2)
        self.dec1 = UNetConvBlock(b*2,  b)
        self.out_conv = nn.Conv2d(b, in_ch, 1)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        e4 = self.enc4(self.pool(e3))
        bn = self.bottleneck(self.pool(e4))

        def _up_cat(up, df, ef):
            u = up(df)
            if u.shape != ef.shape:
                u = F.interpolate(u, size=ef.shape[2:], mode="bilinear", align_corners=False)
            return torch.cat([u, ef], dim=1)

        d4 = self.dec4(_up_cat(self.up4, bn, e4))
        d3 = self.dec3(_up_cat(self.up3, d4, e3))
        d2 = self.dec2(_up_cat(self.up2, d3, e2))
        d1 = self.dec1(_up_cat(self.up1, d2, e1))
        return self.out_conv(d1), [d1, d2, d3]


# =============================================================================
# 6. アーキテクチャ: SELDnet (Phase 2)
# =============================================================================

class ResidualConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch, dropout=0.3):
        super().__init__()
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1)
        self.bn1   = nn.BatchNorm2d(out_ch)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1)
        self.bn2   = nn.BatchNorm2d(out_ch)
        self.skip  = nn.Conv2d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()
        self.pool  = nn.AdaptiveAvgPool2d((None, 1))
        self.drop  = nn.Dropout(dropout)
        self.act   = nn.ReLU(inplace=True)

    def forward(self, x):
        r = self.skip(x)
        out = self.act(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return self.drop(self.pool(self.act(out + r)))


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, max_len=2000):
        super().__init__()
        pe  = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))

    def forward(self, x):
        return x + self.pe[:, :x.size(1)]


class SELDnet(nn.Module):
    def __init__(self, decoder_channels, n_classes, n_tracks=3,
                 n_heads=4, ff_dim=512, dropout=0.3):
        super().__init__()
        self.n_classes = n_classes
        self.n_tracks  = n_tracks
        base = decoder_channels[0]
        self.align = nn.ModuleList([
            nn.Sequential(nn.ConvTranspose2d(dc, base, 1), nn.ReLU(inplace=True))
            for dc in decoder_channels
        ])
        stem_in = base * len(decoder_channels)
        self.stem = nn.Sequential(
            nn.Conv2d(stem_in, stem_in,     5, padding=2), nn.ReLU(inplace=True),
            nn.Conv2d(stem_in, stem_in * 2, 1),            nn.ReLU(inplace=True),
        )
        rcb_in = stem_in * 2
        self.rcb1 = ResidualConvBlock(rcb_in, 128, dropout)
        self.rcb2 = ResidualConvBlock(128,    128, dropout)
        self.rcb3 = ResidualConvBlock(128,    128, dropout)
        self.pos_enc    = PositionalEncoding(128)
        enc_layer = nn.TransformerEncoderLayer(
            d_model=128, nhead=n_heads, dim_feedforward=ff_dim,
            dropout=dropout, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(enc_layer, num_layers=1)
        self.fc1 = nn.Linear(128, 128)
        self.fc2 = nn.Linear(128, n_tracks * n_classes * 3)

    def forward(self, decoder_feats):
        target_size = decoder_feats[0].shape[2:]
        aligned = []
        for i, f in enumerate(decoder_feats):
            a = self.align[i](f)
            if a.shape[2:] != target_size:
                a = F.interpolate(a, size=target_size, mode="bilinear", align_corners=False)
            aligned.append(a)
        x = self.stem(torch.cat(aligned, dim=1))
        x = self.rcb3(self.rcb2(self.rcb1(x)))
        x = self.transformer(self.pos_enc(x.squeeze(-1).permute(0, 2, 1)))
        x = self.fc2(F.relu(self.fc1(x)))
        B, T, _ = x.shape
        return torch.tanh(x.view(B, T, self.n_tracks, self.n_classes, 3))


# =============================================================================
# 7. 統合モデル
# =============================================================================

class SELDUNet(nn.Module):
    def __init__(self, cfg=CFG):
        super().__init__()
        b = cfg["unet_base_ch"]
        self.unet    = UNet(in_ch=cfg["n_channels"], base_ch=b)
        self.seldnet = SELDnet(
            decoder_channels=[b, b*2, b*4],
            n_classes=cfg["n_classes"],
            n_tracks=cfg["n_tracks"],
        )

    def forward(self, x):
        enhanced, decoder_feats = self.unet(x)
        return enhanced, self.seldnet(decoder_feats)


# =============================================================================
# 8. 損失関数
# =============================================================================

def unet_loss(pred, target):
    """8ch MIC: IV なし → 全チャンネル L1"""
    return F.l1_loss(pred, target)


def adpit_loss(pred, target):
    """ADPIT (Auxiliary Duplicating Permutation Invariant Training)"""
    B, T_pred, N, C, _ = pred.shape
    T = min(T_pred, target.shape[1])
    pred, target = pred[:, :T], target[:, :T]
    total = 0.0
    for c in range(C):
        t_c, p_c = target[:, :, :, c, :], pred[:, :, :, c, :]
        best = None
        for perm in permutations(range(N)):
            mse = ((p_c[:, :, list(perm), :] - t_c) ** 2).mean(dim=(2, 3))
            best = mse if best is None else torch.minimum(best, mse)
        total += best.mean()
    return total / C


# =============================================================================
# 9. 評価指標
# =============================================================================

def cart2sph(x, y, z):
    r = math.sqrt(x**2 + y**2 + z**2)
    if r < 1e-8:
        return 0.0, 0.0
    return (math.degrees(math.atan2(y, x)),
            math.degrees(math.asin(max(-1.0, min(1.0, z / r)))))


def angular_distance(az1, el1, az2, el2):
    az1, el1, az2, el2 = map(math.radians, [az1, el1, az2, el2])
    return math.degrees(math.acos(max(-1.0, min(1.0,
        math.sin(el1)*math.sin(el2) +
        math.cos(el1)*math.cos(el2)*math.cos(az1 - az2)
    ))))


def decode_accdoa(seld_out, threshold=0.5):
    events = []
    T, N, C, _ = seld_out.shape
    for t in range(T):
        for n in range(N):
            for c in range(C):
                vec = seld_out[t, n, c]
                if float(np.linalg.norm(vec)) > threshold:
                    az, el = cart2sph(*vec.tolist())
                    events.append((t, c, az, el))
    return events


class SELDMetrics:
    """
    DCASE2023 準拠の SELD 評価指標。
      ER, F1   : location-dependent (検出性能)
      LE_CD    : class-dependent localization error  (クラスごとに平均)
      LR_CD    : class-dependent localization recall (クラスごとに平均)
      SELD Score = (ER + (1-F1) + LE_CD/180 + (1-LR_CD)) / 4
    """

    def __init__(self, n_classes, doa_threshold=20.0):
        self.C, self.doa_th = n_classes, doa_threshold
        self.reset()

    def reset(self):
        self.TP = self.FP = self.FN = 0
        # クラスごとのカウンタ (LE_CD / LR_CD 用)
        self.cls_loc_err = [0.0] * self.C   # DOA 誤差の合計 (クラス別)
        self.cls_loc_tp  = [0]   * self.C   # DOA 条件付き TP (クラス別)
        self.cls_ref     = [0]   * self.C   # 正解イベント数 (クラス別)

    def update(self, pred_events, ref_events, n_frames):
        def to_dict(ev):
            d = {}
            for fr, cls, az, el in ev:
                d.setdefault((fr, cls), []).append((az, el))
            return d

        pred_d, ref_d = to_dict(pred_events), to_dict(ref_events)
        for key in set(pred_d) | set(ref_d):
            fr, cls = key
            preds, refs = pred_d.get(key, []), ref_d.get(key, [])
            tp = min(len(preds), len(refs))
            self.FP += max(0, len(preds) - len(refs))
            self.FN += max(0, len(refs) - len(preds))
            self.cls_ref[cls] += len(refs)

            doa_tp, used = 0, [False] * len(refs)
            for p_az, p_el in preds:
                for j, (r_az, r_el) in enumerate(refs):
                    if not used[j]:
                        d = angular_distance(p_az, p_el, r_az, r_el)
                        if d <= self.doa_th:
                            doa_tp += 1
                            used[j] = True
                            self.cls_loc_err[cls] += d
                            self.cls_loc_tp[cls]  += 1
                            break
            self.TP += doa_tp
            self.FP += tp - doa_tp
            self.FN += tp - doa_tp

    def compute(self):
        # ER, F1 (location-dependent)
        precision = self.TP / (self.TP + self.FP + 1e-8)
        recall    = self.TP / (self.TP + self.FN + 1e-8)
        F1 = 2 * precision * recall / (precision + recall + 1e-8)
        ER = min((self.FP + self.FN) / (self.TP + self.FN + 1e-8), 1.0)

        # LE_CD : クラスごとの平均 DOA 誤差 → クラス平均
        le_per_cls = [
            self.cls_loc_err[c] / self.cls_loc_tp[c]
            for c in range(self.C) if self.cls_loc_tp[c] > 0
        ]
        LE_CD = sum(le_per_cls) / len(le_per_cls) if le_per_cls else 0.0

        # LR_CD : クラスごとの再現率 → クラス平均
        lr_per_cls = [
            self.cls_loc_tp[c] / self.cls_ref[c] if self.cls_ref[c] > 0 else 0.0
            for c in range(self.C)
        ]
        LR_CD = sum(lr_per_cls) / self.C

        SELD = (ER + (1 - F1) + LE_CD / 180.0 + (1 - LR_CD)) / 4.0
        return {"ER": ER, "F1": F1, "LE_CD": LE_CD, "LR_CD": LR_CD, "SELD": SELD}


# =============================================================================
# 10. 学習ループ
# =============================================================================

def train_phase1(model, loader, optimizer, cfg):
    model.train()
    total = 0.0
    for batch in loader:
        feat = batch[0].to(cfg["device"])
        optimizer.zero_grad()
        enhanced, _ = model(feat)
        loss = unet_loss(enhanced, feat)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        total += loss.item()
    return total / len(loader)


def train_phase2(model, loader, optimizer, cfg, freeze_unet=True):
    model.train()
    for p in model.unet.parameters():
        p.requires_grad = not freeze_unet
    total, skipped = 0.0, 0
    for batch in loader:
        if len(batch) != 4:
            skipped += 1
            continue
        feat, target, _, _ = batch
        feat, target = feat.to(cfg["device"]), target.to(cfg["device"])
        optimizer.zero_grad()
        _, seld_out = model(feat)
        loss = adpit_loss(seld_out, target)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        total += loss.item()
    for p in model.unet.parameters():
        p.requires_grad = True
    return total / max(len(loader) - skipped, 1)


def train(cfg=CFG, skip_phase1=False):
    os.makedirs(cfg["output_dir"], exist_ok=True)

    train_set = UNSESSEDataset(cfg, split=cfg["train_split"], augment=True)
    loader    = DataLoader(train_set, batch_size=cfg["batch_size"],
                           shuffle=True, num_workers=0, drop_last=False)

    model = SELDUNet(cfg).to(cfg["device"])
    print(f"[Model] {sum(p.numel() for p in model.parameters())/1e6:.2f}M パラメータ")

    unet_ckpt = os.path.join(cfg["output_dir"], "unet_best.pt")
    h1 = []

    if skip_phase1 and os.path.exists(unet_ckpt):
        print(f"\n=== Phase 1 スキップ: {unet_ckpt} を使用 ===")
        model.unet.load_state_dict(torch.load(unet_ckpt, map_location=cfg["device"]))
    else:
        print("\n=== Phase 1: U-Net 学習 ===")
        opt1, best1 = torch.optim.Adam(model.unet.parameters(), lr=cfg["lr"]), float("inf")
        for ep in range(cfg["epochs_phase1"]):
            loss = train_phase1(model, loader, opt1, cfg)
            h1.append(loss)
            if loss < best1:
                best1 = loss
                torch.save(model.unet.state_dict(), unet_ckpt)
            if (ep + 1) % 10 == 0:
                print(f"  Epoch {ep+1:3d}/{cfg['epochs_phase1']} | loss={loss:.4f}")
        model.unet.load_state_dict(torch.load(unet_ckpt, map_location=cfg["device"]))

    has_labels = any(len(s) == 4 for s in train_set)
    h2 = []
    if has_labels:
        print("\n=== Phase 2: SELDnet 学習 ===")
        opt2, best2 = torch.optim.Adam(model.seldnet.parameters(), lr=cfg["lr"]), float("inf")
        for ep in range(cfg["epochs_phase2"]):
            loss = train_phase2(model, loader, opt2, cfg, freeze_unet=True)
            h2.append(loss)
            if loss < best2:
                best2 = loss
                torch.save(model.state_dict(),
                           os.path.join(cfg["output_dir"], "seld_unet_best.pt"))
            if (ep + 1) % 10 == 0:
                print(f"  Epoch {ep+1:3d}/{cfg['epochs_phase2']} | loss={loss:.4f}")
    else:
        print("\n[警告] ラベルなし → Phase2 スキップ")
        torch.save(model.state_dict(),
                   os.path.join(cfg["output_dir"], "seld_unet_best.pt"))

    _plot_history(h1, h2, cfg["output_dir"])
    print(f"\n学習完了: {cfg['output_dir']}")


def _plot_history(h1, h2, out_dir):
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    plt.plot(h1); plt.title("Phase1: U-Net Loss (L1)")
    plt.xlabel("Epoch"); plt.ylabel("Loss")
    plt.subplot(1, 2, 2)
    if h2:
        plt.plot(h2); plt.title("Phase2: SELDnet Loss (ADPIT)")
        plt.xlabel("Epoch"); plt.ylabel("Loss")
    else:
        plt.text(0.5, 0.5, "Phase2 skipped", ha="center")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "training_curves.png"))
    plt.close()


# =============================================================================
# 11. 評価 / 推論
# =============================================================================

@torch.no_grad()
def evaluate(cfg=CFG):
    model_path = os.path.join(cfg["output_dir"], "seld_unet_best.pt")
    if not os.path.exists(model_path):
        print(f"[Error] モデルが見つかりません: {model_path}")
        return

    model = SELDUNet(cfg).to(cfg["device"])
    model.load_state_dict(torch.load(model_path, map_location=cfg["device"]))
    model.eval()

    eval_set = UNSESSEDataset(cfg, split=cfg["eval_split"], augment=False)
    loader   = DataLoader(eval_set, batch_size=1, shuffle=False, num_workers=0)
    metrics  = SELDMetrics(cfg["n_classes"])
    results  = {}

    for batch in loader:
        if len(batch) == 4:
            feat, target, fnames, seg_idxs = batch
            target = target.to(cfg["device"])
        else:
            feat, fnames, seg_idxs = batch
            target = None
        feat = feat.to(cfg["device"])
        fname, seg_idx = fnames[0], int(seg_idxs[0])

        _, seld_out = model(feat)
        pred_events = decode_accdoa(seld_out[0].cpu().numpy(), threshold=0.5)
        ref_events  = decode_accdoa(target[0].cpu().numpy(), threshold=0.1) if target is not None else []
        if ref_events:
            metrics.update(pred_events, ref_events, cfg["label_frames"])
        results.setdefault(fname, []).append((seg_idx, pred_events, ref_events))

    print("\n=== SELD 評価結果 (UNS-ESSE2023) ===")
    if any(r[2] for segs in results.values() for r in segs):
        res = metrics.compute()
        print(f"  Error Rate     (ER)  : {res['ER']:.4f}   (↓ 低いほど良い)")
        print(f"  F-score        (F1)  : {res['F1']:.4f}   (↑ 高いほど良い)")
        print(f"  LE_CD               : {res['LE_CD']:.2f} deg (↓ 低いほど良い)")
        print(f"  LR_CD               : {res['LR_CD']:.4f}   (↑ 高いほど良い)")
        print(f"  SELD Score          : {res['SELD']:.4f}   (↓ 低いほど良い)")

        # クラス別スコアも表示
        print("\n  --- クラス別 LE / LR ---")
        for c in range(cfg["n_classes"]):
            le_c = metrics.cls_loc_err[c] / metrics.cls_loc_tp[c] if metrics.cls_loc_tp[c] > 0 else float("nan")
            lr_c = metrics.cls_loc_tp[c] / metrics.cls_ref[c] if metrics.cls_ref[c] > 0 else float("nan")
            print(f"  [{CLASS_NAMES[c]:18s}]  LE={le_c:6.2f} deg  LR={lr_c:.4f}")

        # JSON に保存 (セッション終了後も残る)
        import json
        res_save = dict(res)
        res_save["per_class"] = {
            CLASS_NAMES[c]: {
                "LE": metrics.cls_loc_err[c] / metrics.cls_loc_tp[c] if metrics.cls_loc_tp[c] > 0 else None,
                "LR": metrics.cls_loc_tp[c] / metrics.cls_ref[c] if metrics.cls_ref[c] > 0 else None,
            }
            for c in range(cfg["n_classes"])
        }
        res_save["cfg"] = {k: v for k, v in cfg.items() if isinstance(v, (int, float, str, bool))}
        out_json = os.path.join(cfg["output_dir"], "eval_results.json")
        with open(out_json, "w") as f:
            json.dump(res_save, f, indent=2, ensure_ascii=False)
        print(f"\n  結果を保存しました: {out_json}")
    else:
        print("  ラベルなし → メトリクス計算スキップ")

    _visualize_results(results, cfg)
    return results


@torch.no_grad()
def infer(cfg=CFG):
    model_path = os.path.join(cfg["output_dir"], "seld_unet_best.pt")
    if not os.path.exists(model_path):
        print(f"[Error] モデルが見つかりません: {model_path}")
        return

    model = SELDUNet(cfg).to(cfg["device"])
    model.load_state_dict(torch.load(model_path, map_location=cfg["device"]))
    model.eval()

    audio_paths = sorted(
        glob.glob(os.path.join(cfg["audio_root"], "**", "*.wav"), recursive=True) +
        glob.glob(os.path.join(cfg["audio_root"], "**", "*.WAV"), recursive=True)
    )
    dataset = UNSESSEDataset(cfg, split=None, audio_paths_override=audio_paths)
    loader  = DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0)

    os.makedirs(os.path.join(cfg["output_dir"], "predictions"), exist_ok=True)
    all_results = {}

    for batch in loader:
        feat, fnames, seg_idxs = batch
        feat = feat.to(cfg["device"])
        fname, seg_i = fnames[0], int(seg_idxs[0])
        _, seld_out = model(feat)
        pred_events = decode_accdoa(seld_out[0].cpu().numpy(), threshold=0.5)
        all_results.setdefault(fname, []).append((seg_i, pred_events))

    for fname, segs in all_results.items():
        segs.sort(key=lambda x: x[0])
        out_csv = os.path.join(cfg["output_dir"], "predictions",
                               os.path.splitext(fname)[0] + ".csv")
        with open(out_csv, "w") as f:
            f.write("onset_sec,offset_sec,class_idx,class_name,azimuth_deg,elevation_deg\n")
            for seg_i, events in segs:
                t_off = seg_i * cfg["clip_duration"]
                for (fr, cls, az, el) in events:
                    onset  = t_off + fr * cfg["label_hop_sec"]
                    offset = onset + cfg["label_hop_sec"]
                    cname  = CLASS_NAMES[cls] if cls < len(CLASS_NAMES) else str(cls)
                    f.write(f"{onset:.3f},{offset:.3f},{cls},{cname},{az:.1f},{el:.1f}\n")
        print(f"  予測 CSV: {out_csv}")

    _visualize_results(
        {k: [(s, ev, []) for s, ev in v] for k, v in all_results.items()}, cfg
    )


def _visualize_results(results_per_file, cfg):
    os.makedirs(os.path.join(cfg["output_dir"], "figures"), exist_ok=True)
    C = cfg["n_classes"]

    for fname, seg_list in results_per_file.items():
        seg_list = sorted(seg_list, key=lambda x: x[0])
        total_frames = len(seg_list) * cfg["label_frames"]
        pred_map = np.zeros((C, total_frames))
        ref_map  = np.zeros((C, total_frames))

        for i, item in enumerate(seg_list):
            offset = i * cfg["label_frames"]
            for (fr, cls, az, el) in item[1]:
                if fr + offset < total_frames and cls < C:
                    pred_map[cls, fr + offset] = 1
            for (fr, cls, az, el) in (item[2] if len(item) > 2 else []):
                if fr + offset < total_frames and cls < C:
                    ref_map[cls, fr + offset] = 1

        has_ref = ref_map.sum() > 0
        fig, axes = plt.subplots(2 if has_ref else 1, 1,
                                 figsize=(14, 4 * (2 if has_ref else 1)))
        if not has_ref:
            axes = [axes]

        for ax, data, title, cmap in zip(
            axes,
            [pred_map] + ([ref_map] if has_ref else []),
            [f"予測: {fname}"] + ([f"正解: {fname}"] if has_ref else []),
            ["Blues", "Reds"]
        ):
            ax.imshow(data, aspect="auto", origin="lower", cmap=cmap, vmin=0, vmax=1)
            ax.set_title(title)
            ax.set_xlabel("フレーム")
            ax.set_yticks(range(C))
            ax.set_yticklabels(CLASS_NAMES[:C])

        plt.tight_layout()
        plt.savefig(os.path.join(cfg["output_dir"], "figures",
                                 os.path.splitext(fname)[0] + "_seld.png"), dpi=100)
        plt.close()


# =============================================================================
# 12. サンプルデータ生成 (demo モード用)
# =============================================================================

def generate_sample_data(cfg=CFG, n_files=6, duration=10.0):
    """
    動作確認用の合成 8ch マイクアレイ音声 + meta.events.csv を生成する。
    """
    audio_dir = cfg["audio_root"]
    meta_dir  = os.path.dirname(cfg["meta_csv"])
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(meta_dir,  exist_ok=True)

    fs       = cfg["fs"]
    n_samp   = int(duration * fs)
    t        = np.linspace(0, duration, n_samp, endpoint=False)
    n_spk    = 8   # 円形配置の仮想スピーカー数

    # クラスごとの音響特性
    class_params = {
        0: {"freq": 80,   "dur": (0.3, 1.5), "amp": 0.5},  # boom
        1: {"freq": 200,  "dur": (0.05, 0.3), "amp": 0.6}, # gunshot
        2: {"freq": 3000, "dur": (0.2, 0.8), "amp": 0.3},  # shatter
    }

    rows = []
    for i in range(n_files):
        audio  = np.zeros((n_samp, 8), dtype=np.float32)
        splt   = "train" if i < n_files * 0.6 else ("val" if i < n_files * 0.8 else "eval")
        events = []

        for _ in range(np.random.randint(1, 3)):
            cls     = np.random.randint(0, cfg["n_classes"])
            p       = class_params[cls]
            dur     = np.random.uniform(*p["dur"])
            onset   = np.random.uniform(1.0, max(1.1, duration - dur - 1.0))
            offset  = min(onset + dur, duration - 0.1)
            spk_idx = np.random.randint(0, n_spk)
            az      = spk_idx * (360 / n_spk)   # 0, 45, 90, ... 315 deg

            mask = (t >= onset) & (t <= offset)
            sig  = p["amp"] * mask * np.sin(2 * np.pi * p["freq"] * t)
            audio[:, spk_idx] += sig

            events.append((onset, offset, cls, az))
            rows.append({
                "filename":   f"audio/demo_sample_{i:03d}.wav",
                "event_onset":  f"{onset:.3f}",
                "event_offset": f"{offset:.3f}",
                "event_label":  CLASS_NAMES[cls],
                "azimuth":      f"{az:.1f}",
                "event_elevation": "0",
                "event_distance": "5",
                "set":          splt,
                "snr": "0", "spl_before": "0", "spl_after": "0", "identifier": "demo",
            })

        # 環境ノイズ追加
        audio += 0.03 * np.random.randn(*audio.shape).astype(np.float32)
        audio  = np.clip(audio, -1.0, 1.0)
        sf.write(os.path.join(audio_dir, f"demo_sample_{i:03d}.wav"), audio, fs, subtype="PCM_16")

    # meta.events.csv 生成
    fieldnames = ["filename","event_onset","event_offset","event_label",
                  "azimuth","event_elevation","event_distance",
                  "set","snr","spl_before","spl_after","identifier"]
    with open(cfg["meta_csv"], "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"サンプルデータ生成完了: {n_files} ファイル → {audio_dir}")
    print(f"meta.events.csv → {cfg['meta_csv']}")


# =============================================================================
# 13. エントリポイント
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SELD U-Net for UNS-ESSE2023")
    parser.add_argument("--mode", choices=["train", "eval", "infer", "demo"],
                        default="demo")
    parser.add_argument("--data_root",   default=None, help="Zenodo 解凍後のルート")
    parser.add_argument("--audio_root",  default=None)
    parser.add_argument("--meta_csv",    default=None, help="meta.events.csv のパス")
    parser.add_argument("--output_dir",  default=None)
    parser.add_argument("--train_split", default=None, help="学習に使う set 値 (例: train)")
    parser.add_argument("--eval_split",  default=None, help="評価に使う set 値 (例: eval)")
    parser.add_argument("--epochs_p1",   type=int, default=None)
    parser.add_argument("--epochs_p2",   type=int, default=None)
    parser.add_argument("--skip_phase1", action="store_true",
                        help="Phase1 をスキップして保存済み unet_best.pt から Phase2 を実行")
    args = parser.parse_args()

    if args.data_root:   CFG["data_root"]      = args.data_root
    if args.audio_root:  CFG["audio_root"]      = args.audio_root
    if args.meta_csv:    CFG["meta_csv"]         = args.meta_csv
    if args.output_dir:  CFG["output_dir"]       = args.output_dir
    if args.train_split: CFG["train_split"]      = args.train_split
    if args.eval_split:  CFG["eval_split"]       = args.eval_split
    if args.epochs_p1:   CFG["epochs_phase1"]    = args.epochs_p1
    if args.epochs_p2:   CFG["epochs_phase2"]    = args.epochs_p2

    os.makedirs(CFG["output_dir"], exist_ok=True)

    if args.mode == "demo":
        print("=" * 60)
        print("DEMO: UNS-ESSE2023 合成データで動作確認")
        print(f"Classes: {CLASS_NAMES}")
        print("=" * 60)
        CFG["batch_size"] = 2
        if not args.epochs_p1: CFG["epochs_phase1"] = 5
        if not args.epochs_p2: CFG["epochs_phase2"] = 5
        generate_sample_data(CFG, n_files=9, duration=10.0)
        train(CFG)
        evaluate(CFG)

    elif args.mode == "train":
        print("=" * 60)
        print(f"学習 | split={CFG['train_split']} | meta={CFG['meta_csv']}")
        if args.skip_phase1:
            print("  ※ Phase1 スキップ (unet_best.pt から再開)")
        print("=" * 60)
        train(CFG, skip_phase1=args.skip_phase1)

    elif args.mode == "eval":
        print("=" * 60)
        print(f"評価 | split={CFG['eval_split']}")
        print("=" * 60)
        evaluate(CFG)

    elif args.mode == "infer":
        print("=" * 60)
        print(f"推論 | audio={CFG['audio_root']}")
        print("=" * 60)
        infer(CFG)
