#!/bin/bash
#SBATCH -J v2fcausal
#SBATCH -p pro_6000
#SBATCH --gres=gpu:pro_6000:1
#SBATCH --qos=normal
#SBATCH -t 12:00:00
#SBATCH --requeue
#SBATCH --open-mode=append
#SBATCH -o v2fcausal-%j.out
# 確定評価 v2 の因果 ft = v17b と同一（起点 = v2final 基準学習 ep099 / KMIN40 / REPEAT2 / lr1e-4・150ep・StepLR90 / 20ep 毎に全保存 / 高さ入力・ゆらぎ 0.10）。
# 保存 ckpt 全部を因果推論（v12 fold2 1.5 m ＝ 表なし、self val ＝ v2final fold2）→ 統一採点器で ckpt を選ぶ（規則 = 至近帯の距離誤差・実行計画 §4）。
# ⚠️ fold20（確定評価）はここでは推論しない。ckpt を 1 つ選んで v2final_conf.sbatch で 1 回だけ。
set -ex
PS=$HOME/research/PSELDNet/PSELDNets
E2E=$HOME/research/outdoor_seld_e2e
cd $PS
source $E2E/server_sde/_baseline_guard.sh
guard_record
ROOTDIR=$PS/datasets_v2final
HDF5DIR=$PS/_hdf5_v2final
EXP=outdoor_siren_v2final_causal_ft
PARAMS=$E2E/md/design/v2final_params.json
$PS/.venv/bin/python -c "import json,sys;P=json.load(open('$PARAMS'));sys.exit(0 if P.get('status')=='fixed' else 3)" || { echo "params が fixed でない"; exit 3; }
JIT=$($PS/.venv/bin/python -c "import json;print(json.load(open('$PARAMS'))['HEIGHT_JITTER_TRAIN'])")
CK=$HOME/PSELDNets_logs/outdoor_siren_v12/runs/outdoor_siren_v2final_sde_w3/checkpoints/epoch_099.ckpt
[ -f "$CK" ] || CK=$(ls $HOME/PSELDNets_logs/outdoor_siren_v12/runs/outdoor_siren_v2final_sde_w3/checkpoints/epoch_*.ckpt | head -1)
ls -l $CK
export SDE_W_DIST=3.0
export SDE_DIST_MODE=log
export CAUSAL_KMIN=40
export CAUSAL_REPEAT=2
export CAUSAL_SEED=0
export HEIGHT_COND=1
export HEIGHT_TABLE=$E2E/out/dataset_outdoor_siren_v2final/plan/assignment_v2final.csv
export HEIGHT_JITTER=$JIT
export HEIGHT_DEFAULT=1.5
export HEIGHT_OFFSET=0
CFG=configs/experiment/outdoor_siren_v12_hp_clr1e-4e150.yaml
[ -f "$CFG" ] || .venv/bin/python $E2E/server_sde/hp_make_configs.py clr1e-4e150
grep -n "lr\|max_epochs\|step_size" $CFG
cp $E2E/server_sde/height_patch.py $PS/height_patch.py
cp $E2E/server_sde/causal_patch.py $PS/causal_patch.py
cp $E2E/server_sde/_train_causal17.py $PS/_train_causal17.py
cp $E2E/server_sde/_causal_infer_v17.py $PS/_causal_infer_v17.py
sha256sum $CK $PS/height_patch.py $PS/causal_patch.py $PS/_train_causal17.py $PS/_causal_infer_v17.py $CFG $PARAMS | tee $E2E/v2final_causal_sha256_job${SLURM_JOB_ID}.txt

LAST=$HOME/PSELDNets_logs/outdoor_siren_v12/runs/$EXP/checkpoints/last.ckpt
RESUME=""
[ -f "$LAST" ] && RESUME="ckpt_path=$LAST"
echo "job=$SLURM_JOB_ID node=$(hostname) gpu=$(nvidia-smi -L | head -1) resume=${RESUME:-new}"

.venv/bin/python $PS/_train_causal17.py \
  experiment=outdoor_siren_v12_hp_clr1e-4e150 \
  model.kwargs.pretrained_path=$CK \
  experiment_name=$EXP \
  paths.log_dir=$HOME/PSELDNets_logs \
  paths.dataset_dir=$ROOTDIR paths.hdf5_dir=$HDF5DIR \
  callbacks.model_checkpoint.save_top_k=-1 \
  callbacks.model_checkpoint.every_n_epochs=20 \
  $RESUME

export PS
export HEIGHT_JITTER=0
export CAUSAL_PREFIX=fold2_
for ck in $(ls $HOME/PSELDNets_logs/outdoor_siren_v12/runs/$EXP/checkpoints/epoch_*.ckpt | grep -v -- "-v") $HOME/PSELDNets_logs/outdoor_siren_v12/runs/$EXP/checkpoints/last.ckpt; do
  e=$(basename $ck .ckpt); [ "$e" = "last" ] && e=epoch_149
  export CAUSAL_CKPT=$ck
  export HEIGHT_OFFSET=0
  export CAUSAL_DSDIR=$PS/datasets_v12
  export CAUSAL_OUT=infer_v2finalft_${e/epoch_/e}_v12causal
  unset CAUSAL_GLOB
  export HEIGHT_TABLE=""      # v12 val は全クリップ 1.5 m（表を外す。v17 の教訓）
  .venv/bin/python $PS/_causal_infer_v17.py
  export HEIGHT_TABLE=$E2E/out/dataset_outdoor_siren_v2final/plan/assignment_v2final.csv
  export CAUSAL_DSDIR=$ROOTDIR
  export CAUSAL_OUT=infer_v2finalft_${e/epoch_/e}_selfcausal
  .venv/bin/python $PS/_causal_infer_v17.py
done
export HEIGHT_OFFSET=0
guard_verify || exit 1
echo V2FINAL_CAUSAL_DONE
