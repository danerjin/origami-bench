"""Two-tone paper: which side of the paper is visible where.

The paper's top side (as the crease pattern is drawn) is called "front", the other
side "back". In the folded state a face that is not flipped shows its front upward.
Seen from above, a point shows the top-most face covering it; seen from below, the
bottom-most face, whose *other* side faces the viewer.

Visibility depends on the layer order, which is often not unique; a requirement is
satisfied if *some* valid layer order meets it (the folder may choose).
"""

from __future__ import annotations

import numpy as np
from shapely.geometry import Point

from .layers import build_problem, solve_layers
from .simulate import FoldedState


def covering_faces(folded: FoldedState, pt, polys=None) -> list[int]:
    polys = polys or [p.buffer(-1e-7) for p in folded.face_polygons()]
    P = Point(pt)
    return [i for i, p in enumerate(polys) if p.contains(P)]


def visible_side(folded: FoldedState, above: list[tuple[int, int]], pt, from_above: bool = True,
                 polys=None) -> str | None:
    faces = covering_faces(folded, pt, polys)
    if not faces:
        return None
    rel = set(map(tuple, above))
    fs = set(faces)
    if from_above:
        tops = [f for f in faces if not any((g, f) in rel for g in fs if g != f)]
    else:
        tops = [f for f in faces if not any((f, g) in rel for g in fs if g != f)]
    if not tops:
        return None
    f = tops[0]
    up = not folded.face_flipped(f)  # front faces upward
    return ("front" if up else "back") if from_above else ("back" if up else "front")


def tip_sample_point(folded: FoldedState, tree, leaf: int, polys=None):
    """A point just inside the flap at tree leaf ``leaf`` (folded coordinates)."""
    import math

    g = tree.graph
    (parent,) = list(g.neighbors(leaf))
    ang = math.radians(tree.axis_deg)
    axis = np.array([math.cos(ang), math.sin(ang)])
    tip = np.array(g.nodes[leaf]["folded"])
    direction = np.sign(g.nodes[parent]["g"] - g.nodes[leaf]["g"]) or 1.0
    step = min(0.02, 0.25 * g.edges[leaf, parent]["length"])
    polys = polys or [p.buffer(-1e-7) for p in folded.face_polygons()]
    perp = np.array([-axis[1], axis[0]])
    for k in (1.0, 0.5, 0.25):
        base = tip + direction * axis * step * k
        for off in (0.0, 1e-3, -1e-3, 3e-3, -3e-3):
            p = base + perp * off
            if covering_faces(folded, p, polys):
                return p
    return None


def satisfiable(folded: FoldedState, requirements: list[tuple[np.ndarray, str, str]],
                known_order: list[tuple[int, int]] | None = None, budget: int = 50_000) -> bool:
    """Is there one valid layer order meeting every (point, 'above'|'below', 'front'|'back')?"""
    polys = [p.buffer(-1e-7) for p in folded.face_polygons()]
    if known_order is not None and all(
            visible_side(folded, known_order, pt, view == "above", polys) == side
            for pt, view, side in requirements):
        return True
    if len(folded.cp.faces) > 250:
        return False  # too large for the pure-Python search; only the known order was tried
    prob = build_problem(folded)
    sat = prob.sat
    extra = []
    for pt, view, side in requirements:
        faces = covering_faces(folded, pt, polys)
        good = []
        for f in faces:
            up = not folded.face_flipped(f)
            shows = ("front" if up else "back") if view == "above" else ("back" if up else "front")
            if shows != side:
                continue
            y = sat.new_var()  # y -> f is the outermost face at pt
            for g in faces:
                if g == f:
                    continue
                lit = prob.lit_above(f, g) if view == "above" else prob.lit_above(g, f)
                if lit is None:
                    continue
                extra.append([-y, lit])
            good.append(y)
        if not good:
            return False
        extra.append(good)
    saved = list(sat.clauses)
    for c in extra:
        sat.add_clause(c)
    ok = solve_layers(folded, budget=budget, problem=prob).status == "found"
    sat.clauses = saved
    return ok
