"""Task schema and loading.

A task lives in ``tasks/<track>/<task_id>/`` as ``task.json`` plus image assets.
Everything under the ``reference`` key is hidden from the model and only used
by graders.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

TRACKS = ("analytic", "design_text", "design_image")
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


def load_task(path: str | Path) -> Task:
    path = Path(path)
    if path.is_dir():
        path = path / "task.json"
    d = json.loads(path.read_text())
    t = Task(**d)
    t.root = path.parent
    return t


def load_tasks(root: str | Path = "tasks", tracks=None, ids=None, difficulty=None) -> list[Task]:
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
        out.append(t)
    return out
