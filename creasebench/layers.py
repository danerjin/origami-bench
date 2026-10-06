"""Global flat-foldability: solving for a valid layer order.

Variables: for every pair of faces whose folded images overlap, which one is
on top. Constraints (cf. Jason Ku's *flat-folder* / Demaine & O'Rourke):

* crease:      the M/V assignment fixes the order of the two faces at a crease;
* transitivity: three faces with a common overlap are ordered acyclically;
* taco-tortilla: a face spanning across a folded crease cannot lie between
                 the two faces joined at that crease;
* taco-taco:    two coincident creases folded to the same side must nest or
                be disjoint, never interleave.

"Above" always means the +z direction of the folded frame, where the root face
keeps the paper's top side facing up and a valley fold brings paper up.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from .cp import FOLDED_ASSIGNMENTS, CreasePattern
from .sat import SAT
from .simulate import FoldedState

SHRINK = 5e-5  # robust to ~1e-5 coordinate noise; generated faces are much larger
AREA_EPS = 1e-8


@dataclass
class LayerProblem:
    sat: SAT
    pair_var: dict[tuple[int, int], int]  # (i, j) with i < j -> var meaning "i above j"
    mv_var: dict[int, int]  # edge index -> var meaning "valley" (only for U edges)
    stats: dict = field(default_factory=dict)

    def lit_above(self, a: int, b: int) -> int | None:
        """Literal for "a above b", or None if the faces don't overlap."""
        if a < b:
            v = self.pair_var.get((a, b))
            return v
        v = self.pair_var.get((b, a))
        return -v if v else None


@dataclass
class LayerResult:
    status: str  # "found" | "none" | "budget"
    face_above: list[tuple[int, int]] = field(default_factory=list)
    assignments: list[str] | None = None  # with U edges resolved
    stats: dict = field(default_factory=dict)


def _perm_patterns(k: int, allowed) -> set[tuple[bool, ...]]:
    pairs = list(itertools.combinations(range(k), 2))
    pats = set()
    for perm in itertools.permutations(range(k)):  # perm[0] is the top
        rank = {f: i for i, f in enumerate(perm)}
        if allowed(rank):
            pats.add(tuple(rank[i] < rank[j] for i, j in pairs))
    return pats


