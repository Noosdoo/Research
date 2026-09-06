# -*- coding: utf-8 -*-
"""Step 19d: 現場の記入用 CSV（session.csv ＋ events.csv）→ 解析入力 ann_orig.csv（2026-09-06・監査 R04）。

現場では「session.csv（セッション 1 行）」と「events.csv（テイク×イベント 1 行）」だけを書く。
このスクリプトが step19b/19c/20 が必要とする列（BASE_COLS ＋ PLAN_COLS ＋ 校正・原本の対応）に**規則で**変換する。
規則はここに 1 か所だけ書く（記入用 CSV の README と食い違ったらこちらが正）。

変換規則:
  - 一意キー = session_id × take_id。take_id は "<session_id>/<take>"。clip_id（原録音キー）は `原本` 列があればその stem（例 ZOOM0001）、無ければ "<session_id>_take<NN>"
  - 原本ファイル名 = `原本` 列（任意名可・再監査 N01）、無ければ "<session_id>_take<NN>.wav"。step19b は orig_file で音声と照合する
  - session.csv の `用途`（最終評価／調整用・既定 最終評価）: 調整用のセッションの行は ann_orig に入れず <out>_tuning.csv に出す（A′・再監査 N06）
  - 象限 → quadrant、状態 → 状態（そのまま）、区分は session.csv の区分（歩行対比の行は "歩行"）
  - 距離クラス（car_drive/kick/bike）: ラップ = 前端が肩の線を通った瞬間（最接近）。t_cpa = ラップ秒（＋ --lap-offset）、t_start = t_cpa − --pre（既定 6 s。負なら 0）
  - 警告音クラス（siren/horn/backup_beep/bike_bell/crossing）: ラップ = **音の始まり（気づいた瞬間）**。t_start = ラップ、t_cpa = ラップ + --warn-span（既定 3 s）
    → 成功の窓は [ラップ−1 s, ラップ＋4 s]、方向はこの区間の推定方位で比べる（採点器 v3）
  - class=none の行（負例）は t_start=0、t_cpa=原本の長さ（--audio-dir から読む。無ければ空欄で step19b が埋める）
  - 校正: session.csv の LAeq_dB・暗騒音区間_秒・校正ファイル名（`校正原本` 列。無ければ "<session_id>_calib.wav"）から
    calibration_id = 校正原本の stem（例 ZOOM0001）を付ける。step19 --calib raw/ZOOM0001.wav の既定 id と一致する（監査 H01）
  - 点検原本（`点検原本` 列）と `点検方式` を check_file / 点検方式 として引き継ぐ。step19b は check_file を切り出し対象から外す
  - pair_id は "<session_id>/<pair_id>"、trial は 区分（歩行対比は "walk"）
  - session.csv の `マイク高さ_cm`（実測・必須）→ `mic_z`[m]。推論（_causal_infer_v17.py）は HEIGHT_TABLE にこの csv（clip_id, mic_z）を渡す（v17b・2026-09-06）

使い方: python scripts/step19d_field_csv_to_ann.py --session session.csv --events events.csv --out ann_orig.csv
        [--pre 6] [--lap-offset 0] [--warn-span 3] [--audio-dir raw/]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_COLS = ["clip_id", "event_id", "trial", "class", "quadrant", "t_start", "t_cpa",
            "take_id", "pair_id", "区分", "状態", "横距離m", "n_car", "車種", "速度", "特記",
            "session_id", "orig_file", "calibration_id", "calib_file", "check_file", "点検方式", "excluded_files", "LAeq_dB", "暗騒音区間_秒", "t_start_rule", "用途", "mic_z",
            "overlap_group_id", "車両区分", "確認方法"]
CLASSES = {"siren", "horn", "backup_beep", "bike_bell", "car_drive", "crossing", "kick", "bike", "none"}
WARN_CLASSES = {"siren", "horn", "backup_beep", "bike_bell", "crossing"}
QUADS = {"F", "B", "L", "R", ""}


def _arg(name, default=None):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


def read_csv(path: Path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    return [{k.strip(): (v or "").strip() for k, v in r.items() if k is not None} for r in rows]


def take_num(v: str) -> str:
    try:
        return f"{int(float(v)):02d}"
    except ValueError:
        return v


def convert(sessions, events, pre: float, lap_offset: float, audio_dir: Path | None, warn_span: float = 3.0):
    """返り値: (rows, warnings)"""
    warns = []
    ses = {}
    for r in sessions:
        sid = r.get("session_id", "")
        if not sid or sid.startswith("←"):
            continue
        ses[sid] = r
    out = []
    seen = set()
    for r in events:
        sid = r.get("session_id", "")
        if not sid or sid.startswith("←") or r.get("take_id", "") == "":
            continue
        if sid not in ses:
            warns.append(f"session.csv に無い session_id: {sid}（take {r.get('take_id')}）")
            srow = {}
        else:
            srow = ses[sid]
        tk = take_num(r["take_id"])
        cls = r.get("class", "")
        if cls not in CLASSES:
            warns.append(f"{sid}/take{tk}: 未知の class '{cls}'")
        quad = r.get("象限", r.get("quadrant", ""))
        if quad not in QUADS:
            warns.append(f"{sid}/take{tk}: 象限 '{quad}' は F/B/L/R")
        state = r.get("状態", "") or "静止"
        mic_cm = srow.get("マイク高さ_cm", "")
        try:
            mic_z = f"{float(mic_cm) / 100.0:.3f}"
        except ValueError:
            mic_z = ""
            if sid in ses and (sid, "mic") not in seen:
                warns.append(f"{sid}: session.csv に マイク高さ_cm が無い（v17b は装着高さをモデルに入力する。実測して cm で書く）"); seen.add((sid, "mic"))
        kubun = srow.get("区分", "")
        yoto = (srow.get("用途", "") or "").strip()
        if yoto not in ("最終評価", "調整用"):
            if (sid, "yoto") not in seen:
                warns.append(f"{sid}: 用途 '{yoto}' は 最終評価／調整用 のどちらでもない → 保留（<out>_unresolved.csv）。記録紙を直す（再監査2 Q05）"); seen.add((sid, "yoto"))
            yoto = "未確定"
        kind = "歩行" if (r.get("pair_id", "") or kubun == "歩行対比") else kubun
        if kubun == "歩行対比" and cls != "none" and not r.get("pair_id", ""):
            warns.append(f"{sid}/take{tk}: 区分=歩行対比 なのに pair_id が無い（静止/歩行の 2 本に同じ P 番号を付ける）")
        if kubun == "歩行対比" and cls != "none" and not (r.get("状態", "") or "").strip():
            warns.append(f"{sid}/take{tk}: 区分=歩行対比 なのに 状態（静止/歩行）が無い")
        ev = r.get("event_id", "1") or "1"
        key = (sid, tk, ev)
        if key in seen:
            warns.append(f"{sid}/take{tk}: event_id {ev} が重複")
        seen.add(key)
        orig = r.get("原本", "") or f"{sid}_take{tk}.wav"
        clip_key = f"{sid}__{Path(orig).stem}" if r.get("原本", "") else f"{sid}_take{tk}"   # session__原本: 別セッションの同名原本と衝突しない（再監査2 Q03）
        calib_file = srow.get("校正原本", "") or f"{sid}_calib.wav"
        # 校正 id は校正原本の stem（step19 --calib の既定 calib_id と同じ）。校正原本が無い旧様式だけ <session>_calib
        calib_id = Path(calib_file).stem
        check_file = srow.get("点検原本", "")
        # 備考の「除外: a.wav b.wav」（ノートの取り消し・事象 0 件の除外）→ step19b が切り出し対象から外す（ノート監査 H02/H04）
        import re as _re
        m_ex = _re.search(r"除外[:：]\s*([^／\n]+)", srow.get("備考", "") or "")
        excluded = " ".join(m_ex.group(1).split()) if m_ex else ""
        if cls == "none":
            t_start = "0"
            t_cpa = ""
            if audio_dir is not None:
                p = audio_dir / orig
                if p.exists():
                    import soundfile as sf
                    with sf.SoundFile(str(p)) as f:
                        t_cpa = f"{len(f) / f.samplerate:.2f}"
            if t_cpa == "":
                warns.append(f"{sid}/take{tk}: 負例の長さが分からない（--audio-dir に原本が無い）→ t_cpa 空欄。step19b --mode negative は原本から長さを取る")
            rule = "none: [0, 録音長)"
        else:
            lap = r.get("ラップ秒", r.get("t_cpa", ""))
            try:
                tc = float(lap) + lap_offset
            except ValueError:
                warns.append(f"{sid}/take{tk}: ラップ秒が数値でない '{lap}'")
                tc = 0.0
            if cls in WARN_CLASSES:
                t_start = f"{max(0.0, tc):.2f}"; t_cpa = f"{tc + warn_span:.2f}"
                rule = f"警告音: t_start = ラップ（音の始まり）, t_cpa = ラップ + {warn_span:g} s"
            else:
                t_cpa = f"{tc:.2f}"
                t_start = f"{max(0.0, tc - pre):.2f}"
                rule = f"t_start = t_cpa − {pre:g} s（規則）; t_cpa = ラップ秒 {'+ ' + str(lap_offset) + ' s' if lap_offset else ''}"
        out.append({
            "clip_id": clip_key, "event_id": ev, "trial": ("walk" if kind == "歩行" else (srow.get("区分", "") or "?")),
            "class": cls, "quadrant": quad, "t_start": t_start, "t_cpa": t_cpa,
            "take_id": f"{sid}/{tk}", "pair_id": (f"{sid}/{r['pair_id']}" if r.get("pair_id") else ""),
            "区分": kind, "状態": state, "横距離m": r.get("横距離m", ""), "n_car": r.get("n_car", ""),
            "車種": r.get("車種", ""), "速度": r.get("速度", ""), "特記": r.get("特記", ""),
            "overlap_group_id": r.get("overlap_group_id", ""), "車両区分": r.get("車両区分", ""), "確認方法": r.get("確認方法", ""),
            "session_id": sid, "orig_file": orig, "calibration_id": calib_id, "calib_file": calib_file,
            "check_file": check_file, "点検方式": srow.get("点検方式", ""), "excluded_files": excluded,
            "LAeq_dB": srow.get("LAeq_dB", ""), "暗騒音区間_秒": srow.get("暗騒音区間_秒", ""), "t_start_rule": rule,
            "用途": yoto,
            "mic_z": mic_z})
    return out, warns


def main() -> int:
    sessions = read_csv(Path(_arg("--session")))
    events = read_csv(Path(_arg("--events")))
    out_path = Path(_arg("--out", str(ROOT / "out" / "realsmoke" / "ann_orig.csv")))
    pre = float(_arg("--pre", "6"))
    lap_offset = float(_arg("--lap-offset", "0"))
    audio_dir = Path(_arg("--audio-dir")) if _arg("--audio-dir") else None
    warn_span = float(_arg("--warn-span", "3"))
    rows, warns = convert(sessions, events, pre, lap_offset, audio_dir, warn_span)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tuning = [r for r in rows if r.get("用途") == "調整用"]
    unresolved = [r for r in rows if r.get("用途") == "未確定"]
    rows = [r for r in rows if r.get("用途") == "最終評価"]
    if unresolved:
        upath = out_path.with_name(out_path.stem + "_unresolved.csv")
        with open(upath, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=OUT_COLS); w.writeheader(); w.writerows(unresolved)
        print(f"用途が未確定の {len(unresolved)} 行は評価用にも調整用にも入れず保留 -> {upath}")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS); w.writeheader(); w.writerows(rows)
    # セッション表（<out>_sessions.csv）: 事象が 0 行のセッションでも校正・点検・除外の原本名を step19b に渡す（ノート監査 H01/H02）
    spath = out_path.with_name(out_path.stem + "_sessions.csv")
    with open(spath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["session_id", "calib_file", "calibration_id", "check_file", "点検方式", "excluded_files", "用途"]); w.writeheader()
        import re as _re2
        for srow in sessions:
            sid = srow.get("session_id", "")
            if not sid:
                continue
            cf = srow.get("校正原本", "") or f"{sid}_calib.wav"
            m_ex = _re2.search(r"除外[:：]\s*([^／\n]+)", srow.get("備考", "") or "")
            w.writerow({"session_id": sid, "calib_file": cf, "calibration_id": Path(cf).stem, "check_file": srow.get("点検原本", ""),
                        "点検方式": srow.get("点検方式", ""), "excluded_files": " ".join(m_ex.group(1).split()) if m_ex else "",
                        "用途": srow.get("用途", "") or "最終評価"})
    if tuning:
        tpath = out_path.with_name(out_path.stem + "_tuning.csv")
        with open(tpath, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=OUT_COLS); w.writeheader(); w.writerows(tuning)
        print(f"用途=調整用 {len(tuning)} 行は最終評価の入力に含めず -> {tpath}")
    for wmsg in warns:
        print("[WARN]", wmsg)
    n_take = len({(r["session_id"], r["take_id"]) for r in rows})
    print(f"{len(rows)} 行 / {n_take} テイク / {len({r['session_id'] for r in rows})} セッション -> {out_path}")
    print("次: step19 --calib raw/<校正原本> --laeq <LAeq_dB> --gain-only --out <calib-dir>（校正 id = 校正原本の stem）→ step19b --calib-dir <calib-dir> → step19c --ann ... → step20 v3")
    return 1 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
