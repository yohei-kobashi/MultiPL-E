"""
Evaluates a generated Clojure program (.clj).
"""
from pathlib import Path
from safe_subprocess import run
from generic_eval import main

"""
Examples for MultiPL-E composition (prompt + completion + tests):

- completion:
(defn add [x y] (+ x y))

- tests:
;; Our evaluator checks for "0 failures, 0 errors." in stdout
(println)
(println "0 failures, 0 errors.")
"""


def eval_script(path: Path):
    result = run(["clojure", "-J-Dclojure.main.report=stderr", "-M", str(path)])

    if result.timeout:
        status = "Timeout"
    elif result.exit_code != 0:
        status = "Exception"
    elif "\n0 failures, 0 errors.\n" in result.stdout:
        status = "OK"
    else: # test failure
        status = "Exception"

    return {
        "status": status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

if __name__ == "__main__":
    main(eval_script, "Clojure", ".clj")
