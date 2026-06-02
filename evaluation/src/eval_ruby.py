import re
import subprocess
from pathlib import Path
from typing import List

from generic_eval import main as gmain
from decimal import Decimal, ROUND_HALF_UP

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- completion:
def add(x, y)
  x + y
end

- tests:
require 'test/unit'
class TestHumanEval < Test::Unit::TestCase
  def test_add
    assert_equal 5, add(2, 3)
  end
end
"""

DEFAULT_TIMEOUT = 750

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

def eval_script(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    prepared_input = None
    if input_data is not None:
        prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
        prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()

    try:
        completed = subprocess.run(
            ["ruby", str(path)],
            input=(prepared_input.encode("utf-8") if prepared_input is not None else None),
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
        )
        stdout = completed.stdout.decode("utf-8", errors="ignore")
        stderr = completed.stderr.decode("utf-8", errors="ignore")
        returncode = completed.returncode

        if returncode == 0:
            status = "OK"
        elif "SyntaxError" in stderr:
            status = "SyntaxError"
        elif "NameError" in stderr or "NoMethodError" in stderr:
            status = "ReferenceError"
        else:
            status = "Exception"
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="ignore")
        stderr = (exc.stderr or b"").decode("utf-8", errors="ignore")
        returncode = -1
        status = "Timeout"

    expected_outputs = expected_outputs or []
    converted_expected = [_convert_for_compare(item) for item in expected_outputs]
    converted_stdout = _convert_for_compare(stdout)
    matched = bool(converted_expected) and len(converted_stdout) == len(converted_expected[0]) and any(
        all(_compare_values(output, expected) for output,expected in zip(converted_stdout, candidate)) for candidate in converted_expected
    )

    return {
        "status": status,
        "exit_code": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "input": input_data,
        "expected_output": expected_outputs,
        "matched": matched,
    }


if __name__ == "__main__":
    gmain(eval_script, "Ruby", ".rb")
