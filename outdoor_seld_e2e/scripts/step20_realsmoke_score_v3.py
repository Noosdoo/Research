# -*- coding: utf-8 -*-
"""Step 20 v3: 実録採点 — 現行の通知規則 **v4.3＋警告音 hold** で採点し、方向は「注釈と同じ窓の推定方位」で比べる（2026-09-06）。

敵対的レビュー（`md/audit/敵対的レビュー_実録プロトコル_2026-09-05_Astra.md`）R02・R03・R10・W7 への対応。旧 v2（v3.4 規則）は比較用に残す。

規則（合成データの統一採点器 `scripts/_score_unified.py` と同じ正規実装を呼ぶ・独自の規則は発明しない）:
  - 距離クラス（car/kick/bike）: `step12_notify_v43.run_rule3`（`out/notify_v43_sweep/winner.json` の採用構成）→ 発火 (frame, az, tier=強/中, d)
  - 警告音クラス: `step12_notify_v9b_hold.warn_fires(hold=True)`
  - 発火時刻は因果時刻 (k+1)/FPS。クリップ長は予測の最終フレームから（可変長）

3 つの時点・窓を分けて定義する（R03）:
  ① 型分類の窓（記述用のみ・CPA の 2.5〜1.5 秒前）: ここでは使わない（GT の連続方位が無い）
  ② **通知成功の窓** = [t_start − 1 s, t_cpa ＋ 1 s]（合成の採点器と同じ）。critical は強、caution は中か強、safe は強も中も無いこと
  ③ **方向の比較時点** = 注釈の象限を書いた窓（距離クラス: CPA の 2.5〜1.5 秒前 = 記入用 CSV の定義。警告音クラス: 通知が出た瞬間の推定方位を「鳴り始めの向き」と比べる・再監査2 Q06）。
     その窓の**推定方位の中央（単位ベクトル平均）**を 4 象限に丸めて注釈と比べる。発火時刻の方位ではない。窓に推定が無ければ「方向は評価不能（未検出）」

分母（W7）: 到達・抑制は「採点対象イベント」を分母に。方向は「全イベント（未検出は不一致扱い）」と「推定があった例だけ」の両方を出す。
警告音（再監査 N02）: 時間指標は **遅れ = 発火 − 鳴り始め（t_start）**。距離クラスのリード（CPA − 発火）とは別に集計する。方向は鳴り始め直後の窓
  [t_start, t_start + --warn-dir-span（既定 1.0 s）] の推定方位（3 秒全体を平均しない）。「鳴り始め＝気づいた瞬間」は観測上の限界として明記する。
歩行対比（再監査 N05）: pair_id のある行（区分=歩行）は ablation の主要評価に入れない（静止側も）。別集計で **検出フレーム率**（イベント窓内で
  そのクラスが出ているフレームの割合＝歩行対比の主指標）と到達を出し、pair_id ごとの静止−歩行の差を並べる。
前方 F（R02）: 既定で主要評価から除外し「前方（参考）」として別集計（`--include-front` で含める）。
履歴不足（R10）: クリップ内の t_cpa が `--min-history` 秒（既定 7.5）未満のイベントは `history_short` として主要評価から外し件数を出す。
多重車（R06 の暫定）: n_car ≥ 2 の行は「群のいずれかへの通知」として別集計（車両単位の到達率と混ぜない）。
負例（class=none）: 半開区間 [t_start, t_cpa) の担当区間で v4.3＋hold の発火を数える（注釈イベント窓はマスク）。誤警告率は両側 95% CI と片側 95% 上限。

入力列: clip_id,event_id,take_id,pair_id,trial,class,quadrant,t_start,t_cpa,区分,状態[,横距離m,n_car,scored,orig_file,cut_offset_s,...]
予測 CSV: 7 列 [clip,frame,class,track,az,el,dist]（因果推論の val_all_causal.csv 形式）
使い方: python scripts/step20_realsmoke_score_v3.py --pred <csv> --ann <csv> [--out md] [--events-out csv] [--pred-b csv]
        [--dir-window 2.5-1.5] [--min-history 7.5] [--include-front]
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
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
H = _load("nhold", "step12_notify_v9b_hold.py")
V2 = _load("s20v2", "step20_realsmoke_score_v2.py")     # 統計関数・負例の重なり控除・列定義を再利用

FPS = 10.0
T3, SUPP = 1.5, 3.2                     # GT 区分（横距離 = 水平距離）: critical ≤1.5 / caution ≤3.2 / safe >3.2
WIN_PRE, WIN_POST = 1.0, 1.0
CLS_IDX = V2.CLS_IDX
DIST_CLS = V2.DIST_CLS
quadrant_of, gt_tier_of, is_scored, lateral_of = V2.quadrant_of, V2.gt_tier_of, V2.is_scored, V2.lateral_of


def _arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


def load_pred7(path: Path):
    """clip -> frame -> [(cls, az, el, d)]。7 列（因果推論）が前提。6 列（el なし）も読む。"""
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
        out[clip][k].append((c, az, el, d))
    return dict(out)


def fires_of(frames, cfg43, nframes):
    """v4.3＋hold の発火 [(t, az, tier, cls)]（tier: 強/中/警告）。frames: frame -> [(cls, az, el, d)]"""
    fd = {k: [(c, az, d) for c, az, el, d in v if c in DIST_CLS and math.isfinite(d)] for k, v in frames.items()}
    fw = {k: [(c, az, el) for c, az, el, d in v] for k, v in frames.items()}
    fires = []
    res = V43.run_rule3({"x": fd}, cfg43, nframes=nframes).get("x", {})
    for cls, lst in res.items():
        for j, az, tier, d in lst:
            fires.append(((j + 1) / FPS, az, tier, cls))
    for k, cls, az in H.warn_fires(fw, hold=True, nframes=nframes):
        fires.append(((k + 1) / FPS, az, "警告", cls))
    return sorted(fires)


def frame_recall(frames, cls_idx, t0, t1):
    """イベント窓 [t0, t1] のうち、そのクラスの推定があるフレームの割合（歩行対比の主指標。v2 と同じ定義）。"""
    k0, k1 = max(int(math.floor(t0 * FPS)), 0), int(math.ceil(t1 * FPS))
    if k1 <= k0:
        return None
    hit = sum(1 for k in range(k0, k1) if any(c == cls_idx for c, az, el, d in frames.get(k, [])))
    return round(hit / (k1 - k0), 3)


def median_az(frames, cls_idx, t0, t1):
    """窓 [t0, t1] のそのクラスの推定方位の中央（単位ベクトル平均）。無ければ None。"""
    k0, k1 = int(math.floor(t0 * FPS)), int(math.ceil(t1 * FPS))
    xs, ys = [], []
    for k in range(max(k0, 0), k1 + 1):
        for c, az, el, d in frames.get(k, []):
            if c == cls_idx:
                xs.append(math.cos(math.radians(az))); ys.append(math.sin(math.radians(az)))
    if not xs:
        return None
    return math.degrees(math.atan2(sum(ys), sum(xs)))


def evaluate(rows, pred, cfg43, dir_win, min_history, include_front, warn_dir_span=1.0):
    need = defaultdict(float)
    for r in rows:
        need[r["clip_id"]] = max(need[r["clip_id"]], float(r["t_cpa"]) + WIN_POST + 1.0)
    fires_by_clip = {}
    for clip in {r["clip_id"] for r in rows}:
        fr = pred.get(clip, {})
        nf = int(max(need[clip] * FPS, (max(fr.keys()) + 1) if fr else 0, 100)) + 1
        fires_by_clip[clip] = fires_of(fr, cfg43, nf) if fr else []

    pos_windows = defaultdict(list)
    for r in rows:
        if r["class"].strip() != "none":
            pos_windows[r["clip_id"]].append((float(r["t_start"]) - WIN_PRE, float(r["t_cpa"]) + WIN_POST))

    def masked(clip, t):
        return any(a <= t <= b for a, b in pos_windows[clip])

    events, n_false, exposure_s = [], 0, 0.0
    extras = defaultdict(int)
    used_by_clip = {clip: [False] * len(f) for clip, f in fires_by_clip.items()}

    def meta(r):
        return {"take_id": r.get("take_id", ""), "pair_id": r.get("pair_id", ""), "state": r.get("状態", ""),
                "n_car": r.get("n_car", ""), "session": r.get("session_id", "")}

    for r in sorted(rows, key=lambda x: (x["clip_id"], float(x["t_cpa"]))):
        clip, cls = r["clip_id"], r["class"].strip()
        if cls == "none":
            t0, t1 = float(r["t_start"]), float(r["t_cpa"])
            # 重なり控除は v2 と同じ考え方: 担当区間からイベント窓を引く
            segs = sorted((max(t0, a), min(t1, b)) for a, b in pos_windows[clip] if b > t0 and a < t1)
            ov, cur = 0.0, None
            for a, b in segs:
                if cur is None or a > cur[1]:
                    if cur:
                        ov += cur[1] - cur[0]
                    cur = [a, b]
                else:
                    cur[1] = max(cur[1], b)
            if cur:
                ov += cur[1] - cur[0]
            exposure_s += (t1 - t0) - ov
            n_false += sum(1 for (t, az, tier, c) in fires_by_clip[clip] if t0 <= t < t1 and not masked(clip, t))
            continue
        base = {"clip": clip, "trial": r.get("trial", ""), "event_id": r.get("event_id", "1"), "class": cls,
                "quadrant": r.get("quadrant", r.get("象限", "")).strip(), **meta(r),
                "history_short": int(float(r["t_cpa"]) < min_history), "front": int(r.get("quadrant", r.get("象限", "")).strip() == "F"),
                "multi": int(str(r.get("n_car", "1")).strip() not in ("", "1")),
                "walk": int(bool(r.get("pair_id", "").strip()) or r.get("区分", "").strip() == "歩行"),
                "delay": None, "frame_recall": None}
        if not is_scored(r):
            extras["n_maskonly"] += 1
            events.append({**base, "gt_tier": "mask", "notified": None, "fired_tier": None, "lead": None, "quad_ok": None, "az_est": None})
            continue
        ci = CLS_IDX.get(cls)
        if ci is None:
            extras["n_unknown_class"] += 1
            continue
        frames = pred.get(clip, {})
        t0, t1 = float(r["t_start"]) - WIN_PRE, float(r["t_cpa"]) + WIN_POST
        # ③ 方向: 距離クラスは注釈の窓 [t_cpa − dir_win[0], t_cpa − dir_win[1]]、警告音クラスは [t_start, t_cpa]（ラップ＝音の始まり）の推定方位の中央
        if ci in DIST_CLS:
            az_est = median_az(frames, ci, float(r["t_cpa"]) - dir_win[0], float(r["t_cpa"]) - dir_win[1])
        else:
            az_est = median_az(frames, ci, float(r["t_start"]), float(r["t_start"]) + warn_dir_span)   # 鳴り始め直後（N02）
        base["frame_recall"] = frame_recall(frames, ci, float(r["t_start"]), float(r["t_cpa"]))
        quad_ok = None if not base["quadrant"] else (None if az_est is None else quadrant_of(az_est) == base["quadrant"])
        fires = fires_by_clip[clip]; used = used_by_clip[clip]
        if ci in DIST_CLS:
            lat = lateral_of(r)
            if lat is None:
                extras["n_unscored"] += 1
                events.append({**base, "gt_tier": "-", "notified": None, "fired_tier": None, "lead": None, "quad_ok": quad_ok, "az_est": az_est})
                continue
            tier = gt_tier_of(lat)
            in_w = [i for i, (t, az, ft, c) in enumerate(fires) if c == ci and ft in ("強", "中") and t0 <= t <= t1]
            if tier == "safe":
                extras["n_mid_on_safe"] += sum(1 for i in in_w if fires[i][2] == "中")
                events.append({**base, "gt_tier": tier, "notified": not in_w, "fired_tier": (fires[in_w[0]][2] if in_w else None),
                               "lead": None, "quad_ok": quad_ok, "az_est": az_est})
                continue
            pick = None
            for i in in_w:
                if used[i]:
                    continue
                if tier == "critical" and fires[i][2] != "強":
                    continue
                pick = i; break
            if pick is not None:
                used[pick] = True
                if tier == "caution" and fires[pick][2] == "強":
                    extras["n_strong_on_caution"] += 1
                events.append({**base, "gt_tier": tier, "notified": True, "fired_tier": fires[pick][2],
                               "lead": round(float(r["t_cpa"]) - fires[pick][0], 2), "quad_ok": quad_ok, "az_est": az_est})
            else:
                events.append({**base, "gt_tier": tier, "notified": False, "fired_tier": None, "lead": None, "quad_ok": quad_ok, "az_est": az_est})
        else:
            in_w = [i for i, (t, az, ft, c) in enumerate(fires) if c == ci and ft == "警告" and t0 <= t <= t1 and not used[i]]
            if in_w:
                used[in_w[0]] = True
                # 方向 = 通知が出た瞬間の推定方位（記録紙の「鳴り始めの向き」と、その瞬間の推定を比べる・再監査2 Q06）。窓の平均は使わない
                az_fire = fires[in_w[0]][1]
                quad_ok_f = None if not base["quadrant"] else quadrant_of(az_fire) == base["quadrant"]
                events.append({**base, "gt_tier": "warn", "notified": True, "fired_tier": "警告",
                               "lead": None, "delay": round(fires[in_w[0]][0] - float(r["t_start"]), 2),   # 遅れ = 発火 − 鳴り始め（N02）
                               "quad_ok": quad_ok_f, "az_est": az_fire})
            else:
                events.append({**base, "gt_tier": "warn", "notified": False, "fired_tier": None, "lead": None, "quad_ok": quad_ok, "az_est": az_est})
    return events, {"n_false": n_false, "exposure_s": exposure_s}, extras


def summarize(events, include_front):
    """主要評価（前方除外・履歴不足除外・単車）と参考集計を分ける。"""
    scored = [e for e in events if e["notified"] is not None]
    main = [e for e in scored if (include_front or not e["front"]) and not e["history_short"] and not e["multi"] and not e["walk"]]
    side = {"front": [e for e in scored if e["front"] and not include_front and not e["walk"]],
            "history_short": [e for e in scored if e["history_short"] and not e["walk"]],
            "multi": [e for e in scored if e["multi"] and not e["walk"]],
            "walk": [e for e in scored if e["walk"]]}

    def rates(evs):
        by = defaultdict(lambda: [0, 0])
        for e in evs:
            by[e["gt_tier"]][0] += int(bool(e["notified"])); by[e["gt_tier"]][1] += 1
        return by
    return main, side, rates


EVENT_FIELDS = ["clip", "session", "take_id", "pair_id", "state", "trial", "event_id", "class", "n_car", "quadrant",
                "gt_tier", "notified", "fired_tier", "lead", "delay", "frame_recall", "az_est", "quad_ok", "front", "history_short", "multi", "walk"]


def walk_pairs_summary(walk_events):
    """歩行対比: (pair_id, class) ごとに静止側・歩行側を対応づけ、検出フレーム率の差を出す。

    同じ (pair, 状態, class) に事象が 2 件以上ある対は「対象が 1 件に決まらない」として未集計にし、ambiguous に返す（黙って最後の 1 件に置き換えない・再監査2 Q04）。"""
    by = defaultdict(lambda: defaultdict(list))
    for e in walk_events:
        by[(e["pair_id"], e["class"])][e["state"]].append(e)
    rows, diffs, ambiguous = [], [], []
    for (pid, cls), d in sorted(by.items()):
        if any(len(v) > 1 for v in d.values()):
            ambiguous.append((pid, cls, {k: len(v) for k, v in d.items()}))
            continue
        a = d.get("静止", [None])[0]; b = d.get("歩行", [None])[0]
        fa = a["frame_recall"] if a else None; fb = b["frame_recall"] if b else None
        if fa is not None and fb is not None:
            diffs.append(fb - fa)
        rows.append((f"{pid}/{cls}", a, b, fa, fb))
    return rows, diffs, ambiguous


def main() -> int:
    pred_path, ann_path = Path(_arg("--pred")), Path(_arg("--ann"))
    out_md = Path(_arg("--out", str(ROOT / "out" / "realsmoke" / "score_v3.md")))
    events_out = Path(_arg("--events-out", str(out_md.with_name(out_md.stem + "_events.csv"))))
    a, b = _arg("--dir-window", "2.5-1.5").split("-")
    dir_win = (float(a), float(b))
    min_history = float(_arg("--min-history", "7.5"))
    warn_dir_span = float(_arg("--warn-dir-span", "1.0"))
    include_front = "--include-front" in sys.argv
    winner = Path(_arg("--winner", str(ROOT / "out/notify_v43_sweep/winner.json")))
    cfg43 = V43.Cfg43(**json.loads(winner.read_text(encoding="utf-8")))
    pred = load_pred7(pred_path)
    rows = list(csv.DictReader(open(ann_path, encoding="utf-8-sig")))
    events, neg, extras = evaluate(rows, pred, cfg43, dir_win, min_history, include_front, warn_dir_span)
    main_ev, side, rates = summarize(events, include_front)
    by = rates(main_ev)
    hours = neg["exposure_s"] / 3600.0
    label = {"critical": "critical 到達（強）", "caution": "caution 到達（中以上）", "safe": "safe 抑制（強・中とも無し）", "warn": "警告音 到達（hold）"}
    rep = [f"# 実録採点 v3（v4.3＋hold・{V43.label43(cfg43)}・pred={pred_path.name}）", "",
           f"- 通知規則: v4.3（{winner.name}）＋警告音 hold。成功の窓 [開始−{WIN_PRE:.0f} s, CPA＋{WIN_POST:.0f} s]。方向の比較時点 = CPA の {dir_win[0]:.1f}〜{dir_win[1]:.1f} 秒前の推定方位の中央（発火時刻ではない）",
           f"- イベント {len(events)} 件（採点対象 {len([e for e in events if e['notified'] is not None])} 件）。主要評価（ablation・A〜F）{len(main_ev)} 件 = "
           f"{'前方を含む' if include_front else '前方 F を除外'}・履歴不足（CPA<{min_history:.1f} s）除外・n_car≥2 除外・歩行対比（pair_id あり）除外",
           f"- 警告音の時間指標 = 遅れ（発火 − 鳴り始め）。方向 = 通知が出た瞬間の推定方位を記録紙の「鳴り始めの向き」と比べる（未発火なら鳴り始めから {warn_dir_span:.1f} s の中央・参考）", ""]
    rep.append("## 主要評価（イベント単位・分母 = 採点対象）")
    for t in ("critical", "caution", "safe", "warn"):
        if by[t][1]:
            rep.append(f"- {label[t]}: **{by[t][0]}/{by[t][1]}**（{100*by[t][0]/by[t][1]:.0f}%）")
    if extras["n_strong_on_caution"]:
        rep.append(f"- caution 車への強通知（過剰・別掲）: {extras['n_strong_on_caution']} 件")
    if extras["n_mid_on_safe"]:
        rep.append(f"- safe 車への中通知（失敗の内訳）: {extras['n_mid_on_safe']} 件")
    leads = [e["lead"] for e in main_ev if e["lead"] is not None]
    rep.append(f"- 距離クラスのリード中央値 {np.median(leads):.1f} s（範囲 {min(leads):.1f}〜{max(leads):.1f} s、正解時刻はラップ基準）" if leads else "- リード: n/a")
    delays = [e["delay"] for e in main_ev if e["delay"] is not None]
    rep.append(f"- 警告音の遅れ中央値 {np.median(delays):.2f} s（範囲 {min(delays):.2f}〜{max(delays):.2f} s、鳴り始めはラップ）" if delays else "- 警告音の遅れ: n/a")
    # 方向（2 つの分母）
    dq = [e for e in main_ev if e["quadrant"]]
    n_all = len(dq); n_est = sum(1 for e in dq if e["quad_ok"] is not None); n_ok = sum(1 for e in dq if e["quad_ok"])
    rep.append(f"- 方向 4 象限一致: 全イベント分母 **{n_ok}/{n_all}**（未検出 {n_all - n_est} 件は不一致扱い）／推定があった例だけ {n_ok}/{n_est}")
    if hours > 0:
        lo, hi = V2.poisson_rate_ci(neg["n_false"], hours); up1 = V2.poisson_upper95_one_sided(neg["n_false"], hours)
        rep.append(f"- 誤警告 {neg['n_false']} 件 / {hours:.2f} h（v4.3＋hold の発火・注釈窓マスク済み）= {neg['n_false']/hours:.2f} 回/h（両側 95% CI {lo:.2f}〜{hi:.2f}／片側 95% 上限 {up1:.2f}）")
    else:
        rep.append("- 負例露出なし")
    rep += ["", "## 参考集計（主要評価から外したもの）"]
    for key, name in (("front", "前方 F（視野内・参考）"), ("history_short", f"履歴不足（CPA < {min_history:.1f} s）"), ("multi", "多重車 n_car≥2（群のいずれかへの通知）")):
        evs = side[key]
        if not evs:
            rep.append(f"- {name}: 0 件"); continue
        r_ = rates(evs); parts = [f"{t} {r_[t][0]}/{r_[t][1]}" for t in ("critical", "caution", "safe", "warn") if r_[t][1]]
        rep.append(f"- {name}: {len(evs)} 件（" + "、".join(parts) + "）")
    wrows, wdiffs, wamb = walk_pairs_summary(side["walk"])
    if wrows or wamb:
        r_w = rates(side["walk"])
        rep += ["", f"## 歩行対比（pair_id あり・{len(side['walk'])} 件・{len(wrows)} 対（pair×クラス）・対象が決まらず未集計 {len(wamb)} 対）— 主指標 = 検出フレーム率",
                "- 到達: " + "、".join(f"{t} {r_w[t][0]}/{r_w[t][1]}" for t in ("critical", "caution", "safe", "warn") if r_w[t][1])]
        fa = [x[3] for x in wrows if x[3] is not None]; fb = [x[4] for x in wrows if x[4] is not None]
        if fa and fb:
            rep.append(f"- 検出フレーム率 中央値: 静止 {np.median(fa):.3f} / 歩行 {np.median(fb):.3f}（対 {len(wdiffs)} 組の差 歩行−静止 中央値 {np.median(wdiffs):+.3f}）")
        rep += ["", "| pair/クラス | 静止: 成功/検出率 | 歩行: 成功/検出率 |", "| --- | --- | --- |"]
        for pid, a, b, fa1, fb1 in wrows:
            fmt = lambda e, f: ("—" if e is None else f"{'○' if e['notified'] else '×'} / {f if f is not None else '—'}")
            rep.append(f"| {pid} | {fmt(a, fa1)} | {fmt(b, fb1)} |")
        for pid, cls, cnt in wamb:
            rep.append(f"| {pid}/{cls} | 未集計: 同じ状態に事象 {cnt} 件（対象が 1 件に決まらない） | |")
    if extras["n_unscored"]:
        rep.append(f"- 横距離 m 欠落で未採点: {extras['n_unscored']} 件")
    if extras["n_maskonly"]:
        rep.append(f"- scored=0（マスク専用）: {extras['n_maskonly']} 件")
    pred_b = _arg("--pred-b")
    if pred_b:
        ev_b, _, _ = evaluate(rows, load_pred7(Path(pred_b)), cfg43, dir_win, min_history, include_front, warn_dir_span)
        mb, _, _ = summarize(ev_b, include_front)
        key = lambda e: (e["clip"], e["trial"], e["event_id"], e["class"])
        da = {key(e): e for e in main_ev}; db = {key(e): e for e in mb}
        common = sorted(set(da) & set(db))
        b_ = sum(1 for k in common if da[k]["notified"] and not db[k]["notified"]); c_ = sum(1 for k in common if not da[k]["notified"] and db[k]["notified"])
        rep += ["", "## 対応あり比較（A=--pred, B=--pred-b・主要評価のみ）", f"- 成功の不一致対: A○B×={b_} / A×B○={c_} → McNemar 厳密 p={V2.mcnemar_exact(b_, c_):.4f}"]
    rep += ["", "| clip | event | クラス | n_car | 象限 | GT区分 | 成功 | 発火 | リード[s] | 遅れ[s] | 検出率 | 推定方位 | 象限一致 | 除外理由 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for e in events:
        mark = "—" if e["notified"] is None else ("○" if e["notified"] else "×")
        excl = "、".join(n for f, n in (("front", "前方"), ("history_short", "履歴不足"), ("multi", "多重車"), ("walk", "歩行対比")) if e.get(f))
        az_s = ("%.0f°" % e["az_est"]) if e["az_est"] is not None else "—"
        rep.append(f"| {e['clip']} | {e['event_id']} | {e['class']} | {e['n_car']} | {e['quadrant'] or '—'} | {e['gt_tier']} | {mark} | {e['fired_tier'] or '—'} | "
                   f"{e['lead'] if e['lead'] is not None else '—'} | {e['delay'] if e.get('delay') is not None else '—'} | {e['frame_recall'] if e.get('frame_recall') is not None else '—'} | {az_s} | "
                   f"{'○' if e['quad_ok'] else ('×' if e['quad_ok'] is not None else '—')} | {excl or '—'} |")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(rep) + "\n", encoding="utf-8")
    with open(events_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS, extrasaction="ignore"); w.writeheader()
        for e in events:
            w.writerow({k: ("" if e.get(k) is None else e.get(k)) for k in EVENT_FIELDS})
    print("\n".join(rep[:14])); print("->", out_md); print("->", events_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
