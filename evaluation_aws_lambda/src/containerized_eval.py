"""
NOTE: Nothing containerized about this any more. This is just a helper
for problem_evaluator.py.
"""

import inspect
import tempfile
from pathlib import Path
import eval_adb
import eval_ruby
import eval_lua
import eval_python
import eval_python2
import eval_python3
import eval_rust
import eval_kotlin
import eval_java
import eval_racket
import eval_javascript
import eval_swift
import eval_cpp
import eval_c
import eval_php
import eval_dlang
import eval_julia
import eval_r
import eval_fs
import eval_ocaml
import eval_matlab
import eval_hs
import eval_elixir
import eval_clj
import eval_v
import eval_lean
import eval_dart
import eval_delphi


EVALUATORS = {
    "ada": (eval_adb.eval_script, ".adb"),
    "rb": (eval_ruby.eval_script, ".rb"),
    "lua": (eval_lua.eval_script, ".lua"),
    "python": (eval_python3.eval_script, ".py"),
    "python3": (eval_python3.eval_script, ".py"),
    "py": (eval_python3.eval_script, ".py"),
    "notypes.py": (eval_python3.eval_script, ".py"),
    "python2": (eval_python2.eval_script, ".py"),
    "python2_legacy": (eval_python2.eval_script, ".py"),
    "julia": (eval_julia.eval_script, ".jl"),
    "java" : (eval_java.eval_script, ".java"),
    "kotlin": (eval_kotlin.eval_script, ".kt"),
    "kt": (eval_kotlin.eval_script, ".kt"),
    "rust" : (eval_rust.eval_script, ".rs"),
    "rs" : (eval_rust.eval_script, ".rs"),
    "swift": (eval_swift.eval_script, ".swift"),
    "lua": (eval_lua.eval_script, ".lua"),
    "racket": (eval_racket.eval_script, ".rkt"),
    "rkt": (eval_racket.eval_script, ".rkt"),
    "javascript": (eval_javascript.eval_script, ".js"),
    "js": (eval_javascript.eval_script, ".js"),
    "c": (eval_c.eval_script, ".c"),
    "cpp": (eval_cpp.eval_script, ".cpp"),
    "php": (eval_php.eval_script, ".php"),
    "humaneval_to_dlang.py": (eval_dlang.eval_script, ".d"),
    "dlang": (eval_dlang.eval_script, ".d"),
    "d": (eval_dlang.eval_script, ".d"),
    "r": (eval_r.eval_script, ".r"),
    "humaneval_to_r.py": (eval_r.eval_script, ".r"),
    "jl": (eval_julia.eval_script, ".jl"),
    "fs": (eval_fs.eval_script, ".fsx"),
    "ml": (eval_ocaml.eval_script, ".ml"),
    "m": (eval_matlab.eval_script, ".m"),
    "hs": (eval_hs.eval_script, ".hs"),
    "elixir": (eval_elixir.eval_script, ".exs"),
    "clj": (eval_clj.eval_script, ".clj"),
    "coq": (eval_v.eval_script, ".v"),
    "lean": (eval_lean.eval_script, ".lean"),
    "dart": (eval_dart.eval_script, ".dart"),
    "delphi": (eval_delphi.eval_script, ".pas"),
}

def _resolve_evaluator(language):
    if language in EVALUATORS:
        return EVALUATORS[language]
    else:
        eval_module = __import__(f"eval_{language}" if language != "go_test.go" else "eval_go")
        eval_script = eval_module.eval_script
        file_ext = f".{language}" if language != "go_test.go" else "_test.go"
        return eval_script, file_ext

def _invoke_eval_script(eval_script, path, input_data=None, expected_outputs=None):
    try:
        params = inspect.signature(eval_script).parameters
    except (TypeError, ValueError):
        params = {}

    kwargs = {}
    if input_data is not None:
        if "input_data" in params:
            kwargs["input_data"] = input_data
        elif "stdin" in params:
            kwargs["stdin"] = input_data
        elif "input" in params:
            kwargs["input"] = input_data
    if expected_outputs is not None:
        if "expected_outputs" in params:
            kwargs["expected_outputs"] = expected_outputs
        elif "expected_output" in params:
            kwargs["expected_output"] = expected_outputs
        elif "outputs" in params:
            kwargs["outputs"] = expected_outputs
        elif "output" in params:
            kwargs["output"] = expected_outputs

    try:
        return eval_script(path, **kwargs)
    except TypeError:
        # Fallback to legacy signature accepting only Path.
        return eval_script(path)

