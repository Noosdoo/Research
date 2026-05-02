"""
SELD U-Net for UNS-ESSE2023  (v3)
===================================
Model  : "SELD U-Net: Joint Optimization of Sound Event Localization and
          Detection With Noise Reduction" (IEEE Access, 2023)
Dataset: UNS-Exterior Spatial Sound Events 2023
         DOI: 10.5281/zenodo.10792703
Ref code: https://github.com/sharathadavanne/seld-net

━━━ 元論文との相違点（変更が必要な箇所） ━━━━━━━━━━━━━━━━━━
  [データ]
  ✗ 入力: 4ch FOA B-format (論文) → 8ch MIC アレイ (UNS-ESSE2023)
  ✗ 特徴量: mel×4 + IV×3 = 7ch (論文) → mel×8 + GCC-PHAT×7 = 15ch
  ✗ IV 損失重み λ=10 (論文) → GCC-PHAT に IV なし、全均等 L1
  ✗ データ: 合成 FOA (DCASE2022) → 実録音 MIC (UNS-ESSE2023)
  ✗ クラス数: 14 (DCASE) → 3 (boom/gunshot/shatter)
  [学習]
  ✗ エポック: 1000 (論文) → 100 (Colab 時間制約)
  ✗ バッチサイズ: 128 (論文) → 16 (Colab メモリ制約)
  ✗ Phase 2 損失: 通常 ADPIT → 活性フレーム重み付き ADPIT (trivial solution 防止)
  [出力]
  ✗ n_classes=14 (論文) → n_classes=3 (UNS-ESSE2023 の3クラス)

━━━ 元論文との共通点 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✓ 2 フェーズ学習（Phase1: U-Net, Phase2: SELDnet）
  ✓ U-Net アーキテクチャ（4 段エンコーダ・デコーダ + スキップ接続）
  ✓ SELDnet: RCB×3 + Transformer エンコーダ + FC
  ✓ ACCDOA 出力形式（方向余弦ベクトル）
  ✓ ADPIT 損失（Permutation Invariant Training）
  ✓ Nesterov momentum Adam オプティマイザ
  ✓ 周波数マスク augmentation（8 mel-bin）
  ✓ Phase2 で U-Net 重みを固定

━━━ 評価指標 (DCASE2023 標準準拠) ━━━━━━━━━━━━━━━━━━━━━
  ✓ ER  = max(FP, FN) / (TP + FN)   ← 上限なし、2重カウントなし
  ✓ F1  = 2PR/(P+R)  (20° 閾値 TP)
  ✓ LE_CD = ハンガリアン法で最適マッチング（閾値なし）
  ✓ LR_CD = ハンガリアン法ベース再現率

━━━ 動作モード ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python uns_esse2023_seld_unet_v3.py --mode train
  python uns_esse2023_seld_unet_v3.py --mode eval
  python uns_esse2023_seld_unet_v3.py --mode demo
"""

import os, csv, math, glob, json, argparse, warnings
import numpy as np
import soundfile as sf
import librosa
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from scipy.optimize import linear_sum_assignment
from itertools import permutations
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

# =============================================================================
# 1. 設定  (parameter.py 相当)
# =============================================================================

CLASS_NAMES = ["boom", "gunshot_gunfire", "shatter"]
CLASS_MAP   = {"boom": 0, "gunshot": 1, "gunfire": 1,
               "gunshot_gunfire": 1, "shatter": 2}

