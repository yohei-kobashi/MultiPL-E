# -*- coding: utf-8 -*-

# Multip lE 形式の生成コードを，Multipl-E 評価サーバに投げ，評価結果を受け取る．

# Command
# python send_query_to_multipl_eval_server.py --query_input_dir <PATH_TO_COMPLETION_JSON_DIR> --output_base_dir <OUTPUT_BASE_DIR> --num_workers <NUM_WORKERS>
# e.g. 
# python send_query_to_multipl_eval_server.py --query_input_dir /app/data/code_server/multipl_e_completions/qwen3_think_completion_out/humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded/ --output_base_dir tmp_completion_eval_output --num_workers 10

import sys
from pathlib import Path
import logging, logging.config
import pprint
import time
import gzip
import json
import requests 
import argparse

from concurrent.futures import ProcessPoolExecutor


class SendQueryToMultiEvalServer():
    def __init__(self, use_multipl_eval_server=True):
        self.log = logging.getLogger(__name__)
        self.use_multipl_eval_server = use_multipl_eval_server
        if self.use_multipl_eval_server is True:
            self.lang2url = None
        else: 
             self.sv_url = None

    def set_lang2url(self, url_json_path):
        with open(url_json_path, "r") as f:
            self.lang2url = json.load(f)["urls"]
        self.log.debug(f"set lang2url using: {url_json_path}")

    def send_query(self, query_d:dict):
        """
        Args:
            query_d `dict`: {
                        (Required) "language", "prompt", "completions", "tests",
                        }
        Returns:
            `dict`: {
                language: `str`,
                server_status: `str`,
                server_err: `str`,
                temperature: `float`,
                results: `list`[dict] | None 各completionに対応する評価結果が格納される.
                (<Optional>)
                name: `str`,
                prompt: `str`,
                tests: `str`,
                stop_tokens: `list`[str],
                top_p: `float`,
                max_tokens: `int`,

                # 現状, return含めない情報
                # tokens_info: `list`[dict],
                # completions: `list`[str]
            }
        """
        headers = {'Content-Type': 'application/json'}
        query_lang = query_d.get("language", None)
        if self.use_multipl_eval_server is True:
            base_url = self.lang2url.get(query_lang, None)
        else:
            base_url = self.sv_url
        if base_url is None:
            self.log.error(f"Error: No server URL for language: {query_lang}")
            return -1
        _url = f"{base_url}/evaluate"

        
        # --------------------------- Return Info TODO: please add key-value if you want other info.
        language = query_lang
        server_status = None
        server_err = None
        temperature = None
        results = None

        # (Optional)
        name = query_d.get("name", None)
        prompt = query_d.get("prompt", None)
        stop_tokens = query_d.get("stop_tokens", None)
        top_p = query_d.get("top_p", None)
        max_tokens = query_d.get("max_tokens", None)
        tokens_info = query_d.get("tokens_info", None)


        # --------------------------- Request Sucess
        try:
            res = requests.post(url=_url, headers=headers, data=json.dumps(query_d), timeout=30)
            self.log.debug(f"res:{res}")

            # Case: Success
            if res.status_code == requests.codes.ok:
                server_status = 'request_ok'
                res_dict = res.json() 
                # -> Keys: {language, prompt, name, stop_tokens, temperature, top_p, 
                #       max_tokens, tokens_info(list[]), 
                #       results: [{
                #           program, stdout, stderr, exit_code, status:'OK', timestamp
                #       }]
                # self.log.debug(f"res_dict: {res_dict}")
                results = res_dict.get("results", [])

            # Case: Query Error
            else:
                server_status = 'request_error'
                server_err = res.text

        # --------------------------- Request Error
        except requests.RequestException as e:
            server_status = 'request_exception'
            server_err = str(e)
            self.log.error(f"RequestException: {server_err}")

        return {
            "language": language,
            "server_status": server_status,
            "server_err": server_err,
            "temperature": temperature,
            "results": results,
            # (Optional Infos)
            "name": name,
            "prompt": prompt,
            "tests": query_d.get("tests", None),
            "stop_tokens": stop_tokens,
            "top_p": top_p,
            "max_tokens": max_tokens,
            # "completions": query_d.get("completions", None),
            # "tokens_info": tokens_info,
        }

    def process_json(self, inputs: tuple):
        """
        Args:
            inputs (tuple): (json_file_path, output_dir_path)
        """
        json_path, output_dir = inputs
        with open_json(json_path, "r") as f:
                data = json.load(f)
        query_result = self.send_query(data)
        output_path = Path(output_dir) / json_path.name

        if '.gz' in json_path.name:
            # output as json.gz
            with gzip.open(output_path, "wt") as f:
                json.dump(query_result, f, ensure_ascii=False)
        else:
            # output as json
            with open_json(output_path, "w") as f:
                json.dump(query_result, f, ensure_ascii=False)


    def process_dir(self, input_dir:str, output_dir:str, num_workers=1):
        """input_dir に含まれるcompletionコードを持つjson/json.gzを使用し，multipl-e 評価サーバに投げ，結果を output_dir に保存する．
        """

        # -----------------------------------------------------------------------------------------------------------
        # Get evaluation results for the generated completions

        # create output dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        s_time = time.time()
        json_paths = list(Path(input_dir).glob("*.json")) + list(Path(input_dir).glob("*.json.gz"))  # list[Path]
        print(f"start evaluation (query to Multipl-E server). process_dir: {input_dir}, num: {len(json_paths)}")

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = executor.map(self.process_json, [(json_file, output_dir) for json_file in json_paths])
            for _ in futures:
                pass

        elapsed_time = time.time() - s_time

        print(f"get evaluation done. total num: {len(json_paths)} output_dir: {output_dir} elapsed_time: {elapsed_time:.2f} sec")

        # ------------------------------------------------------------------------------------------------------------
        # (Optional run pass@k eval)



