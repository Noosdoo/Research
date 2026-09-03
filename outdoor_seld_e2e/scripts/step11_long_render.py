# -*- coding: utf-8 -*-
"""長尺セット v1（60 秒）の描画（2026-09-03）。step10_long_plan.py の場面仕様 → 4ch FOA flac ＋ GT ラベル ＋ scene.json。

幾何・速度・経路はデモ v3 ツール（_make_custom_demo_scenario_v3.py: 直進・左折・徐行）を借り、
音量（1 m 相当レベル）と暗騒音は学習データと同じ規約（step11_v9_render の _draw_level / NOISE_DBA。計画表で引いた値）。
ラベルの可聴ゲート: 学習データは実信号のマスクで決めるが、ここでは「受聴レベル（1m相当 − 20log10 距離）≥ 暗騒音」の
距離近似（AUDIBLE_SNR_DB=0 と同じ意味）で決める。評価専用セットなので近似で足りる（設計書に明記）。

出力: out/dataset_outdoor_long_v1/{foa/<clip>.flac (4ch 24kHz 60s), metadata_dist/<clip>.csv (frame,class,track,az,el,dist),
      work/<clip>/scene.json, listen/<clip>.wav (試聴用ステレオ・--listen 時)}

使い方:
  python scripts/step11_long_render.py --proto 6 --listen     # 各交通量層から 2 本ずつ（試聴用）
  python scripts/step11_long_render.py --rows 0-49            # シャード（サーバ）
  python scripts/step11_long_render.py --list
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


V3 = _load("demo_v3", "_make_custom_demo_scenario_v3.py")
m9 = V3.m9
from outdoor_seld.geometry import apparent_azel_deg  # noqa: E402

OUT = ROOT / "out/dataset_outdoor_long_v1"
PLAN = OUT / "plan"
CLIP_S = 60.0
FRAMES = int(CLIP_S * 10)
MAX_LABEL_DIST = 80.0          # これより遠い車はラベルにしない（可聴でも規則の対象外）
NTRACK_SLOTS = 3               # mACCDOA の同クラス系列数に合わせる（超えた分は 3 以降）


def load_plan() -> list:
    with open(PLAN / "assignment_long_v1.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def assign_tracks(actives: list) -> list:
    """同時に鳴っている同クラスの車に別の track 番号を割り当てる（区間の貪欲法）。actives: [(cls, frames_bool)]"""
    tracks = []
    for i, (cls, act) in enumerate(actives):
        used = set()
        for j in range(i):
            if actives[j][0] == cls and np.any(actives[j][1] & act):
                used.add(tracks[j])
        t = 0
        while t in used:
            t += 1
        tracks.append(t)
    return tracks


def render(spec: dict, listen: bool = False) -> dict:
    t_start = time.perf_counter()
    m9.CLIP = float(spec.get("clip_s", CLIP_S))
    V3.MIC = np.array([0.0, 0.0, 1.5])
    name = spec["name"]
    seed0 = int(spec["seed"])
    c = m9.sound_speed(m9.TEMP_C)
    n24 = int(m9.CLIP * m9.FS_OUT)
    S = dict(spec)
    mic, mic_x = V3.mic_setup(S)
    events = V3.expand_events(S)
    tk = np.arange(FRAMES) * 0.1
    noise_dba = float(spec["noise_dba"])

    gts, scene_srcs = [], []
    rng_n = np.random.default_rng(seed0 * 7919 + 13)
    mix = m9.diffuse_foa_noise(n24, m9.FS_OUT, rng_n)          # 暗騒音から始めて音源を順に足す（メモリ節約: ステムを溜めない）
    mix *= m9.gain_for_spl_a(mix[0], m9.FS_OUT, noise_dba)
    for i, ev in enumerate(events):
        wp, _rows = V3.build_path(ev, mic_x, ev.get("_shift", 0.0), S)
        t_on = float(ev.get("t_on", 0.0)); t_off = float(ev.get("t_off", m9.CLIP))
        dry = V3.make_dry(ev, seed0 * 101 + i * 17 + 3)
        env = V3.speed_envelope(ev, len(dry))
        if env is not None:
            dry = dry * env
        dry = m9._window(dry, t_on, t_off)
        a0, a1 = int(t_on * m9.FS_SIM), int(t_off * m9.FS_SIM)
        l1m = float(ev.get("level_db", V3.L1M_DEFAULT[ev["class"]]))
        ref = dry[a0:a1]
        if env is not None:
            sel = env[a0:a1] > 0.9
            if sel.sum() > m9.FS_SIM * 0.5:
                ref = dry[a0:a1][sel]
        g = m9.gain_for_spl_a(ref, m9.FS_SIM, l1m)
        _, stem = m9._render_stem(dry * g, wp, mic, c)
        mix += stem
        del stem, dry, ref
        az, _el, _a, _b = apparent_azel_deg(tk, wp, mic, c)
        dist = m9._dist_series(wp, mic, tk)
        recv = l1m - 20.0 * np.log10(np.maximum(dist, 1.0))
        cls_name = "crossing" if ev["class"] == "train" else ev["class"]
        audible = (recv >= noise_dba) & (dist <= MAX_LABEL_DIST)
        act = (tk >= t_on) & (tk < t_off) & np.isfinite(az) & np.isfinite(dist) & audible & ev.get("_label", True)
        gts.append((V3.CLS_IDX[cls_name], az, dist, act))
        scene_srcs.append({"class": ev["class"], "wp": np.asarray(wp, float).tolist() if len(wp) <= 4 else np.asarray(wp, float)[::10].tolist(),
                           "t_on": t_on, "t_off": t_off, "l1m_db": l1m, "min_dist_m": round(float(np.nanmin(dist)), 2),
                           "t_min_dist_s": round(float(tk[int(np.nanargmin(dist))]), 1), "geom": ev.get("geom", "straight")})
    peak = float(np.max(np.abs(mix)))
    scaled = 1.0
    if peak >= m9.PEAK_MAX:
        scaled = m9.PEAK_MAX * 0.9 / peak
        mix *= scaled
    tracks = assign_tracks([(ci, act) for ci, _az, _d, act in gts])

    (OUT / "foa").mkdir(parents=True, exist_ok=True)
    (OUT / "metadata_dist").mkdir(parents=True, exist_ok=True)
    (OUT / "work" / name).mkdir(parents=True, exist_ok=True)
    sf.write(OUT / "foa" / f"{name}.flac", mix.T.astype(np.float32), m9.FS_OUT, subtype="PCM_24")
    n_lab = 0
    with open(OUT / "metadata_dist" / f"{name}.csv", "w", encoding="utf-8", newline="\n") as f:
        for (ci, az, dist, act), tr in zip(gts, tracks):
            for k in range(FRAMES):
                if act[k]:
                    f.write(f"{k},{ci},{tr},{az[k]:.1f},0,{dist[k]:.2f}\n")
                    n_lab += 1
    (OUT / "work" / name / "scene.json").write_text(json.dumps(
        {"spec": spec, "mic": {"motion": spec["motion"], "walk_speed_mps": float(spec.get("walk_speed_kmh", 4.3)) / 3.6},
         "sources": scene_srcs, "tracks": tracks, "peak_scale": scaled, "noise_dba": noise_dba}, ensure_ascii=False, indent=1), encoding="utf-8")
    if listen:
        (OUT / "listen").mkdir(parents=True, exist_ok=True)
        st = np.stack([mix[0] + 0.5 * mix[2], mix[0] - 0.5 * mix[2]], axis=1)
        st = st * (0.9 / max(float(np.max(np.abs(st))), 1e-9))
        sf.write(OUT / "listen" / f"{name}.wav", st.astype(np.float32), m9.FS_OUT, subtype="PCM_16")
    info = {"clip": name, "n_events": len(events), "n_label_frames": n_lab, "peak_scale": scaled,
            "sec": round(time.perf_counter() - t_start, 1),
            "close": [(s["class"], s["min_dist_m"], s["t_min_dist_s"]) for s in scene_srcs if s["min_dist_m"] <= 1.6]}
    print(f"  {name}: 音源 {len(events)} / ラベル {n_lab} フレーム / 至近 {info['close']} / {info['sec']} s"
          + (f" / ピーク調整 ×{scaled:.2f}" if scaled < 1 else ""), flush=True)
    return info


def main() -> int:
    rows = load_plan()
    if "--list" in sys.argv:
        print(f"total {len(rows)} -> {OUT}")
        return 0
    listen = "--listen" in sys.argv
    if "--proto" in sys.argv:
        n = int(sys.argv[sys.argv.index("--proto") + 1])
        picked, seen = [], {}
        for r in rows:
            if r["split"] != "fold40":
                continue
            key = (r["stratum"], r["scene"].split("_")[0])
            if seen.get(key, 0) < max(1, n // 6):
                picked.append(r); seen[key] = seen.get(key, 0) + 1
            if len(picked) >= n:
                break
        part = picked
    else:
        lo, hi = 0, len(rows) - 1
        if "--rows" in sys.argv:
            a, b = sys.argv[sys.argv.index("--rows") + 1].split("-")
            lo, hi = int(a), int(b)
        part = rows[lo:hi + 1]
    t0 = time.time()
    done = skip = 0
    for r in part:
        if (OUT / "foa" / f"{r['clip_id']}.flac").exists() and not listen:
            skip += 1
            continue
        spec = json.loads((PLAN / "specs" / f"{r['clip_id']}.json").read_text(encoding="utf-8"))
        render(spec, listen=listen)
        done += 1
    print(f"FINISHED done={done} skip={skip} {time.time()-t0:.0f}s -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
