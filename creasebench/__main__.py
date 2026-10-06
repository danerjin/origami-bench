"""Utility CLI for working with crease patterns.

    python -m creasebench verify pattern.json [--render out_prefix]
    python -m creasebench grade <task_dir> answer.txt

``pattern.json`` may be a FOLD file or a design answer ({"creases": [...]}).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cp import CreasePattern
from .graders import answer_cp, grade
from .render import render_cp, render_folded
from .tasks import load_task
from .verify import verify


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="check flat-foldability of a crease pattern")
    v.add_argument("path")
    v.add_argument("--render", metavar="PREFIX", help="write PREFIX_cp.png and PREFIX_folded.png")
    g = sub.add_parser("grade", help="grade a saved model response against a task")
    g.add_argument("task")
    g.add_argument("response")
    args = ap.parse_args(argv)

    if args.cmd == "verify":
        d = json.loads(Path(args.path).read_text())
        cp = answer_cp(d) if "creases" in d else CreasePattern.from_fold(d)
        rep = verify(cp)
        print(json.dumps(rep.summary(), indent=1))
        if rep.folded is not None:
            sil = rep.folded.silhouette()
            print(f"folded silhouette area: {sil.area:.6f}")
        if args.render:
            render_cp(cp, f"{args.render}_cp.png")
            if rep.folded is not None:
                render_folded(rep.folded, f"{args.render}_folded.png",
                              above=rep.layers.face_above if rep.layers else None)
    elif args.cmd == "grade":
        print(json.dumps(grade(load_task(args.task), Path(args.response).read_text()), indent=1, default=str))


if __name__ == "__main__":
    main()
