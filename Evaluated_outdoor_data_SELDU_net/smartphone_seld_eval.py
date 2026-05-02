"""
smartphone_seld_eval.py
=======================
スマホ音声（モノラル/ステレオ）で SELD U-Net の SED 性能を評価するスクリプト。

DOA（方向推定）はスマホでは不可能なため、SED（いつ・何が鳴っているか）のみを評価します。
モノラル音声を全4チャンネルに複製して疑似 FOA を生成し、学習済み seld_unet_best.pt を使用します。

【使い方】
  # 1ファイル推論（ラベルなし）
  python smartphone_seld_eval.py --audio recording.wav

  # フォルダ内の全 WAV を一括処理
  python smartphone_seld_eval.py --audio_dir ./phone_recordings

  # ラベル CSV で SED 評価指標も計算
  python smartphone_seld_eval.py --audio recording.wav --label recording.csv

【ラベル CSV フォーマット】
  onset_sec, offset_sec, class_idx
  0.5, 2.3, 0
  3.1, 5.8, 2

  ※ project1.py の 5列形式 (onset,offset,class,az,el) も読み込み可能です。
"""

import os
import sys
import glob
import math
import argparse
import warnings
import numpy as np
import soundfile as sf
import librosa
import torch
import torch.nn.functional as F
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# project1.py からモデルアーキテクチャをインポート
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import project1  # SELDUNet, CFG

BASE_CFG = project1.CFG  # n_fft, hop_length, n_mels, fs, n_classes, … を流用

# ============================================================
# 追加設定
# ============================================================
PHONE_CFG = {
    "model_path":    os.path.join(_HERE, "output", "seld_unet_best.pt"),
    "output_dir":    os.path.join(_HERE, "output_smartphone_seld"),
    "sed_threshold": 0.5,    # ACCDOA ベクトルのノルムがこの値以上で音イベントあり
    "min_event_sec": 0.05,   # これより短いイベントは除去（秒）
    "doa_threshold": 20.0,   # DOA 正解判定閾値（度）-- ラベルに az/el がある場合のみ使用
}

# 音響フレームの時間分解能 (秒/フレーム)
FRAME_HOP_SEC = BASE_CFG["hop_length"] / BASE_CFG["fs"]


# ============================================================
# 特徴量抽出 (スマホ音声 → 疑似 FOA → 7ch 特徴)
# ============================================================

def load_smartphone_audio(path: str) -> tuple[np.ndarray, int]:
    """スマホ WAV/m4a を読み込み、モノラル float32 に変換する。"""
    audio, sr = sf.read(path, always_2d=True)
    mono = audio.mean(axis=1).astype(np.float32)
    return mono, sr


def mono_to_pseudo_foa(mono: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    """
    モノラル音声 → 疑似 4ch FOA (W=X=Y=Z=mono)。

    ゼロパディングより全 4ch に信号を持たせることで、
    mel 特徴量 4ch が有効になり IV も非ゼロになる。
    DOA 情報は乗らないが SED 側の活性化は改善される。

    Returns:
        audio_4ch: (4, samples) float32
    """
    if sr != target_sr:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=target_sr)
    # W=X=Y=Z=mono に複製
    return np.stack([mono, mono, mono, mono], axis=0)  # (4, samples)


def extract_features(audio_4ch: np.ndarray, cfg: dict) -> np.ndarray:
    """
    4ch 音声 → 7ch 特徴量 (mel×4 + IV×3)。
    project1.extract_foa_features と同ロジック。

    Returns:
        feat: (7, T, n_mels) float32
    """
    n_fft    = cfg["n_fft"]
    hop      = cfg["hop_length"]
    n_mels   = cfg["n_mels"]
    fs       = cfg["fs"]

    stfts = [
        librosa.stft(audio_4ch[c].astype(np.float32),
                     n_fft=n_fft, hop_length=hop,
                     win_length=n_fft, window="hann")
        for c in range(4)
    ]
    W, X, Y, Z = stfts

    mel_basis = librosa.filters.mel(sr=fs, n_fft=n_fft, n_mels=n_mels)

    mel_feats = []
    for stft in stfts:
        power  = np.abs(stft) ** 2
        mel    = mel_basis @ power
        mel_db = librosa.power_to_db(mel, ref=np.max)
        mel_feats.append(mel_db)

    W_conj = np.conj(W)
    iv_x   = mel_basis @ np.real(W_conj * X)
    iv_y   = mel_basis @ np.real(W_conj * Y)
    iv_z   = mel_basis @ np.real(W_conj * Z)

    feat = np.stack(mel_feats + [iv_x, iv_y, iv_z], axis=0)  # (7, n_mels, T)
    feat = feat.transpose(0, 2, 1)                             # (7, T, n_mels)
    return feat.astype(np.float32)


