from pathlib import Path
from typing import List

from eval_python3 import eval_script as eval_script_python3

# Compatibility wrapper that keeps the legacy import path but now delegates
# to the dedicated Python 3 evaluator.
def eval_script(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    return eval_script_python3(path=path, input_data=input_data, expected_outputs=expected_outputs)
