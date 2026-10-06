"""Hand-authored reference crease patterns of traditional folds and bases.

Each entry lists only the creases that are *folded* in the final state (pure
precreases are omitted, since a flat-folded crease pattern folds every crease).
Ground-truth geometry is always computed by the simulator, never typed in.
"""

from __future__ import annotations

import math

import numpy as np
from shapely.geometry import Polygon

from .cp import CreasePattern
from .generate import SimpleFolder

T22 = math.tan(math.radians(22.5))  # 0.41421...


def _cp(segs) -> CreasePattern:
    return CreasePattern.from_segments(segs, tol=1e-9)


def book():
    return _cp([((0.5, 0), (0.5, 1), "V")])


def diagonal():
    return _cp([((0, 0), (1, 1), "V")])


def cupboard():
    return _cp([((0.25, 0), (0.25, 1), "V"), ((0.75, 0), (0.75, 1), "V")])


def accordion4():
    return _cp([((0.25, 0), (0.25, 1), "V"), ((0.5, 0), (0.5, 1), "M"), ((0.75, 0), (0.75, 1), "V")])


def blintz():
    m = [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)]
    return _cp([(m[i], m[(i + 1) % 4], "V") for i in range(4)])


def kite_base():
    return _cp([((0, 0), (1, T22), "V"), ((0, 0), (T22, 1), "V")])


def waterbomb_base():
    return _cp([((0, 0), (1, 1), "V"), ((1, 0), (0, 1), "V"), ((0, 0.5), (1, 0.5), "M")])


def preliminary_base():
    return _cp([((0, 0.5), (1, 0.5), "M"), ((0.5, 0), (0.5, 1), "M"), ((0, 0), (1, 1), "V")])


def fish_base():
    a = (1 - math.sqrt(0.5), math.sqrt(0.5))  # (0.2929, 0.7071) on the anti-diagonal
    b = (math.sqrt(0.5), 1 - math.sqrt(0.5))
    return _cp([((0, 0), b, "V"), ((0, 0), a, "V"), ((1, 1), a, "M"), ((1, 1), b, "M"),
                ((1, 0), b, "V"), (b, a, "V"), (a, (0, 1), "V")])


def _simple(seq) -> CreasePattern:
    sf = SimpleFolder()
    for p, q, kind, side in seq:
        assert sf.fold(p, q, kind, side), (p, q)
    return sf.to_generated([]).cp


def map_fold():
    """Book fold, then fold in half again: a 1/4 square, four layers."""
    return _simple([((0.5, 0), (0.5, 1), "V", -1), ((0, 0.5), (1, 0.5), "V", -1)])


def double_blintz():
    m = [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)]
    seq = [(m[i], m[(i + 1) % 4], "V", -1) for i in range(4)]
    # second round: fold the new corners (edge midpoints) to the centre
    q = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]
    seq += [(q[i], q[(i + 1) % 4], "V", -1) for i in [3, 0, 1, 2]]
    return _simple(seq)


REFERENCE = {
    "book": (book, "Book fold: the square folded in half edge to edge."),
    "diagonal": (diagonal, "Diagonal fold: the square folded in half corner to corner."),
    "cupboard": (cupboard, "Cupboard fold: two opposite edges folded to the centre line."),
    "accordion4": (accordion4, "Accordion pleat into four equal strips."),
    "blintz": (blintz, "Blintz fold: all four corners folded to the centre."),
    "kite_base": (kite_base, "Kite base: two adjacent edges folded to a diagonal."),
    "waterbomb_base": (waterbomb_base, "Waterbomb base (triangle base)."),
    "preliminary_base": (preliminary_base, "Preliminary base (square base)."),
    "fish_base": (fish_base, "Fish base: kite folds from two opposite corners with rabbit ears."),
    "map_fold": (map_fold, "Square folded in half twice."),
    "double_blintz": (double_blintz, "Blintz fold applied twice."),
}


def fold_to_convex(target, max_rounds: int = 40) -> CreasePattern:
    """Fold the square into a convex polygon lying inside it, by repeatedly folding
    whatever sticks out across each edge of the target back inside (simple folds).

    Used to build reference solutions for shape-design tasks.
    """
    tgt = Polygon(target)
    if not tgt.exterior.is_ccw:
        tgt = Polygon(list(tgt.exterior.coords)[::-1])
    pts = [np.array(c) for c in tgt.exterior.coords[:-1]]
    sf = SimpleFolder()
    for _ in range(max_rounds):
        changed = False
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            d = (q - p) / np.linalg.norm(q - p)
            n = np.array([d[1], -d[0]])  # points outside the CCW polygon
            outside_half = Polygon([p - 10 * d, q + 10 * d, q + 10 * d + 10 * n, p - 10 * d + 10 * n])
            if sf.silhouette().intersection(outside_half).area > 1e-9 and sf.fold(p, q, "V", -1):
                changed = True
        if not changed:
            break
    return sf.to_generated([]).cp
