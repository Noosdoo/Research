# -*- coding: utf-8 -*-
"""v4.2 Phase A/B 掃引ランナー — 事前宣言（2026-08-30）の実行器。

宣言= md/design/通知v4.2_選定手順の事前宣言_2026-08-30.md。このスクリプトは宣言の
グリッド・分割（mix番号の偶奇・両向きホールドアウト）・方針（至近重視/安全維持）を
**そのまま**実装する。グリッドや方針をここで変えないこと（変える場合は宣言に追記してから）。

使い方:
  Phase A:    python scripts/_notify_v42_sweep.py <pred.csv> <meta_dir> <outdir>
  Phase B:    python scripts/_notify_v42_sweep.py <pred.csv> <meta_dir> <outdir> --phase B
              （<outdir>/phaseA_winner.json の勝ち構成を土台にしきい値を振る）
  機構テスト: python scripts/_notify_v42_sweep.py <pred.csv> <meta_dir> <outdir> \
                  --mechanics [--limit 300]
              → ランダム構成で fires_cpa2（正実装）との**完全一致**を検証し、
                小規模の通し実行をする。**選定には使わない**（出力にも明記される）。

高速化: 微分（LSQ傾き・Theil–Sen・方位変化率×3窓）をクリップごとに前計算する。
前計算経路と正実装のドリフトは --mechanics の一致検証で担保する。
"""
from __future__ import annotations

import importlib.util
import json
import random
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
DG = _load("nv42diag", "_notify_v42_diag.py")

FPS, NFR = v4.FPS, 100
WIN_PRE = WIN_POST = 1.0
BRG_WINS = (5, 9, 13)
SAFE_SLACK = 3.0                       # 至近重視: 抑制 ≥ base−3pt（宣言§4）


# ---------------------------------------------------------------- 宣言グリッド
def phase_a_grid():
    out = []
    for rs in (False, True):
        for bw in BRG_WINS:
            for m, n in ((4, 4), (4, 6), (3, 5)):
                for rc in (None, (0.05, 8.0), (0.05, 15.0), (0.10, 8.0),
                           (0.10, 15.0), (0.20, 8.0), (0.20, 15.0)):
                    for lp in (False, True):
                        kw = dict(robust_slope=rs, brg_win=bw,
                                  confirm_m=m, confirm_n=n, link_pred=lp)
                        if rc:
                            kw.update(route_c=True, adot_th=rc[0], dn=rc[1])
                        out.append(V42.Cfg(**kw))
    assert len(out) == 252, len(out)
    return out


def phase_b_grid(base: "V42.Cfg"):
    out = []
    ths = ([round(base.adot_th + d, 2) for d in (-0.05, 0.0, 0.05) if base.adot_th + d > 0]
           if base.route_c else [base.adot_th])
    for cs in (0.7, 0.85, 1.0, 1.15, 1.3):
        for cm in (1.6, 2.0, 2.4):
            for th in ths:
                out.append(V42.Cfg(**{**asdict(base), "cpa_strong": cs,
                                      "cpa_mid": cm, "adot_th": th}))
    return out


# ------------------------------------------------------------------- 前計算
def precompute(pred):
    """clip -> (link, cls) -> (d_at, az_at, {j: (ddot_lsq, ddot_ts, {win: adot})})"""
    C_link = V42.Cfg(link_pred=True)
    P = {}
    for clip, frames in pred.items():
        per = {}
        for link in (False, True):
            for cls in v4.DIST_CLASSES:
                d_at, az_at = (V42.track_series2(frames, cls, NFR, C_link) if link
                               else v4.track_series(frames, cls, NFR))
                if not d_at:
                    continue
                st = {}
                for j in d_at:
                    v = v4.closing_speed(d_at, j)
                    _, ts = V42.robust_stats(d_at, j, v4.VEL_WIN)
                    adots = {w: v4.azimuth_rate(az_at, j, win=w) for w in BRG_WINS}
                    st[j] = (None if v is None else -v, ts, adots)
                per[(link, cls)] = (d_at, az_at, st)
        P[clip] = per
    return P


