from pathlib import Path
from typing import List

from eval_python_common import eval_with_interpreter


def eval_script(
    path: Path,
    input_data: str | None = None,
    expected_outputs: List[str] | None = None,
):
    return eval_with_interpreter(
        path=path,
        input_data=input_data,
        expected_outputs=expected_outputs,
        executable="python2",
        interpreter_label="python2",
    )
