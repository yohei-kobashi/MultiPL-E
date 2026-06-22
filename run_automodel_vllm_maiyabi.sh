#!/bin/sh

# Miyabi job options
#PBS -q regular-g
#PBS -l select=1:mpiprocs=1
#PBS -l walltime=00:30:00 
#PBS -W group_list=go25
#PBS -j oe

module purge
module load cuda/12.8
module load cudnn/9.10.1.4
module load nvidia/25.3
module load nv-hpcx/25.3

export CC=gcc
export CXX=g++

cd ${PBS_O_WORKDIR}

source ~/miniconda3/etc/profile.d/conda.sh
conda activate inference_env

unset OMPI_MCA_mca_base_env_list
cd MultiPL-E
#mkdir tutorial

export CUDA_VISIBLE_DEVICES=0
export NCCL_IB_DISABLE=1
python3 automodel_vllm_miyabi.py \
    --name ../base_model/Qwen3-4B \
    --num-gpus 1 \
    --root-dataset humaneval \
    --lang rs \
    --temperature 0.2 \
    --batch-size 20 \
    --completion-limit 20 \
    --output-dir-prefix tutorial