# ============================================================
# SED デコード (ACCDOA ベクトルノルムで判定)
# ============================================================

def decode_sed(seld_out: np.ndarray, threshold: float, frame_hop_sec: float,
               min_event_sec: float, n_classes: int) -> list[tuple]:
    """
    ACCDOA 出力から SED イベントリストを生成する。
    DOA（方向）は無視し、ベクトルノルムのみで音イベントを判定する。

    Args:
        seld_out: (T, n_tracks, n_classes, 3)

    Returns:
        events: [(onset_sec, offset_sec, class_idx), ...]
    """
    T, N, C, _ = seld_out.shape
    # トラックを OR 統合: クラスcが1つでもアクティブなら検出
    active = np.zeros((T, C), dtype=bool)
    for n in range(N):
        norms = np.linalg.norm(seld_out[:, n, :, :], axis=-1)  # (T, C)
        active |= (norms >= threshold)

    events = []
    min_frames = max(1, int(min_event_sec / frame_hop_sec))

    for c in range(n_classes):
        in_event = False
        onset_fr = 0
        for t in range(T):
            if active[t, c] and not in_event:
                in_event = True
                onset_fr = t
            elif not active[t, c] and in_event:
                in_event = False
                dur_fr = t - onset_fr
                if dur_fr >= min_frames:
                    events.append((onset_fr * frame_hop_sec,
                                   t * frame_hop_sec, c))
        if in_event:
            dur_fr = T - onset_fr
            if dur_fr >= min_frames:
                events.append((onset_fr * frame_hop_sec,
                               T * frame_hop_sec, c))

    events.sort(key=lambda e: e[0])
    return events


# ============================================================
# ラベル読み込み
# ============================================================