def fires_from_stats(d_at, az_at, st, C):
    """fires_cpa2 と同一の発火を前計算から出す（一致は --mechanics で検証）。"""
    assert not C.robust_scale, "robust_scaleは宣言グリッド外"
    pre = {}
    for j, (ddot_lsq, ddot_ts, adots) in st.items():
        d = d_at[j]
        ddot = ddot_ts if C.robust_slope else ddot_lsq
        adot = adots[C.brg_win]
        dc, tc = v4.cpa_of(d, ddot, adot)
        rc = (C.route_c and adot is not None and abs(adot) <= C.adot_th
              and ddot is not None and ddot < -C.v_close and d <= C.dn)
        pre[j] = (dc, tc, rc)

    def _cond(j, dc_th, tc_th):
        dc, tc, rc = pre.get(j, (None, None, False))
        return (dc is not None and dc <= dc_th and tc <= tc_th) or rc

    def _stream(dc_th, tc_th, d_th):
        a = V42._stream_mn(d_at, az_at, NFR, lambda j, d: _cond(j, dc_th, tc_th),
                           C.confirm_m, C.confirm_n)
        b = V42._stream_mn(d_at, az_at, NFR, lambda j, d: d <= d_th,
                           v4.CONFIRM, v4.CONFIRM)
        return sorted(set(a) | set(b))

    return v4._episodes_with_upgrade(
        _stream(C.cpa_mid, v4.TTC_CAUTION, v4.SUPP),
        _stream(C.cpa_strong, v4.TTC_WARN, v4.T3))


def run_config(P, C, clips):
    res = {}
    for clip in clips:
        per_cls = {}
        for (link, cls), (d_at, az_at, st) in P[clip].items():
            if link != C.link_pred:
                continue
            eps = fires_from_stats(d_at, az_at, st, C)
            if eps:
                per_cls[cls] = eps
        res[clip] = per_cls
    return res


# --------------------------------------------------------------------- 採点
ADOT_SPLIT = 0.10          # [rad/s] 型分類（_notify_v42_q2_table.py と同一の定義を保つ）


def q2type(fr, cpa):
    """判定時窓（CPAの2.5〜1.5秒前）のGT|dθ/dt|中央値で 対向型/すり抜け型 を分ける。"""
    js = [j for j in sorted(fr) if cpa - 25 <= j <= cpa - 15]
    if len(js) < 4:
        return None
    unw = np.unwrap(np.radians([fr[j][0] for j in js]))
    d = np.abs(np.diff(unw)) * FPS / np.diff(js)
    return "対向型" if float(np.median(d)) < ADOT_SPLIT else "すり抜け型"


def load_events(meta_dir, clips):
    out = {}
    for c in clips:
        evs = []
        for cl, t, fr in DG.gt_tracks(meta_dir, c):
            ev = DG.mk_event(cl, t, fr)
            ev["q2type"] = q2type(fr, ev["cpa"])
            evs.append(ev)
        out[c] = evs
    return out


def score_res(events, res, clips):
    """_notify_v42_eval.score() と同じ規則（イベント窓・貪欲マッチ・強=強tierのみ）。"""
    stat = defaultdict(lambda: [0, 0])
    ho = [0, 0]                 # ガードレール用: 安全×対向型の [無発火, 母数]
    n_strong_hit, leads, n_fire = 0, [], 0
    for clip in sorted(clips):
        fires = [(f[0], f[1], f[2], f[3], cls)
                 for cls, eps in res.get(clip, {}).items() for f in eps]
        n_fire += len(fires)
        used = [False] * len(fires)
        used_s = [False] * len(fires)
        for ev in events[clip]:
            a, b = ev["f0"] - WIN_PRE * FPS, ev["cpa"] + WIN_POST * FPS
            hit = None
            for i, fr_ in enumerate(fires):
                if not used[i] and fr_[4] == ev["cls"] and a <= fr_[0] <= b:
                    hit = i
                    break
            if ev["tier"] == "safe":
                stat["safe"][1] += 1
                stat["safe"][0] += int(hit is None)
                if ev.get("q2type") == "対向型":
                    ho[1] += 1
                    ho[0] += int(hit is None)
                if hit is not None:
                    used[hit] = True
                continue
            stat[ev["tier"]][1] += 1
            if hit is not None:
                used[hit] = True
                stat[ev["tier"]][0] += 1
                leads.append((ev["cpa"] - fires[hit][0]) / FPS)
            if ev["tier"] == "critical":
                for i, fr_ in enumerate(fires):
                    if (not used_s[i] and fr_[4] == ev["cls"] and fr_[2] == "強"
                            and a <= fr_[0] <= b):
                        used_s[i] = True
                        n_strong_hit += 1
                        break
    L = np.array(leads) if leads else np.array([0.0])
    g = lambda t: 100 * stat[t][0] / max(stat[t][1], 1)
    return dict(crit=g("critical"),
                strong=100 * n_strong_hit / max(stat["critical"][1], 1),
                caut=g("caution"), safe=g("safe"), lead=float(np.median(L)),
                lead25=float(100 * np.mean(L >= 2.5)), n_fire=n_fire,
                safe_ho=100 * ho[0] / max(ho[1], 1), n_safe_ho=ho[1])


