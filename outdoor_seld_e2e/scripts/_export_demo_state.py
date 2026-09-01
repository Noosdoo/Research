# -*- coding: utf-8 -*-
"""デモの画面表示用: 毎フレームの判定材料（予測最接近・到達時間・危険度域）を書き出す。

scene.csv（毎フレームの方位・距離）から、v4.2と同じ式で d_cpa / t_cpa を計算し、
「いまこの物体をどう判定しているか」の表示文を <clip>_state.csv（t_s|表示文）にする。

⚠️ 表示はフレーム単位の**判定材料**。実際の発火は4フレーム連続の確認などが付くので、
   「強域と表示された瞬間に必ず振動する」わけではない（教材表示と割り切る）。

使い方: python scripts/_export_demo_state.py   （out/joycon_demo/*_scene.csv 全部を処理）
"""
from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

spec = importlib.util.spec_from_file_location(
    "nv4", ROOT / "scripts" / "step12_notify_v4_ttc.py")
v4 = importlib.util.module_from_spec(spec)
sys.modules["nv4"] = v4
spec.loader.exec_module(v4)

DIST = {"car", "kick", "bike"}
JP = {"car": "車", "kick": "キックボード", "bike": "バイク", "siren": "救急車",
      "horn": "クラクション", "backup_beep": "バック音", "bike_bell": "自転車ベル",
      "crossing": "踏切"}
CS, CM, TW, TC = 1.3, 1.6, 2.5, 4.0        # 採用v4.2のしきい値


def main() -> int:
    for sc in sorted((ROOT / "out/joycon_demo").glob("*_scene.csv")):
        clip = sc.name[:-10]               # "_scene.csv" を落とす
        objs = defaultdict(dict)           # obj -> frame -> (az, d)
        cls_of = {}
        for line in sc.read_text(encoding="utf-8").splitlines()[1:]:
            p = line.split(",")
            if len(p) < 5:
                continue
            k = int(round(float(p[0]) * 10))
            objs[p[1]][k] = (float(p[3]), float(p[4]))
            cls_of[p[1]] = p[2]
        lines = []
        for k in range(100):
            parts = []
            for obj, fr in objs.items():
                if k not in fr:
                    continue
                cls = cls_of[obj]
                az, d = fr[k]
                if cls not in DIST:
                    parts.append(f"{JP.get(cls, cls)}: 検出 {az:.0f}°")
                    continue
                d_at = {kk: v[1] for kk, v in fr.items()}
                az_at = {kk: v[0] for kk, v in fr.items()}
                v_ = v4.closing_speed(d_at, k)
                adot = v4.azimuth_rate(az_at, k)
                dc, tc = v4.cpa_of(d, None if v_ is None else -v_, adot)
                if dc is None:
                    lab, detail = "計測中", ""
                else:
                    if (dc <= CS and tc <= TW) or d <= v4.T3:
                        lab = "★至近警告(強)域"
                    elif (dc <= CM and tc <= TC) or d <= v4.SUPP:
                        lab = "▲注意(中)域"
                    else:
                        lab = "・抑制(安全)"
                    detail = f" 最接近予測{dc:.1f}m 到達{tc:.1f}s"
                parts.append(f"{JP.get(cls, cls)}: {d:.1f}m{detail} → {lab}")
            lines.append(f"{k/10.0:.1f}|" + ("  ／  ".join(parts) if parts else ""))
        out = ROOT / "out/joycon_demo" / f"{clip}_state.csv"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{clip}: state 100行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
