from pathlib import Path
from safe_subprocess import run
from generic_eval import main
import os

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


def eval_script(path: Path):
    basename = ".".join(str(path).split(".")[:-1])
    exe_path = basename  # fpc will produce this as the executable

    # Compile with Free Pascal; keep output quiet and optimize lightly
    build_result = run(["fpc", "-O1", "-v0", path, f"-o{exe_path}"])
    if build_result.exit_code != 0:
        return {
            "status": "SyntaxError",
            "exit_code": build_result.exit_code,
            "stdout": build_result.stdout,
            "stderr": build_result.stderr,
        }

    # Run the produced executable
    run_result = run([exe_path])
    try:
        if run_result.timeout:
            status = "Timeout"
        elif run_result.exit_code != 0:
            status = "Exception"
        else:
            status = "OK"
        return {
            "status": status,
            "exit_code": run_result.exit_code,
            "stdout": run_result.stdout,
            "stderr": run_result.stderr,
        }
    finally:
        # Best-effort cleanup of the executable and common artifacts
        try:
            if os.path.exists(exe_path):
                os.remove(exe_path)
        except Exception:
            pass


if __name__ == "__main__":
    main(eval_script, LANG_NAME, LANG_EXT)

