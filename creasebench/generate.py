"""Procedural generation of flat-foldable crease patterns from random simple folds.

A *simple fold* folds every layer along one straight line. Any sequence of
simple folds is physically realisable, so the resulting crease pattern is
flat-foldable by construction and its folded state and a valid layer order are
known exactly. This gives an unbounded, contamination-resistant supply of
analytic-folding tasks with tunable difficulty (number of folds).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.ops import split, unary_union

from .cp import CreasePattern


@dataclass
class Facet:
    paper: Polygon  # region of the original square
    A: np.ndarray  # paper -> folded linear part
    b: np.ndarray

    def folded(self) -> Polygon:
        return _apply(self.paper, self.A, self.b)


@dataclass
class FoldStep:
    p: tuple[float, float]
    q: tuple[float, float]
    kind: str  # "V" or "M" as seen from the viewer of the folded state
    description: str


@dataclass
class Generated:
    cp: CreasePattern
    steps: list[FoldStep]
    face_above: list[tuple[int, int]]  # a valid layer order (CP face indices), generator frame
    face_flipped: list[bool]  # per CP face, in the generator frame

    def face_above_in_frame(self, folded) -> list[tuple[int, int]]:
        """Layer order expressed in the frame of a ``FoldedState`` (which may be flipped over)."""
        r = folded.root_face
        if folded.face_flipped(r) == self.face_flipped[r]:
            return list(self.face_above)
        return [(b, a) for a, b in self.face_above]


def _apply(poly: Polygon, A: np.ndarray, b: np.ndarray) -> Polygon:
    return affinity.affine_transform(poly, [A[0, 0], A[0, 1], A[1, 0], A[1, 1], b[0], b[1]])


def _reflection(p, q):
    p, q = np.asarray(p, float), np.asarray(q, float)
    d = (q - p) / np.linalg.norm(q - p)
    R = 2 * np.outer(d, d) - np.eye(2)
    return R, p - R @ p


def _side(p, q, pt) -> float:
    return (q[0] - p[0]) * (pt[1] - p[1]) - (q[1] - p[1]) * (pt[0] - p[0])


class SimpleFolder:
    def __init__(self) -> None:
        self.facets = [Facet(Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]), np.eye(2), np.zeros(2))]
        self.order = [0]  # bottom -> top
        self.creases: list[tuple[tuple, tuple, str]] = []

    def silhouette(self):
        return unary_union([f.folded().buffer(1e-9) for f in self.facets]).buffer(-1e-9)

    def fold(self, p, q, kind: str, move_side: int) -> bool:
        """Fold every layer on side ``move_side`` (+1 left / -1 right of p->q) over the line."""
        p, q = np.asarray(p, float), np.asarray(q, float)
        d = (q - p) / np.linalg.norm(q - p)
        big = LineString([p - 10 * d, q + 10 * d])
        R, t = _reflection(p, q)
        new_facets: list[Facet] = []
        moving: list[int] = []
        staying: list[int] = []
        new_creases = []
        for idx in self.order:
            f = self.facets[idx]
            F = f.folded()
            pieces = list(split(F, big).geoms) if F.intersects(big) else [F]
            pieces = [g for g in pieces if g.area > 1e-10]
            Ainv = np.linalg.inv(f.A)
            binv = -Ainv @ f.b
            for g in pieces:
                c = g.representative_point()
                s = 1 if _side(p, q, (c.x, c.y)) > 0 else -1
                paper_piece = _apply(g, Ainv, binv)
                if s == move_side:
                    nf = Facet(paper_piece, R @ f.A, R @ f.b + t)
                    moving.append(len(new_facets))
                else:
                    nf = Facet(paper_piece, f.A, f.b)
                    staying.append(len(new_facets))
                new_facets.append(nf)
            if len(pieces) > 1:
                seg = F.intersection(big)
                flipped = np.linalg.det(f.A) < 0
                asg = kind if not flipped else ("M" if kind == "V" else "V")
                for part in getattr(seg, "geoms", [seg]):
                    if part.geom_type != "LineString" or part.length < 1e-9:
                        continue
                    pp = _apply(part, Ainv, binv).coords
                    new_creases.append((tuple(pp[0]), tuple(pp[-1]), asg))
        if not moving or not staying:
            return False
        self.facets = new_facets
        if kind == "V":
            self.order = staying + moving[::-1]
        else:
            self.order = moving[::-1] + staying
        self.creases += new_creases
        return True

    def to_generated(self, steps) -> Generated:
        cp = CreasePattern.from_segments(self.creases)
        # map CP faces to facets
        face_to_facet = []
        for fi, face in enumerate(cp.faces):
            c = Polygon(cp.vertices[face]).representative_point()
            match = [k for k, f in enumerate(self.facets) if f.paper.buffer(1e-9).contains(c)]
            if len(match) != 1:
                raise RuntimeError("could not match CP face to facet")
            face_to_facet.append(match[0])
        rank = {fac: r for r, fac in enumerate(self.order)}
        polys = [self.facets[face_to_facet[i]].folded().buffer(-1e-6) for i in range(len(cp.faces))]
        above = []
        for i in range(len(cp.faces)):
            for j in range(i + 1, len(cp.faces)):
                if polys[i].intersection(polys[j]).area > 1e-9:
                    ri, rj = rank[face_to_facet[i]], rank[face_to_facet[j]]
                    above.append((i, j) if ri > rj else (j, i))
        flipped = [bool(np.linalg.det(self.facets[face_to_facet[i]].A) < 0) for i in range(len(cp.faces))]
        return Generated(cp, steps, above, flipped)


def _candidate_points(sil) -> list[np.ndarray]:
    geoms = getattr(sil, "geoms", [sil])
    pts = []
    for g in geoms:
        ring = np.array(g.exterior.coords[:-1])
        n = len(ring)
        for i in range(n):
            pts.append(ring[i])
            pts.append((ring[i] + ring[(i + 1) % n]) / 2)
    return pts


def random_simple_folds(n_folds: int, seed: int, max_tries: int = 400,
                        min_face_area: float = 2e-3, min_edge: float = 0.02) -> Generated:
    rng = random.Random(seed)
    for _attempt in range(50):
        sf = SimpleFolder()
        steps: list[FoldStep] = []
        tries = 0
        while len(steps) < n_folds and tries < max_tries:
            tries += 1
            sil = sf.silhouette()
            pts = _candidate_points(sil)
            a, b = rng.sample(range(len(pts)), 2)
            A, B = pts[a], pts[b]
            if np.linalg.norm(A - B) < 0.05:
                continue
            if rng.random() < 0.5:
                p, q = A, B  # fold through two points
                desc = "line through two reference points"
            else:
                m = (A + B) / 2  # perpendicular bisector: fold point A onto point B
                d = B - A
                nrm = np.array([-d[1], d[0]])
                p, q = m - nrm, m + nrm
                desc = "fold one reference point onto another"
            big = LineString([p - 10 * (q - p), q + 10 * (q - p)])
            parts = list(split(sil, big).geoms) if sil.intersects(big) else []
            if len(parts) < 2:
                continue
            areas = sorted(g.area for g in parts)
            if areas[0] < 0.08 * sil.area:
                continue
            # move the smaller side (as a folder usually would)
            small = min(parts, key=lambda g: g.area).representative_point()
            move_side = 1 if _side(p, q, (small.x, small.y)) > 0 else -1
            kind = rng.choice("VM")
            snapshot = (list(sf.facets), list(sf.order), list(sf.creases))
            if not sf.fold(p, q, kind, move_side):
                continue
            try:
                g = sf.to_generated(steps)
            except RuntimeError:
                sf.facets, sf.order, sf.creases = snapshot
                continue
            if _degenerate(g.cp, min_face_area, min_edge):
                sf.facets, sf.order, sf.creases = snapshot
                continue
            steps.append(FoldStep(tuple(map(float, p)), tuple(map(float, q)), kind, desc))
        if len(steps) == n_folds:
            return sf.to_generated(steps)
    raise RuntimeError(f"could not generate a {n_folds}-fold pattern (seed {seed})")


def _degenerate(cp: CreasePattern, min_face_area: float, min_edge: float) -> bool:
    from .cp import face_area

    if any(face_area(cp, f) < min_face_area for f in range(len(cp.faces))):
        return True
    for (u, v), a in zip(cp.edges, cp.assignments):
        if np.linalg.norm(cp.vertices[u] - cp.vertices[v]) < min_edge:
            return True
    return False


def _fold_smaller_side(sf: SimpleFolder, p, q, kind: str) -> bool:
    sil = sf.silhouette()
    big = LineString([p - 10 * (q - p), q + 10 * (q - p)])
    parts = list(split(sil, big).geoms) if sil.intersects(big) else []
    if len(parts) < 2:
        return False
    small = min(parts, key=lambda g: g.area).representative_point()
    return sf.fold(p, q, kind, 1 if _side(p, q, (small.x, small.y)) > 0 else -1)


def search_symmetric(check, seed: int, tries: int = 20000) -> CreasePattern | None:
    """Random search over mirror-symmetric simple-fold sequences (about x = 0.5) for a
    folded silhouette satisfying ``check``. Used to prove design tasks are solvable."""
    rng = random.Random(seed)
    mirror = lambda p: np.array([1 - p[0], p[1]])  # noqa: E731
    for _ in range(tries):
        sf = SimpleFolder()
        ok = True
        for _step in range(rng.randint(1, 4)):
            pts = _candidate_points(sf.silhouette())
            if rng.random() < 0.25:  # a self-symmetric horizontal fold
                y = rng.choice([0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875])
                ok = _fold_smaller_side(sf, np.array([0.0, y]), np.array([1.0, y]), rng.choice("VM"))
            else:  # a fold on the left half and its mirror image
                left = [p for p in pts if p[0] < 0.5 - 1e-6]
                if not left:
                    ok = False
                    break
                A = left[rng.randrange(len(left))]
                B = (left[rng.randrange(len(left))] if rng.random() < 0.7
                     else np.array([0.5, rng.choice([0, 0.25, 0.5, 0.75, 1.0])]))
                if np.linalg.norm(A - B) < 0.05:
                    ok = False
                    break
                if rng.random() < 0.5:  # fold A onto B instead of folding through them
                    m, d = (A + B) / 2, B - A
                    A, B = m - np.array([-d[1], d[0]]), m + np.array([-d[1], d[0]])
                kind = rng.choice("VM")
                ok = _fold_smaller_side(sf, A, B, kind) and _fold_smaller_side(sf, mirror(A), mirror(B), kind)
            if not ok:
                break
        if ok and check(sf.silhouette()):
            g = sf.to_generated([])
            if not _degenerate(g.cp, 1e-4, 1e-3):
                return g.cp
    return None