CFG = {
    # ── データ ──────────────────────────────────────────────────────
    "data_root":    "./data",
    "meta_csv":     "./data/meta.events.csv",
    "output_dir":   "./output_v3",
    "train_split":  "train",
    "eval_split":   "eval",

    # ── 音響特徴量 (論文: nfft=1024, hop=512, n_mels=64) ──────────
    "fs":           24000,          # 48kHz → 24kHz リサンプル
    "nfft":         1024,           # 論文準拠
    "hop_len":      512,            # 論文準拠
    "n_mels":       64,             # 論文準拠
    "n_channels":   15,             # mel×8 + GCC-PHAT×7 (MIC 適応)

    # ── セグメント ────────────────────────────────────────────────
    "clip_duration":  10.0,
    "label_hop_sec":  0.1,

    # ── モデル ────────────────────────────────────────────────────
    "n_classes":    3,              # UNS-ESSE2023 (論文は 14)
    "n_tracks":     1,              # 論文準拠 (最大1音源同時発生を想定)
    "unet_base_ch": 32,            # U-Net 基本チャンネル数

    # ── 学習 (論文: batch=128, epochs=1000, NAdam, lr=1e-3) ────────
    "lr":           1e-3,           # 論文準拠
    "batch_size":   16,             # Colab メモリ制約 (論文は 128)
    "epochs_p1":    100,            # 論文は 1000, 時間制約で短縮
    "epochs_p2":    100,            # 論文は 1000, 時間制約で短縮
    "iv_weight":    1.0,            # MIC: IV なし → 全均等 (論文は λ=10)
    "active_weight": 10.0,          # 活性フレーム重み (trivial solution 防止)
    "freq_mask_bins": 8,            # 論文準拠

    # ── デバイス ─────────────────────────────────────────────────
    "device": "cuda" if torch.cuda.is_available() else "cpu",
}

CFG["n_frames"]     = int(CFG["clip_duration"] * CFG["fs"] / CFG["hop_len"])
CFG["label_frames"] = int(CFG["clip_duration"] / CFG["label_hop_sec"])

print(f"Device : {CFG['device']}")
print(f"Classes: {CLASS_NAMES}")
print(f"n_ch={CFG['n_channels']} (8mel+7GCC)  n_frames={CFG['n_frames']}  "
      f"label_frames={CFG['label_frames']}")

# =============================================================================
# 2. 特徴量抽出  (cls_feature_class.py 相当)
# =============================================================================

def _load_8ch(path, fs):
    audio, sr = sf.read(path, always_2d=True)
    n = min(audio.shape[1], 8)
    audio = audio[:, :n].T
    if n < 8:
        audio = np.concatenate([audio, np.zeros((8-n, audio.shape[1]))], 0)
    if sr != fs:
        audio = np.stack([librosa.resample(audio[c], orig_sr=sr, target_sr=fs)
                          for c in range(8)])
    return audio.astype(np.float32)


def extract_features(path, cfg=CFG):
    """
    8ch MIC → (15, T, n_mels)
      ・8ch mel spectrograms (振幅情報)
      ・7ch mel-scale GCC-PHAT  mic0 vs mic1-7 (空間情報)
    """
    audio     = _load_8ch(path, cfg["fs"])
    mel_basis = librosa.filters.mel(sr=cfg["fs"], n_fft=cfg["nfft"],
                                    n_mels=cfg["n_mels"])
    mel_feats, stfts = [], []
    for c in range(8):
        S = librosa.stft(audio[c], n_fft=cfg["nfft"], hop_length=cfg["hop_len"],
                         win_length=cfg["nfft"], window="hann")
        mel_feats.append(librosa.power_to_db(mel_basis @ np.abs(S)**2, ref=np.max))
        stfts.append(S)

    gcc_feats = []
    for c in range(1, 8):
        R = stfts[0] * np.conj(stfts[c])
        R_norm = R / (np.abs(R) + 1e-8)
        gcc_feats.append(mel_basis @ np.real(R_norm))

    feat = np.stack(mel_feats + gcc_feats, 0)   # (15, n_mels, T)
    return feat.transpose(0, 2, 1).astype(np.float32)  # (15, T, n_mels)


def normalize(feat):
    out = np.zeros_like(feat)
    for c in range(feat.shape[0]):
        mn, mx = feat[c].min(), feat[c].max()
        out[c] = (feat[c]-mn)/(mx-mn) if mx-mn > 1e-8 else feat[c]-mn
    return out


def freq_mask(feat, max_bins=8):
    f = np.random.randint(0, max_bins+1)
    if f == 0: return feat
    f0 = np.random.randint(0, feat.shape[-1]-f+1)
    feat = feat.copy(); feat[:, :, f0:f0+f] = 0.; return feat


def segment(feat, n_frames):
    segs = []
    for s in range(0, feat.shape[1], n_frames):
        seg = feat[:, s:s+n_frames, :]
        if seg.shape[1] < n_frames:
            pad = np.zeros((feat.shape[0], n_frames-seg.shape[1], feat.shape[2]),
                           dtype=np.float32)
            seg = np.concatenate([seg, pad], 1)
        segs.append(seg)
    return segs

