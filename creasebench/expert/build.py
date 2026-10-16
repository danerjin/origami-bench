"""Expert split: tasks scored strictly pass/fail, each with a certified reference that passes its own grader.

Families (all ``meta["split"] = "expert"``):

* ``expert-design-*``      design a base for a 14-27 flap tree at a scale that matches or beats a
                           certified TreeMaker reference (universal-molecule packing);
* ``expert-thin-*``        the same, and the base may be no thicker (max paper layers) than the reference;
* ``expert-read-tree-*``   exact tree of a certified TreeMaker base, given ONLY as an image (no coordinates);
* ``expert-regions-*``     name the flap of every marked tip region of a TreeMaker base;
* ``expert-inverse-*``     reconstruct a crease pattern from its folded base alone (outline + x-ray image + tree);
* ``expert-repair-*``      repair several locally invisible M/V defects (every vertex passes Maekawa/Kawasaki;
                           only the global layer order is broken).

Calibration round 1 (docs/eval-opus-5.5-2026-10.md) dropped min-grid (only tiny trees certify) and the mirror
mega-solve (a 2x2 mirror tiling is a map fold) and hardened repair, regions, read-tree and the design bar.

References are generated offline (``python -m creasebench.expert.refgen`` / ``megagen`` / ``gridgen``) and
cached under ``tasks/expert_cache``; this builder only reads the cache.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from ..build_advanced import _save, base_tree, fold_input, segs_json
from ..cp import CreasePattern
from ..packing import packing_bound
from ..render import render_folded
from ..tasks import Task
from ..tree import extract_trees, layer_count
from ..treefit import TargetTree, best_fit
from ..verify import verify
from .refgen import CACHE

VERIFY_TIMEOUT = 900.0  # graders and oracle self-check share this budget
DESIGN_THRESHOLD = 1.0 - 1e-6  # match or beat the certified reference
# regions and repair are reported apart from the headline: in calibration agents solved them by distance
# matching and by writing their own layer-order solvers, so they measure analysis, not expert design
ANALYSIS_SPLIT = "expert-analysis"
MIN_REF_RATIO = 0.7  # design/thin need a reference this close to the L2 packing bound

EXPERT_DESIGN_PROMPT = (
    "Design a crease pattern for ONE uncut unit square whose flat-folded base realizes the target tree below "
    "(the stick figure of {subject}). This is graded pass/fail: the base must fold flat and realize the tree "
    "at a scale of at least {thr:.7f} (one unit of tree length -> {thr:.7f} of the paper side). {extra}")
REPAIR_PROMPT = (
    "The crease pattern below was flat-foldable, but {k} of its mountain/valley assignments have been changed. "
    "Every vertex still satisfies Maekawa's and Kawasaki's theorems (and every other local test): the changes "
    "only break the GLOBAL layer order, so no flat folded state exists. Repair it: return a full M/V assignment "
    "of the SAME creases that folds flat, changing at most {k} assignments relative to the given pattern. "
    "Pass/fail.")
INVERSE_PROMPT = (
    "Below is a flat-folded origami base, folded from ONE uncut unit square: its outline (`folded_outline`, "
    "coordinates in units of the paper side), an x-ray image of the folded state (all layers drawn "
    "translucently), and the stick-figure tree it realizes. Reconstruct the crease pattern. Pass/fail: your "
    "pattern must fold flat, realize the tree at a scale of at least {thr:.5f}, and its folded outline must "
    "match the given one (IoU >= {iou} after the best rotation/reflection/translation).")
READ_TREE_IMAGE_PROMPT = (
    "The image `cp.png` shows the crease pattern of a flat-foldable origami base (one uncut unit square; red solid "
    "= mountain, blue dashed = valley, axes in units of the paper side). No coordinates are given: read the "
    "pattern from the image. Report the stick-figure tree of the folded base: its flaps, branch points and the "
    "length of every segment (in units of the paper side). Pass/fail: exact tree, every segment length within "
    "0.01 of the paper side (or 2%, whichever is larger).")


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


def _bounds(edges) -> dict:
    target = TargetTree.from_json({"edges": edges})
    return {"packing_bound_l2": packing_bound(target, "l2", starts=60)["scale"],
            "packing_bound_linf": packing_bound(target, "linf", starts=60)["scale"]}


def design(tid, edges, subject, out, cp, *, extra="", max_layers=None, meta=None, threshold=DESIGN_THRESHOLD,
           style_req=None, prompt=None, ref_rep=None, bounds=None):
    rep, fit = ref_rep or _ref_fit(cp, edges)
    ref = {"family": "design", "bound": fit.scale, "reference_scale": fit.scale, "solve_efficiency": threshold,
           **(bounds or _bounds(edges)), "verify_timeout": VERIFY_TIMEOUT, "solution": segs_json(cp)}
    if max_layers:
        ref["max_layers"] = max_layers
    if style_req:
        ref["style"] = style_req
    text = prompt or EXPERT_DESIGN_PROMPT.format(subject=subject, thr=threshold * fit.scale, extra=extra)
    t = Task(tid, "design", "hard", text.strip(), inputs={"tree": {"edges": edges}}, reference=ref,
             meta=_meta(**(meta or {}), reference_creases=cp.num_creases()))
    return _save(t, out), rep


def build_expert(out: Path, seed: int = 0, log=print, resume: bool = False) -> list[Task]:
    from ..trees import BIG_TREES, EXPERT_TREES, SEMANTIC_TREES

    rng = random.Random(seed)
    alltrees = {**SEMANTIC_TREES, **BIG_TREES, **EXPERT_TREES}
    tasks: list[Task] = []

    # ---------------------------------------------------------------- TreeMaker references
    tm = _load("tm-")
    log(f"expert: {len(tm)} certified TreeMaker references")
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=4) as ex:
        for d, got in zip(tm, ex.map(_tm_tasks, [(d, str(out), seed, resume) for d in tm])):
            tasks += got
            log(f"expert: {d['name']} -> {len(got)} tasks")

    # ---------------------------------------------------------------- repair
    bp = Path(__file__).resolve().parents[1] / "gen" / "bpstudio" / "samples" / "certified"
    repair_srcs = [(f"bp-{n}", CreasePattern.from_fold(json.loads((bp / f"{n}.fold").read_text()), rebuild=True), k)
                   for n, k in (("lizard_32", 3), ("random_0_18", 3), ("random_0_00", 3), ("tight_0_00", 3))]
    mega = _load("mega-")
    for d in mega:
        repair_srcs.append((d["name"], _cp(d["segments"]), 4))
    for name, cp, k in repair_srcs:
        res = None
        for _ in range(5):
            from ..gen.defects import compose_global

            res = compose_global(cp, rng, n_conflicts=k, timeout=VERIFY_TIMEOUT)
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
                 meta=_meta(split=ANALYSIS_SPLIT, source=name, num_creases=cp.num_creases()))
        tasks.append(_save(t, out, bad))

    log(f"expert: {len(tasks)} tasks")
    return tasks


def _tm_tasks(args) -> list[Task]:
    """All tasks built on one certified TreeMaker reference (verified once)."""
    from ..trees import BIG_TREES, EXPERT_TREES, SEMANTIC_TREES

    d, out, seed, resume = args
    out = Path(out)
    name, r = d["name"], d["result"]
    rng = random.Random(f"{seed}-{name}")
    spec = {**SEMANTIC_TREES, **BIG_TREES, **EXPERT_TREES}[name]
    if resume and all(any(Path(out).glob(f"*/{f}-{name}")) for f in
                      ("expert-design", "expert-thin", "expert-read-tree", "expert-inverse")):
        from ..tasks import load_task

        return [load_task(p / "task.json") for p in sorted(Path(out).glob(f"*/expert-*-{name}"))]
    rep = fit = cp = None
    for tol in (1e-9, 1e-7, 1e-6):  # cached coordinates are rounded; re-planarize tolerantly
        cp = CreasePattern.from_segments([[*s[:4], s[4]] for s in r["segments"]], tol=tol)
        try:
            rep, fit = _ref_fit(cp, spec["edges"])
            break
        except AssertionError:
            rep = None
    if rep is None:
        print(f"expert: reference for {name} does not re-verify from the cache; skipped", flush=True)
        return []
    bounds = _bounds(spec["edges"])
    tasks = []
    strong = fit.scale >= MIN_REF_RATIO * bounds["packing_bound_l2"]
    if not strong:
        print(f"expert: {name} reference reaches only {fit.scale / bounds['packing_bound_l2']:.2f} of the L2 "
              f"packing bound; no design/thin tasks (the bar would be beatable)", flush=True)
    t, _ = design(f"expert-design-{name}", spec["edges"], spec["description"], out, cp, ref_rep=(rep, fit),
                  bounds=bounds, meta={"subject": name, "leaves": _leaves(spec["edges"])}) if strong else (None, None)
    if t is not None:
        tasks.append(t)
    layers = layer_count(rep.folded)
    if strong:
        tasks.append(design(f"expert-thin-{name}", spec["edges"], spec["description"], out, cp, max_layers=layers,
                        ref_rep=(rep, fit), bounds=bounds,
                        extra=f"In addition, no point of the folded base may have more than {layers} layers "
                              f"of paper.", meta={"subject": name, "max_layers": layers})[0])
    tree = base_tree(rep)
    tj = tree.to_json()
    rt = Task(f"expert-read-tree-{name}", "read", "hard", READ_TREE_IMAGE_PROMPT, inputs={},
              reference={"family": "read-tree", "tree": {"edges": tj["edges"]}},
              meta=_meta(subject=name, source=f"tm-{name}", num_creases=cp.num_creases(), leaves=len(tree.leaves),
                         image_only=True))
    rt = _save(rt, out)
    from ..render import render_cp

    render_cp(cp, rt.root / "cp.png", title="Crease pattern", size=24, lw_scale=1.5)
    rt.images = ["cp.png"]
    rt.save(rt.root)
    tasks.append(rt)
    tasks.append(inverse_task(f"expert-inverse-{name}", spec["edges"], cp, rep, out))
    rg = region_task(f"expert-regions-{name}", spec["edges"], cp, rep, out, rng)
    if rg is not None:
        tasks.append(rg)
    return tasks


def region_task(tid, edges, cp, rep, out, rng, k=None):
    from ..render import render_cp
    from .regions import REGIONS_PROMPT, region_boxes

    trees = extract_trees(rep.folded)
    fit = best_fit(trees, TargetTree.from_json({"edges": edges}))
    # every flap tip of the base along any candidate axis, named or not, so no box holds a second tip
    # however the base is read
    tips = {n for t in trees for n in t.graph if t.graph.degree(n) == 1}
    boxes, answer = region_boxes(cp, fit.mapping, rng, k=k, others=tips)
    if len(boxes) < (k or len(fit.mapping)):  # every tip must be marked
        return None
    t = Task(tid, "read", "hard", REGIONS_PROMPT.format(k=len(boxes), labels=", ".join(boxes)),
             inputs={"crease_pattern": fold_input(cp), "tree": {"edges": edges}, "regions": boxes},
             reference={"family": "regions", "regions": answer},
             meta=_meta(split=ANALYSIS_SPLIT, num_creases=cp.num_creases()))
    t = _save(t, out)
    render_cp(cp, t.root / "cp.png", title="Crease pattern with marked regions", boxes=boxes, size=12)
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
