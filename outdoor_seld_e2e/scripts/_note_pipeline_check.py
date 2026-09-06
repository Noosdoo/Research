# -*- coding: utf-8 -*-
"""ノート（jsdom テスト）が出した session.csv / events.csv を、原本一式（校正・点検・事象・除外を同じ raw/ に置く）で
step19d → step19 --calib → step19b --mode event/negative → step19c に流し、原本一覧と出力行の対応を確かめる（ノート監査 H01 の一連の模擬収録）。"""
import csv, io, os, re, subprocess, sys, tempfile
from pathlib import Path
import numpy as np, soundfile as sf
SP = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent   # note_session.csv / note_events.csv の場所
ROOT = Path(r"C:\Users\satos\research\outdoor_seld_e2e"); SC = ROOT / "scripts"; PY = sys.executable
sess = list(csv.DictReader(io.open(SP / "note_session.csv", encoding="utf-8")))
evs = list(csv.DictReader(io.open(SP / "note_events.csv", encoding="utf-8")))
td = Path(tempfile.mkdtemp()); raw = td / "raw"; raw.mkdir(); conv = td / "conv"
names = set()
for s in sess:
    names |= {s["校正原本"], s["点検原本"]}
    m = re.search(r"除外[:：]\s*([^／\n]+)", s.get("備考", "")); names |= set(m.group(1).split()) if m else set()
names |= {e["原本"] for e in evs}
fs = 24000
dur = {n: 12.0 for n in names}
for s in sess:   # 校正ファイルは記録紙の暗騒音区間（例 0-60）と同じ長さにする（切り出しが区間を照合する・再監査2 Q02）
    try:
        a, b = (float(x) for x in (s.get("暗騒音区間_秒") or "0-60").split("-")); dur[s["校正原本"]] = b - a
    except ValueError:
        pass
for n in sorted(names):
    tt = np.arange(int(fs * dur[n])) / fs
    sf.write(str(raw / n), np.tile((0.01 * np.sin(2 * np.pi * 1000.0 * tt))[:, None], (1, 4)).astype(np.float32), fs)
print("raw/:", sorted(names))
def run(args):
    r = subprocess.run([PY] + [str(a) for a in args], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
    print(f"$ {' '.join(Path(str(a)).name if str(a).startswith(str(td)) else str(a) for a in args[:1])} ... rc={r.returncode}")
    return r
r1 = run([SC / "step19d_field_csv_to_ann.py", "--session", SP / "note_session.csv", "--events", SP / "note_events.csv", "--audio-dir", raw, "--out", td / "ann_orig.csv"])
print("  " + r1.stdout.strip().replace("\n", "\n  ")[:600])
rc_cal = []
for s in sess:
    r = run([SC / "step19_realsmoke_convert.py", "--in", raw, "--calib", raw / s["校正原本"], "--laeq", s["LAeq_dB"] or "50", "--gain-only", "--out", conv]); rc_cal.append(r.returncode)
    if r.returncode: print(r.stdout[-400:], r.stderr[-400:])
r3 = run([SC / "step19b_realsmoke_cut.py", "--mode", "event", "--in", raw, "--ann", td / "ann_orig.csv", "--calib-dir", conv, "--pitch", "0", "--roll", "0", "--yaw", "0", "--out", td / "clips", "--ann-out", td / "ann_all.csv"])
print("  " + r3.stdout.strip().replace("\n", "\n  ")[-700:]); print(r3.stderr[-400:] if r3.returncode else "")
r4 = run([SC / "step19b_realsmoke_cut.py", "--mode", "negative", "--in", raw, "--ann", td / "ann_orig.csv", "--calib-dir", conv, "--pitch", "0", "--roll", "0", "--yaw", "0", "--out", td / "clips_neg", "--ann-out", td / "ann_neg.csv"])
print("  " + r4.stdout.strip().replace("\n", "\n  ")[-500:]); print(r4.stderr[-400:] if r4.returncode else "")
rows = list(csv.DictReader(io.open(td / "ann_all.csv", encoding="utf-8"))) if (td / "ann_all.csv").exists() else []
print("切り出し（event）:", sorted({(r["clip_id"], r["orig_file"], r["calibration_id"]) for r in rows}))
print("  クリップ内の注釈行（群・台数）:", [(r["clip_id"], r["event_id"], r.get("overlap_group_id"), r.get("n_car")) for r in rows if r["clip_id"].endswith("_e1")])
ev_origs = {Path(e["原本"]).stem for e in evs if e["class"] != "none"}
print("原本一覧との照合: 事象原本", sorted(ev_origs), "→ 切り出し", sorted({r["orig_file"] for r in rows}), "一致" if ev_origs == {r["orig_file"] for r in rows} else "不一致")
r5 = run([SC / "step19c_ann_validate.py", "--ann", td / "ann_all.csv", "--cut", "--plan", "A=1"])
print("  " + "\n  ".join(l for l in r5.stdout.strip().split("\n") if "ERROR" in l or "NG" in l or "OK" in l or "合格" in l)[-500:])
ok = r1.returncode == 0 and all(x == 0 for x in rc_cal) and r3.returncode == 0 and r4.returncode == 0 and ev_origs == {r["orig_file"] for r in rows}
print("PIPELINE", "OK" if ok else "NG", f"(rc: 19d={r1.returncode}, calib={rc_cal}, 19b event={r3.returncode}, negative={r4.returncode}, 19c={r5.returncode})")
sys.exit(0 if ok else 1)