def load_label(csv_path: str, n_classes: int) -> list[tuple]:
    """
    CSV → [(onset_sec, offset_sec, class_idx), ...]
    3列 (onset,offset,class) または 5列 (onset,offset,class,az,el) を受け付ける。
    """
    if not csv_path or not os.path.exists(csv_path):
        return []
    events = []
    with open(csv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("onset"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                onset  = float(parts[0])
                offset = float(parts[1])
                cls    = int(parts[2])
                if 0 <= cls < n_classes:
                    events.append((onset, offset, cls))
            except ValueError:
                continue
    return events


# ============================================================
# SED 評価指標 (イベントベース)
# ============================================================

def compute_sed_metrics(pred_events: list, ref_events: list,
                        collar: float = 0.25) -> dict:
    """
    イベントベースの F1-score と Error Rate を計算する。
    collar: onset/offset それぞれの許容誤差（秒）
    """
    # クラスごとに集計
    all_classes = set(c for *_, c in pred_events) | set(c for *_, c in ref_events)
    TP = FP = FN = 0

    for cls in all_classes:
        preds = [(o, f) for o, f, c in pred_events if c == cls]
        refs  = [(o, f) for o, f, c in ref_events  if c == cls]

        matched = [False] * len(refs)
        for p_on, p_off in preds:
            hit = False
            for j, (r_on, r_off) in enumerate(refs):
                if not matched[j]:
                    if (abs(p_on - r_on) <= collar and
                            abs(p_off - r_off) <= collar):
                        matched[j] = True
                        hit = True
                        break
            TP += hit
            FP += not hit
        FN += sum(1 for m in matched if not m)

    precision = TP / (TP + FP + 1e-8)
    recall    = TP / (TP + FN + 1e-8)
    F1        = 2 * precision * recall / (precision + recall + 1e-8)
    ER        = (FP + FN) / (TP + FN + 1e-8)

    return {"F1": F1, "ER": min(ER, 1.0), "TP": TP, "FP": FP, "FN": FN}


# ============================================================
# 推論
# ============================================================

@torch.no_grad()
def infer_file(audio_path: str, model, cfg: dict, label_path: str = None) -> dict:
    """
    1ファイルを推論し、SED イベントリストと評価指標を返す。
    """
    mono, sr = load_smartphone_audio(audio_path)
    audio_4ch = mono_to_pseudo_foa(mono, sr, cfg["fs"])

    total_dur = audio_4ch.shape[1] / cfg["fs"]

    feat      = extract_features(audio_4ch, cfg)
    feat      = project1.normalize_feature(feat)
    segments  = project1.segment_feature(feat, cfg["n_frames"])

    model.eval()
    all_events: list[tuple] = []
    frame_offset = 0

    for seg_feat in segments:
        x = torch.from_numpy(seg_feat).unsqueeze(0).to(cfg["device"])  # (1,7,T,M)
        _, seld_out = model(x)   # (1, T, n_tracks, n_classes, 3)
        seld_np = seld_out[0].cpu().numpy()  # (T, n_tracks, n_classes, 3)

        seg_events = decode_sed(
            seld_np,
            threshold    = PHONE_CFG["sed_threshold"],
            frame_hop_sec= FRAME_HOP_SEC,
            min_event_sec= PHONE_CFG["min_event_sec"],
            n_classes    = cfg["n_classes"],
        )
        time_offset = frame_offset * FRAME_HOP_SEC
        for onset, offset, cls in seg_events:
            all_events.append((onset + time_offset, offset + time_offset, cls))
        frame_offset += seld_np.shape[0]

    # ラベル読み込み
    ref_events = load_label(label_path, cfg["n_classes"])

    # SED 評価指標
    metrics = None
    if ref_events:
        metrics = compute_sed_metrics(all_events, ref_events)

    return {
        "pred_events": all_events,
        "ref_events":  ref_events,
        "metrics":     metrics,
        "total_dur":   total_dur,
        "n_frames":    frame_offset,
    }


# ============================================================
# 可視化
# ============================================================

def visualize(result: dict, cfg: dict, out_path: str, title: str = ""):
    """
    予測イベント（青）と正解イベント（赤）を time×class で描画する。
    """
    pred_events = result["pred_events"]
    ref_events  = result["ref_events"]
    total_dur   = result["total_dur"]
    n_cls       = cfg["n_classes"]
    has_ref     = len(ref_events) > 0

    n_rows = 2 if has_ref else 1
    fig, axes = plt.subplots(n_rows, 1,
                             figsize=(14, 4 * n_rows),
                             squeeze=False)

    def draw_events(ax, events, color, label):
        ax.set_xlim(0, total_dur)
        ax.set_ylim(-0.5, n_cls - 0.5)
        ax.set_yticks(range(n_cls))
        ax.set_yticklabels([f"class {i}" for i in range(n_cls)], fontsize=8)
        ax.set_xlabel("時間 (秒)")
        ax.set_title(label, fontsize=9)
        ax.grid(axis="x", alpha=0.3)
        for onset, offset, cls in events:
            ax.barh(cls, offset - onset, left=onset,
                    height=0.6, color=color, alpha=0.75)

    draw_events(axes[0][0], pred_events, "steelblue",
                f"予測 SED イベント (SELD U-Net): {title}")
    if has_ref:
        draw_events(axes[1][0], ref_events, "firebrick",
                    f"正解 SED イベント: {title}")

    plt.tight_layout()
    plt.savefig(out_path, dpi=110)
    plt.close()
    print(f"  可視化保存: {out_path}")


# ============================================================
# 結果の保存
# ============================================================

def save_csv(result: dict, out_path: str):
    with open(out_path, "w") as f:
        f.write("onset_sec,offset_sec,class_idx\n")
        for onset, offset, cls in result["pred_events"]:
            f.write(f"{onset:.3f},{offset:.3f},{cls}\n")
    print(f"  イベント CSV: {out_path}")


def print_result(fname: str, result: dict):
    print(f"\n--- {fname} ---")
    if result["pred_events"]:
        for onset, offset, cls in result["pred_events"]:
            print(f"  {onset:6.2f}s ~ {offset:6.2f}s  class={cls}")
    else:
        print("  (検出イベントなし)")

    m = result["metrics"]
    if m:
        print(f"\n  [SED 評価指標]")
        print(f"  F1-score   : {m['F1']:.4f}")
        print(f"  Error Rate : {m['ER']:.4f}")
        print(f"  TP / FP / FN : {m['TP']} / {m['FP']} / {m['FN']}")


# ============================================================
# エントリポイント
# ============================================================

def build_model(cfg: dict):
    model = project1.SELDUNet(cfg).to(cfg["device"])
    mp = PHONE_CFG["model_path"]
    if not os.path.exists(mp):
        print(f"[警告] モデルが見つかりません: {mp}")
        print("  ランダム重みで推論します（精度は低い）")
    else:
        model.load_state_dict(
            torch.load(mp, map_location=cfg["device"])
        )
        print(f"  モデル読み込み: {mp}")
    model.eval()
    return model


def run_single(audio_path: str, label_path: str, cfg: dict, model=None):
    if model is None:
        model = build_model(cfg)

    os.makedirs(PHONE_CFG["output_dir"], exist_ok=True)
    result = infer_file(audio_path, model, cfg, label_path)

    base    = os.path.splitext(os.path.basename(audio_path))[0]
    out_csv = os.path.join(PHONE_CFG["output_dir"], base + "_events.csv")
    out_fig = os.path.join(PHONE_CFG["output_dir"], base + "_result.png")

    save_csv(result, out_csv)
    visualize(result, cfg, out_fig, title=os.path.basename(audio_path))
    print_result(os.path.basename(audio_path), result)
    return result


def run_dir(audio_dir: str, label_dir: str, cfg: dict):
    model = build_model(cfg)
    wav_files = sorted(
        glob.glob(os.path.join(audio_dir, "*.wav")) +
        glob.glob(os.path.join(audio_dir, "*.WAV")) +
        glob.glob(os.path.join(audio_dir, "*.m4a"))
    )
    if not wav_files:
        print(f"[エラー] 音声ファイルが見つかりません: {audio_dir}")
        return

    print(f"{len(wav_files)} ファイルを処理します")
    all_metrics = []
    for wav_p in wav_files:
        base  = os.path.splitext(os.path.basename(wav_p))[0]
        label = None
        if label_dir:
            for ext in [".csv"]:
                cand = os.path.join(label_dir, base + ext)
                if os.path.exists(cand):
                    label = cand
                    break
        result = run_single(wav_p, label, cfg, model)
        if result["metrics"]:
            all_metrics.append(result["metrics"])

    if all_metrics:
        avg_F1 = np.mean([m["F1"] for m in all_metrics])
        avg_ER = np.mean([m["ER"] for m in all_metrics])
        print(f"\n=== 全ファイル平均 ===")
        print(f"  F1-score   : {avg_F1:.4f}")
        print(f"  Error Rate : {avg_ER:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="スマホ音声で SELD U-Net の SED を評価")
    parser.add_argument("--audio",      default=None, help="1ファイルの音声パス")
    parser.add_argument("--audio_dir",  default=None, help="音声ディレクトリ（一括処理）")
    parser.add_argument("--label",      default=None, help="ラベル CSV（1ファイル）")
    parser.add_argument("--label_dir",  default=None, help="ラベルディレクトリ")
    parser.add_argument("--model",      default=None, help="モデルパス（省略時: output/seld_unet_best.pt）")
    parser.add_argument("--threshold",  type=float, default=None, help="SED 閾値（デフォルト: 0.5）")
    parser.add_argument("--n_classes",  type=int,   default=None, help="クラス数（デフォルト: project1.CFG 準拠）")
    args = parser.parse_args()

    cfg = dict(BASE_CFG)  # project1.CFG のコピー
    if args.model:
        PHONE_CFG["model_path"] = args.model
    if args.threshold:
        PHONE_CFG["sed_threshold"] = args.threshold
    if args.n_classes:
        cfg["n_classes"] = args.n_classes

    os.makedirs(PHONE_CFG["output_dir"], exist_ok=True)

    if args.audio:
        run_single(args.audio, args.label, cfg)
    elif args.audio_dir:
        run_dir(args.audio_dir, args.label_dir, cfg)
    else:
        print("引数が必要です。")
        parser.print_help()
