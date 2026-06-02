import re
import subprocess
import time
from pathlib import Path
from typing import List
from decimal import Decimal

from safe_subprocess import Result, run

DEFAULT_TIMEOUT = 750


def _convert_for_compare(text: str) -> list:
    return re.split(r"\s+", text.strip())


def _is_success(result: Result) -> bool:
    return not result.timeout and result.exit_code == 0


def _compare_values(output: str, expected: str) -> bool:
    output = re.sub(r"\.0+$", "", output)
    expected = re.sub(r"\.0+$", "", expected)
    output = re.sub(r"\-0$", "0", output)
    expected = re.sub(r"\-0$", "0", expected)
    if "..." in expected:
        expected = re.sub(r"\.\.\.$", "", expected)
        return bool(re.match(expected, output))
    elif bool(re.match(r"-?\d+\.\d+$", output)) & bool(re.match(r"-?\d+\.\d+$", expected)):
        output_decimal = Decimal(output)
        expected_decimal = Decimal(expected)
        rel_tol = Decimal("1e-9")
        abs_tol = Decimal("1e-6")
        one = Decimal("1.0")

        return abs(output_decimal - expected_decimal) < max(abs_tol, rel_tol * max(one, abs(expected_decimal)))

    return output == expected


def _run_python(path: Path, input_data: str | None, executable: str) -> tuple[Result, float]:
    start = time.perf_counter()
    if input_data is None:
        res = run([executable, str(path)], timeout_seconds=DEFAULT_TIMEOUT)
        return res, time.perf_counter() - start

    prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
    prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()
    try:
        completed = subprocess.run(
            [executable, str(path)],
            input=prepared_input.encode("utf-8"),
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
        )
        stdout = completed.stdout.decode("utf-8", errors="ignore")
        stderr = completed.stderr.decode("utf-8", errors="ignore")
        res = Result(
            timeout=False,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
        )
        return res, time.perf_counter() - start
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="ignore")
        stderr = (exc.stderr or b"").decode("utf-8", errors="ignore")
        res = Result(
            timeout=True,
            exit_code=-1,
            stdout=stdout,
            stderr=stderr,
        )
        return res, time.perf_counter() - start


def eval_with_interpreter(
    path: Path,
    input_data: str | None,
    expected_outputs: List[str] | None,
    executable: str,
    interpreter_label: str,
):
    res, duration = _run_python(path, input_data=input_data, executable=executable)

    attempts: list[dict] = [
        {
            "interpreter": interpreter_label,
            "duration_sec": round(duration, 3),
            "timeout": res.timeout,
            "exit_code": res.exit_code,
        }
    ]
    errors = {}
    if not _is_success(res):
        errors[interpreter_label] = res.stderr

    if res.timeout:
        status = "Timeout"
    elif res.exit_code == 0:
        status = "OK"
    elif "SyntaxError" in res.stderr:
        status = "SyntaxError"
    else:
        status = "Exception"

    expected_outputs = expected_outputs or []
    converted_expected = [_convert_for_compare(item) for item in expected_outputs]
    converted_stdout = _convert_for_compare(res.stdout)
    matched = bool(converted_expected) and len(converted_stdout) == len(converted_expected[0]) and any(
        all(_compare_values(output, expected) for output, expected in zip(converted_stdout, candidate))
        for candidate in converted_expected
    )

    return {
        "status": status,
        "exit_code": res.exit_code,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "input": input_data,
        "expected_output": expected_outputs,
        "matched": matched,
        "interpreter": interpreter_label,
        "errors": errors if errors else None,
        "attempts": attempts,
    }