# =============================================================================
# 3. アノテーション  (cls_feature_class.py 相当)
# =============================================================================

def load_meta_csv(meta_csv, split, data_root):
    events = {}
    if not os.path.exists(meta_csv): return events
    with open(meta_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row.get("set","").strip() != split: continue
            cls = CLASS_MAP.get(row["event_label"].strip().lower())
            if cls is None: continue
            fname = row["filename"].strip().replace("\\","/")
            ap    = os.path.normpath(os.path.join(data_root, fname))
            az    = float(row.get("event_azimuth", row.get("azimuth","0")))
            el    = float(row.get("event_elevation","0"))
            events.setdefault(ap,[]).append((float(row["event_onset"]),
                                             float(row["event_offset"]),
                                             cls, az, el))
    return events


def events_to_target(events, n_frames, n_classes, n_tracks, hop):
    """イベントリスト → ACCDOA ターゲット (n_frames, n_tracks, n_classes, 3)"""
    tgt = np.zeros((n_frames, n_tracks, n_classes, 3), np.float32)
    for onset, offset, cls, az, el in events:
        if cls >= n_classes: continue
        az_r, el_r = math.radians(az), math.radians(el)
        vec = [math.cos(el_r)*math.cos(az_r),
               math.cos(el_r)*math.sin(az_r),
               math.sin(el_r)]
        for fr in range(int(onset/hop), min(int(offset/hop), n_frames)):
            for tr in range(n_tracks):
                if np.sum(np.abs(tgt[fr,tr,cls])) == 0:
                    tgt[fr,tr,cls] = vec; break
    return tgt

# =============================================================================
# 4. Dataset  (cls_data_generator.py 相当)
# =============================================================================

class UNSDataset(Dataset):
    def __init__(self, cfg, split, augment=False):
        self.cfg, self.augment = cfg, augment
        file_events = load_meta_csv(cfg["meta_csv"], split, cfg["data_root"])
        if not file_events:
            paths = sorted(glob.glob(os.path.join(cfg["data_root"],"audio","**","*.wav"),
                                     recursive=True))
            file_events = {p:[] for p in paths}

        self.segs = []
        print(f"[Dataset:{split}] {len(file_events)} ファイルを処理中...")
        for ap, evs in file_events.items():
            if not os.path.exists(ap):
                continue
            feat  = normalize(extract_features(ap, cfg))
            segs  = segment(feat, cfg["n_frames"])
            lf    = cfg["label_frames"]
            n_tot = lf * len(segs)
            tgt   = (events_to_target(evs, n_tot, cfg["n_classes"],
                                       cfg["n_tracks"], cfg["label_hop_sec"])
                     if evs else None)
            for i, sf_ in enumerate(segs):
                t = (tgt[i*lf:(i+1)*lf] if tgt is not None
                     else np.zeros((lf,cfg["n_tracks"],cfg["n_classes"],3),
                                   np.float32))
                if t.shape[0] < lf:
                    t = np.concatenate([t,
                        np.zeros((lf-t.shape[0],cfg["n_tracks"],
                                  cfg["n_classes"],3),np.float32)],0)
                self.segs.append((sf_, t, os.path.basename(ap), i,
                                  bool(evs)))
        print(f"[Dataset:{split}] セグメント総数: {len(self.segs)}")

    def __len__(self): return len(self.segs)

    def __getitem__(self, idx):
        feat, tgt, fname, si, has_label = self.segs[idx]
        if self.augment: feat = freq_mask(feat, self.cfg["freq_mask_bins"])
        return (torch.from_numpy(feat), torch.from_numpy(tgt),
                fname, si, has_label)

# =============================================================================
# 5. モデル  (keras_model.py 相当 → SELD U-Net PyTorch 実装)
# =============================================================================

class ConvBlock(nn.Module):
    def __init__(self, i, o):
        super().__init__()
        self.b = nn.Sequential(
            nn.Conv2d(i,o,3,padding=1), nn.ReLU(True),
            nn.Conv2d(o,o,3,padding=1), nn.BatchNorm2d(o), nn.ReLU(True))
    def forward(self,x): return self.b(x)


class UNet(nn.Module):
    """論文 Figure 3 準拠 (base_ch=32 でメモリ節約、論文は 64→1024)"""
    def __init__(self, in_ch, base_ch=32):
        super().__init__()
        b = base_ch
        self.e1=ConvBlock(in_ch,b);   self.e2=ConvBlock(b,b*2)
        self.e3=ConvBlock(b*2,b*4);   self.e4=ConvBlock(b*4,b*8)
        self.pool=nn.MaxPool2d(2,2)
        self.bn=ConvBlock(b*8,b*16)
        self.u4=nn.ConvTranspose2d(b*16,b*8,2,2)
        self.d4=ConvBlock(b*16,b*8)
        self.u3=nn.ConvTranspose2d(b*8,b*4,2,2)
        self.d3=ConvBlock(b*8,b*4)
        self.u2=nn.ConvTranspose2d(b*4,b*2,2,2)
        self.d2=ConvBlock(b*4,b*2)
        self.u1=nn.ConvTranspose2d(b*2,b,2,2)
        self.d1=ConvBlock(b*2,b)
        self.out=nn.Conv2d(b,in_ch,1)

    def _cat(self, up, x, skip):
        u = up(x)
        if u.shape != skip.shape:
            u = F.interpolate(u, skip.shape[2:], mode="bilinear",
                              align_corners=False)
        return torch.cat([u,skip],1)

    def forward(self, x):
        e1=self.e1(x);        e2=self.e2(self.pool(e1))
        e3=self.e3(self.pool(e2)); e4=self.e4(self.pool(e3))
        bn=self.bn(self.pool(e4))
        d4=self.d4(self._cat(self.u4,bn,e4))
        d3=self.d3(self._cat(self.u3,d4,e3))
        d2=self.d2(self._cat(self.u2,d3,e2))
        d1=self.d1(self._cat(self.u1,d2,e1))
        return self.out(d1), [d1,d2,d3]


class RCB(nn.Module):
    """Residual Convolutional Block (論文 Figure 6)"""
    def __init__(self, i, o, drop=0.3):
        super().__init__()
        self.c1=nn.Conv2d(i,o,3,padding=1); self.bn1=nn.BatchNorm2d(o)
        self.c2=nn.Conv2d(o,o,3,padding=1); self.bn2=nn.BatchNorm2d(o)
        self.skip=nn.Conv2d(i,o,1) if i!=o else nn.Identity()
        self.pool=nn.AdaptiveAvgPool2d((None,1))
        self.drop=nn.Dropout(drop)

    def forward(self,x):
        r=self.skip(x)
        out=F.relu(self.bn1(self.c1(x)))
        out=self.bn2(self.c2(out))
        return self.drop(self.pool(F.relu(out+r)))


class PosEnc(nn.Module):
    def __init__(self,d,mx=2000):
        super().__init__()
        pe=torch.zeros(mx,d)
        pos=torch.arange(mx).unsqueeze(1).float()
        div=torch.exp(torch.arange(0,d,2).float()*(-math.log(10000)/d))
        pe[:,0::2]=torch.sin(pos*div); pe[:,1::2]=torch.cos(pos*div)
        self.register_buffer("pe",pe.unsqueeze(0))
    def forward(self,x): return x+self.pe[:,:x.size(1)]


class SELDnet(nn.Module):
    """論文 Figure 6 準拠 (3 RCB + Transformer + FC)"""
    def __init__(self, dec_chs, n_cls, n_trk, n_heads=4, ff=512, drop=0.3):
        super().__init__()
        base=dec_chs[0]
        self.align=nn.ModuleList([
            nn.Sequential(nn.ConvTranspose2d(c,base,1),nn.ReLU(True))
            for c in dec_chs])
        si=base*len(dec_chs)
        self.stem=nn.Sequential(
            nn.Conv2d(si,si,5,padding=2),nn.ReLU(True),
            nn.Conv2d(si,si*2,1),nn.ReLU(True))
        ri=si*2
        self.r1=RCB(ri,128,drop); self.r2=RCB(128,128,drop)
        self.r3=RCB(128,128,drop)
        self.pe=PosEnc(128)
        self.tr=nn.TransformerEncoder(
            nn.TransformerEncoderLayer(128,n_heads,ff,drop,batch_first=True),1)
        self.fc1=nn.Linear(128,128); self.fc2=nn.Linear(128,n_trk*n_cls*3)
        self.n_trk=n_trk; self.n_cls=n_cls

    def forward(self,dfs):
        ts=dfs[0].shape[2:]
        aligned=[F.interpolate(self.align[i](f),ts,mode="bilinear",
                               align_corners=False)
                 for i,f in enumerate(dfs)]
        x=self.stem(torch.cat(aligned,1))
        x=self.r3(self.r2(self.r1(x)))
        x=self.tr(self.pe(x.squeeze(-1).permute(0,2,1)))
        x=self.fc2(F.relu(self.fc1(x)))
        B,T,_=x.shape
        return torch.tanh(x.view(B,T,self.n_trk,self.n_cls,3))


class SELDUNet(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        b=cfg["unet_base_ch"]
        self.unet=UNet(cfg["n_channels"],b)
        self.seld=SELDnet([b,b*2,b*4],cfg["n_classes"],cfg["n_tracks"])

    def forward(self,x):
        enh,dfs=self.unet(x)
        return enh, self.seld(dfs)

# =============================================================================
# 6. 損失関数
# =============================================================================

def phase1_loss(pred, target):
    """U-Net L1 損失（MIC: IV なし、全チャンネル均等）"""
    return F.l1_loss(pred, target)


def adpit_loss_weighted(pred, target, active_weight=10.0):
    """
    活性フレーム重み付き ADPIT 損失。
    trivial solution（全ゼロ予測）を防ぐため活性フレームを active_weight 倍に。
    """
    B, Tp, N, C, _ = pred.shape
    T = min(Tp, target.shape[1])
    pred, target = pred[:,:T], target[:,:T]
    total = 0.0
    for c in range(C):
        tc, pc = target[:,:,:,c,:], pred[:,:,:,c,:]
        # 活性マスク: いずれかのトラックに方向ベクトルあり
        active = (tc.norm(dim=-1) > 0.1).any(dim=-1)  # (B, T)
        weight = torch.where(active,
                             torch.tensor(active_weight, device=pred.device),
                             torch.tensor(1.0, device=pred.device))
        best = None
        for perm in permutations(range(N)):
            mse = ((pc[:,:,list(perm),:]-tc)**2).mean(dim=(2,3))  # (B,T)
            best = mse if best is None else torch.minimum(best, mse)
        total += (best * weight).mean()
    return total / C

# =============================================================================
# 7. 評価指標  (evaluation_metrics.py 相当・DCASE2023 標準準拠)
# =============================================================================

def cart2sph(x,y,z):
    r=math.sqrt(x**2+y**2+z**2)
    if r<1e-8: return 0.,0.
    return math.degrees(math.atan2(y,x)), math.degrees(math.asin(max(-1.,min(1.,z/r))))


def ang_dist(az1,el1,az2,el2):
    az1,el1,az2,el2=map(math.radians,[az1,el1,az2,el2])
    return math.degrees(math.acos(max(-1.,min(1.,
        math.sin(el1)*math.sin(el2)+math.cos(el1)*math.cos(el2)*math.cos(az1-az2)))))


def decode(out, th=0.5):
    evs=[]; T,N,C,_=out.shape
    for t in range(T):
        for n in range(N):
            for c in range(C):
                v=out[t,n,c]
                if float(np.linalg.norm(v))>th:
                    evs.append((t,c,*cart2sph(*v.tolist())))
    return evs


class SELDMetrics:
    """
    ER  = max(FP,FN) / (TP+FN)      ← 論文式(12) 正確な実装
    F1  = 2PR/(P+R)  [20° TP]
    LE_CD = Hungarian 法（閾値なし） ← 論文式(18)
    LR_CD = Hungarian 法（閾値なし） ← 論文式(19)
    SELD  = (ER+(1-F1)+LE_CD/180+(1-LR_CD))/4 ← 論文式(20)
    """
    DOA_TH = 20.0

    def __init__(self, n_cls):
        self.C=n_cls; self.reset()

    def reset(self):
        self.TP=self.FP=self.FN=0
        self.hung_err  =[0.]*self.C
        self.hung_match=[0] *self.C
        self.hung_ref  =[0] *self.C

    def _to_dict(self,evs):
        d={}
        for fr,cls,az,el in evs:
            d.setdefault((fr,cls),[]).append((az,el))
        return d

    def update(self, pred_evs, ref_evs):
        pd=self._to_dict(pred_evs); rd=self._to_dict(ref_evs)
        for key in set(pd)|set(rd):
            fr,cls=key
            ps=pd.get(key,[]); rs=rd.get(key,[])
            tp=min(len(ps),len(rs))
            self.FP+=max(0,len(ps)-len(rs))
            self.FN+=max(0,len(rs)-len(ps))
            # TP（20° 閾値あり）
            used=[False]*len(rs); dtp=0
            for p in ps:
                for j,r in enumerate(rs):
                    if not used[j] and ang_dist(*p,*r)<=self.DOA_TH:
                        dtp+=1; used[j]=True; break
            self.TP+=dtp
            self.FP+=tp-dtp; self.FN+=tp-dtp
            # LE_CD / LR_CD（Hungarian、閾値なし）
            self.hung_ref[cls]+=len(rs)
            if ps and rs:
                D=np.array([[ang_dist(*p,*r) for r in rs] for p in ps])
                ri,ci=linear_sum_assignment(D)
                self.hung_match[cls]+=len(ri)
                self.hung_err[cls]+=D[ri,ci].sum()

    def compute(self):
        prec=self.TP/(self.TP+self.FP+1e-8)
        rec =self.TP/(self.TP+self.FN+1e-8)
        F1=2*prec*rec/(prec+rec+1e-8)
        ER=max(self.FP,self.FN)/(self.TP+self.FN+1e-8)   # 論文式(12)
        le=[self.hung_err[c]/self.hung_match[c]
            for c in range(self.C) if self.hung_match[c]>0]
        LE_CD=sum(le)/len(le) if le else 0.
        lr=[self.hung_match[c]/self.hung_ref[c] if self.hung_ref[c]>0 else 0.
            for c in range(self.C)]
        LR_CD=sum(lr)/self.C
        SELD=(ER+(1-F1)+LE_CD/180+(1-LR_CD))/4
        return dict(ER=ER,F1=F1,LE_CD=LE_CD,LR_CD=LR_CD,SELD=SELD)

# =============================================================================
# 8. 学習ループ  (seld.py 相当)
# =============================================================================

def make_nadam(params, lr):
    """Nesterov-Adam (NAdam) - 論文準拠"""
    try:
        return torch.optim.NAdam(params, lr=lr)
    except AttributeError:
        return torch.optim.Adam(params, lr=lr)


def train_p1(model, loader, opt, cfg):
    model.train(); tot=0.
    for batch in loader:
        feat=batch[0].to(cfg["device"])
        opt.zero_grad()
        enh,_=model(feat)
        loss=phase1_loss(enh,feat)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),5.)
        opt.step(); tot+=loss.item()
    return tot/len(loader)


