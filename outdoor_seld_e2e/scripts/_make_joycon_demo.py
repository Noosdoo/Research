# -*- coding: utf-8 -*-
"""Joy-conデモのデータ書き出し（S3・2026-09-01）。

「通知層の出力を先に計算しておいて、クリップの再生に合わせて振動を出す」デモの
データ側を作る。**通知はデモ用の作り物ではなく、採用済みv4.2＋警告音hold規則の
本物の出力**をそのまま使う。

fold31（チューニングval第2版）から性格の違うクリップを自動で数本選び、
各クリップについて
  - 試聴用ステレオwav（FOA→簡易ステレオ: L=W+0.5Y / R=W−0.5Y、デモ用に音量正規化）
  - cues.csv（t_s, side L/R, tier 強/中/警告, class, az_deg）
を out/joycon_demo/ に書く。side は DCASE方位規約（正=左）から決める。
実機で逆に感じたらUnity側のSキーで入れ替え可能。

使い方: python scripts/_make_joycon_demo.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


v4 = _load("nv4", "step12_notify_v4_ttc.py")
V42 = _load("nv42", "step12_notify_v42_bearing.py")
H = _load("nhold", "step12_notify_v9b_hold.py")
DG = _load("ndiag", "_notify_v42_diag.py")

ADOPTED = V42.Cfg(route_c=True, adot_th=0.10, dn=15.0, link_pred=True,
                  cpa_strong=1.3, cpa_mid=1.6)
PRED = ROOT / "out/predictions_v42tune2/val_all_causal.csv"
META = ROOT / "out/dataset_outdoor_siren_v42tune2/metadata_dist"
FOA = ROOT / "out/dataset_outdoor_siren_v42tune2/foa"     # サーバ生成分はscpが必要
OUT = ROOT / "out/joycon_demo"
CLS_JP = {4: "car", 6: "kick", 7: "bike"}
WARN_JP = {0: "siren", 1: "horn", 2: "backup_beep", 3: "bike_bell", 5: "crossing"}


def cues_for(clip, pred_cars, pred_warn):
    """[(t, side, tier, cls, az)] を返す。t=(frame+1)/10（因果の放出時刻規約）。"""
    out = []
    res = V42.run_rule2({clip: pred_cars[clip]}, ADOPTED).get(clip, {})
    for cls, eps in res.items():
        for j, az, tier, d in eps:
            out.append(((j + 1) / 10.0, "L" if az > 0 else "R", tier,
                        CLS_JP.get(cls, str(cls)), az))
    for k, c, az in H.warn_fires(pred_warn[clip], hold=True):
        out.append(((k + 1) / 10.0, "L" if az > 0 else "R", "警告",
                    WARN_JP[c], az))
    return sorted(out)


def gt_summary(clip):
    evs = [DG.mk_event(c, t, fr) for c, t, fr in DG.gt_tracks(META, clip)]
    return evs


def pick_clips(pred_cars, pred_warn):
    """性格の違うクリップを選ぶ: 強あり車 / 抑制(安全のみ) / 警告音入り。"""
    picked = {}
    for clip in sorted(pred_cars):
        if len(picked) >= 5:
            break
        cues = cues_for(clip, pred_cars, pred_warn)
        evs = gt_summary(clip)
        tiers = [c[2] for c in cues]
        has_crit = any(e["tier"] == "critical" for e in evs)
        if "strong_car" not in picked and has_crit and "強" in tiers:
            picked["strong_car"] = (clip, cues, "重大の車→強振動（v4.2）")
        elif ("suppress" not in picked and evs
              and all(e["tier"] == "safe" for e in evs) and "強" not in tiers):
            picked["suppress"] = (clip, cues, "安全な車のみ→強は鳴らない（抑制）")
        elif "warn" not in picked and any(t == "警告" for t in tiers) and has_crit:
            picked["warn"] = (clip, cues, "警告音＋車の複合")
        elif ("multi" not in picked and "強" in tiers
              and sum(1 for e in evs if e["tier"] != "safe") >= 3):
            picked["multi"] = (clip, cues, "複数イベントの連続")
        elif "quiet_warn" not in picked and tiers and all(t == "警告" for t in tiers):
            picked["quiet_warn"] = (clip, cues, "警告音のみ（holdで1回ずつ）")
    return picked


def write_clip(clip, cues, outdir: Path):
    x, sr = sf.read(FOA / f"{clip}.flac", dtype="float64")   # (n,4) W,Y,Z,X
    L = x[:, 0] + 0.5 * x[:, 1]
    R = x[:, 0] - 0.5 * x[:, 1]
    st = np.stack([L, R], axis=1)
    peak = np.max(np.abs(st))
    if peak > 0:
        st = st / peak
    # デモ試聴用のダイナミックレンジ圧縮（2026-09-02追加）:
    # 合成は実SPL規約のため静音部とピークの差が50dB超あり、ピーク正規化だけだと
    # 冒頭の遠距離区間がPCスピーカーで無音に聞こえる（本人指摘）。べき圧縮で
    # 小音量を持ち上げる。⚠️このwavは較正もダイナミクスも捨てた「試聴用」
    st = np.sign(st) * np.abs(st) ** 0.5
    st = st * 0.7
    sf.write(outdir / f"{clip}.wav", st.astype(np.float32), sr, subtype="PCM_16")
    with open(outdir / f"{clip}_cues.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,side,tier,class,az_deg\n")
        for t, side, tier, cls, az in cues:
            f.write(f"{t:.1f},{side},{tier},{cls},{az:.0f}\n")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    pred_cars = v4.load_pred(PRED)
    pred_warn = H.load_pred7(PRED)
    picked = pick_clips(pred_cars, pred_warn)
    M = ["# Joy-conデモ データ（自動生成: _make_joycon_demo.py）", "",
         "- 通知は**採用済みv4.2＋警告音hold**の本物の出力（クリップはfold31）",
         "- 音はデモ試聴用に正規化済み（絶対較正はこのwavでは捨てている）",
         "- side: DCASE方位規約（方位角プラス=左）。逆に感じたらUnityでSキー", ""]
    for key, (clip, cues, desc) in picked.items():
        write_clip(clip, cues, OUT)
        M.append(f"## {clip} — {desc}")
        M += [f"- {t:.1f}s {side} {tier} ({cls}, az={az:.0f}°)"
              for t, side, tier, cls, az in cues] + [""]
        print(f"[{key}] {clip}: {len(cues)} cues — {desc}")
    (OUT / "manifest.md").write_text("\n".join(M), encoding="utf-8")
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
