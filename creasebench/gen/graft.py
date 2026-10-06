"""Grafting: insert strips of paper into an existing crease pattern (Lang, ODS ch. "Grafting").

A strip graft cuts the pattern along a line L and inserts a strip of width w. Creases
crossing L continue straight across the strip (this preserves flat-foldability when
they cross L at right angles); creases lying on L are duplicated on both sides of the
strip. To keep the sheet square we always graft one vertical and one horizontal
strip of the same width and rescale by 1/(1+w). The square where the two strips
cross is a *point graft* site: it can be left plain or filled with a module (e.g. a
waterbomb or preliminary base), which adds a new flap.

Newly created creases are left unassigned and the flat-foldability solver assigns
them; any graft that cannot fold flat is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..cp import CreasePattern
from ..verify import complete_assignment


@dataclass
class Graft:
    x: float  # vertical cut line x = x (base coordinates)
    y: float  # horizontal cut line y = y
    w: float  # strip width (base units)
    point_module: str | None = None  # module placed in the crossing square

    @property
    def scale(self) -> float:
        return 1.0 / (1.0 + self.w)

    def pieces(self) -> list[dict]:
        """Piecewise map from base to grafted coordinates (for graft_preserved)."""
        s, x, y, w = self.scale, self.x, self.y, self.w
        out = []
        for (x0, x1, dx) in ((0, x, 0.0), (x, 1, w)):
            for (y0, y1, dy) in ((0, y, 0.0), (y, 1, w)):
                out.append({"region": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "scale": s,
                            "offset": [s * dx, s * dy]})
        return out

    def to_json(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "point_module": self.point_module,
                "scale": self.scale, "pieces": self.pieces()}


def _split_axis(segs, axis: int, c: float, w: float, eps: float = 1e-12):
    """Insert a strip of width w at coordinate c along ``axis`` (0 = x, 1 = y)."""
    out = []
    for p, q, a in segs:
        p, q = list(p), list(q)
        lo, hi = sorted([p[axis], q[axis]])
        if hi <= c + eps and not (abs(lo - c) < eps and abs(hi - c) < eps):
            out.append((tuple(p), tuple(q), a))
        elif lo >= c - eps and not (abs(lo - c) < eps and abs(hi - c) < eps):
            p[axis] += w
            q[axis] += w
            out.append((tuple(p), tuple(q), a))
        elif abs(lo - c) < eps and abs(hi - c) < eps:
            # crease lying on the cut line: one copy on each side of the strip
            out.append((tuple(p), tuple(q), a))
            p2, q2 = list(p), list(q)
            p2[axis] += w
            q2[axis] += w
            out.append((tuple(p2), tuple(q2), "U"))
        else:
            # crease crossing the cut: split it and bridge the strip
            t = (c - p[axis]) / (q[axis] - p[axis])
            m = [p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])]
            m[axis] = c
            m2 = list(m)
            m2[axis] = c + w
            first, second = (p, q) if p[axis] < q[axis] else (q, p)
            second = list(second)
            second[axis] += w
            out.append((tuple(first), tuple(m), a))
            out.append((tuple(m2), tuple(second), a))
            out.append((tuple(m), tuple(m2), a))
    return out


def graft(base: CreasePattern, g: Graft, timeout: float = 60.0) -> CreasePattern | None:
    segs = [(p, q, a) for p, q, a in base.segments()]
    segs = _split_axis(segs, 0, g.x, g.w)
    segs = _split_axis(segs, 1, g.y, g.w)
    if g.point_module is not None:
        from .bases22 import _transform, module_segments

        mod = [(p, q, "U") for p, q, _ in module_segments(g.point_module)]
        segs += _transform(mod, g.x, g.y, g.w, False, False)
    s = g.scale
    segs = [((p[0] * s, p[1] * s), (q[0] * s, q[1] * s), a) for p, q, a in segs]
    cp = CreasePattern.from_segments(segs, tol=1e-9)
    if cp.warnings and any("conflicting" in w for w in cp.warnings):
        return None
    return complete_assignment(cp, timeout=timeout)


def candidate_lines(base: CreasePattern, axis: int, tol: float = 1e-9) -> list[float]:
    """Cut positions where every crease crossing the line is perpendicular to it."""
    import numpy as np

    coords = sorted({round(float(v), 9) for v in base.vertices[:, axis] if tol < v < 1 - tol})
    out = []
    for c in coords:
        ok = True
        for (u, v), a in zip(base.edges, base.assignments):
            if a == "B":
                continue
            pu, pv = base.vertices[u], base.vertices[v]
            lo, hi = sorted([pu[axis], pv[axis]])
            if lo < c - tol and hi > c + tol:
                d = pv - pu
                if abs(d[1 - axis]) > 1e-9:  # not perpendicular to the line
                    ok = False
                    break
        if ok:
            # vertices lying on the line may only carry creases perpendicular to it
            for vi, pv in enumerate(base.vertices):
                if abs(pv[axis] - c) > tol or not (tol < pv[1 - axis] < 1 - tol):
                    continue
                for (a, b), asg in zip(base.edges, base.assignments):
                    if asg == "B" or vi not in (a, b):
                        continue
                    d = base.vertices[b] - base.vertices[a]
                    if abs(d[1 - axis]) > 1e-9 and abs(d[axis]) > 1e-9:
                        ok = False
                        break
                if not ok:
                    break
        if ok:
            out.append(c)
    return out


def border_graft(base: CreasePattern, w: float, fold_old_border: bool = False,
                 timeout: float = 60.0) -> CreasePattern | None:
    """Add a border of width w all around (then rescale to the unit square).

    Creases that reach the old edge are extended straight to the new edge. With
    ``fold_old_border`` the old edge becomes an (unassigned) crease, so the new margin can
    be folded back -- the classic way to get a colour change along flap edges."""
    s = 1.0 / (1.0 + 2 * w)
    segs = []
    for p, q, a in base.segments():
        p2, q2 = list(p), list(q)
        for end, other in ((p2, q), (q2, p)):
            on_edge = min(end[0], end[1], 1 - end[0], 1 - end[1]) < 1e-9
            if on_edge:
                d = (end[0] - other[0], end[1] - other[1])
                L = (d[0] ** 2 + d[1] ** 2) ** 0.5
                end[0] += d[0] / L * 3 * w
                end[1] += d[1] / L * 3 * w  # clipped to the new sheet by from_segments
        segs.append(((p2[0], p2[1]), (q2[0], q2[1]), a))
    segs = [(((x0 + w) * s, (y0 + w) * s), ((x1 + w) * s, (y1 + w) * s), a)
            for (x0, y0), (x1, y1), a in segs]
    if fold_old_border:
        lo, hi = w * s, (1 + w) * s
        corners = [(lo, lo), (hi, lo), (hi, hi), (lo, hi)]
        segs += [(corners[i], corners[(i + 1) % 4], "U") for i in range(4)]
    cp = CreasePattern.from_segments(segs, tol=1e-9)
    return complete_assignment(cp, timeout=timeout)
