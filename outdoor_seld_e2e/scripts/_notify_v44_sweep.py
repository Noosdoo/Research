# -*- coding: utf-8 -*-
"""v4.4 掃引ランナー — 宣言（2026-09-03 10:30）の実行器。

グリッド: DIR_H {25,40} × GAP_H {3,5} × K {None,2,3} = 12 構成。基準= v4.3（hold/flow なし）。
目的: 通知回数/クリップ 最小。制約（両半分）: 強到達（窓・方位）≥ base−1 / 抑制 ≥ base / リード中央 ≥ base−0.1s /
注意到達 ≥ base−2。勝ち= max(半分ごとの通知回数) 最小、同点は単純な方。
採用（fold30・fold31）: 通知回数 −20%以上・強到達 ≥ −1・リード ≥ −0.1s・抑制 悪化なし、両方で。

使い方:
  python scripts/_notify_v44_sweep.py <fold32 pred> <fold32 meta> <outdir> \
      --verify <fold30 pred> <fold30 meta> --verify <fold31 pred> <fold31 meta>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
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
V42 = _load("nv42", "step12_notify_v42_bearing.py")
V43 = _load("nv43", "step12_notify_v43.py")
V44 = _load("nv44", "step12_notify_v44.py")
AT = _load("nv43at", "_notify_v43_attrib.py")
SW = _load("nv42sw", "_notify_v42_sweep.py")
FPS, NFR = v4.FPS, 100
C43 = V43.Cfg43(**json.loads((ROOT / "out/notify_v43_sweep/winner.json").read_text()))


def grid():
    """第2グリッド（追記1）: H'（追跡系列hold）GAP_H {1,2,3}s × K {None,2,3}。先頭は基準 v4.3。"""
    out = [V44.Cfg44()]
    for gh in (1.0, 2.0, 3.0):
        for k in (None, 2, 3):
            out.append(V44.Cfg44(track_hold=True, gap_h=gh, flow_k=k))
    return out


def precompute(pred):
    """clip -> cls -> (az_at, eps43)。v4.3 の発火は一度だけ計算し、後段フィルタだけ振る。"""
    P = {}
    for clip, frames in pred.items():
        per = {}
        for cls in v4.DIST_CLASSES:
            d_at, az_at = V42.track_series2(frames, cls, NFR, C43)
            if not d_at:
                continue
            per[cls] = (az_at, V43.fires_cpa3(d_at, az_at, NFR, C43))
        P[clip] = per
    return P


def run_config(P, C, clips):
    res = {}
    for clip in clips:
        per_cls = {}
        for cls, (az_at, eps) in P[clip].items():
            f = V44.apply_filters(eps, az_at, C)
            if f:
                per_cls[cls] = f
        res[clip] = per_cls
    return res


def evaluate(P, events, meta_dir, C, clips, ncar):
    res = run_config(P, C, clips)
    s = SW.score_res(events, res, clips)
    # 方位帰属の強到達（AT.score_attrib は第1引数をクリップ集合としてしか使わない）
    sa = AT.score_attrib({c: None for c in clips}, meta_dir, res)
    n_ep = [sum(len(e) for e in res.get(c, {}).values()) for c in clips]
    one = [n for c, n in zip(clips, n_ep) if ncar.get(c) == "1"]
    s["ep_per_clip"] = float(np.mean(n_ep))
    s["multi1"] = float(100 * np.mean([n >= 2 for n in one])) if one else float("nan")
    s["strong_az"] = sa["strong"]
    return s


def ok(s, b):
    return (s["strong"] >= b["strong"] - 1.0 and s["strong_az"] >= b["strong_az"] - 1.0
            and s["safe"] >= b["safe"] and s["lead"] >= b["lead"] - 0.1 and s["caut"] >= b["caut"] - 2.0)


