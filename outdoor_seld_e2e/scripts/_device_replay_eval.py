# -*- coding: utf-8 -*-
"""機器層の再生評価（2026-09-05・中立監査 §4 への対応）。

保存済みの予測（因果推論 csv）から、通知層の緊急度（`_make_joycon_demo_v43.urgency_for` = v4.3 と同じ最接近予測の式）を毎フレーム作り、
**機器層の正式仕様**（`out/joycon_demo_v2/README_機器層の仕様.md` §4: 確認 4 フレーム中 2・保持 0.3 秒・方位の安定化 60°/2 フレーム・
切替の合図と立ち上げ・cos⁴ の 4 方向按分）を Python で再生して、実際に振動子へ出る指令を GT のイベントと突き合わせる。
Unity の `JoyconDemoPlayer.GradedTick` と同じ規則（10 fps で 1 フレーム 1 tick として再生。Unity は描画フレームごとに tick するが、
緊急度は 0.1 秒単位でしか変わらないので、時間分解能 0.1 秒の再生で同じ振る舞いになる）。

測るもの（イベント = GT の連続トラック、tier は v4.3 と同じ 至近/注意/安全）:
  - 振動の到達: イベントの方位から 30° 以内の向きで震えた最初の時刻が CPA＋1 秒までにある
  - 至近の強さ: 至近イベントで、到達したフレームの振幅の最大が 0.8 以上（段階通知の「強」に相当する強さで震えたか）
  - 安全抑制: 安全イベント（最接近 > 3.2 m）に帰属する振動が無い
  - リード: CPA − 最初の帰属振動 [s]
  - 誤った向きの時間: 震えているのに、その向き（安定化後の方位）から 30° 以内に GT の距離クラスがいないフレーム [s/本]
  - 振動時間率: 震えたフレームの割合
  - 切替の合図: 受け入れた方位の跳びの回数

使い方: python scripts/_device_replay_eval.py <出力md> --plan <assignment.csv> [--split fold2] [--clip-max N] --meta <GT dir> <ラベル>=<csv>[@h] ...
"""
from __future__ import annotations

import csv
import importlib.util
import os
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
DG = _load("nv42diag", "_notify_v42_diag.py")
DEMO = _load("demo43", "_make_joycon_demo_v43.py")
FPS = 10

# 機器層の仕様（README_機器層の仕様.md §4）
URG_MIN = 0.15
CONFIRM_WIN, CONFIRM_NEED = 4, 2
HOLD_S = 0.3
JUMP_DEG, JUMP_NEED = 60.0, 2
SIDE_DEG, SIDE_NEED = 8.0, 2          # 側の記憶（2026-09-05）: ±8° が 2 フレーム続いたら左/右に確定し、反対側を 0 に
SIDE_ON = os.environ.get("DEV_SIDE", "1") == "1"   # DEV_SIDE=0 で側の記憶なし（変更前との比較用）
QUIET_RESET_S = 1.0
SWITCH_PAUSE_S, SWITCH_RAMP_S = 0.25, 0.6
UNITS5 = {"FL": 36.0, "FR": -36.0, "L": 108.0, "R": -108.0, "B": 180.0}   # 2026-09-06 00:13: 5 個・72° の均等刻み（本人決定）。後は左右どちらでもない
UNITS6 = {"FL": 30.0, "FR": -30.0, "L": 90.0, "R": -90.0, "BL": 150.0, "BR": -150.0}
UNITS4 = {"FL": 45.0, "FR": -45.0, "BL": 135.0, "BR": -135.0}
UNITS = {"4": UNITS4, "6": UNITS6}.get(os.environ.get("DEV_UNITS", "5"), UNITS5)
def is_rear(a): return abs(a) >= 170.0
PAN_GAIN, PAN_MIN = 1.6, 0.08
ATTR_DEG = 30.0


def dang(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0)


