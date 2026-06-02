import subprocess
from pathlib import Path
from typing import List
import re

from safe_subprocess import Result, run
from decimal import Decimal, ROUND_HALF_UP

LANG_NAME = "PHP"
LANG_EXT = ".php"
DEFAULT_TIMEOUT = 750

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- completion:
<?php
function add($x, $y) { return $x + $y; }

- tests:
if (add(2, 3) === 5) { echo "OK\n"; } else { echo "FAIL\n"; }
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

def _run_php(path: Path, input_data: str | None) -> Result:
    if input_data is None:
        return run(["php", str(path)], timeout_seconds=DEFAULT_TIMEOUT)

    prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
    prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()
    try:
        completed = subprocess.run(
            ["php", str(path)],
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
    r = _run_php(path, input_data=input_data)

    if r.timeout:
        status = "Timeout"
    elif "PHP Parse error" in r.stdout or "PHP Parse error" in r.stderr:
        status = "SyntaxError"
    elif r.exit_code != 0:
        status = "Exception"
    else:
        status = "OK"

    expected_outputs = expected_outputs or []
    converted_expected = [_convert_for_compare(item) for item in expected_outputs]
    converted_stdout = _convert_for_compare(r.stdout)
    matched = bool(converted_expected) and len(converted_stdout) == len(converted_expected[0]) and any(
        all(_compare_values(output, expected) for output,expected in zip(converted_stdout, candidate)) for candidate in converted_expected
    )

    return {
        "status": status,
        "exit_code": r.exit_code,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "input": input_data,
        "expected_output": expected_outputs,
        "matched": matched,
    }
