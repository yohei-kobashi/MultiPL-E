import os
import re
import subprocess
from pathlib import Path
from typing import List

from generic_eval import main
from decimal import Decimal, ROUND_HALF_UP

LANG_NAME = "CSharp"
LANG_EXT = ".cs"
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
    if path.suffix.lower() != ".cs":
        return {
            "status": "Exception",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Unsupported extension: {path.suffix}",
        }

    binary_path = path.with_suffix(".exe")

    build = subprocess.run(
        [
            "csc",
            "/nologo",
            "/o",
            "-r:System.Numerics.dll",
            str(path),
            f"/out:{binary_path}",
        ],
        capture_output=True,
    )
    if build.returncode != 0:
        return {
            "status": "SyntaxError",
            "exit_code": build.returncode,
            "stdout": build.stdout.decode("utf-8", errors="ignore"),
            "stderr": build.stderr.decode("utf-8", errors="ignore"),
        }

    prepared_input = None
    if input_data is not None:
        prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
        prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()

    input_file_path = path.with_suffix(".in")
    stdin_handle = None
    if prepared_input is not None:
        with open(input_file_path, "w", encoding="utf-8") as f:
            f.write(prepared_input)
        stdin_handle = open(input_file_path, "r", encoding="utf-8")
    try:
        completed = subprocess.run(
            ["mono", str(binary_path)],
            stdin=stdin_handle,
            # input=(prepared_input.encode("utf-8") if prepared_input is not None else None),
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
            env={
                "PATH": os.getenv("PATH", ""),
                "MONO_TRACE_LISTENER": "Console.Error",
            },
        )
        stdout = completed.stdout.decode("utf-8", errors="ignore")
        stderr = completed.stderr.decode("utf-8", errors="ignore")
        returncode = completed.returncode

        fail = (
            "System.Diagnostics.DefaultTraceListener.Fail" in stderr
            or "Unhandled Exception" in stderr
        )
        if fail:
            status = "Exception"
        elif returncode == 0:
            status = "OK"
        else:
            status = "Exception"
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="ignore")
        stderr = (exc.stderr or b"").decode("utf-8", errors="ignore")
        returncode = -1
        status = "Timeout"
    finally:
        try:
            if binary_path.exists():
                binary_path.unlink()
            if input_file_path.exists():
                input_file_path.unlink()
        except Exception:
            pass

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
    main(eval_script, LANG_NAME, LANG_EXT)
