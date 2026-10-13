"""Offline generation of certified TreeMaker reference designs for the expert split.

For each target tree, TreeMaker is run with several seeds; a result is kept only if it covers the
square, passes local checks, completes to a globally flat-foldable M/V assignment and folds to a
base whose extracted tree realizes the target (scale > 0). The best-scale certified result is
cached as JSON under ``tasks/expert_cache/`` so task builds stay deterministic and fast.

Usage: python -m creasebench.expert.refgen [names...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

CACHE = Path(__file__).resolve().parents[2] / "tasks" / "expert_cache"


def certify_treemaker(edges, seeds=(1, 2, 3, 4), timeout=240.0, verify_timeout=900.0, max_corner_sets=6, log=print):
    from ..cp import CreasePattern
    from ..gen import treemaker
    from ..tree import extract_trees
    from ..treefit import TargetTree, best_fit
    from ..verify import complete_assignment, verify

    target = TargetTree.from_json({"edges": edges})
    best = None
    for seed in seeds:
        t0 = time.time()
        try:
            r = treemaker.generate(edges, timeout=timeout, corners="auto", seed=seed, restarts=8,
                                   max_corner_sets=max_corner_sets)
        except Exception as e:  # noqa: BLE001
            log(f"  seed {seed}: treemaker failed: {e}")
            continue
        if not (r.get("ok") and r.get("local_ok") and r.get("covers_square")):
            log(f"  seed {seed}: ok={r.get('ok')} local={r.get('local_ok')} cover={r.get('covers_square')}")
            continue
        segs = [s[:5] for s in r["creases"] if s[4] != "F"]
        cp = CreasePattern.from_segments(segs, tol=1e-5)
        cp = complete_assignment(cp, timeout=verify_timeout)
        if cp is None:
            log(f"  seed {seed}: no global assignment")
            continue
        rep = verify(cp, timeout=verify_timeout)
        if not rep.foldable:
            log(f"  seed {seed}: verify {rep.summary().get('reason')}")
            continue
        fit = best_fit(extract_trees(rep.folded), target)
        log(f"  seed {seed}: certified, {cp.num_creases()} creases, tm_scale={r['scale']:.4f} fit={fit.scale:.4f} "
            f"({time.time()-t0:.0f}s)")
        if fit.scale <= 0:
            continue
        if best is None or fit.scale > best["scale"]:
            best = {"scale": fit.scale, "tm_scale": r["scale"], "seed": seed, "num_creases": cp.num_creases(),
                    "segments": [[float(p[0]), float(p[1]), float(q[0]), float(q[1]), a] for p, q, a in cp.segments()]}
    return best


def main(names, retry=False):
    from ..trees import BIG_TREES, SEMANTIC_TREES, EXPERT_TREES

    allt = {**SEMANTIC_TREES, **BIG_TREES, **EXPERT_TREES}
    CACHE.mkdir(parents=True, exist_ok=True)
    for name in names or list(allt):
        f = CACHE / f"tm-{name}.json"
        if f.exists() and not (retry and json.loads(f.read_text())["result"] is None):
            print(name, "cached"); continue
        print(name, flush=True)
        kw = dict(seeds=range(5, 11), max_corner_sets=14, timeout=400.0) if retry else {}
        best = certify_treemaker(allt[name]["edges"], log=lambda s: print(s, flush=True), **kw)
        f.write_text(json.dumps({"name": name, "edges": allt[name]["edges"], "result": best}))
        print(name, "->", None if best is None else f"scale {best['scale']:.4f}", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    main([a for a in args if a != "--retry"], retry="--retry" in args)
