"""Export tasks for offline / external-agent evaluation (no hidden reference data).

    python -m creasebench.export --out DIR [--ids ...] [--tiers ...] [--agentic]

Each task becomes ``DIR/<folder>/`` with ``prompt.md`` (exactly the prompt the runner
would send), the task's images, and every input as ``<key>.json``. Folder names are opaque
by default: task ids can name the answer (``adv-bug-global-...``), so the id -> folder map is
written next to DIR as ``DIR.ids.json``, outside what an agent is shown (``--plain`` keeps the
ids). Agents write their final reply to ``DIR/<folder>/answer.txt``; grade with

    python -m creasebench.run --provider file --answers DIR --ids ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
from pathlib import Path

from .prompts import build_prompt
from .tasks import load_tasks


def id_map_path(out: Path) -> Path:
    out = Path(out)
    return out.with_name(out.name.rstrip("/") + ".ids.json")


def export(tasks, out: Path, agentic: bool = False, opaque: bool = True) -> dict[str, str]:
    """Write the tasks; returns {task_id: folder name}."""
    out.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_hex(8)
    folders = {}
    for t in tasks:
        name = "task-" + hashlib.sha256((salt + t.id).encode()).hexdigest()[:10] if opaque else t.id
        folders[t.id] = name
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "prompt.md").write_text(build_prompt(t, agentic=agentic))
        for p in t.image_paths():
            shutil.copy(p, d / p.name)
        for key, val in t.inputs.items():
            (d / f"{key}.json").write_text(json.dumps(val))
    if opaque:
        id_map_path(out).write_text(json.dumps(folders, indent=1))
    return folders


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks-dir", default="tasks")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--tiers", default="basic,advanced")
    ap.add_argument("--agentic", action="store_true", help="include the python-tool note in prompts")
    ap.add_argument("--plain", action="store_true", help="name folders by task id (leaks the id)")
    args = ap.parse_args(argv)
    tasks = load_tasks(args.tasks_dir, ids=args.ids, tiers=args.tiers.split(","))
    if args.ids:
        tasks = [t for t in tasks if t.id in set(args.ids)]
    export(tasks, Path(args.out), args.agentic, opaque=not args.plain)
    print(f"exported {len(tasks)} tasks to {args.out}")


if __name__ == "__main__":
    main()