def _forbidden(k: int, allowed) -> list[tuple[bool, ...]]:
    ok = _perm_patterns(k, allowed)
    return [p for p in itertools.product((True, False), repeat=k * (k - 1) // 2) if p not in ok]


def _between(r, x, a, b) -> bool:
    return min(r[a], r[b]) < r[x] < max(r[a], r[b])


FORBID_TRANS = _forbidden(3, lambda r: True)
FORBID_TORTILLA = _forbidden(3, lambda r: not _between(r, 2, 0, 1))  # roles (a, b, t)
FORBID_TACOTACO = _forbidden(4, lambda r: _between(r, 2, 0, 1) == _between(r, 3, 0, 1))  # (a,b,c,d)


def _add_template(prob: LayerProblem, faces: tuple[int, ...], forbidden) -> bool:
    lits = []
    for i, j in itertools.combinations(range(len(faces)), 2):
        lit = prob.lit_above(faces[i], faces[j])
        if lit is None:
            return False
        lits.append(lit)
    for pat in forbidden:
        prob.sat.add_clause([-l if bit else l for l, bit in zip(lits, pat)])
    return True


def build_problem(folded: FoldedState) -> LayerProblem:
    cp = folded.cp
    nf = len(cp.faces)
    polys = [p.buffer(-SHRINK) for p in folded.face_polygons()]
    tree = STRtree(polys)
    sat = SAT()
    prob = LayerProblem(sat, {}, {})
    overlap: dict[int, set[int]] = {i: set() for i in range(nf)}
    inter: dict[tuple[int, int], object] = {}
    for i in range(nf):
        for j in tree.query(polys[i]):
            j = int(j)
            if j <= i:
                continue
            g = polys[i].intersection(polys[j])
            if g.area > AREA_EPS:
                prob.pair_var[(i, j)] = sat.new_var()
                overlap[i].add(j)
                overlap[j].add(i)
                inter[(i, j)] = g
    # crease constraints
    eidx = cp.edge_index()
    ef = cp.edge_faces()
    creases = []  # (edge index, face a, face b, folded LineString)
    for key, fs in ef.items():
        if len(fs) != 2:
            continue
        ei = eidx[key]
        asg = cp.assignments[ei]
        if asg not in FOLDED_ASSIGNMENTS:
            continue
        a, b = fs
        seg = LineString(folded.transform(a, cp.vertices[list(key)]))
        creases.append((ei, a, b, seg))
        lit_b_above_a = prob.lit_above(b, a)
        if lit_b_above_a is None:
            continue  # degenerate (zero-area face)
        # valley & a face-up  <=>  b above a
        sign = -1 if folded.face_flipped(a) else 1
        if asg == "U":
            mv = sat.new_var()
            prob.mv_var[ei] = mv
            sat.add_clause([-mv, sign * lit_b_above_a])
            sat.add_clause([mv, -sign * lit_b_above_a])
        else:
            sat.add_clause([(sign if asg == "V" else -sign) * lit_b_above_a])
    # transitivity
    ntrans = 0
    for i in range(nf):
        for j in sorted(x for x in overlap[i] if x > i):
            gij = inter[(i, j)]
            for k in sorted(x for x in overlap[i] & overlap[j] if x > j):
                if gij.intersection(polys[k]).area > AREA_EPS:
                    _add_template(prob, (i, j, k), FORBID_TRANS)
                    ntrans += 1
    # taco-tortilla
    ntt = 0
    for ei, a, b, seg in creases:
        for t in tree.query(seg):
            t = int(t)
            if t in (a, b) or t not in overlap[a] or t not in overlap[b]:
                continue
            piece = seg.intersection(polys[t])
            if piece.length > SHRINK:
                if _add_template(prob, (a, b, t), FORBID_TORTILLA):
                    ntt += 1
    # taco-taco
    ntaco = 0
    for (e1, a, b, s1), (e2, c, d, s2) in itertools.combinations(creases, 2):
        if len({a, b, c, d}) < 4:
            continue
        mid = _collinear_overlap_mid(s1, s2)
        if mid is None:
            continue
        # point slightly to a's side of the shared line
        side_pt = _side_point(s1, mid, polys[a])
        if side_pt is None or not polys[c].contains(side_pt):
            continue
        if _add_template(prob, (a, b, c, d), FORBID_TACOTACO):
            ntaco += 1
    prob.stats = {"faces": nf, "pairs": len(prob.pair_var), "transitivity": ntrans,
                  "taco_tortilla": ntt, "taco_taco": ntaco, "clauses": len(sat.clauses)}
    return prob


def _collinear_overlap_mid(s1: LineString, s2: LineString, tol: float = SHRINK):
    p1, q1 = np.array(s1.coords[0]), np.array(s1.coords[-1])
    p2, q2 = np.array(s2.coords[0]), np.array(s2.coords[-1])
    d = q1 - p1
    L = np.linalg.norm(d)
    if L < 1e-12:
        return None
    u = d / L
    nrm = np.array([-u[1], u[0]])
    if abs(np.dot(p2 - p1, nrm)) > tol or abs(np.dot(q2 - p1, nrm)) > tol:
        return None
    t2 = sorted([np.dot(p2 - p1, u), np.dot(q2 - p1, u)])
    lo, hi = max(0.0, t2[0]), min(L, t2[1])
    if hi - lo < SHRINK:
        return None
    return p1 + u * (lo + hi) / 2


def _side_point(seg: LineString, mid, poly, delta: float = 2 * SHRINK):
    p, q = np.array(seg.coords[0]), np.array(seg.coords[-1])
    u = (q - p) / np.linalg.norm(q - p)
    nrm = np.array([-u[1], u[0]])
    for s in (1, -1):
        pt = Point(mid + s * delta * nrm)
        if poly.contains(pt):
            return pt
    return None


def solve_layers(folded: FoldedState, budget: int = 200_000,
                 extra_above: list[tuple[int, int]] | None = None,
                 problem: LayerProblem | None = None) -> LayerResult:
    prob = problem or build_problem(folded)
    assumptions = []
    if extra_above:
        for a, b in extra_above:
            lit = prob.lit_above(a, b)
            if lit is not None:
                assumptions.append(lit)
    res = prob.sat.solve(assumptions, budget=budget)
    stats = dict(prob.stats, decisions=res.decisions)
    if res.status != "sat":
        return LayerResult("none" if res.status == "unsat" else "budget", stats=stats)
    above = []
    for (i, j), v in prob.pair_var.items():
        above.append((i, j) if res.model[v] else (j, i))
    asg = list(folded.cp.assignments)
    for ei, v in prob.mv_var.items():
        asg[ei] = "V" if res.model[v] else "M"
    return LayerResult("found", above, asg, stats)


def check_claimed_order(folded: FoldedState, above: list[tuple[int, int]],
                        problem: LayerProblem | None = None, budget: int = 200_000) -> bool:
    """Is a (possibly partial) claimed layer order consistent with some valid flat folding?"""
    return solve_layers(folded, budget=budget, extra_above=above, problem=problem).status == "found"
