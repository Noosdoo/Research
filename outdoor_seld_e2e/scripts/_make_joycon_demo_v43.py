# -*- coding: utf-8 -*-
"""Joy-conデモ v2 のデータ書き出し — v4.3＋警告音hold・「鳴らしすぎ」と「段階的な強まり」の確認用（2026-09-03）。

本人「機器側で束ねる案を確認するデモを今日」「安全→注意→至近と進むとき振動は徐々に強くなるか」への対応。
既存 out/joycon_demo/ は消さず、**out/joycon_demo_v2/** に新規に書く（新バージョンは新ファイル）。

fold32（v4.3の選定val・ft2因果推論・**本物のモデル出力**）から性格の違うクリップを選ぶ:
  A flicker  : 1台の車に強が0.8秒おきに複数回（「同じ車への再発火」を体感 → Unityの M キーで束ねON/OFF）
  B escalate : 同じ車が 中→強 と昇格（段階的な強まりを体感 → G キーで「段階(離散)」/「連続(urgency)」切替）
  C stream   : 幹線・歩行・車3台で通知が4回以上（本当の「交通量」の状況）
  D suppress : 安全な車だけで強が出ない（抑制の確認）
各クリップ: <clip>.wav（試聴用ステレオ・べき圧縮）/ _cues.csv（規則の生の出力・束ね無し）/
            _scene.csv（GT位置・可視化用）/ _urgency.csv（**予測**から毎フレームの緊急度 0..1 と方位。連続振動モード用）/
            _detect.csv（**検出層の出力そのもの**: 毎フレームの class/方位/距離。可視化で「見えているもの」を描く）/
            _layout.csv（道路の配置: 車線の横位置と進行方向・歩道・踏切の位置。scene.json から）

緊急度 u の定義（v4.3 の判定材料から）: 予測最接近 d_cpa と到達時間 t_cpa で
   u = 1（d_cpa≤cs かつ t_cpa≤2.5s）… 0（d_cpa≥cm or t_cpa≥4s）の間を線形。距離の保険 d≤1.5m は u=1。
   ⚠️ 表示・体感用。実際の発火は 4/4 の確認つき（cues.csv が本物）

使い方: python scripts/_make_joycon_demo_v43.py   （fold32 の foa が無ければ scp の案内を出す）
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

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
H = _load("nhold", "step12_notify_v9b_hold.py")
DG = _load("ndiag", "_notify_v42_diag.py")

C43 = V43.Cfg43(**json.loads((ROOT / "out/notify_v43_sweep/winner.json").read_text(encoding="utf-8")))
DSN = "v43tune"
PRED = ROOT / f"out/predictions_{DSN}/val_all_causal.csv"
DS = ROOT / f"out/dataset_outdoor_siren_{DSN}"
OUT = ROOT / "out/joycon_demo_v2"
CLS_NAME = {0: "siren", 1: "horn", 2: "backup_beep", 3: "bike_bell", 4: "car", 5: "crossing",
            6: "kick", 7: "bike"}
CS, CM, TW, TC = C43.cpa_strong, C43.cpa_mid, v4.TTC_WARN, v4.TTC_CAUTION


def cues_for(clip, pred_cars, pred_warn):
    out = []
    res = V43.run_rule3({clip: pred_cars[clip]}, C43).get(clip, {})
    for cls, eps in res.items():
        for j, az, tier, d in eps:
            out.append(((j + 1) / 10.0, "L" if az > 0 else "R", tier, CLS_NAME.get(cls, str(cls)), az))
    for k, c, az in H.warn_fires(pred_warn.get(clip, {}), hold=True):
        out.append(((k + 1) / 10.0, "L" if az > 0 else "R", "警告", CLS_NAME[c], az))
    return sorted(out)


def urgency_for(clip, pred_cars):
    """毎フレーム (t_s, u, az) — 距離クラスの追跡系列から v4.3 と同じ式で計算（最大の物体を採用）。"""
    rows = []
    series = {}
    for cls in v4.DIST_CLASSES:
        d_at, az_at = V42.track_series2(pred_cars[clip], cls, 100, C43)
        if d_at:
            series[cls] = (d_at, az_at)
    for j in range(100):
        best = (0.0, 0.0)
        for cls, (d_at, az_at) in series.items():
            d = d_at.get(j)
            if d is None:
                continue
            v = v4.closing_speed(d_at, j, win=C43.vel_win)
            adot = v4.azimuth_rate(az_at, j, win=C43.brg_win)
            dc, tc = v4.cpa_of(d, None if v is None else -v, adot)
            u = 0.0
            if d <= v4.T3:
                u = 1.0
            elif dc is not None:
                ud = float(np.clip((CM - dc) / (CM - CS), 0.0, 1.0)) if CM > CS else float(dc <= CS)
                ut = float(np.clip((TC - tc) / (TC - TW), 0.0, 1.0))
                u = min(ud, ut)
            if u > best[0]:
                best = (u, az_at[j])
        rows.append(((j + 1) / 10.0, best[0], best[1]))
    return rows


def pick(pred_cars, pred_warn, plan):
    picked = {}
    for clip in sorted(pred_cars):
        if len(picked) >= 4:
            break
        r = plan.get(clip, {})
        cues = cues_for(clip, pred_cars, pred_warn)
        cars = [c for c in cues if c[3] == "car"]
        tiers = "".join(c[2] for c in cars)
        evs = [DG.mk_event(c, t, fr) for c, t, fr in DG.gt_tracks(DS / "metadata_dist", clip)]
        has_crit = any(e["tier"] == "critical" for e in evs)
        gaps = [cars[i + 1][0] - cars[i][0] for i in range(len(cars) - 1)]
        if "A_flicker" not in picked and r.get("n_car") == "1" and tiers.count("強") >= 3 and gaps and max(gaps) <= 1.5:
            picked["A_flicker"] = (clip, cues, "A 1台の車に強が0.8秒おきに再発火（束ねON/OFFを M キーで比較）")
        elif "B_escalate" not in picked and r.get("n_car") == "1" and tiers.startswith("中") and "強" in tiers and has_crit:
            picked["B_escalate"] = (clip, cues, "B 同じ車が 中→強 と昇格（段階/連続を G キーで比較）")
        elif ("C_stream" not in picked and r.get("scene_type") == "arterial" and r.get("n_car") == "3"
              and r.get("motion") == "walk" and len(cars) >= 4):
            picked["C_stream"] = (clip, cues, "C 幹線・歩行・車3台の連続通知（本当の交通量）")
        elif ("D_suppress" not in picked and evs and all(e["tier"] == "safe" for e in evs)
              and "強" not in tiers and len(cars) >= 1):
            picked["D_suppress"] = (clip, cues, "D 安全な車だけ→中止まり・強は出ない（抑制）")
    return picked


def detect_rows(clip, pred_cars):
    """検出層の生出力 [(t, class, az, dist|'')]（距離はクラス4/6/7のみ）。"""
    out = []
    for j, evs in sorted(pred_cars[clip].items()):
        for c, az, d in evs:
            out.append(((j + 1) / 10.0, CLS_NAME.get(c, str(c)), az, d if c in v4.DIST_CLASSES else None))
    return out


def layout_rows(clip):
    """scene.json → 道路配置。歩行者は原点・FOA座標（x=前, y=左）。車線= 移動音源の横位置 y と進行方向。"""
    sj = DS / "work" / clip / "scene.json"
    if not sj.exists():
        return []
    sc = json.loads(sj.read_text(encoding="utf-8"))
    rows = [("scene", sc["row"].get("scene_type", ""), sc["mic"].get("motion", ""),
             sc["mic"].get("walk_dir_x", 0.0), round(float(sc["mic"].get("walk_speed_mps", 0.0)), 3))]
    seen = set()
    for s in sc["sources"]:
        if s["kind"] == "vehicle":
            y = round(float(s["wp"][0][2]), 1)
            key = (y, float(s.get("dir_x", 0.0)))
            if key in seen:
                continue
            seen.add(key)
            rows.append(("lane", y, s.get("dir_x", 0.0), s["class"], ""))
        elif s["kind"] == "static":
            rows.append(("static", round(float(s["wp"][0][1]), 1), round(float(s["wp"][0][2]), 1), s["class"], ""))
    return rows


def scene_rows_full(clip):
    """scene.json の軌道から全 100 フレームの位置を出す（2026-09-03「途中で対象物が消えないように」）。

    従来はラベル（可聴ゲート済み）だけを描いていたので、遠い・静かな間は車が画面から消えていた。
    vis=1 はそのフレームにラベルがある（鳴っていて模型が見るべき）、0 は「いるが無音・ラベル無し」。
    """
    import step11_v12_render as v12r
    from outdoor_seld.geometry import apparent_azel_deg
    m9 = v12r.m9
    sj = DS / "work" / clip / "scene.json"
    if not sj.exists():
        return None
    sc = json.loads(sj.read_text(encoding="utf-8"))
    mr = sc["mic"]; mo = mr.get("motion", "static"); Z = 1.5
    if mo == "walk":
        v = float(mr["walk_speed_mps"]); dx = float(mr.get("walk_dir_x", 1.0)); x0 = -dx * v * 5.0
        mic = np.array([[0.0, x0, 0.0, Z], [10.0, x0 + dx * v * 10.0, 0.0, Z]])
    elif mo == "walk_cross_y":
        v = float(mr["walk_speed_mps"]); ts = float(mr["t_stop_s"]); y0 = -0.5 - v * ts
        mic = np.array([[0.0, 0.0, y0, Z], [ts, 0.0, -0.5, Z], [10.0, 0.0, -0.5, Z]])
    else:
        mic = np.array([0.0, 0.0, Z])
    labeled = set()
    for line in open(DS / "metadata_dist" / f"{clip}.csv", encoding="utf-8"):
        g = line.strip().split(",")
        if len(g) == 6:
            labeled.add((int(g[0]), int(g[1]), int(g[2])))
    CLS_IDX = {n: i for i, n in CLS_NAME.items()}
    NAME = {"car_drive": "car"}
    tk = np.arange(100) * 0.1
    c = m9.sound_speed(m9.TEMP_C)
    rows = []
    for src in sc["sources"]:
        cls = NAME.get(src["class"], src["class"])
        if cls not in CLS_IDX:
            continue
        ci = CLS_IDX[cls]; tr = int(src.get("track", 0))
        wp = np.array(src["wp"], float)
        az, _e, _a, _b = apparent_azel_deg(tk, wp, mic, c)
        dist = m9._dist_series(wp, mic, tk)
        for k in range(100):
            if np.isfinite(az[k]) and np.isfinite(dist[k]):
                rows.append((k / 10.0, f"{ci}_{tr}", cls, float(az[k]), float(dist[k]), 1 if (k, ci, tr) in labeled else 0))
    return rows


def write_clip(clip, cues, urg, outdir: Path, det=None, lay=None):
    foa = DS / "foa" / f"{clip}.flac"
    if not foa.exists():
        print(f"  ⚠️ {foa.name} がローカルに無い → scp is-server:~/research/outdoor_seld_e2e/{foa.relative_to(ROOT).as_posix()} {foa.parent}")
        return False
    x, sr = sf.read(foa, dtype="float64")
    st = np.stack([x[:, 0] + 0.5 * x[:, 1], x[:, 0] - 0.5 * x[:, 1]], axis=1)
    st = st / max(np.max(np.abs(st)), 1e-9)
    st = np.sign(st) * np.abs(st) ** 0.5 * 0.7
    sf.write(outdir / f"{clip}.wav", st.astype(np.float32), sr, subtype="PCM_16")
    with open(outdir / f"{clip}_cues.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,side,tier,class,az_deg\n")
        for t, side, tier, cls, az in cues:
            f.write(f"{t:.1f},{side},{tier},{cls},{az:.0f}\n")
    with open(outdir / f"{clip}_scene.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,obj,class,az_deg,dist_m,vis\n")
        full = scene_rows_full(clip)
        if full is None:      # 軌道が無ければ従来どおりラベルから（vis=1）
            for line in open(DS / "metadata_dist" / f"{clip}.csv", encoding="utf-8"):
                g = line.strip().split(",")
                if len(g) == 6:
                    f.write(f"{int(g[0])/10.0:.1f},{g[1]}_{g[2]},{CLS_NAME[int(g[1])]},{float(g[3]):.1f},{float(g[5]):.2f},1\n")
        else:
            for t, obj, cls, az, dist, vis in full:
                f.write(f"{t:.1f},{obj},{cls},{az:.1f},{dist:.2f},{vis}\n")
    with open(outdir / f"{clip}_urgency.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,urgency,az_deg\n")
        for t, u, az in urg:
            f.write(f"{t:.1f},{u:.3f},{az:.0f}\n")
    if det is not None:
        with open(outdir / f"{clip}_detect.csv", "w", encoding="utf-8", newline="\n") as f:
            f.write("t_s,class,az_deg,dist_m\n")
            for t, cls, az, d in det:
                f.write(f"{t:.1f},{cls},{az:.0f},{'' if d is None else f'{d:.2f}'}\n")
    if lay:
        with open(outdir / f"{clip}_layout.csv", "w", encoding="utf-8", newline="\n") as f:
            f.write("type,a,b,c,d\n")
            for r in lay:
                f.write(",".join(str(x) for x in r) + "\n")
    return True


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    plan = {r["clip_id"]: r for r in csv.DictReader(open(DS / "plan" / f"assignment_{DSN}.csv", encoding="utf-8"))}
    pred_cars = v4.load_pred(PRED)
    pred_warn = H.load_pred7(PRED)
    picked = pick(pred_cars, pred_warn, plan)
    M = ["# Joy-conデモ v2 データ（自動生成: _make_joycon_demo_v43.py）", "",
         f"- 通知= **v4.3**（`{V43.label43(C43)}`）＋警告音hold の本物の出力。クリップは fold32・ft2 因果推論",
         "- cues.csv は規則の生の出力（束ね無し）。Unity 側で M=束ね(1秒以内の同段再トリガは延長) / G=連続振動(urgency) を切替",
         "- urgency.csv は予測からの毎フレーム緊急度（0..1）。実発火は cues.csv（4/4確認つき）",
         "- detect.csv は検出層の生出力（class/方位/距離）。layout.csv は道路の配置（車線・歩道・踏切）", ""]
    missing = []
    for key, (clip, cues, desc) in picked.items():
        ok = write_clip(clip, cues, urgency_for(clip, pred_cars), OUT,
                        det=detect_rows(clip, pred_cars), lay=layout_rows(clip))
        if not ok:
            missing.append(clip)
        M.append(f"## {clip} — {desc}")
        M += [f"- {t:.1f}s {side} {tier} ({cls}, az={az:.0f}°)" for t, side, tier, cls, az in cues] + [""]
        print(f"[{key}] {clip}: {len(cues)} cues — {desc}")
    (OUT / "manifest.md").write_text("\n".join(M), encoding="utf-8")
    if missing:
        print("scp が要るクリップ:", " ".join(missing))
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
