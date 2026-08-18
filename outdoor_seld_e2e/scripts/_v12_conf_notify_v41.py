# -*- coding: utf-8 -*-
"""確定評価セット(fold20 core 1,200本)を**通知v4.1**で採点する。

## なぜ必要か

v4.1 の数値（至近到達95.5%など）は検証データ(val)のもので、しかも**到達の定義が
確定評価と違う**（確定評価=車1台ごとの到達率 / v4.1評価=GTイベント単位・窓照合）。
そのまま並べると 69.9% と矛盾して見える。**同じ物差しで測り直す**のがこのスクリプト。

## やり方

確定評価の採点器 `step12_notify_v33.py`（69.9%/90.4%/1.3% を出したもの）を
そのまま使い、**発火の作り方だけ** v4.1 に差し替える。
分母・車ごとの帰属・tier定義・episode分類は一切変えない。

  強 = 予測列(d_cpa≤CPA_STRONG_M かつ t_cpa≤TTC_WARN が CONFIRM_CPA 連続)
     ∪ 保険列(元の dist_triggers(T3) をそのまま呼ぶ)
  中 = 予測列(d_cpa≤CPA_MID_M かつ t_cpa≤TTC_CAUTION が CONFIRM_CPA 連続)
     ∪ 保険列(元の dist_triggers(T2) をそのまま呼ぶ)

保険列に元の関数をそのまま使うので、**v4.1 の発火は v3.4 の発火を必ず含む**。

## 事前登録との関係（重要）

確定評価セットは「基準を先に決めて1回だけ採点する」と事前登録した。これはその
**一発評価とは別の、規則を差し替えた再採点**である。しきい値は検証データだけで
決めており、確定評価の結果を見て調整してはいない。事前登録の一発評価の数値
（v3.4の69.9%/90.4%/1.3%）は**書き換えない**。

使い方:
  PYTHONPATH=scripts:src python scripts/_v12_conf_notify_v41.py <pred> <outdir>
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pred_in = Path(sys.argv[1])
outdir = Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)

pat = re.compile(r"fold20_room1_mix(\d{4})")


def _core_only(clip: str) -> bool:
    m = pat.match(clip)
    return bool(m and 1 <= int(m.group(1)) <= 1200)


core = outdir / "conf_core.csv"
with open(core, "w") as w:
    for line in open(pred_in):
        m = pat.match(line)
        if m and 1 <= int(m.group(1)) <= 1200:
            w.write(line)

os.environ["NOTIFY_LINK_DEG"] = "60"          # v3.4 と同じ
os.environ["B2_DUMP"] = "1"

spec = importlib.util.spec_from_file_location(
    "nv41conf", ROOT / "scripts" / "step12_notify_v33.py")
nv = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0], str(core), str(outdir)]
spec.loader.exec_module(nv)

sp4 = importlib.util.spec_from_file_location(
    "nv4", ROOT / "scripts" / "step12_notify_v4_ttc.py")
v4 = importlib.util.module_from_spec(sp4)
sp4.loader.exec_module(v4)

_dist_triggers = nv.dist_triggers                 # 保険列はこれをそのまま使う


def _series(dseq):
    """v4.1と同じ単一トラック系列（最も近い候補・前フレームと方位±LINK_DEGで連結）。"""
    d_at, az_at, prev = {}, {}, None
    for j in range(100):
        cand = dseq.get(j, [])
        if not cand:
            prev = None
            continue
        if prev is not None:
            linked = [(a, d) for a, d in cand if nv.cdiff(a, prev) <= nv.LINK_DEG]
            if linked:
                cand = linked
        a, d = min(cand, key=lambda x: x[1])
        d_at[j], az_at[j], prev = d, a, a
    return d_at, az_at


def cpa_triggers(dseq, thresh):
    """v4.1の発火列を、元の dist_triggers と同じ [(frame, az)] 形式で返す。"""
    strong = thresh <= nv.T3 + 1e-9
    cpa_th = v4.CPA_STRONG_M if strong else v4.CPA_MID_M
    tc_th = v4.TTC_WARN if strong else v4.TTC_CAUTION

    d_at, az_at = _series(dseq)
    run, hits = 0, {}
    for j in range(100):
        d = d_at.get(j)
        if d is None:
            run = 0
            continue
        vel = v4.closing_speed(d_at, j)
        adot = v4.azimuth_rate(az_at, j)
        dc, tc = v4.cpa_of(d, None if vel is None else -vel, adot)
        ok = dc is not None and dc <= cpa_th and tc <= tc_th
        run = run + 1 if ok else 0
        if run >= v4.CONFIRM_CPA:
            hits[j] = az_at[j]
    for j, a in _dist_triggers(dseq, thresh):     # 距離の保険（v3.4と同一）
        hits.setdefault(j, a)
    return [(j, hits[j]) for j in sorted(hits)]


nv.dist_triggers = cpa_triggers
nv.DS = ROOT / "out" / "dataset_outdoor_siren_v12_conf"
nv.PRED = core
nv.OUT = outdir
nv.MANIFEST_FILTER = _core_only
print(f"[v4.1 conf] CPA_STRONG={v4.CPA_STRONG_M}m CPA_MID={v4.CPA_MID_M}m "
      f"TTC={v4.TTC_WARN}/{v4.TTC_CAUTION}s CONFIRM_CPA={v4.CONFIRM_CPA} "
      f"LINK_DEG={nv.LINK_DEG}", flush=True)
nv.main()

# 採点器の見出しは v3.3 のままなので、何を測ったのかを先頭に書き足す
md = outdir / "notify_v33.md"
if md.exists():
    body = md.read_text(encoding="utf-8")
    head = "\n".join([
        "# 【通知v4.1で再採点】確定評価セット core 1,200本",
        "",
        "**事前登録の一発評価（v3.4・69.9%/90.4%/1.3%）は書き換えていない。**",
        "これはその後に規則だけを差し替えて1回採点し直したものである。",
        "しきい値は検証データだけで決めており、確定評価の結果を見て調整していない。",
        "",
        f"規則: 強=（予測最接近≤{v4.CPA_STRONG_M}m かつ 到達≤{v4.TTC_WARN}s が"
        f"{v4.CONFIRM_CPA}フレーム連続）∪（距離≤{nv.T3}m が2フレーム連続）"
        f" / 中=（≤{v4.CPA_MID_M}m かつ ≤{v4.TTC_CAUTION}s）∪（距離≤{nv.T2}m）",
        "採点器・分母・車ごとの帰属・tier定義は確定評価と同一"
        "（step12_notify_v33.py, NOTIFY_LINK_DEG=60）。",
        "", "---", "", ""])
    md.write_text(head + body, encoding="utf-8")
    (outdir / "notify_v41_conf.md").write_text(head + body, encoding="utf-8")
print(f"[v4.1 conf] -> {outdir}")
