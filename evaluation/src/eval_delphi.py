from pathlib import Path
import subprocess
from typing import List
from safe_subprocess import run, Result
from generic_eval import main
import os
import re
from decimal import Decimal, ROUND_HALF_UP

LANG_NAME = "Delphi"
LANG_EXT = ".pas"

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- prompt (header):
function add(x, y: LongInt): LongInt;

- completion (body fragment):
begin
  add := x + y;
end;

- tests (close and provide program):
program Test;
begin
  if add(2, 3) <> 5 then halt(1);
  writeln('OK');
end.
"""

def _run_executable(executable: str, input_data: str | None = None) -> Result:
    if input_data is None:
        return run([executable])

    prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
    prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()
    try:
        completed = subprocess.run(
            [executable],
            input=prepared_input.encode("utf-8"),
            capture_output=True,
            timeout=750,
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

def exe_testcase(
    executable: str,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    run_result = _run_executable(executable, input_data=input_data)

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


def eval_script(path: Path, input_data: str | None = None, expected_outputs: list[str] | None = None):
    expected_outputs = expected_outputs or []
    basename = ".".join(str(path).split(".")[:-1])
    exe_path = basename  # fpc will produce this as the executable

    # Compile with Free Pascal; keep output quiet and optimize lightly
    build_result = run(["fpc", "-Mdelphi", "-O1", "-v0", path, f"-o{exe_path}"])
    if build_result.exit_code != 0:
        return {
            "status": "SyntaxError",
            "exit_code": build_result.exit_code,
            "stdout": build_result.stdout,
            "stderr": build_result.stderr,
        }

    # Run the produced executable
    try:
        return exe_testcase(
            exe_path,
            input_data=input_data,
            expected_outputs=expected_outputs,
        )
    finally:
        # Best-effort cleanup of the executable and common artifacts
        try:
            if os.path.exists(exe_path):
                os.remove(exe_path)
            if os.path.exists(f"{exe_path}.o"):
                os.remove(f"{exe_path}.o")
            if os.path.exists(f"{exe_path}.ppu"):
                os.remove(f"{exe_path}.ppu")
        except Exception:
            pass


if __name__ == "__main__":
    main(eval_script, LANG_NAME, LANG_EXT)
