import os
import re
import subprocess
from pathlib import Path
from typing import List

from generic_eval import main
from safe_subprocess import Result, run
from decimal import Decimal

LANG_NAME = "C"
LANG_EXT = ".c"
COMPILER = "gcc"
DEFAULT_TIMEOUT = 750

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- prompt (header):
long add(long x, long y) {

- completion (body fragment):
    return x + y;

- tests (close function and provide main):
}
int main() {
    if (add(2, 3) != 5) { return 1; }
    puts("OK");
    return 0;
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

def _run_executable(executable: str, input_data: str | None = None) -> Result:
    if input_data is None:
        return run([executable], timeout_seconds=DEFAULT_TIMEOUT)

    prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
    prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()
    try:
        completed = subprocess.run(
            [executable],
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


def _determine_status(result: Result) -> str:
    if result.timeout:
        return "Timeout"
    if result.exit_code != 0:
        return "Exception"
    return "OK"


def eval_script(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    exe_path = str(path.with_suffix(""))

    build_result = run(
        [COMPILER, str(path), "-O2", "-std=c11", "-o", exe_path, "-lm"],
        timeout_seconds=DEFAULT_TIMEOUT,
    )
    if build_result.exit_code != 0:
        return {
            "status": "SyntaxError",
            "exit_code": build_result.exit_code,
            "stdout": build_result.stdout,
            "stderr": build_result.stderr,
        }

    try:
        run_result = _run_executable(exe_path, input_data=input_data)
    finally:
        try:
            if os.path.exists(exe_path):
                os.remove(exe_path)
        except Exception:
            pass

    status = _determine_status(run_result)
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
