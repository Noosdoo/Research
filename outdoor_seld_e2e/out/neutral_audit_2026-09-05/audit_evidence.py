"""Read saved development predictions only; never run inference or open fold20.

Run from research: DynamicSound/.venv/Scripts/python.exe -B
  outdoor_seld_e2e/out/neutral_audit_2026-09-05/audit_evidence.py
Outputs are confined to this audit directory. Production code is unchanged.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


HP = load("audit_hp", "_hp_score.py")
AT = load("audit_at", "_notify_v43_attrib.py")
V43 = load("audit_v43", "step12_notify_v43.py")
CFG = V43.Cfg43(**json.loads((ROOT / "out/notify_v43_sweep/winner.json").read_text()))
META = ROOT / "out/dataset_outdoor_siren_v15/metadata_dist"
HP.META = META
PLAN15 = ROOT / "out/dataset_outdoor_siren_v15/plan/assignment_v15.csv"
PLAN16 = ROOT / "out/dataset_outdoor_siren_v16/plan/assignment_v16.csv"


def plan(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


P15, P16 = plan(PLAN15), plan(PLAN16)
CLIPS = sorted(r["clip_id"] for r in P15 if r["split"] == "fold2")
GT = {}
EVENTS = {}
for clip in CLIPS:
    rows = []
    with (META / (clip + ".csv")).open(encoding="utf-8") as f:
        for q in csv.reader(f):
            if len(q) == 6:
                rows.append((int(q[0]), int(q[1]), int(q[2]), float(q[3]), float(q[5])))
    GT[clip] = rows
    EVENTS[clip] = [HP.EV.DG.mk_event(c, t, fr) for c, t, fr in HP.EV.DG.gt_tracks(META, clip)]


def hashfile(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def independent_pairs(path):
    """Maximum cardinality one-to-one class/azimuth matches, <=20 deg, frame>=40.

    This diagnoses the denominator/matching issue; it is not a replacement
    preregistered metric. All manifest GT objects are included in recall.
    """
    preds = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for q in csv.reader(f):
            if len(q) >= 7 and int(q[1]) >= 40 and int(q[2]) in HP.SEL.CLS:
                preds[(q[0], int(q[1]), int(q[2]))].append((float(q[4]), float(q[6])))
    counts = Counter()
    rel = []
    for clip, rows in GT.items():
        bykey = defaultdict(list)
        for fr, cl, tr, az, d in rows:
            if fr >= 40 and cl in HP.SEL.CLS:
                bykey[(clip, fr, cl)].append((tr, az, d))
        for key, gs in bykey.items():
            counts["all_gt"] += len(gs)
            counts["all_close_gt"] += sum(g[2] <= 1.5 for g in gs)
            ps = preds.get(key, [])
            if not ps:
                continue
            e = np.array([[abs((p[0] - g[1] + 180) % 360 - 180) for p in ps] for g in gs])
            nearest = Counter()
            for j in range(len(ps)):
                i = min(range(len(gs)), key=lambda k: (e[k, j], gs[k][2]))
                if e[i, j] <= 20:
                    nearest[i] += 1
            counts["duplicate_nearest_gt_assignments"] += sum(max(0, n-1) for n in nearest.values())
            ii, jj = linear_sum_assignment(np.where(e <= 20, e, 1e6))
            for i, j in zip(ii, jj):
                if e[i, j] > 20:
                    continue
                dg, dp = gs[i][2], ps[j][1]
                counts["matched_gt"] += 1
                rel.append(abs(dp-dg) / max(dg, 0.1))
                if dg <= 1.5:
                    counts["matched_close_gt"] += 1
                    counts["caught_close_gt"] += dp <= 1.5
    return dict(counts) | {
        "conditional_median_relative_error_pct": float(np.median(rel)*100),
        "close_recall_all_gt_pct": counts["caught_close_gt"] / counts["all_close_gt"] * 100,
        "close_match_coverage_pct": counts["matched_close_gt"] / counts["all_close_gt"] * 100,
    }


def model(label, relative):
    src = ROOT / relative
    pred = HP.v4.load_pred(src)
    extra = set(pred) - set(CLIPS)
    assert not extra, sorted(extra)[:3]
    missing = set(CLIPS) - set(pred)
    all_pred = {clip: pred.get(clip, {}) for clip in CLIPS}
    res42 = HP.V42.run_rule2(pred, HP.ADOPTED)
    res43 = V43.run_rule3(pred, CFG)
    pair = HP.SEL.pairs(src, META)
    close = pair[pair[:, 1] <= 1.5, 0]
    row = {
        "source": relative, "sha256": hashfile(src),
        "manifest_clips": len(CLIPS), "predicted_clips": len(pred),
        "missing_clips": len(missing),
        "missing_clips_with_any_gt": sum(bool(GT[c]) for c in missing),
        "missing_distance_events": dict(Counter(ev["tier"] for c in missing for ev in EVENTS[c])),
        "reported_method_distance": {
            "pairs": len(pair), "median_relative_error_pct": float(np.median(abs(pair[:, 0]-pair[:, 1])/np.maximum(pair[:, 1], .1))*100),
            "conditional_close_capture_pct": float(np.mean(close <= 1.5)*100),
        },
        "v42_window_prediction_clips": HP.EV.score(pred, META, res42),
        "v42_window_manifest_clips": HP.EV.score(all_pred, META, res42),
        "v42_attribution_manifest_clips": AT.score_attrib(all_pred, META, res42),
        "v43_attribution_manifest_clips": AT.score_attrib(all_pred, META, res43),
        "independent_one_to_one": independent_pairs(src),
    }
    print(json.dumps({label: row}, ensure_ascii=False), flush=True)
    return row


def plan_checks():
    orig = {r["clip_id"]: r for r in P15}
    mismatches = []
    for r in P16:
        baseid = r["clip_id"]
        if r["h_copy"] == "2":
            prefix, num = baseid.rsplit("mix", 1)
            baseid = prefix + "mix" + f"{int(num)-10000:04d}"
        base = orig[baseid]
        ignored = {"grammar", "h_copy"} | ({"clip_id", "mic_z"} if r["h_copy"] == "2" else set())
        for k, v in base.items():
            if k not in ignored and r.get(k) != v:
                mismatches.append((r["clip_id"], k))
    splits = {s: {r["seed"] for r in P16 if r["split"] == s} for s in ("fold1", "fold2")}
    z1 = [float(r["mic_z"]) for r in P16 if r["h_copy"] == "1"]
    z2 = [float(r["mic_z"]) for r in P16 if r["h_copy"] == "2"]
    return {
        "v15_counts": dict(Counter(r["split"] for r in P15)),
        "v16_counts": dict(Counter(r["split"] for r in P16)),
        "v16_train_validation_seed_overlap": len(splits["fold1"] & splits["fold2"]),
        "copy_mismatches_outside_declared_columns": mismatches,
        "copies_with_same_rounded_height": int(np.sum(np.array(z1) == np.array(z2))),
        "v15_sha256": hashfile(PLAN15), "v16_sha256": hashfile(PLAN16),
    }


def synthetic_check():
    m = OUT / "synthetic_gt"
    m.mkdir(exist_ok=True)
    (m / "sample.csv").write_text("40,4,0,0,0,1.0\n40,4,1,120,0,1.0\n", encoding="utf-8")
    p = OUT / "synthetic_pred.csv"
    p.write_text("sample,40,4,0,0,0,1.0\nsample,40,4,1,1,0,1.0\n", encoding="utf-8")
    pairs = HP.SEL.pairs(p, m)
    return {"gt_objects": 2, "distinct_detected_gt_objects": 1,
            "legacy_pairs": pairs.tolist(), "legacy_capture_pct": float(np.mean(pairs[:,0] <= 1.5)*100),
            "recall_with_unique_gt_denominator_pct": 50.0}


def reference_projection():
    src = ROOT / "out/hp_sweep/ref/ft2_e079_val_causal.csv"
    dst = OUT / "ft2_e079_horizontal.csv"
    with src.open(encoding="utf-8") as f, dst.open("w", encoding="utf-8", newline="") as w:
        for q in csv.reader(f):
            if len(q) >= 7:
                q[6] = f"{float(q[6])*math.cos(math.radians(float(q[5]))):.2f}"
            w.write(",".join(q)+"\n")
    meta = ROOT / "out/dataset_outdoor_siren_v12/metadata_dist_h"
    out = {"raw_source_sha256": hashfile(src)}
    for tag, path in (("raw_3d_vs_horizontal_gt", src), ("projected_horizontal_vs_horizontal_gt", dst)):
        p = HP.SEL.pairs(path, meta)
        c = p[p[:,1] <= 1.5, 0]
        out[tag] = {"pairs": len(p), "median_relative_error_pct": float(np.median(abs(p[:,0]-p[:,1])/np.maximum(p[:,1], .1))*100),
                    "conditional_close_capture_pct": float(np.mean(c<=1.5)*100)}
    return out


if __name__ == "__main__":
    evidence = {"plan": plan_checks(), "synthetic": synthetic_check()}
    print(json.dumps(evidence, ensure_ascii=False), flush=True)
    evidence["models"] = {}
    for label, path in [
        ("v15_e139", "out/v15/C/infer_v15ft_e139_selfcausal.csv"),
        ("v15c_e139h", "out/v15c/Ch/infer_v15cft_e139_selfcausal.csv"),
        ("v15b_e139", "out/v15b/C/infer_v15bft_e139_v15causal.csv"),
    ]:
        evidence["models"][label] = model(label, path)
        (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    evidence["reference_projection"] = reference_projection()
    (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"reference_projection": evidence["reference_projection"]}, ensure_ascii=False), flush=True)
