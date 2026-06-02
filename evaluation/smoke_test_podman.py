"""
Smoke-test the monolithic evaluation image with Podman.

This script is intended to run after building evaluation/Dockerfile. It
does not use the FastAPI endpoint because evaluation/src/api.py keeps the
older single-completion schema while the Lambda smoke test targets the newer
Lambda API schema. Instead, it runs one container and calls containerized_eval
inside the image.

Examples:
  podman build -t multipl-e-eval -f evaluation/Dockerfile evaluation
  python3 evaluation/smoke_test_podman.py --image multipl-e-eval
  python3 evaluation/smoke_test_podman.py --image multipl-e-eval python3 rust java
  python3 evaluation/smoke_test_podman.py --image multipl-e-eval --include-io
  python3 evaluation/smoke_test_podman.py --image multipl-e-eval --include-codegeex
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_IMAGE = "multipl-e-eval"

DEFAULT_LANGUAGES = [
    "ada",
    "c",
    "clj",
    "cpp",
    "cs",
    "dart",
    "delphi",
    "dfy",
    "dlang",
    "elixir",
    "fs",
    "go_test.go",
    "hs",
    "java",
    "javascript",
    "julia",
    "kotlin",
    "lean",
    "lua",
    "luau",
    "ocaml",
    "php",
    "pl",
    "python2",
    "python3",
    "r",
    "racket",
    "ruby",
    "rust",
    "scala",
    "sh",
    "swift",
    "ts",
    "v",
]

ALIASES = {
    "adb": "ada",
    "coq": "v",
    "js": "javascript",
    "kt": "kotlin",
    "perl": "pl",
    "python": "python3",
}


PROGRAMS: dict[str, str] = {
    "ada": (
        "with Ada.Text_IO; use Ada.Text_IO;\n"
        "procedure main is\n"
        "begin\n"
        '  Put_Line("OK");\n'
        "end main;\n"
    ),
    "c": '#include <stdio.h>\nint main(void){ puts("OK"); return 0; }\n',
    "clj": '(println)\n(println "0 failures, 0 errors.")\n',
    "cpp": '#include <iostream>\nint main(){ std::cout << "OK\\n"; return 0; }\n',
    "cs": (
        "using System;\n"
        "public static class Program {\n"
        '  public static void Main(){ Console.WriteLine("OK"); }\n'
        "}\n"
    ),
    "dart": 'void main(){ print("OK"); }\n',
    "delphi": "program Test;\nbegin\n  writeln('OK');\nend.\n",
    "dfy": 'method Main() { assert true; }\n',
    "dlang": 'import std.stdio; void main(){ writeln("OK"); }\n',
    "elixir": 'IO.puts("OK")\n',
    "fs": 'printfn "OK"\n',
    "go_test.go": 'package main\nimport "testing"\nfunc TestOK(t *testing.T) {}\n',
    "hs": 'main = putStrLn "OK"\n',
    "java": (
        "class Problem {\n"
        '  public static void main(String[] args){ System.out.println("OK"); }\n'
        "}\n"
    ),
    "javascript": 'console.log("OK")\n',
    "julia": 'println("OK")\n',
    "kotlin": 'object Problem { @JvmStatic fun main(args: Array<String>) { println("OK") } }\n',
    "lean": "theorem t : True := True.intro\n",
    "lua": 'print("OK")\n',
    "luau": 'print("OK")\n',
    "ocaml": 'print_endline "OK"\n',
    "php": '<?php echo "OK\\n";\n',
    "pl": 'print "OK\\n";\n',
    "python2": 'print "OK"\n',
    "python3": 'print("OK")\n',
    "r": 'cat("OK\\n")\n',
    "racket": '#lang racket\n(displayln "OK")\n',
    "ruby": 'puts "OK"\n',
    "rust": 'fn main(){ println!("OK"); }\n',
    "scala": 'object Problem { def main(args: Array[String]) = println("OK") }\n',
    "sh": 'echo OK\n',
    "swift": 'print("OK")\n',
    "ts": 'console.log("OK")\n',
    "v": "Theorem t : True. Proof. trivial. Qed.\n",
}

STDOUT_MARKERS = {
    lang: "OK"
    for lang in DEFAULT_LANGUAGES
    if lang not in {"clj", "dfy", "go_test.go", "lean", "v"}
}
STDOUT_MARKERS["clj"] = "0 failures, 0 errors."


IO_CASES: dict[str, tuple[str, str, list[str]]] = {
    "c": (
        "#include <stdio.h>\n"
        "#include <string.h>\n"
        "int main(void){ char b[256]; if(!fgets(b,sizeof(b),stdin)) return 1;"
        ' b[strcspn(b,"\\r\\n")]=0; puts(b); return 0; }\n',
        "c-echo\n",
        ["c-echo"],
    ),
    "cpp": (
        "#include <iostream>\n#include <string>\n"
        "int main(){ std::string s; if(std::getline(std::cin,s)) std::cout << s << std::endl; }\n",
        "cpp-echo\n",
        ["cpp-echo"],
    ),
    "cs": (
        "using System;\nclass Program { static void Main(){ Console.WriteLine(Console.ReadLine()); } }\n",
        "cs-echo\n",
        ["cs-echo"],
    ),
    "delphi": (
        "program Echo;\nvar s: string;\nbegin\n  readln(s);\n  writeln(s);\nend.\n",
        "pas-echo\n",
        ["pas-echo"],
    ),
    "dlang": (
        "import std.stdio; import std.string;\n"
        "void main(){ auto s = readln(); chomp(s); writeln(s); }\n",
        "d-echo\n",
        ["d-echo"],
    ),
    "go_test.go": (
        "package main\nimport (\n  \"bufio\"\n  \"fmt\"\n  \"os\"\n)\n"
        "func main(){ scanner := bufio.NewScanner(os.Stdin); if scanner.Scan(){ fmt.Println(scanner.Text()) } }\n",
        "go-echo\n",
        ["go-echo"],
    ),
    "java": (
        "import java.io.*;\n"
        "public class Problem { public static void main(String[] args) throws Exception {"
        " BufferedReader br = new BufferedReader(new InputStreamReader(System.in));"
        " System.out.println(br.readLine()); } }\n",
        "java-echo\n",
        ["java-echo"],
    ),
    "javascript": (
        "const fs = require('fs');\n"
        "console.log(fs.readFileSync(0, 'utf8').replace(/\\r?\\n$/, ''));\n",
        "js-echo\n",
        ["js-echo"],
    ),
    "kotlin": (
        "object Problem { @JvmStatic fun main(args: Array<String>) { println(readLine()) } }\n",
        "kt-echo\n",
        ["kt-echo"],
    ),
    "php": (
        "<?php $line = rtrim(fgets(STDIN)); echo $line, \"\\n\";\n",
        "php-echo\n",
        ["php-echo"],
    ),
    "pl": (
        'chomp(my $line = <STDIN>); print "$line\\n";\n',
        "perl-echo\n",
        ["perl-echo"],
    ),
    "python2": (
        "import sys\nline = sys.stdin.readline().rstrip('\\r\\n')\nprint line\n",
        "py2-echo\n",
        ["py2-echo"],
    ),
    "python3": (
        "import sys\nline = sys.stdin.readline().rstrip('\\r\\n')\nprint(line)\n",
        "py3-echo\n",
        ["py3-echo"],
    ),
    "ruby": (
        "line = STDIN.gets&.chomp\nputs line\n",
        "ruby-echo\n",
        ["ruby-echo"],
    ),
    "rust": (
        "use std::io::{self, Read};\n"
        "fn main(){ let mut s=String::new(); io::stdin().read_to_string(&mut s).unwrap();"
        " println!(\"{}\", s.lines().next().unwrap_or(\"\")); }\n",
        "rust-echo\n",
        ["rust-echo"],
    ),
}


CODEGEEX_LANG_MAP = {
    "python": "python3",
    "js": "javascript",
    "go": "go_test.go",
    "cpp": "cpp",
    "rust": "rust",
    "java": "java",
}


def codegeex_runtime_cases() -> list[dict[str, Any]]:
    """Small CodeGeeX-style pass/fail cases adapted from smoke_humanevalx_runtime.py."""
    cases: list[dict[str, Any]] = []
    samples = {
        "python": (
            "def add(a, b):\n    return a + b\n\nassert add(1, 2) == 3\n",
            "def add(a, b):\n    return a + b\n\nassert add(1, 2) == 4\n",
        ),
        "js": (
            "function add(a, b) { return a + b; }\n"
            "if (add(1, 2) !== 3) { throw new Error('wrong'); }\n",
            "function add(a, b) { return a + b; }\n"
            "if (add(1, 2) !== 4) { throw new Error('mismatch'); }\n",
        ),
        "go": (
            "package main\n\nimport \"testing\"\n\n"
            "func add(a, b int) int { return a + b }\n\n"
            "func TestAdd(t *testing.T) {\n"
            "    if add(1, 2) != 3 { t.Fatalf(\"wrong\") }\n"
            "}\n",
            "package main\n\nimport \"testing\"\n\n"
            "func add(a, b int) int { return a + b }\n\n"
            "func TestAdd(t *testing.T) {\n"
            "    if add(1, 2) != 4 { t.Fatalf(\"wrong\") }\n"
            "}\n",
        ),
        "cpp": (
            "int add(int a, int b) { return a + b; }\n"
            "int main() { if (add(1, 2) != 3) return 1; return 0; }\n",
            "int add(int a, int b) { return a + b; }\n"
            "int main() { if (add(1, 2) != 4) return 1; return 0; }\n",
        ),
        "rust": (
            "fn main() {}\n\n"
            "pub fn add(a: i32, b: i32) -> i32 { a + b }\n\n"
            "#[cfg(test)]\nmod tests {\n"
            "    use super::*;\n"
            "    #[test]\n"
            "    fn test_add() { assert_eq!(add(1, 2), 3); }\n"
            "}\n",
            "fn main() {}\n\n"
            "pub fn add(a: i32, b: i32) -> i32 { a + b }\n\n"
            "#[cfg(test)]\nmod tests {\n"
            "    use super::*;\n"
            "    #[test]\n"
            "    fn test_add() { assert_eq!(add(1, 2), 4); }\n"
            "}\n",
        ),
        "java": (
            "public class Main {\n"
            "    static int add(int a, int b) { return a + b; }\n"
            "    public static void main(String[] args) {\n"
            "        if (add(1, 2) != 3) throw new AssertionError(\"wrong\");\n"
            "    }\n"
            "}\n",
            "public class Main {\n"
            "    static int add(int a, int b) { return a + b; }\n"
            "    public static void main(String[] args) {\n"
            "        if (add(1, 2) != 4) throw new AssertionError(\"wrong\");\n"
            "    }\n"
            "}\n",
        ),
    }

    for codegeex_lang, (pass_program, fail_program) in samples.items():
        eval_lang = CODEGEEX_LANG_MAP[codegeex_lang]
        cases.append(
            {
                "name": f"codegeex:{codegeex_lang}:pass_case",
                "language": eval_lang,
                "codegeex_language": codegeex_lang,
                "mode": "string",
                "program": pass_program,
                "expect_status": "OK",
                "expect_codegeex_passed": True,
            }
        )
        cases.append(
            {
                "name": f"codegeex:{codegeex_lang}:fail_case",
                "language": eval_lang,
                "codegeex_language": codegeex_lang,
                "mode": "string",
                "program": fail_program,
                "expect_status": "not-OK",
                "expect_codegeex_passed": False,
            }
        )
    return cases


CONTAINER_RUNNER = r"""
import json
import os
import sys
import time
import traceback

