# -*- coding: utf-8 -*-
"""v4.3 段階2 掃引ランナー — 宣言追記1（2026-09-03）の実行器。

グリッド: strong_adot_max ∈ {None, 0.25, 0.15} × dn ∈ {15, 12} × adot_th ∈ {0.10, 0.07} × rc_brg_win ∈ {5, 9, 13}
   = 36 構成（v4.2採用構成 = (None,15,0.10,5) を含む）
目的: 安全×すり抜け型の強の件数（**方位帰属**）を最小化
制約（両半分）: 強到達（窓帰属）≥ base−1pt / 安全抑制（窓帰属）≥ base−1pt / 安全×対向型 無発火 ≥ base−5pt
勝ち: 制約を両半分で満たす構成のうち max(半分ごとの誤強件数) 最小、同点は min(強到達) 最大
採用（fold30 検証）: 誤強 ≤ base×0.8、強到達 ≥ base−1pt、安全抑制 ≥ base−1pt

使い方:
  python scripts/_notify_v43_sweep.py <fold32 pred.csv> <fold32 meta_dir> <outdir> \
      --verify <fold30 pred.csv> <fold30 meta_dir>
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import defaultdict
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
DG = _load("nv42diag", "_notify_v42_diag.py")
Q2 = _load("nv42q2", "_notify_v42_q2_table.py")
AT = _load("nv43at", "_notify_v43_attrib.py")
SW = _load("nv42sw", "_notify_v42_sweep.py")     # score_res（窓帰属）・half_of・load_events

FPS, NFR = v4.FPS, 100
GRID_SA = (None, 0.25, 0.15)
GRID_DN = (15.0, 12.0)
GRID_ATH = (0.10, 0.07)
GRID_RCW = (5, 9, 13)


def grid():
    out = []
    for sa in GRID_SA:
        for dn in GRID_DN:
            for ath in GRID_ATH:
                for rcw in GRID_RCW:
                    out.append(V43.cfg43(strong_adot_max=sa, dn=dn, adot_th=ath, rc_brg_win=rcw))
    assert len(out) == 36
    return out


def precompute(pred):
    """clip -> cls -> (d_at, az_at, {j: (ddot, {win: adot})})  ※ link=True 固定（採用構成）"""
    C_link = V42.Cfg(link_pred=True)
    P = {}
    for clip, frames in pred.items():
        per = {}
        for cls in v4.DIST_CLASSES:
            d_at, az_at = V42.track_series2(frames, cls, NFR, C_link)
            if not d_at:
                continue
            st = {}
            for j in d_at:
                v = v4.closing_speed(d_at, j)
                st[j] = (None if v is None else -v,
                         {w: v4.azimuth_rate(az_at, j, win=w) for w in GRID_RCW})
            per[cls] = (d_at, az_at, st)
        P[clip] = per
    return P


def fires_from_stats(d_at, az_at, st, C):
    pre = {}
    for j, (ddot, adots) in st.items():
        d = d_at[j]
        adot, adot_rc = adots[C.brg_win], adots[C.rc_brg_win]
        dc, tc = v4.cpa_of(d, ddot, adot)
        rc = (C.route_c and adot_rc is not None and abs(adot_rc) <= C.adot_th
              and ddot is not None and ddot < -C.v_close and d <= C.dn)
        bok = C.strong_adot_max is None or (adot is not None and abs(adot) <= C.strong_adot_max)
        pre[j] = (dc, tc, rc, bok)

    def _cond(j, dc_th, tc_th, strong):
        dc, tc, rc, bok = pre.get(j, (None, None, False, True))
        cpa = dc is not None and dc <= dc_th and tc <= tc_th
        if strong:
            cpa = cpa and bok
        return cpa or rc

    def _stream(dc_th, tc_th, d_th, strong):
        a = V42._stream_mn(d_at, az_at, NFR, lambda j, d: _cond(j, dc_th, tc_th, strong),
                           C.confirm_m, C.confirm_n)
        b = V42._stream_mn(d_at, az_at, NFR, lambda j, d: d <= d_th, v4.CONFIRM, v4.CONFIRM)
        return sorted(set(a) | set(b))

    return v4._episodes_with_upgrade(_stream(C.cpa_mid, v4.TTC_CAUTION, v4.SUPP, False),
                                     _stream(C.cpa_strong, v4.TTC_WARN, v4.T3, True))


def run_config(P, C, clips):
    res = {}
    for clip in clips:
        per_cls = {}
        for cls, (d_at, az_at, st) in P[clip].items():
            eps = fires_from_stats(d_at, az_at, st, C)
            if eps:
                per_cls[cls] = eps
        res[clip] = per_cls
    return res


def false_strong_attrib(events, res, clips):
    """安全×すり抜け型の強（方位帰属）の件数と母数。"""
    n, m = 0, 0
    for clip in clips:
        evs = events[clip]
        fires = [(f[0], f[1], f[2], f[3], cls) for cls, eps in res.get(clip, {}).items() for f in eps]
        att = AT.attribute(fires, evs)
        hit = set()
        for f, i in zip(fires, att):
            if i is not None and f[2] == "強":
                hit.add(i)
        for i, ev in enumerate(evs):
            if ev["tier"] == "safe" and ev.get("q2type") == "すり抜け型":
                m += 1
                n += int(i in hit)
    return n, m


def evaluate(P, events, C, clips):
    res = run_config(P, C, clips)
    s = SW.score_res(events, res, clips)
    fs, m = false_strong_attrib(events, res, clips)
    s["fs"], s["fs_n"] = fs, m
    return s


def ok(s, base):
    return (s["strong"] >= base["strong"] - 1.0 and s["safe"] >= base["safe"] - 1.0
            and s["safe_ho"] >= base["safe_ho"] - 5.0)


def fmt(s):
    return (f"誤強{s['fs']}/{s['fs_n']} 強{s['strong']:.1f}% 抑制{s['safe']:.1f}% "
            f"安全×対向無{s['safe_ho']:.0f}% リード{s['lead']:.2f}s")


def main() -> int:
    pred_path, meta_dir, outdir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    pred = v4.load_pred(pred_path)
    clips = sorted(pred)
    events = SW.load_events(meta_dir, clips)
    P = precompute(pred)
    halves = {h: [c for c in clips if SW.half_of(c) == h] for h in (0, 1)}
    G = grid()
    base_idx = next(i for i, C in enumerate(G) if C == V43.cfg43())
    rows = []
    R = [f"# v4.3 段階2 掃引（fold32・偶奇ホールドアウト）pred={pred_path.name}", "",
         f"- 分割: 偶 {len(halves[0])} / 奇 {len(halves[1])} クリップ。36構成。基準= v4.2採用構成",
         "- 目的= 安全×すり抜け型の強（方位帰属）最小、制約= 強到達≥base−1 / 抑制≥base−1 / 安全×対向型無≥base−5（両半分）", ""]
    base = {}
    for h in (0, 1):
        base[h] = evaluate(P, events, G[base_idx], halves[h])
        R.append(f"- v4.2基準 半分{h}: {fmt(base[h])}")
    R += ["", "| # | 構成 | 偶 | 奇 | 制約 |", "| --- | --- | --- | --- | --- |"]
    for i, C in enumerate(G):
        s0, s1 = evaluate(P, events, C, halves[0]), evaluate(P, events, C, halves[1])
        feas = ok(s0, base[0]) and ok(s1, base[1])
        rows.append((i, C, s0, s1, feas))
        R.append(f"| {i} | {V43.label43(C)} | {fmt(s0)} | {fmt(s1)} | {'✅' if feas else '—'} |")
        print(R[-1], flush=True)
    feas = [r for r in rows if r[4]]
    win = None
    if feas:
        win = min(feas, key=lambda r: (max(r[2]["fs"], r[3]["fs"]), -min(r[2]["strong"], r[3]["strong"])))
    R += ["", "## 勝ち構成（min-max）", ""]
    if win is None:
        R.append("制約を両半分で満たす構成なし → **採用なし**")
    else:
        i, C, s0, s1, _ = win
        R += [f"- #{i} `{V43.label43(C)}`: 偶 {fmt(s0)} / 奇 {fmt(s1)}",
              f"- 基準からの差: 誤強 max {max(base[0]['fs'], base[1]['fs'])} → {max(s0['fs'], s1['fs'])}"]
        (outdir / "winner.json").write_text(json.dumps(asdict(C), indent=2), encoding="utf-8")

    if "--verify" in sys.argv and win is not None:
        vp, vm = Path(sys.argv[sys.argv.index("--verify") + 1]), Path(sys.argv[sys.argv.index("--verify") + 2])
        vpred = v4.load_pred(vp)
        vclips = sorted(vpred)
        vevents = SW.load_events(vm, vclips)
        VP = precompute(vpred)
        sb = evaluate(VP, vevents, G[base_idx], vclips)
        sw = evaluate(VP, vevents, win[1], vclips)
        cond = (sw["fs"] <= 0.8 * sb["fs"] and sw["strong"] >= sb["strong"] - 1.0
                and sw["safe"] >= sb["safe"] - 1.0)
        R += ["", f"## fold30 検証（{vp.name}・2回目の使用）", "",
              f"- v4.2基準: {fmt(sb)}", f"- 勝ち構成: {fmt(sw)}",
              f"- 採用条件（誤強≤base×0.8 / 強≥base−1 / 抑制≥base−1）: {'✅ **採用**' if cond else '❌ **採用なし**'}"]
    (outdir / "sweep_report.md").write_text("\n".join(R) + "\n", encoding="utf-8")
    print("\n".join(R[-8:]))
    print("->", outdir / "sweep_report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
