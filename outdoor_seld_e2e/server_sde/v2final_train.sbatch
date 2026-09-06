#!/bin/bash
#SBATCH -J v2ftrain
#SBATCH -p pro_6000
#SBATCH --gres=gpu:pro_6000:1
#SBATCH --qos=normal
#SBATCH -t 06:00:00
#SBATCH --requeue
#SBATCH --open-mode=append
#SBATCH -o v2ftrain-%j.out
# 確定評価 v2 の基準学習 = v17b レシピそのまま（w3: init=v12_init_from_run3ep84 / W_DIST=3 / log / batch8 / lr3e-4 / StepLR60 / 100ep
# ＋ 装着高さの入力 HEIGHT_COND=1・学習ゆらぎ 0.10 m）。データだけ datasets_v2final。11 月に 1 回だけ。requeue 時は last.ckpt から再開。
set -ex
source ~/research/outdoor_seld_e2e/server_sde/_baseline_guard.sh
guard_record

PS=~/research/PSELDNet/PSELDNets
E2E=$HOME/research/outdoor_seld_e2e
ROOTDIR=$PS/datasets_v2final
HDF5DIR=$PS/_hdf5_v2final
EXP=outdoor_siren_v2final_sde_w3
PARAMS=$E2E/md/design/v2final_params.json
[ -d "$ROOTDIR" ] || { echo "datasets_v2final が無い（先に v2final_gen.sbatch）"; exit 1; }
[ "$ROOTDIR" != "$PS/datasets_v12" ] || { echo "基準ルートと同一"; exit 1; }
$PS/.venv/bin/python -c "import json,sys;P=json.load(open('$PARAMS'));sys.exit(0 if P.get('status')=='fixed' else 3)" || { echo "params が fixed でない"; exit 3; }
JIT=$($PS/.venv/bin/python -c "import json;print(json.load(open('$PARAMS'))['HEIGHT_JITTER_TRAIN'])")
cd $PS
cp $E2E/server_sde/height_patch.py $PS/height_patch.py
cp $E2E/server_sde/_train_sde17.py $PS/_train_sde17.py
sha256sum $PS/height_patch.py $PS/_train_sde17.py $HOME/PSELDNets_logs/v12_init_from_run3ep84.ckpt $PARAMS | tee $E2E/v2final_train_sha256_job${SLURM_JOB_ID}.txt
export SDE_INIT_CKPT=$HOME/PSELDNets_logs/v12_init_from_run3ep84.ckpt
export SDE_W_DIST=3.0
export SDE_DIST_MODE=log
export HEIGHT_COND=1
export HEIGHT_TABLE=$E2E/out/dataset_outdoor_siren_v2final/plan/assignment_v2final.csv
export HEIGHT_JITTER=$JIT
export HEIGHT_DEFAULT=1.5
export HEIGHT_OFFSET=0

LAST=$HOME/PSELDNets_logs/outdoor_siren_v12/runs/$EXP/checkpoints/last.ckpt
RESUME=""
[ -f "$LAST" ] && RESUME="ckpt_path=$LAST"
echo "job=$SLURM_JOB_ID node=$(hostname) gpu=$(nvidia-smi -L | head -1) resume=${RESUME:-new} jitter=$JIT"

.venv/bin/python _train_sde17.py \
  experiment=outdoor_siren_v12 \
  experiment_name=$EXP \
  paths.log_dir=$HOME/PSELDNets_logs \
  paths.dataset_dir=$ROOTDIR paths.hdf5_dir=$HDF5DIR \
  model.kwargs.pretrained_path=$SDE_INIT_CKPT \
  $RESUME

ck=$(ls $HOME/PSELDNets_logs/outdoor_siren_v12/runs/$EXP/checkpoints/epoch_*.ckpt | head -1)
echo "using ckpt: $ck"
.venv/bin/python - "$ck" <<'EOF'
import sys, torch
sd = torch.load(sys.argv[1], map_location="cpu", weights_only=False)["state_dict"]
keys = [k for k in sd if "h_mlp" in k]
assert keys, "h_mlp が ckpt に無い"
print("[height] h_mlp keys:", len(keys))
EOF
guard_verify || exit 1
echo V2FINAL_TRAIN_DONE