# ------------------------------------------------------------- 分割と方針
def half_of(clip: str) -> int:
    m = re.search(r"mix(\d+)$", clip)
    assert m, clip
    return int(m.group(1)) % 2


def constraint_ok(policy, s, base):
    """宣言§4の方針制約。"""
    if policy == "至近重視":
        return s["safe"] >= base["safe"] - SAFE_SLACK
    return s["safe"] >= base["safe"] and s["strong"] >= base["strong"]


def pick(rows, base, policy):
    """rows=[(idx, C, s)] から宣言§4の方針で1つ選ぶ。該当なしなら None。"""
    ok = [r for r in rows if constraint_ok(policy, r[2], base)]
    if not ok:
        return None
    return max(ok, key=lambda r: (r[2]["strong"], r[2]["lead25"], -r[0]))


def fmt(s):
    return (f"強{s['strong']:.1f}% 至近{s['crit']:.1f}% 抑制{s['safe']:.1f}% "
            f"リード{s['lead']:.2f}s ≥2.5s {s['lead25']:.1f}%")


def cfg_label(C):
    parts = []
    if C.robust_slope:
        parts.append("ts")
    parts.append(f"brg{C.brg_win}")
    parts.append(f"mn{C.confirm_m}/{C.confirm_n}")
    if C.route_c:
        parts.append(f"rc({C.adot_th:.2f},{C.dn:.0f})")
    if C.link_pred:
        parts.append("link")
    if (C.cpa_strong, C.cpa_mid) != (v4.CPA_STRONG_M, v4.CPA_MID_M):
        parts.append(f"cs{C.cpa_strong}/cm{C.cpa_mid}")
    return "+".join(parts) or "全OFF"


