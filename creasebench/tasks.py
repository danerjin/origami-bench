"""Task schema and loading.

A task lives in ``tasks/<track>/<task_id>/`` as ``task.json`` plus image assets.
Everything under the ``reference`` key is hidden from the model and only used
by graders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

TRACKS = ("analytic", "design_text", "design_image", "read", "solve", "pack", "design")
TRACK_ALIASES = {"af": "analytic", "dt": "design_text", "di": "design_image"}


@dataclass
class Task:
    id: str
    track: str
    difficulty: str  # "easy" | "medium" | "hard"
    prompt: str  # task-specific instructions (shared conventions are added by prompts.py)
    inputs: dict = field(default_factory=dict)  # data shown to the model (inline JSON)
    images: list[str] = field(default_factory=list)  # asset file names shown to the model
    reference: dict = field(default_factory=dict)  # hidden grading data
    meta: dict = field(default_factory=dict)
    root: Path | None = None  # directory containing the task, set on load

    def image_paths(self) -> list[Path]:
        assert self.root is not None
        return [self.root / name for name in self.images]

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("root")
        return d

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "task.json").write_text(json.dumps(self.to_json(), indent=1))
        self.root = directory


HARD_MIN_CREASES = 100  # analysis tasks on patterns this large are in the hard split
HARD_MIN_LEAVES = 6  # design / packing targets with this many flaps are in the hard split


def _num_creases(task: "Task") -> int:
    if task.meta.get("num_creases"):
        return int(task.meta["num_creases"])
    cp = task.inputs.get("crease_pattern") or {}
    return sum(1 for a in cp.get("edges_assignment", []) if a != "B")


def _num_leaves(task: "Task") -> int:
    tree = task.inputs.get("tree") or {}
    deg: dict = {}
    for e in tree.get("edges", []):
        for n in e[:2]:
            deg[n] = deg.get(n, 0) + 1
    return sum(1 for d in deg.values() if d == 1)


def task_split(task: "Task") -> str:
    """Reporting split: ``warmup`` (basic tier), ``hard`` (big patterns, many-flap targets) or
    ``core`` (the rest of the advanced tier). The headline number is the ``hard`` split."""
    if task.meta.get("split"):
        return task.meta["split"]
    if task.meta.get("tier", "basic") != "advanced":
        return "warmup"
    family = (task.reference or {}).get("family")
    if family in ("pack", "read-tech", "read-color"):
        return "core"  # an optimizer or a direct analysis answers these at any size
    if task.track == "design":
        return "hard" if _num_leaves(task) >= HARD_MIN_LEAVES else "core"
    return "hard" if _num_creases(task) >= HARD_MIN_CREASES else "core"


def load_task(path: str | Path) -> Task:
    path = Path(path)
    if path.is_dir():
        path = path / "task.json"
    d = json.loads(path.read_text())
    t = Task(**d)
    t.root = path.parent
    return t


def load_tasks(root: str | Path = "tasks", tracks=None, ids=None, difficulty=None, tiers=None) -> list[Task]:
    root = Path(root)
    tracks = [TRACK_ALIASES.get(t, t) for t in (tracks or TRACKS)]
    out = []
    for p in sorted(root.glob("*/*/task.json")):
        t = load_task(p)
        if t.track not in tracks:
            continue
        if ids and not any(t.id == i or t.id.startswith(i) for i in ids):
            continue
        if difficulty and t.difficulty not in difficulty:
            continue
        if tiers and t.meta.get("tier", "basic") not in tiers:
            continue
        out.append(t)
    return out
