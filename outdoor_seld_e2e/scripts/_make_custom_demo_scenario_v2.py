# -*- coding: utf-8 -*-
"""Joy-conデモ用シナリオ自作ツール v2（2026-09-03）— v4.3 規則・列車対応・デモv2の出力一式。

v1（_make_custom_demo_scenario.py・2026-09-02）からの変更:
  - 通知規則を v4.3（step12_notify_v43 の勝ち構成）＋警告音hold に
  - 新クラス "train": 列車の通過（4〜8両の点音源・警笛は任意）。ラベルは crossing クラス（v12train と同じ意味拡張）。
    "crossing"（警報機）と組み合わせると「踏切で待つ→列車が目の前を通る」が作れる
  - 出力先 out/joycon_demo_v2/。cues/scene に加えて layout（車線・踏切）/ urgency / detect（=GT系列・オラクル）も書く
  - --all <dir>: フォルダ内の JSON を全部処理

⚠️ 通知は**GT系列に規則を当てたオラクル動作**（知覚モデルは通していない）。cues.csv の末尾に明記。
⚠️ 音量の既定値はデモ用の概算。学習・評価には一切使わない。晴れ前提（雨は入れない）。

使い方:
  python scripts/_make_custom_demo_scenario_v2.py <scenario.json>
  python scripts/_make_custom_demo_scenario_v2.py --all out/joycon_demo_v2/scenarios

JSON（例は out/joycon_demo_v2/scenarios/）:
{
  "name": "fumikiri_matsu", "motion": "static"|"walk", "walk_speed_kmh": 4.3, "noise_dba": 45, "seed": 7,
  "events": [
    {"class": "crossing", "side": "left", "lateral_m": 3.0, "x_m": 2.0},
    {"class": "train", "from": "front", "side": "left", "lateral_m": 5.0, "speed_kmh": 60, "cpa_s": 6.0,
     "n_cars": 6, "horn": "long"|"short3"|null}
  ]
}
classごとのキー:
  car / kick / bike / bike_bell / backup_beep / siren / horn（移動）: from side lateral_m speed_kmh cpa_s [level_db t_on t_off siren_type]
  crossing（静止・警報機）: side lateral_m x_m
  train（移動・列車）: from side lateral_m speed_kmh cpa_s [n_cars horn]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import step11_v12_render as v12r  # noqa: E402  (v12チェーン: 都市騒音・-6dB規約込み)
m9 = v12r.m9
m9.V91 = True                     # 踏切はv2（和音・断続・打音）を使う

from outdoor_seld.geometry import apparent_azel_deg  # noqa: E402
from outdoor_seld.kickboard import make_kickboard  # noqa: E402
from outdoor_seld.motorcycle import make_motorcycle  # noqa: E402
from outdoor_seld.train import make_train_horn, make_train_passby  # noqa: E402
from outdoor_seld.calibration import a_weighted_rms  # noqa: E402


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


V42 = _load("nv42", "step12_notify_v42_bearing.py")
V43 = _load("nv43", "step12_notify_v43.py")
H = _load("nhold", "step12_notify_v9b_hold.py")
v4 = sys.modules["nv42"].v4

C43 = V43.Cfg43(**json.loads((ROOT / "out/notify_v43_sweep/winner.json").read_text(encoding="utf-8")))
CLS_IDX = {"siren": 0, "horn": 1, "backup_beep": 2, "bike_bell": 3, "car": 4, "crossing": 5, "kick": 6, "bike": 7}
NAME_OF = {v: k for k, v in CLS_IDX.items()}
DIST_CLASSES = {4, 6, 7}
L1M_DEFAULT = {"car": 74, "siren": 112, "horn": 104, "backup_beep": 90, "bike_bell": 85,
               "crossing": 92, "kick": 60, "bike": 96, "train": 95}
MIC = np.array([0.0, 0.0, 1.5])
OUT = ROOT / "out/joycon_demo_v2"
CS, CM, TW, TC = C43.cpa_strong, C43.cpa_mid, v4.TTC_WARN, v4.TTC_CAUTION


def make_dry(ev, seed):
    cls = ev["class"]
    v = ev.get("speed_kmh", 30) / 3.6
    rng = np.random.default_rng(seed)
    if cls == "car":
        return m9._make_dry({"class": "car_drive", "speed_mps": v, "params": {"audio_seed": seed, "f0": 42.0}})
    if cls == "siren":
        st = ev.get("siren_type", "peepo")
        p = {"siren_type": st}
        if st == "fire":
            p["audio_seed"] = seed
        return m9._make_dry({"class": "siren", "params": p})
    if cls == "horn":
        return m9._make_dry({"class": "horn", "params": {"audio_seed": seed}})
    if cls == "backup_beep":
        return m9._make_dry({"class": "backup_beep", "params": {}})
    if cls == "bike_bell":
        return m9._make_dry({"class": "bike_bell", "params": {}})
    if cls == "crossing":
        return m9._make_dry({"class": "crossing", "params": {"click_seed": seed}})
    if cls == "kick":
        return make_kickboard(m9.CLIP, m9.FS_SIM, rng, speed_mps=max(v, 1.5))
    if cls == "bike":
        return make_motorcycle(m9.CLIP, m9.FS_SIM, rng, engine_class="motorcycle", speed_mps=max(v, 5.0))
    if cls == "train":
        body = make_train_passby(m9.CLIP, m9.FS_SIM, rng, speed_mps=max(v, 5.0), peak=1.0)
        h = ev.get("horn")
        if h:
            if h == "long":
                seg = make_train_horn(1.5, m9.FS_SIM, rng, horn_type="air")
            else:
                parts = []
                for _ in range(3):
                    parts.append(make_train_horn(0.4, m9.FS_SIM, rng, horn_type="air"))
                    parts.append(np.zeros(int(0.25 * m9.FS_SIM)))
                seg = np.concatenate(parts)
            g_h = (a_weighted_rms(body, m9.FS_SIM) / max(a_weighted_rms(seg, m9.FS_SIM), 1e-12)) * 10.0 ** (6.0 / 20.0)
            i0 = int(float(ev.get("horn_t", 1.0)) * m9.FS_SIM)
            j = min(len(seg), len(body) - i0)
            if j > 0:
                body[i0:i0 + j] += g_h * seg[:j]
        return body
    raise SystemExit(f"未対応class: {cls}")


def mic_setup(S):
    if S.get("motion", "static") != "walk":
        return MIC, (lambda t: 0.0)
    v = float(S.get("walk_speed_kmh", 4.3)) / 3.6
    x0 = -v * 5.0
    wp = np.array([[0.0, x0, 0.0, 1.5], [m9.CLIP, x0 + v * m9.CLIP, 0.0, 1.5]])
    return wp, (lambda t: x0 + v * t)


def waypoints(ev, mic_x, shift_m=0.0):
    y = ev.get("lateral_m", 2.0) * (1.0 if ev.get("side", "left") == "left" else -1.0)
    if ev["class"] == "crossing":
        x = mic_x(5.0) + ev.get("x_m", 3.0)
        return np.array([[0.0, x, y, 2.5], [m9.CLIP, x, y, 2.5]])
    v = ev.get("speed_kmh", 30) / 3.6
    d = -1.0 if ev.get("from", "front") == "front" else 1.0
    cpa = ev.get("cpa_s", 6.0)
    x0 = mic_x(cpa) - d * v * cpa - d * shift_m    # cpa_s の瞬間に歩行者の真横。shift は列車の後続車両用
    return np.array([[0.0, x0, y, 1.5], [m9.CLIP, x0 + d * v * m9.CLIP, y, 1.5]])


def expand_events(S):
    """"train" を n_cars 両の点音源に展開する（先頭だけ警笛・ラベルは先頭/中間/最後尾）。"""
    out = []
    for ev in S["events"]:
        if ev["class"] != "train":
            out.append(dict(ev, _label=True))
            continue
        n = int(ev.get("n_cars", 6))
        labeled = {0, n // 2, n - 1}
        for i in range(n):
            e = dict(ev, _label=(i in labeled), _shift=i * 20.0, _car_index=i)
            if i != 0:
                e["horn"] = None
            e["level_db"] = float(ev.get("level_db", L1M_DEFAULT["train"])) - 10.0 * np.log10(n)
            out.append(e)
    return out


def urgency_from_gt(frames_dist):
    """オラクルの毎フレーム緊急度（距離クラスの GT 系列に v4.3 の判定式）。"""
    rows = []
    series = {}
    for cls in DIST_CLASSES:
        d_at, az_at = V42.track_series2(frames_dist, cls, 100, C43)
        if d_at:
            series[cls] = (d_at, az_at)
    for j in range(100):
        best = (0.0, 0.0)
        for cls, (d_at, az_at) in series.items():
            d = d_at.get(j)
            if d is None:
                continue
            vv = v4.closing_speed(d_at, j, win=C43.vel_win)
            adot = v4.azimuth_rate(az_at, j, win=C43.brg_win)
            dc, tc = v4.cpa_of(d, None if vv is None else -vv, adot)
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


def run(spec_path: Path) -> None:
    S = json.loads(spec_path.read_text(encoding="utf-8"))
    name = S.get("name", spec_path.stem)
    seed0 = int(S.get("seed", 1))
    c = m9.sound_speed(m9.TEMP_C)
    n24 = int(m9.CLIP * m9.FS_OUT)
    mic, mic_x = mic_setup(S)
    events = expand_events(S)

    stems, gt, lanes, statics = [], [], [], []
    for i, ev in enumerate(events):
        wp = waypoints(ev, mic_x, ev.get("_shift", 0.0))
        t_on = float(ev.get("t_on", 0.0))
        t_off = float(ev.get("t_off", m9.CLIP))
        dry = m9._window(make_dry(ev, seed0 * 101 + i * 17 + 3), t_on, t_off)
        a0, a1 = int(t_on * m9.FS_SIM), int(t_off * m9.FS_SIM)
        l1m = float(ev.get("level_db", L1M_DEFAULT[ev["class"]]))
        g = m9.gain_for_spl_a(dry[a0:a1], m9.FS_SIM, l1m)
        _, stem_wr = m9._render_stem(dry * g, wp, mic, c)
        stems.append(stem_wr)
        tk = np.arange(100) * 0.1
        az, _el, _a, _b = apparent_azel_deg(tk, wp, mic, c)
        dist = m9._dist_series(wp, mic, tk)
        act = (tk >= t_on) & (tk < t_off)
        cls_name = "crossing" if ev["class"] == "train" else ev["class"]
        gt.append((CLS_IDX[cls_name], az, dist, act, ev, i))
        if ev["class"] == "crossing":
            statics.append((float(wp[0][1]), float(wp[0][2]), "crossing"))
        else:
            y = float(wp[0][2]); dirx = 1.0 if ev.get("from", "front") == "behind" else -1.0
            key = (round(y, 1), dirx, "train" if ev["class"] == "train" else "car")
            if key not in lanes:
                lanes.append(key)
        print(f"  event{i}: {ev['class']} 最接近{dist.min():.1f}m@{tk[dist.argmin()]:.1f}s l1m={l1m:.1f}dB"
              + ("" if ev.get("_label", True) else " (音のみ・ラベル無し)"))

    rng_n = np.random.default_rng(seed0 * 7919 + 13)
    noise = m9.diffuse_foa_noise(n24, m9.FS_OUT, rng_n)
    noise *= m9.gain_for_spl_a(noise[0], m9.FS_OUT, float(S.get("noise_dba", 45.0)))
    mix = noise.copy()
    for st in stems:
        mix = mix + st
    peak = float(np.max(np.abs(mix)))
    if peak >= m9.PEAK_MAX:
        print(f"⚠️ peak {peak:.2f} が規約上限を超えたため正規化した（音量設定が過大）")
        mix *= (m9.PEAK_MAX * 0.9 / peak)

    # ---- 通知（オラクル: GT系列に v4.3＋hold を当てる）----
    frames_dist, frames_warn = {}, {}
    for ci, az, dist, act, ev, _ in gt:
        if not ev.get("_label", True):
            continue
        for k in range(100):
            if not act[k] or not (np.isfinite(az[k]) and np.isfinite(dist[k])):
                continue
            if ci in DIST_CLASSES:
                frames_dist.setdefault(k, []).append((ci, float(az[k]), float(dist[k])))
            else:
                frames_warn.setdefault(k, {})[ci] = (float(az[k]), 0.0)
    cues = []
    res = V43.run_rule3({"x": frames_dist}, C43).get("x", {})
    for ci, eps in res.items():
        for j, azv, tier, d in eps:
            cues.append(((j + 1) / 10.0, "L" if azv > 0 else "R", tier, NAME_OF[ci], azv))
    warn_clip = {k: [(ci, a, e) for ci, (a, e) in v.items()] for k, v in frames_warn.items()}
    for k, ci, azv in H.warn_fires(warn_clip, hold=True):
        cues.append(((k + 1) / 10.0, "L" if azv > 0 else "R", "警告", NAME_OF[ci], azv))
    cues.sort()

    # ---- 書き出し ----
    OUT.mkdir(parents=True, exist_ok=True)
    st = np.stack([mix[0] + 0.5 * mix[1], mix[0] - 0.5 * mix[1]], axis=1)
    st = st / max(np.max(np.abs(st)), 1e-9)
    st = np.sign(st) * np.abs(st) ** 0.5 * 0.7
    base = OUT / f"custom_{name}"
    sf.write(f"{base}.wav", st.astype(np.float32), m9.FS_OUT, subtype="PCM_16")
    with open(f"{base}_scene.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,obj,class,az_deg,dist_m\n")
        for ci, az, dist, act, ev, oi in gt:
            cname = "train" if ev["class"] == "train" else ev["class"]
            for k in range(100):
                if act[k] and np.isfinite(az[k]) and np.isfinite(dist[k]):
                    f.write(f"{k/10.0:.1f},{oi},{cname},{az[k]:.1f},{dist[k]:.2f}\n")
    with open(f"{base}_detect.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,class,az_deg,dist_m\n")
        for k in sorted(frames_dist):
            for ci, a, d in frames_dist[k]:
                f.write(f"{(k+1)/10.0:.1f},{NAME_OF[ci]},{a:.0f},{d:.2f}\n")
        for k in sorted(frames_warn):
            for ci, (a, _e) in frames_warn[k].items():
                f.write(f"{(k+1)/10.0:.1f},{NAME_OF[ci]},{a:.0f},\n")
        f.write("# オラクル（検出=GT系列）。モデル出力ではない\n")
    with open(f"{base}_urgency.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,urgency,az_deg\n")
        for t, u, az in urgency_from_gt(frames_dist):
            f.write(f"{t:.1f},{u:.3f},{az:.0f}\n")
    with open(f"{base}_layout.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("type,a,b,c,d\n")
        f.write(f"scene,{S.get('scene_type', 'residential')},{S.get('motion', 'static')},{1.0 if S.get('motion') == 'walk' else 0.0},\n")
        for y, dirx, kind in lanes:
            f.write(f"lane,{y},{dirx},{kind},\n")
        for x, y, kind in statics:
            f.write(f"static,{x},{y},{kind},\n")
    with open(f"{base}_cues.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,side,tier,class,az_deg\n")
        for t, side, tier, cls, azv in cues:
            f.write(f"{t:.1f},{side},{tier},{cls},{azv:.0f}\n")
        f.write("# オラクル動作（GT系列+v4.3/hold）。モデル出力ではない\n")
    print(f"custom_{name}: キュー{len(cues)}件 " + " / ".join(f"{t:.1f}s {side} {tier}({cls})" for t, side, tier, cls, _ in cues))


def main() -> int:
    if "--all" in sys.argv:
        d = Path(sys.argv[sys.argv.index("--all") + 1])
        for p in sorted(d.glob("*.json")):
            print(f"== {p.name}")
            run(p)
    else:
        run(Path(sys.argv[1]))
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