# ----------------------------------------------------------------- 実行本体
def sweep(pred, meta_dir, outdir, grid, tag, mechanics=False):
    clips = sorted(pred.keys())
    print(f"[{tag}] クリップ {len(clips):,} / 構成 {len(grid)}", flush=True)
    P = precompute(pred)
    events = load_events(meta_dir, clips)
    halves = {h: [c for c in clips if half_of(c) == h] for h in (0, 1)}
    base_cfg = V42.Cfg()

    results = {}                        # half -> [(idx, C, s)]
    bases = {}
    for h in (0, 1):
        hc = halves[h]
        bases[h] = score_res(events, run_config(P, base_cfg, hc), hc)
        rows = []
        for idx, C in enumerate(grid):
            s = score_res(events, run_config(P, C, hc), hc)
            rows.append((idx, C, s))
            if (idx + 1) % 50 == 0:
                print(f"  half{h}: {idx+1}/{len(grid)}", flush=True)
        results[h] = rows

    R = [f"# v4.2 {tag} 掃引結果", ""]
    if mechanics:
        R += ["⚠️ **機構テスト（既存val・選定には使わない）**", ""]
    R += [f"- 分割: mix番号の偶奇（偶 {len(halves[0]):,} / 奇 {len(halves[1]):,}クリップ）",
          f"- v4.1基準: 偶[{fmt(bases[0])}] / 奇[{fmt(bases[1])}]", ""]
    winner_out = {}
    for policy in ("至近重視", "安全維持"):
        R.append(f"## 方針: {policy}")
        chosen = {}
        for h in (0, 1):
            w = pick(results[h], bases[h], policy)
            chosen[h] = w
            other = 1 - h
            if w is None:
                R.append(f"- half{h}で選定: **該当なし**")
                continue
            idx, C, s = w
            s_o = score_res(events, run_config(P, C, halves[other]), halves[other])
            R += [f"- half{h}で選定 → `{cfg_label(C)}`",
                  f"  - 選定側: {fmt(s)}",
                  f"  - ホールドアウト(half{other}): {fmt(s_o)}"
                  f"（v4.1比 強{s_o['strong']-bases[other]['strong']:+.1f}pt "
                  f"抑制{s_o['safe']-bases[other]['safe']:+.1f}pt）",
                  f"  - 安全×対向型の抑制（ガードレール指標）: 選定側 "
                  f"{bases[h]['safe_ho']:.0f}%→{s['safe_ho']:.0f}% "
                  f"(n={s['n_safe_ho']}) / ホールドアウト "
                  f"{bases[other]['safe_ho']:.0f}%→{s_o['safe_ho']:.0f}% "
                  f"(n={s_o['n_safe_ho']})"]
        same = (chosen[0] is not None and chosen[1] is not None
                and chosen[0][0] == chosen[1][0])
        R.append(f"- **両分割の一致**: {'✅ 同一構成' if same else '❌ 不一致（採用条件を満たさない）'}")
        if same:
            # 宣言§4.5のガードレール: 安全×対向型の抑制がどちらかの半分で
            # v4.1比30pt超悪化していたら、方針を満たしても採用しない（繰り上げなし）
            viol = any(bases[h]["safe_ho"] - chosen[h][2]["safe_ho"] > 30.0
                       for h in (0, 1))
            if viol:
                R.append("- ⚠️ **ガードレール抵触（宣言§4.5）: 安全×対向型の抑制が"
                         "v4.1比30pt超悪化 → 採用なし（次点繰り上げはしない）**")
            else:
                winner_out[policy] = asdict(chosen[0][1])
        R.append("")
    # 全構成の生表（監査用）
    csv_path = outdir / f"{tag}_all.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("half,idx,label,strong,crit,caut,safe,lead,lead25,n_fire\n")
        for h in (0, 1):
            for idx, C, s in results[h]:
                f.write(f"{h},{idx},{cfg_label(C)},{s['strong']:.2f},{s['crit']:.2f},"
                        f"{s['caut']:.2f},{s['safe']:.2f},{s['lead']:.2f},"
                        f"{s['lead25']:.2f},{s['n_fire']}\n")
    (outdir / f"{tag}_report.md").write_text("\n".join(R), encoding="utf-8")
    if winner_out and not mechanics:
        (outdir / f"{tag}_winner.json").write_text(
            json.dumps(winner_out, indent=2), encoding="utf-8")
    print("\n".join(R))
    print("->", outdir / f"{tag}_report.md")