def _normalize_result(program, result, extra=None):
    if isinstance(result.get("stdout"), bytes):
        result["stdout"] = result["stdout"].decode("utf-8", errors="ignore")
    if isinstance(result.get("stderr"), bytes):
        result["stderr"] = result["stderr"].decode("utf-8", errors="ignore")
    if result.get("stdout") is None:
        result["stdout"] = ""
    if result.get("stderr") is None:
        result["stderr"] = ""

    normalized = {
        "program": program,
        "stdout": result["stdout"].replace("!!int", "")[:2048],
        "stderr": result["stderr"][:2048],
        "exit_code": result.get("exit_code"),
        "status": result.get("status"),
    }

    # Preserve optional diagnostic fields when present.
    for key in ("interpreter", "errors", "attempts"):
        if result.get(key) is not None:
            normalized[key] = result.get(key)

    if extra:
        normalized.update(extra)

    return normalized

def eval_string_script(language, program):
    eval_script, file_ext = _resolve_evaluator(language)

    if language in ("java", "scala", "kotlin"):
        class_file = {
            "java": "Problem.java",
            "scala": "Problem.scala",
            "kotlin": "Problem.kt",
        }[language]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / class_file
            p.write_text(program, encoding="utf-8")
            result = _invoke_eval_script(eval_script, p)
            extra = {
                key: result.get(key)
                for key in ("input", "expected_output", "matched", "interpreter", "errors", "attempts")
                if result.get(key) is not None
            }
            return _normalize_result(program, result, extra=extra or None)

    with tempfile.NamedTemporaryFile(suffix=file_ext, delete=True) as f:
        f.write(program.encode("utf-8"))
        f.flush()
        result = _invoke_eval_script(eval_script, Path(f.name))
    extra = {
        key: result.get(key)
        for key in ("input", "expected_output", "matched", "interpreter", "errors", "attempts")
        if result.get(key) is not None
    }
    return _normalize_result(program, result, extra=extra or None)

def eval_source_with_io(language, source_code, input_data, expected_outputs):
    eval_script, file_ext = _resolve_evaluator(language)

    normalized_expected = list(expected_outputs or [])

    if language in ("java", "scala", "kotlin"):
        class_file = {
            "java": "Problem.java",
            "scala": "Problem.scala",
            "kotlin": "Problem.kt",
        }[language]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / class_file
            p.write_text(source_code, encoding="utf-8")
            result = _invoke_eval_script(eval_script, p, input_data=input_data, expected_outputs=normalized_expected)
            extra = {
                key: result.get(key)
                for key in ("input", "expected_output", "matched", "interpreter", "errors", "attempts")
                if result.get(key) is not None
            }
            normalized = _normalize_result(
                source_code,
                result,
                extra=extra or None,
            )
    else:
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=True) as f:
            f.write(source_code.encode("utf-8"))
            f.flush()
            result = _invoke_eval_script(
                eval_script,
                Path(f.name),
                input_data=input_data,
                expected_outputs=normalized_expected,
            )
        extra = {
            key: result.get(key)
            for key in ("input", "expected_output", "matched", "interpreter", "errors", "attempts")
            if result.get(key) is not None
        }
        normalized = _normalize_result(source_code, result, extra=extra or None)

    stdout_value = normalized.get("stdout", "")
    stdout_comp = stdout_value.rstrip("\r\n")
    expected_comp = [item.rstrip("\r\n") for item in normalized_expected]
    matched = bool(expected_comp) and any(stdout_comp == candidate for candidate in expected_comp)

    if "input" not in normalized:
        normalized["input"] = input_data
    if "expected_output" not in normalized or normalized["expected_output"] is None:
        normalized["expected_output"] = normalized_expected
    if "matched" not in normalized:
        normalized["matched"] = matched
    else:
        normalized["matched"] = bool(normalized["matched"]) or matched
    return normalized
