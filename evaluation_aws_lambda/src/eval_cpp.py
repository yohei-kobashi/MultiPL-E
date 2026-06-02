import os
import re
import subprocess
from pathlib import Path
from typing import List

from generic_eval import main
from safe_subprocess import Result, run
from decimal import Decimal, ROUND_HALF_UP

LANG_NAME = "C++"
LANG_EXT = ".cpp"
DEFAULT_TIMEOUT = 750

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- prompt (header):
long add(long x, long y) {

- completion (body fragment):
    return x + y;

- tests (close function and provide main):
}
int main(){
    auto candidate = add;
    assert(candidate(2,3) == 5);
    puts("OK");
}
"""

def _convert_for_compare(text: str) -> list:
    return re.split(r"\s+", text.strip())

def _compare_values(output: str, expected: str) -> bool:
    output = re.sub(r"\.0+$", "", output)
    expected = re.sub(r"\.0+$", "", expected)
    output = re.sub(r"\-0$", "0", output)
    expected = re.sub(r"\-0$", "0", expected)
    if "..." in expected:
        expected = re.sub(r"\.\.\.$", "", expected)
        return bool(re.match(expected, output))
    elif bool(re.match(r"-?\d+\.\d+$", output)) & bool(re.match(r"-?\d+\.\d+$", expected)):
        output = Decimal(output)
        expected = Decimal(expected)
        rel_tol = Decimal("1e-9")
        abs_tol = Decimal("1e-6")
        one = Decimal("1.0")

        return abs(output - expected) < max(abs_tol, rel_tol * max(one, abs(expected)))

    return output == expected

def _run_cpp(binary_path: Path, input_data: str | None) -> Result:
    if input_data is None:
        return run([str(binary_path)], timeout_seconds=DEFAULT_TIMEOUT)

    prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
    prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()
    try:
        completed = subprocess.run(
            [str(binary_path)],
            input=prepared_input.encode("utf-8"),
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
        )
        stdout = completed.stdout.decode("utf-8", errors="ignore")
        stderr = completed.stderr.decode("utf-8", errors="ignore")
        return Result(
            timeout=False,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="ignore")
        stderr = (exc.stderr or b"").decode("utf-8", errors="ignore")
        return Result(
            timeout=True,
            exit_code=-1,
            stdout=stdout,
            stderr=stderr,
        )


def eval_script(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    binary_path = path.with_suffix("")
    build_result = run(["g++", str(path), "-o", str(binary_path), "-std=c++17"])
    if build_result.exit_code != 0:
        return {
            "status": "SyntaxError",
            "exit_code": build_result.exit_code,
            "stdout": build_result.stdout,
            "stderr": build_result.stderr,
        }

    run_result = _run_cpp(binary_path, input_data=input_data)
    try:
        if "In file included from /shared/centos7/gcc/9.2.0-skylake/" in run_result.stderr:
            raise Exception("Skylake bug encountered")
        if "/4.8.2" in run_result.stderr:
            raise Exception("Ancient compiler encountered")
    finally:
        try:
            if binary_path.exists():
                os.remove(binary_path)
        except Exception:
            pass

    if run_result.timeout:
        status = "Timeout"
    elif run_result.exit_code != 0:
        status = "Exception"
    else:
        status = "OK"

    expected_outputs = expected_outputs or []
    converted_expected = [_convert_for_compare(item) for item in expected_outputs]
    converted_stdout = _convert_for_compare(run_result.stdout)
    matched = bool(converted_expected) and len(converted_stdout) == len(converted_expected[0]) and any(
        all(_compare_values(output, expected) for output,expected in zip(converted_stdout, candidate)) for candidate in converted_expected
    )

    return {
        "status": status,
        "exit_code": run_result.exit_code,
        "stdout": run_result.stdout,
        "stderr": run_result.stderr,
        "input": input_data,
        "expected_output": expected_outputs,
        "matched": matched,
    }


if __name__ == "__main__":
    main(eval_script, LANG_NAME, LANG_EXT)
