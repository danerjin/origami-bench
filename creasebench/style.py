"""Technique compliance: which design system a crease pattern lives in.

All checks are exact up to a small numeric tolerance:

* box pleating on an N-grid: crease directions in {0, 45, 90, 135} degrees and every
  vertex on the 1/N lattice;
* Pythagorean stretches (Lang; Lang & Tsai's GOPS): an otherwise box-pleated, rational
  pattern that additionally uses lattice directions coming from a Pythagorean triple
  (a, b, c): hypotenuse slopes b/a and bisector slopes b/(a+c), a/(b+c);
* 22.5-degree design: every direction a multiple of 22.5 degrees, coordinates in
  Z[sqrt2][1/2] (Tachi & Demaine, "Degenerative coordinates in 22.5 grid system");
* hex pleating: directions multiples of 30 degrees, coordinates in Q(sqrt3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

from .cp import CreasePattern

ANG_TOL = 1e-4  # degrees
COORD_TOL = 1e-6
SQRT2 = math.sqrt(2.0)
SQRT3 = math.sqrt(3.0)


def crease_directions(cp: CreasePattern) -> list[float]:
    out = []
    for (u, v), a in zip(cp.edges, cp.assignments):
        if a == "B":
            continue
        d = cp.vertices[v] - cp.vertices[u]
        out.append(math.degrees(math.atan2(d[1], d[0])) % 180.0)
    return out


def _multiple_of(angle: float, step: float) -> bool:
    r = angle / step
    return abs(r - round(r)) * step <= ANG_TOL or abs(angle - 180.0) <= ANG_TOL


def grid_size(cp: CreasePattern, max_n: int = 512) -> int | None:
    """Smallest N such that every vertex lies on the 1/N lattice (None if irrational)."""
    n = 1
    for x in cp.vertices.flatten():
        f = Fraction(float(x)).limit_denominator(max_n)
        if abs(float(f) - x) > COORD_TOL:
            return None
        n = n * f.denominator // math.gcd(n, f.denominator)
        if n > max_n:
            return None
    return n


def in_q_sqrt(x: float, root: float, max_pow2: int = 7, max_den: int = 12) -> bool:
    """Is x = (a + b*root) / d for small integers (d a power of two, or up to max_den)?"""
    dens = sorted({2 ** k for k in range(max_pow2 + 1)} | set(range(1, max_den + 1)))
    for d in dens:
        y = x * d
        for b in range(-2 * d, 2 * d + 1):
            a = y - b * root
            if abs(a - round(a)) <= COORD_TOL * d:
                return True
    return False


# primitive Pythagorean triples with c <= 65
def pythagorean_triples(cmax: int = 65) -> list[tuple[int, int, int]]:
    out = []
    for m in range(2, 10):
        for n in range(1, m):
            if (m - n) % 2 == 1 and math.gcd(m, n) == 1:
                a, b, c = m * m - n * n, 2 * m * n, m * m + n * n
                if c <= cmax:
                    out.append(tuple(sorted((a, b))) + (c,))
    return sorted(out, key=lambda t: t[2])


def stretch_slopes() -> dict[Fraction, tuple[int, int, int]]:
    """Map from lattice slope (in [0, inf)) to the triple it comes from."""
    table: dict[Fraction, tuple[int, int, int]] = {}
    for a, b, c in pythagorean_triples():
        for s in (Fraction(b, a), Fraction(a, b), Fraction(b, a + c), Fraction(a, b + c),
                  Fraction(a + c, b), Fraction(b + c, a)):
            table.setdefault(s, (a, b, c))
    return table


@dataclass
class StyleReport:
    directions: dict[str, int] = field(default_factory=dict)  # family -> crease count
    grid: int | None = None
    box_pleat: bool = False
    angles_22_5: bool = False
    field_sqrt2: bool = False
    hex: bool = False
    stretch_triples: list[tuple[int, int, int]] = field(default_factory=list)
    stretch_creases: int = 0
    other_creases: int = 0  # creases outside the box-pleating + stretch families

    @property
    def pythagorean_stretch(self) -> bool:
        return self.grid is not None and self.stretch_creases > 0 and self.other_creases == 0

    def to_json(self) -> dict:
        return {"grid": self.grid, "box_pleat": self.box_pleat, "angles_22_5": self.angles_22_5,
                "field_sqrt2": self.field_sqrt2, "hex": self.hex,
                "pythagorean_stretch": self.pythagorean_stretch,
                "stretch_triples": [list(t) for t in self.stretch_triples],
                "stretch_creases": self.stretch_creases, "other_creases": self.other_creases,
                "directions": self.directions}


def analyze(cp: CreasePattern) -> StyleReport:
    rep = StyleReport()
    dirs = crease_directions(cp)
    slopes = stretch_slopes()
    triples = set()
    for ang in dirs:
        if _multiple_of(ang, 45.0):
            fam = "bp45"
        elif _multiple_of(ang, 22.5):
            fam = "22.5"
        elif _multiple_of(ang, 30.0):
            fam = "hex30"
        else:
            t = math.tan(math.radians(ang))
            s = Fraction(abs(t)).limit_denominator(64)
            if abs(float(s) - abs(t)) < 1e-6 and s in slopes:
                fam = "stretch"
                triples.add(slopes[s])
            else:
                fam = "other"
        rep.directions[fam] = rep.directions.get(fam, 0) + 1
    rep.grid = grid_size(cp)
    n = len(dirs)
    bp = rep.directions.get("bp45", 0)
    rep.box_pleat = n > 0 and bp == n and rep.grid is not None
    rep.angles_22_5 = n > 0 and bp + rep.directions.get("22.5", 0) == n
    rep.field_sqrt2 = rep.angles_22_5 and all(in_q_sqrt(float(x), SQRT2) for x in np.unique(np.round(cp.vertices, 9)))
    rep.hex = (n > 0 and all(_multiple_of(a, 30.0) for a in dirs)
               and any(not _multiple_of(a, 90.0) for a in dirs))
    rep.stretch_creases = rep.directions.get("stretch", 0)
    rep.stretch_triples = sorted(triples)
    rep.other_creases = n - bp - rep.stretch_creases
    return rep


# ----------------------------------------------------------------------------- grafting
def graft_preserved(base: CreasePattern, answer: CreasePattern, pieces: list[dict], tol: float = 2e-3) -> float:
    """Fraction of the base's crease length found in the answer after the graft transform.

    ``pieces`` is a list of {"region": [[x, y], ...] (polygon in base coordinates),
    "scale": s, "offset": [dx, dy]}: base points p in the region map to s*p + offset.
    Creases must keep their assignment up to a global M/V swap (the graft may flip the
    paper over).
    """
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union

    ans = {"M": [], "V": []}
    for p, q, a in answer.segments():
        if a in ans:
            ans[a].append(LineString([p, q]))
    ans_u = {k: unary_union(v).buffer(tol) if v else None for k, v in ans.items()}
    total = 0.0
    hit = {False: 0.0, True: 0.0}  # swapped?
    for p, q, a in base.segments():
        if a not in "MV":
            continue
        seg = LineString([p, q])
        for pc in pieces:
            part = seg.intersection(Polygon(pc["region"]))
            if part.is_empty or part.length < 1e-9:
                continue
            s, (dx, dy) = pc["scale"], pc["offset"]
            from shapely import affinity
            mapped = affinity.translate(affinity.scale(part, s, s, origin=(0, 0)), dx, dy)
            total += mapped.length
            for swapped in (False, True):
                key = a if not swapped else ("V" if a == "M" else "M")
                if ans_u[key] is not None:
                    hit[swapped] += mapped.intersection(ans_u[key]).length
    return max(hit.values()) / total if total > 0 else 0.0
