"""Flat-folding simulation: folded geometry from a crease pattern.

For a flat fold every crease is folded by +-180 degrees, so the folded position
of each face is obtained by composing reflections across the creases crossed
on a path from a root face. The geometry does not depend on the M/V assignment
(that only affects layer order, see ``layers.py``).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .cp import FOLDED_ASSIGNMENTS, CreasePattern, CPError, face_area


@dataclass
class FoldedState:
    cp: CreasePattern
    root_face: int
    face_A: list[np.ndarray]  # 2x2 linear part per face
    face_b: list[np.ndarray]  # translation per face
    vertices: np.ndarray  # (n, 2) folded vertex coordinates (averaged)
    consistency_error: float  # max disagreement between faces sharing a vertex

    def face_flipped(self, fi: int) -> bool:
        return bool(np.linalg.det(self.face_A[fi]) < 0)

    def transform(self, fi: int, pts: np.ndarray) -> np.ndarray:
        return pts @ self.face_A[fi].T + self.face_b[fi]

    def face_coords(self, fi: int) -> np.ndarray:
        return self.transform(fi, self.cp.vertices[self.cp.faces[fi]])

    def face_polygon(self, fi: int) -> Polygon:
        return Polygon(self.face_coords(fi)).buffer(0)

    def face_polygons(self) -> list[Polygon]:
        return [self.face_polygon(i) for i in range(len(self.cp.faces))]

    def silhouette(self):
        return unary_union([p.buffer(1e-9) for p in self.face_polygons()]).buffer(-1e-9)

    def to_fold(self, face_orders: list[tuple[int, int]] | None = None, precision: int = 8) -> dict:
        d = self.cp.to_fold(precision=precision)
        d["frame_classes"] = ["foldedForm"]
        d["vertices_coords"] = [[round(float(x), precision), round(float(y), precision)]
                                for x, y in self.vertices]
        d["creasebench:faces_flipped"] = [self.face_flipped(i) for i in range(len(self.cp.faces))]
        if face_orders is not None:
            d["creasebench:face_above"] = [[int(a), int(b)] for a, b in face_orders]
        return d


def _reflection(p: np.ndarray, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = q - p
    d = d / np.linalg.norm(d)
    R = 2 * np.outer(d, d) - np.eye(2)
    return R, p - R @ p


def fold(cp: CreasePattern, root_face: int | None = None) -> FoldedState:
    nf = len(cp.faces)
    if nf == 0:
        raise CPError("crease pattern has no faces")
    if root_face is None:
        # largest face; ties (common in symmetric patterns) go to the lowest index
        root_face = max(range(nf), key=lambda f: (round(face_area(cp, f), 6), -f))
    A: list[np.ndarray | None] = [None] * nf
    b: list[np.ndarray | None] = [None] * nf
    A[root_face], b[root_face] = np.eye(2), np.zeros(2)
    eidx = cp.edge_index()
    ef = cp.edge_faces()
    adj: dict[int, list[tuple[int, int, int]]] = {i: [] for i in range(nf)}
    for key, fs in ef.items():
        if len(fs) == 2:
            adj[fs[0]].append((fs[1], *key))
            adj[fs[1]].append((fs[0], *key))
    q = deque([root_face])
    while q:
        f = q.popleft()
        for g, u, v in adj[f]:
            if A[g] is not None:
                continue
            asg = cp.assignments[eidx[(u, v)]]
            if asg in FOLDED_ASSIGNMENTS:
                R, t = _reflection(cp.vertices[u], cp.vertices[v])
                A[g] = A[f] @ R
                b[g] = A[f] @ t + b[f]
            else:
                A[g], b[g] = A[f].copy(), b[f].copy()
            q.append(g)
    if any(a is None for a in A):
        raise CPError("crease pattern faces are not connected")
    sums = np.zeros_like(cp.vertices)
    counts = np.zeros(cp.num_vertices)
    positions: dict[int, list[np.ndarray]] = {}
    for fi, face in enumerate(cp.faces):
        pts = cp.vertices[face] @ A[fi].T + b[fi]
        for v, p in zip(face, pts):
            positions.setdefault(v, []).append(p)
            sums[v] += p
            counts[v] += 1
    counts[counts == 0] = 1
    verts = sums / counts[:, None]
    err = 0.0
    for v, ps in positions.items():
        err = max(err, max(float(np.linalg.norm(p - verts[v])) for p in ps))
    return FoldedState(cp, root_face, A, b, verts, err)  # type: ignore[arg-type]
