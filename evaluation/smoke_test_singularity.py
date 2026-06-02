"""
Smoke-test a Singularity sandbox/SIF built from the evaluation Docker archive.

Typical HPC workflow:
  module purge
  module load singularity squashfuse
  singularity build --sandbox multipl-e-eval_sandbox docker-archive://multipl-e-eval.tar
  python3 evaluation/smoke_test_singularity.py --image multipl-e-eval_sandbox --include-io
  python3 evaluation/smoke_test_singularity.py --image multipl-e-eval_sandbox --include-codegeex

This uses `singularity exec` rather than `singularity run` so the Docker
ENTRYPOINT does not start uvicorn. It directly calls containerized_eval inside
the image through singularity_eval_wrapper.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_test_podman import (
    DEFAULT_LANGUAGES,
    build_cases,
    print_results,
)
from singularity_eval_wrapper import SingularityEvaluationError, SingularityEvaluator


DEFAULT_IMAGE = "multipl-e-eval_sandbox"


CODEGEEX_LANG_MAP = {
    "python": "python3",
    "js": "javascript",
    "go": "go_test.go",
    "cpp": "cpp",
    "rust": "rust",
    "java": "java",
}


def codegeex_runtime_cases() -> list[dict[str, Any]]:
    """Small CodeGeeX-style pass/fail cases adapted from smoke_humanevalx_runtime.py.

    The fail cases intentionally mirror CodeGeeX executor expectations. If the
    MultiPL-E evaluator treats a fail case as OK, this smoke test reports it as
    a compatibility gap.
    """
    cases: list[dict[str, Any]] = []

    samples = {
        "python": (
            "def add(a, b):\n    return a + b\n\nassert add(1, 2) == 3\n",
            "def add(a, b):\n    return a + b\n\nassert add(1, 2) == 4\n",
        ),
        "js": (
            "function add(a, b) { return a + b; }\n"
            "if (add(1, 2) !== 3) { throw new Error('wrong'); }\n",
            "function add(a, b) { return a + b; }\n"
            "if (add(1, 2) !== 4) { throw new Error('mismatch'); }\n",
        ),
        "go": (
            "package main\n\nimport \"testing\"\n\n"
            "func add(a, b int) int { return a + b }\n\n"
            "func TestAdd(t *testing.T) {\n"
            "    if add(1, 2) != 3 { t.Fatalf(\"wrong\") }\n"
            "}\n",
            "package main\n\nimport \"testing\"\n\n"
            "func add(a, b int) int { return a + b }\n\n"
            "func TestAdd(t *testing.T) {\n"
            "    if add(1, 2) != 4 { t.Fatalf(\"wrong\") }\n"
            "}\n",
        ),
        "cpp": (
            "int add(int a, int b) { return a + b; }\n"
            "int main() { if (add(1, 2) != 3) return 1; return 0; }\n",
            "int add(int a, int b) { return a + b; }\n"
            "int main() { if (add(1, 2) != 4) return 1; return 0; }\n",
        ),
        "rust": (
            # CodeGeeX runs cargo test, where this pass/fail distinction matters.
            # MultiPL-E currently compiles/runs the binary, so these cases expose
            # whether Rust test-mode compatibility exists.
            "fn main() {}\n\n"
            "pub fn add(a: i32, b: i32) -> i32 { a + b }\n\n"
            "#[cfg(test)]\nmod tests {\n"
            "    use super::*;\n"
            "    #[test]\n"
            "    fn test_add() { assert_eq!(add(1, 2), 3); }\n"
            "}\n",
            "fn main() {}\n\n"
            "pub fn add(a: i32, b: i32) -> i32 { a + b }\n\n"
            "#[cfg(test)]\nmod tests {\n"
            "    use super::*;\n"
            "    #[test]\n"
            "    fn test_add() { assert_eq!(add(1, 2), 4); }\n"
            "}\n",
        ),
        "java": (
            "public class Main {\n"
            "    static int add(int a, int b) { return a + b; }\n"
            "    public static void main(String[] args) {\n"
            "        if (add(1, 2) != 3) throw new AssertionError(\"wrong\");\n"
            "    }\n"
            "}\n",
            "public class Main {\n"
            "    static int add(int a, int b) { return a + b; }\n"
            "    public static void main(String[] args) {\n"
            "        if (add(1, 2) != 4) throw new AssertionError(\"wrong\");\n"
            "    }\n"
            "}\n",
        ),
    }

    for codegeex_lang, (pass_program, fail_program) in samples.items():
        eval_lang = CODEGEEX_LANG_MAP[codegeex_lang]
        cases.append(
            {
                "name": f"codegeex:{codegeex_lang}:pass_case",
                "language": eval_lang,
                "codegeex_language": codegeex_lang,
                "mode": "string",
                "program": pass_program,
                "expect_status": "OK",
                "expect_codegeex_passed": True,
            }
        )
        cases.append(
            {
                "name": f"codegeex:{codegeex_lang}:fail_case",
                "language": eval_lang,
                "codegeex_language": codegeex_lang,
                "mode": "string",
                "program": fail_program,
                "expect_status": "not-OK",
                "expect_codegeex_passed": False,
            }
        )
    return cases


def run_in_singularity(
    runtime: str,
    image: str,
    cases: list[dict[str, Any]],
    timeout: float,
    binds: list[str],
    cleanenv: bool,
    pwd: str,
) -> list[dict[str, Any]]:
    evaluator = SingularityEvaluator(
        image=image,
        runtime=runtime,
        pwd=pwd,
        cleanenv=cleanenv,
        binds=binds,
        timeout=timeout,
    )
    requests = [_case_to_request(case) for case in cases]
    responses = evaluator.eval_batch(requests, timeout=timeout)
    return [_response_to_result(case, response) for case, response in zip(cases, responses)]


def _case_to_request(case: dict[str, Any]) -> dict[str, Any]:
    if case["mode"] == "string":
        return {
            "mode": "string",
            "language": case["language"],
            "program": case["program"],
        }
    if case["mode"] == "io":
        return {
            "mode": "io",
            "language": case["language"],
            "source_code": case["source_code"],
            "input": case["input"],
            "expected_output": case["expected_output"],
        }
    raise ValueError(f"unknown case mode: {case['mode']}")


def _response_to_result(case: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    result = response.get("result") if isinstance(response, dict) else {}
    if not isinstance(result, dict):
        result = {}
    status = result.get("status")
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    matched = result.get("matched")

    expected_status = case.get("expect_status", "OK")
    if expected_status == "not-OK":
        ok = bool(response.get("ok")) and status != "OK"
    else:
        ok = bool(response.get("ok")) and status == expected_status
    marker = case.get("expect_stdout_contains")
    if marker and marker not in stdout:
        ok = False
    if case["mode"] == "io" and matched is not True:
        ok = False

    return {
        "name": case["name"],
        "language": case["language"],
        "mode": case["mode"],
        "ok": ok,
        "status": status,
        "exit_code": result.get("exit_code"),
        "matched": matched,
        "stdout": str(stdout)[:2000],
        "stderr": str(stderr or response.get("error") or "")[:2000],
        "codegeex_language": case.get("codegeex_language"),
        "expected_codegeex_passed": case.get("expect_codegeex_passed"),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a Singularity evaluation image")
    parser.add_argument("languages", nargs="*", help="Subset of languages to test. Default: all supported languages.")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help=f"Sandbox/SIF path. Default: {DEFAULT_IMAGE}")
    parser.add_argument("--runtime", default="singularity", help="Singularity command. Default: singularity")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Overall test timeout in seconds")
    parser.add_argument("--include-io", action="store_true", help="Also run stdin/expected-output cases where supported")
    parser.add_argument("--include-codegeex", action="store_true", help="Also run CodeGeeX HumanEval-X-style pass/fail compatibility cases")
    parser.add_argument("--bind", action="append", default=[], help="Bind mount spec. May be passed multiple times.")
    parser.add_argument("--no-cleanenv", action="store_true", help="Do not pass --cleanenv to singularity exec")
    parser.add_argument("--pwd", default="/code", help="Working directory inside the image. Default: /code")
    parser.add_argument("--json-output", type=Path, help="Optional path to write full JSON results")
    args = parser.parse_args(argv)

    languages = args.languages or DEFAULT_LANGUAGES
    cases = build_cases(languages, include_io=args.include_io)
    if args.include_codegeex:
        cases.extend(codegeex_runtime_cases())

    try:
        results = run_in_singularity(
            runtime=args.runtime,
            image=args.image,
            cases=cases,
            timeout=args.timeout,
            binds=args.bind,
            cleanenv=not args.no_cleanenv,
            pwd=args.pwd,
        )
    except subprocess.TimeoutExpired:
        print(f"Timed out after {args.timeout} seconds", file=sys.stderr)
        return 124
    except FileNotFoundError:
        print(f"Singularity command not found: {args.runtime}", file=sys.stderr)
        return 127
    except SingularityEvaluationError as exc:
        results = [
            {
                "name": "<singularity>",
                "language": None,
                "mode": None,
                "ok": False,
                "status": f"ContainerExit{exc.returncode}",
                "stderr": exc.stderr[:4000],
            }
        ]

    print_results(results)

    if args.json_output:
        args.json_output.write_text(json.dumps(results, indent=2, ensure_ascii=True) + "\n")

    failures = [result for result in results if not result.get("ok")]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