def train_p2(model, loader, opt, cfg):
    model.train()
    for p in model.unet.parameters(): p.requires_grad=False
    tot=0.; sk=0
    for batch in loader:
        feat,tgt=batch[0].to(cfg["device"]),batch[1].to(cfg["device"])
        opt.zero_grad()
        _,sout=model(feat)
        loss=adpit_loss_weighted(sout,tgt,cfg["active_weight"])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),5.)
        opt.step(); tot+=loss.item()
    for p in model.unet.parameters(): p.requires_grad=True
    return tot/max(len(loader)-sk,1)


def train(cfg=CFG):
    os.makedirs(cfg["output_dir"],exist_ok=True)
    ds   =UNSDataset(cfg,cfg["train_split"],augment=True)
    ldr  =DataLoader(ds,batch_size=cfg["batch_size"],shuffle=True,num_workers=0)
    model=SELDUNet(cfg).to(cfg["device"])
    print(f"[Model] {sum(p.numel() for p in model.parameters())/1e6:.2f}M params")

    ck1=os.path.join(cfg["output_dir"],"unet_best.pt")

    print("\n=== Phase 1: U-Net ===")
    o1=make_nadam(model.unet.parameters(),cfg["lr"]); b1=float("inf"); h1=[]
    for ep in range(cfg["epochs_p1"]):
        l=train_p1(model,ldr,o1,cfg); h1.append(l)
        if l<b1: b1=l; torch.save(model.unet.state_dict(),ck1)
        if (ep+1)%10==0: print(f"  ep{ep+1:3d}/{cfg['epochs_p1']} loss={l:.4f}")
    model.unet.load_state_dict(torch.load(ck1,map_location=cfg["device"]))

    print("\n=== Phase 2: SELDnet ===")
    o2=make_nadam(model.seld.parameters(),cfg["lr"]); b2=float("inf"); h2=[]
    ck2=os.path.join(cfg["output_dir"],"seld_unet_best.pt")
    for ep in range(cfg["epochs_p2"]):
        l=train_p2(model,ldr,o2,cfg); h2.append(l)
        if l<b2: b2=l; torch.save(model.state_dict(),ck2)
        if (ep+1)%10==0: print(f"  ep{ep+1:3d}/{cfg['epochs_p2']} loss={l:.4f}")

    _plot(h1,h2,cfg["output_dir"])
    print(f"\n学習完了: {cfg['output_dir']}")


