## 処理内容
MultiPL-E を用いたコード生成結果に対して，  
1. AWS上のMultiPL-E評価サーバを用いて，評価結果を取得する．
2. 1で得られてあ評価結果に対して，分析&評価を行う.

## 0. 事前準備
- testコードの生成を行う． MultiPL-E/README.md のGenerationを行う．
    - automodel_vllm.pyでテストした

- 出力される1fileの仕様
```
1problem = 1file(.json.gz)としてファイルになっている．
.json.gzが持つ - data-keys: ['name', 'language', 'temperature', 'top_p', 'max_tokens', 'prompt', 'tests', 'completions', 'stop_tokens', 'tokens_info']
```

## 1. 生成されたコードを，AWS上のMultiPL-E評価結果の取得
- 以下のコマンドにより，生成されたコードをAWSのMultiPL-E 評価サーバで評価を行う．結果は，--output_base_dir/<input_dir_name> として保存．
```sh
cd completion_eval_analysis
python send_query_to_multipl_eval_server.py --query_input_dir <PATH_TO_COMPLETION_JSON_DIR> --output_base_dir <OUTPUT_BASE_DIR> --num_workers <NUM_WORKERS>

# ---------------------------------------------------------------------
# e.g. 
# make result dir of MultiPL-E evaluation
mkdir tmp_completion_eval_output

python send_query_to_multipl_eval_server.py --query_input_dir /app/data/code_server/multipl_e_completions/qwen3_think_completion_out/humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded/ --output_base_dir tmp_completion_eval_output --num_workers 10
```

- 参考: MultiPL-E AWSサーバの説明: evaluation_aws_lambda/

- AWSのMultiPL-E　評価用サーバは lang2url.jsonにまとまっている．--query_input_dirにより入力となる1fileの`language`のvalueがlang2url.jsonにない場合には適時，言語&AWS-URLの登録が必要

## 2. MultiPL-E評価結果の分析と評価
### pass@kを得る
```sh
cd completion_eval_analysis

python pass_k.py <MultiPL-Eコード評価結果Dirのパス>

# e.g.
# python pass_k.py ./tmp_completion_eval_output/humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded
# ->
# Dataset,Pass@k,Estimate,NumProblems,MinCompletions,MaxCompletions
# humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded,1,0.7291666666666666,156,20,20
# humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded,10,0.8044348929232235,156,20,20
# humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded,100,1.0,156,20,20
```
