# -*- coding: utf-8 -*-
"""Joy-conデモ用シナリオ自作ツール v3（2026-09-03）— v2 ＋ 加減速・停車・発進・横切り・左折・頭上（高架）。

v2（_make_custom_demo_scenario_v2.py）からの変更（v2 の JSON はそのまま同じ結果になる）:
  - 速度プロファイル profile: "pass"（等速・既定）/ "stop"（減速→停止→[発進]）/ "start"（停車中→発進）
    または speed_knots: [[t_s, km/h], ...]（折れ線で自由に）
  - 経路 geom: "straight"（車線に沿う・既定）/ "cross"（歩行者の進路を横切る道路を y 方向に走る）/
    "turn"（車線から 90° 曲がる。左折巻き込みなど）
  - height_m: 音源の高さ（高架の列車=7m など）。方位だけでなく仰角も付く
  - 速度に応じた音量の包絡（停止中はアイドル idle_db。engine_off なら発進前は無音）
  - layout に xlane（横切る道路・線路・高架）を追加 → ScenarioVisualizer が描く

⚠️ v2 と同じく、通知は GT系列に v4.3＋hold を当てたオラクル動作。音は本物の合成器。晴れ前提。
⚠️ 加減速中の音の変化は「音量の包絡」だけ（エンジン音の高さは変わらない＝近似）。反響（トンネル）は非対応。

使い方:
  python scripts/_make_custom_demo_scenario_v3.py <scenario.json> [...]
  python scripts/_make_custom_demo_scenario_v3.py --all out/joycon_demo_v2/scenarios

移動イベントのキー（v2 のものに加えて）:
  profile: pass|stop|start   t_stop t_go decel_mps2(2.0) accel_mps2(1.5) speed_kmh_after idle_db(-8) engine_off(true)
  speed_knots: [[t, kmh], ...]
  geom: straight|cross|turn  ahead_m（基準点の前方距離）  y_ref_m（cross の基準点の横位置）  turn: left|right  radius_m(6)
  t_ref: 基準点に着く時刻（省略時 cpa_s / t_stop / t_go / t_turn）   travel: same|opposite（start の進行向き）
  height_m: 高さ（既定 1.5）
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

import step11_v12_render as v12r  # noqa: E402
m9 = v12r.m9
m9.V91 = True

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
MOVING = {"car", "kick", "bike", "bike_bell", "backup_beep", "siren", "horn", "train"}


def make_dry(ev, seed):
    cls = ev["class"]
    v = ev.get("speed_kmh", 30) / 3.6
    rng = np.random.default_rng(seed)
    if cls == "car":
        return m9._make_dry({"class": "car_drive", "speed_mps": v,
                             "params": {"audio_seed": seed, "f0": float(ev.get("f0", 42.0))}})
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


# ---------------------------------------------------------------- 速度と経路（v3）
def speed_knots(ev):
    """時刻→速度[m/s] の折れ線の節点 [(t, v), ...]（t は単調増加）。"""
    if "speed_knots" in ev:
        return [(float(t), float(k) / 3.6) for t, k in ev["speed_knots"]]
    v = ev.get("speed_kmh", 30) / 3.6
    prof = ev.get("profile", "pass")
    if prof == "pass":
        return [(0.0, v), (m9.CLIP, v)]
    dec = float(ev.get("decel_mps2", 2.0))
    acc = float(ev.get("accel_mps2", 1.5))
    if prof == "stop":
        t_stop = float(ev.get("t_stop", 5.0))
        t_dec0 = t_stop - v / dec
        k = [(t_dec0 - 1.0, v), (t_dec0, v), (t_stop, 0.0)]
        t_go = ev.get("t_go")
        if t_go is not None and float(t_go) < m9.CLIP:
            v1 = float(ev.get("speed_kmh_after", ev.get("speed_kmh", 30))) / 3.6
            k += [(float(t_go), 0.0), (float(t_go) + v1 / acc, v1), (m9.CLIP + 5.0, v1)]
        else:
            k += [(m9.CLIP + 5.0, 0.0)]
        return k
    if prof == "start":
        t_go = float(ev.get("t_go", 3.0))
        return [(0.0, 0.0), (t_go, 0.0), (t_go + v / acc, v), (m9.CLIP + 5.0, v)]
    raise SystemExit(f"未対応profile: {prof}")


def t_ref_of(ev):
    if "t_ref" in ev:
        return float(ev["t_ref"])
    prof = ev.get("profile", "pass")
    if prof == "stop":
        return float(ev.get("t_stop", 5.0))
    if prof == "start":
        return float(ev.get("t_go", 3.0))
    if ev.get("geom") == "turn":
        return float(ev.get("t_turn", ev.get("cpa_s", 5.0)))
    return float(ev.get("cpa_s", 6.0))


def speed_at(ev, t):
    k = speed_knots(ev)
    return float(np.interp(t, [a for a, _ in k], [b for _, b in k]))


def arc_len(ev):
    """s(t): t=0 からの走行距離（細かい格子で数値積分）。返り値 (t_grid, s_grid)。"""
    k = speed_knots(ev)
    tg = np.arange(0.0, m9.CLIP + 0.5, 0.01)
    vg = np.interp(tg, [a for a, _ in k], [b for _, b in k])
    sg = np.concatenate([[0.0], np.cumsum(0.5 * (vg[1:] + vg[:-1]) * np.diff(tg))])
    return tg, sg


def route_points(ev, S):
    """geom=path の折れ線 [(x,y),...]（歩行者座標）。points 直書き、または route（地図の道路 id を並べる）。

    route の要素は "<way id>" か "<way id>r"（r = 逆向き）。map_roads（_osm_map_layout.py の *_roads.json）から
    折れ線をつなぎ、map_offset（歩行者が立つ位置＝地図座標）を引いて歩行者座標にする。
    """
    off = S.get("map_offset", [0.0, 0.0])
    if "points" in ev:
        P = [(float(x) - off[0], float(y) - off[1]) for x, y in ev["points"]]
    else:
        rj = json.loads((ROOT / S["map_roads"]).read_text(encoding="utf-8"))
        by_id = {str(r["id"]): r["points"] for r in rj["roads"]}
        P = []
        for tag in ev["route"]:
            tag = str(tag)
            rev = tag.endswith("r")
            pts = list(by_id[tag[:-1] if rev else tag])
            if rev:
                pts = pts[::-1]
            for x, y in pts:
                q = (float(x) - off[0], float(y) - off[1])
                if P and abs(P[-1][0] - q[0]) < 0.05 and abs(P[-1][1] - q[1]) < 0.05:
                    continue
                P.append(q)
    assert len(P) >= 2, "path には 2 点以上要る"
    return P


def path_xy(P, s_arr):
    """折れ線 P 上の弧長 s の位置（両端の外は端の線分を延長）。"""
    P = np.asarray(P, float)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    S_ = np.concatenate([[0.0], np.cumsum(seg)])
    xs = np.interp(s_arr, S_, P[:, 0]); ys = np.interp(s_arr, S_, P[:, 1])
    u0 = (P[1] - P[0]) / max(seg[0], 1e-6); u1 = (P[-1] - P[-2]) / max(seg[-1], 1e-6)
    lo = s_arr < 0; hi = s_arr > S_[-1]
    xs[lo] = P[0, 0] + s_arr[lo] * u0[0]; ys[lo] = P[0, 1] + s_arr[lo] * u0[1]
    xs[hi] = P[-1, 0] + (s_arr[hi] - S_[-1]) * u1[0]; ys[hi] = P[-1, 1] + (s_arr[hi] - S_[-1]) * u1[1]
    return xs, ys, S_


def build_path(ev, mic_x, shift_m=0.0, S=None):
    """(M,4) の折れ線軌道と、layout 用の行を返す。u = 基準点からの走行距離（負=手前）。"""
    cls = ev["class"]
    z = float(ev.get("height_m", 1.5))
    lat = ev.get("lateral_m", 2.0) * (1.0 if ev.get("side", "left") == "left" else -1.0)
    if cls == "crossing":
        x = mic_x(5.0) + ev.get("x_m", 3.0)
        return np.array([[0.0, x, lat, 2.5], [m9.CLIP, x, lat, 2.5]]), [("static", x, lat, "crossing", 0.0)]
    geom = ev.get("geom", "straight")
    prof = ev.get("profile", "pass")
    simple = geom == "straight" and prof == "pass" and "speed_knots" not in ev
    t_ref = t_ref_of(ev)
    if geom == "path" and "t_ref" not in ev:
        t_ref = float(ev.get("cpa_s", t_ref))
    if simple:
        # v2 と同一（2点の等速直線）
        v = ev.get("speed_kmh", 30) / 3.6
        d = -1.0 if ev.get("from", "front") == "front" else 1.0
        x0 = mic_x(t_ref) - d * v * t_ref - d * shift_m + d * float(ev.get("ahead_m", 0.0))
        wp = np.array([[0.0, x0, lat, z], [m9.CLIP, x0 + d * v * m9.CLIP, lat, z]])
        return wp, [("lane", lat, d, "train" if cls == "train" else "car", 0.0)]
    tg, sg = arc_len(ev)
    s_ref = float(np.interp(t_ref, tg, sg))
    ts = np.arange(0.0, m9.CLIP + 1e-9, 0.1)
    us = np.interp(ts, tg, sg) - s_ref - shift_m
    ahead = float(ev.get("ahead_m", 0.0))
    rows = []
    if geom == "straight":
        if prof == "start":
            d = 1.0 if ev.get("travel", "same") == "same" else -1.0
        else:
            d = -1.0 if ev.get("from", "front") == "front" else 1.0
        x_ref = mic_x(t_ref) + ahead
        xs = x_ref + d * us
        ys = np.full_like(xs, lat)
        rows.append(("lane", lat, d, "train" if cls == "train" else "car", 0.0))
    elif geom == "cross":
        # 歩行者の進路（x軸）を横切る道路: x = x_ref で固定、y 方向に走る。from=right → y が負から正へ
        dy = 1.0 if ev.get("from", "right") == "right" else -1.0
        x_ref = mic_x(t_ref) + ahead
        y_ref = float(ev.get("y_ref_m", 0.0))
        xs = np.full_like(us, x_ref)
        ys = y_ref + dy * us
        rows.append(("xlane", x_ref, dy, "train" if cls == "train" else "car", z))
    elif geom == "path":
        # 実地図の道路など任意の折れ線。基準点 = t_ref にマイクへ最も近づく折れ線上の点（s_ref_m で上書き可）
        P = route_points(ev, S or {})
        total_len = float(np.sum(np.linalg.norm(np.diff(np.asarray(P, float), axis=0), axis=1)))
        dense = np.linspace(-50.0, total_len + 50.0, 4000)
        px, py, _ = path_xy(P, dense)
        mx = mic_x(t_ref)
        s_ref = float(ev["s_ref_m"]) if "s_ref_m" in ev else float(dense[np.argmin((px - mx) ** 2 + py ** 2)])
        xs, ys, _ = path_xy(P, us + s_ref)
        if not (S or {}).get("map_layout"):
            for (x1, y1), (x2, y2) in zip(P[:-1], P[1:]):
                rows.append(("road", x1, y1, x2, y2, float(ev.get("road_width_m", 5.5))))
    elif geom == "turn":
        # 車線 y=lat を d 向きに走り、基準点で半径 R の 90° の弧を曲がって直進
        d = -1.0 if ev.get("from", "front") == "front" else 1.0
        sy = 1.0 if ev.get("turn", "left") == "left" else -1.0     # +y = 歩行者の左
        R = float(ev.get("radius_m", 6.0))
        x_ref = mic_x(t_ref) + ahead
        q = R * np.pi / 2.0
        xs = np.empty_like(us)
        ys = np.empty_like(us)
        pre = us < 0
        xs[pre] = x_ref + d * us[pre]
        ys[pre] = lat
        arc = (us >= 0) & (us < q)
        phi = us[arc] / R
        xs[arc] = x_ref + d * R * np.sin(phi)
        ys[arc] = lat + sy * R - sy * R * np.cos(phi)
        post = us >= q
        xs[post] = x_ref + d * R
        ys[post] = lat + sy * R + sy * (us[post] - q)
        rows.append(("lane", lat, d, "car", 0.0))
        rows.append(("xlane", x_ref + d * R, sy, "car", 0.0))
    else:
        raise SystemExit(f"未対応geom: {geom}")
    wp = np.stack([ts, xs, ys, np.full_like(xs, z)], axis=1)
    return wp, rows


def speed_envelope(ev, n):
    """放射時刻の格子に対する音量包絡（速度に応じたアイドル減衰・発進前の無音）。"""
    if ev["class"] not in MOVING or ev.get("class") == "train":
        return None
    if ev.get("profile", "pass") == "pass" and "speed_knots" not in ev:
        return None
    t = np.arange(n) / m9.FS_SIM
    v_nom = max(ev.get("speed_kmh", 30) / 3.6, 0.5)
    k = speed_knots(ev)
    v = np.interp(t, [a for a, _ in k], [b for _, b in k])
    idle_db = float(ev.get("idle_db", -8.0))
    g_db = idle_db * (1.0 - np.clip(v / v_nom, 0.0, 1.0))
    env = 10.0 ** (g_db / 20.0)
    if ev.get("profile") == "start" and ev.get("engine_off", True):
        t_go = float(ev.get("t_go", 3.0))
        env *= np.clip((t - (t_go - 0.3)) / 0.3, 0.0, 1.0)     # 発進の 0.3 秒前にエンジン始動
    return env


def expand_events(S):
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

    stems, gt, layout_rows = [], [], []
    for i, ev in enumerate(events):
        wp, rows = build_path(ev, mic_x, ev.get("_shift", 0.0), S)
        for r in rows:
            if r not in layout_rows:
                layout_rows.append(r)
        t_on = float(ev.get("t_on", 0.0))
        t_off = float(ev.get("t_off", m9.CLIP))
        if ev.get("profile") == "start" and ev.get("engine_off", True) and "t_on" not in ev:
            t_on = max(0.0, float(ev.get("t_go", 3.0)) - 0.3)       # 停車中（エンジン停止）はラベル無し
        dry = make_dry(ev, seed0 * 101 + i * 17 + 3)
        env = speed_envelope(ev, len(dry))
        if env is not None:
            dry = dry * env
        dry = m9._window(dry, t_on, t_off)
        a0, a1 = int(t_on * m9.FS_SIM), int(t_off * m9.FS_SIM)
        l1m = float(ev.get("level_db", L1M_DEFAULT[ev["class"]]))
        ref = dry[a0:a1]
        if env is not None:      # 音量の基準は「走行中」の区間で取る（停止中だけで較正しない）
            sel = env[a0:a1] > 0.9
            if sel.sum() > m9.FS_SIM * 0.5:
                ref = dry[a0:a1][sel]
        g = m9.gain_for_spl_a(ref, m9.FS_SIM, l1m)
        _, stem_wr = m9._render_stem(dry * g, wp, mic, c)
        stems.append(stem_wr)
        tk = np.arange(100) * 0.1
        az, _el, _a, _b = apparent_azel_deg(tk, wp, mic, c)
        dist = m9._dist_series(wp, mic, tk)
        act = (tk >= t_on) & (tk < t_off)
        cls_name = "crossing" if ev["class"] == "train" else ev["class"]
        gt.append((CLS_IDX[cls_name], az, dist, act, ev, i))
        extra = ""
        if ev.get("profile", "pass") != "pass" or "speed_knots" in ev:
            extra = f" 速度 {speed_at(ev, 0.0)*3.6:.0f}→{speed_at(ev, m9.CLIP)*3.6:.0f}km/h"
        geom_tag = "/" + ev["geom"] if ev.get("geom") else ""
        print(f"  event{i}: {ev['class']}{geom_tag} 最接近{dist.min():.1f}m@{tk[dist.argmin()]:.1f}s"
              f" l1m={l1m:.1f}dB{extra}" + ("" if ev.get("_label", True) else " (音のみ・ラベル無し)"))

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

    OUT.mkdir(parents=True, exist_ok=True)
    st = np.stack([mix[0] + 0.5 * mix[1], mix[0] - 0.5 * mix[1]], axis=1)
    st = st / max(np.max(np.abs(st)), 1e-9)
    st = np.sign(st) * np.abs(st) ** 0.5 * 0.7
    base = OUT / f"custom_{name}"
    sf.write(f"{base}.wav", st.astype(np.float32), m9.FS_OUT, subtype="PCM_16")
    with open(f"{base}_scene.csv", "w", encoding="utf-8", newline="\n") as f:
        f.write("t_s,obj,class,az_deg,dist_m,vis\n")        # vis: 1=鳴っている, 0=いるが無音（薄く描く。消さない）
        for ci, az, dist, act, ev, oi in gt:
            cname = "train" if ev["class"] == "train" else ev["class"]
            for k in range(100):
                if np.isfinite(az[k]) and np.isfinite(dist[k]):
                    f.write(f"{k/10.0:.1f},{oi},{cname},{az[k]:.1f},{dist[k]:.2f},{1 if act[k] else 0}\n")
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
        for r in layout_rows:
            kind = r[0]
            if kind == "static":
                f.write(f"static,{r[1]},{r[2]},{r[3]},\n")
            elif kind == "lane":
                f.write(f"lane,{r[1]},{r[2]},{r[3]},\n")
            elif kind == "road":
                f.write(f"road,{r[1]:.1f},{r[2]:.1f},{r[3]:.1f},{r[4]:.1f},{r[5]:.1f},car,\n")
            else:
                f.write(f"xlane,{r[1]:.2f},{r[2]},{r[3]},{r[4]}\n")
        if S.get("map_layout"):
            # 実地図（_osm_map_layout.py の出力）を歩行者座標に平行移動して丸ごと足す
            off = S.get("map_offset", [0.0, 0.0])
            for line in (ROOT / S["map_layout"]).read_text(encoding="utf-8").splitlines():
                q = line.split(",")
                if len(q) < 2 or q[0] == "type":
                    continue
                kind = q[0]
                try:
                    if kind in ("road", "water", "rail"):
                        q[1] = f"{float(q[1]) - off[0]:.1f}"; q[2] = f"{float(q[2]) - off[1]:.1f}"
                        q[3] = f"{float(q[3]) - off[0]:.1f}"; q[4] = f"{float(q[4]) - off[1]:.1f}"
                    elif kind in ("bldg", "poi"):
                        q[1] = f"{float(q[1]) - off[0]:.1f}"; q[2] = f"{float(q[2]) - off[1]:.1f}"
                except ValueError:
                    continue
                f.write(",".join(q) + "\n")
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
        for a in sys.argv[1:]:
            print(f"== {Path(a).name}")
            run(Path(a))
    print("->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
