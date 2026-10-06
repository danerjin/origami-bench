"""22.5-degree bases and modules, plus tilings that compose them.

Geometry is written down exactly (coordinates in Z[sqrt2][1/2]); mountain/valley
assignments are found by the flat-foldability solver from unassigned creases, so
every module returned here is certified flat-foldable.
"""

from __future__ import annotations

import math

import numpy as np

from ..cp import CreasePattern
from ..verify import complete_assignment

T = math.tan(math.radians(22.5))  # sqrt2 - 1


def _u(segs):
    return [(tuple(map(float, p)), tuple(map(float, q)), "U") for p, q in segs]


def bird_segments() -> list:
    """Folded creases of the bird base (unit square): diagonals, midlines, the four
    hinge lines of the petal folds and the eight 22.5-degree edge-to-diagonal creases."""
    t = T / 2
    c = (0.5, 0.5)
    corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
    sq = [(0.5, t), (1 - t, 0.5), (0.5, 1 - t), (t, 0.5)]
    mids = [(0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)]
    segs = [(corners[0], corners[2]), (corners[1], corners[3])]
    segs += [(mids[i], c) for i in range(4)]
    segs += [(sq[i], sq[(i + 1) % 4]) for i in range(4)]
    segs += [(corners[a], sq[b]) for a, b in [(0, 3), (0, 0), (1, 0), (1, 1), (2, 1), (2, 2), (3, 2), (3, 3)]]
    return _u(segs)


def frog_segments() -> list:
    """Frog base: a preliminary base whose four flaps are squash- and petal-folded.

    Each quadrant of the sheet carries a bird-base-like pattern around its own
    diagonal; built as the 2x2 mirror tiling of the bird base's quarter structure."""
    return tile_segments([[("bird", False, False), ("bird", True, False)],
                          [("bird", False, True), ("bird", True, True)]])


MODULES = {
    "bird": bird_segments,
}


_MODULE_CACHE: dict[str, list] = {}


def module_segments(name: str) -> list:
    """Certified, M/V-assigned crease segments of a module on the unit square."""
    if name not in _MODULE_CACHE:
        if name == "bird":
            cp = complete_assignment(CreasePattern.from_segments(bird_segments(), tol=1e-9))
        else:
            from .. import reference as R

            cp = R.REFERENCE[name][0]()
        _MODULE_CACHE[name] = [(p, q, a) for p, q, a in cp.segments()]
    return _MODULE_CACHE[name]


def _transform(segs, x0, y0, s, flip_x, flip_y):
    """Place a module; a mirrored copy folds onto its neighbour upside down, so its
    mountains and valleys swap (once per mirror)."""
    swap = flip_x != flip_y
    out = []
    for p, q, a in segs:
        if swap and a in "MV":
            a = "V" if a == "M" else "M"
        pts = []
        for x, y in (p, q):
            if flip_x:
                x = 1 - x
            if flip_y:
                y = 1 - y
            pts.append((x0 + s * x, y0 + s * y))
        out.append((pts[0], pts[1], a))
    return out


def tile_segments(cells: list[list[tuple[str, bool, bool]]], fold_boundaries: bool = True,
                  free_seams: bool = True) -> list:
    """Place module CPs in an n x n grid (cell (i, j) = row i from the bottom, column j),
    each optionally mirrored, and add the cell boundaries as (unassigned) creases.

    With ``free_seams`` the module creases that touch a cell boundary are left
    unassigned too, so the solver can re-balance the seam vertices."""
    n = len(cells)
    s = 1.0 / n
    segs = []

    def on_seam(p):
        return any(abs(c * n - round(c * n)) < 1e-9 and 1e-9 < c < 1 - 1e-9 for c in p)

    for i, row in enumerate(cells):
        for j, (name, fx, fy) in enumerate(row):
            for p, q, a in _transform(module_segments(name), j * s, i * s, s, fx, fy):
                if free_seams and (on_seam(p) or on_seam(q)):
                    a = "U"
                segs.append((p, q, a))
    if fold_boundaries:
        for k in range(1, n):
            segs.append(((k * s, 0.0), (k * s, 1.0), "U"))
            segs.append(((0.0, k * s), (1.0, k * s), "U"))
    return segs


def mirror_cells(name: str, n: int) -> list:
    """n x n mirror tiling of a module: neighbouring cells are reflections of each other,
    so creases meet consistently across cell boundaries."""
    return [[(name, j % 2 == 1, i % 2 == 1) for j in range(n)] for i in range(n)]


def mirror_tiling(name: str, n: int) -> list:
    return tile_segments(mirror_cells(name, n), free_seams=False)


def certify(segs, timeout: float = 60.0) -> CreasePattern | None:
    cp = CreasePattern.from_segments(segs, tol=1e-9)
    if cp.warnings:
        return None
    return complete_assignment(cp, timeout=timeout)


def bird_base() -> CreasePattern:
    cp = certify(bird_segments())
    assert cp is not None
    return cp


def random_cells(n: int, rng: np.random.Generator, names=("bird", "preliminary_base", "waterbomb_base",
                                                           "fish_base", "blintz")) -> list:
    return [[(str(rng.choice(names)), bool(rng.integers(2)), bool(rng.integers(2))) for _ in range(n)]
            for _ in range(n)]


def random_tiling(n: int, rng: np.random.Generator, **kw) -> tuple[list, list]:
    cells = random_cells(n, rng, **kw)
    return tile_segments(cells), cells


def certify_tiling(cells, timeout: float = 60.0) -> CreasePattern | None:
    """Certify a tiling, first with the modules' own assignments at the seams, then with
    the seam creases left for the solver to re-balance."""
    for free in (False, True):
        cp = certify(tile_segments(cells, free_seams=free), timeout=timeout)
        if cp is not None:
            return cp
    return None
