"""
Importable wrapper for running MultiPL-E evaluations inside a Singularity image.

Example:
    from singularity_eval_wrapper import SingularityEvaluator

    evaluator = SingularityEvaluator("multipl-e-eval_sandbox")
    result = evaluator.eval_string("python3", 'print("OK")\\n')
    print(result["status"], result["stdout"])

For stdin / expected-output style tasks:
    result = evaluator.eval_source_with_io(
        "python3",
        "import sys\\nprint(sys.stdin.readline().strip())\\n",
        "hello\\n",
        ["hello"],
    )
    print(result["matched"])
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Iterable


CONTAINER_RUNNER = r"""
import json
import sys
import traceback

from containerized_eval import eval_source_with_io, eval_string_script

payload = json.load(sys.stdin)
requests = payload.get("requests", [])
responses = []

for req in requests:
    try:
        mode = req["mode"]
        if mode == "string":
            result = eval_string_script(req["language"], req["program"])
        elif mode == "io":
            result = eval_source_with_io(
                req["language"],
                req["source_code"],
                req.get("input", ""),
                req.get("expected_output", []),
            )
        else:
            raise ValueError(f"unknown mode: {mode}")
        responses.append({"ok": True, "result": result})
    except Exception:
        responses.append({
            "ok": False,
            "error": traceback.format_exc(),
            "result": {
                "status": "Exception",
                "exit_code": -1,
                "stdout": "",
                "stderr": traceback.format_exc(),
            },
        })

print(json.dumps({"responses": responses}, ensure_ascii=True))
"""


class SingularityEvaluationError(RuntimeError):
    """Raised when Singularity itself fails before returning evaluator results."""

    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = ""):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass
class SingularityEvaluator:
    """Run MultiPL-E evaluator calls in a Singularity sandbox or SIF image."""

    image: str
    runtime: str = "singularity"
    pwd: str = "/code"
    cleanenv: bool = True
    binds: list[str] = field(default_factory=list)
    timeout: float = 300.0

    def eval_string(self, language: str, program: str, *, timeout: float | None = None) -> dict[str, Any]:
        """Evaluate a complete program string with containerized_eval.eval_string_script."""
        response = self.eval_batch(
            [{"mode": "string", "language": language, "program": program}],
            timeout=timeout,
        )[0]
        return response["result"]

    def eval_source_with_io(
        self,
        language: str,
        source_code: str,
        input_data: str,
        expected_output: Iterable[str],
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Evaluate source with stdin and expected outputs."""
        response = self.eval_batch(
            [
                {
                    "mode": "io",
                    "language": language,
                    "source_code": source_code,
                    "input": input_data,
                    "expected_output": list(expected_output),
                }
            ],
            timeout=timeout,
        )[0]
        return response["result"]

    def eval_batch(
        self,
        requests: list[dict[str, Any]],
        *,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate multiple requests in one Singularity process.

        Each request must have either:
        - {"mode": "string", "language": ..., "program": ...}
        - {"mode": "io", "language": ..., "source_code": ..., "input": ..., "expected_output": [...]}
        """
        cmd = self._command()
        proc = subprocess.run(
            cmd,
            input=json.dumps({"requests": requests}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout if timeout is None else timeout,
        )

        if proc.returncode != 0:
            raise SingularityEvaluationError(
                f"{self.runtime} exited with status {proc.returncode}",
                returncode=proc.returncode,
                stderr=proc.stderr,
            )

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SingularityEvaluationError(
                "Evaluator returned non-JSON output",
                returncode=proc.returncode,
                stderr=(proc.stderr + "\nstdout:\n" + proc.stdout),
            ) from exc

        responses = payload.get("responses")
        if not isinstance(responses, list):
            raise SingularityEvaluationError(
                "Evaluator JSON did not contain a responses list",
                returncode=proc.returncode,
                stderr=(proc.stderr + "\nstdout:\n" + proc.stdout),
            )
        return responses

    def _command(self) -> list[str]:
        cmd = [self.runtime, "exec"]
        if self.cleanenv:
            cmd.append("--cleanenv")
        for bind in self.binds:
            cmd.extend(["--bind", bind])
        if self.pwd:
            cmd.extend(["--pwd", self.pwd])
        cmd.extend([self.image, "python3", "-c", CONTAINER_RUNNER])
        return cmd


def eval_string(
    image: str,
    language: str,
    program: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience function for one-off complete-program evaluation."""
    return SingularityEvaluator(image=image, **kwargs).eval_string(language, program)


def eval_source_with_io(
    image: str,
    language: str,
    source_code: str,
    input_data: str,
    expected_output: Iterable[str],
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience function for one-off stdin/expected-output evaluation."""
    return SingularityEvaluator(image=image, **kwargs).eval_source_with_io(
        language,
        source_code,
        input_data,
        expected_output,
    )
