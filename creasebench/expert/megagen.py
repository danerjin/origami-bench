"""Offline generation of certified 600-1100 crease patterns for the expert split.

Two sources:
  * mirror tilings (2x2) of certified BP Studio designs: neighbouring cells are reflections, the
    cell boundaries are new creases, and the whole assignment is re-solved;
  * random mixed 22.5-degree tilings (n x n cells of bird / preliminary / waterbomb / fish / blintz
    modules), which have no global symmetry to exploit.
Only patterns that the full flat-foldability check certifies (long budget) are cached.

Usage: python -m creasebench.expert.megagen
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .refgen import CACHE

BP = Path(__file__).resolve().parents[1] / "gen" / "bpstudio" / "samples" / "certified"


def mirror2x2(cp):
    """Segments of a 2x2 mirror tiling of a unit-square CP; every crease left unassigned."""
    segs = []
    for p, q, a in cp.segments():
        if a == "B":
            continue
        for fx in (0, 1):
            for fy in (0, 1):
                def t(pt):
                    x, y = pt
                    x = (1 - x) if fx else x
                    y = (1 - y) if fy else y
                    return (0.5 * x + 0.5 * fx, 0.5 * y + 0.5 * fy)
                segs.append((t(p), t(q), "U"))
    segs += [((0.5, 0.0), (0.5, 1.0), "U"), ((0.0, 0.5), (1.0, 0.5), "U")]
    return segs


def main(timeout: float = 1800.0):
    from ..cp import CreasePattern
    from ..gen import bases22
    from ..verify import complete_assignment

    CACHE.mkdir(parents=True, exist_ok=True)
    jobs = [(f"mirror-{n}", "bp", n) for n in ("tight_0_00", "random_0_18", "lizard_32")]
    jobs += [(f"tiling22-{n}x{n}-s{s}", "t22", (n, s)) for n, s in ((5, 1), (5, 2), (6, 1), (6, 2))]
    for name, kind, arg in jobs:
        f = CACHE / f"mega-{name}.json"
        if f.exists():
            print(name, "cached", flush=True)
            continue
        t0 = time.time()
        if kind == "bp":
            src = CreasePattern.from_fold(json.loads((BP / f"{arg}.fold").read_text()), rebuild=True)
            segs = mirror2x2(src)
        else:
            n, s = arg
            segs, _ = bases22.random_tiling(n, np.random.default_rng(s))
        cp = CreasePattern.from_segments(segs, tol=1e-9)
        if cp.warnings:
            print(name, "geometry warnings", cp.warnings[:2], flush=True)
            continue
        print(name, cp.num_creases(), "creases; certifying...", flush=True)
        out = complete_assignment(cp, timeout=timeout)
        dt = time.time() - t0
        if out is None:
            print(name, f"NOT certified ({dt:.0f}s)", flush=True)
            f.write_text(json.dumps({"name": name, "result": None}))
            continue
        print(name, f"certified ({dt:.0f}s)", flush=True)
        f.write_text(json.dumps({"name": name, "num_creases": out.num_creases(), "seconds": dt,
                                 "segments": [[*map(float, (*p, *q)), a] for p, q, a in out.segments()]}))


if __name__ == "__main__":
    main()
