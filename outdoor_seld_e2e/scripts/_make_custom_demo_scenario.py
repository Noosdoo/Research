# -*- coding: utf-8 -*-
"""Joy-conデモ用シナリオ自作ツール（2026-09-02、本人「自分でシチュエーション作ってみたい」）。

JSONで「どの音が・どっちから・何秒に最接近するか」を書くと、
本物の合成器（v12チェーン）で10秒の音声を作り、v4.2＋holdの通知規則で振動キューを出す。

⚠️ 通知は**GT系列に規則を当てたオラクル動作**（知覚モデルは通していない）。
   fold31のデモ5本は本物のモデル出力なので、混同しないこと（cues.csvに明記される）。
⚠️ 音量の既定値はデモ用の概算。学習・評価には一切使わない。
✅ 移動音源は t_on=0 で最初から鳴りながら接近する（⑫の「急オンセット」を排した形）。

使い方:
  python scripts/_make_custom_demo_scenario.py <scenario.json>
  → out/joycon_demo/custom_<name>.wav と custom_<name>_cues.csv
    （2つを Unity の StreamingAssets/joycon_demo/ にドラッグ→▶し直すと一覧に出る）

JSONの書き方（例は out/joycon_demo/scenarios/ にある）:
{
  "name": "taikou",          // 出力ファイル名になる
  "noise_dba": 45,           // 背景の都市騒音レベル（40=静か〜65=うるさい）
  "seed": 7,                 // 音色の乱数（変えると同じ配置でも音が変わる）
  "events": [
    {"class": "car",   "from": "front",  "side": "right", "lateral_m": 1.0,
     "speed_kmh": 30, "cpa_s": 6.0},
    {"class": "siren", "from": "behind", "side": "left",  "lateral_m": 5.0,
     "speed_kmh": 50, "cpa_s": 13.0}    // cpa_sをクリップ長(10s)より後にすると
  ]                                     // 「近づき続けたまま終わる」＝接近の緊張感だけ残る
}

classごとの必須/任意キー:
  car / kick / bike / bike_bell / backup_beep（移動音源）:
      from(front|behind) side(left|right) lateral_m speed_kmh cpa_s [level_db]
  siren / horn（移動音源・同上）: [siren_type: peepo|wail|fire] [t_on/t_off(hornの短鳴らし用)]
  crossing（静止音源=踏切警報器）: side lateral_m x_m（道路方向の位置）
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

from outdoor_seld.geometry import apparent_azel_deg, sound_speed  # noqa: E402
from outdoor_seld.kickboard import make_kickboard  # noqa: E402
from outdoor_seld.motorcycle import make_motorcycle  # noqa: E402


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


V42 = _load("nv42", "step12_notify_v42_bearing.py")
H = _load("nhold", "step12_notify_v9b_hold.py")
v4 = sys.modules["nv42"].v4     # V42が読み込んだv4を共有

ADOPTED = V42.Cfg(route_c=True, adot_th=0.10, dn=15.0, link_pred=True,
                  cpa_strong=1.3, cpa_mid=1.6)
CLS_IDX = {"siren": 0, "horn": 1, "backup_beep": 2, "bike_bell": 3,
           "car": 4, "crossing": 5, "kick": 6, "bike": 7}
DIST_CLASSES = {4, 6, 7}
# デモ用の概算音量[dB(A)@1m]（学習規約とは無関係の当て値）
L1M_DEFAULT = {"car": 74, "siren": 112, "horn": 104, "backup_beep": 90,
               "bike_bell": 85, "crossing": 92, "kick": 60, "bike": 96}
MIC = np.array([0.0, 0.0, 1.5])


def make_dry(ev, seed):
    cls = ev["class"]
    v = ev.get("speed_kmh", 30) / 3.6
    rng = np.random.default_rng(seed)
    if cls == "car":
        src = {"class": "car_drive", "speed_mps": v,
               "params": {"audio_seed": seed, "f0": 42.0}}
        return m9._make_dry(src)
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
        return make_motorcycle(m9.CLIP, m9.FS_SIM, rng,
                               engine_class="motorcycle", speed_mps=max(v, 5.0))
    raise SystemExit(f"未対応class: {cls}")


def mic_setup(S):
    """トップレベル "motion": "static"(既定) | "walk"。歩行は+x方向へ直進（回転なし）。

    返り値: (レンダラ/幾何に渡すマイク, 時刻tでのマイクx座標を返す関数)
    """
    if S.get("motion", "static") != "walk":
        return MIC, (lambda t: 0.0)
    v = float(S.get("walk_speed_kmh", 4.3)) / 3.6
    x0 = -v * 5.0                    # 中央対称（既存valのwalkと同じ規約）
    wp = np.array([[0.0, x0, 0.0, 1.5], [m9.CLIP, x0 + v * m9.CLIP, 0.0, 1.5]])
    return wp, (lambda t: x0 + v * t)


def waypoints(ev, mic_x):
    y = ev.get("lateral_m", 2.0) * (1.0 if ev.get("side", "left") == "left" else -1.0)
    if ev["class"] == "crossing":
        x = mic_x(5.0) + ev.get("x_m", 3.0)
        return np.array([[0.0, x, y, 2.5], [m9.CLIP, x, y, 2.5]])
    v = ev.get("speed_kmh", 30) / 3.6
    d = -1.0 if ev.get("from", "front") == "front" else 1.0
    cpa = ev.get("cpa_s", 6.0)
    x0 = mic_x(cpa) - d * v * cpa    # cpa_s の瞬間に歩行者の真横へ来るよう配置
    return np.array([[0.0, x0, y, 1.5], [m9.CLIP, x0 + d * v * m9.CLIP, y, 1.5]])


def main() -> int:
    spec_path = Path(sys.argv[1])
    S = json.loads(spec_path.read_text(encoding="utf-8"))
    name = S.get("name", spec_path.stem)
    seed0 = int(S.get("seed", 1))
    c = m9.sound_speed(m9.TEMP_C)
    n24 = int(m9.CLIP * m9.FS_OUT)
    mic, mic_x = mic_setup(S)

    stems, gt = [], []
    for i, ev in enumerate(S["events"]):
        wp = waypoints(ev, mic_x)
        t_on = float(ev.get("t_on", 0.0))
        t_off = float(ev.get("t_off", m9.CLIP))
        dry = m9._window(make_dry(ev, seed0 * 101 + i * 17 + 3), t_on, t_off)
        a0, a1 = int(t_on * m9.FS_SIM), int(t_off * m9.FS_SIM)
        l1m = float(ev.get("level_db", L1M_DEFAULT[ev["class"]]))
        g = m9.gain_for_spl_a(dry[a0:a1], m9.FS_SIM, l1m)
        _, stem_wr = m9._render_stem(dry * g, wp, mic, c)
        stems.append(stem_wr)
        # GT系列（0.1秒刻み・フレーム中心）— 通知はこの系列へのオラクル
        tk = np.arange(100) * 0.1
        az, _el, _a, _b = apparent_azel_deg(tk, wp, mic, c)
        dist = m9._dist_series(wp, mic, tk)
        act = (tk >= t_on) & (tk < t_off)
        gt.append((CLS_IDX[ev["class"]], az, dist, act, ev))
        print(f"  event{i}: {ev['class']} 最接近{dist.min():.1f}m@{tk[dist.argmin()]:.1f}s "
              f"l1m={l1m}dB")

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

    # ---- 通知（オラクル: GT系列に本物の規則を当てる）----
    frames_dist, frames_warn = {}, {}
    for ci, az, dist, act, ev in gt:
        for k in range(100):
            if not act[k]:
                continue
            # 音の伝播遅延で「まだ届いていない」フレームは方位がNaNになる。
            # 現実でも聞こえていないのだから未検出として扱う
            if not (np.isfinite(az[k]) and np.isfinite(dist[k])):
                continue
            if ci in DIST_CLASSES:
                frames_dist.setdefault(k, []).append((ci, float(az[k]), float(dist[k])))
            else:
                frames_warn.setdefault(k, {})[ci] = (float(az[k]), 0.0)
    cues = []
    res = V42.run_rule2({"x": frames_dist}, ADOPTED).get("x", {})
    for ci, eps in res.items():
        for j, azv, tier, d in eps:
            cues.append(((j + 1) / 10.0, "L" if azv > 0 else "R", tier,
                         [k for k, v in CLS_IDX.items() if v == ci][0], azv))
    warn_clip = {k: [(ci, a, e) for ci, (a, e) in v.items()]
                 for k, v in frames_warn.items()}
    for k, ci, azv in H.warn_fires(warn_clip, hold=True):
        cues.append(((k + 1) / 10.0, "L" if azv > 0 else "R", "警告",
                     [kk for kk, v in CLS_IDX.items() if v == ci][0], azv))
    cues.sort()

    # ---- 書き出し（デモ形式: ステレオ+べき圧縮）----
    outdir = ROOT / "out/joycon_demo"
    outdir.mkdir(parents=True, exist_ok=True)
    L = mix[0] + 0.5 * mix[1]
    R = mix[0] - 0.5 * mix[1]
    st = np.stack([L, R], axis=1)
    st = st / max(np.max(np.abs(st)), 1e-9)
    st = np.sign(st) * np.abs(st) ** 0.5 * 0.7
    sf.write(outdir / f"custom_{name}.wav", st.astype(np.float32), m9.FS_OUT,
             subtype="PCM_16")
    # 可視化用: 全物体の毎フレーム位置（歩行者中心の方位・距離）
    with open(outdir / f"custom_{name}_scene.csv", "w", encoding="utf-8",
              newline="\n") as f:
        f.write("t_s,obj,class,az_deg,dist_m\n")
        for oi, (ci, az, dist, act, ev) in enumerate(gt):
            cname = [k for k, v in CLS_IDX.items() if v == ci][0]
            for k in range(100):
                if act[k] and np.isfinite(az[k]) and np.isfinite(dist[k]):
                    f.write(f"{k/10.0:.1f},{oi},{cname},{az[k]:.1f},{dist[k]:.2f}\n")
    with open(outdir / f"custom_{name}_cues.csv", "w", encoding="utf-8",
              newline="\n") as f:
        f.write("t_s,side,tier,class,az_deg\n")
        for t, side, tier, cls, azv in cues:
            f.write(f"{t:.1f},{side},{tier},{cls},{azv:.0f}\n")
        f.write("# オラクル動作（GT系列+v4.2/hold）。モデル出力ではない\n")
    print(f"\ncustom_{name}: キュー{len(cues)}件")
    for t, side, tier, cls, azv in cues:
        print(f"  {t:.1f}s {side} {tier} ({cls}, az={azv:.0f}°)")
    print(f"-> {outdir}\\custom_{name}.wav / _cues.csv")
    print("Unityの Assets/StreamingAssets/joycon_demo/ に2つをドラッグ → ▶し直し")
    return 0


if __name__ == "__main__":
    sys.exit(main())
