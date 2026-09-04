# -*- coding: utf-8 -*-
"""統一採点器（開発用 v2dev・2026-09-05）— 中立監査 §1〜§3 への対応。

宣言どおりの定義に揃える:
  1. 通知規則 = **v4.3（out/notify_v43_sweep/winner.json）＋警告音 hold**、帰属 = **車ごとの方位帰属**（同クラス・±0.5 s・方位差 ≤30°、
     `_notify_v43_attrib.attribute`）。旧 `_hp_score.py` は v4.2＋時間窓帰属だった
  2. 評価対象 = **plan（manifest）で固定**。予測が無いクリップも「発火ゼロ」として数える（旧: 予測があるクリップだけ走査）
  3. 距離の対応付け = **1 対 1**（同クラス・同フレーム・方位差 ≤20°、方位差の小さい順に貪欲）。旧: 予測ごとに最近傍 GT（GT を消費しない）
  4. 至近捕捉率 = **全至近 GT（≤1.5 m）を分母**（未検出も分母に入る）。旧「条件付き」（成立ペアだけが分母）も併記
  5. 3D 距離を出すモデル（ft2・v15c）は **予測側を d×cos(el) で水平に変換**してから水平 GT で採点（`ラベル=csv@h`）

使い方:
  python scripts/_score_unified.py <出力md> --plan <assignment.csv> [--split fold2] [--clip-max N] --meta <GTディレクトリ>
      [--minframe 40] [--bands 1.4,1.6,1.85,2.1] <ラベル>=<val_all_causal.csv>[@h] ...
  --minframe 0 で「起動直後を含む」値を出す（既定 40 = 因果推論の暖機 4 秒を除く。宣言と同じ）。
  --bands を付けると plan の mic_z で帯ごとの行も出す。
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

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
V43 = _load("nv43", "step12_notify_v43.py")
DG = _load("nv42diag", "_notify_v42_diag.py")
A = _load("nv43attrib", "_notify_v43_attrib.py")
H = _load("nhold", "step12_notify_v9b_hold.py")

C43 = V43.Cfg43(**json.loads((ROOT / "out/notify_v43_sweep/winner.json").read_text(encoding="utf-8")))
FPS = v4.FPS
DIST_CLS = {4, 6, 7}          # car / kick / bike（距離クラス）
AZ_PAIR = 20.0                # 距離対応の方位ゲート（旧と同じ）
TH_CLOSE, TH_SAFE = 1.5, 3.2


def dang(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def arg(argv, key, default=None):
    if key in argv:
        i = argv.index(key); v = argv[i + 1]; del argv[i:i + 2]; return v
    return default


def load_pred_rows(path: Path, horiz: bool):
    """clip -> frame -> [(cls, az, el, d)]。horiz なら d を d×cos(el) に。"""
    out = defaultdict(lambda: defaultdict(list))
    for line in open(path, encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) >= 7:
            clip, k, c, az, el = p[0], int(p[1]), int(p[2]), float(p[4]), float(p[5])
            d = float(p[6]) if p[6] not in ("", "nan") else float("nan")
        elif len(p) == 6:
            clip, k, c, az, el = p[0], int(p[1]), int(p[2]), float(p[3]), float(p[4])
            d = float(p[5])
        else:
            continue
        if horiz and math.isfinite(d):
            d = d * math.cos(math.radians(el))
        out[clip][k].append((c, az, el, d))
    return out


def load_gt(meta: Path, clip: str):
    """frame -> [(cls, trk, az, d)]（距離クラスのみ）"""
    f = meta / f"{clip}.csv"
    out = defaultdict(list)
    if not f.exists():
        return out
    for line in open(f, encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) < 6:
            continue
        c = int(g[1])
        if c in DIST_CLS:
            out[int(g[0])].append((c, int(g[2]), float(g[3]), float(g[5])))
    return out


def fires_of(frames):
    """v4.3＋hold の発火 [(frame, az, tier, d, cls)]（tier: 強/中/警告）。frames: frame -> [(cls, az, el, d)]"""
    frames_dist = {k: [(c, az, d) for c, az, el, d in v if math.isfinite(d)] for k, v in frames.items()}
    frames_warn = {k: [(c, az, el) for c, az, el, d in v] for k, v in frames.items()}
    fires = []
    res = V43.run_rule3({"x": frames_dist}, C43, nframes=100).get("x", {})
    for cls, lst in res.items():
        for j, az, tier, d in lst:
            fires.append((j, az, tier, d, cls))
    for k, cls, az in H.warn_fires(frames_warn, hold=True, nframes=100):
        fires.append((k, az, "警告", 0.0, cls))
    return sorted(fires)


def score_clips(pred, meta: Path, clips, minframe: int):
    stat = defaultdict(lambda: [0, 0]); n_strong = 0; leads = []; n_fire = 0; n_pred_clips = 0
    n_close_gt = n_close_det = n_close_cap = 0
    n_safe_pairs = n_safe_fp = 0
    rel = []; close_est = []; n_pairs = 0
    n_cond_close = n_cond_cap = 0
    for clip in clips:
        frames = pred.get(clip, {})
        if frames:
            n_pred_clips += 1
        gt = load_gt(meta, clip)
        # --- 通知（v4.3＋hold・方位帰属） ---
        evs = [DG.mk_event(c, t, fr) for c, t, fr in DG.gt_tracks(meta, clip)]
        fires = fires_of(frames) if frames else []
        n_fire += len(fires)
        att = A.attribute(fires, evs) if fires else []
        got = defaultdict(set); first = {}
        for f, i in zip(fires, att):
            if i is not None and f[0] <= evs[i]["cpa"] + FPS:
                got[i].add(f[2])
                first[i] = min(first.get(i, 10**9), f[0])
        for i, ev in enumerate(evs):
            hit = bool(got[i])
            if ev["tier"] == "safe":
                stat["safe"][1] += 1; stat["safe"][0] += int(not hit); continue
            stat[ev["tier"]][1] += 1; stat[ev["tier"]][0] += int(hit)
            if hit:
                leads.append((ev["cpa"] - first[i]) / FPS)
            if ev["tier"] == "critical" and "強" in got[i]:
                n_strong += 1
        # --- 距離（1 対 1・全 GT 分母） ---
        for k, gts in gt.items():
            if k < minframe:
                continue
            preds = [(c, az, d) for c, az, el, d in frames.get(k, []) if c in DIST_CLS and math.isfinite(d)]
            cand = []
            for gi, (gc, gt_trk, gaz, gd) in enumerate(gts):
                for pi, (pc, paz, pd) in enumerate(preds):
                    if pc == gc:
                        e = dang(paz, gaz)
                        if e <= AZ_PAIR:
                            cand.append((e, gi, pi))
            cand.sort()
            used_g, used_p = set(), set()
            match = {}
            for e, gi, pi in cand:
                if gi in used_g or pi in used_p:
                    continue
                used_g.add(gi); used_p.add(pi); match[gi] = pi
            for gi, (gc, gt_trk, gaz, gd) in enumerate(gts):
                if gd <= TH_CLOSE:
                    n_close_gt += 1
                if gi in match:
                    pd = preds[match[gi]][2]
                    n_pairs += 1
                    rel.append(abs(pd - gd) / max(gd, 0.1))
                    if gd <= TH_CLOSE:
                        n_close_det += 1; n_cond_close += 1
                        close_est.append(pd)
                        if pd <= TH_CLOSE:
                            n_close_cap += 1; n_cond_cap += 1
                    elif gd > TH_SAFE:
                        n_safe_pairs += 1
                        if pd <= TH_CLOSE:
                            n_safe_fp += 1
    g = lambda t: 100 * stat[t][0] / max(stat[t][1], 1)
    leads = np.array(leads) if leads else np.array([np.nan])
    return dict(
        crit=g("critical"), strong=100 * n_strong / max(stat["critical"][1], 1), caut=g("caution"), safe=g("safe"),
        n_crit=stat["critical"][1], n_caut=stat["caution"][1], n_safe=stat["safe"][1],
        lead=float(np.nanmedian(leads)), lead25=float(100 * np.nanmean(leads >= 2.5)), n_fire=n_fire,
        det_close=100 * n_close_det / max(n_close_gt, 1), cap_all=100 * n_close_cap / max(n_close_gt, 1),
        cap_cond=100 * n_cond_cap / max(n_cond_close, 1), n_close_gt=n_close_gt,
        fp=100 * n_safe_fp / max(n_safe_pairs, 1), close_med=float(np.median(close_est)) if close_est else float("nan"),
        dist_err=float(100 * np.median(rel)) if rel else float("nan"), n_pairs=n_pairs,
        n_clips=len(clips), n_pred_clips=n_pred_clips)


HEADER = ("| 予測 | 本数(予測あり) | 至近到達 | **強到達** | 注意到達 | 安全抑制 | リード中央 | ≥2.5s | 発火数 "
          "| 検出率(GT≤1.5m) | **至近捕捉(全GT)** | 至近捕捉(条件付) | 誤捕捉 | 至近推定距離 | **距離誤差(1対1)** |")
SEP = "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"


def fmt(label, s):
    return (f"| {label} | {s['n_clips']:,}({s['n_pred_clips']:,}) | {s['crit']:.1f}% | **{s['strong']:.1f}%** | {s['caut']:.1f}% "
            f"| {s['safe']:.1f}% | {s['lead']:.2f}s | {s['lead25']:.1f}% | {s['n_fire']:,} "
            f"| {s['det_close']:.1f}% | **{s['cap_all']:.1f}%** | {s['cap_cond']:.1f}% | {s['fp']:.2f}% | {s['close_med']:.2f}m "
            f"| **{s['dist_err']:.1f}%** ({s['n_pairs']:,}) |")


def main() -> int:
    argv = list(sys.argv[1:])
    plan = ROOT / arg(argv, "--plan")
    split = arg(argv, "--split", "fold2")
    clip_max = int(arg(argv, "--clip-max", "0"))
    meta = ROOT / arg(argv, "--meta")
    minframe = int(arg(argv, "--minframe", "40"))
    bands_s = arg(argv, "--bands", "")
    out_md = Path(argv[0])
    items = [a.split("=", 1) for a in argv[1:]]

    rows = []
    with open(plan, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("split", split) != split:
                continue
            if clip_max:
                m = re.search(r"mix(\d+)$", r["clip_id"])
                if m and int(m.group(1)) > clip_max:
                    continue
            rows.append(r)
    clips = [r["clip_id"] for r in rows]
    mic_z = {r["clip_id"]: float(r["mic_z"]) for r in rows if r.get("mic_z")}
    bands = [float(x) for x in bands_s.split(",")] if bands_s else []

    R = [f"# 統一採点（v4.3＋hold・方位帰属・manifest 固定・1対1・全GT分母） — {out_md.stem}", "",
         f"plan= {plan.relative_to(ROOT)} ({split}{f', mix≤{clip_max}' if clip_max else ''}) = {len(clips):,} 本 / GT= {meta.relative_to(ROOT)} / "
         f"frame≥{minframe} / v4.3 = {V43.label43(C43)}", "",
         "本数(予測あり)= manifest の本数（うち予測ファイルにあった本数。無い本は発火ゼロとして採点）。到達・抑制= 車ごとの方位帰属（±0.5 s・≤30°）。",
         "検出率= GT≤1.5 m のフレームのうち 1 対 1 で対応した割合。至近捕捉(全GT)= GT≤1.5 m のうち対応した予測が ≤1.5 m の割合（未検出は不捕捉）。",
         "至近捕捉(条件付)= 旧定義相当（対応したペアだけが分母）。誤捕捉= GT>3.2 m の対応ペアで予測 ≤1.5 m。距離誤差= 1 対 1 ペアの相対誤差中央値(ペア数)。", ""]
    print("\n".join(R[:3]), flush=True)
    R += [HEADER, SEP]
    per_band_rows = []
    for label, src in items:
        horiz = src.endswith("@h")
        p = Path(src[:-2] if horiz else src)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            R.append(f"| {label} | （未着: {p.name}） |"); print(R[-1], flush=True); continue
        pred = load_pred_rows(p, horiz)
        s = score_clips(pred, meta, clips, minframe)
        R.append(fmt(label + (" (予測を水平変換)" if horiz else ""), s)); print(R[-1], flush=True)
        if bands:
            for i in range(len(bands) - 1):
                lo, hi = bands[i], bands[i + 1]
                sub = [c for c in clips if c in mic_z and (lo <= mic_z[c] < hi or (i == len(bands) - 2 and mic_z[c] == hi))]
                if not sub:
                    continue
                sb = score_clips(pred, meta, sub, minframe)
                per_band_rows.append(fmt(f"{label} {lo}〜{hi} m", sb)); print(per_band_rows[-1], flush=True)
    if per_band_rows:
        R += ["", "## 高さの帯ごと（plan の mic_z）", "", HEADER, SEP] + per_band_rows
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(R) + "\n", encoding="utf-8")
    print("->", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