# --------------------- Utils ----------------------------
def open_json(fpath: Path, mode: str):
    return gzip.open(fpath, mode + "t") if fpath.suffix == ".gz" else open(fpath, mode)


# --------------------- main -----------------------------
def get_eval_results():
    parser = argparse.ArgumentParser(description="Process input and output base directories.")
    
    # 必須の引数
    parser.add_argument(
        "--query_input_dir",
        required=True,
        help="Path to the query input directory"
    )
    parser.add_argument(
        "--output_base_dir",
        required=True,
        help="Path to the output base directory. <output_base_dir>/<query_input_dir>"
    )
    parser.add_argument(
        "--num_workers",
        type=int,
        default=1,
        help="Number of worker processes to use"
    )
    args = parser.parse_args()

    RequestSVCtr = SendQueryToMultiEvalServer()
    RequestSVCtr.set_lang2url("./lang2url.json")
    RequestSVCtr.process_dir(args.query_input_dir, args.output_base_dir + "/" + Path(args.query_input_dir).name, num_workers=args.num_workers)

    


def test():
    """ 単一ファイルのみをを評価するテストコード"""
    input_json_dir = None # PATH_TO_COMPLETION_JSON_DIR

    jsonl_paths = list(Path(input_json_dir).glob("*.json")) + list(Path(input_json_dir).glob("*.json.gz"))  # list[Path]
    i0_path = jsonl_paths[0]
    print(f"i0_path: {i0_path}, {type(i0_path)}")

    with open_json(i0_path, "r") as f:
        data = json.load(f)
    print(f"data-keys: {list(data.keys())}")    # -> name, language, prompt, tests, completions, top_p, max_tokens, stop_tokens, tokens_info
    print(f"data['completions'] len: {len(data['completions'])}")

    RequestSVCtr = SendQueryToMultiEvalServer()
    RequestSVCtr.set_lang2url("./lang2url.json")

    query_result = RequestSVCtr.send_query(data)
    print(f"query_result: {query_result}")
    print(f"query_result keys: {list(query_result.keys())}")

if __name__ == "__main__":
    get_eval_results()

    # test()  # debug