def fmt(s):
    return (f"通知{s['ep_per_clip']:.2f}/clip 1台2回以上{s['multi1']:.0f}% 強{s['strong']:.1f}%(方位{s['strong_az']:.1f}%) "
            f"注意{s['caut']:.1f}% 抑制{s['safe']:.1f}% リード{s['lead']:.2f}s")


def load_ncar(meta_dir):
    plan = meta_dir.parent / "plan"
    import csv
    out = {}
    for p in plan.glob("assignment_*.csv"):
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["clip_id"]] = r.get("n_car", "")
    return out


def main() -> int:
    pred_path, meta_dir, outdir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    pred = v4.load_pred(pred_path)
    clips = sorted(pred)
    events = SW.load_events(meta_dir, clips)
    ncar = load_ncar(meta_dir)
    P = precompute(pred)
    halves = {h: [c for c in clips if SW.half_of(c) == h] for h in (0, 1)}
    G = grid()
    base = {h: evaluate(P, events, meta_dir, G[0], halves[h], ncar) for h in (0, 1)}
    R = [f"# v4.4 掃引（fold32・偶奇ホールドアウト）pred={pred_path.name}", "",
         f"- 基準 v4.3 偶: {fmt(base[0])}", f"- 基準 v4.3 奇: {fmt(base[1])}", "",
         "| # | 構成 | 偶 | 奇 | 制約 |", "| --- | --- | --- | --- | --- |"]
    rows = []
    for i, C in enumerate(G[1:], start=1):
        s0, s1 = evaluate(P, events, meta_dir, C, halves[0], ncar), evaluate(P, events, meta_dir, C, halves[1], ncar)
        feas = ok(s0, base[0]) and ok(s1, base[1])
        rows.append((i, C, s0, s1, feas))
        R.append(f"| {i} | {V44.label44(C)} | {fmt(s0)} | {fmt(s1)} | {'✅' if feas else '—'} |")
        print(R[-1], flush=True)
    feas = [r for r in rows if r[4]]
    win = None
    if feas:
        win = min(feas, key=lambda r: (max(r[2]["ep_per_clip"], r[3]["ep_per_clip"]),
                                       r[1].gap_h, 0 if r[1].flow_k is None else r[1].flow_k))
    R += ["", "## 勝ち構成", ""]
    if win is None:
        R.append("制約を両半分で満たす構成なし → **採用なし**")
    else:
        i, C, s0, s1, _ = win
        R.append(f"- #{i} `{V44.label44(C)}`: 偶 {fmt(s0)} / 奇 {fmt(s1)}")
        (outdir / "winner.json").write_text(json.dumps(asdict(C), indent=2), encoding="utf-8")

    if win is not None:
        args = sys.argv
        idx = [k for k, a in enumerate(args) if a == "--verify"]
        for k in idx:
            vp, vm = Path(args[k + 1]), Path(args[k + 2])
            vpred = v4.load_pred(vp)
            vclips = sorted(vpred)
            vev = SW.load_events(vm, vclips)
            vnc = load_ncar(vm)
            VP = precompute(vpred)
            sb = evaluate(VP, vev, vm, G[0], vclips, vnc)
            sw = evaluate(VP, vev, vm, win[1], vclips, vnc)
            cond = (sw["ep_per_clip"] <= 0.8 * sb["ep_per_clip"] and sw["strong"] >= sb["strong"] - 1.0
                    and sw["lead"] >= sb["lead"] - 0.1 and sw["safe"] >= sb["safe"])
            R += ["", f"## 検証 {vp.parent.name}（使用済みデータ・開示）", "",
                  f"- v4.3: {fmt(sb)}", f"- 勝ち: {fmt(sw)}",
                  f"- 採用条件（通知−20%以上 / 強≥−1 / リード≥−0.1s / 抑制悪化なし）: {'✅' if cond else '❌'}"]
    (outdir / "sweep_report.md").write_text("\n".join(R) + "\n", encoding="utf-8")
    print("\n".join(R[-10:]))
    print("->", outdir / "sweep_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
