import os
import sys
import re
import subprocess
from pathlib import Path
from typing import List
import resource

from generic_eval import main
from decimal import Decimal, ROUND_HALF_UP

LANG_NAME = "Rust"
LANG_EXT = ".rs"
DEFAULT_TIMEOUT = 750

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- prompt (header):
fn add(x: isize, y: isize) -> isize {

- completion (body fragment):
    x + y

- tests (close function and provide main):
}
fn main() {
    assert_eq!(add(2,3), 5);
    println!("OK");
}
"""
def increase_stack_size():
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
        target_size = 256 * 1024 * 1024
        
        new_soft = hard
        if hard == resource.RLIM_INFINITY:
             new_soft = target_size
        else:
             new_soft = min(target_size, hard)

        resource.setrlimit(resource.RLIMIT_STACK, (new_soft, hard))
    except Exception as e:
        print(f"Warning: Failed to increase stack size: {e}", file=sys.stderr)

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

increase_stack_size()

def eval_script(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    binary_path = path.with_suffix("")

    stack_size = 1073741824

    try:
        build = subprocess.run(
            ["rustc", "-O", str(path), "-o", str(binary_path), "-C", f"link-args=-Wl,-z,stack-size={stack_size}"],
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "Timeout",
            "exit_code": -1,
            "stdout": "Compiler timeout",
            "stderr": "Compiler timeout",
        }

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

    run_env = os.environ.copy()
    run_env["RUST_MIN_STACK"] = str(stack_size)

    try:
        completed = subprocess.run(
            [str(binary_path)],
            input=(prepared_input.encode("utf-8") if prepared_input is not None else None),
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
            env=run_env,
        )
        stdout = completed.stdout.decode("utf-8", errors="ignore")
        stderr = completed.stderr.decode("utf-8", errors="ignore")
        returncode = completed.returncode
        status = "OK" if returncode == 0 else "Exception"
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="ignore")
        stderr = (exc.stderr or b"").decode("utf-8", errors="ignore")
        returncode = -1
        status = "Timeout"
    finally:
        try:
            if binary_path.exists():
                os.remove(binary_path)
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
