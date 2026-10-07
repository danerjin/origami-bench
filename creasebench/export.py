"""Export tasks for offline / external-agent evaluation (no hidden reference data).

    python -m creasebench.export --out DIR [--ids ...] [--tiers ...] [--agentic]

Each task becomes ``DIR/<task_id>/`` with ``prompt.md`` (exactly the prompt the runner
would send), the task's images, and every input as ``<key>.json``. Agents write their
final reply to ``DIR/<task_id>/answer.txt``; grade with

    python -m creasebench.run --provider file --answers DIR --ids ...
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .prompts import build_prompt
from .tasks import load_tasks


def export(tasks, out: Path, agentic: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for t in tasks:
        d = out / t.id
        d.mkdir(parents=True, exist_ok=True)
        (d / "prompt.md").write_text(build_prompt(t, agentic=agentic))
        for p in t.image_paths():
            shutil.copy(p, d / p.name)
        for key, val in t.inputs.items():
            (d / f"{key}.json").write_text(json.dumps(val))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks-dir", default="tasks")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--tiers", default="basic,advanced")
    ap.add_argument("--agentic", action="store_true", help="include the python-tool note in prompts")
    args = ap.parse_args(argv)
    tasks = load_tasks(args.tasks_dir, ids=args.ids, tiers=args.tiers.split(","))
    if args.ids:
        tasks = [t for t in tasks if t.id in set(args.ids)]
    export(tasks, Path(args.out), args.agentic)
    print(f"exported {len(tasks)} tasks to {args.out}")


if __name__ == "__main__":
    main()
