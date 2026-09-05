"""Read-only protocol audit probes; writes evidence beside this script only.

Run from any directory with a Python containing numpy/scipy/soundfile.
These counterexamples test software behavior, not real H3-VR performance.
"""
from pathlib import Path
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys

sys.dont_write_bytecode = True
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import soundfile as sf

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT / "src"))


def module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


s19 = module("audit_s19", "scripts/step19_realsmoke_convert.py")
cut = module("audit_cut", "scripts/step19b_realsmoke_cut.py")
val = module("audit_val", "scripts/step19c_ann_validate.py")
score = module("audit_score", "scripts/step20_realsmoke_score_v2.py")
from outdoor_seld.calibration import spl_a, gain_for_spl_a

evidence = {"head": subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
fs = 24000
tone = np.sin(2 * np.pi * 1000 * np.arange(fs) / fs)
evidence["a_weighting"] = {
    "one_khz_fullscale_sine_dBA": spl_a(tone, fs),
    "target_52_3_dBA_after_gain": spl_a(tone * gain_for_spl_a(tone, fs, 52.3), fs),
    "scope": "1 kHz normalization and gain transfer only, not IEC instrument certification",
}

# Same positive-right convention as the field CSV: +30 right = -30 math azimuth.
angle = np.deg2rad(-30)
v = np.array([np.cos(angle), np.sin(angle), 0.0])
corrected = s19.rot_matrix(0, 0, 30) @ v
evidence["yaw_sign"] = {"measured_right_deg": 30,
    "corrected_math_azimuth_deg": float(np.rad2deg(np.arctan2(corrected[1], corrected[0])))}

# Front-only checks cannot reveal left/right reflection.
mirror = np.diag([1.0, -1.0, 1.0])
evidence["front_only_calibration"] = {
    "front_after_Y_reflection": (mirror @ np.array([1, 0, 0])).tolist(),
    "left_after_Y_reflection": (mirror @ np.array([0, 1, 0])).tolist(),
    "scope": "identifiability counterexample; does not assert actual recordings are mirrored",
}

raw = OUT / "probe_short_25s_96k.wav"
assert raw.resolve().parent == OUT
try:
    block = np.zeros((96000, 4), dtype=np.float32)
    block[:, 0] = 0.01 * np.sin(2 * np.pi * 1000 * np.arange(96000) / 96000)
    with sf.SoundFile(raw, "w", samplerate=96000, channels=4, subtype="PCM_16") as f:
        for _ in range(25):
            f.write(block)
    failures = {}
    for name, fn in [
        ("gain_only", lambda: s19.calib_gain_db(raw, 52.3, (10, 70))),
        ("convert", lambda: s19.convert(raw, OUT, 52.3, (10, 70), 0, 0, 0)),
    ]:
        try:
            fn()
            failures[name] = "unexpected success"
        except AssertionError as exc:
            failures[name] = str(exc)
    evidence["short_take_calibration"] = {"duration_s": 25, "window_s": [10, 70], **failures}
finally:
    raw.unlink(missing_ok=True)

csv_dir = ROOT / "md/design/実録_記入用CSV_2026-09-05"
session = list(csv.DictReader((csv_dir / "session.csv").open(encoding="utf-8-sig")))[0]
events = list(csv.DictReader((csv_dir / "例_記入済み.csv").open(encoding="utf-8-sig")))
joined = [{**session, **r} for r in events]
val.errs.clear()
val.warns.clear()
with contextlib.redirect_stdout(io.StringIO()):
    val.validate(joined, cut=False, dur=30.0, plan={})
evidence["literal_csv_join"] = {
    "missing_required_columns": sorted(set(val.BASE_COLS) - set(joined[0])),
    "validator_errors": list(val.errs),
}
evidence["example_clip_offsets"] = [
    {"take_id": r["take_id"], "event_id": r["event_id"], "lap_as_cpa_s": float(r["ラップ秒"]),
     "cut_offset_s": cut.plan_event_cut(float(r["ラップ秒"]), 30),
     "cpa_in_clip_s": float(r["ラップ秒"]) - cut.plan_event_cut(float(r["ラップ秒"]), 30)}
    for r in events if r["ラップ秒"]
]

base = {"clip_id": "case", "event_id": "1", "take_id": "s1_1", "trial": "1",
        "class": "car_drive", "quadrant": "F", "t_start": "1", "t_cpa": "8",
        "横距離m": "2.5", "区分": "A", "状態": "静止"}
# A notification at 8.4 s is after CPA, outside the newly stated [5.5,6.5] window.
late_pred = {"case": {82: [(4, 0.0, 2.0)], 83: [(4, 0.0, 2.0)]}}
late_events, _, _ = score.evaluate([base], late_pred, link_deg=60, has_dist=True)
evidence["late_front_notification"] = {"newly_stated_window_s": [5.5, 6.5],
    "actual_accepted_window_s": [0, 9], "result": late_events,
    "included_by_main_scored_filter": len([e for e in late_events if e["notified"] is not None])}

results_by_count = {}
for n in (1, 2):
    ev, _, _ = score.evaluate([{**base, "n_car": str(n)}], late_pred, 60, True)
    results_by_count[str(n)] = ev
evidence["multi_car_count"] = {"same_results": results_by_count["1"] == results_by_count["2"],
    "results": results_by_count}

# A correct late direction can fail against a direction recorded two seconds earlier.
moving_pred = {"case": {76: [(4, -90.0, 2.0)], 77: [(4, -90.0, 2.0)]}}
moving_events, _, _ = score.evaluate([{**base, "quadrant": "B"}], moving_pred, 60, True)
evidence["quadrant_time_mismatch"] = {"GT_at_minus_2s": "B",
    "prediction_at_7_8s": "R", "result": moving_events,
    "scope": "the two directions can both be correct at their own times; no measured path asserted"}

# IDs restart within each session in the field CSV, but the validator keys globally by take_id.
id_rows = [{**base, "take_id": "1", "session_id": "s1"},
           {**base, "take_id": "1", "clip_id": "case_other", "session_id": "s2"}]
val.errs.clear()
val.warns.clear()
with contextlib.redirect_stdout(io.StringIO()):
    val.validate(id_rows, cut=False, dur=30.0, plan={"A": 2})
evidence["global_take_id_collision"] = list(val.errs)

files = [
    "md/audit/敵対的レビュー依頼_実録プロトコル_2026-09-05_Astra用.md",
    "md/design/実録_当日の手順書_車の収録_2026-09-05.md",
    "md/design/実録_機材リスト_2026-09-05.md",
    "md/design/実録ハンドブック_2026-08-13.md",
    "md/design/実録スモーク計画書_2026-07.md",
    "md/design/実録_調整用と最終評価用の分離_2026-09-05.md",
    "scripts/step19_realsmoke_convert.py", "scripts/step19b_realsmoke_cut.py",
    "scripts/step19c_ann_validate.py", "scripts/step20_realsmoke_score_v2.py",
    "scripts/step12_notify_v43.py", "scripts/_notify_v42_q2_table.py",
    "scripts/_notify_v43_attrib.py", "src/outdoor_seld/calibration.py",
] + [str(p.relative_to(ROOT)).replace("\\", "/") for p in sorted(csv_dir.iterdir()) if p.is_file()]
evidence["source_sha256"] = {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}
(OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in evidence.items() if k != "source_sha256"}, ensure_ascii=False, indent=2))
