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


class HeuristicProvider(Provider):
    """Non-LLM algorithmic baseline for the advanced tier.

    * pack: put every flap tip on the paper boundary in depth-first (tree) order, spaced
      proportionally to the tree distance between consecutive tips -- the classic
      "edge flaps" layout, always valid and usually far from optimal;
    * other advanced families: no answer (scores 0), marking what needs real design work.
    """

    name = "heuristic"

    def run(self, task: Task, prompt: str, images: list[Path], sandbox: PythonSandbox | None,
            max_steps: int) -> RunResult:
        if task.reference.get("family") != "pack":
            if task.meta.get("tier") == "advanced":
                return RunResult("", error="no heuristic for this family")
            return UnfoldedProvider().run(task, prompt, images, sandbox, max_steps)
        import networkx as nx

        from ..treefit import TargetTree

        t = TargetTree.from_json(task.inputs["tree"])
        g = t.graph
        root = max(g, key=g.degree)
        order = [n for n in nx.dfs_preorder_nodes(g, root) if g.degree(n) == 1]
        d = [nx.dijkstra_path_length(g, a, b, weight="length") for a, b in zip(order, order[1:] + order[:1])]
        total = sum(d)
        pos, acc = {}, 0.0
        for leaf, step in zip(order, d):
            s = 4.0 * acc / total  # perimeter parameter in [0, 4)
            side, f = int(s), s - int(s)
            xy = [(f, 0.0), (1.0, f), (1 - f, 1.0), (0.0, 1 - f)][side]
            pos[leaf] = [round(xy[0], 6), round(xy[1], 6)]
            acc += step
        return RunResult(_wrap({"positions": pos}))


class FileProvider(Provider):
    """Reads answers written by an external agent: ``<answers_dir>/<folder>/answer.txt``.

    The folder is the task id, or the opaque name ``export`` recorded in ``<answers_dir>.ids.json``."""

    name = "file"

    def __init__(self, answers_dir: str):
        self.root = Path(answers_dir)
        m = self.root.with_name(self.root.name + ".ids.json")
        self.folders = json.loads(m.read_text()) if m.exists() else {}

    def run(self, task: Task, prompt: str, images: list[Path], sandbox: PythonSandbox | None,
            max_steps: int) -> RunResult:
        p = self.root / self.folders.get(task.id, task.id) / "answer.txt"
        if not p.exists():
            return RunResult("", error="no answer file")
        return RunResult(p.read_text())
