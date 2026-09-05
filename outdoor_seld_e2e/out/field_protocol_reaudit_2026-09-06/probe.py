"""Counterexamples for the 2026-09-06 field protocol re-audit.
All inputs are synthetic; production code and research datasets are read only.
"""
from pathlib import Path
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import subprocess
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import soundfile as sf

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DATA = OUT / "fixtures"
DATA.mkdir(exist_ok=True)
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


s19 = load("reaudit_s19", "scripts/step19_realsmoke_convert.py")
s19d = load("reaudit_s19d", "scripts/step19d_field_csv_to_ann.py")
cut = load("reaudit_cut", "scripts/step19b_realsmoke_cut.py")
score = load("reaudit_v3", "scripts/step20_realsmoke_score_v3.py")
cfg = score.V43.Cfg43(**json.loads((ROOT / "out/notify_v43_sweep/winner.json").read_text()))
result = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}


def write_csv(path, rows, cols=None):
    if cols is None:
        cols = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def cli(tag, script, args):
    p = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / script), *map(str, args)],
                       cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf-8")
    (OUT / f"{tag}.log").write_text(p.stdout + p.stderr, encoding="utf-8")
    return {"exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}


sessions = [{"session_id": "S1", "区分": "A", "LAeq_dB": "52.3", "暗騒音区間_秒": "0-60"},
            {"session_id": "S2", "区分": "A", "LAeq_dB": "52.3", "暗騒音区間_秒": "0-60"}]
field = {"session_id": "S1", "take_id": "1", "event_id": "1", "class": "car_drive",
         "象限": "L", "ラップ秒": "10", "n_car": "1", "横距離m": "2.5", "状態": "静止", "pair_id": ""}

# The documented original-name override is not the key used by the cutter.
custom, warnings = s19d.convert(sessions, [{**field, "原本": "ZOOM0001.wav"}], 6, 0, DATA)
write_csv(DATA / "custom_ann.csv", custom)
fs = 24000
t = np.arange(fs * 25) / fs
wave = np.column_stack([0.01 * np.sin(2*np.pi*1000*t), np.zeros((len(t), 3))])
sf.write(DATA / "ZOOM0001.wav", wave, fs, subtype="PCM_24")
p = cli("original_name", "step19b_realsmoke_cut.py", ["--in", DATA / "ZOOM0001.wav",
    "--ann", DATA / "custom_ann.csv", "--out", DATA / "custom_clips", "--ann-out", DATA / "custom_cut.csv",
    "--gain-db", 0, "--calibration-id", "S1_calib"])
result["original_name_override"] = {"source_annotation": custom, "conversion_warnings": warnings,
    "cut_exit": p["exit_code"], "cut_rows": s19d.read_csv(DATA / "custom_cut.csv"), "cut_output": p["stdout"]}

# Per-session calibration IDs are overwritten by one CLI ID in a directory batch.
batch = DATA / "batch"
batch.mkdir(exist_ok=True)
rows, _ = s19d.convert(sessions, [field, {**field, "session_id": "S2"}], 6, 0, batch)
for r in rows:
    sf.write(batch / r["orig_file"], wave, fs, subtype="PCM_24")
write_csv(DATA / "batch_ann.csv", rows)
p = cli("calibration_batch", "step19b_realsmoke_cut.py", ["--in", batch, "--ann", DATA / "batch_ann.csv",
    "--out", DATA / "batch_clips", "--ann-out", DATA / "batch_cut.csv", "--gain-db", 0, "--calibration-id", "S1_calib"])
result["calibration_batch"] = {"exit_code": p["exit_code"],
    "before": [{k: r[k] for k in ("session_id", "calibration_id")} for r in rows],
    "after": [{k: r[k] for k in ("session_id", "calibration_id", "gain_db")} for r in s19d.read_csv(DATA / "batch_cut.csv")]}

# A 60-second LAeq cannot in general calibrate the inner 50 seconds.
tc = np.arange(fs * 60) / fs
amp = np.where((tc < 5) | (tc >= 55), 0.02, 0.01)
wc = amp * np.sin(2*np.pi*1000*tc)
calpath = DATA / "calibration_60s.wav"
sf.write(calpath, np.column_stack([wc, np.zeros((len(wc), 3))]), fs, subtype="FLOAT")
meter = s19.spl_a(wc, fs)
result["calibration_window"] = {"meter_interval_s": [0, 60], "meter_dBA": meter,
    "matching_interval_gain_dB": s19.calib_gain_db(calpath, meter, (0, 60)),
    "documented_5_55_gain_dB": s19.calib_gain_db(calpath, meter, (5, 55)),
    "scope": "constructed nonstationary calibration signal, not a measured hardware error"}

# Purpose and explicit calibration change information are dropped by the converter.
tuning, warns = s19d.convert([{**sessions[0], "用途": "調整用"}], [field], 6, 0, DATA)
changed_cal, _ = s19d.convert(sessions, [{**field, "calibration_id": "S1_after_gain_change"}], 6, 0, DATA)
result["tuning_and_calibration_metadata"] = {"tuning_rows_written_to_main_ann": len(tuning),
    "purpose_retained": "用途" in tuning[0], "warnings": warns,
    "explicit_calibration_id_after_convert": changed_cal[0]["calibration_id"]}

# A warning notification 0.3 s after onset is reported as a positive 2.7 s lead.
warn_source, _ = s19d.convert(sessions, [{**field, "class": "siren", "象限": "R", "ラップ秒": "10", "横距離m": ""}], 6, 0, DATA)
warn_row = cut.rebase_rows(warn_source, 5, 10, "S1_take01", "warning_clip", target_event="1",
                          orig_duration_s=25, calibration_id="S1_calib")[0]
pred = {"warning_clip": {k: [(0, -90.0, 0.0, float("nan"))] for k in range(50, 81)}}
ev, _, _ = score.evaluate([warn_row], pred, cfg, (2.5, 1.5), 7.5, False)
fires = score.fires_of(pred["warning_clip"], cfg, 101)
actual_delay = fires[0][0] - float(warn_row["t_start"])
result["warning_latency"] = {"onset_s": float(warn_row["t_start"]), "pseudo_cpa_s": float(warn_row["t_cpa"]),
    "first_fire_s": fires[0][0], "onset_to_fire_delay_s": actual_delay, "reported_event": ev[0]}

# Onset direction is R; later correct predictions are B and change the window mean.
moving = {"warning_clip": {k: [(0, -90.0 if k < 56 else 180.0, 0.0, float("nan"))] for k in range(50, 81)}}
mev, _, _ = score.evaluate([warn_row], moving, cfg, (2.5, 1.5), 7.5, False)
result["warning_direction"] = {"annotated_onset_direction": "R", "onset_prediction_deg": -90,
    "reported_event": mev[0], "scope": "constructed moving sound with correct onset direction"}

# Walking pairs remain in the main set and the previous continuous walking metric is absent.
walk_rows = []
walk_pred = {}
for name, pair, state, kind in [("a", "", "静止", "A"), ("ws", "S1/P1", "静止", "歩行"), ("ww", "S1/P1", "歩行", "歩行")]:
    walk_rows.append({"clip_id": name, "event_id": "1", "trial": kind, "class": "car_drive", "quadrant": "L",
        "t_start": "2", "t_cpa": "8", "横距離m": "2.5", "take_id": name, "pair_id": pair,
        "区分": kind, "状態": state, "n_car": "1", "session_id": "S1"})
    walk_pred[name] = {k: [(4, 90., 0., 2.)] for k in range(50, 71)}
wev, _, _ = score.evaluate(walk_rows, walk_pred, cfg, (2.5, 1.5), 7.5, False)
main_ev, sides, _ = score.summarize(wev, False)
result["walking_main_population"] = {"main_count": len(main_ev),
    "walking_pair_rows_in_main": sum(bool(e["pair_id"]) for e in main_ev),
    "frame_recall_exported": "frame_recall" in score.EVENT_FIELDS, "events": main_ev}
front_ev, _, _ = score.evaluate([{**walk_rows[0], "quadrant": "F"}], walk_pred, cfg, (2.5, 1.5), 7.5, False)
fm, fsides, _ = score.summarize(front_ev, False)
result["front_fix"] = {"main_count": len(fm), "front_count": len(fsides["front"])}

# The opportunity switch applies to all of D, not just its four siren takes.
op_base = {"clip_id": "A0", "event_id": "1", "trial": "A", "class": "car_drive", "quadrant": "L",
           "t_start": "1", "t_cpa": "8", "take_id": "A0", "区分": "A", "状態": "静止", "横距離m": "2.5"}
exposure = {**op_base, "clip_id": "negative", "take_id": "negative", "class": "none", "quadrant": "",
            "t_start": "0", "t_cpa": "6000", "区分": "負例露出", "横距離m": ""}
op_results = {}
for n_d in (0, 16, 20):
    drows = [{**op_base, "clip_id": f"D{i}", "take_id": f"D{i}", "trial": "D", "区分": "D",
              "class": "crossing" if i < 8 else "backup_beep" if i < 12 else "horn" if i < 16 else "siren",
              "横距離m": ""} for i in range(n_d)]
    ap = DATA / f"opportunity_{n_d}.csv"
    write_csv(ap, [op_base, exposure, *drows])
    for arg in ("D", "D=8"):
        tag = f"opportunity_{n_d}_{arg.replace('=', '_')}"
        p = cli(tag, "step19c_ann_validate.py", ["--ann", ap, "--strict", "--plan",
            "A=1,B=0,C=0,D=20,E=0,F=0,歩行=0", "--opportunity", arg])
        op_results[f"D_count_{n_d}_{arg}"] = {"exit_code": p["exit_code"],
            "D_messages": [s for s in p["stdout"].splitlines() if "区分D" in s or "NG:" in s]}
result["opportunity"] = op_results

result["timing_counterexample"] = {"vehicle_length_m": 4.5, "speed_m_s": 1.0, "assumed_reaction_s": 0.25,
    "button_time_minus_center_CPA_s": 0.25 - 4.5/(2*1.0),
    "scope": "geometric counterexample to guaranteed cancellation, not measured human timing"}

files = ["scripts/step19_realsmoke_convert.py", "scripts/step19b_realsmoke_cut.py", "scripts/step19c_ann_validate.py",
         "scripts/step19d_field_csv_to_ann.py", "scripts/step20_realsmoke_score_v3.py", "scripts/test_realsmoke_v2_units.py",
         "scripts/step12_notify_v43.py", "scripts/step12_notify_v9b_hold.py", "out/notify_v43_sweep/winner.json",
         "md/audit/敵対的レビュー_実録プロトコル_対応計画_2026-09-06.md",
         "md/design/実録_事前登録の変更票_2026-09-06.md", "md/design/実録_当日の手順書_車の収録_2026-09-05.md",
         "md/design/実録_解析パイプライン_現場CSVから採点まで_2026-09-06.md",
         "md/design/実録_調整用と最終評価用の分離_2026-09-05.md", "md/design/実録ハンドブック_2026-08-13.md"]
files += [str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "md/design/実録_記入用CSV_2026-09-05").iterdir() if p.is_file()]
result["source_sha256"] = {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}
result["existing_tests_last_line"] = (OUT / "existing_tests.log").read_text(encoding="utf-8").strip().splitlines()[-1]
(OUT / "evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k not in ("source_sha256", "walking_main_population")}, ensure_ascii=False, indent=2))
