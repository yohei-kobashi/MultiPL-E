#!/bin/bash
#PBS -q short-g
#PBS -l select=1
#PBS -W group_list=go25
#PBS -j oe
module purge
module load cuda/12.8
module load cudnn/9.10.1.4
module load nvidia/25.3
module load nv-hpcx/25.3
source /work/gj26/b20048/miniconda3/etc/profile.d/conda.sh
conda activate inference_env
export CUDA_VISIBLE_DEVICES=0
export PATH="$CONDA_PREFIX/bin:/opt/rh/gcc-toolset-14/root/usr/bin:$PATH"

export CC=/opt/rh/gcc-toolset-14/root/usr/bin/gcc
export CXX=/opt/rh/gcc-toolset-14/root/usr/bin/g++
export TRITON_CC="$CC"
export TRITON_CXX="$CXX"
export CUDAHOSTCXX="$CXX"

export PYTHONNOUSERSITE=1
cd MultiPL-E

MODEL="/work/go25/share/model/Qwen3-Coder-30B-A3B-Instruct-mcore-hf_code_trans_489pairs_0826"
TEMP=0.2
BATCH=20
N_SAMPLES=20
OUT_ROOT="tutorial_0826"

DATASETS_AND_LANGS=(
  "humaneval,adb"
  "humaneval,clj"
  "humaneval,cpp"
  "humaneval,cs"
  "humaneval,d"
  "humaneval,dart"
  "humaneval,elixir"
  "humaneval,go"
  "humaneval,hs"
  "humaneval,java"
  "humaneval,jl"
  "humaneval,js"
  "humaneval,lua"
  "humaneval,ml"
  "humaneval,php"
  "humaneval,pl"
  "humaneval,r"
  "humaneval,rb"
  "humaneval,rkt"
  "humaneval,rs"
  "humaneval,scala"
  "humaneval,sh"
  "humaneval,swift"
  "humaneval,ts"
  "mbpp,adb"
  "mbpp,clj"
  "mbpp,cpp"
  "mbpp,cs"
  "mbpp,d"
  "mbpp,elixir"
  "mbpp,go"
  "mbpp,hs"
  "mbpp,java"
  "mbpp,jl"
  "mbpp,js"
  "mbpp,lua"
  "mbpp,ml"
  "mbpp,php"
  "mbpp,pl"
  "mbpp,r"
  "mbpp,rb"
  "mbpp,rkt"
  "mbpp,rs"
  "mbpp,scala"
  "mbpp,sh"
  "mbpp,swift"
  "mbpp,ts"
)

for pair in "${DATASETS_AND_LANGS[@]}"; do
  IFS=',' read -r DATASET LANG <<< "$pair"
  echo "[$(date +%T)] Generating for dataset=${DATASET}, lang=${LANG}"
  python automodel_vllm.py --name "$MODEL" --root-dataset "$DATASET" --lang "$LANG" --temperature "$TEMP" --batch-size "$BATCH" --completion-limit "$N_SAMPLES" --output-dir-prefix "$OUT_ROOT" --enforce-eager
done