def _plot(h1,h2,d):
    plt.figure(figsize=(10,4))
    plt.subplot(1,2,1); plt.plot(h1)
    plt.title("Phase1 U-Net L1"); plt.xlabel("epoch")
    plt.subplot(1,2,2); plt.plot(h2)
    plt.title("Phase2 ADPIT (weighted)"); plt.xlabel("epoch")
    plt.tight_layout()
    plt.savefig(os.path.join(d,"training_curves.png")); plt.close()

# =============================================================================
# 9. 評価
# =============================================================================

@torch.no_grad()
def evaluate(cfg=CFG, threshold=0.5):
    mp=os.path.join(cfg["output_dir"],"seld_unet_best.pt")
    if not os.path.exists(mp):
        print(f"[Error] モデルなし: {mp}"); return

    model=SELDUNet(cfg).to(cfg["device"])
    model.load_state_dict(torch.load(mp,map_location=cfg["device"]))
    model.eval()

    ds =UNSDataset(cfg,cfg["eval_split"],augment=False)
    ldr=DataLoader(ds,batch_size=1,shuffle=False,num_workers=0)
    met=SELDMetrics(cfg["n_classes"])

    for batch in ldr:
        feat,tgt,_,_,hl=batch
        if not hl[0]: continue
        feat=feat.to(cfg["device"])
        _,sout=model(feat)
        pred=decode(sout[0].cpu().numpy(),threshold)
        ref =decode(tgt[0].numpy(),0.1)
        if ref: met.update(pred,ref)

    print("\n=== SELD 評価結果 (UNS-ESSE2023, v3) ===")
    res=met.compute()
    print(f"  ER    : {res['ER']:.4f}  (↓)   ※上限なし, 論文式(12)")
    print(f"  F1    : {res['F1']:.4f}  (↑)   [20° 閾値 TP]")
    print(f"  LE_CD : {res['LE_CD']:.2f}°  (↓)   ハンガリアン法")
    print(f"  LR_CD : {res['LR_CD']:.4f}  (↑)   ハンガリアン法")
    print(f"  SELD  : {res['SELD']:.4f}  (↓)")
    print(f"\n  --- クラス別 ---")
    for c in range(cfg["n_classes"]):
        le=(met.hung_err[c]/met.hung_match[c] if met.hung_match[c]>0
            else float("nan"))
        lr=(met.hung_match[c]/met.hung_ref[c] if met.hung_ref[c]>0 else 0.)
        print(f"  [{CLASS_NAMES[c]:18s}] LE={le:6.2f}°  LR={lr:.4f}")

    out={**res,
         "per_class":{CLASS_NAMES[c]:{
             "LE":met.hung_err[c]/met.hung_match[c] if met.hung_match[c]>0 else None,
             "LR":met.hung_match[c]/met.hung_ref[c] if met.hung_ref[c]>0 else 0.}
             for c in range(cfg["n_classes"])},
         "threshold":threshold,
         "cfg":{k:v for k,v in cfg.items() if isinstance(v,(int,float,str,bool))}}
    jp=os.path.join(cfg["output_dir"],"eval_results.json")
    with open(jp,"w") as f: json.dump(out,f,indent=2,ensure_ascii=False)
    print(f"\n  保存: {jp}")
    return res

