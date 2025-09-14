# Miyabi job options
#PBS -q regular-g
#PBS -l select=8:mpiprocs=1
#PBS -l walltime=00:30:00 
#PBS -W group_list=go25
#PBS -j oe

module purge
module load cuda/12.8
module load cudnn/9.10.1.4
module load nvidia/25.3
module load nv-hpcx/25.3

ulimit -n 65536

export CC=gcc
export CXX=g++

export CUDA_VISIBLE_DEVICES=0

export NUM_NODES=`wc -l $PBS_NODEFILE | awk '{print $1}'`
export NUM_GPUS_PER_NODE=1
export NUM_GPUS=$(( ${NUM_GPUS_PER_NODE} * ${NUM_NODES} ))

export MASTER_ADDR=`head -1 $PBS_NODEFILE`
export MASTER_PORT=6379

cd ${PBS_O_WORKDIR}

source ~/miniconda3/etc/profile.d/conda.sh
conda activate inference_env

unset OMPI_MCA_mca_base_env_list

echo "NUM_NODES: $NUM_NODES"
echo "NUM_GPUS_PER_NODE: $NUM_GPUS_PER_NODE"
echo "NUM_GPUS: $NUM_GPUS"
echo "MASTER_ADDR: $MASTER_ADDR"
nvidia-smi

mpirun --np $NUM_NODES \
    --hostfile $PBS_NODEFILE \
    -bind-to none -map-by node \
    -x MASTER_ADDR \
    -x MASTER_PORT \
    -x PATH \
    -x LD_LIBRARY_PATH \
    -x CC \
    -x CXX \
    -x NUM_NODES \
    -x NUM_GPUS_PER_NODE \
    -x NUM_GPUS \
    -x CUDA_VISIBLE_DEVICES \
    -x RAY_CGRAPH_get_timeout=600 \
    bash ./MultiPL-E/helper_ray_vllm_miyabi.sh