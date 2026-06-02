"""Minimal FastAPI server for evaluating completions.

This API exposes one POST endpoint ``/evaluate`` which accepts a JSON
payload describing the completions to execute. The expected schema is the
same as the files consumed by :mod:`evaluation.src.main`, namely::

    {
        "name": "HumanEval_53_add",           # optional
        "language": "python",
        "prompt": "...",
        "tests": "...",
        "completions": ["completion1", "completion2"],
        "stop_tokens": ["\n"]
    }

The response mirrors the structure produced by ``evaluation.src.main`` where
``completions`` is replaced with ``results`` containing execution metadata for
each completion.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from containerized_eval import eval_string_script, eval_source_with_io
import traceback

# ==== Lambda-specific settings (configurable via environment variables) ====
# A single Lambda execution environment has limited vCPU, so avoid excessive threads/semaphores.
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "16"))
EVAL_TIMEOUT = float(os.getenv("EVAL_TIMEOUT", "30"))

class EvalRequest(BaseModel):
    """Request model matching ``evaluation.src.main`` input files."""

    language: str
    prompt: str | None = None
    tests: str | None = None
    completions: list[str] | None = None
    source_code: str | None = None
    input: str | None = None
    output: list[str] | None = None
    name: str | None = None
    stop_tokens: list[str] | None = None
    eval_timeout: float | None = None

    class Config:
        extra = "allow"

# Thread pool and semaphore to control concurrency within a single Lambda instance
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
semaphore = asyncio.Semaphore(CONCURRENCY)

app = FastAPI()

@app.get("/healthz")
async def healthz():
    """Health check endpoint."""
    return {"status": "ok"}

@app.post("/evaluate")
async def evaluate(req: EvalRequest):
    """Execute the provided completions and return the results.

    Parameters
    ----------
    req: EvalRequest
        JSON payload describing a set of completions in the same format as used
        by :mod:`evaluation.src.main`.

    Returns
    -------
    dict
        JSON object with execution metadata including ``stdout``,
        ``stderr``, ``exit_code``, ``status`` and ``timestamp``.
    """
    loop = asyncio.get_running_loop()
    results = []
    eval_timeout = EVAL_TIMEOUT if req.eval_timeout is None else float(req.eval_timeout)

    if (
        req.completions is not None
        and req.prompt is not None
        and req.tests is not None
    ):
        # Note: stop_tokens is passed through as-is if used by containerized_eval
        for completion in req.completions:
            # Construct the program: prompt + completion + tests
            program = req.prompt + completion + "\n" + req.tests
            try:
                async with semaphore:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            executor, eval_string_script, req.language, program
                        ),
                        timeout=eval_timeout,
                    )
            except asyncio.TimeoutError:
                result = {
                    "program": program,
                    "stdout": "",
                    "stderr": f"Timeout after {eval_timeout} seconds (api wait_for)",
                    "exit_code": -1,
                    "status": "Timeout",
                }
            except Exception:
                result = {
                    "program": program,
                    "stdout": "",
                    "stderr": traceback.format_exc()[:8000],
                    "exit_code": -1,
                    "status": "Exception",
                }
            # Add timestamp
            result["timestamp"] = int(time.time())
            results.append(result)

        response = req.dict()
        response.pop("completions", None)
        response["results"] = results
        return response

    if (
        req.source_code is not None
        and req.input is not None
        and req.output is not None
    ):
        try:
            async with semaphore:
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        executor,
                        eval_source_with_io,
                        req.language,
                        req.source_code,
                        req.input,
                        req.output,
                    ),
                    timeout=eval_timeout,
                )
        except asyncio.TimeoutError:
            result = {
                "program": req.source_code,
                "stdout": "",
                "stderr": f"Timeout after {eval_timeout} seconds (api wait_for)",
                "exit_code": -1,
                "status": "Timeout",
            }
        except Exception:
            result = {
                "program": req.source_code,
                "stdout": "",
                "stderr": traceback.format_exc()[:8000],
                "exit_code": -1,
                "status": "Exception",
            }
        result["timestamp"] = int(time.time())
        response = req.dict()
        response["results"] = [result]
        return response

    raise HTTPException(
        status_code=400,
        detail=(
            "Invalid request payload: provide either prompt/tests/completions "
            "or source_code/input/output."
        ),
    )

# ==== Single-line addition for Lambda (RIC + Mangum) ====
from mangum import Mangum
handler = Mangum(app)

# ==== Local execution (not used in Lambda production) ====
if __name__ == "__main__":
    import uvicorn
    # In local testing, workers>1 is possible, but in Lambda concurrency is achieved by scaling instances, so 1 is typical
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "9090")),
        workers=int(os.getenv("UVICORN_WORKERS", "1")),
        limit_concurrency=CONCURRENCY,
    )
