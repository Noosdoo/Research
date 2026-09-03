# -*- coding: utf-8 -*-
"""自作場面（オラクル）を本物の検出層に通した版を作る（2026-09-03 本人「最初から正解を渡していないですよね？」への対応）。

流れ: _make_custom_demo_scenario_v3.py --save-foa（4ch flac＋GT）→ サーバ server_sde/custom_infer.sbatch（ft2 e099 因果推論）
      → out/joycon_demo_v2/model_infer/val_all_causal.csv を取得 → このスクリプトで通知（v4.3＋hold）・緊急度・検出を作る。
出力: out/joycon_demo_v2/custom_<name>_model_{cues,urgency,detect}.csv（wav/_scene/_layout はオラクル版のコピー）。
      整理スクリプトが「8_自作場面_本物のモデル出力/<日本語名>_モデル」として Unity に置く。

⚠️ 音・正解位置（_scene）は同じ。違うのは「通知が本物のモデルの検出から出ている」こと。オラクル版と並べて見比べる用。
使い方: python scripts/_make_custom_demo_from_model.py [pred_csv]
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


DEMO = _load("demo43", "_make_joycon_demo_v43.py")
OUT = ROOT / "out/joycon_demo_v2"
MI = OUT / "model_infer"


def main() -> int:
    pred = Path(sys.argv[1]) if len(sys.argv) > 1 else MI / "val_all_causal.csv"
    assert pred.exists(), f"予測が無い: {pred}（サーバの infer_demo_custom_causal/val_all_causal.csv を取得する）"
    pred_cars = DEMO.v4.load_pred(pred)
    pred_warn = DEMO.H.load_pred7(pred)
    clips = sorted(p.stem for p in (MI / "foa").glob("custom_*.flac"))
    if "--only" in sys.argv:                       # 指定した場面だけ書く（既存の出力には触れない）
        keep = set(sys.argv[sys.argv.index("--only") + 1].split(","))
        clips = [c for c in clips if c in keep or c.replace("custom_", "") in keep]
    lines = ["# 自作場面 × 本物の検出層（ft2 e099 因果推論 → v4.3＋hold）", "",
             "| 場面 | オラクル（正解→規則） | モデル（検出→規則） |", "| --- | --- | --- |"]
    n = 0
    for clip in clips:
        pred_cars.setdefault(clip, {})          # 検出ゼロの場面（例: 何も来ない）も扱う
        cues = DEMO.cues_for(clip, pred_cars, pred_warn)
        urg = DEMO.urgency_for(clip, pred_cars)
        det = DEMO.detect_rows(clip, pred_cars)
        base = OUT / f"{clip}_model"
        for ext in (".wav", "_scene.csv", "_layout.csv"):
            src = OUT / f"{clip}{ext}"
            if src.exists():
                shutil.copy2(src, Path(str(base) + ext))
        with open(f"{base}_cues.csv", "w", encoding="utf-8", newline="\n") as f:
            f.write("t_s,side,tier,class,az_deg\n")
            for t, side, tier, cls, az in cues:
                f.write(f"{t:.1f},{side},{tier},{cls},{az:.0f}\n")
            f.write("# 本物の検出層（ft2 e099 因果推論）→ v4.3＋hold。オラクルではない\n")
        with open(f"{base}_urgency.csv", "w", encoding="utf-8", newline="\n") as f:
            f.write("t_s,urgency,az_deg\n")
            for t, u, az in urg:
                f.write(f"{t:.1f},{u:.3f},{az:.0f}\n")
        with open(f"{base}_detect.csv", "w", encoding="utf-8", newline="\n") as f:
            f.write("t_s,class,az_deg,dist_m\n")
            for t, cls, az, d in det:
                f.write(f"{t:.1f},{cls},{az:.0f},{'' if d is None else f'{d:.2f}'}\n")
        # オラクル版の cues を読んで比較表に
        orc = []
        oc = OUT / f"{clip}_cues.csv"
        if oc.exists():
            for line in oc.read_text(encoding="utf-8").splitlines()[1:]:
                if line.startswith("#") or not line.strip():
                    continue
                t, side, tier, cls, az = line.split(",")
                orc.append(f"{float(t):.1f} {side} {tier}({cls})")
        lines.append(f"| {clip.replace('custom_', '')} | {' / '.join(orc) or 'なし'} | "
                     f"{' / '.join(f'{t:.1f} {side} {tier}({cls})' for t, side, tier, cls, _ in cues) or 'なし'} |")
        print(f"{clip}: モデル {len(cues)} 件 / オラクル {len(orc)} 件")
        n += 1
    if "--only" not in sys.argv:
        (OUT / "README_モデル版との比較.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:                                          # 部分実行: 既存の比較表の末尾に行を足すだけ
        rp = OUT / "README_モデル版との比較.md"
        old = rp.read_text(encoding="utf-8").rstrip("\n") if rp.exists() else "\n".join(lines[:4])
        rp.write_text(old + "\n" + "\n".join(lines[4:]) + "\n", encoding="utf-8")
    print(f"-> {n} 場面, {OUT / 'README_モデル版との比較.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
