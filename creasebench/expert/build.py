"""Expert split: tasks scored strictly pass/fail, each with a certified reference that passes its own grader.

Families (all ``meta["split"] = "expert"``):

* ``expert-design-*``      design a base for a 14-27 flap tree at >= 95% of a certified TreeMaker
                           reference's scale (universal-molecule packing);
* ``expert-thin-*``        the same, and the base may be no thicker (max paper layers) than the reference;
* ``expert-read-tree-*``   exact tree of a certified TreeMaker base (non-lattice geometry, many flaps);
* ``expert-inverse-*``     reconstruct a crease pattern from its folded base alone (outline + x-ray image + tree);
* ``expert-min-grid-*``    a box-pleated base on the smallest grid known (certified BP Studio layout);
* ``expert-repair-*``      repair several M/V defects (flips + a locally invisible global conflict);
* ``expert-solve-mega-*``  assign 600-1100 crease patterns (2x2 mirror tilings of BP designs, random 22.5 tilings).

References are generated offline (``python -m creasebench.expert.refgen`` / ``megagen`` / ``gridgen``) and
cached under ``tasks/expert_cache``; this builder only reads the cache.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from ..build_advanced import READ_TREE_PROMPT, SOLVE_PROMPT, _save, base_tree, fold_input, segs_json
from ..cp import CreasePattern
from ..packing import packing_bound
from ..render import render_folded
from ..tasks import Task
from ..tree import extract_trees, layer_count
from ..treefit import TargetTree, best_fit
from ..verify import verify
from .refgen import CACHE

VERIFY_TIMEOUT = 900.0  # graders and oracle self-check share this budget
DESIGN_THRESHOLD = 0.95

EXPERT_DESIGN_PROMPT = (
    "Design a crease pattern for ONE uncut unit square whose flat-folded base realizes the target tree below "
    "(the stick figure of {subject}). This is graded pass/fail: the base must fold flat and realize the tree "
    "at a scale of at least {thr:.5f} (one unit of tree length -> {thr:.5f} of the paper side). {extra}")
REPAIR_PROMPT = (
    "The crease pattern below was flat-foldable, but {k} of its mountain/valley assignments have been changed "
    "(some changes break Maekawa/Kawasaki-style local conditions, at least one only breaks the global layer "
    "order). Repair it: return a full M/V assignment of the SAME creases that folds flat, changing at most {k} "
    "assignments relative to the given pattern. Pass/fail.")
INVERSE_PROMPT = (
    "Below is a flat-folded origami base, folded from ONE uncut unit square: its outline (`folded_outline`, "
    "coordinates in units of the paper side), an x-ray image of the folded state (all layers drawn "
    "translucently), and the stick-figure tree it realizes. Reconstruct the crease pattern. Pass/fail: your "
    "pattern must fold flat, realize the tree at a scale of at least {thr:.5f}, and its folded outline must "
    "match the given one (IoU >= {iou} after the best rotation/reflection/translation).")
MIN_GRID_PROMPT = (
    "Design a BOX-PLEATED crease pattern (every crease at 0/45/90/135 degrees) for ONE uncut unit square whose "
    "flat-folded base realizes the tree below, with tree lengths in grid units: a flap of length L uses L grid "
    "squares. Pass/fail: the scale must be at least 1/{n} (i.e. the layout must fit an N x N grid with N <= {n}; "
    "the best layout we know needs exactly {n}).")
MEGA_SOLVE_PROMPT = SOLVE_PROMPT + " The pattern has {n} creases. Pass/fail."


def _cp(segments) -> CreasePattern:
    return CreasePattern.from_segments([[*s[:4], s[4]] for s in segments], tol=1e-9)


def _load(prefix: str) -> list[dict]:
    out = []
    for f in sorted(CACHE.glob(f"{prefix}*.json")):
        d = json.loads(f.read_text())
        if d.get("result") is not None or d.get("segments"):
            out.append(d)
    return out


def _meta(**kw) -> dict:
    return {"split": "expert", **kw}


def _ref_fit(cp: CreasePattern, edges):
    rep = verify(cp, timeout=VERIFY_TIMEOUT)
    assert rep.foldable, rep.reason
    fit = best_fit(extract_trees(rep.folded), TargetTree.from_json({"edges": edges}))
    return rep, fit


def design(tid, edges, subject, out, cp, *, extra="", max_layers=None, meta=None, threshold=DESIGN_THRESHOLD,
           style_req=None, prompt=None):
    rep, fit = _ref_fit(cp, edges)
    target = TargetTree.from_json({"edges": edges})
    ref = {"family": "design", "bound": fit.scale, "reference_scale": fit.scale, "solve_efficiency": threshold,
           "packing_bound_l2": packing_bound(target, "l2", starts=60)["scale"],
           "packing_bound_linf": packing_bound(target, "linf", starts=60)["scale"],
           "verify_timeout": VERIFY_TIMEOUT, "solution": segs_json(cp)}
    if max_layers:
        ref["max_layers"] = max_layers
    if style_req:
        ref["style"] = style_req
    text = prompt or EXPERT_DESIGN_PROMPT.format(subject=subject, thr=threshold * fit.scale, extra=extra)
    t = Task(tid, "design", "hard", text.strip(), inputs={"tree": {"edges": edges}}, reference=ref,
             meta=_meta(**(meta or {}), reference_creases=cp.num_creases()))
    return _save(t, out), rep


def build_expert(out: Path, seed: int = 0, log=print) -> list[Task]:
    from ..trees import BIG_TREES, EXPERT_TREES, SEMANTIC_TREES

    rng = random.Random(seed)
    alltrees = {**SEMANTIC_TREES, **BIG_TREES, **EXPERT_TREES}
    tasks: list[Task] = []

    # ---------------------------------------------------------------- TreeMaker references
    tm = _load("tm-")
    log(f"expert: {len(tm)} certified TreeMaker references")
    for d in tm:
        name, r = d["name"], d["result"]
        cp = _cp(r["segments"])
        spec = alltrees[name]
        t, rep = design(f"expert-design-{name}", spec["edges"], spec["description"], out, cp,
                        meta={"subject": name, "leaves": _leaves(spec["edges"])})
        tasks.append(t)
        layers = layer_count(rep.folded)
        tasks.append(design(f"expert-thin-{name}", spec["edges"], spec["description"], out, cp, max_layers=layers,
                            extra=f"In addition, no point of the folded base may have more than {layers} layers "
                                  f"of paper.", meta={"subject": name, "max_layers": layers})[0])
        tree = base_tree(rep)
        tj = tree.to_json()
        rt = Task(f"expert-read-tree-{name}", "read", "hard", READ_TREE_PROMPT + " Pass/fail: exact tree.",
                  inputs={"crease_pattern": fold_input(cp)},
                  reference={"family": "read-tree", "tree": {"edges": tj["edges"]}},
                  meta=_meta(source=f"tm-{name}", num_creases=cp.num_creases(), leaves=len(tree.leaves)))
        tasks.append(_save(rt, out, cp))
        tasks.append(inverse_task(f"expert-inverse-{name}", spec["edges"], cp, rep, out))
        rt = region_task(f"expert-regions-{name}", spec["edges"], cp, rep, out, rng)
        if rt is not None:
            tasks.append(rt)

    # ---------------------------------------------------------------- minimal-grid box pleating
    for d in _load("grid-"):
        r = d["result"]
        cp = _cp(r["segments"])
        edges = [[f"n{u}", f"n{v}", float(l)] for u, v, l in d["edges"]]
        n = r["n_ref"]
        t, _ = design(f"expert-min-grid-{d['name']}", edges, "", out, cp, threshold=1.0 - 1e-6,
                      style_req={"kind": "box_pleat"}, prompt=MIN_GRID_PROMPT.format(n=n),
                      meta={"n_ref": n, "n_pack": r["n_pack"]})
        t.reference["bound"] = t.reference["reference_scale"]
        t.save(t.root)
        tasks.append(t)

    # ---------------------------------------------------------------- repair
    bp = Path(__file__).resolve().parents[1] / "gen" / "bpstudio" / "samples" / "certified"
    repair_srcs = [(f"bp-{n}", CreasePattern.from_fold(json.loads((bp / f"{n}.fold").read_text()), rebuild=True), k)
                   for n, k in (("lizard_32", 4), ("random_0_18", 4), ("random_0_00", 3), ("tight_0_00", 3))]
    mega = _load("mega-")
    for d in mega:
        repair_srcs.append((d["name"], _cp(d["segments"]), 6))
    for name, cp, k in repair_srcs:
        res = None
        for _ in range(5):
            from ..gen.defects import compose_defects

            res = compose_defects(cp, rng, n_flips=k, with_global=True, timeout=VERIFY_TIMEOUT)
            if res is not None:
                break
        if res is None:
            log(f"expert: no repair task for {name}")
            continue
        bad, info = res
        t = Task(f"expert-repair-{name}", "solve", "hard", REPAIR_PROMPT.format(k=info["n_edits"]),
                 inputs={"crease_pattern": fold_input(bad)},
                 reference={"family": "repair", "max_edits": info["n_edits"], "solution": segs_json(cp),
                            "defects": info, "verify_timeout": VERIFY_TIMEOUT},
                 meta=_meta(source=name, num_creases=cp.num_creases()))
        tasks.append(_save(t, out, bad))

    # ---------------------------------------------------------------- mega solve
    for d in mega:
        cp = _cp(d["segments"])
        t = Task(f"expert-solve-{d['name']}", "solve", "hard", MEGA_SOLVE_PROMPT.format(n=cp.num_creases()),
                 inputs={"crease_pattern": fold_input(cp, unassigned=True)},
                 reference={"family": "solve", "solution": segs_json(cp), "verify_timeout": VERIFY_TIMEOUT},
                 meta=_meta(source=d["name"], num_creases=cp.num_creases()))
        tasks.append(_save(t, out, cp, unassigned=True))
    log(f"expert: {len(tasks)} tasks")
    return tasks


def region_task(tid, edges, cp, rep, out, rng, k=6):
    from ..render import render_cp
    from .regions import REGIONS_PROMPT, region_boxes

    fit = best_fit(extract_trees(rep.folded), TargetTree.from_json({"edges": edges}))
    boxes, answer = region_boxes(cp, fit.mapping, rng, k=k)
    if len(boxes) < 3:
        return None
    t = Task(tid, "read", "hard", REGIONS_PROMPT.format(k=len(boxes), labels=", ".join(boxes)),
             inputs={"crease_pattern": fold_input(cp), "tree": {"edges": edges}, "regions": boxes},
             reference={"family": "regions", "regions": answer},
             meta=_meta(num_creases=cp.num_creases()))
    t = _save(t, out)
    render_cp(cp, t.root / "cp.png", title="Crease pattern with marked regions", boxes=boxes)
    t.images = ["cp.png"]
    t.save(t.root)
    return t


def _leaves(edges) -> int:
    deg: dict = {}
    for a, b, _ in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    return sum(1 for v in deg.values() if v == 1)


def inverse_task(tid, edges, cp, rep, out, min_iou=0.97, scale_tol=0.02) -> Task:
    target = TargetTree.from_json({"edges": edges})
    fit = best_fit(extract_trees(rep.folded), target)
    sil = rep.folded.silhouette()
    geoms = list(sil.geoms) if hasattr(sil, "geoms") else [sil]
    outline = [[[round(float(x), 6), round(float(y), 6)] for x, y in g.exterior.coords] for g in geoms]
    thr = (1 - scale_tol) * fit.scale
    t = Task(tid, "design", "hard", INVERSE_PROMPT.format(thr=thr, iou=min_iou),
             inputs={"tree": {"edges": edges}, "folded_outline": outline if len(outline) > 1 else outline[0]},
             reference={"family": "inverse", "reference_scale": fit.scale, "scale_tol": scale_tol, "min_iou": min_iou,
                        "verify_timeout": VERIFY_TIMEOUT, "solution": segs_json(cp)},
             meta=_meta(source=tid, num_creases=cp.num_creases()))
    t = _save(t, out)
    render_folded(rep.folded, t.root / "folded.png", above=rep.layers.face_above if rep.layers else None,
                  title="Folded base (x-ray)")
    t.images = ["folded.png"]
    t.save(t.root)
    return t
