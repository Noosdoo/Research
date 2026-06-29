# 屋外SELD プロジェクト（DynamicSound土台）

## 研究目的
難聴者の屋外歩行支援。後方など視覚で捉えにくい方向から接近する危険音（車両・自転車・緊急車両サイレン）を
**種類＋方向（SELD）**で検出して本人に伝える。装着型・FOA（単一アレイ）路線。基盤モデルは PSELDNets。

## 重要な前提（関連研究調査の結論 2026-06）
- **「屋外SELD生成器を初めて作る」は言えない**。既存がある：
  - **DynamicSound**（屋外物理シミュ：ドップラー/距離減衰/空気吸収ISO9613/地面反射）arXiv:2601.15433, `github.com/vlsi-nanocomputing/dynamic-sound`
  - WASN屋外SELD(2403.20130, モデル提案・simのみ)／装着型SELD(Wearable SELD 2202.08458, 6DoF 2403.01670, PAWS, SoundWatch 等)
- ＝ ツール・応用・屋外SELDは**ほぼ既出**。分野は混んでる。**「初/新規」は封印。**
- **唯一空いてそう**：「屋外SELDの sim-to-real で **どの物理が効くか** を体系的にablation」（DynamicSoundは物理だけ・SELD学習/評価なし）。要・全文確認＋指導教員相談。

## 方針（再配置）
- **物理は自作しない → DynamicSound を“使う”**。
- 自分の仕事＝**DynamicSound出力 → SELD教師データ化（FOA化＋DCASEラベル＋多音源シーン）** ＋
  **学習(PSELDNets finetune)→実録屋外でsim-to-real→「何が効くか」ablation** ＋ 難聴者応用文脈。

## 環境
- DynamicSound: `C:\Users\satos\research\dynamic-sound`（clone済・venv: `dynamic-sound/.venv` に `dynamic-sound 1.0.3`）
- 例: `dynamic-sound/examples/car_road.ipynb`（車が道を通過＝屋外物理全部入り）、`run_car.py`（実行用）
- API要点:
  - `ds.Path([[t, x,y,z, qw,qx,qy,qz], ...])` 時刻ごとの位置＋姿勢
  - `ds.Simulation(temperature, pressure, relative_humidity)`
  - `ds.microphones.MicrophoneArray(file_path, sample_rate, positions=[(x,y,z, q...),...])`
  - `ds.sources.AudioFile(filename, gain_db)` / `SineWave` / `WhiteNoise`
  - 地面反射＝z鏡像のpathをもう1ソースとして足す
  - `sim.add_microphone(path, microphone)` / `sim.add_source(path, source)` / `sim.run()`

## 既にやった関連作業（別フォルダ）
- `seld_move_ablation/edc/`：既存ツール＝室内の実証（EDC/T60: metu教室1.3s / SELDGEN pra 0.5s、metu音源最遠2.35m）。
  - ゼミ用：「既存SELD合成は室内 → 屋外用が要る」を示す材料。図=edc_compare.png、試聴=car_dry/metu/seldgen.wav。
- `seld_move_ablation/gen_outdoor_dataset.py`：自作の自由音場FOA生成MVP（物理なし）。→ DynamicSoundに置換 or 連携を検討。

## 検証済みの所見（2026-06-24・gitソース確認済）
- **car例5s完走OK**：`DynamicSound/run_car_5s.py` → `_out/car_5s.wav`（4ch/8192Hz/NaN無）。前回0バイトは20sが重く落ちただけ。
- **物理モデルの中身**（`_simulation.py` run()）：ドップラー（遅延時刻の二次方程式）＋1/r＋空気吸収ISO9613(FIR)＋地面反射（鏡像音源）。
- **マイクは無指向の点のみ**（`_microphones.py`）。Hedraphoneも無指向カプセル配置だけで**音響シャドウ無し**。→ ch間差は到達時間差(≤1samp)＋微小距離差のみ（実測 corr=0.997, lag≈0-1samp）。
- **FOA可否の結論**：
  - ❌ 近接4chアレイ→配列処理でFOA：**無理**（無指向点・2cm差・差が小さすぎ）。
  - ✅ **解析エンコードFOA**：原点に無指向マイク1個→物理済みモノラル取得→既知のDoA(az,el)からB-format(W/X/Y/Z)を式で生成。直接音と地面反射は別方向なので別々にエンコード。
  - 利点：SELDのDoA正解ラベルが誤差ゼロ。欠点：空間手がかりが理想的すぎ＝**sim-to-realギャップ**（実マイク指向性/頭部回折/個体差ゼロ）。卒論で限界明記。

## DynamicSound API の罠（実地で踏んだ）
- `ds.sources.AudioFile(..., loop=True)` が**既定**。短い音源（IR用clickなど）はループ再生される。IRや1発物は **`loop=False` 必須**。車の連続音源(26s/60s)は短時間レンダリングならループしないので無害。
- コンソール(cp932)で `≈` 等のprintはUnicodeErrorで落ちる→print内は ASCII で。

## 図・音の素材（_out/・SpatialScaper比較と同一音源）
- 同一音源=`SELD-Data-Generator/srir/ambisonics_dependencies/car_demos/car_dry_mono.wav`（metu/seldgen と共通）。
- `car_compare.png`：dry/metu(実測室)/seldgen(シミュ室)/DynamicSound(屋外) のスペクトログラム4面。屋外だけドップラーV＋通過の山。
- `edc_compare3.png` / `ir_compare3.png`：残響比較。既存=部屋(metu1.3s/seldgen0.5s)、DynamicSound=屋外(残響なし・反射1発)。※「T60≈0」は自由音場近似。実屋外は建物反射あり＝言い過ぎ注意。
- `car_physics.png`：距離減衰(1/r)とRMS包絡の一致＋ドップラー。
- スクリプト：`DynamicSound/{run_car_5s,viz_car,car_compare,edc_with_dynamicsound}.py`

## TODO（次の一手）
1. ~~car例を動かして出力確認~~ → 完了（上記）。
2. **解析エンコードFOAラッパ**を書く：①原点に無指向Microphone＋音源ごとに別sim → 物理済みモノラル取得、②Pathから各時刻のDoA算出、③B-format生成（音源/反射別）、④DCASEフォーマットのラベル(class, frame, az, el)同時出力。←自分の価値の中心。
3. 「どの物理が効くか」ablationの設計（Doppler/距離/空気/地面 on/off）。
4. 実録屋外テストセットの計画（sim-to-real用）。
5. 新規性の置き場所を指導教員と確定。
