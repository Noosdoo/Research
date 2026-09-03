# -*- coding: utf-8 -*-
"""D10 至近・低速の試聴用 A/B（2026-09-03）: 同じクリップを v13（元）と v14（徐行・至近）で描画し、
ステレオ wav（W±0.5Y の簡易ダウンミックス・デモと同じ）を out/v14_proto_listen/{before,after}/ に書く。

使い方: python scripts/_v14_proto_listen.py [N=12]
描画先は一時フォルダ（out/v14_proto_listen/_ds_*）で、正式データセット（v13/v14）には書かない。
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import step11_v14_render as v14  # noqa: E402

m9 = v14.m9
OUT = ROOT / "out/v14_proto_listen"


def render_to(row: dict, ds: Path) -> Path:
    m9.DS = ds
    m9.WORK = ds / "work"
    v14.generate_clip(row)
    return ds / "foa" / f"{row['clip_id']}.flac"


def to_stereo(flac: Path, wav: Path) -> None:
    x, fs = sf.read(flac, dtype="float32", always_2d=True)      # (n, 4) W X Y Z
    st = np.stack([x[:, 0] + 0.5 * x[:, 2], x[:, 0] - 0.5 * x[:, 2]], axis=1)
    st = st / max(float(np.max(np.abs(st))), 1e-9)
    st = np.sign(st) * np.abs(st) ** 0.5 * 0.7
    sf.write(wav, st.astype(np.float32), fs, subtype="PCM_16")


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    rows = [r for r in v14.load_plan_v14() if r["close_slow"] == "1" and r["split"] == "fold2"][:n]
    for sub in ("before", "after"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    lines = ["# D10 至近・低速 試聴 A/B（before = v13 のまま / after = v14 徐行・至近）", "",
             "| clip | 歩行/静止 | 雨 | 速度 km/h（前→後） | 最接近 m（前→後） | 音量補正 dB |", "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        r13 = dict(r); r13["close_slow"] = ""
        s13 = v14.sample_scene_v14(r13)
        car = next(s for s in s13["sources"] if s.get("class") == "car_drive" and s.get("kind") == "vehicle" and s.get("track", 0) == 0)
        v_before, cpa_before = car["speed_mps"] * 3.6, car["cpa_rel_target_m"]
        f_b = render_to(r13, OUT / "_ds_before")
        f_a = render_to(r, OUT / "_ds_after")
        to_stereo(f_b, OUT / "before" / f"{r['clip_id']}.wav")
        to_stereo(f_a, OUT / "after" / f"{r['clip_id']}.wav")
        lines.append(f"| {r['clip_id']} | {r['motion']} | {r['rain'] or 'なし'} | {v_before:.0f}→{float(r['cs_speed_kmh']):.0f} "
                     f"| {cpa_before:.2f}→{float(r['cs_cpa_m']):.2f} | {float(r['cs_level_adj_db']):.0f} |")
        print(lines[-1], flush=True)
    lines += ["", "聞きどころ: after は車がゆっくり（5〜15 km/h）真横 1 m 前後を通る。エンジン音の高さは同じで音量だけ下げている（近似）。",
              "before は同じ場面を 11〜36 km/h（v10 で生活道路 30 km/h に合わせた範囲） で通る元の版。"]
    (OUT / "README_試聴.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for sub in ("_ds_before", "_ds_after"):
        shutil.rmtree(OUT / sub / "work", ignore_errors=True)
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