def replay(urg):
    """urg: [(t, u, az)] 0.1 秒刻み → [(t, eff_u, stable_az, {unit: amp}, accepted_jump)]"""
    out = []
    recent = []
    held_u, held_az, held_t = 0.0, 0.0, -10.0
    stable_az, jump_frames, have_stable = 0.0, 0, False
    switch_t0 = -10.0
    side, side_l, side_r = 0, 0, 0
    n_switch = 0
    for (t, u, az) in urg:
        recent.append(u); recent = recent[-CONFIRM_WIN:]
        confirmed = u >= URG_MIN and sum(1 for x in recent if x >= URG_MIN) >= CONFIRM_NEED
        if confirmed:
            held_u, held_az, held_t = u, az, t
        if confirmed:
            eu, eaz = u, az
        else:
            eu, eaz = ((held_u, held_az) if t - held_t < HOLD_S - 1e-9 else (0.0, held_az))
        accepted = False
        if eu >= URG_MIN:
            if not have_stable:
                stable_az, have_stable, jump_frames = eaz, True, 0
            elif dang(eaz, stable_az) <= JUMP_DEG:
                stable_az, jump_frames = eaz, 0
            elif confirmed:
                jump_frames += 1
                if jump_frames >= JUMP_NEED:
                    stable_az, jump_frames, accepted = eaz, 0, True
        elif t - held_t >= QUIET_RESET_S:
            have_stable, jump_frames = False, 0
            side, side_l, side_r = 0, 0, 0
        if accepted:
            side, side_l, side_r = 0, 0, 0
        if confirmed and eu >= URG_MIN:
            if stable_az >= SIDE_DEG: side_l += 1; side_r = 0
            elif stable_az <= -SIDE_DEG: side_r += 1; side_l = 0
            else: side_l = side_r = 0
            if side_l >= SIDE_NEED: side = +1
            if side_r >= SIDE_NEED: side = -1
        amps = {}
        if accepted:
            n_switch += 1; switch_t0 = t
            # 合図: 新しい側（安定化後の方位に最も近い振動子）で 0.2 秒・振幅 1.0
            k = min(UNITS, key=lambda kk: dang(stable_az, UNITS[kk]))
            amps[k] = 1.0
        elif eu >= URG_MIN and t - switch_t0 >= SWITCH_PAUSE_S:
            ramp = min(1.0, max(0.0, (t - switch_t0 - SWITCH_PAUSE_S) / SWITCH_RAMP_S))
            amp = (0.25 + 0.75 * eu) * (0.3 + 0.7 * ramp)
            w = {k: max(0.0, math.cos(math.radians(stable_az - a))) ** 4 for k, a in UNITS.items()}
            if SIDE_ON and side != 0:
                for k, a in UNITS.items():
                    if not is_rear(a) and ((side > 0 and a < 0) or (side < 0 and a > 0)): w[k] = 0.0
            s = sum(w.values())
            for k in UNITS:
                a = amp * w[k] / s * PAN_GAIN if s > 0 else 0.0
                if a >= PAN_MIN:
                    amps[k] = min(1.0, a)
        out.append((t, eu, stable_az, amps, accepted))
    return out, n_switch


def load_pred_rows(path: Path, horiz: bool):
    """v4.load_pred と同じ構造（clip -> frame -> [(cls, az, d)]）。horiz なら d×cos(el)。"""
    out = defaultdict(lambda: defaultdict(list))
    for line in open(path, encoding="utf-8"):
        p = line.strip().split(",")
        if len(p) >= 7:
            clip, k, c, az, el = p[0], int(p[1]), int(p[2]), float(p[4]), float(p[5])
            d = float(p[6]) if p[6] not in ("", "nan") else float("nan")
        elif len(p) == 6:
            clip, k, c, az, el, d = p[0], int(p[1]), int(p[2]), float(p[3]), float(p[4]), float(p[5])
        else:
            continue
        if not math.isfinite(d):
            continue
        if horiz:
            d = d * math.cos(math.radians(el))
        out[clip][k].append((c, az, d))
    return dict(out)


