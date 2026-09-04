# -*- coding: utf-8 -*-
"""マイク高さの帯ごとの採点（2026-09-05）。v15 系（高さ 1.4〜2.1 m を行ごとに引いた val）の予測を、
plan の mic_z で帯に分けて `_hp_score.row` と同じ列で採点する（頑健性の副指標 = v15 宣言 §5.4）。

使い方:
  python scripts/_band_score.py <出力md> --plan out/dataset_outdoor_siren_v15/plan/assignment_v15.csv \
      --meta out/dataset_outdoor_siren_v15/metadata_dist [--bands 1.4,1.6,1.85,2.1] [--clip-max 9000] \
      <ラベル>=<val_all_causal.csv> ...
  --clip-max N: clip_id の mix 番号が N 以下の行だけ使う（v16 val から v15 val 部分を抜くとき）
帯ごとに予測 csv を絞った一時ファイルを作り、GT ディレクトリはそのまま（採点は予測側のクリップ集合で回る）。
"""
from __future__ import annotations

import csv
import importlib.util
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


HP = _load("hpscore", "_hp_score.py")


def arg(argv, key, default=None):
    if key in argv:
        i = argv.index(key)
        v = argv[i + 1]
        del argv[i:i + 2]
        return v
    return default


def main() -> int:
    argv = list(sys.argv[1:])
    plan = ROOT / arg(argv, "--plan", "out/dataset_outdoor_siren_v15/plan/assignment_v15.csv")
    meta = ROOT / arg(argv, "--meta", "out/dataset_outdoor_siren_v15/metadata_dist")
    bands = [float(x) for x in arg(argv, "--bands", "1.4,1.6,1.85,2.1").split(",")]
    clip_max = int(arg(argv, "--clip-max", "0"))
    out_md = Path(argv[0])
    items = [a.split("=", 1) for a in argv[1:]]
    HP.META = meta

    mic_z = {}
    with open(plan, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mic_z[r["clip_id"]] = float(r["mic_z"])

    def band_of(clip):
        z = mic_z.get(clip)
        if z is None:
            return None
        for i in range(len(bands) - 1):
            if bands[i] <= z <= bands[i + 1] + (1e-9 if i == len(bands) - 2 else -1e-9):
                return i
        return None

    def keep(clip):
        if clip_max:
            m = re.search(r"mix(\d+)$", clip)
            if not m or int(m.group(1)) > clip_max:
                return False
        return True

    labels = [f"{bands[i]}〜{bands[i+1]} m" for i in range(len(bands) - 1)]
    R = [f"# 高さ帯ごとの採点 — {out_md.stem}", "",
         f"plan= {plan.relative_to(ROOT)} / GT= {meta.relative_to(ROOT)}" + (f" / mix≤{clip_max}" if clip_max else ""),
         "列は `_hp_score.py` と同じ（通知 v4.2 採用構成・至近捕捉= GT≤1.5 m を 1.5 m で捕まえる率・距離誤差= 方位 20° 以内ペアの相対誤差中央値）。", ""]
    tmpdir = Path(tempfile.mkdtemp(prefix="band_"))
    for label, src in items:
        p = Path(src)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            R.append(f"（未着: {p.name}）")
            continue
        lines = [ln for ln in open(p, encoding="utf-8") if ln.strip()]
        per = {i: [] for i in range(len(bands) - 1)}
        n_clip = {i: set() for i in range(len(bands) - 1)}
        for ln in lines:
            clip = ln.split(",", 1)[0]
            if not keep(clip):
                continue
            b = band_of(clip)
            if b is not None:
                per[b].append(ln)
                n_clip[b].add(clip)
        allf = tmpdir / f"{label}_all.csv"
        allf.write_text("".join(ln for ln in lines if keep(ln.split(',', 1)[0])), encoding="utf-8")
        R += [f"## {label}", "",
              "| 帯（本数） | 至近到達 | **強到達** | 注意到達 | 安全抑制 | リード中央 | ≥2.5s | 発火数 "
              "| 至近捕捉 | 誤捕捉 | 至近推定距離 | 距離誤差 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        n_all = len({ln.split(',', 1)[0] for ln in lines if keep(ln.split(',', 1)[0])})
        R.append(HP.row(f"全体（{n_all:,}）", allf))
        print(R[-1], flush=True)
        for i in range(len(bands) - 1):
            f = tmpdir / f"{label}_b{i}.csv"
            f.write_text("".join(per[i]), encoding="utf-8")
            R.append(HP.row(f"{labels[i]}（{len(n_clip[i]):,}）", f))
            print(R[-1], flush=True)
        R.append("")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(R) + "\n", encoding="utf-8")
    print("->", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