# =============================================================================
# 10. デモ用合成データ生成
# =============================================================================

def generate_demo(cfg=CFG, n=9):
    ad=os.path.join(cfg["data_root"],"audio"); os.makedirs(ad,exist_ok=True)
    md=os.path.dirname(cfg["meta_csv"]);      os.makedirs(md,exist_ok=True)
    fs=cfg["fs"]; dur=10.; ns=int(dur*fs)
    t=np.linspace(0,dur,ns,endpoint=False)
    cls_p={0:(80,.5,(0.3,1.5)),1:(200,.6,(0.05,0.3)),2:(3000,.3,(0.2,0.8))}
    rows=[]
    for i in range(n):
        audio=np.zeros((ns,8),np.float32)
        splt="train" if i<n*.6 else ("val" if i<n*.8 else "eval")
        cls=np.random.randint(0,3); freq,amp,(dlo,dhi)=cls_p[cls]
        dur_=np.random.uniform(dlo,dhi)
        onset=np.random.uniform(1.,max(1.1,dur-dur_-1.))
        offset=min(onset+dur_,dur-.1)
        spk=np.random.randint(0,8); az=spk*45.
        mask=(t>=onset)&(t<=offset)
        sig=amp*mask*np.sin(2*np.pi*freq*t)
        for m in range(8):
            dl=int(abs(m-spk)*.5)
            audio[:,m]+=np.roll(sig,dl)*(0.8**abs(m-spk))
        audio+=.03*np.random.randn(*audio.shape).astype(np.float32)
        audio=np.clip(audio,-1.,1.)
        fn=f"audio/demo_{i:03d}.wav"
        sf.write(os.path.join(cfg["data_root"],fn),audio,fs,subtype="PCM_16")
        rows.append({"filename":fn,"event_onset":f"{onset:.3f}",
                     "event_offset":f"{offset:.3f}","event_label":CLASS_NAMES[cls],
                     "event_azimuth":f"{az:.1f}","event_elevation":"0",
                     "event_distance":"5","set":splt,
                     "snr":"0","spl_before":"0","spl_after":"0","identifier":"demo"})
    flds=["filename","event_onset","event_offset","event_label","event_azimuth",
          "event_elevation","event_distance","set","snr","spl_before","spl_after",
          "identifier"]
    with open(cfg["meta_csv"],"w",newline="") as f:
        csv.DictWriter(f,flds,delimiter="\t").writeheader()
        csv.DictWriter(f,flds,delimiter="\t").writerows(rows)
    print(f"デモデータ生成完了: {n} ファイル")

