#!/bin/sh

HOSTNAME=`hostname -s`

echo "[${HOSTNAME}] OMPI_COMM_WORLD_SIZE=${OMPI_COMM_WORLD_SIZE}"
echo "[${HOSTNAME}] OMPI_COMM_WORLD_RANK=${OMPI_COMM_WORLD_RANK}"
echo "[${HOSTNAME}] OMPI_COMM_WORLD_LOCAL_SIZE=${OMPI_COMM_WORLD_LOCAL_SIZE}"
echo "[${HOSTNAME}] OMPI_COMM_WORLD_LOCAL_RANK=${OMPI_COMM_WORLD_LOCAL_RANK}"
echo "[${HOSTNAME}] OMPI_COMM_WORLD_NODE_RANK=${OMPI_COMM_WORLD_NODE_RANK}"

export MACHINE_RANK=$OMPI_COMM_WORLD_RANK
echo "[${HOSTNAME}] MACHINE_RANK=$MACHINE_RANK"

export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
export NCCL_DEBUG=WARN

model_name="/work/go25/share/base_model/Qwen3-235B-A22B-Thinking-2507-FP8"

# Rayクラスタの設定
if [[ "$OMPI_COMM_WORLD_RANK" == "0" ]]; then
    echo "[${HOSTNAME}] Starting Ray head node..."
    ray start --head --port=$MASTER_PORT --num-gpus=$NUM_GPUS_PER_NODE
    sleep 10
else
    echo "[${HOSTNAME}] Starting Ray worker node..."
    ray start --address=$MASTER_ADDR:$MASTER_PORT --num-gpus=$NUM_GPUS_PER_NODE
    sleep 10
fi

# Ray クラスタの状態を確認
echo "[${HOSTNAME}] Ray cluster status:"
ray status

if [[ "$OMPI_COMM_WORLD_RANK" == "0" ]]; then
    echo "[${HOSTNAME}] Launching vLLM server on master node..."
    vllm serve $model_name \
        --tensor-parallel-size $NUM_GPUS_PER_NODE \
        --pipeline-parallel-size $NUM_NODES \
        --distributed-executor-backend ray \
        --enable-reasoning \
        --reasoning-parser deepseek_r1 \
        --host 0.0.0.0 \
        --port 8000 \
        --max-num-batched-tokens 8096 \
        --gpu-memory-utilization 0.8 \
        --max-model-len 16192 &

    echo "[${HOSTNAME}] Waiting for the vLLM server to be ready..."
    
    timeout=300         # 最大待機時間（秒）。5分。
    interval=5          # 確認間隔（秒）
    elapsed_time=0

    while [ $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health) -ne 200 ] && [ $elapsed_time -lt $timeout ]; do
        echo "Server not ready yet. Waited ${elapsed_time}s. Retrying in ${interval}s..."
        sleep $interval
        elapsed_time=$((elapsed_time + interval))
    done

    if [ $elapsed_time -ge $timeout ]; then
        echo "Error: Server did not start within the ${timeout}s timeout. Aborting."
        exit 1 
    fi


    echo "[${HOSTNAME}] Server is ready! Running the client..."
    python3 ./MultiPL-E/automodel_vllm_miyabi_client.py \
        --api-base http://localhost:8000/v1 \
        --name $model_name \
        --root-dataset humaneval \
        --lang rs \
        --temperature 0.2 \
        --batch-size 20 \
        --completion-limit 20 \
        --output-dir-prefix ./MultiPL-E/tutorial


    echo "[${HOSTNAME}] Shutting down vLLM server (PID $VLLM_PID)..."
    kill $VLLM_PID
    KILLED_SUCCESSFULLY=false
    for i in {1..10}; do
        if ! ps -p $VLLM_PID > /dev/null; then
            KILLED_SUCCESSFULLY=true
            break
        fi
        sleep 1
    done

    if [ "$KILLED_SUCCESSFULLY" = true ]; then
        echo "[${HOSTNAME}] vLLM server shut down successfully."
    else
        echo "[${HOSTNAME}] vLLM server (PID $VLLM_PID) might not have shut down properly. Forcing kill."
        kill -9 $VLLM_PID
    fi

    qdel ${PBS_JOBID}

else
    echo "[${HOSTNAME}] Worker node. Waiting for tasks from the Ray cluster."
fi

echo "[${HOSTNAME}] Script execution finished."

