"""
Smoke-test all deployed Lambda evaluators by sending a minimal program
that should succeed (or at least execute) and report the status.

It loads base URLs from `lang2url.json` and POSTs to `<url>/evaluate` with
the payload expected by `src/api.py`:

{
  "language": <lang>,
  "prompt": "",
  "tests": "",
  "completions": [<entire_program_string>]
}

Usage:
  python smoke_test_lambdas.py              # test all
  python smoke_test_lambdas.py python rust  # test specific languages

Notes:
- Some languages (e.g., Java/Scala) expect a specific entry class/object name
  as per eval_* implementation. This script uses those conventions (e.g.,
  Java/Scala use `Problem`).
- Go uses the special language key `go_test.go` which produces a `_test.go` file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional, List

import requests
from urllib.parse import urljoin


def load_lang_urls(path: Path) -> Dict[str, str]:
    obj = json.loads(path.read_text())
    return obj.get("urls", {})


def canonical_program_lang(lang: str) -> str:
    if lang == "python3":
        return "python"
    if lang == "python2":
        return "python2_legacy"
    return {
        "adb": "ada",
        "d": "dlang",
        "jl": "julia",
        "js": "javascript",
        "kt": "kotlin",
        "ml": "ocaml",
        "rb": "ruby",
        "rkt": "racket",
        "rs": "rust",
    }.get(lang, lang)


def program_for(lang: str) -> str:
    lang = canonical_program_lang(lang)
    # Entire programs that should compile/run and print or pass trivially.
    # For most languages we just print "OK".
    m: Dict[str, str] = {
        # Scripting
        "python": 'print("OK")\n',
        "python2_legacy": 'print "OK"\n',  # Intentionally Python 2 syntax
        "javascript": 'console.log("OK")\n',
        "ts": 'console.log("OK")\n',
        "ruby": 'puts "OK"\n',
        "lua": 'print("OK")\n',
        "luau": 'print("OK")\n',
        "php": '<?php echo "OK\n";\n',
        "r": 'cat("OK\n")\n',
        "racket": '#lang racket\n(displayln "OK")\n',
        "sh": '#!/usr/bin/env bash\necho OK\n',
        "pl": 'print "OK\\n";\n',  # Perl
        # Clojure: ensure stdout contains "\n0 failures, 0 errors.\n"
        # Emit an empty line before the summary to match evaluator substring.
        "clj": '(println)\n(println "0 failures, 0 errors.")\n',

        # Compiled
        "cpp": '#include <iostream>\nint main(){ std::cout << "OK\\n"; return 0; }\n',
        "c": '#include <stdio.h>\nint main(){ puts("OK"); return 0; }\n',
        "rust": 'fn main(){ println!("OK"); }\n',
        "swift": 'print("OK")\n',
        "ocaml": 'print_endline "OK"\n',
        "fs": 'printfn "OK"\n',
        "hs": 'main = putStrLn "OK"\n',
        "scala": 'object Problem { def main(args: Array[String]) = println("OK") }\n',
        # Non-public class to avoid filename constraint under current Lambda evaluator
        "java": 'class Problem { public static void main(String[] args){ System.out.println("OK"); } }\n',
        "kotlin": 'fun main() {\n    println("OK")\n}\n',
        "cs": 'using System; public static class Program { public static void Main(){ Console.WriteLine("OK"); } }\n',
        "dlang": 'import std.stdio; void main(){ writeln("OK"); }\n',
        "dart": 'void main(){ print("OK"); }\n',
        "julia": 'println("OK")\n',
        "elixir": 'IO.puts("OK")\n',
        # Ada must define procedure main so gnatchop emits main.adb for our evaluator
        "ada": 'with Ada.Text_IO; use Ada.Text_IO;\nprocedure main is\nbegin\n  Put_Line("OK");\nend main;\n',
        # Delphi / Free Pascal
        "delphi": "program Test;\nbegin\n  writeln('OK');\nend.\n",

        # Proof/verification oriented
        # Coq (key is `v` here, evaluator compiles with `coqc`)
        "v": 'Theorem t : True. Proof. trivial. Qed.\n',
        # Lean: keep it as trivial proposition
        # Note: Depending on Lean version, capitalized True may be required (Lean 4).
        # If using Lean 3, `true`/`trivial` may be needed.
        "lean": 'theorem t : True := True.intro\n',
        # Dafny
        "dfy": 'method Main() { print "OK\\n"; }\n',

        # Go (tests only)
        "go_test.go": 'package main\nimport "testing"\nfunc TestOK(t *testing.T) {}\n',
    }

    code = m.get(lang)
    if code is None:
        # As a conservative default, try a generic print program in common syntaxes.
        # Many evaluators will just fail gracefully; the goal is smoke-checking the endpoint.
        return 'print("OK")\n'
    return code


def tests_for(lang: str) -> str | None:
    lang = canonical_program_lang(lang)
    # Additional code appended as `tests` to validate concatenation behavior.
    # Only defined for languages where simply appending another print is valid.
    m: Dict[str, str] = {
        "python": 'print("T")\n',
        "python2_legacy": 'print "T"\n',
        "javascript": 'console.log("T")\n',
        "ts": 'console.log("T")\n',
        "ruby": 'puts "T"\n',
        "lua": 'print("T")\n',
        "luau": 'print("T")\n',
        "php": 'echo "T\\n";\n',
        "r": 'cat("T\\n")\n',
        # For Racket, do NOT emit #lang again; append only expression
        "racket": '(displayln "T")\n',
        "sh": '#!/usr/bin/env bash\necho T\n',
        "pl": 'print "T\\n";\n',
        "julia": 'println("T")\n',
        "elixir": 'IO.puts("T")\n',
        # Clojure OK checker relies on specific summary line
        "clj": '(println)\n(println "0 failures, 0 errors.")\n',
        # Dafny verification: keep tests empty (verification summary is enough)
        "dfy": '',
    }
    return m.get(lang)


def make_payload(lang: str, tests: str = "", prompt: str = "") -> dict:
    return {
        "language": lang,
        "prompt": prompt,
        "tests": tests,
        # Send the entire program as a single completion
        "completions": [program_for(lang)],
        "name": f"smoke_{lang}",
        "stop_tokens": ["\n"],
    }


def make_io_payload(lang: str, source_code: str, input_data: str, expected_output: List[str]) -> dict:
    return {
        "language": lang,
        "source_code": source_code,
        "input": input_data,
        "output": expected_output,
        "name": f"smoke_{lang}_io",
    }


def test_one(
    lang: str,
    base_url: str,
    timeout: float = 30.0,
    tests: str = "",
    case: str | None = None,
    prompt: str = "",
    completion_override: Optional[str] = None,
) -> dict:
    url = urljoin(base_url if base_url.endswith("/") else base_url + "/", "evaluate")
    payload = make_payload(lang, tests=tests, prompt=prompt)
    if completion_override is not None:
        payload["completions"] = [completion_override]
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        status = resp.status_code
        data = None
        err = None
        try:
            data = resp.json()
        except Exception:
            err = resp.text
        result_entry = (data.get("results") or [{}])[0] if isinstance(data, dict) else {}
        return {
            "language": f"{lang}{'+' + case if case else ''}",
            "url": base_url,
            "http_status": status,
            "ok": status == 200,
            "result_status": result_entry.get("status"),
            "stderr": result_entry.get("stderr") if isinstance(result_entry, dict) else err,
            "stdout": result_entry.get("stdout") if isinstance(result_entry, dict) else None,
            "program": result_entry.get("program") if isinstance(result_entry, dict) else None,
        }
    except requests.RequestException as e:
        return {
            "language": f"{lang}{'+' + case if case else ''}",
            "url": base_url,
            "http_status": None,
            "ok": False,
            "result_status": None,
            "stderr": str(e),
        }


def warmup_one(
    lang: str,
    base_url: str,
    timeout: float = 90.0,
    eval_timeout: float = 90.0,
) -> dict:
    """Invoke the evaluator once before recording smoke-test results."""
    url = urljoin(base_url if base_url.endswith("/") else base_url + "/", "evaluate")
    payload = make_payload(lang)
    payload["name"] = f"warmup_{lang}"
    payload["eval_timeout"] = eval_timeout
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        result_status = None
        try:
            data = resp.json()
            if isinstance(data, dict):
                result_status = (data.get("results") or [{}])[0].get("status")
        except Exception:
            pass
        return {
            "language": lang,
            "url": base_url,
            "http_status": resp.status_code,
            "ok": resp.status_code == 200,
            "result_status": result_status,
            "stderr": None,
        }
    except requests.RequestException as e:
        return {
            "language": lang,
            "url": base_url,
            "http_status": None,
            "ok": False,
            "result_status": None,
            "stderr": str(e),
        }


def test_one_io(
    lang: str,
    base_url: str,
    source_code: str,
    input_data: str,
    expected_output: List[str],
    timeout: float = 30.0,
    case: str | None = None,
) -> dict:
    url = urljoin(base_url if base_url.endswith("/") else base_url + "/", "evaluate")
    payload = make_io_payload(lang, source_code, input_data, expected_output)
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        status = resp.status_code
        data = None
        err = None
        result_status = None
        matched = None
        expected = expected_output
        try:
            data = resp.json()
            if isinstance(data, dict):
                result_obj = (data.get("results") or [{}])[0]
                result_status = result_obj.get("status")
                matched = result_obj.get("matched")
                expected = result_obj.get("expected_output", expected_output)
        except Exception:
            err = resp.text
        is_ok = status == 200
        if is_ok:
            if result_status not in (None, "OK"):
                is_ok = False
            expected_list = expected if isinstance(expected, list) else [expected] if expected else []
            if expected_list and matched is False:
                is_ok = False
        stderr_val = None
        result_entry = (data.get("results") or [{}])[0] if isinstance(data, dict) else {}
        if isinstance(result_entry, dict):
            stderr_val = result_entry.get("stderr")
        if stderr_val is None:
            stderr_val = err
        return {
            "language": f"{lang}{'+' + case if case else ''}",
            "url": base_url,
            "http_status": status,
            "ok": is_ok,
            "result_status": result_status,
            "matched": matched,
            "stderr": stderr_val,
            "stdout": result_entry.get("stdout") if isinstance(result_entry, dict) else None,
            "program": result_entry.get("program") if isinstance(result_entry, dict) else None,
            "expected_output": expected if isinstance(expected, list) else [expected] if expected else [],
        }
    except requests.RequestException as e:
        return {
            "language": f"{lang}{'+' + case if case else ''}",
            "url": base_url,
            "http_status": None,
            "ok": False,
            "result_status": None,
            "matched": None,
            "stderr": str(e),
        }


def triad_for(lang: str) -> Optional[Tuple[str, str, str]]:
    lang = canonical_program_lang(lang)
    # Returns (prompt, completion_fragment, tests) for structured languages.
    m: Dict[str, Tuple[str, str, str]] = {
        "python": (
            "",
            "def add(x, y):\n    return x + y\n",
            "if __name__ == \"__main__\":\n    assert add(2,3) == 5\n    print(\"OK\")\n",
        ),
        "python2_legacy": (
            "",
            "def add(x, y):\n    return x + y\n",
            "if __name__ == \"__main__\":\n    assert add(2,3) == 5\n    print \"OK\"\n",
        ),
        "javascript": (
            "",
            "function add(x, y) { return x + y; }\n",
            "const assert = require('node:assert');\nassert.strictEqual(add(2,3), 5);\nconsole.log('OK');\n",
        ),
        "ts": (
            "",
            "function add(x: number, y: number): number { return x + y; }\n",
            "console.assert(add(2,3) === 5);\nconsole.log('OK');\n",
        ),
        "ruby": (
            "",
            "def add(x, y)\n  x + y\nend\n",
            "require 'test/unit'\nclass TestHumanEval < Test::Unit::TestCase\n  def test_add\n    assert_equal 5, add(2,3)\n  end\nend\n",
        ),
        "lua": (
            "",
            "function add(x, y) return x + y end\n",
            "assert(add(2,3) == 5)\nprint('OK')\n",
        ),
        "luau": (
            "",
            "function add(x, y) return x + y end\n",
            "assert(add(2,3) == 5)\nprint('OK')\n",
        ),
        "php": (
            "",
            "<?php\nfunction add($x, $y) { return $x + $y; }\n",
            "if (add(2, 3) === 5) { echo \"OK\\n\"; } else { echo \"FAIL\\n\"; }\n",
        ),
        "r": (
            "",
            "add <- function(x, y) x + y\n",
            "stopifnot(add(2,3) == 5)\ncat(\"OK\\n\")\n",
        ),
        "racket": (
            "#lang racket\n(define (add x y) (+ x y))\n",
            "",
            "(require rackunit)\n(check-equal? (add 2 3) 5)\n(displayln \"OK\")\n",
        ),
        "sh": (
            "",
            "add(){ echo $(($1 + $2)); }\n",
            "if [ \"$(add 2 3)\" -eq 5 ]; then echo OK; else echo FAIL; fi\n",
        ),
        "pl": (
            "",
            "sub add { return $_[0] + $_[1]; }\n",
            "if (add(2,3) != 5) { die \"FAIL\\n\" } else { print \"OK\\n\" }\n",
        ),
        "julia": (
            "",
            "add(x,y) = x + y\n",
            "@assert add(2,3) == 5\nprintln(\"OK\")\n",
        ),
        "elixir": (
            "",
            "defmodule M do\n  def add(x,y), do: x + y\nend\n",
            "if M.add(2,3) != 5 do\n  raise \"FAIL\"\nelse\n  IO.puts(\"OK\")\nend\n",
        ),
        "clj": (
            "",
            "(defn add [x y] (+ x y))\n",
            "(println)\n(println \"0 failures, 0 errors.\")\n",
        ),
        "cpp": (
            "#include <assert.h>\n#include <stdio.h>\nlong add(long x, long y) {\n",
            "    return x + y;",
            "}\nint main(){\n    long (*candidate)(long,long) = add;\n    assert(candidate(2,3) == 5);\n    puts(\"OK\");\n}\n",
        ),
        "c": (
            "#include <assert.h>\n#include <stdio.h>\nlong add(long x, long y) {\n",
            "    return x + y;",
            "}\nint main(void) {\n    assert(add(2,3) == 5);\n    puts(\"OK\");\n    return 0;\n}\n",
        ),
        "rust": (
            "fn add(x: isize, y: isize) -> isize {\n",
            "    x + y",
            "}\nfn main() {\n    assert_eq!(add(2,3), 5);\n    println!(\"OK\");\n}\n",
        ),
        "java": (
            "class Problem {\n    public static long add(long x, long y) {\n",
            "        return x + y;",
            "    }\n    public static void main(String[] args) {\n        assert add(2L, 3L) == 5L;\n        System.out.println(\"OK\");\n    }\n}\n",
        ),
        "kotlin": (
            "object Problem {\n    fun add(x: Long, y: Long): Long {\n",
            "        return x + y",
            "    }\n    @JvmStatic\n    fun main(args: Array<String>) {\n        check(add(2L, 3L) == 5L)\n        println(\"OK\")\n    }\n}\n",
        ),
        "scala": (
            "object Problem {\n  def add(x: Long, y: Long): Long = {\n",
            "    x + y",
            "  }\n  def main(args: Array[String]) = {\n    assert(add(2L, 3L) == 5L)\n    println(\"OK\")\n  }\n}\n",
        ),
        "cs": (
            "using System; using System.Diagnostics; class Problem {\n    public static long Add(long x, long y) {\n",
            "        return x + y;",
            "    }\n    public static void Main(string[] args) {\n        Debug.Assert(Add(2L, 3L) == 5L);\n        Console.WriteLine(\"OK\");\n    }\n}\n",
        ),
        "dlang": (
            "long add(long x, long y) {\n",
            "    return x + y;",
            "}\nvoid main() {\n    assert(add(2, 3) == 5);\n    import std.stdio; writeln(\"OK\");\n}\n",
        ),
        "dart": (
            "int add(int x, int y) {\n",
            "  return x + y;",
            "}\nvoid main() {\n  assert(add(2,3) == 5);\n  print('OK');\n}\n",
        ),
        "ocaml": (
            "let add x y =\n",
            "  x + y",
            ";; assert (add 2 3 = 5);\nprint_endline \"OK\";;\n",
        ),
        "fs": (
            "let add x y =\n",
            "    x + y",
            "\nprintfn \"%d\" (add 2 3)\n",
        ),
        "hs": (
            "add :: Int -> Int -> Int\nadd x y =\n",
            "  x + y",
            "\nmain = do\n  if add 2 3 == 5 then putStrLn \"OK\" else error \"FAIL\"\n",
        ),
        "swift": (
            "func add(_ x: Int, _ y: Int) -> Int {\n",
            "    return x + y",
            "}\nif add(2,3) == 5 { print(\"OK\") } else { fatalError(\"FAIL\") }\n",
        ),
        "lean": (
            "def add (x y : Nat) := x + y\n",
            "",
            "theorem t : add 2 3 = 5 := rfl\n",
        ),
        "v": (
            "Definition add (x y : nat) := x + y.\n",
            "",
            "Example t : add 2 3 = 5.\nProof. reflexivity. Qed.\n",
        ),
        "delphi": (
            # prompt (include program header and function signature)
            "program Test;\n\nfunction add(x, y: LongInt): LongInt;\n",
            # completion (function body fragment)
            "begin\n  add := x + y;\nend;\n",
            # tests (program body)
            "begin\n  if add(2, 3) <> 5 then halt(1);\n  writeln('OK');\nend.\n",
        ),
        "go_test.go": (
            "package main\n\nimport \"testing\"\n\nfunc add(x, y int) int {\n",
            "    return x + y",
            "}\n\nfunc TestAdd(t *testing.T) {\n    if add(2, 3) != 5 {\n        t.Fatal(\"fail\")\n    }\n}\n",
        ),
    }
    return m.get(lang)


def io_case_for(lang: str) -> Optional[Tuple[str, str, List[str], List[str]]]:
    lang = canonical_program_lang(lang)
    # Returns (source_code, input_data, expected_ok, expected_bad) for IO evaluators.
    m: Dict[str, Tuple[str, str, List[str], List[str]]] = {
        "c": (
            "#include <stdio.h>\n"
            "#include <string.h>\n"
            "int main(void) {\n"
            "    char buf[256];\n"
            "    if (fgets(buf, sizeof(buf), stdin) == NULL) {\n"
            "        return 1;\n"
            "    }\n"
            "    buf[strcspn(buf, \"\\r\\n\")] = '\\0';\n"
            "    puts(buf);\n"
            "    return 0;\n"
            "}\n",
            "c-echo\n",
            ["c-echo"],
            ["c-echo__mismatch__"],
        ),
        "delphi": (
            "program Echo;\n"
            "var s: string;\n"
            "begin\n"
            "  readln(s);\n"
            "  writeln(s);\n"
            "end.\n",
            "zz\n",
            ["zz"],
            ["zz__mismatch__"],
        ),
        "dlang": (
            "import std.stdio;\n"
            "import std.string;\n"
            "void main() {\n"
            "    string line = readln();\n"
            "    chomp(line);\n"
            "    writeln(line);\n"
            "}\n",
            "io-check\n",
            ["io-check"],
            ["io-check__mismatch__"],
        ),
        "kotlin": (
            "fun main() {\n"
            "    println(\"OK\")\n"
            "}\n",
            "",
            ["OK"],
            ["not-ok"],
        ),
        "go_test.go": (
            "package main\n"
            "import (\n"
            "    \"bufio\"\n"
            "    \"fmt\"\n"
            "    \"os\"\n"
            ")\n"
            "func main() {\n"
            "    scanner := bufio.NewScanner(os.Stdin)\n"
            "    if scanner.Scan() {\n"
            "        fmt.Println(scanner.Text())\n"
            "    }\n"
            "}\n",
            "go-echo\n",
            ["go-echo"],
            ["go-echo__mismatch__"],
        ),
        "javascript": (
            "const fs = require('fs');\n"
            "const input = fs.readFileSync(0, 'utf8').replace(/\\r?\\n$/, '');\n"
            "console.log(input);\n",
            "js-echo\n",
            ["js-echo"],
            ["js-echo__mismatch__"],
        ),
        "python": (
            "import sys\n"
            "line = sys.stdin.readline().rstrip('\\r\\n')\n"
            "print(line)\n",
            "py-echo\n",
            ["py-echo"],
            ["py-echo__mismatch__"],
        ),
        "python2_legacy": (
            "import sys\n"
            "line = sys.stdin.readline().rstrip('\\r\\n')\n"
            "print line\n",
            "py-echo\n",
            ["py-echo"],
            ["py-echo__mismatch__"],
        ),
        "java": (
            "import java.io.BufferedReader;\n"
            "import java.io.InputStreamReader;\n"
            "public class Problem {\n"
            "    public static void main(String[] args) throws Exception {\n"
            "        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));\n"
            "        String line = br.readLine();\n"
            "        if (line != null) {\n"
            "            System.out.println(line.trim());\n"
            "        }\n"
            "    }\n"
            "}\n",
            "java-echo\n",
            ["java-echo"],
            ["java-echo__mismatch__"],
        ),
        "rust": (
            "use std::io::{self, Read};\n"
            "fn main() {\n"
            "    let mut input = String::new();\n"
            "    io::stdin().read_to_string(&mut input).unwrap();\n"
            "    let line = input.lines().next().unwrap_or(\"\");\n"
            "    println!(\"{}\", line);\n"
            "}\n",
            "rust-echo\n",
            ["rust-echo"],
            ["rust-echo__mismatch__"],
        ),
        "cpp": (
            "#include <iostream>\n"
            "#include <string>\n"
            "int main() {\n"
            "    std::string line;\n"
            "    if (std::getline(std::cin, line)) {\n"
            "        std::cout << line << std::endl;\n"
            "    }\n"
            "    return 0;\n"
            "}\n",
            "cpp-echo\n",
            ["cpp-echo"],
            ["cpp-echo__mismatch__"],
        ),
        "php": (
            "<?php\n"
            "$line = rtrim(fgets(STDIN));\n"
            "echo $line, \"\\n\";\n",
            "php-echo\n",
            ["php-echo"],
            ["php-echo__mismatch__"],
        ),
        "cs": (
            "using System;\n"
            "class Program {\n"
            "    static void Main() {\n"
            "        var line = Console.ReadLine();\n"
            "        Console.WriteLine(line);\n"
            "    }\n"
            "}\n",
            "cs-echo\n",
            ["cs-echo"],
            ["cs-echo__mismatch__"],
        ),
        "ruby": (
            "line = STDIN.gets&.chomp\n"
            "puts line\n",
            "ruby-echo\n",
            ["ruby-echo"],
            ["ruby-echo__mismatch__"],
        ),
        "pl": (
            "chomp(my $line = <STDIN>);\n"
            "print \"$line\\n\";\n",
            "perl-echo\n",
            ["perl-echo"],
            ["perl-echo__mismatch__"],
        ),
    }
    return m.get(lang)


def run_python3_suite(base_url: str) -> list[dict]:
    """Run Python 3 smoke tests."""
    results = []
    results.append(test_one("python3", base_url, case="py3"))
    tcode_py3 = tests_for("python")
    if tcode_py3 is not None:
        results.append(test_one("python3", base_url, tests=tcode_py3, case="py3-tests"))
    triad_py3 = triad_for("python")
    if triad_py3 is not None:
        pr, comp, ts = triad_py3
        results.append(test_one("python3", base_url, tests=ts, prompt=pr, case="py3-triad", completion_override=comp))
    io_py3 = io_case_for("python")
    if io_py3 is not None:
        io_program, io_input, io_expected, io_expected_bad = io_py3
        results.append(test_one_io("python3", base_url, io_program, io_input, io_expected, case="py3-io-ok"))
        results.append(test_one_io("python3", base_url, io_program, io_input, io_expected_bad, case="py3-io-bad"))
    return results


def run_python2_suite(base_url: str) -> list[dict]:
    """Run Python 2 smoke tests."""
    results = []
    py2_prog = program_for("python2_legacy")
    results.append(test_one("python2", base_url, case="py2", completion_override=py2_prog))
    tcode_py2 = tests_for("python2_legacy")
    if tcode_py2 is not None:
        results.append(test_one("python2", base_url, tests=tcode_py2, case="py2-tests", completion_override=py2_prog))
    triad_py2 = triad_for("python2_legacy")
    if triad_py2 is not None:
        pr2, comp2, ts2 = triad_py2
        results.append(test_one("python2", base_url, tests=ts2, prompt=pr2, case="py2-triad", completion_override=comp2))
    io_py2 = io_case_for("python2_legacy")
    if io_py2 is not None:
        io_program2, io_input2, io_expected2, io_expected_bad2 = io_py2
        results.append(test_one_io("python2", base_url, io_program2, io_input2, io_expected2, case="py2-io-ok"))
        results.append(test_one_io("python2", base_url, io_program2, io_input2, io_expected_bad2, case="py2-io-bad"))

    return results


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Smoke-test deployed Lambda evaluators")
    ap.add_argument("languages", nargs="*", help="Subset of languages to test (default: all in lang2url.json)")
    ap.add_argument("--urls", default="lang2url.json", help="Path to JSON file mapping languages to URLs")
    ap.add_argument("--no-warmup", action="store_true", help="Skip the initial warmup evaluate request per target")
    ap.add_argument("--warmup-timeout", type=float, default=90.0, help="Client timeout for each warmup request")
    ap.add_argument("--warmup-eval-timeout", type=float, default=90.0, help="Server-side eval_timeout sent with warmup requests")
    args = ap.parse_args(argv)

    lang2url = load_lang_urls(Path(args.urls))
    if not lang2url:
        print("No URLs found in", args.urls)
        return 2

    targets_raw = args.languages or list(lang2url.keys())
    # If "python" is requested but python2/python3 URLs exist, expand into both.
    expanded_targets: list[str] = []
    for lang in targets_raw:
        if lang == "python" and "python2" in lang2url and "python3" in lang2url:
            expanded_targets.extend(["python3", "python2"])
        else:
            expanded_targets.append(lang)
    # Deduplicate while preserving order
    seen = set()
    targets: list[str] = []
    for lang in expanded_targets:
        if lang not in seen:
            targets.append(lang)
            seen.add(lang)

    results = []
    for lang in targets:
        url = lang2url.get(lang) or (lang == "python" and lang2url.get("python3")) or None
        if not url:
            results.append({
                "language": lang,
                "url": None,
                "http_status": None,
                "ok": False,
                "result_status": None,
                "stderr": "No URL in mapping",
            })
            continue
        if not args.no_warmup:
            warmup = warmup_one(
                lang,
                url,
                timeout=args.warmup_timeout,
                eval_timeout=args.warmup_eval_timeout,
            )
            if not warmup.get("ok"):
                print(
                    f"[warmup] {lang}: http={warmup.get('http_status')} "
                    f"result={warmup.get('result_status')} "
                    f"error={str(warmup.get('stderr') or '')[:300]}",
                    file=sys.stderr,
                )
        if lang == "python3":
            results.extend(run_python3_suite(url))
            continue
        if lang == "python2":
            results.extend(run_python2_suite(url))
            continue
        if lang == "python":
            # Backward-compatible single-URL path if only "python" is provided
            results.extend(run_python3_suite(url))
            results.extend(run_python2_suite(url))
            continue
        # Base case
        r = test_one(lang, url)
        results.append(r)
        # With-tests case (if supported)
        tcode = tests_for(lang)
        if tcode is not None:
            r2 = test_one(lang, url, tests=tcode, case="tests")
            results.append(r2)
        # Structured triad case (if available)
        triad = triad_for(lang)
        if triad is not None:
            pr, comp, ts = triad
            r3 = test_one(lang, url, tests=ts, prompt=pr, case="triad", completion_override=comp)
            results.append(r3)
        io_case = io_case_for(lang)
        if io_case is not None:
            io_program, io_input, io_expected, io_expected_bad = io_case
            r4 = test_one_io(lang, url, io_program, io_input, io_expected, case="io-ok")
            results.append(r4)
            r5 = test_one_io(lang, url, io_program, io_input, io_expected_bad, case="io-bad")
            results.append(r5)

    # Pretty print summary
    print("Language,HTTP_OK,Result,URL")
    for r in results:
        print(f"{r['language']},{r['ok']},{r.get('result_status')},{r.get('url')}")

    # Optionally, print failures with errors
    failures = [r for r in results if (not r.get("ok")) or (r.get("result_status") not in (None, "OK"))]
    if failures:
        print("\nFailures (details):")
        for r in failures:
            stdout_snippet = str(r.get("stdout") or "")[:800]
            program_snippet = str(r.get("program") or "")[:800]
            expected_repr = r.get("expected_output")
            print(f"- {r['language']}: http={r['http_status']} result={r.get('result_status')}")
            print(f"  stderr: {str(r.get('stderr'))[:800]}")
            if stdout_snippet:
                print(f"  stdout: {stdout_snippet}")
            if program_snippet:
                print(f"  program: {program_snippet}")
            if expected_repr:
                print(f"  expected: {expected_repr}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
