# -*- coding: utf-8 -*-
# python pass_k.py <MultiPL-Eコード評価結果Dirのパス>

# e.g.
# python pass_k.py ./tmp_completion_eval_output/humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded
# ->
# Dataset,Pass@k,Estimate,NumProblems,MinCompletions,MaxCompletions
# humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded,1,0.7291666666666666,156,20,20
# humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded,10,0.8044348929232235,156,20,20
# humaneval-rs-Qwen_Qwen3_235B_A22B_Thinking_2507_FP8-0.2-reworded,100,1.0,156,20,20

"""

This script calculates pass@k. It receives a list of directories as its
argument, and calculates the mean pass@k for the set of problems in each
directory. It checks that all results in a directory were generated at the same
temperature. It calculates pass@1 for temperature 0.2 and both pass@10 and
pass@100 for temperature 0.8.

The output has the following columns:

- Dataset: the name of a directory
- Pass@k: the value of k
- Estimate: the mean pass@k for the problems in the directory
- NumProblems: the number of problems in the directory
- MinCompletions: the minimum number of completions for any problem in the 
  directory
- MaxCompletions: the maximum number of completions for any problem in the
  directory
"""
import numpy as np
from pathlib import Path
import itertools
import argparse
import json
import gzip
# from multipl_e.util import gunzip_json, eprint    # change


def estimator(n: int, c: int, k: int) -> float:
    """
    Calculates 1 - comb(n - c, k) / comb(n, k).
    """
    if n - c < k:
        return 1.0
    return 1.0 - np.prod(1.0 - k / np.arange(n - c + 1, n + 1))


def for_file(path: Path):
    if path.suffix == ".gz":
        with gzip.open(path, 'rt') as f:    # change
            data = json.load(f)
    else:
        with open(path, 'r') as f:
            data = json.load(f)

    if data is None:
        return None
    n = len(data["results"])
    c = len([True for r in data["results"] if r["status"]
            == "OK" and r["exit_code"] == 0])
    return {
        "pass@1": estimator(n, c, 1),
        "pass@10": estimator(n, c, 10),
        "pass@100": estimator(n, c, 100),
        "n": n,
        "c": c,
        "temperature": data["temperature"] if "temperature" in data else 0.2
    }


def main():
    """
    Args:
        dirs: Specify a directory that contains multiple JSON files of evaluation results for code generated with a model's generation parameters.
            Json(.json or .json.gz) file structure
                {
                    "temperature": 0.2,  
                    "results": [
                        {
                            "status": "OK",
                            "exit_code": 0,
                            "output": "..."
                        },
                        ...
                    ]
                }

    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--suppress-header",
                        action="store_true", help="Suppress the header")
    parser.add_argument("-k", type=int, default=None, help="The value of k")
    parser.add_argument(
        "dirs", type=str,  help="Directories with results. ", nargs="+")
    args = parser.parse_args()
    if not args.suppress_header:
        print("Dataset,Pass@k,Estimate,NumProblems,MinCompletions,MaxCompletions")
    for d in args.dirs:
        result_jsons = [for_file(p) for p in itertools.chain(
            # Path(d).glob("*.results.json"), Path(d).glob("*.results.json.gz"))]
            Path(d).glob("*.json"), Path(d).glob("*.json.gz"))]
        results = [r for r in result_jsons if r is not None]
        name = d.split("/")[-1] if d.split("/")[-1] != "" else d.split("/")[-2]

        temperature_set = set([r["temperature"] for r in results])
        if len(temperature_set) != 1:
            print(f"[Error] Found multiple temperatures {temperature_set} in {d} {results}")
            exit()
        temperature = list(temperature_set)[0]
        
        num_problems = len(results)
        min_completions = np.min([r["n"] for r in results])
        max_completions = np.max([r["n"] for r in results])
        
        pass_1 = np.mean([r["pass@1"] for r in results])
        pass_10 = np.mean([r["pass@10"] for r in results])
        pass_100 = np.mean([r["pass@100"] for r in results])
        print(
            f"{name},1,{pass_1},{num_problems},{min_completions},{max_completions}")
        print(
            f"{name},10,{pass_10},{num_problems},{min_completions},{max_completions}")
        print(
            f"{name},100,{pass_100},{num_problems},{min_completions},{max_completions}")

        if args.k is not None:
            pass_k = np.mean([estimator(r["n"], r["c"], args.k) for r in results])
            print(
                f"{name},{args.k},{pass_k},{num_problems},{min_completions},{max_completions}")


if __name__ == "__main__":
    main()