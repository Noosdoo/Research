# -*- coding: utf-8 -*-
"""確定評価v2 用の通知チェーン（**v4.3 ＋ 警告音hold**）— 2026-09-03。todo③「v33チェーンへの組み込み」。

- 車: 確定評価の採点器 `step12_notify_v33.py`（車ごとの方位帰属・分母=manifest・tier定義）を**そのまま**使い、
  距離トリガの作り方だけ v4.3（`step12_notify_v43.py`）に差し替える（`_v12_conf_notify_v41.py` と同じ流儀。
  保険列= v33 の dist_triggers をそのまま union）。
- 警告音5クラス: `step12_notify_v9b_hold.py` の hold 方式（前回**検出**から5秒）で到達・重複を採点。
- 出力: <outdir>/notify_v2chain.md（車=v33形式 ＋ 警告音=hold形式 ＋ 見出しに規則を明記）

⚠️ fold20（確定評価セット）に当てるのは v2 の事前登録が発効した後の**1回だけ**。
   本スクリプトの動作確認は val（fold2 等）で行う（--ds / --regex で対象を指定）。

使い方:
  PYTHONPATH=scripts:src python scripts/_conf_notify_v2chain.py <pred.csv> <outdir> \
      --ds out/dataset_outdoor_siren_v11 --regex "fold2_room1_mix(\\d{4})" --max 1200
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
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


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


pred_in = Path(sys.argv[1])
outdir = Path(sys.argv[2])
outdir.mkdir(parents=True, exist_ok=True)
DS = ROOT / arg("--ds", "out/dataset_outdoor_siren_v12_conf")
REGEX = arg("--regex", r"fold20_room1_mix(\d{4})")
MAXN = int(arg("--max", "1200"))
WINNER = ROOT / arg("--winner", "out/notify_v43_sweep/winner.json")
pat = re.compile(REGEX)


def _in_scope(clip: str) -> bool:
    m = pat.match(clip)
    return bool(m and 1 <= int(m.group(1)) <= MAXN)


core = outdir / "pred_core.csv"
with open(core, "w", encoding="utf-8") as w:
    for line in open(pred_in, encoding="utf-8"):
        if _in_scope(line.split(",", 1)[0]):
            w.write(line)

# ---- 車: v33 採点器 ＋ v4.3 トリガ ----------------------------------------------
os.environ["NOTIFY_LINK_DEG"] = "60"          # v3.4 と同じ（v4.1 conf と同一設定）
os.environ["B2_DUMP"] = "1"
spec = importlib.util.spec_from_file_location("nv33chain", ROOT / "scripts" / "step12_notify_v33.py")
nv = importlib.util.module_from_spec(spec)
_argv = sys.argv
sys.argv = [sys.argv[0], str(core), str(outdir)]
spec.loader.exec_module(nv)
sys.argv = _argv

v4 = _load("nv4", "step12_notify_v4_ttc.py")
V42 = _load("nv42", "step12_notify_v42_bearing.py")
V43 = _load("nv43", "step12_notify_v43.py")
HOLD = _load("nv9hold", "step12_notify_v9b_hold.py")
C43 = V43.Cfg43(**json.loads(WINNER.read_text(encoding="utf-8")))
_dist_triggers = nv.dist_triggers                 # 保険列（v3.4 と同一）


def _series43(dseq):
    """v4.3 と同じ系列（予測方位で連結 link_pred=True）。dseq: frame -> [(az, d)]。"""
    pred_clip = {j: [(nv.CAR, a, d) for a, d in cand] for j, cand in dseq.items()}
    return V42.track_series2(pred_clip, nv.CAR, 100, C43)


def v43_triggers(dseq, thresh):
    """v4.3 の（強 or 中）発火フレーム列を dist_triggers 互換 [(frame, az)] で返す。"""
    strong = thresh <= nv.T3 + 1e-9
    d_at, az_at = _series43(dseq)
    pre = {}
    for j in range(100):
        d = d_at.get(j)
        if d is None:
            continue
        v = v4.closing_speed(d_at, j, win=C43.vel_win)
        ddot = None if v is None else -v
        adot = v4.azimuth_rate(az_at, j, win=C43.brg_win)
        adot_rc = adot if C43.rc_brg_win == C43.brg_win else v4.azimuth_rate(az_at, j, win=C43.rc_brg_win)
        dc, tc = v4.cpa_of(d, ddot, adot)
        rc = (C43.route_c and adot_rc is not None and abs(adot_rc) <= C43.adot_th
              and ddot is not None and ddot < -C43.v_close and d <= C43.dn)
        bok = C43.strong_adot_max is None or (adot is not None and abs(adot) <= C43.strong_adot_max)
        pre[j] = (dc, tc, rc, bok)
    dc_th, tc_th = (C43.cpa_strong, v4.TTC_WARN) if strong else (C43.cpa_mid, v4.TTC_CAUTION)

    def cond(j, d):
        dc, tc, rc, bok = pre.get(j, (None, None, False, True))
        cpa = dc is not None and dc <= dc_th and tc <= tc_th
        if strong:
            cpa = cpa and bok
        return cpa or rc

    hits = {j: a for j, a, _d in V42._stream_mn(d_at, az_at, 100, cond, C43.confirm_m, C43.confirm_n)}
    for j, a in _dist_triggers(dseq, thresh):     # 距離の保険（v3.4 と同一）
        hits.setdefault(j, a)
    return [(j, hits[j]) for j in sorted(hits)]


nv.dist_triggers = v43_triggers
nv.DS = DS
nv.PRED = core
nv.OUT = outdir
nv.MANIFEST_FILTER = _in_scope
print(f"[v2chain] cars=v4.3 {V43.label43(C43)} cs{C43.cpa_strong}/cm{C43.cpa_mid} + 保険(v3.4) / "
      f"LINK_DEG={nv.LINK_DEG} / DS={DS.name}", flush=True)
nv.main()

# ---- 警告音: hold 方式 ------------------------------------------------------------
pred7 = HOLD.load_pred7(core)
meta = DS / "metadata_dist"
tot = hit = fires_n = dup = 0
for clip in sorted({p.stem for p in meta.glob("*.csv") if _in_scope(p.stem)}):
    evs = HOLD.warn_events(meta, clip)
    fires = HOLD.warn_fires(pred7.get(clip, {}), hold=True) if clip in pred7 else []
    fires_n += len(fires)
    for c, f0, f1 in evs:
        tot += 1
        inside = [f for f in fires if f[1] == c and f0 - 10 <= f[0] <= f1 + 10]
        hit += int(bool(inside))
        dup += max(len(inside) - 1, 0)
warn_md = [f"## 警告音5クラス（hold方式・前回検出から{HOLD.v9.REFRACTORY/10:.0f}秒）", "",
           f"- GTイベント {tot:,} / 到達 {hit:,}（**{100*hit/max(tot,1):.1f}%**）",
           f"- 発火 {fires_n:,} / 同一イベント内の重複発火 {dup:,}"]

md = outdir / "notify_v33.md"
body = md.read_text(encoding="utf-8") if md.exists() else ""
head = "\n".join([
    "# 【通知v2チェーン = v4.3 ＋ 警告音hold】",
    "",
    f"- 対象: {DS.name} / {REGEX} ≤{MAXN}",
    f"- 車の規則: v4.3 `{V43.label43(C43)}` cs{C43.cpa_strong}/cm{C43.cpa_mid}（予測列 M/N={C43.confirm_m}/{C43.confirm_n}）"
    f" ∪ 距離の保険（v3.4 と同一）。採点器・分母・車ごとの方位帰属（±25°）・tier定義は確定評価 v1 と同一（step12_notify_v33.py）",
    "- 警告音の規則: hold（前回検出から5秒・アンカー方位固定）",
    "", "---", ""])
(outdir / "notify_v2chain.md").write_text(head + body + "\n\n" + "\n".join(warn_md) + "\n", encoding="utf-8")
print("\n".join(warn_md))
print(f"[v2chain] -> {outdir / 'notify_v2chain.md'}")
