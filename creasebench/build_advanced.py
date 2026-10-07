"""Build the advanced tier: expert crease-pattern reading and tree-theory design.

Every crease pattern shipped here is *generated* (22.5-degree modules and tilings,
grafts, Box Pleating Studio layouts, TreeMaker bases) and certified flat-foldable;
ground truth (trees, techniques, colours) is computed from the folded state.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from . import style
from .color import satisfiable, tip_sample_point
from .cp import CreasePattern
from .packing import packing_bound
from .render import render_cp
from .tasks import Task
from .tree import extract_trees
from .treefit import TargetTree, best_fit
from .trees import SEMANTIC_TREES
from .verify import verify

READ_TREE_PROMPT = ("Below is the crease pattern of a flat-foldable origami base (one uncut square; also shown "
                    "as an image). Fold it in your head (or with code) and report the stick-figure tree of the "
                    "folded base: its flaps, branch points and the length of every segment.")
READ_TECH_PROMPT = ("Below is an origami crease pattern. Identify the design system it uses: is it box-pleated "
                    "(and on which grid), is it a 22.5-degree design, and does it contain Pythagorean stretches "
                    "(which triples)?")
READ_COLOR_PROMPT = ("The crease pattern below is folded from two-tone paper. The side facing you in the drawing is "
                     "'front', the other side 'back'. For each listed flap tip (given by its position on the "
                     "unfolded paper), say which side of the paper is visible at that tip in the folded base, "
                     "seen from above and from below (the folded model is viewed with the paper of the largest "
                     "face, near its crease-pattern position, still showing its front side upward). Where layer "
                     "order is a choice, the listed tips are ones whose colour does not depend on it.")
SOLVE_PROMPT = ("Below is the geometry of a flat-foldable crease pattern with every crease unassigned ('U'). "
                "Assign mountain or valley to every crease so that the whole pattern folds flat (Maekawa and "
                "Kawasaki at every vertex, and a valid global layer order).")
PACK_PROMPT = ("Target tree for an origami base (the stick figure of the model). Choose where each flap tip "
               "lies on the unit-square sheet so that the scale m is as large as possible, where m is the "
               "largest value with dist(u_i, u_j) >= m * d_tree(i, j) for every pair of leaves. {norm}")
DESIGN_PROMPT = ("Design a crease pattern for ONE uncut unit square whose flat-folded base realizes the target "
                 "tree below at the largest scale you can (the stick figure of {subject}). {extra}")


def fold_input(cp: CreasePattern, unassigned: bool = False) -> dict:
    d = cp.to_fold(precision=10)
    out = {k: d[k] for k in ("vertices_coords", "edges_vertices", "edges_assignment", "faces_vertices")}
    out["vertices_coords"] = [[round(x, 8), round(y, 8)] for x, y in out["vertices_coords"]]
    if unassigned:
        out["edges_assignment"] = ["B" if a == "B" else "U" for a in out["edges_assignment"]]
    return out


def segs_json(cp: CreasePattern) -> list:
    return [[round(p[0], 10), round(p[1], 10), round(q[0], 10), round(q[1], 10), a] for p, q, a in cp.segments()]


def _leaf_edges(t) -> list[float]:
    g = t.graph
    return [l for u, v, l in g.edges(data="length") if g.degree(u) == 1 or g.degree(v) == 1]


def base_tree(rep, stub_frac: float = 0.2):
    """The base's tree along its own axis.

    Projecting onto a tilted axis shortens every flap and adds many short stubs, which can
    inflate the *total* length. So the axis is chosen to maximize the total length of real
    flaps: leaf edges at least ``stub_frac`` times the longest flap seen on any axis. Ties go
    to the tree with fewer leaves."""
    trees = extract_trees(rep.folded)
    longest = max((max(_leaf_edges(t), default=0.0) for t in trees), default=0.0)
    return max(trees, key=lambda t: (round(sum(x for x in _leaf_edges(t) if x >= stub_frac * longest), 6),
                                     -len(t.leaves)))


def _save(task: Task, out: Path, cp: CreasePattern | None = None, unassigned=False) -> Task:
    d = out / task.track / task.id
    task.meta["tier"] = "advanced"
    task.save(d)
    if cp is not None:
        show = cp
        if unassigned:
            show = CreasePattern(cp.vertices, cp.edges, ["B" if a == "B" else "U" for a in cp.assignments],
                                 cp.faces)
        render_cp(show, d / "cp.png", title="Crease pattern" if not unassigned else "Unassigned crease pattern")
        task.images = ["cp.png"]
        task.save(d)
    return task


# ----------------------------------------------------------------------------- sources
def sources(log=print) -> list[dict]:
    """Certified generated crease patterns with provenance."""
    from .gen import bases22 as B
    from .gen import graft as G

    out = []

    def add(name, cp, kind, **meta):
        if cp is None:
            log(f"  source {name}: not certified, skipped")
            return
        out.append({"name": name, "cp": cp, "kind": kind, "meta": meta})
        log(f"  source {name}: {cp.num_creases()} creases")

    bird = B.bird_base()
    add("bird", bird, "22.5", generator="bases22.bird")
    add("bird-2x2", B.certify_tiling(B.mirror_cells("bird", 2)), "22.5", generator="bases22.mirror_tiling")
    add("dblintz-2x2", B.certify_tiling(B.mirror_cells("double_blintz", 2)), "bp",
        generator="bases22.mirror_tiling")
    rng = np.random.default_rng(7)
    found = 0
    for _ in range(200):
        if found >= 3:
            break
        cells = B.random_cells(2, rng)
        segs = B.tile_segments(cells)
        from .foldability import check_local

        cp0 = CreasePattern.from_segments(segs, tol=1e-9)
        if any(v.rule in ("odd_degree", "kawasaki") for v in check_local(cp0).violations):
            continue
        cp = B.certify_tiling(cells, timeout=60)
        if cp is not None and cp.num_creases() >= 60:
            found += 1
            add(f"tiling-{found}", cp, "22.5", generator="bases22.random_tiling", cells=cells)
    add("bird-border", G.border_graft(bird, 0.1, fold_old_border=True), "22.5",
        generator="graft.border_graft", base="bird", w=0.1)
    add("waterbomb-border", G.border_graft(__import__("creasebench.reference", fromlist=["x"]).waterbomb_base(),
                                           0.125, fold_old_border=True), "bp",
        generator="graft.border_graft", base="waterbomb", w=0.125)
    # Box Pleating Studio and TreeMaker outputs, when their drivers are installed
    try:
        from .gen import bpstudio

        for item in getattr(bpstudio, "reference_designs", lambda: [])():
            add(item["name"], item["cp"], "bp-studio", **item.get("meta", {}))
    except Exception as e:  # noqa: BLE001
        log(f"  bpstudio unavailable: {e}")
    try:
        from .gen import treemaker

        if treemaker.available():
            for item in treemaker.reference_designs():
                add(item["name"], item["cp"], "treemaker", **item.get("meta", {}))
    except Exception as e:  # noqa: BLE001
        log(f"  treemaker unavailable: {e}")
    return out


# ----------------------------------------------------------------------------- families
def read_tree_task(src, out: Path) -> Task:
    rep = verify(src["cp"])
    tree = base_tree(rep)
    tj = tree.to_json()
    t = Task(f"adv-read-tree-{src['name']}", "read", "hard" if src["cp"].num_creases() > 100 else "medium",
             READ_TREE_PROMPT, inputs={"crease_pattern": fold_input(src["cp"])},
             reference={"family": "read-tree", "tree": {"edges": tj["edges"]}},
             meta={"source": src["name"], **src["meta"], "num_creases": src["cp"].num_creases(),
                   "leaves": len(tree.leaves)})
    return _save(t, out, src["cp"])


def read_tech_task(src, out: Path) -> Task:
    rep = style.analyze(src["cp"])
    tech = {"box_pleat": rep.box_pleat, "grid": rep.grid, "angles_22_5": rep.angles_22_5,
            "pythagorean_stretch": rep.pythagorean_stretch, "stretch_triples": [list(t) for t in rep.stretch_triples]}
    t = Task(f"adv-read-tech-{src['name']}", "read", "medium", READ_TECH_PROMPT,
             inputs={"crease_pattern": fold_input(src["cp"])}, reference={"family": "read-tech", "tech": tech},
             meta={"source": src["name"], **src["meta"]})
    return _save(t, out, src["cp"])


def read_color_task(src, out: Path) -> Task | None:
    if len(src["cp"].faces) > 250:
        return None  # uniqueness of colours can only be proven for smaller patterns
    rep = verify(src["cp"])
    tree = base_tree(rep)
    polys = [p.buffer(-1e-7) for p in rep.folded.face_polygons()]
    colors, tips = {}, {}
    for k, leaf in enumerate(tree.leaves):
        pt = tip_sample_point(rep.folded, tree, leaf, polys)
        if pt is None:
            continue
        entry = {}
        for view in ("above", "below"):
            can = {side: satisfiable(rep.folded, [(pt, view, side)], rep.layers.face_above)
                   for side in ("front", "back")}
            if can["front"] != can["back"]:
                entry[view] = "front" if can["front"] else "back"
        if len(entry) == 2:
            tid = f"tip{k}"
            colors[tid] = entry
            tips[tid] = [round(float(c), 6) for c in src["cp"].vertices[leaf]]
    if len(colors) < 2:
        return None
    t = Task(f"adv-read-color-{src['name']}", "read", "hard", READ_COLOR_PROMPT,
             inputs={"crease_pattern": fold_input(src["cp"]), "flap_tips": tips},
             reference={"family": "read-color", "colors": colors}, meta={"source": src["name"], **src["meta"]})
    return _save(t, out, src["cp"])


def solve_task(src, out: Path) -> Task:
    t = Task(f"adv-solve-{src['name']}", "solve", "hard" if src["cp"].num_creases() > 100 else "medium",
             SOLVE_PROMPT, inputs={"crease_pattern": fold_input(src["cp"], unassigned=True)},
             reference={"family": "solve", "solution": segs_json(src["cp"])},
             meta={"source": src["name"], **src["meta"], "num_creases": src["cp"].num_creases()})
    return _save(t, out, src["cp"], unassigned=True)


def analytic_adv_task(src, out: Path) -> Task:
    from .build import analytic_task

    t = analytic_task(f"adv-af-{src['name']}", src["cp"], out, {"source": src["name"], **src["meta"]}, "hard")
    t.meta["tier"] = "advanced"
    t.save(t.root)
    return t


def bug_task(src, out: Path, rng: random.Random, kind: str) -> Task | None:
    from .build import analytic_task
    from .gen import defects

    if kind == "flip":
        cp, info = defects.flip_one(src["cp"], rng)
    elif kind == "nudge":
        cp, info = defects.nudge_vertex(src["cp"], rng)
    else:
        res = defects.global_conflict(src["cp"], rng)
        if res is None:
            return None
        cp, info = res
    t = analytic_task(f"adv-bug-{kind}-{src['name']}", cp, out, {"source": src["name"], "defect": info}, "hard")
    t.meta["tier"] = "advanced"
    t.save(t.root)
    return t


def pack_task(name: str, spec: dict, norm: str, out: Path) -> Task:
    target = TargetTree.from_json(spec)
    b = packing_bound(target, norm, starts=60)
    extra = ("Distances are Euclidean (circle packing)." if norm == "l2" else
             "This is BOX PLEATING: distances use the L-infinity norm max(|dx|, |dy|) (square packing).")
    t = Task(f"adv-pack-{norm}-{name}", "pack", "medium", PACK_PROMPT.format(norm=extra),
             inputs={"tree": {"edges": spec["edges"]}},
             reference={"family": "pack", "norm": norm, "bound": b["scale"], "solution": b["positions"],
                        "solve_threshold": 0.98},
             meta={"subject": name})
    return _save(t, out)


def design_task(tid: str, target_edges, subject: str, out: Path, *, reference_cp: CreasePattern | None = None,
                style_req: dict | None = None, colors: dict | None = None, graft: dict | None = None,
                base_cp: CreasePattern | None = None, extra: str = "", difficulty: str = "hard",
                meta: dict | None = None) -> Task:
    target = TargetTree.from_json({"edges": target_edges})
    bound = packing_bound(target, "l2", starts=60)["scale"]
    ref_scale = None
    if reference_cp is not None:
        rep = verify(reference_cp)
        ref_scale = best_fit(extract_trees(rep.folded), target).scale
        bound = max(bound, ref_scale)
    reference = {"family": "design", "bound": bound, "packing_bound_l2": bound if ref_scale is None else None,
                 "reference_scale": ref_scale, "solve_efficiency": 0.6}
    if reference_cp is not None:
        reference["solution"] = segs_json(reference_cp)
    inputs = {"tree": {"edges": target_edges}}
    if style_req:
        reference["style"] = style_req
    if colors:
        reference["colors"] = colors
    if graft:
        reference["graft"] = graft
        inputs["base_crease_pattern"] = fold_input(base_cp)
    t = Task(tid, "design", difficulty, DESIGN_PROMPT.format(subject=subject, extra=extra).strip(), inputs=inputs,
             reference=reference, meta=meta or {})
    return _save(t, out, base_cp if graft else None)


def simplified_tree(cp: CreasePattern, min_frac: float = 0.15, max_leaves: int = 12):
    """Tree of a certified base with short leaves pruned (used as a design target).

    Leaves shorter than ``min_frac`` of the longest edge are removed, then the shortest
    remaining leaves until at most ``max_leaves`` are left. The base still realizes the
    pruned tree (it only drops flaps), so it stays a valid reference design."""
    import networkx as nx

    rep = verify(cp)
    tree = base_tree(rep)
    g = tree.graph.copy()
    longest = max(l for *_, l in g.edges(data="length"))

    def leaves():
        return [n for n in g if g.degree(n) == 1]

    def leaf_len(n):
        (p,) = list(g.neighbors(n))
        return g.edges[n, p]["length"]

    def contract():
        for n in [n for n in g if g.degree(n) == 2]:
            a, b = list(g.neighbors(n))
            if not g.has_edge(a, b):
                g.add_edge(a, b, length=g.edges[n, a]["length"] + g.edges[n, b]["length"])
                g.remove_node(n)

    while True:
        lv = leaves()
        short = [n for n in lv if leaf_len(n) < min_frac * longest]
        if len(lv) > max_leaves and not short:
            short = [min(lv, key=leaf_len)]
        if not short or len(lv) <= 2:
            break
        g.remove_node(min(short, key=leaf_len))
        contract()
    names = {n: f"n{i}" for i, n in enumerate(sorted(g))}
    return [[names[u], names[v], round(l / longest * 4, 3)] for u, v, l in g.edges(data="length")], tree


# ----------------------------------------------------------------------------- driver
def build_advanced(out: Path, seed: int = 0, log=print) -> list[Task]:
    rng = random.Random(seed)
    tasks: list[Task] = []
    log("advanced: collecting certified sources")
    srcs = sources(log)
    by = {s["name"]: s for s in srcs}
    log("advanced: reading tasks")
    for s in srcs:
        tasks.append(read_tree_task(s, out))
        tasks.append(solve_task(s, out))
    for s in srcs:
        if s["kind"] in ("bp", "bp-studio", "treemaker") or s["name"] in ("bird-2x2", "bird-border"):
            tasks.append(read_tech_task(s, out))
    for name in ("bird-border", "waterbomb-border", "bird"):
        if name in by:
            t = read_color_task(by[name], out)
            if t is not None:
                tasks.append(t)
    for name in ("bird", "waterbomb-border"):
        if name in by:
            tasks.append(analytic_adv_task(by[name], out))
    for s, kind in [(by.get("bird-2x2"), "flip"), (by.get("tiling-1"), "nudge"), (by.get("bird-border"), "flip"),
                    (by.get("tiling-2"), "global"), (by.get("bird-2x2"), "global"),
                    (by.get("bp-lizard-32"), "flip"), (by.get("bp-stretch-gops-14"), "nudge"),
                    (by.get("bp-three-flap-16"), "global")]:
        if s is not None:
            t = bug_task(s, out, rng, kind)
            if t is not None:
                tasks.append(t)
    log("advanced: packing tasks")
    for name in ("lizard", "beetle", "scorpion", "deer"):
        tasks.append(pack_task(name, SEMANTIC_TREES[name], "l2", out))
    for name in ("lizard", "spider"):
        tasks.append(pack_task(name, SEMANTIC_TREES[name], "linf", out))
    log("advanced: design tasks")
    for name, spec in SEMANTIC_TREES.items():
        ref = by.get(f"tm-{name}")
        tasks.append(design_task(f"adv-design-{name}", spec["edges"], spec["description"], out,
                                 reference_cp=ref["cp"] if ref else None,
                                 meta={"subject": name, "reference": ref["meta"] if ref else None}))
    for name in ("bird-2x2", "tiling-1", "bird-border"):
        if name in by:
            edges, _ = simplified_tree(by[name]["cp"])
            tasks.append(design_task(f"adv-design-from-{name}", edges, "a generated multi-flap base", out,
                                     reference_cp=by[name]["cp"], meta={"source": name}))
    # style-constrained
    star4 = [["c", "a", 1], ["c", "b", 1], ["c", "d", 1], ["c", "e", 1]]
    tasks.append(design_task("adv-style-22_5-star4", star4, "a four-flap star", out, reference_cp=by["bird"]["cp"],
                             style_req={"kind": "angles_22_5"},
                             extra="Every crease must lie at a multiple of 22.5 degrees.", meta={"style": "22.5"}))
    tasks.append(design_task("adv-style-bp-lizard", SEMANTIC_TREES["lizard"]["edges"],
                             SEMANTIC_TREES["lizard"]["description"], out,
                             style_req={"kind": "box_pleat", "max_grid": 32},
                             extra="The crease pattern must be box-pleated on a grid of at most 32 x 32.",
                             meta={"style": "box_pleat"}))
    for name, grid in (("bp-lizard-32", 32), ("bp-tight-0-00", 24), ("bp-three-flap-16", 16)):
        if name in by:
            src = by[name]
            edges = [[f"n{u}", f"n{v}", float(l)] for u, v, l in src["meta"]["tree"]]
            tasks.append(design_task(
                f"adv-style-{name}", edges, "a box-pleated base (tree lengths in grid units)", out,
                reference_cp=src["cp"], style_req={"kind": "box_pleat", "max_grid": grid},
                extra=f"The crease pattern must be box-pleated on a grid of at most {grid} x {grid}.",
                meta={"style": "box_pleat", "source": name}))
    tasks.append(design_task("adv-style-stretch-beetle", SEMANTIC_TREES["beetle"]["edges"],
                             SEMANTIC_TREES["beetle"]["description"], out,
                             style_req={"kind": "pythagorean_stretch", "max_grid": 48},
                             extra="Use box pleating with at least one Pythagorean stretch (grid at most 48).",
                             meta={"style": "stretch"}))
    # grafting
    if "bird-border" in by:
        from .gen.graft import Graft

        edges, _ = simplified_tree(by["bird-border"]["cp"])
        w = 0.1
        s = 1 / (1 + 2 * w)
        pieces = [{"region": [[0, 0], [1, 0], [1, 1], [0, 1]], "scale": s, "offset": [w * s, w * s]}]
        tasks.append(design_task(
            "adv-graft-bird-border", edges, "a bird base enlarged by border grafting", out,
            reference_cp=by["bird-border"]["cp"], base_cp=by["bird"]["cp"],
            graft={"pieces": pieces, "min_preserved": 0.9, "w": w},
            extra=(f"Start from the given bird-base crease pattern: shrink it by 1/(1+2*{w}) and graft a border "
                   f"strip of width {w} (before shrinking) all around it, so that at least 90% of the original "
                   "creases are kept (same positions after the shrink, assignments may all be swapped). The "
                   "border may be folded."),
            meta={"technique": "border graft"}))
    # colour change
    if "bird-border" in by:
        src = by["bird-border"]
        edges, tree = simplified_tree(src["cp"])
        rep = verify(src["cp"])
        target = TargetTree.from_json({"edges": edges})
        fit = best_fit(extract_trees(rep.folded), target)
        polys = [p.buffer(-1e-7) for p in rep.folded.face_polygons()]
        trees = {t.axis_deg: t for t in extract_trees(rep.folded)}
        ftree = trees.get(fit.axis_deg)
        colors = {}
        for leaf_name, base_leaf in fit.mapping.items():
            pt = tip_sample_point(rep.folded, ftree, base_leaf, polys)
            if pt is None:
                continue
            for side in ("back",):
                if satisfiable(rep.folded, [(pt, "above", side)], rep.layers.face_above) and not satisfiable(
                        rep.folded, [(pt, "above", "front")], rep.layers.face_above):
                    colors[leaf_name] = {"above": side}
        if colors:
            tasks.append(design_task("adv-color-bird-border", edges, "a multi-flap base on two-tone paper", out,
                                     reference_cp=src["cp"], colors=colors,
                                     extra=("Colour requirement: at the tip of each listed flap the BACK side of "
                                            "the paper must be visible from above: " + json.dumps(colors)),
                                     meta={"technique": "color change"}))
            tasks.append(design_task("adv-composite-bird-border", edges, "a multi-flap base on two-tone paper", out,
                                     reference_cp=src["cp"], colors=colors, style_req={"kind": "angles_22_5"},
                                     extra=("Use only creases at multiples of 22.5 degrees, and at the tip of each "
                                            "listed flap the BACK side must be visible from above: "
                                            + json.dumps(colors)),
                                     meta={"technique": "22.5 + color change"}))
    return tasks
