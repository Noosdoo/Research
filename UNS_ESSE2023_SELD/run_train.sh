#!/bin/bash
#SBATCH --reservation=1263
#SBATCH -p A100.80gb
#SBATCH --gres=gpu:resv:1
#SBATCH -J SELD_UNET
#SBATCH -o log.%J
#SBATCH --time 00-07:00:00

nvidia-smi

docker run \
    --gpus device=$(mig-list) \
    --shm-size=32g \
    --ulimit memlock=-1 \
    --ulimit stack=67108864 \
    --rm \
    -v ~:/workspace/mounted \
    nvcr.io/nvidia/pytorch:23.03-py3 \
    bash -c "pip install librosa soundfile -q && \
             cd /workspace/mounted/UNS_ESSE2023_SELD && \
             python uns_esse2023_seld.py --mode train"
