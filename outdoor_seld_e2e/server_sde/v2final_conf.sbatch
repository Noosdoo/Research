#!/bin/bash
#SBATCH -J v2fconf
#SBATCH -p pro_6000
#SBATCH --gres=gpu:pro_6000:1
#SBATCH --qos=normal
#SBATCH -t 03:00:00
#SBATCH -o v2fconf-%j.out
# 確定評価 v2（fold20 core 1,200 本・1 回だけ・介入なし）: 選んだ因果 ft ckpt（V2FINAL_CKPT）で fold20 を因果推論 → conf_all.csv → v1 と同じ採点器
# （_v12_conf_notify_server.py: v3.3/v3.4 ＋ B2 個票）で v1 と直接比較。fold20 は v1 の確定評価セット（outdoor_siren_v12_conf・マイク 1.5 m）を
# そのまま使う（生成しない）。装着高さ入力は表なし・既定 1.5 m。停止規則: 本ジョブは 1 回だけ。結果が悪くても差し替えない。
# 使い方: V2FINAL_CKPT=<選んだ ckpt の絶対パス> sbatch server_sde/v2final_conf.sbatch
set -ex
PS=$HOME/research/PSELDNet/PSELDNets
E2E=$HOME/research/outdoor_seld_e2e
PY=$PS/.venv/bin/python
cd $E2E
source $E2E/server_sde/_baseline_guard.sh
guard_record
PARAMS=$E2E/md/design/v2final_params.json
$PY -c "import json,sys;P=json.load(open('$PARAMS'));sys.exit(0 if P.get('status')=='fixed' else 3)" || { echo "params が fixed でない"; exit 3; }
[ -n "$V2FINAL_CKPT" ] && [ -f "$V2FINAL_CKPT" ] || { echo "V2FINAL_CKPT（選んだ因果 ft の ckpt）を渡す"; exit 3; }
[ -e $PS/datasets_v12/outdoor_siren_v12_conf ] || { echo "fold20 の確定評価セットが無い（v12_conf_all.sbatch で作られたもの）"; exit 1; }
OUTNAME=infer_v2final_conf
[ -d $HOME/PSELDNets_logs/outdoor_siren_v12/runs/$OUTNAME ] && { echo "既に確定評価を 1 回実行済み（$OUTNAME）。停止規則により再実行しない"; exit 4; }
sha256sum $V2FINAL_CKPT $PARAMS scripts/_causal_infer_v17.py server_sde/_causal_infer_v17.py server_sde/height_patch.py scripts/_v12_conf_notify_server.py | tee v2final_conf_sha256_job${SLURM_JOB_ID}.txt
git rev-parse HEAD | tee -a v2final_conf_sha256_job${SLURM_JOB_ID}.txt

cd $PS
cp $E2E/server_sde/height_patch.py $PS/height_patch.py
cp $E2E/server_sde/causal_patch.py $PS/causal_patch.py
cp $E2E/server_sde/_causal_infer_v17.py $PS/_causal_infer_v17.py
export PS
export SDE_W_DIST=3.0
export SDE_DIST_MODE=log
export CAUSAL_KMIN=40
export CAUSAL_REPEAT=2
export CAUSAL_SEED=0
export HEIGHT_COND=1
export HEIGHT_TABLE=""          # fold20 は全クリップ 1.5 m
export HEIGHT_DEFAULT=1.5
export HEIGHT_JITTER=0
export HEIGHT_OFFSET=0
export CAUSAL_CKPT=$V2FINAL_CKPT
export CAUSAL_DSDIR=$PS/datasets_v12
export CAUSAL_PREFIX=fold20_
export CAUSAL_OUT=$OUTNAME
unset CAUSAL_GLOB
.venv/bin/python $PS/_causal_infer_v17.py

# 連結 → v1 と同じ採点器
SUB=$HOME/PSELDNets_logs/outdoor_siren_v12/runs/$OUTNAME/submissions
[ -d "$SUB" ] || SUB=$(ls -d $HOME/PSELDNets_logs/outdoor_siren_v12/runs/$OUTNAME/*/submissions 2>/dev/null | head -1)
python3 - "$SUB" <<'EOF'
import sys, glob, os
sub = sys.argv[1]
out = os.path.join(os.path.dirname(sub), "conf_all.csv")
with open(out, "w") as w:
    for f in sorted(glob.glob(os.path.join(sub, "*.csv"))):
        clip = os.path.splitext(os.path.basename(f))[0]
        for line in open(f):
            line = line.strip()
            if line:
                w.write(clip + "," + line + "\n")
print("wrote", out, sum(1 for _ in open(out)))
EOF
cd $E2E
PYTHONPATH=scripts:src $PY scripts/_v12_conf_notify_server.py \
  $(dirname $SUB)/conf_all.csv \
  $E2E/out/v2final_conf_notify_v33 $E2E/out/v2final_conf_notify_v34
guard_verify || exit 1
echo V2FINAL_CONF_DONE
