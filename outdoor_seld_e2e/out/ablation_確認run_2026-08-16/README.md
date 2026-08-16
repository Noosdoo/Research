# ablation 確認run の採点結果（2026-08-16）— **保存対象・削除禁止**

本人指示（2026-08-16 19:26）:「本番扱いにはしません。でもこの結果は必ず取っておいてください」

## これは何か

2026-08-15〜16に実施した **ablation確認run** の採点結果。経緯と解釈は
`md/design/ablation確認run_2026-08-15.md` §5-bis を参照。

- **本番ではない。卒論・発表にこの数値を使わない**（各arm 1本・ゼミ後に土俵が変わる可能性）
- ただし **順位と傾向は本番の予測材料として有効**であり、
  「この実験デザインで差が検出できる」ことの実証記録として保存する

## 中身

| ディレクトリ | 中身 |
| --- | --- |
| `abl_score_BASELINE_w3_val/` | 基準 v12 w3（job315学習）のval採点 |
| `abl_score_SEED2_val/` | **ラン揺れフロア**（基準と同条件・seedのみ変更 job834） |
| `abl_score_no_1r_fullval/` | no_1r の転移評価（**主要評価**） |
| `abl_score_no_1r_selfval/` | no_1r の自条件val（参考） |
| `abl_score_no_ground_fullval/` | no_ground の転移評価 |
| `abl_score_no_doppler_fullval/` | no_doppler の転移評価 |
| `abl_score_no_airabs_fullval/` | no_airabs の転移評価 |

各ディレクトリに `class_table.md`（クラス別の検出率・方向誤差）と
`dist_score.md`（距離誤差・GT距離帯別・3段仕分け）がある。

## 要点（詳細は §5-bis）

ラン揺れフロア **約1pt** に対し、重大tier再現率の変化:

**no_ground −10.9pt ＞ no_1r −8.1pt ＞ no_doppler −3.3pt ≫ no_airabs −0.4pt（差なし）**

効き目は **地面反射 ＞ 幾何減衰 ＞ ドップラー ≫ 大気吸収**。
事前登録では no_ground は「むしろ改善」と予想していたため、**最大の劣化は予想外**。

## サーバ側に残っている大物（本番前の片付けで扱いを分けること）

以下は容量が大きいためリポジトリには入れていない。**削除してよいもの/残すもの**を分ける。

| 対象 | 場所（is-server） | 扱い |
| --- | --- | --- |
| armデータセット ×4 | `out/dataset_outdoor_siren_v12_abl_*` | 各34GB。**削除可**（再生成できる） |
| arm用datasetsルート ×4 | `PSELDNet/PSELDNets/datasets_v12_abl_*` | **削除可** |
| arm用キャッシュ ×4 | `PSELDNet/PSELDNets/_hdf5_abl_*` | **削除可** |
| **学習済みckpt ×5** | `PSELDNets_logs/outdoor_siren_v12/runs/outdoor_siren_v12_abl_*`<br>`.../outdoor_siren_v12_sde_w3_seed2` | **残す**（再現に2.5時間かかる。特に seed2 はフロアの根拠） |
| **予測CSV ×6** | `PSELDNets_logs/.../runs/infer_*/val_all.csv` | **残す**（各8MB。再採点の入力） |

**注意**: 計画書 §9.8「本番開始前の片付け」は当初「確認runの成果物を削除する」と書いていたが、
本指示により **ckptと予測CSVは残す** よう改訂済み（2026-08-16）。
