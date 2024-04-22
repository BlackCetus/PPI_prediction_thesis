#!/bin/bash
#
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=10
#SBATCH --gpus-per-task=1
#SBATCH --partition=shared-gpu
#SBATCH --exclude=gpu01.exbio.wzw.tum.de
#SBATCH --time=2-0
#SBATCH --error=/nfs/home/students/t.reim/bachelor/pytorchtest/slurm/err/%j.err
#SBATCH --output=/nfs/home/students/t.reim/bachelor/pytorchtest/slurm/out/%j.out
#SBATCH --job-name=ppi-attention
#SBATCH --mem-per-gpu=40G

srun python /nfs/home/students/t.reim/bachelor/pytorchtest/main.py \
-data gold_stand \
-model crossattention \
-lr 0.001 \
-max 1000 \
-epoch 20 \
-batch 32 \
-sub \
-subsize 0.5 \
-emb \
-emb_dim 1280 \
-wandb \
-heads 8 \
-dropout 0.2 \
-run crossatt_confpred_0_9
