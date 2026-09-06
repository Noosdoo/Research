#!/bin/bash
#SBATCH -J v2fgen
#SBATCH -p pro_6000
#SBATCH --gres=gpu:pro_6000:1
#SBATCH --qos=normal
#SBATCH -t 10:00:00
#SBATCH --requeue
#SBATCH -o v2fgen-%j.out
# 確定評価 v2 の最終学習データ生成（2026-09-07 準備・11 月に 1 回だけ実行）: plan（v2final_params.json のつまみ）→ 全量生成 18,000 本（24 シャード）
# → 距離GT（水平）→ datasets_v2final ルート → 前処理。実行計画 = md/design/確定評価v2_最終学習_実行計画_2026-09-07.md
# 書き込み先は out/dataset_outdoor_siren_v2final/ ・ $PS/datasets_v2final ・ $PS/_hdf5_v2final のみ。基準（v12）は guard で無変更を保証。
set -x
cd ~/research/outdoor_seld_e2e
PS=~/research/PSELDNet/PSELDNets
PY=$PS/.venv/bin/python
export PYTHONPATH=scripts:src
source ~/research/outdoor_seld_e2e/server_sde/_baseline_guard.sh
guard_record
# 発効チェック: params が fixed で、git の HEAD に入っていること（証跡）
$PY - <<'EOF'
import json, sys
P = json.load(open("md/design/v2final_params.json", encoding="utf-8"))
print("params status =", P.get("status"), "declared_at =", P.get("declared_at"))
sys.exit(0 if P.get("status") == "fixed" else 3)
EOF
[ $? -eq 0 ] || { echo "params が fixed でない。中止"; exit 3; }
git status --porcelain md/design/v2final_params.json | grep -q . && { echo "params が未コミット。中止"; exit 3; }
sha256sum md/design/v2final_params.json scripts/step10_v2final_plan.py scripts/_run_v2final_gen.py scripts/step19_dist_labels_v2final.py \
  scripts/step11_v16_render.py scripts/step11_v14_render.py scripts/step11_v13_render.py | tee v2final_sha256_job${SLURM_JOB_ID}.txt

$PY scripts/step10_v2final_plan.py | tail -4
N=$($PY -c "import json;print(json.load(open('md/design/v2final_params.json'))['N_ROWS_EXPECTED'])"); SH=24
STEP=$(( (N + SH - 1) / SH ))
pids=()
for i in $(seq 0 $((SH - 1))); do
  lo=$((i * STEP)); hi=$(( (i + 1) * STEP - 1 ))
  [ $hi -ge $N ] && hi=$((N - 1))
  $PY scripts/_run_v2final_gen.py --rows $lo-$hi > v2final_shard_$i.log 2>&1 &
  pids+=($!)
done
fail=0
for p in "${pids[@]}"; do wait $p || fail=1; done
[ $fail -eq 0 ] || { echo SHARD_FAILED; exit 1; }
ls out/dataset_outdoor_siren_v2final/foa | wc -l

# 距離GT（水平距離・プリロール対応版）
$PY scripts/step19_dist_labels_v2final.py | tail -2
ls out/dataset_outdoor_siren_v2final/metadata_dist | wc -l

# datasets_v2final ルート（リンク名は outdoor_siren_v12 = hydra の dataset 設定を変えないため）
ROOTDIR=$PS/datasets_v2final
HDF5DIR=$PS/_hdf5_v2final
[ "$ROOTDIR" != "$PS/datasets_v12" ] || { echo "基準ルートと同一"; exit 1; }
mkdir -p $ROOTDIR
cp -n $PS/datasets_v12/cls_indices_train.tsv $ROOTDIR/cls_indices_train.tsv
[ -e $ROOTDIR/outdoor_siren_v12 ] || ln -s ~/research/outdoor_seld_e2e/out/dataset_outdoor_siren_v2final $ROOTDIR/outdoor_siren_v12

cd $PS
$PY _preproc_emptyok12.py dataset=outdoor_siren_v12 dataset_type=dev \
    wav_format=.flac mode=extract_data num_workers=8 \
    paths.dataset_dir=$ROOTDIR paths.hdf5_dir=$HDF5DIR
$PY _preproc_sde.py mode=extract_data dataset=outdoor_siren_v12 \
    dataset_type=dev paths.dataset_dir=$ROOTDIR paths.hdf5_dir=$HDF5DIR
ls -la $HDF5DIR/label/*/dev/ || true

guard_verify || exit 1
echo V2FINAL_GEN_DONE
