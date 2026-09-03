# -*- coding: utf-8 -*-
"""通知 v4.4 — 「鳴らしすぎ」対策の後段フィルタ（車のhold ＋ 流れモード）。2026-09-03。

宣言= md/design/通知v4.4_鳴らしすぎ対策の事前宣言_2026-09-03.md。
v4.3（step12_notify_v43.py）の**発火の作り方は変えず**、出てきたエピソード列に後段で掛ける。

  H 車のhold: 発火時の方位をアンカーに固定。同クラスの検出（track_series2 の系列）がアンカー±DIR_H°で
     続く間（途切れ < GAP_H 秒）は新しい「中」を出さない。中→強の昇格は1回だけ許す（強は必ず届く）。
  F 流れモード: 同じ側（方位の符号）で「中」が K 回出たら、その側の中を以後止める（強は常に通す）。

Cfg44 の既定（DIR_H=None）は v4.3 と発火完全一致（--verify）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
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


v4 = _load("nv4", "step12_notify_v4_ttc.py")
V42 = _load("nv42", "step12_notify_v42_bearing.py")
V43 = _load("nv43", "step12_notify_v43.py")
FPS = v4.FPS


@dataclass(frozen=True)
class Cfg44:
    dir_h: float | None = None    # [deg] 第1グリッド（アンカー固定）。None = 使わない
    gap_h: float = 5.0            # [s]   検出の途切れがこれ未満なら「続いている」
    flow_k: int | None = None     # 同じ側で中が K 回出たら以後の中を止める。None=なし
    track_hold: bool = False      # 追記1の H': 追跡系列の連続性で同一物体を判定（dir_h と排他）
    jump_deg: float = 60.0        # H': 隣接フレームの方位差がこれを超えたら別物体（LINK_DEG と同値）
    jump_m: float | None = None   # 追記2: 隣接フレームの距離差がこれを超えたら別物体（None=見ない）
    flip_reset: bool = False      # 追記2: 遠ざかり(3フレーム以上)→接近 に反転したら別物体
    refrac_s: float | None = None # 追記3 R: 通知出力の不応期[s]。同段以下の再通知を前回から refrac_s 未満なら出さない
                                  #（物体を問わない＝出力のレート制限。中→強の昇格は通す）


RANK = {"中": 1, "強": 2}


def apply_filters(eps, az_at, C: Cfg44, d_at=None):
    """eps=[(frame, az, tier, d)]（時刻順）→ フィルタ後のエピソード列。az_at/d_at= そのクラスの検出系列。"""
    if C.dir_h is None and C.flow_k is None and not C.track_hold and C.refrac_s is None:
        return list(eps)
    out = []
    anchors = []                    # [az, last_det_frame, tier]（第1グリッド: アンカー固定）
    n_mid_side = {1: 0, -1: 0}      # 側（az>=0: 左=+1）ごとの中の回数
    # H'（track_hold）: 直前エピソードの段と、系列の「同一物体」区間の追跡
    seg_tier = None                 # 現在の同一物体区間で出した最高段（None=未発火）
    prev_j, prev_az = None, None    # 系列の直前の検出
    prev_d, n_recede = None, 0      # 追記2: 直前の距離と「遠ざかり」連続フレーム数
    last_out = {}                   # 追記3 R: 段 -> 最後に出した frame
    eps = sorted(eps, key=lambda e: e[0])
    ei = 0
    last_frame = max([e[0] for e in eps] + [0])
    for j in range(int(last_frame) + 1):
        a_det = az_at.get(j)
        if C.track_hold and a_det is not None:
            d_det = d_at.get(j) if d_at is not None else None
            new_obj = prev_j is not None and ((j - prev_j) >= C.gap_h * FPS
                                              or v4.cdiff(a_det, prev_az) > C.jump_deg)
            if not new_obj and C.jump_m is not None and prev_d is not None and d_det is not None                     and prev_j is not None and j - prev_j == 1 and abs(d_det - prev_d) > C.jump_m:
                new_obj = True                     # 距離が跳ぶ → 別物体
            if not new_obj and C.flip_reset and prev_d is not None and d_det is not None                     and prev_j is not None and j - prev_j == 1:
                if d_det > prev_d + 0.05:
                    n_recede += 1
                elif d_det < prev_d - 0.05:
                    if n_recede >= 3:
                        new_obj = True             # 遠ざかっていたのに近づき始めた → 別物体
                    n_recede = 0
            if new_obj:
                seg_tier = None
                n_recede = 0
            prev_j, prev_az, prev_d = j, a_det, d_det
        if C.dir_h is not None and a_det is not None:
            for an in anchors:
                if v4.cdiff(a_det, an[0]) <= C.dir_h:
                    an[1] = j
        while ei < len(eps) and eps[ei][0] == j:
            f, az, tier, d = eps[ei]
            ei += 1
            keep = True
            if C.track_hold:
                if seg_tier is not None and RANK[tier] <= RANK[seg_tier]:
                    keep = False                    # 同一物体への同段以下の再発火は出さない
                else:
                    seg_tier = tier                 # 初回 or 昇格（中→強は1回だけ通る）
            if keep and C.dir_h is not None:
                hit = [an for an in anchors
                       if (j - an[1]) < C.gap_h * FPS and v4.cdiff(az, an[0]) <= C.dir_h]
                if hit:
                    an = hit[0]
                    if tier == "強" and an[2] == "中":
                        an[2] = "強"                 # 昇格は1回だけ通す
                    else:
                        keep = False
                else:
                    anchors.append([az, j, tier])
            if keep and C.refrac_s is not None:
                # 同段以下の直近出力から refrac_s 未満なら出さない（強は中の直後でも出る=昇格）
                blocked = any(j - last_out[t] < C.refrac_s * FPS for t in last_out if RANK[t] >= RANK[tier])
                if blocked:
                    keep = False
            if keep and C.flow_k is not None and tier == "中":
                side = 1 if az >= 0 else -1
                if n_mid_side[side] >= C.flow_k:
                    keep = False
                else:
                    n_mid_side[side] += 1
            if keep:
                out.append((f, az, tier, d))
                if C.refrac_s is not None:
                    last_out[tier] = j
    return out


def run_rule4(pred, C43: "V43.Cfg43", C44: Cfg44, nframes: int = 100):
    res = {}
    for clip, frames in pred.items():
        per_cls = {}
        for cls in v4.DIST_CLASSES:
            d_at, az_at = V42.track_series2(frames, cls, nframes, C43)
            if not d_at:
                continue
            eps = apply_filters(V43.fires_cpa3(d_at, az_at, nframes, C43), az_at, C44, d_at)
            if eps:
                per_cls[cls] = eps
        res[clip] = per_cls
    return res


def label44(C: Cfg44) -> str:
    if C.track_hold:
        h = f"trackhold({C.gap_h:.0f}s,jump{C.jump_deg:.0f}" + (f",dj{C.jump_m:.0f}m" if C.jump_m is not None else "") + (",flip" if C.flip_reset else "") + ")"
    else:
        h = "hold-off" if C.dir_h is None else f"hold({C.dir_h:.0f}deg,{C.gap_h:.0f}s)"
    f = "flow-off" if C.flow_k is None else f"flowK{C.flow_k}"
    r = "" if C.refrac_s is None else f"+refrac{C.refrac_s:.1f}s"
    return f"{h}+{f}{r}"


if __name__ == "__main__":
    if "--verify" in sys.argv:
        pred = v4.load_pred(Path(sys.argv[sys.argv.index("--verify") + 1]))
        C43 = V43.Cfg43(**json.loads((ROOT / "out/notify_v43_sweep/winner.json").read_text()))
        a = V43.run_rule3(pred, C43)
        b = run_rule4(pred, C43, Cfg44())
        print("v4.3 と Cfg44既定 の発火:", "完全一致 ✅" if a == b else "不一致 ❌")
        sys.exit(0 if a == b else 1)
