import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List

from generic_eval import main
from safe_subprocess import Result, run
from decimal import Decimal, ROUND_HALF_UP

LANG_NAME = "Java"
LANG_EXT = ".java"
DEFAULT_TIMEOUT = 750

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- prompt (header):
class Problem {
    public static long add(long x, long y) {

- completion (body fragment):
        return x + y;

- tests (close method/class and provide main):
    }
    public static void main(String[] args) {
        assert add(2L, 3L) == 5L;
        System.out.println("OK");
    }
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

def _detect_class_name(source: str) -> str:
    """
    Extract the public class name so we can compile/run with a matching filename.
    Falls back to the historical default of Problem when no public class is found.
    """
    class_pattern = r"public\s+(?:final\s+|abstract\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)"
    m = re.search(class_pattern, source)
    return m.group(1) if m else "Problem"

def _run_java(outdir: str, javatuples_path: Path, env: dict, input_data: str | None, class_name: str) -> Result:
    cmd = ["java", "-ea", "-DONLINE_JUDGE=1", "-cp", f"{outdir}:{javatuples_path}", class_name]
    if input_data is None:
        return run(cmd, env=env)

    prepared_input = input_data.replace("\r\n", "\n").replace("\r", "")
    prepared_input = re.sub(r'[^\S \t\r\n]+', '', prepared_input).lstrip()
    try:
        completed = subprocess.run(
            cmd,
            input=prepared_input.encode("utf-8"),
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
            env=env,
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
    sys_env = os.environ.copy()
    javatuples_path = Path("/usr/multiple/javatuples-1.2.jar")
    sys_env["CLASSPATH"] = f"{javatuples_path}"

    with tempfile.TemporaryDirectory() as outdir:
        source = path.read_text(encoding="utf-8")
        class_name = _detect_class_name(source)
        # Ensure the filename matches the declared public class to avoid javac errors.
        adjusted_path = Path(outdir) / f"{class_name}.java"
        adjusted_path.write_text(source, encoding="utf-8")
        compile_result = run(
            ["javac", "-encoding", "UTF8", "-d", outdir, str(adjusted_path)],
            env=sys_env,
        )

        if compile_result.exit_code != 0:
            return {
                "status": "SyntaxError",
                "exit_code": compile_result.exit_code,
                "stdout": compile_result.stdout,
                "stderr": compile_result.stderr,
            }

        run_result = _run_java(outdir, javatuples_path, sys_env, input_data, class_name)

    if run_result.timeout:
        status = "Timeout"
    elif run_result.exit_code == 0:
        status = "OK"
    else:
        status = "Exception"

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
