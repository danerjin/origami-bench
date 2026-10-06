"""Local flat-foldability checks (Maekawa and Kawasaki) at interior vertices."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .cp import FOLDED_ASSIGNMENTS, CreasePattern, is_boundary_vertex


@dataclass
class VertexViolation:
    vertex: int
    rule: str  # "kawasaki" | "maekawa" | "odd_degree"
    detail: str

    def to_dict(self) -> dict:
        return {"vertex": self.vertex, "rule": self.rule, "detail": self.detail}


@dataclass
class LocalReport:
    violations: list[VertexViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def bad_vertices(self) -> set[int]:
        return {v.vertex for v in self.violations}


def vertex_creases(cp: CreasePattern) -> dict[int, list[tuple[float, str]]]:
    """For every vertex, the (angle, assignment) of each incident folded crease."""
    out: dict[int, list[tuple[float, str]]] = {i: [] for i in range(cp.num_vertices)}
    for (u, v), a in zip(cp.edges, cp.assignments):
        if a not in FOLDED_ASSIGNMENTS:
            continue
        pu, pv = cp.vertices[u], cp.vertices[v]
        out[u].append((math.atan2(pv[1] - pu[1], pv[0] - pu[0]), a))
        out[v].append((math.atan2(pu[1] - pv[1], pu[0] - pv[0]), a))
    return out


def check_local(cp: CreasePattern, angle_tol: float = 5e-3) -> LocalReport:
    rep = LocalReport()
    for vi, creases in vertex_creases(cp).items():
        if not creases or is_boundary_vertex(cp.vertices[vi]):
            continue
        creases.sort()
        n = len(creases)
        if n % 2:
            rep.violations.append(VertexViolation(vi, "odd_degree", f"{n} creases meet here"))
            continue
        sectors = [(creases[(i + 1) % n][0] - creases[i][0]) % (2 * math.pi) for i in range(n)]
        if n == 2:
            # two creases must be collinear (a straight crease through the vertex)
            alt = sectors[0] - sectors[1]
        else:
            alt = sum(s if i % 2 == 0 else -s for i, s in enumerate(sectors))
        if abs(alt) > angle_tol:
            rep.violations.append(VertexViolation(
                vi, "kawasaki", f"alternating angle sum is {math.degrees(alt):.3f} deg, not 0"))
        asg = [a for _, a in creases]
        if "U" not in asg:
            m, v = asg.count("M"), asg.count("V")
            if abs(m - v) != 2:
                rep.violations.append(VertexViolation(vi, "maekawa", f"M={m}, V={v}; |M-V| must be 2"))
            elif abs(alt) <= angle_tol and not crimp_foldable(sectors, asg):
                rep.violations.append(VertexViolation(
                    vi, "big_little_big", "no valid crimp sequence (a locally smallest sector is "
                    "bounded by two creases of the same type)"))
    return rep


def crimp_foldable(sectors: list[float], asg: list[str], tol: float = 1e-6) -> bool:
    """Single-vertex flat-foldability with an M/V assignment (crimping / big-little-big).

    ``sectors[i]`` is the angle between crease i and crease i+1 (cyclically); ``asg[i]`` is
    crease i's assignment. Repeatedly crimp a sector that is no larger than both neighbours
    and bounded by opposite creases; the vertex folds flat iff this reduces to two sectors
    bounded by equal creases. (Algorithm as in Demaine & O'Rourke; cf. COrigami Alg. 1.)
    """
    secs = list(sectors)
    left = list(asg)  # crease before sector i
    right = [asg[(i + 1) % len(asg)] for i in range(len(asg))]  # crease after sector i
    while len(secs) > 2:
        n = len(secs)
        for i in range(n):
            if (left[i] != right[i] and secs[i] <= secs[i - 1] + tol
                    and secs[i] <= secs[(i + 1) % n] + tol):
                j, k = (i - 1) % n, (i + 1) % n
                secs[j] = secs[j] - secs[i] + secs[k]
                right[j] = right[k]
                for idx in sorted({i, k}, reverse=True):
                    del secs[idx], left[idx], right[idx]
                break
        else:
            return False
    return len(secs) == 2 and left[0] == right[0] == left[1] == right[1]
