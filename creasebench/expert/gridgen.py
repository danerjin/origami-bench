"""Offline search for certified minimal-grid box-pleated references (expert min-grid family).

Usage: python -m creasebench.expert.gridgen
"""

from __future__ import annotations

import json
import time

from .refgen import CACHE

# integer trees (node 0 = body); lengths in grid units. Uneven flaps make the packing non-trivial.
GRID_TREES = {
    # star and two-hub trees (the shapes BP Studio's pleat completion handles), uneven integer flaps
    "lizard": [(0, 1, 8), (0, 2, 8), (0, 3, 8), (0, 4, 16), (4, 5, 8), (4, 6, 8), (4, 7, 8)],
    "star5": [(0, 1, 7), (0, 2, 5), (0, 3, 5), (0, 4, 3), (0, 5, 6)],
    "star6": [(0, 1, 6), (0, 2, 6), (0, 3, 4), (0, 4, 4), (0, 5, 3), (0, 6, 5)],
    "hub2a": [(0, 7, 3), (0, 1, 5), (0, 2, 5), (0, 3, 4), (7, 4, 6), (7, 5, 6), (7, 6, 2)],
    "hub2b": [(0, 7, 2), (0, 1, 7), (0, 2, 4), (7, 3, 5), (7, 4, 5), (7, 5, 3)],
    "hub2c": [(0, 7, 4), (0, 1, 6), (0, 2, 6), (0, 3, 2), (7, 4, 4), (7, 5, 4), (7, 6, 5)],
    "star7": [(0, 1, 5), (0, 2, 5), (0, 3, 4), (0, 4, 4), (0, 5, 3), (0, 6, 3), (0, 7, 6)],
}


def main():
    from ..gen.bpgrid import certified_min_grid

    CACHE.mkdir(parents=True, exist_ok=True)
    for name, edges in GRID_TREES.items():
        f = CACHE / f"grid-{name}.json"
        if f.exists():
            print(name, "cached", flush=True)
            continue
        t0 = time.time()
        print(name, flush=True)
        r = certified_min_grid(edges, tries_per_grid=25, slack=4, log=lambda s: print(s, flush=True))
        if r is None:
            f.write_text(json.dumps({"name": name, "edges": edges, "result": None}))
            continue
        n_pack, n_ref, cp, lay = r
        res = None
        if cp is not None:
            res = {"n_pack": n_pack, "n_ref": n_ref, "layout": {str(k): v for k, v in lay.items()},
                   "num_creases": cp.num_creases(),
                   "segments": [[float(p[0]), float(p[1]), float(q[0]), float(q[1]), a] for p, q, a in cp.segments()]}
        print(name, "n_pack", n_pack, "n_ref", n_ref, f"{time.time()-t0:.0f}s", flush=True)
        f.write_text(json.dumps({"name": name, "edges": edges, "n_pack": n_pack, "result": res}))


if __name__ == "__main__":
    main()
