"""Minimal FastAPI server mirroring the batch evaluator.

The ``/evaluate`` endpoint accepts exactly the same JSON structure used by
``main.py`` for batch evaluation.  The request body must contain at least the
following keys:

* ``language``    - name of the programming language (e.g. ``"python"``)
* ``prompt``      - preamble string containing helper code
* ``tests``       - test code appended after each completion
* ``completions`` - list of completion strings to evaluate

Additional keys such as ``name`` or ``stop_tokens`` are preserved in the
response.  The response matches the per-file output of ``main.py`` and contains
a ``results`` array with one entry for each completion.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import time
from containerized_eval import eval_string_script
import asyncio
from concurrent.futures import ThreadPoolExecutor

class EvalRequest(BaseModel):
    """Input format matching ``main.py``."""

    language: str
    prompt: str
    tests: str
    completions: List[str]
    name: Optional[str] = None
    stop_tokens: Optional[List[str]] = None

executor = ThreadPoolExecutor(max_workers=100)
semaphore = asyncio.Semaphore(100)

app = FastAPI()

def _eval_completion(problem: dict, idx: int) -> dict:
    """Evaluate a single completion synchronously."""
    program = problem["prompt"] + problem["completions"][idx] + "\n" + problem["tests"]
    result = eval_string_script(problem["language"], program)
    result["program"] = program
    result["timestamp"] = int(time.time())
    return result

def _evaluate_problem(problem: dict) -> dict:
    """Evaluate all completions from ``problem`` and return a result dict."""
    test_results = problem.copy()
    completions = test_results.pop("completions", [])
    test_results["results"] = []
    if not completions:
        return test_results

    max_workers = min(len(completions), 100)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for res in pool.map(lambda idx: _eval_completion(problem, idx), range(len(completions))):
            test_results["results"].append(res)
    return test_results

@app.post("/evaluate")
async def evaluate(req: EvalRequest):
    """Evaluate all completions from the request and return results."""
    loop = asyncio.get_running_loop()
    problem = req.dict()
    try:
        async with semaphore:
            return await asyncio.wait_for(
                loop.run_in_executor(executor, _evaluate_problem, problem),
                timeout=30,
            )
    except asyncio.TimeoutError:
        truncated = problem.copy()
        truncated.pop("completions", None)
        truncated["results"] = [
            {
                "program": "",
                "stdout": "",
                "stderr": "Timeout",
                "exit_code": -1,
                "status": "Timeout",
                "timestamp": int(time.time()),
            }
        ]
        return truncated

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=9090,
        workers=4,
        limit_concurrency=100,
    )