from containerized_eval import eval_source_with_io, eval_string_script

payload = json.load(sys.stdin)
cases = payload["cases"]

for case in cases:
    started = time.time()
    result = None
    error = None
    try:
        if case["mode"] == "string":
            result = eval_string_script(case["language"], case["program"])
        elif case["mode"] == "io":
            result = eval_source_with_io(
                case["language"],
                case["source_code"],
                case["input"],
                case["expected_output"],
            )
        else:
            raise ValueError(f"unknown mode: {case['mode']}")
    except Exception:
        error = traceback.format_exc()
        result = {
            "status": "Exception",
            "exit_code": -1,
            "stdout": "",
            "stderr": error,
        }

    status = result.get("status") if isinstance(result, dict) else None
    stdout = result.get("stdout", "") if isinstance(result, dict) else ""
    stderr = result.get("stderr", "") if isinstance(result, dict) else ""
    matched = result.get("matched") if isinstance(result, dict) else None

    expected_status = case.get("expect_status", "OK")
    if expected_status == "not-OK":
        ok = status != "OK"
    else:
        ok = status == expected_status
    marker = case.get("expect_stdout_contains")
    if marker and marker not in stdout:
        ok = False
    if case["mode"] == "io" and matched is not True:
        ok = False

    print(json.dumps({
        "name": case["name"],
        "language": case["language"],
        "mode": case["mode"],
        "ok": ok,
        "status": status,
        "exit_code": result.get("exit_code") if isinstance(result, dict) else None,
        "matched": matched,
        "stdout": stdout[:2000],
        "stderr": stderr[:2000],
        "elapsed_sec": round(time.time() - started, 3),
        "codegeex_language": case.get("codegeex_language"),
        "expected_codegeex_passed": case.get("expect_codegeex_passed"),
    }, ensure_ascii=True), flush=True)
