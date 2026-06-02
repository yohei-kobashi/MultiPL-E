import os
import re
import subprocess
from pathlib import Path
from typing import List

from safe_subprocess import Result, run
from decimal import Decimal, ROUND_HALF_UP

RDMD_PATH = "/usr/local/bin/rdmd"
DEFAULT_TIMEOUT = 750

ENABLE_SYNTAX_CHECK = False

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- prompt (header):
long add(long x, long y) {

- completion (body fragment):
    return x + y;

- tests (close and provide main):
}
void main() {
    assert(add(2, 3) == 5);
    import std.stdio; writeln("OK");
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

def _run_with_stdin(command: List[str], input_data: str) -> Result:
    prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
    prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()
    try:
        completed = subprocess.run(
            command,
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
    if result.exit_code == 0:
        return "OK"
    if "Error:" in result.stderr:
        return "SyntaxError"
    return "Exception"


def _eval_with_unittest(path: Path) -> dict:
    result = run([RDMD_PATH, "-unittest", "-main", str(path)], timeout_seconds=DEFAULT_TIMEOUT)
    if "might not be correctly installed" in result.stderr:
        raise Exception("D is not correctly installed")
    status = _determine_status(result)
    return {
        "status": status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _eval_with_io(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    command = [RDMD_PATH, str(path)]

    if input_data is None:
        result = run(command, timeout_seconds=DEFAULT_TIMEOUT)
    else:
        result = _run_with_stdin(command, input_data)

    if "might not be correctly installed" in result.stderr:
        raise Exception("D is not correctly installed")

    status = _determine_status(result)

    expected_outputs = expected_outputs or []
    converted_expected = [_convert_for_compare(item) for item in expected_outputs]
    converted_stdout = _convert_for_compare(result.stdout)
    matched = bool(converted_expected) and len(converted_stdout) == len(converted_expected[0]) and any(
        all(_compare_values(output, expected) for output,expected in zip(converted_stdout, candidate)) for candidate in converted_expected
    )

    return {
        "status": status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "input": input_data,
        "expected_output": expected_outputs,
        "matched": matched,
    }


def eval_script(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    expects_io = input_data is not None or expected_outputs is not None
    if expects_io:
        return _eval_with_io(path, input_data=input_data, expected_outputs=expected_outputs)
    return _eval_with_unittest(path)


DIR = "d-keep-code_davinci_001_temp_0.2"
def main():
    directory = Path(Path(__file__).parent, "..", "datasets", DIR).resolve()

    count = {"OK": 0, "Timeout": 0, "Exception": 0, "SyntaxError": 0}
    for filename in os.listdir(directory):
        path = Path.joinpath(directory, filename)
        r = eval_script(path)
        status = r["status"]
        count[status] += 1

        if ENABLE_SYNTAX_CHECK and status == "SyntaxError":
            error_msgs = r["stderr"].split("\n")
            with open(path) as source_file:
                lines = source_file.readlines()
                unittest_line_start = lines.index("unittest\n")
                unittest_line_end = len(lines)
                for err_msg_line in error_msgs:
                    matched_parts = re.match(r"(\/?.*?\.[\w:]+\/.*.d)\(([0-9]+)\): Error: (.*)", err_msg_line[2:-1])
                    _file, line_num = matched_parts[1], int(matched_parts[2])
                    if unittest_line_start <= line_num and line_num <= unittest_line_end:
                        print("===============")
                        print(path, "contains error in unit test part")
                        print(error_msgs)
                        print("===============")

        filename = filename.split(".")[0]
        print(f"Dlang,{filename},{status}")

    print(DIR + ":" + str(count))

if __name__ == "__main__":
    main()