# =============================================================================
# 11. エントリポイント
# =============================================================================

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",choices=["train","eval","demo"],default="demo")
    ap.add_argument("--data_root",default=None)
    ap.add_argument("--output_dir",default=None)
    ap.add_argument("--epochs_p1",type=int,default=None)
    ap.add_argument("--epochs_p2",type=int,default=None)
    ap.add_argument("--threshold",type=float,default=0.5)
    args=ap.parse_args()

    if args.data_root:  CFG["data_root"] =args.data_root
    if args.output_dir: CFG["output_dir"]=args.output_dir
    if args.epochs_p1:  CFG["epochs_p1"] =args.epochs_p1
    if args.epochs_p2:  CFG["epochs_p2"] =args.epochs_p2
    os.makedirs(CFG["output_dir"],exist_ok=True)

    if args.mode=="demo":
        print("="*60); print("DEMO: 合成データで動作確認"); print("="*60)
        CFG["batch_size"]=2; CFG["epochs_p1"]=5; CFG["epochs_p2"]=5
        generate_demo(CFG); train(CFG); evaluate(CFG,args.threshold)
    elif args.mode=="train":
        print("="*60); print(f"学習 | split={CFG['train_split']}"); print("="*60)
        train(CFG)
    elif args.mode=="eval":
        print("="*60); print(f"評価 | split={CFG['eval_split']}"); print("="*60)
        evaluate(CFG,args.threshold)