def sweep_minmax(pred, meta_dir, outdir, grid, tag, verify=None):
    """宣言§7.4の min-max 安定規則（fold31用）。

    両方の半分で方針制約を満たす構成のうち min(強到達_偶, 強到達_奇) 最大を選ぶ。
    同率は min(リード≥2.5s) 最大 → 構成番号最小。
    verify=(fold30のpred CSV, meta_dir) を渡すと、勝ち構成の fold30 検証と
    採用判定（§7.4の(i)(ii)(iii)）まで行う（Phase B' で使う）。
    """
    clips = sorted(pred.keys())
    print(f"[{tag}] クリップ {len(clips):,} / 構成 {len(grid)}", flush=True)
    P = precompute(pred)
    events = load_events(meta_dir, clips)
    halves = {h: [c for c in clips if half_of(c) == h] for h in (0, 1)}
    base_cfg = V42.Cfg()
    bases = {h: score_res(events, run_config(P, base_cfg, halves[h]), halves[h])
             for h in (0, 1)}
    rows = {0: [], 1: []}
    for idx, C in enumerate(grid):
        for h in (0, 1):
            rows[h].append(score_res(events, run_config(P, C, halves[h]), halves[h]))
        if (idx + 1) % 50 == 0:
            print(f"  {idx+1}/{len(grid)}", flush=True)

    R = [f"# v4.2 {tag} 掃引結果（min-max規則・宣言§7.4）", "",
         f"- 分割: mix番号の偶奇（偶 {len(halves[0]):,} / 奇 {len(halves[1]):,}クリップ）",
         f"- v4.1基準: 偶[{fmt(bases[0])}] / 奇[{fmt(bases[1])}]", ""]
    winner_out = {}
    for policy in ("至近重視", "安全維持"):
        R.append(f"## 方針: {policy}")
        cand = [i for i in range(len(grid))
                if constraint_ok(policy, rows[0][i], bases[0])
                and constraint_ok(policy, rows[1][i], bases[1])]
        if not cand:
            R += ["- **候補なし**（両半分で制約を満たす構成が無い）", ""]
            continue
        w = max(cand, key=lambda i: (min(rows[0][i]["strong"], rows[1][i]["strong"]),
                                     min(rows[0][i]["lead25"], rows[1][i]["lead25"]),
                                     -i))
        C = grid[w]
        gr31 = all(bases[h]["safe_ho"] - rows[h][w]["safe_ho"] <= 30.0 for h in (0, 1))
        R += [f"- 勝ち構成（候補{len(cand)}件中）→ `{cfg_label(C)}`",
              f"  - 偶: {fmt(rows[0][w])}（v4.1比 強{rows[0][w]['strong']-bases[0]['strong']:+.1f}pt "
              f"抑制{rows[0][w]['safe']-bases[0]['safe']:+.1f}pt）",
              f"  - 奇: {fmt(rows[1][w])}（v4.1比 強{rows[1][w]['strong']-bases[1]['strong']:+.1f}pt "
              f"抑制{rows[1][w]['safe']-bases[1]['safe']:+.1f}pt）",
              f"  - min(強到達) = {min(rows[0][w]['strong'], rows[1][w]['strong']):.1f}%",
              f"  - 安全×対向型（ガードレール指標）: "
              f"偶 {bases[0]['safe_ho']:.0f}%→{rows[0][w]['safe_ho']:.0f}% (n={rows[0][w]['n_safe_ho']}) / "
              f"奇 {bases[1]['safe_ho']:.0f}%→{rows[1][w]['safe_ho']:.0f}% (n={rows[1][w]['n_safe_ho']})"
              f" → {'✅' if gr31 else '❌ 30pt超悪化'}", ""]
        winner_out[policy] = dict(cfg=asdict(C), guard31=gr31)

    with open(outdir / f"{tag}_all.csv", "w", encoding="utf-8") as f:
        f.write("half,idx,label,strong,crit,caut,safe,safe_ho,lead,lead25,n_fire\n")
        for h in (0, 1):
            for idx, C in enumerate(grid):
                s = rows[h][idx]
                f.write(f"{h},{idx},{cfg_label(C)},{s['strong']:.2f},{s['crit']:.2f},"
                        f"{s['caut']:.2f},{s['safe']:.2f},{s['safe_ho']:.2f},"
                        f"{s['lead']:.2f},{s['lead25']:.2f},{s['n_fire']}\n")

    if verify and winner_out:
        R.append("## fold30 検証と採用判定（宣言§7.4）")
        vpred = v4.load_pred(Path(verify[0]))
        vclips = sorted(vpred.keys())
        vP = precompute(vpred)
        vevents = load_events(Path(verify[1]), vclips)
        vbase = score_res(vevents, run_config(vP, base_cfg, vclips), vclips)
        R.append(f"- fold30全体のv4.1基準: {fmt(vbase)} / 安全×対向型 {vbase['safe_ho']:.0f}%")
        for policy, wo in winner_out.items():
            C = V42.Cfg(**wo["cfg"])
            vs = score_res(vevents, run_config(vP, C, vclips), vclips)
            ok_i = vs["strong"] - vbase["strong"] >= 1.0
            ok_ii = vs["safe"] >= vbase["safe"] - 3.0
            ok_iii = wo["guard31"] and (vbase["safe_ho"] - vs["safe_ho"] <= 30.0)
            wo["adopted"] = bool(ok_i and ok_ii and ok_iii)
            R += [f"- **{policy}** `{cfg_label(C)}` の fold30: {fmt(vs)} / "
                  f"安全×対向型 {vs['safe_ho']:.0f}%",
                  f"  - (i) 強 {vs['strong']-vbase['strong']:+.1f}pt ≥ +1pt: "
                  f"{'✅' if ok_i else '❌'} / (ii) 抑制 {vs['safe']-vbase['safe']:+.1f}pt "
                  f"≥ −3pt: {'✅' if ok_ii else '❌'} / (iii) ガードレール: "
                  f"{'✅' if ok_iii else '❌'}",
                  f"  - **採用判定: {'✅ 採用' if wo['adopted'] else '❌ 採用なし'}**", ""]

    (outdir / f"{tag}_report.md").write_text("\n".join(R), encoding="utf-8")
    (outdir / f"{tag}_winner.json").write_text(
        json.dumps(winner_out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n".join(R))
    print("->", outdir / f"{tag}_report.md")


def verify_against_reference(pred, n_cfg=6, n_clip=30, seed=20260830):
    """前計算経路 fires_from_stats == 正実装 fires_cpa2 の完全一致検証。"""
    rng = random.Random(seed)
    grid = phase_a_grid()
    cfgs = rng.sample(grid, n_cfg)
    # しきい値も動かした構成を2つ足す（Phase B相当の経路検証）
    cfgs += [V42.Cfg(**{**asdict(rng.choice(grid)), "cpa_strong": 0.7, "cpa_mid": 2.4}),
             V42.Cfg(**{**asdict(rng.choice(grid)), "cpa_strong": 1.3, "cpa_mid": 1.6})]
    clips = rng.sample(sorted(pred.keys()), min(n_clip, len(pred)))
    sub = {c: pred[c] for c in clips}
    P = precompute(sub)
    for k, C in enumerate(cfgs):
        fast = run_config(P, C, clips)
        slow = V42.run_rule2(sub, C)
        assert fast == slow, f"前計算経路が正実装と不一致: cfg={cfg_label(C)}"
        print(f"  一致検証 {k+1}/{len(cfgs)}: {cfg_label(C)} ✅", flush=True)
    print(f"一致検証 PASS（構成{len(cfgs)}×クリップ{len(clips)}）")


def main() -> int:
    pred_path, meta_dir = Path(sys.argv[1]), Path(sys.argv[2])
    outdir = Path(sys.argv[3])
    outdir.mkdir(parents=True, exist_ok=True)
    phase = sys.argv[sys.argv.index("--phase") + 1] if "--phase" in sys.argv else "A"
    rule = sys.argv[sys.argv.index("--rule") + 1] if "--rule" in sys.argv else "argmax"
    mech = "--mechanics" in sys.argv
    limit = (int(sys.argv[sys.argv.index("--limit") + 1])
             if "--limit" in sys.argv else 0)
    verify = None
    if "--verify-pred" in sys.argv:
        verify = (sys.argv[sys.argv.index("--verify-pred") + 1],
                  sys.argv[sys.argv.index("--verify-meta") + 1])

    pred = v4.load_pred(pred_path)
    if limit:
        keep = sorted(pred.keys())[:limit]
        pred = {c: pred[c] for c in keep}

    if mech:
        print("== 機構テスト（選定には使わない） ==", flush=True)
        verify_against_reference(pred)
        sweep(pred, meta_dir, outdir, phase_a_grid(), "mechanicsA", mechanics=True)
        return 0

    if rule == "minmax":                     # 宣言§7.4（fold31用）
        if phase == "A":
            sweep_minmax(pred, meta_dir, outdir, phase_a_grid(), "minmaxA")
        else:
            wj = json.loads((outdir / "minmaxA_winner.json").read_text(encoding="utf-8"))
            key = "至近重視" if "至近重視" in wj else "安全維持"
            base = V42.Cfg(**wj[key]["cfg"])
            print(f"Phase B' 土台 = {cfg_label(base)}（方針: {key}）")
            sweep_minmax(pred, meta_dir, outdir, phase_b_grid(base), "minmaxB",
                         verify=verify)
        return 0

    if phase == "A":
        sweep(pred, meta_dir, outdir, phase_a_grid(), "phaseA")
    else:
        wj = json.loads((outdir / "phaseA_winner.json").read_text(encoding="utf-8"))
        key = "至近重視" if "至近重視" in wj else "安全維持"
        base = V42.Cfg(**wj[key])
        print(f"Phase B 土台 = {cfg_label(base)}（方針: {key}）")
        sweep(pred, meta_dir, outdir, phase_b_grid(base), "phaseB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
