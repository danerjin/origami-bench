"""Non-LLM reference providers: the oracle (upper bound) and trivial baselines (lower bound)."""

from __future__ import annotations

import json
from pathlib import Path

from ..tasks import Task
from .base import Provider, PythonSandbox, RunResult


def _wrap(obj) -> str:
    return "```json\n" + json.dumps(obj) + "\n```"


class OracleProvider(Provider):
    """Answers with the hidden reference solution. Should score 1.0 everywhere."""

    name = "oracle"

    def run(self, task: Task, prompt: str, images: list[Path], sandbox: PythonSandbox | None,
            max_steps: int) -> RunResult:
        from ..build import oracle_answer

        return RunResult(oracle_answer(task))


class UnfoldedProvider(Provider):
    """Trivial baseline: claims the paper stays flat (AF) or folds it in half once (design)."""

    name = "unfolded"

    def run(self, task: Task, prompt: str, images: list[Path], sandbox: PythonSandbox | None,
            max_steps: int) -> RunResult:
        if task.track == "analytic":
            cp = task.inputs["crease_pattern"]
            return RunResult(_wrap({"foldable": True, "folded_vertices": cp["vertices_coords"]}))
        return RunResult(_wrap({"creases": [[0.5, 0, 0.5, 1, "V"]]}))