def score(pred, meta: Path, clips):
    stat = defaultdict(lambda: [0, 0]); n_strong = 0; leads = []
    wrong_s = 0.0; duty = 0.0; n_switch_tot = 0; opp_s = 0.0
    for clip in clips:
        evs = [DG.mk_event(c, t, fr) for c, t, fr in DG.gt_tracks(meta, clip)]
        frames = pred.get(clip)
        if frames:
            urg = DEMO.urgency_for(clip, {clip: frames})
            rep, n_sw = replay(urg)
        else:
            rep, n_sw = [], 0
        n_switch_tot += n_sw
        first = {}; maxamp = defaultdict(float); attributed_frames = 0
        for (t, eu, saz, amps, acc) in rep:
            if not amps:
                continue
            k = int(round(t * FPS)) - 1
            duty += 1.0 / 100
            # 帰属: このフレームに GT がいて方位差 30° 以内の最も近いイベント
            best, best_e = None, None
            for i, ev in enumerate(evs):
                if k in ev["fr"]:
                    e = dang(saz, ev["fr"][k][0])
                    if e <= ATTR_DEG and (best_e is None or e < best_e):
                        best, best_e = i, e
            if best is None:
                wrong_s += 1.0 / FPS
                continue
            gaz = evs[best]["fr"][k][0]
            if abs(gaz) >= SIDE_DEG:
                opp = {k for k, a in UNITS.items() if not is_rear(a) and ((gaz > 0 and a < 0) or (gaz < 0 and a > 0))}
                if any(u in amps for u in opp):
                    opp_s += 1.0 / FPS
            if k <= evs[best]["cpa"] + FPS:
                first.setdefault(best, k)
                maxamp[best] = max(maxamp[best], max(amps.values()))
        for i, ev in enumerate(evs):
            hit = i in first
            if ev["tier"] == "safe":
                stat["safe"][1] += 1; stat["safe"][0] += int(not hit); continue
            stat[ev["tier"]][1] += 1; stat[ev["tier"]][0] += int(hit)
            if hit:
                leads.append((ev["cpa"] - first[i]) / FPS)
            if ev["tier"] == "critical" and hit and maxamp[i] >= 0.8:
                n_strong += 1
    g = lambda t: 100 * stat[t][0] / max(stat[t][1], 1)
    leads = np.array(leads) if leads else np.array([np.nan])
    n = max(len(clips), 1)
    return dict(crit=g("critical"), strong=100 * n_strong / max(stat["critical"][1], 1), caut=g("caution"), safe=g("safe"),
                lead=float(np.nanmedian(leads)), lead25=float(100 * np.nanmean(leads >= 2.5)),
                wrong=wrong_s / n, opp=opp_s / n, duty=100 * duty / n, n_switch=n_switch_tot / n, n_clips=len(clips))


def main() -> int:
    argv = list(sys.argv[1:])

    def arg(key, default=None):
        if key in argv:
            i = argv.index(key); v = argv[i + 1]; del argv[i:i + 2]; return v
        return default

    plan = ROOT / arg("--plan"); split = arg("--split", "fold2"); clip_max = int(arg("--clip-max", "0")); meta = ROOT / arg("--meta")
    out_md = Path(argv[0]); items = [a.split("=", 1) for a in argv[1:]]
    clips = []
    with open(plan, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("split", split) != split:
                continue
            if clip_max:
                m = re.search(r"mix(\d+)$", r["clip_id"])
                if m and int(m.group(1)) > clip_max:
                    continue
            clips.append(r["clip_id"])
    R = [f"# 機器層の再生評価（連続モード・正式仕様を再生・振動子 {len(UNITS)} 個: {','.join(f'{k}{a:+.0f}' for k, a in UNITS.items())}） — {out_md.stem}", "",
         f"plan= {plan.relative_to(ROOT)} ({split}{f', mix≤{clip_max}' if clip_max else ''}) = {len(clips):,} 本 / GT= {meta.relative_to(ROOT)}", "",
         "到達= イベントの方位から 30° 以内の向きで震えた最初の時刻が CPA＋1 s まで。至近で振幅≥0.8= 段階通知の「強」相当の強さで震えた至近イベントの割合。",
         "誤った向き= 震えているのに向きの 30° 以内に GT がいない時間 [s/本]。反対側の振動子= 帰属した GT が |方位| ≥ 8° のとき反対側（前右・後右 / 前左・後左）が震えていた時間 [s/本]。振動時間率= 震えたフレームの割合。切替= 受け入れた方位の跳び（合図）の回数/本。"
         + ("" if SIDE_ON else "  ⚠️ DEV_SIDE=0（側の記憶なし＝変更前）"), "",
         "| 予測 | 本数 | 至近到達(振動) | **至近で振幅≥0.8** | 注意到達 | 安全抑制 | リード中央 | ≥2.5s | 誤った向き [s/本] | 反対側の振動子 [s/本] | 振動時間率 | 切替/本 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    print("\n".join(R[:3]), flush=True)
    for label, src in items:
        horiz = src.endswith("@h"); p = Path(src[:-2] if horiz else src)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            R.append(f"| {label} | （未着: {p.name}） |"); print(R[-1], flush=True); continue
        s = score(load_pred_rows(p, horiz), meta, clips)
        R.append(f"| {label}{' (予測を水平変換)' if horiz else ''} | {s['n_clips']:,} | {s['crit']:.1f}% | **{s['strong']:.1f}%** | {s['caut']:.1f}% | {s['safe']:.1f}% "
                 f"| {s['lead']:.2f}s | {s['lead25']:.1f}% | {s['wrong']:.2f} | {s['opp']:.2f} | {s['duty']:.1f}% | {s['n_switch']:.2f} |")
        print(R[-1], flush=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(R) + "\n", encoding="utf-8")
    print("->", out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
