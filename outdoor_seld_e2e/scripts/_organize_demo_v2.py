# -*- coding: utf-8 -*-
"""デモv2のデータを「種類別フォルダ・日本語名」に整理し、Unity プロジェクトへ配置する（2026-09-03）。

入力: out/joycon_demo_v2/ の custom_<name>.* と fold32_*.*（各 wav/_cues/_scene/_urgency/_detect/_layout）
出力: out/joycon_demo_v2/場面/<カテゴリ>/<日本語名>.*（コピー。元ファイルは残す）
      --unity: C:/Users/satos/JoyconDemo/Assets/StreamingAssets/joycon_demo_v2/ へ同じ構成でコピーし、
               Assets/JoyconDemoPlayer.cs と Assets/ScenarioVisualizer.cs を out/joycon_demo_v2/unity/ で上書き
使い方: python scripts/_organize_demo_v2.py [--unity]
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "out/joycon_demo_v2"
DST = SRC / "場面"
UNITY = Path("C:/Users/satos/JoyconDemo/Assets")
EXTS = [".wav", "_cues.csv", "_scene.csv", "_urgency.csv", "_detect.csv", "_layout.csv"]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# (元の名前, カテゴリ, 日本語名)
MAP = [
    ("custom_01_roji_ushiro_kuruma", "1_路地・住宅街", "路地_後ろからゆっくり車_至近"),
    ("custom_02_roji_taikou_kuruma", "1_路地・住宅街", "路地_前から対向車"),
    ("custom_16_ushiro_kuruma_yukkuri_tsuika", "1_路地・住宅街", "路地_ゆっくり抜けていく車"),
    ("custom_14_fukugo_mae_kuruma_ushiro_jitensha", "1_路地・住宅街", "複合_前から車と後ろから自転車ベル"),
    ("custom_13_shizuka_nanimonai", "1_路地・住宅街", "静かな住宅街_何も来ない"),
    ("custom_03_kansen_hodou_renzoku", "2_幹線道路・交差点・歩道", "幹線歩道_車3台が連続"),
    ("custom_15_kansen_shingo_machi", "2_幹線道路・交差点・歩道", "幹線_信号待ちで車が次々"),
    ("custom_04_fumikiri_matsu_ressha", "3_踏切・列車・高架", "踏切で待つ_列車が目の前を通過"),
    ("custom_05_fumikiri_keihou_dake", "3_踏切・列車・高架", "踏切_警報だけで列車はまだ"),
    ("custom_06_chushajo_backup", "4_駐車場・自転車・小型車両", "駐車場_バックしてくる車"),
    ("custom_07_jitensha_bell_ushiro", "4_駐車場・自転車・小型車両", "後ろから自転車ベル"),
    ("custom_08_kick_ushiro", "4_駐車場・自転車・小型車両", "後ろからキックボード"),
    ("custom_09_bike_ushiro", "4_駐車場・自転車・小型車両", "後ろからバイク"),
    ("custom_10_kyukyusha_tsuuka", "5_緊急車両・クラクション", "救急車が横を通過"),
    ("custom_11_kyukyusha_sekkin_nomi", "5_緊急車両・クラクション", "救急車が近づくだけ"),
    ("custom_12_horn_narasareru", "5_緊急車両・クラクション", "クラクションを鳴らされる"),
    ("custom_17_teisha_kuruma_hasshin", "1_路地・住宅街", "路肩に停車中の車が発進して走り去る"),
    ("custom_21_takuhai_bike_teishi_hasshin", "4_駐車場・自転車・小型車両", "宅配バイクが後ろから来て停止_発進"),
    ("custom_18_oudan_migi_kara_kuruma", "2_幹線道路・交差点・歩道", "横断歩道を渡る途中_右から車が減速して横切る"),
    ("custom_20_basutei_basu_teisha_hasshin", "2_幹線道路・交差点・歩道", "バス停_バスが真横に停車して発進"),
    ("custom_22_kousaten_yokogiru_kuruma", "2_幹線道路・交差点・歩道", "交差点の角で待つ_前の道路を車が横切る"),
    ("custom_23_sasetsu_makikomi", "2_幹線道路・交差点・歩道", "左折巻き込み_後ろの車が目の前で左折"),
    ("custom_19_koukashita_zujou_ressha", "3_踏切・列車・高架", "高架下_頭上を列車が通過_後ろから車"),
    ("custom_24_rikadai_seimon_matsu_sasetsu", "7_実地図_理科大正門前", "正門前で待つ_北から車が左折_南西からも車"),
    ("custom_25_rikadai_seimon_deru_wataru", "7_実地図_理科大正門前", "正門から出て交差点を渡る_東から車"),
    ("custom_26_rikadai_seimon_nansei_kara", "7_実地図_理科大正門前", "南西から車が交差点を抜ける_後ろから自転車ベル"),
    ("custom_27_rikadai_seimon_aruite_sasetsu_mae", "7_実地図_理科大正門前", "歩行_渡る瞬間に北からの車が目の前を左折"),
    ("custom_28_rikadai_seimon_aruite_usetsu_ushiro", "7_実地図_理科大正門前", "歩行_渡った直後に東からの車が背中側を右折"),
    ("fold32_room1_mix0007", "6_本物のモデル出力", "A_同じ車に強が再発火_束ね確認"),
    ("fold32_room1_mix0067", "6_本物のモデル出力", "B_中から強へ昇格_段階と連続"),
    ("fold32_room1_mix0128", "6_本物のモデル出力", "C_幹線歩行_車3台の連続通知"),
    ("fold32_room1_mix0120", "6_本物のモデル出力", "D_安全な車だけ_抑制"),
]


def copy_set(src_base: Path, dst_base: Path) -> int:
    n = 0
    dst_base.parent.mkdir(parents=True, exist_ok=True)
    for ext in EXTS:
        s = Path(str(src_base) + ext)
        if s.exists():
            shutil.copy2(s, Path(str(dst_base) + ext))
            n += 1
    return n


def main() -> int:
    total = 0
    for src, cat, jp in MAP:
        n = copy_set(SRC / src, DST / cat / jp)
        total += n
        print(f"  {cat}/{jp}: {n} files")
    print(f"-> {DST}  ({total} files)")
    if "--unity" in sys.argv:
        assert UNITY.exists(), UNITY
        udst = UNITY / "StreamingAssets" / "joycon_demo_v2"
        if udst.exists():
            shutil.rmtree(udst)
        shutil.copytree(DST, udst)
        for cs in ("JoyconDemoPlayer.cs", "ScenarioVisualizer.cs"):
            shutil.copy2(SRC / "unity" / cs, UNITY / cs)
        print(f"-> Unity: {udst} + {UNITY}/JoyconDemoPlayer.cs, ScenarioVisualizer.cs (overwritten)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
