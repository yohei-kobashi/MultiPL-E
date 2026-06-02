import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from generic_eval import main
from safe_subprocess import Result, run
from decimal import Decimal, ROUND_HALF_UP

LANG_NAME = "Kotlin"
LANG_EXT = ".kt"
DEFAULT_TIMEOUT = 750

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- prompt (header):
object Problem {
    fun add(x: Long, y: Long): Long {

- completion (body fragment):
        return x + y

- tests (close method/object and provide main):
    }
    @JvmStatic
    fun main(args: Array<String>) {
        check(add(2L, 3L) == 5L)
        println("OK")
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

def _run_with_stdin(
    command: List[str],
    sys_env: dict[str, str],
    input_data: str,
) -> Result:
    prepared = input_data.replace("\r\n", "\n").replace("\r", "")
    prepared = re.sub(r'[^\S \t\r\n]+', '', prepared).lstrip()
    try:
        completed = subprocess.run(
            command,
            input=prepared.encode("utf-8"),
            capture_output=True,
            timeout=DEFAULT_TIMEOUT,
            env=sys_env,
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


def _execute_java(
    base_cmd: List[str],
    sys_env: dict[str, str],
    input_data: Optional[str] = None,
) -> Result:
    if input_data is None:
        return run(base_cmd, env=sys_env, timeout_seconds=DEFAULT_TIMEOUT)
    return _run_with_stdin(base_cmd, sys_env, input_data)


def eval_script(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    sys_env = os.environ.copy()
    javatuples_path = Path("/usr/multiple/javatuples-1.2.jar")
    expected_outputs = expected_outputs or []

    with tempfile.TemporaryDirectory() as tmpdir:
        jar_path = Path(tmpdir) / "problem.jar"

        compile_args = ["kotlinc", str(path)]
        if javatuples_path.exists():
            compile_args.extend(["-classpath", str(javatuples_path)])
        compile_args.extend(["-include-runtime", "-d", str(jar_path)])

        compile_result = run(compile_args, env=sys_env, timeout_seconds=DEFAULT_TIMEOUT)
        if compile_result.exit_code != 0:
            status = "SyntaxError"
            result = compile_result
        else:
            classpath_entries = [str(jar_path)]
            if javatuples_path.exists():
                classpath_entries.append(str(javatuples_path))
            classpath = os.pathsep.join(classpath_entries)

            entry_points = ["ProblemKt", "Problem"]
            run_result = None
            status = "Exception"

            for entry in entry_points:
                command = ["java", "-ea", "-cp", classpath, entry]
                run_result = _execute_java(command, sys_env, input_data=input_data)
                if run_result.timeout:
                    status = "Timeout"
                    break
                if run_result.exit_code == 0:
                    status = "OK"
                    break
                class_not_found = "Could not find or load main class" in run_result.stderr
                no_main_method = "NoSuchMethodError: main" in run_result.stderr
                if class_not_found or no_main_method:
                    continue
                status = "Exception"
                break
            else:
                command = ["java", "-ea", "-jar", str(jar_path)]
                run_result = _execute_java(command, sys_env, input_data=input_data)
                if run_result.timeout:
                    status = "Timeout"
                elif run_result.exit_code == 0:
                    status = "OK"
                else:
                    status = "Exception"

            result = run_result

    response = {
        "status": status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

    if input_data is not None or expected_outputs:
        converted_expected = [_convert_for_compare(item) for item in expected_outputs]
        converted_stdout = _convert_for_compare(result.stdout)
        matched = bool(converted_expected) and len(converted_stdout) == len(converted_expected[0]) and any(
            all(_compare_values(output, expected) for output,expected in zip(converted_stdout, candidate)) for candidate in converted_expected
        )
        response.update(
            {
                "input": input_data,
                "expected_output": expected_outputs,
                "matched": matched,
            }
        )

    return response


if __name__ == "__main__":
    main(eval_script, LANG_NAME, LANG_EXT)