"""


def normalize_language(lang: str) -> str:
    return ALIASES.get(lang, lang)


def build_cases(languages: list[str], include_io: bool) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for requested in languages:
        lang = normalize_language(requested)
        program = PROGRAMS.get(lang)
        if program is None:
            raise SystemExit(f"No smoke program defined for language: {requested}")
        cases.append(
            {
                "name": f"{lang}:basic",
                "language": lang,
                "mode": "string",
                "program": program,
                "expect_status": "OK",
                "expect_stdout_contains": STDOUT_MARKERS.get(lang),
            }
        )
        if include_io and lang in IO_CASES:
            source_code, input_data, expected_output = IO_CASES[lang]
            cases.append(
                {
                    "name": f"{lang}:io",
                    "language": lang,
                    "mode": "io",
                    "source_code": source_code,
                    "input": input_data,
                    "expected_output": expected_output,
                    "expect_status": "OK",
                }
            )
    return cases


def run_in_container(
    runtime: str,
    image: str,
    cases: list[dict[str, Any]],
    timeout: float,
    network: str | None,
) -> list[dict[str, Any]]:
    cmd = [runtime, "run", "--rm", "-i"]
    if network is not None:
        cmd.extend(["--network", network])
    cmd.extend(["--entrypoint", "python3", image, "-c", CONTAINER_RUNNER])

    proc = subprocess.run(
        cmd,
        input=json.dumps({"cases": cases}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )

    results: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            results.append(
                {
                    "name": "<container-output>",
                    "language": None,
                    "mode": None,
                    "ok": False,
                    "status": "InvalidJSON",
                    "stderr": line,
                }
            )

    if proc.returncode != 0:
        results.append(
            {
                "name": "<podman>",
                "language": None,
                "mode": None,
                "ok": False,
                "status": f"ContainerExit{proc.returncode}",
                "stderr": proc.stderr[:4000],
            }
        )
    elif proc.stderr.strip():
        results.append(
            {
                "name": "<podman-stderr>",
                "language": None,
                "mode": None,
                "ok": True,
                "status": "Stderr",
                "stderr": proc.stderr[:4000],
            }
        )

    return results


def print_results(results: list[dict[str, Any]]) -> None:
    print("Case,OK,Status,Exit,Matched,Seconds")
    for result in results:
        print(
            f"{result.get('name')},"
            f"{result.get('ok')},"
            f"{result.get('status')},"
            f"{result.get('exit_code')},"
            f"{result.get('matched')},"
            f"{result.get('elapsed_sec')}"
        )

    failures = [result for result in results if not result.get("ok")]
    if failures:
        print("\nFailures:")
        for result in failures:
            print(f"- {result.get('name')}: status={result.get('status')} exit={result.get('exit_code')}")
            stdout = str(result.get("stdout") or "")[:800]
            stderr = str(result.get("stderr") or "")[:1200]
            if stdout:
                print(f"  stdout: {stdout}")
            if stderr:
                print(f"  stderr: {stderr}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test a built evaluation Podman image")
    parser.add_argument("languages", nargs="*", help="Subset of languages to test. Default: all supported languages.")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help=f"Image tag to test. Default: {DEFAULT_IMAGE}")
    parser.add_argument("--runtime", default="podman", help="Container runtime command. Default: podman")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Overall container timeout in seconds")
    parser.add_argument("--include-io", action="store_true", help="Also run stdin/expected-output cases where supported")
    parser.add_argument("--include-codegeex", action="store_true", help="Also run CodeGeeX HumanEval-X-style pass/fail compatibility cases")
    parser.add_argument("--network", default="none", help="Container network mode. Use '' to omit --network.")
    parser.add_argument("--json-output", type=Path, help="Optional path to write full JSON results")
    args = parser.parse_args(argv)

    languages = args.languages or DEFAULT_LANGUAGES
    cases = build_cases(languages, include_io=args.include_io)
    if args.include_codegeex:
        cases.extend(codegeex_runtime_cases())
    network = args.network if args.network else None

    try:
        results = run_in_container(
            runtime=args.runtime,
            image=args.image,
            cases=cases,
            timeout=args.timeout,
            network=network,
        )
    except subprocess.TimeoutExpired:
        print(f"Timed out after {args.timeout} seconds", file=sys.stderr)
        return 124
    except FileNotFoundError:
        print(f"Container runtime not found: {args.runtime}", file=sys.stderr)
        return 127

    print_results(results)

    if args.json_output:
        args.json_output.write_text(json.dumps(results, indent=2, ensure_ascii=True) + "\n")

    failures = [result for result in results if not result.get("ok")]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
